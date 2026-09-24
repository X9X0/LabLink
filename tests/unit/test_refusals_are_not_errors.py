"""Refusing a setpoint is an answer, not a fault, and logs like one.

Seen on the bench the moment the 1902B's measured 0.8 V floor went live::

    18:08:37 - ERROR - server.api.equipment - Error executing command:
               1902B will not go below 0.8V (asked for 0.7V)

Nothing was wrong. The operator had scrolled a dial one notch past the
bottom of the instrument's range and been told so, correctly, in 0.19s.
But a dial scrolled down produces one of those per notch, so ordinary
use now writes bursts of ERROR into the log -- and a log where routine
operation writes errors is one where a real error is easy to miss.

That is not hypothetical here. Diagnosing the server outage earlier the
same evening meant reading 7443 log lines about one dead scope to find
what else was in there. Log noise has already cost time on this bench.

The fix has to stay narrow. ``Invalid GETD response`` is also a
ValueError and is a genuine framing fault -- the one that serial desync
shows up as -- so demoting every ValueError would hide the bug this
suite spent a night chasing. Only range refusals change severity, and
they say so by type.
"""

import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.equipment.base import SetpointRefused
from server.equipment.bk_power_supply import BK1902B, BKPowerSupplyBase


def driver(cls):
    made = cls.__new__(cls)
    BKPowerSupplyBase.__init__(made, None, "ASRL/dev/ttyUSB0::INSTR")
    cls.__init__(made, None, "ASRL/dev/ttyUSB0::INSTR")
    return made


class TestARefusalIsItsOwnKindOfThing:
    @pytest.mark.asyncio
    async def test_below_the_floor_raises_a_refusal(self):
        supply = driver(BK1902B)
        with pytest.raises(SetpointRefused):
            await supply.set_voltage(0.7)

    @pytest.mark.asyncio
    async def test_above_the_ceiling_raises_a_refusal(self):
        supply = driver(BK1902B)
        with pytest.raises(SetpointRefused):
            await supply.set_voltage(999.0)

    @pytest.mark.asyncio
    async def test_it_is_still_a_value_error(self):
        """Callers have always caught these as one; only severity changes."""
        supply = driver(BK1902B)
        with pytest.raises(ValueError):
            await supply.set_voltage(0.7)

    @pytest.mark.asyncio
    async def test_the_message_still_names_the_limit(self):
        supply = driver(BK1902B)
        with pytest.raises(SetpointRefused) as refused:
            await supply.set_voltage(0.7)
        assert "0.8" in str(refused.value)
        assert "1902B" in str(refused.value)


class TestARealFaultIsStillAFault:
    """The narrowness is the point."""

    def test_a_framing_error_is_not_a_refusal(self):
        """``Invalid GETD response`` is how serial desync surfaces.

        It is a ValueError too. If it were demoted with the refusals it
        would vanish into INFO, and it is the single most useful line in
        the log when a fixed-width supply loses sync.
        """
        import inspect

        source = inspect.getsource(BKPowerSupplyBase.get_readings)
        assert "raise ValueError(f\"Invalid GETD response" in source, (
            "if this moved, check it did not become a SetpointRefused")

    def test_the_encoder_still_raises_a_plain_value_error(self):
        """An over-wide field shifts every character after it. That is a
        bug in our encoding, not the operator asking for too much."""
        supply = driver(BK1902B)
        with pytest.raises(ValueError) as boom:
            supply._encode_field(9999.0, 1)
        assert not isinstance(boom.value, SetpointRefused)


class TestTheApiLogsItAtInfo:
    @staticmethod
    def _levels_for(exc):
        """Run the endpoint's handler over `exc` and report what it logged."""
        import asyncio

        from server.api import equipment as api

        class _Equipment:
            cached_info = None

            async def execute_command(self, action, parameters):
                raise exc

        original = api.equipment_manager.get_equipment
        api.equipment_manager.get_equipment = lambda _id: _Equipment()
        # Locks are a different endpoint concern; this is about what the
        # handler logs once the driver has refused.
        locks_were = api.settings.enable_equipment_locks
        api.settings.enable_equipment_locks = False
        try:
            from shared.models.commands import Command

            command = Command(equipment_id="ps_1", command_id="c1",
                              action="set_voltage",
                              parameters={"voltage": 0.7})
            return asyncio.run(api.execute_command("ps_1", command))
        finally:
            api.equipment_manager.get_equipment = original
            api.settings.enable_equipment_locks = locks_were

    def test_a_refusal_does_not_log_an_error(self, caplog):
        caplog.set_level(logging.INFO, logger="server.api.equipment")
        answer = self._levels_for(
            SetpointRefused("1902B will not go below 0.8V (asked for 0.7V)"))

        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert not errors, (
            "a refused setpoint logged at ERROR; scrolling a dial past the "
            f"floor writes one per notch: {[r.getMessage() for r in errors]}")
        assert any(r.levelno == logging.INFO for r in caplog.records), (
            "the refusal should still be recorded, just not as a fault")
        assert answer.success is False
        assert "0.8" in (answer.error or "")

    def test_a_real_fault_still_logs_an_error(self, caplog):
        """Demoting refusals must not demote everything."""
        caplog.set_level(logging.INFO, logger="server.api.equipment")
        self._levels_for(ValueError("Invalid GETD response: "))

        assert [r for r in caplog.records if r.levelno >= logging.ERROR], (
            "a framing fault was not logged as an error")
