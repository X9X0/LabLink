"""A power supply can be acquired from.

On the bench, neither supply could:

    1902B  'voltage'  ->  400 cannot acquire
    9205B  'voltage'  ->  400 cannot acquire
    DL3021A           ->  200

_get_channel_value knew get_measurement, get_voltage, get_current and a
generic command. Every instrument implements get_readings and only some
implement get_measurement -- the load has one, the supplies do not --
so no supply could be acquired from at all. Before the channel guard
existed the session was accepted and filled with NaN instead, which is
why nobody had noticed.

Key names differ by instrument class, and both are reasonable: a supply
separates what was asked for from what is happening (voltage_set
against voltage_actual), while a load reporting one voltage has nothing
to disambiguate. The operator should not have to know which.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.acquisition.manager import AcquisitionManager


class Supply:
    """Keys as the 1902B and 9205B actually report them."""

    def __init__(self, **overrides):
        self.readings = {
            "voltage_actual": 5.01,
            "current_actual": 0.25,
            "voltage_set": 5.0,
            "current_set": 1.0,
            "output_enabled": True,
        }
        self.readings.update(overrides)

    async def get_readings(self, channel: int = 1):
        return dict(self.readings)


class Load:
    """Keys as the DL3021A reports them, and a get_measurement besides."""

    async def get_readings(self):
        return {"voltage": 4.98, "current": 0.1, "power": 0.498,
                "setpoint": 0.1, "mode": "CC"}

    async def get_measurement(self, channel):
        if channel not in ("voltage", "current", "power"):
            raise NotImplementedError(channel)
        return {"voltage": 4.98, "current": 0.1, "power": 0.498}[channel]


class TestTheSupplyChannels:
    @pytest.mark.parametrize("channel,expected", [
        ("voltage", 5.01),
        ("current", 0.25),
        ("voltage_set", 5.0),
        ("current_set", 1.0),
    ])
    @pytest.mark.asyncio
    async def test_it_reads_what_the_operator_asked_for(self, channel,
                                                        expected):
        manager = AcquisitionManager()
        value = await manager._get_channel_value(Supply(), channel)
        assert value == pytest.approx(expected)

    @pytest.mark.asyncio
    async def test_power_is_computed_when_it_is_not_reported(self):
        """The supplies report volts and amps and nothing else.
        Multiplying them is not a guess."""
        manager = AcquisitionManager()
        value = await manager._get_channel_value(Supply(), "power")
        assert value == pytest.approx(5.01 * 0.25)

    @pytest.mark.asyncio
    async def test_a_channel_it_does_not_have_is_still_refused(self):
        manager = AcquisitionManager()
        with pytest.raises(NotImplementedError):
            await manager._get_channel_value(Supply(), "CH1")

    @pytest.mark.asyncio
    async def test_a_session_on_a_supply_is_accepted(self):
        from server.acquisition.models import AcquisitionConfig

        manager = AcquisitionManager()
        config = AcquisitionConfig(
            equipment_id="ps_1",
            channels=["voltage", "current", "power", "voltage_set"])

        session = await manager.create_session(Supply(), config)
        assert session.acquisition_id in manager._sessions


class TestTheLoadStillWorks:
    @pytest.mark.parametrize("channel,expected", [
        ("voltage", 4.98),
        ("current", 0.1),
        ("power", 0.498),
    ])
    @pytest.mark.asyncio
    async def test_get_measurement_is_still_preferred(self, channel,
                                                      expected):
        manager = AcquisitionManager()
        value = await manager._get_channel_value(Load(), channel)
        assert value == pytest.approx(expected)

    @pytest.mark.asyncio
    async def test_readings_cover_what_get_measurement_does_not(self):
        """The load's get_measurement refuses 'setpoint'; its readings
        carry it."""
        manager = AcquisitionManager()
        value = await manager._get_channel_value(Load(), "setpoint")
        assert value == pytest.approx(0.1)


class TestABusyInstrumentIsNotAnUnsupportedOne:
    """create_session refuses outright on NotImplementedError, so the
    two must not look the same. An instrument that is switched off is
    the loop's to retry."""

    class Busy:
        async def get_measurement(self, channel):
            raise OSError("resource busy")

    @pytest.mark.asyncio
    async def test_the_original_error_survives(self):
        manager = AcquisitionManager()
        with pytest.raises(OSError):
            await manager._get_channel_value(self.Busy(), "voltage")

    @pytest.mark.asyncio
    async def test_it_does_not_become_not_implemented(self):
        manager = AcquisitionManager()
        try:
            await manager._get_channel_value(self.Busy(), "voltage")
        except NotImplementedError:
            pytest.fail("a busy instrument was reported as unsupported, "
                        "which refuses the session instead of retrying")
        except OSError:
            pass


class TestTheQuantityGettersRespectTheChannel:
    """get_voltage and get_current ignore the channel argument, so they
    must only answer for the quantity they return. Asked for 'current',
    the old order would have called get_voltage and returned volts."""

    class VoltsOnly:
        async def get_voltage(self):
            return 12.0

    @pytest.mark.asyncio
    async def test_voltage_is_answered(self):
        manager = AcquisitionManager()
        assert await manager._get_channel_value(
            self.VoltsOnly(), "voltage") == pytest.approx(12.0)

    @pytest.mark.asyncio
    async def test_current_is_not_answered_with_volts(self):
        manager = AcquisitionManager()
        with pytest.raises(NotImplementedError):
            await manager._get_channel_value(self.VoltsOnly(), "current")


class TestARowIsOneSample:
    """Every channel in a row must come from one read.

    Calling get_readings per channel made a row three separate visits
    to the instrument. Stepping a load from 0.1 A to 0.3 A to 0.5 A
    while acquiring volts, amps and watts, the rows taken during a step
    disagreed with themselves:

        4.97 V   0.14 A   0.84490 W      (V*I = 0.6958)

    The current there was read after the voltage and before the power,
    and the load moved in between. It also cost three round trips a
    sample where one does.
    """

    class Drifting:
        """A supply whose current rises on every read, as one does while
        a load is being stepped."""

        def __init__(self):
            self.reads = 0

        async def get_readings(self):
            self.reads += 1
            return {"voltage_actual": 5.0,
                    "current_actual": 0.1 * self.reads}

    @pytest.mark.asyncio
    async def test_one_read_serves_the_whole_row(self):
        manager = AcquisitionManager()
        supply = self.Drifting()

        sample = await manager._read_once(supply)
        volts = await manager._get_channel_value(supply, "voltage", sample)
        amps = await manager._get_channel_value(supply, "current", sample)
        watts = await manager._get_channel_value(supply, "power", sample)

        assert supply.reads == 1, (
            f"{supply.reads} visits to the instrument for one row")
        assert watts == pytest.approx(volts * amps), (
            f"{volts} V x {amps} A is not {watts} W -- the row is not one "
            f"sample")

    @pytest.mark.asyncio
    async def test_without_a_shared_read_it_would_drift(self):
        """The bug, demonstrated: three independent reads disagree."""
        manager = AcquisitionManager()
        supply = self.Drifting()

        volts = await manager._get_channel_value(supply, "voltage")
        amps = await manager._get_channel_value(supply, "current")
        watts = await manager._get_channel_value(supply, "power")

        assert supply.reads == 3
        assert watts != pytest.approx(volts * amps), (
            "the fixture is meant to drift; if it does not, this test "
            "proves nothing")

    @pytest.mark.asyncio
    async def test_a_lone_caller_still_gets_a_value(self):
        """create_session and the trigger wait pass no sample."""
        manager = AcquisitionManager()
        value = await manager._get_channel_value(Supply(), "voltage")
        assert value == pytest.approx(5.01)
