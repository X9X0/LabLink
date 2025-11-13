"""Enhanced WebSocket manager with advanced features.

This module extends the basic StreamManager with:
- Stream recording capabilities
- Message compression
- Priority-based routing
- Backpressure handling
"""

import asyncio
import base64
import json
import logging
from typing import Any, Dict, Optional, Set
from datetime import datetime
from fastapi import WebSocket

from .enhanced_features import (
    StreamRecorder,
    StreamRecordingConfig,
    MessageCompressor,
    CompressionType,
    BackpressureHandler,
    BackpressureConfig,
    MessagePriority,
    RecordingFormat,
)

logger = logging.getLogger(__name__)


class EnhancedStreamManager:
    """Enhanced WebSocket stream manager with advanced features."""

    def __init__(
        self,
        recording_config: Optional[StreamRecordingConfig] = None,
        backpressure_config: Optional[BackpressureConfig] = None,
    ):
        """Initialize enhanced stream manager.

        Args:
            recording_config: Stream recording configuration
            backpressure_config: Backpressure handling configuration
        """
        # Connection management
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
        self.streaming_tasks: Dict[str, asyncio.Task] = {}

        # Enhanced features
        self.recording_config = recording_config or StreamRecordingConfig()
        self.backpressure_config = backpressure_config or BackpressureConfig()

        # Feature managers
        self.recorder = StreamRecorder(self.recording_config)
        self.compressor = MessageCompressor()

        # Per-connection backpressure handlers
        self.backpressure_handlers: Dict[str, BackpressureHandler] = {}

        # Per-connection send tasks
        self.send_tasks: Dict[str, asyncio.Task] = {}

        # Statistics
        self.stats = {
            "total_connections": 0,
            "total_messages_sent": 0,
            "total_messages_received": 0,
            "total_bytes_sent": 0,
            "total_bytes_received": 0,
            "compression_ratio_sum": 0.0,
            "compression_count": 0,
        }

    async def connect(
        self,
        websocket: WebSocket,
        client_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Accept and configure a WebSocket connection.

        Args:
            websocket: WebSocket connection
            client_id: Unique client identifier
            metadata: Optional connection metadata
        """
        await websocket.accept()

        # Store connection
        self.active_connections[client_id] = websocket
        self.connection_metadata[client_id] = metadata or {}

        # Initialize backpressure handler for this connection
        self.backpressure_handlers[client_id] = BackpressureHandler(
            self.backpressure_config
        )

        # Start send task for this connection
        self.send_tasks[client_id] = asyncio.create_task(
            self._send_loop(client_id)
        )

        # Update statistics
        self.stats["total_connections"] += 1

        logger.info(
            f"WebSocket connected: {client_id}. "
            f"Total connections: {len(self.active_connections)}"
        )

        # Send welcome message with capabilities
        await self._send_capabilities(client_id)

    def disconnect(self, client_id: str):
        """Disconnect a WebSocket connection.

        Args:
            client_id: Client identifier
        """
        if client_id not in self.active_connections:
            return

        # Cancel send task
        if client_id in self.send_tasks:
            self.send_tasks[client_id].cancel()
            del self.send_tasks[client_id]

        # Remove connection
        del self.active_connections[client_id]
        del self.connection_metadata[client_id]

        # Remove backpressure handler
        if client_id in self.backpressure_handlers:
            del self.backpressure_handlers[client_id]

        logger.info(
            f"WebSocket disconnected: {client_id}. "
            f"Total connections: {len(self.active_connections)}"
        )

    async def send_to_client(
        self,
        client_id: str,
        message: Dict[str, Any],
        priority: MessagePriority = MessagePriority.NORMAL,
        compression: Optional[CompressionType] = None,
    ) -> bool:
        """Send a message to a specific client.

        Args:
            client_id: Client identifier
            message: Message to send
            priority: Message priority
            compression: Optional compression type

        Returns:
            True if queued/sent, False if failed
        """
        if client_id not in self.active_connections:
            return False

        # Add compression metadata if specified
        if compression and compression != CompressionType.NONE:
            message["_compression"] = compression.value

        # Queue message with backpressure handling
        handler = self.backpressure_handlers[client_id]
        return await handler.queue_message(message, priority)

    async def broadcast(
        self,
        message: Dict[str, Any],
        priority: MessagePriority = MessagePriority.NORMAL,
        compression: Optional[CompressionType] = None,
        exclude_clients: Optional[Set[str]] = None,
    ):
        """Broadcast a message to all connected clients.

        Args:
            message: Message to broadcast
            priority: Message priority
            compression: Optional compression type
            exclude_clients: Optional set of client IDs to exclude
        """
        exclude = exclude_clients or set()

        for client_id in list(self.active_connections.keys()):
            if client_id not in exclude:
                await self.send_to_client(
                    client_id, message, priority, compression
                )

    async def _send_loop(self, client_id: str):
        """Background task to send queued messages to client.

        Args:
            client_id: Client identifier
        """
        websocket = self.active_connections[client_id]
        handler = self.backpressure_handlers[client_id]

        try:
            while True:
                # Get next message from queue
                priority_msg = await handler.get_next_message()

                if priority_msg is None:
                    # No messages available or rate limited, wait a bit
                    await asyncio.sleep(0.01)
                    continue

                message = priority_msg.data

                # Check if message should be compressed
                compression_type = CompressionType.NONE
                if "_compression" in message:
                    compression_type = CompressionType(message["_compression"])
                    del message["_compression"]

                # Send message
                try:
                    if compression_type != CompressionType.NONE:
                        # Send compressed message
                        await self._send_compressed(
                            websocket, message, compression_type
                        )
                    else:
                        # Send uncompressed JSON
                        await websocket.send_json(message)

                    self.stats["total_messages_sent"] += 1

                    # Record to file if enabled
                    if self.recording_config.enabled:
                        for session_id in self.recorder.get_active_recordings():
                            # Check if this client is part of recording
                            # (simplified - in production, you'd filter by session)
                            self.recorder.record_message(session_id, message)

                except Exception as e:
                    logger.error(
                        f"Error sending message to {client_id}: {e}"
                    )
                    self.disconnect(client_id)
                    break

        except asyncio.CancelledError:
            logger.info(f"Send loop cancelled for {client_id}")
        except Exception as e:
            logger.error(f"Error in send loop for {client_id}: {e}")

    async def _send_compressed(
        self,
        websocket: WebSocket,
        message: Dict[str, Any],
        compression_type: CompressionType
    ):
        """Send a compressed message.

        Args:
            websocket: WebSocket connection
            message: Message to send
            compression_type: Type of compression to use
        """
        # Convert to JSON string
        json_str = json.dumps(message)
        original_size = len(json_str.encode("utf-8"))

        # Compress
        compressed = self.compressor.compress(json_str, compression_type)
        compressed_size = len(compressed)

        # Calculate compression ratio
        ratio = self.compressor.calculate_compression_ratio(
            json_str, compressed
        )
        self.stats["compression_ratio_sum"] += ratio
        self.stats["compression_count"] += 1

        # Send as binary with compression metadata
        # Format: 1 byte compression type + compressed data
        compression_byte = bytes([compression_type.value.encode("utf-8")[0]])
        await websocket.send_bytes(compression_byte + compressed)

        self.stats["total_bytes_sent"] += compressed_size

        logger.debug(
            f"Sent compressed message: {original_size} -> {compressed_size} bytes "
            f"(ratio: {ratio:.2f}x)"
        )

    async def _send_capabilities(self, client_id: str):
        """Send server capabilities to client.

        Args:
            client_id: Client identifier
        """
        capabilities = {
            "type": "capabilities",
            "features": {
                "compression": {
                    "enabled": True,
                    "types": [ct.value for ct in CompressionType],
                },
                "priorities": {
                    "enabled": True,
                    "levels": [p.name for p in MessagePriority],
                },
                "recording": {
                    "enabled": self.recording_config.enabled,
                    "formats": [f.value for f in RecordingFormat],
                },
                "backpressure": {
                    "enabled": self.backpressure_config.enabled,
                    "max_queue_size": self.backpressure_config.max_queue_size,
                    "rate_limit": self.backpressure_config.max_messages_per_second,
                },
            },
        }

        await self.send_to_client(
            client_id, capabilities, MessagePriority.HIGH
        )

    def start_recording(
        self,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Start recording WebSocket stream.

        Args:
            session_id: Recording session identifier
            metadata: Optional recording metadata

        Returns:
            Path to recording file
        """
        return self.recorder.start_recording(session_id, metadata)

    def stop_recording(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Stop recording WebSocket stream.

        Args:
            session_id: Recording session identifier

        Returns:
            Recording statistics
        """
        return self.recorder.stop_recording(session_id)

    def get_recording_stats(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get recording statistics.

        Args:
            session_id: Recording session identifier

        Returns:
            Recording statistics
        """
        return self.recorder.get_recording_stats(session_id)

    def get_active_recordings(self) -> list[str]:
        """Get list of active recording sessions."""
        return self.recorder.get_active_recordings()

    def get_backpressure_stats(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Get backpressure statistics for a client.

        Args:
            client_id: Client identifier

        Returns:
            Backpressure statistics
        """
        if client_id not in self.backpressure_handlers:
            return None

        return self.backpressure_handlers[client_id].get_stats()

    def get_global_stats(self) -> Dict[str, Any]:
        """Get global statistics for all connections."""
        avg_compression_ratio = 0.0
        if self.stats["compression_count"] > 0:
            avg_compression_ratio = (
                self.stats["compression_ratio_sum"] /
                self.stats["compression_count"]
            )

        return {
            **self.stats,
            "active_connections": len(self.active_connections),
            "active_recordings": len(self.recorder.get_active_recordings()),
            "average_compression_ratio": avg_compression_ratio,
        }

    def get_connection_info(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific connection.

        Args:
            client_id: Client identifier

        Returns:
            Connection information
        """
        if client_id not in self.active_connections:
            return None

        backpressure_stats = self.get_backpressure_stats(client_id)

        return {
            "client_id": client_id,
            "metadata": self.connection_metadata.get(client_id, {}),
            "backpressure": backpressure_stats,
        }

    def get_all_connections(self) -> list[Dict[str, Any]]:
        """Get information about all active connections."""
        return [
            self.get_connection_info(client_id)
            for client_id in self.active_connections.keys()
        ]
