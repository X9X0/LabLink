"""Equipment profile management system."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field

from server.config.settings import settings

logger = logging.getLogger(__name__)


class EquipmentProfile(BaseModel):
    """Equipment configuration profile."""

    name: str = Field(..., description="Profile name")
    description: Optional[str] = Field(None, description="Profile description")
    equipment_type: str = Field(..., description="Equipment type (oscilloscope, power_supply, etc.)")
    model: str = Field(..., description="Equipment model")
    settings: Dict[str, Any] = Field(default_factory=dict, description="Equipment settings")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    modified_at: datetime = Field(default_factory=datetime.now, description="Last modification timestamp")
    tags: List[str] = Field(default_factory=list, description="Profile tags for categorization")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ProfileManager:
    """Manages equipment profiles."""

    def __init__(self):
        self.profile_dir = Path(settings.profile_dir)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.enabled = settings.enable_profiles
        self.auto_load = settings.auto_load_profiles
        self._profiles_cache: Dict[str, EquipmentProfile] = {}

    def _get_profile_path(self, profile_name: str) -> Path:
        """Get path for a profile file."""
        # Sanitize profile name
        safe_name = "".join(c for c in profile_name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name.replace(' ', '_')
        return self.profile_dir / f"{safe_name}.json"

    def save_profile(self, profile: EquipmentProfile) -> bool:
        """
        Save equipment profile to disk.

        Args:
            profile: EquipmentProfile to save

        Returns:
            bool: True if successful
        """
        if not self.enabled:
            logger.warning("Profiles disabled, cannot save")
            return False

        try:
            profile.modified_at = datetime.now()
            profile_path = self._get_profile_path(profile.name)

            with open(profile_path, 'w') as f:
                json.dump(profile.dict(), f, indent=2, default=str)

            self._profiles_cache[profile.name] = profile
            logger.info(f"Saved profile '{profile.name}' to {profile_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save profile '{profile.name}': {e}")
            return False

    def load_profile(self, profile_name: str) -> Optional[EquipmentProfile]:
        """
        Load equipment profile from disk.

        Args:
            profile_name: Name of profile to load

        Returns:
            EquipmentProfile if found, None otherwise
        """
        if not self.enabled:
            logger.warning("Profiles disabled, cannot load")
            return None

        # Check cache first
        if profile_name in self._profiles_cache:
            return self._profiles_cache[profile_name]

        try:
            profile_path = self._get_profile_path(profile_name)

            if not profile_path.exists():
                logger.warning(f"Profile '{profile_name}' not found at {profile_path}")
                return None

            with open(profile_path, 'r') as f:
                data = json.load(f)

            profile = EquipmentProfile(**data)
            self._profiles_cache[profile_name] = profile
            logger.info(f"Loaded profile '{profile_name}' from {profile_path}")
            return profile

        except Exception as e:
            logger.error(f"Failed to load profile '{profile_name}': {e}")
            return None

    def list_profiles(self, equipment_type: Optional[str] = None) -> List[EquipmentProfile]:
        """
        List all available profiles.

        Args:
            equipment_type: Optional filter by equipment type

        Returns:
            List of EquipmentProfiles
        """
        if not self.enabled:
            return []

        profiles = []

        try:
            for profile_file in self.profile_dir.glob("*.json"):
                try:
                    with open(profile_file, 'r') as f:
                        data = json.load(f)
                    profile = EquipmentProfile(**data)

                    if equipment_type is None or profile.equipment_type == equipment_type:
                        profiles.append(profile)

                except Exception as e:
                    logger.error(f"Error loading profile {profile_file}: {e}")

            return sorted(profiles, key=lambda p: p.modified_at, reverse=True)

        except Exception as e:
            logger.error(f"Error listing profiles: {e}")
            return []

    def delete_profile(self, profile_name: str) -> bool:
        """
        Delete equipment profile.

        Args:
            profile_name: Name of profile to delete

        Returns:
            bool: True if successful
        """
        if not self.enabled:
            logger.warning("Profiles disabled, cannot delete")
            return False

        try:
            profile_path = self._get_profile_path(profile_name)

            if not profile_path.exists():
                logger.warning(f"Profile '{profile_name}' not found")
                return False

            profile_path.unlink()
            if profile_name in self._profiles_cache:
                del self._profiles_cache[profile_name]

            logger.info(f"Deleted profile '{profile_name}'")
            return True

        except Exception as e:
            logger.error(f"Failed to delete profile '{profile_name}': {e}")
            return False

    def apply_profile(self, equipment, profile_name: str) -> bool:
        """
        Apply profile settings to equipment.

        Args:
            equipment: Equipment instance
            profile_name: Name of profile to apply

        Returns:
            bool: True if successful
        """
        profile = self.load_profile(profile_name)
        if not profile:
            return False

        try:
            # Verify equipment type matches
            if hasattr(equipment, 'model') and equipment.model != profile.model:
                logger.warning(
                    f"Profile model '{profile.model}' doesn't match equipment model '{equipment.model}'"
                )

            logger.info(f"Applying profile '{profile_name}' to equipment {equipment.cached_info.id if equipment.cached_info else 'unknown'}")

            # Apply settings
            # This is a placeholder - actual implementation depends on equipment driver structure
            # In a real scenario, you'd call appropriate equipment methods with profile.settings
            for key, value in profile.settings.items():
                logger.info(f"  Setting {key} = {value}")
                # Example: await equipment.execute_command(key, value)

            return True

        except Exception as e:
            logger.error(f"Failed to apply profile '{profile_name}': {e}")
            return False

    def create_profile_from_equipment(
        self,
        equipment,
        profile_name: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Optional[EquipmentProfile]:
        """
        Create a profile from current equipment settings.

        Args:
            equipment: Equipment instance
            profile_name: Name for the new profile
            description: Optional profile description
            tags: Optional tags

        Returns:
            EquipmentProfile if successful, None otherwise
        """
        try:
            # Get current equipment settings
            # This is a placeholder - actual implementation depends on equipment structure
            current_settings = {}

            profile = EquipmentProfile(
                name=profile_name,
                description=description or f"Profile for {equipment.model}",
                equipment_type=equipment.cached_info.type.value if equipment.cached_info else "unknown",
                model=equipment.model,
                settings=current_settings,
                tags=tags or []
            )

            if self.save_profile(profile):
                return profile

            return None

        except Exception as e:
            logger.error(f"Failed to create profile from equipment: {e}")
            return None


# Global profile manager instance
profile_manager = ProfileManager()


def create_default_profiles():
    """Create default profiles for common equipment configurations."""
    if not settings.enable_profiles:
        return

    logger.info("Creating default equipment profiles...")

    # Oscilloscope default profiles
    scope_profiles = [
        EquipmentProfile(
            name="Oscilloscope - Debug Quick",
            description="Quick debug settings: 1ms/div, AC coupling, auto trigger",
            equipment_type="oscilloscope",
            model="generic",
            settings={
                "timebase_scale": 0.001,  # 1ms/div
                "channel_1_scale": 1.0,    # 1V/div
                "channel_1_coupling": "AC",
                "trigger_mode": "auto"
            },
            tags=["debug", "quick", "default"]
        ),
        EquipmentProfile(
            name="Oscilloscope - Power Analysis",
            description="Power supply analysis: 10us/div, DC coupling",
            equipment_type="oscilloscope",
            model="generic",
            settings={
                "timebase_scale": 0.00001,  # 10us/div
                "channel_1_scale": 5.0,      # 5V/div
                "channel_1_coupling": "DC",
                "trigger_mode": "normal"
            },
            tags=["power", "analysis"]
        )
    ]

    # Power supply default profiles
    ps_profiles = [
        EquipmentProfile(
            name="Power Supply - 5V Logic",
            description="5V @ 1A for digital logic circuits",
            equipment_type="power_supply",
            model="generic",
            settings={
                "voltage": 5.0,
                "current_limit": 1.0,
                "output_enabled": False
            },
            tags=["5v", "logic", "default"]
        ),
        EquipmentProfile(
            name="Power Supply - 3.3V MCU",
            description="3.3V @ 500mA for microcontrollers",
            equipment_type="power_supply",
            model="generic",
            settings={
                "voltage": 3.3,
                "current_limit": 0.5,
                "output_enabled": False
            },
            tags=["3v3", "mcu", "default"]
        ),
        EquipmentProfile(
            name="Power Supply - 12V Standard",
            description="12V @ 2A for general use",
            equipment_type="power_supply",
            model="generic",
            settings={
                "voltage": 12.0,
                "current_limit": 2.0,
                "output_enabled": False
            },
            tags=["12v", "standard"]
        )
    ]

    # Electronic load default profiles
    load_profiles = [
        EquipmentProfile(
            name="Electronic Load - Battery Test",
            description="Constant current mode for battery discharge testing",
            equipment_type="electronic_load",
            model="generic",
            settings={
                "mode": "CC",
                "current": 1.0,
                "load_enabled": False
            },
            tags=["battery", "discharge", "test"]
        ),
        EquipmentProfile(
            name="Electronic Load - Power Supply Test",
            description="Constant resistance mode for power supply testing",
            equipment_type="electronic_load",
            model="generic",
            settings={
                "mode": "CR",
                "resistance": 10.0,
                "load_enabled": False
            },
            tags=["power_supply", "test"]
        )
    ]

    # Save all default profiles
    all_profiles = scope_profiles + ps_profiles + load_profiles
    for profile in all_profiles:
        profile_manager.save_profile(profile)

    logger.info(f"Created {len(all_profiles)} default profiles")
