"""Tests for the mock data acquisition / switch unit."""

import math

import pytest

from server.equipment.mock.mock_daq import MockDAQ
from shared.models.data import DataAcquisitionData
from shared.models.equipment import EquipmentType


@pytest.fixture
async def daq():
    dev = MockDAQ()
    await dev.connect()
    dev.set_noise(0.0)
    yield dev
    await dev.disconnect()


class TestMockDAQ:
    @pytest.mark.asyncio
    async def test_connect_info_status_modules(self, daq):
        info = await daq.get_info()
        assert info.type == EquipmentType.DATA_ACQUISITION
        assert info.id.startswith("daq_")
        assert info.model == "MockDAQ-300" and info.resource_string == "MOCK::DAQ::0"
        modules = await daq.get_modules()
        assert modules[1]["model"] == "MC3120" and modules[2]["model"] == "MC3120"
        assert modules[1]["channels"] == 20 and modules[3]["kind"] == "actuator"
        status = await daq.get_status()
        caps = status.capabilities
        assert status.connected is True and caps["mock"] is True
        assert caps["slots"] == [1, 2, 3, 4, 5] and caps["modules"]["2"]["model"] == "MC3120"
        assert caps["dmm_installed"] is True and "TEMP" in caps["functions"]
        assert caps["supports_acquisition"] is True

    @pytest.mark.asyncio
    async def test_scan_returns_simulated_values(self, daq):
        assert await daq.set_scan_list("101:105") == ["101", "102", "103", "104", "105"]
        data = await daq.scan()
        assert isinstance(data, DataAcquisitionData)
        assert data.scan_list == ["101", "102", "103", "104", "105"]
        assert data.readings["101"] == pytest.approx(1.0) and data.readings["105"] == pytest.approx(1.4)
        assert data.units["103"] == "V" and data.functions["103"] == "DCV"
        assert data.installed_modules == {"1": "MC3120", "2": "MC3120", "3": "MC3416"}
        daq.set_simulated_value("103", 4.7)
        assert (await daq.scan()).readings["103"] == pytest.approx(4.7)
        daq.simulate_overload("104")
        assert math.isnan((await daq.scan()).readings["104"])
        daq.simulate_overload("104", False)
        # manual range too small -> overload
        await daq.configure_channel("103", "DCV", range=2)
        assert math.isnan((await daq.scan()).readings["103"])
        assert await daq.get_data_points() == 5 - 1
        # scan list is stored in ascending order like the real mainframe
        assert await daq.set_scan_list(["205", "201"]) == ["201", "205"]
        with pytest.raises(ValueError):
            await daq.set_scan_list("301")  # actuator channels cannot be scanned
        with pytest.raises(ValueError):
            await daq.set_scan_list("121")  # MC3120 has 20 channels

    @pytest.mark.asyncio
    async def test_configure_temperature_and_units(self, daq):
        cfg = await daq.configure_channel("201:203", "TEMP", sensor="TC", sensor_type="K")
        assert cfg["function"] == "TEMP" and cfg["sensor"] == "TC" and cfg["sensor_type"] == "K"
        await daq.set_scan_list("201:203")
        data = await daq.scan()
        assert data.readings["201"] == pytest.approx(20.0) and data.units["201"] == "C"
        assert await daq.set_temperature_unit("F", "201") == "F"
        data = await daq.scan()
        assert data.readings["201"] == pytest.approx(68.0) and data.units["201"] == "F"
        assert data.readings["202"] == pytest.approx(20.5) and data.units["202"] == "C"
        assert await daq.set_temperature_unit("K") == "K"  # whole scan list
        assert (await daq.scan()).readings["203"] == pytest.approx(21.0 + 273.15)
        with pytest.raises(ValueError):
            await daq.set_temperature_unit("F", "101")  # not a temperature channel
        with pytest.raises(ValueError):
            await daq.configure_channel("101", "TEMP", sensor="TC", sensor_type="X")
        with pytest.raises(ValueError):
            await daq.configure_channel("101", "DCI")  # MC3120 has no current channels
        with pytest.raises(ValueError):
            await daq.configure_channel("115", "FRES")  # 4-wire pairs use 1..10
        cfg = await daq.get_configuration("201,101")
        assert cfg["201"]["function"] == "TEMP" and cfg["101"]["function"] == "DCV"

    @pytest.mark.asyncio
    async def test_read_channel_and_switching(self, daq):
        single = await daq.read_channel("CH110")
        assert single["channel"] == "110" and single["value"] == pytest.approx(1.9) and single["unit"] == "V"
        with pytest.raises(ValueError):
            await daq.read_channel("301")  # actuator
        assert await daq.close_channel("301:303") == {"301": True, "302": True, "303": True}
        assert await daq.get_closed_channels() == ["301", "302", "303"]
        assert await daq.open_channel("302") == {"302": False}
        assert await daq.get_closed_channels("301:305") == ["301", "303"]
        await daq.set_scan_list("101:102")
        with pytest.raises(ValueError):
            await daq.close_channel("101")  # in the scan list
        await daq.close_channel("105")  # multiplexer relay outside the scan list is fine
        with pytest.raises(ValueError):
            await daq.close_channel("401")  # empty slot

    @pytest.mark.asyncio
    async def test_trigger(self, daq):
        trig = await daq.set_trigger("timer", count=5, interval=1.5)
        assert trig == {"source": "TIMER", "count": 5, "interval": 1.5}
        trig = await daq.set_trigger("BUS", count="INF")
        assert trig["count"] == "INFINITY" and trig["source"] == "BUS"
        await daq.set_scan_list("101")
        await daq.trigger_scan()
        assert daq.scan_count == 1
        with pytest.raises(ValueError):
            await daq.set_trigger("LASER")
        with pytest.raises(ValueError):
            await daq.set_trigger("IMM", count=0)

    @pytest.mark.asyncio
    async def test_get_measurement_shares_one_scan_per_cycle(self, daq):
        await daq.set_scan_list("101:103")
        m1 = await daq.get_measurement("101")
        m2 = await daq.get_measurement("CH102")
        m3 = await daq.get_measurement("@103")
        assert daq.scan_count == 1
        assert m1["value"] == pytest.approx(1.0) and m2["value"] == pytest.approx(1.1) and m3["value"] == pytest.approx(1.2)
        assert m1["unit"] == "V" and m1["function"] == "DCV" and m1["overload"] is False
        await daq.get_measurement("101")  # next polling cycle
        assert daq.scan_count == 2
        other = await daq.get_measurement("205")  # not in the scan list: direct read
        assert other["value"] == pytest.approx(22.0) and daq.scan_count == 2
        with pytest.raises(ValueError):
            await daq.get_measurement("999")

    @pytest.mark.asyncio
    async def test_execute_command_dispatch_state_reset(self, daq):
        await daq.execute_command("configure_channel", {"channel": "101:102", "function": "DCV", "range": 20})
        assert await daq.execute_command("set_scan_list", {"channels": "101:102"}) == ["101", "102"]
        readings = await daq.execute_command("get_readings", {})
        assert isinstance(readings, DataAcquisitionData) and set(readings.readings) == {"101", "102"}
        meas = await daq.execute_command("get_measurements", {"channel": 1})
        assert meas["102"] == pytest.approx(1.1) and meas["102_unit"] == "V"
        state = await daq.execute_command("get_state", {})
        assert state["scan_list"] == ["101", "102"] and state["channels"]["101"]["range"] == 20.0
        assert state["modules"] == {"1": "MC3120", "2": "MC3120", "3": "MC3416"}
        assert (await daq.execute_command("get_error", {}))["code"] == 0
        assert await daq.execute_command("self_test", {}) is True
        with pytest.raises(ValueError):
            await daq.execute_command("teleport", {})
        await daq.execute_command("reset", {})
        assert await daq.get_scan_list() == []
        with pytest.raises(ValueError):
            await daq.scan()
        await daq.disconnect()
        with pytest.raises(RuntimeError):
            await daq.execute_command("get_readings", {})
