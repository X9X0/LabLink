"""BK Precision power supply drivers.

Covers the legacy fixed-width ASCII supplies — 1685B/1687B/1688B,
1900B/1901B/1902B, 1696/1697/1698 and 9103/9104 — plus the SCPI models that
LabLink shipped drivers for before the registry existed.

The fixed-width protocol has no query syntax, no error queue and no ``*IDN?``:
a command is a mnemonic followed by zero-padded positional digit fields, CR
terminated. Everything therefore rests on getting the field scaling right, and
the scaling is *not* uniform across the family. See :class:`FixedWidthDialect`.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict

from server.config.settings import settings
from shared.models.data import PowerSupplyData
from shared.models.equipment import (EquipmentInfo, EquipmentStatus,
                                     EquipmentType)

from .base import BaseEquipment
from .bk_registry import resolve_model
from .bk_scpi import BK9130Series, BKSCPIPowerSupply
from .safety import (SafetyLimits, SafetyValidator, emergency_stop_manager,
                     get_default_limits)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FixedWidthDialect:
    """Field scaling and polarity for one fixed-width protocol variant.

    Three things differ across the family and each of them silently commands
    the wrong value rather than raising:

    * ``current_decimals`` — the 1685B carries two decimal places for current,
      the 1687B/1688B/1900B/1901B/1902B one. Sending a 1685B ``CURR025``
      meaning 2.5 A actually asks it for 0.25 A.
    * ``sout_on`` — on the 1685B and 1900B lines ``SOUT0`` *enables* the
      output; on the 9103/9104 ``SOUT0`` disables it.
    * ``preset_indexed`` — the 9103/9104 put a preset selector in front of the
      value and use four-digit two-decimal fields, so a 1685B-shaped
      ``VOLT120`` is not even the right length.
    """

    #: Decimal places in the three-digit VOLT / GETS voltage field.
    voltage_decimals: int = 1
    #: Decimal places in the three-digit CURR / GETS current field.
    current_decimals: int = 1
    #: Width of the VOLT / CURR / GETS fields.
    field_width: int = 3
    #: Divisor for the four-digit GETD voltage reading.
    reading_voltage_divisor: float = 100.0
    #: Divisor for the four-digit GETD current reading.
    reading_current_divisor: float = 100.0
    #: Value of the SOUT argument that turns the output ON.
    sout_on: str = "0"
    #: Whether VOLT / CURR / GETS take a leading preset index.
    preset_indexed: bool = False

    @property
    def sout_off(self) -> str:
        return "1" if self.sout_on == "0" else "0"


#: The 1687B/1688B/1900B/1901B/1902B default: one decimal for both fields.
DIALECT_STANDARD = FixedWidthDialect()

#: The 1685B alone carries two decimal places for current.
DIALECT_1685B = FixedWidthDialect(current_decimals=2)

#: The 9103/9104: preset-indexed, four-digit two-decimal fields, and SOUT is
#: the other way round.
DIALECT_PRESET_INDEXED = FixedWidthDialect(
    voltage_decimals=2, current_decimals=2, field_width=4, sout_on="1",
    preset_indexed=True,
)


def dialect_for(model: str) -> FixedWidthDialect:
    """Pick the fixed-width dialect for a model, defaulting to the common one."""
    info = resolve_model(model)
    if info and info.dialect == "preset_indexed":
        return DIALECT_PRESET_INDEXED
    if (model or "").upper().replace(" ", "").startswith("1685B"):
        return DIALECT_1685B
    return DIALECT_STANDARD


class BKPowerSupplyBase(BaseEquipment):
    """Base class for BK Precision power supplies."""

    def __init__(self, resource_manager, resource_string: str):
        """Initialize BK power supply."""
        super().__init__(resource_manager, resource_string)
        self.manufacturer = "BK Precision"
        self.model = "Unknown"
        self.num_channels = 1
        self.max_voltage = 60.0
        self.max_current = 5.0
        # Field scaling and SOUT polarity vary across the fixed-width family;
        # subclasses set their model first and then re-resolve this.
        self.dialect = DIALECT_STANDARD

        # Initialize safety validator
        self.safety_validator = None
        self._current_voltage = 0.0  # Track current voltage for slew rate limiting
        self._current_current = 0.0  # Track current current for slew rate limiting

    def _parse_bk_response(self, response: str) -> str:
        """Parse BK Precision response and remove OK suffix."""
        # BK responses end with \rOK\r
        response = response.strip()
        if response.endswith('OK'):
            response = response[:-2].strip()
        return response

    def _encode_field(self, value: float, decimals: int) -> str:
        """Encode a value as a zero-padded fixed-width integer field.

        Raising here matters: an over-wide field silently shifts every
        following character, so a value the supply cannot express has to be
        refused rather than truncated.
        """
        scaled = round(value * (10 ** decimals))
        if scaled < 0:
            raise ValueError("value must be non-negative")
        text = str(scaled)
        if len(text) > self.dialect.field_width:
            raise ValueError(
                f"{value} needs {len(text)} digits at {decimals} decimal "
                f"place(s), but the field is {self.dialect.field_width} wide"
            )
        return text.zfill(self.dialect.field_width)

    def _encode_voltage(self, volts: float) -> str:
        return self._encode_field(volts, self.dialect.voltage_decimals)

    def _encode_current(self, amps: float) -> str:
        return self._encode_field(amps, self.dialect.current_decimals)

    def _decode_setpoints(self, response: str) -> tuple:
        """Split a GETS reply into (voltage, current) at the dialect scaling."""
        width = self.dialect.field_width
        if len(response) < width * 2:
            raise ValueError(f"Invalid GETS response: {response}")
        voltage = int(response[:width]) / (10 ** self.dialect.voltage_decimals)
        current = int(response[width:width * 2]) / (
            10 ** self.dialect.current_decimals
        )
        return voltage, current

    async def _bk_query(self, command: str) -> str:
        """Send BK Precision command and parse response.

        BK responses are formatted as: DATA\rOK\r
        We need to read the full response, not just until the first \r

        Uses locking to ensure serial commands execute one at a time,
        preventing collisions when multiple requests happen simultaneously.
        """
        await self._ensure_connected()

        # Lock to prevent concurrent serial port access
        async with self._lock:
            loop = asyncio.get_event_loop()

            # Flush input buffer to clear any junk from previous failed reads
            try:
                if hasattr(self.instrument, 'flush') and hasattr(self.instrument.flush, '__call__'):
                    await loop.run_in_executor(None, self.instrument.flush, 1)  # Flush input (VI_READ_BUF)
            except Exception:
                pass  # Ignore flush errors

            # Send command (write_termination = '\r' is already set)
            logger.debug(f"Sending BK command: {command}")
            await loop.run_in_executor(None, self.instrument.write, command)

            # Read full response - keep reading until we get OK\r or timeout
            # Use read_bytes to get raw data instead of relying on read_termination
            full_response = b''
            start_time = loop.time()
            timeout = self.instrument.timeout / 1000.0  # Convert ms to seconds

            while True:
                try:
                    # Read one byte at a time until we get the full response
                    chunk = await loop.run_in_executor(None, self.instrument.read_bytes, 1)
                    full_response += chunk

                    # Check if we've received the complete response (ends with OK\r)
                    if full_response.endswith(b'OK\r'):
                        break

                    # Timeout check
                    if loop.time() - start_time > timeout:
                        raise TimeoutError(f"Timeout waiting for OK terminator. Got: {full_response}")

                except Exception as e:
                    if full_response:
                        logger.error(f"Error reading response after {len(full_response)} bytes: {e}")
                    raise

            # Decode and parse
            response_str = full_response.decode('ascii', errors='ignore')
            logger.debug(f"Received BK response ({len(full_response)} bytes): {repr(response_str)}")
            return self._parse_bk_response(response_str)

    async def connect(self):
        """Connect to the BK power supply with serial port configuration.

        Note: Serial communication protection is handled by _bk_query() locking,
        not here, to avoid deadlock when calling _bk_query() during connect.
        """
        try:
            # Refresh resource manager if needed
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

            # Configure serial port settings for BK Precision devices
            # Baud rate: 9600, Data bits: 8, Parity: None, Stop bits: 1
            if "ASRL" in self.resource_string:  # Serial/ASRL connection
                self.instrument.baud_rate = 9600
                self.instrument.data_bits = 8
                self.instrument.parity = 0  # None
                self.instrument.stop_bits = 10  # 1 stop bit (constant value)
                self.instrument.flow_control = 0  # None
                # BK Precision 1900B series uses CR only (not CR+LF)
                self.instrument.read_termination = '\r'
                self.instrument.write_termination = '\r'
                logger.info(f"Configured serial port: 9600 8N1 with CR termination")

            # Set timeout (2 seconds - BK responds quickly)
            self.instrument.timeout = 2000

            # Verify connection with GMAX command (BK Precision proprietary)
            # GMAX returns max voltage and current: VVVCCC format
            try:
                gmax_response = await self._bk_query("GMAX")
                logger.info(f"Connected to BK device, GMAX response: {gmax_response}")
            except Exception as e:
                logger.warning(f"GMAX query failed: {e}, attempting connection anyway")

            self.connected = True

            # Cache equipment info
            self.cached_info = await self.get_info()

        except Exception as e:
            logger.error(f"Failed to connect to {self.resource_string}: {e}")
            self.connected = False
            raise

    def _initialize_safety(self, equipment_id: str):
        """Initialize safety validator with appropriate limits."""
        if not settings.enable_safety_limits:
            logger.info(f"Safety limits disabled for {equipment_id}")
            return

        # Get default limits for power supply
        default_limits = get_default_limits("power_supply")

        # Override with equipment-specific limits
        safety_limits = SafetyLimits(
            max_voltage=self.max_voltage,
            max_current=self.max_current,
            max_power=default_limits.max_power,
            voltage_slew_rate=(
                default_limits.voltage_slew_rate if settings.enforce_slew_rate else None
            ),
            current_slew_rate=(
                default_limits.current_slew_rate if settings.enforce_slew_rate else None
            ),
            require_interlock=False,
        )

        self.safety_validator = SafetyValidator(safety_limits, equipment_id)
        logger.info(f"Safety validator initialized for {equipment_id}")

    async def get_info(self) -> EquipmentInfo:
        """Get power supply information."""
        # BK Precision 1900B series doesn't support *IDN? - use model info
        manufacturer = self.manufacturer
        model = self.model
        serial = None

        # Try to get GMAX to verify connection and get max values
        try:
            gmax_response = await self._bk_query("GMAX")
            # GMAX format: VVVCCC (voltage*10, current*10)
            if len(gmax_response) >= 6:
                max_v = int(gmax_response[:3]) / 10.0
                max_i = int(gmax_response[3:6]) / 10.0
                logger.info(f"Verified BK device: max {max_v}V, {max_i}A")
        except Exception as e:
            logger.warning(f"Could not query GMAX: {e}")

        # Generate deterministic ID from resource string
        from .base import generate_equipment_id
        equipment_id = generate_equipment_id(self.resource_string, "ps_")

        # Initialize safety validator
        self._initialize_safety(equipment_id)

        return EquipmentInfo(
            id=equipment_id,
            type=EquipmentType.POWER_SUPPLY,
            manufacturer=manufacturer,
            model=model,
            serial_number=serial,
            connection_type=self._determine_connection_type(),
            resource_string=self.resource_string,
        )

    async def get_status(self) -> EquipmentStatus:
        """Get power supply status."""
        # Try to get firmware info from *IDN?, but don't fail if it doesn't work
        firmware = None
        try:
            idn = await self._query("*IDN?")
            parts = idn.split(",")
            firmware = parts[3] if len(parts) > 3 else None
        except Exception:
            # *IDN? not supported or timed out, continue without firmware info
            pass

        capabilities = {
            "num_channels": self.num_channels,
            "max_voltage": self.max_voltage,
            "max_current": self.max_current,
        }

        return EquipmentStatus(
            id=self.cached_info.id if self.cached_info else "unknown",
            connected=self.connected,
            firmware_version=firmware,
            capabilities=capabilities,
        )

    async def execute_command(self, command: str, parameters: dict) -> Any:
        """Execute a command on the power supply."""
        if command == "set_voltage":
            return await self.set_voltage(**parameters)
        elif command == "set_current":
            return await self.set_current(**parameters)
        elif command == "set_output":
            return await self.set_output(**parameters)
        elif command == "get_readings":
            return await self.get_readings(**parameters)
        elif command == "get_setpoints":
            return await self.get_setpoints(**parameters)
        else:
            raise ValueError(f"Unknown command: {command}")

    async def set_voltage(self, voltage: float, channel: int = 1):
        """Set output voltage."""
        # Check emergency stop
        if emergency_stop_manager.is_active():
            raise RuntimeError("Emergency stop is active - operation blocked")

        # Basic range check
        if voltage < 0 or voltage > self.max_voltage:
            raise ValueError(f"Voltage must be between 0 and {self.max_voltage}V")

        # Safety checks if enabled
        if self.safety_validator and settings.enable_safety_limits:
            # Check voltage limits
            self.safety_validator.check_voltage(voltage)

            # Apply slew rate limiting
            if settings.enforce_slew_rate:
                voltage = await self.safety_validator.apply_voltage_slew_limit(
                    voltage, self._current_voltage
                )

        await self._write(f"VOLT{self._encode_voltage(voltage)}")
        self._current_voltage = voltage

    async def set_current(self, current: float, channel: int = 1):
        """Set current limit."""
        # Check emergency stop
        if emergency_stop_manager.is_active():
            raise RuntimeError("Emergency stop is active - operation blocked")

        # Basic range check
        if current < 0 or current > self.max_current:
            raise ValueError(f"Current must be between 0 and {self.max_current}A")

        # Safety checks if enabled
        if self.safety_validator and settings.enable_safety_limits:
            # Check current limits
            self.safety_validator.check_current(current)

            # Apply slew rate limiting
            if settings.enforce_slew_rate:
                current = await self.safety_validator.apply_current_slew_limit(
                    current, self._current_current
                )

        await self._write(f"CURR{self._encode_current(current)}")
        self._current_current = current

    async def set_output(self, enabled: bool, channel: int = 1):
        """Enable or disable output."""
        # Check emergency stop (only when enabling output)
        if enabled and emergency_stop_manager.is_active():
            raise RuntimeError("Emergency stop is active - cannot enable output")

        # SOUT polarity is dialect-specific: 0 enables the output on the
        # 1685B/1900B lines, and disables it on the 9103/9104.
        await self._write(
            f"SOUT{self.dialect.sout_on if enabled else self.dialect.sout_off}"
        )

    async def get_readings(self, channel: int = 1) -> PowerSupplyData:
        """Get current voltage and current readings using BK Precision protocol."""
        # GETD returns: VVVVIIIIIM (voltage*100, current*1000, mode)
        getd_response = await self._bk_query("GETD")

        if len(getd_response) < 9:
            raise ValueError(f"Invalid GETD response: {getd_response}")

        voltage = int(getd_response[:4]) / self.dialect.reading_voltage_divisor
        current = int(getd_response[4:8]) / self.dialect.reading_current_divisor
        mode = int(getd_response[8])  # 0=CV, 1=CC

        # GOUT mirrors SOUT, so its polarity is dialect-specific too.
        gout_response = await self._bk_query("GOUT")
        output_enabled = gout_response.strip() == self.dialect.sout_on

        # Get setpoints: GETS returns VVVCCC (voltage*10, current*10)
        gets_response = await self._bk_query("GETS")

        voltage_set, current_set = self._decode_setpoints(gets_response)

        # Determine CV/CC mode from mode byte
        in_cc_mode = (mode == 1)
        in_cv_mode = (mode == 0)

        return PowerSupplyData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            channel=channel,
            voltage_set=voltage_set,
            current_set=current_set,
            voltage_actual=voltage,
            current_actual=current,
            output_enabled=output_enabled,
            in_cv_mode=in_cv_mode,
            in_cc_mode=in_cc_mode,
        )

    async def get_setpoints(self, channel: int = 1) -> Dict[str, float]:
        """Get voltage and current setpoints using BK Precision protocol."""
        # GETS returns: VVVCCC (voltage*10, current*10)
        gets_response = await self._bk_query("GETS")
        voltage_set, current_set = self._decode_setpoints(gets_response)

        return {
            "voltage": voltage_set,
            "current": current_set,
        }


class BK9206B(BKSCPIPowerSupply):
    """BK Precision 9206B Multi-Range DC Power Supply.

    A USBTMC SCPI instrument, like its 9205B sibling. It previously inherited
    the fixed-width base and so spoke ``GETD``/``GETS``/``SOUT`` — the legacy
    1685B protocol, which this supply does not implement.
    """

    def __init__(self, resource_manager, resource_string: str):
        super().__init__(resource_manager, resource_string, model="9206B")
        self.model = "9206B"
        self.num_channels = 1
        # Multi-range: 60V/5A or 120V/2.5A
        self.max_voltage = 120.0
        self.max_current = 5.0


class BK9130B(BK9130Series):
    """BK Precision 9130B/9131B/9132B triple output DC power supply.

    This is a SCPI instrument, not a fixed-width one. It previously inherited
    the legacy base, which meant its readings went out as ``GETD``/``GETS`` —
    commands a 9130B does not implement — while its setters went out as SCPI.
    Reads therefore failed against real hardware even though writes worked.
    """

    def __init__(self, resource_manager, resource_string: str):
        super().__init__(resource_manager, resource_string, model="9130B")
        self.num_channels = 3
        # CH1/CH2 reach 30 V; CH3 is the 5 V logic rail (see
        # channel_max_voltage on BK9130Series).
        self.max_voltage = 30.0
        self.max_current = 3.0


class BK9205B(BaseEquipment):
    """Driver for BK Precision 9205B Multi-Range DC Power Supply.

    Note: The BK 9205B uses standard SCPI commands via USB, unlike older
    BK models (1685B, 1902B) which use proprietary serial protocol.
    """

    def __init__(self, resource_manager, resource_string: str):
        """Initialize BK 9205B."""
        super().__init__(resource_manager, resource_string)
        self.manufacturer = "BK Precision"
        self.model = "9205B"
        self.num_channels = 1
        # Multi-range: 60V/10A or 120V/5A
        self.max_voltage = 120.0
        self.max_current = 10.0

        # Initialize safety validator
        self.safety_validator = None
        self._current_voltage = 0.0
        self._current_current = 0.0

    async def connect(self):
        """Connect to the BK 9205B power supply."""
        try:
            # Refresh resource manager if needed
            self._refresh_resource_manager()

            # Close old instrument if it exists
            if self.instrument is not None:
                try:
                    self.instrument.close()
                except Exception:
                    pass
                self.instrument = None

            # Open the resource
            self.instrument = self.resource_manager.open_resource(
                self.resource_string
            )

            # Set timeout and termination for USB/SCPI communication
            self.instrument.timeout = 5000  # 5 seconds
            self.instrument.write_termination = '\n'
            self.instrument.read_termination = '\n'

            # Verify connection with *IDN?
            idn = await self._query("*IDN?")
            logger.info(f"Connected to BK 9205B: {idn}")

            # Check for errors
            error = await self._query("SYST:ERR?")
            if not error.startswith("0"):
                logger.warning(f"Device error after connect: {error}")

            self.connected = True

            # Cache equipment info
            self.cached_info = await self.get_info()

        except Exception as e:
            error_msg = str(e).lower()

            # If device not found, provide diagnostic information
            if "not found" in error_msg or "no device" in error_msg:
                from server.utils.usb_diagnostics import log_usb_diagnostics
                logger.error(f"Device not found at {self.resource_string}")
                log_usb_diagnostics(self.resource_string)
                logger.error(
                    "\n" + "=" * 70 + "\n"
                    "USB DEVICE CONNECTION FAILED\n"
                    "=" * 70 + "\n"
                    "If the serial number is unreadable (shows as ???), this indicates\n"
                    "a USB communication issue after long server uptime.\n\n"
                    "COMMON FIXES:\n"
                    "  1. Unplug and replug the USB device\n"
                    "  2. Restart the LabLink server\n"
                    "  3. Check USB cable and connection quality\n"
                    "  4. Update device firmware if available\n"
                    "  5. Run 'USB Device Diagnostics' from the client's Diagnostic tab\n"
                    "=" * 70
                )

            logger.error(f"Failed to connect to {self.resource_string}: {e}")
            self.connected = False
            raise

    def _initialize_safety(self, equipment_id: str):
        """Initialize safety validator with appropriate limits."""
        if not settings.enable_safety_limits:
            logger.info(f"Safety limits disabled for {equipment_id}")
            return

        # Get default limits for power supply
        default_limits = get_default_limits("power_supply")

        # Override with equipment-specific limits
        safety_limits = SafetyLimits(
            max_voltage=self.max_voltage,
            max_current=self.max_current,
            max_power=default_limits.max_power,
            voltage_slew_rate=(
                default_limits.voltage_slew_rate if settings.enforce_slew_rate else None
            ),
            current_slew_rate=(
                default_limits.current_slew_rate if settings.enforce_slew_rate else None
            ),
            require_interlock=False,
        )

        self.safety_validator = SafetyValidator(safety_limits, equipment_id)
        logger.info(f"Safety validator initialized for {equipment_id}")

    async def get_info(self) -> EquipmentInfo:
        """Get power supply information."""
        try:
            idn = await self._query("*IDN?")
            # *IDN? returns: B&K Precision, 9205B, SERIAL, FIRMWARE
            parts = idn.split(",")
            manufacturer = parts[0].strip() if len(parts) > 0 else self.manufacturer
            model = parts[1].strip() if len(parts) > 1 else self.model
            serial = parts[2].strip() if len(parts) > 2 else None
        except Exception as e:
            logger.warning(f"Could not query *IDN?: {e}")
            manufacturer = self.manufacturer
            model = self.model
            serial = None

        # Generate deterministic ID from resource string
        from .base import generate_equipment_id
        equipment_id = generate_equipment_id(self.resource_string, "ps_")

        # Initialize safety validator
        self._initialize_safety(equipment_id)

        return EquipmentInfo(
            id=equipment_id,
            type=EquipmentType.POWER_SUPPLY,
            manufacturer=manufacturer,
            model=model,
            serial_number=serial,
            connection_type=self._determine_connection_type(),
            resource_string=self.resource_string,
        )

    async def get_status(self) -> EquipmentStatus:
        """Get power supply status."""
        firmware = None
        try:
            idn = await self._query("*IDN?")
            parts = idn.split(",")
            firmware = parts[3].strip() if len(parts) > 3 else None
        except Exception:
            pass

        capabilities = {
            "num_channels": self.num_channels,
            "max_voltage": self.max_voltage,
            "max_current": self.max_current,
        }

        return EquipmentStatus(
            id=self.cached_info.id if self.cached_info else "unknown",
            connected=self.connected,
            firmware_version=firmware,
            capabilities=capabilities,
        )

    async def execute_command(self, command: str, parameters: dict) -> Any:
        """Execute a command on the power supply."""
        if command == "set_voltage":
            return await self.set_voltage(**parameters)
        elif command == "set_current":
            return await self.set_current(**parameters)
        elif command == "set_output":
            return await self.set_output(**parameters)
        elif command == "get_readings":
            return await self.get_readings(**parameters)
        elif command == "get_setpoints":
            return await self.get_setpoints(**parameters)
        else:
            raise ValueError(f"Unknown command: {command}")

    async def set_voltage(self, voltage: float, channel: int = 1):
        """Set output voltage using SCPI."""
        # Check emergency stop
        if emergency_stop_manager.is_active():
            raise RuntimeError("Emergency stop is active - operation blocked")

        # Basic range check
        if voltage < 0 or voltage > self.max_voltage:
            raise ValueError(f"Voltage must be between 0 and {self.max_voltage}V")

        # Safety checks if enabled
        if self.safety_validator and settings.enable_safety_limits:
            self.safety_validator.check_voltage(voltage)

            if settings.enforce_slew_rate:
                voltage = await self.safety_validator.apply_voltage_slew_limit(
                    voltage, self._current_voltage
                )

        # SCPI command
        await self._write(f"VOLT {voltage}")
        self._current_voltage = voltage

    async def set_current(self, current: float, channel: int = 1):
        """Set current limit using SCPI."""
        # Check emergency stop
        if emergency_stop_manager.is_active():
            raise RuntimeError("Emergency stop is active - operation blocked")

        # Basic range check
        if current < 0 or current > self.max_current:
            raise ValueError(f"Current must be between 0 and {self.max_current}A")

        # Safety checks if enabled
        if self.safety_validator and settings.enable_safety_limits:
            self.safety_validator.check_current(current)

            if settings.enforce_slew_rate:
                current = await self.safety_validator.apply_current_slew_limit(
                    current, self._current_current
                )

        # SCPI command
        await self._write(f"CURR {current}")
        self._current_current = current

    async def set_output(self, enabled: bool, channel: int = 1):
        """Enable or disable output using SCPI."""
        # Check emergency stop (only when enabling output)
        if enabled and emergency_stop_manager.is_active():
            raise RuntimeError("Emergency stop is active - cannot enable output")

        # SCPI command
        await self._write(f"OUTP {'ON' if enabled else 'OFF'}")

    async def get_readings(self, channel: int = 1) -> PowerSupplyData:
        """Get current voltage and current readings using SCPI."""
        # Query actual measurements
        voltage = float(await self._query("MEAS:VOLT?"))
        current = float(await self._query("MEAS:CURR?"))

        # Query setpoints
        voltage_set = float(await self._query("VOLT?"))
        current_set = float(await self._query("CURR?"))

        # Query output state
        output_response = await self._query("OUTP?")
        output_enabled = output_response.strip() in ["1", "ON"]

        # Determine CV/CC mode based on actual vs setpoint
        # If actual voltage is close to setpoint, we're in CV mode
        # If actual current is close to limit, we're in CC mode
        voltage_tolerance = 0.1  # 100mV
        current_tolerance = 0.01  # 10mA

        in_cv_mode = abs(voltage - voltage_set) < voltage_tolerance
        in_cc_mode = abs(current - current_set) < current_tolerance and current > 0.01

        return PowerSupplyData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            channel=channel,
            voltage_set=voltage_set,
            current_set=current_set,
            voltage_actual=voltage,
            current_actual=current,
            output_enabled=output_enabled,
            in_cv_mode=in_cv_mode,
            in_cc_mode=in_cc_mode,
        )

    async def get_setpoints(self, channel: int = 1) -> Dict[str, float]:
        """Get voltage and current setpoints using SCPI."""
        voltage_set = float(await self._query("VOLT?"))
        current_set = float(await self._query("CURR?"))

        return {
            "voltage": voltage_set,
            "current": current_set,
        }


class BK1685B(BKPowerSupplyBase):
    """Driver for BK Precision 1685B DC Power Supply."""

    def __init__(self, resource_manager, resource_string: str):
        """Initialize BK 1685B."""
        super().__init__(resource_manager, resource_string)
        self.model = "1685B"
        self.num_channels = 1
        # 1685B specs: 0-18V, 0-5A
        self.max_voltage = 18.0
        self.max_current = 5.0
        # Two decimal places for current on this model alone.
        self.dialect = DIALECT_1685B


class BK1902B(BKPowerSupplyBase):
    """Driver for BK Precision 1902B DC Power Supply."""

    def __init__(self, resource_manager, resource_string: str):
        """Initialize BK 1902B."""
        super().__init__(resource_manager, resource_string)
        self.model = "1902B"
        self.num_channels = 1
        # 1902B specs: 1-60V, 0-15A, 900W
        self.max_voltage = 60.0
        self.max_current = 15.0
        self.dialect = DIALECT_STANDARD


class BK1687B(BKPowerSupplyBase):
    """BK Precision 1687B DC power supply (0-60V, 0-8.5A)."""

    def __init__(self, resource_manager, resource_string: str):
        super().__init__(resource_manager, resource_string)
        self.model = "1687B"
        self.max_voltage = 60.0
        self.max_current = 8.5
        self.dialect = DIALECT_STANDARD


class BK1688B(BKPowerSupplyBase):
    """BK Precision 1688B DC power supply (0-36V, 0-14A)."""

    def __init__(self, resource_manager, resource_string: str):
        super().__init__(resource_manager, resource_string)
        self.model = "1688B"
        self.max_voltage = 36.0
        self.max_current = 14.0
        self.dialect = DIALECT_STANDARD


class BK1901B(BKPowerSupplyBase):
    """BK Precision 1901B DC power supply (0-35V, 0-30A)."""

    def __init__(self, resource_manager, resource_string: str):
        super().__init__(resource_manager, resource_string)
        self.model = "1901B"
        self.max_voltage = 35.0
        self.max_current = 30.0
        self.dialect = DIALECT_STANDARD


class BK9103(BKPowerSupplyBase):
    """BK Precision 9103/9104 multi-range DC power supply.

    Fixed-width like the 1685B, but a different dialect throughout: VOLT and
    CURR take a leading preset index with four-digit two-decimal fields, and
    ``SOUT1`` — not ``SOUT0`` — enables the output. Driving one with the
    1685B dialect turns the output off when asked to turn it on.
    """

    #: Preset slot the driver programs. Slot 0 is the live output.
    PRESET = 0

    def __init__(self, resource_manager, resource_string: str,
                 model: str = "9103"):
        super().__init__(resource_manager, resource_string)
        self.model = model
        # 9103: 42V/20A; 9104: 84V/10A. Both are 320 W.
        self.max_voltage = 84.0 if model == "9104" else 42.0
        self.max_current = 10.0 if model == "9104" else 20.0
        self.dialect = DIALECT_PRESET_INDEXED

    async def set_voltage(self, voltage: float, channel: int = 1):
        if emergency_stop_manager.is_active():
            raise RuntimeError("Emergency stop is active - operation blocked")
        if voltage < 0 or voltage > self.max_voltage:
            raise ValueError(f"Voltage must be between 0 and {self.max_voltage}V")
        await self._write(f"VOLT{self.PRESET}{self._encode_voltage(voltage)}")
        self._current_voltage = voltage

    async def set_current(self, current: float, channel: int = 1):
        if emergency_stop_manager.is_active():
            raise RuntimeError("Emergency stop is active - operation blocked")
        if current < 0 or current > self.max_current:
            raise ValueError(f"Current must be between 0 and {self.max_current}A")
        await self._write(f"CURR{self.PRESET}{self._encode_current(current)}")
        self._current_current = current

    async def get_setpoints(self, channel: int = 1) -> Dict[str, float]:
        """GETS on this model needs the preset index it should report."""
        response = await self._bk_query(f"GETS{self.PRESET}")
        voltage_set, current_set = self._decode_setpoints(response)
        return {"voltage": voltage_set, "current": current_set}


class BK9104(BK9103):
    """BK Precision 9104 multi-range DC power supply (0-84V, 0-10A)."""

    def __init__(self, resource_manager, resource_string: str):
        super().__init__(resource_manager, resource_string, model="9104")


class BK1696(BKPowerSupplyBase):
    """BK Precision 1696/1697/1698 DC power supply.

    Fixed-width over RS-232 or RS-485, 9600 8N1, straight-through cable — not
    the null modem the rest of the serial line wants.
    """

    def __init__(self, resource_manager, resource_string: str,
                 model: str = "1696"):
        super().__init__(resource_manager, resource_string)
        self.model = model
        self.max_voltage = 20.0
        self.max_current = 9.99
        self.dialect = DIALECT_STANDARD
