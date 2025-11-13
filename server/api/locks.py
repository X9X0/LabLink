"""REST API endpoints for equipment lock and session management."""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from server.equipment.locks import (
    LockManager,
    LockMode,
    LockViolation,
    lock_manager,
)
from server.equipment.sessions import (
    SessionManager,
    SessionInfo,
    session_manager,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/locks", tags=["Equipment Locks & Sessions"])


# ============================================================================
# Request/Response Models
# ============================================================================

class AcquireLockRequest(BaseModel):
    """Request to acquire equipment lock."""
    equipment_id: str
    session_id: str
    lock_mode: LockMode = LockMode.EXCLUSIVE
    timeout_seconds: int = Field(default=300, ge=0, description="Lock timeout in seconds (0 = no timeout)")
    queue_if_busy: bool = Field(default=False, description="Add to queue if equipment is locked")


class ReleaseLockRequest(BaseModel):
    """Request to release equipment lock."""
    equipment_id: str
    session_id: str
    force: bool = Field(default=False, description="Force release (admin only)")


class UpdateActivityRequest(BaseModel):
    """Request to update lock/session activity."""
    session_id: str


class CreateSessionRequest(BaseModel):
    """Request to create a new session."""
    client_name: Optional[str] = None
    client_ip: Optional[str] = None
    timeout_seconds: int = Field(default=600, ge=0, description="Session timeout in seconds")
    metadata: Optional[dict] = None


class LockStatusResponse(BaseModel):
    """Lock status information."""
    equipment_id: str
    locked: bool
    lock_mode: Optional[str] = None
    session_id: Optional[str] = None
    lock_id: Optional[str] = None
    acquired_at: Optional[str] = None
    time_remaining: Optional[float] = None
    observer_count: Optional[int] = None
    observer_sessions: Optional[List[str]] = None
    queue_length: int = 0


class QueueStatusResponse(BaseModel):
    """Queue status information."""
    equipment_id: str
    queue: List[dict]


class SessionResponse(BaseModel):
    """Session information response."""
    session_id: str
    client_name: Optional[str]
    client_ip: Optional[str]
    created_at: str
    last_activity: str
    time_remaining: Optional[float]
    duration_seconds: float
    metadata: dict


class AllLocksResponse(BaseModel):
    """All locks information."""
    exclusive_locks: dict
    observer_locks: dict
    queues: dict


# ============================================================================
# Lock Management Endpoints
# ============================================================================

@router.post("/acquire", summary="Acquire equipment lock")
async def acquire_lock(request: AcquireLockRequest):
    """
    Acquire a lock on equipment.

    - **EXCLUSIVE** mode: Full control, blocks all other access
    - **OBSERVER** mode: Read-only, doesn't block other observers
    - Set `queue_if_busy=True` to join queue when equipment is locked
    - Lock auto-releases after `timeout_seconds` of inactivity (0 = never)
    """
    try:
        result = await lock_manager.acquire_lock(
            equipment_id=request.equipment_id,
            session_id=request.session_id,
            lock_mode=request.lock_mode,
            timeout_seconds=request.timeout_seconds,
            queue_if_busy=request.queue_if_busy
        )

        # Update session activity
        session_manager.update_session_activity(request.session_id)

        return result

    except LockViolation as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Error acquiring lock: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to acquire lock: {str(e)}")


@router.post("/release", summary="Release equipment lock")
async def release_lock(request: ReleaseLockRequest):
    """
    Release a lock on equipment.

    - Normal release: Must own the lock
    - Force release: Admin only, releases any lock (use with caution)
    - Automatically processes queue after release
    """
    try:
        result = await lock_manager.release_lock(
            equipment_id=request.equipment_id,
            session_id=request.session_id,
            force=request.force
        )

        # Update session activity
        session_manager.update_session_activity(request.session_id)

        return result

    except LockViolation as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error releasing lock: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to release lock: {str(e)}")


@router.get("/status/{equipment_id}", response_model=LockStatusResponse, summary="Get equipment lock status")
async def get_lock_status(equipment_id: str):
    """
    Get current lock status for specific equipment.

    Returns information about:
    - Lock state (locked/unlocked)
    - Lock owner (session ID)
    - Time remaining before timeout
    - Queue length
    - Observer count
    """
    try:
        status = lock_manager.get_lock_status(equipment_id)
        status["equipment_id"] = equipment_id
        return LockStatusResponse(**status)

    except Exception as e:
        logger.error(f"Error getting lock status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get lock status: {str(e)}")


@router.get("/queue/{equipment_id}", response_model=QueueStatusResponse, summary="Get equipment lock queue")
async def get_queue_status(equipment_id: str):
    """
    Get lock queue for specific equipment.

    Shows all sessions waiting for equipment access, in order.
    """
    try:
        queue = lock_manager.get_queue_status(equipment_id)
        return QueueStatusResponse(
            equipment_id=equipment_id,
            queue=[entry.dict() for entry in queue]
        )

    except Exception as e:
        logger.error(f"Error getting queue status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get queue status: {str(e)}")


@router.get("/all", response_model=AllLocksResponse, summary="Get all locks")
async def get_all_locks():
    """
    Get all current locks across all equipment.

    Returns:
    - All exclusive locks
    - All observer locks
    - All queues
    """
    try:
        return lock_manager.get_all_locks()

    except Exception as e:
        logger.error(f"Error getting all locks: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get all locks: {str(e)}")


@router.get("/events/{equipment_id}", summary="Get lock events for equipment")
async def get_lock_events(
    equipment_id: str,
    limit: int = Query(default=50, ge=1, le=1000, description="Maximum number of events to return")
):
    """
    Get lock event history for specific equipment.

    Returns recent lock/unlock events, queue changes, etc.
    """
    try:
        events = lock_manager.get_lock_events(equipment_id, limit=limit)
        return {
            "equipment_id": equipment_id,
            "events": events,
            "count": len(events)
        }

    except Exception as e:
        logger.error(f"Error getting lock events: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get lock events: {str(e)}")


@router.post("/activity/{equipment_id}", summary="Update lock activity")
async def update_lock_activity(equipment_id: str, request: UpdateActivityRequest):
    """
    Update lock activity timestamp to prevent timeout.

    Call this periodically to keep lock alive during long operations.
    """
    try:
        success = lock_manager.update_lock_activity(equipment_id, request.session_id)

        if success:
            # Also update session activity
            session_manager.update_session_activity(request.session_id)

            return {
                "success": True,
                "message": "Activity updated",
                "equipment_id": equipment_id,
                "session_id": request.session_id
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"No lock found for equipment {equipment_id} and session {request.session_id}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating lock activity: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update activity: {str(e)}")


# ============================================================================
# Session Management Endpoints
# ============================================================================

@router.post("/sessions/create", response_model=SessionResponse, summary="Create new session")
async def create_session(request: CreateSessionRequest, http_request: Request):
    """
    Create a new client session.

    Sessions track client connections and manage lock ownership.
    Auto-expires after inactivity timeout.
    """
    try:
        # Get client IP from request if not provided
        client_ip = request.client_ip or http_request.client.host

        session = session_manager.create_session(
            client_name=request.client_name,
            client_ip=client_ip,
            timeout_seconds=request.timeout_seconds,
            metadata=request.metadata
        )

        return SessionResponse(
            session_id=session.session_id,
            client_name=session.client_name,
            client_ip=session.client_ip,
            created_at=session.created_at.isoformat(),
            last_activity=session.last_activity.isoformat(),
            time_remaining=session.time_remaining(),
            duration_seconds=session.session_duration(),
            metadata=session.metadata
        )

    except Exception as e:
        logger.error(f"Error creating session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")


@router.delete("/sessions/{session_id}", summary="End session")
async def end_session(session_id: str):
    """
    End a client session.

    Automatically releases all locks held by this session.
    """
    try:
        # Release all locks for this session
        released_count = await lock_manager.release_all_session_locks(session_id)

        # End the session
        success = session_manager.end_session(session_id)

        if success:
            return {
                "success": True,
                "message": "Session ended",
                "session_id": session_id,
                "locks_released": released_count
            }
        else:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ending session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to end session: {str(e)}")


@router.get("/sessions/{session_id}", response_model=SessionResponse, summary="Get session info")
async def get_session(session_id: str):
    """
    Get information about a specific session.
    """
    try:
        session = session_manager.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        return SessionResponse(
            session_id=session.session_id,
            client_name=session.client_name,
            client_ip=session.client_ip,
            created_at=session.created_at.isoformat(),
            last_activity=session.last_activity.isoformat(),
            time_remaining=session.time_remaining(),
            duration_seconds=session.session_duration(),
            metadata=session.metadata
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get session: {str(e)}")


@router.get("/sessions", summary="Get all sessions")
async def get_all_sessions():
    """
    Get all active sessions.
    """
    try:
        sessions = session_manager.get_all_sessions()

        return {
            "sessions": [
                SessionResponse(
                    session_id=s.session_id,
                    client_name=s.client_name,
                    client_ip=s.client_ip,
                    created_at=s.created_at.isoformat(),
                    last_activity=s.last_activity.isoformat(),
                    time_remaining=s.time_remaining(),
                    duration_seconds=s.session_duration(),
                    metadata=s.metadata
                ).dict()
                for s in sessions
            ],
            "count": len(sessions)
        }

    except Exception as e:
        logger.error(f"Error getting all sessions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get sessions: {str(e)}")


@router.post("/sessions/{session_id}/activity", summary="Update session activity")
async def update_session_activity(session_id: str):
    """
    Update session activity timestamp to prevent timeout.

    Call this periodically to keep session alive.
    """
    try:
        success = session_manager.update_session_activity(session_id)

        if success:
            return {
                "success": True,
                "message": "Session activity updated",
                "session_id": session_id
            }
        else:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating session activity: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update activity: {str(e)}")


@router.get("/sessions/{session_id}/locks", summary="Get session locks")
async def get_session_locks(session_id: str):
    """
    Get all equipment locked by a specific session.
    """
    try:
        # Verify session exists
        session = session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        locked_equipment = lock_manager.get_session_locks(session_id)

        return {
            "session_id": session_id,
            "locked_equipment": locked_equipment,
            "count": len(locked_equipment)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session locks: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get session locks: {str(e)}")


@router.get("/sessions/{session_id}/events", summary="Get session events")
async def get_session_events(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=1000, description="Maximum number of events to return")
):
    """
    Get event history for a specific session.
    """
    try:
        events = session_manager.get_session_events(session_id, limit=limit)

        return {
            "session_id": session_id,
            "events": events,
            "count": len(events)
        }

    except Exception as e:
        logger.error(f"Error getting session events: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get session events: {str(e)}")


# ============================================================================
# Cleanup Endpoint
# ============================================================================

@router.post("/cleanup", summary="Clean up expired sessions and locks")
async def cleanup_expired():
    """
    Manually trigger cleanup of expired sessions and locks.

    Normally runs automatically in background, but can be triggered manually.
    """
    try:
        # Cleanup expired sessions
        expired_sessions = session_manager.cleanup_expired_sessions()

        # Cleanup expired locks (handled automatically by lock manager)
        # But we can also release locks for expired sessions
        for session_id in expired_sessions:
            await lock_manager.release_all_session_locks(session_id)

        return {
            "success": True,
            "message": "Cleanup completed",
            "expired_sessions": len(expired_sessions),
            "session_ids": expired_sessions
        }

    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")
