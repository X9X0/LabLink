"""Equipment state management for snapshots, comparison, and restoration.

Provides comprehensive state capture, versioning, comparison, and restoration
capabilities for all equipment types.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EquipmentState(BaseModel):
    """Represents a complete equipment state snapshot."""

    state_id: str = Field(default_factory=lambda: str(uuid4()))
    equipment_id: str
    equipment_type: str
    equipment_model: str
    timestamp: datetime = Field(default_factory=datetime.now)
    name: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    state_data: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class StateDiff(BaseModel):
    """Represents differences between two equipment states."""

    state_id_1: str
    state_id_2: str
    equipment_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    added: Dict[str, Any] = Field(default_factory=dict)
    removed: Dict[str, Any] = Field(default_factory=dict)
    modified: Dict[str, Any] = Field(default_factory=dict)
    unchanged: List[str] = Field(default_factory=list)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class StateVersion(BaseModel):
    """Represents a versioned state with history tracking."""

    version_id: str = Field(default_factory=lambda: str(uuid4()))
    equipment_id: str
    version_number: int
    state: EquipmentState
    parent_version_id: Optional[str] = None
    change_description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class StateManager:
    """Manages equipment state snapshots, comparison, and restoration."""

    def __init__(self):
        self._states: Dict[str, EquipmentState] = {}  # state_id -> state
        self._equipment_states: Dict[str, List[str]] = {}  # equipment_id -> [state_ids]
        self._named_states: Dict[str, Dict[str, str]] = (
            {}
        )  # equipment_id -> {name: state_id}
        self._versions: Dict[str, List[StateVersion]] = {}  # equipment_id -> [versions]
        self._state_dir: Optional[Path] = None

    def set_state_directory(self, directory: str):
        """Set directory for state file storage."""
        self._state_dir = Path(directory)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"State directory set to: {self._state_dir}")

    async def capture_state(
        self,
        equipment,
        name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        save_to_disk: bool = False,
    ) -> EquipmentState:
        """
        Capture current equipment state.

        Args:
            equipment: Equipment instance to capture
            name: Optional name for the state
            description: Optional description
            tags: Optional tags for categorization
            save_to_disk: Whether to save to disk

        Returns:
            EquipmentState object
        """
        # Get equipment info
        info = await equipment.get_info()
        equipment_id = info.id

        # Capture state data
        state_data = {}

        try:
            # Get status (common to all equipment)
            status = await equipment.get_status()
            state_data["status"] = status.dict()

            # Try to get equipment-specific state
            if hasattr(equipment, "get_state"):
                # Equipment has custom get_state method
                custom_state = await equipment.get_state()
                state_data.update(custom_state)
            else:
                # Build state from common methods
                await self._capture_common_state(equipment, state_data)

        except Exception as e:
            logger.error(f"Error capturing state for {equipment_id}: {e}")
            raise

        # Create state object
        state = EquipmentState(
            equipment_id=equipment_id,
            equipment_type=(
                info.type.value if hasattr(info.type, "value") else str(info.type)
            ),
            equipment_model=info.model,
            name=name,
            description=description,
            tags=tags or [],
            state_data=state_data,
            metadata={
                "manufacturer": info.manufacturer,
                "serial_number": info.serial_number,
            },
        )

        # Store in memory
        self._states[state.state_id] = state

        # Track for equipment
        if equipment_id not in self._equipment_states:
            self._equipment_states[equipment_id] = []
        self._equipment_states[equipment_id].append(state.state_id)

        # Store named state
        if name:
            if equipment_id not in self._named_states:
                self._named_states[equipment_id] = {}
            self._named_states[equipment_id][name] = state.state_id

        # Save to disk if requested
        if save_to_disk and self._state_dir:
            self._save_state_to_disk(state)

        logger.info(f"Captured state {state.state_id} for equipment {equipment_id}")

        return state

    async def _capture_common_state(self, equipment, state_data: Dict[str, Any]):
        """Capture common state data from equipment."""
        # Try common getter methods
        common_getters = {
            "voltage": "get_voltage",
            "current": "get_current",
            "power": "get_power",
            "output_enabled": "get_output",
            "input_enabled": "get_input",
            "mode": "get_mode",
            "range": "get_range",
            "timebase": "get_timebase",
            "trigger": "get_trigger",
            "channels": "get_channel_settings",
        }

        for key, method_name in common_getters.items():
            if hasattr(equipment, method_name):
                try:
                    method = getattr(equipment, method_name)
                    value = await method()
                    state_data[key] = value
                except Exception as e:
                    logger.debug(f"Could not capture {key}: {e}")

    async def restore_state(
        self,
        equipment,
        state_id: Optional[str] = None,
        state_name: Optional[str] = None,
        state: Optional[EquipmentState] = None,
    ) -> bool:
        """
        Restore equipment to a previous state.

        Args:
            equipment: Equipment instance to restore
            state_id: State ID to restore (mutually exclusive with state_name and state)
            state_name: Named state to restore
            state: State object to restore

        Returns:
            True if successful
        """
        # Get the state to restore
        if state:
            target_state = state
        elif state_id:
            target_state = self._states.get(state_id)
            if not target_state:
                raise ValueError(f"State {state_id} not found")
        elif state_name:
            info = await equipment.get_info()
            equipment_id = info.id

            if equipment_id not in self._named_states:
                raise ValueError(f"No named states for equipment {equipment_id}")

            if state_name not in self._named_states[equipment_id]:
                raise ValueError(f"Named state '{state_name}' not found")

            state_id = self._named_states[equipment_id][state_name]
            target_state = self._states[state_id]
        else:
            raise ValueError("Must provide state_id, state_name, or state")

        # Verify equipment matches
        info = await equipment.get_info()
        if target_state.equipment_id != info.id:
            raise ValueError(
                f"State is for equipment {target_state.equipment_id}, "
                f"but trying to restore to {info.id}"
            )

        # Restore state data
        state_data = target_state.state_data

        try:
            # Try custom restore method first
            if hasattr(equipment, "restore_state"):
                await equipment.restore_state(state_data)
            else:
                # Restore using common setters
                await self._restore_common_state(equipment, state_data)

            logger.info(
                f"Restored state {target_state.state_id} to equipment {info.id}"
            )
            return True

        except Exception as e:
            logger.error(f"Error restoring state: {e}")
            raise

    async def _restore_common_state(self, equipment, state_data: Dict[str, Any]):
        """Restore common state data to equipment."""
        # Try common setter methods
        common_setters = {
            "voltage": "set_voltage",
            "current": "set_current",
            "mode": "set_mode",
            "range": "set_range",
            "timebase": "set_timebase",
            "trigger": "set_trigger",
            "output_enabled": "set_output",
            "input_enabled": "set_input",
        }

        for key, method_name in common_setters.items():
            if key in state_data and hasattr(equipment, method_name):
                try:
                    method = getattr(equipment, method_name)
                    value = state_data[key]
                    await method(value)
                    logger.debug(f"Restored {key} = {value}")
                except Exception as e:
                    logger.warning(f"Could not restore {key}: {e}")

    def compare_states(
        self, state1: EquipmentState, state2: EquipmentState
    ) -> StateDiff:
        """
        Compare two equipment states and return differences.

        Args:
            state1: First state
            state2: Second state

        Returns:
            StateDiff object
        """
        if state1.equipment_id != state2.equipment_id:
            raise ValueError("Cannot compare states from different equipment")

        diff = StateDiff(
            state_id_1=state1.state_id,
            state_id_2=state2.state_id,
            equipment_id=state1.equipment_id,
        )

        # Get all keys
        keys1 = set(state1.state_data.keys())
        keys2 = set(state2.state_data.keys())

        # Find added keys
        added_keys = keys2 - keys1
        for key in added_keys:
            diff.added[key] = state2.state_data[key]

        # Find removed keys
        removed_keys = keys1 - keys2
        for key in removed_keys:
            diff.removed[key] = state1.state_data[key]

        # Find modified/unchanged keys
        common_keys = keys1 & keys2
        for key in common_keys:
            val1 = state1.state_data[key]
            val2 = state2.state_data[key]

            if val1 != val2:
                diff.modified[key] = {"old": val1, "new": val2}
            else:
                diff.unchanged.append(key)

        return diff

    def get_state(self, state_id: str) -> Optional[EquipmentState]:
        """Get state by ID."""
        return self._states.get(state_id)

    def get_named_state(self, equipment_id: str, name: str) -> Optional[EquipmentState]:
        """Get named state for equipment."""
        if equipment_id not in self._named_states:
            return None

        if name not in self._named_states[equipment_id]:
            return None

        state_id = self._named_states[equipment_id][name]
        return self._states.get(state_id)

    def get_equipment_states(
        self, equipment_id: str, limit: Optional[int] = None
    ) -> List[EquipmentState]:
        """Get all states for equipment."""
        if equipment_id not in self._equipment_states:
            return []

        state_ids = self._equipment_states[equipment_id]

        # Get state objects
        states = [self._states[sid] for sid in state_ids if sid in self._states]

        # Sort by timestamp (newest first)
        states.sort(key=lambda s: s.timestamp, reverse=True)

        # Apply limit
        if limit:
            states = states[:limit]

        return states

    def get_named_states(self, equipment_id: str) -> Dict[str, str]:
        """Get all named states for equipment."""
        return self._named_states.get(equipment_id, {})

    def delete_state(self, state_id: str) -> bool:
        """Delete a state."""
        if state_id not in self._states:
            return False

        state = self._states[state_id]
        equipment_id = state.equipment_id

        # Remove from states
        del self._states[state_id]

        # Remove from equipment states
        if equipment_id in self._equipment_states:
            self._equipment_states[equipment_id] = [
                sid for sid in self._equipment_states[equipment_id] if sid != state_id
            ]

        # Remove from named states
        if equipment_id in self._named_states:
            to_remove = [
                name
                for name, sid in self._named_states[equipment_id].items()
                if sid == state_id
            ]
            for name in to_remove:
                del self._named_states[equipment_id][name]

        # Delete from disk
        if self._state_dir:
            self._delete_state_from_disk(state_id)

        logger.info(f"Deleted state {state_id}")
        return True

    def _save_state_to_disk(self, state: EquipmentState):
        """Save state to disk as JSON."""
        if not self._state_dir:
            return

        filename = f"{state.equipment_id}_{state.state_id}.json"
        filepath = self._state_dir / filename

        try:
            with open(filepath, "w") as f:
                json.dump(state.dict(), f, indent=2, default=str)
            logger.debug(f"Saved state to {filepath}")
        except Exception as e:
            logger.error(f"Error saving state to disk: {e}")

    def _delete_state_from_disk(self, state_id: str):
        """Delete state file from disk."""
        if not self._state_dir:
            return

        # Find file with state_id
        for filepath in self._state_dir.glob(f"*_{state_id}.json"):
            try:
                filepath.unlink()
                logger.debug(f"Deleted state file {filepath}")
            except Exception as e:
                logger.error(f"Error deleting state file: {e}")

    def load_states_from_disk(self) -> int:
        """Load all states from disk."""
        if not self._state_dir or not self._state_dir.exists():
            return 0

        loaded_count = 0

        for filepath in self._state_dir.glob("*.json"):
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)

                state = EquipmentState(**data)

                # Store in memory
                self._states[state.state_id] = state

                # Track for equipment
                equipment_id = state.equipment_id
                if equipment_id not in self._equipment_states:
                    self._equipment_states[equipment_id] = []
                if state.state_id not in self._equipment_states[equipment_id]:
                    self._equipment_states[equipment_id].append(state.state_id)

                # Track named state
                if state.name:
                    if equipment_id not in self._named_states:
                        self._named_states[equipment_id] = {}
                    self._named_states[equipment_id][state.name] = state.state_id

                loaded_count += 1

            except Exception as e:
                logger.error(f"Error loading state from {filepath}: {e}")

        logger.info(f"Loaded {loaded_count} states from disk")
        return loaded_count

    def export_state(self, state_id: str) -> Dict[str, Any]:
        """Export state as dictionary."""
        state = self._states.get(state_id)
        if not state:
            raise ValueError(f"State {state_id} not found")

        return state.dict()

    def import_state(self, state_dict: Dict[str, Any]) -> EquipmentState:
        """Import state from dictionary."""
        state = EquipmentState(**state_dict)

        # Store in memory
        self._states[state.state_id] = state

        # Track for equipment
        equipment_id = state.equipment_id
        if equipment_id not in self._equipment_states:
            self._equipment_states[equipment_id] = []
        if state.state_id not in self._equipment_states[equipment_id]:
            self._equipment_states[equipment_id].append(state.state_id)

        # Track named state
        if state.name:
            if equipment_id not in self._named_states:
                self._named_states[equipment_id] = {}
            self._named_states[equipment_id][state.name] = state.state_id

        logger.info(f"Imported state {state.state_id}")
        return state

    def create_version(
        self,
        equipment_id: str,
        state: EquipmentState,
        change_description: Optional[str] = None,
    ) -> StateVersion:
        """Create a versioned state."""
        if equipment_id not in self._versions:
            self._versions[equipment_id] = []

        versions = self._versions[equipment_id]
        version_number = len(versions) + 1

        # Get parent version
        parent_version_id = None
        if versions:
            parent_version_id = versions[-1].version_id

        version = StateVersion(
            equipment_id=equipment_id,
            version_number=version_number,
            state=state,
            parent_version_id=parent_version_id,
            change_description=change_description,
        )

        versions.append(version)

        logger.info(f"Created version {version_number} for equipment {equipment_id}")

        return version

    def get_versions(self, equipment_id: str) -> List[StateVersion]:
        """Get all versions for equipment."""
        return self._versions.get(equipment_id, [])

    def get_version(
        self, equipment_id: str, version_number: int
    ) -> Optional[StateVersion]:
        """Get specific version."""
        versions = self._versions.get(equipment_id, [])

        for version in versions:
            if version.version_number == version_number:
                return version

        return None


# Global state manager instance
state_manager = StateManager()
