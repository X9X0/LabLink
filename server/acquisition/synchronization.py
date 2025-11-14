"""Multi-instrument synchronization for coordinated data acquisition."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set

from .models import AcquisitionConfig, AcquisitionState

logger = logging.getLogger(__name__)


class SyncState(str, Enum):
    """Synchronization group state."""

    IDLE = "idle"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class SyncConfig:
    """Configuration for synchronized acquisition."""

    group_id: str
    equipment_ids: List[str]
    master_equipment_id: Optional[str] = None  # Device that controls timing
    sync_tolerance_ms: float = 10.0  # Maximum allowed time difference
    wait_for_all: bool = True  # Wait for all devices before starting
    auto_align_timestamps: bool = True  # Align timestamps to master


@dataclass
class SyncStatus:
    """Status of synchronization group."""

    group_id: str
    state: SyncState
    equipment_count: int
    ready_count: int
    running_count: int
    acquisition_ids: Dict[str, str] = field(
        default_factory=dict
    )  # equipment_id -> acquisition_id
    start_time: Optional[datetime] = None
    sync_errors: List[str] = field(default_factory=list)


class SynchronizationGroup:
    """Manages synchronized acquisition across multiple instruments."""

    def __init__(self, config: SyncConfig):
        """
        Initialize synchronization group.

        Args:
            config: Synchronization configuration
        """
        self.config = config
        self.state = SyncState.IDLE
        self.acquisition_ids: Dict[str, str] = {}  # equipment_id -> acquisition_id
        self.start_time: Optional[datetime] = None
        self.ready_equipment: Set[str] = set()
        self.sync_errors: List[str] = []
        self._lock = asyncio.Lock()

        # Use first equipment as master if not specified
        if (
            self.config.master_equipment_id is None
            and len(self.config.equipment_ids) > 0
        ):
            self.config.master_equipment_id = self.config.equipment_ids[0]

    async def add_acquisition(self, equipment_id: str, acquisition_id: str):
        """
        Add an acquisition session to the sync group.

        Args:
            equipment_id: Equipment identifier
            acquisition_id: Acquisition session ID
        """
        async with self._lock:
            if equipment_id not in self.config.equipment_ids:
                raise ValueError(f"Equipment {equipment_id} not in sync group")

            self.acquisition_ids[equipment_id] = acquisition_id
            self.ready_equipment.add(equipment_id)

            logger.info(
                f"Added acquisition {acquisition_id} for {equipment_id} to sync group {self.config.group_id}"
            )

            # Check if all ready
            if len(self.ready_equipment) == len(self.config.equipment_ids):
                self.state = SyncState.READY
                logger.info(
                    f"Sync group {self.config.group_id} is ready ({len(self.ready_equipment)} devices)"
                )

    async def remove_acquisition(self, equipment_id: str):
        """Remove an acquisition from the sync group."""
        async with self._lock:
            if equipment_id in self.acquisition_ids:
                del self.acquisition_ids[equipment_id]
            self.ready_equipment.discard(equipment_id)

            if len(self.acquisition_ids) == 0:
                self.state = SyncState.IDLE

    def is_ready(self) -> bool:
        """Check if all acquisitions are ready to start."""
        if self.config.wait_for_all:
            return len(self.ready_equipment) == len(self.config.equipment_ids)
        else:
            return len(self.ready_equipment) > 0

    async def start_synchronized(self, acquisition_manager):
        """
        Start all acquisitions in the group simultaneously.

        Args:
            acquisition_manager: AcquisitionManager instance

        Returns:
            True if all started successfully
        """
        async with self._lock:
            if not self.is_ready():
                self.sync_errors.append("Not all acquisitions ready")
                return False

            self.state = SyncState.PREPARING
            self.sync_errors.clear()

            # Record sync start time
            self.start_time = datetime.now()
            sync_timestamp = self.start_time.timestamp()

            # Start all acquisitions
            start_tasks = []
            for equipment_id, acquisition_id in self.acquisition_ids.items():
                task = acquisition_manager.start_acquisition(acquisition_id)
                start_tasks.append(task)

            # Wait for all to start
            results = await asyncio.gather(*start_tasks, return_exceptions=True)

            # Check for errors
            failed = []
            for i, (equipment_id, result) in enumerate(
                zip(self.acquisition_ids.keys(), results)
            ):
                if isinstance(result, Exception):
                    failed.append(equipment_id)
                    self.sync_errors.append(f"{equipment_id}: {str(result)}")

            if failed:
                logger.error(
                    f"Failed to start sync group {self.config.group_id}: {failed}"
                )
                self.state = SyncState.ERROR
                return False

            self.state = SyncState.RUNNING
            logger.info(
                f"Sync group {self.config.group_id} started successfully at {self.start_time}"
            )

            return True

    async def stop_synchronized(self, acquisition_manager):
        """
        Stop all acquisitions in the group simultaneously.

        Args:
            acquisition_manager: AcquisitionManager instance

        Returns:
            True if all stopped successfully
        """
        async with self._lock:
            if self.state != SyncState.RUNNING:
                return False

            # Stop all acquisitions
            stop_tasks = []
            for acquisition_id in self.acquisition_ids.values():
                task = acquisition_manager.stop_acquisition(acquisition_id)
                stop_tasks.append(task)

            # Wait for all to stop
            await asyncio.gather(*stop_tasks, return_exceptions=True)

            self.state = SyncState.STOPPED
            logger.info(f"Sync group {self.config.group_id} stopped")

            return True

    async def pause_synchronized(self, acquisition_manager):
        """Pause all acquisitions in the group."""
        async with self._lock:
            if self.state != SyncState.RUNNING:
                return False

            pause_tasks = []
            for acquisition_id in self.acquisition_ids.values():
                task = acquisition_manager.pause_acquisition(acquisition_id)
                pause_tasks.append(task)

            await asyncio.gather(*pause_tasks, return_exceptions=True)

            self.state = SyncState.PAUSED
            logger.info(f"Sync group {self.config.group_id} paused")

            return True

    async def resume_synchronized(self, acquisition_manager):
        """Resume all acquisitions in the group."""
        async with self._lock:
            if self.state != SyncState.PAUSED:
                return False

            resume_tasks = []
            for acquisition_id in self.acquisition_ids.values():
                task = acquisition_manager.resume_acquisition(acquisition_id)
                resume_tasks.append(task)

            await asyncio.gather(*resume_tasks, return_exceptions=True)

            self.state = SyncState.RUNNING
            logger.info(f"Sync group {self.config.group_id} resumed")

            return True

    def get_status(self) -> SyncStatus:
        """Get current synchronization status."""
        return SyncStatus(
            group_id=self.config.group_id,
            state=self.state,
            equipment_count=len(self.config.equipment_ids),
            ready_count=len(self.ready_equipment),
            running_count=len(self.acquisition_ids),
            acquisition_ids=self.acquisition_ids.copy(),
            start_time=self.start_time,
            sync_errors=self.sync_errors.copy(),
        )

    async def get_synchronized_data(
        self, acquisition_manager, num_samples: Optional[int] = None
    ):
        """
        Get synchronized data from all acquisitions.

        Args:
            acquisition_manager: AcquisitionManager instance
            num_samples: Number of samples to retrieve from each

        Returns:
            Dictionary mapping equipment_id to (data, timestamps) tuples
        """
        synchronized_data = {}

        for equipment_id, acquisition_id in self.acquisition_ids.items():
            data, timestamps = acquisition_manager.get_buffer_data(
                acquisition_id, num_samples
            )
            synchronized_data[equipment_id] = {"data": data, "timestamps": timestamps}

        # Align timestamps if requested
        if self.config.auto_align_timestamps and self.start_time is not None:
            reference_time = self.start_time.timestamp()

            for equipment_id in synchronized_data:
                timestamps = synchronized_data[equipment_id]["timestamps"]
                # Make timestamps relative to sync start time
                aligned_timestamps = timestamps - reference_time
                synchronized_data[equipment_id]["timestamps"] = aligned_timestamps

        return synchronized_data


class SynchronizationManager:
    """Manages synchronization groups for multi-instrument acquisition."""

    def __init__(self):
        """Initialize synchronization manager."""
        self._sync_groups: Dict[str, SynchronizationGroup] = {}
        self._lock = asyncio.Lock()

    async def create_sync_group(self, config: SyncConfig) -> SynchronizationGroup:
        """
        Create a new synchronization group.

        Args:
            config: Synchronization configuration

        Returns:
            SynchronizationGroup instance
        """
        async with self._lock:
            if config.group_id in self._sync_groups:
                raise ValueError(f"Sync group {config.group_id} already exists")

            group = SynchronizationGroup(config)
            self._sync_groups[config.group_id] = group

            logger.info(
                f"Created sync group {config.group_id} with {len(config.equipment_ids)} devices"
            )

            return group

    async def get_sync_group(self, group_id: str) -> Optional[SynchronizationGroup]:
        """Get synchronization group by ID."""
        return self._sync_groups.get(group_id)

    async def delete_sync_group(self, group_id: str) -> bool:
        """
        Delete a synchronization group.

        Args:
            group_id: Group identifier

        Returns:
            True if deleted successfully
        """
        async with self._lock:
            if group_id not in self._sync_groups:
                return False

            group = self._sync_groups[group_id]

            # Can only delete if stopped or idle
            if group.state not in [SyncState.IDLE, SyncState.STOPPED, SyncState.ERROR]:
                raise ValueError(
                    f"Cannot delete active sync group (state: {group.state})"
                )

            del self._sync_groups[group_id]
            logger.info(f"Deleted sync group {group_id}")

            return True

    async def list_sync_groups(self) -> List[SyncStatus]:
        """List all synchronization groups."""
        return [group.get_status() for group in self._sync_groups.values()]

    async def get_group_status(self, group_id: str) -> Optional[SyncStatus]:
        """Get status of a specific sync group."""
        group = self._sync_groups.get(group_id)
        if group is None:
            return None

        return group.get_status()


# Global synchronization manager instance
sync_manager = SynchronizationManager()
