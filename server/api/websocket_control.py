"""API endpoints for WebSocket control and monitoring."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum

# Import will be available after we integrate with main.py
# from websocket.enhanced_manager import enhanced_stream_manager


router = APIRouter(prefix="/api/websocket", tags=["websocket"])


class CompressionTypeAPI(str, Enum):
    """Compression types for API."""
    NONE = "none"
    GZIP = "gzip"
    ZLIB = "zlib"


class MessagePriorityAPI(str, Enum):
    """Message priorities for API."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class RecordingFormatAPI(str, Enum):
    """Recording formats for API."""
    JSON = "json"
    JSONL = "jsonl"
    CSV = "csv"
    BINARY = "binary"


class StartRecordingRequest(BaseModel):
    """Request to start recording a WebSocket stream."""
    session_id: str = Field(..., description="Recording session identifier")
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Optional metadata"
    )


class StartRecordingResponse(BaseModel):
    """Response for start recording."""
    session_id: str
    filepath: str
    started_at: str


class StopRecordingResponse(BaseModel):
    """Response for stop recording."""
    session_id: str
    filepath: str
    duration_seconds: float
    message_count: int
    bytes_written: int
    messages_per_second: float


class RecordingStatsResponse(BaseModel):
    """Recording statistics."""
    session_id: str
    filepath: str
    duration_seconds: float
    message_count: int
    bytes_written: int
    messages_per_second: float


class ConnectionInfo(BaseModel):
    """Connection information."""
    client_id: str
    metadata: Dict[str, Any]
    backpressure: Optional[Dict[str, Any]]


class GlobalStats(BaseModel):
    """Global WebSocket statistics."""
    total_connections: int
    total_messages_sent: int
    total_messages_received: int
    total_bytes_sent: int
    total_bytes_received: int
    active_connections: int
    active_recordings: int
    average_compression_ratio: float


class BackpressureStats(BaseModel):
    """Backpressure statistics for a connection."""
    messages_queued: int
    messages_sent: int
    messages_dropped: int
    queue_overflows: int
    rate_limit_hits: int
    queue_size: int
    queue_size_by_priority: Dict[str, int]


class SendTestMessageRequest(BaseModel):
    """Request to send a test message."""
    client_id: Optional[str] = Field(
        None, description="Client ID (None for broadcast)"
    )
    message: Dict[str, Any] = Field(..., description="Message to send")
    priority: MessagePriorityAPI = Field(
        MessagePriorityAPI.NORMAL, description="Message priority"
    )
    compression: CompressionTypeAPI = Field(
        CompressionTypeAPI.NONE, description="Compression type"
    )


# Note: enhanced_stream_manager will be imported from main.py after integration
enhanced_stream_manager = None


def set_stream_manager(manager):
    """Set the global stream manager instance."""
    global enhanced_stream_manager
    enhanced_stream_manager = manager


@router.post("/recording/start", response_model=StartRecordingResponse)
async def start_recording(request: StartRecordingRequest):
    """Start recording WebSocket stream to file.

    Records all WebSocket messages for the specified session to a file.
    Supports multiple formats (JSON, JSONL, CSV, Binary) with optional compression.
    """
    if enhanced_stream_manager is None:
        raise HTTPException(status_code=503, detail="WebSocket manager not initialized")

    try:
        from datetime import datetime

        filepath = enhanced_stream_manager.start_recording(
            request.session_id,
            request.metadata
        )

        return StartRecordingResponse(
            session_id=request.session_id,
            filepath=filepath,
            started_at=datetime.now().isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recording/stop/{session_id}", response_model=StopRecordingResponse)
async def stop_recording(session_id: str):
    """Stop recording a WebSocket stream.

    Returns statistics about the recording including duration, message count,
    and file size.
    """
    if enhanced_stream_manager is None:
        raise HTTPException(status_code=503, detail="WebSocket manager not initialized")

    stats = enhanced_stream_manager.stop_recording(session_id)
    if stats is None:
        raise HTTPException(
            status_code=404,
            detail=f"Recording session {session_id} not found"
        )

    return StopRecordingResponse(
        session_id=session_id,
        **stats
    )


@router.get("/recording/stats/{session_id}", response_model=RecordingStatsResponse)
async def get_recording_stats(session_id: str):
    """Get statistics for an active recording session."""
    if enhanced_stream_manager is None:
        raise HTTPException(status_code=503, detail="WebSocket manager not initialized")

    stats = enhanced_stream_manager.get_recording_stats(session_id)
    if stats is None:
        raise HTTPException(
            status_code=404,
            detail=f"Recording session {session_id} not found"
        )

    return RecordingStatsResponse(
        session_id=session_id,
        **stats
    )


@router.get("/recording/active", response_model=List[str])
async def get_active_recordings():
    """Get list of active recording sessions."""
    if enhanced_stream_manager is None:
        raise HTTPException(status_code=503, detail="WebSocket manager not initialized")

    return enhanced_stream_manager.get_active_recordings()


@router.get("/connections", response_model=List[ConnectionInfo])
async def get_connections():
    """Get information about all active WebSocket connections."""
    if enhanced_stream_manager is None:
        raise HTTPException(status_code=503, detail="WebSocket manager not initialized")

    return enhanced_stream_manager.get_all_connections()


@router.get("/connections/{client_id}", response_model=ConnectionInfo)
async def get_connection_info(client_id: str):
    """Get information about a specific WebSocket connection."""
    if enhanced_stream_manager is None:
        raise HTTPException(status_code=503, detail="WebSocket manager not initialized")

    info = enhanced_stream_manager.get_connection_info(client_id)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=f"Connection {client_id} not found"
        )

    return info


@router.get("/connections/{client_id}/backpressure", response_model=BackpressureStats)
async def get_connection_backpressure(client_id: str):
    """Get backpressure statistics for a specific connection."""
    if enhanced_stream_manager is None:
        raise HTTPException(status_code=503, detail="WebSocket manager not initialized")

    stats = enhanced_stream_manager.get_backpressure_stats(client_id)
    if stats is None:
        raise HTTPException(
            status_code=404,
            detail=f"Connection {client_id} not found"
        )

    return stats


@router.get("/stats", response_model=GlobalStats)
async def get_global_stats():
    """Get global WebSocket statistics."""
    if enhanced_stream_manager is None:
        raise HTTPException(status_code=503, detail="WebSocket manager not initialized")

    return enhanced_stream_manager.get_global_stats()


@router.post("/test/send")
async def send_test_message(request: SendTestMessageRequest):
    """Send a test message through WebSocket.

    Useful for testing compression, priority channels, and backpressure handling.
    """
    if enhanced_stream_manager is None:
        raise HTTPException(status_code=503, detail="WebSocket manager not initialized")

    # Convert API enums to internal enums
    from websocket.enhanced_features import MessagePriority, CompressionType

    priority_map = {
        MessagePriorityAPI.LOW: MessagePriority.LOW,
        MessagePriorityAPI.NORMAL: MessagePriority.NORMAL,
        MessagePriorityAPI.HIGH: MessagePriority.HIGH,
        MessagePriorityAPI.CRITICAL: MessagePriority.CRITICAL,
    }

    compression_map = {
        CompressionTypeAPI.NONE: CompressionType.NONE,
        CompressionTypeAPI.GZIP: CompressionType.GZIP,
        CompressionTypeAPI.ZLIB: CompressionType.ZLIB,
    }

    priority = priority_map[request.priority]
    compression = compression_map[request.compression]

    try:
        if request.client_id:
            # Send to specific client
            success = await enhanced_stream_manager.send_to_client(
                request.client_id,
                request.message,
                priority,
                compression
            )
            if not success:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to queue message"
                )
        else:
            # Broadcast to all clients
            await enhanced_stream_manager.broadcast(
                request.message,
                priority,
                compression
            )

        return {"status": "success", "message": "Message queued for sending"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
