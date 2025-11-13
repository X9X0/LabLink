"""Data acquisition API endpoints."""

import logging
from typing import Any
from fastapi import APIRouter, HTTPException

from shared.models.commands import DataStreamConfig

from server.equipment.manager import equipment_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/stream/configure")
async def configure_stream(config: DataStreamConfig):
    """Configure data streaming for a device."""
    try:
        equipment = equipment_manager.get_equipment(config.equipment_id)
        if equipment is None:
            raise HTTPException(status_code=404, detail="Device not found")

        # Store streaming configuration
        # TODO: Implement streaming manager
        return {"status": "configured", "config": config.dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error configuring stream: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{equipment_id}/snapshot")
async def get_data_snapshot(equipment_id: str, data_type: str = "readings"):
    """Get a single snapshot of data from a device."""
    try:
        equipment = equipment_manager.get_equipment(equipment_id)
        if equipment is None:
            raise HTTPException(status_code=404, detail="Device not found")

        # Execute appropriate command based on data type and equipment
        if data_type == "readings":
            result = await equipment.execute_command("get_readings", {})
        elif data_type == "waveform":
            result = await equipment.execute_command("get_waveform", {"channel": 1})
        elif data_type == "measurements":
            result = await equipment.execute_command("get_measurements", {"channel": 1})
        else:
            raise HTTPException(status_code=400, detail=f"Unknown data type: {data_type}")

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting data snapshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))
