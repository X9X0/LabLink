"""A single-flight guard must not be able to wedge itself shut.

Panels that refresh on a timer skip a tick while the previous request is still
out. Guarding that with a boolean cleared in a `finally` looks right and is
not: qasync destroys pending tasks when the loop is disturbed -- the client log
says "Task was destroyed but it is pending" -- and a task destroyed mid-await
never runs its finally. The flag stayed set for the life of the process, so the
equipment list stopped refreshing entirely and only a client restart brought it
back. That is what happened after every server update, which disturbs the loop
by design: the server goes away mid-request.

Recording when the work started keeps the guard while making the failure
survivable. A slot still held long after anything could plausibly be running is
taken anyway, so the worst case is one overlapping refresh rather than a panel
frozen until restart.
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from client.utils.inflight import (  # noqa: E402
    READINGS_ABANDONED_AFTER, REFRESH_ABANDONED_AFTER, claim_slot,
    release_slot)


class Panel:
    """Stands in for a panel holding one in-flight slot."""

    def __init__(self):
        self._started_at = None


@pytest.fixture
def panel():
    return Panel()


class TestTheGuardStillGuards:
    def test_the_first_caller_gets_the_slot(self, panel):
        assert claim_slot(panel, "_started_at", REFRESH_ABANDONED_AFTER)

    def test_a_second_caller_is_turned_away(self, panel):
        claim_slot(panel, "_started_at", REFRESH_ABANDONED_AFTER)

        assert not claim_slot(panel, "_started_at", REFRESH_ABANDONED_AFTER)

    def test_releasing_lets_the_next_one_through(self, panel):
        claim_slot(panel, "_started_at", REFRESH_ABANDONED_AFTER)
        release_slot(panel, "_started_at")

        assert claim_slot(panel, "_started_at", REFRESH_ABANDONED_AFTER)


class TestADestroyedTaskDoesNotWedgeIt:
    def test_a_slot_held_too_long_is_taken_anyway(self, panel):
        """The regression: the holder was destroyed and never released it."""
        claim_slot(panel, "_started_at", REFRESH_ABANDONED_AFTER)
        # Wind the clock back past the threshold, as if that task never came
        # back -- which is what "Task was destroyed but it is pending" means.
        panel._started_at -= REFRESH_ABANDONED_AFTER + 1

        assert claim_slot(panel, "_started_at", REFRESH_ABANDONED_AFTER), (
            "a destroyed task left the panel unable to refresh ever again"
        )

    def test_recovery_leaves_the_slot_usable(self, panel):
        """Not just once: the guard has to keep working afterwards."""
        claim_slot(panel, "_started_at", REFRESH_ABANDONED_AFTER)
        panel._started_at -= REFRESH_ABANDONED_AFTER + 1
        claim_slot(panel, "_started_at", REFRESH_ABANDONED_AFTER)

        assert not claim_slot(panel, "_started_at", REFRESH_ABANDONED_AFTER)

    def test_a_slot_held_briefly_is_still_respected(self, panel):
        """Recovery must not become "no guard at all"."""
        claim_slot(panel, "_started_at", REFRESH_ABANDONED_AFTER)
        panel._started_at -= REFRESH_ABANDONED_AFTER / 2

        assert not claim_slot(panel, "_started_at", REFRESH_ABANDONED_AFTER)


class TestTheThresholds:
    def test_readings_recover_sooner_than_a_list_refresh(self):
        """Readings run many times a second; a blank panel for 45s is not ok."""
        assert READINGS_ABANDONED_AFTER < REFRESH_ABANDONED_AFTER

    def test_a_refresh_outlasts_a_fan_out_over_several_dead_servers(self):
        """Each unreachable server costs a ten-second connect timeout."""
        assert REFRESH_ABANDONED_AFTER > 30

    def test_the_clock_is_monotonic(self, panel):
        """A wall clock can step backwards and hold the slot indefinitely."""
        claim_slot(panel, "_started_at", REFRESH_ABANDONED_AFTER)

        assert abs(panel._started_at - time.monotonic()) < 1.0
