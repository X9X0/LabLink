"""VISA resource scanner for equipment discovery."""

import logging
import re
from datetime import datetime
from typing import List, Optional

import pyvisa

from .models import (ConnectionStatus, DeviceType, DiscoveredDevice,
                     DiscoveryConfig, DiscoveryMethod)

logger = logging.getLogger(__name__)


class VISAScanner:
    """Scans for VISA resources (TCPIP, USB, GPIB, Serial)."""

    def __init__(self, config: DiscoveryConfig, visa_backend: str = "@py"):
        """Initialize VISA scanner.

        Args:
            config: Discovery configuration
            visa_backend: PyVISA backend (@py, @ni, @sim)
        """
        self.config = config
        self.visa_backend = visa_backend
        self.rm: Optional[pyvisa.ResourceManager] = None

    def _get_resource_manager(self) -> pyvisa.ResourceManager:
        """Get or create VISA resource manager.

        Returns:
            VISA resource manager
        """
        if self.rm is None:
            try:
                self.rm = pyvisa.ResourceManager(self.visa_backend)
                logger.info(f"Initialized VISA resource manager: {self.visa_backend}")
            except Exception as e:
                logger.error(f"Failed to initialize VISA resource manager: {e}")
                raise

        return self.rm

    def scan(self) -> List[DiscoveredDevice]:
        """Scan for VISA resources.

        Returns:
            List of discovered devices

        Raises:
            Exception: If scan fails
        """
        devices = []

        try:
            rm = self._get_resource_manager()

            # Build query string based on configuration
            query = self._build_query_string()
            logger.info(f"Scanning VISA resources: {query}")

            # List resources
            resources = rm.list_resources(query)
            logger.info(f"Found {len(resources)} VISA resources")

            # Process each resource
            for resource_name in resources:
                try:
                    device = self._process_resource(resource_name)
                    if device:
                        devices.append(device)
                except Exception as e:
                    logger.warning(f"Failed to process resource {resource_name}: {e}")

        except Exception as e:
            logger.error(f"VISA scan failed: {e}")
            raise

        return devices

    def _build_query_string(self) -> str:
        """Build VISA query string based on configuration.

        Returns:
            VISA query string (e.g., "?*::INSTR")
        """
        # Start with all resources
        parts = []

        # Add specific interface types
        if self.config.scan_tcpip:
            parts.append("TCPIP?*::INSTR")
        if self.config.scan_usb:
            parts.append("USB?*::INSTR")
        if self.config.scan_gpib:
            parts.append("GPIB?*::INSTR")
        if self.config.scan_serial:
            parts.append("ASRL?*::INSTR")

        # If none specified, scan all
        if not parts:
            return "?*::INSTR"

        # Return first part (VISA doesn't support OR queries)
        # We'll need to scan each type separately
        return "?*::INSTR"  # Scan all for now

    def _process_resource(self, resource_name: str) -> Optional[DiscoveredDevice]:
        """Process a single VISA resource.

        Args:
            resource_name: VISA resource name

        Returns:
            Discovered device or None
        """
        # Parse resource name
        interface_type = self._get_interface_type(resource_name)

        # Skip if interface not enabled
        if interface_type == "TCPIP" and not self.config.scan_tcpip:
            return None
        if interface_type == "USB" and not self.config.scan_usb:
            return None
        if interface_type == "GPIB" and not self.config.scan_gpib:
            return None
        if interface_type == "ASRL" and not self.config.scan_serial:
            return None

        # Create base device
        device = DiscoveredDevice(
            device_id=self._generate_device_id(resource_name),
            resource_name=resource_name,
            discovery_method=DiscoveryMethod.VISA,
            discovered_at=datetime.now(),
            last_seen=datetime.now(),
            status=ConnectionStatus.AVAILABLE,
        )

        # Parse network information for TCPIP devices
        if interface_type == "TCPIP":
            ip_address, hostname, port = self._parse_tcpip_resource(resource_name)
            device.ip_address = ip_address
            device.hostname = hostname
            device.port = port

        # Query device identification if enabled
        if self.config.test_connections and self.config.query_idn:
            try:
                device_info = self._query_device_info(resource_name)
                if device_info:
                    device.manufacturer = device_info.get("manufacturer")
                    device.model = device_info.get("model")
                    device.serial_number = device_info.get("serial_number")
                    device.firmware_version = device_info.get("firmware_version")
                    device.device_type = self._infer_device_type(device_info)
                    device.confidence_score = 0.9  # High confidence if we got *IDN?
                    device.status = ConnectionStatus.AVAILABLE
            except Exception as e:
                logger.debug(f"Failed to query device info for {resource_name}: {e}")
                device.status = ConnectionStatus.OFFLINE
                device.confidence_score = 0.3  # Low confidence

        return device

    def _get_interface_type(self, resource_name: str) -> str:
        """Get interface type from resource name.

        Args:
            resource_name: VISA resource name

        Returns:
            Interface type (TCPIP, USB, GPIB, ASRL)
        """
        if resource_name.startswith("TCPIP"):
            return "TCPIP"
        elif resource_name.startswith("USB"):
            return "USB"
        elif resource_name.startswith("GPIB"):
            return "GPIB"
        elif resource_name.startswith("ASRL"):
            return "ASRL"
        else:
            return "UNKNOWN"

    def _parse_tcpip_resource(
        self, resource_name: str
    ) -> tuple[Optional[str], Optional[str], Optional[int]]:
        """Parse TCPIP resource name.

        Args:
            resource_name: VISA resource name (e.g., TCPIP::192.168.1.100::INSTR)

        Returns:
            Tuple of (ip_address, hostname, port)
        """
        # TCPIP[board]::host address[::LAN device name][::INSTR]
        # Examples:
        # TCPIP::192.168.1.100::INSTR
        # TCPIP0::192.168.1.100::inst0::INSTR
        # TCPIP::hostname.local::5025::SOCKET

        parts = resource_name.split("::")
        ip_address = None
        hostname = None
        port = None

        if len(parts) >= 2:
            # Second part is host address (IP or hostname)
            host = parts[1]

            # Check if it's an IP address
            if self._is_ip_address(host):
                ip_address = host
            else:
                hostname = host

            # Check for port (SOCKET resources)
            if len(parts) >= 3 and parts[-1] == "SOCKET":
                try:
                    port = int(parts[2])
                except ValueError:
                    pass

        return ip_address, hostname, port

    def _is_ip_address(self, text: str) -> bool:
        """Check if text is an IP address.

        Args:
            text: Text to check

        Returns:
            True if IP address
        """
        pattern = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
        return bool(re.match(pattern, text))

    def _query_device_info(self, resource_name: str) -> Optional[dict]:
        """Query device identification.

        Args:
            resource_name: VISA resource name

        Returns:
            Device info dictionary or None
        """
        rm = self._get_resource_manager()

        try:
            # Open resource with timeout
            instrument = rm.open_resource(
                resource_name, timeout=self.config.connection_timeout_ms
            )

            try:
                # Query *IDN?
                idn_response = instrument.query("*IDN?").strip()
                logger.debug(f"*IDN? response from {resource_name}: {idn_response}")

                # Parse *IDN? response
                if self.config.parse_idn:
                    return self._parse_idn_response(idn_response)
                else:
                    return {"raw_idn": idn_response}

            finally:
                instrument.close()

        except Exception as e:
            logger.debug(f"Failed to query *IDN? from {resource_name}: {e}")
            return None

    def _parse_idn_response(self, idn_response: str) -> dict:
        """Parse *IDN? response.

        Standard format: MANUFACTURER,MODEL,SERIAL,FIRMWARE
        Example: "Rigol Technologies,MSO2072A,DS1ZA123456789,00.01.02.00"

        Args:
            idn_response: *IDN? response string

        Returns:
            Parsed device info
        """
        info = {"raw_idn": idn_response}

        # Split by comma
        parts = [p.strip() for p in idn_response.split(",")]

        if len(parts) >= 1:
            info["manufacturer"] = parts[0]
        if len(parts) >= 2:
            info["model"] = parts[1]
        if len(parts) >= 3:
            info["serial_number"] = parts[2]
        if len(parts) >= 4:
            info["firmware_version"] = parts[3]

        return info

    def _infer_device_type(self, device_info: dict) -> DeviceType:
        """Infer device type from device info.

        Args:
            device_info: Device information dictionary

        Returns:
            Inferred device type
        """
        # Get manufacturer and model
        manufacturer = (device_info.get("manufacturer") or "").lower()
        model = (device_info.get("model") or "").lower()
        combined = f"{manufacturer} {model}"

        # Oscilloscope patterns
        if any(
            keyword in combined
            for keyword in ["mso", "dso", "ds", "oscilloscope", "scope"]
        ):
            return DeviceType.OSCILLOSCOPE

        # Power supply patterns
        if any(
            keyword in combined
            for keyword in ["power supply", "ps", "dp", "pps", "9206", "9205", "9130"]
        ):
            return DeviceType.POWER_SUPPLY

        # Electronic load patterns
        if any(
            keyword in combined
            for keyword in [
                "electronic load",
                "e-load",
                "dl",
                "load",
                "1902",
                "dl3021",
            ]
        ):
            return DeviceType.ELECTRONIC_LOAD

        # Multimeter patterns
        if any(keyword in combined for keyword in ["multimeter", "dmm", "34"]):
            return DeviceType.MULTIMETER

        # Function generator patterns
        if any(
            keyword in combined
            for keyword in ["function generator", "waveform generator", "dg", "fg"]
        ):
            return DeviceType.FUNCTION_GENERATOR

        # Spectrum analyzer patterns
        if any(keyword in combined for keyword in ["spectrum analyzer", "sa", "rsa"]):
            return DeviceType.SPECTRUM_ANALYZER

        return DeviceType.UNKNOWN

    def _generate_device_id(self, resource_name: str) -> str:
        """Generate unique device ID from resource name.

        Args:
            resource_name: VISA resource name

        Returns:
            Device ID
        """
        # Use resource name as base, clean it up
        device_id = resource_name.replace("::", "_").replace("?", "").lower()

        # Add timestamp to ensure uniqueness
        # (In practice, we'd want to use serial number or MAC address)
        return device_id

    def test_connection(self, resource_name: str) -> tuple[bool, Optional[str]]:
        """Test connection to a resource.

        Args:
            resource_name: VISA resource name

        Returns:
            Tuple of (success, error_message)
        """
        rm = self._get_resource_manager()

        try:
            instrument = rm.open_resource(
                resource_name, timeout=self.config.connection_timeout_ms
            )
            try:
                # Try to query *IDN?
                instrument.query("*IDN?")
                return True, None
            finally:
                instrument.close()

        except Exception as e:
            return False, str(e)

    def close(self):
        """Close VISA resource manager."""
        if self.rm:
            try:
                self.rm.close()
                logger.info("Closed VISA resource manager")
            except Exception as e:
                logger.error(f"Error closing VISA resource manager: {e}")
            finally:
                self.rm = None
