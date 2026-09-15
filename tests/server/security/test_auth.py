"""
Comprehensive tests for security/auth.py module.

Tests cover:
- Password hashing and verification
- JWT token creation and decoding
- Session management
- Login attempt tracking
- Token expiration
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
import sys
import os

# Add server to path
from server.security.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    decode_refresh_token,
    user_to_response,
    AuthConfig,
    SessionManager,
    LoginAttemptTracker,
    generate_secure_secret_key
)
from server.security.models import AuthMethod, User, Role, RoleType, TokenPayload


class TestPasswordHashing:
    """Test password hashing and verification."""

    def test_hash_password(self):
        """Test that password hashing works correctly."""
        password = "test_password_123"
        hashed = hash_password(password)

        assert hashed != password
        assert len(hashed) > 0
        assert hashed.startswith('$2b$')  # bcrypt prefix

    def test_hash_password_different_hashes(self):
        """Test that same password produces different hashes (salt)."""
        password = "same_password"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        assert hash1 != hash2  # Different due to salt

    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        password = "correct_password"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        password = "correct_password"
        wrong_password = "wrong_password"
        hashed = hash_password(password)

        assert verify_password(wrong_password, hashed) is False

    def test_verify_password_empty(self):
        """Test password verification with empty password."""
        hashed = hash_password("test")
        assert verify_password("", hashed) is False


class TestJWTTokens:
    """Test JWT token creation and decoding."""

    @pytest.fixture
    def auth_config(self):
        """Create auth config for testing."""
        return AuthConfig(
            secret_key="test_secret_key_for_jwt_tokens_12345",
            algorithm="HS256",
            access_token_expire_minutes=30,
            refresh_token_expire_days=7
        )

    @pytest.fixture
    def sample_user(self):
        """Create sample user for testing."""
        admin_role = Role(
            name="admin",
            role_type=RoleType.ADMIN,
            permissions=[]
        )
        return User(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            hashed_password=hash_password("password"),
            roles=[admin_role.role_id],
            is_active=True
        )

    def test_create_access_token(self, auth_config, sample_user):
        """Test access token creation."""
        token = create_access_token(
            user=sample_user,
            config=auth_config
        )

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token(self, auth_config, sample_user):
        """Test refresh token creation."""
        token = create_refresh_token(
            user_id=sample_user.user_id,
            config=auth_config
        )

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_access_token(self, auth_config, sample_user):
        """Test decoding valid access token."""
        token = create_access_token(
            user=sample_user,
            config=auth_config
        )

        payload = decode_token(token, config=auth_config)

        assert payload is not None
        assert payload.sub == sample_user.user_id
        assert payload.exp is not None

    def test_decode_refresh_token(self, auth_config, sample_user):
        """Test decoding valid refresh token."""
        token = create_refresh_token(
            user_id=sample_user.user_id,
            config=auth_config
        )

        user_id = decode_refresh_token(token, config=auth_config)

        assert user_id == sample_user.user_id

    def test_decode_token_rejects_a_refresh_token(self, auth_config, sample_user):
        """A refresh token must not be usable as an access token."""
        refresh = create_refresh_token(
            user_id=sample_user.user_id, config=auth_config
        )

        assert decode_token(refresh, config=auth_config) is None

    def test_decode_invalid_token(self, auth_config):
        """Test decoding invalid token."""
        invalid_token = "invalid.jwt.token"

        payload = decode_token(invalid_token, config=auth_config)
        assert payload is None

    def test_decode_expired_token(self, auth_config):
        """Test decoding expired token."""
        # Create token with past expiration
        past_time = datetime.utcnow() - timedelta(hours=1)
        token_data = {
            "sub": "testuser",
            "exp": past_time
        }

        import jwt
        token = jwt.encode(token_data, auth_config.secret_key, algorithm=auth_config.algorithm)

        payload = decode_token(token, config=auth_config)
        assert payload is None

    def test_token_with_additional_claims(self, auth_config, sample_user):
        """Test token encodes user information."""
        token = create_access_token(user=sample_user, config=auth_config)
        payload = decode_token(token, config=auth_config)

        # Check that the token contains user information
        assert payload.sub == sample_user.user_id
        assert payload.username == sample_user.username
        assert payload.exp is not None


class TestUserToResponse:
    """Test user_to_response function."""

    def test_user_to_response(self):
        """Test converting user to response model."""
        admin_role = Role(
            name="admin",
            role_type=RoleType.ADMIN,
            permissions=[]
        )
        user = User(
            user_id="user-123",
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            hashed_password=hash_password("password"),
            roles=[admin_role.role_id],
            is_active=True
        )

        response = user_to_response(user)

        assert response.user_id == "user-123"
        assert response.username == "testuser"
        assert response.email == "test@example.com"
        assert response.full_name == "Test User"
        assert response.is_active is True
        assert len(response.roles) == 1
        assert response.roles == [admin_role.role_id]
        # Password should not be in response
        assert not hasattr(response, 'hashed_password')


class TestSessionManager:
    """Test session management.

    Sessions are keyed by a generated session_id (not by token) and are
    hard-deleted on destroy; the access token carries the session_id so the
    token can be revoked by destroying its session.
    """

    @pytest.fixture
    def session_manager(self):
        """Create session manager for testing (in-memory, no DB)."""
        return SessionManager()

    @pytest.fixture
    def sample_user(self):
        """Create sample user for testing."""
        return User(
            user_id="user-123",
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            hashed_password=hash_password("password"),
            roles=[],
            is_active=True,
            is_superuser=False,
        )

    def test_create_session(self, session_manager, sample_user):
        """Test creating a new session."""
        session_id = session_manager.create_session(
            sample_user,
            "192.168.1.100",
            auth_method=AuthMethod.PASSWORD,
            expires_in_minutes=30,
        )

        assert session_id
        session = session_manager.get_session(session_id)
        assert session is not None
        assert session.user_id == sample_user.user_id
        assert session.username == sample_user.username
        assert session.ip_address == "192.168.1.100"
        assert session.auth_method == AuthMethod.PASSWORD
        assert session.created_at is not None

    def test_session_ids_are_unique(self, session_manager, sample_user):
        """Each login must get its own revocable session."""
        first = session_manager.create_session(
            sample_user, "10.0.0.1", AuthMethod.PASSWORD, 30
        )
        second = session_manager.create_session(
            sample_user, "10.0.0.1", AuthMethod.PASSWORD, 30
        )

        assert first != second

    def test_get_session(self, session_manager, sample_user):
        """Test retrieving a session."""
        session_id = session_manager.create_session(
            sample_user, "192.168.1.100", AuthMethod.PASSWORD, 30
        )

        retrieved = session_manager.get_session(session_id)

        assert retrieved is not None
        assert retrieved.session_id == session_id
        assert retrieved.user_id == sample_user.user_id

    def test_get_nonexistent_session(self, session_manager):
        """Test retrieving a nonexistent session."""
        assert session_manager.get_session("nonexistent-session-id") is None

    def test_expired_session_is_not_returned(self, session_manager, sample_user):
        """An expired session must not authenticate a request."""
        session_id = session_manager.create_session(
            sample_user, "192.168.1.100", AuthMethod.PASSWORD, 30
        )
        session_manager._sessions[session_id].expires_at = datetime.now(
            timezone.utc
        ) - timedelta(minutes=1)

        assert session_manager.get_session(session_id) is None

    def test_destroy_session(self, session_manager, sample_user):
        """Test destroying a single session."""
        session_id = session_manager.create_session(
            sample_user, "192.168.1.100", AuthMethod.PASSWORD, 30
        )

        assert session_manager.destroy_session(session_id) is True
        assert session_manager.get_session(session_id) is None

    def test_destroy_unknown_session_returns_false(self, session_manager):
        assert session_manager.destroy_session("no-such-session") is False

    def test_get_user_sessions(self, session_manager, sample_user):
        """Test getting all sessions for a user."""
        for _ in range(3):
            session_manager.create_session(
                sample_user, "192.168.1.100", AuthMethod.PASSWORD, 30
            )

        sessions = session_manager.get_user_sessions(sample_user.user_id)

        assert len(sessions) == 3
        assert all(s.user_id == sample_user.user_id for s in sessions)

    def test_destroy_user_sessions(self, session_manager, sample_user):
        """Logout / password change revokes every session for the user."""
        for _ in range(3):
            session_manager.create_session(
                sample_user, "192.168.1.100", AuthMethod.PASSWORD, 30
            )

        destroyed = session_manager.destroy_user_sessions(sample_user.user_id)

        assert destroyed == 3
        assert session_manager.get_user_sessions(sample_user.user_id) == []

    def test_destroy_user_sessions_leaves_other_users(
        self, session_manager, sample_user
    ):
        other = sample_user.copy(update={"user_id": "user-999", "username": "other"})
        session_manager.create_session(
            sample_user, "192.168.1.100", AuthMethod.PASSWORD, 30
        )
        other_session = session_manager.create_session(
            other, "192.168.1.101", AuthMethod.PASSWORD, 30
        )

        session_manager.destroy_user_sessions(sample_user.user_id)

        assert session_manager.get_session(other_session) is not None

    def test_cleanup_expired_sessions(self, session_manager, sample_user):
        """Expired sessions are removed so the store cannot grow forever."""
        # Create every session first: create_session() prunes as it goes, so
        # expiring them beforehand would let creation do the cleanup instead.
        live = session_manager.create_session(
            sample_user, "192.168.1.100", AuthMethod.PASSWORD, 30
        )
        stale = [
            session_manager.create_session(
                sample_user, "192.168.1.100", AuthMethod.PASSWORD, 30
            )
            for _ in range(3)
        ]
        for sid in stale:
            session_manager._sessions[sid].expires_at = datetime.now(
                timezone.utc
            ) - timedelta(minutes=1)

        removed = session_manager.cleanup_expired_sessions()

        assert removed == 3
        assert session_manager.get_session(live) is not None

    def test_creating_a_session_prunes_expired_ones(
        self, session_manager, sample_user
    ):
        """Token refresh creates a session each time; expired ones must go."""
        stale = session_manager.create_session(
            sample_user, "192.168.1.100", AuthMethod.PASSWORD, 30
        )
        session_manager._sessions[stale].expires_at = datetime.now(
            timezone.utc
        ) - timedelta(minutes=1)

        fresh = session_manager.create_session(
            sample_user, "192.168.1.100", AuthMethod.PASSWORD, 30
        )

        assert stale not in session_manager._sessions
        assert session_manager.get_session(fresh) is not None


class TestLoginAttemptTracker:
    """Test login attempt tracking and account lockout.

    The tracker is configured from AuthConfig (max_failed_login_attempts /
    account_lockout_duration_minutes), not from constructor kwargs.
    """

    @pytest.fixture
    def tracker(self):
        """Create login attempt tracker for testing."""
        return LoginAttemptTracker(
            AuthConfig(
                secret_key="test-secret-key",
                max_failed_login_attempts=5,
                account_lockout_duration_minutes=30,
            )
        )

    def test_record_failed_attempt(self, tracker):
        """Test recording failed login attempts."""
        assert tracker.record_failed_attempt("testuser") == 1
        assert tracker.get_attempt_count("testuser") == 1

    def test_multiple_failed_attempts(self, tracker):
        """Test recording multiple failed attempts."""
        for _ in range(3):
            tracker.record_failed_attempt("testuser")

        assert tracker.get_attempt_count("testuser") == 3

    def test_unknown_user_has_no_attempts(self, tracker):
        assert tracker.get_attempt_count("never-seen") == 0

    def test_is_locked_out_false(self, tracker):
        """Test account not locked out with few attempts."""
        for _ in range(3):
            tracker.record_failed_attempt("testuser")

        assert tracker.is_locked_out("testuser") is False

    def test_is_locked_out_true(self, tracker):
        """Test account locked out at max attempts."""
        for _ in range(5):
            tracker.record_failed_attempt("testuser")

        assert tracker.is_locked_out("testuser") is True

    def test_attempts_are_per_username(self, tracker):
        for _ in range(5):
            tracker.record_failed_attempt("victim")
        tracker.record_failed_attempt("bystander")

        assert tracker.is_locked_out("victim") is True
        assert tracker.is_locked_out("bystander") is False

    def test_clear_attempts_on_success(self, tracker):
        """Test clearing attempts after successful login."""
        for _ in range(3):
            tracker.record_failed_attempt("testuser")

        tracker.clear_attempts("testuser")

        assert tracker.get_attempt_count("testuser") == 0
        assert tracker.is_locked_out("testuser") is False

    def test_lockout_time_remaining(self, tracker):
        """A locked-out account reports how long it stays locked."""
        for _ in range(5):
            tracker.record_failed_attempt("testuser")

        remaining = tracker.get_lockout_time_remaining("testuser")

        assert remaining is not None
        assert 0 < remaining <= 30 * 60

    def test_no_lockout_time_when_not_locked(self, tracker):
        tracker.record_failed_attempt("testuser")

        assert tracker.get_lockout_time_remaining("testuser") is None

    def test_old_attempts_fall_outside_the_window(self):
        """Attempts older than the lockout window stop counting."""
        tracker = LoginAttemptTracker(
            AuthConfig(
                secret_key="test-secret-key",
                max_failed_login_attempts=3,
                account_lockout_duration_minutes=30,
            )
        )
        for _ in range(3):
            tracker.record_failed_attempt("testuser")
        assert tracker.is_locked_out("testuser") is True

        tracker._attempts["testuser"] = [
            datetime.now(timezone.utc) - timedelta(minutes=31)
            for _ in range(3)
        ]

        assert tracker.get_attempt_count("testuser") == 0
        assert tracker.is_locked_out("testuser") is False
