"""
Role-Based Access Control (RBAC) for LabLink

Provides decorators and middleware for:
- Permission checking
- Role verification
- Resource-level access control
"""

import logging
from functools import wraps
from typing import Callable, List, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .auth import AuthConfig, decode_token
from .models import (AuthMethod, PermissionAction, ResourceType, TokenPayload,
                     User)

logger = logging.getLogger(__name__)

# Security scheme for Swagger UI
security_scheme = HTTPBearer()


# ============================================================================
# Dependency Injection for FastAPI
# ============================================================================


class RBACDependencies:
    """Dependencies for RBAC in FastAPI."""

    def __init__(self, config: AuthConfig, get_user_func: Callable):
        self.config = config
        self.get_user_func = get_user_func

    async def get_current_user(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    ) -> User:
        """
        Get the current authenticated user from JWT token.

        Raises:
            HTTPException: If authentication fails
        """
        token = credentials.credentials

        # Decode token
        token_payload = decode_token(token, self.config)
        if not token_payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Get user
        user = await self.get_user_func(token_payload.sub)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is disabled",
            )

        # Check if user is locked
        if user.locked_until and user.locked_until > datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is temporarily locked",
            )

        return user

    async def get_current_active_user(
        self,
        current_user: User = Depends(get_current_user),
    ) -> User:
        """Get current active user (convenience wrapper)."""
        return current_user

    async def get_current_superuser(
        self,
        current_user: User = Depends(get_current_user),
    ) -> User:
        """
        Get current user and verify they are a superuser.

        Raises:
            HTTPException: If user is not a superuser
        """
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Superuser access required",
            )
        return current_user


# ============================================================================
# Permission Checking
# ============================================================================


class PermissionChecker:
    """Checks permissions for users."""

    def __init__(self, get_role_func: Callable):
        """
        Initialize permission checker.

        Args:
            get_role_func: Async function to get role by ID
        """
        self.get_role_func = get_role_func

    async def has_permission(
        self,
        user: User,
        resource: ResourceType,
        action: PermissionAction,
        resource_id: Optional[str] = None,
    ) -> bool:
        """
        Check if user has a specific permission.

        Args:
            user: User to check
            resource: Resource type
            action: Action to perform
            resource_id: Specific resource ID (optional)

        Returns:
            True if user has permission
        """
        # Superuser always has permission
        if user.is_superuser:
            return True

        # Check each role
        for role_id in user.roles:
            role = await self.get_role_func(role_id)
            if not role:
                continue

            if role.has_permission(resource.value, action.value, resource_id):
                return True

        return False

    async def require_permission(
        self,
        user: User,
        resource: ResourceType,
        action: PermissionAction,
        resource_id: Optional[str] = None,
    ):
        """
        Require user to have permission, raise HTTPException if not.

        Args:
            user: User to check
            resource: Resource type
            action: Action to perform
            resource_id: Specific resource ID (optional)

        Raises:
            HTTPException: If user lacks permission
        """
        if not await self.has_permission(user, resource, action, resource_id):
            logger.warning(
                f"Access denied: user={user.username} resource={resource.value} "
                f"action={action.value} resource_id={resource_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {action.value} on {resource.value}",
            )

    def create_permission_dependency(
        self,
        resource: ResourceType,
        action: PermissionAction,
        resource_id: Optional[str] = None,
    ):
        """
        Create a FastAPI dependency for permission checking.

        Args:
            resource: Resource type
            action: Action to perform
            resource_id: Specific resource ID (optional)

        Returns:
            FastAPI dependency function
        """

        async def check_permission(user: User = Depends(get_current_user)):
            await self.require_permission(user, resource, action, resource_id)
            return user

        return check_permission


# ============================================================================
# Decorators
# ============================================================================


def require_auth(get_user_func: Callable, config: AuthConfig):
    """
    Decorator to require authentication for a route.

    Args:
        get_user_func: Function to get user by ID
        config: Auth configuration

    Returns:
        Decorator function
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, request: Request = None, **kwargs):
            # Extract token from Authorization header
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing or invalid authorization header",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            token = auth_header.split(" ")[1]

            # Decode token
            token_payload = decode_token(token, config)
            if not token_payload:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Get user
            user = await get_user_func(token_payload.sub)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Check if active
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User account is disabled",
                )

            # Add user to kwargs
            kwargs["current_user"] = user

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_permission(
    resource: ResourceType,
    action: PermissionAction,
    get_role_func: Callable,
    resource_id_param: Optional[str] = None,
):
    """
    Decorator to require specific permission for a route.

    Args:
        resource: Resource type
        action: Action to perform
        get_role_func: Function to get role by ID
        resource_id_param: Name of parameter containing resource ID

    Returns:
        Decorator function
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, current_user: User = None, **kwargs):
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )

            # Extract resource_id if specified
            resource_id = None
            if resource_id_param and resource_id_param in kwargs:
                resource_id = kwargs[resource_id_param]

            # Check permission
            checker = PermissionChecker(get_role_func)
            await checker.require_permission(
                current_user, resource, action, resource_id
            )

            return await func(*args, current_user=current_user, **kwargs)

        return wrapper

    return decorator


def require_role(role_name: str):
    """
    Decorator to require specific role for a route.

    Args:
        role_name: Name of required role

    Returns:
        Decorator function
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, current_user: User = None, **kwargs):
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )

            # Check if user has role
            if role_name not in current_user.roles and not current_user.is_superuser:
                logger.warning(
                    f"Access denied: user={current_user.username} required_role={role_name}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role '{role_name}' required",
                )

            return await func(*args, current_user=current_user, **kwargs)

        return wrapper

    return decorator


def require_superuser():
    """
    Decorator to require superuser access for a route.

    Returns:
        Decorator function
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, current_user: User = None, **kwargs):
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )

            if not current_user.is_superuser:
                logger.warning(f"Superuser access denied: user={current_user.username}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Superuser access required",
                )

            return await func(*args, current_user=current_user, **kwargs)

        return wrapper

    return decorator


# ============================================================================
# API Key Authentication
# ============================================================================


class APIKeyChecker:
    """Checks API keys for authentication."""

    def __init__(self, get_api_key_func: Callable, get_user_func: Callable):
        """
        Initialize API key checker.

        Args:
            get_api_key_func: Function to get API key
            get_user_func: Function to get user by ID
        """
        self.get_api_key_func = get_api_key_func
        self.get_user_func = get_user_func

    async def authenticate_api_key(self, key: str, ip_address: str) -> Optional[User]:
        """
        Authenticate using an API key.

        Args:
            key: API key string
            ip_address: Client IP address

        Returns:
            User if authentication successful, None otherwise
        """
        # Get API key
        api_key = await self.get_api_key_func(key)
        if not api_key:
            return None

        # Check if valid
        if not api_key.is_valid():
            return None

        # Get user
        user = await self.get_user_func(api_key.user_id)
        if not user or not user.is_active:
            return None

        # Update usage
        api_key.last_used = datetime.utcnow()
        api_key.last_used_ip = ip_address
        api_key.usage_count += 1

        return user

    async def check_api_key_scope(self, api_key, scope: str) -> bool:
        """
        Check if API key has specific scope.

        Args:
            api_key: APIKey object
            scope: Scope to check (e.g., "equipment:read")

        Returns:
            True if API key has scope
        """
        return api_key.has_scope(scope)


# ============================================================================
# IP Whitelisting
# ============================================================================


class IPWhitelistChecker:
    """Checks IP addresses against whitelist/blacklist."""

    def __init__(self, get_whitelist_func: Callable):
        """
        Initialize IP whitelist checker.

        Args:
            get_whitelist_func: Function to get all whitelist entries
        """
        self.get_whitelist_func = get_whitelist_func

    async def is_ip_allowed(self, ip_address: str) -> bool:
        """
        Check if IP address is allowed.

        Args:
            ip_address: IP address to check

        Returns:
            True if allowed
        """
        from ipaddress import ip_address as parse_ip
        from ipaddress import ip_network

        try:
            client_ip = parse_ip(ip_address)
        except ValueError:
            logger.error(f"Invalid IP address: {ip_address}")
            return False

        entries = await self.get_whitelist_func()

        # Check blacklist first
        for entry in entries:
            if not entry.is_whitelist:  # Blacklist entry
                try:
                    if "/" in entry.ip_address:
                        network = ip_network(entry.ip_address, strict=False)
                        if client_ip in network:
                            logger.warning(f"IP {ip_address} is blacklisted")
                            return False
                    else:
                        if str(client_ip) == entry.ip_address:
                            logger.warning(f"IP {ip_address} is blacklisted")
                            return False
                except ValueError:
                    continue

        # Check whitelist (if any whitelist entries exist)
        whitelist_entries = [e for e in entries if e.is_whitelist]
        if not whitelist_entries:
            return True  # No whitelist = all IPs allowed

        for entry in whitelist_entries:
            try:
                if "/" in entry.ip_address:
                    network = ip_network(entry.ip_address, strict=False)
                    if client_ip in network:
                        return True
                else:
                    if str(client_ip) == entry.ip_address:
                        return True
            except ValueError:
                continue

        logger.warning(f"IP {ip_address} not in whitelist")
        return False


# ============================================================================
# Helper Functions
# ============================================================================

from datetime import datetime


def extract_token_from_request(request: Request) -> Optional[str]:
    """Extract JWT token from request."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    return auth_header.split(" ")[1]


def extract_api_key_from_request(request: Request) -> Optional[str]:
    """Extract API key from request headers."""
    # Check X-API-Key header
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return api_key

    # Check Authorization header with API key format
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("ApiKey "):
        return auth_header.split(" ")[1]

    return None


def get_client_ip(request: Request) -> str:
    """Get client IP address from request."""
    # Check X-Forwarded-For header (if behind proxy)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fall back to direct client
    if request.client:
        return request.client.host

    return "unknown"
