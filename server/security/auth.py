"""
Authentication System for LabLink

Provides JWT-based authentication with:
- Password hashing (bcrypt)
- Token generation and validation
- Refresh tokens
- Session management
"""

import logging
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

# Password hashing
import bcrypt
# JWT tokens
import jwt
from jwt import PyJWTError

from .models import (AuthMethod, SessionInfo, TokenPayload, TokenResponse,
                     User, UserResponse)

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================


class AuthConfig:
    """Authentication configuration."""

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 30,
        refresh_token_expire_days: int = 7,
        password_reset_expire_hours: int = 24,
        max_failed_login_attempts: int = 5,
        account_lockout_duration_minutes: int = 30,
        require_password_change_days: int = 90,
    ):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days
        self.password_reset_expire_hours = password_reset_expire_hours
        self.max_failed_login_attempts = max_failed_login_attempts
        self.account_lockout_duration_minutes = account_lockout_duration_minutes
        self.require_password_change_days = require_password_change_days


# ============================================================================
# Password Hashing
# ============================================================================


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Hashed password
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash.

    Args:
        plain_password: Plain text password
        hashed_password: Bcrypt hashed password

    Returns:
        True if password matches
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False


# ============================================================================
# JWT Token Management
# ============================================================================


def create_access_token(
    user: User,
    config: AuthConfig,
    auth_method: AuthMethod = AuthMethod.PASSWORD,
) -> str:
    """
    Create a JWT access token.

    Args:
        user: User object
        config: Authentication configuration
        auth_method: How the user authenticated

    Returns:
        Encoded JWT token
    """
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=config.access_token_expire_minutes)

    payload = TokenPayload(
        sub=user.user_id,
        username=user.username,
        roles=user.roles,
        is_superuser=user.is_superuser,
        exp=expires,
        iat=now,
        auth_method=auth_method,
    )

    token = jwt.encode(payload.dict(), config.secret_key, algorithm=config.algorithm)

    return token


def create_refresh_token(user_id: str, config: AuthConfig) -> str:
    """
    Create a refresh token.

    Args:
        user_id: User ID
        config: Authentication configuration

    Returns:
        Encoded JWT refresh token
    """
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=config.refresh_token_expire_days)

    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": expires,
        "iat": now,
        "jti": secrets.token_urlsafe(16),  # Unique token ID
    }

    token = jwt.encode(payload, config.secret_key, algorithm=config.algorithm)

    return token


def decode_token(token: str, config: AuthConfig) -> Optional[TokenPayload]:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT token string
        config: Authentication configuration

    Returns:
        TokenPayload if valid, None otherwise
    """
    try:
        payload = jwt.decode(token, config.secret_key, algorithms=[config.algorithm])

        # Check if it's a refresh token
        if payload.get("type") == "refresh":
            return None

        return TokenPayload(**payload)

    except PyJWTError as e:
        logger.warning(f"Token validation failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Token decode error: {e}")
        return None


def decode_refresh_token(token: str, config: AuthConfig) -> Optional[str]:
    """
    Decode a refresh token.

    Args:
        token: Refresh token string
        config: Authentication configuration

    Returns:
        User ID if valid, None otherwise
    """
    try:
        payload = jwt.decode(token, config.secret_key, algorithms=[config.algorithm])

        # Verify it's a refresh token
        if payload.get("type") != "refresh":
            return None

        return payload.get("sub")

    except PyJWTError as e:
        logger.warning(f"Refresh token validation failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Refresh token decode error: {e}")
        return None


# ============================================================================
# Session Management
# ============================================================================


class SessionManager:
    """Manages active user sessions with optional SQLite write-through."""

    def __init__(self, db_path: Optional[Path] = None):
        self._sessions: Dict[str, SessionInfo] = {}  # session_id -> SessionInfo
        self._db_path = db_path

        if db_path is not None:
            self._rehydrate_sessions()

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def _db_write(self, sql: str, params: tuple = ()):
        """Execute a single write statement on the sessions DB."""
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    def _rehydrate_sessions(self):
        """Load non-expired sessions from DB into the in-memory dict."""
        conn = sqlite3.connect(str(self._db_path))
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc)
            cursor.execute(
                "SELECT session_id, user_id, username, ip_address, auth_method, "
                "created_at, expires_at, last_activity FROM sessions WHERE expires_at > ?",
                (now.isoformat(),),
            )
            loaded = 0
            for row in cursor.fetchall():
                try:
                    session = SessionInfo(
                        session_id=row[0],
                        user_id=row[1],
                        username=row[2],
                        ip_address=row[3],
                        auth_method=AuthMethod(row[4]),
                        created_at=datetime.fromisoformat(row[5]),
                        expires_at=datetime.fromisoformat(row[6]),
                        last_activity=datetime.fromisoformat(row[7]),
                    )
                    self._sessions[row[0]] = session
                    loaded += 1
                except Exception as e:
                    logger.warning(f"Failed to rehydrate session {row[0]}: {e}")
            logger.info(f"Rehydrated {loaded} sessions from database")
        except Exception as e:
            logger.warning(f"Session rehydration skipped: {e}")
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Session operations
    # ------------------------------------------------------------------

    def create_session(
        self,
        user: User,
        ip_address: str,
        auth_method: AuthMethod,
        expires_in_minutes: int = 30,
    ) -> str:
        """Create a new session."""
        session_id = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=expires_in_minutes)

        session = SessionInfo(
            session_id=session_id,
            user_id=user.user_id,
            username=user.username,
            ip_address=ip_address,
            auth_method=auth_method,
            created_at=now,
            expires_at=expires_at,
            last_activity=now,
        )

        self._sessions[session_id] = session

        if self._db_path is not None:
            self._db_write(
                "INSERT OR REPLACE INTO sessions "
                "(session_id, user_id, username, ip_address, auth_method, "
                "created_at, expires_at, last_activity) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    user.user_id,
                    user.username,
                    ip_address,
                    auth_method.value,
                    now.isoformat(),
                    expires_at.isoformat(),
                    now.isoformat(),
                ),
            )

        logger.info(f"Session created for user {user.username} from {ip_address}")
        return session_id

    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """Get session by ID."""
        session = self._sessions.get(session_id)

        if not session:
            return None

        # Check if expired
        if datetime.now(timezone.utc) > session.expires_at:
            self.destroy_session(session_id)
            return None

        # Update last activity
        session.last_activity = datetime.now(timezone.utc)
        if self._db_path is not None:
            self._db_write(
                "UPDATE sessions SET last_activity = ? WHERE session_id = ?",
                (session.last_activity.isoformat(), session_id),
            )
        return session

    def destroy_session(self, session_id: str) -> bool:
        """Destroy a session."""
        if session_id in self._sessions:
            session = self._sessions[session_id]
            del self._sessions[session_id]
            if self._db_path is not None:
                self._db_write(
                    "DELETE FROM sessions WHERE session_id = ?", (session_id,)
                )
            logger.info(f"Session destroyed for user {session.username}")
            return True
        return False

    def destroy_user_sessions(self, user_id: str) -> int:
        """Destroy all sessions for a user."""
        count = 0
        session_ids = list(self._sessions.keys())
        for session_id in session_ids:
            session = self._sessions[session_id]
            if session.user_id == user_id:
                # Remove from memory without triggering individual DB deletes;
                # the bulk DELETE below handles the DB side atomically.
                del self._sessions[session_id]
                logger.info(f"Session destroyed for user {session.username}")
                count += 1

        # Bulk-delete all sessions for this user from DB in one query, which
        # also catches any orphaned DB rows that were not in _sessions.
        if self._db_path is not None:
            self._db_write(
                "DELETE FROM sessions WHERE user_id = ?", (user_id,)
            )

        return count

    def get_active_sessions(self) -> list[SessionInfo]:
        """Get all active sessions."""
        now = datetime.now(timezone.utc)
        active = []

        # Clean up expired sessions
        session_ids = list(self._sessions.keys())
        for session_id in session_ids:
            session = self._sessions[session_id]
            if now > session.expires_at:
                self.destroy_session(session_id)
            else:
                active.append(session)

        return active

    def get_user_sessions(self, user_id: str) -> list[SessionInfo]:
        """Get all sessions for a user."""
        return [s for s in self.get_active_sessions() if s.user_id == user_id]

    def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions."""
        now = datetime.now(timezone.utc)
        count = 0

        session_ids = list(self._sessions.keys())
        for session_id in session_ids:
            session = self._sessions[session_id]
            if now > session.expires_at:
                self.destroy_session(session_id)
                count += 1

        # Bulk-delete any orphaned expired rows from DB
        if self._db_path is not None:
            self._db_write(
                "DELETE FROM sessions WHERE expires_at <= ?", (now.isoformat(),)
            )

        return count


# ============================================================================
# Login Attempt Tracking
# ============================================================================


class LoginAttemptTracker:
    """Tracks failed login attempts for account lockout."""

    def __init__(self, config: AuthConfig):
        self.config = config
        self._attempts: Dict[str, list[datetime]] = {}  # username -> [timestamps]

    def record_failed_attempt(self, username: str) -> int:
        """
        Record a failed login attempt.

        Returns:
            Number of failed attempts
        """
        now = datetime.now(timezone.utc)

        if username not in self._attempts:
            self._attempts[username] = []

        self._attempts[username].append(now)

        # Clean old attempts (older than lockout duration)
        cutoff = now - timedelta(minutes=self.config.account_lockout_duration_minutes)
        self._attempts[username] = [t for t in self._attempts[username] if t > cutoff]

        return len(self._attempts[username])

    def clear_attempts(self, username: str):
        """Clear failed attempts for a user."""
        if username in self._attempts:
            del self._attempts[username]

    def get_attempt_count(self, username: str) -> int:
        """Get current failed attempt count."""
        if username not in self._attempts:
            return 0

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=self.config.account_lockout_duration_minutes)

        # Filter recent attempts
        recent_attempts = [t for t in self._attempts[username] if t > cutoff]

        self._attempts[username] = recent_attempts
        return len(recent_attempts)

    def is_locked_out(self, username: str) -> bool:
        """Check if account is locked out."""
        return self.get_attempt_count(username) >= self.config.max_failed_login_attempts

    def get_lockout_time_remaining(self, username: str) -> Optional[int]:
        """
        Get remaining lockout time in seconds.

        Returns:
            Seconds remaining, or None if not locked out
        """
        if not self.is_locked_out(username):
            return None

        if username not in self._attempts or not self._attempts[username]:
            return None

        # Lockout expires after duration from first failed attempt
        first_attempt = min(self._attempts[username])
        lockout_until = first_attempt + timedelta(
            minutes=self.config.account_lockout_duration_minutes
        )
        remaining = (lockout_until - datetime.now(timezone.utc)).total_seconds()

        return max(0, int(remaining))


# ============================================================================
# Helper Functions
# ============================================================================


def generate_secure_secret_key(length: int = 64) -> str:
    """Generate a secure secret key for JWT signing."""
    return secrets.token_urlsafe(length)


def user_to_response(user: User) -> UserResponse:
    """Convert User to UserResponse."""
    return UserResponse(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        roles=user.roles,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        must_change_password=user.must_change_password,
        mfa_enabled=user.mfa_enabled,
        last_login=user.last_login,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
