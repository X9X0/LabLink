"""API endpoints for Equipment Discovery system."""

from typing import List, Optional

from discovery import (ConnectionHistoryEntry, ConnectionStatistics,
                       DeviceAlias, DiscoveredDevice, DiscoveryScanRequest,
                       DiscoveryScanResult, DiscoveryStatus, LastKnownGood,
                       SmartRecommendation, get_discovery_manager)
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


# === Discovery Scanning ===


@router.post("/scan", response_model=DiscoveryScanResult)
async def scan_devices(request: Optional[DiscoveryScanRequest] = None):
    """Scan for equipment devices.

    Performs discovery scan using enabled methods (mDNS, VISA, USB).
    Results are cached based on configuration TTL.

    **Request Body** (optional):
    - methods: List of discovery methods to use (defaults to all enabled)
    - test_connections: Test discovered devices (default: true)
    - force_refresh: Ignore cache and force new scan (default: false)

    **Returns:**
    - Scan result with discovered devices and statistics

    **Example:**
    ```json
    {
      "methods": ["mdns", "visa"],
      "test_connections": true,
      "force_refresh": false
    }
    ```
    """
    try:
        manager = get_discovery_manager()
        result = await manager.scan(request)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=DiscoveryStatus)
async def get_discovery_status():
    """Get discovery system status.

    Returns current state of discovery system including scan statistics,
    device counts, and scheduling information.

    **Returns:**
    - is_running: Discovery is active
    - last_scan/next_scan: Scan timing
    - total_devices/available_devices/connected_devices: Device counts
    - mdns_devices/visa_devices/usb_devices: Counts by discovery method
    - last_scan_duration_ms/avg_scan_duration_ms: Performance metrics
    """
    try:
        manager = get_discovery_manager()
        status = manager.get_status()
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Device Management ===


@router.get("/devices", response_model=List[DiscoveredDevice])
async def list_devices(
    device_type: Optional[str] = Query(None, description="Filter by device type"),
    status: Optional[str] = Query(None, description="Filter by status"),
):
    """List discovered devices.

    Returns all discovered devices with optional filtering by type and status.

    **Query Parameters:**
    - device_type: Filter by type (oscilloscope, power_supply, electronic_load, etc.)
    - status: Filter by status (available, connected, offline, error)

    **Returns:**
    - List of discovered devices sorted by last seen (most recent first)

    **Example Response:**
    ```json
    [
      {
        "device_id": "tcpip_192_168_1_100_instr",
        "resource_name": "TCPIP::192.168.1.100::INSTR",
        "manufacturer": "Rigol Technologies",
        "model": "MSO2072A",
        "device_type": "oscilloscope",
        "discovery_method": "mdns",
        "status": "available",
        "confidence_score": 0.95,
        "recommended": true
      }
    ]
    ```
    """
    try:
        manager = get_discovery_manager()
        devices = manager.get_devices(device_type=device_type, status=status)
        return devices
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/devices/{device_id}", response_model=DiscoveredDevice)
async def get_device(device_id: str):
    """Get device details by ID.

    **Path Parameters:**
    - device_id: Device identifier

    **Returns:**
    - Complete device information

    **Raises:**
    - 404: Device not found
    """
    try:
        manager = get_discovery_manager()
        device = manager.get_device(device_id)

        if device is None:
            raise HTTPException(status_code=404, detail="Device not found")

        return device
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/devices/by-alias/{alias}", response_model=DiscoveredDevice)
async def get_device_by_alias(alias: str):
    """Get device by alias.

    **Path Parameters:**
    - alias: Device alias (e.g., 'scope1', 'ps-bench')

    **Returns:**
    - Device with matching alias

    **Raises:**
    - 404: Device not found
    """
    try:
        manager = get_discovery_manager()
        device = manager.get_device_by_alias(alias)

        if device is None:
            raise HTTPException(status_code=404, detail="Device not found")

        return device
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Device Aliases and Metadata ===


@router.post("/devices/{device_id}/alias")
async def set_device_alias(device_id: str, alias_data: DeviceAlias):
    """Set device alias and metadata.

    Assigns friendly name, alias, location, and tags to a device for easier identification.

    **Path Parameters:**
    - device_id: Device identifier

    **Request Body:**
    - alias: Short alias (e.g., 'scope1', 'ps-bench')
    - friendly_name: Full friendly name
    - location: Physical location
    - tags: List of tags
    - notes: User notes

    **Example:**
    ```json
    {
      "device_id": "tcpip_192_168_1_100_instr",
      "alias": "scope1",
      "friendly_name": "Main Bench Oscilloscope",
      "location": "Lab A - Bench 1",
      "tags": ["calibrated", "primary"],
      "notes": "Use for precision measurements"
    }
    ```

    **Returns:**
    - Success message

    **Raises:**
    - 404: Device not found
    """
    try:
        manager = get_discovery_manager()
        success = manager.set_alias(device_id, alias_data)

        if not success:
            raise HTTPException(status_code=404, detail="Device not found")

        return {"message": "Alias set successfully", "device_id": device_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Smart Recommendations ===


@router.get("/recommendations", response_model=List[SmartRecommendation])
async def get_recommendations(
    device_type: Optional[str] = Query(None, description="Filter by device type"),
    limit: int = Query(5, ge=1, le=20, description="Maximum recommendations"),
):
    """Get smart connection recommendations.

    Returns recommended devices based on discovery confidence, connection history,
    and success rates.

    **Query Parameters:**
    - device_type: Filter by type
    - limit: Maximum recommendations (1-20, default: 5)

    **Returns:**
    - List of recommendations with confidence scores and reasons

    **Example Response:**
    ```json
    [
      {
        "device_id": "mdns_192_168_1_100_5025",
        "resource_name": "TCPIP::192.168.1.100::INSTR",
        "confidence": 0.95,
        "reason": "Advertised via mDNS; Identified as Rigol MSO2072A; High success rate (98%); Recently seen",
        "last_successful": "2025-11-13T14:30:22",
        "success_rate": 0.98,
        "response_time_ms": 45.2
      }
    ]
    ```
    """
    try:
        manager = get_discovery_manager()
        recommendations = manager.get_recommendations(
            device_type=device_type, limit=limit
        )
        return recommendations
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Connection History ===


@router.get("/history", response_model=List[ConnectionHistoryEntry])
async def get_connection_history(
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum entries"),
):
    """Get connection history.

    Returns historical connection events with filtering options.

    **Query Parameters:**
    - device_id: Filter by device
    - event_type: Filter by type (connected, disconnected, failed)
    - limit: Maximum entries (1-1000, default: 100)

    **Returns:**
    - List of connection history entries sorted by timestamp (newest first)

    **Example Response:**
    ```json
    [
      {
        "entry_id": 1234,
        "device_id": "tcpip_192_168_1_100_instr",
        "resource_name": "TCPIP::192.168.1.100::INSTR",
        "event_type": "connected",
        "timestamp": "2025-11-13T14:30:22",
        "success": true,
        "connection_time_ms": 45.2,
        "manufacturer": "Rigol Technologies",
        "model": "MSO2072A"
      }
    ]
    ```
    """
    try:
        manager = get_discovery_manager()
        history = manager.history.get_history(
            device_id=device_id, event_type=event_type, limit=limit
        )
        return history
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{device_id}/statistics", response_model=ConnectionStatistics)
async def get_connection_statistics(device_id: str):
    """Get connection statistics for a device.

    Returns comprehensive statistics including success rate, timing, and recent failures.

    **Path Parameters:**
    - device_id: Device identifier

    **Returns:**
    - Connection statistics

    **Example Response:**
    ```json
    {
      "device_id": "tcpip_192_168_1_100_instr",
      "total_connections": 150,
      "successful_connections": 147,
      "failed_connections": 3,
      "success_rate": 0.98,
      "avg_connection_time_ms": 45.2,
      "min_connection_time_ms": 32.1,
      "max_connection_time_ms": 120.5,
      "first_connection": "2025-10-01T10:00:00",
      "last_connection": "2025-11-13T14:30:22",
      "last_successful": "2025-11-13T14:30:22",
      "recent_failures": 0
    }
    ```

    **Raises:**
    - 404: No statistics available for device
    """
    try:
        manager = get_discovery_manager()
        stats = manager.history.get_statistics(device_id)

        if stats is None:
            raise HTTPException(
                status_code=404, detail="No statistics available for device"
            )

        return stats
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{device_id}/last-known-good", response_model=LastKnownGood)
async def get_last_known_good(device_id: str):
    """Get last known good configuration for a device.

    Returns the last successful connection configuration including resource name,
    timing, and device information.

    **Path Parameters:**
    - device_id: Device identifier

    **Returns:**
    - Last known good configuration

    **Raises:**
    - 404: No last known good configuration found
    """
    try:
        manager = get_discovery_manager()
        lkg = manager.history.get_last_known_good(device_id)

        if lkg is None:
            raise HTTPException(
                status_code=404, detail="No last known good configuration found"
            )

        return lkg
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === System Information ===


@router.get("/info")
async def get_discovery_info():
    """Get discovery system information.

    Returns configuration, capabilities, and feature status.

    **Returns:**
    - Configuration settings
    - Enabled discovery methods
    - Supported device types
    - Feature availability (mDNS, history, recommendations)

    **Example Response:**
    ```json
    {
      "enabled_methods": ["mdns", "visa", "usb"],
      "mdns_available": true,
      "auto_discovery_enabled": true,
      "scan_intervals": {
        "mdns_sec": 60,
        "visa_sec": 30
      },
      "history_enabled": true,
      "history_retention_days": 90,
      "recommendations_enabled": true,
      "cache_enabled": true,
      "cache_ttl_sec": 300,
      "supported_device_types": [
        "oscilloscope",
        "power_supply",
        "electronic_load",
        "multimeter",
        "function_generator",
        "spectrum_analyzer"
      ]
    }
    ```
    """
    try:
        manager = get_discovery_manager()
        config = manager.config

        enabled_methods = []
        if config.enable_mdns:
            enabled_methods.append("mdns")
        if config.enable_visa_scan:
            enabled_methods.append("visa")
        if config.enable_usb_scan:
            enabled_methods.append("usb")

        return {
            "enabled_methods": enabled_methods,
            "mdns_available": manager.mdns_scanner.is_available(),
            "auto_discovery_enabled": config.enable_auto_discovery,
            "scan_intervals": {
                "mdns_sec": config.mdns_scan_interval_sec,
                "visa_sec": config.visa_scan_interval_sec,
            },
            "history_enabled": config.enable_history,
            "history_retention_days": config.history_retention_days,
            "max_history_entries": config.max_history_entries,
            "recommendations_enabled": config.enable_recommendations,
            "min_confidence_threshold": config.min_confidence_threshold,
            "cache_enabled": config.cache_discovered_devices,
            "cache_ttl_sec": config.cache_ttl_sec,
            "test_connections": config.test_connections,
            "connection_timeout_ms": config.connection_timeout_ms,
            "supported_device_types": [
                "oscilloscope",
                "power_supply",
                "electronic_load",
                "multimeter",
                "function_generator",
                "spectrum_analyzer",
                "unknown",
            ],
            "features": {
                "mdns_discovery": "Automatic network device discovery via mDNS/Bonjour",
                "visa_scanning": "Scan TCPIP, USB, GPIB, and Serial VISA resources",
                "connection_history": "Track all connection events with statistics",
                "smart_recommendations": "AI-powered connection recommendations",
                "device_aliases": "User-friendly names and metadata for devices",
                "last_known_good": "Automatic tracking of working configurations",
                "auto_discovery": "Periodic automatic scanning",
                "device_caching": "Fast access to recently discovered devices",
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
