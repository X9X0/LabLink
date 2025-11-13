"""Enhanced WebSocket server for real-time data streaming with advanced features.

This module provides an enhanced WebSocket server with:
- Stream recording to files
- Message compression (gzip/zlib)
- Priority-based message routing
- Backpressure handling and flow control
"""

import asyncio
import json
import logging
from typing import Optional
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect

from equipment.manager import equipment_manager
from websocket.enhanced_manager import EnhancedStreamManager
from websocket.enhanced_features import (
    StreamRecordingConfig,
    BackpressureConfig,
    MessagePriority,
    CompressionType,
    RecordingFormat,
)
from config.settings import settings

logger = logging.getLogger(__name__)


# Create enhanced stream manager with configuration from settings
def create_enhanced_stream_manager() -> EnhancedStreamManager:
    """Create enhanced stream manager with settings from configuration."""

    # Recording configuration
    recording_config = StreamRecordingConfig(
        enabled=getattr(settings, "ws_recording_enabled", False),
        format=RecordingFormat(
            getattr(settings, "ws_recording_format", "jsonl")
        ),
        output_dir=getattr(
            settings, "ws_recording_dir", "./data/ws_recordings"
        ),
        max_file_size_mb=getattr(settings, "ws_recording_max_size_mb", 100),
        include_timestamps=getattr(settings, "ws_recording_timestamps", True),
        include_metadata=getattr(settings, "ws_recording_metadata", True),
        compress_output=getattr(settings, "ws_recording_compress", True),
    )

    # Backpressure configuration
    backpressure_config = BackpressureConfig(
        enabled=getattr(settings, "ws_backpressure_enabled", True),
        max_queue_size=getattr(settings, "ws_message_queue_size", 1000),
        warning_threshold=getattr(settings, "ws_queue_warning_threshold", 750),
        drop_low_priority=getattr(settings, "ws_drop_low_priority", True),
        rate_limit_enabled=getattr(settings, "ws_rate_limit_enabled", True),
        max_messages_per_second=getattr(
            settings, "ws_max_messages_per_second", 100
        ),
        burst_size=getattr(settings, "ws_burst_size", 50),
    )

    return EnhancedStreamManager(
        recording_config=recording_config,
        backpressure_config=backpressure_config,
    )


# Global enhanced stream manager
enhanced_stream_manager = create_enhanced_stream_manager()


async def handle_websocket_enhanced(websocket: WebSocket, client_id: Optional[str] = None):
    """Handle enhanced WebSocket connection with advanced features.

    Args:
        websocket: WebSocket connection
        client_id: Optional client identifier (auto-generated if not provided)
    """
    # Generate client ID if not provided
    if client_id is None:
        import uuid
        client_id = f"client_{uuid.uuid4().hex[:8]}"

    # Connect with metadata
    metadata = {
        "connected_at": datetime.now().isoformat(),
        "user_agent": websocket.headers.get("user-agent", "unknown"),
    }

    await enhanced_stream_manager.connect(websocket, client_id, metadata)

    try:
        while True:
            # Receive messages from client
            data = await websocket.receive_text()
            message = json.loads(data)

            # Handle different message types
            msg_type = message.get("type")

            if msg_type == "start_stream":
                await handle_start_stream(client_id, message)

            elif msg_type == "stop_stream":
                await handle_stop_stream(client_id, message)

            elif msg_type == "start_acquisition_stream":
                await handle_start_acquisition_stream(client_id, message)

            elif msg_type == "stop_acquisition_stream":
                await handle_stop_acquisition_stream(client_id, message)

            elif msg_type == "start_recording":
                await handle_start_recording(client_id, message)

            elif msg_type == "stop_recording":
                await handle_stop_recording(client_id, message)

            elif msg_type == "set_compression":
                await handle_set_compression(client_id, message)

            elif msg_type == "set_priority":
                await handle_set_priority(client_id, message)

            elif msg_type == "get_stats":
                await handle_get_stats(client_id)

            elif msg_type == "ping":
                await enhanced_stream_manager.send_to_client(
                    client_id,
                    {"type": "pong", "timestamp": datetime.now().isoformat()},
                    MessagePriority.HIGH
                )

            else:
                logger.warning(f"Unknown message type: {msg_type}")

    except WebSocketDisconnect:
        enhanced_stream_manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
        enhanced_stream_manager.disconnect(client_id)


async def handle_start_stream(client_id: str, message: dict):
    """Handle start stream request."""
    equipment_id = message.get("equipment_id")
    stream_type = message.get("stream_type", "readings")
    interval_ms = message.get("interval_ms", 100)
    priority = message.get("priority", "normal")
    compression = message.get("compression", "none")

    # Convert priority and compression
    priority_enum = MessagePriority[priority.upper()]
    compression_enum = CompressionType(compression.lower())

    # Start streaming task
    task_key = f"{equipment_id}_{stream_type}_{client_id}"

    task = asyncio.create_task(
        stream_equipment_data(
            client_id, equipment_id, stream_type, interval_ms,
            priority_enum, compression_enum
        )
    )

    enhanced_stream_manager.streaming_tasks[task_key] = task

    await enhanced_stream_manager.send_to_client(
        client_id,
        {
            "type": "stream_started",
            "equipment_id": equipment_id,
            "stream_type": stream_type,
        },
        MessagePriority.HIGH
    )


async def handle_stop_stream(client_id: str, message: dict):
    """Handle stop stream request."""
    equipment_id = message.get("equipment_id")
    stream_type = message.get("stream_type", "readings")

    task_key = f"{equipment_id}_{stream_type}_{client_id}"

    if task_key in enhanced_stream_manager.streaming_tasks:
        enhanced_stream_manager.streaming_tasks[task_key].cancel()
        del enhanced_stream_manager.streaming_tasks[task_key]

        await enhanced_stream_manager.send_to_client(
            client_id,
            {
                "type": "stream_stopped",
                "equipment_id": equipment_id,
                "stream_type": stream_type,
            },
            MessagePriority.HIGH
        )


async def handle_start_acquisition_stream(client_id: str, message: dict):
    """Handle start acquisition stream request."""
    acquisition_id = message.get("acquisition_id")
    interval_ms = message.get("interval_ms", 100)
    num_samples = message.get("num_samples", 100)
    priority = message.get("priority", "normal")
    compression = message.get("compression", "none")

    priority_enum = MessagePriority[priority.upper()]
    compression_enum = CompressionType(compression.lower())

    task_key = f"acquisition_{acquisition_id}_{client_id}"

    task = asyncio.create_task(
        stream_acquisition_data(
            client_id, acquisition_id, interval_ms, num_samples,
            priority_enum, compression_enum
        )
    )

    enhanced_stream_manager.streaming_tasks[task_key] = task

    await enhanced_stream_manager.send_to_client(
        client_id,
        {
            "type": "acquisition_stream_started",
            "acquisition_id": acquisition_id,
        },
        MessagePriority.HIGH
    )


async def handle_stop_acquisition_stream(client_id: str, message: dict):
    """Handle stop acquisition stream request."""
    acquisition_id = message.get("acquisition_id")

    task_key = f"acquisition_{acquisition_id}_{client_id}"

    if task_key in enhanced_stream_manager.streaming_tasks:
        enhanced_stream_manager.streaming_tasks[task_key].cancel()
        del enhanced_stream_manager.streaming_tasks[task_key]

        await enhanced_stream_manager.send_to_client(
            client_id,
            {
                "type": "acquisition_stream_stopped",
                "acquisition_id": acquisition_id,
            },
            MessagePriority.HIGH
        )


async def handle_start_recording(client_id: str, message: dict):
    """Handle start recording request."""
    session_id = message.get("session_id", f"recording_{client_id}")
    metadata = message.get("metadata", {})

    try:
        filepath = enhanced_stream_manager.start_recording(session_id, metadata)

        await enhanced_stream_manager.send_to_client(
            client_id,
            {
                "type": "recording_started",
                "session_id": session_id,
                "filepath": filepath,
            },
            MessagePriority.HIGH
        )
    except Exception as e:
        await enhanced_stream_manager.send_to_client(
            client_id,
            {
                "type": "error",
                "error": f"Failed to start recording: {str(e)}",
            },
            MessagePriority.HIGH
        )


async def handle_stop_recording(client_id: str, message: dict):
    """Handle stop recording request."""
    session_id = message.get("session_id")

    stats = enhanced_stream_manager.stop_recording(session_id)

    if stats:
        await enhanced_stream_manager.send_to_client(
            client_id,
            {
                "type": "recording_stopped",
                "session_id": session_id,
                "stats": stats,
            },
            MessagePriority.HIGH
        )
    else:
        await enhanced_stream_manager.send_to_client(
            client_id,
            {
                "type": "error",
                "error": f"Recording session {session_id} not found",
            },
            MessagePriority.HIGH
        )


async def handle_set_compression(client_id: str, message: dict):
    """Handle set compression request."""
    compression = message.get("compression", "none")

    # Store compression preference in metadata
    if client_id in enhanced_stream_manager.connection_metadata:
        enhanced_stream_manager.connection_metadata[client_id]["compression"] = compression

    await enhanced_stream_manager.send_to_client(
        client_id,
        {
            "type": "compression_set",
            "compression": compression,
        },
        MessagePriority.HIGH
    )


async def handle_set_priority(client_id: str, message: dict):
    """Handle set priority request."""
    priority = message.get("priority", "normal")

    # Store priority preference in metadata
    if client_id in enhanced_stream_manager.connection_metadata:
        enhanced_stream_manager.connection_metadata[client_id]["priority"] = priority

    await enhanced_stream_manager.send_to_client(
        client_id,
        {
            "type": "priority_set",
            "priority": priority,
        },
        MessagePriority.HIGH
    )


async def handle_get_stats(client_id: str):
    """Handle get stats request."""
    connection_stats = enhanced_stream_manager.get_backpressure_stats(client_id)
    global_stats = enhanced_stream_manager.get_global_stats()

    await enhanced_stream_manager.send_to_client(
        client_id,
        {
            "type": "stats",
            "connection": connection_stats,
            "global": global_stats,
        },
        MessagePriority.HIGH
    )


async def stream_equipment_data(
    client_id: str,
    equipment_id: str,
    stream_type: str,
    interval_ms: int,
    priority: MessagePriority,
    compression: CompressionType
):
    """Stream equipment data to client."""
    interval_sec = interval_ms / 1000.0

    while True:
        try:
            equipment = equipment_manager.get_equipment(equipment_id)
            if equipment is None:
                logger.warning(
                    f"Equipment {equipment_id} not found, stopping stream"
                )
                break

            # Get data based on stream type
            if stream_type == "readings":
                data = await equipment.execute_command("get_readings", {})
            elif stream_type == "waveform":
                data = await equipment.execute_command(
                    "get_waveform", {"channel": 1}
                )
            elif stream_type == "measurements":
                data = await equipment.execute_command(
                    "get_measurements", {"channel": 1}
                )
            else:
                logger.error(f"Unknown stream type: {stream_type}")
                break

            # Convert data to dict if it's a Pydantic model
            if hasattr(data, "dict"):
                data_dict = data.dict()
            elif isinstance(data, dict):
                data_dict = data
            else:
                data_dict = {"value": str(data)}

            # Send data
            message = {
                "type": "stream_data",
                "equipment_id": equipment_id,
                "stream_type": stream_type,
                "data": data_dict,
                "timestamp": datetime.now().isoformat(),
            }

            await enhanced_stream_manager.send_to_client(
                client_id, message, priority, compression
            )

            # Wait for next interval
            await asyncio.sleep(interval_sec)

        except asyncio.CancelledError:
            logger.info(
                f"Streaming task cancelled for {equipment_id}/{stream_type}"
            )
            break
        except Exception as e:
            logger.error(f"Error in streaming task: {e}")
            await asyncio.sleep(interval_sec)


async def stream_acquisition_data(
    client_id: str,
    acquisition_id: str,
    interval_ms: int,
    num_samples: int,
    priority: MessagePriority,
    compression: CompressionType
):
    """Stream acquisition data to client."""
    from acquisition import acquisition_manager

    interval_sec = interval_ms / 1000.0

    while True:
        try:
            # Get acquisition session
            session = acquisition_manager.get_session(acquisition_id)
            if session is None:
                logger.warning(
                    f"Acquisition {acquisition_id} not found, stopping stream"
                )
                break

            # Get latest data from buffer
            data, timestamps = acquisition_manager.get_buffer_data(
                acquisition_id, num_samples
            )

            if len(timestamps) == 0:
                # No data yet, just send status
                message = {
                    "type": "acquisition_stream",
                    "acquisition_id": acquisition_id,
                    "state": session.state,
                    "stats": session.stats.dict(),
                    "data": None,
                    "timestamp": datetime.now().isoformat(),
                }
            else:
                # Convert to JSON-serializable format
                message = {
                    "type": "acquisition_stream",
                    "acquisition_id": acquisition_id,
                    "state": session.state,
                    "stats": session.stats.dict(),
                    "data": {
                        "timestamps": [
                            datetime.fromtimestamp(t).isoformat()
                            for t in timestamps
                        ],
                        "values": {
                            channel: data[i, :].tolist()
                            for i, channel in enumerate(session.config.channels)
                        },
                        "count": len(timestamps),
                    },
                    "timestamp": datetime.now().isoformat(),
                }

            await enhanced_stream_manager.send_to_client(
                client_id, message, priority, compression
            )

            # Wait for next interval
            await asyncio.sleep(interval_sec)

        except asyncio.CancelledError:
            logger.info(
                f"Acquisition streaming task cancelled for {acquisition_id}"
            )
            break
        except Exception as e:
            logger.error(f"Error in acquisition streaming task: {e}")
            await asyncio.sleep(interval_sec)
