"""Diagnostics data models."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DiagnosticStatus(str, Enum):
    """Diagnostic test status."""

    UNKNOWN = "unknown"
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    ERROR = "error"
    RUNNING = "running"
    PENDING = "pending"


class DiagnosticCategory(str, Enum):
    """Category of diagnostic test."""

    CONNECTION = "connection"
    COMMUNICATION = "communication"
    PERFORMANCE = "performance"
    FUNCTIONALITY = "functionality"
    CALIBRATION = "calibration"
    SAFETY = "safety"
    SYSTEM = "system"


class HealthStatus(str, Enum):
    """Overall equipment health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    WARNING = "warning"
    CRITICAL = "critical"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class DiagnosticTest(BaseModel):
    """A single diagnostic test configuration."""

    test_id: str = Field(default_factory=lambda: f"test_{uuid.uuid4().hex[:8]}")
    name: str = Field(..., description="Test name")
    description: Optional[str] = Field(None, description="Test description")
    category: DiagnosticCategory = Field(..., description="Test category")
    equipment_id: Optional[str] = Field(None, description="Target equipment ID")

    # Test parameters
    timeout_seconds: int = Field(default=30, description="Test timeout")
    retry_count: int = Field(default=3, description="Number of retries")
    threshold_warning: Optional[float] = Field(None, description="Warning threshold")
    threshold_critical: Optional[float] = Field(None, description="Critical threshold")

    # Metadata
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.now)
    last_run: Optional[datetime] = Field(None)


class DiagnosticResult(BaseModel):
    """Result of a diagnostic test execution."""

    result_id: str = Field(default_factory=lambda: f"result_{uuid.uuid4().hex[:8]}")
    test_id: str = Field(..., description="Associated test ID")
    equipment_id: Optional[str] = Field(None, description="Equipment ID")

    # Execution details
    status: DiagnosticStatus = Field(..., description="Test status")
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = Field(None)
    duration_seconds: Optional[float] = Field(None)

    # Results
    value: Optional[float] = Field(None, description="Measured value")
    expected_value: Optional[float] = Field(None, description="Expected value")
    tolerance: Optional[float] = Field(None, description="Acceptable tolerance")

    # Details
    message: Optional[str] = Field(None, description="Result message")
    details: Dict[str, Any] = Field(
        default_factory=dict, description="Additional details"
    )
    error: Optional[str] = Field(None, description="Error message if failed")

    # Recommendations
    recommendations: List[str] = Field(
        default_factory=list, description="Recommendations"
    )


class ConnectionDiagnostics(BaseModel):
    """Connection diagnostic results."""

    equipment_id: str
    is_connected: bool
    connection_time: Optional[datetime] = None
    disconnection_count: int = 0
    last_error: Optional[str] = None
    uptime_seconds: Optional[float] = None

    # VISA details
    visa_resource: Optional[str] = None
    visa_interface_type: Optional[str] = None
    timeout_ms: Optional[int] = None

    # Connection quality
    response_time_ms: Optional[float] = None
    packet_loss_percent: Optional[float] = None
    error_rate: Optional[float] = None


class CommunicationDiagnostics(BaseModel):
    """Communication diagnostic results."""

    equipment_id: str

    # Command statistics
    total_commands: int = 0
    successful_commands: int = 0
    failed_commands: int = 0
    timeout_count: int = 0
    retry_count: int = 0

    # Performance metrics
    average_response_time_ms: float = 0.0
    min_response_time_ms: float = 0.0
    max_response_time_ms: float = 0.0

    # Data transfer
    bytes_sent: int = 0
    bytes_received: int = 0
    data_transfer_rate_bps: float = 0.0

    # Errors
    last_error: Optional[str] = None
    error_history: List[Dict[str, Any]] = Field(default_factory=list)
    error_rate: Optional[float] = None  # Percentage of failed commands


class PerformanceBenchmark(BaseModel):
    """Performance benchmark results."""

    benchmark_id: str = Field(default_factory=lambda: f"bench_{uuid.uuid4().hex[:8]}")
    equipment_id: str
    timestamp: datetime = Field(default_factory=datetime.now)

    # Command performance
    command_latency_ms: Dict[str, float] = Field(default_factory=dict)
    throughput_commands_per_sec: float = 0.0

    # Data acquisition performance
    sample_rate_hz: Optional[float] = None
    data_transfer_rate_mbps: Optional[float] = None
    buffer_fill_time_ms: Optional[float] = None

    # Resource usage
    cpu_usage_percent: Optional[float] = None
    memory_usage_mb: Optional[float] = None

    # Comparison to baseline
    baseline_deviation_percent: Optional[float] = None
    performance_score: Optional[float] = None  # 0-100


class EquipmentHealth(BaseModel):
    """Overall equipment health assessment."""

    equipment_id: str
    timestamp: datetime = Field(default_factory=datetime.now)

    # Overall status
    health_status: HealthStatus = Field(..., description="Overall health")
    health_score: float = Field(..., description="Health score 0-100")

    # Component statuses
    connection_status: DiagnosticStatus = DiagnosticStatus.UNKNOWN
    communication_status: DiagnosticStatus = DiagnosticStatus.UNKNOWN
    performance_status: DiagnosticStatus = DiagnosticStatus.UNKNOWN
    functionality_status: DiagnosticStatus = DiagnosticStatus.UNKNOWN

    # Diagnostics
    connection_diagnostics: Optional[ConnectionDiagnostics] = None
    communication_diagnostics: Optional[CommunicationDiagnostics] = None
    performance_benchmark: Optional[PerformanceBenchmark] = None

    # Issues
    active_issues: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)

    # Test results
    test_results: List[DiagnosticResult] = Field(default_factory=list)
    passed_tests: int = 0
    failed_tests: int = 0
    warning_tests: int = 0


class DiagnosticReport(BaseModel):
    """Comprehensive diagnostic report."""

    report_id: str = Field(default_factory=lambda: f"report_{uuid.uuid4().hex[:8]}")
    timestamp: datetime = Field(default_factory=datetime.now)

    # Scope
    equipment_ids: List[str] = Field(default_factory=list)
    categories: List[DiagnosticCategory] = Field(default_factory=list)

    # Results
    equipment_health: List[EquipmentHealth] = Field(default_factory=list)
    overall_health: HealthStatus = Field(..., description="System-wide health")

    # Statistics
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    warning_tests: int = 0

    # Duration
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    # Summary
    critical_issues: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class SystemDiagnostics(BaseModel):
    """System-wide diagnostics."""

    timestamp: datetime = Field(default_factory=datetime.now)

    # Equipment overview
    total_equipment: int = 0
    connected_equipment: int = 0
    disconnected_equipment: int = 0
    healthy_equipment: int = 0
    degraded_equipment: int = 0
    critical_equipment: int = 0

    # System resources
    server_cpu_percent: Optional[float] = None
    server_memory_percent: Optional[float] = None
    server_disk_percent: Optional[float] = None
    server_uptime_seconds: Optional[float] = None

    # API statistics
    total_api_calls: int = 0
    failed_api_calls: int = 0
    average_response_time_ms: float = 0.0

    # Health status by equipment
    equipment_health: Dict[str, HealthStatus] = Field(default_factory=dict)
