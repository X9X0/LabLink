"""The lock status endpoint must report what the lock manager records.

The gap this covers is a seam, which is why neither side's tests saw it. The
manager stored `username` and `client_ip` and computed `expired`, and its own
tests confirmed that. The client tests fed `LockStatusWidget` dicts containing
those keys, and confirmed it renders them. In between, `LockStatusResponse`
did not declare the fields, and a response model silently drops what it does
not name -- so every real lock rendered as "an unidentified session".

Found by pointing the actual widgets at a running server. These tests are the
cheaper way to notice next time.
"""

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# The repo root, so `server.*` resolves -- and only the root. See #197.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.api.locks import router  # noqa: E402
from server.equipment.locks import lock_manager  # noqa: E402

EQUIPMENT = "test-supply"


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_locks():
    """Each test starts with no locks, and leaves none behind."""
    lock_manager._locks.clear()
    yield
    lock_manager._locks.clear()


def _acquire(client, **overrides):
    body = {
        "equipment_id": EQUIPMENT,
        "session_id": "session-under-test",
        "lock_mode": "exclusive",
        "timeout_seconds": 300,
    }
    body.update(overrides)
    response = client.post("/api/locks/acquire", json=body)
    assert response.status_code == 200, response.text
    return response


class TestStatusReportsAttribution:
    def test_who_holds_it_survives_the_response_model(self, client):
        _acquire(client, username="alice")

        status = client.get(f"/api/locks/status/{EQUIPMENT}").json()

        assert status["username"] == "alice", (
            "the holder's name is recorded by the manager and must reach the "
            "caller, or every lock renders as an unidentified session"
        )
        assert status["client_ip"] is not None

    def test_the_address_is_observed_not_claimed(self, client):
        """A caller does not get to say where it is connecting from.

        `client_ip` comes from `get_client_ip`, which reads the connection and
        honours LABLINK_TRUSTED_PROXIES. A body field would be a free-text
        label on an audit record.
        """
        _acquire(client, username="alice", client_ip="10.10.0.77")

        status = client.get(f"/api/locks/status/{EQUIPMENT}").json()

        assert status["client_ip"] != "10.10.0.77"
        assert status["client_ip"] == "testclient"  # the actual peer

    def test_the_countdown_fields_are_reported(self, client):
        """A caller rendering a lock should not reimplement expiry."""
        _acquire(client, timeout_seconds=300)

        status = client.get(f"/api/locks/status/{EQUIPMENT}").json()

        assert status["timeout_seconds"] == 300
        assert status["expired"] is False
        assert status["last_activity"] is not None
        assert 0 < status["time_remaining"] <= 300

    def test_an_unnamed_holder_is_still_reported(self, client):
        """Attribution is best-effort; an unknown name must not drop the lock.

        The address survives regardless -- it is observed, not supplied -- so
        the strip can still say where control went even with no username.
        """
        _acquire(client)

        status = client.get(f"/api/locks/status/{EQUIPMENT}").json()

        assert status["locked"] is True
        assert status["username"] is None
        assert status["client_ip"] is not None

    def test_no_timeout_is_reported_as_zero_not_missing(self, client):
        """The widget distinguishes "no timeout" from "unknown" on this field."""
        _acquire(client, timeout_seconds=0)

        status = client.get(f"/api/locks/status/{EQUIPMENT}").json()

        assert status["timeout_seconds"] == 0
        assert status["expired"] is False

    def test_unlocked_equipment_reports_no_holder(self, client):
        status = client.get(f"/api/locks/status/{EQUIPMENT}").json()

        assert status["locked"] is False
        assert status["username"] is None
