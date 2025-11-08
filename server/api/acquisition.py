"""REST API endpoints for data acquisition."""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from equipment.manager import equipment_manager
from acquisition import (
    acquisition_manager,
    AcquisitionConfig,
    AcquisitionMode,
    TriggerType,
    TriggerConfig,
    ExportFormat,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/acquisition", tags=["Data Acquisition"])


# ============================================================================
# Request/Response Models
# ============================================================================

class CreateSessionRequest(BaseModel):
    """Request to create acquisition session."""
    equipment_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    mode: AcquisitionMode = AcquisitionMode.CONTINUOUS
    sample_rate: float = Field(default=1.0, gt=0)
    num_samples: Optional[int] = Field(None, ge=1)
    duration_seconds: Optional[float] = Field(None, gt=0)
    channels: List[str] = Field(default=["CH1"])
    buffer_size: int = Field(default=10000, ge=100)
    auto_export: bool = False
    export_format: ExportFormat = ExportFormat.CSV


class ExportDataRequest(BaseModel):
    """Request to export acquisition data."""
    acquisition_id: str
    format: ExportFormat = ExportFormat.CSV
    filepath: Optional[str] = None


# ============================================================================
# Session Management Endpoints
# ============================================================================

@router.post("/session/create", summary="Create acquisition session")
async def create_session(request: CreateSessionRequest):
    """
    Create a new data acquisition session.

    - Configure acquisition parameters
    - Set up circular buffer
    - Prepare for data collection
    """
    try:
        equipment = equipment_manager.get_equipment(request.equipment_id)
        if not equipment:
            raise HTTPException(
                status_code=404,
                detail=f"Equipment {request.equipment_id} not found"
            )

        config = AcquisitionConfig(
            equipment_id=request.equipment_id,
            name=request.name,
            description=request.description,
            mode=request.mode,
            sample_rate=request.sample_rate,
            num_samples=request.num_samples,
            duration_seconds=request.duration_seconds,
            channels=request.channels,
            buffer_size=request.buffer_size,
            auto_export=request.auto_export,
            export_format=request.export_format
        )

        session = await acquisition_manager.create_session(equipment, config)

        return {
            "success": True,
            "message": "Acquisition session created",
            "acquisition_id": session.acquisition_id,
            "state": session.state
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating acquisition session: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create session: {str(e)}"
        )


@router.post("/session/{acquisition_id}/start", summary="Start acquisition")
async def start_acquisition(acquisition_id: str):
    """Start data acquisition for a session."""
    try:
        session = acquisition_manager.get_session(acquisition_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Acquisition {acquisition_id} not found"
            )

        equipment = equipment_manager.get_equipment(session.equipment_id)
        if not equipment:
            raise HTTPException(
                status_code=404,
                detail=f"Equipment {session.equipment_id} not found"
            )

        success = await acquisition_manager.start_acquisition(acquisition_id, equipment)

        return {
            "success": success,
            "message": "Acquisition started" if success else "Already running",
            "acquisition_id": acquisition_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting acquisition: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start acquisition: {str(e)}"
        )


@router.post("/session/{acquisition_id}/stop", summary="Stop acquisition")
async def stop_acquisition(acquisition_id: str):
    """Stop data acquisition."""
    try:
        success = await acquisition_manager.stop_acquisition(acquisition_id)

        return {
            "success": success,
            "message": "Acquisition stopped",
            "acquisition_id": acquisition_id
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error stopping acquisition: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop acquisition: {str(e)}"
        )


@router.post("/session/{acquisition_id}/pause", summary="Pause acquisition")
async def pause_acquisition(acquisition_id: str):
    """Pause data acquisition."""
    try:
        success = await acquisition_manager.pause_acquisition(acquisition_id)

        return {
            "success": success,
            "message": "Acquisition paused" if success else "Not acquiring",
            "acquisition_id": acquisition_id
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error pausing acquisition: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to pause acquisition: {str(e)}"
        )


@router.post("/session/{acquisition_id}/resume", summary="Resume acquisition")
async def resume_acquisition(acquisition_id: str):
    """Resume paused acquisition."""
    try:
        success = await acquisition_manager.resume_acquisition(acquisition_id)

        return {
            "success": success,
            "message": "Acquisition resumed" if success else "Not paused",
            "acquisition_id": acquisition_id
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error resuming acquisition: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to resume acquisition: {str(e)}"
        )


# ============================================================================
# Data Retrieval Endpoints
# ============================================================================

@router.get("/session/{acquisition_id}/status", summary="Get session status")
async def get_session_status(acquisition_id: str):
    """Get acquisition session status and statistics."""
    try:
        session = acquisition_manager.get_session(acquisition_id)

        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Acquisition {acquisition_id} not found"
            )

        return {
            "acquisition_id": session.acquisition_id,
            "equipment_id": session.equipment_id,
            "state": session.state,
            "config": session.config.dict(),
            "stats": session.stats.dict(),
            "created_at": session.created_at.isoformat(),
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "stopped_at": session.stopped_at.isoformat() if session.stopped_at else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get status: {str(e)}"
        )


@router.get("/session/{acquisition_id}/data", summary="Get acquired data")
async def get_acquisition_data(
    acquisition_id: str,
    num_samples: Optional[int] = Query(None, description="Number of samples to retrieve")
):
    """Get data from acquisition buffer."""
    try:
        data, timestamps = acquisition_manager.get_buffer_data(acquisition_id, num_samples)

        session = acquisition_manager.get_session(acquisition_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Acquisition {acquisition_id} not found"
            )

        # Convert to JSON-serializable format
        from datetime import datetime
        return {
            "acquisition_id": acquisition_id,
            "channels": session.config.channels,
            "data": {
                "timestamps": [datetime.fromtimestamp(t).isoformat() for t in timestamps],
                "values": {
                    channel: data[i, :].tolist()
                    for i, channel in enumerate(session.config.channels)
                }
            },
            "count": len(timestamps)
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting data: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get data: {str(e)}"
        )


@router.get("/sessions", summary="List all sessions")
async def list_sessions():
    """Get all acquisition sessions."""
    try:
        sessions = acquisition_manager.get_all_sessions()

        return {
            "sessions": [
                {
                    "acquisition_id": s.acquisition_id,
                    "equipment_id": s.equipment_id,
                    "name": s.config.name,
                    "state": s.state,
                    "mode": s.config.mode,
                    "created_at": s.created_at.isoformat(),
                    "total_samples": s.stats.total_samples
                }
                for s in sessions
            ],
            "count": len(sessions)
        }

    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list sessions: {str(e)}"
        )


# ============================================================================
# Export Endpoints
# ============================================================================

@router.post("/export", summary="Export acquisition data")
async def export_data(request: ExportDataRequest):
    """Export acquired data to file."""
    try:
        filepath = await acquisition_manager.export_data(
            request.acquisition_id,
            request.format,
            request.filepath
        )

        return {
            "success": True,
            "message": "Data exported successfully",
            "filepath": filepath,
            "format": request.format
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error exporting data: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to export data: {str(e)}"
        )


@router.delete("/session/{acquisition_id}", summary="Delete session")
async def delete_session(acquisition_id: str):
    """Delete an acquisition session."""
    try:
        success = await acquisition_manager.delete_session(acquisition_id)

        if success:
            return {
                "success": True,
                "message": "Session deleted",
                "acquisition_id": acquisition_id
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Acquisition {acquisition_id} not found"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete session: {str(e)}"
        )
