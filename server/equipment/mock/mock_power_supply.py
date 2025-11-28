"""Mock power supply driver for testing without hardware."""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import numpy as np

from shared.models.data import PowerSupplyData
from shared.models.equipment import (ConnectionType, EquipmentInfo,
                                     EquipmentStatus, EquipmentType)

logger = logging.getLogger(__name__)


class MockPowerSupply:
    """Mock power supply that simulates realistic behavior."""

    def __init__(self, resource_manager=None, resource_string: str = "MOCK::PSU::0"):
        """Initialize mock power supply."""
        self.resource_string = resource_string
        self.connected = False
        self.cached_info: Optional[EquipmentInfo] = None

        # Power supply parameters
        self.manufacturer = "Mock Instruments"
        self.model = "MockPSU-3030"
        self.serial_number = f"MOCK{uuid.uuid4().hex[:8].upper()}"
        self.firmware_version = "v2.1.0-mock"
        self.num_channels = 3

        # Channel specifications (realistic limits)
        self.max_voltage = {1: 30.0, 2: 30.0, 3: 5.0}  # V
        self.max_current = {1: 3.0, 2: 3.0, 3: 3.0}  # A

        # Channel state
        self.voltage_set = {1: 0.0, 2: 0.0, 3: 0.0}  # Set voltage
        self.current_set = {1: 1.0, 2: 1.0, 3: 1.0}  # Set current limit
        self.output_enabled = {1: False, 2: False, 3: False}

        # Simulated load (resistance) per channel
        self.load_resistance = {1: 10.0, 2: 10.0, 3: 10.0}  # Ohms

        # Measurement noise
        self.voltage_noise = 0.001  # 1mV
        self.current_noise = 0.0001  # 0.1mA

    async def connect(self):
        """Simulate connection to power supply."""
        await asyncio.sleep(0.1)  # Simulate connection delay
        self.connected = True

        # Cache equipment info
        self.cached_info = await self.get_info()
        logger.info(f"Connected to mock power supply: {self.model}")

    async def disconnect(self):
        """Simulate disconnection."""
        await asyncio.sleep(0.05)
        self.connected = False
        logger.info(f"Disconnected from mock power supply")

    async def get_info(self) -> EquipmentInfo:
        """Get power supply information."""
        # Generate deterministic ID from resource string
        from ..base import generate_equipment_id
        equipment_id = generate_equipment_id(self.resource_string, "ps_")

        return EquipmentInfo(
            id=equipment_id,
            type=EquipmentType.POWER_SUPPLY,
            manufacturer=self.manufacturer,
            model=self.model,
            serial_number=self.serial_number,
            connection_type=ConnectionType.USB,
            resource_string=self.resource_string,
        )

    async def get_status(self) -> EquipmentStatus:
        """Get power supply status."""
        try:
            capabilities = {
                "num_channels": self.num_channels,
                "max_voltage": f"{max(self.max_voltage.values())}V",
                "max_current": f"{max(self.max_current.values())}A",
                "channels": {
                    f"ch{i}": {
                        "max_voltage": f"{self.max_voltage[i]}V",
                        "max_current": f"{self.max_current[i]}A",
                    }
                    for i in range(1, self.num_channels + 1)
                },
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
        """Execute a command on the power supply."""
        if not self.connected:
            raise RuntimeError("Mock power supply not connected")

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
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        max_v = self.max_voltage[channel]
        if voltage < 0 or voltage > max_v:
            raise ValueError(f"Voltage must be between 0 and {max_v}V")

        self.voltage_set[channel] = voltage
        await asyncio.sleep(0.02)  # Simulate command delay

    async def set_current(self, current: float, channel: int = 1):
        """Set current limit."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        max_i = self.max_current[channel]
        if current < 0 or current > max_i:
            raise ValueError(f"Current must be between 0 and {max_i}A")

        self.current_set[channel] = current
        await asyncio.sleep(0.02)

    async def set_output(self, enabled: bool, channel: int = 1):
        """Enable or disable output."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        self.output_enabled[channel] = enabled
        await asyncio.sleep(0.05)  # Simulate relay switching delay

    async def get_measurement(self, channel: str) -> Dict[str, float]:
        """Get single measurement value for data acquisition.

        Args:
            channel: Channel identifier (e.g., 'CH1', 'CH2', or just '1', '2')

        Returns:
            Dict with 'value' key containing the output voltage reading
        """
        # Parse channel number from string (handle 'CH1' or '1' format)
        channel_num = int(channel.replace("CH", "").replace("ch", ""))

        if channel_num < 1 or channel_num > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        # Get current voltage output
        readings = await self.get_readings(channel_num)
        return {"value": readings.voltage_actual}

    async def get_readings(self, channel: int = 1) -> PowerSupplyData:
        """Get current voltage and current readings."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        # Simulate measurement delay
        await asyncio.sleep(0.01)

        # Get setpoints
        voltage_set = self.voltage_set[channel]
        current_set = self.current_set[channel]
        output_enabled = self.output_enabled[channel]

        if not output_enabled:
            # Output off - no voltage or current
            voltage_actual = 0.0
            current_actual = 0.0
            in_cv_mode = False
            in_cc_mode = False
        else:
            # Simulate realistic behavior based on load
            load_resistance = self.load_resistance[channel]

            # Calculate what current would flow at set voltage
            ideal_current = (
                voltage_set / load_resistance if load_resistance > 0 else 999.0
            )

            # Determine mode based on current limit
            if ideal_current <= current_set:
                # Constant Voltage mode - load determines current
                in_cv_mode = True
                in_cc_mode = False
                voltage_actual = voltage_set
                current_actual = ideal_current
            else:
                # Constant Current mode - current limited
                in_cv_mode = False
                in_cc_mode = True
                current_actual = current_set
                voltage_actual = current_set * load_resistance

            # Add realistic noise
            voltage_actual += np.random.normal(0, self.voltage_noise)
            current_actual += np.random.normal(0, self.current_noise)

            # Clamp to valid ranges
            voltage_actual = max(0.0, min(voltage_actual, self.max_voltage[channel]))
            current_actual = max(0.0, min(current_actual, self.max_current[channel]))

        return PowerSupplyData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            channel=channel,
            voltage_set=voltage_set,
            current_set=current_set,
            voltage_actual=voltage_actual,
            current_actual=current_actual,
            output_enabled=output_enabled,
            in_cv_mode=in_cv_mode,
            in_cc_mode=in_cc_mode,
        )

    async def get_setpoints(self, channel: int = 1) -> Dict[str, float]:
        """Get voltage and current setpoints."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        return {
            "voltage": self.voltage_set[channel],
            "current": self.current_set[channel],
        }

    # Additional methods for controlling mock behavior
    def set_load_resistance(self, channel: int, resistance: float):
        """Set the simulated load resistance for a channel."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")
        if resistance <= 0:
            raise ValueError("Resistance must be positive")
        self.load_resistance[channel] = resistance

    def simulate_short_circuit(self, channel: int):
        """Simulate a short circuit on a channel."""
        self.load_resistance[channel] = 0.001  # Very low resistance

    def simulate_open_circuit(self, channel: int):
        """Simulate an open circuit on a channel."""
        self.load_resistance[channel] = 1e9  # Very high resistance
