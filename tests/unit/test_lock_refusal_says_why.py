"""A refused control command must say which of three things went wrong.

``can_control_equipment`` returns False for three unrelated situations,
and the message described all of them the same way::

    Equipment ps_56fdd3df is locked by session unknown.
    Acquire exclusive lock before control commands.

"Session unknown" is what you get when there is no lock record at all
-- the dict lookup misses and the default lands in the message. So the
commonest case, *you have not taken a lock*, was reported as somebody
else having taken your instrument. That is not a vague message, it is
a wrong one, and it sends an operator looking for a colleague to ask.

Hit on this bench: a lock timed out after 300s of inactivity, the next
write came back "locked by session unknown", and the first assumption
was that another session had grabbed the supply. It had not; the lock
had simply lapsed.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.api.equipment import _why_control_was_refused


class FakeLocks:
    def __init__(self, status):
        self._status = status

    def get_lock_status(self, equipment_id):
        return self._status


@pytest.fixture
def locks(monkeypatch):
    def install(status):
        monkeypatch.setattr("server.api.equipment.lock_manager",
                            FakeLocks(status))
    return install


class TestNobodyHoldsIt:
    """The common case, and the one the old message was wrong about."""

    def test_it_does_not_claim_someone_else_has_it(self, locks):
        locks({"locked": False})
        said = _why_control_was_refused("ps_1", "me")
        assert "unknown" not in said.lower(), (
            f"still implying a mystery owner: {said}")
        assert "locked by" not in said.lower(), (
            f"says it is locked when it is not: {said}")

    def test_it_says_what_to_do(self, locks):
        locks({"locked": False})
        said = _why_control_was_refused("ps_1", "me")
        assert "acquire" in said.lower()

    def test_it_mentions_the_lapsed_lock_possibility(self, locks):
        """Which is how an operator gets here without doing anything."""
        locks({"locked": False})
        assert "timed out" in _why_control_was_refused("ps_1", "me").lower()


class TestSomebodyElseHoldsIt:
    def test_it_names_them(self, locks):
        locks({"locked": True, "session_id": "other-session",
               "username": "scap", "expired": False})
        said = _why_control_was_refused("ps_1", "me")
        assert "scap" in said
        assert "other-session" in said

    def test_it_falls_back_when_there_is_no_username(self, locks):
        locks({"locked": True, "session_id": "other-session",
               "username": None, "expired": False})
        said = _why_control_was_refused("ps_1", "me")
        assert "another session" in said

    def test_an_expired_lock_is_called_out(self, locks):
        """Otherwise the advice is 'go and find them', wrongly."""
        locks({"locked": True, "session_id": "other", "username": "scap",
               "expired": True})
        assert "expired" in _why_control_was_refused("ps_1", "me").lower()


class TestYouHoldItButOnlyToWatch:
    def test_it_says_so_rather_than_naming_you_as_the_blocker(self, locks):
        locks({"locked": True, "session_id": "me", "username": "scap",
               "expired": False})
        said = _why_control_was_refused("ps_1", "me")
        assert "observer" in said.lower(), (
            f"told the operator their own session is blocking them: {said}")
        assert "exclusiv" in said.lower()


class TestTheThreeAreActuallyDifferent:
    def test_no_two_read_the_same(self, monkeypatch):
        cases = [
            {"locked": False},
            {"locked": True, "session_id": "other", "username": "x",
             "expired": False},
            {"locked": True, "session_id": "me", "username": "x",
             "expired": False},
        ]
        said = []
        for status in cases:
            monkeypatch.setattr("server.api.equipment.lock_manager",
                                FakeLocks(status))
            said.append(_why_control_was_refused("ps_1", "me"))
        assert len(set(said)) == 3, (
            "two situations still produce the same message, which is how "
            f"the original bug read: {said}")
