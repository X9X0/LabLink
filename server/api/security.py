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

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from security import (APIKey,  # Models; MFA Models; Manager; Auth
                      APIKeyCreate, APIKeyResponse, AuditEventType,
                      AuditLogEntry, AuditLogQuery, BackupCodesResponse,
                      IPWhitelistCreate, IPWhitelistEntry, LoginRequest,
                      MFADisableRequest, MFALoginRequest, MFASetupResponse,
                      MFAStatusResponse, MFAVerifyRequest, OAuth2LinkResponse,
                      OAuth2LoginRequest, OAuth2Provider, PasswordChange,
                      PasswordReset, RefreshTokenRequest, Role, SecurityStatus,
                      SessionInfo, TokenResponse, User, UserCreate,
                      UserResponse, UserUpdate, create_access_token,
                      create_refresh_token, decode_refresh_token,
                      get_security_manager, user_to_response, verify_password)
from security.rbac import get_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/security")
security_scheme = HTTPBearer()


# ============================================================================
# Helper Functions
# ============================================================================


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
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
        remaining = security_manager.attempt_tracker.get_lockout_time_remaining(
            login_request.username
        )
        await security_manager.audit_log(
            AuditLogEntry(
                event_type=AuditEventType.LOGIN_FAILED,
                username=login_request.username,
                ip_address=ip_address,
                success=False,
                error_message=f"Account locked for {remaining} seconds",
            )
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account temporarily locked. Try again in {remaining} seconds.",
        )

    # Get user
    user = await security_manager.get_user_by_username(login_request.username)

    if not user:
        # Record failed attempt
        security_manager.attempt_tracker.record_failed_attempt(login_request.username)
        await security_manager.audit_log(
            AuditLogEntry(
                event_type=AuditEventType.LOGIN_FAILED,
                username=login_request.username,
                ip_address=ip_address,
                success=False,
                error_message="User not found",
            )
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Verify password
    if not verify_password(login_request.password, user.hashed_password):
        # Record failed attempt
        attempts = security_manager.attempt_tracker.record_failed_attempt(
            login_request.username
        )
        await security_manager.audit_log(
            AuditLogEntry(
                event_type=AuditEventType.LOGIN_FAILED,
                user_id=user.user_id,
                username=user.username,
                ip_address=ip_address,
                success=False,
                error_message="Invalid password",
            )
        )

        remaining_attempts = (
            security_manager.config.max_failed_login_attempts - attempts
        )
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
        await security_manager.audit_log(
            AuditLogEntry(
                event_type=AuditEventType.LOGIN_FAILED,
                user_id=user.user_id,
                username=user.username,
                ip_address=ip_address,
                success=False,
                error_message="Account disabled",
            )
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # Check MFA
    if user.mfa_enabled:
        # MFA is enabled - require token
        mfa_token = getattr(login_request, "mfa_token", None)

        if not mfa_token:
            # MFA required but no token provided
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="MFA token required",
                headers={"X-MFA-Required": "true"},
            )

        # Verify MFA token
        from security.mfa import verify_mfa_token

        is_valid, used_backup_code = verify_mfa_token(
            user.mfa_secret, mfa_token, user.backup_codes
        )

        if not is_valid:
            # Record failed attempt
            attempts = security_manager.attempt_tracker.record_failed_attempt(
                login_request.username
            )
            await security_manager.audit_log(
                AuditLogEntry(
                    event_type=AuditEventType.LOGIN_FAILED,
                    user_id=user.user_id,
                    username=user.username,
                    ip_address=ip_address,
                    success=False,
                    error_message="Invalid MFA token",
                )
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA token",
            )

        # If backup code was used, remove it
        if used_backup_code:
            # Find and remove the used backup code
            for code_hash in user.backup_codes:
                from security.mfa import verify_backup_code

                if verify_backup_code(mfa_token, code_hash):
                    await security_manager.remove_backup_code(user.user_id, code_hash)
                    logger.info(f"Backup code used for user: {user.username}")
                    break

    # Clear failed attempts
    security_manager.attempt_tracker.clear_attempts(login_request.username)

    # Update last login
    from sqlite3 import connect

    conn = connect(str(security_manager.db_path))
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE users SET last_login = ?, last_login_ip = ? WHERE user_id = ?
    """,
        (datetime.utcnow(), ip_address, user.user_id),
    )
    conn.commit()
    conn.close()

    # Create tokens
    access_token = create_access_token(user, security_manager.config)
    refresh_token = create_refresh_token(user.user_id, security_manager.config)

    # Create session
    from security.models import AuthMethod as AuthMethodEnum

    session_id = security_manager.session_manager.create_session(
        user,
        ip_address,
        auth_method=AuthMethodEnum.PASSWORD,
        expires_in_minutes=security_manager.config.access_token_expire_minutes,
    )

    # Audit log
    await security_manager.audit_log(
        AuditLogEntry(
            event_type=AuditEventType.LOGIN_SUCCESS,
            user_id=user.user_id,
            username=user.username,
            ip_address=ip_address,
            success=True,
            auth_method=AuthMethodEnum.PASSWORD,
        )
    )

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
    await security_manager.audit_log(
        AuditLogEntry(
            event_type=AuditEventType.LOGOUT,
            user_id=current_user.user_id,
            username=current_user.username,
            success=True,
        )
    )

    logger.info(f"User logged out: {current_user.username} ({count} sessions)")

    return {"message": "Logged out successfully", "sessions_destroyed": count}


@router.post("/refresh", response_model=TokenResponse, tags=["authentication"])
async def refresh_token(refresh_request: RefreshTokenRequest):
    """Refresh access token using refresh token."""
    security_manager = get_security_manager()

    # Decode refresh token
    user_id = decode_refresh_token(
        refresh_request.refresh_token, security_manager.config
    )
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
# Multi-Factor Authentication Endpoints
# ============================================================================


@router.post("/mfa/setup", response_model=MFASetupResponse, tags=["mfa"])
async def setup_mfa(current_user: User = Depends(get_current_user)):
    """
    Set up MFA for the current user.

    Returns QR code, secret, and backup codes.
    """
    if current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled",
        )

    from security.mfa import hash_backup_codes
    from security.mfa import setup_mfa as mfa_setup

    # Generate MFA setup data
    secret, qr_code, backup_codes, provisioning_uri = mfa_setup(current_user.username)

    # Store in user record (but don't enable yet - requires verification)
    security_manager = get_security_manager()
    hashed_codes = hash_backup_codes(backup_codes)

    # Temporarily store for verification
    # Note: MFA is not enabled until verified via /mfa/enable
    await security_manager.enable_mfa(current_user.user_id, secret, hashed_codes)

    logger.info(f"MFA setup initiated for user: {current_user.username}")

    return MFASetupResponse(
        secret=secret,
        qr_code=qr_code,
        backup_codes=backup_codes,
        provisioning_uri=provisioning_uri,
    )


@router.post("/mfa/verify", tags=["mfa"])
async def verify_mfa_setup(
    verify_request: MFAVerifyRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Verify MFA setup by providing a TOTP token.

    This confirms the user has successfully scanned the QR code.
    """
    security_manager = get_security_manager()

    # Get fresh user data
    user = await security_manager.get_user(current_user.user_id)
    if not user or not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA setup not initiated",
        )

    # Verify the token
    from security.mfa import verify_totp_token

    if not verify_totp_token(user.mfa_secret, verify_request.token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid MFA token",
        )

    logger.info(f"MFA verified and enabled for user: {current_user.username}")

    return {"message": "MFA successfully enabled"}


@router.post("/mfa/disable", tags=["mfa"])
async def disable_mfa(
    disable_request: MFADisableRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Disable MFA for the current user.

    Requires password confirmation and optional MFA token.
    """
    from security.auth import verify_password

    # Verify password
    if not verify_password(disable_request.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
        )

    # If MFA is enabled, require MFA token
    if current_user.mfa_enabled and disable_request.mfa_token:
        from security.mfa import verify_mfa_token

        is_valid, _ = verify_mfa_token(
            current_user.mfa_secret,
            disable_request.mfa_token,
            current_user.backup_codes,
        )
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA token",
            )

    # Disable MFA
    security_manager = get_security_manager()
    await security_manager.disable_mfa(current_user.user_id)

    logger.info(f"MFA disabled for user: {current_user.username}")

    return {"message": "MFA disabled successfully"}


@router.get("/mfa/status", response_model=MFAStatusResponse, tags=["mfa"])
async def get_mfa_status(current_user: User = Depends(get_current_user)):
    """Get MFA status for the current user."""
    backup_codes_remaining = (
        len(current_user.backup_codes) if current_user.backup_codes else 0
    )

    return MFAStatusResponse(
        mfa_enabled=current_user.mfa_enabled,
        backup_codes_remaining=backup_codes_remaining,
    )


@router.post(
    "/mfa/backup-codes/regenerate", response_model=BackupCodesResponse, tags=["mfa"]
)
async def regenerate_backup_codes(current_user: User = Depends(get_current_user)):
    """
    Regenerate backup codes for the current user.

    Requires MFA to be enabled.
    """
    if not current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled",
        )

    from security.mfa import generate_backup_codes, hash_backup_codes

    # Generate new codes
    new_codes = generate_backup_codes()
    hashed_codes = hash_backup_codes(new_codes)

    # Update in database
    security_manager = get_security_manager()
    await security_manager.regenerate_backup_codes(current_user.user_id, hashed_codes)

    logger.info(f"Backup codes regenerated for user: {current_user.username}")

    return BackupCodesResponse(backup_codes=new_codes)


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
        user = await security_manager.create_user(
            user_create, created_by=current_user.user_id
        )
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

    await security_manager.audit_log(
        AuditLogEntry(
            event_type=AuditEventType.USER_UPDATED,
            user_id=current_user.user_id,
            resource_id=user_id,
        )
    )

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

    from sqlite3 import connect

    from security.auth import hash_password

    conn = connect(str(security_manager.db_path))
    cursor = conn.cursor()

    try:
        new_hash = hash_password(password_reset.new_password)
        cursor.execute(
            """
            UPDATE users SET
                hashed_password = ?,
                must_change_password = ?,
                updated_at = ?
            WHERE user_id = ?
        """,
            (
                new_hash,
                password_reset.must_change_password,
                datetime.utcnow(),
                password_reset.user_id,
            ),
        )

        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        conn.commit()

        await security_manager.audit_log(
            AuditLogEntry(
                event_type=AuditEventType.PASSWORD_CHANGED,
                user_id=current_user.user_id,
                resource_id=password_reset.user_id,
                details={"admin_reset": True},
            )
        )

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
    return await security_manager.add_ip_whitelist(
        entry_create, created_by=current_user.user_id
    )


@router.get(
    "/ip-whitelist", response_model=List[IPWhitelistEntry], tags=["ip-whitelist"]
)
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


# ============================================================================
# OAuth2 Authentication Endpoints
# ============================================================================


@router.get("/oauth2/providers", tags=["oauth2"])
async def list_oauth2_providers():
    """List available OAuth2 providers."""
    from security.oauth2 import get_oauth2_manager

    oauth2_manager = get_oauth2_manager()
    enabled_providers = oauth2_manager.get_enabled_providers()

    return {
        "providers": [
            {
                "provider": provider.value,
                "name": provider.value.capitalize(),
                "enabled": True,
            }
            for provider in enabled_providers
        ]
    }


@router.get("/oauth2/authorize/{provider}", tags=["oauth2"])
async def get_oauth2_authorization_url(
    provider: OAuth2Provider,
    redirect_uri: str,
    state: Optional[str] = None,
):
    """
    Get OAuth2 authorization URL for provider.

    Args:
        provider: OAuth2 provider (google, github, microsoft)
        redirect_uri: Redirect URI after authorization
        state: Optional state parameter for CSRF protection

    Returns:
        Authorization URL and state
    """
    from security.oauth2 import get_oauth2_manager

    oauth2_manager = get_oauth2_manager()
    prov = oauth2_manager.get_provider(provider)

    if not prov:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth2 provider not configured: {provider}",
        )

    if not prov.config.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth2 provider disabled: {provider}",
        )

    # Generate state if not provided (for CSRF protection)
    import secrets

    if not state:
        state = secrets.token_urlsafe(32)

    authorization_url = prov.get_authorization_url(redirect_uri, state)

    return {
        "authorization_url": authorization_url,
        "state": state,
        "provider": provider.value,
    }


@router.post("/oauth2/login", response_model=TokenResponse, tags=["oauth2"])
async def oauth2_login(
    login_request: OAuth2LoginRequest,
    request: Request,
):
    """
    Login with OAuth2 provider.

    Creates a new user account if email doesn't exist, or logs in existing user.

    Args:
        login_request: OAuth2 login request with code and redirect_uri
        request: FastAPI request object

    Returns:
        JWT tokens and user information
    """
    from security.oauth2 import get_oauth2_manager

    security_manager = get_security_manager()
    oauth2_manager = get_oauth2_manager()

    try:
        # Authenticate with OAuth2 provider
        external_id, email, full_name = await oauth2_manager.authenticate(
            login_request.provider,
            login_request.code,
            login_request.redirect_uri,
        )

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No email received from OAuth2 provider",
            )

        # Check if user exists with this email
        user = await security_manager.get_user_by_username(email)

        if not user:
            # Create new user from OAuth2 data
            import secrets

            from security import UserCreate, create_default_operator_role

            # Generate random password (user won't use it, OAuth2 only)
            random_password = secrets.token_urlsafe(32)

            # Get default operator role
            operator_role = create_default_operator_role()
            existing_role = security_manager.get_role_by_name(operator_role.name)
            role_ids = [existing_role.role_id] if existing_role else []

            user_create = UserCreate(
                username=email,
                email=email,
                password=random_password,
                full_name=full_name or email,
                roles=role_ids,
                must_change_password=False,  # OAuth2 users don't use passwords
            )

            user = await security_manager.create_user(user_create, created_by=None)

            # Log audit event
            await security_manager.log_audit_event(
                event_type=AuditEventType.USER_CREATED,
                user_id=user.user_id,
                ip_address=request.client.host if request.client else None,
                details={
                    "method": "oauth2",
                    "provider": login_request.provider.value,
                    "external_id": external_id,
                },
            )

            logger.info(
                f"New user created via OAuth2: {email} ({login_request.provider})"
            )

        # Link OAuth2 account if not already linked
        # Note: In production, you'd want to store OAuth2 provider associations
        # in a separate table (user_id, provider, external_id)

        # Create JWT tokens
        access_token = create_access_token(
            data={"sub": user.username, "user_id": user.user_id},
            config=security_manager.config,
        )

        refresh_token = create_refresh_token(
            data={"sub": user.username, "user_id": user.user_id},
            config=security_manager.config,
        )

        # Create session
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

        session_id = security_manager.session_manager.create_session(
            user_id=user.user_id,
            username=user.username,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Log successful login
        await security_manager.log_audit_event(
            event_type=AuditEventType.LOGIN_SUCCESS,
            user_id=user.user_id,
            username=user.username,
            ip_address=ip_address,
            details={
                "method": "oauth2",
                "provider": login_request.provider.value,
                "session_id": session_id,
            },
        )

        logger.info(
            f"OAuth2 login successful: {user.username} via {login_request.provider}"
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=user_to_response(user),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth2 login failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"OAuth2 authentication failed: {str(e)}",
        )


@router.post("/oauth2/link", response_model=OAuth2LinkResponse, tags=["oauth2"])
async def link_oauth2_account(
    link_request: OAuth2LoginRequest,
    current_user: User = Depends(get_current_user),
    request: Request = None,
):
    """
    Link OAuth2 account to existing user.

    Args:
        link_request: OAuth2 login request with code and redirect_uri
        current_user: Currently authenticated user
        request: FastAPI request object

    Returns:
        OAuth2 link response with provider info
    """
    from security.oauth2 import get_oauth2_manager

    security_manager = get_security_manager()
    oauth2_manager = get_oauth2_manager()

    try:
        # Authenticate with OAuth2 provider
        external_id, email, full_name = await oauth2_manager.authenticate(
            link_request.provider,
            link_request.code,
            link_request.redirect_uri,
        )

        # Note: In production, you'd want to store this association in a database table
        # For now, we'll just log it

        # Log audit event
        await security_manager.log_audit_event(
            event_type=AuditEventType.OAUTH2_LINKED,
            user_id=current_user.user_id,
            username=current_user.username,
            ip_address=request.client.host if request and request.client else None,
            details={
                "provider": link_request.provider.value,
                "external_id": external_id,
                "email": email,
            },
        )

        logger.info(
            f"OAuth2 account linked: {current_user.username} -> {link_request.provider} ({external_id})"
        )

        return OAuth2LinkResponse(
            success=True,
            provider=link_request.provider,
            external_id=external_id,
            email=email,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth2 link failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth2 link failed: {str(e)}",
        )
