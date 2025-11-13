"""
Performance Analyzer
====================

Analyzes performance trends, detects degradation, and generates reports.
"""

import logging
import statistics
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta

from .models import (
    PerformanceMetric,
    PerformanceTrend,
    PerformanceReport,
    PerformanceBaseline,
    PerformanceAlert,
    TrendDirection,
    PerformanceStatus,
    MetricType,
)
from .monitor import get_performance_monitor

logger = logging.getLogger(__name__)


class PerformanceAnalyzer:
    """Analyzes performance data for trends and insights."""

    def __init__(self):
        """Initialize performance analyzer."""
        self.monitor = None

    def _get_monitor(self):
        """Get performance monitor instance."""
        if self.monitor is None:
            self.monitor = get_performance_monitor()
        return self.monitor

    # ==================== Trend Analysis ====================

    async def analyze_trend(
        self,
        equipment_id: Optional[str],
        component: str,
        metric_type: MetricType,
        hours: float = 24.0
    ) -> Optional[PerformanceTrend]:
        """
        Analyze performance trend over specified period.

        Args:
            equipment_id: Equipment ID
            component: Component name
            metric_type: Type of metric to analyze
            hours: Hours of history to analyze

        Returns:
            Trend analysis or None if insufficient data
        """
        monitor = self._get_monitor()
        if not monitor:
            return None

        # Get metrics for analysis period
        start_time = datetime.now() - timedelta(hours=hours)
        metrics = await monitor.get_metrics(
            equipment_id=equipment_id,
            component=component,
            metric_type=metric_type,
            start_time=start_time
        )

        if len(metrics) < 10:
            logger.warning(f"Insufficient data for trend analysis (need 10+, got {len(metrics)})")
            return None

        # Sort by timestamp
        metrics.sort(key=lambda m: m.timestamp)

        # Extract values and timestamps
        values = [m.value for m in metrics]
        timestamps = [(m.timestamp - metrics[0].timestamp).total_seconds() / 3600 for m in metrics]

        # Calculate statistics
        mean = statistics.mean(values)
        std_dev = statistics.stdev(values) if len(values) > 1 else 0
        min_val = min(values)
        max_val = max(values)

        # Linear regression for trend
        slope, correlation = self._linear_regression(timestamps, values)

        # Determine trend direction
        direction = self._determine_trend_direction(slope, correlation, std_dev, mean)

        # Get baseline for comparison
        baseline = await monitor.get_baseline(equipment_id, component)
        baseline_mean = None
        deviation_from_baseline = None

        if baseline:
            if metric_type == MetricType.LATENCY:
                baseline_mean = baseline.avg_latency_ms
            elif metric_type == MetricType.THROUGHPUT:
                baseline_mean = baseline.avg_throughput
            elif metric_type == MetricType.ERROR_RATE:
                baseline_mean = baseline.error_rate_percent

            if baseline_mean:
                deviation_from_baseline = ((mean - baseline_mean) / baseline_mean) * 100

        # Calculate predictions
        predicted_1h = mean + (slope * 1) if slope else mean
        predicted_24h = mean + (slope * 24) if slope else mean

        # Estimate time to threshold breach
        time_to_threshold = None
        if baseline and slope > 0 and metric_type == MetricType.LATENCY:
            threshold = baseline.latency_warning_threshold_ms
            if mean < threshold:
                time_to_threshold = (threshold - mean) / slope if slope > 0 else None

        # Create trend object
        trend = PerformanceTrend(
            equipment_id=equipment_id,
            component=component,
            direction=direction,
            slope=slope,
            correlation=correlation,
            confidence=abs(correlation),
            start_time=metrics[0].timestamp,
            end_time=metrics[-1].timestamp,
            sample_count=len(metrics),
            mean_value=mean,
            std_deviation=std_dev,
            min_value=min_val,
            max_value=max_val,
            baseline_mean=baseline_mean,
            deviation_from_baseline=deviation_from_baseline,
            predicted_value_1h=predicted_1h,
            predicted_value_24h=predicted_24h,
            time_to_threshold=time_to_threshold
        )

        return trend

    def _linear_regression(self, x: List[float], y: List[float]) -> tuple:
        """
        Perform linear regression.

        Returns:
            Tuple of (slope, correlation)
        """
        n = len(x)
        if n < 2:
            return 0.0, 0.0

        # Calculate means
        x_mean = sum(x) / n
        y_mean = sum(y) / n

        # Calculate slope
        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        slope = numerator / denominator if denominator != 0 else 0.0

        # Calculate correlation coefficient
        x_std = statistics.stdev(x) if n > 1 else 0
        y_std = statistics.stdev(y) if n > 1 else 0

        if x_std == 0 or y_std == 0:
            correlation = 0.0
        else:
            correlation = numerator / (n * x_std * y_std)

        return slope, correlation

    def _determine_trend_direction(
        self,
        slope: float,
        correlation: float,
        std_dev: float,
        mean: float
    ) -> TrendDirection:
        """Determine trend direction from statistics."""
        # Require minimum correlation for trend confidence
        if abs(correlation) < 0.3:
            return TrendDirection.STABLE

        # Calculate coefficient of variation
        cv = (std_dev / mean) * 100 if mean != 0 else 0

        # High variability = unstable
        if cv > 50:
            return TrendDirection.UNKNOWN

        # Significant slope with good correlation
        if abs(slope) > (0.1 * mean) and abs(correlation) > 0.5:
            if slope > 0:
                # For latency/errors, increasing is degrading
                return TrendDirection.DEGRADING
            else:
                # For latency/errors, decreasing is improving
                return TrendDirection.IMPROVING
        elif abs(slope) > (0.05 * mean):
            if slope > 0:
                return TrendDirection.DEGRADING
            else:
                return TrendDirection.STABLE

        return TrendDirection.STABLE

    # ==================== Performance Status ====================

    async def get_performance_status(
        self,
        equipment_id: Optional[str],
        component: str
    ) -> PerformanceStatus:
        """
        Determine overall performance status for component.

        Args:
            equipment_id: Equipment ID
            component: Component name

        Returns:
            Performance status
        """
        monitor = self._get_monitor()
        if not monitor:
            return PerformanceStatus.UNKNOWN

        # Get recent metrics
        metrics = await monitor.get_metrics(
            equipment_id=equipment_id,
            component=component,
            start_time=datetime.now() - timedelta(hours=1),
            limit=100
        )

        if not metrics:
            return PerformanceStatus.UNKNOWN

        # Get baseline
        baseline = await monitor.get_baseline(equipment_id, component)
        if not baseline:
            return PerformanceStatus.UNKNOWN

        # Calculate average deviation from baseline
        deviations = [m.deviation_percent for m in metrics if m.deviation_percent is not None]
        if not deviations:
            return PerformanceStatus.UNKNOWN

        avg_deviation = statistics.mean(deviations)

        # Determine status based on deviation
        if avg_deviation < -10:
            return PerformanceStatus.EXCELLENT
        elif avg_deviation < 10:
            return PerformanceStatus.GOOD
        elif avg_deviation < 30:
            return PerformanceStatus.DEGRADED
        elif avg_deviation < 50:
            return PerformanceStatus.POOR
        else:
            return PerformanceStatus.CRITICAL

    # ==================== Performance Reports ====================

    async def generate_performance_report(
        self,
        equipment_ids: Optional[List[str]] = None,
        components: Optional[List[str]] = None,
        hours: float = 24.0
    ) -> PerformanceReport:
        """
        Generate comprehensive performance report.

        Args:
            equipment_ids: Equipment IDs to include
            components: Components to analyze
            hours: Hours of history to analyze

        Returns:
            Performance report
        """
        monitor = self._get_monitor()
        start_time = datetime.now() - timedelta(hours=hours)
        end_time = datetime.now()

        # Get active alerts
        active_alerts = await monitor.get_active_alerts() if monitor else []

        # Analyze each component
        component_performance = {}
        trend_analyses = []
        degraded_components = []
        critical_components = []

        if components:
            for component in components:
                for equipment_id in (equipment_ids or [None]):
                    # Analyze latency trend
                    latency_trend = await self.analyze_trend(
                        equipment_id, component, MetricType.LATENCY, hours
                    )
                    if latency_trend:
                        trend_analyses.append(latency_trend)

                    # Get performance status
                    status = await self.get_performance_status(equipment_id, component)

                    key = f"{equipment_id}:{component}" if equipment_id else component
                    component_performance[key] = {
                        "status": status.value,
                        "latency_trend": latency_trend.direction.value if latency_trend else "unknown"
                    }

                    if status == PerformanceStatus.DEGRADED:
                        degraded_components.append(key)
                    elif status in [PerformanceStatus.POOR, PerformanceStatus.CRITICAL]:
                        critical_components.append(key)

        # Calculate overall health score
        if component_performance:
            status_scores = {
                PerformanceStatus.EXCELLENT: 100,
                PerformanceStatus.GOOD: 85,
                PerformanceStatus.DEGRADED: 65,
                PerformanceStatus.POOR: 40,
                PerformanceStatus.CRITICAL: 20,
                PerformanceStatus.UNKNOWN: 50
            }
            statuses = [PerformanceStatus(v["status"]) for v in component_performance.values()]
            health_score = statistics.mean([status_scores[s] for s in statuses])
        else:
            health_score = 50.0

        # Determine overall status
        if health_score >= 85:
            overall_status = PerformanceStatus.EXCELLENT
        elif health_score >= 70:
            overall_status = PerformanceStatus.GOOD
        elif health_score >= 50:
            overall_status = PerformanceStatus.DEGRADED
        elif health_score >= 30:
            overall_status = PerformanceStatus.POOR
        else:
            overall_status = PerformanceStatus.CRITICAL

        # Generate recommendations
        recommendations = self._generate_recommendations(
            degraded_components, critical_components, active_alerts
        )

        report = PerformanceReport(
            equipment_ids=equipment_ids or [],
            components=components or [],
            start_time=start_time,
            end_time=end_time,
            overall_status=overall_status,
            health_score=health_score,
            active_alerts=len(active_alerts),
            degraded_components=degraded_components,
            critical_components=critical_components,
            recommendations=recommendations,
            component_performance=component_performance,
            trend_analyses=trend_analyses,
            alerts=active_alerts
        )

        return report

    def _generate_recommendations(
        self,
        degraded: List[str],
        critical: List[str],
        alerts: List[PerformanceAlert]
    ) -> List[str]:
        """Generate performance improvement recommendations."""
        recommendations = []

        if critical:
            recommendations.append(
                f"URGENT: {len(critical)} component(s) have critical performance issues requiring immediate attention"
            )
            recommendations.append("Review system resources (CPU, memory, network)")
            recommendations.append("Check for equipment hardware issues")

        if degraded:
            recommendations.append(
                f"{len(degraded)} component(s) showing performance degradation"
            )
            recommendations.append("Monitor trends closely for further degradation")
            recommendations.append("Consider baseline recalibration if changes are expected")

        if len(alerts) > 5:
            recommendations.append("High number of performance alerts - review system health")

        if not recommendations:
            recommendations.append("Performance within expected parameters")
            recommendations.append("Continue monitoring for any changes")

        return recommendations


# Global performance analyzer instance
performance_analyzer = PerformanceAnalyzer()
