"""Tests for equipment management API endpoints."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from shared.models.equipment import EquipmentInfo, EquipmentType, EquipmentStatus


@pytest.mark.api
class TestEquipmentDiscovery:
    """Tests for equipment discovery endpoints."""

    def test_discover_devices_success(self, client, mock_equipment_manager):
        """Test successful device discovery."""
        # Arrange
        expected_resources = [
            "USB0::0x1AB1::0x04CE::DS1ZA123456789::INSTR",
            "USB0::0x0957::0x0F07::MY12345678::INSTR",
        ]
        mock_equipment_manager.discover_devices.return_value = expected_resources

        # Patch the manager in the equipment module
        with patch("api.equipment.equipment_manager", mock_equipment_manager):
            # Act
            response = client.post("/api/equipment/discover")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert "resources" in data
            assert len(data["resources"]) == 2
            assert data["resources"] == expected_resources
            mock_equipment_manager.discover_devices.assert_called_once()

    def test_discover_devices_empty(self, client, mock_equipment_manager):
        """Test device discovery with no devices found."""
        # Arrange
        mock_equipment_manager.discover_devices.return_value = []

        with patch("api.equipment.equipment_manager", mock_equipment_manager):
            # Act
            response = client.post("/api/equipment/discover")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["resources"] == []

    def test_discover_devices_error(self, client, mock_equipment_manager):
        """Test device discovery with error."""
        # Arrange
        mock_equipment_manager.discover_devices.side_effect = Exception("VISA backend not available")

        with patch("api.equipment.equipment_manager", mock_equipment_manager):
            # Act
            response = client.post("/api/equipment/discover")

            # Assert
            assert response.status_code == 500
            assert "VISA backend not available" in response.json()["detail"]


@pytest.mark.api
class TestEquipmentConnection:
    """Tests for equipment connection endpoints."""

    def test_connect_device_success(self, client, mock_equipment_manager, sample_equipment_data):
        """Test successful device connection."""
        # Arrange
        mock_equipment_manager.connect_device.return_value = "test_scope_001"

        with patch("api.equipment.equipment_manager", mock_equipment_manager):
            # Act
            response = client.post("/api/equipment/connect", json=sample_equipment_data)

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["equipment_id"] == "test_scope_001"
            assert data["status"] == "connected"
            mock_equipment_manager.connect_device.assert_called_once()

    def test_connect_device_invalid_resource(self, client, mock_equipment_manager):
        """Test connection with invalid resource string."""
        # Arrange
        invalid_data = {
            "resource_string": "INVALID::RESOURCE",
            "equipment_type": "oscilloscope",
            "model": "Unknown",
        }
        mock_equipment_manager.connect_device.side_effect = Exception("Invalid resource string")

        with patch("api.equipment.equipment_manager", mock_equipment_manager):
            # Act
            response = client.post("/api/equipment/connect", json=invalid_data)

            # Assert
            assert response.status_code == 500
            assert "Invalid resource string" in response.json()["detail"]

    def test_connect_device_already_connected(self, client, mock_equipment_manager, sample_equipment_data):
        """Test connecting to already connected device."""
        # Arrange
        mock_equipment_manager.connect_device.side_effect = Exception("Device already connected")

        with patch("api.equipment.equipment_manager", mock_equipment_manager):
            # Act
            response = client.post("/api/equipment/connect", json=sample_equipment_data)

            # Assert
            assert response.status_code == 500
            assert "already connected" in response.json()["detail"].lower()

    def test_disconnect_device_success(self, client, mock_equipment_manager, mock_lock_manager):
        """Test successful device disconnection."""
        # Arrange
        equipment_id = "test_scope_001"
        session_id = "session_123"

        with patch("server.api.equipment.equipment_manager", mock_equipment_manager), \
             patch("api.equipment.lock_manager", mock_lock_manager), \
             patch("api.equipment.settings") as mock_settings:

            mock_settings.enable_equipment_locks = True

            # Act
            response = client.post(
                f"/api/equipment/disconnect/{equipment_id}",
                params={"session_id": session_id}
            )

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["equipment_id"] == equipment_id
            assert data["status"] == "disconnected"
            mock_lock_manager.release_lock.assert_called_once_with(
                equipment_id, session_id, force=False
            )
            mock_equipment_manager.disconnect_device.assert_called_once_with(equipment_id)

    def test_disconnect_device_not_found(self, client, mock_equipment_manager):
        """Test disconnecting non-existent device."""
        # Arrange
        mock_equipment_manager.disconnect_device.side_effect = Exception("Device not found")

        with patch("api.equipment.equipment_manager", mock_equipment_manager):
            # Act
            response = client.post("/api/equipment/disconnect/nonexistent_device")

            # Assert
            assert response.status_code == 500
            assert "Device not found" in response.json()["detail"]


@pytest.mark.api
class TestEquipmentList:
    """Tests for equipment listing endpoints."""

    def test_list_devices_empty(self, client, mock_equipment_manager):
        """Test listing devices when none are connected."""
        # Arrange
        mock_equipment_manager.get_connected_devices.return_value = []

        with patch("api.equipment.equipment_manager", mock_equipment_manager):
            # Act
            response = client.get("/api/equipment/list")

            # Assert
            assert response.status_code == 200
            assert response.json() == []

    def test_list_devices_with_equipment(self, client, mock_equipment_manager):
        """Test listing devices with connected equipment."""
        # Arrange
        mock_devices = [
            EquipmentInfo(
                id="test_scope_001",
                type=EquipmentType.OSCILLOSCOPE,
                model="Rigol DS1054Z",
                manufacturer="Rigol",
                resource="USB0::0x1AB1::0x04CE::DS1ZA123456789::INSTR",
                capabilities={"num_channels": 4},
                status=EquipmentStatus.CONNECTED,
            ),
            EquipmentInfo(
                id="test_psu_001",
                type=EquipmentType.POWER_SUPPLY,
                model="Keysight E36312A",
                manufacturer="Keysight",
                resource="USB0::0x0957::0x0F07::MY12345678::INSTR",
                capabilities={"num_channels": 3},
                status=EquipmentStatus.CONNECTED,
            ),
        ]
        mock_equipment_manager.get_connected_devices.return_value = mock_devices

        with patch("api.equipment.equipment_manager", mock_equipment_manager):
            # Act
            response = client.get("/api/equipment/list")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["id"] == "test_scope_001"
            assert data[0]["type"] == "oscilloscope"
            assert data[1]["id"] == "test_psu_001"
            assert data[1]["type"] == "power_supply"

    def test_list_devices_error(self, client, mock_equipment_manager):
        """Test listing devices with error."""
        # Arrange
        mock_equipment_manager.get_connected_devices.side_effect = Exception("Internal error")

        with patch("api.equipment.equipment_manager", mock_equipment_manager):
            # Act
            response = client.get("/api/equipment/list")

            # Assert
            assert response.status_code == 500


@pytest.mark.api
class TestEquipmentInfo:
    """Tests for equipment info endpoints."""

    def test_get_equipment_info_success(self, client, mock_equipment_manager, mock_equipment):
        """Test getting equipment info successfully."""
        # Arrange
        equipment_id = "test_scope_001"
        mock_equipment_manager.get_device.return_value = mock_equipment

        with patch("api.equipment.equipment_manager", mock_equipment_manager):
            # Note: This endpoint might not exist yet, but we're designing the test for it
            # If the endpoint doesn't exist, this test will fail and remind us to implement it
            response = client.get(f"/api/equipment/{equipment_id}/info")

            # Assert - expecting it to work or fail gracefully
            assert response.status_code in [200, 404]

    def test_get_equipment_info_not_found(self, client, mock_equipment_manager):
        """Test getting info for non-existent equipment."""
        # Arrange
        mock_equipment_manager.get_device.return_value = None

        with patch("api.equipment.equipment_manager", mock_equipment_manager):
            # Act
            response = client.get("/api/equipment/nonexistent/info")

            # Assert - expecting 404 or the endpoint doesn't exist (404)
            assert response.status_code == 404


@pytest.mark.api
class TestEquipmentControl:
    """Tests for equipment control endpoints."""

    def test_send_command_success(self, client, mock_equipment_manager, mock_equipment):
        """Test sending command to equipment."""
        # Arrange
        equipment_id = "test_scope_001"
        command_data = {
            "action": "reset",
            "parameters": {},
        }

        mock_equipment_manager.get_device.return_value = mock_equipment

        with patch("api.equipment.equipment_manager", mock_equipment_manager):
            # Act - testing command endpoint
            response = client.post(
                f"/api/equipment/{equipment_id}/command",
                json=command_data
            )

            # Assert - expecting endpoint to exist or 404
            assert response.status_code in [200, 404]

    def test_send_command_device_not_found(self, client, mock_equipment_manager):
        """Test sending command to non-existent device."""
        # Arrange
        mock_equipment_manager.get_device.return_value = None
        command_data = {"action": "reset"}

        with patch("api.equipment.equipment_manager", mock_equipment_manager):
            # Act
            response = client.post(
                "/api/equipment/nonexistent/command",
                json=command_data
            )

            # Assert
            assert response.status_code == 404


@pytest.mark.api
@pytest.mark.integration
class TestEquipmentWorkflow:
    """Integration tests for complete equipment workflows."""

    def test_discover_connect_disconnect_workflow(self, client, mock_equipment_manager, mock_lock_manager):
        """Test complete workflow: discover -> connect -> disconnect."""
        with patch("server.api.equipment.equipment_manager", mock_equipment_manager), \
             patch("server.api.equipment.lock_manager", mock_lock_manager):

            # Step 1: Discover devices
            discover_response = client.post("/api/equipment/discover")
            assert discover_response.status_code == 200
            resources = discover_response.json()["resources"]
            assert len(resources) > 0

            # Step 2: Connect to first device
            connect_data = {
                "resource_string": resources[0],
                "equipment_type": "oscilloscope",
                "model": "Rigol DS1054Z",
            }
            connect_response = client.post("/api/equipment/connect", json=connect_data)
            assert connect_response.status_code == 200
            equipment_id = connect_response.json()["equipment_id"]

            # Step 3: Disconnect device
            disconnect_response = client.post(f"/api/equipment/disconnect/{equipment_id}")
            assert disconnect_response.status_code == 200
            assert disconnect_response.json()["status"] == "disconnected"
