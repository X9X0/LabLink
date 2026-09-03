"""Equipment manager for handling multiple lab instruments."""

import asyncio
import logging
from typing import Dict, List, Optional

from pyvisa import ResourceManager

from shared.models.equipment import (EquipmentInfo, EquipmentStatus,
                                     EquipmentType)

from .base import BaseEquipment
from .bk_power_supply import (BK1685B, BK1687B, BK1688B, BK1696, BK1901B,
                              BK1902B, BK9103, BK9104, BK9130B, BK9205B,
                              BK9206B)
from .bk_registry import (PROTOCOL_SCPI, equipment_type_for, resolve_model)
from .bk_scpi import (BKSCPIElectronicLoad, BKSCPIMultimeter,
                      BKSCPIPowerSupply)
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
            self.resource_manager = None

    async def discover_devices(self):
        """Discover available VISA devices using discovery manager.

        Returns:
            List of DiscoveredDevice objects with full device information
        """
        try:
            # Use discovery manager for comprehensive discovery with filtering
            from server.discovery import get_discovery_manager

            discovery_manager = get_discovery_manager()
            result = await discovery_manager.scan()

            # Return full discovered device objects
            devices = result.devices
            logger.info(f"Discovered {len(devices)} VISA resources via discovery manager")
            return devices

        except Exception as e:
            # Fallback to direct VISA scanning if discovery manager not available
            logger.warning(f"Discovery manager not available, falling back to direct VISA scan: {e}")

            if not self.resource_manager:
                return []

            try:
                from server.discovery.models import DiscoveredDevice, DeviceType, DiscoveryMethod
                import uuid

                resources = self.resource_manager.list_resources()
                logger.info(f"Discovered VISA resources (fallback): {resources}")

                # Convert resource strings to minimal DiscoveredDevice objects
                devices = []
                for resource in resources:
                    device = DiscoveredDevice(
                        device_id=str(uuid.uuid4()),
                        resource_name=resource,
                        device_type=DeviceType.UNKNOWN,
                        discovery_method=DiscoveryMethod.VISA,
                        confidence_score=0.5,
                    )
                    devices.append(device)

                return devices
            except Exception as e2:
                logger.error(f"Error discovering devices: {e2}")
                return []

    async def connect_device(
        self, resource_string: str, equipment_type: EquipmentType, model: str
    ) -> str:
        """Connect to a device and add it to the manager."""
        async with self._lock:
            try:
                # Ensure resource manager is initialized (lazy initialization)
                # Always create a new one if None or invalid
                if not self.resource_manager:
                    logger.warning("Resource manager not initialized, initializing now...")
                    self.resource_manager = ResourceManager("@py")
                    logger.info("Resource manager initialized (lazy)")
                else:
                    # Try to use existing resource manager, recreate if closed
                    try:
                        # Test if resource manager is valid by attempting to list resources
                        _ = self.resource_manager.list_resources()
                    except Exception:
                        logger.warning("Resource manager invalid, recreating...")
                        try:
                            self.resource_manager.close()
                        except Exception:
                            pass
                        self.resource_manager = ResourceManager("@py")
                        logger.info("Resource manager recreated")

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

                # Record connection event for diagnostics
                from server.diagnostics import diagnostics_manager
                diagnostics_manager.record_connection(equipment_id)

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

        # B&K Precision: dispatched through the model registry so every
        # documented family is reachable, not just the hand-listed few.
        bk_equipment = self._create_bk_instance(
            resource_string, equipment_type, model
        )
        if bk_equipment is not None:
            return bk_equipment

        return None

    #: Models with a hand-written driver, which wins over the generic one.
    _BK_SPECIFIC_DRIVERS = {
        "1685B": BK1685B, "1687B": BK1687B, "1688B": BK1688B,
        "1901B": BK1901B, "1902B": BK1902B,
        "9103": BK9103, "9104": BK9104,
        "9130B": BK9130B, "9131B": BK9130B, "9132B": BK9130B,
        "9205B": BK9205B, "9206B": BK9206B,
        "1696": BK1696, "1697": BK1696, "1698": BK1696,
    }

    #: Generic SCPI driver per LabLink equipment type.
    _BK_GENERIC_DRIVERS = {
        EquipmentType.POWER_SUPPLY: BKSCPIPowerSupply,
        EquipmentType.ELECTRONIC_LOAD: BKSCPIElectronicLoad,
        EquipmentType.MULTIMETER: BKSCPIMultimeter,
    }

    def _create_bk_instance(
        self, resource_string: str, equipment_type: EquipmentType, model: str
    ) -> Optional[BaseEquipment]:
        """Build a B&K driver for `model`, or None if it is not a B&K model.

        A SKU is resolved to its family first, so a 9241 gets the 9240-series
        driver and a 2569B-MSO is recognised as a 2560B scope, rather than
        falling through as unsupported.
        """
        info = resolve_model(model)
        if info is None:
            return None

        # An exact SKU with its own driver takes precedence over the family's.
        sku = model.upper().replace(" ", "").replace("-", "")
        for candidate in (sku, info.key):
            driver = self._BK_SPECIFIC_DRIVERS.get(candidate)
            if driver:
                return driver(self.resource_manager, resource_string)
        for documented_sku in info.skus:
            if sku.endswith(documented_sku) and documented_sku in self._BK_SPECIFIC_DRIVERS:
                return self._BK_SPECIFIC_DRIVERS[documented_sku](
                    self.resource_manager, resource_string
                )

        # No hand-written driver: the generic SCPI drivers cover the rest,
        # but only where the protocol family and the category both line up.
        if info.protocol != PROTOCOL_SCPI:
            logger.warning(
                f"B&K {info.name} speaks the {info.protocol} protocol, which "
                f"has no LabLink driver yet"
            )
            return None

        resolved_type = equipment_type_for(info)
        if resolved_type is None:
            logger.warning(
                f"B&K {info.name} is a {info.category}; LabLink has no "
                f"equipment type for it"
            )
            return None

        driver = self._BK_GENERIC_DRIVERS.get(EquipmentType(resolved_type))
        if driver is None:
            return None

        logger.info(
            f"Using the generic B&K SCPI driver for {info.name} "
            f"({resolved_type})"
        )
        return driver(self.resource_manager, resource_string, model=model)

    async def disconnect_device(self, equipment_id: str):
        """Disconnect a device."""
        async with self._lock:
            if equipment_id in self.equipment:
                equipment = self.equipment[equipment_id]

                # Safe state on disconnect - disable outputs
                from server.config.settings import settings

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

                # Record disconnection event for diagnostics
                from server.diagnostics import diagnostics_manager
                diagnostics_manager.record_disconnection(equipment_id)

                logger.info(f"Disconnected device {equipment_id}")

    def get_equipment(self, equipment_id: str) -> Optional[BaseEquipment]:
        """Get equipment by ID."""
        return self.equipment.get(equipment_id)

    async def get_connected_devices(self) -> List[EquipmentInfo]:
        """Get list of all connected devices."""
        async with self._lock:
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
