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

from .auth import (AuthConfig, LoginAttemptTracker, SessionManager,
                   create_access_token, create_refresh_token,
                   decode_refresh_token, decode_token,
                   generate_secure_secret_key, hash_password, user_to_response,
                   verify_password)
from .manager import (SecurityManager, get_security_manager,
                      init_security_manager)
from .models import (  # Enums; Permission models; User models; Authentication models; API Key models; IP Whitelist models; OAuth2 models; Audit models; Status models; MFA models; Helper functions
    APIKey, APIKeyCreate, APIKeyResponse, AuditEventType, AuditLogEntry,
    AuditLogQuery, AuthMethod, BackupCodesResponse, IPWhitelistCreate,
    IPWhitelistEntry, LoginRequest, MFADisableRequest, MFALoginRequest,
    MFASetupRequest, MFASetupResponse, MFAStatusResponse, MFAVerifyRequest,
    OAuth2Config, OAuth2LinkResponse, OAuth2LoginRequest, OAuth2Provider,
    PasswordChange, PasswordReset, Permission, PermissionAction,
    RefreshTokenRequest, ResourceType, Role, RoleType, SecurityStatus,
    SessionInfo, TokenPayload, TokenResponse, User, UserCreate, UserResponse,
    UserUpdate, create_default_admin_role, create_default_operator_role,
    create_default_viewer_role, generate_api_key)
from .oauth2 import (OAUTH2_DEFAULTS, OAuth2Manager, get_oauth2_manager,
                     init_oauth2_manager)

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
    "MFASetupRequest",
    "MFASetupResponse",
    "MFAVerifyRequest",
    "MFALoginRequest",
    "MFADisableRequest",
    "BackupCodesResponse",
    "MFAStatusResponse",
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
