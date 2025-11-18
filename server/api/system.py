"""API endpoints for system management."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.system import get_version, get_version_info, update_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Request Models ====================


class UpdateCheckRequest(BaseModel):
    """Request model for checking updates."""

    git_remote: str = "origin"
    git_branch: Optional[str] = None


class UpdateStartRequest(BaseModel):
    """Request model for starting update."""

    git_remote: str = "origin"
    git_branch: Optional[str] = None


# ==================== Version Endpoints ====================


@router.get("/system/version", summary="Get server version")
async def get_server_version():
    """Get current server version information."""
    try:
        version_info = get_version_info()

        return {
            "success": True,
            "version": get_version(),
            "version_info": version_info,
        }

    except Exception as e:
        logger.error(f"Error getting version: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get version: {str(e)}"
        )


# ==================== Update Endpoints ====================


@router.get("/system/update/status", summary="Get update status")
async def get_update_status():
    """Get current update status and progress."""
    try:
        status = update_manager.get_status()

        return {"success": True, **status}

    except Exception as e:
        logger.error(f"Error getting update status: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get update status: {str(e)}"
        )


@router.post("/system/update/check", summary="Check for updates")
async def check_for_updates(request: UpdateCheckRequest):
    """Check if updates are available.

    Args:
        request: Update check configuration

    Returns:
        Update availability information
    """
    try:
        result = await update_manager.check_for_updates(
            git_remote=request.git_remote, git_branch=request.git_branch
        )

        return {"success": True, **result}

    except Exception as e:
        logger.error(f"Error checking for updates: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to check for updates: {str(e)}"
        )


@router.post("/system/update/start", summary="Start system update")
async def start_system_update(request: UpdateStartRequest):
    """Start the system update process.

    WARNING: This will pull latest code from git. In Docker environments,
    a rebuild and restart will be required.

    Args:
        request: Update configuration

    Returns:
        Update result
    """
    try:
        result = await update_manager.start_update(
            git_remote=request.git_remote, git_branch=request.git_branch
        )

        return result

    except Exception as e:
        logger.error(f"Error starting update: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to start update: {str(e)}"
        )


@router.post("/system/update/rollback", summary="Rollback to previous version")
async def rollback_system():
    """Rollback to the previous version.

    Returns:
        Rollback result
    """
    try:
        result = await update_manager.rollback()

        return result

    except Exception as e:
        logger.error(f"Error rolling back: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to rollback: {str(e)}")


# ==================== Auto-Rebuild Endpoints ====================


class AutoRebuildConfigRequest(BaseModel):
    """Request model for configuring auto-rebuild."""

    enabled: bool
    rebuild_command: Optional[str] = None


@router.post("/system/update/configure-rebuild", summary="Configure auto-rebuild")
async def configure_auto_rebuild(request: AutoRebuildConfigRequest):
    """Configure automatic Docker rebuild after updates.

    Args:
        request: Auto-rebuild configuration

    Returns:
        Configuration result
    """
    try:
        result = update_manager.configure_auto_rebuild(
            enabled=request.enabled, command=request.rebuild_command
        )

        return result

    except Exception as e:
        logger.error(f"Error configuring auto-rebuild: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to configure auto-rebuild: {str(e)}"
        )


@router.post("/system/update/rebuild", summary="Execute Docker rebuild")
async def execute_rebuild():
    """Execute Docker rebuild and restart.

    WARNING: This will rebuild Docker containers and restart the server.
    The Docker socket must be mounted or Docker CLI must be available.

    Returns:
        Rebuild result
    """
    try:
        result = await update_manager.execute_rebuild()

        return result

    except Exception as e:
        logger.error(f"Error executing rebuild: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to execute rebuild: {str(e)}"
        )


# ==================== Scheduled Check Endpoints ====================


class ScheduledCheckConfigRequest(BaseModel):
    """Request model for configuring scheduled checks."""

    enabled: bool
    interval_hours: int = 24
    git_remote: str = "origin"
    git_branch: Optional[str] = None


@router.post("/system/update/configure-scheduled", summary="Configure scheduled checks")
async def configure_scheduled_checks(request: ScheduledCheckConfigRequest):
    """Configure automatic scheduled update checking.

    Args:
        request: Scheduled check configuration

    Returns:
        Configuration result
    """
    try:
        result = update_manager.configure_scheduled_checks(
            enabled=request.enabled,
            interval_hours=request.interval_hours,
            git_remote=request.git_remote,
            git_branch=request.git_branch,
        )

        # If enabled, start the scheduled checks
        if request.enabled:
            start_result = await update_manager.start_scheduled_checks()
            result["started"] = start_result.get("success", False)

        return result

    except Exception as e:
        logger.error(f"Error configuring scheduled checks: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to configure scheduled checks: {str(e)}"
        )


@router.post("/system/update/scheduled/start", summary="Start scheduled checks")
async def start_scheduled_checks():
    """Start the scheduled update checking task.

    Returns:
        Start result
    """
    try:
        result = await update_manager.start_scheduled_checks()

        return result

    except Exception as e:
        logger.error(f"Error starting scheduled checks: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to start scheduled checks: {str(e)}"
        )


@router.post("/system/update/scheduled/stop", summary="Stop scheduled checks")
async def stop_scheduled_checks():
    """Stop the scheduled update checking task.

    Returns:
        Stop result
    """
    try:
        result = await update_manager.stop_scheduled_checks()

        return result

    except Exception as e:
        logger.error(f"Error stopping scheduled checks: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to stop scheduled checks: {str(e)}"
        )
