"""
End-to-end HTTP tests for the authentication endpoints.

These drive the real router against a real SecurityManager on a throwaway
database - no mocking of the auth path - so they exercise the full
login -> authenticated request -> logout -> token rejected lifecycle that
session-bound access tokens introduced.
"""

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../server"))

import security.manager as manager_module
from api.security import router
from security.auth import AuthConfig
from security.manager import SecurityManager
from security.models import UserCreate

PASSWORD = "Str0ng-Passw0rd!"


@pytest.fixture
def security_manager(tmp_path, monkeypatch):
    config = AuthConfig(
        secret_key="integration-test-secret-key",
        access_token_expire_minutes=30,
        max_failed_login_attempts=5,
    )
    mgr = SecurityManager(db_path=str(tmp_path / "security.db"), config=config)
    monkeypatch.setattr(manager_module, "_security_manager", mgr)
    return mgr


@pytest.fixture
def client(security_manager):
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def account(security_manager, event_loop=None):
    """A real user in the real database."""
    import asyncio

    return asyncio.get_event_loop().run_until_complete(
        security_manager.create_user(
            UserCreate(
                username="testuser",
                email="testuser@example.com",
                password=PASSWORD,
                full_name="Test User",
            )
        )
    )


def _login(client, username="testuser", password=PASSWORD):
    return client.post(
        "/api/security/login", json={"username": username, "password": password}
    )


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestLogin:
    def test_login_succeeds_with_valid_credentials(self, client, account):
        response = _login(client)

        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["user"]["username"] == "testuser"

    def test_login_rejects_wrong_password(self, client, account):
        response = _login(client, password="wrong-password")

        assert response.status_code == 401

    def test_login_rejects_unknown_user(self, client, account):
        response = _login(client, username="nobody")

        assert response.status_code == 401

    def test_repeated_failures_lock_the_account(self, client, account):
        for _ in range(5):
            _login(client, password="wrong-password")

        # Even the correct password is refused while locked out.
        response = _login(client)

        assert response.status_code == 429


class TestAuthenticatedAccess:
    def test_token_grants_access(self, client, account):
        token = _login(client).json()["access_token"]

        response = client.get("/api/security/me", headers=_auth(token))

        assert response.status_code == 200
        assert response.json()["username"] == "testuser"

    def test_missing_token_is_rejected(self, client, account):
        assert client.get("/api/security/me").status_code == 401

    def test_garbage_token_is_rejected(self, client, account):
        response = client.get("/api/security/me", headers=_auth("not.a.jwt"))

        assert response.status_code == 401


class TestLogoutRevokesTheToken:
    """The core of the v1.3.0 change, exercised over HTTP."""

    def test_token_stops_working_after_logout(self, client, account):
        token = _login(client).json()["access_token"]
        assert client.get("/api/security/me", headers=_auth(token)).status_code == 200

        logout = client.post("/api/security/logout", headers=_auth(token))
        assert logout.status_code == 200

        after = client.get("/api/security/me", headers=_auth(token))
        assert after.status_code == 401, (
            "access token still works after logout - it is not revocable"
        )

    def test_password_change_revokes_existing_tokens(self, client, account):
        token = _login(client).json()["access_token"]

        changed = client.post(
            "/api/security/users/change-password",
            headers=_auth(token),
            json={"old_password": PASSWORD, "new_password": "An0ther-Passw0rd!"},
        )
        assert changed.status_code == 200

        after = client.get("/api/security/me", headers=_auth(token))
        assert after.status_code == 401, (
            "access token survived a password change"
        )

    def test_logout_does_not_affect_other_users(self, client, security_manager):
        import asyncio

        loop = asyncio.get_event_loop()
        for name in ("alice", "bob"):
            loop.run_until_complete(
                security_manager.create_user(
                    UserCreate(
                        username=name,
                        email=f"{name}@example.com",
                        password=PASSWORD,
                        full_name=name.title(),
                    )
                )
            )
        alice = _login(client, "alice").json()["access_token"]
        bob = _login(client, "bob").json()["access_token"]

        client.post("/api/security/logout", headers=_auth(alice))

        assert client.get("/api/security/me", headers=_auth(bob)).status_code == 200


class TestRefresh:
    def test_refresh_returns_a_working_token(self, client, account):
        refresh_token = _login(client).json()["refresh_token"]

        response = client.post(
            "/api/security/refresh", json={"refresh_token": refresh_token}
        )

        assert response.status_code == 200
        new_token = response.json()["access_token"]
        assert client.get(
            "/api/security/me", headers=_auth(new_token)
        ).status_code == 200

    def test_refreshed_token_is_also_revocable(self, client, account):
        """A token minted by /refresh must be revocable like a login token."""
        refresh_token = _login(client).json()["refresh_token"]
        new_token = client.post(
            "/api/security/refresh", json={"refresh_token": refresh_token}
        ).json()["access_token"]

        client.post("/api/security/logout", headers=_auth(new_token))

        assert client.get(
            "/api/security/me", headers=_auth(new_token)
        ).status_code == 401

    def test_refresh_rejects_a_garbage_token(self, client, account):
        response = client.post(
            "/api/security/refresh", json={"refresh_token": "not.a.jwt"}
        )

        assert response.status_code == 401

    def test_access_token_is_not_accepted_as_a_refresh_token(self, client, account):
        access_token = _login(client).json()["access_token"]

        response = client.post(
            "/api/security/refresh", json={"refresh_token": access_token}
        )

        assert response.status_code == 401
