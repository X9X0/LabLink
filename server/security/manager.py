"""
Security Manager for LabLink

Centralized management of:
- Users and authentication
- Roles and permissions
- API keys
- IP whitelisting
- Audit logging
- SQLite persistence
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from .auth import (AuthConfig, LoginAttemptTracker, SessionManager,
                   create_access_token, create_refresh_token,
                   decode_refresh_token, hash_password, user_to_response,
                   verify_password)
from .models import (APIKey, APIKeyCreate, AuditEventType, AuditLogEntry,
                     AuditLogQuery, IPWhitelistCreate, IPWhitelistEntry,
                     Permission, Role, RoleType, SecurityStatus, User,
                     UserCreate, UserUpdate, create_default_admin_role,
                     create_default_operator_role, create_default_viewer_role)

logger = logging.getLogger(__name__)


# ============================================================================
# Security Manager
# ============================================================================


class SecurityManager:
    """Manages all security operations with SQLite persistence."""

    def __init__(
        self,
        db_path: str = "data/security.db",
        config: Optional[AuthConfig] = None,
    ):
        """
        Initialize security manager.

        Args:
            db_path: Path to SQLite database
            config: Authentication configuration
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Configuration
        if config is None:
            from secrets import token_urlsafe

            config = AuthConfig(secret_key=token_urlsafe(64))
        self.config = config

        # Session and attempt tracking
        self.session_manager = SessionManager()
        self.attempt_tracker = LoginAttemptTracker(config)

        # Initialize database
        self._init_database()

        # Create default roles if not exist
        self._ensure_default_roles()

    # ========================================================================
    # Database Initialization
    # ========================================================================

    def _init_database(self):
        """Initialize SQLite database schema."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # Users table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                full_name TEXT,
                roles TEXT NOT NULL,  -- JSON array of role_ids
                is_active BOOLEAN DEFAULT 1,
                is_superuser BOOLEAN DEFAULT 0,
                must_change_password BOOLEAN DEFAULT 0,
                password_expires_at TIMESTAMP,
                failed_login_attempts INTEGER DEFAULT 0,
                locked_until TIMESTAMP,
                last_login TIMESTAMP,
                last_login_ip TEXT,
                oauth2_providers TEXT,  -- JSON dict
                metadata TEXT,  -- JSON dict
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                created_by TEXT
            )
        """
        )

        # Roles table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS roles (
                role_id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                role_type TEXT NOT NULL,
                description TEXT,
                permissions TEXT NOT NULL,  -- JSON array of permissions
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
        """
        )

        # API Keys table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                key_id TEXT PRIMARY KEY,
                key TEXT UNIQUE NOT NULL,
                key_prefix TEXT NOT NULL,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                scopes TEXT NOT NULL,  -- JSON array
                permissions TEXT NOT NULL,  -- JSON array
                is_active BOOLEAN DEFAULT 1,
                expires_at TIMESTAMP,
                last_used TIMESTAMP,
                last_used_ip TEXT,
                usage_count INTEGER DEFAULT 0,
                created_at TIMESTAMP NOT NULL,
                created_by TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """
        )

        # IP Whitelist table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ip_whitelist (
                entry_id TEXT PRIMARY KEY,
                ip_address TEXT NOT NULL,
                is_whitelist BOOLEAN DEFAULT 1,
                description TEXT,
                created_at TIMESTAMP NOT NULL,
                created_by TEXT NOT NULL,
                expires_at TIMESTAMP
            )
        """
        )

        # Audit Log table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                entry_id TEXT PRIMARY KEY,
                timestamp TIMESTAMP NOT NULL,
                event_type TEXT NOT NULL,
                user_id TEXT,
                username TEXT,
                ip_address TEXT,
                resource_type TEXT,
                resource_id TEXT,
                action TEXT,
                success BOOLEAN DEFAULT 1,
                error_message TEXT,
                details TEXT,  -- JSON dict
                auth_method TEXT
            )
        """
        )

        # Create indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_key ON api_keys(key)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log(user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_log_event_type ON audit_log(event_type)"
        )

        # Add MFA columns if they don't exist (migration)
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN mfa_enabled BOOLEAN DEFAULT 0")
            logger.info("Added mfa_enabled column to users table")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            cursor.execute("ALTER TABLE users ADD COLUMN mfa_secret TEXT")
            logger.info("Added mfa_secret column to users table")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN backup_codes TEXT"
            )  # JSON array
            logger.info("Added backup_codes column to users table")
        except sqlite3.OperationalError:
            pass  # Column already exists

        conn.commit()
        conn.close()

        logger.info(f"Security database initialized: {self.db_path}")

    def _ensure_default_roles(self):
        """Create default roles if they don't exist."""
        # Check if roles exist
        if self.get_role_by_name("admin"):
            return

        # Create default roles
        admin_role = create_default_admin_role()
        operator_role = create_default_operator_role()
        viewer_role = create_default_viewer_role()

        self.create_role(admin_role)
        self.create_role(operator_role)
        self.create_role(viewer_role)

        logger.info("Default roles created (admin, operator, viewer)")

    # ========================================================================
    # User Management
    # ========================================================================

    async def create_user(
        self, user_create: UserCreate, created_by: Optional[str] = None
    ) -> User:
        """Create a new user."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            # Check if username exists
            cursor.execute(
                "SELECT user_id FROM users WHERE username = ?", (user_create.username,)
            )
            if cursor.fetchone():
                raise ValueError(f"Username '{user_create.username}' already exists")

            # Check if email exists
            cursor.execute(
                "SELECT user_id FROM users WHERE email = ?", (user_create.email,)
            )
            if cursor.fetchone():
                raise ValueError(f"Email '{user_create.email}' already exists")

            # Create user
            from secrets import token_urlsafe

            user_id = token_urlsafe(16)
            now = datetime.utcnow()

            user = User(
                user_id=user_id,
                username=user_create.username,
                email=user_create.email,
                hashed_password=hash_password(user_create.password),
                full_name=user_create.full_name,
                roles=user_create.roles,
                is_active=user_create.is_active,
                must_change_password=user_create.must_change_password,
                created_at=now,
                updated_at=now,
                created_by=created_by,
            )

            # Insert into database
            cursor.execute(
                """
                INSERT INTO users (
                    user_id, username, email, hashed_password, full_name,
                    roles, is_active, is_superuser, must_change_password,
                    password_expires_at, failed_login_attempts, locked_until,
                    last_login, last_login_ip, oauth2_providers, metadata,
                    created_at, updated_at, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    user.user_id,
                    user.username,
                    user.email,
                    user.hashed_password,
                    user.full_name,
                    json.dumps(user.roles),
                    user.is_active,
                    user.is_superuser,
                    user.must_change_password,
                    user.password_expires_at,
                    user.failed_login_attempts,
                    user.locked_until,
                    user.last_login,
                    user.last_login_ip,
                    json.dumps(user.oauth2_providers),
                    json.dumps(user.metadata),
                    user.created_at,
                    user.updated_at,
                    user.created_by,
                ),
            )

            conn.commit()

            # Audit log
            await self.audit_log(
                AuditLogEntry(
                    event_type=AuditEventType.USER_CREATED,
                    user_id=created_by,
                    resource_id=user.user_id,
                    details={"username": user.username, "email": user.email},
                )
            )

            logger.info(f"User created: {user.username} (ID: {user.user_id})")
            return user

        finally:
            conn.close()

    async def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                return None

            return self._user_from_row(row)

        finally:
            conn.close()

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            if not row:
                return None

            return self._user_from_row(row)

        finally:
            conn.close()

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
            row = cursor.fetchone()
            if not row:
                return None

            return self._user_from_row(row)

        finally:
            conn.close()

    async def list_users(self, is_active: Optional[bool] = None) -> List[User]:
        """List all users."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            if is_active is None:
                cursor.execute("SELECT * FROM users ORDER BY username")
            else:
                cursor.execute(
                    "SELECT * FROM users WHERE is_active = ? ORDER BY username",
                    (is_active,),
                )

            return [self._user_from_row(row) for row in cursor.fetchall()]

        finally:
            conn.close()

    async def update_user(self, user_id: str, update: UserUpdate) -> Optional[User]:
        """Update user information."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            user = await self.get_user(user_id)
            if not user:
                return None

            # Update fields
            if update.email is not None:
                user.email = update.email
            if update.full_name is not None:
                user.full_name = update.full_name
            if update.roles is not None:
                user.roles = update.roles
            if update.is_active is not None:
                user.is_active = update.is_active
            if update.is_superuser is not None:
                user.is_superuser = update.is_superuser
            if update.must_change_password is not None:
                user.must_change_password = update.must_change_password

            user.updated_at = datetime.utcnow()

            # Update database
            cursor.execute(
                """
                UPDATE users SET
                    email = ?, full_name = ?, roles = ?, is_active = ?,
                    is_superuser = ?, must_change_password = ?, updated_at = ?
                WHERE user_id = ?
            """,
                (
                    user.email,
                    user.full_name,
                    json.dumps(user.roles),
                    user.is_active,
                    user.is_superuser,
                    user.must_change_password,
                    user.updated_at,
                    user_id,
                ),
            )

            conn.commit()

            logger.info(f"User updated: {user.username}")
            return user

        finally:
            conn.close()

    async def delete_user(self, user_id: str) -> bool:
        """Delete a user."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            user = await self.get_user(user_id)
            if not user:
                return False

            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            conn.commit()

            # Audit log
            await self.audit_log(
                AuditLogEntry(
                    event_type=AuditEventType.USER_DELETED,
                    resource_id=user_id,
                    details={"username": user.username},
                )
            )

            logger.info(f"User deleted: {user.username}")
            return True

        finally:
            conn.close()

    async def change_password(
        self, user_id: str, old_password: str, new_password: str
    ) -> bool:
        """Change user password."""
        user = await self.get_user(user_id)
        if not user:
            return False

        # Verify old password
        if not verify_password(old_password, user.hashed_password):
            return False

        # Update password
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            new_hash = hash_password(new_password)
            cursor.execute(
                """
                UPDATE users SET
                    hashed_password = ?,
                    must_change_password = 0,
                    password_expires_at = ?,
                    updated_at = ?
                WHERE user_id = ?
            """,
                (
                    new_hash,
                    datetime.utcnow()
                    + timedelta(days=self.config.require_password_change_days),
                    datetime.utcnow(),
                    user_id,
                ),
            )

            conn.commit()

            # Audit log
            await self.audit_log(
                AuditLogEntry(
                    event_type=AuditEventType.PASSWORD_CHANGED,
                    user_id=user_id,
                    username=user.username,
                )
            )

            logger.info(f"Password changed for user: {user.username}")
            return True

        finally:
            conn.close()

    def _user_from_row(self, row) -> User:
        """Convert database row to User object."""
        return User(
            user_id=row[0],
            username=row[1],
            email=row[2],
            hashed_password=row[3],
            full_name=row[4],
            roles=json.loads(row[5]) if row[5] else [],
            is_active=bool(row[6]),
            is_superuser=bool(row[7]),
            must_change_password=bool(row[8]),
            password_expires_at=datetime.fromisoformat(row[9]) if row[9] else None,
            failed_login_attempts=row[10] or 0,
            locked_until=datetime.fromisoformat(row[11]) if row[11] else None,
            last_login=datetime.fromisoformat(row[12]) if row[12] else None,
            last_login_ip=row[13],
            oauth2_providers=json.loads(row[14]) if row[14] else {},
            metadata=json.loads(row[15]) if row[15] else {},
            created_at=datetime.fromisoformat(row[16]),
            updated_at=datetime.fromisoformat(row[17]),
            created_by=row[18],
            # MFA fields (indices 19, 20, 21) - handle gracefully if columns don't exist yet
            mfa_enabled=(
                bool(row[19]) if len(row) > 19 and row[19] is not None else False
            ),
            mfa_secret=row[20] if len(row) > 20 else None,
            backup_codes=json.loads(row[21]) if len(row) > 21 and row[21] else [],
        )

    # ========================================================================
    # Multi-Factor Authentication
    # ========================================================================

    async def enable_mfa(
        self, user_id: str, secret: str, backup_codes: List[str]
    ) -> bool:
        """
        Enable MFA for a user.

        Args:
            user_id: User ID
            secret: Base32 encoded TOTP secret
            backup_codes: List of hashed backup codes

        Returns:
            True if successful
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                UPDATE users
                SET mfa_enabled = 1, mfa_secret = ?, backup_codes = ?, updated_at = ?
                WHERE user_id = ?
            """,
                (secret, json.dumps(backup_codes), datetime.utcnow(), user_id),
            )

            conn.commit()
            logger.info(f"MFA enabled for user: {user_id}")
            return cursor.rowcount > 0

        finally:
            conn.close()

    async def disable_mfa(self, user_id: str) -> bool:
        """
        Disable MFA for a user.

        Args:
            user_id: User ID

        Returns:
            True if successful
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                UPDATE users
                SET mfa_enabled = 0, mfa_secret = NULL, backup_codes = NULL, updated_at = ?
                WHERE user_id = ?
            """,
                (datetime.utcnow(), user_id),
            )

            conn.commit()
            logger.info(f"MFA disabled for user: {user_id}")
            return cursor.rowcount > 0

        finally:
            conn.close()

    async def regenerate_backup_codes(self, user_id: str, new_codes: List[str]) -> bool:
        """
        Regenerate backup codes for a user.

        Args:
            user_id: User ID
            new_codes: List of new hashed backup codes

        Returns:
            True if successful
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                UPDATE users
                SET backup_codes = ?, updated_at = ?
                WHERE user_id = ? AND mfa_enabled = 1
            """,
                (json.dumps(new_codes), datetime.utcnow(), user_id),
            )

            conn.commit()
            if cursor.rowcount > 0:
                logger.info(f"Backup codes regenerated for user: {user_id}")
                return True
            else:
                logger.warning(
                    f"Failed to regenerate backup codes for user: {user_id} (MFA not enabled)"
                )
                return False

        finally:
            conn.close()

    async def remove_backup_code(self, user_id: str, used_code_hash: str) -> bool:
        """
        Remove a used backup code from a user's list.

        Args:
            user_id: User ID
            used_code_hash: Hash of the used backup code

        Returns:
            True if successful
        """
        user = await self.get_user(user_id)
        if not user or not user.mfa_enabled:
            return False

        # Remove the used code
        remaining_codes = [code for code in user.backup_codes if code != used_code_hash]

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                UPDATE users
                SET backup_codes = ?, updated_at = ?
                WHERE user_id = ?
            """,
                (json.dumps(remaining_codes), datetime.utcnow(), user_id),
            )

            conn.commit()
            logger.info(
                f"Backup code removed for user: {user_id}. Remaining: {len(remaining_codes)}"
            )
            return True

        finally:
            conn.close()

    # ========================================================================
    # Role Management
    # ========================================================================

    def create_role(self, role: Role) -> Role:
        """Create a new role."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO roles (
                    role_id, name, role_type, description, permissions,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    role.role_id,
                    role.name,
                    role.role_type.value,
                    role.description,
                    json.dumps([p.dict() for p in role.permissions]),
                    role.created_at,
                    role.updated_at,
                ),
            )

            conn.commit()
            logger.info(f"Role created: {role.name}")
            return role

        finally:
            conn.close()

    async def get_role(self, role_id: str) -> Optional[Role]:
        """Get role by ID."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM roles WHERE role_id = ?", (role_id,))
            row = cursor.fetchone()
            if not row:
                return None

            return self._role_from_row(row)

        finally:
            conn.close()

    def get_role_by_name(self, name: str) -> Optional[Role]:
        """Get role by name."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM roles WHERE name = ?", (name,))
            row = cursor.fetchone()
            if not row:
                return None

            return self._role_from_row(row)

        finally:
            conn.close()

    async def list_roles(self) -> List[Role]:
        """List all roles."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM roles ORDER BY name")
            return [self._role_from_row(row) for row in cursor.fetchall()]

        finally:
            conn.close()

    def _role_from_row(self, row) -> Role:
        """Convert database row to Role object."""
        permissions_data = json.loads(row[4])
        permissions = [Permission(**p) for p in permissions_data]

        return Role(
            role_id=row[0],
            name=row[1],
            role_type=RoleType(row[2]),
            description=row[3],
            permissions=permissions,
            created_at=datetime.fromisoformat(row[5]),
            updated_at=datetime.fromisoformat(row[6]),
        )

    # ========================================================================
    # API Key Management
    # ========================================================================

    async def create_api_key(
        self,
        user_id: str,
        key_create: APIKeyCreate,
        created_by: str,
    ) -> APIKey:
        """Create a new API key."""
        from secrets import token_urlsafe

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            now = datetime.utcnow()
            expires_at = None
            if key_create.expires_in_days:
                expires_at = now + timedelta(days=key_create.expires_in_days)

            api_key = APIKey(
                user_id=user_id,
                name=key_create.name,
                description=key_create.description,
                scopes=key_create.scopes,
                expires_at=expires_at,
                created_by=created_by,
            )

            cursor.execute(
                """
                INSERT INTO api_keys (
                    key_id, key, key_prefix, user_id, name, description,
                    scopes, permissions, is_active, expires_at, last_used,
                    last_used_ip, usage_count, created_at, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    api_key.key_id,
                    api_key.key,
                    api_key.key_prefix,
                    api_key.user_id,
                    api_key.name,
                    api_key.description,
                    json.dumps(api_key.scopes),
                    json.dumps([p.dict() for p in api_key.permissions]),
                    api_key.is_active,
                    api_key.expires_at,
                    api_key.last_used,
                    api_key.last_used_ip,
                    api_key.usage_count,
                    now,
                    api_key.created_by,
                ),
            )

            conn.commit()

            # Audit log
            await self.audit_log(
                AuditLogEntry(
                    event_type=AuditEventType.API_KEY_CREATED,
                    user_id=created_by,
                    resource_id=api_key.key_id,
                    details={"name": api_key.name, "user_id": user_id},
                )
            )

            logger.info(f"API key created: {api_key.name} for user {user_id}")
            return api_key

        finally:
            conn.close()

    async def get_api_key(self, key: str) -> Optional[APIKey]:
        """Get API key by key string."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM api_keys WHERE key = ?", (key,))
            row = cursor.fetchone()
            if not row:
                return None

            return self._api_key_from_row(row)

        finally:
            conn.close()

    async def list_api_keys(self, user_id: Optional[str] = None) -> List[APIKey]:
        """List API keys."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            if user_id:
                cursor.execute(
                    "SELECT * FROM api_keys WHERE user_id = ? ORDER BY created_at DESC",
                    (user_id,),
                )
            else:
                cursor.execute("SELECT * FROM api_keys ORDER BY created_at DESC")

            return [self._api_key_from_row(row) for row in cursor.fetchall()]

        finally:
            conn.close()

    async def revoke_api_key(self, key_id: str) -> bool:
        """Revoke an API key."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute(
                "UPDATE api_keys SET is_active = 0 WHERE key_id = ?", (key_id,)
            )
            conn.commit()

            if cursor.rowcount > 0:
                # Audit log
                await self.audit_log(
                    AuditLogEntry(
                        event_type=AuditEventType.API_KEY_REVOKED,
                        resource_id=key_id,
                    )
                )

                logger.info(f"API key revoked: {key_id}")
                return True

            return False

        finally:
            conn.close()

    def _api_key_from_row(self, row) -> APIKey:
        """Convert database row to APIKey object."""
        permissions_data = json.loads(row[7])
        permissions = [Permission(**p) for p in permissions_data]

        return APIKey(
            key_id=row[0],
            key=row[1],
            key_prefix=row[2],
            user_id=row[3],
            name=row[4],
            description=row[5],
            scopes=json.loads(row[6]),
            permissions=permissions,
            is_active=bool(row[8]),
            expires_at=datetime.fromisoformat(row[9]) if row[9] else None,
            last_used=datetime.fromisoformat(row[10]) if row[10] else None,
            last_used_ip=row[11],
            usage_count=row[12] or 0,
            created_at=datetime.fromisoformat(row[13]),
            created_by=row[14],
        )

    # ========================================================================
    # IP Whitelist Management
    # ========================================================================

    async def add_ip_whitelist(
        self, entry_create: IPWhitelistCreate, created_by: str
    ) -> IPWhitelistEntry:
        """Add IP to whitelist."""
        from secrets import token_urlsafe

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            now = datetime.utcnow()
            expires_at = None
            if entry_create.expires_in_days:
                expires_at = now + timedelta(days=entry_create.expires_in_days)

            entry = IPWhitelistEntry(
                ip_address=entry_create.ip_address,
                is_whitelist=entry_create.is_whitelist,
                description=entry_create.description,
                created_by=created_by,
                expires_at=expires_at,
            )

            cursor.execute(
                """
                INSERT INTO ip_whitelist (
                    entry_id, ip_address, is_whitelist, description,
                    created_at, created_by, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    entry.entry_id,
                    entry.ip_address,
                    entry.is_whitelist,
                    entry.description,
                    entry.created_at,
                    entry.created_by,
                    entry.expires_at,
                ),
            )

            conn.commit()

            logger.info(
                f"IP {'whitelist' if entry.is_whitelist else 'blacklist'} entry added: {entry.ip_address}"
            )
            return entry

        finally:
            conn.close()

    async def list_ip_whitelist(self) -> List[IPWhitelistEntry]:
        """List all IP whitelist entries."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM ip_whitelist ORDER BY created_at DESC")
            return [self._ip_whitelist_from_row(row) for row in cursor.fetchall()]

        finally:
            conn.close()

    async def remove_ip_whitelist(self, entry_id: str) -> bool:
        """Remove IP whitelist entry."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM ip_whitelist WHERE entry_id = ?", (entry_id,))
            conn.commit()

            return cursor.rowcount > 0

        finally:
            conn.close()

    def _ip_whitelist_from_row(self, row) -> IPWhitelistEntry:
        """Convert database row to IPWhitelistEntry object."""
        return IPWhitelistEntry(
            entry_id=row[0],
            ip_address=row[1],
            is_whitelist=bool(row[2]),
            description=row[3],
            created_at=datetime.fromisoformat(row[4]),
            created_by=row[5],
            expires_at=datetime.fromisoformat(row[6]) if row[6] else None,
        )

    # ========================================================================
    # Audit Logging
    # ========================================================================

    async def audit_log(self, entry: AuditLogEntry):
        """Record an audit log entry."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO audit_log (
                    entry_id, timestamp, event_type, user_id, username,
                    ip_address, resource_type, resource_id, action, success,
                    error_message, details, auth_method
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    entry.entry_id,
                    entry.timestamp,
                    entry.event_type.value,
                    entry.user_id,
                    entry.username,
                    entry.ip_address,
                    entry.resource_type.value if entry.resource_type else None,
                    entry.resource_id,
                    entry.action,
                    entry.success,
                    entry.error_message,
                    json.dumps(entry.details),
                    entry.auth_method.value if entry.auth_method else None,
                ),
            )

            conn.commit()

        finally:
            conn.close()

    async def query_audit_log(self, query: AuditLogQuery) -> List[AuditLogEntry]:
        """Query audit log."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            sql = "SELECT * FROM audit_log WHERE 1=1"
            params = []

            if query.user_id:
                sql += " AND user_id = ?"
                params.append(query.user_id)

            if query.username:
                sql += " AND username = ?"
                params.append(query.username)

            if query.event_type:
                sql += " AND event_type = ?"
                params.append(query.event_type.value)

            if query.resource_type:
                sql += " AND resource_type = ?"
                params.append(query.resource_type.value)

            if query.start_time:
                sql += " AND timestamp >= ?"
                params.append(query.start_time)

            if query.end_time:
                sql += " AND timestamp <= ?"
                params.append(query.end_time)

            if query.success is not None:
                sql += " AND success = ?"
                params.append(query.success)

            sql += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([query.limit, query.offset])

            cursor.execute(sql, params)
            return [self._audit_log_from_row(row) for row in cursor.fetchall()]

        finally:
            conn.close()

    def _audit_log_from_row(self, row) -> AuditLogEntry:
        """Convert database row to AuditLogEntry object."""
        from .models import AuthMethod, ResourceType

        return AuditLogEntry(
            entry_id=row[0],
            timestamp=datetime.fromisoformat(row[1]),
            event_type=AuditEventType(row[2]),
            user_id=row[3],
            username=row[4],
            ip_address=row[5],
            resource_type=ResourceType(row[6]) if row[6] else None,
            resource_id=row[7],
            action=row[8],
            success=bool(row[9]),
            error_message=row[10],
            details=json.loads(row[11]) if row[11] else {},
            auth_method=AuthMethod(row[12]) if row[12] else None,
        )

    # ========================================================================
    # Security Status
    # ========================================================================

    async def get_security_status(self) -> SecurityStatus:
        """Get overall security system status."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            # Count users
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
            active_users = cursor.fetchone()[0]

            # Count roles
            cursor.execute("SELECT COUNT(*) FROM roles")
            total_roles = cursor.fetchone()[0]

            # Count API keys
            cursor.execute("SELECT COUNT(*) FROM api_keys")
            total_api_keys = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM api_keys WHERE is_active = 1")
            active_api_keys = cursor.fetchone()[0]

            # Count whitelist
            cursor.execute("SELECT COUNT(*) FROM ip_whitelist WHERE is_whitelist = 1")
            whitelist_entries = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM ip_whitelist WHERE is_whitelist = 0")
            blacklist_entries = cursor.fetchone()[0]

            # Failed login attempts in last 24 hours
            since = datetime.utcnow() - timedelta(hours=24)
            cursor.execute(
                """
                SELECT COUNT(*) FROM audit_log
                WHERE event_type = ? AND timestamp >= ?
            """,
                (AuditEventType.LOGIN_FAILED.value, since),
            )
            failed_login_attempts_24h = cursor.fetchone()[0]

            # Active sessions
            active_sessions = len(self.session_manager.get_active_sessions())

            return SecurityStatus(
                enabled=True,
                authentication_required=True,
                ip_whitelisting_enabled=whitelist_entries > 0,
                oauth2_enabled=False,  # TODO: Implement OAuth2
                total_users=total_users,
                active_users=active_users,
                total_roles=total_roles,
                total_api_keys=total_api_keys,
                active_api_keys=active_api_keys,
                whitelist_entries=whitelist_entries,
                blacklist_entries=blacklist_entries,
                failed_login_attempts_24h=failed_login_attempts_24h,
                active_sessions=active_sessions,
            )

        finally:
            conn.close()


# ============================================================================
# Global Instance
# ============================================================================

_security_manager: Optional[SecurityManager] = None


def init_security_manager(
    db_path: str = "data/security.db",
    config: Optional[AuthConfig] = None,
) -> SecurityManager:
    """Initialize global security manager."""
    global _security_manager
    _security_manager = SecurityManager(db_path, config)
    return _security_manager


def get_security_manager() -> SecurityManager:
    """Get global security manager."""
    if _security_manager is None:
        raise RuntimeError("Security manager not initialized")
    return _security_manager
