"""
Comprehensive tests for the diagnostics system.

Tests cover:
- DiagnosticStatus, DiagnosticCategory, HealthStatus enums
- All diagnostic models (Pydantic validation)
- DiagnosticsManager class:
  - Health checks and scoring
  - Connection diagnostics
  - Communication diagnostics
  - Performance benchmarking
  - Functionality testing
  - Statistics tracking
  - Report generation
  - System diagnostics
  - Enhanced diagnostics (temperature, errors, self-test, calibration)
"""

import asyncio
import json
import pytest
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock, call

from server.diagnostics.models import (
    DiagnosticStatus,
    DiagnosticCategory,
    HealthStatus,
    DiagnosticTest,
    DiagnosticResult,
    ConnectionDiagnostics,
    CommunicationDiagnostics,
    PerformanceBenchmark,
    EquipmentHealth,
    DiagnosticReport,
    SystemDiagnostics,
)

from server.diagnostics.manager import DiagnosticsManager


# ==================== Fixtures ====================


@pytest.fixture
def diagnostics_manager():
    """Create a fresh diagnostics manager for each test."""
    return DiagnosticsManager()


@pytest.fixture
def mock_equipment():
    """Create a mock equipment object."""
    equipment = AsyncMock()
    equipment.equipment_id = "test_scope_001"
    equipment.resource_name = "USB0::0x1AB1::0x04CE::DS1ZA123456789::INSTR"

    # Default mock responses
    equipment.query.return_value = "RIGOL TECHNOLOGIES,DS1054Z,DS1ZA123456789,00.04.04.SP2"
    equipment.get_temperature.return_value = 35.5
    equipment.get_operating_hours.return_value = 1234.5
    equipment.get_error_code.return_value = 0
    equipment.get_error_message.return_value = "No error"
    equipment.run_self_test.return_value = {"passed": True, "details": "All tests passed"}
    equipment.get_info.return_value = Mock(manufacturer="Rigol")

    return equipment


@pytest.fixture
def mock_equipment_manager(mock_equipment):
    """Create a mock equipment manager."""
    manager = Mock()
    manager.get_equipment.return_value = mock_equipment
    manager.equipment = {"test_scope_001": mock_equipment}
    manager._equipment = {"test_scope_001": mock_equipment}
    manager.get_connected_devices.return_value = [mock_equipment]
    return manager


@pytest.fixture
def mock_calibration_manager():
    """Create a mock calibration manager."""
    from server.equipment.calibration import CalibrationStatus, CalibrationResult

    manager = AsyncMock()
    manager.get_calibration_status.return_value = CalibrationStatus.CURRENT
    manager.get_latest_calibration.return_value = Mock(
        calibration_date=datetime.now() - timedelta(days=30),
        due_date=datetime.now() + timedelta(days=335),
        result=CalibrationResult.PASS,
    )
    manager.get_days_until_due.return_value = 335
    manager.is_calibration_current.return_value = True
    return manager


# ==================== Enum Tests ====================


class TestDiagnosticEnums:
    """Test diagnostic enumeration types."""

    def test_diagnostic_status_values(self):
        """Test DiagnosticStatus enum has all expected values."""
        assert DiagnosticStatus.UNKNOWN == "unknown"
        assert DiagnosticStatus.PASS == "pass"
        assert DiagnosticStatus.FAIL == "fail"
        assert DiagnosticStatus.WARNING == "warning"
        assert DiagnosticStatus.ERROR == "error"
        assert DiagnosticStatus.RUNNING == "running"
        assert DiagnosticStatus.PENDING == "pending"

    def test_diagnostic_category_values(self):
        """Test DiagnosticCategory enum has all expected values."""
        assert DiagnosticCategory.CONNECTION == "connection"
        assert DiagnosticCategory.COMMUNICATION == "communication"
        assert DiagnosticCategory.PERFORMANCE == "performance"
        assert DiagnosticCategory.FUNCTIONALITY == "functionality"
        assert DiagnosticCategory.CALIBRATION == "calibration"
        assert DiagnosticCategory.SAFETY == "safety"
        assert DiagnosticCategory.SYSTEM == "system"

    def test_health_status_values(self):
        """Test HealthStatus enum has all expected values."""
        assert HealthStatus.HEALTHY == "healthy"
        assert HealthStatus.DEGRADED == "degraded"
        assert HealthStatus.WARNING == "warning"
        assert HealthStatus.CRITICAL == "critical"
        assert HealthStatus.OFFLINE == "offline"
        assert HealthStatus.UNKNOWN == "unknown"


# ==================== Model Tests ====================


class TestDiagnosticModels:
    """Test diagnostic Pydantic models."""

    def test_diagnostic_test_minimal(self):
        """Test creating minimal DiagnosticTest."""
        test = DiagnosticTest(
            name="Connection Test",
            category=DiagnosticCategory.CONNECTION,
        )

        assert test.name == "Connection Test"
        assert test.category == DiagnosticCategory.CONNECTION
        assert test.test_id.startswith("test_")
        assert test.timeout_seconds == 30
        assert test.retry_count == 3
        assert test.enabled is True
        assert isinstance(test.created_at, datetime)

    def test_diagnostic_test_with_thresholds(self):
        """Test DiagnosticTest with thresholds."""
        test = DiagnosticTest(
            name="Temperature Check",
            category=DiagnosticCategory.FUNCTIONALITY,
            equipment_id="scope_001",
            threshold_warning=50.0,
            threshold_critical=70.0,
            timeout_seconds=60,
        )

        assert test.equipment_id == "scope_001"
        assert test.threshold_warning == 50.0
        assert test.threshold_critical == 70.0
        assert test.timeout_seconds == 60

    def test_diagnostic_result_pass(self):
        """Test DiagnosticResult for passing test."""
        result = DiagnosticResult(
            test_id="test_001",
            equipment_id="scope_001",
            status=DiagnosticStatus.PASS,
            value=95.5,
            expected_value=100.0,
            tolerance=5.0,
            message="Test passed",
        )

        assert result.status == DiagnosticStatus.PASS
        assert result.value == 95.5
        assert result.expected_value == 100.0
        assert result.message == "Test passed"
        assert result.error is None

    def test_diagnostic_result_fail_with_error(self):
        """Test DiagnosticResult for failed test."""
        result = DiagnosticResult(
            test_id="test_002",
            equipment_id="scope_001",
            status=DiagnosticStatus.FAIL,
            message="Test failed",
            error="Connection timeout",
        )

        assert result.status == DiagnosticStatus.FAIL
        assert result.error == "Connection timeout"

    def test_connection_diagnostics(self):
        """Test ConnectionDiagnostics model."""
        conn = ConnectionDiagnostics(
            equipment_id="scope_001",
            is_connected=True,
            connection_time=datetime.now(),
            disconnection_count=2,
            uptime_seconds=3600.0,
            visa_resource="USB0::...",
            response_time_ms=45.2,
            error_rate=2.5,
        )

        assert conn.is_connected is True
        assert conn.disconnection_count == 2
        assert conn.uptime_seconds == 3600.0
        assert conn.response_time_ms == 45.2
        assert conn.error_rate == 2.5

    def test_communication_diagnostics(self):
        """Test CommunicationDiagnostics model."""
        comm = CommunicationDiagnostics(
            equipment_id="scope_001",
            total_commands=1000,
            successful_commands=980,
            failed_commands=20,
            timeout_count=5,
            average_response_time_ms=125.5,
            min_response_time_ms=50.0,
            max_response_time_ms=500.0,
            bytes_sent=50000,
            bytes_received=150000,
        )

        assert comm.total_commands == 1000
        assert comm.successful_commands == 980
        assert comm.failed_commands == 20
        assert comm.timeout_count == 5
        assert comm.bytes_sent == 50000

    def test_performance_benchmark(self):
        """Test PerformanceBenchmark model."""
        benchmark = PerformanceBenchmark(
            equipment_id="scope_001",
            command_latency_ms={"*IDN?": 45.2, "*OPC?": 30.1},
            throughput_commands_per_sec=25.5,
            cpu_usage_percent=15.2,
            memory_usage_mb=128.5,
            performance_score=92.0,
        )

        assert benchmark.equipment_id == "scope_001"
        assert benchmark.command_latency_ms["*IDN?"] == 45.2
        assert benchmark.throughput_commands_per_sec == 25.5
        assert benchmark.performance_score == 92.0
        assert benchmark.benchmark_id.startswith("bench_")

    def test_equipment_health(self):
        """Test EquipmentHealth model."""
        health = EquipmentHealth(
            equipment_id="scope_001",
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

        assert health.equipment_id == "scope_001"
        assert health.health_status == HealthStatus.HEALTHY
        assert health.health_score == 95.0
        assert health.passed_tests == 10
        assert health.failed_tests == 0

    def test_diagnostic_report(self):
        """Test DiagnosticReport model."""
        report = DiagnosticReport(
            equipment_ids=["scope_001", "psu_001"],
            categories=[DiagnosticCategory.CONNECTION, DiagnosticCategory.PERFORMANCE],
            overall_health=HealthStatus.HEALTHY,
            total_tests=50,
            passed_tests=48,
            failed_tests=1,
            warning_tests=1,
        )

        assert len(report.equipment_ids) == 2
        assert len(report.categories) == 2
        assert report.overall_health == HealthStatus.HEALTHY
        assert report.total_tests == 50
        assert report.report_id.startswith("report_")

    def test_system_diagnostics(self):
        """Test SystemDiagnostics model."""
        sys_diag = SystemDiagnostics(
            total_equipment=10,
            connected_equipment=8,
            disconnected_equipment=2,
            healthy_equipment=6,
            degraded_equipment=2,
            critical_equipment=0,
            server_cpu_percent=25.5,
            server_memory_percent=60.2,
            server_disk_percent=45.0,
            server_uptime_seconds=86400.0,
        )

        assert sys_diag.total_equipment == 10
        assert sys_diag.connected_equipment == 8
        assert sys_diag.healthy_equipment == 6
        assert sys_diag.server_cpu_percent == 25.5


# ==================== DiagnosticsManager Tests ====================


class TestDiagnosticsManager:
    """Test DiagnosticsManager functionality."""

    def test_manager_initialization(self, diagnostics_manager):
        """Test DiagnosticsManager initializes correctly."""
        assert isinstance(diagnostics_manager._tests, dict)
        assert isinstance(diagnostics_manager._results, dict)
        assert isinstance(diagnostics_manager._health_cache, dict)
        assert isinstance(diagnostics_manager._benchmarks, dict)
        assert diagnostics_manager._max_benchmark_history == 100
        assert isinstance(diagnostics_manager._server_start_time, datetime)

    @pytest.mark.asyncio
    async def test_check_equipment_health_not_found(self, diagnostics_manager):
        """Test health check for non-existent equipment."""
        with patch("equipment.manager.equipment_manager") as mock_manager:
            mock_manager.get_equipment.return_value = None

            health = await diagnostics_manager.check_equipment_health("nonexistent")

            assert health.equipment_id == "nonexistent"
            assert health.health_status == HealthStatus.OFFLINE
            assert health.health_score == 0.0
            assert "Equipment not found" in health.active_issues

    @pytest.mark.asyncio
    async def test_check_equipment_health_success(
        self, diagnostics_manager, mock_equipment, mock_equipment_manager
    ):
        """Test successful equipment health check."""
        with patch("equipment.manager.equipment_manager", mock_equipment_manager):
            health = await diagnostics_manager.check_equipment_health("test_scope_001")

            assert health.equipment_id == "test_scope_001"
            assert isinstance(health.health_status, HealthStatus)
            assert 0.0 <= health.health_score <= 100.0
            assert health.connection_diagnostics is not None
            assert health.communication_diagnostics is not None

            # Verify queries were made
            assert mock_equipment.query.called

    @pytest.mark.asyncio
    async def test_check_connection_success(
        self, diagnostics_manager, mock_equipment, mock_equipment_manager
    ):
        """Test connection diagnostics for connected equipment."""
        with patch("equipment.manager.equipment_manager", mock_equipment_manager):
            # Record some connection stats
            diagnostics_manager.record_connection("test_scope_001")

            conn_diag = await diagnostics_manager._check_connection("test_scope_001")

            assert conn_diag.equipment_id == "test_scope_001"
            assert conn_diag.is_connected is True
            assert conn_diag.response_time_ms is not None
            assert conn_diag.response_time_ms > 0

            # Verify IDN query was made
            mock_equipment.query.assert_called_with("*IDN?")

    @pytest.mark.asyncio
    async def test_check_connection_failure(
        self, diagnostics_manager, mock_equipment, mock_equipment_manager
    ):
        """Test connection diagnostics when equipment fails to respond."""
        mock_equipment.query.side_effect = Exception("Connection timeout")

        with patch("equipment.manager.equipment_manager", mock_equipment_manager):
            conn_diag = await diagnostics_manager._check_connection("test_scope_001")

            assert conn_diag.is_connected is False
            assert conn_diag.response_time_ms is None

    @pytest.mark.asyncio
    async def test_check_connection_not_found(self, diagnostics_manager):
        """Test connection diagnostics for non-existent equipment."""
        with patch("equipment.manager.equipment_manager") as mock_manager:
            mock_manager.get_equipment.return_value = None

            conn_diag = await diagnostics_manager._check_connection("nonexistent")

            assert conn_diag.equipment_id == "nonexistent"
            assert conn_diag.is_connected is False

    @pytest.mark.asyncio
    async def test_check_communication(self, diagnostics_manager):
        """Test communication diagnostics."""
        # Record some communication stats
        diagnostics_manager.record_command(
            "test_scope_001",
            success=True,
            response_time_ms=50.0,
            bytes_sent=100,
            bytes_received=500,
        )
        diagnostics_manager.record_command(
            "test_scope_001",
            success=True,
            response_time_ms=75.0,
            bytes_sent=150,
            bytes_received=600,
        )
        diagnostics_manager.record_command(
            "test_scope_001",
            success=False,
            response_time_ms=200.0,
            error="Timeout",
        )

        comm_diag = await diagnostics_manager._check_communication("test_scope_001")

        assert comm_diag.equipment_id == "test_scope_001"
        assert comm_diag.total_commands == 3
        assert comm_diag.successful_commands == 2
        assert comm_diag.failed_commands == 1
        assert comm_diag.bytes_sent == 250
        assert comm_diag.bytes_received == 1100
        assert comm_diag.average_response_time_ms > 0

    @pytest.mark.asyncio
    async def test_check_communication_no_stats(self, diagnostics_manager):
        """Test communication diagnostics with no recorded stats."""
        comm_diag = await diagnostics_manager._check_communication("new_equipment")

        assert comm_diag.equipment_id == "new_equipment"
        assert comm_diag.total_commands == 0
        assert comm_diag.successful_commands == 0
        assert comm_diag.failed_commands == 0
        assert comm_diag.average_response_time_ms == 0.0

    @pytest.mark.asyncio
    async def test_run_performance_benchmark(
        self, diagnostics_manager, mock_equipment, mock_equipment_manager
    ):
        """Test performance benchmark execution."""
        with patch("equipment.manager.equipment_manager", mock_equipment_manager):
            benchmark = await diagnostics_manager._run_performance_benchmark("test_scope_001")

            assert benchmark is not None
            assert benchmark.equipment_id == "test_scope_001"
            assert "*IDN?" in benchmark.command_latency_ms
            assert "*OPC?" in benchmark.command_latency_ms
            assert benchmark.throughput_commands_per_sec >= 0
            assert benchmark.cpu_usage_percent is not None
            assert benchmark.memory_usage_mb is not None
            assert 0 <= benchmark.performance_score <= 100

    @pytest.mark.asyncio
    async def test_run_performance_benchmark_not_found(self, diagnostics_manager):
        """Test performance benchmark for non-existent equipment."""
        with patch("equipment.manager.equipment_manager") as mock_manager:
            mock_manager.get_equipment.return_value = None

            benchmark = await diagnostics_manager._run_performance_benchmark("nonexistent")

            assert benchmark is None

    @pytest.mark.asyncio
    async def test_run_performance_benchmark_command_failure(
        self, diagnostics_manager, mock_equipment, mock_equipment_manager
    ):
        """Test performance benchmark when commands fail."""
        mock_equipment.query.side_effect = Exception("Command failed")

        with patch("equipment.manager.equipment_manager", mock_equipment_manager):
            benchmark = await diagnostics_manager._run_performance_benchmark("test_scope_001")

            assert benchmark is not None
            # Failed commands should have -1 latency
            assert all(latency == -1 for latency in benchmark.command_latency_ms.values())

    @pytest.mark.asyncio
    async def test_check_functionality(
        self, diagnostics_manager, mock_equipment, mock_equipment_manager
    ):
        """Test functionality checks."""
        with patch("equipment.manager.equipment_manager", mock_equipment_manager):
            results = await diagnostics_manager._check_functionality("test_scope_001")

            assert len(results) == 3  # IDN, OPC, Error query
            assert all(isinstance(r, DiagnosticResult) for r in results)
            assert all(r.equipment_id == "test_scope_001" for r in results)

            # All should pass with mock equipment
            passed = [r for r in results if r.status == DiagnosticStatus.PASS]
            assert len(passed) >= 2  # At least IDN and OPC should pass

    @pytest.mark.asyncio
    async def test_check_functionality_not_found(self, diagnostics_manager):
        """Test functionality checks for non-existent equipment."""
        with patch("equipment.manager.equipment_manager") as mock_manager:
            mock_manager.get_equipment.return_value = None

            results = await diagnostics_manager._check_functionality("nonexistent")

            assert results == []

    @pytest.mark.asyncio
    async def test_run_test_success(
        self, diagnostics_manager, mock_equipment, mock_equipment_manager
    ):
        """Test running a single diagnostic test successfully."""
        async def test_func():
            return "Test result"

        result = await diagnostics_manager._run_test(
            "Test Name",
            "test_scope_001",
            test_func,
            "Expected outcome",
        )

        assert result.status == DiagnosticStatus.PASS
        assert result.equipment_id == "test_scope_001"
        assert "Test passed" in result.message
        assert result.error is None
        assert result.duration_seconds is not None

    @pytest.mark.asyncio
    async def test_run_test_failure(self, diagnostics_manager):
        """Test running a single diagnostic test that fails."""
        async def test_func():
            raise Exception("Test error")

        result = await diagnostics_manager._run_test(
            "Test Name",
            "test_scope_001",
            test_func,
            "Expected outcome",
        )

        assert result.status == DiagnosticStatus.FAIL
        assert result.equipment_id == "test_scope_001"
        assert "Test failed" in result.message
        assert result.error == "Test error"

    def test_calculate_health_score_perfect(self, diagnostics_manager):
        """Test health score calculation for perfect health."""
        connection = ConnectionDiagnostics(
            equipment_id="test",
            is_connected=True,
            response_time_ms=50.0,
        )

        communication = CommunicationDiagnostics(
            equipment_id="test",
            total_commands=100,
            successful_commands=100,
        )

        performance = PerformanceBenchmark(
            equipment_id="test",
            performance_score=100.0,
        )

        func_results = [
            DiagnosticResult(
                test_id="test1",
                equipment_id="test",
                status=DiagnosticStatus.PASS,
            ),
            DiagnosticResult(
                test_id="test2",
                equipment_id="test",
                status=DiagnosticStatus.PASS,
            ),
        ]

        score = diagnostics_manager._calculate_health_score(
            connection, communication, performance, func_results
        )

        # Perfect score should be 100
        assert score == 100.0

    def test_calculate_health_score_disconnected(self, diagnostics_manager):
        """Test health score calculation for disconnected equipment."""
        connection = ConnectionDiagnostics(
            equipment_id="test",
            is_connected=False,
        )

        communication = CommunicationDiagnostics(
            equipment_id="test",
            total_commands=0,
        )

        performance = None
        func_results = []

        score = diagnostics_manager._calculate_health_score(
            connection, communication, performance, func_results
        )

        # Disconnected should have very low score
        assert score < 50.0

    def test_calculate_health_score_partial_failure(self, diagnostics_manager):
        """Test health score calculation with partial failures."""
        connection = ConnectionDiagnostics(
            equipment_id="test",
            is_connected=True,
            response_time_ms=400.0,  # Slower response
        )

        communication = CommunicationDiagnostics(
            equipment_id="test",
            total_commands=100,
            successful_commands=90,  # 90% success rate
        )

        performance = PerformanceBenchmark(
            equipment_id="test",
            performance_score=80.0,
        )

        func_results = [
            DiagnosticResult(test_id="test1", equipment_id="test", status=DiagnosticStatus.PASS),
            DiagnosticResult(test_id="test2", equipment_id="test", status=DiagnosticStatus.FAIL),
        ]

        score = diagnostics_manager._calculate_health_score(
            connection, communication, performance, func_results
        )

        # Should be between 50-90
        assert 50.0 < score < 90.0

    def test_determine_health_status(self, diagnostics_manager):
        """Test health status determination from score."""
        assert diagnostics_manager._determine_health_status(95.0) == HealthStatus.HEALTHY
        assert diagnostics_manager._determine_health_status(90.0) == HealthStatus.HEALTHY
        assert diagnostics_manager._determine_health_status(75.0) == HealthStatus.DEGRADED
        assert diagnostics_manager._determine_health_status(60.0) == HealthStatus.WARNING
        assert diagnostics_manager._determine_health_status(40.0) == HealthStatus.CRITICAL
        assert diagnostics_manager._determine_health_status(0.0) == HealthStatus.OFFLINE

    def test_get_communication_status(self, diagnostics_manager):
        """Test communication status determination."""
        # Unknown - no commands
        comm = CommunicationDiagnostics(equipment_id="test", total_commands=0)
        assert diagnostics_manager._get_communication_status(comm) == DiagnosticStatus.UNKNOWN

        # Pass - 98% success
        comm = CommunicationDiagnostics(
            equipment_id="test",
            total_commands=100,
            successful_commands=98,
        )
        assert diagnostics_manager._get_communication_status(comm) == DiagnosticStatus.PASS

        # Warning - 85% success
        comm = CommunicationDiagnostics(
            equipment_id="test",
            total_commands=100,
            successful_commands=85,
        )
        assert diagnostics_manager._get_communication_status(comm) == DiagnosticStatus.WARNING

        # Fail - 75% success
        comm = CommunicationDiagnostics(
            equipment_id="test",
            total_commands=100,
            successful_commands=75,
        )
        assert diagnostics_manager._get_communication_status(comm) == DiagnosticStatus.FAIL

    def test_get_performance_status(self, diagnostics_manager):
        """Test performance status determination."""
        # Unknown - no benchmark
        assert diagnostics_manager._get_performance_status(None) == DiagnosticStatus.UNKNOWN

        # Pass - score >= 80
        perf = PerformanceBenchmark(equipment_id="test", performance_score=85.0)
        assert diagnostics_manager._get_performance_status(perf) == DiagnosticStatus.PASS

        # Warning - score between 60-80
        perf = PerformanceBenchmark(equipment_id="test", performance_score=70.0)
        assert diagnostics_manager._get_performance_status(perf) == DiagnosticStatus.WARNING

        # Fail - score < 60
        perf = PerformanceBenchmark(equipment_id="test", performance_score=50.0)
        assert diagnostics_manager._get_performance_status(perf) == DiagnosticStatus.FAIL

    def test_get_functionality_status(self, diagnostics_manager):
        """Test functionality status determination."""
        # Unknown - no results
        assert diagnostics_manager._get_functionality_status([]) == DiagnosticStatus.UNKNOWN

        # Pass - 100% success
        results = [
            DiagnosticResult(test_id="t1", equipment_id="test", status=DiagnosticStatus.PASS),
            DiagnosticResult(test_id="t2", equipment_id="test", status=DiagnosticStatus.PASS),
        ]
        assert diagnostics_manager._get_functionality_status(results) == DiagnosticStatus.PASS

        # Warning - 75% success
        results = [
            DiagnosticResult(test_id="t1", equipment_id="test", status=DiagnosticStatus.PASS),
            DiagnosticResult(test_id="t2", equipment_id="test", status=DiagnosticStatus.PASS),
            DiagnosticResult(test_id="t3", equipment_id="test", status=DiagnosticStatus.PASS),
            DiagnosticResult(test_id="t4", equipment_id="test", status=DiagnosticStatus.FAIL),
        ]
        assert diagnostics_manager._get_functionality_status(results) == DiagnosticStatus.WARNING

        # Fail - 60% success
        results = [
            DiagnosticResult(test_id="t1", equipment_id="test", status=DiagnosticStatus.PASS),
            DiagnosticResult(test_id="t2", equipment_id="test", status=DiagnosticStatus.PASS),
            DiagnosticResult(test_id="t3", equipment_id="test", status=DiagnosticStatus.PASS),
            DiagnosticResult(test_id="t4", equipment_id="test", status=DiagnosticStatus.FAIL),
            DiagnosticResult(test_id="t5", equipment_id="test", status=DiagnosticStatus.FAIL),
        ]
        assert diagnostics_manager._get_functionality_status(results) == DiagnosticStatus.FAIL

    @pytest.mark.asyncio
    async def test_generate_diagnostic_report(
        self, diagnostics_manager, mock_equipment, mock_equipment_manager
    ):
        """Test diagnostic report generation."""
        with patch("equipment.manager.equipment_manager", mock_equipment_manager):
            report = await diagnostics_manager.generate_diagnostic_report(
                equipment_ids=["test_scope_001"],
                categories=[DiagnosticCategory.CONNECTION, DiagnosticCategory.PERFORMANCE],
            )

            assert isinstance(report, DiagnosticReport)
            assert len(report.equipment_ids) == 1
            assert "test_scope_001" in report.equipment_ids
            assert len(report.categories) == 2
            assert isinstance(report.overall_health, HealthStatus)
            assert report.duration_seconds is not None
            assert report.completed_at is not None

    @pytest.mark.asyncio
    async def test_generate_diagnostic_report_all_equipment(
        self, diagnostics_manager, mock_equipment, mock_equipment_manager
    ):
        """Test diagnostic report generation for all equipment."""
        with patch("equipment.manager.equipment_manager", mock_equipment_manager):
            report = await diagnostics_manager.generate_diagnostic_report()

            assert isinstance(report, DiagnosticReport)
            assert len(report.equipment_ids) >= 1
            assert isinstance(report.overall_health, HealthStatus)

    @pytest.mark.asyncio
    async def test_get_system_diagnostics(
        self, diagnostics_manager, mock_equipment, mock_equipment_manager
    ):
        """Test system-wide diagnostics."""
        with patch("equipment.manager.equipment_manager", mock_equipment_manager):
            # Generate some health data first
            await diagnostics_manager.check_equipment_health("test_scope_001")

            sys_diag = await diagnostics_manager.get_system_diagnostics()

            assert isinstance(sys_diag, SystemDiagnostics)
            assert sys_diag.total_equipment >= 1
            assert sys_diag.connected_equipment >= 0
            assert sys_diag.server_cpu_percent is not None
            assert sys_diag.server_memory_percent is not None
            assert sys_diag.server_disk_percent is not None
            assert sys_diag.server_uptime_seconds is not None
            assert sys_diag.server_uptime_seconds >= 0


# ==================== Statistics Tracking Tests ====================


class TestStatisticsTracking:
    """Test statistics tracking functionality."""

    def test_record_connection(self, diagnostics_manager):
        """Test recording equipment connection."""
        diagnostics_manager.record_connection("test_scope_001")

        stats = diagnostics_manager._connection_stats["test_scope_001"]
        assert stats["connection_count"] == 1
        assert stats["last_connected"] is not None
        assert isinstance(stats["last_connected"], datetime)

    def test_record_multiple_connections(self, diagnostics_manager):
        """Test recording multiple connections."""
        diagnostics_manager.record_connection("test_scope_001")
        diagnostics_manager.record_connection("test_scope_001")
        diagnostics_manager.record_connection("test_scope_001")

        stats = diagnostics_manager._connection_stats["test_scope_001"]
        assert stats["connection_count"] == 3

    def test_record_disconnection(self, diagnostics_manager):
        """Test recording equipment disconnection."""
        diagnostics_manager.record_disconnection("test_scope_001", error="Connection lost")

        stats = diagnostics_manager._connection_stats["test_scope_001"]
        assert stats["disconnection_count"] == 1
        assert len(stats["errors"]) == 1
        assert stats["errors"][0]["error"] == "Connection lost"

    def test_record_disconnection_without_error(self, diagnostics_manager):
        """Test recording disconnection without error."""
        diagnostics_manager.record_disconnection("test_scope_001")

        stats = diagnostics_manager._connection_stats["test_scope_001"]
        assert stats["disconnection_count"] == 1
        assert len(stats["errors"]) == 0

    def test_record_command_success(self, diagnostics_manager):
        """Test recording successful command."""
        diagnostics_manager.record_command(
            "test_scope_001",
            success=True,
            response_time_ms=50.5,
            bytes_sent=100,
            bytes_received=500,
        )

        stats = diagnostics_manager._communication_stats["test_scope_001"]
        assert stats["total_commands"] == 1
        assert stats["successful"] == 1
        assert stats["failed"] == 0
        assert len(stats["response_times"]) == 1
        assert stats["response_times"][0] == 50.5
        assert stats["bytes_sent"] == 100
        assert stats["bytes_received"] == 500

    def test_record_command_failure(self, diagnostics_manager):
        """Test recording failed command."""
        diagnostics_manager.record_command(
            "test_scope_001",
            success=False,
            response_time_ms=200.0,
            error="Timeout",
        )

        stats = diagnostics_manager._communication_stats["test_scope_001"]
        assert stats["total_commands"] == 1
        assert stats["successful"] == 0
        assert stats["failed"] == 1
        assert stats["last_error"] == "Timeout"
        assert len(stats["error_list"]) == 1

    def test_record_many_commands_response_time_limit(self, diagnostics_manager):
        """Test that response times are limited to 1000 entries."""
        for i in range(1500):
            diagnostics_manager.record_command(
                "test_scope_001",
                success=True,
                response_time_ms=float(i),
            )

        stats = diagnostics_manager._communication_stats["test_scope_001"]
        assert stats["total_commands"] == 1500
        assert len(stats["response_times"]) == 1000  # Capped at 1000

    def test_get_health_cache(self, diagnostics_manager):
        """Test getting cached health status."""
        # Initially None
        assert diagnostics_manager.get_health_cache("test_scope_001") is None

        # Add to cache
        health = EquipmentHealth(
            equipment_id="test_scope_001",
            health_status=HealthStatus.HEALTHY,
            health_score=95.0,
        )
        diagnostics_manager._health_cache["test_scope_001"] = health

        # Should retrieve from cache
        cached = diagnostics_manager.get_health_cache("test_scope_001")
        assert cached is not None
        assert cached.equipment_id == "test_scope_001"
        assert cached.health_score == 95.0

    def test_get_benchmark_history(self, diagnostics_manager):
        """Test getting benchmark history."""
        # Initially empty
        history = diagnostics_manager.get_benchmark_history("test_scope_001")
        assert len(history) == 0

        # Add benchmarks
        for i in range(5):
            benchmark = PerformanceBenchmark(
                equipment_id="test_scope_001",
                performance_score=float(90 - i),
            )
            diagnostics_manager._benchmarks["test_scope_001"].append(benchmark)

        # Retrieve history
        history = diagnostics_manager.get_benchmark_history("test_scope_001")
        assert len(history) == 5
        assert all(b.equipment_id == "test_scope_001" for b in history)

    def test_get_benchmark_history_with_limit(self, diagnostics_manager):
        """Test getting limited benchmark history."""
        # Add many benchmarks
        for i in range(150):
            benchmark = PerformanceBenchmark(
                equipment_id="test_scope_001",
                performance_score=float(i),
            )
            diagnostics_manager._benchmarks["test_scope_001"].append(benchmark)

            # Manually trim to max history (like the manager does)
            if len(diagnostics_manager._benchmarks["test_scope_001"]) > diagnostics_manager._max_benchmark_history:
                diagnostics_manager._benchmarks["test_scope_001"].pop(0)

        # Should only keep last 100 (due to max_benchmark_history)
        assert len(diagnostics_manager._benchmarks["test_scope_001"]) == 100

        # Get limited history
        history = diagnostics_manager.get_benchmark_history("test_scope_001", limit=10)
        assert len(history) == 10


# ==================== Enhanced Diagnostics Tests ====================


class TestEnhancedDiagnostics:
    """Test enhanced diagnostic features (v0.12.0)."""

    @pytest.mark.asyncio
    async def test_check_temperature_success(
        self, diagnostics_manager, mock_equipment, mock_equipment_manager
    ):
        """Test temperature check success."""
        with patch("equipment.manager.equipment_manager", mock_equipment_manager):
            temp = await diagnostics_manager.check_temperature("test_scope_001")

            assert temp == 35.5
            mock_equipment.get_temperature.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_temperature_not_found(self, diagnostics_manager):
        """Test temperature check for non-existent equipment."""
        with patch("equipment.manager.equipment_manager") as mock_manager:
            mock_manager.get_equipment.return_value = None

            temp = await diagnostics_manager.check_temperature("nonexistent")

            assert temp is None

    @pytest.mark.asyncio
    async def test_check_temperature_not_supported(
        self, diagnostics_manager, mock_equipment, mock_equipment_manager
    ):
        """Test temperature check when not supported."""
        mock_equipment.get_temperature.return_value = None

        with patch("equipment.manager.equipment_manager", mock_equipment_manager):
            temp = await diagnostics_manager.check_temperature("test_scope_001")

            assert temp is None

    @pytest.mark.asyncio
    async def test_check_temperature_error(
        self, diagnostics_manager, mock_equipment, mock_equipment_manager
    ):
        """Test temperature check with error."""
        mock_equipment.get_temperature.side_effect = Exception("Sensor error")

        with patch("equipment.manager.equipment_manager", mock_equipment_manager):
            temp = await diagnostics_manager.check_temperature("test_scope_001")

            assert temp is None

    @pytest.mark.asyncio
    async def test_check_error_codes_no_error(
        self, diagnostics_manager, mock_equipment, mock_equipment_manager
    ):
        """Test error code check when no errors."""
        with patch("equipment.manager.equipment_manager", mock_equipment_manager):
            with patch("equipment.error_codes.get_error_code_db") as mock_db:
                error_info = await diagnostics_manager.check_error_codes("test_scope_001")

                assert error_info["has_error"] is False
                assert error_info["error_code"] == 0

    @pytest.mark.asyncio
    async def test_check_error_codes_with_error(
        self, diagnostics_manager, mock_equipment, mock_equipment_manager
    ):
        """Test error code check with active error."""
        mock_equipment.get_error_code.return_value = -100
        mock_equipment.get_error_message.return_value = "Command error"

        with patch("equipment.manager.equipment_manager", mock_equipment_manager):
            with patch("equipment.error_codes.get_error_code_db") as mock_db:
                mock_db.return_value.get_troubleshooting_info.return_value = {
                    "severity": "error",
                    "category": "communication",
                }

                error_info = await diagnostics_manager.check_error_codes("test_scope_001")

                assert error_info["has_error"] is True
                assert error_info["error_code"] == -100
                assert error_info["error_message"] == "Command error"

    @pytest.mark.asyncio
    async def test_check_error_codes_not_found(self, diagnostics_manager):
        """Test error code check for non-existent equipment."""
        with patch("equipment.manager.equipment_manager") as mock_manager:
            mock_manager.get_equipment.return_value = None

            error_info = await diagnostics_manager.check_error_codes("nonexistent")

            assert "error" in error_info
            assert "not found" in error_info["error"].lower()

    @pytest.mark.asyncio
    async def test_run_self_test_pass(
        self, diagnostics_manager, mock_equipment, mock_equipment_manager
    ):
        """Test self-test execution that passes."""
        with patch("equipment.manager.equipment_manager", mock_equipment_manager):
            result = await diagnostics_manager.run_self_test("test_scope_001")

            assert isinstance(result, DiagnosticResult)
            assert result.test_id == "self_test"
            assert result.equipment_id == "test_scope_001"
            assert result.status == DiagnosticStatus.PASS
            assert "passed" in result.message

    @pytest.mark.asyncio
    async def test_run_self_test_fail(
        self, diagnostics_manager, mock_equipment, mock_equipment_manager
    ):
        """Test self-test execution that fails."""
        mock_equipment.run_self_test.return_value = {"passed": False, "details": "Hardware error"}

        with patch("equipment.manager.equipment_manager", mock_equipment_manager):
            result = await diagnostics_manager.run_self_test("test_scope_001")

            assert result.status == DiagnosticStatus.FAIL
            assert "failed" in result.message

    @pytest.mark.asyncio
    async def test_run_self_test_not_supported(
        self, diagnostics_manager, mock_equipment, mock_equipment_manager
    ):
        """Test self-test when not supported."""
        mock_equipment.run_self_test.return_value = None

        with patch("equipment.manager.equipment_manager", mock_equipment_manager):
            result = await diagnostics_manager.run_self_test("test_scope_001")

            assert result.status == DiagnosticStatus.UNKNOWN
            assert "not supported" in result.message

    @pytest.mark.asyncio
    async def test_run_self_test_not_found(self, diagnostics_manager):
        """Test self-test for non-existent equipment."""
        with patch("equipment.manager.equipment_manager") as mock_manager:
            mock_manager.get_equipment.return_value = None

            result = await diagnostics_manager.run_self_test("nonexistent")

            assert result.status == DiagnosticStatus.ERROR
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_check_calibration_status_current(
        self, diagnostics_manager, mock_calibration_manager
    ):
        """Test calibration status check for current calibration."""
        with patch("equipment.calibration.get_calibration_manager", return_value=mock_calibration_manager):
            cal_status = await diagnostics_manager.check_calibration_status("test_scope_001")

            assert cal_status["status"] == "current"
            assert cal_status["is_current"] is True
            assert cal_status["days_until_due"] == 335

    @pytest.mark.asyncio
    async def test_check_calibration_status_no_manager(self, diagnostics_manager):
        """Test calibration status check when manager not initialized."""
        with patch("equipment.calibration.get_calibration_manager", return_value=None):
            cal_status = await diagnostics_manager.check_calibration_status("test_scope_001")

            assert "error" in cal_status
            assert cal_status["status"] == "unknown"

    @pytest.mark.asyncio
    async def test_get_equipment_diagnostics(
        self, diagnostics_manager, mock_equipment, mock_equipment_manager, mock_calibration_manager
    ):
        """Test comprehensive equipment diagnostics."""
        with patch("equipment.manager.equipment_manager", mock_equipment_manager):
            with patch("equipment.calibration.get_calibration_manager", return_value=mock_calibration_manager):
                with patch("equipment.error_codes.get_error_code_db") as mock_db:
                    diagnostics = await diagnostics_manager.get_equipment_diagnostics("test_scope_001")

                    assert diagnostics["equipment_id"] == "test_scope_001"
                    assert "timestamp" in diagnostics
                    assert diagnostics["temperature_celsius"] == 35.5
                    assert diagnostics["operating_hours"] == 1234.5
                    assert diagnostics["error_info"] is not None
                    assert diagnostics["calibration_status"] is not None

    @pytest.mark.asyncio
    async def test_get_equipment_diagnostics_not_found(self, diagnostics_manager):
        """Test comprehensive diagnostics for non-existent equipment."""
        with patch("equipment.manager.equipment_manager") as mock_manager:
            mock_manager.get_equipment.return_value = None

            diagnostics = await diagnostics_manager.get_equipment_diagnostics("nonexistent")

            assert "error" in diagnostics
            assert "not found" in diagnostics["error"].lower()
