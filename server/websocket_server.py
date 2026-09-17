"""WebSocket server for real-time data streaming."""

import asyncio
import json
import logging

from fastapi.encoders import jsonable_encoder
from datetime import datetime
import time
from typing import Optional, Set

from server.equipment.manager import equipment_manager
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class StreamManager:
    """Manages WebSocket connections and data streaming."""

    def __init__(self):
        """Initialize stream manager."""
        self.active_connections: Set[WebSocket] = set()
        self.streaming_tasks: dict[str, asyncio.Task] = {}
        #: Last frame fingerprint per stream, for dropping duplicates.
        self._last_frame: dict = {}

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
        # Encode once, before touching any connection. send_json uses a plain
        # json.dumps, which cannot encode the datetime every readings payload
        # carries -- and because that raised inside the per-connection loop,
        # a serialisation bug was being treated as that client hanging up and
        # dropped the websocket. The encoding either works for everyone or
        # for no one; it says nothing about any connection.
        try:
            payload = jsonable_encoder(message)
        except Exception as e:
            logger.error(f"Cannot encode broadcast message: {e}")
            return

        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(payload)
            except Exception as e:
                logger.error(f"Error broadcasting: {e}")
                disconnected.add(connection)

        # Remove disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

    def _is_repeat(self, task_key: str, data) -> bool:
        """Whether this frame carries the same samples as the one before.

        Compared on the samples alone: a frame differing only in its
        data_id -- which is a fresh uuid every read -- is the same trace.
        """
        if not isinstance(data, dict):
            return False
        samples = data.get("voltage")
        if samples is None:
            return False
        fingerprint = (data.get("channel"), len(samples),
                       tuple(samples[::16]), samples[-1] if samples else None)
        if self._last_frame.get(task_key) == fingerprint:
            return True
        self._last_frame[task_key] = fingerprint
        return False

    async def start_streaming(
        self, equipment_id: str, stream_type: str, interval_ms: int = 100,
        parameters: Optional[dict] = None,
    ):
        """Start streaming data from a device.

        ``parameters`` are handed to the driver command, which is what lets a
        "trace" stream name its channel and point count.
        """
        task_key = f"{equipment_id}_{stream_type}"

        # Stop existing stream if any
        if task_key in self.streaming_tasks:
            self.streaming_tasks[task_key].cancel()

        # Create new streaming task
        task = asyncio.create_task(
            self._stream_data(equipment_id, stream_type, interval_ms,
                              parameters or {})
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

    async def _stream_data(self, equipment_id: str, stream_type: str,
                           interval_ms: int, parameters: Optional[dict] = None):
        """Stream data from a device on a fixed cadence.

        The cadence is held by deadline rather than by sleeping a fixed gap
        *after* the work. That matters on an instrument which stalls: this
        DS1054Z pauses ~150 ms on roughly one exchange in ten, and sleeping a
        whole interval after a stalled read turns a 150 ms hiccup into a
        150 ms + interval gap, so stalls compound into visible stutter.
        A deadline absorbs the stall into the slack instead, and slips only
        when the work genuinely outruns the interval.
        """
        interval_sec = interval_ms / 1000.0
        parameters = parameters or {}
        task_key = f"{equipment_id}_{stream_type}"
        next_due = time.monotonic()
        self._last_frame.pop(task_key, None)

        while True:
            try:
                if not self.active_connections:
                    # Nobody is listening. A stream with no audience still
                    # takes the instrument's I/O lock and still costs the
                    # control panel its turn, so idle instead of driving it.
                    await asyncio.sleep(interval_sec)
                    next_due = time.monotonic()
                    continue
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
                        "get_measurements", parameters or {"channel": 1}
                    )
                elif stream_type == "trace":
                    # The samples, where the "waveform" stream sends only
                    # metadata. Pushed from here so a live trace costs no HTTP
                    # round trip per frame and the server can keep the
                    # instrument busy rather than waiting to be asked.
                    data = await equipment.execute_command(
                        "get_waveform_data",
                        parameters or {"channel": 1, "points": 600},
                    )
                    if self._is_repeat(task_key, data):
                        # Measured on the bench: reading at 100 Hz produced
                        # about 9 distinct frames a second, because a settled
                        # repetitive signal redraws to the same screen. The
                        # duplicates cost the client a redraw and the network
                        # a frame to show nothing new, so they stop here. A
                        # changing signal dedupes to almost nothing and every
                        # frame goes, which is the point: the rate follows the
                        # signal rather than a number somebody picked.
                        next_due += interval_sec
                        slack = next_due - time.monotonic()
                        if slack > 0:
                            await asyncio.sleep(slack)
                        elif slack < -interval_sec:
                            next_due = time.monotonic()
                        continue
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

                # Hold the cadence by deadline: a frame that overran leaves
                # nothing to wait for rather than pushing the next one out by
                # a further interval.
                next_due += interval_sec
                slack = next_due - time.monotonic()
                if slack > 0:
                    await asyncio.sleep(slack)
                elif slack < -interval_sec:
                    # Far enough behind that catching up would mean a burst of
                    # back-to-back frames at the instrument. Drop the lost
                    # ground instead of trying to make it up.
                    next_due = time.monotonic()

            except asyncio.CancelledError:
                logger.info(
                    f"Streaming task cancelled for {equipment_id}/{stream_type}"
                )
                break
            except ValueError as e:
                # The instrument does not have this command -- a scope asked
                # for "get_readings", say. Every pass sends the identical
                # command, so what failed once fails forever: retrying just
                # fills the log twice a second and burns the interval.
                logger.error(
                    f"{equipment_id} cannot stream {stream_type}: {e}; "
                    "stopping this stream"
                )
                break
            except Exception as e:
                logger.error(f"Error in streaming task: {e}")
                await asyncio.sleep(interval_sec)

    async def _stream_acquisition(
        self, acquisition_id: str, interval_ms: int, num_samples: int = 100
    ):
        """Stream real-time acquisition data."""
        from server.acquisition import acquisition_manager

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
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                logger.warning(f"Received invalid JSON from WebSocket client: {data!r}")
                await stream_manager.send_to_client(
                    websocket, {"type": "error", "detail": "Invalid JSON"}
                )
                continue

            # Handle different message types
            msg_type = message.get("type")

            if msg_type == "start_stream":
                equipment_id = message.get("equipment_id")
                stream_type = message.get("stream_type", "readings")
                interval_ms = message.get("interval_ms", 100)
                # A trace stream names its channel and point count here.
                parameters = message.get("parameters") or {}
                await stream_manager.start_streaming(
                    equipment_id, stream_type, interval_ms, parameters
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
