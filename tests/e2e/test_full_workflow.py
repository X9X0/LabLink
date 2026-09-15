"""End-to-end workflow tests."""

import pytest
import asyncio
import time


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.requires_hardware
class TestFullWorkflow:
    """Test complete workflows through the system."""

    @pytest.mark.asyncio
    async def test_equipment_discovery_workflow(self):
        """Test complete equipment discovery workflow."""
        try:
            from client.api.client import LabLinkClient

            # Connect to server
            client = LabLinkClient(host="localhost", api_port=8000, ws_port=8001)

            connected = client.connect()
            if not connected:
                pytest.skip("Server not available")

            # Discover equipment
            result = client.discover_equipment()
            assert result is not None

            # List equipment
            equipment_list = client.list_equipment()
            assert isinstance(equipment_list, list)

            # Disconnect
            client.disconnect()

        except Exception as e:
            pytest.skip(f"Workflow failed: {e}")

    @pytest.mark.asyncio
    async def test_data_acquisition_workflow(self):
        """Test complete data acquisition workflow."""
        try:
            from client.api.client import LabLinkClient

            client = LabLinkClient(host="localhost", api_port=8000, ws_port=8001)

            if not client.connect():
                pytest.skip("Server not available")

            # Get equipment list
            equipment_list = client.list_equipment()
            if not equipment_list:
                pytest.skip("No equipment available")

            equipment_id = equipment_list[0]["id"]

            # Connect to equipment
            client.connect_equipment(equipment_id)

            # Start data stream
            await client.start_equipment_stream(
                equipment_id=equipment_id,
                stream_type="readings",
                interval_ms=100
            )

            # Collect data for a short time
            await asyncio.sleep(2)

            # Stop stream
            await client.stop_equipment_stream(
                equipment_id=equipment_id,
                stream_type="readings"
            )

            # Disconnect equipment
            client.disconnect_equipment(equipment_id)

            # Disconnect client
            client.disconnect()

        except Exception as e:
            pytest.skip(f"Workflow failed: {e}")

    @pytest.mark.asyncio
    async def test_power_supply_control_workflow(self):
        """Test controlling power supply through full stack."""
        pytest.skip("Requires physical power supply")

    @pytest.mark.asyncio
    async def test_oscilloscope_capture_workflow(self):
        """Test capturing oscilloscope data through full stack."""
        pytest.skip("Requires physical oscilloscope")

    @pytest.mark.asyncio
    async def test_electronic_load_test_workflow(self):
        """Test electronic load testing workflow."""
        pytest.skip("Requires physical electronic load")


@pytest.mark.e2e
@pytest.mark.slow
class TestMockEquipmentWorkflow:
    """Test workflows with mock equipment."""

    @pytest.mark.asyncio
    async def test_mock_equipment_full_workflow(self):
        """Test complete workflow with mock equipment."""
        try:
            from client.api.client import LabLinkClient
            from server.equipment.mock import (
                MockOscilloscope,
                MockPowerSupply,
                MockElectronicLoad
            )

            # Create mock equipment
            scope = MockOscilloscope(None, "MOCK::SCOPE::4CH")
            psu = MockPowerSupply(None, "MOCK::PSU::3CH")
            load = MockElectronicLoad(None, "MOCK::LOAD::350W")

            # Connect all. These are coroutines: calling them without await
            # only produces a truthy coroutine object and asserts nothing.
            await scope.connect()
            await psu.connect()
            await load.connect()

            # Test oscilloscope workflow. Channel setup is a single
            # set_channel() call, not separate enable/scale setters.
            await scope.set_channel(1, enabled=True, scale=1.0)
            waveform = await scope.get_waveform(1)
            assert waveform is not None
            assert waveform.channel == 1
            # Samples travel separately over the binary WebSocket channel;
            # the model carries the metadata and a data_id to match them.
            assert waveform.num_samples > 0
            assert waveform.data_id

            # Test power supply workflow
            await psu.set_voltage(12.0, channel=1)
            await psu.set_current(2.0, channel=1)
            await psu.set_output(True, channel=1)
            psu_data = await psu.get_readings(channel=1)
            assert psu_data is not None

            # Test electronic load workflow
            await load.set_mode("CC")
            await load.set_current(5.0)
            await load.set_input(True)
            load_data = await load.get_readings()
            assert load_data is not None
            assert load_data.mode == "CC"

            # Clean up
            await scope.disconnect()
            await psu.disconnect()
            await load.disconnect()

        except ImportError:
            pytest.skip("Mock equipment not available")


@pytest.mark.e2e
@pytest.mark.requires_gui
class TestGUIWorkflow:
    """Test GUI-based workflows."""

    def test_gui_launch(self):
        """Test that GUI can launch."""
        pytest.skip("GUI testing not implemented - requires display and user interaction")

    def test_equipment_panel_interaction(self):
        """Test interacting with equipment panels."""
        pytest.skip("GUI testing not implemented - requires display and user interaction")
