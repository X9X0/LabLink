"""Mock oscilloscope driver for testing without hardware."""

import logging
import uuid
import asyncio
import numpy as np
from typing import Any, Dict, Optional
from datetime import datetime

import sys
sys.path.append("../../../shared")
from models.equipment import EquipmentInfo, EquipmentStatus, EquipmentType, ConnectionType
from models.data import WaveformData

logger = logging.getLogger(__name__)


class MockOscilloscope:
    """Mock oscilloscope that generates realistic waveforms."""

    def __init__(self, resource_manager=None, resource_string: str = "MOCK::SCOPE::0"):
        """Initialize mock oscilloscope."""
        self.resource_string = resource_string
        self.connected = False
        self.cached_info: Optional[EquipmentInfo] = None

        # Oscilloscope parameters
        self.manufacturer = "Mock Instruments"
        self.model = "MockScope-2000"
        self.serial_number = f"MOCK{uuid.uuid4().hex[:8].upper()}"
        self.firmware_version = "v1.0.0-mock"
        self.num_channels = 4

        # Channel settings (channel 1-4)
        self.channel_enabled = {1: True, 2: True, 3: False, 4: False}
        self.channel_scale = {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0}  # V/div
        self.channel_offset = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}  # V
        self.channel_coupling = {1: "DC", 2: "DC", 3: "DC", 4: "DC"}

        # Timebase settings
        self.time_scale = 1e-3  # 1ms/div
        self.time_offset = 0.0

        # Trigger settings
        self.trigger_mode = "AUTO"  # AUTO, NORM, SINGLE
        self.running = True

        # Waveform generation parameters
        self.waveform_type = {1: "sine", 2: "square", 3: "triangle", 4: "noise"}
        self.frequency = {1: 1000.0, 2: 500.0, 3: 250.0, 4: 1000.0}  # Hz
        self.amplitude = {1: 2.0, 2: 3.0, 3: 1.5, 4: 0.5}  # V
        self.noise_level = 0.02  # Noise amplitude in V

        # Acquisition settings
        self.sample_rate = 1e9  # 1 GSa/s
        self.memory_depth = 1000  # Number of points per acquisition

    async def connect(self):
        """Simulate connection to oscilloscope."""
        await asyncio.sleep(0.1)  # Simulate connection delay
        self.connected = True

        # Cache equipment info
        self.cached_info = await self.get_info()
        logger.info(f"Connected to mock oscilloscope: {self.model}")

    async def disconnect(self):
        """Simulate disconnection."""
        await asyncio.sleep(0.05)
        self.connected = False
        logger.info(f"Disconnected from mock oscilloscope")

    async def get_info(self) -> EquipmentInfo:
        """Get oscilloscope information."""
        equipment_id = f"scope_{uuid.uuid4().hex[:8]}"

        return EquipmentInfo(
            id=equipment_id,
            type=EquipmentType.OSCILLOSCOPE,
            manufacturer=self.manufacturer,
            model=self.model,
            serial_number=self.serial_number,
            connection_type=ConnectionType.ETHERNET,
            resource_string=self.resource_string,
        )

    async def get_status(self) -> EquipmentStatus:
        """Get oscilloscope status."""
        try:
            capabilities = {
                "num_channels": self.num_channels,
                "bandwidth": "200MHz",
                "sample_rate": f"{self.sample_rate/1e9:.0f}GSa/s",
                "memory_depth": f"{self.memory_depth}pts",
                "waveform_types": ["sine", "square", "triangle", "noise"],
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
        """Execute a command on the oscilloscope."""
        if not self.connected:
            raise RuntimeError("Mock oscilloscope not connected")

        if command == "get_waveform":
            return await self.get_waveform(**parameters)
        elif command == "get_waveform_raw":
            return await self.get_waveform_raw(**parameters)
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

    def _generate_waveform(self, channel: int, num_points: int) -> np.ndarray:
        """Generate realistic waveform data."""
        # Time array
        duration = num_points / self.sample_rate
        t = np.linspace(0, duration, num_points)

        # Get waveform parameters
        waveform_type = self.waveform_type.get(channel, "sine")
        freq = self.frequency.get(channel, 1000.0)
        amp = self.amplitude.get(channel, 1.0)
        offset = self.channel_offset.get(channel, 0.0)

        # Generate base waveform
        if waveform_type == "sine":
            waveform = amp * np.sin(2 * np.pi * freq * t)
        elif waveform_type == "square":
            waveform = amp * np.sign(np.sin(2 * np.pi * freq * t))
        elif waveform_type == "triangle":
            waveform = amp * (2 * np.abs(2 * (freq * t - np.floor(freq * t + 0.5))) - 1)
        elif waveform_type == "noise":
            waveform = np.random.normal(0, amp, num_points)
        else:
            waveform = np.zeros(num_points)

        # Add noise
        noise = np.random.normal(0, self.noise_level, num_points)
        waveform = waveform + noise + offset

        return waveform

    async def get_waveform(self, channel: int = 1) -> WaveformData:
        """Get waveform metadata from a channel."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        if not self.channel_enabled.get(channel, False):
            raise ValueError(f"Channel {channel} is not enabled")

        # Simulate acquisition delay
        await asyncio.sleep(0.05)

        # Calculate number of points
        num_points = self.memory_depth

        # Time increment
        x_increment = 1.0 / self.sample_rate

        # Create waveform data object
        data_id = f"waveform_{uuid.uuid4().hex[:8]}"

        waveform_data = WaveformData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            channel=channel,
            sample_rate=self.sample_rate,
            time_scale=self.time_scale,
            voltage_scale=self.channel_scale.get(channel, 1.0),
            voltage_offset=self.channel_offset.get(channel, 0.0),
            num_samples=num_points,
            data_id=data_id,
        )

        return waveform_data

    async def get_waveform_raw(self, channel: int = 1) -> bytes:
        """Get raw waveform data."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        # Simulate acquisition delay
        await asyncio.sleep(0.05)

        # Generate waveform
        waveform = self._generate_waveform(channel, self.memory_depth)

        # Convert to 8-bit unsigned data (typical for oscilloscopes)
        # Map voltage to 0-255 range
        scale = self.channel_scale.get(channel, 1.0)
        offset = self.channel_offset.get(channel, 0.0)

        # Normalize to 8-bit range
        waveform_normalized = ((waveform - offset) / (scale * 10) + 0.5) * 255
        waveform_normalized = np.clip(waveform_normalized, 0, 255).astype(np.uint8)

        return bytes(waveform_normalized)

    async def set_timebase(self, scale: float, offset: float = 0.0):
        """Set timebase settings."""
        if scale <= 0:
            raise ValueError("Time scale must be positive")

        self.time_scale = scale
        self.time_offset = offset
        await asyncio.sleep(0.01)

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

        if coupling not in ["DC", "AC", "GND"]:
            raise ValueError("Coupling must be DC, AC, or GND")

        self.channel_enabled[channel] = enabled
        self.channel_scale[channel] = scale
        self.channel_offset[channel] = offset
        self.channel_coupling[channel] = coupling

        await asyncio.sleep(0.01)

    async def trigger_single(self):
        """Set trigger to single mode."""
        self.trigger_mode = "SINGLE"
        self.running = False
        await asyncio.sleep(0.01)

    async def trigger_run(self):
        """Start continuous triggering."""
        self.trigger_mode = "AUTO"
        self.running = True
        await asyncio.sleep(0.01)

    async def trigger_stop(self):
        """Stop triggering."""
        self.running = False
        await asyncio.sleep(0.01)

    async def autoscale(self):
        """Simulate autoscale operation."""
        # Auto-adjust scales based on signal amplitude
        await asyncio.sleep(0.5)  # Simulate autoscale time

        for channel in range(1, self.num_channels + 1):
            if self.channel_enabled.get(channel, False):
                amp = self.amplitude.get(channel, 1.0)
                # Set scale to show about 8 divisions of signal
                self.channel_scale[channel] = amp / 3.0

    async def get_measurement(self, channel: str) -> Dict[str, float]:
        """Get single measurement value for data acquisition.

        Args:
            channel: Channel identifier (e.g., 'CH1', 'CH2', or just '1', '2')

        Returns:
            Dict with 'value' key containing the instantaneous voltage reading
        """
        # Parse channel number from string (handle 'CH1' or '1' format)
        channel_num = int(channel.replace('CH', '').replace('ch', ''))

        if channel_num < 1 or channel_num > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        # Generate a single sample point for this channel
        waveform_type = self.waveform_type.get(channel_num, "sine")
        freq = self.frequency.get(channel_num, 1000.0)
        amp = self.amplitude.get(channel_num, 1.0)
        offset = self.channel_offset.get(channel_num, 0.0)

        # Get current time-dependent value
        t = datetime.now().timestamp()

        if waveform_type == "sine":
            value = amp * np.sin(2 * np.pi * freq * t)
        elif waveform_type == "square":
            value = amp * np.sign(np.sin(2 * np.pi * freq * t))
        elif waveform_type == "triangle":
            value = amp * (2 * np.abs(2 * (freq * t - np.floor(freq * t + 0.5))) - 1)
        elif waveform_type == "noise":
            value = np.random.normal(0, amp)
        else:
            value = 0.0

        # Add noise and offset
        noise = np.random.normal(0, self.noise_level)
        value = float(value + noise + offset)

        return {"value": value}

    async def get_measurements(self, channel: int = 1) -> Dict[str, float]:
        """Get automated measurements for a channel."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        if not self.channel_enabled.get(channel, False):
            raise ValueError(f"Channel {channel} is not enabled")

        # Simulate measurement delay
        await asyncio.sleep(0.1)

        # Generate a waveform to measure
        waveform = self._generate_waveform(channel, 1000)

        # Calculate measurements
        vpp = np.max(waveform) - np.min(waveform)
        vmax = np.max(waveform)
        vmin = np.min(waveform)
        vavg = np.mean(waveform)
        vrms = np.sqrt(np.mean(waveform**2))

        # Frequency from configured value
        freq = self.frequency.get(channel, 1000.0)
        period = 1.0 / freq if freq > 0 else 0.0

        measurements = {
            "vpp": float(vpp),
            "vmax": float(vmax),
            "vmin": float(vmin),
            "vavg": float(vavg),
            "vrms": float(vrms),
            "freq": float(freq),
            "period": float(period),
        }

        return measurements

    # Additional methods for controlling mock behavior
    def set_waveform_type(self, channel: int, waveform_type: str):
        """Set the waveform type for a channel (sine, square, triangle, noise)."""
        if waveform_type not in ["sine", "square", "triangle", "noise"]:
            raise ValueError("Invalid waveform type")
        self.waveform_type[channel] = waveform_type

    def set_signal_frequency(self, channel: int, frequency: float):
        """Set the signal frequency for a channel."""
        if frequency <= 0:
            raise ValueError("Frequency must be positive")
        self.frequency[channel] = frequency

    def set_signal_amplitude(self, channel: int, amplitude: float):
        """Set the signal amplitude for a channel."""
        if amplitude < 0:
            raise ValueError("Amplitude must be non-negative")
        self.amplitude[channel] = amplitude
