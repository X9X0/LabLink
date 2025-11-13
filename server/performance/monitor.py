"""
Performance Monitor
===================

Collects, stores, and analyzes performance metrics with baseline tracking
and degradation detection.
"""

import logging
import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from collections import defaultdict
import statistics

from .models import (
    PerformanceBaseline,
    PerformanceMetric,
    PerformanceTrend,
    PerformanceAlert,
    PerformanceThresholds,
    MetricType,
    TrendDirection,
    PerformanceStatus,
)

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """Monitors and tracks equipment and system performance."""

    def __init__(self, db_path: str = "data/performance.db"):
        """
        Initialize performance monitor.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._baselines: Dict[str, PerformanceBaseline] = {}
        self._thresholds: Dict[str, PerformanceThresholds] = {}
        self._active_alerts: Dict[str, PerformanceAlert] = {}
        
        # Initialize database
        self._init_database()
        self._load_baselines()
        self._load_thresholds()
        
        logger.info(f"Performance monitor initialized with database: {self.db_path}")

    def _init_database(self):
        """Initialize SQLite database schema."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Performance metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS performance_metrics (
                metric_id TEXT PRIMARY KEY,
                equipment_id TEXT,
                component TEXT NOT NULL,
                metric_type TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                operation TEXT,
                metadata TEXT,
                baseline_id TEXT,
                deviation_percent REAL,
                within_threshold INTEGER
            )
        """)
        
        # Performance baselines table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS performance_baselines (
                baseline_id TEXT PRIMARY KEY,
                equipment_id TEXT,
                component TEXT NOT NULL,
                avg_latency_ms REAL NOT NULL,
                p95_latency_ms REAL NOT NULL,
                p99_latency_ms REAL NOT NULL,
                avg_throughput REAL NOT NULL,
                error_rate_percent REAL DEFAULT 0.0,
                latency_warning_threshold_ms REAL NOT NULL,
                latency_critical_threshold_ms REAL NOT NULL,
                throughput_warning_threshold REAL NOT NULL,
                error_rate_warning_threshold REAL DEFAULT 5.0,
                error_rate_critical_threshold REAL DEFAULT 10.0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                sample_count INTEGER NOT NULL,
                measurement_period_hours REAL NOT NULL,
                confidence_level REAL DEFAULT 0.95,
                notes TEXT,
                tags TEXT
            )
        """)
        
        # Performance alerts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS performance_alerts (
                alert_id TEXT PRIMARY KEY,
                equipment_id TEXT,
                component TEXT NOT NULL,
                severity TEXT NOT NULL,
                metric_type TEXT NOT NULL,
                current_value REAL NOT NULL,
                threshold_value REAL NOT NULL,
                baseline_value REAL,
                trend_direction TEXT,
                degradation_percent REAL NOT NULL,
                message TEXT NOT NULL,
                recommendations TEXT,
                triggered_at TEXT NOT NULL,
                acknowledged_at TEXT,
                resolved_at TEXT,
                active INTEGER DEFAULT 1
            )
        """)
        
        # Create indexes for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_metrics_timestamp 
            ON performance_metrics(timestamp DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_metrics_equipment 
            ON performance_metrics(equipment_id, component, timestamp DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_active 
            ON performance_alerts(active, triggered_at DESC)
        """)
        
        conn.commit()
        conn.close()
        
        logger.info("Performance database schema initialized")

    def _load_baselines(self):
        """Load baselines from database."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM performance_baselines")
        rows = cursor.fetchall()
        
        for row in rows:
            baseline = PerformanceBaseline(
                baseline_id=row[0],
                equipment_id=row[1],
                component=row[2],
                avg_latency_ms=row[3],
                p95_latency_ms=row[4],
                p99_latency_ms=row[5],
                avg_throughput=row[6],
                error_rate_percent=row[7],
                latency_warning_threshold_ms=row[8],
                latency_critical_threshold_ms=row[9],
                throughput_warning_threshold=row[10],
                error_rate_warning_threshold=row[11],
                error_rate_critical_threshold=row[12],
                created_at=datetime.fromisoformat(row[13]),
                updated_at=datetime.fromisoformat(row[14]),
                sample_count=row[15],
                measurement_period_hours=row[16],
                confidence_level=row[17],
                notes=row[18],
                tags=json.loads(row[19]) if row[19] else []
            )
            
            key = f"{baseline.equipment_id}:{baseline.component}"
            self._baselines[key] = baseline
        
        conn.close()
        logger.info(f"Loaded {len(self._baselines)} performance baselines")

    def _load_thresholds(self):
        """Load default thresholds."""
        # Create default thresholds for common components
        default_thresholds = [
            PerformanceThresholds(component="equipment_commands"),
            PerformanceThresholds(component="api_requests"),
            PerformanceThresholds(component="data_acquisition"),
        ]
        
        for threshold in default_thresholds:
            key = f"{threshold.equipment_id}:{threshold.component}"
            self._thresholds[key] = threshold

    # ==================== Metric Recording ====================

    async def record_metric(self, metric: PerformanceMetric) -> PerformanceMetric:
        """
        Record a performance metric.

        Args:
            metric: Performance metric to record

        Returns:
            Recorded metric with baseline comparison
        """
        # Compare to baseline if available
        key = f"{metric.equipment_id}:{metric.component}"
        baseline = self._baselines.get(key)
        
        if baseline:
            metric.baseline_id = baseline.baseline_id
            
            # Calculate deviation based on metric type
            if metric.metric_type == MetricType.LATENCY:
                baseline_value = baseline.avg_latency_ms
                threshold = baseline.latency_warning_threshold_ms
            elif metric.metric_type == MetricType.THROUGHPUT:
                baseline_value = baseline.avg_throughput
                threshold = baseline.throughput_warning_threshold
            elif metric.metric_type == MetricType.ERROR_RATE:
                baseline_value = baseline.error_rate_percent
                threshold = baseline.error_rate_warning_threshold
            else:
                baseline_value = None
                threshold = None
            
            if baseline_value is not None:
                metric.deviation_percent = ((metric.value - baseline_value) / baseline_value) * 100
                metric.within_threshold = abs(metric.value - baseline_value) <= threshold
                
                # Check for performance degradation
                await self._check_degradation(metric, baseline)
        
        # Store in database
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO performance_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            metric.metric_id,
            metric.equipment_id,
            metric.component,
            metric.metric_type.value,
            metric.value,
            metric.unit,
            metric.timestamp.isoformat(),
            metric.operation,
            json.dumps(metric.metadata),
            metric.baseline_id,
            metric.deviation_percent,
            1 if metric.within_threshold else 0 if metric.within_threshold is not None else None
        ))
        
        conn.commit()
        conn.close()
        
        return metric

    async def _check_degradation(self, metric: PerformanceMetric, baseline: PerformanceBaseline):
        """Check for performance degradation and create alerts if needed."""
        if metric.deviation_percent is None:
            return
        
        # Determine if degradation is significant
        degradation = abs(metric.deviation_percent)
        
        # Get thresholds
        key = f"{metric.equipment_id}:{metric.component}"
        thresholds = self._thresholds.get(key, PerformanceThresholds(component=metric.component))
        
        severity = None
        if degradation >= thresholds.degradation_critical:
            severity = "critical"
        elif degradation >= thresholds.degradation_warning:
            severity = "warning"
        
        if severity:
            # Create or update alert
            await self._create_performance_alert(
                equipment_id=metric.equipment_id,
                component=metric.component,
                severity=severity,
                metric_type=metric.metric_type,
                current_value=metric.value,
                baseline_value=baseline.avg_latency_ms if metric.metric_type == MetricType.LATENCY else baseline.avg_throughput,
                degradation_percent=degradation,
                thresholds=thresholds
            )

    async def _create_performance_alert(
        self,
        equipment_id: Optional[str],
        component: str,
        severity: str,
        metric_type: MetricType,
        current_value: float,
        baseline_value: float,
        degradation_percent: float,
        thresholds: PerformanceThresholds
    ):
        """Create a performance alert."""
        # Check if alert already exists
        alert_key = f"{equipment_id}:{component}:{metric_type.value}"
        existing_alert = self._active_alerts.get(alert_key)
        
        if existing_alert and existing_alert.active:
            # Update existing alert
            existing_alert.current_value = current_value
            existing_alert.degradation_percent = degradation_percent
            return
        
        # Create new alert
        message = f"{component} performance degraded by {degradation_percent:.1f}%"
        recommendations = self._get_recommendations(metric_type, degradation_percent)
        
        alert = PerformanceAlert(
            equipment_id=equipment_id,
            component=component,
            severity=severity,
            metric_type=metric_type,
            current_value=current_value,
            threshold_value=thresholds.latency_warning_ms if metric_type == MetricType.LATENCY else thresholds.throughput_warning,
            baseline_value=baseline_value,
            degradation_percent=degradation_percent,
            message=message,
            recommendations=recommendations
        )
        
        # Store alert
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO performance_alerts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            alert.alert_id,
            alert.equipment_id,
            alert.component,
            alert.severity,
            alert.metric_type.value,
            alert.current_value,
            alert.threshold_value,
            alert.baseline_value,
            alert.trend_direction.value if alert.trend_direction else None,
            alert.degradation_percent,
            alert.message,
            json.dumps(alert.recommendations),
            alert.triggered_at.isoformat(),
            alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
            alert.resolved_at.isoformat() if alert.resolved_at else None,
            1 if alert.active else 0
        ))
        
        conn.commit()
        conn.close()
        
        self._active_alerts[alert_key] = alert
        logger.warning(f"Performance alert created: {message}")

    def _get_recommendations(self, metric_type: MetricType, degradation: float) -> List[str]:
        """Get performance improvement recommendations."""
        recommendations = []
        
        if metric_type == MetricType.LATENCY:
            if degradation > 50:
                recommendations.extend([
                    "Check equipment connection quality",
                    "Verify network latency and bandwidth",
                    "Review equipment load and command queue depth",
                    "Consider equipment restart if issue persists"
                ])
            else:
                recommendations.extend([
                    "Monitor trend - may require investigation if continues",
                    "Check for network congestion",
                    "Review recent configuration changes"
                ])
        
        elif metric_type == MetricType.THROUGHPUT:
            recommendations.extend([
                "Check for resource bottlenecks (CPU, memory, network)",
                "Review command batching and parallelization",
                "Verify equipment is not overloaded"
            ])
        
        elif metric_type == MetricType.ERROR_RATE:
            recommendations.extend([
                "Review error logs for patterns",
                "Check equipment status and health",
                "Verify command syntax and parameters",
                "Consider equipment recalibration"
            ])
        
        return recommendations

    # ==================== Baseline Management ====================

    async def create_baseline(
        self,
        equipment_id: Optional[str],
        component: str,
        measurement_period_hours: float = 24.0
    ) -> PerformanceBaseline:
        """
        Create performance baseline from historical data.

        Args:
            equipment_id: Equipment ID (None for system-wide)
            component: Component name
            measurement_period_hours: Hours of data to analyze

        Returns:
            Created baseline
        """
        # Get historical metrics
        cutoff_time = datetime.now() - timedelta(hours=measurement_period_hours)
        metrics = await self.get_metrics(
            equipment_id=equipment_id,
            component=component,
            start_time=cutoff_time
        )
        
        if len(metrics) < 10:
            raise ValueError(f"Insufficient data for baseline (need 10+, got {len(metrics)})")
        
        # Calculate statistics
        latencies = [m.value for m in metrics if m.metric_type == MetricType.LATENCY]
        throughputs = [m.value for m in metrics if m.metric_type == MetricType.THROUGHPUT]
        error_rates = [m.value for m in metrics if m.metric_type == MetricType.ERROR_RATE]
        
        if not latencies:
            raise ValueError("No latency metrics found for baseline")
        
        # Calculate percentiles
        latencies_sorted = sorted(latencies)
        p95_index = int(len(latencies_sorted) * 0.95)
        p99_index = int(len(latencies_sorted) * 0.99)
        
        # Create baseline
        baseline = PerformanceBaseline(
            equipment_id=equipment_id,
            component=component,
            avg_latency_ms=statistics.mean(latencies),
            p95_latency_ms=latencies_sorted[p95_index],
            p99_latency_ms=latencies_sorted[p99_index],
            avg_throughput=statistics.mean(throughputs) if throughputs else 0.0,
            error_rate_percent=statistics.mean(error_rates) if error_rates else 0.0,
            latency_warning_threshold_ms=latencies_sorted[p95_index] * 1.5,
            latency_critical_threshold_ms=latencies_sorted[p95_index] * 2.0,
            throughput_warning_threshold=statistics.mean(throughputs) * 0.7 if throughputs else 10.0,
            sample_count=len(metrics),
            measurement_period_hours=measurement_period_hours
        )
        
        # Store baseline
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO performance_baselines VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            baseline.baseline_id,
            baseline.equipment_id,
            baseline.component,
            baseline.avg_latency_ms,
            baseline.p95_latency_ms,
            baseline.p99_latency_ms,
            baseline.avg_throughput,
            baseline.error_rate_percent,
            baseline.latency_warning_threshold_ms,
            baseline.latency_critical_threshold_ms,
            baseline.throughput_warning_threshold,
            baseline.error_rate_warning_threshold,
            baseline.error_rate_critical_threshold,
            baseline.created_at.isoformat(),
            baseline.updated_at.isoformat(),
            baseline.sample_count,
            baseline.measurement_period_hours,
            baseline.confidence_level,
            baseline.notes,
            json.dumps(baseline.tags)
        ))
        
        conn.commit()
        conn.close()
        
        # Cache baseline
        key = f"{equipment_id}:{component}"
        self._baselines[key] = baseline
        
        logger.info(f"Created performance baseline for {component}: {baseline.baseline_id}")
        
        return baseline

    async def get_baseline(
        self,
        equipment_id: Optional[str],
        component: str
    ) -> Optional[PerformanceBaseline]:
        """Get performance baseline for component."""
        key = f"{equipment_id}:{component}"
        return self._baselines.get(key)

    # ==================== Metric Retrieval ====================

    async def get_metrics(
        self,
        equipment_id: Optional[str] = None,
        component: Optional[str] = None,
        metric_type: Optional[MetricType] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[PerformanceMetric]:
        """
        Retrieve performance metrics with filtering.

        Args:
            equipment_id: Filter by equipment ID
            component: Filter by component
            metric_type: Filter by metric type
            start_time: Start time for query
            end_time: End time for query
            limit: Maximum number of results

        Returns:
            List of performance metrics
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        query = "SELECT * FROM performance_metrics WHERE 1=1"
        params = []
        
        if equipment_id is not None:
            query += " AND equipment_id = ?"
            params.append(equipment_id)
        
        if component:
            query += " AND component = ?"
            params.append(component)
        
        if metric_type:
            query += " AND metric_type = ?"
            params.append(metric_type.value)
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        metrics = []
        for row in rows:
            metric = PerformanceMetric(
                metric_id=row[0],
                equipment_id=row[1],
                component=row[2],
                metric_type=MetricType(row[3]),
                value=row[4],
                unit=row[5],
                timestamp=datetime.fromisoformat(row[6]),
                operation=row[7],
                metadata=json.loads(row[8]) if row[8] else {},
                baseline_id=row[9],
                deviation_percent=row[10],
                within_threshold=bool(row[11]) if row[11] is not None else None
            )
            metrics.append(metric)
        
        return metrics

    # ==================== Alert Management ====================

    async def get_active_alerts(
        self,
        equipment_id: Optional[str] = None,
        severity: Optional[str] = None
    ) -> List[PerformanceAlert]:
        """Get active performance alerts."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        query = "SELECT * FROM performance_alerts WHERE active = 1"
        params = []
        
        if equipment_id:
            query += " AND equipment_id = ?"
            params.append(equipment_id)
        
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        
        query += " ORDER BY triggered_at DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        alerts = []
        for row in rows:
            alert = PerformanceAlert(
                alert_id=row[0],
                equipment_id=row[1],
                component=row[2],
                severity=row[3],
                metric_type=MetricType(row[4]),
                current_value=row[5],
                threshold_value=row[6],
                baseline_value=row[7],
                trend_direction=TrendDirection(row[8]) if row[8] else None,
                degradation_percent=row[9],
                message=row[10],
                recommendations=json.loads(row[11]) if row[11] else [],
                triggered_at=datetime.fromisoformat(row[12]),
                acknowledged_at=datetime.fromisoformat(row[13]) if row[13] else None,
                resolved_at=datetime.fromisoformat(row[14]) if row[14] else None,
                active=bool(row[15])
            )
            alerts.append(alert)
        
        return alerts

    async def acknowledge_alert(self, alert_id: str):
        """Acknowledge a performance alert."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE performance_alerts 
            SET acknowledged_at = ? 
            WHERE alert_id = ?
        """, (datetime.now().isoformat(), alert_id))
        
        conn.commit()
        conn.close()

    async def resolve_alert(self, alert_id: str):
        """Resolve a performance alert."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE performance_alerts 
            SET resolved_at = ?, active = 0 
            WHERE alert_id = ?
        """, (datetime.now().isoformat(), alert_id))
        
        conn.commit()
        conn.close()
        
        # Remove from active alerts cache
        for key, alert in list(self._active_alerts.items()):
            if alert.alert_id == alert_id:
                del self._active_alerts[key]
                break


# Global performance monitor instance
performance_monitor: Optional[PerformanceMonitor] = None


def get_performance_monitor() -> Optional[PerformanceMonitor]:
    """Get the global performance monitor instance."""
    return performance_monitor


def initialize_performance_monitor(db_path: str = "data/performance.db") -> PerformanceMonitor:
    """
    Initialize the global performance monitor.

    Args:
        db_path: Path to SQLite database

    Returns:
        Initialized performance monitor
    """
    global performance_monitor
    performance_monitor = PerformanceMonitor(db_path)
    return performance_monitor
