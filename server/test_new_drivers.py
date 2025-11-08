#!/usr/bin/env python3
"""
Standalone test script for new equipment drivers.
Tests without requiring pytest - uses standard unittest with mocks.
"""

import sys
import asyncio
from unittest.mock import MagicMock, AsyncMock

# Add parent directory to path
sys.path.append("..")

from equipment.rigol_scope import RigolDS1104
from equipment.rigol_electronic_load import RigolDL3021A
from equipment.bk_power_supply import BK9205B, BK1685B


class TestResults:
    """Track test results."""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def add_pass(self, test_name):
        self.passed += 1
        print(f"  ✓ {test_name}")

    def add_fail(self, test_name, error):
        self.failed += 1
        self.errors.append((test_name, str(error)))
        print(f"  ✗ {test_name}: {error}")

    def summary(self):
        print(f"\n{'='*60}")
        print(f"Test Summary: {self.passed} passed, {self.failed} failed")
        print(f"{'='*60}")
        if self.errors:
            print("\nFailures:")
            for name, error in self.errors:
                print(f"  - {name}: {error}")
        return self.failed == 0


def create_mock_instrument(idn_response):
    """Create a mock VISA instrument."""
    mock = MagicMock()
    mock.timeout = 10000
    mock.query = MagicMock(return_value=idn_response)
    mock.write = MagicMock()
    mock.close = MagicMock()
    mock.query_binary_values = MagicMock(return_value=[0] * 1000)
    return mock


def create_mock_resource_manager(instrument):
    """Create a mock VISA resource manager."""
    mock_rm = MagicMock()
    mock_rm.open_resource = MagicMock(return_value=instrument)
    return mock_rm


async def test_rigol_ds1104(results):
    """Test Rigol DS1104 oscilloscope driver."""
    print("\nTesting Rigol DS1104 Oscilloscope...")

    idn = "RIGOL TECHNOLOGIES,DS1104Z,DS1ZA123456789,00.04.04.SP3"
    mock_inst = create_mock_instrument(idn)
    mock_rm = create_mock_resource_manager(mock_inst)

    scope = RigolDS1104(mock_rm, "USB0::0x1AB1::0x0588::DS1ZA123456789::INSTR")

    # Test connection
    try:
        await scope.connect()
        assert scope.connected is True
        results.add_pass("DS1104: Connection")
    except Exception as e:
        results.add_fail("DS1104: Connection", e)

    # Test get_info
    try:
        info = await scope.get_info()
        assert info.model == "DS1104Z"
        assert info.manufacturer == "RIGOL TECHNOLOGIES"
        results.add_pass("DS1104: Get Info")
    except Exception as e:
        results.add_fail("DS1104: Get Info", e)

    # Test get_status
    try:
        status = await scope.get_status()
        assert status.connected is True
        assert status.capabilities["num_channels"] == 4
        results.add_pass("DS1104: Get Status")
    except Exception as e:
        results.add_fail("DS1104: Get Status", e)

    # Test set_timebase
    try:
        await scope.set_timebase(scale=0.001, offset=0.0)
        results.add_pass("DS1104: Set Timebase")
    except Exception as e:
        results.add_fail("DS1104: Set Timebase", e)

    # Test trigger commands
    try:
        await scope.trigger_run()
        await scope.trigger_stop()
        results.add_pass("DS1104: Trigger Commands")
    except Exception as e:
        results.add_fail("DS1104: Trigger Commands", e)

    # Test disconnect
    try:
        await scope.disconnect()
        assert scope.connected is False
        results.add_pass("DS1104: Disconnect")
    except Exception as e:
        results.add_fail("DS1104: Disconnect", e)


async def test_rigol_dl3021a(results):
    """Test Rigol DL3021A electronic load driver."""
    print("\nTesting Rigol DL3021A Electronic Load...")

    idn = "RIGOL TECHNOLOGIES,DL3021A,DL3A123456789,00.01.03"
    mock_inst = create_mock_instrument(idn)
    mock_rm = create_mock_resource_manager(mock_inst)

    load = RigolDL3021A(mock_rm, "USB0::0x1AB1::0x0C1C::DL3A123456789::INSTR")

    # Test connection
    try:
        await load.connect()
        assert load.connected is True
        results.add_pass("DL3021A: Connection")
    except Exception as e:
        results.add_fail("DL3021A: Connection", e)

    # Test get_info
    try:
        info = await load.get_info()
        assert info.model == "DL3021A"
        assert info.manufacturer == "RIGOL TECHNOLOGIES"
        results.add_pass("DL3021A: Get Info")
    except Exception as e:
        results.add_fail("DL3021A: Get Info", e)

    # Test get_status
    try:
        status = await load.get_status()
        assert status.capabilities["max_current"] == 40.0
        assert status.capabilities["max_power"] == 200.0
        results.add_pass("DL3021A: Get Status")
    except Exception as e:
        results.add_fail("DL3021A: Get Status", e)

    # Test set_mode
    try:
        await load.set_mode("CC")
        await load.set_mode("CV")
        results.add_pass("DL3021A: Set Mode")
    except Exception as e:
        results.add_fail("DL3021A: Set Mode", e)

    # Test set_current
    try:
        await load.set_current(10.0)
        results.add_pass("DL3021A: Set Current")
    except Exception as e:
        results.add_fail("DL3021A: Set Current", e)

    # Test set_input
    try:
        await load.set_input(True)
        await load.set_input(False)
        results.add_pass("DL3021A: Set Input")
    except Exception as e:
        results.add_fail("DL3021A: Set Input", e)

    # Test disconnect
    try:
        await load.disconnect()
        results.add_pass("DL3021A: Disconnect")
    except Exception as e:
        results.add_fail("DL3021A: Disconnect", e)


async def test_bk9205b(results):
    """Test BK Precision 9205B power supply driver."""
    print("\nTesting BK Precision 9205B Power Supply...")

    idn = "BK Precision,9205B,123456,V1.0"
    mock_inst = create_mock_instrument(idn)
    mock_rm = create_mock_resource_manager(mock_inst)

    ps = BK9205B(mock_rm, "USB0::0xFFFF::0x9205::123456::INSTR")

    # Test connection
    try:
        await ps.connect()
        assert ps.connected is True
        results.add_pass("BK9205B: Connection")
    except Exception as e:
        results.add_fail("BK9205B: Connection", e)

    # Test get_info
    try:
        info = await ps.get_info()
        assert info.model == "9205B"
        results.add_pass("BK9205B: Get Info")
    except Exception as e:
        results.add_fail("BK9205B: Get Info", e)

    # Test get_status
    try:
        status = await ps.get_status()
        assert status.capabilities["max_voltage"] == 120.0
        assert status.capabilities["max_current"] == 10.0
        results.add_pass("BK9205B: Get Status")
    except Exception as e:
        results.add_fail("BK9205B: Get Status", e)

    # Test set_voltage
    try:
        await ps.set_voltage(12.0)
        results.add_pass("BK9205B: Set Voltage")
    except Exception as e:
        results.add_fail("BK9205B: Set Voltage", e)

    # Test set_current
    try:
        await ps.set_current(5.0)
        results.add_pass("BK9205B: Set Current")
    except Exception as e:
        results.add_fail("BK9205B: Set Current", e)

    # Test set_output
    try:
        await ps.set_output(True)
        await ps.set_output(False)
        results.add_pass("BK9205B: Set Output")
    except Exception as e:
        results.add_fail("BK9205B: Set Output", e)

    # Test disconnect
    try:
        await ps.disconnect()
        results.add_pass("BK9205B: Disconnect")
    except Exception as e:
        results.add_fail("BK9205B: Disconnect", e)


async def test_bk1685b(results):
    """Test BK Precision 1685B power supply driver."""
    print("\nTesting BK Precision 1685B Power Supply...")

    idn = "BK Precision,1685B,123456,V2.1"
    mock_inst = create_mock_instrument(idn)
    mock_rm = create_mock_resource_manager(mock_inst)

    ps = BK1685B(mock_rm, "USB0::0xFFFF::0x1685::123456::INSTR")

    # Test connection
    try:
        await ps.connect()
        assert ps.connected is True
        results.add_pass("BK1685B: Connection")
    except Exception as e:
        results.add_fail("BK1685B: Connection", e)

    # Test get_info
    try:
        info = await ps.get_info()
        assert info.model == "1685B"
        results.add_pass("BK1685B: Get Info")
    except Exception as e:
        results.add_fail("BK1685B: Get Info", e)

    # Test get_status
    try:
        status = await ps.get_status()
        assert status.capabilities["max_voltage"] == 18.0
        assert status.capabilities["max_current"] == 5.0
        results.add_pass("BK1685B: Get Status")
    except Exception as e:
        results.add_fail("BK1685B: Get Status", e)

    # Test set_voltage
    try:
        await ps.set_voltage(15.0)
        results.add_pass("BK1685B: Set Voltage")
    except Exception as e:
        results.add_fail("BK1685B: Set Voltage", e)

    # Test set_current
    try:
        await ps.set_current(3.0)
        results.add_pass("BK1685B: Set Current")
    except Exception as e:
        results.add_fail("BK1685B: Set Current", e)

    # Test disconnect
    try:
        await ps.disconnect()
        results.add_pass("BK1685B: Disconnect")
    except Exception as e:
        results.add_fail("BK1685B: Disconnect", e)


async def main():
    """Run all tests."""
    print("="*60)
    print("LabLink New Equipment Driver Test Suite")
    print("="*60)

    results = TestResults()

    await test_rigol_ds1104(results)
    await test_rigol_dl3021a(results)
    await test_bk9205b(results)
    await test_bk1685b(results)

    success = results.summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
