"""API endpoints for equipment calibration management."""

import logging
from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from equipment.calibration import (
    get_calibration_manager,
    CalibrationRecord,
    CalibrationSchedule,
    CalibrationType,
    CalibrationResult,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Request/Response Models ====================


class CalibrationRecordCreate(BaseModel):
    """Request model for creating calibration record."""
    equipment_id: str
    equipment_type: str
    equipment_model: str
    calibration_type: str  # Will be converted to CalibrationType
    due_date: datetime
    result: str  # Will be converted to CalibrationResult
    performed_by: str
    organization: Optional[str] = None
    location: Optional[str] = None
    pre_calibration_measurements: dict = Field(default_factory=dict)
    post_calibration_measurements: dict = Field(default_factory=dict)
    standards_used: List[dict] = Field(default_factory=list)
    temperature_celsius: Optional[float] = None
    humidity_percent: Optional[float] = None
    adjustments_made: List[str] = Field(default_factory=list)
    out_of_tolerance_items: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    certificate_number: Optional[str] = None


class CalibrationScheduleCreate(BaseModel):
    """Request model for creating calibration schedule."""
    equipment_id: str
    interval_days: int
    warning_days: int = 30
    auto_schedule: bool = True
    notify_due_soon: bool = True
    notify_overdue: bool = True
    notification_emails: List[str] = Field(default_factory=list)


# ==================== Calibration Record Endpoints ====================


@router.post("/calibration/records", summary="Add calibration record")
async def add_calibration_record(record_data: CalibrationRecordCreate):
    """Add a new calibration record."""
    cal_manager = get_calibration_manager()

    if not cal_manager:
        raise HTTPException(status_code=503, detail="Calibration manager not initialized")

    try:
        # Convert string enums to actual enums
        record = CalibrationRecord(
            equipment_id=record_data.equipment_id,
            equipment_type=record_data.equipment_type,
            equipment_model=record_data.equipment_model,
            calibration_type=CalibrationType(record_data.calibration_type),
            due_date=record_data.due_date,
            result=CalibrationResult(record_data.result),
            performed_by=record_data.performed_by,
            organization=record_data.organization,
            location=record_data.location,
            pre_calibration_measurements=record_data.pre_calibration_measurements,
            post_calibration_measurements=record_data.post_calibration_measurements,
            standards_used=record_data.standards_used,
            temperature_celsius=record_data.temperature_celsius,
            humidity_percent=record_data.humidity_percent,
            adjustments_made=record_data.adjustments_made,
            out_of_tolerance_items=record_data.out_of_tolerance_items,
            notes=record_data.notes,
            certificate_number=record_data.certificate_number
        )

        added_record = await cal_manager.add_calibration_record(record)

        return {
            "success": True,
            "calibration_id": added_record.calibration_id,
            "record": added_record.dict()
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid value: {str(e)}")
    except Exception as e:
        logger.error(f"Error adding calibration record: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add record: {str(e)}")


@router.get("/calibration/records/{equipment_id}", summary="Get calibration history")
async def get_calibration_history(equipment_id: str, limit: Optional[int] = None):
    """Get calibration history for equipment."""
    cal_manager = get_calibration_manager()

    if not cal_manager:
        raise HTTPException(status_code=503, detail="Calibration manager not initialized")

    try:
        history = await cal_manager.get_calibration_history(equipment_id, limit)

        return {
            "success": True,
            "equipment_id": equipment_id,
            "count": len(history),
            "records": [record.dict() for record in history]
        }

    except Exception as e:
        logger.error(f"Error getting calibration history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get history: {str(e)}")


@router.get("/calibration/records/{equipment_id}/latest", summary="Get latest calibration")
async def get_latest_calibration(equipment_id: str):
    """Get most recent calibration record."""
    cal_manager = get_calibration_manager()

    if not cal_manager:
        raise HTTPException(status_code=503, detail="Calibration manager not initialized")

    try:
        latest = await cal_manager.get_latest_calibration(equipment_id)

        if latest is None:
            return {
                "success": True,
                "equipment_id": equipment_id,
                "has_calibration": False,
                "record": None
            }

        return {
            "success": True,
            "equipment_id": equipment_id,
            "has_calibration": True,
            "record": latest.dict()
        }

    except Exception as e:
        logger.error(f"Error getting latest calibration: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get calibration: {str(e)}")


@router.delete("/calibration/records/{equipment_id}/{calibration_id}", summary="Delete calibration record")
async def delete_calibration_record(equipment_id: str, calibration_id: str):
    """Delete a calibration record."""
    cal_manager = get_calibration_manager()

    if not cal_manager:
        raise HTTPException(status_code=503, detail="Calibration manager not initialized")

    try:
        deleted = await cal_manager.delete_calibration_record(equipment_id, calibration_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="Calibration record not found")

        return {
            "success": True,
            "message": f"Calibration record {calibration_id} deleted"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting calibration record: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete record: {str(e)}")


# ==================== Calibration Status Endpoints ====================


@router.get("/calibration/status/{equipment_id}", summary="Get calibration status")
async def get_calibration_status(equipment_id: str):
    """Get current calibration status for equipment."""
    cal_manager = get_calibration_manager()

    if not cal_manager:
        raise HTTPException(status_code=503, detail="Calibration manager not initialized")

    try:
        status = await cal_manager.get_calibration_status(equipment_id)
        is_current = await cal_manager.is_calibration_current(equipment_id)
        days_until_due = await cal_manager.get_days_until_due(equipment_id)
        latest = await cal_manager.get_latest_calibration(equipment_id)

        return {
            "success": True,
            "equipment_id": equipment_id,
            "status": status.value,
            "is_current": is_current,
            "days_until_due": days_until_due,
            "last_calibration_date": latest.calibration_date if latest else None,
            "next_due_date": latest.due_date if latest else None
        }

    except Exception as e:
        logger.error(f"Error getting calibration status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@router.get("/calibration/due", summary="Get due calibrations")
async def get_due_calibrations(include_due_soon: bool = True):
    """Get list of equipment with calibrations due."""
    cal_manager = get_calibration_manager()

    if not cal_manager:
        raise HTTPException(status_code=503, detail="Calibration manager not initialized")

    try:
        due_list = await cal_manager.get_due_calibrations(include_due_soon)

        return {
            "success": True,
            "count": len(due_list),
            "equipment": due_list
        }

    except Exception as e:
        logger.error(f"Error getting due calibrations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get due calibrations: {str(e)}")


# ==================== Calibration Schedule Endpoints ====================


@router.post("/calibration/schedules", summary="Set calibration schedule")
async def set_calibration_schedule(schedule_data: CalibrationScheduleCreate):
    """Set calibration schedule for equipment."""
    cal_manager = get_calibration_manager()

    if not cal_manager:
        raise HTTPException(status_code=503, detail="Calibration manager not initialized")

    try:
        schedule = CalibrationSchedule(
            equipment_id=schedule_data.equipment_id,
            interval_days=schedule_data.interval_days,
            warning_days=schedule_data.warning_days,
            auto_schedule=schedule_data.auto_schedule,
            notify_due_soon=schedule_data.notify_due_soon,
            notify_overdue=schedule_data.notify_overdue,
            notification_emails=schedule_data.notification_emails
        )

        await cal_manager.set_calibration_schedule(schedule)

        return {
            "success": True,
            "message": "Calibration schedule set",
            "schedule": schedule.dict()
        }

    except Exception as e:
        logger.error(f"Error setting calibration schedule: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to set schedule: {str(e)}")


@router.get("/calibration/schedules/{equipment_id}", summary="Get calibration schedule")
async def get_calibration_schedule(equipment_id: str):
    """Get calibration schedule for equipment."""
    cal_manager = get_calibration_manager()

    if not cal_manager:
        raise HTTPException(status_code=503, detail="Calibration manager not initialized")

    try:
        schedule = await cal_manager.get_calibration_schedule(equipment_id)

        if schedule is None:
            return {
                "success": True,
                "equipment_id": equipment_id,
                "has_schedule": False,
                "schedule": None
            }

        return {
            "success": True,
            "equipment_id": equipment_id,
            "has_schedule": True,
            "schedule": schedule.dict()
        }

    except Exception as e:
        logger.error(f"Error getting calibration schedule: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get schedule: {str(e)}")


@router.delete("/calibration/schedules/{equipment_id}", summary="Delete calibration schedule")
async def delete_calibration_schedule(equipment_id: str):
    """Delete calibration schedule."""
    cal_manager = get_calibration_manager()

    if not cal_manager:
        raise HTTPException(status_code=503, detail="Calibration manager not initialized")

    try:
        deleted = await cal_manager.delete_calibration_schedule(equipment_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="Schedule not found")

        return {
            "success": True,
            "message": f"Calibration schedule deleted for {equipment_id}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting calibration schedule: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete schedule: {str(e)}")


# ==================== Calibration Reporting ====================


@router.get("/calibration/report", summary="Generate calibration report")
async def generate_calibration_report(equipment_ids: Optional[List[str]] = None):
    """Generate calibration status report."""
    cal_manager = get_calibration_manager()

    if not cal_manager:
        raise HTTPException(status_code=503, detail="Calibration manager not initialized")

    try:
        report = await cal_manager.generate_calibration_report(equipment_ids)

        return {
            "success": True,
            "report": report
        }

    except Exception as e:
        logger.error(f"Error generating calibration report: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")
