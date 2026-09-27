"""You cannot lock equipment that is not there.

Seen on the bench: a deploy restart emptied the equipment registry, and
acquiring an exclusive lock on the electronic load still returned 200
with a lock id, a mode and a timeout. The very next command came back
404 "Device not found".

That is a confident yes to a question whose answer is no. The lock
blocked nobody and protected nothing, and it misreported the
situation -- a missing registration looked like a broken command, and
the real cause took a separate round of digging to find.

Locking is a claim about an instrument. If there is no instrument,
there is no claim to make.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from fastapi.testclient import TestClient

    FASTAPI = True
except ImportError:
    FASTAPI = False

pytestmark = pytest.mark.skipif(not FASTAPI, reason="fastapi is required")

if FASTAPI:
    from server.api.locks import router
    from fastapi import FastAPI


@pytest.fixture
def client(monkeypatch):
    registered = {"load_real": object()}

    class Manager:
        def get_equipment(self, equipment_id):
            return registered.get(equipment_id)

    import server.equipment.manager as manager_module

    monkeypatch.setattr(manager_module, "equipment_manager", Manager())

    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def acquire(client, equipment_id, session="test-session"):
    return client.post("/api/locks/acquire", json={
        "equipment_id": equipment_id,
        "session_id": session,
        "lock_mode": "exclusive",
    })


class TestLockingSomethingThatIsNotThere:
    def test_it_is_refused(self, client):
        answer = acquire(client, "load_there_is_no_such_thing")
        assert answer.status_code == 404, answer.text

    def test_the_message_says_what_to_do(self, client):
        """The bench case was a restart that emptied the registry, and
        the fix was to reconnect -- which the message should say, because
        the person reading it has just been told 'not found' about an
        instrument sitting in front of them."""
        answer = acquire(client, "load_there_is_no_such_thing")
        said = answer.json()["detail"].lower()
        assert "reconnect" in said, said
        assert "load_there_is_no_such_thing" in answer.json()["detail"]

    def test_it_is_not_reported_as_a_server_error(self, client):
        """The endpoint wraps everything in a blanket except Exception
        that answers 500. A 404 raised inside it has to be let through,
        or the one sentence explaining the situation is buried under
        'Failed to acquire lock'."""
        answer = acquire(client, "nope")
        assert answer.status_code != 500, answer.text
        assert "Failed to acquire lock" not in answer.text


class TestRealEquipmentStillLocks:
    def test_it_is_granted(self, client):
        answer = acquire(client, "load_real")
        assert answer.status_code == 200, answer.text
        assert answer.json().get("success") is not False
