"""Pytest configuration and fixtures for API endpoint tests."""

import pytest
import sys
from pathlib import Path
from typing import AsyncGenerator, Dict
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Add server to path
server_path = Path(__file__).parent.parent.parent / "server"
sys.path.insert(0, str(server_path))


@pytest.fixture
def mock_equipment_manager():
    """Create a mock equipment manager."""
    mock_manager = MagicMock()
    mock_manager.equipment = {}
    mock_manager.initialize = AsyncMock()
    mock_manager.shutdown = AsyncMock()
    mock_manager.discover_devices = AsyncMock(return_value=[
        "USB0::0x1AB1::0x04CE::DS1ZA123456789::INSTR",
        "USB0::0x0957::0x0F07::MY12345678::INSTR",
    ])
    mock_manager.connect_device = AsyncMock(return_value="test_scope_001")
    mock_manager.disconnect_device = AsyncMock()
    mock_manager.get_connected_devices = MagicMock(return_value=[])
    mock_manager.get_device = MagicMock(return_value=None)
    return mock_manager


@pytest.fixture
def mock_equipment():
    """Create a mock equipment instance."""
    from shared.models.equipment import EquipmentInfo, EquipmentType, EquipmentStatus

    mock_eq = MagicMock()
    mock_eq.equipment_id = "test_scope_001"
    mock_eq.connected = True

    # Mock equipment info
    mock_info = EquipmentInfo(
        id="test_scope_001",
        type=EquipmentType.OSCILLOSCOPE,
        model="Rigol DS1054Z",
        manufacturer="Rigol",
        resource="USB0::0x1AB1::0x04CE::DS1ZA123456789::INSTR",
        capabilities={
            "num_channels": 4,
            "max_sample_rate": 1e9,
            "max_bandwidth": 50e6,
        },
        status=EquipmentStatus.CONNECTED,
    )

    mock_eq.get_info = AsyncMock(return_value=mock_info)
    mock_eq.connect = AsyncMock()
    mock_eq.disconnect = AsyncMock()
    mock_eq.reset = AsyncMock()
    mock_eq.get_waveform = AsyncMock()
    mock_eq.set_output = AsyncMock()
    mock_eq.set_input = AsyncMock()

    return mock_eq


@pytest.fixture
def mock_power_supply():
    """Create a mock power supply instance."""
    from shared.models.equipment import EquipmentInfo, EquipmentType, EquipmentStatus

    mock_psu = MagicMock()
    mock_psu.equipment_id = "test_psu_001"
    mock_psu.connected = True

    mock_info = EquipmentInfo(
        id="test_psu_001",
        type=EquipmentType.POWER_SUPPLY,
        model="Keysight E36312A",
        manufacturer="Keysight",
        resource="USB0::0x0957::0x0F07::MY12345678::INSTR",
        capabilities={
            "num_channels": 3,
            "max_voltage": 30.0,
            "max_current": 5.0,
        },
        status=EquipmentStatus.CONNECTED,
    )

    mock_psu.get_info = AsyncMock(return_value=mock_info)
    mock_psu.connect = AsyncMock()
    mock_psu.disconnect = AsyncMock()
    mock_psu.set_output = AsyncMock()
    mock_psu.set_voltage = AsyncMock()
    mock_psu.set_current = AsyncMock()
    mock_psu.get_readings = AsyncMock()

    return mock_psu


@pytest.fixture
def mock_lock_manager():
    """Create a mock lock manager."""
    mock_manager = MagicMock()
    mock_manager.acquire_lock = AsyncMock(return_value=True)
    mock_manager.release_lock = AsyncMock()
    mock_manager.check_lock = AsyncMock(return_value=None)
    mock_manager.get_all_locks = MagicMock(return_value={})
    mock_manager.start_cleanup_task = AsyncMock()
    mock_manager.stop_cleanup_task = AsyncMock()
    return mock_manager


@pytest.fixture
def mock_emergency_stop_manager():
    """Create a mock emergency stop manager."""
    from datetime import datetime

    mock_manager = MagicMock()
    mock_manager.is_emergency_stopped = False
    mock_manager.stopped_equipment = set()

    def activate_stop():
        mock_manager.is_emergency_stopped = True
        return {
            "active": True,
            "stop_time": datetime.utcnow(),
            "equipment_count": 0,
        }

    def deactivate_stop():
        mock_manager.is_emergency_stopped = False
        mock_manager.stopped_equipment.clear()
        return {
            "active": False,
            "stop_time": None,
        }

    mock_manager.activate_emergency_stop = MagicMock(side_effect=activate_stop)
    mock_manager.deactivate_emergency_stop = MagicMock(side_effect=deactivate_stop)
    mock_manager.register_stopped_equipment = MagicMock(
        side_effect=lambda eq_id: mock_manager.stopped_equipment.add(eq_id)
    )
    mock_manager.get_status = MagicMock(
        side_effect=lambda: {
            "active": mock_manager.is_emergency_stopped,
            "stopped_equipment": list(mock_manager.stopped_equipment),
        }
    )

    return mock_manager


@pytest.fixture
def mock_acquisition_manager():
    """Create a mock acquisition manager."""
    mock_manager = MagicMock()
    mock_manager.sessions = {}
    mock_manager.create_session = AsyncMock(return_value="session_001")
    mock_manager.start_session = AsyncMock()
    mock_manager.stop_session = AsyncMock()
    mock_manager.get_session = MagicMock(return_value=None)
    mock_manager.get_all_sessions = MagicMock(return_value=[])
    mock_manager.delete_session = AsyncMock()
    mock_manager.set_export_directory = MagicMock()
    return mock_manager


@pytest.fixture
def mock_alarm_manager():
    """Create a mock alarm manager."""
    mock_manager = MagicMock()
    mock_manager.alarms = {}
    mock_manager.create_alarm = AsyncMock(return_value="alarm_001")
    mock_manager.get_alarm = MagicMock(return_value=None)
    mock_manager.get_all_alarms = MagicMock(return_value=[])
    mock_manager.delete_alarm = AsyncMock()
    mock_manager.acknowledge_alarm = AsyncMock()
    return mock_manager


@pytest.fixture
def mock_scheduler_manager():
    """Create a mock scheduler manager."""
    mock_manager = MagicMock()
    mock_manager.jobs = {}
    mock_manager.create_job = AsyncMock(return_value="job_001")
    mock_manager.get_job = MagicMock(return_value=None)
    mock_manager.get_all_jobs = MagicMock(return_value=[])
    mock_manager.delete_job = AsyncMock()
    mock_manager.start = AsyncMock()
    mock_manager.shutdown = AsyncMock()
    return mock_manager


@pytest.fixture
def mock_security_manager():
    """Create a mock security manager."""
    from datetime import datetime, timedelta

    mock_manager = MagicMock()

    # Mock user
    mock_user = MagicMock()
    mock_user.user_id = "user_001"
    mock_user.username = "testuser"
    mock_user.email = "test@example.com"
    mock_user.full_name = "Test User"
    mock_user.is_active = True
    mock_user.is_superuser = False
    mock_user.roles = []
    mock_user.created_at = datetime.utcnow()
    mock_user.updated_at = datetime.utcnow()

    # Mock token
    mock_token = {
        "access_token": "mock_access_token_12345",
        "refresh_token": "mock_refresh_token_67890",
        "token_type": "bearer",
        "expires_in": 3600,
    }

    mock_manager.authenticate_user = AsyncMock(return_value=mock_user)
    mock_manager.create_user = AsyncMock(return_value=mock_user)
    mock_manager.get_user_by_username = AsyncMock(return_value=mock_user)
    mock_manager.get_user_by_id = AsyncMock(return_value=mock_user)
    mock_manager.update_user = AsyncMock(return_value=mock_user)
    mock_manager.delete_user = AsyncMock()
    mock_manager.create_access_token = MagicMock(return_value=mock_token)
    mock_manager.verify_token = MagicMock(return_value={"sub": "testuser", "user_id": "user_001"})
    mock_manager.check_permission = MagicMock(return_value=True)

    return mock_manager


@pytest.fixture
def app_with_mocks(
    mock_equipment_manager,
    mock_lock_manager,
    mock_emergency_stop_manager,
    mock_acquisition_manager,
    mock_alarm_manager,
    mock_scheduler_manager,
):
    """Create FastAPI app with mocked dependencies."""
    # Create a minimal FastAPI app for testing
    from fastapi import FastAPI

    app = FastAPI(title="LabLink Test API")

    # Patch the managers before importing routers
    with patch("equipment.manager.equipment_manager", mock_equipment_manager), \
         patch("equipment.locks.lock_manager", mock_lock_manager), \
         patch("equipment.safety.emergency_stop_manager", mock_emergency_stop_manager), \
         patch("acquisition.acquisition_manager", mock_acquisition_manager), \
         patch("alarm.alarm_manager", mock_alarm_manager), \
         patch("scheduler.scheduler_manager", mock_scheduler_manager):

        # Import and register routers
        try:
            from api.equipment import router as equipment_router
            from api.safety import router as safety_router
            # Uncomment as more routers are tested
            # from api.acquisition import router as acquisition_router
            # from api.alarms import router as alarms_router
            # from api.scheduler import router as scheduler_router

            app.include_router(equipment_router, prefix="/api/equipment", tags=["equipment"])
            app.include_router(safety_router, prefix="/api/safety", tags=["safety"])
            # app.include_router(acquisition_router, prefix="/api/acquisition", tags=["acquisition"])
            # app.include_router(alarms_router, prefix="/api", tags=["alarms"])
            # app.include_router(scheduler_router, prefix="/api", tags=["scheduler"])
        except ImportError as e:
            pytest.skip(f"Could not import API routers: {e}")

        yield app


@pytest.fixture
def client(app_with_mocks):
    """Create a test client for the FastAPI app."""
    return TestClient(app_with_mocks)


@pytest.fixture
async def async_client(app_with_mocks) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client for the FastAPI app."""
    async with AsyncClient(app=app_with_mocks, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers():
    """Create mock authentication headers."""
    return {
        "Authorization": "Bearer mock_access_token_12345",
        "Content-Type": "application/json",
    }


@pytest.fixture
def sample_equipment_data() -> Dict:
    """Sample equipment data for testing."""
    return {
        "resource_string": "USB0::0x1AB1::0x04CE::DS1ZA123456789::INSTR",
        "equipment_type": "oscilloscope",
        "model": "Rigol DS1054Z",
    }


@pytest.fixture
def sample_acquisition_session_data() -> Dict:
    """Sample acquisition session data for testing."""
    return {
        "equipment_id": "test_scope_001",
        "mode": "continuous",
        "sample_rate": 1000,
        "duration": 10.0,
        "auto_export": False,
    }


@pytest.fixture
def sample_alarm_data() -> Dict:
    """Sample alarm data for testing."""
    return {
        "equipment_id": "test_psu_001",
        "alarm_type": "overvoltage",
        "threshold": 15.0,
        "comparison": "greater_than",
        "enabled": True,
    }


@pytest.fixture
def sample_scheduler_job_data() -> Dict:
    """Sample scheduler job data for testing."""
    return {
        "name": "Daily voltage check",
        "equipment_id": "test_psu_001",
        "action": "measure_voltage",
        "schedule_type": "cron",
        "cron_expression": "0 9 * * *",  # 9 AM daily
        "enabled": True,
    }
