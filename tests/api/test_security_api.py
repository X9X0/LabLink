"""
End-to-end HTTP tests for the user-management and role endpoints.

These drive the real router against a real SecurityManager on a throwaway
database. Authentication lifecycle tests live in
test_security_api_integration.py; this module covers user CRUD, the superuser
authorization on those endpoints, and role listing.
"""

import asyncio
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
        secret_key="user-management-test-secret-key",
        access_token_expire_minutes=30,
        max_failed_login_attempts=50,  # these tests log in repeatedly
    )
    mgr = SecurityManager(db_path=str(tmp_path / "security.db"), config=config)
    monkeypatch.setattr(manager_module, "_security_manager", mgr)
    return mgr


@pytest.fixture
def api(security_manager):
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _make_user(security_manager, username, is_superuser=False):
    user = asyncio.run(
        security_manager.create_user(
            UserCreate(
                username=username,
                email=f"{username}@example.com",
                password=PASSWORD,
                full_name=username.title(),
            )
        )
    )
    if is_superuser:
        # Promote directly in the DB; there is no "make superuser" endpoint.
        import sqlite3

        conn = sqlite3.connect(str(security_manager.db_path))
        try:
            conn.execute(
                "UPDATE users SET is_superuser = 1 WHERE user_id = ?", (user.user_id,)
            )
            conn.commit()
        finally:
            conn.close()
    return user


def _token(api, username):
    response = api.post(
        "/api/security/login", json={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_token(api, security_manager):
    _make_user(security_manager, "admin", is_superuser=True)
    return _token(api, "admin")


@pytest.fixture
def plain_token(api, security_manager):
    _make_user(security_manager, "operator")
    return _token(api, "operator")


@pytest.mark.api
class TestCreateUser:
    def test_superuser_can_create_a_user(self, api, admin_token):
        response = api.post(
            "/api/security/users",
            headers=_auth(admin_token),
            json={
                "username": "newuser",
                "email": "newuser@example.com",
                "password": PASSWORD,
                "full_name": "New User",
            },
        )

        assert response.status_code == 200, response.text
        assert response.json()["username"] == "newuser"

    def test_duplicate_username_is_rejected(self, api, admin_token):
        payload = {
            "username": "dupe",
            "email": "dupe@example.com",
            "password": PASSWORD,
            "full_name": "Dupe",
        }
        assert api.post(
            "/api/security/users", headers=_auth(admin_token), json=payload
        ).status_code == 200

        second = api.post(
            "/api/security/users", headers=_auth(admin_token), json=payload
        )

        assert second.status_code == 400

    def test_non_superuser_cannot_create_a_user(self, api, plain_token):
        """The authorization check the previous mocked tests never exercised."""
        response = api.post(
            "/api/security/users",
            headers=_auth(plain_token),
            json={
                "username": "sneaky",
                "email": "sneaky@example.com",
                "password": PASSWORD,
                "full_name": "Sneaky",
            },
        )

        assert response.status_code == 403

    def test_unauthenticated_cannot_create_a_user(self, api):
        response = api.post(
            "/api/security/users",
            json={
                "username": "anon",
                "email": "anon@example.com",
                "password": PASSWORD,
                "full_name": "Anon",
            },
        )

        assert response.status_code == 401

    def test_weak_password_is_rejected(self, api, admin_token):
        response = api.post(
            "/api/security/users",
            headers=_auth(admin_token),
            json={
                "username": "weak",
                "email": "weak@example.com",
                "password": "short",
                "full_name": "Weak",
            },
        )

        assert response.status_code == 422


@pytest.mark.api
class TestListAndGetUsers:
    def test_superuser_can_list_users(self, api, admin_token, security_manager):
        _make_user(security_manager, "listed")

        response = api.get("/api/security/users", headers=_auth(admin_token))

        assert response.status_code == 200
        assert {u["username"] for u in response.json()} >= {"admin", "listed"}

    def test_non_superuser_cannot_list_users(self, api, plain_token):
        response = api.get("/api/security/users", headers=_auth(plain_token))

        assert response.status_code == 403

    def test_user_can_read_their_own_record(self, api, security_manager):
        user = _make_user(security_manager, "selfreader")
        token = _token(api, "selfreader")

        response = api.get(
            f"/api/security/users/{user.user_id}", headers=_auth(token)
        )

        assert response.status_code == 200
        assert response.json()["username"] == "selfreader"

    def test_user_cannot_read_another_users_record(self, api, security_manager):
        other = _make_user(security_manager, "other")
        _make_user(security_manager, "nosy")
        token = _token(api, "nosy")

        response = api.get(
            f"/api/security/users/{other.user_id}", headers=_auth(token)
        )

        assert response.status_code == 403

    def test_unknown_user_id_returns_404(self, api, admin_token):
        response = api.get(
            "/api/security/users/no-such-user", headers=_auth(admin_token)
        )

        assert response.status_code == 404


@pytest.mark.api
class TestUpdateAndDeleteUser:
    def test_superuser_can_update_a_user(self, api, admin_token, security_manager):
        user = _make_user(security_manager, "updatable")

        response = api.patch(
            f"/api/security/users/{user.user_id}",
            headers=_auth(admin_token),
            json={"full_name": "Updated Name"},
        )

        assert response.status_code == 200
        assert response.json()["full_name"] == "Updated Name"

    def test_updating_an_unknown_user_returns_404(self, api, admin_token):
        response = api.patch(
            "/api/security/users/no-such-user",
            headers=_auth(admin_token),
            json={"full_name": "Nobody"},
        )

        assert response.status_code == 404

    def test_non_superuser_cannot_update_a_user(
        self, api, plain_token, security_manager
    ):
        user = _make_user(security_manager, "target")

        response = api.patch(
            f"/api/security/users/{user.user_id}",
            headers=_auth(plain_token),
            json={"full_name": "Hijacked"},
        )

        assert response.status_code == 403

    def test_superuser_can_delete_a_user(self, api, admin_token, security_manager):
        user = _make_user(security_manager, "deletable")

        response = api.delete(
            f"/api/security/users/{user.user_id}", headers=_auth(admin_token)
        )

        assert response.status_code == 200
        assert api.get(
            f"/api/security/users/{user.user_id}", headers=_auth(admin_token)
        ).status_code == 404

    def test_non_superuser_cannot_delete_a_user(
        self, api, plain_token, security_manager
    ):
        user = _make_user(security_manager, "victim")

        response = api.delete(
            f"/api/security/users/{user.user_id}", headers=_auth(plain_token)
        )

        assert response.status_code == 403


@pytest.mark.api
class TestRoles:
    def test_default_roles_are_listed(self, api, plain_token):
        response = api.get("/api/security/roles", headers=_auth(plain_token))

        assert response.status_code == 200
        assert {r["name"] for r in response.json()} >= {"admin", "operator", "viewer"}

    def test_roles_require_authentication(self, api):
        assert api.get("/api/security/roles").status_code == 401

    def test_unknown_role_returns_404(self, api, plain_token):
        response = api.get(
            "/api/security/roles/no-such-role", headers=_auth(plain_token)
        )

        assert response.status_code == 404
