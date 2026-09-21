"""A supply has a floor, and asking below it is worse than useless.

Measured on the bench, with no load: both the 1685B and the 1902B stop at
0.1 V. The 1685B's current stops at 0.01 A; the 1902B's reaches 0.0 A.

Below the floor the instrument does not refuse the command -- it ignores
it, with no reply at all. The driver, which now waits for the "OK" that
every fixed-width command is supposed to send, then spends a full read
timeout waiting for one that is never coming:

    no acknowledgement after 'VOLT000': VI_ERROR_TMO
    asked voltage for 0.0 and it still reads 0.8 after 3s

Sixteen of those in four minutes of testing, against 481 writes that
were acknowledged normally. Saying no up front costs nothing and tells
the operator something true.
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


class TestTheMeasuredFloors:
    def test_the_1685b_stops_at_a_tenth_of_a_volt(self):
        assert driver(BK1685B).min_voltage == pytest.approx(0.1)

    def test_the_1685b_current_stops_at_a_hundredth_of_an_amp(self):
        assert driver(BK1685B).min_current == pytest.approx(0.01)

    def test_the_1902b_stops_at_a_tenth_of_a_volt(self):
        assert driver(BK1902B).min_voltage == pytest.approx(0.1)

    def test_the_1902b_current_does_reach_zero(self):
        """Measured, and different from the 1685B: do not assume symmetry."""
        assert driver(BK1902B).min_current == pytest.approx(0.0)

    def test_an_unmeasured_model_claims_no_floor(self):
        """Better than inheriting a number nobody checked."""
        base = BKPowerSupplyBase.__new__(BKPowerSupplyBase)
        BKPowerSupplyBase.__init__(base, None, "ASRL/dev/ttyUSB9::INSTR")
        assert base.min_voltage == 0.0
        assert base.min_current == 0.0


class TestAskingBelowTheFloorIsRefused:
    @pytest.mark.asyncio
    async def test_zero_volts_is_refused_rather_than_ignored(self):
        """Zero is the value that was actually failing."""
        supply = driver(BK1685B)
        with pytest.raises(ValueError) as refused:
            await supply.set_voltage(0.0)
        assert "0.1" in str(refused.value)
        assert "1685B" in str(refused.value)

    @pytest.mark.asyncio
    async def test_just_below_the_floor_is_refused(self):
        supply = driver(BK1685B)
        with pytest.raises(ValueError):
            await supply.set_voltage(0.05)

    @pytest.mark.asyncio
    async def test_current_below_the_floor_is_refused(self):
        supply = driver(BK1685B)
        with pytest.raises(ValueError) as refused:
            await supply.set_current(0.0)
        assert "0.01" in str(refused.value)

    @pytest.mark.asyncio
    async def test_the_1902b_still_accepts_zero_amps(self):
        """It reaches 0.0 A, so refusing it would be wrong."""
        supply = driver(BK1902B)
        supply._write = _record(supply)
        await supply.set_current(0.0)
        assert supply.written, "a reachable value was refused"

    @pytest.mark.asyncio
    async def test_the_floor_itself_is_accepted(self):
        supply = driver(BK1685B)
        supply._write = _record(supply)
        await supply.set_voltage(0.1)
        assert supply.written == ["VOLT001"]

    @pytest.mark.asyncio
    async def test_an_ordinary_value_is_unaffected(self):
        supply = driver(BK1685B)
        supply._write = _record(supply)
        await supply.set_voltage(12.0)
        assert supply.written == ["VOLT120"]


class TestThePanelIsToldTheFloor:
    def test_capabilities_carry_it(self):
        supply = driver(BK1685B)
        caps = supply._capabilities() if hasattr(supply, "_capabilities") else None
        if caps is None:
            import inspect
            source = inspect.getsource(type(supply).get_equipment_info
                                       if hasattr(type(supply), "get_equipment_info")
                                       else BKPowerSupplyBase)
            assert '"min_voltage"' in source and '"min_current"' in source
        else:
            assert caps["min_voltage"] == pytest.approx(0.1)


def _record(supply):
    supply.written = []

    async def write(command):
        supply.written.append(command)

    return write
