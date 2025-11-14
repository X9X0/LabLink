"""BK Precision electronic load driver."""

import logging
import uuid
from typing import Any

from shared.models.data import ElectronicLoadData
from shared.models.equipment import (EquipmentInfo, EquipmentStatus,
                                     EquipmentType)

from .base import BaseEquipment

logger = logging.getLogger(__name__)


class BK1902B(BaseEquipment):
    """Driver for BK Precision 1902B DC Electronic Load."""

    def __init__(self, resource_manager, resource_string: str):
        """Initialize BK 1902B."""
        super().__init__(resource_manager, resource_string)
        self.manufacturer = "BK Precision"
        self.model = "1902B"
        # 1902B specs: 200W, 120V, 30A
        self.max_voltage = 120.0
        self.max_current = 30.0
        self.max_power = 200.0

    async def get_info(self) -> EquipmentInfo:
        """Get electronic load information."""
        idn = await self._query("*IDN?")
        parts = idn.split(",")

        manufacturer = parts[0] if len(parts) > 0 else self.manufacturer
        model = parts[1] if len(parts) > 1 else self.model
        serial = parts[2] if len(parts) > 2 else None

        equipment_id = f"load_{uuid.uuid4().hex[:8]}"

        return EquipmentInfo(
            id=equipment_id,
            type=EquipmentType.ELECTRONIC_LOAD,
            manufacturer=manufacturer,
            model=model,
            serial_number=serial,
            connection_type=self._determine_connection_type(),
            resource_string=self.resource_string,
        )

    async def get_status(self) -> EquipmentStatus:
        """Get electronic load status."""
        try:
            idn = await self._query("*IDN?")
            parts = idn.split(",")
            firmware = parts[3] if len(parts) > 3 else None

            capabilities = {
                "max_voltage": self.max_voltage,
                "max_current": self.max_current,
                "max_power": self.max_power,
                "modes": ["CC", "CV", "CR", "CP"],
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
        """Execute a command on the electronic load."""
        if command == "set_mode":
            return await self.set_mode(**parameters)
        elif command == "set_current":
            return await self.set_current(**parameters)
        elif command == "set_voltage":
            return await self.set_voltage(**parameters)
        elif command == "set_resistance":
            return await self.set_resistance(**parameters)
        elif command == "set_power":
            return await self.set_power(**parameters)
        elif command == "set_input":
            return await self.set_input(**parameters)
        elif command == "get_readings":
            return await self.get_readings()
        else:
            raise ValueError(f"Unknown command: {command}")

    async def set_mode(self, mode: str):
        """Set operating mode (CC, CV, CR, CP)."""
        mode_upper = mode.upper()
        if mode_upper not in ["CC", "CV", "CR", "CP"]:
            raise ValueError("Mode must be CC, CV, CR, or CP")

        await self._write(f"FUNC {mode_upper}")

    async def set_current(self, current: float):
        """Set current in CC mode (Amps)."""
        if current < 0 or current > self.max_current:
            raise ValueError(f"Current must be between 0 and {self.max_current}A")

        await self._write(f"CURR {current}")

    async def set_voltage(self, voltage: float):
        """Set voltage in CV mode (Volts)."""
        if voltage < 0 or voltage > self.max_voltage:
            raise ValueError(f"Voltage must be between 0 and {self.max_voltage}V")

        await self._write(f"VOLT {voltage}")

    async def set_resistance(self, resistance: float):
        """Set resistance in CR mode (Ohms)."""
        if resistance <= 0:
            raise ValueError("Resistance must be greater than 0")

        await self._write(f"RES {resistance}")

    async def set_power(self, power: float):
        """Set power in CP mode (Watts)."""
        if power < 0 or power > self.max_power:
            raise ValueError(f"Power must be between 0 and {self.max_power}W")

        await self._write(f"POW {power}")

    async def set_input(self, enabled: bool):
        """Enable or disable load input."""
        await self._write(f"INP {'ON' if enabled else 'OFF'}")

    async def get_readings(self) -> ElectronicLoadData:
        """Get current readings from the load."""
        # Get mode
        mode = await self._query("FUNC?")
        mode = mode.strip()

        # Get setpoint based on mode
        if mode == "CURR" or mode == "CC":
            setpoint_str = await self._query("CURR?")
            mode = "CC"
        elif mode == "VOLT" or mode == "CV":
            setpoint_str = await self._query("VOLT?")
            mode = "CV"
        elif mode == "RES" or mode == "CR":
            setpoint_str = await self._query("RES?")
            mode = "CR"
        elif mode == "POW" or mode == "CP":
            setpoint_str = await self._query("POW?")
            mode = "CP"
        else:
            setpoint_str = "0"
            mode = "CC"

        setpoint = float(setpoint_str)

        # Get measured values
        voltage_str = await self._query("MEAS:VOLT?")
        current_str = await self._query("MEAS:CURR?")
        power_str = await self._query("MEAS:POW?")

        voltage = float(voltage_str)
        current = float(current_str)
        power = float(power_str)

        # Get input state
        input_state = await self._query("INP?")
        load_enabled = input_state.strip() == "1" or input_state.strip().upper() == "ON"

        return ElectronicLoadData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            mode=mode,
            setpoint=setpoint,
            voltage=voltage,
            current=current,
            power=power,
            load_enabled=load_enabled,
        )
