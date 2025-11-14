"""Discovery manager - coordinates all discovery methods."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .history import ConnectionHistoryTracker
from .mdns_scanner import MDNSScanner
from .models import (ConnectionStatistics, ConnectionStatus, DeviceAlias,
                     DiscoveredDevice, DiscoveryConfig, DiscoveryMethod,
                     DiscoveryScanRequest, DiscoveryScanResult,
                     DiscoveryStatus, LastKnownGood, SmartRecommendation)
from .visa_scanner import VISAScanner

logger = logging.getLogger(__name__)


class DiscoveryManager:
    """Manages equipment discovery and connection tracking."""

    def __init__(self, config: DiscoveryConfig, visa_backend: str = "@py"):
        """Initialize discovery manager.

        Args:
            config: Discovery configuration
            visa_backend: PyVISA backend
        """
        self.config = config
        self.visa_backend = visa_backend

        # Scanners
        self.visa_scanner = VISAScanner(config, visa_backend)
        self.mdns_scanner = MDNSScanner(config)

        # Connection history
        self.history = ConnectionHistoryTracker(config)

        # Device cache
        self.devices: Dict[str, DiscoveredDevice] = {}
        self.aliases: Dict[str, DeviceAlias] = {}

        # Discovery state
        self.is_running = False
        self.last_scan: Optional[datetime] = None
        self._scan_task: Optional[asyncio.Task] = None

        # Statistics
        self.total_scans = 0
        self.scan_durations: List[float] = []

    async def start_auto_discovery(self):
        """Start automatic periodic discovery."""
        if self.is_running:
            logger.warning("Auto-discovery already running")
            return

        if not self.config.enable_auto_discovery:
            logger.info("Auto-discovery is disabled")
            return

        logger.info("Starting auto-discovery...")
        self.is_running = True
        self._scan_task = asyncio.create_task(self._auto_discovery_loop())

    async def stop_auto_discovery(self):
        """Stop automatic discovery."""
        if not self.is_running:
            return

        logger.info("Stopping auto-discovery...")
        self.is_running = False

        if self._scan_task and not self._scan_task.done():
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass

        logger.info("Auto-discovery stopped")

    async def _auto_discovery_loop(self):
        """Automatic discovery loop."""
        while self.is_running:
            try:
                # Perform scan
                logger.debug("Running auto-discovery scan...")
                await self.scan()

                # Wait for next scan
                # Use minimum of VISA and mDNS intervals
                interval = min(
                    self.config.visa_scan_interval_sec,
                    self.config.mdns_scan_interval_sec,
                )
                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Auto-discovery error: {e}")
                await asyncio.sleep(60)  # Wait before retry

    async def scan(
        self, request: Optional[DiscoveryScanRequest] = None
    ) -> DiscoveryScanResult:
        """Perform discovery scan.

        Args:
            request: Scan request (optional)

        Returns:
            Scan result
        """
        scan_id = str(uuid.uuid4())[:8]
        started_at = datetime.now()

        logger.info(f"Starting discovery scan {scan_id}...")

        result = DiscoveryScanResult(
            scan_id=scan_id,
            started_at=started_at,
            completed_at=started_at,
            duration_ms=0.0,
        )

        try:
            # Determine which methods to use
            methods = (
                request.methods
                if request and request.methods
                else [DiscoveryMethod.VISA, DiscoveryMethod.MDNS]
            )

            # Check cache
            use_cache = (
                not request or not request.force_refresh
            ) and self.config.cache_discovered_devices
            if use_cache and self.devices:
                cache_age = (
                    (datetime.now() - self.last_scan).total_seconds()
                    if self.last_scan
                    else float("inf")
                )
                if cache_age < self.config.cache_ttl_sec:
                    logger.debug(f"Using cached devices (age: {cache_age:.1f}s)")
                    result.devices = list(self.devices.values())
                    result.devices_found = len(result.devices)
                    result.completed_at = datetime.now()
                    result.duration_ms = (
                        result.completed_at - result.started_at
                    ).total_seconds() * 1000
                    result.success = True
                    return result

            discovered = []

            # VISA scan
            if DiscoveryMethod.VISA in methods and self.config.enable_visa_scan:
                try:
                    logger.debug("Running VISA scan...")
                    visa_devices = self.visa_scanner.scan()
                    discovered.extend(visa_devices)
                    result.visa_count = len(visa_devices)
                    logger.info(f"VISA scan found {len(visa_devices)} devices")
                except Exception as e:
                    logger.error(f"VISA scan failed: {e}")
                    result.errors.append(f"VISA scan failed: {e}")

            # mDNS scan
            if DiscoveryMethod.MDNS in methods and self.config.enable_mdns:
                if self.mdns_scanner.is_available():
                    try:
                        logger.debug("Running mDNS scan...")
                        mdns_devices = self.mdns_scanner.scan()
                        discovered.extend(mdns_devices)
                        result.mdns_count = len(mdns_devices)
                        logger.info(f"mDNS scan found {len(mdns_devices)} devices")
                    except Exception as e:
                        logger.error(f"mDNS scan failed: {e}")
                        result.errors.append(f"mDNS scan failed: {e}")
                else:
                    logger.debug("mDNS scanning not available (zeroconf not installed)")

            # Merge discovered devices with existing cache
            new_count, updated_count = self._update_device_cache(discovered)

            result.devices_found = len(discovered)
            result.new_devices = new_count
            result.updated_devices = updated_count
            result.devices = list(self.devices.values())

            # Update scan statistics
            self.last_scan = datetime.now()
            self.total_scans += 1

            result.success = len(result.errors) == 0

            logger.info(
                f"Discovery scan {scan_id} complete: {result.devices_found} devices "
                f"({result.new_devices} new, {result.updated_devices} updated)"
            )

        except Exception as e:
            logger.error(f"Discovery scan failed: {e}")
            result.success = False
            result.errors.append(str(e))

        # Update timing
        result.completed_at = datetime.now()
        result.duration_ms = (
            result.completed_at - result.started_at
        ).total_seconds() * 1000

        self.scan_durations.append(result.duration_ms)
        if len(self.scan_durations) > 100:
            self.scan_durations = self.scan_durations[-100:]

        return result

    def _update_device_cache(
        self, discovered: List[DiscoveredDevice]
    ) -> tuple[int, int]:
        """Update device cache with newly discovered devices.

        Args:
            discovered: List of discovered devices

        Returns:
            Tuple of (new_count, updated_count)
        """
        new_count = 0
        updated_count = 0

        for device in discovered:
            device_id = device.device_id

            if device_id in self.devices:
                # Update existing device
                existing = self.devices[device_id]

                # Update last_seen
                device.last_seen = datetime.now()

                # Preserve user configuration
                device.friendly_name = existing.friendly_name
                device.alias = existing.alias
                device.location = existing.location
                device.tags = existing.tags

                # Update device
                self.devices[device_id] = device
                updated_count += 1
            else:
                # New device
                self.devices[device_id] = device
                new_count += 1

                logger.info(
                    f"New device discovered: {device.manufacturer} {device.model} "
                    f"({device.resource_name})"
                )

        return new_count, updated_count

    def get_devices(
        self,
        device_type: Optional[str] = None,
        status: Optional[ConnectionStatus] = None,
    ) -> List[DiscoveredDevice]:
        """Get discovered devices with filtering.

        Args:
            device_type: Filter by device type
            status: Filter by status

        Returns:
            List of devices
        """
        devices = list(self.devices.values())

        # Apply filters
        if device_type:
            devices = [d for d in devices if d.device_type.value == device_type]

        if status:
            devices = [d for d in devices if d.status == status]

        # Sort by last seen (most recent first)
        devices.sort(key=lambda d: d.last_seen, reverse=True)

        return devices

    def get_device(self, device_id: str) -> Optional[DiscoveredDevice]:
        """Get device by ID.

        Args:
            device_id: Device identifier

        Returns:
            Device or None
        """
        return self.devices.get(device_id)

    def get_device_by_alias(self, alias: str) -> Optional[DiscoveredDevice]:
        """Get device by alias.

        Args:
            alias: Device alias

        Returns:
            Device or None
        """
        # Find device with matching alias
        for device in self.devices.values():
            if device.alias == alias:
                return device

        return None

    def set_alias(self, device_id: str, alias_data: DeviceAlias) -> bool:
        """Set device alias and metadata.

        Args:
            device_id: Device identifier
            alias_data: Alias data

        Returns:
            True if successful
        """
        device = self.devices.get(device_id)
        if not device:
            return False

        # Update device
        device.alias = alias_data.alias
        device.friendly_name = alias_data.friendly_name
        device.location = alias_data.location
        device.tags = alias_data.tags

        # Store in aliases dict
        self.aliases[device_id] = alias_data

        logger.info(f"Set alias for {device_id}: {alias_data.alias}")
        return True

    def get_recommendations(
        self, device_type: Optional[str] = None, limit: int = 5
    ) -> List[SmartRecommendation]:
        """Get smart connection recommendations.

        Args:
            device_type: Filter by device type
            limit: Maximum recommendations

        Returns:
            List of recommendations
        """
        if not self.config.enable_recommendations:
            return []

        recommendations = []

        # Get devices
        devices = self.get_devices(device_type=device_type)

        # Filter by confidence threshold
        devices = [
            d
            for d in devices
            if d.confidence_score >= self.config.min_confidence_threshold
        ]

        # Get connection statistics for each
        for device in devices:
            stats = self.history.get_statistics(device.device_id)

            # Calculate recommendation confidence
            confidence = self._calculate_recommendation_confidence(device, stats)

            if confidence >= self.config.min_confidence_threshold:
                reason = self._generate_recommendation_reason(device, stats)

                rec = SmartRecommendation(
                    device_id=device.device_id,
                    resource_name=device.resource_name,
                    confidence=confidence,
                    reason=reason,
                    last_successful=stats.last_successful if stats else None,
                    success_rate=stats.success_rate if stats else None,
                    response_time_ms=device.response_time_ms,
                )

                recommendations.append(rec)

        # Sort by confidence (highest first)
        recommendations.sort(key=lambda r: r.confidence, reverse=True)

        return recommendations[:limit]

    def _calculate_recommendation_confidence(
        self, device: DiscoveredDevice, stats: Optional[ConnectionStatistics]
    ) -> float:
        """Calculate recommendation confidence score.

        Args:
            device: Discovered device
            stats: Connection statistics

        Returns:
            Confidence score (0-1)
        """
        # Start with device's base confidence
        confidence = device.confidence_score

        # Boost if recently seen
        if device.last_seen:
            age_minutes = (datetime.now() - device.last_seen).total_seconds() / 60
            if age_minutes < 5:
                confidence *= 1.2  # Recent sighting bonus
            elif age_minutes > 60:
                confidence *= 0.8  # Old sighting penalty

        # Boost based on connection history
        if stats:
            # High success rate
            if stats.success_rate > 0.9:
                confidence *= 1.3
            elif stats.success_rate > 0.7:
                confidence *= 1.1
            elif stats.success_rate < 0.3:
                confidence *= 0.5

            # Penalize recent failures
            if stats.recent_failures > 3:
                confidence *= 0.5

        # Boost for mDNS devices (they advertise themselves)
        if device.discovery_method == DiscoveryMethod.MDNS:
            confidence *= 1.1

        # Cap at 1.0
        return min(confidence, 1.0)

    def _generate_recommendation_reason(
        self, device: DiscoveredDevice, stats: Optional[ConnectionStatistics]
    ) -> str:
        """Generate human-readable recommendation reason.

        Args:
            device: Discovered device
            stats: Connection statistics

        Returns:
            Reason string
        """
        reasons = []

        # Discovery method
        if device.discovery_method == DiscoveryMethod.MDNS:
            reasons.append("Advertised via mDNS")
        elif device.discovery_method == DiscoveryMethod.VISA:
            reasons.append("Found via VISA")

        # Device identification
        if device.manufacturer and device.model:
            reasons.append(f"Identified as {device.manufacturer} {device.model}")

        # Connection history
        if stats:
            if stats.success_rate > 0.9:
                reasons.append(f"High success rate ({stats.success_rate*100:.0f}%)")
            if stats.total_connections > 10:
                reasons.append(
                    f"Frequently used ({stats.total_connections} connections)"
                )

        # Recent activity
        if device.last_seen:
            age_minutes = (datetime.now() - device.last_seen).total_seconds() / 60
            if age_minutes < 5:
                reasons.append("Recently seen")

        return "; ".join(reasons) if reasons else "Available device"

    def get_status(self) -> DiscoveryStatus:
        """Get discovery system status.

        Returns:
            Discovery status
        """
        # Count devices by status
        available = sum(
            1 for d in self.devices.values() if d.status == ConnectionStatus.AVAILABLE
        )
        connected = sum(
            1 for d in self.devices.values() if d.status == ConnectionStatus.CONNECTED
        )
        offline = sum(
            1 for d in self.devices.values() if d.status == ConnectionStatus.OFFLINE
        )

        # Count by method
        mdns_count = sum(
            1
            for d in self.devices.values()
            if d.discovery_method == DiscoveryMethod.MDNS
        )
        visa_count = sum(
            1
            for d in self.devices.values()
            if d.discovery_method == DiscoveryMethod.VISA
        )
        usb_count = sum(
            1
            for d in self.devices.values()
            if d.discovery_method == DiscoveryMethod.USB
        )
        manual_count = sum(
            1
            for d in self.devices.values()
            if d.discovery_method == DiscoveryMethod.MANUAL
        )

        # Calculate average scan duration
        avg_duration = (
            sum(self.scan_durations) / len(self.scan_durations)
            if self.scan_durations
            else None
        )

        # Calculate next scan time
        next_scan = None
        if self.is_running and self.last_scan:
            interval = min(
                self.config.visa_scan_interval_sec,
                self.config.mdns_scan_interval_sec,
            )
            next_scan = self.last_scan + timedelta(seconds=interval)

        return DiscoveryStatus(
            is_running=self.is_running,
            last_scan=self.last_scan,
            next_scan=next_scan,
            total_devices=len(self.devices),
            available_devices=available,
            connected_devices=connected,
            offline_devices=offline,
            mdns_devices=mdns_count,
            visa_devices=visa_count,
            usb_devices=usb_count,
            manual_devices=manual_count,
            last_scan_duration_ms=(
                self.scan_durations[-1] if self.scan_durations else None
            ),
            avg_scan_duration_ms=avg_duration,
        )

    def mark_connected(self, device_id: str, equipment_id: str):
        """Mark device as connected.

        Args:
            device_id: Device identifier
            equipment_id: Equipment manager ID
        """
        device = self.devices.get(device_id)
        if device:
            device.status = ConnectionStatus.CONNECTED
            device.is_connected = True
            device.metadata["equipment_id"] = equipment_id

            # Record connection
            self.history.record_connection(
                device_id=device_id,
                resource_name=device.resource_name,
                success=True,
                manufacturer=device.manufacturer,
                model=device.model,
            )

            logger.info(f"Device {device_id} marked as connected")

    def mark_disconnected(self, device_id: str):
        """Mark device as disconnected.

        Args:
            device_id: Device identifier
        """
        device = self.devices.get(device_id)
        if device:
            device.status = ConnectionStatus.AVAILABLE
            device.is_connected = False
            if "equipment_id" in device.metadata:
                del device.metadata["equipment_id"]

            # Record disconnection
            self.history.record_disconnection(
                device_id=device_id, resource_name=device.resource_name
            )

            logger.info(f"Device {device_id} marked as disconnected")

    def cleanup(self):
        """Cleanup old devices and history."""
        # Remove devices not seen recently
        cutoff = datetime.now() - timedelta(days=7)
        to_remove = [
            device_id
            for device_id, device in self.devices.items()
            if device.last_seen < cutoff and not device.is_connected
        ]

        for device_id in to_remove:
            del self.devices[device_id]
            logger.debug(f"Removed stale device: {device_id}")

        # Cleanup history
        if self.config.enable_history:
            self.history.cleanup()


# Global discovery manager instance
_discovery_manager: Optional[DiscoveryManager] = None


def initialize_discovery_manager(
    config: DiscoveryConfig, visa_backend: str = "@py"
) -> DiscoveryManager:
    """Initialize global discovery manager.

    Args:
        config: Discovery configuration
        visa_backend: VISA backend

    Returns:
        Discovery manager instance
    """
    global _discovery_manager
    _discovery_manager = DiscoveryManager(config, visa_backend)
    return _discovery_manager


def get_discovery_manager() -> DiscoveryManager:
    """Get global discovery manager instance.

    Returns:
        Discovery manager

    Raises:
        RuntimeError: If manager not initialized
    """
    if _discovery_manager is None:
        raise RuntimeError("Discovery manager not initialized")
    return _discovery_manager
