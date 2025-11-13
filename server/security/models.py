"""
Security Models for LabLink Advanced Security System

Provides data models for:
- User accounts and authentication
- Role-based access control (RBAC)
- API key management
- IP whitelisting
- OAuth2 integration
- Security audit logging
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, EmailStr, validator
import secrets
import string


# ============================================================================
# Enumerations
# ============================================================================

class RoleType(str, Enum):
    """Predefined system roles."""
    ADMIN = "admin"  # Full access to all resources
    OPERATOR = "operator"  # Can control equipment, view data
    VIEWER = "viewer"  # Read-only access
    CUSTOM = "custom"  # Custom role with specific permissions


class PermissionAction(str, Enum):
    """Permission actions."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"
    ADMIN = "admin"  # Full admin access to resource


class ResourceType(str, Enum):
    """Resources that can be protected."""
    EQUIPMENT = "equipment"
    ACQUISITION = "acquisition"
    PROFILES = "profiles"
    STATES = "states"
    SAFETY = "safety"
    LOCKS = "locks"
    ALARMS = "alarms"
    SCHEDULER = "scheduler"
    DIAGNOSTICS = "diagnostics"
    PERFORMANCE = "performance"
    BACKUP = "backup"
    DISCOVERY = "discovery"
    WAVEFORM = "waveform"
    ANALYSIS = "analysis"
    DATABASE = "database"
    CALIBRATION = "calibration"
    TESTING = "testing"
    USERS = "users"
    ROLES = "roles"
    API_KEYS = "api_keys"
    SETTINGS = "settings"
    SYSTEM = "system"


class AuthMethod(str, Enum):
    """Authentication methods."""
    PASSWORD = "password"
    API_KEY = "api_key"
    JWT = "jwt"
    OAUTH2 = "oauth2"


class OAuth2Provider(str, Enum):
    """Supported OAuth2 providers."""
    GOOGLE = "google"
    GITHUB = "github"
    MICROSOFT = "microsoft"
    CUSTOM = "custom"


class AuditEventType(str, Enum):
    """Security audit event types."""
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    PASSWORD_CHANGED = "password_changed"
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"
    ROLE_CHANGED = "role_changed"
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_REVOKED = "permission_revoked"
    API_KEY_CREATED = "api_key_created"
    API_KEY_REVOKED = "api_key_revoked"
    ACCESS_DENIED = "access_denied"
    IP_BLOCKED = "ip_blocked"
    TOKEN_EXPIRED = "token_expired"
    OAUTH2_LINKED = "oauth2_linked"
    OAUTH2_UNLINKED = "oauth2_unlinked"


# ============================================================================
# Permission Models
# ============================================================================

class Permission(BaseModel):
    """A specific permission for a resource and action."""
    permission_id: str = Field(default_factory=lambda: secrets.token_urlsafe(16))
    resource: ResourceType
    action: PermissionAction
    description: Optional[str] = None
    resource_id: Optional[str] = None  # Specific resource instance (e.g., equipment_id)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def matches(self, resource: str, action: str, resource_id: Optional[str] = None) -> bool:
        """Check if this permission matches the requested access."""
        # Check resource match
        if self.resource.value != resource:
            return False

        # Check action match (ADMIN action grants all actions)
        if self.action == PermissionAction.ADMIN:
            return True
        if self.action.value != action:
            return False

        # Check resource_id match (None means all resources of this type)
        if self.resource_id is None:
            return True
        if self.resource_id == resource_id:
            return True

        return False


class Role(BaseModel):
    """A role groups permissions together."""
    role_id: str = Field(default_factory=lambda: secrets.token_urlsafe(16))
    name: str  # e.g., "admin", "operator", "viewer", "custom_lab_tech"
    role_type: RoleType
    description: Optional[str] = None
    permissions: List[Permission] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def has_permission(
        self,
        resource: str,
        action: str,
        resource_id: Optional[str] = None
    ) -> bool:
        """Check if this role has a specific permission."""
        for perm in self.permissions:
            if perm.matches(resource, action, resource_id):
                return True
        return False


# ============================================================================
# User Models
# ============================================================================

class User(BaseModel):
    """User account."""
    user_id: str = Field(default_factory=lambda: secrets.token_urlsafe(16))
    username: str  # Unique username
    email: EmailStr  # User email
    hashed_password: str  # Bcrypt hashed password
    full_name: Optional[str] = None
    roles: List[str] = Field(default_factory=list)  # List of role_ids
    is_active: bool = True
    is_superuser: bool = False  # Superuser bypasses all permissions
    must_change_password: bool = False  # Force password change on next login
    password_expires_at: Optional[datetime] = None
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None  # Account lockout
    last_login: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    oauth2_providers: Dict[str, str] = Field(default_factory=dict)  # provider -> external_id
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None  # user_id of creator

    @validator("username")
    def username_valid(cls, v):
        """Validate username format."""
        if not v or len(v) < 3:
            raise ValueError("Username must be at least 3 characters")
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username can only contain letters, numbers, underscores, and hyphens")
        return v


class UserCreate(BaseModel):
    """Request to create a new user."""
    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    roles: List[str] = Field(default_factory=list)
    is_active: bool = True
    must_change_password: bool = False

    @validator("password")
    def password_strength(cls, v):
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserUpdate(BaseModel):
    """Request to update user information."""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    roles: Optional[List[str]] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    must_change_password: Optional[bool] = None


class UserResponse(BaseModel):
    """User information for API responses (excludes sensitive data)."""
    user_id: str
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    roles: List[str]
    is_active: bool
    is_superuser: bool
    must_change_password: bool
    last_login: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class PasswordChange(BaseModel):
    """Request to change password."""
    old_password: str
    new_password: str

    @validator("new_password")
    def password_strength(cls, v):
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class PasswordReset(BaseModel):
    """Request to reset password (admin only)."""
    user_id: str
    new_password: str
    must_change_password: bool = True


# ============================================================================
# Authentication Models
# ============================================================================

class LoginRequest(BaseModel):
    """Login request."""
    username: str
    password: str


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    refresh_token: Optional[str] = None
    user: UserResponse


class TokenPayload(BaseModel):
    """JWT token payload."""
    sub: str  # user_id
    username: str
    roles: List[str]
    is_superuser: bool
    exp: datetime  # expiration
    iat: datetime  # issued at
    auth_method: AuthMethod = AuthMethod.PASSWORD


class RefreshTokenRequest(BaseModel):
    """Request to refresh access token."""
    refresh_token: str


# ============================================================================
# API Key Models
# ============================================================================

class APIKey(BaseModel):
    """API key for programmatic access."""
    key_id: str = Field(default_factory=lambda: secrets.token_urlsafe(16))
    key: str = Field(default_factory=lambda: "lablink_" + secrets.token_urlsafe(32))
    key_prefix: str = ""  # First 8 chars for display
    user_id: str
    name: str  # Descriptive name for the key
    description: Optional[str] = None
    scopes: List[str] = Field(default_factory=list)  # Specific permissions (resource:action)
    permissions: List[Permission] = Field(default_factory=list)  # Direct permissions
    is_active: bool = True
    expires_at: Optional[datetime] = None
    last_used: Optional[datetime] = None
    last_used_ip: Optional[str] = None
    usage_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str  # user_id

    def __init__(self, **data):
        super().__init__(**data)
        if not self.key_prefix:
            self.key_prefix = self.key[:12] + "..."

    def is_valid(self) -> bool:
        """Check if API key is valid."""
        if not self.is_active:
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True

    def has_scope(self, scope: str) -> bool:
        """Check if API key has specific scope."""
        if not self.scopes:  # Empty scopes = all access
            return True
        return scope in self.scopes or "*" in self.scopes


class APIKeyCreate(BaseModel):
    """Request to create API key."""
    name: str
    description: Optional[str] = None
    scopes: List[str] = Field(default_factory=list)
    expires_in_days: Optional[int] = None  # None = no expiration

    @validator("expires_in_days")
    def validate_expiration(cls, v):
        """Validate expiration period."""
        if v is not None and v < 1:
            raise ValueError("Expiration must be at least 1 day")
        if v is not None and v > 365:
            raise ValueError("Expiration cannot exceed 365 days")
        return v


class APIKeyResponse(BaseModel):
    """API key response (includes full key only on creation)."""
    key_id: str
    key: Optional[str] = None  # Only returned on creation
    key_prefix: str
    name: str
    description: Optional[str] = None
    scopes: List[str]
    is_active: bool
    expires_at: Optional[datetime] = None
    last_used: Optional[datetime] = None
    usage_count: int
    created_at: datetime


# ============================================================================
# IP Whitelisting Models
# ============================================================================

class IPWhitelistEntry(BaseModel):
    """IP whitelist/blacklist entry."""
    entry_id: str = Field(default_factory=lambda: secrets.token_urlsafe(16))
    ip_address: str  # Can be single IP or CIDR range
    is_whitelist: bool = True  # True = whitelist, False = blacklist
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str  # user_id
    expires_at: Optional[datetime] = None


class IPWhitelistCreate(BaseModel):
    """Request to add IP to whitelist."""
    ip_address: str
    is_whitelist: bool = True
    description: Optional[str] = None
    expires_in_days: Optional[int] = None


# ============================================================================
# OAuth2 Models
# ============================================================================

class OAuth2Config(BaseModel):
    """OAuth2 provider configuration."""
    provider: OAuth2Provider
    client_id: str
    client_secret: str
    authorization_url: str
    token_url: str
    user_info_url: str
    scopes: List[str] = Field(default_factory=list)
    enabled: bool = True


class OAuth2LoginRequest(BaseModel):
    """OAuth2 login/link request."""
    provider: OAuth2Provider
    code: str  # Authorization code
    redirect_uri: str
    state: Optional[str] = None


class OAuth2LinkResponse(BaseModel):
    """Response after linking OAuth2 account."""
    success: bool
    provider: OAuth2Provider
    external_id: str
    email: Optional[str] = None


# ============================================================================
# Audit Logging Models
# ============================================================================

class AuditLogEntry(BaseModel):
    """Security audit log entry."""
    entry_id: str = Field(default_factory=lambda: secrets.token_urlsafe(16))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: AuditEventType
    user_id: Optional[str] = None
    username: Optional[str] = None
    ip_address: Optional[str] = None
    resource_type: Optional[ResourceType] = None
    resource_id: Optional[str] = None
    action: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    auth_method: Optional[AuthMethod] = None


class AuditLogQuery(BaseModel):
    """Query parameters for audit log."""
    user_id: Optional[str] = None
    username: Optional[str] = None
    event_type: Optional[AuditEventType] = None
    resource_type: Optional[ResourceType] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    success: Optional[bool] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


# ============================================================================
# Security Status Models
# ============================================================================

class SecurityStatus(BaseModel):
    """Overall security system status."""
    enabled: bool
    authentication_required: bool
    ip_whitelisting_enabled: bool
    oauth2_enabled: bool
    total_users: int
    active_users: int
    total_roles: int
    total_api_keys: int
    active_api_keys: int
    whitelist_entries: int
    blacklist_entries: int
    failed_login_attempts_24h: int
    active_sessions: int


class SessionInfo(BaseModel):
    """Information about an active session."""
    session_id: str
    user_id: str
    username: str
    ip_address: str
    auth_method: AuthMethod
    created_at: datetime
    expires_at: datetime
    last_activity: datetime


# ============================================================================
# Helper Functions
# ============================================================================

def generate_api_key() -> str:
    """Generate a secure API key."""
    alphabet = string.ascii_letters + string.digits
    key = ''.join(secrets.choice(alphabet) for _ in range(40))
    return f"lablink_{key}"


def create_default_admin_role() -> Role:
    """Create the default admin role with all permissions."""
    permissions = []
    for resource in ResourceType:
        permissions.append(Permission(
            resource=resource,
            action=PermissionAction.ADMIN,
            description=f"Full admin access to {resource.value}"
        ))

    return Role(
        name="admin",
        role_type=RoleType.ADMIN,
        description="Administrator with full system access",
        permissions=permissions
    )


def create_default_operator_role() -> Role:
    """Create the default operator role."""
    permissions = [
        # Equipment access
        Permission(resource=ResourceType.EQUIPMENT, action=PermissionAction.READ),
        Permission(resource=ResourceType.EQUIPMENT, action=PermissionAction.WRITE),
        Permission(resource=ResourceType.EQUIPMENT, action=PermissionAction.EXECUTE),

        # Acquisition
        Permission(resource=ResourceType.ACQUISITION, action=PermissionAction.READ),
        Permission(resource=ResourceType.ACQUISITION, action=PermissionAction.WRITE),
        Permission(resource=ResourceType.ACQUISITION, action=PermissionAction.EXECUTE),

        # Profiles
        Permission(resource=ResourceType.PROFILES, action=PermissionAction.READ),
        Permission(resource=ResourceType.PROFILES, action=PermissionAction.WRITE),

        # States
        Permission(resource=ResourceType.STATES, action=PermissionAction.READ),
        Permission(resource=ResourceType.STATES, action=PermissionAction.WRITE),

        # Safety (read/write but not delete)
        Permission(resource=ResourceType.SAFETY, action=PermissionAction.READ),
        Permission(resource=ResourceType.SAFETY, action=PermissionAction.WRITE),

        # Locks
        Permission(resource=ResourceType.LOCKS, action=PermissionAction.READ),
        Permission(resource=ResourceType.LOCKS, action=PermissionAction.WRITE),

        # Diagnostics
        Permission(resource=ResourceType.DIAGNOSTICS, action=PermissionAction.READ),
        Permission(resource=ResourceType.DIAGNOSTICS, action=PermissionAction.EXECUTE),

        # Waveform
        Permission(resource=ResourceType.WAVEFORM, action=PermissionAction.READ),
        Permission(resource=ResourceType.WAVEFORM, action=PermissionAction.WRITE),

        # Analysis
        Permission(resource=ResourceType.ANALYSIS, action=PermissionAction.READ),
        Permission(resource=ResourceType.ANALYSIS, action=PermissionAction.WRITE),

        # Discovery
        Permission(resource=ResourceType.DISCOVERY, action=PermissionAction.READ),
        Permission(resource=ResourceType.DISCOVERY, action=PermissionAction.EXECUTE),
    ]

    return Role(
        name="operator",
        role_type=RoleType.OPERATOR,
        description="Equipment operator with control access",
        permissions=permissions
    )


def create_default_viewer_role() -> Role:
    """Create the default viewer role (read-only)."""
    permissions = []
    for resource in ResourceType:
        if resource not in [ResourceType.USERS, ResourceType.ROLES, ResourceType.API_KEYS, ResourceType.SETTINGS]:
            permissions.append(Permission(
                resource=resource,
                action=PermissionAction.READ,
                description=f"Read-only access to {resource.value}"
            ))

    return Role(
        name="viewer",
        role_type=RoleType.VIEWER,
        description="Read-only access to equipment and data",
        permissions=permissions
    )
