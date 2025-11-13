"""Waveform manager for high-speed acquisition and persistence."""

import asyncio
import numpy as np
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import deque
import uuid

from .models import (
    ExtendedWaveformData,
    WaveformCaptureConfig,
    PersistenceConfig,
    PersistenceMode,
    XYPlotData,
)
from .analyzer import WaveformAnalyzer

logger = logging.getLogger(__name__)


class WaveformManager:
    """High-level waveform management and acquisition."""

    def __init__(self, equipment_manager):
        """Initialize waveform manager.

        Args:
            equipment_manager: Reference to equipment manager
        """
        self.equipment_manager = equipment_manager
        self.analyzer = WaveformAnalyzer()

        # Waveform cache (equipment_id -> channel -> latest waveform)
        self.waveform_cache: Dict[str, Dict[int, ExtendedWaveformData]] = {}

        # Persistence buffers (equipment_id -> channel -> deque of waveforms)
        self.persistence_buffers: Dict[str, Dict[int, deque]] = {}
        self.persistence_configs: Dict[str, PersistenceConfig] = {}

        # High-speed acquisition state
        self.acquisition_tasks: Dict[str, asyncio.Task] = {}

        # XY plot cache
        self.xy_plot_cache: Dict[str, XYPlotData] = {}

        logger.info("WaveformManager initialized")

    async def capture_waveform(
        self,
        equipment_id: str,
        config: WaveformCaptureConfig,
    ) -> ExtendedWaveformData:
        """Capture waveform with advanced options.

        Args:
            equipment_id: Equipment identifier
            config: Capture configuration

        Returns:
            ExtendedWaveformData with full waveform
        """
        equipment = self.equipment_manager.get_equipment(equipment_id)
        if not equipment:
            raise ValueError(f"Equipment not found: {equipment_id}")

        waveforms = []

        # Capture multiple waveforms for averaging
        for _ in range(config.num_averages):
            # Get waveform metadata
            waveform_meta = await equipment.execute_command(
                "get_waveform", {"channel": config.channel}
            )

            # Get raw waveform data
            raw_data = await equipment.execute_command(
                "get_waveform_raw", {"channel": config.channel}
            )

            # Convert raw bytes to voltage array
            voltage_data = self._raw_to_voltage(
                raw_data,
                waveform_meta.voltage_scale,
                waveform_meta.voltage_offset,
            )

            # Generate time array
            num_samples = len(voltage_data)
            dt = 1.0 / waveform_meta.sample_rate
            time_data = np.arange(num_samples) * dt

            # Create extended waveform
            waveform = ExtendedWaveformData(
                equipment_id=equipment_id,
                channel=config.channel,
                timestamp=datetime.now(),
                sample_rate=waveform_meta.sample_rate,
                time_scale=waveform_meta.time_scale,
                voltage_scale=waveform_meta.voltage_scale,
                voltage_offset=waveform_meta.voltage_offset,
                num_samples=num_samples,
                data_id=f"waveform_{uuid.uuid4().hex[:8]}",
                time_data=time_data.tolist(),
                voltage_data=voltage_data.tolist(),
            )

            waveforms.append(waveform)

            if config.single_shot:
                break

            # Small delay between captures for averaging
            if config.num_averages > 1:
                await asyncio.sleep(0.05)

        # Average waveforms if requested
        if config.num_averages > 1:
            result_waveform = self._average_waveforms(waveforms)
        else:
            result_waveform = waveforms[0]

        # Apply post-processing
        if config.reduce_points:
            result_waveform = self._decimate_waveform(result_waveform, config.reduce_points)

        if config.apply_smoothing:
            result_waveform = self._smooth_waveform(result_waveform)

        # Cache waveform
        if equipment_id not in self.waveform_cache:
            self.waveform_cache[equipment_id] = {}
        self.waveform_cache[equipment_id][config.channel] = result_waveform

        # Update persistence buffer if enabled
        await self._update_persistence(equipment_id, config.channel, result_waveform)

        return result_waveform

    async def start_continuous_acquisition(
        self,
        equipment_id: str,
        channel: int,
        rate_hz: float = 10.0,
        callback = None,
    ) -> str:
        """Start continuous high-speed waveform acquisition.

        Args:
            equipment_id: Equipment identifier
            channel: Channel number
            rate_hz: Acquisition rate in Hz
            callback: Optional callback function for each waveform

        Returns:
            Acquisition task ID
        """
        task_id = f"acq_{equipment_id}_ch{channel}_{uuid.uuid4().hex[:8]}"

        async def acquisition_loop():
            """Continuous acquisition loop."""
            config = WaveformCaptureConfig(channel=channel, single_shot=False)
            period = 1.0 / rate_hz

            while True:
                try:
                    start_time = asyncio.get_event_loop().time()

                    # Capture waveform
                    waveform = await self.capture_waveform(equipment_id, config)

                    # Call callback if provided
                    if callback:
                        await callback(waveform)

                    # Maintain acquisition rate
                    elapsed = asyncio.get_event_loop().time() - start_time
                    sleep_time = max(0, period - elapsed)
                    await asyncio.sleep(sleep_time)

                except asyncio.CancelledError:
                    logger.info(f"Acquisition {task_id} cancelled")
                    break
                except Exception as e:
                    logger.error(f"Error in acquisition loop: {e}")
                    await asyncio.sleep(1.0)  # Back off on error

        # Start acquisition task
        task = asyncio.create_task(acquisition_loop())
        self.acquisition_tasks[task_id] = task

        logger.info(f"Started continuous acquisition: {task_id}")
        return task_id

    async def stop_continuous_acquisition(self, task_id: str):
        """Stop continuous acquisition.

        Args:
            task_id: Acquisition task ID
        """
        if task_id in self.acquisition_tasks:
            task = self.acquisition_tasks[task_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self.acquisition_tasks[task_id]
            logger.info(f"Stopped acquisition: {task_id}")

    def enable_persistence(
        self,
        equipment_id: str,
        channel: int,
        config: PersistenceConfig,
    ):
        """Enable persistence mode for a channel.

        Args:
            equipment_id: Equipment identifier
            channel: Channel number
            config: Persistence configuration
        """
        # Initialize persistence buffer
        if equipment_id not in self.persistence_buffers:
            self.persistence_buffers[equipment_id] = {}

        if channel not in self.persistence_buffers[equipment_id]:
            self.persistence_buffers[equipment_id][channel] = deque(
                maxlen=config.max_waveforms
            )

        self.persistence_configs[f"{equipment_id}_ch{channel}"] = config
        logger.info(f"Enabled persistence for {equipment_id} channel {channel}")

    def disable_persistence(self, equipment_id: str, channel: int):
        """Disable persistence mode.

        Args:
            equipment_id: Equipment identifier
            channel: Channel number
        """
        key = f"{equipment_id}_ch{channel}"
        if key in self.persistence_configs:
            del self.persistence_configs[key]

        if equipment_id in self.persistence_buffers:
            if channel in self.persistence_buffers[equipment_id]:
                self.persistence_buffers[equipment_id][channel].clear()

        logger.info(f"Disabled persistence for {equipment_id} channel {channel}")

    def get_persistence_data(
        self, equipment_id: str, channel: int
    ) -> Optional[ExtendedWaveformData]:
        """Get accumulated persistence data.

        Args:
            equipment_id: Equipment identifier
            channel: Channel number

        Returns:
            Waveform with persistence overlay, or None
        """
        if equipment_id not in self.persistence_buffers:
            return None

        if channel not in self.persistence_buffers[equipment_id]:
            return None

        buffer = self.persistence_buffers[equipment_id][channel]
        if len(buffer) == 0:
            return None

        key = f"{equipment_id}_ch{channel}"
        config = self.persistence_configs.get(key)

        if not config:
            return None

        # Get persistence overlay based on mode
        if config.mode == PersistenceMode.ENVELOPE:
            return self._calculate_envelope(list(buffer))
        elif config.mode == PersistenceMode.INFINITE:
            return self._overlay_waveforms(list(buffer))
        elif config.mode == PersistenceMode.VARIABLE:
            return self._variable_persistence(list(buffer), config.decay_time)
        else:
            return None

    async def create_xy_plot(
        self,
        equipment_id: str,
        x_channel: int,
        y_channel: int,
    ) -> XYPlotData:
        """Create XY plot from two channels.

        Args:
            equipment_id: Equipment identifier
            x_channel: X-axis channel
            y_channel: Y-axis channel

        Returns:
            XYPlotData
        """
        # Get cached waveforms
        if equipment_id not in self.waveform_cache:
            raise ValueError("No waveforms cached for equipment")

        x_waveform = self.waveform_cache[equipment_id].get(x_channel)
        y_waveform = self.waveform_cache[equipment_id].get(y_channel)

        if not x_waveform or not y_waveform:
            raise ValueError("Both channels must be captured first")

        # Ensure same length
        min_len = min(len(x_waveform.voltage_data), len(y_waveform.voltage_data))
        x_data = x_waveform.voltage_data[:min_len]
        y_data = y_waveform.voltage_data[:min_len]

        xy_plot = XYPlotData(
            equipment_id=equipment_id,
            timestamp=datetime.now(),
            x_channel=x_channel,
            y_channel=y_channel,
            x_data=x_data,
            y_data=y_data,
            num_points=min_len,
        )

        # Cache XY plot
        cache_key = f"{equipment_id}_xy_{x_channel}_{y_channel}"
        self.xy_plot_cache[cache_key] = xy_plot

        return xy_plot

    def get_cached_waveform(
        self, equipment_id: str, channel: int
    ) -> Optional[ExtendedWaveformData]:
        """Get cached waveform.

        Args:
            equipment_id: Equipment identifier
            channel: Channel number

        Returns:
            Cached waveform or None
        """
        if equipment_id in self.waveform_cache:
            return self.waveform_cache[equipment_id].get(channel)
        return None

    def clear_cache(self, equipment_id: Optional[str] = None):
        """Clear waveform cache.

        Args:
            equipment_id: Optional equipment ID (clear all if None)
        """
        if equipment_id:
            if equipment_id in self.waveform_cache:
                del self.waveform_cache[equipment_id]
        else:
            self.waveform_cache.clear()

    # Helper methods
    def _raw_to_voltage(
        self, raw_data: bytes, voltage_scale: float, voltage_offset: float
    ) -> np.ndarray:
        """Convert raw byte data to voltage array.

        Args:
            raw_data: Raw byte data from oscilloscope
            voltage_scale: Voltage scale (V/div)
            voltage_offset: Voltage offset (V)

        Returns:
            Voltage array in volts
        """
        # Convert bytes to numpy array
        data_array = np.frombuffer(raw_data, dtype=np.uint8)

        # Convert to voltage
        # Typical mapping: 0-255 -> -5 to +5 divisions
        normalized = (data_array.astype(float) / 255.0 - 0.5) * 10  # -5 to +5 divisions
        voltage = normalized * voltage_scale + voltage_offset

        return voltage

    def _average_waveforms(
        self, waveforms: List[ExtendedWaveformData]
    ) -> ExtendedWaveformData:
        """Average multiple waveforms.

        Args:
            waveforms: List of waveforms to average

        Returns:
            Averaged waveform
        """
        if not waveforms:
            raise ValueError("No waveforms to average")

        # Use first waveform as template
        result = ExtendedWaveformData(
            equipment_id=waveforms[0].equipment_id,
            channel=waveforms[0].channel,
            timestamp=datetime.now(),
            sample_rate=waveforms[0].sample_rate,
            time_scale=waveforms[0].time_scale,
            voltage_scale=waveforms[0].voltage_scale,
            voltage_offset=waveforms[0].voltage_offset,
            num_samples=waveforms[0].num_samples,
            data_id=f"waveform_avg_{uuid.uuid4().hex[:8]}",
            time_data=waveforms[0].time_data,
            voltage_data=[],
        )

        # Average voltage data
        voltage_arrays = [np.array(w.voltage_data) for w in waveforms]
        avg_voltage = np.mean(voltage_arrays, axis=0)
        result.voltage_data = avg_voltage.tolist()

        return result

    def _decimate_waveform(
        self, waveform: ExtendedWaveformData, target_points: int
    ) -> ExtendedWaveformData:
        """Decimate waveform to reduce number of points.

        Args:
            waveform: Input waveform
            target_points: Target number of points

        Returns:
            Decimated waveform
        """
        if target_points >= len(waveform.voltage_data):
            return waveform

        voltage = np.array(waveform.voltage_data)
        time = np.array(waveform.time_data)

        # Decimate using scipy (anti-aliasing filter)
        from scipy import signal as sp_signal
        factor = len(voltage) // target_points
        if factor > 1:
            voltage_decimated = sp_signal.decimate(voltage, factor)
            time_decimated = sp_signal.decimate(time, factor)
        else:
            voltage_decimated = voltage
            time_decimated = time

        result = ExtendedWaveformData(
            equipment_id=waveform.equipment_id,
            channel=waveform.channel,
            timestamp=waveform.timestamp,
            sample_rate=waveform.sample_rate / factor if factor > 1 else waveform.sample_rate,
            time_scale=waveform.time_scale,
            voltage_scale=waveform.voltage_scale,
            voltage_offset=waveform.voltage_offset,
            num_samples=len(voltage_decimated),
            data_id=f"waveform_dec_{uuid.uuid4().hex[:8]}",
            time_data=time_decimated.tolist(),
            voltage_data=voltage_decimated.tolist(),
        )

        return result

    def _smooth_waveform(
        self, waveform: ExtendedWaveformData, window_size: int = 5
    ) -> ExtendedWaveformData:
        """Apply smoothing filter to waveform.

        Args:
            waveform: Input waveform
            window_size: Smoothing window size

        Returns:
            Smoothed waveform
        """
        voltage = np.array(waveform.voltage_data)

        # Moving average smoothing
        kernel = np.ones(window_size) / window_size
        voltage_smooth = np.convolve(voltage, kernel, mode='same')

        result = ExtendedWaveformData(
            equipment_id=waveform.equipment_id,
            channel=waveform.channel,
            timestamp=waveform.timestamp,
            sample_rate=waveform.sample_rate,
            time_scale=waveform.time_scale,
            voltage_scale=waveform.voltage_scale,
            voltage_offset=waveform.voltage_offset,
            num_samples=waveform.num_samples,
            data_id=f"waveform_smooth_{uuid.uuid4().hex[:8]}",
            time_data=waveform.time_data,
            voltage_data=voltage_smooth.tolist(),
        )

        return result

    async def _update_persistence(
        self, equipment_id: str, channel: int, waveform: ExtendedWaveformData
    ):
        """Update persistence buffer with new waveform.

        Args:
            equipment_id: Equipment identifier
            channel: Channel number
            waveform: New waveform
        """
        key = f"{equipment_id}_ch{channel}"
        if key not in self.persistence_configs:
            return  # Persistence not enabled

        if equipment_id not in self.persistence_buffers:
            self.persistence_buffers[equipment_id] = {}

        if channel not in self.persistence_buffers[equipment_id]:
            config = self.persistence_configs[key]
            self.persistence_buffers[equipment_id][channel] = deque(
                maxlen=config.max_waveforms
            )

        self.persistence_buffers[equipment_id][channel].append(waveform)

    def _calculate_envelope(
        self, waveforms: List[ExtendedWaveformData]
    ) -> ExtendedWaveformData:
        """Calculate min/max envelope from waveforms.

        Args:
            waveforms: List of waveforms

        Returns:
            Envelope waveform (contains min and max as alternating points)
        """
        if not waveforms:
            raise ValueError("No waveforms for envelope")

        voltage_arrays = [np.array(w.voltage_data) for w in waveforms]
        min_envelope = np.min(voltage_arrays, axis=0)
        max_envelope = np.max(voltage_arrays, axis=0)

        # Interleave min and max for visualization
        envelope = np.zeros(len(min_envelope) * 2)
        envelope[0::2] = min_envelope
        envelope[1::2] = max_envelope

        result = ExtendedWaveformData(
            equipment_id=waveforms[0].equipment_id,
            channel=waveforms[0].channel,
            timestamp=datetime.now(),
            sample_rate=waveforms[0].sample_rate,
            time_scale=waveforms[0].time_scale,
            voltage_scale=waveforms[0].voltage_scale,
            voltage_offset=waveforms[0].voltage_offset,
            num_samples=len(envelope),
            data_id=f"envelope_{uuid.uuid4().hex[:8]}",
            time_data=waveforms[0].time_data * 2,  # Duplicate time points
            voltage_data=envelope.tolist(),
        )

        return result

    def _overlay_waveforms(
        self, waveforms: List[ExtendedWaveformData]
    ) -> ExtendedWaveformData:
        """Overlay all waveforms (for infinite persistence).

        Args:
            waveforms: List of waveforms

        Returns:
            Most recent waveform (client handles overlay visualization)
        """
        # Return most recent waveform
        # In a real implementation, this would return all waveforms
        # for the client to overlay
        return waveforms[-1]

    def _variable_persistence(
        self, waveforms: List[ExtendedWaveformData], decay_time: float
    ) -> ExtendedWaveformData:
        """Apply variable persistence with decay.

        Args:
            waveforms: List of waveforms (oldest to newest)
            decay_time: Decay time in seconds

        Returns:
            Weighted average waveform
        """
        if not waveforms:
            raise ValueError("No waveforms for variable persistence")

        now = datetime.now()
        voltage_arrays = []
        weights = []

        for waveform in waveforms:
            # Calculate weight based on age
            age = (now - waveform.timestamp).total_seconds()
            weight = np.exp(-age / decay_time)
            weights.append(weight)
            voltage_arrays.append(np.array(waveform.voltage_data))

        # Weighted average
        weights = np.array(weights)
        weights /= np.sum(weights)  # Normalize

        weighted_avg = np.zeros_like(voltage_arrays[0])
        for i, voltage in enumerate(voltage_arrays):
            weighted_avg += voltage * weights[i]

        result = ExtendedWaveformData(
            equipment_id=waveforms[-1].equipment_id,
            channel=waveforms[-1].channel,
            timestamp=datetime.now(),
            sample_rate=waveforms[-1].sample_rate,
            time_scale=waveforms[-1].time_scale,
            voltage_scale=waveforms[-1].voltage_scale,
            voltage_offset=waveforms[-1].voltage_offset,
            num_samples=len(weighted_avg),
            data_id=f"persistence_{uuid.uuid4().hex[:8]}",
            time_data=waveforms[-1].time_data,
            voltage_data=weighted_avg.tolist(),
        )

        return result
