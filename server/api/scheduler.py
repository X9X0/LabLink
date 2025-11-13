"""API endpoints for scheduled operations."""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.scheduler import (
    scheduler_manager,
    ScheduleConfig,
    ScheduleType,
    TriggerType,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Request Models ====================


class CreateJobRequest(BaseModel):
    """Request to create a scheduled job."""
    name: str
    description: Optional[str] = None
    schedule_type: str
    equipment_id: Optional[str] = None
    trigger_type: str
    cron_expression: Optional[str] = None
    interval_seconds: Optional[int] = None
    interval_minutes: Optional[int] = None
    interval_hours: Optional[int] = None
    run_date: Optional[str] = None
    time_of_day: Optional[str] = None
    day_of_week: Optional[int] = None
    parameters: dict = {}
    enabled: bool = True
    tags: List[str] = []
    # v0.14.0: Integration fields
    profile_id: Optional[str] = None
    on_failure_alarm: bool = False
    conflict_policy: str = "skip"


# ==================== Job Management Endpoints ====================


@router.post("/scheduler/jobs/create", summary="Create scheduled job")
async def create_job(request: CreateJobRequest):
    """Create a new scheduled job."""
    try:
        config = ScheduleConfig(
            name=request.name,
            description=request.description,
            schedule_type=ScheduleType(request.schedule_type),
            equipment_id=request.equipment_id,
            trigger_type=TriggerType(request.trigger_type),
            cron_expression=request.cron_expression,
            interval_seconds=request.interval_seconds,
            interval_minutes=request.interval_minutes,
            interval_hours=request.interval_hours,
            time_of_day=request.time_of_day,
            day_of_week=request.day_of_week,
            parameters=request.parameters,
            enabled=request.enabled,
            tags=request.tags,
            profile_id=request.profile_id,
            on_failure_alarm=request.on_failure_alarm,
            conflict_policy=request.conflict_policy
        )

        result = await scheduler_manager.create_job(config)

        return {
            "success": True,
            "job_id": result.job_id,
            "message": "Job created successfully"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating job: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create job: {str(e)}")


@router.get("/scheduler/jobs/{job_id}", summary="Get job")
async def get_job(job_id: str):
    """Get job configuration by ID."""
    job = scheduler_manager.get_job(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return {
        "success": True,
        "job": job.dict()
    }


@router.get("/scheduler/jobs", summary="List jobs")
async def list_jobs(enabled: Optional[bool] = None):
    """List all scheduled jobs."""
    jobs = scheduler_manager.list_jobs(enabled=enabled)

    return {
        "success": True,
        "count": len(jobs),
        "jobs": [j.dict() for j in jobs]
    }


@router.delete("/scheduler/jobs/{job_id}", summary="Delete job")
async def delete_job(job_id: str):
    """Delete a scheduled job."""
    try:
        success = await scheduler_manager.delete_job(job_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        return {
            "success": True,
            "message": "Job deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting job: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete job: {str(e)}")


@router.post("/scheduler/jobs/{job_id}/pause", summary="Pause job")
async def pause_job(job_id: str):
    """Pause a scheduled job."""
    try:
        success = await scheduler_manager.pause_job(job_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        return {
            "success": True,
            "message": "Job paused"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing job: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to pause job: {str(e)}")


@router.post("/scheduler/jobs/{job_id}/resume", summary="Resume job")
async def resume_job(job_id: str):
    """Resume a paused job."""
    try:
        success = await scheduler_manager.resume_job(job_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        return {
            "success": True,
            "message": "Job resumed"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming job: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to resume job: {str(e)}")


@router.post("/scheduler/jobs/{job_id}/run", summary="Run job now")
async def run_job_now(job_id: str):
    """Manually trigger a job to run immediately."""
    try:
        execution = await scheduler_manager.run_job_now(job_id)

        return {
            "success": True,
            "execution_id": execution.execution_id,
            "message": "Job triggered"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error running job: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to run job: {str(e)}")


# ==================== Execution Endpoints ====================


@router.get("/scheduler/executions/{execution_id}", summary="Get execution")
async def get_execution(execution_id: str):
    """Get execution details by ID."""
    execution = scheduler_manager.get_execution(execution_id)

    if execution is None:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

    return {
        "success": True,
        "execution": execution.dict()
    }


@router.get("/scheduler/executions", summary="List executions")
async def list_executions(job_id: Optional[str] = None, limit: int = 100):
    """List job executions."""
    try:
        executions = scheduler_manager.list_executions(job_id=job_id, limit=limit)

        return {
            "success": True,
            "count": len(executions),
            "executions": [e.dict() for e in executions]
        }

    except Exception as e:
        logger.error(f"Error listing executions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list executions: {str(e)}")


@router.get("/scheduler/jobs/{job_id}/history", summary="Get job history")
async def get_job_history(job_id: str):
    """Get execution history for a job."""
    history = scheduler_manager.get_job_history(job_id)

    if history is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return {
        "success": True,
        "history": history.dict()
    }


# ==================== Statistics Endpoints ====================


@router.get("/scheduler/statistics", summary="Get scheduler statistics")
async def get_statistics():
    """Get scheduler statistics."""
    try:
        stats = scheduler_manager.get_statistics()

        return {
            "success": True,
            "statistics": stats.dict()
        }

    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")


@router.get("/scheduler/running", summary="Get running jobs")
async def get_running_jobs():
    """Get list of currently running jobs."""
    try:
        running_jobs = scheduler_manager.get_running_jobs()

        return {
            "success": True,
            "count": len(running_jobs),
            "running_jobs": running_jobs
        }

    except Exception as e:
        logger.error(f"Error getting running jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get running jobs: {str(e)}")
