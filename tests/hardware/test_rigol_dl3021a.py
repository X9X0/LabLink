"""Tests for Rigol DL3021A electronic load driver."""

import pytest
from unittest.mock import MagicMock
import sys
sys.path.append("..")
from equipment.rigol_electronic_load import RigolDL3021A


class TestRigolDL3021A:
    """Test suite for Rigol DL3021A electronic load."""

    @pytest.fixture
    def load(self, mock_resource_manager_with_instrument):
        """Create a Rigol DL3021A instance."""
        return RigolDL3021A(
            mock_resource_manager_with_instrument,
            "USB0::0x1AB1::0x0C1C::DL3A123456789::INSTR"
        )

    @pytest.mark.asyncio
    async def test_connect(self, load, mock_instrument):
        """Test connecting to the electronic load."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DL3021A,DL3A123456789,00.01.03"

        await load.connect()

        assert load.connected is True
        assert load.instrument is not None
        mock_instrument.query.assert_called()

    @pytest.mark.asyncio
    async def test_disconnect(self, load, mock_instrument):
        """Test disconnecting from the electronic load."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DL3021A,DL3A123456789,00.01.03"

        await load.connect()
        await load.disconnect()

        assert load.connected is False
        mock_instrument.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_info(self, load, mock_instrument):
        """Test getting equipment information."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DL3021A,DL3A123456789,00.01.03"

        await load.connect()
        info = await load.get_info()

        assert info.manufacturer == "RIGOL TECHNOLOGIES"
        assert info.model == "DL3021A"
        assert info.serial_number == "DL3A123456789"
        assert "load_" in info.id

    @pytest.mark.asyncio
    async def test_get_status(self, load, mock_instrument):
        """Test getting electronic load status."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DL3021A,DL3A123456789,00.01.03"

        await load.connect()
        status = await load.get_status()

        assert status.connected is True
        assert status.firmware_version == "00.01.03"
        assert status.capabilities["max_voltage"] == 150.0
        assert status.capabilities["max_current"] == 40.0
        assert status.capabilities["max_power"] == 200.0
        assert "CC" in status.capabilities["modes"]

    @pytest.mark.asyncio
    async def test_set_mode(self, load, mock_instrument):
        """Test setting operating mode."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DL3021A,DL3A123456789,00.01.03"

        await load.connect()

        # Test valid modes
        await load.set_mode("CC")
        await load.set_mode("CV")
        await load.set_mode("CR")
        await load.set_mode("CP")

        assert mock_instrument.write.call_count >= 4

    @pytest.mark.asyncio
    async def test_set_mode_invalid(self, load, mock_instrument):
        """Test that invalid modes raise errors."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DL3021A,DL3A123456789,00.01.03"

        await load.connect()

        with pytest.raises(ValueError):
            await load.set_mode("INVALID")

    @pytest.mark.asyncio
    async def test_set_current(self, load, mock_instrument):
        """Test setting current."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DL3021A,DL3A123456789,00.01.03"

        await load.connect()
        await load.set_current(10.0)

        mock_instrument.write.assert_called()

        # Test out of range
        with pytest.raises(ValueError):
            await load.set_current(50.0)  # Max is 40A

        with pytest.raises(ValueError):
            await load.set_current(-1.0)

    @pytest.mark.asyncio
    async def test_set_voltage(self, load, mock_instrument):
        """Test setting voltage."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DL3021A,DL3A123456789,00.01.03"

        await load.connect()
        await load.set_voltage(50.0)

        mock_instrument.write.assert_called()

        # Test out of range
        with pytest.raises(ValueError):
            await load.set_voltage(200.0)  # Max is 150V

        with pytest.raises(ValueError):
            await load.set_voltage(-1.0)

    @pytest.mark.asyncio
    async def test_set_resistance(self, load, mock_instrument):
        """Test setting resistance."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DL3021A,DL3A123456789,00.01.03"

        await load.connect()
        await load.set_resistance(100.0)

        mock_instrument.write.assert_called()

        # Test invalid value
        with pytest.raises(ValueError):
            await load.set_resistance(0.0)

        with pytest.raises(ValueError):
            await load.set_resistance(-10.0)

    @pytest.mark.asyncio
    async def test_set_power(self, load, mock_instrument):
        """Test setting power."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DL3021A,DL3A123456789,00.01.03"

        await load.connect()
        await load.set_power(100.0)

        mock_instrument.write.assert_called()

        # Test out of range
        with pytest.raises(ValueError):
            await load.set_power(300.0)  # Max is 200W

        with pytest.raises(ValueError):
            await load.set_power(-1.0)

    @pytest.mark.asyncio
    async def test_set_input(self, load, mock_instrument):
        """Test enabling/disabling input."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DL3021A,DL3A123456789,00.01.03"

        await load.connect()

        await load.set_input(True)
        await load.set_input(False)

        assert mock_instrument.write.call_count >= 2

    @pytest.mark.asyncio
    async def test_get_readings(self, load, mock_instrument):
        """Test getting readings from the load."""
        mock_instrument.query.side_effect = [
            "RIGOL TECHNOLOGIES,DL3021A,DL3A123456789,00.01.03",  # IDN for connect
            "RIGOL TECHNOLOGIES,DL3021A,DL3A123456789,00.01.03",  # IDN for get_info
            "CC",      # Mode
            "5.0",     # Current setpoint
            "12.5",    # Voltage measurement
            "5.0",     # Current measurement
            "62.5",    # Power measurement
            "ON"       # Input state
        ]

        await load.connect()
        readings = await load.get_readings()

        assert readings.mode == "CC"
        assert readings.setpoint == 5.0
        assert readings.voltage == 12.5
        assert readings.current == 5.0
        assert readings.power == 62.5
        assert readings.load_enabled is True

    @pytest.mark.asyncio
    async def test_get_readings_different_modes(self, load, mock_instrument):
        """Test getting readings in different operating modes."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DL3021A,DL3A123456789,00.01.03"

        await load.connect()

        # Test CV mode
        mock_instrument.query.side_effect = [
            "CV", "12.0", "12.0", "5.0", "60.0", "ON"
        ]
        readings = await load.get_readings()
        assert readings.mode == "CV"

        # Test CR mode
        mock_instrument.query.side_effect = [
            "CR", "10.0", "12.0", "1.2", "14.4", "ON"
        ]
        readings = await load.get_readings()
        assert readings.mode == "CR"

        # Test CP mode
        mock_instrument.query.side_effect = [
            "CP", "50.0", "12.0", "4.17", "50.0", "ON"
        ]
        readings = await load.get_readings()
        assert readings.mode == "CP"

    @pytest.mark.asyncio
    async def test_execute_command(self, load, mock_instrument):
        """Test execute_command dispatcher."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DL3021A,DL3A123456789,00.01.03"

        await load.connect()

        # Test valid commands
        await load.execute_command("set_mode", {"mode": "CC"})
        await load.execute_command("set_current", {"current": 10.0})
        await load.execute_command("set_input", {"enabled": True})

        # Test invalid command
        with pytest.raises(ValueError):
            await load.execute_command("invalid_command", {})
