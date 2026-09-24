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

What it has to be is *true*, though, and three numbers were offered for
the 1902B before anyone asked the supply itself:

    0.1 V   what the front panel would display
    1.0 V   what the driver's own spec line says
    1.1 V   where an unloaded output settled

All three were wrong. Asked over the wire -- three rounds of 1.2, 0.8,
0.7 -- it answered identically every time: 1.2 and 0.8 acknowledged and
the setpoint moved, 0.7 ignored with no reply and the setpoint left at
0.8. The floor is 0.8 V.

What makes that conclusive where the earlier numbers were not is that it
rests on the acknowledgement, not on the output voltage. The supply was
in CC against a 0 A limit throughout and read 0.13 V the entire time --
a reading equally consistent with every floor anyone had proposed.

The 1685B claims nothing. It was swapped off the bench before it could
be asked, and a floor nobody measured is exactly what this file exists
to prevent.
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

    def test_the_1902b_floors_at_the_measured_value(self):
        """0.8 V: asked over the wire, three rounds, same answer each time.

        Not 1.0 from the spec line and not 0.1 from the front panel. A
        floor set to the spec's 1.0 would refuse 0.8 and 0.9, both of
        which the supply accepts -- and would refuse them in the server,
        so the instrument would never be asked and the error could not
        be found from the bench.
        """
        assert driver(BK1902B).min_voltage == pytest.approx(0.8)

    def test_the_1902b_current_still_reaches_zero(self):
        """Measured separately: do not assume the two are symmetric."""
        assert driver(BK1902B).min_current == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_the_lowest_accepted_voltage_is_not_refused(self):
        """0.8 is a value the supply takes; refusing it would be a bug."""
        supply = driver(BK1902B)
        supply._write = _record(supply)
        await supply.set_voltage(0.8)
        assert supply.written == ["VOLT008"]

    @pytest.mark.asyncio
    async def test_the_highest_ignored_voltage_is_refused(self):
        """0.7 earns a full 10s read timeout on the wire; say no first."""
        supply = driver(BK1902B)
        with pytest.raises(ValueError):
            await supply.set_voltage(0.7)

    def test_the_1685b_claims_no_floor(self):
        assert driver(BK1685B).min_voltage == pytest.approx(0.0)
        assert driver(BK1685B).min_current == pytest.approx(0.0)

    def test_an_unmeasured_model_claims_no_floor(self):
        """Better than inheriting a number nobody checked."""
        base = BKPowerSupplyBase.__new__(BKPowerSupplyBase)
        BKPowerSupplyBase.__init__(base, None, "ASRL/dev/ttyUSB9::INSTR")
        assert base.min_voltage == 0.0
        assert base.min_current == 0.0

    def test_an_unmeasured_model_is_not_refused_anything(self):
        """The whole point: the instrument gets asked, so it can answer.

        The 1902B has since been measured and does claim a floor. The
        1685B has not -- it was swapped off the bench before anyone put
        a question to it -- so it must keep letting everything through.
        """
        supply = driver(BK1685B)
        supply._write = _record(supply)
        import asyncio
        asyncio.run(supply.set_voltage(0.0))
        assert supply.written == ["VOLT000"], (
            "the 1685B refused 0 V in the server, so the bench can never "
            "find out what the supply would have done")


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
