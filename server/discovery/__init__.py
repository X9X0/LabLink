"""Equipment discovery system for LabLink server."""

from .models import (
    DiscoveryMethod,
    DeviceType,
    ConnectionStatus,
    DiscoveredDevice,
    ConnectionHistoryEntry,
    LastKnownGood,
    SmartRecommendation,
    DeviceAlias,
    ConnectionStatistics,
    DiscoveryConfig,
    DiscoveryStatus,
    DiscoveryScanRequest,
    DiscoveryScanResult,
)
from .manager import DiscoveryManager, initialize_discovery_manager, get_discovery_manager
from .visa_scanner import VISAScanner
from .mdns_scanner import MDNSScanner
from .history import ConnectionHistoryTracker

__all__ = [
    # Enums
    "DiscoveryMethod",
    "DeviceType",
    "ConnectionStatus",
    # Models
    "DiscoveredDevice",
    "ConnectionHistoryEntry",
    "LastKnownGood",
    "SmartRecommendation",
    "DeviceAlias",
    "ConnectionStatistics",
    "DiscoveryConfig",
    "DiscoveryStatus",
    "DiscoveryScanRequest",
    "DiscoveryScanResult",
    # Manager
    "DiscoveryManager",
    "initialize_discovery_manager",
    "get_discovery_manager",
    # Scanners
    "VISAScanner",
    "MDNSScanner",
    "ConnectionHistoryTracker",
]
