"""Tests for BK Precision power supply drivers (9205B and 1685B)."""

import pytest
from unittest.mock import MagicMock
import sys
sys.path.append("..")
from equipment.bk_power_supply import BK9205B, BK1685B


class TestBK9205B:
    """Test suite for BK Precision 9205B power supply."""

    @pytest.fixture
    def power_supply(self, mock_resource_manager_with_instrument):
        """Create a BK 9205B instance."""
        return BK9205B(
            mock_resource_manager_with_instrument,
            "USB0::0xFFFF::0x9205::123456::INSTR"
        )

    @pytest.mark.asyncio
    async def test_connect(self, power_supply, mock_instrument):
        """Test connecting to the power supply."""
        mock_instrument.query.return_value = "BK Precision,9205B,123456,V1.0"

        await power_supply.connect()

        assert power_supply.connected is True
        assert power_supply.instrument is not None
        mock_instrument.query.assert_called()

    @pytest.mark.asyncio
    async def test_disconnect(self, power_supply, mock_instrument):
        """Test disconnecting from the power supply."""
        mock_instrument.query.return_value = "BK Precision,9205B,123456,V1.0"

        await power_supply.connect()
        await power_supply.disconnect()

        assert power_supply.connected is False
        mock_instrument.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_info(self, power_supply, mock_instrument):
        """Test getting equipment information."""
        mock_instrument.query.return_value = "BK Precision,9205B,123456,V1.0"

        await power_supply.connect()
        info = await power_supply.get_info()

        assert info.manufacturer == "BK Precision"
        assert info.model == "9205B"
        assert info.serial_number == "123456"
        assert "ps_" in info.id

    @pytest.mark.asyncio
    async def test_get_status(self, power_supply, mock_instrument):
        """Test getting power supply status."""
        mock_instrument.query.return_value = "BK Precision,9205B,123456,V1.0"

        await power_supply.connect()
        status = await power_supply.get_status()

        assert status.connected is True
        assert status.firmware_version == "V1.0"
        assert status.capabilities["max_voltage"] == 120.0
        assert status.capabilities["max_current"] == 10.0
        assert status.capabilities["num_channels"] == 1

    @pytest.mark.asyncio
    async def test_set_voltage(self, power_supply, mock_instrument):
        """Test setting voltage."""
        mock_instrument.query.return_value = "BK Precision,9205B,123456,V1.0"

        await power_supply.connect()
        await power_supply.set_voltage(12.0)

        mock_instrument.write.assert_called()

        # Test out of range
        with pytest.raises(ValueError):
            await power_supply.set_voltage(150.0)  # Max is 120V

        with pytest.raises(ValueError):
            await power_supply.set_voltage(-1.0)

    @pytest.mark.asyncio
    async def test_set_current(self, power_supply, mock_instrument):
        """Test setting current limit."""
        mock_instrument.query.return_value = "BK Precision,9205B,123456,V1.0"

        await power_supply.connect()
        await power_supply.set_current(5.0)

        mock_instrument.write.assert_called()

        # Test out of range
        with pytest.raises(ValueError):
            await power_supply.set_current(15.0)  # Max is 10A

        with pytest.raises(ValueError):
            await power_supply.set_current(-1.0)

    @pytest.mark.asyncio
    async def test_set_output(self, power_supply, mock_instrument):
        """Test enabling/disabling output."""
        mock_instrument.query.return_value = "BK Precision,9205B,123456,V1.0"

        await power_supply.connect()

        await power_supply.set_output(True)
        await power_supply.set_output(False)

        assert mock_instrument.write.call_count >= 2

    @pytest.mark.asyncio
    async def test_get_readings(self, power_supply, mock_instrument):
        """Test getting readings from the power supply."""
        mock_instrument.query.side_effect = [
            "BK Precision,9205B,123456,V1.0",  # IDN for connect
            "BK Precision,9205B,123456,V1.0",  # IDN for get_info
            "12.05",  # Measured voltage
            "2.50",   # Measured current
            "1",      # Output state (ON)
            "12.00",  # Voltage setpoint
            "5.00"    # Current setpoint
        ]

        await power_supply.connect()
        readings = await power_supply.get_readings()

        assert readings.voltage_actual == 12.05
        assert readings.current_actual == 2.50
        assert readings.output_enabled is True
        assert readings.voltage_set == 12.00
        assert readings.current_set == 5.00

    @pytest.mark.asyncio
    async def test_execute_command(self, power_supply, mock_instrument):
        """Test execute_command dispatcher."""
        mock_instrument.query.return_value = "BK Precision,9205B,123456,V1.0"

        await power_supply.connect()

        # Test valid commands
        await power_supply.execute_command("set_voltage", {"voltage": 12.0})
        await power_supply.execute_command("set_current", {"current": 5.0})
        await power_supply.execute_command("set_output", {"enabled": True})

        # Test invalid command
        with pytest.raises(ValueError):
            await power_supply.execute_command("invalid_command", {})


class TestBK1685B:
    """Test suite for BK Precision 1685B power supply."""

    @pytest.fixture
    def power_supply(self, mock_resource_manager_with_instrument):
        """Create a BK 1685B instance."""
        return BK1685B(
            mock_resource_manager_with_instrument,
            "USB0::0xFFFF::0x1685::123456::INSTR"
        )

    @pytest.mark.asyncio
    async def test_connect(self, power_supply, mock_instrument):
        """Test connecting to the power supply."""
        mock_instrument.query.return_value = "BK Precision,1685B,123456,V2.1"

        await power_supply.connect()

        assert power_supply.connected is True
        assert power_supply.instrument is not None

    @pytest.mark.asyncio
    async def test_get_info(self, power_supply, mock_instrument):
        """Test getting equipment information."""
        mock_instrument.query.return_value = "BK Precision,1685B,123456,V2.1"

        await power_supply.connect()
        info = await power_supply.get_info()

        assert info.manufacturer == "BK Precision"
        assert info.model == "1685B"
        assert info.serial_number == "123456"
        assert "ps_" in info.id

    @pytest.mark.asyncio
    async def test_get_status(self, power_supply, mock_instrument):
        """Test getting power supply status."""
        mock_instrument.query.return_value = "BK Precision,1685B,123456,V2.1"

        await power_supply.connect()
        status = await power_supply.get_status()

        assert status.connected is True
        assert status.firmware_version == "V2.1"
        assert status.capabilities["max_voltage"] == 18.0
        assert status.capabilities["max_current"] == 5.0
        assert status.capabilities["num_channels"] == 1

    @pytest.mark.asyncio
    async def test_set_voltage(self, power_supply, mock_instrument):
        """Test setting voltage."""
        mock_instrument.query.return_value = "BK Precision,1685B,123456,V2.1"

        await power_supply.connect()
        await power_supply.set_voltage(15.0)

        mock_instrument.write.assert_called()

        # Test out of range
        with pytest.raises(ValueError):
            await power_supply.set_voltage(20.0)  # Max is 18V

        with pytest.raises(ValueError):
            await power_supply.set_voltage(-1.0)

    @pytest.mark.asyncio
    async def test_set_current(self, power_supply, mock_instrument):
        """Test setting current limit."""
        mock_instrument.query.return_value = "BK Precision,1685B,123456,V2.1"

        await power_supply.connect()
        await power_supply.set_current(3.0)

        mock_instrument.write.assert_called()

        # Test out of range
        with pytest.raises(ValueError):
            await power_supply.set_current(6.0)  # Max is 5A

        with pytest.raises(ValueError):
            await power_supply.set_current(-1.0)

    @pytest.mark.asyncio
    async def test_get_readings(self, power_supply, mock_instrument):
        """Test getting readings from the power supply."""
        mock_instrument.query.side_effect = [
            "BK Precision,1685B,123456,V2.1",  # IDN for connect
            "BK Precision,1685B,123456,V2.1",  # IDN for get_info
            "5.02",   # Measured voltage
            "1.25",   # Measured current
            "ON",     # Output state
            "5.00",   # Voltage setpoint
            "2.00"    # Current setpoint
        ]

        await power_supply.connect()
        readings = await power_supply.get_readings()

        assert readings.voltage_actual == 5.02
        assert readings.current_actual == 1.25
        assert readings.output_enabled is True
        assert readings.voltage_set == 5.00
        assert readings.current_set == 2.00

    @pytest.mark.asyncio
    async def test_cv_cc_mode_detection(self, power_supply, mock_instrument):
        """Test CV/CC mode detection."""
        mock_instrument.query.return_value = "BK Precision,1685B,123456,V2.1"

        await power_supply.connect()

        # Test CV mode (current well below limit)
        mock_instrument.query.side_effect = [
            "5.00",   # Measured voltage
            "1.00",   # Measured current (well below limit)
            "ON",     # Output state
            "5.00",   # Voltage setpoint
            "3.00"    # Current setpoint
        ]
        readings = await power_supply.get_readings()
        assert readings.in_cv_mode is True
        assert readings.in_cc_mode is False

        # Test CC mode (current at limit)
        mock_instrument.query.side_effect = [
            "4.50",   # Measured voltage
            "3.00",   # Measured current (at limit)
            "ON",     # Output state
            "5.00",   # Voltage setpoint
            "3.00"    # Current setpoint
        ]
        readings = await power_supply.get_readings()
        assert readings.in_cc_mode is True
        assert readings.in_cv_mode is False
