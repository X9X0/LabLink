"""
Security API Endpoints for LabLink

Provides REST API for:
- Authentication (login, logout, token refresh)
- User management
- Role management
- API key management
- IP whitelisting
- Audit logging
- Security status
"""

from datetime import datetime
from typing import List, Optional
import logging

from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from security import (
    # Models
    User,
    UserCreate,
    UserUpdate,
    UserResponse,
    PasswordChange,
    PasswordReset,
    LoginRequest,
    TokenResponse,
    RefreshTokenRequest,
    Role,
    APIKey,
    APIKeyCreate,
    APIKeyResponse,
    IPWhitelistEntry,
    IPWhitelistCreate,
    AuditLogEntry,
    AuditLogQuery,
    SecurityStatus,
    SessionInfo,
    AuditEventType,

    # Manager
    get_security_manager,

    # Auth
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    verify_password,
    user_to_response,
)

from security.rbac import get_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/security")
security_scheme = HTTPBearer()


# ============================================================================
# Helper Functions
# ============================================================================

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme)
) -> User:
    """Get current authenticated user from token."""
    security_manager = get_security_manager()
    token = credentials.credentials

    from security.auth import decode_token
    token_payload = decode_token(token, security_manager.config)

    if not token_payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user = await security_manager.get_user(token_payload.sub)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


async def require_superuser(current_user: User = Depends(get_current_user)) -> User:
    """Require current user to be a superuser."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser access required",
        )
    return current_user


# ============================================================================
# Authentication Endpoints
# ============================================================================

@router.post("/login", response_model=TokenResponse, tags=["authentication"])
async def login(request: Request, login_request: LoginRequest):
    """
    Login with username and password.

    Returns JWT access token and optional refresh token.
    """
    security_manager = get_security_manager()
    ip_address = get_client_ip(request)

    # Check if account is locked
    if security_manager.attempt_tracker.is_locked_out(login_request.username):
        remaining = security_manager.attempt_tracker.get_lockout_time_remaining(login_request.username)
        await security_manager.audit_log(AuditLogEntry(
            event_type=AuditEventType.LOGIN_FAILED,
            username=login_request.username,
            ip_address=ip_address,
            success=False,
            error_message=f"Account locked for {remaining} seconds",
        ))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account temporarily locked. Try again in {remaining} seconds.",
        )

    # Get user
    user = await security_manager.get_user_by_username(login_request.username)

    if not user:
        # Record failed attempt
        security_manager.attempt_tracker.record_failed_attempt(login_request.username)
        await security_manager.audit_log(AuditLogEntry(
            event_type=AuditEventType.LOGIN_FAILED,
            username=login_request.username,
            ip_address=ip_address,
            success=False,
            error_message="User not found",
        ))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Verify password
    if not verify_password(login_request.password, user.hashed_password):
        # Record failed attempt
        attempts = security_manager.attempt_tracker.record_failed_attempt(login_request.username)
        await security_manager.audit_log(AuditLogEntry(
            event_type=AuditEventType.LOGIN_FAILED,
            user_id=user.user_id,
            username=user.username,
            ip_address=ip_address,
            success=False,
            error_message="Invalid password",
        ))

        remaining_attempts = security_manager.config.max_failed_login_attempts - attempts
        if remaining_attempts > 0:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid username or password. {remaining_attempts} attempts remaining.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed attempts. Account temporarily locked.",
            )

    # Check if user is active
    if not user.is_active:
        await security_manager.audit_log(AuditLogEntry(
            event_type=AuditEventType.LOGIN_FAILED,
            user_id=user.user_id,
            username=user.username,
            ip_address=ip_address,
            success=False,
            error_message="Account disabled",
        ))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # Clear failed attempts
    security_manager.attempt_tracker.clear_attempts(login_request.username)

    # Update last login
    from sqlite3 import connect
    conn = connect(str(security_manager.db_path))
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users SET last_login = ?, last_login_ip = ? WHERE user_id = ?
    """, (datetime.utcnow(), ip_address, user.user_id))
    conn.commit()
    conn.close()

    # Create tokens
    access_token = create_access_token(user, security_manager.config)
    refresh_token = create_refresh_token(user.user_id, security_manager.config)

    # Create session
    from security.models import AuthMethod as AuthMethodEnum
    session_id = security_manager.session_manager.create_session(
        user, ip_address,
        auth_method=AuthMethodEnum.PASSWORD,
        expires_in_minutes=security_manager.config.access_token_expire_minutes,
    )

    # Audit log
    await security_manager.audit_log(AuditLogEntry(
        event_type=AuditEventType.LOGIN_SUCCESS,
        user_id=user.user_id,
        username=user.username,
        ip_address=ip_address,
        success=True,
        auth_method=AuthMethodEnum.PASSWORD,
    ))

    logger.info(f"User logged in: {user.username} from {ip_address}")

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=security_manager.config.access_token_expire_minutes * 60,
        refresh_token=refresh_token,
        user=user_to_response(user),
    )


@router.post("/logout", tags=["authentication"])
async def logout(current_user: User = Depends(get_current_user)):
    """Logout and invalidate session."""
    security_manager = get_security_manager()

    # Destroy all user sessions
    count = security_manager.session_manager.destroy_user_sessions(current_user.user_id)

    # Audit log
    await security_manager.audit_log(AuditLogEntry(
        event_type=AuditEventType.LOGOUT,
        user_id=current_user.user_id,
        username=current_user.username,
        success=True,
    ))

    logger.info(f"User logged out: {current_user.username} ({count} sessions)")

    return {"message": "Logged out successfully", "sessions_destroyed": count}


@router.post("/refresh", response_model=TokenResponse, tags=["authentication"])
async def refresh_token(refresh_request: RefreshTokenRequest):
    """Refresh access token using refresh token."""
    security_manager = get_security_manager()

    # Decode refresh token
    user_id = decode_refresh_token(refresh_request.refresh_token, security_manager.config)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Get user
    user = await security_manager.get_user(user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Create new tokens
    access_token = create_access_token(user, security_manager.config)
    new_refresh_token = create_refresh_token(user.user_id, security_manager.config)

    logger.info(f"Token refreshed for user: {user.username}")

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=security_manager.config.access_token_expire_minutes * 60,
        refresh_token=new_refresh_token,
        user=user_to_response(user),
    )


@router.get("/me", response_model=UserResponse, tags=["authentication"])
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information."""
    return user_to_response(current_user)


# ============================================================================
# User Management Endpoints
# ============================================================================

@router.post("/users", response_model=UserResponse, tags=["users"])
async def create_user(
    user_create: UserCreate,
    current_user: User = Depends(require_superuser),
):
    """Create a new user (superuser only)."""
    security_manager = get_security_manager()

    try:
        user = await security_manager.create_user(user_create, created_by=current_user.user_id)
        return user_to_response(user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/users", response_model=List[UserResponse], tags=["users"])
async def list_users(
    is_active: Optional[bool] = None,
    current_user: User = Depends(require_superuser),
):
    """List all users (superuser only)."""
    security_manager = get_security_manager()
    users = await security_manager.list_users(is_active=is_active)
    return [user_to_response(u) for u in users]


@router.get("/users/{user_id}", response_model=UserResponse, tags=["users"])
async def get_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get user by ID."""
    # Users can view their own profile, superusers can view any
    if current_user.user_id != user_id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )

    security_manager = get_security_manager()
    user = await security_manager.get_user(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return user_to_response(user)


@router.patch("/users/{user_id}", response_model=UserResponse, tags=["users"])
async def update_user(
    user_id: str,
    update: UserUpdate,
    current_user: User = Depends(require_superuser),
):
    """Update user (superuser only)."""
    security_manager = get_security_manager()
    user = await security_manager.update_user(user_id, update)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await security_manager.audit_log(AuditLogEntry(
        event_type=AuditEventType.USER_UPDATED,
        user_id=current_user.user_id,
        resource_id=user_id,
    ))

    return user_to_response(user)


@router.delete("/users/{user_id}", tags=["users"])
async def delete_user(
    user_id: str,
    current_user: User = Depends(require_superuser),
):
    """Delete user (superuser only)."""
    # Prevent self-deletion
    if current_user.user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    security_manager = get_security_manager()
    success = await security_manager.delete_user(user_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return {"message": "User deleted successfully"}


@router.post("/users/change-password", tags=["users"])
async def change_password(
    password_change: PasswordChange,
    current_user: User = Depends(get_current_user),
):
    """Change own password."""
    security_manager = get_security_manager()

    success = await security_manager.change_password(
        current_user.user_id,
        password_change.old_password,
        password_change.new_password,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid old password",
        )

    return {"message": "Password changed successfully"}


@router.post("/users/reset-password", tags=["users"])
async def reset_password(
    password_reset: PasswordReset,
    current_user: User = Depends(require_superuser),
):
    """Reset user password (superuser only)."""
    security_manager = get_security_manager()

    from security.auth import hash_password
    from sqlite3 import connect

    conn = connect(str(security_manager.db_path))
    cursor = conn.cursor()

    try:
        new_hash = hash_password(password_reset.new_password)
        cursor.execute("""
            UPDATE users SET
                hashed_password = ?,
                must_change_password = ?,
                updated_at = ?
            WHERE user_id = ?
        """, (
            new_hash,
            password_reset.must_change_password,
            datetime.utcnow(),
            password_reset.user_id,
        ))

        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        conn.commit()

        await security_manager.audit_log(AuditLogEntry(
            event_type=AuditEventType.PASSWORD_CHANGED,
            user_id=current_user.user_id,
            resource_id=password_reset.user_id,
            details={"admin_reset": True},
        ))

        return {"message": "Password reset successfully"}

    finally:
        conn.close()


# ============================================================================
# Role Management Endpoints
# ============================================================================

@router.get("/roles", response_model=List[Role], tags=["roles"])
async def list_roles(current_user: User = Depends(get_current_user)):
    """List all roles."""
    security_manager = get_security_manager()
    return await security_manager.list_roles()


@router.get("/roles/{role_id}", response_model=Role, tags=["roles"])
async def get_role(
    role_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get role by ID."""
    security_manager = get_security_manager()
    role = await security_manager.get_role(role_id)

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    return role


# ============================================================================
# API Key Management Endpoints
# ============================================================================

@router.post("/api-keys", response_model=APIKeyResponse, tags=["api-keys"])
async def create_api_key(
    key_create: APIKeyCreate,
    current_user: User = Depends(get_current_user),
):
    """Create a new API key."""
    security_manager = get_security_manager()

    api_key = await security_manager.create_api_key(
        current_user.user_id,
        key_create,
        created_by=current_user.user_id,
    )

    # Return full key only on creation
    return APIKeyResponse(
        key_id=api_key.key_id,
        key=api_key.key,  # Only returned here!
        key_prefix=api_key.key_prefix,
        name=api_key.name,
        description=api_key.description,
        scopes=api_key.scopes,
        is_active=api_key.is_active,
        expires_at=api_key.expires_at,
        last_used=api_key.last_used,
        usage_count=api_key.usage_count,
        created_at=api_key.created_at,
    )


@router.get("/api-keys", response_model=List[APIKeyResponse], tags=["api-keys"])
async def list_api_keys(
    current_user: User = Depends(get_current_user),
):
    """List user's API keys."""
    security_manager = get_security_manager()

    # Superusers can see all keys
    user_id = None if current_user.is_superuser else current_user.user_id

    api_keys = await security_manager.list_api_keys(user_id=user_id)

    return [
        APIKeyResponse(
            key_id=k.key_id,
            key=None,  # Never return full key after creation
            key_prefix=k.key_prefix,
            name=k.name,
            description=k.description,
            scopes=k.scopes,
            is_active=k.is_active,
            expires_at=k.expires_at,
            last_used=k.last_used,
            usage_count=k.usage_count,
            created_at=k.created_at,
        )
        for k in api_keys
    ]


@router.delete("/api-keys/{key_id}", tags=["api-keys"])
async def revoke_api_key(
    key_id: str,
    current_user: User = Depends(get_current_user),
):
    """Revoke an API key."""
    security_manager = get_security_manager()

    # Get the key to check ownership
    api_keys = await security_manager.list_api_keys(user_id=current_user.user_id)
    owned_key_ids = [k.key_id for k in api_keys]

    # Only owner or superuser can revoke
    if key_id not in owned_key_ids and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied",
        )

    success = await security_manager.revoke_api_key(key_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    return {"message": "API key revoked successfully"}


# ============================================================================
# IP Whitelist Endpoints
# ============================================================================

@router.post("/ip-whitelist", response_model=IPWhitelistEntry, tags=["ip-whitelist"])
async def add_ip_whitelist(
    entry_create: IPWhitelistCreate,
    current_user: User = Depends(require_superuser),
):
    """Add IP to whitelist (superuser only)."""
    security_manager = get_security_manager()
    return await security_manager.add_ip_whitelist(entry_create, created_by=current_user.user_id)


@router.get("/ip-whitelist", response_model=List[IPWhitelistEntry], tags=["ip-whitelist"])
async def list_ip_whitelist(current_user: User = Depends(require_superuser)):
    """List IP whitelist entries (superuser only)."""
    security_manager = get_security_manager()
    return await security_manager.list_ip_whitelist()


@router.delete("/ip-whitelist/{entry_id}", tags=["ip-whitelist"])
async def remove_ip_whitelist(
    entry_id: str,
    current_user: User = Depends(require_superuser),
):
    """Remove IP whitelist entry (superuser only)."""
    security_manager = get_security_manager()
    success = await security_manager.remove_ip_whitelist(entry_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found",
        )

    return {"message": "IP whitelist entry removed"}


# ============================================================================
# Audit Log Endpoints
# ============================================================================

@router.post("/audit-log/query", response_model=List[AuditLogEntry], tags=["audit"])
async def query_audit_log(
    query: AuditLogQuery,
    current_user: User = Depends(require_superuser),
):
    """Query audit log (superuser only)."""
    security_manager = get_security_manager()
    return await security_manager.query_audit_log(query)


# ============================================================================
# Security Status Endpoints
# ============================================================================

@router.get("/status", response_model=SecurityStatus, tags=["status"])
async def get_security_status(current_user: User = Depends(require_superuser)):
    """Get security system status (superuser only)."""
    security_manager = get_security_manager()
    return await security_manager.get_security_status()


@router.get("/sessions", response_model=List[SessionInfo], tags=["status"])
async def list_active_sessions(current_user: User = Depends(require_superuser)):
    """List active sessions (superuser only)."""
    security_manager = get_security_manager()
    return security_manager.session_manager.get_active_sessions()


@router.get("/sessions/me", response_model=List[SessionInfo], tags=["status"])
async def list_my_sessions(current_user: User = Depends(get_current_user)):
    """List current user's sessions."""
    security_manager = get_security_manager()
    return security_manager.session_manager.get_user_sessions(current_user.user_id)
