"""API endpoints for alarm management."""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from alarm import (
    alarm_manager,
    notification_manager,
    AlarmConfig,
    AlarmAcknowledgment,
    AlarmSeverity,
    AlarmState,
    NotificationConfig
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Request Models ====================


class CreateAlarmRequest(BaseModel):
    """Request to create an alarm."""
    name: str
    description: Optional[str] = None
    equipment_id: Optional[str] = None
    parameter: str
    alarm_type: str = "threshold"
    condition: str = "greater_than"
    severity: str = "warning"
    threshold: Optional[float] = None
    threshold_high: Optional[float] = None
    threshold_low: Optional[float] = None
    deadband: Optional[float] = None
    delay_seconds: float = 0.0
    auto_clear: bool = True
    enabled: bool = True
    notifications: List[str] = []
    tags: List[str] = []


class UpdateAlarmRequest(BaseModel):
    """Request to update an alarm."""
    name: Optional[str] = None
    description: Optional[str] = None
    parameter: Optional[str] = None
    condition: Optional[str] = None
    severity: Optional[str] = None
    threshold: Optional[float] = None
    threshold_high: Optional[float] = None
    threshold_low: Optional[float] = None
    deadband: Optional[float] = None
    enabled: Optional[bool] = None
    notifications: Optional[List[str]] = None


class AcknowledgeAlarmRequest(BaseModel):
    """Request to acknowledge an alarm."""
    event_id: str
    acknowledged_by: str
    note: Optional[str] = None


class CheckAlarmRequest(BaseModel):
    """Request to manually check an alarm."""
    alarm_id: str
    value: float


# ==================== Alarm Management Endpoints ====================


@router.post("/alarms/create", summary="Create alarm")
async def create_alarm(request: CreateAlarmRequest):
    """Create a new alarm configuration."""
    try:
        config = AlarmConfig(
            name=request.name,
            description=request.description,
            equipment_id=request.equipment_id,
            parameter=request.parameter,
            alarm_type=request.alarm_type,
            condition=request.condition,
            severity=request.severity,
            threshold=request.threshold,
            threshold_high=request.threshold_high,
            threshold_low=request.threshold_low,
            deadband=request.deadband,
            delay_seconds=request.delay_seconds,
            auto_clear=request.auto_clear,
            enabled=request.enabled,
            notifications=request.notifications,
            tags=request.tags
        )

        result = await alarm_manager.create_alarm(config)

        return {
            "success": True,
            "alarm_id": result.alarm_id,
            "message": "Alarm created successfully"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating alarm: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create alarm: {str(e)}")


@router.get("/alarms/{alarm_id}", summary="Get alarm")
async def get_alarm(alarm_id: str):
    """Get alarm configuration by ID."""
    alarm = alarm_manager.get_alarm(alarm_id)

    if alarm is None:
        raise HTTPException(status_code=404, detail=f"Alarm {alarm_id} not found")

    return {
        "success": True,
        "alarm": alarm.dict()
    }


@router.get("/alarms", summary="List alarms")
async def list_alarms(
    equipment_id: Optional[str] = None,
    enabled: Optional[bool] = None
):
    """List all alarm configurations."""
    alarms = alarm_manager.list_alarms()

    # Filter
    if equipment_id:
        alarms = [a for a in alarms if a.equipment_id == equipment_id]
    if enabled is not None:
        alarms = [a for a in alarms if a.enabled == enabled]

    return {
        "success": True,
        "count": len(alarms),
        "alarms": [a.dict() for a in alarms]
    }


@router.put("/alarms/{alarm_id}", summary="Update alarm")
async def update_alarm(alarm_id: str, request: UpdateAlarmRequest):
    """Update alarm configuration."""
    try:
        # Get existing alarm
        alarm = alarm_manager.get_alarm(alarm_id)
        if alarm is None:
            raise HTTPException(status_code=404, detail=f"Alarm {alarm_id} not found")

        # Update fields
        if request.name is not None:
            alarm.name = request.name
        if request.description is not None:
            alarm.description = request.description
        if request.parameter is not None:
            alarm.parameter = request.parameter
        if request.condition is not None:
            alarm.condition = request.condition
        if request.severity is not None:
            alarm.severity = request.severity
        if request.threshold is not None:
            alarm.threshold = request.threshold
        if request.threshold_high is not None:
            alarm.threshold_high = request.threshold_high
        if request.threshold_low is not None:
            alarm.threshold_low = request.threshold_low
        if request.deadband is not None:
            alarm.deadband = request.deadband
        if request.enabled is not None:
            alarm.enabled = request.enabled
        if request.notifications is not None:
            alarm.notifications = request.notifications

        result = await alarm_manager.update_alarm(alarm_id, alarm)

        return {
            "success": True,
            "message": "Alarm updated successfully",
            "alarm": result.dict()
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating alarm: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update alarm: {str(e)}")


@router.delete("/alarms/{alarm_id}", summary="Delete alarm")
async def delete_alarm(alarm_id: str):
    """Delete an alarm configuration."""
    try:
        success = await alarm_manager.delete_alarm(alarm_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Alarm {alarm_id} not found")

        return {
            "success": True,
            "message": "Alarm deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting alarm: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete alarm: {str(e)}")


@router.post("/alarms/{alarm_id}/enable", summary="Enable alarm")
async def enable_alarm(alarm_id: str):
    """Enable an alarm."""
    try:
        success = await alarm_manager.enable_alarm(alarm_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Alarm {alarm_id} not found")

        return {
            "success": True,
            "message": "Alarm enabled"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enabling alarm: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to enable alarm: {str(e)}")


@router.post("/alarms/{alarm_id}/disable", summary="Disable alarm")
async def disable_alarm(alarm_id: str):
    """Disable an alarm."""
    try:
        success = await alarm_manager.disable_alarm(alarm_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Alarm {alarm_id} not found")

        return {
            "success": True,
            "message": "Alarm disabled"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling alarm: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to disable alarm: {str(e)}")


@router.post("/alarms/check", summary="Check alarm")
async def check_alarm(request: CheckAlarmRequest):
    """Manually check an alarm condition."""
    try:
        event = await alarm_manager.check_alarm(request.alarm_id, request.value)

        return {
            "success": True,
            "triggered": event is not None,
            "event": event.dict() if event else None
        }

    except Exception as e:
        logger.error(f"Error checking alarm: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check alarm: {str(e)}")


# ==================== Alarm Event Endpoints ====================


@router.get("/alarms/events/active", summary="List active alarms")
async def list_active_alarms():
    """List all active alarm events."""
    events = alarm_manager.list_active_events()

    return {
        "success": True,
        "count": len(events),
        "events": [e.dict() for e in events]
    }


@router.get("/alarms/events", summary="List alarm events")
async def list_alarm_events(
    state: Optional[str] = None,
    severity: Optional[str] = None,
    equipment_id: Optional[str] = None,
    limit: int = 100
):
    """List alarm events with filtering."""
    try:
        # Convert string enums
        state_filter = AlarmState(state) if state else None
        severity_filter = AlarmSeverity(severity) if severity else None

        events = alarm_manager.list_events(
            state=state_filter,
            severity=severity_filter,
            equipment_id=equipment_id,
            limit=limit
        )

        return {
            "success": True,
            "count": len(events),
            "events": [e.dict() for e in events]
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid filter value: {str(e)}")
    except Exception as e:
        logger.error(f"Error listing events: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list events: {str(e)}")


@router.get("/alarms/events/{event_id}", summary="Get alarm event")
async def get_alarm_event(event_id: str):
    """Get alarm event by ID."""
    event = alarm_manager.get_event(event_id)

    if event is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    return {
        "success": True,
        "event": event.dict()
    }


@router.post("/alarms/events/acknowledge", summary="Acknowledge alarm")
async def acknowledge_alarm(request: AcknowledgeAlarmRequest):
    """Acknowledge an alarm event."""
    try:
        ack = AlarmAcknowledgment(
            event_id=request.event_id,
            acknowledged_by=request.acknowledged_by,
            note=request.note
        )

        success = await alarm_manager.acknowledge_alarm(ack)

        if not success:
            raise HTTPException(status_code=404, detail=f"Event {request.event_id} not found or already acknowledged")

        return {
            "success": True,
            "message": "Alarm acknowledged"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error acknowledging alarm: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to acknowledge alarm: {str(e)}")


@router.post("/alarms/{alarm_id}/clear", summary="Clear alarm")
async def clear_alarm(alarm_id: str):
    """Manually clear an alarm."""
    try:
        success = await alarm_manager.clear_alarm(alarm_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"No active alarm for {alarm_id}")

        return {
            "success": True,
            "message": "Alarm cleared"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing alarm: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear alarm: {str(e)}")


# ==================== Statistics Endpoints ====================


@router.get("/alarms/statistics", summary="Get alarm statistics")
async def get_alarm_statistics():
    """Get alarm system statistics."""
    try:
        stats = alarm_manager.get_statistics()

        return {
            "success": True,
            "statistics": stats.dict()
        }

    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")


# ==================== Notification Configuration Endpoints ====================


@router.post("/alarms/notifications/configure", summary="Configure notifications")
async def configure_notifications(config: NotificationConfig):
    """Configure alarm notification settings."""
    try:
        notification_manager.configure(config)

        return {
            "success": True,
            "message": "Notification configuration updated"
        }

    except Exception as e:
        logger.error(f"Error configuring notifications: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to configure notifications: {str(e)}")


@router.get("/alarms/notifications/config", summary="Get notification configuration")
async def get_notification_config():
    """Get current notification configuration."""
    return {
        "success": True,
        "config": notification_manager.config.dict()
    }
