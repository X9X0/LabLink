"""Equipment discovery system data models."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DiscoveryMethod(str, Enum):
    """Method used to discover equipment."""

    MDNS = "mdns"  # mDNS/Bonjour discovery
    VISA = "visa"  # VISA resource discovery
    USB = "usb"  # USB device discovery
    MANUAL = "manual"  # Manually added
    CACHE = "cache"  # From connection cache


class DeviceType(str, Enum):
    """Type of discovered device."""

    OSCILLOSCOPE = "oscilloscope"
    POWER_SUPPLY = "power_supply"
    ELECTRONIC_LOAD = "electronic_load"
    MULTIMETER = "multimeter"
    FUNCTION_GENERATOR = "function_generator"
    SPECTRUM_ANALYZER = "spectrum_analyzer"
    UNKNOWN = "unknown"


class ConnectionStatus(str, Enum):
    """Status of device connection."""

    AVAILABLE = "available"  # Device is available
    CONNECTED = "connected"  # Currently connected
    OFFLINE = "offline"  # Device not responding
    ERROR = "error"  # Connection error


class DiscoveredDevice(BaseModel):
    """Information about a discovered equipment."""

    # Identity
    device_id: str = Field(..., description="Unique device identifier")
    resource_name: str = Field(
        ..., description="VISA resource name (e.g., TCPIP::192.168.1.100::INSTR)"
    )

    # Device info
    manufacturer: Optional[str] = Field(None, description="Manufacturer name")
    model: Optional[str] = Field(None, description="Model number")
    serial_number: Optional[str] = Field(None, description="Serial number")
    firmware_version: Optional[str] = Field(None, description="Firmware version")
    device_type: DeviceType = Field(DeviceType.UNKNOWN, description="Type of device")

    # Network info (for TCPIP devices)
    ip_address: Optional[str] = Field(None, description="IP address")
    hostname: Optional[str] = Field(None, description="Hostname")
    mac_address: Optional[str] = Field(None, description="MAC address")
    port: Optional[int] = Field(None, description="TCP/IP port")

    # Discovery info
    discovery_method: DiscoveryMethod = Field(
        ..., description="How device was discovered"
    )
    discovered_at: datetime = Field(
        default_factory=datetime.now, description="When device was discovered"
    )
    last_seen: datetime = Field(
        default_factory=datetime.now, description="Last time device was seen"
    )

    # Connection status
    status: ConnectionStatus = Field(
        ConnectionStatus.AVAILABLE, description="Connection status"
    )
    is_connected: bool = Field(False, description="Currently connected to server")

    # User configuration
    friendly_name: Optional[str] = Field(
        None, description="User-assigned friendly name"
    )
    alias: Optional[str] = Field(None, description="Short alias for device")
    location: Optional[str] = Field(None, description="Physical location")
    tags: List[str] = Field(default_factory=list, description="User tags")

    # Metadata
    capabilities: List[str] = Field(
        default_factory=list, description="Device capabilities"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    # Connection quality
    signal_strength: Optional[int] = Field(
        None, ge=0, le=100, description="Signal strength (0-100)"
    )
    response_time_ms: Optional[float] = Field(
        None, description="Average response time in ms"
    )

    # Smart recommendations
    confidence_score: float = Field(
        0.0, ge=0.0, le=1.0, description="Confidence in device identification"
    )
    recommended: bool = Field(False, description="Recommended for connection")


class ConnectionHistoryEntry(BaseModel):
    """Record of a device connection event."""

    # Identity
    entry_id: Optional[int] = Field(None, description="Entry ID")
    device_id: str = Field(..., description="Device identifier")
    resource_name: str = Field(..., description="VISA resource name")

    # Event info
    event_type: str = Field(
        ..., description="Event type (connected, disconnected, failed)"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Event timestamp"
    )

    # Connection details
    success: bool = Field(..., description="Connection successful")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    connection_time_ms: Optional[float] = Field(
        None, description="Time to establish connection"
    )

    # Device info at time of connection
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    firmware_version: Optional[str] = None

    # User/session
    user_id: Optional[str] = Field(None, description="User who initiated connection")
    session_id: Optional[str] = Field(None, description="Session identifier")

    # Context
    discovery_method: Optional[DiscoveryMethod] = None
    ip_address: Optional[str] = None


class LastKnownGood(BaseModel):
    """Last known good connection configuration."""

    device_id: str = Field(..., description="Device identifier")
    resource_name: str = Field(..., description="VISA resource name that worked")

    # Connection details
    last_successful: datetime = Field(
        ..., description="Last successful connection time"
    )
    connection_count: int = Field(0, description="Number of successful connections")

    # Device info
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None

    # Network info (if applicable)
    ip_address: Optional[str] = None
    hostname: Optional[str] = None

    # Performance
    avg_response_time_ms: float = Field(0.0, description="Average response time")
    last_error: Optional[str] = Field(None, description="Last error encountered")


class SmartRecommendation(BaseModel):
    """Smart connection recommendation."""

    device_id: str = Field(..., description="Device identifier")
    resource_name: str = Field(..., description="Recommended resource name")

    # Recommendation basis
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0-1)")
    reason: str = Field(..., description="Why this is recommended")

    # Supporting evidence
    last_successful: Optional[datetime] = None
    success_rate: Optional[float] = None
    response_time_ms: Optional[float] = None

    # Alternative options
    alternatives: List[str] = Field(
        default_factory=list, description="Alternative resource names"
    )


class DiscoveryConfig(BaseModel):
    """Configuration for equipment discovery."""

    # Enable/disable discovery methods
    enable_mdns: bool = Field(True, description="Enable mDNS/Bonjour discovery")
    enable_visa_scan: bool = Field(True, description="Enable VISA resource scanning")
    enable_usb_scan: bool = Field(True, description="Enable USB device scanning")
    enable_auto_discovery: bool = Field(
        True, description="Enable automatic discovery on startup"
    )

    # Discovery intervals
    mdns_scan_interval_sec: int = Field(
        60, ge=10, description="mDNS scan interval (seconds)"
    )
    visa_scan_interval_sec: int = Field(
        30, ge=10, description="VISA scan interval (seconds)"
    )

    # Discovery scope
    scan_tcpip: bool = Field(True, description="Scan TCPIP resources")
    scan_usb: bool = Field(True, description="Scan USB resources")
    scan_gpib: bool = Field(False, description="Scan GPIB resources")
    scan_serial: bool = Field(True, description="Scan serial resources")  # Enable by default for USB-to-serial devices

    # Network settings (for mDNS)
    mdns_service_type: str = Field(
        "_scpi._tcp.local.", description="mDNS service type to search for"
    )
    mdns_timeout_sec: float = Field(5.0, ge=1.0, description="mDNS query timeout")

    # Connection testing
    test_connections: bool = Field(True, description="Test discovered devices")
    connection_timeout_ms: int = Field(
        5000, ge=1000, description="Connection test timeout"
    )

    # History settings
    enable_history: bool = Field(True, description="Track connection history")
    history_retention_days: int = Field(90, ge=1, description="Days to keep history")
    max_history_entries: int = Field(
        1000, ge=100, description="Maximum history entries"
    )

    # Smart recommendations
    enable_recommendations: bool = Field(
        True, description="Enable smart recommendations"
    )
    min_confidence_threshold: float = Field(
        0.6, ge=0.0, le=1.0, description="Minimum confidence for recommendations"
    )

    # Cache settings
    cache_discovered_devices: bool = Field(True, description="Cache discovered devices")
    cache_ttl_sec: int = Field(300, ge=60, description="Cache TTL (seconds)")

    # Device identification
    query_idn: bool = Field(True, description="Query *IDN? for device identification")
    parse_idn: bool = Field(
        True, description="Parse *IDN? response for manufacturer/model"
    )


class DiscoveryStatus(BaseModel):
    """Current status of discovery system."""

    # Discovery state
    is_running: bool = Field(False, description="Discovery is active")
    last_scan: Optional[datetime] = Field(None, description="Last scan time")
    next_scan: Optional[datetime] = Field(None, description="Next scheduled scan")

    # Statistics
    total_devices: int = Field(0, description="Total devices discovered")
    available_devices: int = Field(0, description="Available devices")
    connected_devices: int = Field(0, description="Connected devices")
    offline_devices: int = Field(0, description="Offline devices")

    # By method
    mdns_devices: int = Field(0, description="Devices found via mDNS")
    visa_devices: int = Field(0, description="Devices found via VISA")
    usb_devices: int = Field(0, description="Devices found via USB")
    manual_devices: int = Field(0, description="Manually added devices")

    # Performance
    last_scan_duration_ms: Optional[float] = None
    avg_scan_duration_ms: Optional[float] = None

    # Errors
    errors: List[str] = Field(default_factory=list, description="Recent errors")


class DiscoveryScanRequest(BaseModel):
    """Request to perform discovery scan."""

    methods: Optional[List[DiscoveryMethod]] = Field(
        None, description="Methods to use (all if None)"
    )
    test_connections: bool = Field(True, description="Test discovered devices")
    force_refresh: bool = Field(False, description="Ignore cache")


class DiscoveryScanResult(BaseModel):
    """Result of a discovery scan."""

    scan_id: str = Field(..., description="Scan identifier")
    started_at: datetime = Field(..., description="Scan start time")
    completed_at: datetime = Field(..., description="Scan completion time")
    duration_ms: float = Field(..., description="Scan duration")

    # Devices found
    devices_found: int = Field(0, description="Number of devices found")
    new_devices: int = Field(0, description="New devices")
    updated_devices: int = Field(0, description="Updated devices")

    # By method
    mdns_count: int = Field(0, description="Devices via mDNS")
    visa_count: int = Field(0, description="Devices via VISA")
    usb_count: int = Field(0, description="Devices via USB")

    # Devices
    devices: List[DiscoveredDevice] = Field(
        default_factory=list, description="Discovered devices"
    )

    # Errors
    errors: List[str] = Field(default_factory=list, description="Errors encountered")
    success: bool = Field(True, description="Scan successful")


class DeviceAlias(BaseModel):
    """User-assigned alias for a device."""

    device_id: str = Field(..., description="Device identifier")
    alias: str = Field(..., description="Short alias (e.g., 'scope1', 'ps-bench')")
    friendly_name: Optional[str] = Field(None, description="Full friendly name")
    location: Optional[str] = Field(None, description="Physical location")
    tags: List[str] = Field(default_factory=list, description="Tags")
    notes: Optional[str] = Field(None, description="User notes")
    created_at: datetime = Field(
        default_factory=datetime.now, description="Created timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.now, description="Updated timestamp"
    )


class ConnectionStatistics(BaseModel):
    """Connection statistics for a device."""

    device_id: str = Field(..., description="Device identifier")

    # Connection counts
    total_connections: int = Field(0, description="Total connection attempts")
    successful_connections: int = Field(0, description="Successful connections")
    failed_connections: int = Field(0, description="Failed connections")

    # Success rate
    success_rate: float = Field(0.0, ge=0.0, le=1.0, description="Success rate (0-1)")

    # Timing
    avg_connection_time_ms: float = Field(0.0, description="Average connection time")
    min_connection_time_ms: Optional[float] = None
    max_connection_time_ms: Optional[float] = None

    # First and last
    first_connection: Optional[datetime] = None
    last_connection: Optional[datetime] = None
    last_successful: Optional[datetime] = None
    last_failed: Optional[datetime] = None

    # Recent performance
    recent_failures: int = Field(0, description="Recent consecutive failures")
    last_error: Optional[str] = None
