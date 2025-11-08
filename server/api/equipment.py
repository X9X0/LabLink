"""Equipment management API endpoints."""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import sys
sys.path.append("../../shared")
from models.equipment import EquipmentInfo, EquipmentStatus, EquipmentType, EquipmentCommand
from models.commands import Command, CommandResponse

from equipment.manager import equipment_manager
from equipment.locks import lock_manager
from config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# Commands that require exclusive control (vs read-only)
CONTROL_COMMANDS = {
    "set_voltage", "set_current", "set_output", "set_input",
    "set_mode", "set_range", "set_channel", "set_trigger",
    "set_timebase", "set_scale", "set_position", "set_offset",
    "reset", "clear", "save", "recall", "calibrate"
}


def requires_control(action: str) -> bool:
    """Check if an action requires exclusive equipment control."""
    action_lower = action.lower()
    return any(cmd in action_lower for cmd in CONTROL_COMMANDS)


class ConnectDeviceRequest(BaseModel):
    """Request to connect to a device."""
    resource_string: str
    equipment_type: EquipmentType
    model: str


class DiscoverDevicesResponse(BaseModel):
    """Response for device discovery."""
    resources: List[str]


@router.get("/discover", response_model=DiscoverDevicesResponse)
async def discover_devices():
    """Discover available VISA devices."""
    try:
        resources = await equipment_manager.discover_devices()
        return DiscoverDevicesResponse(resources=resources)
    except Exception as e:
        logger.error(f"Error discovering devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/connect", response_model=dict)
async def connect_device(request: ConnectDeviceRequest):
    """Connect to a device."""
    try:
        equipment_id = await equipment_manager.connect_device(
            request.resource_string,
            request.equipment_type,
            request.model,
        )
        return {"equipment_id": equipment_id, "status": "connected"}
    except Exception as e:
        logger.error(f"Error connecting device: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disconnect/{equipment_id}")
async def disconnect_device(equipment_id: str, session_id: Optional[str] = None):
    """Disconnect a device."""
    try:
        # Release locks for this equipment
        if settings.enable_equipment_locks and session_id:
            try:
                await lock_manager.release_lock(equipment_id, session_id, force=False)
            except Exception as e:
                logger.warning(f"Error releasing lock during disconnect: {e}")

        await equipment_manager.disconnect_device(equipment_id)
        return {"equipment_id": equipment_id, "status": "disconnected"}
    except Exception as e:
        logger.error(f"Error disconnecting device: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list", response_model=List[EquipmentInfo])
async def list_devices():
    """List all connected devices."""
    try:
        devices = equipment_manager.get_connected_devices()
        return devices
    except Exception as e:
        logger.error(f"Error listing devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{equipment_id}/status", response_model=EquipmentStatus)
async def get_device_status(equipment_id: str):
    """Get status of a specific device."""
    try:
        status = await equipment_manager.get_device_status(equipment_id)
        if status is None:
            raise HTTPException(status_code=404, detail="Device not found")
        return status
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting device status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{equipment_id}/command", response_model=CommandResponse)
async def execute_command(equipment_id: str, command: Command):
    """Execute a command on a device."""
    try:
        equipment = equipment_manager.get_equipment(equipment_id)
        if equipment is None:
            raise HTTPException(status_code=404, detail="Device not found")

        # Check lock requirements if enabled
        if settings.enable_equipment_locks:
            is_control_command = requires_control(command.action)

            if is_control_command:
                # Control commands require exclusive lock
                if not command.session_id:
                    raise HTTPException(
                        status_code=401,
                        detail="session_id required for control commands when locks are enabled"
                    )

                if not lock_manager.can_control_equipment(equipment_id, command.session_id):
                    lock_status = lock_manager.get_lock_status(equipment_id)
                    current_owner = lock_status.get("session_id", "unknown")
                    raise HTTPException(
                        status_code=403,
                        detail=f"Equipment {equipment_id} is locked by session {current_owner}. "
                               f"Acquire exclusive lock before control commands."
                    )

                # Update lock activity
                lock_manager.update_lock_activity(equipment_id, command.session_id)

            else:
                # Read-only commands require at least observer access
                if command.session_id:
                    if not lock_manager.can_observe_equipment(equipment_id, command.session_id):
                        raise HTTPException(
                            status_code=403,
                            detail=f"No observer or control access to equipment {equipment_id}"
                        )

                    # Update lock activity if session has a lock
                    lock_manager.update_lock_activity(equipment_id, command.session_id)

        result = await equipment.execute_command(command.action, command.parameters)

        return CommandResponse(
            command_id=command.command_id,
            success=True,
            data=result,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing command: {e}")
        return CommandResponse(
            command_id=command.command_id,
            success=False,
            error=str(e),
        )
