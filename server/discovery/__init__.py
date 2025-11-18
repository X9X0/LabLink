"""Equipment discovery system for LabLink server."""

from .history import ConnectionHistoryTracker
from .manager import (DiscoveryManager, get_discovery_manager,
                      initialize_discovery_manager)
from .mdns_scanner import MDNSScanner
from .models import (ConnectionHistoryEntry, ConnectionStatistics,
                     ConnectionStatus, DeviceAlias, DeviceType,
                     DiscoveredDevice, DiscoveryConfig, DiscoveryMethod,
                     DiscoveryScanRequest, DiscoveryScanResult,
                     DiscoveryStatus, LastKnownGood, SmartRecommendation)
from .pi_discovery import DiscoveredPi, PiDiscovery, pi_discovery
from .visa_scanner import VISAScanner

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
    "DiscoveredPi",
    # Manager
    "DiscoveryManager",
    "initialize_discovery_manager",
    "get_discovery_manager",
    # Scanners
    "VISAScanner",
    "MDNSScanner",
    "ConnectionHistoryTracker",
    "PiDiscovery",
    "pi_discovery",
]
