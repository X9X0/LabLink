"""VISA resource scanner for equipment discovery."""

import asyncio
import logging
import re
from datetime import datetime
from typing import Callable, List, Optional

import pyvisa

from .models import (ConnectionStatus, DeviceType, DiscoveredDevice,
                     DiscoveryConfig, DiscoveryMethod)
from .usb_hardware_db import get_device_info_from_resource

logger = logging.getLogger(__name__)


class VISAScanner:
    """Scans for VISA resources (TCPIP, USB, GPIB, Serial)."""

    def __init__(
        self,
        config: DiscoveryConfig,
        visa_backend: str = "@py",
        progress_callback: Optional[Callable[[str, dict], None]] = None,
    ):
        """Initialize VISA scanner.

        Args:
            config: Discovery configuration
            visa_backend: PyVISA backend (@py, @ni, @sim)
            progress_callback: Optional callback for progress updates (message, data)
        """
        self.config = config
        self.visa_backend = visa_backend
        self.rm: Optional[pyvisa.ResourceManager] = None
        self.progress_callback = progress_callback

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

    async def scan(self) -> List[DiscoveredDevice]:
        """Scan for VISA resources asynchronously.

        Returns:
            List of discovered devices

        Raises:
            Exception: If scan fails
        """
        devices = []

        try:
            # Create resource manager for this scan
            # (will reuse existing if available)
            rm = self._get_resource_manager()

            # Build query string based on configuration
            query = self._build_query_string()
            logger.info(f"Scanning VISA resources: {query}")

            if self.progress_callback:
                self.progress_callback(
                    "Enumerating VISA resources...",
                    {"stage": "enumeration", "query": query},
                )

            # List resources (blocking I/O, run in executor)
            loop = asyncio.get_event_loop()
            resources = await loop.run_in_executor(None, rm.list_resources, query)
            logger.info(f"Found {len(resources)} VISA resources: {list(resources)}")

            if self.progress_callback:
                self.progress_callback(
                    f"Found {len(resources)} VISA resources",
                    {
                        "stage": "found_resources",
                        "count": len(resources),
                        "resources": list(resources),
                    },
                )

            # Process resources in parallel (with controlled concurrency)
            # Limit to 3 concurrent queries to avoid overwhelming devices
            semaphore = asyncio.Semaphore(3)

            async def process_with_semaphore(resource_name: str, index: int):
                async with semaphore:
                    if self.progress_callback:
                        self.progress_callback(
                            f"Querying device {index + 1}/{len(resources)}: {resource_name}",
                            {
                                "stage": "querying",
                                "current": index + 1,
                                "total": len(resources),
                                "resource": resource_name,
                            },
                        )
                    try:
                        device = await self._process_resource(resource_name)
                        if device and self.progress_callback:
                            self.progress_callback(
                                f"Identified: {device.manufacturer} {device.model}",
                                {
                                    "stage": "identified",
                                    "device_id": device.device_id,
                                    "manufacturer": device.manufacturer,
                                    "model": device.model,
                                    "resource": resource_name,
                                },
                            )
                        return device
                    except Exception as e:
                        logger.warning(
                            f"Failed to process resource {resource_name}: {e}"
                        )
                        if self.progress_callback:
                            self.progress_callback(
                                f"Failed to query {resource_name}: {str(e)}",
                                {
                                    "stage": "error",
                                    "resource": resource_name,
                                    "error": str(e),
                                },
                            )
                        return None

            # Process all resources concurrently
            tasks = [
                process_with_semaphore(resource, i)
                for i, resource in enumerate(resources)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=False)

            # Filter out None results
            devices = [d for d in results if d is not None]

            # Log which resources were filtered out
            filtered_count = len(results) - len(devices)
            if filtered_count > 0:
                logger.warning(
                    f"Filtered out {filtered_count} resources that could not be identified"
                )

            if self.progress_callback:
                self.progress_callback(
                    f"Discovery complete: {len(devices)} devices identified",
                    {"stage": "complete", "device_count": len(devices)},
                )

        except Exception as e:
            logger.error(f"VISA scan failed: {e}")
            if self.progress_callback:
                self.progress_callback(
                    f"VISA scan error: {str(e)}", {"stage": "error", "error": str(e)}
                )
            raise

        finally:
            # Close resource manager after scan to prevent file descriptor leaks
            self.close()

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

    async def _process_resource(
        self, resource_name: str
    ) -> Optional[DiscoveredDevice]:
        """Process a single VISA resource asynchronously.

        Args:
            resource_name: VISA resource name

        Returns:
            Discovered device or None
        """
        # Parse resource name
        interface_type = self._get_interface_type(resource_name)

        # Skip if interface not enabled
        if interface_type == "TCPIP" and not self.config.scan_tcpip:
            logger.debug(f"Skipping TCPIP resource (disabled): {resource_name}")
            return None
        if interface_type == "USB" and not self.config.scan_usb:
            logger.debug(f"Skipping USB resource (disabled): {resource_name}")
            return None
        if interface_type == "GPIB" and not self.config.scan_gpib:
            logger.debug(f"Skipping GPIB resource (disabled): {resource_name}")
            return None
        if interface_type == "ASRL" and not self.config.scan_serial:
            logger.info(f"⚠️ Skipping ASRL resource (DISABLED in config): {resource_name}, scan_serial={self.config.scan_serial}")
            return None

        logger.debug(f"Processing {interface_type} resource: {resource_name}")

        # Log ASRL resources at INFO level for visibility
        if interface_type == "ASRL":
            logger.info(f"✓ Processing ASRL (serial) device: {resource_name}, scan_serial={self.config.scan_serial}")

        # Create base device
        device = DiscoveredDevice(
            device_id=self._generate_device_id(resource_name),
            resource_name=resource_name,
            discovery_method=DiscoveryMethod.VISA,
            status=ConnectionStatus.AVAILABLE,
        )

        # Parse network information for TCPIP devices
        if interface_type == "TCPIP":
            ip_address, hostname, port = self._parse_tcpip_resource(resource_name)
            device.ip_address = ip_address
            device.hostname = hostname
            device.port = port

        # Try USB hardware database first (faster, no device communication needed)
        # Works for both USB and ASRL (serial) devices
        usb_device_info = None
        if interface_type in ["USB", "ASRL"]:
            usb_device_info = get_device_info_from_resource(resource_name)
            if usb_device_info:
                logger.debug(
                    f"Found device in hardware database: {usb_device_info} (interface: {interface_type})"
                )
                # Don't use generic USB-to-Serial chip info, wait for *IDN? or better identification
                if usb_device_info.device_type != DeviceType.UNKNOWN:
                    if interface_type == "ASRL":
                        logger.info(
                            f"Serial device identified from USB hardware DB: "
                            f"{usb_device_info.manufacturer} {usb_device_info.model}"
                        )
                    device.manufacturer = usb_device_info.manufacturer
                    device.model = usb_device_info.model
                    device.device_type = usb_device_info.device_type
                    device.confidence_score = 0.7  # Good confidence from USB ID
                    device.status = ConnectionStatus.AVAILABLE
                    # Store additional info in metadata
                    if usb_device_info.description:
                        device.metadata["description"] = usb_device_info.description
                    if usb_device_info.max_voltage:
                        device.metadata["max_voltage"] = usb_device_info.max_voltage
                    if usb_device_info.max_current:
                        device.metadata["max_current"] = usb_device_info.max_current
                else:
                    # Generic USB-to-Serial chip, don't use this info yet
                    if interface_type == "ASRL":
                        logger.info(
                            f"Serial device uses generic USB-to-Serial chip "
                            f"({usb_device_info.manufacturer} {usb_device_info.model}), "
                            f"will try *IDN? for identification"
                        )
                    logger.debug(
                        f"Found generic USB-to-Serial chip ({usb_device_info.manufacturer} "
                        f"{usb_device_info.model}), will try *IDN? for better identification"
                    )
                    usb_device_info = None  # Clear it so we try *IDN?
            else:
                if interface_type == "ASRL":
                    logger.info(
                        f"No USB hardware info found for serial device {resource_name}, "
                        f"will try *IDN? query"
                    )

        # Query device identification if enabled (will override USB database info if successful)
        if self.config.test_connections and self.config.query_idn:
            try:
                device_info = await self._query_device_info(resource_name)
                if device_info:
                    # *IDN? succeeded - use this info (highest confidence)
                    device.manufacturer = device_info.get("manufacturer")
                    device.model = device_info.get("model")
                    device.serial_number = device_info.get("serial_number")
                    device.firmware_version = device_info.get("firmware_version")
                    device.device_type = self._infer_device_type(device_info)
                    device.confidence_score = 0.9  # High confidence if we got *IDN?
                    device.status = ConnectionStatus.AVAILABLE
                    logger.debug(
                        f"Successfully queried *IDN? from {resource_name}: "
                        f"{device.manufacturer} {device.model}"
                    )
                else:
                    # *IDN? failed but we have USB database info
                    if usb_device_info:
                        logger.debug(
                            f"*IDN? failed, using USB database info for {resource_name}"
                        )
                        # Keep USB database info (already set above)
                    else:
                        # No info available - for serial devices, still return them
                        # as they might use proprietary protocols
                        if interface_type == "ASRL":
                            logger.info(
                                f"Serial device at {resource_name} did not respond to *IDN?, "
                                f"may use proprietary protocol (e.g., BK Precision legacy devices)"
                            )
                            device.status = ConnectionStatus.AVAILABLE
                            device.confidence_score = 0.4  # Low-medium confidence
                            device.device_type = DeviceType.UNKNOWN
                            device.manufacturer = "Unknown"
                            device.model = f"Serial Device ({interface_type})"
                            device.metadata["note"] = "Does not respond to *IDN?, may use proprietary protocol"
                        else:
                            # TCP/IP or GPIB device that doesn't respond - mark as offline
                            device.status = ConnectionStatus.OFFLINE
                            device.confidence_score = 0.3  # Low confidence
            except Exception as e:
                logger.debug(f"Failed to query device info for {resource_name}: {e}")
                # If we have USB database info, keep it; otherwise handle based on interface
                if not usb_device_info:
                    # For serial devices, still return them as they might use proprietary protocols
                    if interface_type == "ASRL":
                        logger.info(
                            f"Serial device at {resource_name} query failed: {e}, "
                            f"may use proprietary protocol"
                        )
                        device.status = ConnectionStatus.AVAILABLE
                        device.confidence_score = 0.4  # Low-medium confidence
                        device.device_type = DeviceType.UNKNOWN
                        device.manufacturer = "Unknown"
                        device.model = f"Serial Device ({interface_type})"
                        device.metadata["note"] = "Failed to query, may use proprietary protocol"
                    else:
                        device.status = ConnectionStatus.OFFLINE
                        device.confidence_score = 0.3  # Low confidence
                else:
                    logger.debug(
                        f"*IDN? failed, but USB database provided identification"
                    )

        # Log final device status before returning
        if interface_type == "ASRL":
            logger.info(
                f"Returning serial device: {resource_name}, "
                f"manufacturer={device.manufacturer}, model={device.model}, "
                f"status={device.status}, confidence={device.confidence_score}"
            )

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

    async def _query_device_info(self, resource_name: str) -> Optional[dict]:
        """Query device identification asynchronously.

        Args:
            resource_name: VISA resource name

        Returns:
            Device info dictionary or None
        """

        def _blocking_query():
            """Blocking query to run in executor."""
            rm = self._get_resource_manager()
            try:
                # Open resource with timeout
                instrument = rm.open_resource(
                    resource_name, timeout=self.config.connection_timeout_ms
                )

                try:
                    # Query *IDN?
                    idn_response = instrument.query("*IDN?").strip()
                    logger.debug(
                        f"*IDN? response from {resource_name}: {idn_response}"
                    )

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

        # Run blocking I/O in executor
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _blocking_query)

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

    async def test_connection(
        self, resource_name: str
    ) -> tuple[bool, Optional[str]]:
        """Test connection to a resource asynchronously.

        Args:
            resource_name: VISA resource name

        Returns:
            Tuple of (success, error_message)
        """

        def _blocking_test():
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

        # Run blocking I/O in executor
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _blocking_test)

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
