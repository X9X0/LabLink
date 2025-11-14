"""Utility functions for LabLink GUI client."""

from .data_buffer import CircularBuffer, SlidingWindowBuffer
from .websocket_manager import MessageType, StreamType, WebSocketManager

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
