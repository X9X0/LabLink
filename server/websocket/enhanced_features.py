"""Enhanced WebSocket features for LabLink.

This module provides advanced WebSocket capabilities including:
- Stream recording to files
- Message compression options
- Priority channels for message routing
- Backpressure handling for flow control
"""

import asyncio
import gzip
import json
import logging
import time
import zlib
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)


class CompressionType(str, Enum):
    """Message compression types."""
    NONE = "none"
    GZIP = "gzip"
    ZLIB = "zlib"


class MessagePriority(int, Enum):
    """Message priority levels."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class RecordingFormat(str, Enum):
    """Stream recording formats."""
    JSON = "json"
    JSONL = "jsonl"  # JSON Lines (one JSON object per line)
    CSV = "csv"
    BINARY = "binary"


@dataclass
class StreamRecordingConfig:
    """Configuration for stream recording."""
    enabled: bool = False
    format: RecordingFormat = RecordingFormat.JSONL
    output_dir: str = "./data/recordings"
    max_file_size_mb: int = 100
    include_timestamps: bool = True
    include_metadata: bool = True
    compress_output: bool = True


@dataclass
class BackpressureConfig:
    """Configuration for backpressure handling."""
    enabled: bool = True
    max_queue_size: int = 1000
    warning_threshold: int = 750  # 75% of max
    drop_low_priority: bool = True
    rate_limit_enabled: bool = True
    max_messages_per_second: int = 100
    burst_size: int = 50


@dataclass
class PriorityMessage:
    """Message with priority information."""
    priority: MessagePriority
    timestamp: float
    data: Dict[str, Any]
    compressed: bool = False
    compression_type: Optional[CompressionType] = None


class StreamRecorder:
    """Records WebSocket streams to files."""

    def __init__(self, config: StreamRecordingConfig):
        """Initialize stream recorder."""
        self.config = config
        self.recording_sessions: Dict[str, Dict[str, Any]] = {}
        self._ensure_output_dir()

    def _ensure_output_dir(self):
        """Ensure output directory exists."""
        Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)

    def start_recording(
        self,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Start recording a stream.

        Args:
            session_id: Unique session identifier
            metadata: Optional metadata to include in recording

        Returns:
            Path to the recording file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"stream_{session_id}_{timestamp}"

        # Add extension based on format
        if self.config.format == RecordingFormat.JSON:
            filename += ".json"
        elif self.config.format == RecordingFormat.JSONL:
            filename += ".jsonl"
        elif self.config.format == RecordingFormat.CSV:
            filename += ".csv"
        elif self.config.format == RecordingFormat.BINARY:
            filename += ".bin"

        # Add .gz if compression is enabled
        if self.config.compress_output:
            filename += ".gz"

        filepath = Path(self.config.output_dir) / filename

        # Initialize recording session
        self.recording_sessions[session_id] = {
            "filepath": str(filepath),
            "start_time": time.time(),
            "message_count": 0,
            "bytes_written": 0,
            "metadata": metadata or {},
            "file_handle": None,
        }

        # Open file based on format
        if self.config.compress_output:
            self.recording_sessions[session_id]["file_handle"] = gzip.open(
                filepath, "wt", encoding="utf-8"
            )
        else:
            self.recording_sessions[session_id]["file_handle"] = open(
                filepath, "w", encoding="utf-8"
            )

        # Write header/metadata based on format
        if self.config.format == RecordingFormat.JSON:
            # JSON format starts with array
            session = self.recording_sessions[session_id]
            session["file_handle"].write("[\n")
            if self.config.include_metadata and metadata:
                session["file_handle"].write(
                    json.dumps({"_metadata": metadata}, indent=2) + ",\n"
                )
        elif self.config.format == RecordingFormat.CSV:
            # CSV format writes header
            session = self.recording_sessions[session_id]
            session["file_handle"].write("timestamp,message_type,data\n")

        logger.info(f"Started recording stream {session_id} to {filepath}")
        return str(filepath)

    def record_message(self, session_id: str, message: Dict[str, Any]):
        """Record a message to the stream.

        Args:
            session_id: Session identifier
            message: Message to record
        """
        if session_id not in self.recording_sessions:
            logger.warning(f"No active recording for session {session_id}")
            return

        session = self.recording_sessions[session_id]
        file_handle = session["file_handle"]

        # Add timestamp if configured
        if self.config.include_timestamps:
            message = {
                "_timestamp": datetime.now().isoformat(),
                **message
            }

        # Write based on format
        try:
            if self.config.format == RecordingFormat.JSON:
                # JSON format (array of messages)
                if session["message_count"] > 0:
                    file_handle.write(",\n")
                file_handle.write(json.dumps(message, indent=2))

            elif self.config.format == RecordingFormat.JSONL:
                # JSONL format (one JSON per line)
                file_handle.write(json.dumps(message) + "\n")

            elif self.config.format == RecordingFormat.CSV:
                # CSV format
                timestamp = message.get("_timestamp", "")
                msg_type = message.get("type", "")
                data_str = json.dumps(message)
                file_handle.write(f'"{timestamp}","{msg_type}","{data_str}"\n')

            elif self.config.format == RecordingFormat.BINARY:
                # Binary format (simple JSON encoding for now)
                data = json.dumps(message).encode("utf-8")
                file_handle.write(data + b"\n")

            session["message_count"] += 1

            # Check file size
            current_size_mb = file_handle.tell() / (1024 * 1024)
            session["bytes_written"] = file_handle.tell()

            if current_size_mb >= self.config.max_file_size_mb:
                logger.warning(
                    f"Recording {session_id} reached max size, stopping"
                )
                self.stop_recording(session_id)

        except Exception as e:
            logger.error(f"Error recording message: {e}")

    def stop_recording(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Stop recording a stream.

        Args:
            session_id: Session identifier

        Returns:
            Recording statistics
        """
        if session_id not in self.recording_sessions:
            return None

        session = self.recording_sessions[session_id]
        file_handle = session["file_handle"]

        # Write footer based on format
        if self.config.format == RecordingFormat.JSON:
            file_handle.write("\n]")

        # Close file
        file_handle.close()

        # Calculate statistics
        duration = time.time() - session["start_time"]
        stats = {
            "filepath": session["filepath"],
            "duration_seconds": duration,
            "message_count": session["message_count"],
            "bytes_written": session["bytes_written"],
            "messages_per_second": (
                session["message_count"] / duration if duration > 0 else 0
            ),
        }

        logger.info(
            f"Stopped recording {session_id}: "
            f"{stats['message_count']} messages, "
            f"{stats['bytes_written']} bytes"
        )

        # Remove session
        del self.recording_sessions[session_id]

        return stats

    def get_active_recordings(self) -> List[str]:
        """Get list of active recording session IDs."""
        return list(self.recording_sessions.keys())

    def get_recording_stats(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get statistics for an active recording."""
        if session_id not in self.recording_sessions:
            return None

        session = self.recording_sessions[session_id]
        duration = time.time() - session["start_time"]

        return {
            "filepath": session["filepath"],
            "duration_seconds": duration,
            "message_count": session["message_count"],
            "bytes_written": session["bytes_written"],
            "messages_per_second": (
                session["message_count"] / duration if duration > 0 else 0
            ),
        }


class MessageCompressor:
    """Handles message compression for WebSocket."""

    @staticmethod
    def compress(
        data: str,
        compression_type: CompressionType = CompressionType.GZIP
    ) -> bytes:
        """Compress a string message.

        Args:
            data: String data to compress
            compression_type: Type of compression to use

        Returns:
            Compressed bytes
        """
        if compression_type == CompressionType.NONE:
            return data.encode("utf-8")

        data_bytes = data.encode("utf-8")

        if compression_type == CompressionType.GZIP:
            return gzip.compress(data_bytes)
        elif compression_type == CompressionType.ZLIB:
            return zlib.compress(data_bytes)

        return data_bytes

    @staticmethod
    def decompress(
        data: bytes,
        compression_type: CompressionType = CompressionType.GZIP
    ) -> str:
        """Decompress bytes to string.

        Args:
            data: Compressed bytes
            compression_type: Type of compression used

        Returns:
            Decompressed string
        """
        if compression_type == CompressionType.NONE:
            return data.decode("utf-8")

        if compression_type == CompressionType.GZIP:
            return gzip.decompress(data).decode("utf-8")
        elif compression_type == CompressionType.ZLIB:
            return zlib.decompress(data).decode("utf-8")

        return data.decode("utf-8")

    @staticmethod
    def calculate_compression_ratio(
        original: str,
        compressed: bytes
    ) -> float:
        """Calculate compression ratio.

        Args:
            original: Original string
            compressed: Compressed bytes

        Returns:
            Compression ratio (original_size / compressed_size)
        """
        original_size = len(original.encode("utf-8"))
        compressed_size = len(compressed)

        if compressed_size == 0:
            return 1.0

        return original_size / compressed_size


class PriorityQueue:
    """Priority queue for WebSocket messages."""

    def __init__(self, max_size: int = 1000):
        """Initialize priority queue."""
        self.max_size = max_size
        # Separate queues for each priority level
        self.queues: Dict[MessagePriority, deque] = {
            MessagePriority.CRITICAL: deque(),
            MessagePriority.HIGH: deque(),
            MessagePriority.NORMAL: deque(),
            MessagePriority.LOW: deque(),
        }
        self._size = 0

    def put(
        self,
        message: Dict[str, Any],
        priority: MessagePriority = MessagePriority.NORMAL
    ) -> bool:
        """Add message to queue.

        Args:
            message: Message to queue
            priority: Message priority

        Returns:
            True if added, False if queue is full
        """
        if self._size >= self.max_size:
            return False

        priority_msg = PriorityMessage(
            priority=priority,
            timestamp=time.time(),
            data=message
        )

        self.queues[priority].append(priority_msg)
        self._size += 1
        return True

    def get(self) -> Optional[PriorityMessage]:
        """Get highest priority message from queue.

        Returns:
            Message with highest priority, or None if empty
        """
        # Check queues in priority order
        for priority in [
            MessagePriority.CRITICAL,
            MessagePriority.HIGH,
            MessagePriority.NORMAL,
            MessagePriority.LOW
        ]:
            if self.queues[priority]:
                self._size -= 1
                return self.queues[priority].popleft()

        return None

    def size(self) -> int:
        """Get total queue size."""
        return self._size

    def size_by_priority(self, priority: MessagePriority) -> int:
        """Get queue size for specific priority."""
        return len(self.queues[priority])

    def clear_low_priority(self) -> int:
        """Clear low priority messages.

        Returns:
            Number of messages cleared
        """
        count = len(self.queues[MessagePriority.LOW])
        self.queues[MessagePriority.LOW].clear()
        self._size -= count
        return count

    def is_full(self) -> bool:
        """Check if queue is full."""
        return self._size >= self.max_size

    def clear(self):
        """Clear all messages from queue."""
        for queue in self.queues.values():
            queue.clear()
        self._size = 0


class BackpressureHandler:
    """Handles backpressure and flow control for WebSocket."""

    def __init__(self, config: BackpressureConfig):
        """Initialize backpressure handler."""
        self.config = config
        self.message_queue = PriorityQueue(max_size=config.max_queue_size)
        self.rate_limiter = RateLimiter(
            max_rate=config.max_messages_per_second,
            burst_size=config.burst_size
        )
        self.stats = {
            "messages_queued": 0,
            "messages_sent": 0,
            "messages_dropped": 0,
            "queue_overflows": 0,
            "rate_limit_hits": 0,
        }

    async def queue_message(
        self,
        message: Dict[str, Any],
        priority: MessagePriority = MessagePriority.NORMAL
    ) -> bool:
        """Queue a message for sending.

        Args:
            message: Message to queue
            priority: Message priority

        Returns:
            True if queued, False if dropped
        """
        if not self.config.enabled:
            return True

        # Check if queue is full
        if self.message_queue.is_full():
            if self.config.drop_low_priority:
                # Drop low priority messages to make room
                dropped = self.message_queue.clear_low_priority()
                self.stats["messages_dropped"] += dropped
                logger.warning(
                    f"Queue full, dropped {dropped} low priority messages"
                )
            else:
                self.stats["queue_overflows"] += 1
                self.stats["messages_dropped"] += 1
                logger.warning("Queue full, message dropped")
                return False

        # Check warning threshold
        queue_size = self.message_queue.size()
        if queue_size >= self.config.warning_threshold:
            logger.warning(
                f"Queue size {queue_size} exceeds warning threshold "
                f"{self.config.warning_threshold}"
            )

        # Queue message
        if self.message_queue.put(message, priority):
            self.stats["messages_queued"] += 1
            return True
        else:
            self.stats["messages_dropped"] += 1
            return False

    async def get_next_message(self) -> Optional[PriorityMessage]:
        """Get next message to send, respecting rate limits.

        Returns:
            Next message to send, or None if no messages or rate limited
        """
        if not self.config.enabled:
            return None

        # Check rate limit
        if self.config.rate_limit_enabled:
            if not await self.rate_limiter.acquire():
                self.stats["rate_limit_hits"] += 1
                return None

        # Get next message
        message = self.message_queue.get()
        if message:
            self.stats["messages_sent"] += 1

        return message

    def get_stats(self) -> Dict[str, Any]:
        """Get backpressure handler statistics."""
        return {
            **self.stats,
            "queue_size": self.message_queue.size(),
            "queue_size_by_priority": {
                "critical": self.message_queue.size_by_priority(
                    MessagePriority.CRITICAL
                ),
                "high": self.message_queue.size_by_priority(MessagePriority.HIGH),
                "normal": self.message_queue.size_by_priority(
                    MessagePriority.NORMAL
                ),
                "low": self.message_queue.size_by_priority(MessagePriority.LOW),
            },
        }

    def reset_stats(self):
        """Reset statistics."""
        self.stats = {
            "messages_queued": 0,
            "messages_sent": 0,
            "messages_dropped": 0,
            "queue_overflows": 0,
            "rate_limit_hits": 0,
        }


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, max_rate: int, burst_size: int):
        """Initialize rate limiter.

        Args:
            max_rate: Maximum messages per second
            burst_size: Maximum burst size
        """
        self.max_rate = max_rate
        self.burst_size = burst_size
        self.tokens = burst_size
        self.last_refill = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """Acquire a token for sending a message.

        Returns:
            True if token acquired, False if rate limited
        """
        async with self._lock:
            # Refill tokens based on time elapsed
            now = time.time()
            elapsed = now - self.last_refill
            tokens_to_add = elapsed * self.max_rate

            self.tokens = min(self.burst_size, self.tokens + tokens_to_add)
            self.last_refill = now

            # Try to acquire token
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True

            return False

    def get_tokens(self) -> float:
        """Get current token count."""
        return self.tokens
