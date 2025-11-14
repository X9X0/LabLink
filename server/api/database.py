"""API endpoints for database queries and management."""

from datetime import datetime, timedelta
from typing import List, Optional

from database import get_database_manager
from database.models import CommandStatus, QueryResult, SessionStatus
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/database", tags=["database"])


# === Request/Response Models ===


class CommandHistoryQuery(BaseModel):
    """Command history query parameters."""

    equipment_id: Optional[str] = None
    user_id: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: Optional[CommandStatus] = None
    limit: int = Field(100, ge=1, le=1000)
    offset: int = Field(0, ge=0)


class MeasurementQuery(BaseModel):
    """Measurement query parameters."""

    equipment_id: Optional[str] = None
    measurement_type: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = Field(100, ge=1, le=1000)
    offset: int = Field(0, ge=0)


class UsageStatisticsQuery(BaseModel):
    """Equipment usage statistics query."""

    equipment_id: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class CleanupRequest(BaseModel):
    """Database cleanup request."""

    retention_days: Optional[int] = Field(
        None, ge=1, le=365, description="Days to keep"
    )


# === Command History Endpoints ===


@router.get("/commands")
async def query_command_history(
    equipment_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Query command history.

    Returns paginated command execution records with optional filtering.

    **Query Parameters:**
    - equipment_id: Filter by equipment ID
    - user_id: Filter by user ID
    - start_time: Filter by start time (ISO format)
    - end_time: Filter by end time (ISO format)
    - status: Filter by status (success, failed, timeout, error)
    - limit: Maximum records to return (1-1000, default: 100)
    - offset: Number of records to skip for pagination (default: 0)

    **Returns:**
    - records: List of command records
    - total_count: Total matching records
    - page: Current page number
    - page_size: Records per page
    - has_more: Whether more records available
    - query_time_ms: Query execution time
    """
    try:
        db = get_database_manager()

        status_enum = CommandStatus(status) if status else None

        result = db.get_command_history(
            equipment_id=equipment_id,
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
            status=status_enum,
            limit=limit,
            offset=offset,
        )

        return result.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/commands/recent")
async def get_recent_commands(
    equipment_id: Optional[str] = Query(None),
    minutes: int = Query(60, ge=1, le=1440),  # 1 minute to 24 hours
    limit: int = Query(100, ge=1, le=500),
):
    """Get recent commands for an equipment.

    **Query Parameters:**
    - equipment_id: Equipment ID (optional, returns all if omitted)
    - minutes: Number of minutes to look back (1-1440, default: 60)
    - limit: Maximum commands to return (1-500, default: 100)

    **Returns:**
    - List of recent command records
    """
    try:
        db = get_database_manager()

        start_time = datetime.now() - timedelta(minutes=minutes)

        result = db.get_command_history(
            equipment_id=equipment_id,
            start_time=start_time,
            limit=limit,
            offset=0,
        )

        return result.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/commands/failed")
async def get_failed_commands(
    equipment_id: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=168),  # 1 hour to 7 days
    limit: int = Query(100, ge=1, le=500),
):
    """Get failed commands.

    **Query Parameters:**
    - equipment_id: Equipment ID (optional)
    - hours: Number of hours to look back (1-168, default: 24)
    - limit: Maximum commands to return (1-500, default: 100)

    **Returns:**
    - List of failed command records
    """
    try:
        db = get_database_manager()

        start_time = datetime.now() - timedelta(hours=hours)

        result = db.get_command_history(
            equipment_id=equipment_id,
            start_time=start_time,
            status=CommandStatus.FAILED,
            limit=limit,
            offset=0,
        )

        return result.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Measurement Endpoints ===


@router.get("/measurements")
async def query_measurements(
    equipment_id: Optional[str] = Query(None),
    measurement_type: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Query measurement history.

    Returns paginated measurement records with optional filtering.

    **Query Parameters:**
    - equipment_id: Filter by equipment ID
    - measurement_type: Filter by measurement type (voltage, current, power, etc.)
    - start_time: Filter by start time (ISO format)
    - end_time: Filter by end time (ISO format)
    - limit: Maximum records to return (1-1000, default: 100)
    - offset: Number of records to skip for pagination (default: 0)

    **Returns:**
    - records: List of measurement records
    - total_count: Total matching records
    - page: Current page number
    - page_size: Records per page
    - has_more: Whether more records available
    - query_time_ms: Query execution time
    """
    try:
        db = get_database_manager()

        result = db.get_measurements(
            equipment_id=equipment_id,
            measurement_type=measurement_type,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )

        return result.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/measurements/recent")
async def get_recent_measurements(
    equipment_id: str = Query(..., description="Equipment ID"),
    measurement_type: Optional[str] = Query(None),
    minutes: int = Query(60, ge=1, le=1440),
    limit: int = Query(100, ge=1, le=500),
):
    """Get recent measurements for an equipment.

    **Query Parameters:**
    - equipment_id: Equipment ID (required)
    - measurement_type: Filter by measurement type (optional)
    - minutes: Number of minutes to look back (1-1440, default: 60)
    - limit: Maximum measurements to return (1-500, default: 100)

    **Returns:**
    - List of recent measurement records
    """
    try:
        db = get_database_manager()

        start_time = datetime.now() - timedelta(minutes=minutes)

        result = db.get_measurements(
            equipment_id=equipment_id,
            measurement_type=measurement_type,
            start_time=start_time,
            limit=limit,
            offset=0,
        )

        return result.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/measurements/trend")
async def get_measurement_trend(
    equipment_id: str = Query(...),
    measurement_type: str = Query(...),
    hours: int = Query(24, ge=1, le=168),
    interval_minutes: int = Query(60, ge=1, le=1440),
):
    """Get measurement trend data with time-based aggregation.

    Returns aggregated measurement data (avg, min, max) over time intervals.

    **Query Parameters:**
    - equipment_id: Equipment ID (required)
    - measurement_type: Measurement type (required)
    - hours: Number of hours to look back (1-168, default: 24)
    - interval_minutes: Aggregation interval in minutes (1-1440, default: 60)

    **Returns:**
    - List of aggregated data points with timestamps
    """
    try:
        db = get_database_manager()

        start_time = datetime.now() - timedelta(hours=hours)

        # Get all measurements in the time range
        result = db.get_measurements(
            equipment_id=equipment_id,
            measurement_type=measurement_type,
            start_time=start_time,
            limit=10000,  # Large limit to get all data
            offset=0,
        )

        # Aggregate by time intervals
        import statistics
        from collections import defaultdict

        interval_seconds = interval_minutes * 60
        buckets = defaultdict(list)

        for record in result.records:
            timestamp = datetime.fromisoformat(record["timestamp"])
            bucket_time = timestamp.replace(
                minute=(timestamp.minute // interval_minutes) * interval_minutes,
                second=0,
                microsecond=0,
            )
            buckets[bucket_time].append(record["value"])

        # Calculate aggregates
        trend_data = []
        for bucket_time in sorted(buckets.keys()):
            values = buckets[bucket_time]
            trend_data.append(
                {
                    "timestamp": bucket_time.isoformat(),
                    "count": len(values),
                    "average": statistics.mean(values),
                    "minimum": min(values),
                    "maximum": max(values),
                    "std_dev": statistics.stdev(values) if len(values) > 1 else 0.0,
                }
            )

        return {
            "equipment_id": equipment_id,
            "measurement_type": measurement_type,
            "start_time": start_time.isoformat(),
            "end_time": datetime.now().isoformat(),
            "interval_minutes": interval_minutes,
            "data_points": len(trend_data),
            "trend": trend_data,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Equipment Usage Endpoints ===


@router.get("/usage/statistics")
async def get_usage_statistics(
    equipment_id: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
):
    """Get equipment usage statistics.

    Returns aggregated usage statistics including session counts, durations,
    command counts, measurement counts, and error counts.

    **Query Parameters:**
    - equipment_id: Filter by equipment ID (optional, returns all if omitted)
    - start_time: Filter by start time (ISO format, optional)
    - end_time: Filter by end time (ISO format, optional)

    **Returns:**
    - session_count: Number of usage sessions
    - total_duration_seconds: Total connection time
    - average_duration_seconds: Average session duration
    - total_commands: Total commands executed
    - total_measurements: Total measurements taken
    - total_errors: Total errors encountered
    """
    try:
        db = get_database_manager()

        stats = db.get_equipment_usage_statistics(
            equipment_id=equipment_id,
            start_time=start_time,
            end_time=end_time,
        )

        return stats

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/usage/summary")
async def get_usage_summary(
    days: int = Query(7, ge=1, le=90, description="Number of days to summarize"),
):
    """Get usage summary for all equipment.

    Returns usage statistics per equipment for the specified time period.

    **Query Parameters:**
    - days: Number of days to look back (1-90, default: 7)

    **Returns:**
    - List of equipment usage summaries
    """
    try:
        db = get_database_manager()
        start_time = datetime.now() - timedelta(days=days)

        # Get statistics for all equipment (no equipment_id filter)
        # This requires a custom query
        import sqlite3

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                equipment_id,
                equipment_type,
                COUNT(*) as session_count,
                SUM(duration_seconds) as total_duration,
                AVG(duration_seconds) as avg_duration,
                SUM(command_count) as total_commands,
                SUM(measurement_count) as total_measurements,
                SUM(error_count) as total_errors
            FROM equipment_usage
            WHERE session_start >= ?
            GROUP BY equipment_id, equipment_type
            ORDER BY total_duration DESC
        """,
            (start_time.isoformat(),),
        )

        results = []
        for row in cursor.fetchall():
            results.append(
                {
                    "equipment_id": row[0],
                    "equipment_type": row[1],
                    "session_count": row[2],
                    "total_duration_seconds": row[3] or 0.0,
                    "average_duration_seconds": row[4] or 0.0,
                    "total_commands": row[5] or 0,
                    "total_measurements": row[6] or 0,
                    "total_errors": row[7] or 0,
                }
            )

        conn.close()

        return {
            "period_days": days,
            "start_time": start_time.isoformat(),
            "end_time": datetime.now().isoformat(),
            "equipment_count": len(results),
            "equipment_usage": results,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Database Management Endpoints ===


@router.get("/statistics")
async def get_database_statistics():
    """Get database statistics.

    Returns overall database statistics including record counts and size.

    **Returns:**
    - command_count: Number of command records
    - measurement_count: Number of measurement records
    - usage_session_count: Number of usage session records
    - data_session_count: Number of data acquisition session records
    - database_size_bytes: Database file size in bytes
    - database_size_mb: Database file size in MB
    - database_path: Database file path
    - retention_days: Data retention period
    """
    try:
        db = get_database_manager()
        stats = db.get_database_statistics()
        return stats

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cleanup")
async def cleanup_old_records(request: CleanupRequest):
    """Clean up old records.

    Removes records older than the retention period to free up space.

    **Request Body:**
    - retention_days: Days to keep (uses config default if not specified)

    **Returns:**
    - message: Success message
    - retention_days: Retention period used
    """
    try:
        db = get_database_manager()
        db.cleanup_old_records(days=request.retention_days)

        return {
            "message": "Old records cleaned up successfully",
            "retention_days": request.retention_days or db.config.retention_days,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def get_database_health():
    """Get database health status.

    Returns database health metrics including size, record counts, and warnings.

    **Returns:**
    - healthy: Overall health status
    - warnings: List of warning messages
    - statistics: Database statistics
    """
    try:
        db = get_database_manager()
        stats = db.get_database_statistics()

        warnings = []

        # Check database size
        if stats["database_size_mb"] > db.config.max_db_size_mb * 0.9:
            warnings.append(
                f"Database size ({stats['database_size_mb']:.1f} MB) approaching limit ({db.config.max_db_size_mb} MB)"
            )

        # Check large table counts
        if stats["command_count"] > 1000000:
            warnings.append(
                f"Large number of command records ({stats['command_count']:,}). Consider cleanup."
            )

        if stats["measurement_count"] > 1000000:
            warnings.append(
                f"Large number of measurement records ({stats['measurement_count']:,}). Consider cleanup."
            )

        return {
            "healthy": len(warnings) == 0,
            "warnings": warnings,
            "statistics": stats,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/info")
async def get_database_info():
    """Get database system information.

    Returns configuration and capabilities of the database system.

    **Returns:**
    - Database configuration
    - Supported features
    - Record types
    """
    try:
        db = get_database_manager()

        return {
            "database_path": db.db_path,
            "config": {
                "command_logging_enabled": db.config.enable_command_logging,
                "measurement_archival_enabled": db.config.enable_measurement_archival,
                "usage_tracking_enabled": db.config.enable_usage_tracking,
                "retention_days": db.config.retention_days,
                "auto_cleanup_enabled": db.config.auto_cleanup,
                "max_database_size_mb": db.config.max_db_size_mb,
            },
            "features": {
                "command_history": "Track all SCPI commands sent to equipment",
                "measurement_archival": "Archive all measurements for historical analysis",
                "usage_tracking": "Track equipment connection time and usage patterns",
                "data_sessions": "Track data acquisition sessions",
                "query_api": "RESTful API for querying historical data",
                "auto_cleanup": "Automatic cleanup of old records",
            },
            "record_types": [
                "command_history",
                "measurements",
                "equipment_usage",
                "data_sessions",
            ],
            "query_features": [
                "Filtering by equipment, user, time range, status",
                "Pagination support",
                "Trend analysis",
                "Aggregation and statistics",
            ],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
