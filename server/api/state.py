"""REST API endpoints for equipment state management."""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from server.equipment.manager import equipment_manager
from server.equipment.state import EquipmentState, StateDiff, state_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/state", tags=["Equipment State Management"])


# ============================================================================
# Request/Response Models
# ============================================================================


class CaptureStateRequest(BaseModel):
    """Request to capture equipment state."""

    equipment_id: str
    name: Optional[str] = Field(None, description="Optional name for the state")
    description: Optional[str] = Field(None, description="Optional description")
    tags: List[str] = Field(default_factory=list, description="Optional tags")
    save_to_disk: bool = Field(default=False, description="Save state to disk")


class RestoreStateRequest(BaseModel):
    """Request to restore equipment state."""

    equipment_id: str
    state_id: Optional[str] = None
    state_name: Optional[str] = None


class CompareStatesRequest(BaseModel):
    """Request to compare two states."""

    state_id_1: str
    state_id_2: str


class StateResponse(BaseModel):
    """Equipment state response."""

    state_id: str
    equipment_id: str
    equipment_type: str
    equipment_model: str
    timestamp: str
    name: Optional[str]
    description: Optional[str]
    tags: List[str]
    state_data: dict
    metadata: dict


class StateDiffResponse(BaseModel):
    """State comparison response."""

    state_id_1: str
    state_id_2: str
    equipment_id: str
    timestamp: str
    added: dict
    removed: dict
    modified: dict
    unchanged: List[str]
    summary: dict


# ============================================================================
# State Capture & Restore Endpoints
# ============================================================================


@router.post("/capture", summary="Capture equipment state")
async def capture_state(request: CaptureStateRequest):
    """
    Capture current equipment state as a snapshot.

    - Saves complete equipment configuration
    - Optionally name the state for easy access
    - Optionally save to disk for persistence
    - Returns state ID for future reference
    """
    try:
        equipment = equipment_manager.get_equipment(request.equipment_id)
        if not equipment:
            raise HTTPException(
                status_code=404, detail=f"Equipment {request.equipment_id} not found"
            )

        state = await state_manager.capture_state(
            equipment=equipment,
            name=request.name,
            description=request.description,
            tags=request.tags,
            save_to_disk=request.save_to_disk,
        )

        return {
            "success": True,
            "message": "State captured successfully",
            "state": StateResponse(
                state_id=state.state_id,
                equipment_id=state.equipment_id,
                equipment_type=state.equipment_type,
                equipment_model=state.equipment_model,
                timestamp=state.timestamp.isoformat(),
                name=state.name,
                description=state.description,
                tags=state.tags,
                state_data=state.state_data,
                metadata=state.metadata,
            ).dict(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error capturing state: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to capture state: {str(e)}"
        )


@router.post("/restore", summary="Restore equipment state")
async def restore_state(request: RestoreStateRequest):
    """
    Restore equipment to a previous state.

    - Restore by state ID or state name
    - Applies all captured settings
    - Use with caution - overwrites current configuration
    """
    try:
        equipment = equipment_manager.get_equipment(request.equipment_id)
        if not equipment:
            raise HTTPException(
                status_code=404, detail=f"Equipment {request.equipment_id} not found"
            )

        if not request.state_id and not request.state_name:
            raise HTTPException(
                status_code=400, detail="Must provide state_id or state_name"
            )

        success = await state_manager.restore_state(
            equipment=equipment,
            state_id=request.state_id,
            state_name=request.state_name,
        )

        if success:
            return {
                "success": True,
                "message": "State restored successfully",
                "equipment_id": request.equipment_id,
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to restore state")

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error restoring state: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to restore state: {str(e)}"
        )


# ============================================================================
# State Query Endpoints
# ============================================================================


@router.get("/get/{state_id}", summary="Get state by ID")
async def get_state(state_id: str):
    """
    Get state information by ID.
    """
    try:
        state = state_manager.get_state(state_id)

        if not state:
            raise HTTPException(status_code=404, detail=f"State {state_id} not found")

        return StateResponse(
            state_id=state.state_id,
            equipment_id=state.equipment_id,
            equipment_type=state.equipment_type,
            equipment_model=state.equipment_model,
            timestamp=state.timestamp.isoformat(),
            name=state.name,
            description=state.description,
            tags=state.tags,
            state_data=state.state_data,
            metadata=state.metadata,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting state: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get state: {str(e)}")


@router.get("/list/{equipment_id}", summary="List equipment states")
async def list_equipment_states(
    equipment_id: str,
    limit: int = Query(
        default=50, ge=1, le=1000, description="Maximum number of states to return"
    ),
):
    """
    Get all captured states for specific equipment.

    Returns states sorted by timestamp (newest first).
    """
    try:
        states = state_manager.get_equipment_states(equipment_id, limit=limit)

        return {
            "equipment_id": equipment_id,
            "states": [
                StateResponse(
                    state_id=s.state_id,
                    equipment_id=s.equipment_id,
                    equipment_type=s.equipment_type,
                    equipment_model=s.equipment_model,
                    timestamp=s.timestamp.isoformat(),
                    name=s.name,
                    description=s.description,
                    tags=s.tags,
                    state_data=s.state_data,
                    metadata=s.metadata,
                ).dict()
                for s in states
            ],
            "count": len(states),
        }

    except Exception as e:
        logger.error(f"Error listing states: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list states: {str(e)}")


@router.get("/named/{equipment_id}", summary="Get named states")
async def get_named_states(equipment_id: str):
    """
    Get all named states for equipment.

    Returns mapping of state names to state IDs.
    """
    try:
        named_states = state_manager.get_named_states(equipment_id)

        # Get full state info for each
        states_info = {}
        for name, state_id in named_states.items():
            state = state_manager.get_state(state_id)
            if state:
                states_info[name] = {
                    "state_id": state.state_id,
                    "timestamp": state.timestamp.isoformat(),
                    "description": state.description,
                    "tags": state.tags,
                }

        return {
            "equipment_id": equipment_id,
            "named_states": states_info,
            "count": len(states_info),
        }

    except Exception as e:
        logger.error(f"Error getting named states: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get named states: {str(e)}"
        )


@router.get("/named/{equipment_id}/{name}", summary="Get named state")
async def get_named_state(equipment_id: str, name: str):
    """
    Get a specific named state.
    """
    try:
        state = state_manager.get_named_state(equipment_id, name)

        if not state:
            raise HTTPException(
                status_code=404,
                detail=f"Named state '{name}' not found for equipment {equipment_id}",
            )

        return StateResponse(
            state_id=state.state_id,
            equipment_id=state.equipment_id,
            equipment_type=state.equipment_type,
            equipment_model=state.equipment_model,
            timestamp=state.timestamp.isoformat(),
            name=state.name,
            description=state.description,
            tags=state.tags,
            state_data=state.state_data,
            metadata=state.metadata,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting named state: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get named state: {str(e)}"
        )


# ============================================================================
# State Comparison Endpoints
# ============================================================================


@router.post("/compare", summary="Compare two states")
async def compare_states(request: CompareStatesRequest):
    """
    Compare two equipment states and show differences.

    Returns:
    - Added parameters (in state 2 but not state 1)
    - Removed parameters (in state 1 but not state 2)
    - Modified parameters (different values)
    - Unchanged parameters
    """
    try:
        state1 = state_manager.get_state(request.state_id_1)
        state2 = state_manager.get_state(request.state_id_2)

        if not state1:
            raise HTTPException(
                status_code=404, detail=f"State {request.state_id_1} not found"
            )

        if not state2:
            raise HTTPException(
                status_code=404, detail=f"State {request.state_id_2} not found"
            )

        diff = state_manager.compare_states(state1, state2)

        # Create summary
        summary = {
            "total_parameters": len(state1.state_data),
            "added_count": len(diff.added),
            "removed_count": len(diff.removed),
            "modified_count": len(diff.modified),
            "unchanged_count": len(diff.unchanged),
            "has_differences": bool(diff.added or diff.removed or diff.modified),
        }

        return StateDiffResponse(
            state_id_1=diff.state_id_1,
            state_id_2=diff.state_id_2,
            equipment_id=diff.equipment_id,
            timestamp=diff.timestamp.isoformat(),
            added=diff.added,
            removed=diff.removed,
            modified=diff.modified,
            unchanged=diff.unchanged,
            summary=summary,
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error comparing states: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to compare states: {str(e)}"
        )


# ============================================================================
# State Management Endpoints
# ============================================================================


@router.delete("/delete/{state_id}", summary="Delete state")
async def delete_state(state_id: str):
    """
    Delete a captured state.

    Removes from memory and disk (if saved).
    """
    try:
        success = state_manager.delete_state(state_id)

        if success:
            return {
                "success": True,
                "message": "State deleted successfully",
                "state_id": state_id,
            }
        else:
            raise HTTPException(status_code=404, detail=f"State {state_id} not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting state: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete state: {str(e)}")


@router.post("/export/{state_id}", summary="Export state")
async def export_state(state_id: str):
    """
    Export state as JSON.

    Returns complete state data for backup or sharing.
    """
    try:
        state_dict = state_manager.export_state(state_id)

        return {"success": True, "state": state_dict}

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error exporting state: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export state: {str(e)}")


@router.post("/import", summary="Import state")
async def import_state(state_dict: dict):
    """
    Import state from JSON.

    Useful for restoring backups or sharing states.
    """
    try:
        state = state_manager.import_state(state_dict)

        return {
            "success": True,
            "message": "State imported successfully",
            "state_id": state.state_id,
            "equipment_id": state.equipment_id,
        }

    except Exception as e:
        logger.error(f"Error importing state: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to import state: {str(e)}")


# ============================================================================
# Version Management Endpoints
# ============================================================================


@router.post("/version/create/{equipment_id}", summary="Create state version")
async def create_state_version(
    equipment_id: str, change_description: Optional[str] = None
):
    """
    Create a versioned snapshot of current equipment state.

    Maintains version history with parent-child relationships.
    """
    try:
        equipment = equipment_manager.get_equipment(equipment_id)
        if not equipment:
            raise HTTPException(
                status_code=404, detail=f"Equipment {equipment_id} not found"
            )

        # Capture current state
        state = await state_manager.capture_state(
            equipment=equipment, description=change_description, save_to_disk=True
        )

        # Create version
        version = state_manager.create_version(
            equipment_id=equipment_id,
            state=state,
            change_description=change_description,
        )

        return {
            "success": True,
            "message": "Version created successfully",
            "version_id": version.version_id,
            "version_number": version.version_number,
            "state_id": state.state_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating version: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create version: {str(e)}"
        )


@router.get("/version/list/{equipment_id}", summary="List state versions")
async def list_state_versions(equipment_id: str):
    """
    Get all state versions for equipment.
    """
    try:
        versions = state_manager.get_versions(equipment_id)

        return {
            "equipment_id": equipment_id,
            "versions": [
                {
                    "version_id": v.version_id,
                    "version_number": v.version_number,
                    "state_id": v.state.state_id,
                    "parent_version_id": v.parent_version_id,
                    "change_description": v.change_description,
                    "created_at": v.created_at.isoformat(),
                }
                for v in versions
            ],
            "count": len(versions),
        }

    except Exception as e:
        logger.error(f"Error listing versions: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to list versions: {str(e)}"
        )


@router.get(
    "/version/get/{equipment_id}/{version_number}", summary="Get specific version"
)
async def get_state_version(equipment_id: str, version_number: int):
    """
    Get a specific state version.
    """
    try:
        version = state_manager.get_version(equipment_id, version_number)

        if not version:
            raise HTTPException(
                status_code=404,
                detail=f"Version {version_number} not found for equipment {equipment_id}",
            )

        return {
            "version_id": version.version_id,
            "version_number": version.version_number,
            "equipment_id": version.equipment_id,
            "parent_version_id": version.parent_version_id,
            "change_description": version.change_description,
            "created_at": version.created_at.isoformat(),
            "state": StateResponse(
                state_id=version.state.state_id,
                equipment_id=version.state.equipment_id,
                equipment_type=version.state.equipment_type,
                equipment_model=version.state.equipment_model,
                timestamp=version.state.timestamp.isoformat(),
                name=version.state.name,
                description=version.state.description,
                tags=version.state.tags,
                state_data=version.state.state_data,
                metadata=version.state.metadata,
            ).dict(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting version: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get version: {str(e)}")
