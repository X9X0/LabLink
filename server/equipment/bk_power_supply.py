"""BK Precision power supply drivers."""

import logging
import uuid
from typing import Any, Dict

from server.config.settings import settings
from shared.models.data import PowerSupplyData
from shared.models.equipment import (EquipmentInfo, EquipmentStatus,
                                     EquipmentType)

from .base import BaseEquipment
from .safety import (SafetyLimits, SafetyValidator, emergency_stop_manager,
                     get_default_limits)

logger = logging.getLogger(__name__)


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

        # Initialize safety validator
        self.safety_validator = None
        self._current_voltage = 0.0  # Track current voltage for slew rate limiting
        self._current_current = 0.0  # Track current current for slew rate limiting

    async def connect(self):
        """Connect to the BK power supply with serial port configuration."""
        async with self._lock:
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
                    # BK Precision devices typically use CR+LF termination
                    self.instrument.read_termination = '\r\n'
                    self.instrument.write_termination = '\r\n'
                    logger.info(f"Configured serial port: 9600 8N1 with CR+LF termination")

                # Set timeout (10 seconds)
                self.instrument.timeout = 10000

                # Try to verify connection with IDN query
                # Some BK Precision models may not support *IDN? immediately
                try:
                    idn = await self._query("*IDN?")
                    logger.info(f"Connected to device: {idn}")
                except Exception as e:
                    logger.warning(f"*IDN? query failed: {e}, attempting connection anyway")
                    # Device might not support *IDN? or need initialization
                    # Continue connection attempt

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
        # Try to get IDN, but use defaults if it fails
        manufacturer = self.manufacturer
        model = self.model
        serial = None

        try:
            idn = await self._query("*IDN?")
            parts = idn.split(",")
            manufacturer = parts[0].strip() if len(parts) > 0 else self.manufacturer
            model = parts[1].strip() if len(parts) > 1 else self.model
            serial = parts[2].strip() if len(parts) > 2 else None
            logger.info(f"Got device info from *IDN?: {manufacturer} {model}")
        except Exception as e:
            logger.warning(f"Could not query *IDN?, using defaults: {e}")
            # Use default values set in __init__

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

        # Set voltage
        await self._write(f"VOLT {voltage}")
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

        # Set current
        await self._write(f"CURR {current}")
        self._current_current = current

    async def set_output(self, enabled: bool, channel: int = 1):
        """Enable or disable output."""
        # Check emergency stop (only when enabling output)
        if enabled and emergency_stop_manager.is_active():
            raise RuntimeError("Emergency stop is active - cannot enable output")

        await self._write(f"OUTP {'ON' if enabled else 'OFF'}")

    async def get_readings(self, channel: int = 1) -> PowerSupplyData:
        """Get current voltage and current readings."""
        voltage_str = await self._query("MEAS:VOLT?")
        current_str = await self._query("MEAS:CURR?")

        voltage = float(voltage_str)
        current = float(current_str)

        # Get output state
        output_state = await self._query("OUTP?")
        output_enabled = (
            output_state.strip() == "1" or output_state.strip().upper() == "ON"
        )

        # Get setpoints
        voltage_set_str = await self._query("VOLT?")
        current_set_str = await self._query("CURR?")

        voltage_set = float(voltage_set_str)
        current_set = float(current_set_str)

        # Determine CV/CC mode (if current is close to limit, likely in CC mode)
        in_cc_mode = abs(current - current_set) < 0.01
        in_cv_mode = not in_cc_mode

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
        """Get voltage and current setpoints."""
        voltage_str = await self._query("VOLT?")
        current_str = await self._query("CURR?")

        return {
            "voltage": float(voltage_str),
            "current": float(current_str),
        }


class BK9206B(BKPowerSupplyBase):
    """Driver for BK Precision 9206B Multi-Range DC Power Supply."""

    def __init__(self, resource_manager, resource_string: str):
        """Initialize BK 9206B."""
        super().__init__(resource_manager, resource_string)
        self.model = "9206B"
        self.num_channels = 1
        # Multi-range: 60V/5A or 120V/2.5A
        self.max_voltage = 120.0
        self.max_current = 5.0


class BK9130B(BKPowerSupplyBase):
    """Driver for BK Precision 9130B Triple Output DC Power Supply."""

    def __init__(self, resource_manager, resource_string: str):
        """Initialize BK 9130B."""
        super().__init__(resource_manager, resource_string)
        self.model = "9130B"
        self.num_channels = 3
        # CH1/CH2: 30V/3A, CH3: 5V/3A
        self.max_voltage = 30.0
        self.max_current = 3.0

    async def set_voltage(self, voltage: float, channel: int = 1):
        """Set output voltage for specific channel."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        max_v = 5.0 if channel == 3 else self.max_voltage
        if voltage < 0 or voltage > max_v:
            raise ValueError(
                f"Voltage must be between 0 and {max_v}V for channel {channel}"
            )

        await self._write(f"INST:NSEL {channel}")
        await self._write(f"VOLT {voltage}")

    async def set_current(self, current: float, channel: int = 1):
        """Set current limit for specific channel."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        if current < 0 or current > self.max_current:
            raise ValueError(f"Current must be between 0 and {self.max_current}A")

        await self._write(f"INST:NSEL {channel}")
        await self._write(f"CURR {current}")

    async def set_output(self, enabled: bool, channel: int = 1):
        """Enable or disable output for specific channel."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        await self._write(f"INST:NSEL {channel}")
        await self._write(f"OUTP {'ON' if enabled else 'OFF'}")

    async def get_readings(self, channel: int = 1) -> PowerSupplyData:
        """Get readings for specific channel."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        # Select channel
        await self._write(f"INST:NSEL {channel}")

        # Get readings using base class method
        return await super().get_readings(channel)


class BK9205B(BKPowerSupplyBase):
    """Driver for BK Precision 9205B Multi-Range DC Power Supply."""

    def __init__(self, resource_manager, resource_string: str):
        """Initialize BK 9205B."""
        super().__init__(resource_manager, resource_string)
        self.model = "9205B"
        self.num_channels = 1
        # Multi-range: 60V/10A or 120V/5A
        self.max_voltage = 120.0
        self.max_current = 10.0


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
