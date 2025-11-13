"""Diagnostics manager for equipment health and performance monitoring."""

import asyncio
import logging
import time
import psutil
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict

from .models import (
    DiagnosticTest,
    DiagnosticResult,
    DiagnosticStatus,
    DiagnosticCategory,
    HealthStatus,
    ConnectionDiagnostics,
    CommunicationDiagnostics,
    PerformanceBenchmark,
    EquipmentHealth,
    DiagnosticReport,
    SystemDiagnostics,
)

logger = logging.getLogger(__name__)


class DiagnosticsManager:
    """Manages equipment diagnostics and health monitoring."""

    def __init__(self):
        """Initialize diagnostics manager."""
        self._tests: Dict[str, DiagnosticTest] = {}
        self._results: Dict[str, DiagnosticResult] = {}
        self._health_cache: Dict[str, EquipmentHealth] = {}
        self._benchmarks: Dict[str, List[PerformanceBenchmark]] = defaultdict(list)
        self._max_benchmark_history = 100

        # Statistics tracking
        self._connection_stats: Dict[str, Dict] = defaultdict(lambda: {
            "connection_count": 0,
            "disconnection_count": 0,
            "total_uptime": 0,
            "last_connected": None,
            "errors": []
        })

        self._communication_stats: Dict[str, Dict] = defaultdict(lambda: {
            "total_commands": 0,
            "successful": 0,
            "failed": 0,
            "timeouts": 0,
            "retries": 0,
            "response_times": [],
            "bytes_sent": 0,
            "bytes_received": 0
        })

        self._server_start_time = datetime.now()

    # ==================== Health Checks ====================

    async def check_equipment_health(self, equipment_id: str) -> EquipmentHealth:
        """Perform comprehensive health check on equipment."""
        from equipment.manager import equipment_manager

        equipment = equipment_manager.get_equipment(equipment_id)
        if not equipment:
            return EquipmentHealth(
                equipment_id=equipment_id,
                health_status=HealthStatus.OFFLINE,
                health_score=0.0,
                active_issues=["Equipment not found"]
            )

        # Run all diagnostic tests
        connection_diag = await self._check_connection(equipment_id)
        comm_diag = await self._check_communication(equipment_id)
        perf_benchmark = await self._run_performance_benchmark(equipment_id)
        func_results = await self._check_functionality(equipment_id)

        # Calculate health score
        health_score = self._calculate_health_score(
            connection_diag, comm_diag, perf_benchmark, func_results
        )

        # Determine overall status
        health_status = self._determine_health_status(health_score)

        # Collect issues and recommendations
        issues = []
        warnings = []
        recommendations = []

        if not connection_diag.is_connected:
            issues.append("Equipment is disconnected")
            recommendations.append("Check physical connections and power")

        if comm_diag.error_rate and comm_diag.error_rate > 5.0:
            warnings.append(f"High communication error rate: {comm_diag.error_rate:.1f}%")
            recommendations.append("Check cable quality and connection stability")

        if comm_diag.average_response_time_ms > 1000:
            warnings.append(f"Slow response time: {comm_diag.average_response_time_ms:.0f}ms")
            recommendations.append("Check network latency or equipment load")

        # Determine component statuses
        connection_status = DiagnosticStatus.PASS if connection_diag.is_connected else DiagnosticStatus.FAIL
        communication_status = self._get_communication_status(comm_diag)
        performance_status = self._get_performance_status(perf_benchmark)
        functionality_status = self._get_functionality_status(func_results)

        health = EquipmentHealth(
            equipment_id=equipment_id,
            health_status=health_status,
            health_score=health_score,
            connection_status=connection_status,
            communication_status=communication_status,
            performance_status=performance_status,
            functionality_status=functionality_status,
            connection_diagnostics=connection_diag,
            communication_diagnostics=comm_diag,
            performance_benchmark=perf_benchmark,
            active_issues=issues,
            warnings=warnings,
            recommendations=recommendations,
            test_results=func_results,
            passed_tests=len([r for r in func_results if r.status == DiagnosticStatus.PASS]),
            failed_tests=len([r for r in func_results if r.status == DiagnosticStatus.FAIL]),
            warning_tests=len([r for r in func_results if r.status == DiagnosticStatus.WARNING])
        )

        self._health_cache[equipment_id] = health
        return health

    async def _check_connection(self, equipment_id: str) -> ConnectionDiagnostics:
        """Check connection status and quality."""
        from equipment.manager import equipment_manager

        equipment = equipment_manager.get_equipment(equipment_id)
        stats = self._connection_stats[equipment_id]

        if not equipment:
            return ConnectionDiagnostics(
                equipment_id=equipment_id,
                is_connected=False
            )

        # Measure response time
        start = time.time()
        try:
            # Simple query to test connection
            await equipment.query("*IDN?")
            response_time_ms = (time.time() - start) * 1000
            is_connected = True
        except Exception as e:
            response_time_ms = None
            is_connected = False
            stats["errors"].append({"timestamp": datetime.now(), "error": str(e)})

        # Calculate uptime
        uptime = None
        if stats["last_connected"]:
            uptime = (datetime.now() - stats["last_connected"]).total_seconds()

        # Calculate error rate
        error_rate = None
        total_attempts = stats["connection_count"] + stats["disconnection_count"]
        if total_attempts > 0:
            error_rate = (stats["disconnection_count"] / total_attempts) * 100

        return ConnectionDiagnostics(
            equipment_id=equipment_id,
            is_connected=is_connected,
            connection_time=stats["last_connected"],
            disconnection_count=stats["disconnection_count"],
            last_error=stats["errors"][-1]["error"] if stats["errors"] else None,
            uptime_seconds=uptime,
            visa_resource=equipment.resource_name if hasattr(equipment, 'resource_name') else None,
            response_time_ms=response_time_ms,
            error_rate=error_rate
        )

    async def _check_communication(self, equipment_id: str) -> CommunicationDiagnostics:
        """Check communication quality and statistics."""
        stats = self._communication_stats[equipment_id]

        # Calculate statistics
        total = stats["total_commands"]
        successful = stats["successful"]
        failed = stats["failed"]

        response_times = stats["response_times"][-100:]  # Last 100
        avg_response = sum(response_times) / len(response_times) if response_times else 0
        min_response = min(response_times) if response_times else 0
        max_response = max(response_times) if response_times else 0

        # Calculate data transfer rate (simplified)
        data_rate = 0.0
        if stats["bytes_sent"] + stats["bytes_received"] > 0:
            # Assume over last hour or uptime
            time_window = 3600  # seconds
            total_bytes = stats["bytes_sent"] + stats["bytes_received"]
            data_rate = (total_bytes * 8) / time_window  # bits per second

        # Get recent errors
        error_history = []
        for err in stats.get("error_list", [])[-10:]:
            error_history.append(err)

        return CommunicationDiagnostics(
            equipment_id=equipment_id,
            total_commands=total,
            successful_commands=successful,
            failed_commands=failed,
            timeout_count=stats["timeouts"],
            retry_count=stats["retries"],
            average_response_time_ms=avg_response,
            min_response_time_ms=min_response,
            max_response_time_ms=max_response,
            bytes_sent=stats["bytes_sent"],
            bytes_received=stats["bytes_received"],
            data_transfer_rate_bps=data_rate,
            last_error=stats.get("last_error"),
            error_history=error_history
        )

    async def _run_performance_benchmark(self, equipment_id: str) -> Optional[PerformanceBenchmark]:
        """Run performance benchmarks on equipment."""
        from equipment.manager import equipment_manager

        equipment = equipment_manager.get_equipment(equipment_id)
        if not equipment:
            return None

        command_latencies = {}

        # Test common commands
        test_commands = ["*IDN?", "*OPC?", "*STB?"]
        for cmd in test_commands:
            try:
                start = time.time()
                await equipment.query(cmd)
                latency = (time.time() - start) * 1000
                command_latencies[cmd] = latency
            except Exception as e:
                logger.debug(f"Benchmark command {cmd} failed: {e}")
                command_latencies[cmd] = -1

        # Calculate throughput
        throughput = 0.0
        if command_latencies:
            valid_latencies = [l for l in command_latencies.values() if l > 0]
            if valid_latencies:
                avg_latency = sum(valid_latencies) / len(valid_latencies)
                throughput = 1000 / avg_latency if avg_latency > 0 else 0  # commands/sec

        # System resources
        cpu_usage = psutil.cpu_percent(interval=0.1)
        memory_info = psutil.virtual_memory()
        memory_usage = memory_info.used / (1024 * 1024)  # MB

        # Performance score (simplified)
        perf_score = 100.0
        if command_latencies:
            avg_latency = sum([l for l in command_latencies.values() if l > 0]) / len(command_latencies)
            # Penalize for slow responses
            if avg_latency > 100:
                perf_score -= min(50, (avg_latency - 100) / 10)

        benchmark = PerformanceBenchmark(
            equipment_id=equipment_id,
            command_latency_ms=command_latencies,
            throughput_commands_per_sec=throughput,
            cpu_usage_percent=cpu_usage,
            memory_usage_mb=memory_usage,
            performance_score=max(0, perf_score)
        )

        # Store in history
        self._benchmarks[equipment_id].append(benchmark)
        if len(self._benchmarks[equipment_id]) > self._max_benchmark_history:
            self._benchmarks[equipment_id].pop(0)

        return benchmark

    async def _check_functionality(self, equipment_id: str) -> List[DiagnosticResult]:
        """Run functionality tests on equipment."""
        from equipment.manager import equipment_manager

        equipment = equipment_manager.get_equipment(equipment_id)
        results = []

        if not equipment:
            return results

        # Test 1: IDN query
        result = await self._run_test(
            "IDN Query Test",
            equipment_id,
            lambda: equipment.query("*IDN?"),
            expected="Equipment responds to identification query"
        )
        results.append(result)

        # Test 2: OPC (Operation Complete)
        result = await self._run_test(
            "Operation Complete Test",
            equipment_id,
            lambda: equipment.query("*OPC?"),
            expected="Equipment responds to operation complete query"
        )
        results.append(result)

        # Test 3: Error query (if supported)
        result = await self._run_test(
            "Error Query Test",
            equipment_id,
            lambda: equipment.query("SYST:ERR?"),
            expected="Equipment can report errors"
        )
        results.append(result)

        return results

    async def _run_test(self, name: str, equipment_id: str, test_func, expected: str) -> DiagnosticResult:
        """Run a single diagnostic test."""
        started_at = datetime.now()

        try:
            start = time.time()
            result_value = await test_func()
            duration = time.time() - start

            return DiagnosticResult(
                test_id=f"test_{name.lower().replace(' ', '_')}",
                equipment_id=equipment_id,
                status=DiagnosticStatus.PASS,
                started_at=started_at,
                completed_at=datetime.now(),
                duration_seconds=duration,
                message=f"Test passed: {expected}",
                details={"result": str(result_value)}
            )

        except Exception as e:
            return DiagnosticResult(
                test_id=f"test_{name.lower().replace(' ', '_')}",
                equipment_id=equipment_id,
                status=DiagnosticStatus.FAIL,
                started_at=started_at,
                completed_at=datetime.now(),
                message=f"Test failed: {expected}",
                error=str(e)
            )

    def _calculate_health_score(
        self,
        connection: ConnectionDiagnostics,
        communication: CommunicationDiagnostics,
        performance: Optional[PerformanceBenchmark],
        func_results: List[DiagnosticResult]
    ) -> float:
        """Calculate overall health score (0-100)."""
        score = 0.0

        # Connection (30 points)
        if connection.is_connected:
            score += 30
            if connection.response_time_ms and connection.response_time_ms < 100:
                score += 10
            elif connection.response_time_ms and connection.response_time_ms < 500:
                score += 5

        # Communication (30 points)
        if communication.total_commands > 0:
            success_rate = (communication.successful_commands / communication.total_commands) * 100
            score += (success_rate / 100) * 30

        # Performance (20 points)
        if performance and performance.performance_score:
            score += (performance.performance_score / 100) * 20

        # Functionality (20 points)
        if func_results:
            passed = len([r for r in func_results if r.status == DiagnosticStatus.PASS])
            score += (passed / len(func_results)) * 20

        return min(100.0, max(0.0, score))

    def _determine_health_status(self, health_score: float) -> HealthStatus:
        """Determine health status from score."""
        if health_score >= 90:
            return HealthStatus.HEALTHY
        elif health_score >= 70:
            return HealthStatus.DEGRADED
        elif health_score >= 50:
            return HealthStatus.WARNING
        elif health_score > 0:
            return HealthStatus.CRITICAL
        else:
            return HealthStatus.OFFLINE

    def _get_communication_status(self, comm: CommunicationDiagnostics) -> DiagnosticStatus:
        """Get communication status from diagnostics."""
        if comm.total_commands == 0:
            return DiagnosticStatus.UNKNOWN

        success_rate = (comm.successful_commands / comm.total_commands) * 100
        if success_rate >= 95:
            return DiagnosticStatus.PASS
        elif success_rate >= 80:
            return DiagnosticStatus.WARNING
        else:
            return DiagnosticStatus.FAIL

    def _get_performance_status(self, perf: Optional[PerformanceBenchmark]) -> DiagnosticStatus:
        """Get performance status from benchmark."""
        if not perf or not perf.performance_score:
            return DiagnosticStatus.UNKNOWN

        if perf.performance_score >= 80:
            return DiagnosticStatus.PASS
        elif perf.performance_score >= 60:
            return DiagnosticStatus.WARNING
        else:
            return DiagnosticStatus.FAIL

    def _get_functionality_status(self, results: List[DiagnosticResult]) -> DiagnosticStatus:
        """Get functionality status from test results."""
        if not results:
            return DiagnosticStatus.UNKNOWN

        passed = len([r for r in results if r.status == DiagnosticStatus.PASS])
        pass_rate = (passed / len(results)) * 100

        if pass_rate >= 90:
            return DiagnosticStatus.PASS
        elif pass_rate >= 70:
            return DiagnosticStatus.WARNING
        else:
            return DiagnosticStatus.FAIL

    # ==================== Diagnostic Reports ====================

    async def generate_diagnostic_report(
        self,
        equipment_ids: Optional[List[str]] = None,
        categories: Optional[List[DiagnosticCategory]] = None
    ) -> DiagnosticReport:
        """Generate comprehensive diagnostic report."""
        from equipment.manager import equipment_manager

        started_at = datetime.now()

        # Default to all equipment
        if not equipment_ids:
            equipment_ids = list(equipment_manager._equipment.keys())

        # Run health checks on all equipment
        equipment_health = []
        for eq_id in equipment_ids:
            health = await self.check_equipment_health(eq_id)
            equipment_health.append(health)

        # Calculate statistics
        total_tests = sum(h.passed_tests + h.failed_tests + h.warning_tests for h in equipment_health)
        passed_tests = sum(h.passed_tests for h in equipment_health)
        failed_tests = sum(h.failed_tests for h in equipment_health)
        warning_tests = sum(h.warning_tests for h in equipment_health)

        # Collect issues
        critical_issues = []
        warnings = []
        recommendations = []

        for health in equipment_health:
            critical_issues.extend(health.active_issues)
            warnings.extend(health.warnings)
            recommendations.extend(health.recommendations)

        # Determine overall health
        if all(h.health_status == HealthStatus.HEALTHY for h in equipment_health):
            overall_health = HealthStatus.HEALTHY
        elif any(h.health_status == HealthStatus.CRITICAL for h in equipment_health):
            overall_health = HealthStatus.CRITICAL
        elif any(h.health_status == HealthStatus.WARNING for h in equipment_health):
            overall_health = HealthStatus.WARNING
        elif any(h.health_status == HealthStatus.DEGRADED for h in equipment_health):
            overall_health = HealthStatus.DEGRADED
        else:
            overall_health = HealthStatus.UNKNOWN

        completed_at = datetime.now()
        duration = (completed_at - started_at).total_seconds()

        return DiagnosticReport(
            equipment_ids=equipment_ids,
            categories=categories or list(DiagnosticCategory),
            equipment_health=equipment_health,
            overall_health=overall_health,
            total_tests=total_tests,
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            warning_tests=warning_tests,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            critical_issues=list(set(critical_issues)),
            warnings=list(set(warnings)),
            recommendations=list(set(recommendations))
        )

    async def get_system_diagnostics(self) -> SystemDiagnostics:
        """Get system-wide diagnostics."""
        from equipment.manager import equipment_manager

        # Equipment overview
        all_equipment = equipment_manager._equipment
        total_equipment = len(all_equipment)
        connected_equipment = len(equipment_manager.get_connected_devices())

        # Count by health status
        healthy = degraded = critical = 0
        equipment_health_status = {}

        for eq_id in all_equipment.keys():
            if eq_id in self._health_cache:
                health = self._health_cache[eq_id]
                equipment_health_status[eq_id] = health.health_status

                if health.health_status == HealthStatus.HEALTHY:
                    healthy += 1
                elif health.health_status == HealthStatus.DEGRADED:
                    degraded += 1
                elif health.health_status == HealthStatus.CRITICAL:
                    critical += 1

        # System resources
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        uptime = (datetime.now() - self._server_start_time).total_seconds()

        return SystemDiagnostics(
            total_equipment=total_equipment,
            connected_equipment=connected_equipment,
            disconnected_equipment=total_equipment - connected_equipment,
            healthy_equipment=healthy,
            degraded_equipment=degraded,
            critical_equipment=critical,
            server_cpu_percent=cpu_percent,
            server_memory_percent=memory.percent,
            server_disk_percent=disk.percent,
            server_uptime_seconds=uptime,
            equipment_health=equipment_health_status
        )

    # ==================== Enhanced Diagnostics (v0.12.0) ====================

    async def check_temperature(self, equipment_id: str) -> Optional[float]:
        """
        Check equipment temperature.

        Args:
            equipment_id: Equipment identifier

        Returns:
            Temperature in Celsius, or None if not supported
        """
        from equipment.manager import equipment_manager

        equipment = equipment_manager.get_equipment(equipment_id)
        if not equipment:
            return None

        try:
            temperature = await equipment.get_temperature()
            if temperature is not None:
                logger.debug(f"Equipment {equipment_id} temperature: {temperature}°C")
            return temperature
        except Exception as e:
            logger.error(f"Error checking temperature for {equipment_id}: {e}")
            return None

    async def check_error_codes(self, equipment_id: str) -> Dict[str, Any]:
        """
        Check equipment error codes and get interpretation.

        Args:
            equipment_id: Equipment identifier

        Returns:
            Dictionary with error information
        """
        from equipment.manager import equipment_manager
        from equipment.error_codes import get_error_code_db

        equipment = equipment_manager.get_equipment(equipment_id)
        if not equipment:
            return {"error": "Equipment not found"}

        try:
            error_code = await equipment.get_error_code()
            error_message = await equipment.get_error_message()

            if error_code is None:
                return {
                    "has_error": False,
                    "error_code": None,
                    "error_message": None
                }

            # Get detailed error information from database
            error_db = get_error_code_db()
            error_info = {}

            if error_db:
                # Determine vendor from equipment
                vendor = "standard"
                equipment_info = await equipment.get_info()
                if "rigol" in equipment_info.manufacturer.lower():
                    vendor = "rigol"
                elif "bk" in equipment_info.manufacturer.lower():
                    vendor = "bk_precision"

                error_info = error_db.get_troubleshooting_info(error_code, vendor)

            return {
                "has_error": True,
                "error_code": error_code,
                "error_message": error_message,
                "error_info": error_info
            }

        except Exception as e:
            logger.error(f"Error checking error codes for {equipment_id}: {e}")
            return {"error": str(e)}

    async def run_self_test(self, equipment_id: str) -> DiagnosticResult:
        """
        Run equipment built-in self-test.

        Args:
            equipment_id: Equipment identifier

        Returns:
            Diagnostic result
        """
        from equipment.manager import equipment_manager

        equipment = equipment_manager.get_equipment(equipment_id)
        started_at = datetime.now()

        if not equipment:
            return DiagnosticResult(
                test_id="self_test",
                equipment_id=equipment_id,
                status=DiagnosticStatus.ERROR,
                started_at=started_at,
                completed_at=datetime.now(),
                error="Equipment not found"
            )

        try:
            start_time = time.time()
            result = await equipment.run_self_test()
            duration = time.time() - start_time

            if result is None:
                return DiagnosticResult(
                    test_id="self_test",
                    equipment_id=equipment_id,
                    status=DiagnosticStatus.UNKNOWN,
                    started_at=started_at,
                    completed_at=datetime.now(),
                    duration_seconds=duration,
                    message="Self-test not supported by equipment"
                )

            passed = result.get("passed", False)
            status = DiagnosticStatus.PASS if passed else DiagnosticStatus.FAIL

            return DiagnosticResult(
                test_id="self_test",
                equipment_id=equipment_id,
                status=status,
                started_at=started_at,
                completed_at=datetime.now(),
                duration_seconds=duration,
                message=f"Self-test {'passed' if passed else 'failed'}",
                details=result
            )

        except Exception as e:
            return DiagnosticResult(
                test_id="self_test",
                equipment_id=equipment_id,
                status=DiagnosticStatus.ERROR,
                started_at=started_at,
                completed_at=datetime.now(),
                error=str(e)
            )

    async def check_calibration_status(self, equipment_id: str) -> Dict[str, Any]:
        """
        Check equipment calibration status.

        Args:
            equipment_id: Equipment identifier

        Returns:
            Dictionary with calibration status information
        """
        from equipment.calibration import get_calibration_manager

        cal_manager = get_calibration_manager()

        if not cal_manager:
            return {
                "error": "Calibration manager not initialized",
                "status": "unknown"
            }

        try:
            status = await cal_manager.get_calibration_status(equipment_id)
            latest_record = await cal_manager.get_latest_calibration(equipment_id)
            days_until_due = await cal_manager.get_days_until_due(equipment_id)
            is_current = await cal_manager.is_calibration_current(equipment_id)

            return {
                "status": status.value,
                "is_current": is_current,
                "days_until_due": days_until_due,
                "last_calibration_date": latest_record.calibration_date if latest_record else None,
                "next_due_date": latest_record.due_date if latest_record else None,
                "last_result": latest_record.result.value if latest_record else None
            }

        except Exception as e:
            logger.error(f"Error checking calibration status for {equipment_id}: {e}")
            return {"error": str(e), "status": "error"}

    async def get_equipment_diagnostics(self, equipment_id: str) -> Dict[str, Any]:
        """
        Get comprehensive diagnostic information for equipment.

        This includes temperature, error codes, calibration status, and operating hours.

        Args:
            equipment_id: Equipment identifier

        Returns:
            Dictionary with all diagnostic information
        """
        from equipment.manager import equipment_manager

        equipment = equipment_manager.get_equipment(equipment_id)

        if not equipment:
            return {"error": "Equipment not found"}

        # Gather all diagnostic data
        diagnostics = {
            "equipment_id": equipment_id,
            "timestamp": datetime.now(),
            "temperature_celsius": None,
            "operating_hours": None,
            "error_info": None,
            "calibration_status": None
        }

        try:
            # Temperature
            diagnostics["temperature_celsius"] = await self.check_temperature(equipment_id)

            # Operating hours
            operating_hours = await equipment.get_operating_hours()
            diagnostics["operating_hours"] = operating_hours

            # Error codes
            diagnostics["error_info"] = await self.check_error_codes(equipment_id)

            # Calibration status
            diagnostics["calibration_status"] = await self.check_calibration_status(equipment_id)

        except Exception as e:
            logger.error(f"Error gathering diagnostics for {equipment_id}: {e}")
            diagnostics["error"] = str(e)

        return diagnostics

    # ==================== Statistics Tracking ====================

    def record_connection(self, equipment_id: str):
        """Record equipment connection."""
        stats = self._connection_stats[equipment_id]
        stats["connection_count"] += 1
        stats["last_connected"] = datetime.now()

    def record_disconnection(self, equipment_id: str, error: Optional[str] = None):
        """Record equipment disconnection."""
        stats = self._connection_stats[equipment_id]
        stats["disconnection_count"] += 1
        if error:
            stats["errors"].append({"timestamp": datetime.now(), "error": error})

    def record_command(
        self,
        equipment_id: str,
        success: bool,
        response_time_ms: float,
        bytes_sent: int = 0,
        bytes_received: int = 0,
        error: Optional[str] = None
    ):
        """Record command execution statistics."""
        stats = self._communication_stats[equipment_id]
        stats["total_commands"] += 1

        if success:
            stats["successful"] += 1
        else:
            stats["failed"] += 1
            if error:
                if "error_list" not in stats:
                    stats["error_list"] = []
                stats["error_list"].append({
                    "timestamp": datetime.now(),
                    "error": error
                })
                stats["last_error"] = error

        stats["response_times"].append(response_time_ms)
        if len(stats["response_times"]) > 1000:
            stats["response_times"] = stats["response_times"][-1000:]

        stats["bytes_sent"] += bytes_sent
        stats["bytes_received"] += bytes_received

    def get_health_cache(self, equipment_id: str) -> Optional[EquipmentHealth]:
        """Get cached health status."""
        return self._health_cache.get(equipment_id)

    def get_benchmark_history(
        self,
        equipment_id: str,
        limit: int = 100
    ) -> List[PerformanceBenchmark]:
        """Get benchmark history for equipment."""
        benchmarks = self._benchmarks.get(equipment_id, [])
        return benchmarks[-limit:]


# Global diagnostics manager
diagnostics_manager = DiagnosticsManager()
