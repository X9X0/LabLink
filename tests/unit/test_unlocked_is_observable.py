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

    def test_someone_else_is_not_granted_observer_status(self, locks):
        """can_observe_equipment still answers what it says on the tin.

        The endpoint no longer asks it for reads -- see
        TestReadsAreNeverRefused -- but the question "does this session
        have observer or control rights" still has the same answer.
        """
        self._hold(locks, "owner")
        assert locks.can_observe_equipment("ps_1", "intruder") is False

    def test_an_explicit_observer_still_can(self, locks):
        self._hold(locks, "owner")
        locks._observer_locks.setdefault("ps_1", set()).add("watcher")
        assert locks.can_observe_equipment("ps_1", "watcher") is True

    def test_another_instrument_being_locked_changes_nothing(self, locks):
        self._hold(locks, "owner")
        assert locks.can_observe_equipment("ps_2", "anyone") is True


class TestReadsAreNeverRefused:
    """A lock is a claim on changing an instrument, not on watching one.

    Reported from the bench: switching supplies gave 403s on the setpoint
    read, and the log showed why -- a second session held the lock.

        00:18:43  Could not read setpoints from ps_58f4c6c0: 403
        00:18:43  Lost the lock on the selected equipment to admin
        00:18:49  Overrode lock on ps_58f4c6c0 previously held by admin

    Both sessions were the operator's own machine: every client restart
    mints a new session id and the old lock lives on until it times out,
    so eight restarts in an evening makes this routine. The panel showed
    live readings while refusing to say what the instrument was set to,
    because GET /readings never consulted a lock and get_setpoints, which
    goes through the command endpoint, did.
    """

    def test_the_command_endpoint_does_not_gate_reads_on_a_lock(self):
        import inspect

        from server.api import equipment as api

        source = inspect.getsource(api.execute_command)
        after_control = source[source.index("else:"):]
        assert "can_observe_equipment" not in after_control, (
            "a read is still refused when somebody else holds the lock")
        assert "No observer or control access" not in after_control

    def test_control_still_requires_the_lock(self):
        """The half that must not change."""
        import inspect

        from server.api import equipment as api

        source = inspect.getsource(api.execute_command)
        assert "can_control_equipment" in source
        assert "Acquire exclusive lock before control commands" in source

    def test_a_read_still_keeps_a_holder_s_lock_alive(self):
        import inspect

        from server.api import equipment as api

        source = inspect.getsource(api.execute_command)
        assert source.count("update_lock_activity") >= 2, (
            "a holder reading their own instrument should not have their "
            "lock time out underneath them")
