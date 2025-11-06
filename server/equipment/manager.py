"""Equipment manager for handling multiple lab instruments."""

import logging
from typing import Dict, List, Optional
import asyncio
from pyvisa import ResourceManager

import sys
sys.path.append("../../shared")
from models.equipment import EquipmentInfo, EquipmentStatus, EquipmentType

from .base import BaseEquipment
from .rigol_scope import RigolMSO2072A
from .bk_power_supply import BK9206B, BK9130B
from .bk_electronic_load import BK1902B

logger = logging.getLogger(__name__)


class EquipmentManager:
    """Manages all connected equipment."""

    def __init__(self):
        """Initialize equipment manager."""
        self.equipment: Dict[str, BaseEquipment] = {}
        self.resource_manager: Optional[ResourceManager] = None
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Initialize the equipment manager."""
        try:
            self.resource_manager = ResourceManager("@py")
            logger.info("Equipment manager initialized")
            await self.discover_devices()
        except Exception as e:
            logger.error(f"Failed to initialize equipment manager: {e}")

    async def shutdown(self):
        """Shutdown and cleanup all equipment connections."""
        async with self._lock:
            for equipment_id, equipment in self.equipment.items():
                try:
                    await equipment.disconnect()
                    logger.info(f"Disconnected {equipment_id}")
                except Exception as e:
                    logger.error(f"Error disconnecting {equipment_id}: {e}")
            self.equipment.clear()

        if self.resource_manager:
            self.resource_manager.close()

    async def discover_devices(self) -> List[str]:
        """Discover available VISA devices."""
        if not self.resource_manager:
            return []

        try:
            resources = self.resource_manager.list_resources()
            logger.info(f"Discovered VISA resources: {resources}")
            return list(resources)
        except Exception as e:
            logger.error(f"Error discovering devices: {e}")
            return []

    async def connect_device(self, resource_string: str, equipment_type: EquipmentType, model: str) -> str:
        """Connect to a device and add it to the manager."""
        async with self._lock:
            try:
                # Create appropriate equipment instance based on model
                equipment = self._create_equipment_instance(resource_string, equipment_type, model)

                if equipment is None:
                    raise ValueError(f"Unsupported equipment model: {model}")

                # Connect to the device
                await equipment.connect()

                # Get equipment info
                info = await equipment.get_info()
                equipment_id = info.id

                # Store equipment
                self.equipment[equipment_id] = equipment

                logger.info(f"Connected to {model} at {resource_string} with ID {equipment_id}")
                return equipment_id

            except Exception as e:
                logger.error(f"Failed to connect to device at {resource_string}: {e}")
                raise

    def _create_equipment_instance(
        self, resource_string: str, equipment_type: EquipmentType, model: str
    ) -> Optional[BaseEquipment]:
        """Create appropriate equipment instance based on model."""
        if not self.resource_manager:
            return None

        model_upper = model.upper()

        # Rigol oscilloscopes
        if "MSO2072A" in model_upper or "MSO2072" in model_upper:
            return RigolMSO2072A(self.resource_manager, resource_string)

        # BK Precision power supplies
        elif "9206" in model_upper:
            return BK9206B(self.resource_manager, resource_string)
        elif "9130" in model_upper or "9131" in model_upper:
            return BK9130B(self.resource_manager, resource_string)

        # BK Precision electronic loads
        elif "1902" in model_upper:
            return BK1902B(self.resource_manager, resource_string)

        return None

    async def disconnect_device(self, equipment_id: str):
        """Disconnect a device."""
        async with self._lock:
            if equipment_id in self.equipment:
                await self.equipment[equipment_id].disconnect()
                del self.equipment[equipment_id]
                logger.info(f"Disconnected device {equipment_id}")

    def get_equipment(self, equipment_id: str) -> Optional[BaseEquipment]:
        """Get equipment by ID."""
        return self.equipment.get(equipment_id)

    def get_connected_devices(self) -> List[EquipmentInfo]:
        """Get list of all connected devices."""
        return [equipment.cached_info for equipment in self.equipment.values() if equipment.cached_info]

    async def get_device_status(self, equipment_id: str) -> Optional[EquipmentStatus]:
        """Get status of a specific device."""
        equipment = self.get_equipment(equipment_id)
        if equipment:
            return await equipment.get_status()
        return None


# Global equipment manager instance
equipment_manager = EquipmentManager()
