"""BK Precision power supply drivers."""

import logging
import uuid
from typing import Any, Dict

import sys
sys.path.append("../../shared")
from models.equipment import EquipmentInfo, EquipmentStatus, EquipmentType
from models.data import PowerSupplyData

from .base import BaseEquipment

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

    async def get_info(self) -> EquipmentInfo:
        """Get power supply information."""
        idn = await self._query("*IDN?")
        parts = idn.split(",")

        manufacturer = parts[0] if len(parts) > 0 else self.manufacturer
        model = parts[1] if len(parts) > 1 else self.model
        serial = parts[2] if len(parts) > 2 else None

        equipment_id = f"ps_{uuid.uuid4().hex[:8]}"

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
        try:
            idn = await self._query("*IDN?")
            parts = idn.split(",")
            firmware = parts[3] if len(parts) > 3 else None

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
        except Exception as e:
            return EquipmentStatus(
                id=self.cached_info.id if self.cached_info else "unknown",
                connected=False,
                error=str(e),
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
        if voltage < 0 or voltage > self.max_voltage:
            raise ValueError(f"Voltage must be between 0 and {self.max_voltage}V")

        await self._write(f"VOLT {voltage}")

    async def set_current(self, current: float, channel: int = 1):
        """Set current limit."""
        if current < 0 or current > self.max_current:
            raise ValueError(f"Current must be between 0 and {self.max_current}A")

        await self._write(f"CURR {current}")

    async def set_output(self, enabled: bool, channel: int = 1):
        """Enable or disable output."""
        await self._write(f"OUTP {'ON' if enabled else 'OFF'}")

    async def get_readings(self, channel: int = 1) -> PowerSupplyData:
        """Get current voltage and current readings."""
        voltage_str = await self._query("MEAS:VOLT?")
        current_str = await self._query("MEAS:CURR?")

        voltage = float(voltage_str)
        current = float(current_str)

        # Get output state
        output_state = await self._query("OUTP?")
        output_enabled = output_state.strip() == "1" or output_state.strip().upper() == "ON"

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
            raise ValueError(f"Voltage must be between 0 and {max_v}V for channel {channel}")

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
