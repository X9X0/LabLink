"""API endpoints for safety and emergency stop functionality."""

import logging
from typing import List

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from server.equipment.manager import equipment_manager
from server.equipment.safety import SafetyEvent, emergency_stop_manager

logger = logging.getLogger(__name__)

router = APIRouter()


class EmergencyStopResponse(BaseModel):
    """Response for emergency stop operations."""

    success: bool
    message: str
    active: bool
    stop_time: str = None
    equipment_count: int = 0


class SafetyStatusResponse(BaseModel):
    """Response for safety status."""

    emergency_stop_active: bool
    stopped_equipment: List[str]
    equipment_with_safety: int
    total_equipment: int


@router.post("/emergency-stop/activate", response_model=EmergencyStopResponse)
async def activate_emergency_stop():
    """
    Activate emergency stop - disables all equipment outputs immediately.

    This is a critical safety feature that:
    - Disables all power supply outputs
    - Disables all electronic load inputs
    - Stops all ongoing operations
    - Logs the emergency stop event

    Returns:
        Emergency stop status
    """
    try:
        logger.critical("🛑 EMERGENCY STOP REQUESTED VIA API 🛑")

        # Activate emergency stop
        result = emergency_stop_manager.activate_emergency_stop()

        # Disable all equipment outputs
        disabled_count = 0
        for equipment_id, equipment in equipment_manager.equipment.items():
            try:
                # Try to disable output based on equipment type
                if hasattr(equipment, "set_output"):
                    # Power supply
                    await equipment.set_output(False)
                    disabled_count += 1
                    logger.info(f"Disabled output for {equipment_id}")
                elif hasattr(equipment, "set_input"):
                    # Electronic load
                    await equipment.set_input(False)
                    disabled_count += 1
                    logger.info(f"Disabled input for {equipment_id}")

                emergency_stop_manager.register_stopped_equipment(equipment_id)

            except Exception as e:
                logger.error(f"Error disabling {equipment_id}: {e}")

        return EmergencyStopResponse(
            success=True,
            message=f"Emergency stop activated - {disabled_count} equipment outputs disabled",
            active=True,
            stop_time=(
                result.get("stop_time").isoformat() if result.get("stop_time") else None
            ),
            equipment_count=disabled_count,
        )

    except Exception as e:
        logger.error(f"Error activating emergency stop: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to activate emergency stop: {str(e)}",
        )


@router.post("/emergency-stop/deactivate", response_model=EmergencyStopResponse)
async def deactivate_emergency_stop():
    """
    Deactivate emergency stop.

    Note: This does NOT re-enable outputs automatically.
    Outputs must be manually re-enabled by the operator.

    Returns:
        Emergency stop status
    """
    try:
        result = emergency_stop_manager.deactivate_emergency_stop()

        if result.get("already_inactive"):
            return EmergencyStopResponse(
                success=True, message="Emergency stop was not active", active=False
            )

        logger.info("Emergency stop deactivated")

        return EmergencyStopResponse(
            success=True,
            message="Emergency stop deactivated - outputs remain disabled",
            active=False,
            equipment_count=result.get("equipment_count", 0),
        )

    except Exception as e:
        logger.error(f"Error deactivating emergency stop: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deactivate emergency stop: {str(e)}",
        )


@router.get("/emergency-stop/status", response_model=EmergencyStopResponse)
async def get_emergency_stop_status():
    """
    Get current emergency stop status.

    Returns:
        Emergency stop status
    """
    status = emergency_stop_manager.get_status()

    return EmergencyStopResponse(
        success=True,
        message="Emergency stop status retrieved",
        active=status["active"],
        stop_time=status["stop_time"].isoformat() if status["stop_time"] else None,
        equipment_count=len(status["stopped_equipment"]),
    )


@router.get("/status", response_model=SafetyStatusResponse)
async def get_safety_status():
    """
    Get overall safety system status.

    Returns:
        Safety status including emergency stop and equipment safety info
    """
    try:
        e_stop_status = emergency_stop_manager.get_status()

        # Count equipment with safety validators
        equipment_with_safety = sum(
            1
            for eq in equipment_manager.equipment.values()
            if hasattr(eq, "safety_validator")
        )

        total_equipment = len(equipment_manager.equipment)

        return SafetyStatusResponse(
            emergency_stop_active=e_stop_status["active"],
            stopped_equipment=e_stop_status["stopped_equipment"],
            equipment_with_safety=equipment_with_safety,
            total_equipment=total_equipment,
        )

    except Exception as e:
        logger.error(f"Error getting safety status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get safety status: {str(e)}",
        )


@router.get("/events/{equipment_id}")
async def get_safety_events(equipment_id: str, limit: int = 50):
    """
    Get safety events for specific equipment.

    Args:
        equipment_id: Equipment identifier
        limit: Maximum number of events to return

    Returns:
        List of recent safety events
    """
    try:
        equipment = equipment_manager.get_equipment(equipment_id)

        if not equipment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Equipment '{equipment_id}' not found",
            )

        if not hasattr(equipment, "safety_validator"):
            return {
                "equipment_id": equipment_id,
                "events": [],
                "message": "No safety validator configured for this equipment",
            }

        events = equipment.safety_validator.get_safety_events(limit=limit)

        return {
            "equipment_id": equipment_id,
            "events": [e.dict() for e in events],
            "count": len(events),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting safety events: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get safety events: {str(e)}",
        )
