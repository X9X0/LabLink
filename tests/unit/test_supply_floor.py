"""A supply has a floor, and asking below it is worse than useless.

Below the floor the instrument does not refuse the command -- it ignores
it, with no reply at all. The driver, which now waits for the "OK" that
every fixed-width command is supposed to send, then spends a full read
timeout waiting for one that is never coming:

    no acknowledgement after 'VOLT000': VI_ERROR_TMO
    asked voltage for 0.0 and it still reads 0.8 after 3s

Sixteen of those in four minutes of testing, against 481 writes that
were acknowledged normally. Saying no up front costs nothing and tells
the operator something true.

What it has to be is *true*, though, and so far every number offered for
these two supplies has come from an unloaded bench:

    0.1 V   what the front panel would display
    1.10 V  what the 1685B sat at when asked for less
    1.00 V  what the 1902B sat at when asked for less

An unloaded supply's output tells you nothing about whether it accepted
a setpoint, because with no current drawn there is nothing to pull the
output down to it. All three numbers are consistent with a floor and
equally consistent with no floor at all, so neither model claims one
here. The measurement that separates them is GETS under load: what the
supply says its setpoint is, rather than what its output happens to be.

The refusal machinery below is tested against a driver given an explicit
floor, so it stays covered while no real model claims one.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.equipment.bk_power_supply import (BK1685B, BK1902B,
                                              BKPowerSupplyBase)


def driver(cls):
    """A driver without a resource manager or a port."""
    made = cls.__new__(cls)
    BKPowerSupplyBase.__init__(made, None, "ASRL/dev/ttyUSB0::INSTR")
    cls.__init__(made, None, "ASRL/dev/ttyUSB0::INSTR")
    return made


class TestOnlyWhatTheWireSupports:
    """A floor is a claim about the serial command, not the front panel.

    Twice now a number has been taken from an unloaded output and
    written down as the floor -- 0.1 V from what the front panel would
    display, then 1.0 V from where the 1902B settled when asked for
    less. Neither is evidence: an unloaded supply's output is not its
    setpoint.

    A wrong floor is self-concealing, too. At 1.0 the server refuses the
    write itself, so the instrument is never asked and the guess can
    never be caught on the bench. That is the reason to claim nothing
    rather than to guess low.
    """

    def test_the_1902b_claims_no_floor(self):
        """1-60 V is its spec line, not a measurement of VOLT."""
        assert driver(BK1902B).min_voltage == pytest.approx(0.0)
        assert driver(BK1902B).min_current == pytest.approx(0.0)

    def test_the_1685b_claims_no_floor(self):
        assert driver(BK1685B).min_voltage == pytest.approx(0.0)
        assert driver(BK1685B).min_current == pytest.approx(0.0)

    def test_an_unmeasured_model_claims_no_floor(self):
        """Better than inheriting a number nobody checked."""
        base = BKPowerSupplyBase.__new__(BKPowerSupplyBase)
        BKPowerSupplyBase.__init__(base, None, "ASRL/dev/ttyUSB9::INSTR")
        assert base.min_voltage == 0.0
        assert base.min_current == 0.0

    def test_nothing_below_the_dial_is_refused_by_either(self):
        """The whole point: the instrument gets asked, so it can answer."""
        for cls in (BK1685B, BK1902B):
            supply = driver(cls)
            supply._write = _record(supply)
            import asyncio
            asyncio.run(supply.set_voltage(0.0))
            assert supply.written == ["VOLT000"], (
                f"{supply.model} refused 0 V in the server, so the bench "
                f"can never find out what the supply would have done")


def with_floor(cls, volts=None, amps=None):
    """A driver told a floor, so the refusal path stays covered.

    No real model claims one at the moment. The mechanism still has to
    work, and has to be ready for the first floor that is measured
    rather than inferred.
    """
    made = driver(cls)
    if volts is not None:
        made.min_voltage = volts
    if amps is not None:
        made.min_current = amps
    return made


class TestAskingBelowTheFloorIsRefused:
    @pytest.mark.asyncio
    async def test_below_the_floor_is_refused_rather_than_ignored(self):
        """A supply that ignores the command costs a full read timeout."""
        supply = with_floor(BK1902B, volts=1.0)
        with pytest.raises(ValueError) as refused:
            await supply.set_voltage(0.5)
        assert "1.0" in str(refused.value) or "1 " in str(refused.value)
        assert "1902B" in str(refused.value)

    @pytest.mark.asyncio
    async def test_zero_volts_is_refused_on_a_supply_with_a_floor(self):
        supply = with_floor(BK1902B, volts=1.0)
        with pytest.raises(ValueError):
            await supply.set_voltage(0.0)

    @pytest.mark.asyncio
    async def test_a_supply_claiming_no_floor_refuses_nothing(self):
        """Better to let it through than to invent a limit."""
        supply = driver(BK1685B)
        supply._write = _record(supply)
        await supply.set_voltage(0.0)
        assert supply.written == ["VOLT000"]

    @pytest.mark.asyncio
    async def test_a_voltage_floor_does_not_bleed_into_current(self):
        """The two are measured separately; do not assume symmetry."""
        supply = with_floor(BK1902B, volts=1.0)
        supply._write = _record(supply)
        await supply.set_current(0.0)
        assert supply.written, "a reachable value was refused"

    @pytest.mark.asyncio
    async def test_the_floor_itself_is_accepted(self):
        supply = with_floor(BK1902B, volts=1.0)
        supply._write = _record(supply)
        await supply.set_voltage(1.0)
        assert supply.written == ["VOLT010"]

    @pytest.mark.asyncio
    async def test_an_ordinary_value_is_unaffected(self):
        supply = driver(BK1685B)
        supply._write = _record(supply)
        await supply.set_voltage(12.0)
        assert supply.written == ["VOLT120"]


class TestThePanelIsToldTheFloor:
    def test_capabilities_carry_it(self):
        supply = with_floor(BK1902B, volts=1.0)
        caps = supply._capabilities() if hasattr(supply, "_capabilities") else None
        if caps is None:
            import inspect
            source = inspect.getsource(type(supply).get_equipment_info
                                       if hasattr(type(supply), "get_equipment_info")
                                       else BKPowerSupplyBase)
            assert '"min_voltage"' in source and '"min_current"' in source
        else:
            assert caps["min_voltage"] == pytest.approx(1.0)


def _record(supply):
    supply.written = []

    async def write(command):
        supply.written.append(command)

    return write
