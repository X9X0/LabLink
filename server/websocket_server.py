"""WebSocket server for real-time data streaming."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Set

from equipment.manager import equipment_manager
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class StreamManager:
    """Manages WebSocket connections and data streaming."""

    def __init__(self):
        """Initialize stream manager."""
        self.active_connections: Set[WebSocket] = set()
        self.streaming_tasks: dict[str, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket):
        """Accept a WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(
            f"WebSocket connected. Total connections: {len(self.active_connections)}"
        )

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        self.active_connections.discard(websocket)
        logger.info(
            f"WebSocket disconnected. Total connections: {len(self.active_connections)}"
        )

        # If no more clients connected, stop all streaming tasks to prevent resource leaks
        if len(self.active_connections) == 0:
            logger.info("No active connections remaining, stopping all streaming tasks")
            tasks_to_cancel = list(self.streaming_tasks.items())
            for task_key, task in tasks_to_cancel:
                if not task.done():
                    task.cancel()
                    logger.debug(f"Cancelled streaming task: {task_key}")
            self.streaming_tasks.clear()

    async def send_to_client(self, websocket: WebSocket, message: dict):
        """Send a message to a specific client."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting: {e}")
                disconnected.add(connection)

        # Remove disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

    async def start_streaming(
        self, equipment_id: str, stream_type: str, interval_ms: int = 100
    ):
        """Start streaming data from a device."""
        task_key = f"{equipment_id}_{stream_type}"

        # Stop existing stream if any
        if task_key in self.streaming_tasks:
            self.streaming_tasks[task_key].cancel()

        # Create new streaming task
        task = asyncio.create_task(
            self._stream_data(equipment_id, stream_type, interval_ms)
        )
        self.streaming_tasks[task_key] = task
        logger.info(f"Started streaming {stream_type} from {equipment_id}")

    async def stop_streaming(self, equipment_id: str, stream_type: str):
        """Stop streaming data from a device."""
        task_key = f"{equipment_id}_{stream_type}"

        if task_key in self.streaming_tasks:
            self.streaming_tasks[task_key].cancel()
            del self.streaming_tasks[task_key]
            logger.info(f"Stopped streaming {stream_type} from {equipment_id}")

    async def _stream_data(self, equipment_id: str, stream_type: str, interval_ms: int):
        """Stream data from a device at regular intervals."""
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

                # Broadcast data
                message = {
                    "type": "stream_data",
                    "equipment_id": equipment_id,
                    "stream_type": stream_type,
                    "data": data_dict,
                }
                await self.broadcast(message)

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

    async def _stream_acquisition(
        self, acquisition_id: str, interval_ms: int, num_samples: int = 100
    ):
        """Stream real-time acquisition data."""
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
                    }

                await self.broadcast(message)

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

    async def start_acquisition_stream(
        self, acquisition_id: str, interval_ms: int = 100, num_samples: int = 100
    ):
        """Start streaming acquisition data."""
        task_key = f"acquisition_{acquisition_id}"

        # Stop existing stream if any
        if task_key in self.streaming_tasks:
            self.streaming_tasks[task_key].cancel()

        # Create new streaming task
        task = asyncio.create_task(
            self._stream_acquisition(acquisition_id, interval_ms, num_samples)
        )
        self.streaming_tasks[task_key] = task
        logger.info(f"Started acquisition streaming for {acquisition_id}")

    async def stop_acquisition_stream(self, acquisition_id: str):
        """Stop streaming acquisition data."""
        task_key = f"acquisition_{acquisition_id}"

        if task_key in self.streaming_tasks:
            self.streaming_tasks[task_key].cancel()
            del self.streaming_tasks[task_key]
            logger.info(f"Stopped acquisition streaming for {acquisition_id}")


# Global stream manager
stream_manager = StreamManager()


async def handle_websocket(websocket: WebSocket):
    """Handle WebSocket connection."""
    await stream_manager.connect(websocket)

    try:
        while True:
            # Receive messages from client
            data = await websocket.receive_text()
            message = json.loads(data)

            # Handle different message types
            msg_type = message.get("type")

            if msg_type == "start_stream":
                equipment_id = message.get("equipment_id")
                stream_type = message.get("stream_type", "readings")
                interval_ms = message.get("interval_ms", 100)
                await stream_manager.start_streaming(
                    equipment_id, stream_type, interval_ms
                )
                await stream_manager.send_to_client(
                    websocket,
                    {
                        "type": "stream_started",
                        "equipment_id": equipment_id,
                        "stream_type": stream_type,
                    },
                )

            elif msg_type == "stop_stream":
                equipment_id = message.get("equipment_id")
                stream_type = message.get("stream_type", "readings")
                await stream_manager.stop_streaming(equipment_id, stream_type)
                await stream_manager.send_to_client(
                    websocket,
                    {
                        "type": "stream_stopped",
                        "equipment_id": equipment_id,
                        "stream_type": stream_type,
                    },
                )

            elif msg_type == "start_acquisition_stream":
                acquisition_id = message.get("acquisition_id")
                interval_ms = message.get("interval_ms", 100)
                num_samples = message.get("num_samples", 100)
                await stream_manager.start_acquisition_stream(
                    acquisition_id, interval_ms, num_samples
                )
                await stream_manager.send_to_client(
                    websocket,
                    {
                        "type": "acquisition_stream_started",
                        "acquisition_id": acquisition_id,
                    },
                )

            elif msg_type == "stop_acquisition_stream":
                acquisition_id = message.get("acquisition_id")
                await stream_manager.stop_acquisition_stream(acquisition_id)
                await stream_manager.send_to_client(
                    websocket,
                    {
                        "type": "acquisition_stream_stopped",
                        "acquisition_id": acquisition_id,
                    },
                )

            elif msg_type == "ping":
                await stream_manager.send_to_client(websocket, {"type": "pong"})

    except WebSocketDisconnect:
        stream_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        stream_manager.disconnect(websocket)
