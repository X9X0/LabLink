"""Every driver can measure a channel, not only the ones that had to.

Each instrument implements get_readings; only some implemented
get_measurement -- the DL3000 load did, the supplies did not. The
acquisition engine reached for the second, so no power supply could be
acquired from at all.

That was fixed in the engine, by falling back to readings. It made
acquisition work and left the gap where it was: the next caller
reaching for get_measurement on a supply would meet exactly the same
wall, and nothing in the base class said the method was optional.

So the base class now derives it from get_readings. A driver that can
measure a channel directly still overrides -- the load does, because
it has a SCPI query per quantity and reading all four to return one
would be wasteful.
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.equipment.base import BaseEquipment


class Supply(BaseEquipment):
    """Keys as the 1902B and 9205B report them, and no power."""

    def __init__(self, **overrides):
        self.readings = {
            "voltage_actual": 5.01,
            "current_actual": 0.25,
            "voltage_set": 5.0,
            "current_set": 1.0,
        }
        self.readings.update(overrides)

    async def get_readings(self, channel: int = 1):
        return dict(self.readings)

    async def get_info(self):
        raise NotImplementedError

    async def get_status(self):
        raise NotImplementedError

    async def execute_command(self, command, parameters):
        raise NotImplementedError


class Silent(Supply):
    """A driver with no readings at all."""

    async def get_readings(self, channel: int = 1):
        raise OSError("no reply")


class TestASupplyCanMeasure:
    @pytest.mark.parametrize("channel,value,unit", [
        ("V", 5.01, "V"),
        ("I", 0.25, "A"),
        ("VSET", 5.0, "V"),
        ("ISET", 1.0, "A"),
    ])
    @pytest.mark.asyncio
    async def test_the_quantity_comes_back_with_its_unit(self, channel,
                                                         value, unit):
        got = await Supply().get_measurement(channel)
        assert got["value"] == pytest.approx(value)
        assert got["unit"] == unit

    @pytest.mark.asyncio
    async def test_power_is_computed_when_it_is_not_reported(self):
        got = await Supply().get_measurement("P")
        assert got["value"] == pytest.approx(5.01 * 0.25)
        assert got["unit"] == "W"

    @pytest.mark.parametrize("spelling", [
        "V", "v", "VOLT", "voltage", "CH1:V", "ch1:voltage",
    ])
    @pytest.mark.asyncio
    async def test_the_spellings_a_caller_might_use(self, spelling):
        got = await Supply().get_measurement(spelling)
        assert got["value"] == pytest.approx(5.01)

    @pytest.mark.asyncio
    async def test_the_default_channel_is_voltage(self):
        assert (await Supply().get_measurement())["quantity"] == "voltage"

    @pytest.mark.asyncio
    async def test_an_unknown_channel_says_what_it_takes(self):
        with pytest.raises(ValueError) as refused:
            await Supply().get_measurement("TEMPERATURE")
        assert "V" in str(refused.value)

    @pytest.mark.asyncio
    async def test_a_quantity_it_does_not_report_is_refused(self):
        """A supply has no resistance to give."""
        with pytest.raises(NotImplementedError):
            await Supply().get_measurement("R")

    @pytest.mark.asyncio
    async def test_a_driver_with_no_readings_says_so(self):
        with pytest.raises(NotImplementedError):
            await Silent().get_measurement("V")


class TestPowerNeedsBothHalves:
    @pytest.mark.asyncio
    async def test_it_is_refused_without_current(self):
        supply = Supply()
        del supply.readings["current_actual"]
        with pytest.raises(NotImplementedError):
            await supply.get_measurement("P")

    @pytest.mark.asyncio
    async def test_a_reported_power_is_preferred_to_a_computed_one(self):
        """If a driver measures power, that is better than V times I."""
        supply = Supply(power=1.0)
        assert (await supply.get_measurement("P"))["value"] == pytest.approx(
            1.0)


class TestTheLoadKeepsItsOwn:
    def test_it_overrides_rather_than_inherits(self):
        """It has a SCPI query per quantity; reading all four to return
        one would be wasteful."""
        from server.equipment.rigol_electronic_load import RigolDL3000Base

        assert "get_measurement" in RigolDL3000Base.__dict__, (
            "the load lost its own implementation")


class TestEveryDriverHasIt:
    """The point of putting it on the base class."""

    @pytest.mark.parametrize("module,name", [
        ("server.equipment.bk_power_supply", "BK1902B"),
        ("server.equipment.bk_scpi", "BKSCPIPowerSupply"),
        ("server.equipment.bk_scpi", "BKSCPIElectronicLoad"),
        ("server.equipment.bk_scpi", "BKSCPIMultimeter"),
        ("server.equipment.rigol_electronic_load", "RigolDL3021A"),
    ])
    def test_the_method_is_there(self, module, name):
        import importlib

        cls = getattr(importlib.import_module(module), name)
        assert hasattr(cls, "get_measurement"), name


class TestTheAcquisitionEngineUsesIt:
    """With the gap closed, a supply resolves through get_measurement
    rather than the engine's readings fallback."""

    @pytest.mark.asyncio
    async def test_a_supply_channel_resolves(self):
        from server.acquisition.manager import AcquisitionManager

        manager = AcquisitionManager()
        value = await manager._get_channel_value(Supply(), "voltage")
        assert value == pytest.approx(5.01)

    @pytest.mark.asyncio
    async def test_power_still_arrives(self):
        from server.acquisition.manager import AcquisitionManager

        manager = AcquisitionManager()
        value = await manager._get_channel_value(Supply(), "power")
        assert value == pytest.approx(5.01 * 0.25)
        assert not math.isnan(value)
