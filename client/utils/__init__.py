"""Utility functions for LabLink GUI client."""

from .websocket_manager import WebSocketManager, StreamType, MessageType
from .data_buffer import CircularBuffer, SlidingWindowBuffer

try:
    from .settings import SettingsManager, get_settings
    SETTINGS_AVAILABLE = True
except ImportError:
    SETTINGS_AVAILABLE = False
    SettingsManager = None
    get_settings = None

__all__ = [
    "WebSocketManager",
    "StreamType",
    "MessageType",
    "CircularBuffer",
    "SlidingWindowBuffer",
    "SettingsManager",
    "get_settings",
]
