"""WebSocket manager for real-time data streaming."""

import asyncio
import json
import logging
from typing import Dict, Callable, Optional, Any, List
from enum import Enum
from dataclasses import dataclass

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
except ImportError:
    websockets = None
    WebSocketClientProtocol = None

logger = logging.getLogger(__name__)


class StreamType(str, Enum):
    """Types of data streams."""
    READINGS = "readings"
    WAVEFORM = "waveform"
    MEASUREMENTS = "measurements"


class MessageType(str, Enum):
    """WebSocket message types."""
    # Client -> Server
    START_STREAM = "start_stream"
    STOP_STREAM = "stop_stream"
    START_ACQUISITION_STREAM = "start_acquisition_stream"
    STOP_ACQUISITION_STREAM = "stop_acquisition_stream"
    PING = "ping"

    # Server -> Client
    STREAM_DATA = "stream_data"
    ACQUISITION_STREAM = "acquisition_stream"
    STREAM_STARTED = "stream_started"
    STREAM_STOPPED = "stream_stopped"
    ACQUISITION_STREAM_STARTED = "acquisition_stream_started"
    ACQUISITION_STREAM_STOPPED = "acquisition_stream_stopped"
    PONG = "pong"


@dataclass
class StreamConfig:
    """Configuration for a data stream."""
    equipment_id: str
    stream_type: str
    interval_ms: int = 100
    parameters: Dict[str, Any] = None

    def __post_init__(self):
        """Initialize default parameters."""
        if self.parameters is None:
            self.parameters = {}


class WebSocketManager:
    """Manages WebSocket connection and data streaming."""

    def __init__(self, host: str = "localhost", port: int = 8001):
        """Initialize WebSocket manager.

        Args:
            host: Server hostname
            port: WebSocket port
        """
        if websockets is None:
            raise ImportError("websockets library not installed. Install with: pip install websockets")

        self.host = host
        self.port = port
        self.url = f"ws://{host}:{port}/ws"

        self._connection: Optional[WebSocketClientProtocol] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None

        # Callbacks for different message types
        self._message_handlers: Dict[str, List[Callable]] = {
            MessageType.STREAM_DATA: [],
            MessageType.ACQUISITION_STREAM: [],
            MessageType.STREAM_STARTED: [],
            MessageType.STREAM_STOPPED: [],
            MessageType.ACQUISITION_STREAM_STARTED: [],
            MessageType.ACQUISITION_STREAM_STOPPED: [],
            MessageType.PONG: [],
        }

        # Stream data handlers (for convenience)
        self._stream_data_handlers: List[Callable] = []

        # Generic message callback for all messages
        self._generic_callbacks: List[Callable] = []

        # Connection state
        self.connected = False
        self.connecting = False
        self._should_reconnect = True
        self._reconnect_delay = 5.0  # seconds

        # Active streams tracking
        self._active_streams: Dict[str, StreamConfig] = {}

        # Statistics
        self.messages_received = 0
        self.messages_sent = 0
        self.errors = 0

    # ==================== Connection Management ====================

    async def connect(self) -> bool:
        """Connect to WebSocket server.

        Returns:
            True if connected successfully
        """
        if self.connected or self.connecting:
            logger.warning("Already connected or connecting")
            return self.connected

        self.connecting = True

        try:
            logger.info(f"Connecting to WebSocket at {self.url}")
            self._connection = await websockets.connect(
                self.url,
                ping_interval=20,
                ping_timeout=10,
            )

            self.connected = True
            self.connecting = False
            logger.info("WebSocket connected successfully")

            # Start receiving messages
            self._receive_task = asyncio.create_task(self._receive_loop())

            # Start periodic ping
            self._ping_task = asyncio.create_task(self._ping_loop())

            # Restart any active streams
            await self._restart_streams()

            return True

        except Exception as e:
            self.connecting = False
            logger.error(f"Failed to connect WebSocket: {e}")

            # Start reconnection if enabled
            if self._should_reconnect and not self._reconnect_task:
                self._reconnect_task = asyncio.create_task(self._reconnect_loop())

            return False

    async def disconnect(self):
        """Disconnect from WebSocket server."""
        logger.info("Disconnecting WebSocket")

        self._should_reconnect = False
        self.connected = False

        # Cancel tasks
        if self._receive_task:
            self._receive_task.cancel()
            self._receive_task = None

        if self._ping_task:
            self._ping_task.cancel()
            self._ping_task = None

        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None

        # Close connection
        if self._connection:
            try:
                await self._connection.close()
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")
            finally:
                self._connection = None

        logger.info("WebSocket disconnected")

    async def _receive_loop(self):
        """Receive and process messages from server."""
        try:
            async for message in self._connection:
                try:
                    self.messages_received += 1
                    data = json.loads(message)
                    await self._handle_message(data)

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode message: {e}")
                    self.errors += 1

                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    self.errors += 1

        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
            self.connected = False

            # Start reconnection if enabled
            if self._should_reconnect:
                self._reconnect_task = asyncio.create_task(self._reconnect_loop())

        except Exception as e:
            logger.error(f"Error in receive loop: {e}")
            self.connected = False
            self.errors += 1

    async def _reconnect_loop(self):
        """Automatically reconnect on connection loss."""
        while self._should_reconnect and not self.connected:
            logger.info(f"Attempting to reconnect in {self._reconnect_delay} seconds...")
            await asyncio.sleep(self._reconnect_delay)

            if self._should_reconnect:
                await self.connect()

    async def _ping_loop(self):
        """Send periodic pings to keep connection alive."""
        while self.connected:
            try:
                await asyncio.sleep(30)  # Ping every 30 seconds
                if self.connected:
                    await self.send_ping()
            except Exception as e:
                logger.error(f"Error in ping loop: {e}")

    async def _restart_streams(self):
        """Restart all active streams after reconnection."""
        if not self._active_streams:
            return

        logger.info(f"Restarting {len(self._active_streams)} active streams")

        for stream_key, config in list(self._active_streams.items()):
            try:
                await self.start_equipment_stream(
                    equipment_id=config.equipment_id,
                    stream_type=config.stream_type,
                    interval_ms=config.interval_ms
                )
            except Exception as e:
                logger.error(f"Failed to restart stream {stream_key}: {e}")

    async def _handle_message(self, data: Dict[str, Any]):
        """Handle incoming message from server.

        Args:
            data: Parsed message data
        """
        msg_type = data.get("type")

        # Call specific handlers
        if msg_type in self._message_handlers:
            for handler in self._message_handlers[msg_type]:
                try:
                    # Check if handler is async
                    if asyncio.iscoroutinefunction(handler):
                        await handler(data)
                    else:
                        handler(data)
                except Exception as e:
                    logger.error(f"Error in message handler: {e}")

        # Call stream data handlers for stream_data messages
        if msg_type == "stream_data":
            for handler in self._stream_data_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(data)
                    else:
                        handler(data)
                except Exception as e:
                    logger.error(f"Error in stream data handler: {e}")

        # Call generic handlers
        for handler in self._generic_callbacks:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"Error in generic handler: {e}")

    async def _route_message(self, data: Dict[str, Any]):
        """Alias for _handle_message for backward compatibility.

        Args:
            data: Parsed message data
        """
        await self._handle_message(data)

    # ==================== Message Sending ====================

    async def _send_message(self, message: Dict[str, Any]):
        """Send a message to server.

        Args:
            message: Message dictionary to send
        """
        if not self.connected or not self._connection:
            raise RuntimeError("WebSocket not connected")

        try:
            await self._connection.send(json.dumps(message))
            self.messages_sent += 1
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            self.errors += 1
            raise

    async def send_ping(self):
        """Send ping to server."""
        await self._send_message({"type": MessageType.PING})

    # ==================== Equipment Streaming ====================

    async def start_equipment_stream(
        self,
        equipment_id: str,
        stream_type: str = "readings",
        interval_ms: int = 100
    ):
        """Start streaming data from equipment.

        Args:
            equipment_id: Equipment ID
            stream_type: Type of data to stream (string or StreamType enum)
            interval_ms: Update interval in milliseconds
        """
        # Convert StreamType enum to string if needed
        if isinstance(stream_type, StreamType):
            stream_type_str = stream_type.value
        else:
            stream_type_str = stream_type

        message = {
            "type": MessageType.START_STREAM,
            "equipment_id": equipment_id,
            "stream_type": stream_type_str,
            "interval_ms": interval_ms
        }

        await self._send_message(message)

        # Track active stream
        stream_key = f"{equipment_id}_{stream_type_str}"
        self._active_streams[stream_key] = StreamConfig(
            equipment_id=equipment_id,
            stream_type=stream_type_str,
            interval_ms=interval_ms
        )

        logger.info(f"Started {stream_type_str} stream for {equipment_id}")

    async def stop_equipment_stream(
        self,
        equipment_id: str,
        stream_type: str = "readings"
    ):
        """Stop streaming data from equipment.

        Args:
            equipment_id: Equipment ID
            stream_type: Type of data stream to stop (string or StreamType enum)
        """
        # Convert StreamType enum to string if needed
        if isinstance(stream_type, StreamType):
            stream_type_str = stream_type.value
        else:
            stream_type_str = stream_type

        message = {
            "type": MessageType.STOP_STREAM,
            "equipment_id": equipment_id,
            "stream_type": stream_type_str
        }

        await self._send_message(message)

        # Remove from active streams
        stream_key = f"{equipment_id}_{stream_type_str}"
        self._active_streams.pop(stream_key, None)

        logger.info(f"Stopped {stream_type_str} stream for {equipment_id}")

    # ==================== Acquisition Streaming ====================

    async def start_acquisition_stream(
        self,
        acquisition_id: str,
        interval_ms: int = 100,
        num_samples: int = 100
    ):
        """Start streaming acquisition data.

        Args:
            acquisition_id: Acquisition session ID
            interval_ms: Update interval in milliseconds
            num_samples: Number of samples to send per update
        """
        message = {
            "type": MessageType.START_ACQUISITION_STREAM,
            "acquisition_id": acquisition_id,
            "interval_ms": interval_ms,
            "num_samples": num_samples
        }

        await self._send_message(message)
        logger.info(f"Started acquisition stream for {acquisition_id}")

    async def stop_acquisition_stream(self, acquisition_id: str):
        """Stop streaming acquisition data.

        Args:
            acquisition_id: Acquisition session ID
        """
        message = {
            "type": MessageType.STOP_ACQUISITION_STREAM,
            "acquisition_id": acquisition_id
        }

        await self._send_message(message)
        logger.info(f"Stopped acquisition stream for {acquisition_id}")

    # ==================== Callback Registration ====================

    def register_handler(self, message_type: MessageType, handler: Callable):
        """Register a handler for specific message type.

        Args:
            message_type: Type of message to handle
            handler: Callback function (can be sync or async)
        """
        if message_type in self._message_handlers:
            self._message_handlers[message_type].append(handler)
        else:
            logger.warning(f"Unknown message type: {message_type}")

    def unregister_handler(self, message_type: MessageType, handler: Callable):
        """Unregister a handler.

        Args:
            message_type: Type of message
            handler: Callback function to remove
        """
        if message_type in self._message_handlers:
            try:
                self._message_handlers[message_type].remove(handler)
            except ValueError:
                pass

    def register_generic_handler(self, handler: Callable):
        """Register a handler for all messages.

        Args:
            handler: Callback function (can be sync or async)
        """
        self._generic_callbacks.append(handler)

    def unregister_generic_handler(self, handler: Callable):
        """Unregister a generic handler.

        Args:
            handler: Callback function to remove
        """
        try:
            self._generic_callbacks.remove(handler)
        except ValueError:
            pass

    # Backward compatibility aliases
    def register_message_handler(self, message_type: str, handler: Callable):
        """Register a handler for specific message type (alias for register_handler).

        Args:
            message_type: Type of message to handle (string)
            handler: Callback function (can be sync or async)
        """
        # Create message type entry if it doesn't exist
        if message_type not in self._message_handlers:
            self._message_handlers[message_type] = []
        self._message_handlers[message_type].append(handler)

    def unregister_message_handler(self, message_type: str, handler: Callable):
        """Unregister a message handler (alias for unregister_handler).

        Args:
            message_type: Type of message
            handler: Callback function to remove
        """
        if message_type in self._message_handlers:
            try:
                self._message_handlers[message_type].remove(handler)
            except ValueError:
                pass

    def register_stream_data_handler(self, handler: Callable):
        """Register a handler for stream data messages.

        Args:
            handler: Callback function (can be sync or async)
        """
        self._stream_data_handlers.append(handler)

    def unregister_stream_data_handler(self, handler: Callable):
        """Unregister a stream data handler.

        Args:
            handler: Callback function to remove
        """
        try:
            self._stream_data_handlers.remove(handler)
        except ValueError:
            pass

    # ==================== Convenience Methods ====================

    def on_stream_data(self, handler: Callable):
        """Register handler for equipment stream data.

        Usage:
            @ws_manager.on_stream_data
            def handle_data(message):
                equipment_id = message['equipment_id']
                data = message['data']
                ...
        """
        self.register_handler(MessageType.STREAM_DATA, handler)
        return handler

    def on_acquisition_data(self, handler: Callable):
        """Register handler for acquisition stream data.

        Usage:
            @ws_manager.on_acquisition_data
            def handle_acq_data(message):
                acquisition_id = message['acquisition_id']
                data = message['data']
                ...
        """
        self.register_handler(MessageType.ACQUISITION_STREAM, handler)
        return handler

    # ==================== Status and Statistics ====================

    def get_statistics(self) -> Dict[str, Any]:
        """Get WebSocket statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "connected": self.connected,
            "messages_received": self.messages_received,
            "messages_sent": self.messages_sent,
            "errors": self.errors,
            "active_streams": len(self._active_streams),
            "stream_list": list(self._active_streams.keys()),
            "message_handlers": len(self._message_handlers),
            "stream_data_handlers": len(self._stream_data_handlers)
        }

    def get_active_streams(self) -> List[str]:
        """Get list of active stream identifiers.

        Returns:
            List of stream keys
        """
        return list(self._active_streams.keys())
