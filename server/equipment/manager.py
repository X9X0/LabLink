"""Equipment manager for handling multiple lab instruments."""

import asyncio
import logging
from typing import Dict, List, Optional

from pyvisa import ResourceManager

from shared.models.equipment import (EquipmentInfo, EquipmentStatus,
                                     EquipmentType)

from .base import BaseEquipment
from .bk_electronic_load import BK1902B
from .bk_power_supply import BK1685B, BK9130B, BK9205B, BK9206B
from .mock.mock_electronic_load import MockElectronicLoad
from .mock.mock_oscilloscope import MockOscilloscope
from .mock.mock_power_supply import MockPowerSupply
from .rigol_electronic_load import RigolDL3021A
from .rigol_scope import RigolDS1102D, RigolDS1104, RigolMSO2072A

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

    async def connect_device(
        self, resource_string: str, equipment_type: EquipmentType, model: str
    ) -> str:
        """Connect to a device and add it to the manager."""
        async with self._lock:
            try:
                # Create appropriate equipment instance based on model
                equipment = self._create_equipment_instance(
                    resource_string, equipment_type, model
                )

                if equipment is None:
                    raise ValueError(f"Unsupported equipment model: {model}")

                # Connect to the device
                await equipment.connect()

                # Get equipment info
                info = await equipment.get_info()
                equipment_id = info.id

                # Store equipment
                self.equipment[equipment_id] = equipment

                logger.info(
                    f"Connected to {model} at {resource_string} with ID {equipment_id}"
                )
                return equipment_id

            except Exception as e:
                logger.error(f"Failed to connect to device at {resource_string}: {e}")
                raise

    def _create_equipment_instance(
        self, resource_string: str, equipment_type: EquipmentType, model: str
    ) -> Optional[BaseEquipment]:
        """Create appropriate equipment instance based on model."""
        model_upper = model.upper()

        # Mock equipment (doesn't require resource_manager)
        if "MOCK" in model_upper or "MOCK::" in resource_string.upper():
            if (
                "SCOPE" in model_upper
                or "OSCILLOSCOPE" in model_upper
                or equipment_type == EquipmentType.OSCILLOSCOPE
            ):
                return MockOscilloscope(None, resource_string)
            elif (
                "PSU" in model_upper
                or "POWER" in model_upper
                or equipment_type == EquipmentType.POWER_SUPPLY
            ):
                return MockPowerSupply(None, resource_string)
            elif (
                "LOAD" in model_upper or equipment_type == EquipmentType.ELECTRONIC_LOAD
            ):
                return MockElectronicLoad(None, resource_string)

        # Real equipment requires resource_manager
        if not self.resource_manager:
            return None

        # Rigol oscilloscopes
        if "MSO2072A" in model_upper or "MSO2072" in model_upper:
            return RigolMSO2072A(self.resource_manager, resource_string)
        elif "DS1104" in model_upper or "DS1104Z" in model_upper:
            return RigolDS1104(self.resource_manager, resource_string)
        elif "DS1102D" in model_upper or "DS1102" in model_upper:
            return RigolDS1102D(self.resource_manager, resource_string)

        # Rigol electronic loads
        elif "DL3021" in model_upper:
            return RigolDL3021A(self.resource_manager, resource_string)

        # BK Precision power supplies
        elif "9206" in model_upper:
            return BK9206B(self.resource_manager, resource_string)
        elif "9205" in model_upper:
            return BK9205B(self.resource_manager, resource_string)
        elif "9130" in model_upper or "9131" in model_upper:
            return BK9130B(self.resource_manager, resource_string)
        elif "1685" in model_upper:
            return BK1685B(self.resource_manager, resource_string)

        # BK Precision electronic loads
        elif "1902" in model_upper:
            return BK1902B(self.resource_manager, resource_string)

        return None

    async def disconnect_device(self, equipment_id: str):
        """Disconnect a device."""
        async with self._lock:
            if equipment_id in self.equipment:
                equipment = self.equipment[equipment_id]

                # Safe state on disconnect - disable outputs
                from config.settings import settings

                if settings.safe_state_on_disconnect:
                    try:
                        logger.info(
                            f"Putting {equipment_id} into safe state before disconnect"
                        )

                        # Try to disable output based on equipment type
                        if hasattr(equipment, "set_output"):
                            # Power supply
                            await equipment.set_output(False)
                            logger.info(f"Disabled output for {equipment_id}")
                        elif hasattr(equipment, "set_input"):
                            # Electronic load
                            await equipment.set_input(False)
                            logger.info(f"Disabled input for {equipment_id}")

                    except Exception as e:
                        logger.error(
                            f"Error putting {equipment_id} into safe state: {e}"
                        )

                await equipment.disconnect()
                del self.equipment[equipment_id]
                logger.info(f"Disconnected device {equipment_id}")

    def get_equipment(self, equipment_id: str) -> Optional[BaseEquipment]:
        """Get equipment by ID."""
        return self.equipment.get(equipment_id)

    def get_connected_devices(self) -> List[EquipmentInfo]:
        """Get list of all connected devices."""
        return [
            equipment.cached_info
            for equipment in self.equipment.values()
            if equipment.cached_info
        ]

    async def get_device_status(self, equipment_id: str) -> Optional[EquipmentStatus]:
        """Get status of a specific device."""
        equipment = self.get_equipment(equipment_id)
        if equipment:
            return await equipment.get_status()
        return None


# Global equipment manager instance
equipment_manager = EquipmentManager()
