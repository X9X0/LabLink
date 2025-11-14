"""Tests for enhanced WebSocket features.

Tests cover:
- Stream recording to files
- Message compression
- Priority channels
- Backpressure handling
"""

import asyncio
import gzip
import json
import shutil
# Import the modules we're testing
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from websocket.enhanced_features import (BackpressureConfig,
                                         BackpressureHandler, CompressionType,
                                         MessageCompressor, MessagePriority,
                                         PriorityQueue, RateLimiter,
                                         RecordingFormat, StreamRecorder,
                                         StreamRecordingConfig)
from websocket.enhanced_manager import EnhancedStreamManager


class TestStreamRecorder:
    """Test stream recording functionality."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def recorder(self, temp_dir):
        """Create stream recorder with temp directory."""
        config = StreamRecordingConfig(
            enabled=True,
            format=RecordingFormat.JSONL,
            output_dir=temp_dir,
            max_file_size_mb=1,
            compress_output=False,
        )
        return StreamRecorder(config)

    def test_start_recording(self, recorder, temp_dir):
        """Test starting a recording session."""
        filepath = recorder.start_recording("test_session", {"test": "metadata"})

        assert filepath.startswith(temp_dir)
        assert "test_session" in filepath
        assert Path(filepath).exists()
        assert "test_session" in recorder.get_active_recordings()

    def test_record_message(self, recorder):
        """Test recording a message."""
        recorder.start_recording("test_session")

        message = {"type": "test", "data": "hello"}
        recorder.record_message("test_session", message)

        session = recorder.recording_sessions["test_session"]
        assert session["message_count"] == 1

    def test_stop_recording(self, recorder, temp_dir):
        """Test stopping a recording session."""
        recorder.start_recording("test_session")

        # Record some messages
        for i in range(10):
            recorder.record_message("test_session", {"count": i})

        stats = recorder.stop_recording("test_session")

        assert stats is not None
        assert stats["message_count"] == 10
        assert "test_session" not in recorder.get_active_recordings()

    def test_jsonl_format(self, recorder, temp_dir):
        """Test JSONL recording format."""
        filepath = recorder.start_recording("jsonl_test")

        messages = [
            {"type": "msg1", "value": 1},
            {"type": "msg2", "value": 2},
            {"type": "msg3", "value": 3},
        ]

        for msg in messages:
            recorder.record_message("jsonl_test", msg)

        recorder.stop_recording("jsonl_test")

        # Verify file content
        with open(filepath, "r") as f:
            lines = f.readlines()
            assert len(lines) == 3
            for i, line in enumerate(lines):
                data = json.loads(line)
                assert data["value"] == i + 1

    def test_compressed_recording(self, temp_dir):
        """Test compressed recording output."""
        config = StreamRecordingConfig(
            enabled=True,
            format=RecordingFormat.JSONL,
            output_dir=temp_dir,
            compress_output=True,
        )
        recorder = StreamRecorder(config)

        filepath = recorder.start_recording("compressed_test")
        assert filepath.endswith(".gz")

        # Record messages
        for i in range(10):
            recorder.record_message("compressed_test", {"count": i})

        recorder.stop_recording("compressed_test")

        # Verify compressed file can be read
        with gzip.open(filepath, "rt") as f:
            lines = f.readlines()
            assert len(lines) == 10

    def test_max_file_size(self, temp_dir):
        """Test maximum file size limit."""
        config = StreamRecordingConfig(
            enabled=True,
            output_dir=temp_dir,
            max_file_size_mb=0.001,  # 1KB limit
            compress_output=False,
        )
        recorder = StreamRecorder(config)

        filepath = recorder.start_recording("size_test")

        # Record large messages until limit is reached
        large_message = {"data": "x" * 1000}

        for i in range(100):
            if "size_test" not in recorder.get_active_recordings():
                break
            recorder.record_message("size_test", large_message)

        # Recording should have stopped due to size limit
        assert "size_test" not in recorder.get_active_recordings()


class TestMessageCompressor:
    """Test message compression."""

    def test_gzip_compression(self):
        """Test GZIP compression."""
        original = "Hello World" * 100
        compressed = MessageCompressor.compress(original, CompressionType.GZIP)

        assert len(compressed) < len(original.encode("utf-8"))
        assert isinstance(compressed, bytes)

    def test_zlib_compression(self):
        """Test ZLIB compression."""
        original = "Hello World" * 100
        compressed = MessageCompressor.compress(original, CompressionType.ZLIB)

        assert len(compressed) < len(original.encode("utf-8"))
        assert isinstance(compressed, bytes)

    def test_no_compression(self):
        """Test no compression."""
        original = "Hello World"
        compressed = MessageCompressor.compress(original, CompressionType.NONE)

        assert compressed == original.encode("utf-8")

    def test_gzip_decompression(self):
        """Test GZIP decompression."""
        original = "Hello World" * 100
        compressed = MessageCompressor.compress(original, CompressionType.GZIP)
        decompressed = MessageCompressor.decompress(compressed, CompressionType.GZIP)

        assert decompressed == original

    def test_zlib_decompression(self):
        """Test ZLIB decompression."""
        original = "Hello World" * 100
        compressed = MessageCompressor.compress(original, CompressionType.ZLIB)
        decompressed = MessageCompressor.decompress(compressed, CompressionType.ZLIB)

        assert decompressed == original

    def test_compression_ratio(self):
        """Test compression ratio calculation."""
        original = "Hello World" * 100
        compressed = MessageCompressor.compress(original, CompressionType.GZIP)
        ratio = MessageCompressor.calculate_compression_ratio(original, compressed)

        assert ratio > 1.0  # Should have some compression


class TestPriorityQueue:
    """Test priority queue."""

    def test_priority_order(self):
        """Test messages are retrieved in priority order."""
        queue = PriorityQueue(max_size=100)

        # Add messages with different priorities
        queue.put({"msg": "low"}, MessagePriority.LOW)
        queue.put({"msg": "normal"}, MessagePriority.NORMAL)
        queue.put({"msg": "high"}, MessagePriority.HIGH)
        queue.put({"msg": "critical"}, MessagePriority.CRITICAL)

        # Retrieve in priority order
        msg1 = queue.get()
        assert msg1.data["msg"] == "critical"

        msg2 = queue.get()
        assert msg2.data["msg"] == "high"

        msg3 = queue.get()
        assert msg3.data["msg"] == "normal"

        msg4 = queue.get()
        assert msg4.data["msg"] == "low"

    def test_queue_full(self):
        """Test queue full behavior."""
        queue = PriorityQueue(max_size=3)

        # Fill queue
        assert queue.put({"msg": 1}, MessagePriority.NORMAL)
        assert queue.put({"msg": 2}, MessagePriority.NORMAL)
        assert queue.put({"msg": 3}, MessagePriority.NORMAL)

        # Try to add when full
        assert not queue.put({"msg": 4}, MessagePriority.NORMAL)
        assert queue.is_full()

    def test_clear_low_priority(self):
        """Test clearing low priority messages."""
        queue = PriorityQueue(max_size=100)

        # Add messages with different priorities
        queue.put({"msg": "low1"}, MessagePriority.LOW)
        queue.put({"msg": "low2"}, MessagePriority.LOW)
        queue.put({"msg": "normal"}, MessagePriority.NORMAL)
        queue.put({"msg": "high"}, MessagePriority.HIGH)

        # Clear low priority
        cleared = queue.clear_low_priority()

        assert cleared == 2
        assert queue.size() == 2

    def test_size_by_priority(self):
        """Test getting size by priority."""
        queue = PriorityQueue(max_size=100)

        queue.put({"msg": "low1"}, MessagePriority.LOW)
        queue.put({"msg": "low2"}, MessagePriority.LOW)
        queue.put({"msg": "normal"}, MessagePriority.NORMAL)
        queue.put({"msg": "high"}, MessagePriority.HIGH)

        assert queue.size_by_priority(MessagePriority.LOW) == 2
        assert queue.size_by_priority(MessagePriority.NORMAL) == 1
        assert queue.size_by_priority(MessagePriority.HIGH) == 1
        assert queue.size_by_priority(MessagePriority.CRITICAL) == 0


class TestRateLimiter:
    """Test rate limiter."""

    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test rate limiting functionality."""
        limiter = RateLimiter(max_rate=10, burst_size=5)

        # Acquire tokens up to burst size
        for _ in range(5):
            assert await limiter.acquire()

        # Next acquisition should fail (no tokens left)
        assert not await limiter.acquire()

        # Wait for tokens to refill
        await asyncio.sleep(0.2)

        # Should be able to acquire again
        assert await limiter.acquire()

    @pytest.mark.asyncio
    async def test_burst_size(self):
        """Test burst size limit."""
        limiter = RateLimiter(max_rate=100, burst_size=10)

        # Should be able to acquire burst_size tokens immediately
        for _ in range(10):
            assert await limiter.acquire()

        # 11th should fail
        assert not await limiter.acquire()


class TestBackpressureHandler:
    """Test backpressure handler."""

    @pytest.mark.asyncio
    async def test_queue_message(self):
        """Test queuing messages."""
        config = BackpressureConfig(
            enabled=True,
            max_queue_size=10,
            rate_limit_enabled=False,
        )
        handler = BackpressureHandler(config)

        # Queue some messages
        for i in range(5):
            assert await handler.queue_message({"count": i}, MessagePriority.NORMAL)

        stats = handler.get_stats()
        assert stats["messages_queued"] == 5
        assert stats["queue_size"] == 5

    @pytest.mark.asyncio
    async def test_queue_overflow(self):
        """Test queue overflow behavior."""
        config = BackpressureConfig(
            enabled=True,
            max_queue_size=3,
            drop_low_priority=False,
        )
        handler = BackpressureHandler(config)

        # Fill queue
        for i in range(3):
            await handler.queue_message({"count": i}, MessagePriority.NORMAL)

        # Try to add when full
        result = await handler.queue_message({"count": 4}, MessagePriority.NORMAL)
        assert not result

        stats = handler.get_stats()
        assert stats["messages_dropped"] == 1
        assert stats["queue_overflows"] == 1

    @pytest.mark.asyncio
    async def test_drop_low_priority(self):
        """Test dropping low priority messages."""
        config = BackpressureConfig(
            enabled=True,
            max_queue_size=5,
            drop_low_priority=True,
        )
        handler = BackpressureHandler(config)

        # Add low priority messages
        for i in range(3):
            await handler.queue_message({"count": i}, MessagePriority.LOW)

        # Add normal priority messages
        for i in range(2):
            await handler.queue_message({"count": i}, MessagePriority.NORMAL)

        # Queue is full, add high priority (should drop low priority)
        result = await handler.queue_message({"count": 99}, MessagePriority.HIGH)
        assert result

        stats = handler.get_stats()
        assert stats["messages_dropped"] == 3  # Low priority messages dropped

    @pytest.mark.asyncio
    async def test_get_next_message(self):
        """Test getting next message."""
        config = BackpressureConfig(
            enabled=True,
            rate_limit_enabled=False,
        )
        handler = BackpressureHandler(config)

        # Queue messages
        await handler.queue_message({"msg": "first"}, MessagePriority.NORMAL)
        await handler.queue_message({"msg": "second"}, MessagePriority.HIGH)

        # Get messages (should be in priority order)
        msg1 = await handler.get_next_message()
        assert msg1.data["msg"] == "second"  # High priority first

        msg2 = await handler.get_next_message()
        assert msg2.data["msg"] == "first"


class TestEnhancedStreamManager:
    """Test enhanced stream manager."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def manager(self, temp_dir):
        """Create enhanced stream manager."""
        recording_config = StreamRecordingConfig(
            enabled=True,
            output_dir=temp_dir,
            compress_output=False,
        )
        backpressure_config = BackpressureConfig(
            enabled=True,
            max_queue_size=100,
            rate_limit_enabled=False,
        )
        return EnhancedStreamManager(recording_config, backpressure_config)

    @pytest.mark.asyncio
    async def test_connect(self, manager):
        """Test WebSocket connection."""
        mock_websocket = AsyncMock()

        await manager.connect(mock_websocket, "test_client")

        assert "test_client" in manager.active_connections
        assert "test_client" in manager.backpressure_handlers
        assert "test_client" in manager.send_tasks
        mock_websocket.accept.assert_called_once()

    def test_disconnect(self, manager):
        """Test WebSocket disconnection."""
        mock_websocket = AsyncMock()

        # Connect first
        asyncio.run(manager.connect(mock_websocket, "test_client"))

        # Disconnect
        manager.disconnect("test_client")

        assert "test_client" not in manager.active_connections
        assert "test_client" not in manager.backpressure_handlers

    @pytest.mark.asyncio
    async def test_send_to_client(self, manager):
        """Test sending message to client."""
        mock_websocket = AsyncMock()
        await manager.connect(mock_websocket, "test_client")

        # Send message
        result = await manager.send_to_client(
            "test_client", {"type": "test", "data": "hello"}, MessagePriority.NORMAL
        )

        assert result is True

        # Check message was queued
        stats = manager.get_backpressure_stats("test_client")
        assert stats["messages_queued"] > 0

    @pytest.mark.asyncio
    async def test_broadcast(self, manager):
        """Test broadcasting to all clients."""
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        await manager.connect(mock_ws1, "client1")
        await manager.connect(mock_ws2, "client2")

        # Broadcast message
        await manager.broadcast(
            {"type": "broadcast", "data": "hello all"}, MessagePriority.NORMAL
        )

        # Both clients should have messages queued
        stats1 = manager.get_backpressure_stats("client1")
        stats2 = manager.get_backpressure_stats("client2")

        assert stats1["messages_queued"] > 0
        assert stats2["messages_queued"] > 0

    def test_recording_integration(self, manager):
        """Test recording integration."""
        # Start recording
        filepath = manager.start_recording("test_recording")
        assert filepath is not None

        # Check active recordings
        recordings = manager.get_active_recordings()
        assert "test_recording" in recordings

        # Stop recording
        stats = manager.stop_recording("test_recording")
        assert stats is not None

    def test_get_global_stats(self, manager):
        """Test getting global statistics."""
        stats = manager.get_global_stats()

        assert "total_connections" in stats
        assert "total_messages_sent" in stats
        assert "active_connections" in stats
        assert "active_recordings" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
