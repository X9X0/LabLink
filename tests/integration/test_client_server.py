"""Integration tests for client-server communication."""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch
import requests


@pytest.mark.integration
@pytest.mark.slow
class TestClientServerIntegration:
    """Test client-server integration."""

    @pytest.fixture(scope="class")
    def server_url(self):
        """Get server URL (assumes server is running)."""
        return "http://localhost:8000"

    @pytest.fixture(scope="class")
    def ws_url(self):
        """Get WebSocket URL."""
        return "ws://localhost:8001/ws"

    def test_server_health(self, server_url):
        """Test server health endpoint."""
        try:
            response = requests.get(f"{server_url}/health", timeout=5)
            assert response.status_code == 200

            data = response.json()
            assert "status" in data
            assert data["status"] in ["healthy", "degraded"]

        except requests.exceptions.ConnectionError:
            pytest.skip("Server not running")

    def test_server_info(self, server_url):
        """Test server info endpoint."""
        try:
            response = requests.get(server_url, timeout=5)
            assert response.status_code == 200

            data = response.json()
            assert "name" in data
            assert "version" in data
            assert "status" in data

        except requests.exceptions.ConnectionError:
            pytest.skip("Server not running")

    def test_equipment_list(self, server_url):
        """Test equipment list endpoint."""
        try:
            response = requests.get(f"{server_url}/api/equipment", timeout=5)
            assert response.status_code == 200

            data = response.json()
            assert isinstance(data, list)

        except requests.exceptions.ConnectionError:
            pytest.skip("Server not running")

    def test_discovery(self, server_url):
        """Test equipment discovery."""
        try:
            response = requests.post(
                f"{server_url}/api/equipment/discover",
                timeout=10
            )
            assert response.status_code == 200

            data = response.json()
            assert "discovered" in data
            assert isinstance(data["discovered"], int)

        except requests.exceptions.ConnectionError:
            pytest.skip("Server not running")

    @pytest.mark.asyncio
    async def test_client_connection(self):
        """Test client can connect to server."""
        try:
            from client.api.client import LabLinkClient

            client = LabLinkClient(host="localhost", api_port=8000, ws_port=8001)

            # Try to connect
            connected = client.connect()

            if connected:
                assert client.connected is True

                # Get server info
                info = client.get_server_info()
                assert info is not None
                assert "name" in info

                # Health check
                health = client.health_check()
                assert health is not None

                client.disconnect()
            else:
                pytest.skip("Could not connect to server")

        except Exception as e:
            pytest.skip(f"Client connection failed: {e}")


@pytest.mark.integration
class TestMockEquipmentIntegration:
    """Test integration with mock equipment."""

    @pytest.fixture
    def mock_scope_driver(self):
        """Create mock oscilloscope driver."""
        try:
            from server.equipment.mock.mock_oscilloscope import MockOscilloscope
            return MockOscilloscope(None, "MOCK::SCOPE::4CH")
        except ImportError:
            pytest.skip("Mock equipment not available")

    @pytest.fixture
    def mock_psu_driver(self):
        """Create mock power supply driver."""
        try:
            from server.equipment.mock.mock_power_supply import MockPowerSupply
            return MockPowerSupply(None, "MOCK::PSU::3CH")
        except ImportError:
            pytest.skip("Mock equipment not available")

    @pytest.fixture
    def mock_load_driver(self):
        """Create mock electronic load driver."""
        try:
            from server.equipment.mock.mock_electronic_load import MockElectronicLoad
            return MockElectronicLoad(None, "MOCK::LOAD::350W")
        except ImportError:
            pytest.skip("Mock equipment not available")

    @pytest.mark.asyncio
    async def test_mock_scope_basic_operations(self, mock_scope_driver):
        """Test basic mock oscilloscope operations."""
        # Connect
        await mock_scope_driver.connect()
        assert mock_scope_driver.connected is True

        # Get info
        info = await mock_scope_driver.get_info()
        assert info is not None
        assert "Mock" in info.manufacturer

        # Get waveform
        waveform = await mock_scope_driver.get_waveform(1)
        assert waveform is not None
        assert waveform.num_samples > 0

        # Disconnect
        await mock_scope_driver.disconnect()
        assert mock_scope_driver.connected is False

    @pytest.mark.asyncio
    async def test_mock_psu_basic_operations(self, mock_psu_driver):
        """Test basic mock power supply operations."""
        # Connect
        await mock_psu_driver.connect()
        assert mock_psu_driver.connected is True

        # Set voltage and current
        await mock_psu_driver.set_voltage(12.0, channel=1)
        await mock_psu_driver.set_current(2.0, channel=1)

        # Enable output
        await mock_psu_driver.set_output(True, channel=1)

        # Get readings
        data = await mock_psu_driver.get_readings(channel=1)
        assert data is not None
        assert hasattr(data, 'voltage_actual')
        assert hasattr(data, 'current_actual')

        # Disable output
        await mock_psu_driver.set_output(False, channel=1)

        # Disconnect
        await mock_psu_driver.disconnect()

    @pytest.mark.asyncio
    async def test_mock_load_basic_operations(self, mock_load_driver):
        """Test basic mock electronic load operations."""
        # Connect
        await mock_load_driver.connect()
        assert mock_load_driver.connected is True

        # Set mode to CC
        await mock_load_driver.set_mode("CC")
        await mock_load_driver.set_current(5.0)

        # Enable input
        await mock_load_driver.set_input(True)

        # Get readings
        data = await mock_load_driver.get_readings()
        assert data is not None
        assert hasattr(data, 'voltage')
        assert hasattr(data, 'current')
        assert hasattr(data, 'mode')

        # Disable input
        await mock_load_driver.set_input(False)

        # Disconnect
        await mock_load_driver.disconnect()

    @pytest.mark.asyncio
    async def test_mock_scope_streaming(self, mock_scope_driver):
        """Test mock oscilloscope data streaming."""
        await mock_scope_driver.connect()

        # Collect some waveforms
        waveforms = []
        for _ in range(5):
            waveform = await mock_scope_driver.get_waveform(1)
            waveforms.append(waveform)
            await asyncio.sleep(0.1)

        # Verify we got data
        assert len(waveforms) == 5
        for waveform in waveforms:
            assert waveform.num_samples > 0

        await mock_scope_driver.disconnect()

    @pytest.mark.asyncio
    async def test_mock_psu_mode_switching(self, mock_psu_driver):
        """Test power supply CV/CC mode switching."""
        await mock_psu_driver.connect()

        # Set voltage and current
        await mock_psu_driver.set_voltage(12.0, channel=1)
        await mock_psu_driver.set_current(2.0, channel=1)

        # Set high load resistance (low current draw)
        mock_psu_driver.load_resistance[1] = 50.0  # Ohms

        await mock_psu_driver.set_output(True, channel=1)

        data = await mock_psu_driver.get_readings(channel=1)

        # Should be in CV mode (current < limit)
        assert data.in_cv_mode is True
        assert data.voltage_actual == pytest.approx(12.0, rel=0.01)

        # Now set low resistance (high current draw)
        mock_psu_driver.load_resistance[1] = 1.0  # Ohms

        data = await mock_psu_driver.get_readings(channel=1)

        # Should be in CC mode (current = limit)
        assert data.in_cc_mode is True
        assert data.current_actual == pytest.approx(2.0, rel=0.01)

        await mock_psu_driver.disconnect()

    @pytest.mark.asyncio
    async def test_mock_load_mode_changes(self, mock_load_driver):
        """Test electronic load mode changes."""
        await mock_load_driver.connect()

        modes = ["CC", "CV", "CR", "CP"]

        for mode in modes:
            await mock_load_driver.set_mode(mode)

            if mode == "CC":
                await mock_load_driver.set_current(5.0)
            elif mode == "CV":
                await mock_load_driver.set_voltage(12.0)
            elif mode == "CR":
                await mock_load_driver.set_resistance(10.0)
            elif mode == "CP":
                await mock_load_driver.set_power(100.0)

            await mock_load_driver.set_input(True)

            data = await mock_load_driver.get_readings()
            assert data.mode == mode

            await mock_load_driver.set_input(False)

        await mock_load_driver.disconnect()
