"""Tests for the mock multimeter and its integration with the equipment
manager, acquisition engine and profile defaults."""

import math

import pytest

from server.acquisition.manager import AcquisitionManager
from server.acquisition.models import AcquisitionConfig, AcquisitionMode
from server.equipment.manager import EquipmentManager
from server.equipment.mock.mock_multimeter import MockMultimeter
from server.equipment.mock_helper import MockEquipmentHelper
from shared.models.data import MultimeterData
from shared.models.equipment import EquipmentType


@pytest.fixture
async def equipment_manager():
    manager = EquipmentManager()
    await manager.initialize()
    yield manager
    await manager.shutdown()


@pytest.fixture
async def mock_dmm(equipment_manager):
    equipment_id = await equipment_manager.connect_device(
        resource_string="MOCK::DMM::0",
        equipment_type=EquipmentType.MULTIMETER,
        model="MockDMM-3068",
    )
    yield equipment_id, equipment_manager.equipment[equipment_id]


class TestMockMultimeterStandalone:
    @pytest.mark.asyncio
    async def test_connect_info_status(self):
        dmm = MockMultimeter()
        await dmm.connect()
        info = await dmm.get_info()
        assert info.type == EquipmentType.MULTIMETER
        assert info.id.startswith("dmm_")
        status = await dmm.get_status()
        assert status.connected is True
        assert status.capabilities["digits"] == 6.5
        assert status.capabilities["function"] == "DCV"

    @pytest.mark.asyncio
    async def test_measure_matches_simulated_value(self):
        dmm = MockMultimeter()
        await dmm.connect()
        dmm.set_noise(0.0)
        dmm.set_simulated_value("RES", 4700.0)
        reading = await dmm.measure("RES")
        assert isinstance(reading, MultimeterData)
        assert reading.function == "RES"
        assert reading.value == pytest.approx(4700.0)
        assert reading.unit == "Ohm"
        assert reading.range_full_scale == pytest.approx(20e3)  # auto-ranged

    @pytest.mark.asyncio
    async def test_manual_range_and_overload(self):
        dmm = MockMultimeter()
        await dmm.connect()
        dmm.set_noise(0.0)
        dmm.set_simulated_value("DCV", 5.0)
        rng = await dmm.set_range(2.0, function="DCV")  # too small for 5 V
        assert rng["index"] == 1 and rng["auto_range"] is False
        reading = await dmm.measure()
        assert reading.overload is True and reading.value is None
        await dmm.set_auto_range(True)
        reading = await dmm.measure()
        assert reading.value == pytest.approx(5.0)
        dmm.simulate_overload("DCV")
        assert (await dmm.measure()).overload is True

    @pytest.mark.asyncio
    async def test_commands_not_connected(self):
        dmm = MockMultimeter()
        with pytest.raises(RuntimeError):
            await dmm.execute_command("get_readings", {})

    @pytest.mark.asyncio
    async def test_secondary_display_and_channels(self):
        dmm = MockMultimeter()
        await dmm.connect()
        dmm.set_noise(0.0)
        await dmm.set_function("ACV")
        await dmm.set_secondary_function("FREQ")
        reading = await dmm.get_readings()
        assert reading.secondary_function == "FREQ"
        assert reading.secondary_value == pytest.approx(1000.0)
        assert (await dmm.get_measurement("CH2"))["unit"] == "Hz"
        assert (await dmm.get_measurement("CH1"))["function"] == "ACV"
        assert (await dmm.get_measurement("DCI"))["value"] == pytest.approx(0.1)

    @pytest.mark.asyncio
    async def test_math_and_limits(self):
        dmm = MockMultimeter()
        await dmm.connect()
        dmm.set_noise(0.0)
        await dmm.set_math_function("MAX")
        await dmm.read_samples(5)
        stats = await dmm.get_statistics()
        assert stats["count"] == 5 and stats["max"] == pytest.approx(5.0)
        await dmm.set_limits(4.9, 5.1)
        assert await dmm.get_limit_result() == "PASS"
        await dmm.set_limits(0.0, 1.0)
        assert await dmm.get_limit_result() == "FAIL"
        rel = await dmm.set_rel_offset("CURR")
        assert rel["offset"] == pytest.approx(5.0)
        assert (await dmm.measure()).value == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_validation_errors(self):
        dmm = MockMultimeter()
        await dmm.connect()
        with pytest.raises(ValueError):
            await dmm.set_function("KELVIN")
        with pytest.raises(ValueError):
            await dmm.set_rate("TURBO")
        with pytest.raises(ValueError):
            await dmm.set_trigger_source("MAYBE")
        with pytest.raises(ValueError):
            await dmm.set_continuity_threshold(5000)
        with pytest.raises(ValueError):
            await dmm.execute_command("nope", {})


class TestMockMultimeterViaManager:
    @pytest.mark.asyncio
    async def test_manager_creates_mock_dmm(self, mock_dmm):
        equipment_id, dmm = mock_dmm
        assert isinstance(dmm, MockMultimeter)
        assert equipment_id.startswith("dmm_")
        readings = await dmm.execute_command("get_readings", {})
        assert readings.function == "DCV"

    @pytest.mark.asyncio
    async def test_manager_matches_dmm_keyword(self, equipment_manager):
        eq = equipment_manager._create_equipment_instance(
            "MOCK::DMM::7", EquipmentType.MULTIMETER, "MockDMM"
        )
        assert isinstance(eq, MockMultimeter)

    @pytest.mark.asyncio
    async def test_default_mock_set_includes_multimeter(self, equipment_manager):
        ids = await MockEquipmentHelper.register_default_mock_equipment(equipment_manager)
        types = {(await equipment_manager.equipment[i].get_info()).type for i in ids}
        assert EquipmentType.MULTIMETER in types
        assert "MOCK::DMM::0" in MockEquipmentHelper.list_mock_resource_strings()

    @pytest.mark.asyncio
    async def test_register_mock_multimeters_by_type(self, equipment_manager):
        ids = await MockEquipmentHelper.register_mock_equipment(
            equipment_manager, EquipmentType.MULTIMETER, count=2
        )
        assert len(ids) == 2


class TestMockMultimeterAcquisition:
    @pytest.mark.asyncio
    async def test_single_shot_acquisition_on_function_channels(self, mock_dmm):
        import asyncio

        equipment_id, dmm = mock_dmm
        dmm.set_noise(0.0)
        dmm.set_simulated_value("DCV", 3.3)
        dmm.set_simulated_value("RES", 220.0)

        acq = AcquisitionManager()
        config = AcquisitionConfig(
            equipment_id=equipment_id,
            mode=AcquisitionMode.SINGLE_SHOT,
            sample_rate=50.0,
            num_samples=5,
            channels=["DCV", "RES"],
            buffer_size=100,
        )
        session = await acq.create_session(dmm, config)
        assert await acq.start_acquisition(session.acquisition_id, dmm)

        for _ in range(200):
            data, timestamps = acq.get_buffer_data(session.acquisition_id)
            if len(timestamps) >= 5:
                break
            await asyncio.sleep(0.02)
        data, timestamps = acq.get_buffer_data(session.acquisition_id)
        assert len(timestamps) >= 5
        # data shape is (channels, samples) in config.channels order
        assert list(data[0, :]) == pytest.approx([3.3] * len(timestamps))
        assert list(data[1, :]) == pytest.approx([220.0] * len(timestamps))
        assert not math.isnan(float(data[0, 0]))
        try:
            await acq.stop_acquisition(session.acquisition_id)
        except Exception:
            pass  # already finished its single shot
