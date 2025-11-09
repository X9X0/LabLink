"""Unit tests for WebSocket manager."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock


try:
    from client.utils.websocket_manager import WebSocketManager, StreamConfig
    WS_AVAILABLE = True
except ImportError:
    WS_AVAILABLE = False


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.skipif(not WS_AVAILABLE, reason="WebSocket dependencies not available")
class TestWebSocketManager:
    """Test WebSocketManager class."""

    @pytest.fixture
    def manager(self):
        """Create WebSocket manager instance."""
        return WebSocketManager(host="localhost", port=8001)

    def test_initialization(self, manager):
        """Test manager initializes correctly."""
        assert manager.host == "localhost"
        assert manager.port == 8001
        assert manager.url == "ws://localhost:8001/ws"
        assert manager.connected is False
        assert len(manager._active_streams) == 0

    @pytest.mark.asyncio
    async def test_connect_success(self, manager):
        """Test successful connection."""
        with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.closed = False
            mock_connect.return_value = mock_ws

            result = await manager.connect()

            assert result is True
            assert manager.connected is True
            mock_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self, manager):
        """Test connection failure."""
        with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_connect.side_effect = Exception("Connection failed")

            result = await manager.connect()

            assert result is False
            assert manager.connected is False

    @pytest.mark.asyncio
    async def test_disconnect(self, manager):
        """Test disconnection."""
        # Mock connection
        manager._connection = AsyncMock()
        manager._connection.close = AsyncMock()
        manager.connected = True

        await manager.disconnect()

        assert manager.connected is False
        manager._connection.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message(self, manager):
        """Test sending message."""
        # Mock connection
        manager._connection = AsyncMock()
        manager._connection.send = AsyncMock()
        manager.connected = True

        message = {"type": "test", "data": "hello"}
        await manager._send_message(message)

        manager._connection.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_not_connected(self, manager):
        """Test sending message when not connected."""
        message = {"type": "test"}

        with pytest.raises(RuntimeError):
            await manager._send_message(message)

    @pytest.mark.asyncio
    async def test_start_equipment_stream(self, manager):
        """Test starting equipment stream."""
        manager._connection = AsyncMock()
        manager._connection.send = AsyncMock()
        manager.connected = True

        await manager.start_equipment_stream(
            equipment_id="test_001",
            stream_type="readings",
            interval_ms=100
        )

        # Verify stream registered
        stream_key = "test_001_readings"
        assert stream_key in manager._active_streams

        stream_config = manager._active_streams[stream_key]
        assert stream_config.equipment_id == "test_001"
        assert stream_config.stream_type == "readings"
        assert stream_config.interval_ms == 100

    @pytest.mark.asyncio
    async def test_stop_equipment_stream(self, manager):
        """Test stopping equipment stream."""
        manager._connection = AsyncMock()
        manager._connection.send = AsyncMock()
        manager.connected = True

        # Start stream first
        await manager.start_equipment_stream(
            equipment_id="test_001",
            stream_type="readings",
            interval_ms=100
        )

        # Stop stream
        await manager.stop_equipment_stream(
            equipment_id="test_001",
            stream_type="readings"
        )

        # Verify stream removed
        stream_key = "test_001_readings"
        assert stream_key not in manager._active_streams

    def test_register_message_handler(self, manager):
        """Test registering message handler."""
        handler = Mock()

        manager.register_message_handler("test_type", handler)

        assert "test_type" in manager._message_handlers
        assert handler in manager._message_handlers["test_type"]

    def test_unregister_message_handler(self, manager):
        """Test unregistering message handler."""
        handler = Mock()

        manager.register_message_handler("test_type", handler)
        manager.unregister_message_handler("test_type", handler)

        assert handler not in manager._message_handlers.get("test_type", [])

    def test_register_stream_data_handler(self, manager):
        """Test registering stream data handler."""
        handler = Mock()

        manager.register_stream_data_handler(handler)

        assert handler in manager._stream_data_handlers

    def test_unregister_stream_data_handler(self, manager):
        """Test unregistering stream data handler."""
        handler = Mock()

        manager.register_stream_data_handler(handler)
        manager.unregister_stream_data_handler(handler)

        assert handler not in manager._stream_data_handlers

    @pytest.mark.asyncio
    async def test_message_routing(self, manager):
        """Test message routing to handlers."""
        handler1 = Mock()
        handler2 = Mock()

        manager.register_message_handler("test_type", handler1)
        manager.register_message_handler("other_type", handler2)

        message = {"type": "test_type", "data": "hello"}

        await manager._route_message(message)

        handler1.assert_called_once_with(message)
        handler2.assert_not_called()

    @pytest.mark.asyncio
    async def test_stream_data_routing(self, manager):
        """Test stream data routing."""
        handler = Mock()
        manager.register_stream_data_handler(handler)

        message = {
            "type": "stream_data",
            "equipment_id": "test_001",
            "stream_type": "readings",
            "data": {"value": 1.5}
        }

        await manager._route_message(message)

        handler.assert_called_once_with(message)

    def test_get_statistics(self, manager):
        """Test getting statistics."""
        stats = manager.get_statistics()

        assert "connected" in stats
        assert "active_streams" in stats
        assert "message_handlers" in stats
        assert "stream_data_handlers" in stats

        assert stats["connected"] == manager.connected
        assert stats["active_streams"] == 0


@pytest.mark.unit
class TestStreamConfig:
    """Test StreamConfig class."""

    def test_initialization(self):
        """Test StreamConfig initializes correctly."""
        config = StreamConfig(
            equipment_id="test_001",
            stream_type="readings",
            interval_ms=100,
            parameters={"channel": 1}
        )

        assert config.equipment_id == "test_001"
        assert config.stream_type == "readings"
        assert config.interval_ms == 100
        assert config.parameters == {"channel": 1}

    def test_default_parameters(self):
        """Test StreamConfig with default parameters."""
        config = StreamConfig(
            equipment_id="test_001",
            stream_type="readings",
            interval_ms=100
        )

        assert config.parameters == {}
