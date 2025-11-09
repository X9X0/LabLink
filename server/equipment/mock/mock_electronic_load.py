"""Mock electronic load driver for testing without hardware."""

import logging
import uuid
import asyncio
import numpy as np
from typing import Any, Optional
from datetime import datetime

import sys
sys.path.append("../../../shared")
from models.equipment import EquipmentInfo, EquipmentStatus, EquipmentType, ConnectionType
from models.data import ElectronicLoadData

logger = logging.getLogger(__name__)


class MockElectronicLoad:
    """Mock electronic load that simulates realistic behavior."""

    def __init__(self, resource_manager=None, resource_string: str = "MOCK::LOAD::0"):
        """Initialize mock electronic load."""
        self.resource_string = resource_string
        self.connected = False
        self.cached_info: Optional[EquipmentInfo] = None

        # Electronic load parameters
        self.manufacturer = "Mock Instruments"
        self.model = "MockLoad-300"
        self.serial_number = f"MOCK{uuid.uuid4().hex[:8].upper()}"
        self.firmware_version = "v1.5.0-mock"

        # Specifications
        self.max_voltage = 120.0  # V
        self.max_current = 30.0  # A
        self.max_power = 300.0  # W

        # Operating state
        self.mode = "CC"  # CC, CV, CR, CP
        self.setpoint = 0.0  # Value depends on mode
        self.load_enabled = False

        # Mode-specific setpoints
        self.current_setpoint = 1.0  # A
        self.voltage_setpoint = 10.0  # V
        self.resistance_setpoint = 10.0  # Ohms
        self.power_setpoint = 50.0  # W

        # Simulated source (what's connected to the load)
        self.source_voltage = 12.0  # V (simulated power supply)
        self.source_resistance = 0.1  # Ohms (source impedance)

        # Measurement noise
        self.voltage_noise = 0.002  # 2mV
        self.current_noise = 0.001  # 1mA
        self.power_noise = 0.01  # 10mW

    async def connect(self):
        """Simulate connection to electronic load."""
        await asyncio.sleep(0.1)  # Simulate connection delay
        self.connected = True

        # Cache equipment info
        self.cached_info = await self.get_info()
        logger.info(f"Connected to mock electronic load: {self.model}")

    async def disconnect(self):
        """Simulate disconnection."""
        await asyncio.sleep(0.05)
        self.connected = False
        logger.info(f"Disconnected from mock electronic load")

    async def get_info(self) -> EquipmentInfo:
        """Get electronic load information."""
        equipment_id = f"load_{uuid.uuid4().hex[:8]}"

        return EquipmentInfo(
            id=equipment_id,
            type=EquipmentType.ELECTRONIC_LOAD,
            manufacturer=self.manufacturer,
            model=self.model,
            serial_number=self.serial_number,
            connection_type=ConnectionType.USB,
            resource_string=self.resource_string,
        )

    async def get_status(self) -> EquipmentStatus:
        """Get electronic load status."""
        try:
            capabilities = {
                "max_voltage": self.max_voltage,
                "max_current": self.max_current,
                "max_power": self.max_power,
                "modes": ["CC", "CV", "CR", "CP"],
            }

            return EquipmentStatus(
                id=self.cached_info.id if self.cached_info else "unknown",
                connected=self.connected,
                firmware_version=self.firmware_version,
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
        if not self.connected:
            raise RuntimeError("Mock electronic load not connected")

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

        self.mode = mode_upper

        # Update setpoint based on mode
        if self.mode == "CC":
            self.setpoint = self.current_setpoint
        elif self.mode == "CV":
            self.setpoint = self.voltage_setpoint
        elif self.mode == "CR":
            self.setpoint = self.resistance_setpoint
        elif self.mode == "CP":
            self.setpoint = self.power_setpoint

        await asyncio.sleep(0.02)

    async def set_current(self, current: float):
        """Set current in CC mode (Amps)."""
        if current < 0 or current > self.max_current:
            raise ValueError(f"Current must be between 0 and {self.max_current}A")

        self.current_setpoint = current
        if self.mode == "CC":
            self.setpoint = current

        await asyncio.sleep(0.02)

    async def set_voltage(self, voltage: float):
        """Set voltage in CV mode (Volts)."""
        if voltage < 0 or voltage > self.max_voltage:
            raise ValueError(f"Voltage must be between 0 and {self.max_voltage}V")

        self.voltage_setpoint = voltage
        if self.mode == "CV":
            self.setpoint = voltage

        await asyncio.sleep(0.02)

    async def set_resistance(self, resistance: float):
        """Set resistance in CR mode (Ohms)."""
        if resistance <= 0:
            raise ValueError("Resistance must be greater than 0")

        self.resistance_setpoint = resistance
        if self.mode == "CR":
            self.setpoint = resistance

        await asyncio.sleep(0.02)

    async def set_power(self, power: float):
        """Set power in CP mode (Watts)."""
        if power < 0 or power > self.max_power:
            raise ValueError(f"Power must be between 0 and {self.max_power}W")

        self.power_setpoint = power
        if self.mode == "CP":
            self.setpoint = power

        await asyncio.sleep(0.02)

    async def set_input(self, enabled: bool):
        """Enable or disable load input."""
        self.load_enabled = enabled
        await asyncio.sleep(0.05)

    def _calculate_load_state(self):
        """Calculate realistic voltage, current, and power based on mode and source."""
        if not self.load_enabled:
            return 0.0, 0.0, 0.0

        # Start with source parameters
        v_source = self.source_voltage
        r_source = self.source_resistance

        # Calculate based on mode
        if self.mode == "CC":
            # Constant Current mode - draw specified current
            current = self.current_setpoint
            voltage = v_source - (current * r_source)

            # Check if source can provide this current
            if voltage < 0:
                # Source can't provide the current - limit it
                current = v_source / r_source
                voltage = 0.0

        elif self.mode == "CV":
            # Constant Voltage mode - maintain specified voltage
            voltage = self.voltage_setpoint
            current = (v_source - voltage) / r_source if r_source > 0 else 0.0

            # Check validity
            if current < 0:
                current = 0.0
                voltage = v_source

        elif self.mode == "CR":
            # Constant Resistance mode - act as resistor
            resistance = self.resistance_setpoint
            total_r = r_source + resistance
            current = v_source / total_r if total_r > 0 else 0.0
            voltage = current * resistance

        elif self.mode == "CP":
            # Constant Power mode - maintain specified power
            # This is more complex - need to solve quadratic equation
            # P = V * I, and V = V_source - I * R_source
            # P = (V_source - I * R_source) * I
            # P = V_source * I - I^2 * R_source
            # I^2 * R_source - V_source * I + P = 0

            P = self.power_setpoint
            a = r_source
            b = -v_source
            c = P

            if a == 0:
                # No source resistance
                current = P / v_source if v_source > 0 else 0.0
            else:
                discriminant = b**2 - 4*a*c
                if discriminant < 0:
                    # Can't achieve requested power
                    current = v_source / (2 * r_source)
                else:
                    # Take the smaller current solution
                    current = (-b - np.sqrt(discriminant)) / (2 * a)

            voltage = v_source - (current * r_source)

            # Ensure non-negative
            if voltage < 0 or current < 0:
                current = 0.0
                voltage = 0.0

        else:
            voltage = 0.0
            current = 0.0

        # Calculate power
        power = voltage * current

        # Apply limits
        current = min(current, self.max_current)
        voltage = min(voltage, self.max_voltage)
        power = min(power, self.max_power)

        # Ensure power doesn't exceed limit
        if power > self.max_power:
            # Scale back current to stay within power limit
            current = self.max_power / voltage if voltage > 0 else 0.0
            power = voltage * current

        return voltage, current, power

    async def get_readings(self) -> ElectronicLoadData:
        """Get current readings from the load."""
        # Simulate measurement delay
        await asyncio.sleep(0.01)

        # Calculate realistic values
        voltage, current, power = self._calculate_load_state()

        # Add noise
        voltage += np.random.normal(0, self.voltage_noise)
        current += np.random.normal(0, self.current_noise)
        power += np.random.normal(0, self.power_noise)

        # Ensure non-negative
        voltage = max(0.0, voltage)
        current = max(0.0, current)
        power = max(0.0, power)

        return ElectronicLoadData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            mode=self.mode,
            setpoint=self.setpoint,
            voltage=voltage,
            current=current,
            power=power,
            load_enabled=self.load_enabled,
        )

    # Additional methods for controlling mock behavior
    def set_source_voltage(self, voltage: float):
        """Set the simulated source voltage."""
        if voltage < 0:
            raise ValueError("Source voltage must be non-negative")
        self.source_voltage = voltage

    def set_source_resistance(self, resistance: float):
        """Set the simulated source resistance."""
        if resistance < 0:
            raise ValueError("Source resistance must be non-negative")
        self.source_resistance = resistance

    def simulate_power_supply(self, voltage: float, resistance: float = 0.1):
        """Simulate being connected to a power supply."""
        self.set_source_voltage(voltage)
        self.set_source_resistance(resistance)
