"""WebSocket manager for real-time data streaming."""

import asyncio
from urllib.parse import quote
import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

try:
    import websockets

    # websockets 14 replaced the legacy client with the asyncio implementation;
    # websockets.client.WebSocketClientProtocol still resolves but is deprecated
    # and slated for removal. Prefer the modern type and fall back for older
    # installs.
    try:
        from websockets.asyncio.client import ClientConnection as WebSocketClientProtocol
    except ImportError:  # websockets < 14
        from websockets.client import WebSocketClientProtocol
except ImportError:
    websockets = None
    WebSocketClientProtocol = None

logger = logging.getLogger(__name__)


class StreamType(str, Enum):
    """Types of data streams."""

    READINGS = "readings"
    WAVEFORM = "waveform"        # metadata only: no samples
    MEASUREMENTS = "measurements"
    TRACE = "trace"              # the samples, pushed for a live trace


class MessageType(str, Enum):
    """WebSocket message types."""

    # Client -> Server
    START_STREAM = "start_stream"
    STOP_STREAM = "stop_stream"
    START_ACQUISITION_STREAM = "start_acquisition_stream"
    STOP_ACQUISITION_STREAM = "stop_acquisition_stream"
    PING = "ping"

    # Server -> Client
    #
    # This list was missing two thirds of what the server actually
    # sends -- discovery_progress, every alarm and scheduler event, the
    # diagnostics ones. That was not merely untidy: register_handler
    # accepts only the types seeded into _message_handlers below and
    # otherwise logs a warning and returns, so registering for any of
    # the absent ones silently did nothing. Callers that happened to use
    # register_message_handler, documented as an alias but in fact the
    # permissive one, worked; the rest failed quietly.
    #
    # Derived by grepping the server for what it puts in "type". Keep it
    # that way: an entry missing here is a handler that never fires.
    STREAM_DATA = "stream_data"
    ACQUISITION_STREAM = "acquisition_stream"
    STREAM_STARTED = "stream_started"
    STREAM_STOPPED = "stream_stopped"
    ACQUISITION_STREAM_STARTED = "acquisition_stream_started"
    ACQUISITION_STREAM_STOPPED = "acquisition_stream_stopped"
    PONG = "pong"
    DISCOVERY_PROGRESS = "discovery_progress"
    CAPABILITIES = "capabilities"
    ERROR = "error"
    BROADCAST = "broadcast"
    REFRESH = "refresh"
    STATS = "stats"
    # Alarms
    ALARM = "alarm"
    ALARM_EVENT = "alarm_event"
    ALARM_UPDATED = "alarm_updated"
    ALARM_CLEARED = "alarm_cleared"
    # Scheduler
    JOB_CREATED = "job_created"
    JOB_UPDATED = "job_updated"
    JOB_DELETED = "job_deleted"
    JOB_STARTED = "job_started"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    # Recording and diagnostics
    RECORDING_STARTED = "recording_started"
    RECORDING_STOPPED = "recording_stopped"
    COMPRESSION_SET = "compression_set"
    PRIORITY_SET = "priority_set"
    ERROR_SPIKE = "error_spike"
    REPEATED_ERROR = "repeated_error"
    SLOW_OPERATION = "slow_operation"


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
            raise ImportError(
                "websockets library not installed. Install with: pip install websockets"
            )

        self.host = host
        self.port = port
        self.base_url = f"ws://{host}:{port}/ws"
        self.url = self.base_url

        #: Returns the current access token, or None. The server closes /ws
        #: with 4001 unless the token is supplied as a query parameter, and
        #: nothing here ever supplied one -- so on a secured server the socket
        #: never connected at all and simply retried every five seconds
        #: forever. Read at connect time rather than stored, so a token
        #: renewed elsewhere is picked up by the next attempt.
        self.token_provider = None

        #: Asks for a new access token after the server rejects this one.
        self.renew_token = None

        #: Set when the server closed the socket over the credential.
        self._rejected_for_auth = False

        self._connection: Optional[WebSocketClientProtocol] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None

        # Callbacks for different message types.
        #
        # Seeded from the enum rather than hand-listed. The hand-written
        # version held seven of them and drifted from both the enum and
        # the server, and because register_handler treats an unseeded
        # type as unknown, every gap was a handler that never fired.
        self._message_handlers: Dict[str, List[Callable]] = {
            member.value: [] for member in MessageType
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

    def _authenticated_url(self) -> str:
        """The socket URL, carrying the access token when there is one."""
        token = None
        if self.token_provider is not None:
            try:
                token = self.token_provider()
            except Exception as e:
                logger.warning(f"Could not read the access token: {e}")

        if not token:
            return self.base_url
        return f"{self.base_url}?token={quote(token, safe='')}"


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
            self.url = self._authenticated_url()
            # The token is a query parameter, so keep it out of the log.
            logger.info(f"Connecting to WebSocket at {self.base_url}")
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
            # 4001 is the server's own "authentication" close code; a secured
            # server also refuses the handshake outright with 403. Either way
            # the credential is the problem, and retrying with the same one
            # cannot help.
            detail = str(e)
            self._rejected_for_auth = "4001" in detail or "403" in detail
            logger.error(f"Failed to connect WebSocket: {e}")
            if self._rejected_for_auth:
                logger.info("WebSocket refused the credential; will renew before retrying")

            self._ensure_reconnecting()

            return False

    def _ensure_reconnecting(self):
        """Start the reconnect loop, unless one is already running.

        Tested on the task rather than on "have we ever made one". The
        guard used to be ``not self._reconnect_task``, and nothing ever
        put that attribute back to None when the loop finished -- so after
        the first reconnect the attribute stayed truthy for the life of
        the process and every later attempt was silently skipped. One
        disconnect/reconnect cycle worked; the ones after it did not.
        """
        if not self._should_reconnect:
            return
        running = self._reconnect_task
        if running is not None and not running.done():
            return
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    def _note_connection_lost(self, why: str):
        """Mark the connection down and get a reconnect going.

        Whatever noticed -- the reader, the ping, a failed send -- the
        connection is gone and something has to say so. Only the reader's
        ConnectionClosed branch used to do it, so a failure seen anywhere
        else left ``connected`` True with no reader and no reconnect: the
        ping loop then pinged a dead socket every thirty seconds for as
        long as the application ran. Eight minutes of that were in the
        bench log before anyone restarted the client.
        """
        if self.connected:
            logger.warning(f"WebSocket connection lost: {why}")
        self.connected = False
        self._ensure_reconnecting()

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

        except asyncio.CancelledError:
            raise                       # disconnect() asked; do not reconnect

        except websockets.exceptions.ConnectionClosed:
            self._note_connection_lost("the server closed it")

        except Exception as e:
            self.errors += 1
            # Also reconnects. This branch used to mark the connection down
            # and stop there, so anything that was not a clean
            # ConnectionClosed killed the reader for good and left nothing
            # watching the socket.
            self._note_connection_lost(str(e))

    async def _reconnect_loop(self):
        """Automatically reconnect on connection loss."""
        try:
            await self._reconnecting()
        finally:
            # Cleared so the next loss can start a new one. Leaving it set
            # is what made reconnection a once-per-process affair.
            self._reconnect_task = None

    async def _reconnecting(self):
        while self._should_reconnect and not self.connected:
            logger.info(
                f"Attempting to reconnect in {self._reconnect_delay} seconds..."
            )
            await asyncio.sleep(self._reconnect_delay)

            if self._should_reconnect:
                # A rejected token will be rejected again on every retry, so
                # renew before reconnecting rather than reconnecting forever
                # with the credential the server has already refused.
                if self._rejected_for_auth and self.renew_token is not None:
                    try:
                        self.renew_token()
                    except Exception as e:
                        logger.warning(f"Could not renew the token: {e}")
                    self._rejected_for_auth = False

                await self.connect()

    async def _ping_loop(self):
        """Send periodic pings, and report the connection dead when one fails.

        A ping that cannot be sent is the clearest evidence there is that
        the connection has gone. This used to log the exception and carry
        on round the loop, so a dead socket was pinged every thirty
        seconds indefinitely -- ``connected`` stayed True, nothing
        reconnected, and the operator's streams were off with no sign of
        it beyond a repeating line in the log.
        """
        while self.connected:
            try:
                await asyncio.sleep(30)  # Ping every 30 seconds
                if self.connected:
                    await self.send_ping()
            except asyncio.CancelledError:
                raise                   # disconnect() asked
            except Exception as e:
                self._note_connection_lost(f"ping failed: {e}")
                return

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
                    interval_ms=config.interval_ms,
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
        self, equipment_id: str, stream_type: str = "readings",
        interval_ms: int = 100, parameters: Optional[dict] = None,
    ):
        """Start streaming data from equipment.

        Args:
            equipment_id: Equipment ID
            stream_type: Type of data to stream (string or StreamType enum)
            interval_ms: Update interval in milliseconds
            parameters: passed to the driver command; a trace stream names
                its channel and point count here
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
            "interval_ms": interval_ms,
            "parameters": parameters or {},
        }

        # Recorded before sending, not after. This list is what the
        # operator has asked for, not what happened to succeed, and it is
        # what _restart_streams replays once the socket is back. Recording
        # it afterwards meant a start that failed *because* the socket had
        # just died was never remembered -- so the reconnect restored the
        # connection and not the stream, and the readings stayed off with
        # nothing saying so:
        #
        #   22:42:19  Could not start equipment stream: keepalive ping timeout
        #   22:42:19  WebSocket connection lost: ping failed
        #   22:42:24  WebSocket connected successfully   (and no stream)
        stream_key = f"{equipment_id}_{stream_type_str}"
        self._active_streams[stream_key] = StreamConfig(
            equipment_id=equipment_id,
            stream_type=stream_type_str,
            interval_ms=interval_ms,
        )

        await self._send_message(message)

        logger.info(f"Started {stream_type_str} stream for {equipment_id}")

    async def stop_equipment_stream(
        self, equipment_id: str, stream_type: str = "readings"
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
            "stream_type": stream_type_str,
        }

        await self._send_message(message)

        # Remove from active streams
        stream_key = f"{equipment_id}_{stream_type_str}"
        self._active_streams.pop(stream_key, None)

        logger.info(f"Stopped {stream_type_str} stream for {equipment_id}")

    # ==================== Acquisition Streaming ====================

    async def start_acquisition_stream(
        self, acquisition_id: str, interval_ms: int = 100, num_samples: int = 100
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
            "num_samples": num_samples,
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
            "acquisition_id": acquisition_id,
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
        # Registering must never be a silent no-op. This used to log a
        # warning and drop the handler for any type not pre-seeded, so a
        # panel asking for a message the server really does send simply
        # never heard it, with one warning at startup to say so. The
        # handler is now always recorded; an unrecognised name is still
        # worth a warning, because it is most likely a typo, but the
        # registration stands either way.
        if message_type not in self._message_handlers:
            known = {member.value for member in MessageType}
            if str(message_type) not in known:
                logger.warning(
                    f"Registering for {message_type!r}, which is not a "
                    f"known MessageType -- check the spelling, or add it "
                    f"if the server has grown a new one"
                )
            self._message_handlers[message_type] = []
        self._message_handlers[message_type].append(handler)

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
            "stream_data_handlers": len(self._stream_data_handlers),
        }

    def get_active_streams(self) -> List[str]:
        """Get list of active stream identifiers.

        Returns:
            List of stream keys
        """
        return list(self._active_streams.keys())
