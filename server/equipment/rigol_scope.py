"""Rigol oscilloscope driver."""

import logging
import uuid
import numpy as np
from typing import Any, Dict, Optional

import sys
sys.path.append("../../shared")
from models.equipment import EquipmentInfo, EquipmentStatus, EquipmentType
from models.data import WaveformData

from .base import BaseEquipment

logger = logging.getLogger(__name__)


class RigolMSO2072A(BaseEquipment):
    """Driver for Rigol MSO2072A oscilloscope."""

    def __init__(self, resource_manager, resource_string: str):
        """Initialize Rigol scope."""
        super().__init__(resource_manager, resource_string)
        self.model = "MSO2072A"
        self.manufacturer = "Rigol"
        self.num_channels = 2
        self.num_digital = 16

    async def get_info(self) -> EquipmentInfo:
        """Get oscilloscope information."""
        idn = await self._query("*IDN?")
        parts = idn.split(",")

        manufacturer = parts[0] if len(parts) > 0 else self.manufacturer
        model = parts[1] if len(parts) > 1 else self.model
        serial = parts[2] if len(parts) > 2 else None

        equipment_id = f"scope_{uuid.uuid4().hex[:8]}"

        return EquipmentInfo(
            id=equipment_id,
            type=EquipmentType.OSCILLOSCOPE,
            manufacturer=manufacturer,
            model=model,
            serial_number=serial,
            connection_type=self._determine_connection_type(),
            resource_string=self.resource_string,
        )

    async def get_status(self) -> EquipmentStatus:
        """Get oscilloscope status."""
        try:
            # Get basic status
            idn = await self._query("*IDN?")
            parts = idn.split(",")
            firmware = parts[3] if len(parts) > 3 else None

            # Get capabilities
            capabilities = {
                "num_channels": self.num_channels,
                "num_digital": self.num_digital,
                "bandwidth": "70MHz",
                "sample_rate": "2GSa/s",
                "memory_depth": "56Mpts",
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
        """Execute a command on the oscilloscope."""
        if command == "get_waveform":
            return await self.get_waveform(**parameters)
        elif command == "set_timebase":
            return await self.set_timebase(**parameters)
        elif command == "set_channel":
            return await self.set_channel(**parameters)
        elif command == "trigger_single":
            return await self.trigger_single()
        elif command == "trigger_run":
            return await self.trigger_run()
        elif command == "trigger_stop":
            return await self.trigger_stop()
        elif command == "autoscale":
            return await self.autoscale()
        elif command == "get_measurements":
            return await self.get_measurements(**parameters)
        else:
            raise ValueError(f"Unknown command: {command}")

    async def get_waveform(self, channel: int = 1) -> WaveformData:
        """Get waveform data from a channel."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        # Set waveform source
        await self._write(f":WAV:SOUR CHAN{channel}")

        # Set waveform mode to normal
        await self._write(":WAV:MODE NORM")

        # Set format to BYTE
        await self._write(":WAV:FORM BYTE")

        # Get preamble (contains scaling info)
        preamble = await self._query(":WAV:PRE?")
        preamble_parts = preamble.split(",")

        # Parse preamble
        # Format: <format>,<type>,<points>,<count>,<xincrement>,<xorigin>,<xreference>,<yincrement>,<yorigin>,<yreference>
        if len(preamble_parts) >= 10:
            num_points = int(preamble_parts[2])
            x_increment = float(preamble_parts[4])
            x_origin = float(preamble_parts[5])
            y_increment = float(preamble_parts[7])
            y_origin = float(preamble_parts[8])
            y_reference = float(preamble_parts[9])
        else:
            raise ValueError("Invalid preamble format")

        # Get timebase and vertical settings
        time_scale = float(await self._query(":TIM:MAIN:SCAL?"))
        volt_scale = float(await self._query(f":CHAN{channel}:SCAL?"))
        volt_offset = float(await self._query(f":CHAN{channel}:OFFS?"))

        # Get sample rate
        sample_rate = 1.0 / x_increment if x_increment > 0 else 1e9

        # Create waveform data object
        data_id = f"waveform_{uuid.uuid4().hex[:8]}"

        waveform_data = WaveformData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            channel=channel,
            sample_rate=sample_rate,
            time_scale=time_scale,
            voltage_scale=volt_scale,
            voltage_offset=volt_offset,
            num_samples=num_points,
            data_id=data_id,
        )

        # Note: Actual waveform data should be fetched separately via :WAV:DATA?
        # and transmitted via binary WebSocket to avoid overhead

        return waveform_data

    async def get_waveform_raw(self, channel: int = 1) -> bytes:
        """Get raw waveform data."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        # Set waveform source
        await self._write(f":WAV:SOUR CHAN{channel}")
        await self._write(":WAV:MODE NORM")
        await self._write(":WAV:FORM BYTE")

        # Get data
        raw_data = await self._query_binary(":WAV:DATA?")
        return raw_data

    async def set_timebase(self, scale: float, offset: float = 0.0):
        """Set timebase settings."""
        await self._write(f":TIM:MAIN:SCAL {scale}")
        await self._write(f":TIM:MAIN:OFFS {offset}")

    async def set_channel(
        self,
        channel: int,
        enabled: bool = True,
        scale: float = 1.0,
        offset: float = 0.0,
        coupling: str = "DC",
    ):
        """Set channel settings."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        await self._write(f":CHAN{channel}:DISP {'ON' if enabled else 'OFF'}")
        await self._write(f":CHAN{channel}:SCAL {scale}")
        await self._write(f":CHAN{channel}:OFFS {offset}")
        await self._write(f":CHAN{channel}:COUP {coupling}")

    async def trigger_single(self):
        """Set trigger to single mode."""
        await self._write(":SING")

    async def trigger_run(self):
        """Start continuous triggering."""
        await self._write(":RUN")

    async def trigger_stop(self):
        """Stop triggering."""
        await self._write(":STOP")

    async def autoscale(self):
        """Run autoscale."""
        await self._write(":AUT")

    async def get_measurements(self, channel: int = 1) -> Dict[str, float]:
        """Get automated measurements for a channel."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        measurements = {}

        try:
            # Set measurement source
            await self._write(f":MEAS:SOUR CHAN{channel}")

            # Get common measurements
            measurements["vpp"] = float(await self._query(":MEAS:VPP?"))
            measurements["vmax"] = float(await self._query(":MEAS:VMAX?"))
            measurements["vmin"] = float(await self._query(":MEAS:VMIN?"))
            measurements["vavg"] = float(await self._query(":MEAS:VAV?"))
            measurements["vrms"] = float(await self._query(":MEAS:VRMS?"))
            measurements["freq"] = float(await self._query(":MEAS:FREQ?"))
            measurements["period"] = float(await self._query(":MEAS:PER?"))

        except Exception as e:
            logger.error(f"Error getting measurements: {e}")

        return measurements
