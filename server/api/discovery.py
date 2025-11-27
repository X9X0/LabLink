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


# === Raspberry Pi Discovery ===


@router.post("/pi/scan")
async def scan_raspberry_pis(
    network: Optional[str] = None,
    timeout: float = 2.0
):
    """Scan network for Raspberry Pi devices.

    Discovers Raspberry Pis on the local network and identifies which ones
    are running LabLink server.

    **Query Parameters:**
    - network: Network CIDR to scan (e.g., "192.168.1.0/24"). Auto-detects if not provided.
    - timeout: Timeout in seconds for each host check (default: 2.0)

    **Returns:**
    - List of discovered Raspberry Pis with LabLink status

    **Example Response:**
    ```json
    {
      "success": true,
      "scan_time_sec": 45.2,
      "pis_found": 2,
      "lablink_servers": 1,
      "discovered_pis": [
        {
          "ip_address": "192.168.1.100",
          "hostname": "lablink-pi",
          "mac_address": "B8:27:EB:XX:XX:XX",
          "is_lablink": true,
          "lablink_version": "0.28.0",
          "lablink_name": "LabLink",
          "reachable": true,
          "response_time_ms": 15.3
        }
      ]
    }
    ```
    """
    try:
        from discovery import pi_discovery
        import time

        start_time = time.time()

        # Run discovery
        discovered_pis = await pi_discovery.discover_network(network=network, timeout=timeout)

        scan_time = time.time() - start_time
        lablink_count = sum(1 for pi in discovered_pis if pi.is_lablink)

        return {
            "success": True,
            "scan_time_sec": round(scan_time, 1),
            "pis_found": len(discovered_pis),
            "lablink_servers": lablink_count,
            "discovered_pis": [
                {
                    "ip_address": pi.ip_address,
                    "hostname": pi.hostname,
                    "mac_address": pi.mac_address,
                    "is_lablink": pi.is_lablink,
                    "lablink_version": pi.lablink_version,
                    "lablink_name": pi.lablink_name,
                    "os_info": pi.os_info,
                    "reachable": pi.reachable,
                    "response_time_ms": pi.response_time_ms,
                }
                for pi in discovered_pis
            ],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pi/status")
async def get_pi_discovery_status():
    """Get Raspberry Pi discovery status.

    **Returns:**
    - Discovery status and cached results

    **Example Response:**
    ```json
    {
      "scan_in_progress": false,
      "last_scan_results": [...]
    }
    ```
    """
    try:
        from discovery import pi_discovery

        return {
            "scan_in_progress": pi_discovery.scan_in_progress,
            "last_scan_count": len(pi_discovery.discovered_pis),
            "last_scan_results": [
                {
                    "ip_address": pi.ip_address,
                    "hostname": pi.hostname,
                    "is_lablink": pi.is_lablink,
                    "lablink_version": pi.lablink_version,
                }
                for pi in pi_discovery.discovered_pis
            ],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Discovery Settings ===


@router.get("/settings")
async def get_discovery_settings():
    """Get discovery system settings.

    Returns current configuration for discovery scanning options.

    **Returns:**
    - scan_tcpip: Scan TCPIP resources
    - scan_usb: Scan USB resources
    - scan_gpib: Scan GPIB resources
    - scan_serial: Scan serial resources
    - enable_mdns: Enable mDNS discovery
    - enable_visa: Enable VISA scanning
    - enable_auto_discovery: Enable automatic periodic scanning
    - test_connections: Test discovered devices
    - query_idn: Query *IDN? for identification

    **Example Response:**
    ```json
    {
      "scan_tcpip": true,
      "scan_usb": true,
      "scan_gpib": false,
      "scan_serial": false,
      "enable_mdns": true,
      "enable_visa": true,
      "enable_auto_discovery": true,
      "test_connections": true,
      "query_idn": true
    }
    ```
    """
    try:
        from server.config.settings import settings

        return {
            "scan_tcpip": settings.discovery_scan_tcpip,
            "scan_usb": settings.discovery_scan_usb,
            "scan_gpib": settings.discovery_scan_gpib,
            "scan_serial": settings.discovery_scan_serial,
            "enable_mdns": settings.enable_mdns_discovery,
            "enable_visa": settings.enable_visa_discovery,
            "enable_auto_discovery": settings.enable_auto_discovery,
            "test_connections": settings.discovery_test_connections,
            "query_idn": settings.discovery_query_idn,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings")
async def update_discovery_settings(
    scan_tcpip: Optional[bool] = None,
    scan_usb: Optional[bool] = None,
    scan_gpib: Optional[bool] = None,
    scan_serial: Optional[bool] = None,
    enable_mdns: Optional[bool] = None,
    enable_visa: Optional[bool] = None,
    enable_auto_discovery: Optional[bool] = None,
    test_connections: Optional[bool] = None,
    query_idn: Optional[bool] = None,
):
    """Update discovery system settings.

    Updates discovery scanning configuration. Only provided parameters will be updated.

    **Query Parameters:**
    - scan_tcpip: Enable/disable TCPIP scanning
    - scan_usb: Enable/disable USB scanning
    - scan_gpib: Enable/disable GPIB scanning
    - scan_serial: Enable/disable serial scanning
    - enable_mdns: Enable/disable mDNS discovery
    - enable_visa: Enable/disable VISA scanning
    - enable_auto_discovery: Enable/disable automatic periodic scanning
    - test_connections: Enable/disable connection testing
    - query_idn: Enable/disable *IDN? queries

    **Returns:**
    - success: Whether update was successful
    - updated_settings: The new settings values

    **Example:**
    ```
    POST /api/discovery/settings?scan_serial=true&scan_gpib=true
    ```
    """
    try:
        from server.config.settings import settings

        updated = {}

        # Update global settings
        if scan_tcpip is not None:
            settings.discovery_scan_tcpip = scan_tcpip
            updated["scan_tcpip"] = scan_tcpip

        if scan_usb is not None:
            settings.discovery_scan_usb = scan_usb
            updated["scan_usb"] = scan_usb

        if scan_gpib is not None:
            settings.discovery_scan_gpib = scan_gpib
            updated["scan_gpib"] = scan_gpib

        if scan_serial is not None:
            settings.discovery_scan_serial = scan_serial
            updated["scan_serial"] = scan_serial

        if enable_mdns is not None:
            settings.enable_mdns_discovery = enable_mdns
            updated["enable_mdns"] = enable_mdns

        if enable_visa is not None:
            settings.enable_visa_discovery = enable_visa
            updated["enable_visa"] = enable_visa

        if enable_auto_discovery is not None:
            settings.enable_auto_discovery = enable_auto_discovery
            updated["enable_auto_discovery"] = enable_auto_discovery

        if test_connections is not None:
            settings.discovery_test_connections = test_connections
            updated["test_connections"] = test_connections

        if query_idn is not None:
            settings.discovery_query_idn = query_idn
            updated["query_idn"] = query_idn

        # Update discovery manager's config in real-time
        try:
            manager = get_discovery_manager()

            # Update discovery manager config
            if scan_tcpip is not None:
                manager.config.scan_tcpip = scan_tcpip
            if scan_usb is not None:
                manager.config.scan_usb = scan_usb
            if scan_gpib is not None:
                manager.config.scan_gpib = scan_gpib
            if scan_serial is not None:
                manager.config.scan_serial = scan_serial
            if enable_mdns is not None:
                manager.config.enable_mdns = enable_mdns
            if enable_visa is not None:
                manager.config.enable_visa_scan = enable_visa
            if enable_auto_discovery is not None:
                manager.config.enable_auto_discovery = enable_auto_discovery
            if test_connections is not None:
                manager.config.test_connections = test_connections
            if query_idn is not None:
                manager.config.query_idn = query_idn

            # Update VISA scanner config (it references the manager's config)
            if scan_tcpip is not None:
                manager.visa_scanner.config.scan_tcpip = scan_tcpip
            if scan_usb is not None:
                manager.visa_scanner.config.scan_usb = scan_usb
            if scan_gpib is not None:
                manager.visa_scanner.config.scan_gpib = scan_gpib
            if scan_serial is not None:
                manager.visa_scanner.config.scan_serial = scan_serial
            if test_connections is not None:
                manager.visa_scanner.config.test_connections = test_connections
            if query_idn is not None:
                manager.visa_scanner.config.query_idn = query_idn

        except Exception as e:
            logger.warning(f"Could not update discovery manager config: {e}")

        return {
            "success": True,
            "message": f"Updated {len(updated)} setting(s)",
            "updated_settings": updated,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
