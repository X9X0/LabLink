"""A rate-limited setpoint has to arrive, not just set off in the right direction.

Reported from the bench twice. The second time the server log said it
plainly: the operator scrolled the dial down to 9.6 V and the supply
stopped at 15.6 V.

    requested 28.6, limited to 31.64  (max change 0.309 over 0.015s)
    requested 21.6, limited to 26.64
    requested 15.6, limited to 16.92
    requested  9.6, limited to 15.58   <- and there it stayed

``SlewRateLimiter.check_and_limit`` clamps the write to what the rate
allows and returns the clamped value. The target is discarded, so a change
larger than one step never arrives. Whether it got close depended on how
many writes happened to be sent, which nobody designed: driving the dial
faster produced fewer writes and moved the supply less.

The rate limit itself is not in question -- 20 V/s for a supply, chosen
deliberately. A rate limit says how fast to approach a value, not that it
need never be reached.

The tests that matter most here are the ones about stopping: a background
task that writes to lab equipment has to give up when the equipment goes
away, when it is refused, and when it is getting nowhere.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.equipment.slew_ramp import SlewRamps


class Supply:
    """A setpoint that may only move `rate` per step, as the limiter allows."""

    def __init__(self, value=0.0, step=1.0, fail_after=None):
        self.value = value
        self.step = step
        self.writes = []
        self._fail_after = fail_after
        self.ramps = SlewRamps("fake supply")

    async def set_voltage(self, target):
        if self._fail_after is not None and len(self.writes) >= self._fail_after:
            raise RuntimeError("Emergency stop is active - operation blocked")
        move = max(-self.step, min(self.step, target - self.value))
        self.value = round(self.value + move, 6)
        self.writes.append(self.value)
        self.ramps.note("voltage", target, self.value, self.set_voltage)


async def settle(limit=5.0):
    """Let the ramp run to completion, without waiting on wall clock."""
    deadline = asyncio.get_event_loop().time() + limit
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.01)
        others = [t for t in asyncio.all_tasks()
                  if t is not asyncio.current_task() and not t.done()]
        if not others:
            return
    raise AssertionError("the ramp never finished")


class TestItArrives:
    @pytest.mark.asyncio
    async def test_a_clamped_setpoint_keeps_going_until_it_gets_there(self):
        """The bench report, in one test: 9.6 asked for, 15.6 delivered."""
        supply = Supply(value=31.9, step=1.0)
        await supply.set_voltage(9.6)
        assert supply.value != pytest.approx(9.6), "the clamp did not engage"

        await settle()

        assert supply.value == pytest.approx(9.6), (
            f"stopped at {supply.value}; the operator asked for 9.6")

    @pytest.mark.asyncio
    async def test_it_approaches_in_steps_rather_than_jumping(self):
        """The rate limit is the point; arriving must not bypass it."""
        supply = Supply(value=0.0, step=1.0)
        await supply.set_voltage(5.0)
        await settle()

        assert supply.writes == [pytest.approx(v) for v in (1, 2, 3, 4, 5)], (
            f"moved in {supply.writes}, not one step at a time")

    @pytest.mark.asyncio
    async def test_a_setpoint_within_one_step_needs_no_ramp(self):
        supply = Supply(value=0.0, step=1.0)
        await supply.set_voltage(0.5)
        assert supply.ramps.travelling("voltage") is False
        assert supply.writes == [pytest.approx(0.5)]

    @pytest.mark.asyncio
    async def test_it_ramps_downwards_too(self):
        supply = Supply(value=10.0, step=1.0)
        await supply.set_voltage(6.0)
        await settle()
        assert supply.value == pytest.approx(6.0)


class TestANewTargetReplacesTheOldOne:
    @pytest.mark.asyncio
    async def test_moving_the_dial_again_retargets(self):
        """Where the operator was heading a moment ago no longer matters."""
        supply = Supply(value=0.0, step=1.0)
        await supply.set_voltage(20.0)
        await asyncio.sleep(0.12)
        await supply.set_voltage(3.0)
        await settle()

        assert supply.value == pytest.approx(3.0)
        assert max(supply.writes) < 20.0, (
            f"carried on towards the abandoned target: {supply.writes}")

    @pytest.mark.asyncio
    async def test_retargeting_does_not_start_a_second_ramp(self):
        supply = Supply(value=0.0, step=1.0)
        await supply.set_voltage(20.0)
        await asyncio.sleep(0.12)
        await supply.set_voltage(25.0)
        await settle()
        assert supply.value == pytest.approx(25.0)
        # One writer: the values never go backwards, which two ramps
        # fighting over the same setpoint would produce.
        assert supply.writes == sorted(supply.writes), supply.writes


class TestItStops:
    """A task writing to lab equipment has to know when to give up."""

    @pytest.mark.asyncio
    async def test_a_refusal_ends_the_ramp(self):
        """An emergency stop or a disconnect mid-ramp raises; stop writing."""
        supply = Supply(value=0.0, step=1.0, fail_after=3)
        await supply.set_voltage(50.0)
        await settle()

        assert supply.ramps.travelling() is False
        assert len(supply.writes) == 3, (
            f"kept writing after a refusal: {supply.writes}")

    @pytest.mark.asyncio
    async def test_stopping_abandons_a_ramp_in_progress(self):
        """What disconnect calls: nothing may keep driving a supply that
        has been taken away."""
        supply = Supply(value=0.0, step=1.0)
        await supply.set_voltage(50.0)
        await asyncio.sleep(0.12)
        supply.ramps.stop()
        written_by_then = len(supply.writes)
        await asyncio.sleep(0.2)

        assert supply.ramps.travelling() is False
        assert len(supply.writes) == written_by_then, (
            "still writing to disconnected equipment")

    @pytest.mark.asyncio
    async def test_it_gives_up_on_a_target_it_cannot_reach(self, monkeypatch):
        """A supply that will not move must not be written to forever."""
        monkeypatch.setattr("server.equipment.slew_ramp.GIVE_UP_AFTER_SEC", 0.2)
        supply = Supply(value=0.0, step=0.0)      # never moves
        await supply.set_voltage(50.0)
        await asyncio.sleep(0.6)

        assert supply.ramps.travelling() is False
        assert len(supply.writes) < 20, f"{len(supply.writes)} writes and counting"

    @pytest.mark.asyncio
    async def test_arriving_leaves_nothing_running(self):
        supply = Supply(value=0.0, step=1.0)
        await supply.set_voltage(4.0)
        await settle()
        assert supply.ramps.travelling() is False
        assert supply.ramps.target("voltage") is None


class TestParametersAreIndependent:
    @pytest.mark.asyncio
    async def test_voltage_and_current_ramp_separately(self):
        ramps = SlewRamps("fake")
        state = {"voltage": 0.0, "current": 0.0}
        writes = []

        def mover(name):
            async def move(target):
                step = max(-1.0, min(1.0, target - state[name]))
                state[name] = round(state[name] + step, 6)
                writes.append((name, state[name]))
                ramps.note(name, target, state[name], move)
            return move

        await mover("voltage")(5.0)
        await mover("current")(3.0)
        await settle()

        assert state["voltage"] == pytest.approx(5.0)
        assert state["current"] == pytest.approx(3.0)
