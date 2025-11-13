"""API endpoints for performance monitoring."""

import logging
from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from performance import (
    performance_monitor,
    performance_analyzer,
    PerformanceMetric,
    MetricType,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Request Models ====================


class RecordMetricRequest(BaseModel):
    """Request to record a performance metric."""
    equipment_id: Optional[str] = None
    component: str
    metric_type: str  # Will be converted to MetricType
    value: float
    unit: str
    operation: Optional[str] = None


class CreateBaselineRequest(BaseModel):
    """Request to create a performance baseline."""
    equipment_id: Optional[str] = None
    component: str
    measurement_period_hours: float = 24.0


# ==================== Metric Endpoints ====================


@router.post("/performance/metrics", summary="Record performance metric")
async def record_performance_metric(request: RecordMetricRequest):
    """Record a new performance metric."""
    try:
        metric = PerformanceMetric(
            equipment_id=request.equipment_id,
            component=request.component,
            metric_type=MetricType(request.metric_type),
            value=request.value,
            unit=request.unit,
            operation=request.operation
        )

        recorded = await performance_monitor.record_metric(metric)

        return {
            "success": True,
            "metric_id": recorded.metric_id,
            "deviation_percent": recorded.deviation_percent,
            "within_threshold": recorded.within_threshold
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid metric type: {str(e)}")
    except Exception as e:
        logger.error(f"Error recording metric: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record metric: {str(e)}")


@router.get("/performance/metrics", summary="Get performance metrics")
async def get_performance_metrics(
    equipment_id: Optional[str] = None,
    component: Optional[str] = None,
    metric_type: Optional[str] = None,
    hours: float = Query(24.0, description="Hours of history"),
    limit: int = Query(1000, le=10000)
):
    """Retrieve performance metrics with filtering."""
    try:
        start_time = datetime.now() - timedelta(hours=hours)

        metric_type_enum = MetricType(metric_type) if metric_type else None

        metrics = await performance_monitor.get_metrics(
            equipment_id=equipment_id,
            component=component,
            metric_type=metric_type_enum,
            start_time=start_time,
            limit=limit
        )

        return {
            "success": True,
            "count": len(metrics),
            "metrics": [m.dict() for m in metrics]
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid metric type: {str(e)}")
    except Exception as e:
        logger.error(f"Error retrieving metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve metrics: {str(e)}")


# ==================== Baseline Endpoints ====================


@router.post("/performance/baselines", summary="Create performance baseline")
async def create_performance_baseline(request: CreateBaselineRequest):
    """Create a performance baseline from historical data."""
    try:
        baseline = await performance_monitor.create_baseline(
            equipment_id=request.equipment_id,
            component=request.component,
            measurement_period_hours=request.measurement_period_hours
        )

        return {
            "success": True,
            "baseline": baseline.dict()
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating baseline: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create baseline: {str(e)}")


@router.get("/performance/baselines/{component}", summary="Get performance baseline")
async def get_performance_baseline(
    component: str,
    equipment_id: Optional[str] = None
):
    """Get performance baseline for a component."""
    try:
        baseline = await performance_monitor.get_baseline(equipment_id, component)

        if baseline is None:
            raise HTTPException(
                status_code=404,
                detail=f"No baseline found for component: {component}"
            )

        return {
            "success": True,
            "baseline": baseline.dict()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving baseline: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve baseline: {str(e)}")


# ==================== Trend Analysis Endpoints ====================


@router.get("/performance/trends/{component}", summary="Analyze performance trend")
async def analyze_performance_trend(
    component: str,
    equipment_id: Optional[str] = None,
    metric_type: str = Query("latency", description="Metric type to analyze"),
    hours: float = Query(24.0, description="Hours to analyze")
):
    """Analyze performance trend for a component."""
    try:
        metric_type_enum = MetricType(metric_type)

        trend = await performance_analyzer.analyze_trend(
            equipment_id=equipment_id,
            component=component,
            metric_type=metric_type_enum,
            hours=hours
        )

        if trend is None:
            return {
                "success": True,
                "trend": None,
                "message": "Insufficient data for trend analysis"
            }

        return {
            "success": True,
            "trend": trend.dict()
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid metric type: {str(e)}")
    except Exception as e:
        logger.error(f"Error analyzing trend: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to analyze trend: {str(e)}")


@router.get("/performance/status/{component}", summary="Get performance status")
async def get_performance_status(
    component: str,
    equipment_id: Optional[str] = None
):
    """Get overall performance status for a component."""
    try:
        status = await performance_analyzer.get_performance_status(equipment_id, component)

        return {
            "success": True,
            "component": component,
            "equipment_id": equipment_id,
            "status": status.value
        }

    except Exception as e:
        logger.error(f"Error getting performance status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


# ==================== Alert Endpoints ====================


@router.get("/performance/alerts", summary="Get performance alerts")
async def get_performance_alerts(
    equipment_id: Optional[str] = None,
    severity: Optional[str] = None,
    active_only: bool = True
):
    """Get performance alerts."""
    try:
        if active_only:
            alerts = await performance_monitor.get_active_alerts(equipment_id, severity)
        else:
            # Would need to implement get_all_alerts
            alerts = await performance_monitor.get_active_alerts(equipment_id, severity)

        return {
            "success": True,
            "count": len(alerts),
            "alerts": [alert.dict() for alert in alerts]
        }

    except Exception as e:
        logger.error(f"Error retrieving alerts: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve alerts: {str(e)}")


@router.post("/performance/alerts/{alert_id}/acknowledge", summary="Acknowledge alert")
async def acknowledge_performance_alert(alert_id: str):
    """Acknowledge a performance alert."""
    try:
        await performance_monitor.acknowledge_alert(alert_id)

        return {
            "success": True,
            "message": f"Alert {alert_id} acknowledged"
        }

    except Exception as e:
        logger.error(f"Error acknowledging alert: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to acknowledge alert: {str(e)}")


@router.post("/performance/alerts/{alert_id}/resolve", summary="Resolve alert")
async def resolve_performance_alert(alert_id: str):
    """Resolve a performance alert."""
    try:
        await performance_monitor.resolve_alert(alert_id)

        return {
            "success": True,
            "message": f"Alert {alert_id} resolved"
        }

    except Exception as e:
        logger.error(f"Error resolving alert: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to resolve alert: {str(e)}")


# ==================== Report Endpoints ====================


@router.post("/performance/reports", summary="Generate performance report")
async def generate_performance_report(
    equipment_ids: Optional[List[str]] = None,
    components: Optional[List[str]] = None,
    hours: float = 24.0
):
    """Generate comprehensive performance report."""
    try:
        report = await performance_analyzer.generate_performance_report(
            equipment_ids=equipment_ids,
            components=components,
            hours=hours
        )

        return {
            "success": True,
            "report": report.dict()
        }

    except Exception as e:
        logger.error(f"Error generating report: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


@router.get("/performance/summary", summary="Get performance summary")
async def get_performance_summary():
    """Get quick performance summary."""
    try:
        # Get active alerts
        alerts = await performance_monitor.get_active_alerts()

        # Get recent metrics for common components
        components = ["equipment_commands", "api_requests", "data_acquisition"]
        component_status = {}

        for component in components:
            status = await performance_analyzer.get_performance_status(None, component)
            component_status[component] = status.value

        return {
            "success": True,
            "summary": {
                "active_alerts": len(alerts),
                "critical_alerts": len([a for a in alerts if a.severity == "critical"]),
                "component_status": component_status,
                "timestamp": datetime.now().isoformat()
            }
        }

    except Exception as e:
        logger.error(f"Error getting summary: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get summary: {str(e)}")
