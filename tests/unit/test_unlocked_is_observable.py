"""An instrument nobody has locked can be read by anyone.

Watched on the bench while switching between two supplies: selecting one
releases the previous lock before taking the new one, and a setpoint read
that landed in that gap was refused.

    23:30:56,968  Released lock on ps_56fdd3df
    23:30:56,989  Could not read setpoints from ps_56fdd3df: 403
    23:30:57,000  Acquired exclusive lock on ps_56fdd3df

The panel then showed a stale setpoint for that instrument until
something changed it. It happened five times in one short test.

Reading setpoints goes through the command endpoint, which asks
can_observe_equipment for any read carrying a session id -- and that
returned False unless the session held a lock. So sending a session id
made a read *less* likely to be allowed than sending none, and an
instrument with no lock on it at all was readable by nobody.

A lock is a claim on changing something. The panels say so themselves:
"not holding the lock means you cannot change the instrument, not that
you cannot watch it."
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.equipment.locks import EquipmentLock, LockManager, LockMode


@pytest.fixture
def locks():
    return LockManager()


class TestNoLockMeansNoRestriction:
    def test_an_unlocked_instrument_is_observable(self, locks):
        """The bench failure, in one assertion."""
        assert locks.can_observe_equipment("ps_1", "session-a") is True, (
            "a read was refused on an instrument nobody had locked, which "
            "is what the gap between releasing and acquiring looks like")

    def test_any_session_may_observe_it(self, locks):
        for session in ("session-a", "session-b", "anyone"):
            assert locks.can_observe_equipment("ps_1", session) is True

    def test_an_expired_lock_counts_as_nobody(self, locks, monkeypatch):
        """It lingers in the table until the background sweep runs."""
        held = EquipmentLock(equipment_id="ps_1", session_id="session-a",
                             lock_mode=LockMode.EXCLUSIVE)
        locks._locks["ps_1"] = held
        monkeypatch.setattr(type(held), "is_expired", lambda self: True)

        assert locks.can_observe_equipment("ps_1", "session-b") is True, (
            "a lock that has timed out still excluded everyone else")


class TestALiveLockIsStillRespected:
    """Only the no-lock case changed; the policy itself is untouched."""

    def _hold(self, locks, session="owner"):
        locks._locks["ps_1"] = EquipmentLock(
            equipment_id="ps_1", session_id=session,
            lock_mode=LockMode.EXCLUSIVE)
        return locks._locks["ps_1"]

    def test_the_holder_can_observe(self, locks):
        self._hold(locks, "owner")
        assert locks.can_observe_equipment("ps_1", "owner") is True

    def test_someone_else_still_cannot(self, locks):
        self._hold(locks, "owner")
        assert locks.can_observe_equipment("ps_1", "intruder") is False, (
            "this change was meant to cover the unlocked case only")

    def test_an_explicit_observer_still_can(self, locks):
        self._hold(locks, "owner")
        locks._observer_locks.setdefault("ps_1", set()).add("watcher")
        assert locks.can_observe_equipment("ps_1", "watcher") is True

    def test_another_instrument_being_locked_changes_nothing(self, locks):
        self._hold(locks, "owner")
        assert locks.can_observe_equipment("ps_2", "anyone") is True
