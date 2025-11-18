"""
Comprehensive tests for diagnostics API endpoints.

Tests cover all 16 diagnostics API endpoints:
- Health monitoring (health, cached health, all health)
- Connection diagnostics
- Communication diagnostics
- Performance benchmarking (run, history)
- System diagnostics
- Diagnostic reports
- Enhanced diagnostics (temperature, errors, self-test, calibration, comprehensive)
- Statistics recording (connection, disconnection)
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime
from fastapi.testclient import TestClient
from fastapi import FastAPI

from server.diagnostics.models import (
    HealthStatus,
    DiagnosticStatus,
    DiagnosticCategory,
    EquipmentHealth,
    ConnectionDiagnostics,
    CommunicationDiagnostics,
    PerformanceBenchmark,
    SystemDiagnostics,
    DiagnosticReport,
    DiagnosticResult,
)


# ==================== Fixtures ====================


@pytest.fixture
def mock_diagnostics_manager():
    """Create a mock diagnostics manager."""
    mock_manager = AsyncMock()

    # Mock equipment health
    mock_health = EquipmentHealth(
        equipment_id="test_scope_001",
        health_status=HealthStatus.HEALTHY,
        health_score=95.0,
        connection_status=DiagnosticStatus.PASS,
        communication_status=DiagnosticStatus.PASS,
        performance_status=DiagnosticStatus.PASS,
        functionality_status=DiagnosticStatus.PASS,
        passed_tests=10,
        failed_tests=0,
        warning_tests=1,
    )

    # Mock connection diagnostics
    mock_connection = ConnectionDiagnostics(
        equipment_id="test_scope_001",
        is_connected=True,
        connection_time=datetime.now(),
        disconnection_count=0,
        uptime_seconds=3600.0,
        response_time_ms=45.2,
        error_rate=0.5,
    )

    # Mock communication diagnostics
    mock_communication = CommunicationDiagnostics(
        equipment_id="test_scope_001",
        total_commands=1000,
        successful_commands=995,
        failed_commands=5,
        average_response_time_ms=50.0,
    )

    # Mock performance benchmark
    mock_benchmark = PerformanceBenchmark(
        equipment_id="test_scope_001",
        command_latency_ms={"*IDN?": 45.2, "*OPC?": 30.1},
        throughput_commands_per_sec=25.0,
        cpu_usage_percent=15.0,
        memory_usage_mb=128.0,
        performance_score=92.0,
    )

    # Mock system diagnostics
    mock_system = SystemDiagnostics(
        total_equipment=5,
        connected_equipment=4,
        disconnected_equipment=1,
        healthy_equipment=3,
        degraded_equipment=1,
        critical_equipment=0,
        server_cpu_percent=25.0,
        server_memory_percent=60.0,
        server_disk_percent=45.0,
        server_uptime_seconds=86400.0,
    )

    # Mock diagnostic report
    mock_report = DiagnosticReport(
        equipment_ids=["test_scope_001"],
        categories=[DiagnosticCategory.CONNECTION],
        overall_health=HealthStatus.HEALTHY,
        total_tests=10,
        passed_tests=9,
        failed_tests=0,
        warning_tests=1,
    )

    # Mock diagnostic result
    mock_result = DiagnosticResult(
        test_id="self_test",
        equipment_id="test_scope_001",
        status=DiagnosticStatus.PASS,
        message="Self-test passed",
    )

    # Configure mock methods
    mock_manager.check_equipment_health.return_value = mock_health
    mock_manager.get_health_cache.return_value = mock_health
    mock_manager._check_connection.return_value = mock_connection
    mock_manager._check_communication.return_value = mock_communication
    mock_manager._run_performance_benchmark.return_value = mock_benchmark
    mock_manager.get_benchmark_history.return_value = [mock_benchmark]
    mock_manager.get_system_diagnostics.return_value = mock_system
    mock_manager.generate_diagnostic_report.return_value = mock_report
    mock_manager.check_temperature.return_value = 35.5
    mock_manager.check_error_codes.return_value = {
        "has_error": False,
        "error_code": 0,
        "error_message": "No error",
    }
    mock_manager.run_self_test.return_value = mock_result
    mock_manager.check_calibration_status.return_value = {
        "status": "current",
        "is_current": True,
        "days_until_due": 335,
    }
    mock_manager.get_equipment_diagnostics.return_value = {
        "equipment_id": "test_scope_001",
        "timestamp": datetime.now(),
        "temperature_celsius": 35.5,
        "operating_hours": 1234.5,
        "error_info": {"has_error": False},
        "calibration_status": {"status": "current"},
    }

    # Statistics recording methods (non-async)
    mock_manager.record_connection = MagicMock()
    mock_manager.record_disconnection = MagicMock()

    return mock_manager


@pytest.fixture
def mock_equipment_manager_for_diagnostics():
    """Create a mock equipment manager for diagnostics tests."""
    mock_manager = MagicMock()
    mock_manager.equipment = {
        "test_scope_001": MagicMock(),
        "test_psu_001": MagicMock(),
    }
    return mock_manager


@pytest.fixture
def diagnostics_client(mock_diagnostics_manager, mock_equipment_manager_for_diagnostics):
    """Create a test client with diagnostics router."""
    app = FastAPI()

    with patch("server.diagnostics.diagnostics_manager", mock_diagnostics_manager), \
         patch("equipment.manager.equipment_manager", mock_equipment_manager_for_diagnostics):

        # Import and register diagnostics router
        from server.api.diagnostics import router as diagnostics_router
        app.include_router(diagnostics_router, tags=["diagnostics"])

        yield TestClient(app), mock_diagnostics_manager


# ==================== Health Monitoring Tests ====================


@pytest.mark.api
class TestHealthMonitoring:
    """Tests for health monitoring endpoints."""

    def test_get_equipment_health_success(self, diagnostics_client):
        """Test getting equipment health successfully."""
        client, mock_manager = diagnostics_client

        response = client.get("/diagnostics/health/test_scope_001")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "health" in data
        assert data["health"]["equipment_id"] == "test_scope_001"
        assert data["health"]["health_status"] == "healthy"
        assert data["health"]["health_score"] == 95.0

        mock_manager.check_equipment_health.assert_called_once_with("test_scope_001")

    def test_get_equipment_health_error(self, diagnostics_client):
        """Test getting equipment health with error."""
        client, mock_manager = diagnostics_client
        mock_manager.check_equipment_health.side_effect = Exception("Test error")

        response = client.get("/diagnostics/health/test_scope_001")

        assert response.status_code == 500
        assert "Failed to check health" in response.json()["detail"]

    def test_get_all_equipment_health_success(self, diagnostics_client):
        """Test getting health for all equipment."""
        client, mock_manager = diagnostics_client

        response = client.get("/diagnostics/health")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "equipment_health" in data
        assert "count" in data
        assert data["count"] == 2  # test_scope_001 and test_psu_001

    def test_get_cached_health_success(self, diagnostics_client):
        """Test getting cached health status."""
        client, mock_manager = diagnostics_client

        response = client.get("/diagnostics/health/test_scope_001/cached")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["cached"] is True
        assert "health" in data
        assert data["health"]["equipment_id"] == "test_scope_001"

        mock_manager.get_health_cache.assert_called_once_with("test_scope_001")

    def test_get_cached_health_not_found(self, diagnostics_client):
        """Test getting cached health when not available."""
        client, mock_manager = diagnostics_client
        mock_manager.get_health_cache.return_value = None

        response = client.get("/diagnostics/health/test_scope_001/cached")

        assert response.status_code == 404
        assert "No cached health data" in response.json()["detail"]


# ==================== Connection Diagnostics Tests ====================


@pytest.mark.api
class TestConnectionDiagnostics:
    """Tests for connection diagnostics endpoints."""

    def test_check_connection_success(self, diagnostics_client):
        """Test checking connection status successfully."""
        client, mock_manager = diagnostics_client

        response = client.get("/diagnostics/connection/test_scope_001")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "connection" in data
        assert data["connection"]["equipment_id"] == "test_scope_001"
        assert data["connection"]["is_connected"] is True
        assert data["connection"]["response_time_ms"] == 45.2

        mock_manager._check_connection.assert_called_once_with("test_scope_001")

    def test_check_connection_error(self, diagnostics_client):
        """Test checking connection with error."""
        client, mock_manager = diagnostics_client
        mock_manager._check_connection.side_effect = Exception("Connection check failed")

        response = client.get("/diagnostics/connection/test_scope_001")

        assert response.status_code == 500
        assert "Failed to check connection" in response.json()["detail"]


# ==================== Communication Diagnostics Tests ====================


@pytest.mark.api
class TestCommunicationDiagnostics:
    """Tests for communication diagnostics endpoints."""

    def test_get_communication_diagnostics_success(self, diagnostics_client):
        """Test getting communication diagnostics successfully."""
        client, mock_manager = diagnostics_client

        response = client.get("/diagnostics/communication/test_scope_001")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "communication" in data
        assert data["communication"]["equipment_id"] == "test_scope_001"
        assert data["communication"]["total_commands"] == 1000
        assert data["communication"]["successful_commands"] == 995

        mock_manager._check_communication.assert_called_once_with("test_scope_001")

    def test_get_communication_diagnostics_error(self, diagnostics_client):
        """Test getting communication diagnostics with error."""
        client, mock_manager = diagnostics_client
        mock_manager._check_communication.side_effect = Exception("Comm check failed")

        response = client.get("/diagnostics/communication/test_scope_001")

        assert response.status_code == 500
        assert "Failed to check communication" in response.json()["detail"]


# ==================== Performance Benchmarking Tests ====================


@pytest.mark.api
class TestPerformanceBenchmarking:
    """Tests for performance benchmarking endpoints."""

    def test_run_benchmark_success(self, diagnostics_client):
        """Test running performance benchmark successfully."""
        client, mock_manager = diagnostics_client

        response = client.post("/diagnostics/benchmark/test_scope_001")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "benchmark" in data
        assert data["benchmark"]["equipment_id"] == "test_scope_001"
        assert data["benchmark"]["performance_score"] == 92.0
        assert "*IDN?" in data["benchmark"]["command_latency_ms"]

        mock_manager._run_performance_benchmark.assert_called_once_with("test_scope_001")

    def test_run_benchmark_equipment_not_found(self, diagnostics_client):
        """Test running benchmark on non-existent equipment."""
        client, mock_manager = diagnostics_client
        mock_manager._run_performance_benchmark.return_value = None

        response = client.post("/diagnostics/benchmark/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_run_benchmark_error(self, diagnostics_client):
        """Test running benchmark with error."""
        client, mock_manager = diagnostics_client
        mock_manager._run_performance_benchmark.side_effect = Exception("Benchmark failed")

        response = client.post("/diagnostics/benchmark/test_scope_001")

        assert response.status_code == 500
        assert "Failed to run benchmark" in response.json()["detail"]

    def test_get_benchmark_history_success(self, diagnostics_client):
        """Test getting benchmark history successfully."""
        client, mock_manager = diagnostics_client

        response = client.get("/diagnostics/benchmark/test_scope_001/history")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "benchmarks" in data
        assert "count" in data
        assert data["count"] == 1
        assert len(data["benchmarks"]) == 1

        mock_manager.get_benchmark_history.assert_called_once_with("test_scope_001", 100)

    def test_get_benchmark_history_with_limit(self, diagnostics_client):
        """Test getting benchmark history with custom limit."""
        client, mock_manager = diagnostics_client

        response = client.get("/diagnostics/benchmark/test_scope_001/history?limit=50")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        mock_manager.get_benchmark_history.assert_called_once_with("test_scope_001", 50)

    def test_get_benchmark_history_error(self, diagnostics_client):
        """Test getting benchmark history with error."""
        client, mock_manager = diagnostics_client
        mock_manager.get_benchmark_history.side_effect = Exception("History fetch failed")

        response = client.get("/diagnostics/benchmark/test_scope_001/history")

        assert response.status_code == 500
        assert "Failed to get history" in response.json()["detail"]


# ==================== Diagnostic Reports Tests ====================


@pytest.mark.api
class TestDiagnosticReports:
    """Tests for diagnostic report generation."""

    def test_generate_diagnostic_report_success(self, diagnostics_client):
        """Test generating diagnostic report successfully."""
        client, mock_manager = diagnostics_client

        response = client.post(
            "/diagnostics/report",
            json={
                "equipment_ids": ["test_scope_001"],
                "categories": ["connection", "performance"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "report" in data
        assert data["report"]["overall_health"] == "healthy"
        assert data["report"]["total_tests"] == 10

    def test_generate_diagnostic_report_no_params(self, diagnostics_client):
        """Test generating report with no parameters (all equipment)."""
        client, mock_manager = diagnostics_client

        response = client.post("/diagnostics/report", json={})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "report" in data

        # Should be called with None for both params
        mock_manager.generate_diagnostic_report.assert_called_once_with(
            equipment_ids=None, categories=None
        )

    def test_generate_diagnostic_report_invalid_category(self, diagnostics_client):
        """Test generating report with invalid category."""
        client, mock_manager = diagnostics_client

        response = client.post(
            "/diagnostics/report",
            json={
                "equipment_ids": ["test_scope_001"],
                "categories": ["invalid_category"],
            },
        )

        assert response.status_code == 400
        assert "Invalid category" in response.json()["detail"]

    def test_generate_diagnostic_report_error(self, diagnostics_client):
        """Test generating report with error."""
        client, mock_manager = diagnostics_client
        mock_manager.generate_diagnostic_report.side_effect = Exception("Report generation failed")

        response = client.post("/diagnostics/report", json={})

        assert response.status_code == 500
        assert "Failed to generate report" in response.json()["detail"]


# ==================== System Diagnostics Tests ====================


@pytest.mark.api
class TestSystemDiagnostics:
    """Tests for system-wide diagnostics."""

    def test_get_system_diagnostics_success(self, diagnostics_client):
        """Test getting system diagnostics successfully."""
        client, mock_manager = diagnostics_client

        response = client.get("/diagnostics/system")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "system" in data
        assert data["system"]["total_equipment"] == 5
        assert data["system"]["connected_equipment"] == 4
        assert data["system"]["healthy_equipment"] == 3
        assert data["system"]["server_cpu_percent"] == 25.0

        mock_manager.get_system_diagnostics.assert_called_once()

    def test_get_system_diagnostics_error(self, diagnostics_client):
        """Test getting system diagnostics with error."""
        client, mock_manager = diagnostics_client
        mock_manager.get_system_diagnostics.side_effect = Exception("System check failed")

        response = client.get("/diagnostics/system")

        assert response.status_code == 500
        assert "Failed to get system diagnostics" in response.json()["detail"]


# ==================== Enhanced Diagnostics Tests ====================


@pytest.mark.api
class TestEnhancedDiagnostics:
    """Tests for enhanced diagnostic features (v0.12.0)."""

    def test_check_equipment_temperature_success(self, diagnostics_client):
        """Test checking equipment temperature successfully."""
        client, mock_manager = diagnostics_client

        response = client.get("/diagnostics/temperature/test_scope_001")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["equipment_id"] == "test_scope_001"
        assert data["temperature_celsius"] == 35.5
        assert data["supported"] is True

        mock_manager.check_temperature.assert_called_once_with("test_scope_001")

    def test_check_equipment_temperature_not_supported(self, diagnostics_client):
        """Test checking temperature when not supported."""
        client, mock_manager = diagnostics_client
        mock_manager.check_temperature.return_value = None

        response = client.get("/diagnostics/temperature/test_scope_001")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["temperature_celsius"] is None
        assert data["supported"] is False

    def test_check_equipment_temperature_error(self, diagnostics_client):
        """Test checking temperature with error."""
        client, mock_manager = diagnostics_client
        mock_manager.check_temperature.side_effect = Exception("Temperature check failed")

        response = client.get("/diagnostics/temperature/test_scope_001")

        assert response.status_code == 500
        assert "Failed to check temperature" in response.json()["detail"]

    def test_check_equipment_errors_no_error(self, diagnostics_client):
        """Test checking equipment errors when no errors present."""
        client, mock_manager = diagnostics_client

        response = client.get("/diagnostics/errors/test_scope_001")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["equipment_id"] == "test_scope_001"
        assert data["has_error"] is False
        assert data["error_code"] == 0

        mock_manager.check_error_codes.assert_called_once_with("test_scope_001")

    def test_check_equipment_errors_with_error(self, diagnostics_client):
        """Test checking equipment errors when error present."""
        client, mock_manager = diagnostics_client
        mock_manager.check_error_codes.return_value = {
            "has_error": True,
            "error_code": -100,
            "error_message": "Command error",
            "error_info": {"severity": "error"},
        }

        response = client.get("/diagnostics/errors/test_scope_001")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["has_error"] is True
        assert data["error_code"] == -100
        assert data["error_message"] == "Command error"

    def test_check_equipment_errors_exception(self, diagnostics_client):
        """Test checking equipment errors with exception."""
        client, mock_manager = diagnostics_client
        mock_manager.check_error_codes.side_effect = Exception("Error check failed")

        response = client.get("/diagnostics/errors/test_scope_001")

        assert response.status_code == 500
        assert "Failed to check error codes" in response.json()["detail"]

    def test_run_equipment_self_test_success(self, diagnostics_client):
        """Test running self-test successfully."""
        client, mock_manager = diagnostics_client

        response = client.post("/diagnostics/self-test/test_scope_001")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "test_result" in data
        assert data["test_result"]["status"] == "pass"
        assert data["test_result"]["equipment_id"] == "test_scope_001"

        mock_manager.run_self_test.assert_called_once_with("test_scope_001")

    def test_run_equipment_self_test_failed(self, diagnostics_client):
        """Test running self-test that fails."""
        client, mock_manager = diagnostics_client
        mock_result = DiagnosticResult(
            test_id="self_test",
            equipment_id="test_scope_001",
            status=DiagnosticStatus.FAIL,
            message="Self-test failed",
        )
        mock_manager.run_self_test.return_value = mock_result

        response = client.post("/diagnostics/self-test/test_scope_001")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["test_result"]["status"] == "fail"

    def test_run_equipment_self_test_error(self, diagnostics_client):
        """Test running self-test with error."""
        client, mock_manager = diagnostics_client
        mock_manager.run_self_test.side_effect = Exception("Self-test error")

        response = client.post("/diagnostics/self-test/test_scope_001")

        assert response.status_code == 500
        assert "Failed to run self-test" in response.json()["detail"]

    def test_check_calibration_status_success(self, diagnostics_client):
        """Test checking calibration status successfully."""
        client, mock_manager = diagnostics_client

        response = client.get("/diagnostics/calibration/test_scope_001")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["equipment_id"] == "test_scope_001"
        assert data["status"] == "current"
        assert data["is_current"] is True
        assert data["days_until_due"] == 335

        mock_manager.check_calibration_status.assert_called_once_with("test_scope_001")

    def test_check_calibration_status_overdue(self, diagnostics_client):
        """Test checking calibration status when overdue."""
        client, mock_manager = diagnostics_client
        mock_manager.check_calibration_status.return_value = {
            "status": "overdue",
            "is_current": False,
            "days_until_due": -30,
        }

        response = client.get("/diagnostics/calibration/test_scope_001")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "overdue"
        assert data["is_current"] is False

    def test_check_calibration_status_error(self, diagnostics_client):
        """Test checking calibration status with error."""
        client, mock_manager = diagnostics_client
        mock_manager.check_calibration_status.side_effect = Exception("Cal check failed")

        response = client.get("/diagnostics/calibration/test_scope_001")

        assert response.status_code == 500
        assert "Failed to check calibration" in response.json()["detail"]

    def test_get_comprehensive_diagnostics_success(self, diagnostics_client):
        """Test getting comprehensive diagnostics successfully."""
        client, mock_manager = diagnostics_client

        response = client.get("/diagnostics/comprehensive/test_scope_001")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["equipment_id"] == "test_scope_001"
        assert data["temperature_celsius"] == 35.5
        assert data["operating_hours"] == 1234.5
        assert "error_info" in data
        assert "calibration_status" in data

        mock_manager.get_equipment_diagnostics.assert_called_once_with("test_scope_001")

    def test_get_comprehensive_diagnostics_error(self, diagnostics_client):
        """Test getting comprehensive diagnostics with error."""
        client, mock_manager = diagnostics_client
        mock_manager.get_equipment_diagnostics.side_effect = Exception("Diagnostics failed")

        response = client.get("/diagnostics/comprehensive/test_scope_001")

        assert response.status_code == 500
        assert "Failed to get diagnostics" in response.json()["detail"]


# ==================== Statistics Recording Tests ====================


@pytest.mark.api
class TestStatisticsRecording:
    """Tests for statistics recording endpoints."""

    def test_record_connection_event_success(self, diagnostics_client):
        """Test recording connection event successfully."""
        client, mock_manager = diagnostics_client

        response = client.post("/diagnostics/stats/connection/test_scope_001")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Connection event recorded" in data["message"]

        mock_manager.record_connection.assert_called_once_with("test_scope_001")

    def test_record_disconnection_event_without_error(self, diagnostics_client):
        """Test recording disconnection event without error."""
        client, mock_manager = diagnostics_client

        response = client.post("/diagnostics/stats/disconnection/test_scope_001")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Disconnection event recorded" in data["message"]

        mock_manager.record_disconnection.assert_called_once_with("test_scope_001", None)

    def test_record_disconnection_event_with_error(self, diagnostics_client):
        """Test recording disconnection event with error message."""
        client, mock_manager = diagnostics_client

        response = client.post(
            "/diagnostics/stats/disconnection/test_scope_001?error=Connection lost"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        mock_manager.record_disconnection.assert_called_once_with(
            "test_scope_001", "Connection lost"
        )


# ==================== Integration Tests ====================


@pytest.mark.api
class TestDiagnosticsIntegration:
    """Integration tests for diagnostics API."""

    def test_full_health_check_workflow(self, diagnostics_client):
        """Test complete health check workflow."""
        client, mock_manager = diagnostics_client

        # 1. Check if cached health exists
        response = client.get("/diagnostics/health/test_scope_001/cached")
        # May or may not exist initially

        # 2. Run full health check
        response = client.get("/diagnostics/health/test_scope_001")
        assert response.status_code == 200
        assert response.json()["success"] is True

        # 3. Now cached health should exist
        mock_manager.check_equipment_health.assert_called()

    def test_benchmark_workflow(self, diagnostics_client):
        """Test benchmark workflow."""
        client, mock_manager = diagnostics_client

        # 1. Run benchmark
        response = client.post("/diagnostics/benchmark/test_scope_001")
        assert response.status_code == 200
        assert response.json()["success"] is True

        # 2. Get benchmark history
        response = client.get("/diagnostics/benchmark/test_scope_001/history")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 1

    def test_enhanced_diagnostics_workflow(self, diagnostics_client):
        """Test enhanced diagnostics workflow."""
        client, mock_manager = diagnostics_client

        # Check temperature
        response = client.get("/diagnostics/temperature/test_scope_001")
        assert response.status_code == 200

        # Check errors
        response = client.get("/diagnostics/errors/test_scope_001")
        assert response.status_code == 200

        # Check calibration
        response = client.get("/diagnostics/calibration/test_scope_001")
        assert response.status_code == 200

        # Get comprehensive diagnostics
        response = client.get("/diagnostics/comprehensive/test_scope_001")
        assert response.status_code == 200
        data = response.json()
        assert "temperature_celsius" in data
        assert "error_info" in data
        assert "calibration_status" in data

    def test_system_overview_workflow(self, diagnostics_client):
        """Test system overview workflow."""
        client, mock_manager = diagnostics_client

        # Get all equipment health
        response = client.get("/diagnostics/health")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 1

        # Get system diagnostics
        response = client.get("/diagnostics/system")
        assert response.status_code == 200
        data = response.json()
        assert "system" in data
        assert data["system"]["total_equipment"] > 0

        # Generate comprehensive report
        response = client.post("/diagnostics/report", json={})
        assert response.status_code == 200
        data = response.json()
        assert "report" in data
