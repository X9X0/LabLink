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
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import sys
import os

# Add server to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../server'))

from security.auth import (
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
from security.models import User, Role, RoleType, TokenPayload


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
            roles=[admin_role],
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
        assert payload["sub"] == sample_user.user_id
        assert "exp" in payload

    def test_decode_refresh_token(self, auth_config, sample_user):
        """Test decoding valid refresh token."""
        token = create_refresh_token(
            user_id=sample_user.user_id,
            config=auth_config
        )

        payload = decode_token(token, config=auth_config)

        assert payload is not None
        assert payload["sub"] == sample_user.user_id
        assert "exp" in payload

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
        assert payload["sub"] == sample_user.user_id
        assert "exp" in payload
        # Additional claims would be added based on the actual implementation


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
        assert response.roles[0].name == "admin"
        # Password should not be in response
        assert not hasattr(response, 'hashed_password')


class TestSessionManager:
    """Test session management."""

    @pytest.fixture
    def session_manager(self):
        """Create session manager for testing."""
        return SessionManager()

    @pytest.fixture
    def sample_user(self):
        """Create sample user for testing."""
        return User(
            id="user-123",
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            hashed_password=hash_password("password"),
            roles=[],
            is_active=True
        )

    def test_create_session(self, session_manager, sample_user):
        """Test creating a new session."""
        token = "test-token-123"
        ip_address = "192.168.1.100"
        user_agent = "Mozilla/5.0"

        session = session_manager.create_session(
            user_id=sample_user.user_id,
            username=sample_user.username,
            token=token,
            ip_address=ip_address,
            user_agent=user_agent
        )

        assert session.user_id == sample_user.user_id
        assert session.username == sample_user.username
        assert session.token == token
        assert session.ip_address == ip_address
        assert session.user_agent == user_agent
        assert session.is_active is True
        assert session.created_at is not None

    def test_get_session(self, session_manager, sample_user):
        """Test retrieving a session."""
        token = "test-token-456"
        session = session_manager.create_session(
            user_id=sample_user.user_id,
            username=sample_user.username,
            token=token,
            ip_address="192.168.1.100",
            user_agent="Test Agent"
        )

        retrieved = session_manager.get_session(token)
        assert retrieved is not None
        assert retrieved.token == token
        assert retrieved.user_id == sample_user.user_id

    def test_get_nonexistent_session(self, session_manager):
        """Test retrieving a nonexistent session."""
        retrieved = session_manager.get_session("nonexistent-token")
        assert retrieved is None

    def test_invalidate_session(self, session_manager, sample_user):
        """Test invalidating a session."""
        token = "test-token-789"
        session_manager.create_session(
            user_id=sample_user.user_id,
            username=sample_user.username,
            token=token,
            ip_address="192.168.1.100",
            user_agent="Test Agent"
        )

        session_manager.invalidate_session(token)

        # Session should be marked as inactive
        session = session_manager.get_session(token)
        assert session is not None
        assert session.is_active is False
        assert session.logout_at is not None

    def test_get_user_sessions(self, session_manager, sample_user):
        """Test getting all sessions for a user."""
        # Create multiple sessions
        tokens = ["token-1", "token-2", "token-3"]
        for token in tokens:
            session_manager.create_session(
                user_id=sample_user.user_id,
                username=sample_user.username,
                token=token,
                ip_address="192.168.1.100",
                user_agent="Test Agent"
            )

        sessions = session_manager.get_user_sessions(sample_user.user_id)
        assert len(sessions) == 3
        assert all(s.user_id == sample_user.user_id for s in sessions)

    def test_invalidate_all_user_sessions(self, session_manager, sample_user):
        """Test invalidating all sessions for a user."""
        # Create multiple sessions
        tokens = ["token-a", "token-b", "token-c"]
        for token in tokens:
            session_manager.create_session(
                user_id=sample_user.user_id,
                username=sample_user.username,
                token=token,
                ip_address="192.168.1.100",
                user_agent="Test Agent"
            )

        session_manager.invalidate_all_user_sessions(sample_user.user_id)

        sessions = session_manager.get_user_sessions(sample_user.user_id)
        assert all(not s.is_active for s in sessions)


class TestLoginAttemptTracker:
    """Test login attempt tracking and account lockout."""

    @pytest.fixture
    def tracker(self):
        """Create login attempt tracker for testing."""
        return LoginAttemptTracker(
            max_attempts=5,
            lockout_duration_minutes=30
        )

    def test_record_failed_attempt(self, tracker):
        """Test recording failed login attempts."""
        username = "testuser"

        tracker.record_failed_attempt(username)

        attempts = tracker.get_failed_attempts(username)
        assert attempts == 1

    def test_multiple_failed_attempts(self, tracker):
        """Test recording multiple failed attempts."""
        username = "testuser"

        for i in range(3):
            tracker.record_failed_attempt(username)

        attempts = tracker.get_failed_attempts(username)
        assert attempts == 3

    def test_is_locked_out_false(self, tracker):
        """Test account not locked out with few attempts."""
        username = "testuser"

        for i in range(3):
            tracker.record_failed_attempt(username)

        assert tracker.is_locked_out(username) is False

    def test_is_locked_out_true(self, tracker):
        """Test account locked out after max attempts."""
        username = "testuser"

        for i in range(6):  # More than max_attempts (5)
            tracker.record_failed_attempt(username)

        assert tracker.is_locked_out(username) is True

    def test_reset_attempts_on_success(self, tracker):
        """Test resetting attempts after successful login."""
        username = "testuser"

        for i in range(3):
            tracker.record_failed_attempt(username)

        tracker.reset_attempts(username)

        attempts = tracker.get_failed_attempts(username)
        assert attempts == 0
        assert tracker.is_locked_out(username) is False

    def test_lockout_expiration(self, tracker):
        """Test that lockout expires after duration."""
        # Create tracker with very short lockout
        short_tracker = LoginAttemptTracker(
            max_attempts=3,
            lockout_duration_minutes=0.01  # ~0.6 seconds
        )

        username = "testuser"

        # Lock out the account
        for i in range(4):
            short_tracker.record_failed_attempt(username)

        assert short_tracker.is_locked_out(username) is True

        # Wait for lockout to expire
        import time
        time.sleep(1)

        # Should be unlocked now
        assert short_tracker.is_locked_out(username) is False


class TestSecretKeyGeneration:
    """Test secure secret key generation."""

    def test_generate_secure_secret_key(self):
        """Test generating secure secret key."""
        key = generate_secure_secret_key()

        assert key is not None
        assert isinstance(key, str)
        assert len(key) >= 32  # Should be at least 32 characters

    def test_generate_different_keys(self):
        """Test that each generation produces different key."""
        key1 = generate_secure_secret_key()
        key2 = generate_secure_secret_key()

        assert key1 != key2


class TestAuthConfig:
    """Test AuthConfig class."""

    def test_auth_config_creation(self):
        """Test creating auth config."""
        config = AuthConfig(
            secret_key="test-secret",
            algorithm="HS256",
            access_token_expire_minutes=30,
            refresh_token_expire_days=7
        )

        assert config.secret_key == "test-secret"
        assert config.algorithm == "HS256"
        assert config.access_token_expire_minutes == 30
        assert config.refresh_token_expire_days == 7

    def test_auth_config_defaults(self):
        """Test auth config with default values."""
        config = AuthConfig(secret_key="test-secret")

        assert config.algorithm == "HS256"
        assert config.access_token_expire_minutes == 30
        assert config.refresh_token_expire_days == 7


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
