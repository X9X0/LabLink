"""
Tests for session-bound access tokens (token revocation).

An access token is only accepted while its backing session is alive, so
logout, password change and admin password reset revoke a token immediately
instead of leaving it usable until its natural expiry.
"""

import os
import sys

import pytest
from fastapi import HTTPException
import server.security.manager as manager_module
from server.api.security import get_current_user
from server.security.auth import AuthConfig, create_access_token, decode_token
from server.security.manager import SecurityManager
from server.security.models import AuthMethod, User


@pytest.fixture
def config():
    return AuthConfig(secret_key="test-secret-key-for-revocation-tests")


@pytest.fixture
def security_manager(tmp_path, config, monkeypatch):
    """A real SecurityManager on a throwaway DB, installed as the singleton."""
    mgr = SecurityManager(db_path=str(tmp_path / "security.db"), config=config)
    monkeypatch.setattr(manager_module, "_security_manager", mgr)
    return mgr


@pytest.fixture
def user():
    return User(
        user_id="user-1",
        username="alice",
        email="alice@example.com",
        hashed_password="not-used-here",
        full_name="Alice",
        roles=[],
        is_active=True,
        is_superuser=False,
    )


def _issue_token(security_manager, user, config):
    """Log a user in the way /login does: session first, then bound token."""
    session_id = security_manager.session_manager.create_session(
        user,
        "127.0.0.1",
        auth_method=AuthMethod.PASSWORD,
        expires_in_minutes=config.access_token_expire_minutes,
    )
    token = create_access_token(
        user, config, auth_method=AuthMethod.PASSWORD, session_id=session_id
    )
    return token, session_id


class TestSessionBoundTokens:
    """The token must carry, and be checked against, a live session."""

    def test_access_token_carries_session_id(self, security_manager, user, config):
        token, session_id = _issue_token(security_manager, user, config)

        payload = decode_token(token, config)

        assert payload is not None
        assert payload.session_id == session_id

    def test_session_is_live_immediately_after_login(
        self, security_manager, user, config
    ):
        _, session_id = _issue_token(security_manager, user, config)

        assert security_manager.session_manager.get_session(session_id) is not None

    def test_token_without_session_id_has_none(self, user, config):
        """A token minted without a session (pre-1.3.0 shape) is identifiable."""
        legacy = create_access_token(user, config)

        payload = decode_token(legacy, config)

        assert payload is not None
        assert payload.session_id is None


class TestRevocation:
    """Destroying the session must invalidate the already-issued token."""

    def test_jwt_still_verifies_after_revocation(
        self, security_manager, user, config
    ):
        """The signature stays valid - which is exactly why the session check
        is needed rather than relying on the JWT alone."""
        token, _ = _issue_token(security_manager, user, config)

        security_manager.session_manager.destroy_user_sessions(user.user_id)

        assert decode_token(token, config) is not None

    def test_session_gone_after_logout(self, security_manager, user, config):
        _, session_id = _issue_token(security_manager, user, config)

        destroyed = security_manager.session_manager.destroy_user_sessions(
            user.user_id
        )

        assert destroyed == 1
        assert security_manager.session_manager.get_session(session_id) is None

    def test_only_target_users_sessions_are_revoked(
        self, security_manager, user, config
    ):
        other = user.copy(update={"user_id": "user-2", "username": "bob"})
        _, alice_session = _issue_token(security_manager, user, config)
        _, bob_session = _issue_token(security_manager, other, config)

        security_manager.session_manager.destroy_user_sessions(user.user_id)

        assert security_manager.session_manager.get_session(alice_session) is None
        assert security_manager.session_manager.get_session(bob_session) is not None


class TestGetCurrentUserEnforcement:
    """get_current_user is the choke point that enforces revocation."""

    class _Credentials:
        def __init__(self, token):
            self.credentials = token

    @pytest.mark.asyncio
    async def test_valid_token_with_live_session_is_accepted(
        self, security_manager, config
    ):
        """Guards against the session check rejecting legitimate tokens."""
        from server.security.models import UserCreate

        created = await security_manager.create_user(
            UserCreate(
                username="carol",
                email="carol@example.com",
                password="Str0ng-Passw0rd!",
                full_name="Carol",
            )
        )
        token, _ = _issue_token(security_manager, created, config)

        resolved = await get_current_user(self._Credentials(token))

        assert resolved.user_id == created.user_id
        assert resolved.username == "carol"

    @pytest.mark.asyncio
    async def test_revoked_token_is_rejected_with_401(
        self, security_manager, user, config
    ):
        token, _ = _issue_token(security_manager, user, config)
        security_manager.session_manager.destroy_user_sessions(user.user_id)

        with pytest.raises(HTTPException) as exc:
            await get_current_user(self._Credentials(token))

        assert exc.value.status_code == 401
        assert "revoked" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_token_without_session_id_is_rejected_with_401(
        self, security_manager, user, config
    ):
        """Tokens issued before this change must not be honoured."""
        legacy = create_access_token(user, config)

        with pytest.raises(HTTPException) as exc:
            await get_current_user(self._Credentials(legacy))

        assert exc.value.status_code == 401
        assert "revoked" in exc.value.detail.lower()


class TestSessionPruning:
    """Sessions are pruned on creation so refreshes can't grow the table."""

    def test_expired_sessions_are_pruned_on_create(
        self, security_manager, user, config
    ):
        from datetime import datetime, timedelta, timezone

        sm = security_manager.session_manager
        stale = []
        for _ in range(10):
            sid = sm.create_session(user, "127.0.0.1", AuthMethod.PASSWORD, 30)
            sm._sessions[sid].expires_at = datetime.now(timezone.utc) - timedelta(
                minutes=1
            )
            sm._db_write(
                "UPDATE sessions SET expires_at = ? WHERE session_id = ?",
                (
                    (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
                    sid,
                ),
            )
            stale.append(sid)

        fresh = sm.create_session(user, "127.0.0.1", AuthMethod.PASSWORD, 30)

        assert sm.get_session(fresh) is not None
        for sid in stale:
            assert sm.get_session(sid) is None
