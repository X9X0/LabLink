"""Tests for Rigol DS1104 oscilloscope driver."""

import pytest
from unittest.mock import MagicMock
import sys
sys.path.append("..")
from equipment.rigol_scope import RigolDS1104


class TestRigolDS1104:
    """Test suite for Rigol DS1104 oscilloscope."""

    @pytest.fixture
    def scope(self, mock_resource_manager_with_instrument):
        """Create a Rigol DS1104 instance."""
        return RigolDS1104(
            mock_resource_manager_with_instrument,
            "USB0::0x1AB1::0x0588::DS1ZA123456789::INSTR"
        )

    @pytest.mark.asyncio
    async def test_connect(self, scope, mock_instrument):
        """Test connecting to the oscilloscope."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DS1104Z,DS1ZA123456789,00.04.04.SP3"

        await scope.connect()

        assert scope.connected is True
        assert scope.instrument is not None
        mock_instrument.query.assert_called()

    @pytest.mark.asyncio
    async def test_disconnect(self, scope, mock_instrument):
        """Test disconnecting from the oscilloscope."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DS1104Z,DS1ZA123456789,00.04.04.SP3"

        await scope.connect()
        await scope.disconnect()

        assert scope.connected is False
        mock_instrument.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_info(self, scope, mock_instrument):
        """Test getting equipment information."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DS1104Z,DS1ZA123456789,00.04.04.SP3"

        await scope.connect()
        info = await scope.get_info()

        assert info.manufacturer == "RIGOL TECHNOLOGIES"
        assert info.model == "DS1104Z"
        assert info.serial_number == "DS1ZA123456789"
        assert "scope_" in info.id

    @pytest.mark.asyncio
    async def test_get_status(self, scope, mock_instrument):
        """Test getting oscilloscope status."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DS1104Z,DS1ZA123456789,00.04.04.SP3"

        await scope.connect()
        status = await scope.get_status()

        assert status.connected is True
        assert status.firmware_version == "00.04.04.SP3"
        assert status.capabilities["num_channels"] == 4
        assert status.capabilities["bandwidth"] == "100MHz"

    @pytest.mark.asyncio
    async def test_set_timebase(self, scope, mock_instrument):
        """Test setting timebase."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DS1104Z,DS1ZA123456789,00.04.04.SP3"

        await scope.connect()
        await scope.set_timebase(scale=0.001, offset=0.0)

        assert mock_instrument.write.call_count >= 2

    @pytest.mark.asyncio
    async def test_set_channel(self, scope, mock_instrument):
        """Test setting channel configuration."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DS1104Z,DS1ZA123456789,00.04.04.SP3"

        await scope.connect()
        await scope.set_channel(channel=1, enabled=True, scale=1.0, offset=0.0, coupling="DC")

        assert mock_instrument.write.call_count >= 4

    @pytest.mark.asyncio
    async def test_trigger_commands(self, scope, mock_instrument):
        """Test trigger commands."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DS1104Z,DS1ZA123456789,00.04.04.SP3"

        await scope.connect()

        await scope.trigger_single()
        await scope.trigger_run()
        await scope.trigger_stop()

        assert mock_instrument.write.call_count >= 3

    @pytest.mark.asyncio
    async def test_autoscale(self, scope, mock_instrument):
        """Test autoscale command."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DS1104Z,DS1ZA123456789,00.04.04.SP3"

        await scope.connect()
        await scope.autoscale()

        mock_instrument.write.assert_called()

    @pytest.mark.asyncio
    async def test_get_measurements(self, scope, mock_instrument):
        """Test getting measurements."""
        mock_instrument.query.side_effect = [
            "RIGOL TECHNOLOGIES,DS1104Z,DS1ZA123456789,00.04.04.SP3",  # IDN for connect
            "RIGOL TECHNOLOGIES,DS1104Z,DS1ZA123456789,00.04.04.SP3",  # IDN for get_info
            "3.3",    # VPP
            "5.0",    # VMAX
            "-1.7",   # VMIN
            "1.65",   # VAVG
            "2.3",    # VRMS
            "1000.0", # FREQ
            "0.001"   # PERIOD
        ]

        await scope.connect()
        measurements = await scope.get_measurements(channel=1)

        assert measurements["vpp"] == 3.3
        assert measurements["vmax"] == 5.0
        assert measurements["vmin"] == -1.7
        assert measurements["freq"] == 1000.0

    @pytest.mark.asyncio
    async def test_get_waveform(self, scope, mock_instrument):
        """Test getting waveform data."""
        mock_instrument.query.side_effect = [
            "RIGOL TECHNOLOGIES,DS1104Z,DS1ZA123456789,00.04.04.SP3",  # IDN for connect
            "RIGOL TECHNOLOGIES,DS1104Z,DS1ZA123456789,00.04.04.SP3",  # IDN for get_info
            "0,0,1200,1,4.0e-09,0.0,0,0.04,0.0,127",  # Preamble
            "0.001",   # Time scale
            "1.0",     # Voltage scale
            "0.0"      # Voltage offset
        ]

        await scope.connect()
        waveform = await scope.get_waveform(channel=1)

        assert waveform.channel == 1
        assert waveform.num_samples == 1200
        assert "waveform_" in waveform.data_id

    @pytest.mark.asyncio
    async def test_invalid_channel(self, scope, mock_instrument):
        """Test that invalid channel numbers raise errors."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DS1104Z,DS1ZA123456789,00.04.04.SP3"

        await scope.connect()

        with pytest.raises(ValueError):
            await scope.get_waveform(channel=5)  # DS1104 has only 4 channels

        with pytest.raises(ValueError):
            await scope.get_measurements(channel=0)

    @pytest.mark.asyncio
    async def test_execute_command(self, scope, mock_instrument):
        """Test execute_command dispatcher."""
        mock_instrument.query.return_value = "RIGOL TECHNOLOGIES,DS1104Z,DS1ZA123456789,00.04.04.SP3"

        await scope.connect()

        # Test valid commands
        await scope.execute_command("trigger_run", {})
        await scope.execute_command("autoscale", {})

        # Test invalid command
        with pytest.raises(ValueError):
            await scope.execute_command("invalid_command", {})
