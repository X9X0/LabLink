"""Tests for multi-instrument acquisition synchronization.

This module tests the synchronization functionality for coordinating data acquisition
across multiple instruments, including:
- Synchronization states and configuration
- SynchronizationGroup for managing coordinated acquisitions
- SynchronizationManager for managing multiple sync groups
- State transitions and error handling
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.acquisition.synchronization import (
    SyncConfig,
    SyncState,
    SyncStatus,
    SynchronizationGroup,
    SynchronizationManager,
)


# ============================================================================
# Test SyncState Enum
# ============================================================================


class TestSyncState:
    """Test the SyncState enumeration."""

    def test_sync_state_values(self):
        """Test that all expected sync states are defined."""
        assert SyncState.IDLE == "idle"
        assert SyncState.PREPARING == "preparing"
        assert SyncState.READY == "ready"
        assert SyncState.RUNNING == "running"
        assert SyncState.PAUSED == "paused"
        assert SyncState.STOPPED == "stopped"
        assert SyncState.ERROR == "error"

    def test_sync_state_membership(self):
        """Test that SyncState values are members of the enum."""
        assert "idle" in [state.value for state in SyncState]
        assert "running" in [state.value for state in SyncState]
        assert "error" in [state.value for state in SyncState]


# ============================================================================
# Test SyncConfig Dataclass
# ============================================================================


class TestSyncConfig:
    """Test the SyncConfig dataclass."""

    def test_sync_config_creation(self):
        """Test creating a synchronization configuration."""
        config = SyncConfig(
            group_id="group1",
            equipment_ids=["scope1", "scope2", "scope3"],
            master_equipment_id="scope1",
        )

        assert config.group_id == "group1"
        assert config.equipment_ids == ["scope1", "scope2", "scope3"]
        assert config.master_equipment_id == "scope1"
        assert config.sync_tolerance_ms == 10.0  # Default
        assert config.wait_for_all is True  # Default
        assert config.auto_align_timestamps is True  # Default

    def test_sync_config_defaults(self):
        """Test SyncConfig with default values."""
        config = SyncConfig(group_id="group1", equipment_ids=["scope1", "scope2"])

        assert config.master_equipment_id is None
        assert config.sync_tolerance_ms == 10.0
        assert config.wait_for_all is True
        assert config.auto_align_timestamps is True

    def test_sync_config_custom_values(self):
        """Test SyncConfig with custom values."""
        config = SyncConfig(
            group_id="group1",
            equipment_ids=["scope1", "scope2"],
            master_equipment_id="scope2",
            sync_tolerance_ms=5.0,
            wait_for_all=False,
            auto_align_timestamps=False,
        )

        assert config.sync_tolerance_ms == 5.0
        assert config.wait_for_all is False
        assert config.auto_align_timestamps is False


# ============================================================================
# Test SyncStatus Dataclass
# ============================================================================


class TestSyncStatus:
    """Test the SyncStatus dataclass."""

    def test_sync_status_creation(self):
        """Test creating a synchronization status."""
        status = SyncStatus(
            group_id="group1",
            state=SyncState.RUNNING,
            equipment_count=3,
            ready_count=3,
            running_count=3,
            acquisition_ids={"scope1": "acq1", "scope2": "acq2"},
            start_time=datetime.now(),
            sync_errors=[],
        )

        assert status.group_id == "group1"
        assert status.state == SyncState.RUNNING
        assert status.equipment_count == 3
        assert status.ready_count == 3
        assert status.running_count == 3
        assert len(status.acquisition_ids) == 2

    def test_sync_status_defaults(self):
        """Test SyncStatus with default values."""
        status = SyncStatus(
            group_id="group1",
            state=SyncState.IDLE,
            equipment_count=0,
            ready_count=0,
            running_count=0,
        )

        assert status.acquisition_ids == {}
        assert status.start_time is None
        assert status.sync_errors == []


# ============================================================================
# Test SynchronizationGroup
# ============================================================================


class TestSynchronizationGroup:
    """Test the SynchronizationGroup class."""

    def test_initialization(self):
        """Test SynchronizationGroup initialization."""
        config = SyncConfig(
            group_id="group1",
            equipment_ids=["scope1", "scope2"],
            master_equipment_id="scope1",
        )
        group = SynchronizationGroup(config)

        assert group.config == config
        assert group.state == SyncState.IDLE
        assert group.acquisition_ids == {}
        assert group.start_time is None
        assert len(group.ready_equipment) == 0
        assert group.sync_errors == []

    def test_auto_select_master(self):
        """Test automatic master equipment selection."""
        config = SyncConfig(
            group_id="group1",
            equipment_ids=["scope1", "scope2", "scope3"],
            # master_equipment_id not specified
        )
        group = SynchronizationGroup(config)

        # Should auto-select first equipment as master
        assert group.config.master_equipment_id == "scope1"

    @pytest.mark.asyncio
    async def test_add_acquisition_success(self):
        """Test adding an acquisition to the sync group."""
        config = SyncConfig(
            group_id="group1", equipment_ids=["scope1", "scope2", "scope3"]
        )
        group = SynchronizationGroup(config)

        await group.add_acquisition("scope1", "acq1")

        assert group.acquisition_ids["scope1"] == "acq1"
        assert "scope1" in group.ready_equipment
        assert group.state == SyncState.IDLE  # Not all ready yet

    @pytest.mark.asyncio
    async def test_add_acquisition_invalid_equipment(self):
        """Test adding acquisition for equipment not in group raises error."""
        config = SyncConfig(group_id="group1", equipment_ids=["scope1", "scope2"])
        group = SynchronizationGroup(config)

        with pytest.raises(ValueError, match="not in sync group"):
            await group.add_acquisition("scope3", "acq3")

    @pytest.mark.asyncio
    async def test_add_acquisition_all_ready(self):
        """Test that state transitions to READY when all acquisitions added."""
        config = SyncConfig(group_id="group1", equipment_ids=["scope1", "scope2"])
        group = SynchronizationGroup(config)

        await group.add_acquisition("scope1", "acq1")
        assert group.state == SyncState.IDLE

        await group.add_acquisition("scope2", "acq2")
        assert group.state == SyncState.READY

    @pytest.mark.asyncio
    async def test_remove_acquisition(self):
        """Test removing an acquisition from the sync group."""
        config = SyncConfig(group_id="group1", equipment_ids=["scope1", "scope2"])
        group = SynchronizationGroup(config)

        await group.add_acquisition("scope1", "acq1")
        await group.add_acquisition("scope2", "acq2")
        assert group.state == SyncState.READY

        await group.remove_acquisition("scope1")
        assert "scope1" not in group.acquisition_ids
        assert "scope1" not in group.ready_equipment

    @pytest.mark.asyncio
    async def test_remove_acquisition_transitions_to_idle(self):
        """Test that removing all acquisitions transitions state to IDLE."""
        config = SyncConfig(group_id="group1", equipment_ids=["scope1"])
        group = SynchronizationGroup(config)

        await group.add_acquisition("scope1", "acq1")
        await group.remove_acquisition("scope1")

        assert group.state == SyncState.IDLE
        assert len(group.acquisition_ids) == 0

    def test_is_ready_wait_for_all_true(self):
        """Test is_ready() when wait_for_all is True."""
        config = SyncConfig(
            group_id="group1", equipment_ids=["scope1", "scope2"], wait_for_all=True
        )
        group = SynchronizationGroup(config)

        assert not group.is_ready()  # None ready

        group.ready_equipment.add("scope1")
        assert not group.is_ready()  # Only 1 of 2 ready

        group.ready_equipment.add("scope2")
        assert group.is_ready()  # All ready

    def test_is_ready_wait_for_all_false(self):
        """Test is_ready() when wait_for_all is False."""
        config = SyncConfig(
            group_id="group1", equipment_ids=["scope1", "scope2"], wait_for_all=False
        )
        group = SynchronizationGroup(config)

        assert not group.is_ready()  # None ready

        group.ready_equipment.add("scope1")
        assert group.is_ready()  # At least one ready

    @pytest.mark.asyncio
    async def test_start_synchronized_success(self):
        """Test starting synchronized acquisitions successfully."""
        config = SyncConfig(group_id="group1", equipment_ids=["scope1", "scope2"])
        group = SynchronizationGroup(config)

        await group.add_acquisition("scope1", "acq1")
        await group.add_acquisition("scope2", "acq2")

        # Mock acquisition manager
        mock_manager = MagicMock()
        mock_manager.start_acquisition = AsyncMock(return_value=True)

        result = await group.start_synchronized(mock_manager)

        assert result is True
        assert group.state == SyncState.RUNNING
        assert group.start_time is not None
        assert len(group.sync_errors) == 0

        # Verify all acquisitions were started
        assert mock_manager.start_acquisition.call_count == 2

    @pytest.mark.asyncio
    async def test_start_synchronized_not_ready(self):
        """Test that start_synchronized fails if group is not ready."""
        config = SyncConfig(group_id="group1", equipment_ids=["scope1", "scope2"])
        group = SynchronizationGroup(config)

        # Only add one acquisition
        await group.add_acquisition("scope1", "acq1")

        mock_manager = MagicMock()

        result = await group.start_synchronized(mock_manager)

        assert result is False
        assert "Not all acquisitions ready" in group.sync_errors
        assert group.state == SyncState.IDLE

    @pytest.mark.asyncio
    async def test_start_synchronized_with_errors(self):
        """Test start_synchronized handles errors from acquisitions."""
        config = SyncConfig(group_id="group1", equipment_ids=["scope1", "scope2"])
        group = SynchronizationGroup(config)

        await group.add_acquisition("scope1", "acq1")
        await group.add_acquisition("scope2", "acq2")

        # Mock manager with one acquisition failing
        mock_manager = MagicMock()
        mock_manager.start_acquisition = AsyncMock(
            side_effect=[True, Exception("Connection failed")]
        )

        result = await group.start_synchronized(mock_manager)

        assert result is False
        assert group.state == SyncState.ERROR
        assert len(group.sync_errors) > 0
        assert "Connection failed" in group.sync_errors[0]

    @pytest.mark.asyncio
    async def test_stop_synchronized(self):
        """Test stopping synchronized acquisitions."""
        config = SyncConfig(group_id="group1", equipment_ids=["scope1", "scope2"])
        group = SynchronizationGroup(config)
        group.state = SyncState.RUNNING
        group.acquisition_ids = {"scope1": "acq1", "scope2": "acq2"}

        # Mock acquisition manager
        mock_manager = MagicMock()
        mock_manager.stop_acquisition = AsyncMock(return_value=True)

        result = await group.stop_synchronized(mock_manager)

        assert result is True
        assert group.state == SyncState.STOPPED
        assert mock_manager.stop_acquisition.call_count == 2

    @pytest.mark.asyncio
    async def test_stop_synchronized_invalid_state(self):
        """Test that stop_synchronized fails if not running."""
        config = SyncConfig(group_id="group1", equipment_ids=["scope1"])
        group = SynchronizationGroup(config)
        group.state = SyncState.IDLE

        mock_manager = MagicMock()

        result = await group.stop_synchronized(mock_manager)

        assert result is False

    @pytest.mark.asyncio
    async def test_pause_synchronized(self):
        """Test pausing synchronized acquisitions."""
        config = SyncConfig(group_id="group1", equipment_ids=["scope1", "scope2"])
        group = SynchronizationGroup(config)
        group.state = SyncState.RUNNING
        group.acquisition_ids = {"scope1": "acq1", "scope2": "acq2"}

        # Mock acquisition manager
        mock_manager = MagicMock()
        mock_manager.pause_acquisition = AsyncMock(return_value=True)

        result = await group.pause_synchronized(mock_manager)

        assert result is True
        assert group.state == SyncState.PAUSED
        assert mock_manager.pause_acquisition.call_count == 2

    @pytest.mark.asyncio
    async def test_pause_synchronized_invalid_state(self):
        """Test that pause_synchronized fails if not running."""
        config = SyncConfig(group_id="group1", equipment_ids=["scope1"])
        group = SynchronizationGroup(config)
        group.state = SyncState.IDLE

        mock_manager = MagicMock()

        result = await group.pause_synchronized(mock_manager)

        assert result is False

    @pytest.mark.asyncio
    async def test_resume_synchronized(self):
        """Test resuming synchronized acquisitions."""
        config = SyncConfig(group_id="group1", equipment_ids=["scope1", "scope2"])
        group = SynchronizationGroup(config)
        group.state = SyncState.PAUSED
        group.acquisition_ids = {"scope1": "acq1", "scope2": "acq2"}

        # Mock acquisition manager
        mock_manager = MagicMock()
        mock_manager.resume_acquisition = AsyncMock(return_value=True)

        result = await group.resume_synchronized(mock_manager)

        assert result is True
        assert group.state == SyncState.RUNNING
        assert mock_manager.resume_acquisition.call_count == 2

    @pytest.mark.asyncio
    async def test_resume_synchronized_invalid_state(self):
        """Test that resume_synchronized fails if not paused."""
        config = SyncConfig(group_id="group1", equipment_ids=["scope1"])
        group = SynchronizationGroup(config)
        group.state = SyncState.RUNNING

        mock_manager = MagicMock()

        result = await group.resume_synchronized(mock_manager)

        assert result is False

    def test_get_status(self):
        """Test getting synchronization group status."""
        config = SyncConfig(group_id="group1", equipment_ids=["scope1", "scope2"])
        group = SynchronizationGroup(config)
        group.state = SyncState.RUNNING
        group.acquisition_ids = {"scope1": "acq1", "scope2": "acq2"}
        group.ready_equipment = {"scope1", "scope2"}
        group.start_time = datetime.now()

        status = group.get_status()

        assert isinstance(status, SyncStatus)
        assert status.group_id == "group1"
        assert status.state == SyncState.RUNNING
        assert status.equipment_count == 2
        assert status.ready_count == 2
        assert status.running_count == 2
        assert status.acquisition_ids == {"scope1": "acq1", "scope2": "acq2"}
        assert status.start_time is not None

    @pytest.mark.asyncio
    async def test_get_synchronized_data_without_alignment(self):
        """Test getting synchronized data without timestamp alignment."""
        import numpy as np

        config = SyncConfig(
            group_id="group1",
            equipment_ids=["scope1", "scope2"],
            auto_align_timestamps=False,
        )
        group = SynchronizationGroup(config)
        group.acquisition_ids = {"scope1": "acq1", "scope2": "acq2"}

        # Mock acquisition manager
        mock_manager = MagicMock()
        mock_manager.get_buffer_data = MagicMock(
            side_effect=[
                (np.array([1, 2, 3]), np.array([0.0, 0.1, 0.2])),
                (np.array([4, 5, 6]), np.array([0.0, 0.1, 0.2])),
            ]
        )

        data = await group.get_synchronized_data(mock_manager)

        assert "scope1" in data
        assert "scope2" in data
        assert len(data["scope1"]["data"]) == 3
        assert len(data["scope2"]["data"]) == 3

    @pytest.mark.asyncio
    async def test_get_synchronized_data_with_alignment(self):
        """Test getting synchronized data with timestamp alignment."""
        import numpy as np

        config = SyncConfig(
            group_id="group1",
            equipment_ids=["scope1", "scope2"],
            auto_align_timestamps=True,
        )
        group = SynchronizationGroup(config)
        group.acquisition_ids = {"scope1": "acq1", "scope2": "acq2"}
        group.start_time = datetime.now()

        # Mock acquisition manager
        mock_manager = MagicMock()
        reference_time = group.start_time.timestamp()
        mock_manager.get_buffer_data = MagicMock(
            side_effect=[
                (
                    np.array([1, 2, 3]),
                    np.array([reference_time, reference_time + 0.1, reference_time + 0.2]),
                ),
                (
                    np.array([4, 5, 6]),
                    np.array([reference_time, reference_time + 0.1, reference_time + 0.2]),
                ),
            ]
        )

        data = await group.get_synchronized_data(mock_manager)

        # Timestamps should be aligned relative to start_time
        assert data["scope1"]["timestamps"][0] == 0.0  # First timestamp is 0
        assert data["scope2"]["timestamps"][0] == 0.0


# ============================================================================
# Test SynchronizationManager
# ============================================================================


class TestSynchronizationManager:
    """Test the SynchronizationManager class."""

    def test_initialization(self):
        """Test SynchronizationManager initialization."""
        manager = SynchronizationManager()

        assert len(manager._sync_groups) == 0

    @pytest.mark.asyncio
    async def test_create_sync_group(self):
        """Test creating a synchronization group."""
        manager = SynchronizationManager()
        config = SyncConfig(group_id="group1", equipment_ids=["scope1", "scope2"])

        group = await manager.create_sync_group(config)

        assert isinstance(group, SynchronizationGroup)
        assert group.config == config
        assert len(manager._sync_groups) == 1

    @pytest.mark.asyncio
    async def test_create_sync_group_duplicate_id(self):
        """Test that creating duplicate sync group raises error."""
        manager = SynchronizationManager()
        config = SyncConfig(group_id="group1", equipment_ids=["scope1", "scope2"])

        await manager.create_sync_group(config)

        with pytest.raises(ValueError, match="already exists"):
            await manager.create_sync_group(config)

    @pytest.mark.asyncio
    async def test_get_sync_group(self):
        """Test getting a synchronization group by ID."""
        manager = SynchronizationManager()
        config = SyncConfig(group_id="group1", equipment_ids=["scope1", "scope2"])

        created_group = await manager.create_sync_group(config)
        retrieved_group = await manager.get_sync_group("group1")

        assert retrieved_group is created_group

    @pytest.mark.asyncio
    async def test_get_sync_group_not_found(self):
        """Test getting a non-existent sync group returns None."""
        manager = SynchronizationManager()

        group = await manager.get_sync_group("nonexistent")

        assert group is None

    @pytest.mark.asyncio
    async def test_delete_sync_group_success(self):
        """Test deleting a synchronization group."""
        manager = SynchronizationManager()
        config = SyncConfig(group_id="group1", equipment_ids=["scope1"])
        group = await manager.create_sync_group(config)
        group.state = SyncState.STOPPED

        result = await manager.delete_sync_group("group1")

        assert result is True
        assert len(manager._sync_groups) == 0

    @pytest.mark.asyncio
    async def test_delete_sync_group_not_found(self):
        """Test deleting non-existent group returns False."""
        manager = SynchronizationManager()

        result = await manager.delete_sync_group("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_sync_group_active_state(self):
        """Test that deleting active sync group raises error."""
        manager = SynchronizationManager()
        config = SyncConfig(group_id="group1", equipment_ids=["scope1"])
        group = await manager.create_sync_group(config)
        group.state = SyncState.RUNNING

        with pytest.raises(ValueError, match="Cannot delete active sync group"):
            await manager.delete_sync_group("group1")

    @pytest.mark.asyncio
    async def test_delete_sync_group_allowed_states(self):
        """Test that deleting is allowed for IDLE, STOPPED, and ERROR states."""
        manager = SynchronizationManager()

        # Test IDLE state
        config1 = SyncConfig(group_id="group1", equipment_ids=["scope1"])
        group1 = await manager.create_sync_group(config1)
        group1.state = SyncState.IDLE
        assert await manager.delete_sync_group("group1") is True

        # Test STOPPED state
        config2 = SyncConfig(group_id="group2", equipment_ids=["scope2"])
        group2 = await manager.create_sync_group(config2)
        group2.state = SyncState.STOPPED
        assert await manager.delete_sync_group("group2") is True

        # Test ERROR state
        config3 = SyncConfig(group_id="group3", equipment_ids=["scope3"])
        group3 = await manager.create_sync_group(config3)
        group3.state = SyncState.ERROR
        assert await manager.delete_sync_group("group3") is True

    @pytest.mark.asyncio
    async def test_list_sync_groups(self):
        """Test listing all synchronization groups."""
        manager = SynchronizationManager()

        config1 = SyncConfig(group_id="group1", equipment_ids=["scope1"])
        config2 = SyncConfig(group_id="group2", equipment_ids=["scope2", "scope3"])

        await manager.create_sync_group(config1)
        await manager.create_sync_group(config2)

        groups = await manager.list_sync_groups()

        assert len(groups) == 2
        assert all(isinstance(status, SyncStatus) for status in groups)
        group_ids = {status.group_id for status in groups}
        assert group_ids == {"group1", "group2"}

    @pytest.mark.asyncio
    async def test_list_sync_groups_empty(self):
        """Test listing sync groups when none exist."""
        manager = SynchronizationManager()

        groups = await manager.list_sync_groups()

        assert groups == []

    @pytest.mark.asyncio
    async def test_get_group_status(self):
        """Test getting status of a specific sync group."""
        manager = SynchronizationManager()
        config = SyncConfig(group_id="group1", equipment_ids=["scope1", "scope2"])

        await manager.create_sync_group(config)
        status = await manager.get_group_status("group1")

        assert isinstance(status, SyncStatus)
        assert status.group_id == "group1"
        assert status.equipment_count == 2

    @pytest.mark.asyncio
    async def test_get_group_status_not_found(self):
        """Test getting status of non-existent group returns None."""
        manager = SynchronizationManager()

        status = await manager.get_group_status("nonexistent")

        assert status is None
