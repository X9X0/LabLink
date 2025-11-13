"""REST API endpoints for data acquisition."""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from server.equipment.manager import equipment_manager
from acquisition import (
    acquisition_manager,
    AcquisitionConfig,
    AcquisitionMode,
    TriggerType,
    TriggerConfig,
    ExportFormat,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Data Acquisition"])


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


# ==================== Statistics Endpoints ====================


@router.get("/session/{acquisition_id}/stats/rolling", summary="Get rolling statistics")
async def get_rolling_stats(
    acquisition_id: str,
    channel: str,
    num_samples: Optional[int] = None
):
    """
    Get rolling statistics for a channel.

    Args:
        acquisition_id: Acquisition session ID
        channel: Channel name
        num_samples: Number of samples to analyze (None = all)

    Returns:
        Rolling statistics (mean, std, min, max, etc.)
    """
    try:
        stats = acquisition_manager.compute_rolling_stats(acquisition_id, channel, num_samples)

        if stats is None:
            raise HTTPException(
                status_code=404,
                detail=f"Session {acquisition_id} not found or channel {channel} invalid"
            )

        return {
            "success": True,
            "acquisition_id": acquisition_id,
            "channel": channel,
            "stats": {
                "mean": stats.mean,
                "std": stats.std,
                "min": stats.min,
                "max": stats.max,
                "median": stats.median,
                "rms": stats.rms,
                "peak_to_peak": stats.peak_to_peak,
                "num_samples": stats.num_samples
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error computing rolling stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to compute statistics: {str(e)}"
        )


@router.get("/session/{acquisition_id}/stats/fft", summary="Get FFT analysis")
async def get_fft_analysis(
    acquisition_id: str,
    channel: str,
    num_samples: Optional[int] = None,
    window: str = "hann"
):
    """
    Get FFT frequency analysis for a channel.

    Args:
        acquisition_id: Acquisition session ID
        channel: Channel name
        num_samples: Number of samples to analyze (None = all)
        window: Window function (hann, hamming, blackman)

    Returns:
        FFT analysis with frequencies, magnitudes, dominant frequency, THD, SNR
    """
    try:
        fft_result = acquisition_manager.compute_fft(acquisition_id, channel, num_samples, window)

        if fft_result is None:
            raise HTTPException(
                status_code=404,
                detail=f"Session {acquisition_id} not found or channel {channel} invalid"
            )

        return {
            "success": True,
            "acquisition_id": acquisition_id,
            "channel": channel,
            "fft": {
                "frequencies": fft_result.frequencies.tolist(),
                "magnitudes": fft_result.magnitudes.tolist(),
                "phases": fft_result.phases.tolist(),
                "dominant_frequency": fft_result.dominant_frequency,
                "fundamental_amplitude": fft_result.fundamental_amplitude,
                "thd_percent": fft_result.thd,
                "snr_db": fft_result.snr
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error computing FFT: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to compute FFT: {str(e)}"
        )


@router.get("/session/{acquisition_id}/stats/trend", summary="Detect trend")
async def detect_trend(
    acquisition_id: str,
    channel: str,
    num_samples: Optional[int] = None
):
    """
    Detect trend in channel data.

    Args:
        acquisition_id: Acquisition session ID
        channel: Channel name
        num_samples: Number of samples to analyze (None = all)

    Returns:
        Trend analysis (rising, falling, stable, noisy)
    """
    try:
        trend_result = acquisition_manager.detect_trend(acquisition_id, channel, num_samples)

        if trend_result is None:
            raise HTTPException(
                status_code=404,
                detail=f"Session {acquisition_id} not found or channel {channel} invalid"
            )

        return {
            "success": True,
            "acquisition_id": acquisition_id,
            "channel": channel,
            "trend": {
                "type": trend_result.trend,
                "slope": trend_result.slope,
                "r_squared": trend_result.r_squared,
                "confidence": trend_result.confidence
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error detecting trend: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to detect trend: {str(e)}"
        )


@router.get("/session/{acquisition_id}/stats/quality", summary="Assess data quality")
async def assess_quality(
    acquisition_id: str,
    channel: str,
    num_samples: Optional[int] = None,
    outlier_threshold: float = 3.0
):
    """
    Assess data quality for a channel.

    Args:
        acquisition_id: Acquisition session ID
        channel: Channel name
        num_samples: Number of samples to analyze (None = all)
        outlier_threshold: Number of std deviations for outlier detection

    Returns:
        Data quality metrics (noise level, stability, outliers)
    """
    try:
        quality = acquisition_manager.assess_data_quality(
            acquisition_id, channel, num_samples, outlier_threshold
        )

        if quality is None:
            raise HTTPException(
                status_code=404,
                detail=f"Session {acquisition_id} not found or channel {channel} invalid"
            )

        return {
            "success": True,
            "acquisition_id": acquisition_id,
            "channel": channel,
            "quality": {
                "noise_level": quality.noise_level,
                "stability_score": quality.stability_score,
                "outlier_count": quality.outlier_count,
                "missing_count": quality.missing_count,
                "valid_percentage": quality.valid_percentage
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assessing quality: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to assess quality: {str(e)}"
        )


@router.get("/session/{acquisition_id}/stats/peaks", summary="Detect peaks")
async def detect_peaks(
    acquisition_id: str,
    channel: str,
    num_samples: Optional[int] = None,
    prominence: Optional[float] = None,
    distance: Optional[int] = None,
    height: Optional[float] = None
):
    """
    Detect peaks in channel data.

    Args:
        acquisition_id: Acquisition session ID
        channel: Channel name
        num_samples: Number of samples to analyze (None = all)
        prominence: Required prominence of peaks
        distance: Minimum distance between peaks
        height: Minimum height of peaks

    Returns:
        Peak information (indices, values, count)
    """
    try:
        peaks = acquisition_manager.detect_peaks(
            acquisition_id, channel, num_samples, prominence, distance, height
        )

        if peaks is None:
            raise HTTPException(
                status_code=404,
                detail=f"Session {acquisition_id} not found or channel {channel} invalid"
            )

        return {
            "success": True,
            "acquisition_id": acquisition_id,
            "channel": channel,
            "peaks": {
                "indices": peaks.indices.tolist(),
                "values": peaks.values.tolist(),
                "count": peaks.count
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error detecting peaks: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to detect peaks: {str(e)}"
        )


@router.get("/session/{acquisition_id}/stats/crossings", summary="Detect threshold crossings")
async def detect_crossings(
    acquisition_id: str,
    channel: str,
    threshold: float,
    direction: str = "both",
    num_samples: Optional[int] = None
):
    """
    Detect threshold crossings in channel data.

    Args:
        acquisition_id: Acquisition session ID
        channel: Channel name
        threshold: Threshold value
        direction: 'rising', 'falling', or 'both'
        num_samples: Number of samples to analyze (None = all)

    Returns:
        Threshold crossing indices
    """
    try:
        if direction not in ["rising", "falling", "both"]:
            raise HTTPException(
                status_code=400,
                detail="Direction must be 'rising', 'falling', or 'both'"
            )

        crossings = acquisition_manager.detect_threshold_crossings(
            acquisition_id, channel, threshold, direction, num_samples
        )

        if crossings is None:
            raise HTTPException(
                status_code=404,
                detail=f"Session {acquisition_id} not found or channel {channel} invalid"
            )

        return {
            "success": True,
            "acquisition_id": acquisition_id,
            "channel": channel,
            "threshold": threshold,
            "crossings": {
                "rising": crossings["rising"].tolist(),
                "falling": crossings["falling"].tolist(),
                "total": len(crossings["rising"]) + len(crossings["falling"])
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error detecting crossings: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to detect crossings: {str(e)}"
        )


# ==================== Synchronization Endpoints ====================


class CreateSyncGroupRequest(BaseModel):
    """Request to create a synchronization group."""
    group_id: str
    equipment_ids: List[str]
    master_equipment_id: Optional[str] = None
    sync_tolerance_ms: float = 10.0
    wait_for_all: bool = True
    auto_align_timestamps: bool = True


class AddToSyncGroupRequest(BaseModel):
    """Request to add acquisition to sync group."""
    equipment_id: str
    acquisition_id: str


@router.post("/sync/group/create", summary="Create synchronization group")
async def create_sync_group(request: CreateSyncGroupRequest):
    """
    Create a multi-instrument synchronization group.

    Args:
        request: Sync group configuration

    Returns:
        Sync group status
    """
    try:
        from acquisition.synchronization import sync_manager, SyncConfig

        config = SyncConfig(
            group_id=request.group_id,
            equipment_ids=request.equipment_ids,
            master_equipment_id=request.master_equipment_id,
            sync_tolerance_ms=request.sync_tolerance_ms,
            wait_for_all=request.wait_for_all,
            auto_align_timestamps=request.auto_align_timestamps
        )

        group = await sync_manager.create_sync_group(config)

        return {
            "success": True,
            "message": "Sync group created",
            "status": {
                "group_id": group.config.group_id,
                "state": group.state,
                "equipment_count": len(group.config.equipment_ids),
                "equipment_ids": group.config.equipment_ids,
                "master": group.config.master_equipment_id
            }
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating sync group: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create sync group: {str(e)}"
        )


@router.post("/sync/group/{group_id}/add", summary="Add acquisition to sync group")
async def add_to_sync_group(group_id: str, request: AddToSyncGroupRequest):
    """Add an acquisition session to a synchronization group."""
    try:
        from acquisition.synchronization import sync_manager

        group = await sync_manager.get_sync_group(group_id)
        if group is None:
            raise HTTPException(
                status_code=404,
                detail=f"Sync group {group_id} not found"
            )

        await group.add_acquisition(request.equipment_id, request.acquisition_id)

        return {
            "success": True,
            "message": "Acquisition added to sync group",
            "status": {
                "group_id": group_id,
                "state": group.state,
                "ready_count": len(group.ready_equipment),
                "total_count": len(group.config.equipment_ids)
            }
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding to sync group: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to add to sync group: {str(e)}"
        )


@router.post("/sync/group/{group_id}/start", summary="Start synchronized acquisition")
async def start_sync_group(group_id: str):
    """Start all acquisitions in a sync group simultaneously."""
    try:
        from acquisition.synchronization import sync_manager

        group = await sync_manager.get_sync_group(group_id)
        if group is None:
            raise HTTPException(
                status_code=404,
                detail=f"Sync group {group_id} not found"
            )

        success = await group.start_synchronized(acquisition_manager)

        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to start sync group: {group.sync_errors}"
            )

        return {
            "success": True,
            "message": "Sync group started",
            "status": {
                "group_id": group_id,
                "state": group.state,
                "start_time": group.start_time.isoformat() if group.start_time else None,
                "acquisition_ids": group.acquisition_ids
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting sync group: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start sync group: {str(e)}"
        )


@router.post("/sync/group/{group_id}/stop", summary="Stop synchronized acquisition")
async def stop_sync_group(group_id: str):
    """Stop all acquisitions in a sync group."""
    try:
        from acquisition.synchronization import sync_manager

        group = await sync_manager.get_sync_group(group_id)
        if group is None:
            raise HTTPException(
                status_code=404,
                detail=f"Sync group {group_id} not found"
            )

        success = await group.stop_synchronized(acquisition_manager)

        if not success:
            raise HTTPException(
                status_code=400,
                detail="Sync group not in running state"
            )

        return {
            "success": True,
            "message": "Sync group stopped",
            "group_id": group_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping sync group: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop sync group: {str(e)}"
        )


@router.post("/sync/group/{group_id}/pause", summary="Pause synchronized acquisition")
async def pause_sync_group(group_id: str):
    """Pause all acquisitions in a sync group."""
    try:
        from acquisition.synchronization import sync_manager

        group = await sync_manager.get_sync_group(group_id)
        if group is None:
            raise HTTPException(
                status_code=404,
                detail=f"Sync group {group_id} not found"
            )

        success = await group.pause_synchronized(acquisition_manager)

        if not success:
            raise HTTPException(
                status_code=400,
                detail="Sync group not in running state"
            )

        return {
            "success": True,
            "message": "Sync group paused",
            "group_id": group_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing sync group: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to pause sync group: {str(e)}"
        )


@router.post("/sync/group/{group_id}/resume", summary="Resume synchronized acquisition")
async def resume_sync_group(group_id: str):
    """Resume all acquisitions in a sync group."""
    try:
        from acquisition.synchronization import sync_manager

        group = await sync_manager.get_sync_group(group_id)
        if group is None:
            raise HTTPException(
                status_code=404,
                detail=f"Sync group {group_id} not found"
            )

        success = await group.resume_synchronized(acquisition_manager)

        if not success:
            raise HTTPException(
                status_code=400,
                detail="Sync group not in paused state"
            )

        return {
            "success": True,
            "message": "Sync group resumed",
            "group_id": group_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming sync group: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to resume sync group: {str(e)}"
        )


@router.get("/sync/group/{group_id}/status", summary="Get sync group status")
async def get_sync_group_status(group_id: str):
    """Get status of a synchronization group."""
    try:
        from acquisition.synchronization import sync_manager

        status = await sync_manager.get_group_status(group_id)

        if status is None:
            raise HTTPException(
                status_code=404,
                detail=f"Sync group {group_id} not found"
            )

        return {
            "success": True,
            "status": {
                "group_id": status.group_id,
                "state": status.state,
                "equipment_count": status.equipment_count,
                "ready_count": status.ready_count,
                "running_count": status.running_count,
                "acquisition_ids": status.acquisition_ids,
                "start_time": status.start_time.isoformat() if status.start_time else None,
                "sync_errors": status.sync_errors
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting sync group status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get status: {str(e)}"
        )


@router.get("/sync/group/{group_id}/data", summary="Get synchronized data")
async def get_sync_group_data(group_id: str, num_samples: Optional[int] = None):
    """Get synchronized data from all acquisitions in a group."""
    try:
        from acquisition.synchronization import sync_manager

        group = await sync_manager.get_sync_group(group_id)
        if group is None:
            raise HTTPException(
                status_code=404,
                detail=f"Sync group {group_id} not found"
            )

        synchronized_data = await group.get_synchronized_data(acquisition_manager, num_samples)

        # Convert to JSON-serializable format
        response_data = {}
        for equipment_id, data_dict in synchronized_data.items():
            response_data[equipment_id] = {
                "data": data_dict["data"].tolist(),
                "timestamps": data_dict["timestamps"].tolist()
            }

        return {
            "success": True,
            "group_id": group_id,
            "data": response_data
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting sync group data: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get data: {str(e)}"
        )


@router.get("/sync/groups", summary="List all sync groups")
async def list_sync_groups():
    """List all synchronization groups."""
    try:
        from acquisition.synchronization import sync_manager

        groups = await sync_manager.list_sync_groups()

        return {
            "success": True,
            "count": len(groups),
            "groups": [
                {
                    "group_id": status.group_id,
                    "state": status.state,
                    "equipment_count": status.equipment_count,
                    "ready_count": status.ready_count,
                    "running_count": status.running_count
                }
                for status in groups
            ]
        }

    except Exception as e:
        logger.error(f"Error listing sync groups: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list sync groups: {str(e)}"
        )


@router.delete("/sync/group/{group_id}", summary="Delete sync group")
async def delete_sync_group(group_id: str):
    """Delete a synchronization group."""
    try:
        from acquisition.synchronization import sync_manager

        success = await sync_manager.delete_sync_group(group_id)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Sync group {group_id} not found"
            )

        return {
            "success": True,
            "message": "Sync group deleted",
            "group_id": group_id
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting sync group: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete sync group: {str(e)}"
        )
