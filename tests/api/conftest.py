"""Pytest configuration and fixtures for API endpoint tests."""

import pytest
import sys
from pathlib import Path
from typing import AsyncGenerator, Dict
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from httpx import AsyncClient

# The repo root, so `server.*` resolves. Deliberately NOT server/ itself:
# putting both on the path lets the same file import under two names, and
# Python then builds two module objects with two sets of module-level
# singletons. That is issue #197 -- a lock reaper polling a dictionary the
# API never writes to.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def mock_equipment_manager():
    """Create a mock equipment manager."""
    mock_manager = MagicMock()
    mock_manager.equipment = {}
    mock_manager.initialize = AsyncMock()
    mock_manager.shutdown = AsyncMock()
    from server.discovery.models import DiscoveredDevice, DiscoveryMethod

    mock_manager.discover_devices = AsyncMock(return_value=[
        DiscoveredDevice(
            device_id="dev-1",
            resource_name="USB0::0x1AB1::0x04CE::DS1ZA123456789::INSTR",
            model="DS1054Z",
            discovery_method=DiscoveryMethod.VISA,
        ),
        DiscoveredDevice(
            device_id="dev-2",
            resource_name="USB0::0x0957::0x0F07::MY12345678::INSTR",
            model="E36312A",
            discovery_method=DiscoveryMethod.VISA,
        ),
    ])
    mock_manager.connect_device = AsyncMock(return_value="test_scope_001")
    mock_manager.disconnect_device = AsyncMock()
    mock_manager.get_connected_devices = AsyncMock(return_value=[])
    mock_manager.get_device = MagicMock(return_value=None)
    mock_manager.get_equipment = MagicMock(return_value=None)
    return mock_manager


@pytest.fixture
def mock_equipment():
    """Create a mock equipment instance."""
    from shared.models.equipment import (ConnectionType, EquipmentInfo,
                                        EquipmentStatus, EquipmentType)

    mock_eq = MagicMock()
    mock_eq.equipment_id = "test_scope_001"
    mock_eq.connected = True

    # Mock equipment info
    mock_info = EquipmentInfo(
        id="test_scope_001",
        type=EquipmentType.OSCILLOSCOPE,
        model="Rigol DS1054Z",
        manufacturer="Rigol",
        connection_type=ConnectionType.USB,
        resource_string="USB0::0x1AB1::0x04CE::DS1ZA123456789::INSTR",
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
    from shared.models.equipment import (ConnectionType, EquipmentInfo,
                                        EquipmentStatus, EquipmentType)

    mock_psu = MagicMock()
    mock_psu.equipment_id = "test_psu_001"
    mock_psu.connected = True

    mock_info = EquipmentInfo(
        id="test_psu_001",
        type=EquipmentType.POWER_SUPPLY,
        model="Keysight E36312A",
        manufacturer="Keysight",
        connection_type=ConnectionType.USB,
        resource_string="USB0::0x0957::0x0F07::MY12345678::INSTR",
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
    mock_manager.can_control_equipment = MagicMock(return_value=True)
    mock_manager.get_lock_status = MagicMock(return_value={})
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
    with patch("server.equipment.manager.equipment_manager", mock_equipment_manager), \
         patch("server.equipment.locks.lock_manager", mock_lock_manager), \
         patch("server.equipment.safety.emergency_stop_manager", mock_emergency_stop_manager), \
         patch("server.acquisition.acquisition_manager", mock_acquisition_manager), \
         patch("server.alarm.alarm_manager", mock_alarm_manager), \
         patch("server.scheduler.scheduler_manager", mock_scheduler_manager):

        # Import and register routers
        try:
            from server.api.equipment import router as equipment_router
            from server.api.safety import router as safety_router
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


@pytest.fixture
def alarms_scheduler_app(tmp_path):
    """A FastAPI app with the alarm and scheduler routers actually mounted.

    These routers were commented out of `app_with_mocks`, so every request in
    test_alarms_scheduler_api.py returned 404 -- and every assertion in that
    file accepted 404, so 26 tests passed without touching the API they name.

    Real managers rather than mocks, for the reason the mocks failed here: they
    had drifted from the interface they stood in for. `create_alarm` returned
    the string "alarm_001" where the route reads `result.alarm_id`, and the
    route calls `list_alarms()` where the mock offered `get_all_alarms`. A
    double that disagrees with the real object tests nothing except itself.

    AlarmManager is pure in-memory. SchedulerManager persists, so it gets a
    SQLite path under tmp_path rather than the repo's data/ directory.
    """
    from fastapi import FastAPI

    import server.api.alarms as alarms_api
    import server.api.scheduler as scheduler_api
    from server.alarm.manager import AlarmManager
    from server.scheduler.manager import SchedulerManager

    alarm_manager = AlarmManager()
    scheduler_manager = SchedulerManager(db_path=str(tmp_path / "scheduler.db"))

    # Patch where the routes look the name up, not where it is defined: both
    # modules did `from ... import alarm_manager` at import time, so patching
    # the defining module would leave the bound name untouched. That is the
    # same hazard as the patch targets in #197.
    with patch.object(alarms_api, "alarm_manager", alarm_manager), \
         patch.object(scheduler_api, "scheduler_manager", scheduler_manager):
        app = FastAPI(title="LabLink Alarms/Scheduler Test API")
        app.include_router(alarms_api.router, prefix="/api", tags=["alarms"])
        app.include_router(scheduler_api.router, prefix="/api", tags=["scheduler"])

        yield app

        # Threshold alarms start a monitoring task on creation; leaving those
        # running leaks tasks across tests.
        for task in list(alarm_manager._monitoring_tasks.values()):
            task.cancel()


@pytest.fixture
def alarms_client(alarms_scheduler_app):
    """Test client whose app really serves the alarm and scheduler routes."""
    return TestClient(alarms_scheduler_app)
