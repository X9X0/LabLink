"""
LabLink Advanced Security System

Provides comprehensive security features:
- JWT authentication
- Role-based access control (RBAC)
- API key management
- IP whitelisting
- OAuth2 integration
- Security audit logging
"""

from .models import (
    # Enums
    RoleType,
    PermissionAction,
    ResourceType,
    AuthMethod,
    OAuth2Provider,
    AuditEventType,

    # Permission models
    Permission,
    Role,

    # User models
    User,
    UserCreate,
    UserUpdate,
    UserResponse,
    PasswordChange,
    PasswordReset,

    # Authentication models
    LoginRequest,
    TokenResponse,
    TokenPayload,
    RefreshTokenRequest,

    # API Key models
    APIKey,
    APIKeyCreate,
    APIKeyResponse,

    # IP Whitelist models
    IPWhitelistEntry,
    IPWhitelistCreate,

    # OAuth2 models
    OAuth2Config,
    OAuth2LoginRequest,
    OAuth2LinkResponse,

    # Audit models
    AuditLogEntry,
    AuditLogQuery,

    # Status models
    SecurityStatus,
    SessionInfo,

    # Helper functions
    generate_api_key,
    create_default_admin_role,
    create_default_operator_role,
    create_default_viewer_role,
)

from .auth import (
    AuthConfig,
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    decode_refresh_token,
    user_to_response,
    SessionManager,
    LoginAttemptTracker,
    generate_secure_secret_key,
)

from .manager import (
    SecurityManager,
    get_security_manager,
    init_security_manager,
)

from .oauth2 import (
    OAuth2Manager,
    get_oauth2_manager,
    init_oauth2_manager,
    OAUTH2_DEFAULTS,
)

__all__ = [
    # Enums
    "RoleType",
    "PermissionAction",
    "ResourceType",
    "AuthMethod",
    "OAuth2Provider",
    "AuditEventType",

    # Models
    "Permission",
    "Role",
    "User",
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "PasswordChange",
    "PasswordReset",
    "LoginRequest",
    "TokenResponse",
    "TokenPayload",
    "RefreshTokenRequest",
    "APIKey",
    "APIKeyCreate",
    "APIKeyResponse",
    "IPWhitelistEntry",
    "IPWhitelistCreate",
    "OAuth2Config",
    "OAuth2LoginRequest",
    "OAuth2LinkResponse",
    "AuditLogEntry",
    "AuditLogQuery",
    "SecurityStatus",
    "SessionInfo",

    # Auth functions
    "AuthConfig",
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "decode_refresh_token",
    "user_to_response",
    "SessionManager",
    "LoginAttemptTracker",
    "generate_secure_secret_key",

    # Helper functions
    "generate_api_key",
    "create_default_admin_role",
    "create_default_operator_role",
    "create_default_viewer_role",

    # Managers
    "SecurityManager",
    "get_security_manager",
    "init_security_manager",
    "OAuth2Manager",
    "get_oauth2_manager",
    "init_oauth2_manager",
    "OAUTH2_DEFAULTS",
]
