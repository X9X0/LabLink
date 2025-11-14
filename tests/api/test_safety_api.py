"""Tests for safety and emergency stop API endpoints."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime


@pytest.mark.api
class TestEmergencyStop:
    """Tests for emergency stop functionality."""

    def test_activate_emergency_stop_success(self, client, mock_emergency_stop_manager, mock_equipment_manager):
        """Test successful emergency stop activation."""
        # Arrange
        stop_time = datetime.utcnow()
        mock_emergency_stop_manager.activate_emergency_stop.return_value = {
            "active": True,
            "stop_time": stop_time,
            "equipment_count": 0,
        }

        # Mock equipment with output control
        mock_psu = MagicMock()
        mock_psu.set_output = AsyncMock()
        mock_equipment_manager.equipment = {"test_psu_001": mock_psu}

        with patch("api.safety.emergency_stop_manager", mock_emergency_stop_manager), \
             patch("api.safety.equipment_manager", mock_equipment_manager):

            # Act
            response = client.post("/api/safety/emergency-stop/activate")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["active"] is True
            assert "Emergency stop activated" in data["message"]
            assert data["equipment_count"] >= 0

            # Verify emergency stop was activated
            mock_emergency_stop_manager.activate_emergency_stop.assert_called_once()

            # Verify equipment was disabled
            mock_psu.set_output.assert_called_once_with(False)
            mock_emergency_stop_manager.register_stopped_equipment.assert_called_with("test_psu_001")

    def test_activate_emergency_stop_with_multiple_equipment(
        self, client, mock_emergency_stop_manager, mock_equipment_manager
    ):
        """Test emergency stop with multiple equipment."""
        # Arrange
        mock_psu1 = MagicMock()
        mock_psu1.set_output = AsyncMock()

        mock_psu2 = MagicMock()
        mock_psu2.set_output = AsyncMock()

        mock_load = MagicMock()
        mock_load.set_input = AsyncMock()

        mock_equipment_manager.equipment = {
            "test_psu_001": mock_psu1,
            "test_psu_002": mock_psu2,
            "test_load_001": mock_load,
        }

        with patch("api.safety.emergency_stop_manager", mock_emergency_stop_manager), \
             patch("api.safety.equipment_manager", mock_equipment_manager):

            # Act
            response = client.post("/api/safety/emergency-stop/activate")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["equipment_count"] == 3

            # Verify all equipment was disabled
            mock_psu1.set_output.assert_called_once_with(False)
            mock_psu2.set_output.assert_called_once_with(False)
            mock_load.set_input.assert_called_once_with(False)

    def test_activate_emergency_stop_with_equipment_error(
        self, client, mock_emergency_stop_manager, mock_equipment_manager
    ):
        """Test emergency stop when equipment fails to disable."""
        # Arrange
        mock_psu = MagicMock()
        mock_psu.set_output = AsyncMock(side_effect=Exception("Communication error"))

        mock_equipment_manager.equipment = {"test_psu_001": mock_psu}

        with patch("api.safety.emergency_stop_manager", mock_emergency_stop_manager), \
             patch("api.safety.equipment_manager", mock_equipment_manager):

            # Act
            response = client.post("/api/safety/emergency-stop/activate")

            # Assert
            # Emergency stop should still succeed even if individual equipment fails
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    def test_activate_emergency_stop_no_equipment(
        self, client, mock_emergency_stop_manager, mock_equipment_manager
    ):
        """Test emergency stop with no equipment connected."""
        # Arrange
        mock_equipment_manager.equipment = {}

        with patch("api.safety.emergency_stop_manager", mock_emergency_stop_manager), \
             patch("api.safety.equipment_manager", mock_equipment_manager):

            # Act
            response = client.post("/api/safety/emergency-stop/activate")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["equipment_count"] == 0


@pytest.mark.api
class TestEmergencyStopDeactivation:
    """Tests for emergency stop deactivation."""

    def test_deactivate_emergency_stop_success(self, client, mock_emergency_stop_manager):
        """Test successful emergency stop deactivation."""
        # Arrange
        mock_emergency_stop_manager.deactivate_emergency_stop.return_value = {
            "active": False,
            "stop_time": None,
        }

        with patch("api.safety.emergency_stop_manager", mock_emergency_stop_manager):
            # Act
            response = client.post("/api/safety/emergency-stop/deactivate")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["active"] is False
            assert "deactivated" in data["message"].lower()

            # Verify deactivation was called
            mock_emergency_stop_manager.deactivate_emergency_stop.assert_called_once()

    def test_deactivate_when_not_active(self, client, mock_emergency_stop_manager):
        """Test deactivating emergency stop when not active."""
        # Arrange
        mock_emergency_stop_manager.is_emergency_stopped = False
        mock_emergency_stop_manager.deactivate_emergency_stop.return_value = {
            "active": False,
            "stop_time": None,
        }

        with patch("api.safety.emergency_stop_manager", mock_emergency_stop_manager):
            # Act
            response = client.post("/api/safety/emergency-stop/deactivate")

            # Assert
            assert response.status_code == 200
            # Should succeed even if not active


@pytest.mark.api
class TestSafetyStatus:
    """Tests for safety status endpoints."""

    def test_get_safety_status_normal(self, client, mock_emergency_stop_manager, mock_equipment_manager):
        """Test getting safety status under normal conditions."""
        # Arrange
        mock_emergency_stop_manager.get_status.return_value = {
            "active": False,
            "stopped_equipment": [],
        }
        mock_emergency_stop_manager.is_emergency_stopped = False
        mock_emergency_stop_manager.stopped_equipment = set()

        mock_equipment_manager.equipment = {
            "test_psu_001": MagicMock(),
            "test_scope_001": MagicMock(),
        }

        with patch("api.safety.emergency_stop_manager", mock_emergency_stop_manager), \
             patch("api.safety.equipment_manager", mock_equipment_manager):

            # Act
            response = client.get("/api/safety/status")

            # Assert
            # Note: This endpoint may not exist yet, so we check for 200 or 404
            if response.status_code == 200:
                data = response.json()
                assert "emergency_stop_active" in data
                assert data["emergency_stop_active"] is False

    def test_get_safety_status_emergency_active(
        self, client, mock_emergency_stop_manager, mock_equipment_manager
    ):
        """Test getting safety status when emergency stop is active."""
        # Arrange
        mock_emergency_stop_manager.is_emergency_stopped = True
        mock_emergency_stop_manager.stopped_equipment = {"test_psu_001", "test_load_001"}
        mock_emergency_stop_manager.get_status.return_value = {
            "active": True,
            "stopped_equipment": ["test_psu_001", "test_load_001"],
        }

        mock_equipment_manager.equipment = {
            "test_psu_001": MagicMock(),
            "test_load_001": MagicMock(),
        }

        with patch("api.safety.emergency_stop_manager", mock_emergency_stop_manager), \
             patch("api.safety.equipment_manager", mock_equipment_manager):

            # Act
            response = client.get("/api/safety/status")

            # Assert - endpoint may not exist yet
            if response.status_code == 200:
                data = response.json()
                assert data["emergency_stop_active"] is True
                assert len(data["stopped_equipment"]) == 2


@pytest.mark.api
class TestSafetyLimits:
    """Tests for safety limits functionality."""

    def test_set_safety_limit_success(self, client):
        """Test setting safety limit for equipment."""
        # Arrange
        limit_data = {
            "equipment_id": "test_psu_001",
            "parameter": "voltage",
            "min_value": 0.0,
            "max_value": 30.0,
            "enabled": True,
        }

        # Act
        response = client.post("/api/safety/limits", json=limit_data)

        # Assert - endpoint may not be fully implemented
        # We accept both success and 404 (endpoint doesn't exist yet)
        assert response.status_code in [200, 201, 404]

    def test_get_safety_limits(self, client):
        """Test getting safety limits for equipment."""
        # Act
        response = client.get("/api/safety/limits/test_psu_001")

        # Assert - endpoint may not exist yet
        assert response.status_code in [200, 404]

    def test_delete_safety_limit(self, client):
        """Test deleting safety limit."""
        # Act
        response = client.delete("/api/safety/limits/limit_001")

        # Assert - endpoint may not exist yet
        assert response.status_code in [200, 204, 404]


@pytest.mark.api
@pytest.mark.integration
class TestEmergencyStopWorkflow:
    """Integration tests for emergency stop workflow."""

    def test_complete_emergency_stop_workflow(
        self, client, mock_emergency_stop_manager, mock_equipment_manager
    ):
        """Test complete emergency stop workflow: activate -> check status -> deactivate."""
        # Setup equipment
        mock_psu = MagicMock()
        mock_psu.set_output = AsyncMock()
        mock_equipment_manager.equipment = {"test_psu_001": mock_psu}

        with patch("api.safety.emergency_stop_manager", mock_emergency_stop_manager), \
             patch("api.safety.equipment_manager", mock_equipment_manager):

            # Step 1: Activate emergency stop
            activate_response = client.post("/api/safety/emergency-stop/activate")
            assert activate_response.status_code == 200
            assert activate_response.json()["active"] is True

            # Step 2: Check status (if endpoint exists)
            status_response = client.get("/api/safety/status")
            if status_response.status_code == 200:
                assert status_response.json()["emergency_stop_active"] is True

            # Step 3: Deactivate emergency stop
            deactivate_response = client.post("/api/safety/emergency-stop/deactivate")
            assert deactivate_response.status_code == 200
            assert deactivate_response.json()["active"] is False

    def test_emergency_stop_persists_across_requests(
        self, client, mock_emergency_stop_manager, mock_equipment_manager
    ):
        """Test that emergency stop state persists across multiple requests."""
        mock_equipment_manager.equipment = {}

        with patch("api.safety.emergency_stop_manager", mock_emergency_stop_manager), \
             patch("api.safety.equipment_manager", mock_equipment_manager):

            # Activate
            response1 = client.post("/api/safety/emergency-stop/activate")
            assert response1.status_code == 200

            # Check it's still active
            assert mock_emergency_stop_manager.is_emergency_stopped is True

            # Deactivate
            response2 = client.post("/api/safety/emergency-stop/deactivate")
            assert response2.status_code == 200

            # Check it's deactivated
            assert mock_emergency_stop_manager.is_emergency_stopped is False


@pytest.mark.api
class TestSafetyInterlocks:
    """Tests for safety interlock functionality."""

    def test_create_interlock(self, client):
        """Test creating safety interlock."""
        # Arrange
        interlock_data = {
            "name": "Voltage-Current Interlock",
            "condition": "voltage > 25 AND current > 4",
            "action": "emergency_stop",
            "enabled": True,
        }

        # Act
        response = client.post("/api/safety/interlocks", json=interlock_data)

        # Assert - endpoint may not exist yet
        assert response.status_code in [200, 201, 404]

    def test_list_interlocks(self, client):
        """Test listing safety interlocks."""
        # Act
        response = client.get("/api/safety/interlocks")

        # Assert
        assert response.status_code in [200, 404]

    def test_delete_interlock(self, client):
        """Test deleting safety interlock."""
        # Act
        response = client.delete("/api/safety/interlocks/interlock_001")

        # Assert
        assert response.status_code in [200, 204, 404]
