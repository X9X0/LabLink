"""Performance monitoring data models."""

from enum import Enum
from typing import Optional, Dict, List, Any
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


class TrendDirection(str, Enum):
    """Direction of performance trend."""
    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class PerformanceStatus(str, Enum):
    """Overall performance status."""
    EXCELLENT = "excellent"  # Performance above baseline
    GOOD = "good"  # Performance at baseline
    DEGRADED = "degraded"  # Performance below baseline but acceptable
    POOR = "poor"  # Performance significantly degraded
    CRITICAL = "critical"  # Performance critically degraded
    UNKNOWN = "unknown"  # Cannot determine status


class MetricType(str, Enum):
    """Types of performance metrics."""
    LATENCY = "latency"  # Command response time
    THROUGHPUT = "throughput"  # Commands per second
    ERROR_RATE = "error_rate"  # Percentage of failed commands
    CPU_USAGE = "cpu_usage"  # CPU utilization percentage
    MEMORY_USAGE = "memory_usage"  # Memory utilization percentage
    BANDWIDTH = "bandwidth"  # Data transfer rate
    QUEUE_DEPTH = "queue_depth"  # Command queue depth


class PerformanceBaseline(BaseModel):
    """Performance baseline for an equipment or system component."""
    baseline_id: str = Field(default_factory=lambda: f"baseline_{uuid.uuid4().hex[:12]}")
    equipment_id: Optional[str] = Field(None, description="Equipment ID (None for system-wide)")
    component: str = Field(..., description="Component being monitored")
    
    # Baseline metrics
    avg_latency_ms: float = Field(..., description="Average command latency in ms")
    p95_latency_ms: float = Field(..., description="95th percentile latency in ms")
    p99_latency_ms: float = Field(..., description="99th percentile latency in ms")
    avg_throughput: float = Field(..., description="Average throughput (commands/sec)")
    error_rate_percent: float = Field(default=0.0, description="Baseline error rate %")
    
    # Thresholds for alerting
    latency_warning_threshold_ms: float = Field(..., description="Latency warning threshold")
    latency_critical_threshold_ms: float = Field(..., description="Latency critical threshold")
    throughput_warning_threshold: float = Field(..., description="Throughput warning threshold")
    error_rate_warning_threshold: float = Field(default=5.0, description="Error rate warning %")
    error_rate_critical_threshold: float = Field(default=10.0, description="Error rate critical %")
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    sample_count: int = Field(..., description="Number of samples used for baseline")
    measurement_period_hours: float = Field(..., description="Measurement period in hours")
    confidence_level: float = Field(default=0.95, description="Statistical confidence level")
    
    # Environmental context
    notes: Optional[str] = Field(None, description="Additional notes")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")


class PerformanceMetric(BaseModel):
    """A single performance metric measurement."""
    metric_id: str = Field(default_factory=lambda: f"metric_{uuid.uuid4().hex[:12]}")
    equipment_id: Optional[str] = Field(None, description="Equipment ID")
    component: str = Field(..., description="Component being monitored")
    metric_type: MetricType = Field(..., description="Type of metric")
    
    # Measurement
    value: float = Field(..., description="Metric value")
    unit: str = Field(..., description="Unit of measurement")
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # Context
    operation: Optional[str] = Field(None, description="Operation being measured")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    # Comparison to baseline
    baseline_id: Optional[str] = Field(None, description="Associated baseline ID")
    deviation_percent: Optional[float] = Field(None, description="% deviation from baseline")
    within_threshold: Optional[bool] = Field(None, description="Within acceptable threshold")


class PerformanceTrend(BaseModel):
    """Performance trend analysis results."""
    trend_id: str = Field(default_factory=lambda: f"trend_{uuid.uuid4().hex[:12]}")
    equipment_id: Optional[str] = Field(None, description="Equipment ID")
    component: str = Field(..., description="Component being analyzed")
    
    # Trend analysis
    direction: TrendDirection = Field(..., description="Trend direction")
    slope: float = Field(..., description="Trend slope (change per hour)")
    correlation: float = Field(..., description="Correlation coefficient (-1 to 1)")
    confidence: float = Field(..., description="Confidence in trend (0 to 1)")
    
    # Time period
    start_time: datetime = Field(..., description="Analysis start time")
    end_time: datetime = Field(..., description="Analysis end time")
    sample_count: int = Field(..., description="Number of samples analyzed")
    
    # Statistical summary
    mean_value: float = Field(..., description="Mean value over period")
    std_deviation: float = Field(..., description="Standard deviation")
    min_value: float = Field(..., description="Minimum value")
    max_value: float = Field(..., description="Maximum value")
    
    # Baseline comparison
    baseline_mean: Optional[float] = Field(None, description="Baseline mean value")
    deviation_from_baseline: Optional[float] = Field(None, description="% deviation from baseline")
    
    # Predictions
    predicted_value_1h: Optional[float] = Field(None, description="Predicted value in 1 hour")
    predicted_value_24h: Optional[float] = Field(None, description="Predicted value in 24 hours")
    time_to_threshold: Optional[float] = Field(None, description="Hours until threshold breach")
    
    # Analysis timestamp
    analyzed_at: datetime = Field(default_factory=datetime.now)


class PerformanceAlert(BaseModel):
    """Performance-related alert."""
    alert_id: str = Field(default_factory=lambda: f"perf_alert_{uuid.uuid4().hex[:12]}")
    equipment_id: Optional[str] = Field(None, description="Equipment ID")
    component: str = Field(..., description="Component with performance issue")
    
    # Alert details
    severity: str = Field(..., description="Alert severity (warning, critical)")
    metric_type: MetricType = Field(..., description="Metric that triggered alert")
    current_value: float = Field(..., description="Current metric value")
    threshold_value: float = Field(..., description="Threshold that was breached")
    baseline_value: Optional[float] = Field(None, description="Baseline value")
    
    # Trend information
    trend_direction: Optional[TrendDirection] = Field(None, description="Current trend")
    degradation_percent: float = Field(..., description="% degradation from baseline")
    
    # Message and recommendations
    message: str = Field(..., description="Alert message")
    recommendations: List[str] = Field(default_factory=list, description="Recommended actions")
    
    # Status
    triggered_at: datetime = Field(default_factory=datetime.now)
    acknowledged_at: Optional[datetime] = Field(None, description="When alert was acknowledged")
    resolved_at: Optional[datetime] = Field(None, description="When issue was resolved")
    active: bool = Field(default=True, description="Whether alert is active")


class PerformanceReport(BaseModel):
    """Comprehensive performance analysis report."""
    report_id: str = Field(default_factory=lambda: f"perf_report_{uuid.uuid4().hex[:12]}")
    
    # Scope
    equipment_ids: List[str] = Field(default_factory=list, description="Equipment included")
    components: List[str] = Field(default_factory=list, description="Components analyzed")
    
    # Time period
    start_time: datetime = Field(..., description="Report start time")
    end_time: datetime = Field(..., description="Report end time")
    generated_at: datetime = Field(default_factory=datetime.now)
    
    # Overall status
    overall_status: PerformanceStatus = Field(..., description="Overall performance status")
    health_score: float = Field(..., description="Overall performance health (0-100)")
    
    # Summary statistics
    total_measurements: int = Field(default=0, description="Total measurements analyzed")
    avg_latency_ms: float = Field(default=0.0, description="Average latency")
    avg_throughput: float = Field(default=0.0, description="Average throughput")
    error_rate_percent: float = Field(default=0.0, description="Error rate")
    
    # Comparison to baseline
    latency_vs_baseline_percent: Optional[float] = Field(None, description="Latency vs baseline %")
    throughput_vs_baseline_percent: Optional[float] = Field(None, description="Throughput vs baseline %")
    
    # Trends
    latency_trend: Optional[TrendDirection] = Field(None, description="Latency trend")
    throughput_trend: Optional[TrendDirection] = Field(None, description="Throughput trend")
    error_rate_trend: Optional[TrendDirection] = Field(None, description="Error rate trend")
    
    # Issues and recommendations
    active_alerts: int = Field(default=0, description="Number of active alerts")
    degraded_components: List[str] = Field(default_factory=list, description="Components with degraded performance")
    critical_components: List[str] = Field(default_factory=list, description="Components with critical performance")
    recommendations: List[str] = Field(default_factory=list, description="Performance improvement recommendations")
    
    # Detailed data
    component_performance: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-component performance details"
    )
    trend_analyses: List[PerformanceTrend] = Field(default_factory=list, description="Trend analyses")
    alerts: List[PerformanceAlert] = Field(default_factory=list, description="Active alerts")


class PerformanceThresholds(BaseModel):
    """Performance threshold configuration."""
    equipment_id: Optional[str] = Field(None, description="Equipment ID (None for system-wide)")
    component: str = Field(..., description="Component name")
    
    # Latency thresholds (milliseconds)
    latency_warning_ms: float = Field(default=100.0, description="Latency warning threshold")
    latency_critical_ms: float = Field(default=500.0, description="Latency critical threshold")
    
    # Throughput thresholds (commands/sec)
    throughput_warning: float = Field(default=10.0, description="Throughput warning threshold")
    throughput_critical: float = Field(default=5.0, description="Throughput critical threshold")
    
    # Error rate thresholds (percentage)
    error_rate_warning: float = Field(default=5.0, description="Error rate warning %")
    error_rate_critical: float = Field(default=10.0, description="Error rate critical %")
    
    # Degradation thresholds (percentage from baseline)
    degradation_warning: float = Field(default=20.0, description="Performance degradation warning %")
    degradation_critical: float = Field(default=50.0, description="Performance degradation critical %")
    
    # Measurement window
    measurement_window_minutes: int = Field(default=60, description="Measurement window in minutes")
    min_samples_required: int = Field(default=10, description="Minimum samples for analysis")
