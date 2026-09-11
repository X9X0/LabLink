"""Base class for all equipment."""

import asyncio
import hashlib
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from pyvisa import ResourceManager
from pyvisa.resources import MessageBasedResource

from shared.models.equipment import (ConnectionType, EquipmentInfo,
                                     EquipmentStatus, EquipmentType)

logger = logging.getLogger(__name__)


def generate_equipment_id(resource_string: str, prefix: str) -> str:
    """Generate a deterministic equipment ID from the resource string.

    Args:
        resource_string: The VISA resource string (e.g., "TCPIP::192.168.1.100::INSTR")
        prefix: The prefix to use for the ID (e.g., "ps_", "scope_", "load_")

    Returns:
        A deterministic equipment ID (e.g., "ps_a1b2c3d4")
    """
    # Create a hash of the resource string
    hash_obj = hashlib.sha256(resource_string.encode())
    # Take first 8 characters of hex digest for a compact ID
    hash_hex = hash_obj.hexdigest()[:8]
    return f"{prefix}{hash_hex}"


class _ReentrantAsyncLock:
    """An asyncio lock that the task holding it may take again.

    Instrument I/O has to be serialised per instrument: the health monitor's
    poll, a client's readings timer and the operator's set_output all arrive
    as separate coroutines, and a USBTMC device handed two interleaved
    transfers stalls its bulk pipe and fails everything after that with
    "[Errno 32] Pipe error", while a serial supply hands one caller the
    other's reply. A plain asyncio.Lock would deadlock the reconnect path,
    where _query() -> _ensure_connected() -> connect() -> _query() all run in
    one task, so this one is re-entrant for the task that owns it.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self._owner: Optional[asyncio.Task] = None
        self._depth = 0

    async def __aenter__(self):
        me = asyncio.current_task()
        if self._owner is me:
            self._depth += 1
            return self
        await self._lock.acquire()
        self._owner = me
        self._depth = 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._depth -= 1
        if self._depth == 0:
            self._owner = None
            self._lock.release()
        return False

    def locked(self) -> bool:
        return self._lock.locked()


class BaseEquipment(ABC):
    """Base class for all lab equipment."""

    #: Seconds to let a USB device re-enumerate after a reset before the
    #: exchange that provoked the reset is retried.
    USB_RESET_SETTLE_SEC = 1.0

    def __init__(self, resource_manager: ResourceManager, resource_string: str):
        """Initialize equipment."""
        self.resource_manager = resource_manager
        self.resource_string = resource_string
        self.instrument: Optional[MessageBasedResource] = None
        self.connected = False
        self.cached_info: Optional[EquipmentInfo] = None
        self._lock = asyncio.Lock()
        # Held for every exchange with the instrument; see _ReentrantAsyncLock.
        self._io_lock = _ReentrantAsyncLock()
        self._is_connecting = False  # Flag to prevent recursion during connection

    def _is_instrument_valid(self) -> bool:
        """Check if the instrument session is still valid."""
        if not self.instrument:
            return False

        try:
            # Try to access the session attribute to check if it's still valid
            _ = self.instrument.session
            return True
        except Exception:
            return False

    def _is_resource_manager_valid(self) -> bool:
        """Check if the resource manager is still valid."""
        if not self.resource_manager:
            return False

        try:
            # Try to list resources to check if manager is still valid
            _ = self.resource_manager.list_resources()
            return True
        except Exception:
            return False

    def _refresh_resource_manager(self):
        """Refresh the resource manager if it's invalid."""
        if not self._is_resource_manager_valid():
            logger.warning(f"Resource manager invalid, creating new one for {self.resource_string}")
            try:
                # Close the old one if possible
                if self.resource_manager:
                    try:
                        self.resource_manager.close()
                    except Exception:
                        pass
                # Create a new resource manager
                from pyvisa import ResourceManager
                self.resource_manager = ResourceManager("@py")
                logger.info("Created new resource manager")
            except Exception as e:
                logger.error(f"Failed to create new resource manager: {e}")
                raise

    async def _ensure_connected(self):
        """Ensure the instrument is connected and session is valid.

        Automatically reconnects if the session has become invalid.
        """
        # Skip validation during initial connection to prevent recursion
        if self._is_connecting:
            return

        if not self._is_instrument_valid():
            logger.warning(f"Invalid instrument session detected for {self.resource_string}, reconnecting...")
            # Close the old invalid instrument
            if self.instrument is not None:
                try:
                    self.instrument.close()
                except Exception:
                    pass  # Ignore errors when closing invalid sessions
            self.instrument = None
            self.connected = False
            # Reconnect
            await self.connect()

    async def connect(self):
        """Connect to the equipment."""
        async with self._lock:
            try:
                # Set flag to prevent recursion during connection
                self._is_connecting = True

                # Ensure resource manager is valid before opening resource
                self._refresh_resource_manager()

                # Close old instrument if it exists
                if self.instrument is not None:
                    try:
                        self.instrument.close()
                    except Exception:
                        pass  # Ignore errors when closing invalid sessions
                    self.instrument = None

                # Open the resource
                self.instrument = self.resource_manager.open_resource(
                    self.resource_string
                )

                # Set timeout (10 seconds)
                self.instrument.timeout = 10000

                # Verify connection with IDN query
                idn = await self._query("*IDN?")
                logger.info(f"Connected to device: {idn}")

                self.connected = True

                # Cache equipment info
                self.cached_info = await self.get_info()

            except Exception as e:
                logger.error(f"Failed to connect to {self.resource_string}: {e}")
                self.connected = False
                raise
            finally:
                # Always clear the connecting flag
                self._is_connecting = False

    async def disconnect(self):
        """Close the transport. Sends nothing to the instrument.

        This really is only `instrument.close()`. If you are looking for why a
        supply's output went off on disconnect, it is not here: the decision
        is made one layer up, in `EquipmentManager.disconnect_device`, which
        applies the disconnect policy before calling this. See issue #198 --
        the answer was mislocated in exactly this docstring's direction once
        already.
        """
        async with self._lock:
            if self.instrument:
                try:
                    self.instrument.close()
                    logger.info(f"Disconnected from {self.resource_string}")
                except Exception as e:
                    logger.error(f"Error disconnecting: {e}")
                finally:
                    self.instrument = None
                    self.connected = False

    # ==================== Instrument I/O ====================
    #
    # Every exchange with the instrument goes through _write, _query or
    # _query_binary, and each holds self._io_lock for the whole exchange. The
    # lock is what keeps the health monitor, a client's readings poll and a
    # set_output from interleaving on the wire. A driver that talks to
    # self.instrument directly has to take the same lock -- see
    # BKPowerSupplyBase._bk_query.

    async def query(self, command: str) -> str:
        """Query the instrument. The public face of _query, for diagnostics."""
        return await self._query(command)

    async def write(self, command: str) -> None:
        """Write to the instrument. The public face of _write, for diagnostics."""
        await self._write(command)

    async def health_probe(self) -> str:
        """The cheapest exchange that proves the instrument is still there.

        *IDN? by default, which every SCPI instrument answers. A driver for an
        instrument with no *IDN? overrides this: asking a fixed-width B&K
        supply for *IDN? costs a full timeout on every health poll and holds
        the port against real traffic the whole time.
        """
        return await self._query("*IDN?")

    @staticmethod
    def _is_usb_pipe_error(error: BaseException) -> bool:
        """EPIPE from pyusb: the device has stalled a bulk endpoint."""
        return getattr(error, "errno", None) == 32 or "Pipe error" in str(error)

    def _recover_usb_stall(self, error: BaseException) -> bool:
        """Reset the USB device behind a pipe error. True if a retry is worth it.

        pyvisa-py's USBTMC layer neither resets a device when it opens it nor
        clears a halted endpoint, so once a 9205B's bulk pipe has stalled every
        later transfer fails the same way until something resets the device.
        The pyusb device is reachable through the pyvisa-py session: reset it,
        drop our session, and let _ensure_connected() open a fresh one.
        """
        if not self._is_usb_pipe_error(error) or self.instrument is None:
            return False
        if not self.resource_string.upper().startswith("USB"):
            return False

        instrument, self.instrument, self.connected = self.instrument, None, False
        reset = False
        try:
            session = instrument.visalib.sessions[instrument.session]
            session.interface.usb_dev.reset()
            reset = True
            logger.warning(
                f"Reset the stalled USB device behind {self.resource_string}"
            )
        except Exception as e:
            logger.error(
                f"Could not reset the USB device behind {self.resource_string}: {e}"
            )
        finally:
            try:
                instrument.close()
            except Exception:
                pass
        return reset

    async def _write(self, command: str):
        """Write a command to the instrument."""
        async with self._io_lock:
            try:
                await self._write_unlocked(command)
            except Exception as e:
                if not self._recover_usb_stall(e):
                    raise
                logger.info(
                    f"Retrying '{command}' on {self.resource_string} after USB reset"
                )
                await asyncio.sleep(self.USB_RESET_SETTLE_SEC)
                await self._write_unlocked(command)

    async def _query(self, command: str) -> str:
        """Query the instrument and return response."""
        async with self._io_lock:
            try:
                return await self._query_unlocked(command)
            except Exception as e:
                if not self._recover_usb_stall(e):
                    raise
                logger.info(
                    f"Retrying '{command}' on {self.resource_string} after USB reset"
                )
                await asyncio.sleep(self.USB_RESET_SETTLE_SEC)
                return await self._query_unlocked(command)

    async def _write_unlocked(self, command: str):
        """_write without the lock. Only _write should call this."""
        # Ensure we have a valid connection, reconnect if needed
        await self._ensure_connected()

        if not self.instrument:
            raise RuntimeError("Equipment not connected")

        import time
        start_time = time.perf_counter()
        success = False
        error_msg = None

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.instrument.write, command)
            success = True
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error writing command '{command}': {e}")
            raise
        finally:
            # Record command statistics for diagnostics
            response_time_ms = (time.perf_counter() - start_time) * 1000
            try:
                from server.diagnostics import diagnostics_manager
                if hasattr(self, 'cached_info') and self.cached_info:
                    diagnostics_manager.record_command(
                        equipment_id=self.cached_info.id,
                        success=success,
                        response_time_ms=response_time_ms,
                        bytes_sent=len(command.encode()),
                        error=error_msg,
                    )
            except Exception:
                # Don't let diagnostics recording interfere with operations
                pass

    async def _query_unlocked(self, command: str) -> str:
        """_query without the lock. Only _query should call this."""
        # Ensure we have a valid connection, reconnect if needed
        await self._ensure_connected()

        if not self.instrument:
            raise RuntimeError("Equipment not connected")

        import time
        start_time = time.perf_counter()
        success = False
        error_msg = None
        response = ""

        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, self.instrument.query, command)
            success = True
            return response.strip()
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error querying '{command}': {e}")
            raise
        finally:
            # Record command statistics for diagnostics
            response_time_ms = (time.perf_counter() - start_time) * 1000
            try:
                from server.diagnostics import diagnostics_manager
                if hasattr(self, 'cached_info') and self.cached_info:
                    diagnostics_manager.record_command(
                        equipment_id=self.cached_info.id,
                        success=success,
                        response_time_ms=response_time_ms,
                        bytes_sent=len(command.encode()),
                        bytes_received=len(response.encode()) if response else 0,
                        error=error_msg,
                    )
            except Exception:
                # Don't let diagnostics recording interfere with operations
                pass

    async def _query_binary(self, command: str) -> bytes:
        """Query the instrument and return binary response."""
        async with self._io_lock:
            # Ensure we have a valid connection, reconnect if needed
            await self._ensure_connected()

            if not self.instrument:
                raise RuntimeError("Equipment not connected")

            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None, self.instrument.query_binary_values, command, datatype="B"
                )
                return bytes(response)
            except Exception as e:
                logger.error(f"Error querying binary '{command}': {e}")
                raise

    @abstractmethod
    async def get_info(self) -> EquipmentInfo:
        """Get equipment information."""
        pass

    @abstractmethod
    async def get_status(self) -> EquipmentStatus:
        """Get current equipment status."""
        pass

    @abstractmethod
    async def execute_command(self, command: str, parameters: dict) -> Any:
        """Execute a command on the equipment."""
        pass

    # ==================== Optional Diagnostic Methods (v0.12.0) ====================
    # Subclasses can override these methods to provide equipment-specific diagnostics

    async def get_temperature(self) -> Optional[float]:
        """
        Get equipment internal temperature (if supported).

        Returns:
            Temperature in Celsius, or None if not supported
        """
        return None

    async def get_operating_hours(self) -> Optional[float]:
        """
        Get cumulative operating hours (if supported).

        Returns:
            Operating hours, or None if not supported
        """
        return None

    async def get_error_code(self) -> Optional[int]:
        """
        Get last error code (if supported).

        Returns:
            Error code number, or None if no error or not supported
        """
        try:
            # Try standard SCPI error query
            response = await self._query("SYST:ERR?")
            # Parse response format: "code,message"
            if response and "," in response:
                code_str = response.split(",")[0].strip()
                return int(code_str)
        except Exception:
            pass
        return None

    async def get_error_message(self) -> Optional[str]:
        """
        Get last error message (if supported).

        Returns:
            Error message, or None if no error or not supported
        """
        try:
            # Try standard SCPI error query
            response = await self._query("SYST:ERR?")
            # Parse response format: "code,message"
            if response and "," in response:
                message = response.split(",", 1)[1].strip().strip('"')
                return message
        except Exception:
            pass
        return None

    async def clear_errors(self) -> bool:
        """
        Clear equipment error queue (if supported).

        Returns:
            True if errors cleared, False if not supported
        """
        try:
            await self._write("*CLS")
            return True
        except Exception:
            return False

    async def run_self_test(self) -> Optional[dict]:
        """
        Run equipment built-in self-test (BIST) if supported.

        Returns:
            Dictionary with self-test results, or None if not supported
            Format: {
                "passed": bool,
                "tests": List[{"name": str, "passed": bool, "details": str}],
                "timestamp": datetime
            }
        """
        return None

    async def get_calibration_info(self) -> Optional[dict]:
        """
        Get calibration information from equipment (if stored in firmware).

        Returns:
            Dictionary with calibration info, or None if not supported
            Format: {
                "last_cal_date": datetime,
                "next_cal_date": datetime,
                "cal_count": int
            }
        """
        return None

    async def run_diagnostic_test(self, test_name: str) -> Optional[dict]:
        """
        Run equipment-specific diagnostic test.

        Args:
            test_name: Name of diagnostic test to run

        Returns:
            Test results dictionary, or None if not supported
        """
        return None

    def _determine_connection_type(self) -> ConnectionType:
        """Determine connection type from resource string."""
        resource_upper = self.resource_string.upper()
        if "USB" in resource_upper:
            return ConnectionType.USB
        elif "ASRL" in resource_upper or "COM" in resource_upper:
            return ConnectionType.SERIAL
        elif "TCPIP" in resource_upper:
            return ConnectionType.ETHERNET
        elif "GPIB" in resource_upper:
            return ConnectionType.GPIB
        return ConnectionType.USB  # Default

    # ==================== Firmware Update Methods (v0.28.0) ====================

    async def update_firmware(self, firmware_data: bytes) -> bool:
        """
        Update equipment firmware.

        This is a default implementation that should be overridden by subclasses
        that support firmware updates. Many lab equipment don't support remote
        firmware updates or have vendor-specific protocols.

        Args:
            firmware_data: Binary firmware file data

        Returns:
            True if update successful, False otherwise

        Raises:
            NotImplementedError: If equipment doesn't support firmware updates
        """
        raise NotImplementedError(
            f"Firmware update not supported for {self.__class__.__name__}. "
            "This equipment either doesn't support remote firmware updates or "
            "the update procedure hasn't been implemented yet."
        )

    async def supports_firmware_update(self) -> bool:
        """
        Check if equipment supports remote firmware updates.

        Returns:
            True if firmware updates are supported, False otherwise
        """
        # Try to call update_firmware with empty data to see if NotImplementedError is raised
        try:
            # We don't actually want to update, just check if the method is implemented
            # Subclasses that support updates should override this method
            return False
        except Exception:
            return False

    async def get_firmware_version(self) -> Optional[str]:
        """
        Get current firmware version from equipment.

        Returns:
            Firmware version string, or None if not available
        """
        try:
            # Try to get version from status
            status = await self.get_status()
            return status.firmware_version
        except Exception as e:
            logger.error(f"Error getting firmware version: {e}")
            return None

    async def backup_firmware(self) -> Optional[bytes]:
        """
        Create backup of current firmware (if supported).

        Returns:
            Firmware binary data, or None if backup not supported
        """
        logger.warning(
            f"Firmware backup not supported for {self.__class__.__name__}"
        )
        return None

    async def restore_firmware(self, firmware_data: bytes) -> bool:
        """
        Restore firmware from backup.

        Args:
            firmware_data: Binary firmware backup data

        Returns:
            True if restore successful, False otherwise
        """
        # Use the standard update method
        return await self.update_firmware(firmware_data)
