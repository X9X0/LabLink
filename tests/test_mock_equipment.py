"""
Automated tests using mock equipment.

These tests validate LabLink functionality using mock equipment drivers,
enabling testing without physical hardware.
"""

import pytest
import asyncio
from typing import Dict

# Import from server and shared packages
from server.equipment.manager import EquipmentManager
from server.equipment.mock_helper import MockEquipmentHelper, setup_demo_lab
from shared.models.equipment import EquipmentType, EquipmentStatus


# ==================== Fixtures ====================

@pytest.fixture
async def equipment_manager():
    """Fixture providing initialized equipment manager."""
    manager = EquipmentManager()
    await manager.initialize()
    yield manager
    await manager.shutdown()


@pytest.fixture
async def mock_lab(equipment_manager):
    """Fixture providing complete mock lab (oscilloscope, PSU, load)."""
    lab = await setup_demo_lab(equipment_manager)
    yield lab
    # Cleanup handled by equipment_manager fixture


@pytest.fixture
async def mock_oscilloscope(equipment_manager):
    """Fixture providing single mock oscilloscope."""
    equipment_id = await equipment_manager.connect_device(
        resource_string="MOCK::SCOPE::0",
        equipment_type=EquipmentType.OSCILLOSCOPE,
        model="MockScope-2000"
    )
    yield equipment_id, equipment_manager.equipment[equipment_id]


@pytest.fixture
async def mock_power_supply(equipment_manager):
    """Fixture providing single mock power supply."""
    equipment_id = await equipment_manager.connect_device(
        resource_string="MOCK::PSU::0",
        equipment_type=EquipmentType.POWER_SUPPLY,
        model="MockPSU-3000"
    )
    yield equipment_id, equipment_manager.equipment[equipment_id]


@pytest.fixture
async def mock_electronic_load(equipment_manager):
    """Fixture providing single mock electronic load."""
    equipment_id = await equipment_manager.connect_device(
        resource_string="MOCK::LOAD::0",
        equipment_type=EquipmentType.ELECTRONIC_LOAD,
        model="MockLoad-1000"
    )
    yield equipment_id, equipment_manager.equipment[equipment_id]


# ==================== Equipment Manager Tests ====================

@pytest.mark.asyncio
async def test_equipment_manager_initialization(equipment_manager):
    """Test equipment manager initializes correctly."""
    assert equipment_manager is not None
    assert equipment_manager.resource_manager is not None


@pytest.mark.asyncio
async def test_mock_lab_setup(equipment_manager):
    """Test complete mock lab setup."""
    lab = await setup_demo_lab(equipment_manager)

    assert 'oscilloscope' in lab
    assert 'power_supply' in lab
    assert 'electronic_load' in lab

    # Verify all equipment is connected
    assert equipment_manager.equipment[lab['oscilloscope']].connected
    assert equipment_manager.equipment[lab['power_supply']].connected
    assert equipment_manager.equipment[lab['electronic_load']].connected


# ==================== Mock Oscilloscope Tests ====================

@pytest.mark.asyncio
async def test_oscilloscope_connection(mock_oscilloscope):
    """Test oscilloscope connects successfully."""
    equipment_id, equipment = mock_oscilloscope

    assert equipment.connected
    # Check ID prefix matches equipment type
    assert equipment_id.startswith('scope_')


@pytest.mark.asyncio
async def test_oscilloscope_info(mock_oscilloscope):
    """Test oscilloscope returns correct info."""
    equipment_id, equipment = mock_oscilloscope

    info = await equipment.get_info()

    assert info.type == EquipmentType.OSCILLOSCOPE
    assert info.manufacturer == "Mock Instruments"
    assert info.model == "MockScope-2000"
    assert "MOCK" in info.serial_number


@pytest.mark.asyncio
async def test_oscilloscope_status(mock_oscilloscope):
    """Test oscilloscope status retrieval."""
    equipment_id, equipment = mock_oscilloscope

    status = await equipment.get_status()

    assert status.connected
    assert status.error is None or status.error == ""
    assert "num_channels" in status.capabilities
    assert status.capabilities["num_channels"] == 4


@pytest.mark.asyncio
async def test_oscilloscope_waveform_acquisition(mock_oscilloscope):
    """Test waveform data acquisition."""
    equipment_id, equipment = mock_oscilloscope

    waveform = await equipment.get_waveform(channel=1)

    assert waveform is not None
    assert waveform.num_samples > 0
    assert waveform.channel == 1


@pytest.mark.asyncio
async def test_oscilloscope_measurements(mock_oscilloscope):
    """Test oscilloscope automated measurements."""
    equipment_id, equipment = mock_oscilloscope

    measurements = await equipment.get_measurements(channel=1)

    assert isinstance(measurements, dict)
    assert 'vpp' in measurements
    assert 'freq' in measurements  # Note: 'freq' not 'frequency'
    assert 'vrms' in measurements
    assert measurements['vpp'] > 0


@pytest.mark.asyncio
async def test_oscilloscope_waveform_types(mock_oscilloscope):
    """Test different waveform type generation."""
    equipment_id, equipment = mock_oscilloscope

    waveform_types = ["sine", "square", "triangle", "noise"]

    for waveform_type in waveform_types:
        equipment.set_waveform_type(1, waveform_type)
        waveform = await equipment.get_waveform(channel=1)

        assert waveform.num_samples > 0


@pytest.mark.asyncio
async def test_oscilloscope_configuration(mock_oscilloscope, equipment_manager):
    """Test oscilloscope configuration via helper."""
    equipment_id, equipment = mock_oscilloscope

    await MockEquipmentHelper.configure_mock_oscilloscope(
        equipment_manager,
        equipment_id,
        {
            "channel": 1,
            "waveform_type": "sine",
            "frequency": 2000.0,
            "amplitude": 3.0
        }
    )

    assert equipment.waveform_type[1] == "sine"
    assert equipment.frequency[1] == 2000.0
    assert equipment.amplitude[1] == 3.0


# ==================== Mock Power Supply Tests ====================

@pytest.mark.asyncio
async def test_power_supply_connection(mock_power_supply):
    """Test power supply connects successfully."""
    equipment_id, equipment = mock_power_supply

    assert equipment.connected
    assert equipment_id.startswith('ps_')


@pytest.mark.asyncio
async def test_power_supply_info(mock_power_supply):
    """Test power supply returns correct info."""
    equipment_id, equipment = mock_power_supply

    info = await equipment.get_info()

    assert info.type == EquipmentType.POWER_SUPPLY
    assert "Mock" in info.manufacturer
    assert "PSU" in info.model


@pytest.mark.asyncio
async def test_power_supply_voltage_control(mock_power_supply):
    """Test power supply voltage control."""
    equipment_id, equipment = mock_power_supply

    # Set voltage and enable output
    await equipment.set_voltage(12.0)
    await equipment.set_output(True)  # Must enable output to measure actual voltage

    # Allow settling
    await asyncio.sleep(0.1)

    # Verify setpoint was set correctly (actual voltage may vary with load)
    readings = await equipment.get_readings()
    assert readings.voltage_set == 12.0
    assert readings.output_enabled


@pytest.mark.asyncio
async def test_power_supply_current_control(mock_power_supply):
    """Test power supply current control."""
    equipment_id, equipment = mock_power_supply

    # Set current limit
    await equipment.set_current(2.0)
    await asyncio.sleep(0.1)

    readings = await equipment.get_readings()
    # Current limit should be set
    assert readings.current_set == 2.0


@pytest.mark.asyncio
async def test_power_supply_output_control(mock_power_supply):
    """Test power supply output enable/disable."""
    equipment_id, equipment = mock_power_supply

    # Disable output
    await equipment.set_output(False)
    readings = await equipment.get_readings()
    assert not readings.output_enabled

    # Enable output
    await equipment.set_output(True)
    readings = await equipment.get_readings()
    assert readings.output_enabled


@pytest.mark.asyncio
async def test_power_supply_measurements(mock_power_supply):
    """Test power supply measurement readings."""
    equipment_id, equipment = mock_power_supply

    # Set known state
    await equipment.set_voltage(10.0)
    await equipment.set_output(True)
    await asyncio.sleep(0.1)

    readings = await equipment.get_readings()

    assert readings.voltage_actual is not None
    assert readings.current_actual is not None
    assert readings.output_enabled


# ==================== Mock Electronic Load Tests ====================

@pytest.mark.asyncio
async def test_electronic_load_connection(mock_electronic_load):
    """Test electronic load connects successfully."""
    equipment_id, equipment = mock_electronic_load

    assert equipment.connected
    assert equipment_id.startswith('load_')


@pytest.mark.asyncio
async def test_electronic_load_info(mock_electronic_load):
    """Test electronic load returns correct info."""
    equipment_id, equipment = mock_electronic_load

    info = await equipment.get_info()

    assert info.type == EquipmentType.ELECTRONIC_LOAD
    assert "Mock" in info.manufacturer
    assert "Load" in info.model


@pytest.mark.asyncio
async def test_electronic_load_modes(mock_electronic_load):
    """Test electronic load mode switching."""
    equipment_id, equipment = mock_electronic_load

    modes = ["CC", "CV", "CR", "CP"]

    for mode in modes:
        await equipment.set_mode(mode)
        readings = await equipment.get_readings()
        assert readings.mode == mode


@pytest.mark.asyncio
async def test_electronic_load_cc_mode(mock_electronic_load):
    """Test constant current (CC) mode."""
    equipment_id, equipment = mock_electronic_load

    await equipment.set_mode("CC")
    await equipment.set_current(3.0)
    await equipment.set_input(True)
    await asyncio.sleep(0.1)

    readings = await equipment.get_readings()
    assert readings.mode == "CC"
    assert readings.load_enabled


@pytest.mark.asyncio
async def test_electronic_load_input_control(mock_electronic_load):
    """Test electronic load input enable/disable."""
    equipment_id, equipment = mock_electronic_load

    # Disable input
    await equipment.set_input(False)
    readings = await equipment.get_readings()
    assert not readings.load_enabled

    # Enable input
    await equipment.set_input(True)
    readings = await equipment.get_readings()
    assert readings.load_enabled


@pytest.mark.asyncio
async def test_electronic_load_measurements(mock_electronic_load):
    """Test electronic load measurement readings."""
    equipment_id, equipment = mock_electronic_load

    await equipment.set_mode("CC")
    await equipment.set_current(2.0)
    await equipment.set_input(True)
    await asyncio.sleep(0.1)

    readings = await equipment.get_readings()

    assert readings.voltage is not None
    assert readings.current is not None
    assert readings.power is not None
    assert readings.mode == "CC"


# ==================== Multi-Device Tests ====================

@pytest.mark.asyncio
async def test_multiple_oscilloscopes(equipment_manager):
    """Test registering and using multiple oscilloscopes."""
    # Register 3 oscilloscopes
    scope_ids = await MockEquipmentHelper.register_mock_equipment(
        equipment_manager,
        EquipmentType.OSCILLOSCOPE,
        count=3
    )

    assert len(scope_ids) == 3

    # Verify all are connected
    for scope_id in scope_ids:
        equipment = equipment_manager.equipment[scope_id]
        assert equipment.connected


@pytest.mark.asyncio
async def test_concurrent_waveform_acquisition(equipment_manager):
    """Test acquiring waveforms from multiple oscilloscopes concurrently."""
    # Register 2 oscilloscopes
    scope_ids = await MockEquipmentHelper.register_mock_equipment(
        equipment_manager,
        EquipmentType.OSCILLOSCOPE,
        count=2
    )

    # Acquire from both simultaneously
    tasks = []
    for scope_id in scope_ids:
        equipment = equipment_manager.equipment[scope_id]
        tasks.append(equipment.get_waveform(channel=1))

    waveforms = await asyncio.gather(*tasks)

    assert len(waveforms) == 2
    for waveform in waveforms:
        assert waveform.num_samples > 0


@pytest.mark.asyncio
async def test_full_lab_workflow(mock_lab, equipment_manager):
    """Test complete lab workflow with all equipment types."""
    # Get equipment
    scope = equipment_manager.equipment[mock_lab['oscilloscope']]
    psu = equipment_manager.equipment[mock_lab['power_supply']]
    load = equipment_manager.equipment[mock_lab['electronic_load']]

    # Configure power supply
    await psu.set_voltage(12.0)
    await psu.set_output(True)

    # Configure electronic load
    await load.set_mode("CC")
    await load.set_current(1.0)
    await load.set_input(True)

    # Acquire waveform
    waveform = await scope.get_waveform(channel=1)

    # Verify all operations succeeded
    psu_readings = await psu.get_readings()
    load_readings = await load.get_readings()

    assert psu_readings.voltage_actual > 0
    assert load_readings.load_enabled
    assert waveform.num_samples > 0


# ==================== Helper Function Tests ====================

@pytest.mark.asyncio
async def test_list_mock_resource_strings():
    """Test listing available mock resource strings."""
    resources = MockEquipmentHelper.list_mock_resource_strings()

    assert len(resources) > 0
    assert "MOCK::SCOPE::0" in resources
    assert "MOCK::PSU::0" in resources
    assert "MOCK::LOAD::0" in resources


@pytest.mark.asyncio
async def test_register_default_mock_equipment(equipment_manager):
    """Test default mock equipment registration."""
    equipment_ids = await MockEquipmentHelper.register_default_mock_equipment(
        equipment_manager
    )

    assert len(equipment_ids) == 3

    # Verify types
    types_found = set()
    for equipment_id in equipment_ids:
        equipment = equipment_manager.equipment[equipment_id]
        info = await equipment.get_info()
        types_found.add(info.type)

    assert EquipmentType.OSCILLOSCOPE in types_found
    assert EquipmentType.POWER_SUPPLY in types_found
    assert EquipmentType.ELECTRONIC_LOAD in types_found


# ==================== Performance Tests ====================

@pytest.mark.asyncio
async def test_oscilloscope_acquisition_performance(mock_oscilloscope):
    """Test oscilloscope acquisition performance."""
    equipment_id, equipment = mock_oscilloscope

    import time

    # Measure 10 acquisitions
    start_time = time.time()
    for _ in range(10):
        await equipment.get_waveform(channel=1)
    elapsed = time.time() - start_time

    # Should complete reasonably fast (< 1 second total)
    assert elapsed < 1.0, f"10 acquisitions took {elapsed:.2f}s (should be < 1s)"


@pytest.mark.asyncio
async def test_concurrent_equipment_operations(mock_lab, equipment_manager):
    """Test concurrent operations on multiple equipment types."""
    import time

    scope = equipment_manager.equipment[mock_lab['oscilloscope']]
    psu = equipment_manager.equipment[mock_lab['power_supply']]
    load = equipment_manager.equipment[mock_lab['electronic_load']]

    # Run operations concurrently
    start_time = time.time()
    results = await asyncio.gather(
        scope.get_waveform(channel=1),
        psu.get_readings(),
        load.get_readings()
    )
    elapsed = time.time() - start_time

    # Should complete quickly
    assert elapsed < 0.5, f"Concurrent operations took {elapsed:.3f}s"
    assert len(results) == 3


# ==================== Test Summary ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
