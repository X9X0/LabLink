"""Tests for BK Precision power supply drivers (9205B and 1685B)."""

import pytest
from unittest.mock import MagicMock, patch
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
        responses = {
            "*IDN?": "BK Precision,9205B,123456,V1.0",
            "MEAS:VOLT?": "12.05",
            "MEAS:CURR?": "2.50",
            "VOLT?": "12.00",
            "CURR?": "5.00",
            "OUTP?": "1",
            "SYST:ERR?": '0,"No error"',
        }
        mock_instrument.query.side_effect = lambda cmd, *a, **k: responses[cmd]

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
        # The 1685B does not support *IDN?, so the driver reports no serial.
        assert info.serial_number is None
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
        # GETD: VVVV(/100) IIII(/100) mode  -> 5.02 V, 12.50 A, CV.
        # Both reading fields are two decimals, per the worked example in the
        # 1685B/1900B manuals (030201450 = 3.02 V, 1.45 A).
        # GOUT: "0" means output ON (the protocol inverts this)
        # GETS on a 1685B: VVV(/10) CCC(/100) -> 5.0 V, 0.20 A setpoints
        bk_responses = {
            "GETD": "050212500",
            "GOUT": "0",
            "GETS": "050020",
        }

        async def fake_bk_query(command):
            return bk_responses[command]

        await power_supply.connect()
        with patch.object(power_supply, "_bk_query", side_effect=fake_bk_query):
            readings = await power_supply.get_readings()

        assert readings.voltage_actual == 5.02
        assert readings.current_actual == 12.50
        assert readings.output_enabled is True
        assert readings.voltage_set == 5.00
        assert readings.current_set == 0.20

    @pytest.mark.asyncio
    async def test_cv_cc_mode_detection(self, power_supply, mock_instrument):
        """Test CV/CC mode detection."""
        mock_instrument.query.return_value = "BK Precision,1685B,123456,V2.1"

        await power_supply.connect()

        # The 1685B reports CV/CC in the GETD mode byte (0 = CV, 1 = CC)
        # rather than through SCPI queries.
        async def bk_query_with_mode(mode_digit):
            async def _query(command):
                return {
                    "GETD": f"05001000{mode_digit}",
                    "GOUT": "0",
                    "GETS": "050030",
                }[command]

            return _query

        # Test CV mode
        with patch.object(
            power_supply, "_bk_query", side_effect=await bk_query_with_mode("0")
        ):
            readings = await power_supply.get_readings()
        assert readings.in_cv_mode is True
        assert readings.in_cc_mode is False

        # Test CC mode
        with patch.object(
            power_supply, "_bk_query", side_effect=await bk_query_with_mode("1")
        ):
            readings = await power_supply.get_readings()
        assert readings.in_cc_mode is True
        assert readings.in_cv_mode is False
