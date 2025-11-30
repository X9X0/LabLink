"""mDNS/Bonjour scanner for equipment discovery."""

import logging
import socket
from datetime import datetime
from typing import Dict, List, Optional

from .models import (ConnectionStatus, DeviceType, DiscoveredDevice,
                     DiscoveryConfig, DiscoveryMethod)

logger = logging.getLogger(__name__)

# Try to import zeroconf (optional dependency)
try:
    from zeroconf import ServiceBrowser, ServiceInfo, ServiceListener, Zeroconf

    ZEROCONF_AVAILABLE = True
except ImportError:
    ZEROCONF_AVAILABLE = False

    # Define dummy classes for when zeroconf is not available
    class ServiceListener:  # type: ignore
        """Dummy ServiceListener for when zeroconf is not available."""

        pass

    Zeroconf = None  # type: ignore
    ServiceInfo = None  # type: ignore
    ServiceBrowser = None  # type: ignore

    logger.warning(
        "zeroconf library not available - mDNS discovery disabled. "
        "Install with: pip install zeroconf"
    )


class MDNSScanner:
    """Scans for equipment using mDNS/Bonjour."""

    def __init__(self, config: DiscoveryConfig):
        """Initialize mDNS scanner.

        Args:
            config: Discovery configuration
        """
        self.config = config
        self.zeroconf: Optional[Zeroconf] = None
        self.discovered_services: Dict[str, ServiceInfo] = {}

    def is_available(self) -> bool:
        """Check if mDNS scanning is available.

        Returns:
            True if zeroconf library is available
        """
        return ZEROCONF_AVAILABLE

    def scan(self) -> List[DiscoveredDevice]:
        """Scan for mDNS services.

        Returns:
            List of discovered devices

        Raises:
            RuntimeError: If zeroconf not available
        """
        if not ZEROCONF_AVAILABLE:
            raise RuntimeError(
                "mDNS scanning not available - zeroconf library not installed"
            )

        devices = []
        browser = None

        try:
            # Create zeroconf instance
            self.zeroconf = Zeroconf()

            # Create service listener
            listener = SCPIServiceListener(self)

            # Browse for SCPI services
            service_type = self.config.mdns_service_type
            logger.info(f"Browsing for mDNS services: {service_type}")

            browser = ServiceBrowser(self.zeroconf, service_type, listener)

            # Wait for scan timeout
            import time

            time.sleep(self.config.mdns_timeout_sec)

            # Process discovered services
            for name, info in self.discovered_services.items():
                try:
                    device = self._process_service(info)
                    if device:
                        devices.append(device)
                except Exception as e:
                    logger.warning(f"Failed to process mDNS service {name}: {e}")

            logger.info(f"mDNS scan found {len(devices)} devices")

        except Exception as e:
            logger.error(f"mDNS scan failed: {e}")
            raise

        finally:
            # Close browser first to prevent file descriptor leaks
            if browser:
                try:
                    browser.cancel()
                    logger.debug("Cancelled mDNS service browser")
                except Exception as e:
                    logger.warning(f"Error cancelling service browser: {e}")

            # Then close zeroconf
            if self.zeroconf:
                self.zeroconf.close()
                self.zeroconf = None

        return devices

    def _process_service(self, info: "ServiceInfo") -> Optional[DiscoveredDevice]:
        """Process a discovered mDNS service.

        Args:
            info: Service information

        Returns:
            Discovered device or None
        """
        # Get service properties
        addresses = info.parsed_addresses()
        if not addresses:
            logger.debug(f"Service {info.name} has no addresses")
            return None

        # Use first address
        ip_address = addresses[0]

        # Get port
        port = info.port if info.port else 5025  # Default SCPI port

        # Get hostname
        hostname = info.server.rstrip(".") if info.server else None

        # Build VISA resource name
        resource_name = f"TCPIP::{ip_address}::INSTR"
        if port != 5025:  # Non-standard port
            resource_name = f"TCPIP::{ip_address}::{port}::SOCKET"

        # Get properties from TXT records
        properties = {}
        if info.properties:
            for key, value in info.properties.items():
                try:
                    # Decode bytes to string
                    key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                    value_str = (
                        value.decode("utf-8") if isinstance(value, bytes) else value
                    )
                    properties[key_str] = value_str
                except:
                    pass

        # Create device
        device = DiscoveredDevice(
            device_id=self._generate_device_id(ip_address, port),
            resource_name=resource_name,
            discovery_method=DiscoveryMethod.MDNS,
            discovered_at=datetime.now(),
            last_seen=datetime.now(),
            status=ConnectionStatus.AVAILABLE,
            ip_address=ip_address,
            hostname=hostname,
            port=port,
            metadata={"mdns_properties": properties, "service_name": info.name},
        )

        # Extract device info from mDNS properties
        device.manufacturer = properties.get("manufacturer") or properties.get("vendor")
        device.model = properties.get("model")
        device.serial_number = properties.get("serial") or properties.get("sn")
        device.firmware_version = properties.get("firmware") or properties.get("fw")

        # Infer device type from properties
        device_type_str = properties.get("type") or properties.get("device_type")
        if device_type_str:
            device.device_type = self._parse_device_type(device_type_str)
        elif device.model:
            device.device_type = self._infer_device_type_from_model(device.model)

        # Set high confidence for mDNS devices (they advertise themselves)
        device.confidence_score = 0.95
        device.recommended = True

        return device

    def _parse_device_type(self, type_str: str) -> DeviceType:
        """Parse device type string.

        Args:
            type_str: Device type string

        Returns:
            Device type enum
        """
        type_lower = type_str.lower()

        if "oscilloscope" in type_lower or "scope" in type_lower:
            return DeviceType.OSCILLOSCOPE
        elif "power" in type_lower and "supply" in type_lower:
            return DeviceType.POWER_SUPPLY
        elif "load" in type_lower:
            return DeviceType.ELECTRONIC_LOAD
        elif "multimeter" in type_lower or "dmm" in type_lower:
            return DeviceType.MULTIMETER
        elif "generator" in type_lower:
            return DeviceType.FUNCTION_GENERATOR
        elif "analyzer" in type_lower:
            return DeviceType.SPECTRUM_ANALYZER

        return DeviceType.UNKNOWN

    def _infer_device_type_from_model(self, model: str) -> DeviceType:
        """Infer device type from model number.

        Args:
            model: Model number

        Returns:
            Inferred device type
        """
        model_lower = model.lower()

        # Oscilloscope patterns
        if any(keyword in model_lower for keyword in ["mso", "dso", "ds"]):
            return DeviceType.OSCILLOSCOPE

        # Power supply patterns
        if any(keyword in model_lower for keyword in ["dp", "pps"]):
            return DeviceType.POWER_SUPPLY

        # Electronic load patterns
        if any(keyword in model_lower for keyword in ["dl", "load"]):
            return DeviceType.ELECTRONIC_LOAD

        return DeviceType.UNKNOWN

    def _generate_device_id(self, ip_address: str, port: int) -> str:
        """Generate unique device ID.

        Args:
            ip_address: IP address
            port: Port number

        Returns:
            Device ID
        """
        return f"mdns_{ip_address.replace('.', '_')}_{port}"

    def add_service(self, zeroconf: Zeroconf, service_type: str, name: str):
        """Callback when a service is added.

        Args:
            zeroconf: Zeroconf instance
            service_type: Service type
            name: Service name
        """
        info = zeroconf.get_service_info(service_type, name)
        if info:
            logger.debug(f"mDNS service added: {name}")
            self.discovered_services[name] = info

    def remove_service(self, zeroconf: Zeroconf, service_type: str, name: str):
        """Callback when a service is removed.

        Args:
            zeroconf: Zeroconf instance
            service_type: Service type
            name: Service name
        """
        logger.debug(f"mDNS service removed: {name}")
        if name in self.discovered_services:
            del self.discovered_services[name]

    def update_service(self, zeroconf: Zeroconf, service_type: str, name: str):
        """Callback when a service is updated.

        Args:
            zeroconf: Zeroconf instance
            service_type: Service type
            name: Service name
        """
        info = zeroconf.get_service_info(service_type, name)
        if info:
            logger.debug(f"mDNS service updated: {name}")
            self.discovered_services[name] = info


class SCPIServiceListener(ServiceListener):
    """Service listener for SCPI devices."""

    def __init__(self, scanner: MDNSScanner):
        """Initialize listener.

        Args:
            scanner: Parent mDNS scanner
        """
        self.scanner = scanner

    def add_service(self, zeroconf: Zeroconf, service_type: str, name: str):
        """Service added callback."""
        self.scanner.add_service(zeroconf, service_type, name)

    def remove_service(self, zeroconf: Zeroconf, service_type: str, name: str):
        """Service removed callback."""
        self.scanner.remove_service(zeroconf, service_type, name)

    def update_service(self, zeroconf: Zeroconf, service_type: str, name: str):
        """Service updated callback."""
        self.scanner.update_service(zeroconf, service_type, name)


def scan_local_network_devices(timeout: float = 5.0) -> List[str]:
    """Scan local network for potential SCPI devices (fallback method).

    This is a simple TCP port scan for common SCPI ports (5025, 5024, etc.)
    on the local subnet. Use as fallback when mDNS is not available.

    Args:
        timeout: Scan timeout per host

    Returns:
        List of IP addresses with open SCPI ports
    """
    devices = []

    try:
        # Get local IP and subnet
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)

        # Parse subnet (simple /24 assumption)
        parts = local_ip.split(".")
        if len(parts) == 4:
            subnet = f"{parts[0]}.{parts[1]}.{parts[2]}"

            # Scan common SCPI ports on local subnet
            scpi_ports = [5025, 5024, 111]  # Common SCPI ports

            logger.info(f"Scanning local subnet {subnet}.0/24 for SCPI devices...")

            for i in range(1, 255):
                ip = f"{subnet}.{i}"

                for port in scpi_ports:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(0.1)  # Quick timeout

                    try:
                        result = sock.connect_ex((ip, port))
                        if result == 0:
                            logger.info(f"Found open port {port} on {ip}")
                            if ip not in devices:
                                devices.append(ip)
                    except:
                        pass
                    finally:
                        sock.close()

    except Exception as e:
        logger.error(f"Network scan failed: {e}")

    return devices
