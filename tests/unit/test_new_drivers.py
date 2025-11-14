#!/usr/bin/env python3
"""
Unit tests for new equipment drivers.
Tests equipment driver functionality with mocks.
"""

import sys
import asyncio
import pytest
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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rigol_ds1104():
    """Test Rigol DS1104 oscilloscope driver."""
    from unittest.mock import patch

    idn = "RIGOL TECHNOLOGIES,DS1104Z,DS1ZA123456789,00.04.04.SP3"
    mock_inst = create_mock_instrument(idn)
    mock_rm = create_mock_resource_manager(mock_inst)

    scope = RigolDS1104(mock_rm, "USB0::0x1AB1::0x0588::DS1ZA123456789::INSTR")

    # Patch the async query/write methods to avoid connection issues
    with patch.object(scope, '_query', new_callable=AsyncMock) as mock_query, \
         patch.object(scope, '_write', new_callable=AsyncMock) as mock_write:

        # Configure mock_query to return appropriate values
        mock_query.return_value = idn

        # Test connection
        await scope.connect()
        assert scope.connected is True

        # Test get_info
        info = await scope.get_info()
        assert info.model == "DS1104Z"
        assert info.manufacturer == "RIGOL TECHNOLOGIES"

        # Test get_status
        status = await scope.get_status()
        assert status.connected is True
        assert status.capabilities["num_channels"] == 4

        # Test set_timebase
        await scope.set_timebase(scale=0.001, offset=0.0)
        mock_write.assert_called()

        # Test trigger commands
        await scope.trigger_run()
        await scope.trigger_stop()

        # Test disconnect
        await scope.disconnect()
        assert scope.connected is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rigol_dl3021a():
    """Test Rigol DL3021A electronic load driver."""
    from unittest.mock import patch

    idn = "RIGOL TECHNOLOGIES,DL3021A,DL3A123456789,00.01.03"
    mock_inst = create_mock_instrument(idn)
    mock_rm = create_mock_resource_manager(mock_inst)

    load = RigolDL3021A(mock_rm, "USB0::0x1AB1::0x0C1C::DL3A123456789::INSTR")

    # Patch the async query/write methods
    with patch.object(load, '_query', new_callable=AsyncMock) as mock_query, \
         patch.object(load, '_write', new_callable=AsyncMock):

        mock_query.return_value = idn

        # Test connection
        await load.connect()
        assert load.connected is True

        # Test get_info
        info = await load.get_info()
        assert info.model == "DL3021A"
        assert info.manufacturer == "RIGOL TECHNOLOGIES"

        # Test get_status
        status = await load.get_status()
        assert status.capabilities["max_current"] == 40.0
        assert status.capabilities["max_power"] == 200.0

        # Test set_mode
        await load.set_mode("CC")
        await load.set_mode("CV")

        # Test set_current
        await load.set_current(10.0)

        # Test set_input
        await load.set_input(True)
        await load.set_input(False)

        # Test disconnect
        await load.disconnect()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bk9205b():
    """Test BK Precision 9205B power supply driver."""
    from unittest.mock import patch

    idn = "BK Precision,9205B,123456,V1.0"
    mock_inst = create_mock_instrument(idn)
    mock_rm = create_mock_resource_manager(mock_inst)

    ps = BK9205B(mock_rm, "USB0::0xFFFF::0x9205::123456::INSTR")

    # Patch the async query/write methods
    with patch.object(ps, '_query', new_callable=AsyncMock) as mock_query, \
         patch.object(ps, '_write', new_callable=AsyncMock):

        mock_query.return_value = idn

        # Test connection
        await ps.connect()
        assert ps.connected is True

        # Test get_info
        info = await ps.get_info()
        assert info.model == "9205B"

        # Test get_status
        status = await ps.get_status()
        assert status.capabilities["max_voltage"] == 120.0
        assert status.capabilities["max_current"] == 10.0

        # Test set_voltage
        await ps.set_voltage(12.0)

        # Test set_current
        await ps.set_current(5.0)

        # Test set_output
        await ps.set_output(True)
        await ps.set_output(False)

        # Test disconnect
        await ps.disconnect()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bk1685b():
    """Test BK Precision 1685B power supply driver."""
    from unittest.mock import patch

    idn = "BK Precision,1685B,123456,V2.1"
    mock_inst = create_mock_instrument(idn)
    mock_rm = create_mock_resource_manager(mock_inst)

    ps = BK1685B(mock_rm, "USB0::0xFFFF::0x1685::123456::INSTR")

    # Patch the async query/write methods
    with patch.object(ps, '_query', new_callable=AsyncMock) as mock_query, \
         patch.object(ps, '_write', new_callable=AsyncMock):

        mock_query.return_value = idn

        # Test connection
        await ps.connect()
        assert ps.connected is True

        # Test get_info
        info = await ps.get_info()
        assert info.model == "1685B"

        # Test get_status
        status = await ps.get_status()
        assert status.capabilities["max_voltage"] == 18.0
        assert status.capabilities["max_current"] == 5.0

        # Test set_voltage
        await ps.set_voltage(15.0)

        # Test set_current
        await ps.set_current(3.0)

        # Test disconnect
        await ps.disconnect()


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
