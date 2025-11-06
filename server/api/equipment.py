"""Equipment management API endpoints."""

import logging
from typing import List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import sys
sys.path.append("../../shared")
from models.equipment import EquipmentInfo, EquipmentStatus, EquipmentType, EquipmentCommand
from models.commands import Command, CommandResponse

from equipment.manager import equipment_manager

logger = logging.getLogger(__name__)

router = APIRouter()


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
async def disconnect_device(equipment_id: str):
    """Disconnect a device."""
    try:
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
