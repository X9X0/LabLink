"""Data acquisition manager for coordinating data collection."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import csv
import json

import numpy as np

from .models import (
    AcquisitionConfig,
    AcquisitionSession,
    AcquisitionState,
    AcquisitionMode,
    TriggerType,
    TriggerEdge,
    CircularBuffer,
    DataPoint,
    ExportFormat,
)

logger = logging.getLogger(__name__)


class AcquisitionManager:
    """Manages data acquisition sessions across equipment."""

    def __init__(self):
        self._sessions: Dict[str, AcquisitionSession] = {}
        self._buffers: Dict[str, CircularBuffer] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._export_dir: Optional[Path] = None

    def set_export_directory(self, directory: str):
        """Set directory for data exports."""
        self._export_dir = Path(directory)
        self._export_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Export directory set to: {self._export_dir}")

    async def create_session(
        self,
        equipment,
        config: AcquisitionConfig
    ) -> AcquisitionSession:
        """
        Create a new acquisition session.

        Args:
            equipment: Equipment instance to acquire from
            config: Acquisition configuration

        Returns:
            AcquisitionSession object
        """
        acquisition_id = config.acquisition_id

        # Verify equipment ID matches
        info = await equipment.get_info()
        if config.equipment_id != info.id:
            raise ValueError(
                f"Config equipment_id {config.equipment_id} doesn't match "
                f"equipment {info.id}"
            )

        # Create session
        session = AcquisitionSession(
            acquisition_id=acquisition_id,
            equipment_id=config.equipment_id,
            config=config,
            state=AcquisitionState.IDLE
        )

        # Create circular buffer
        buffer = CircularBuffer(
            size=config.buffer_size,
            num_channels=len(config.channels)
        )

        # Store session and buffer
        self._sessions[acquisition_id] = session
        self._buffers[acquisition_id] = buffer

        logger.info(f"Created acquisition session {acquisition_id} for {config.equipment_id}")

        return session

    async def start_acquisition(
        self,
        acquisition_id: str,
        equipment
    ) -> bool:
        """
        Start data acquisition.

        Args:
            acquisition_id: ID of acquisition session
            equipment: Equipment instance

        Returns:
            True if started successfully
        """
        if acquisition_id not in self._sessions:
            raise ValueError(f"Acquisition {acquisition_id} not found")

        session = self._sessions[acquisition_id]
        config = session.config

        # Check if already running
        if session.state == AcquisitionState.ACQUIRING:
            logger.warning(f"Acquisition {acquisition_id} already running")
            return False

        # Update session state
        session.state = AcquisitionState.WAITING_TRIGGER if config.trigger_config.trigger_type != TriggerType.IMMEDIATE else AcquisitionState.ACQUIRING
        session.started_at = datetime.now()
        session.stats.start_time = session.started_at

        # Start acquisition task
        task = asyncio.create_task(
            self._acquisition_loop(acquisition_id, equipment)
        )
        self._tasks[acquisition_id] = task

        logger.info(f"Started acquisition {acquisition_id}")

        return True

    async def stop_acquisition(self, acquisition_id: str) -> bool:
        """
        Stop data acquisition.

        Args:
            acquisition_id: ID of acquisition session

        Returns:
            True if stopped successfully
        """
        if acquisition_id not in self._sessions:
            raise ValueError(f"Acquisition {acquisition_id} not found")

        session = self._sessions[acquisition_id]

        # Cancel task if running
        if acquisition_id in self._tasks:
            task = self._tasks[acquisition_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self._tasks[acquisition_id]

        # Update session state
        session.state = AcquisitionState.STOPPED
        session.stopped_at = datetime.now()

        if session.stats.start_time:
            session.stats.end_time = session.stopped_at
            session.stats.duration_seconds = (
                session.stopped_at - session.stats.start_time
            ).total_seconds()

        # Auto-export if configured
        if session.config.auto_export:
            await self.export_data(acquisition_id, session.config.export_format)

        logger.info(f"Stopped acquisition {acquisition_id}")

        return True

    async def pause_acquisition(self, acquisition_id: str) -> bool:
        """Pause data acquisition."""
        if acquisition_id not in self._sessions:
            raise ValueError(f"Acquisition {acquisition_id} not found")

        session = self._sessions[acquisition_id]

        if session.state != AcquisitionState.ACQUIRING:
            return False

        session.state = AcquisitionState.PAUSED
        logger.info(f"Paused acquisition {acquisition_id}")

        return True

    async def resume_acquisition(self, acquisition_id: str) -> bool:
        """Resume paused acquisition."""
        if acquisition_id not in self._sessions:
            raise ValueError(f"Acquisition {acquisition_id} not found")

        session = self._sessions[acquisition_id]

        if session.state != AcquisitionState.PAUSED:
            return False

        session.state = AcquisitionState.ACQUIRING
        logger.info(f"Resumed acquisition {acquisition_id}")

        return True

    async def _acquisition_loop(self, acquisition_id: str, equipment):
        """Main acquisition loop (runs in background task)."""
        session = self._sessions[acquisition_id]
        config = session.config
        buffer = self._buffers[acquisition_id]

        try:
            # Wait for trigger if needed
            if config.trigger_config.trigger_type != TriggerType.IMMEDIATE:
                await self._wait_for_trigger(acquisition_id, equipment)

            session.state = AcquisitionState.ACQUIRING

            # Calculate sleep time based on sample rate
            sleep_time = 1.0 / config.sample_rate

            samples_acquired = 0

            while True:
                # Check if we should stop
                if session.state == AcquisitionState.STOPPED:
                    break

                # Skip if paused
                if session.state == AcquisitionState.PAUSED:
                    await asyncio.sleep(0.1)
                    continue

                # Acquire data
                timestamp = datetime.now().timestamp()
                values = []

                for channel in config.channels:
                    try:
                        # Get measurement from equipment
                        value = await self._get_channel_value(equipment, channel)
                        values.append(value)
                    except Exception as e:
                        logger.error(f"Error reading channel {channel}: {e}")
                        values.append(np.nan)

                # Add to buffer
                buffer.add(values, timestamp)

                # Update stats
                samples_acquired += 1
                session.stats.total_samples = samples_acquired
                for i, channel in enumerate(config.channels):
                    session.stats.samples_per_channel[channel] = samples_acquired

                # Check if we've reached the target number of samples
                if config.mode == AcquisitionMode.SINGLE_SHOT:
                    if config.num_samples and samples_acquired >= config.num_samples:
                        logger.info(f"Acquired {samples_acquired} samples, stopping")
                        break

                # Check duration limit
                if config.duration_seconds:
                    elapsed = (datetime.now() - session.started_at).total_seconds()
                    if elapsed >= config.duration_seconds:
                        logger.info(f"Reached duration limit of {config.duration_seconds}s")
                        break

                # Sleep until next sample
                await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            logger.info(f"Acquisition {acquisition_id} cancelled")
            raise

        except Exception as e:
            logger.error(f"Error in acquisition loop: {e}")
            session.state = AcquisitionState.ERROR
            session.error_message = str(e)

        finally:
            # Update final stats
            if session.stats.start_time:
                session.stats.end_time = datetime.now()
                session.stats.duration_seconds = (
                    session.stats.end_time - session.stats.start_time
                ).total_seconds()

                if session.stats.duration_seconds > 0:
                    session.stats.actual_sample_rate = (
                        session.stats.total_samples / session.stats.duration_seconds
                    )

            # Calculate min/max/mean
            if buffer.count > 0:
                data, _ = buffer.get_all()
                for i, channel in enumerate(config.channels):
                    channel_data = data[i, :]
                    session.stats.min_values[channel] = float(np.nanmin(channel_data))
                    session.stats.max_values[channel] = float(np.nanmax(channel_data))
                    session.stats.mean_values[channel] = float(np.nanmean(channel_data))

            session.stats.buffer_overruns = buffer.overruns

    async def _wait_for_trigger(self, acquisition_id: str, equipment):
        """Wait for trigger condition."""
        session = self._sessions[acquisition_id]
        config = session.config.trigger_config

        if config.trigger_type == TriggerType.IMMEDIATE:
            return

        elif config.trigger_type == TriggerType.TIME:
            # Wait until specific time (simplified - just wait a bit)
            await asyncio.sleep(1.0)

        elif config.trigger_type in [TriggerType.LEVEL, TriggerType.EDGE]:
            # Monitor channel for trigger condition
            if not config.channel or config.level is None:
                raise ValueError("Level/edge trigger requires channel and level")

            logger.info(f"Waiting for {config.trigger_type} trigger on {config.channel}")

            last_value = None

            while session.state == AcquisitionState.WAITING_TRIGGER:
                value = await self._get_channel_value(equipment, config.channel)

                if config.trigger_type == TriggerType.LEVEL:
                    if value >= config.level:
                        logger.info(f"Trigger condition met: {value} >= {config.level}")
                        break

                elif config.trigger_type == TriggerType.EDGE:
                    if last_value is not None:
                        if config.edge == TriggerEdge.RISING:
                            if last_value < config.level and value >= config.level:
                                logger.info(f"Rising edge trigger: {last_value} -> {value}")
                                break
                        elif config.edge == TriggerEdge.FALLING:
                            if last_value > config.level and value <= config.level:
                                logger.info(f"Falling edge trigger: {last_value} -> {value}")
                                break
                        elif config.edge == TriggerEdge.EITHER:
                            if (last_value < config.level and value >= config.level) or \
                               (last_value > config.level and value <= config.level):
                                logger.info(f"Edge trigger: {last_value} -> {value}")
                                break

                    last_value = value

                await asyncio.sleep(0.1)  # Check every 100ms

    async def _get_channel_value(self, equipment, channel: str) -> float:
        """Get current value from equipment channel."""
        # This is a simplified version - equipment drivers should implement proper channel reading

        # Try common methods
        if hasattr(equipment, 'get_measurement'):
            result = await equipment.get_measurement(channel)
            if isinstance(result, dict) and 'value' in result:
                return float(result['value'])
            return float(result)

        elif hasattr(equipment, 'get_voltage'):
            return float(await equipment.get_voltage())

        elif hasattr(equipment, 'get_current'):
            return float(await equipment.get_current())

        else:
            # Fallback: try to execute command
            try:
                result = await equipment.execute_command("get_measurement", {"channel": channel})
                if isinstance(result, dict) and 'value' in result:
                    return float(result['value'])
                return float(result)
            except:
                raise NotImplementedError(
                    f"Equipment doesn't implement data acquisition for channel {channel}"
                )

    def get_session(self, acquisition_id: str) -> Optional[AcquisitionSession]:
        """Get acquisition session by ID."""
        return self._sessions.get(acquisition_id)

    def get_all_sessions(self) -> List[AcquisitionSession]:
        """Get all acquisition sessions."""
        return list(self._sessions.values())

    def get_buffer_data(
        self,
        acquisition_id: str,
        num_samples: Optional[int] = None
    ) -> tuple:
        """Get data from acquisition buffer."""
        if acquisition_id not in self._buffers:
            raise ValueError(f"Acquisition {acquisition_id} not found")

        buffer = self._buffers[acquisition_id]
        return buffer.get_latest(num_samples)

    async def export_data(
        self,
        acquisition_id: str,
        format: ExportFormat = ExportFormat.CSV,
        filepath: Optional[str] = None
    ) -> str:
        """
        Export acquired data to file.

        Args:
            acquisition_id: ID of acquisition session
            format: Export format
            filepath: Optional custom filepath

        Returns:
            Path to exported file
        """
        if acquisition_id not in self._sessions:
            raise ValueError(f"Acquisition {acquisition_id} not found")

        if acquisition_id not in self._buffers:
            raise ValueError(f"No data available for {acquisition_id}")

        session = self._sessions[acquisition_id]
        buffer = self._buffers[acquisition_id]

        # Get all data
        data, timestamps = buffer.get_all()

        if data.size == 0:
            raise ValueError("No data to export")

        # Determine export path
        if filepath:
            export_path = Path(filepath)
        elif self._export_dir:
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{session.config.equipment_id}_{acquisition_id}_{timestamp_str}"
            export_path = self._export_dir / f"{filename}.{format.value}"
        else:
            raise ValueError("No export directory configured and no filepath provided")

        # Export based on format
        if format == ExportFormat.CSV:
            await self._export_csv(export_path, session, data, timestamps)

        elif format == ExportFormat.NUMPY:
            await self._export_numpy(export_path, session, data, timestamps)

        elif format == ExportFormat.JSON:
            await self._export_json(export_path, session, data, timestamps)

        elif format == ExportFormat.HDF5:
            await self._export_hdf5(export_path, session, data, timestamps)

        logger.info(f"Exported data to {export_path}")

        return str(export_path)

    async def _export_csv(self, filepath: Path, session: AcquisitionSession, data: np.ndarray, timestamps: np.ndarray):
        """Export to CSV format."""
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)

            # Header
            header = ['timestamp'] + session.config.channels
            writer.writerow(header)

            # Data
            for i in range(len(timestamps)):
                row = [datetime.fromtimestamp(timestamps[i]).isoformat()]
                row.extend(data[:, i].tolist())
                writer.writerow(row)

    async def _export_numpy(self, filepath: Path, session: AcquisitionSession, data: np.ndarray, timestamps: np.ndarray):
        """Export to NumPy binary format."""
        np.savez(
            filepath,
            data=data,
            timestamps=timestamps,
            channels=session.config.channels,
            metadata=session.config.metadata
        )

    async def _export_json(self, filepath: Path, session: AcquisitionSession, data: np.ndarray, timestamps: np.ndarray):
        """Export to JSON format."""
        export_data = {
            "acquisition_id": session.acquisition_id,
            "equipment_id": session.equipment_id,
            "config": session.config.dict(),
            "stats": session.stats.dict(),
            "data": {
                "timestamps": [datetime.fromtimestamp(t).isoformat() for t in timestamps],
                "channels": {
                    channel: data[i, :].tolist()
                    for i, channel in enumerate(session.config.channels)
                }
            }
        }

        with open(filepath, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)

    async def _export_hdf5(self, filepath: Path, session: AcquisitionSession, data: np.ndarray, timestamps: np.ndarray):
        """Export to HDF5 format."""
        try:
            import h5py
        except ImportError:
            logger.warning("h5py not installed, falling back to NumPy format")
            await self._export_numpy(filepath.with_suffix('.npz'), session, data, timestamps)
            return

        with h5py.File(filepath, 'w') as f:
            # Create groups
            config_group = f.create_group('config')
            stats_group = f.create_group('stats')
            data_group = f.create_group('data')

            # Store config
            config_group.attrs['acquisition_id'] = session.acquisition_id
            config_group.attrs['equipment_id'] = session.equipment_id
            config_group.attrs['mode'] = session.config.mode
            config_group.attrs['sample_rate'] = session.config.sample_rate

            # Store stats
            stats_group.attrs['total_samples'] = session.stats.total_samples
            stats_group.attrs['duration_seconds'] = session.stats.duration_seconds or 0

            # Store data
            data_group.create_dataset('timestamps', data=timestamps)
            for i, channel in enumerate(session.config.channels):
                data_group.create_dataset(channel, data=data[i, :])

    async def delete_session(self, acquisition_id: str) -> bool:
        """Delete an acquisition session."""
        if acquisition_id not in self._sessions:
            return False

        # Stop if running
        if acquisition_id in self._tasks:
            await self.stop_acquisition(acquisition_id)

        # Remove session and buffer
        del self._sessions[acquisition_id]
        if acquisition_id in self._buffers:
            del self._buffers[acquisition_id]

        logger.info(f"Deleted acquisition session {acquisition_id}")

        return True


# Global acquisition manager instance
acquisition_manager = AcquisitionManager()
