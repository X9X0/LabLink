"""API endpoints for equipment profile management."""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from server.equipment.profiles import profile_manager, EquipmentProfile

logger = logging.getLogger(__name__)

router = APIRouter()


class ProfileCreateRequest(BaseModel):
    """Request to create a profile."""
    name: str
    description: Optional[str] = None
    equipment_type: str
    model: str
    settings: dict
    tags: Optional[List[str]] = None


class ProfileListResponse(BaseModel):
    """Response for profile list."""
    profiles: List[EquipmentProfile]
    count: int


class ProfileResponse(BaseModel):
    """Response for single profile operations."""
    success: bool
    message: str
    profile: Optional[EquipmentProfile] = None


@router.get("/list", response_model=ProfileListResponse)
async def list_profiles(equipment_type: Optional[str] = None):
    """
    List all available equipment profiles.

    Args:
        equipment_type: Optional filter by equipment type

    Returns:
        List of profiles
    """
    try:
        profiles = profile_manager.list_profiles(equipment_type=equipment_type)
        return ProfileListResponse(
            profiles=profiles,
            count=len(profiles)
        )
    except Exception as e:
        logger.error(f"Error listing profiles: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list profiles: {str(e)}"
        )


@router.get("/{profile_name}", response_model=ProfileResponse)
async def get_profile(profile_name: str):
    """
    Get a specific profile by name.

    Args:
        profile_name: Name of the profile

    Returns:
        Profile data
    """
    try:
        profile = profile_manager.load_profile(profile_name)

        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Profile '{profile_name}' not found"
            )

        return ProfileResponse(
            success=True,
            message="Profile retrieved successfully",
            profile=profile
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get profile: {str(e)}"
        )


@router.post("/create", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(request: ProfileCreateRequest):
    """
    Create a new equipment profile.

    Args:
        request: Profile creation request

    Returns:
        Created profile
    """
    try:
        profile = EquipmentProfile(
            name=request.name,
            description=request.description,
            equipment_type=request.equipment_type,
            model=request.model,
            settings=request.settings,
            tags=request.tags or []
        )

        if profile_manager.save_profile(profile):
            return ProfileResponse(
                success=True,
                message=f"Profile '{request.name}' created successfully",
                profile=profile
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save profile"
            )

    except Exception as e:
        logger.error(f"Error creating profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create profile: {str(e)}"
        )


@router.put("/{profile_name}", response_model=ProfileResponse)
async def update_profile(profile_name: str, request: ProfileCreateRequest):
    """
    Update an existing profile.

    Args:
        profile_name: Name of profile to update
        request: Updated profile data

    Returns:
        Updated profile
    """
    try:
        # Check if profile exists
        existing_profile = profile_manager.load_profile(profile_name)
        if not existing_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Profile '{profile_name}' not found"
            )

        # Create updated profile
        profile = EquipmentProfile(
            name=request.name,
            description=request.description,
            equipment_type=request.equipment_type,
            model=request.model,
            settings=request.settings,
            tags=request.tags or [],
            created_at=existing_profile.created_at  # Preserve creation time
        )

        if profile_manager.save_profile(profile):
            # If name changed, delete old profile
            if request.name != profile_name:
                profile_manager.delete_profile(profile_name)

            return ProfileResponse(
                success=True,
                message=f"Profile updated successfully",
                profile=profile
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update profile"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}"
        )


@router.delete("/{profile_name}", response_model=ProfileResponse)
async def delete_profile(profile_name: str):
    """
    Delete a profile.

    Args:
        profile_name: Name of profile to delete

    Returns:
        Success status
    """
    try:
        if profile_manager.delete_profile(profile_name):
            return ProfileResponse(
                success=True,
                message=f"Profile '{profile_name}' deleted successfully"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Profile '{profile_name}' not found"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete profile: {str(e)}"
        )


@router.post("/{profile_name}/apply/{equipment_id}", response_model=ProfileResponse)
async def apply_profile_to_equipment(profile_name: str, equipment_id: str):
    """
    Apply a profile to connected equipment.

    Args:
        profile_name: Name of profile to apply
        equipment_id: ID of equipment to apply profile to

    Returns:
        Success status
    """
    try:
        from equipment.manager import equipment_manager

        equipment = equipment_manager.get_equipment(equipment_id)
        if not equipment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Equipment '{equipment_id}' not found"
            )

        if profile_manager.apply_profile(equipment, profile_name):
            return ProfileResponse(
                success=True,
                message=f"Profile '{profile_name}' applied to equipment '{equipment_id}'"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to apply profile"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error applying profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to apply profile: {str(e)}"
        )
