"""Equipment manager for handling multiple lab instruments."""

import asyncio
import logging
from typing import Dict, List, Optional

from pyvisa import ResourceManager

from shared.models.equipment import (EquipmentInfo, EquipmentStatus,
                                     EquipmentType)

from .base import BaseEquipment
from .bk_power_supply import BK1685B, BK1902B, BK9130B, BK9205B, BK9206B
from .mock.mock_electronic_load import MockElectronicLoad
from .mock.mock_multimeter import MockMultimeter
from .mock.mock_oscilloscope import MockOscilloscope
from .mock.mock_power_supply import MockPowerSupply
from .rigol_electronic_load import RigolDL3021A, RigolDL3031A
from .rigol_multimeter import RigolDM3058, RigolDM3058E, RigolDM3068
from .mock.mock_function_generator import MockFunctionGenerator
from .mock.mock_daq import MockDAQ
from .mock.mock_rf_generator import MockRFGenerator
from .mock.mock_spectrum_analyzer import MockSpectrumAnalyzer
from .rigol_multimeter_dm858 import RigolDM858, RigolDM858E
from .rigol_rf_generator import RigolDSG800, RigolDSG3000, RigolDSG5000
from .mock.mock_vna import MockVNA
from .rigol_daq import RigolM300
from .rigol_vna import RigolDNA6000, RigolRSAN
from .rigol_modern_scope import (RigolDHO800, RigolDHO1000, RigolDHO5000,
                                 RigolDS1000ZE, RigolDS4000, RigolDS6000,
                                 RigolDS8000R, RigolDS70000, RigolDS80000,
                                 RigolMHO900, RigolMSO5000, RigolMSO7000,
                                 RigolMSO8000)
from .rigol_spectrum_analyzer import (RigolDSA800, RigolDSA1000, RigolRSA800,
                                      RigolRSA3000, RigolRSA5000, RigolRSA6000)
from .rigol_function_generator import (RigolDG800, RigolDG800Pro, RigolDG900,
                                       RigolDG1000Z, RigolDG2000, RigolDG4000,
                                       RigolDG5000, RigolDG5000Pro, RigolDG6000)
from .rigol_power_supply import (RigolDP700, RigolDP800, RigolDP900, RigolDP1116A,
                                 RigolDP1308A, RigolDP2000)
from .rigol_scope import RigolDS1102D, RigolDS1104, RigolMSO2072A

logger = logging.getLogger(__name__)


# Driver classes that declare ``MODEL_KEYWORDS`` (upper-case model substrings).
# Matched in order, first hit wins, so put the most specific classes first
# (e.g. a VNA variant "RSA3030N" before the spectrum analyzer "RSA3030").
KEYWORD_DRIVER_CLASSES = [
    # Multimeters (DM858E before DM858; DM30xx handled by the explicit rules below)
    RigolDM858E,
    RigolDM858,
    # Electronic loads (DL3031/DL3041 rows; DL3021 handled by the explicit rule)
    RigolDL3031A,
    # RF signal generators
    RigolDSG5000,
    RigolDSG3000,
    RigolDSG800,
    # Vector network analyzers: RSAxxxxN must precede the RSA spectrum-analyzer classes
    RigolRSAN,
    RigolDNA6000,
    # Data acquisition
    RigolM300,
    # Oscilloscopes (modern SCPI tree); 5-digit DS7xxxx/DS8xxxx and -R before plain
    RigolDS1000ZE,
    RigolDS80000,
    RigolDS70000,
    RigolDS8000R,
    RigolMSO8000,
    RigolMSO7000,
    RigolMSO5000,
    RigolDHO5000,
    RigolMHO900,
    RigolDHO1000,
    RigolDHO800,
    RigolDS6000,
    RigolDS4000,
    # Spectrum analyzers (RSA before DSA; E/A suffixed models are listed first in each class)
    RigolRSA6000,
    RigolRSA800,
    RigolRSA5000,
    RigolRSA3000,
    RigolDSA1000,
    RigolDSA800,
    # Function generators: Pro platform before the classic classes
    RigolDG5000Pro,
    RigolDG800Pro,
    RigolDG6000,
    RigolDG5000,
    RigolDG4000,
    RigolDG2000,
    RigolDG1000Z,
    RigolDG900,
    RigolDG800,
    # Power supplies
    RigolDP1308A,
    RigolDP1116A,
    RigolDP2000,
    RigolDP900,
    RigolDP700,
    RigolDP800,
]


def find_keyword_driver(model_upper: str):
    """Return the first keyword-registered driver class matching a model string."""
    for cls in KEYWORD_DRIVER_CLASSES:
        keywords = getattr(cls, "MODEL_KEYWORDS", ())
        if any(k.upper() in model_upper for k in keywords):
            return cls
    return None


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
            from discovery import get_discovery_manager

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
                from discovery.models import DiscoveredDevice, DeviceType, DiscoveryMethod
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
                from diagnostics import diagnostics_manager
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
            elif (
                "DMM" in model_upper
                or "MULTIMETER" in model_upper
                or equipment_type == EquipmentType.MULTIMETER
            ):
                return MockMultimeter(None, resource_string)
            elif (
                "RFGEN" in model_upper
                or "RF" in model_upper
                or equipment_type == EquipmentType.RF_SIGNAL_GENERATOR
            ):
                return MockRFGenerator(None, resource_string)
            elif (
                "FGEN" in model_upper
                or "FUNCTION" in model_upper
                or "AWG" in model_upper
                or equipment_type == EquipmentType.FUNCTION_GENERATOR
            ):
                return MockFunctionGenerator(None, resource_string)
            elif (
                "SPECTRUM" in model_upper
                or "MOCKSA" in model_upper
                or "::SA::" in resource_string.upper()
                or equipment_type == EquipmentType.SPECTRUM_ANALYZER
            ):
                return MockSpectrumAnalyzer(None, resource_string)
            elif (
                "VNA" in model_upper
                or "NETWORK" in model_upper
                or equipment_type == EquipmentType.VECTOR_NETWORK_ANALYZER
            ):
                return MockVNA(None, resource_string)
            elif (
                "DAQ" in model_upper
                or "ACQUISITION" in model_upper
                or equipment_type == EquipmentType.DATA_ACQUISITION
            ):
                return MockDAQ(None, resource_string)

        # Real equipment requires resource_manager
        if not self.resource_manager:
            return None

        # Rigol oscilloscopes
        # MSO2000A / DS2000A share one command tree (2 analog channels)
        if any(
            k in model_upper
            for k in ("MSO2072", "MSO2102", "MSO2202", "MSO2302",
                      "DS2072", "DS2102", "DS2202", "DS2302", "DS2000A", "MSO2000A")
        ):
            return RigolMSO2072A(self.resource_manager, resource_string)
        # DS1000Z family (4 analog channels) shares the DS1104Z command tree
        elif any(
            k in model_upper
            for k in ("DS1104", "DS1054Z", "DS1074Z", "DS1000Z")
        ) and "Z-E" not in model_upper:
            return RigolDS1104(self.resource_manager, resource_string)
        # DS1000D/E legacy family (2 analog channels) shares the DS1102D tree
        elif any(k in model_upper for k in ("DS1102D", "DS1102E", "DS1052D", "DS1052E", "DS1102", "DS1000D", "DS1000E")):
            return RigolDS1102D(self.resource_manager, resource_string)

        # Rigol electronic loads
        elif "DL3021" in model_upper:
            return RigolDL3021A(self.resource_manager, resource_string)

        # Rigol digital multimeters (DM3058E must be tested before DM3058)
        elif "DM3068" in model_upper:
            return RigolDM3068(self.resource_manager, resource_string)
        elif "DM3058E" in model_upper:
            return RigolDM3058E(self.resource_manager, resource_string)
        elif "DM3058" in model_upper:
            return RigolDM3058(self.resource_manager, resource_string)

        # Keyword-registered driver families (Rigol DP, DG, DSA/RSA, DSG, ...)
        elif find_keyword_driver(model_upper) is not None:
            return find_keyword_driver(model_upper)(self.resource_manager, resource_string)

        # BK Precision power supplies
        elif "9206" in model_upper:
            return BK9206B(self.resource_manager, resource_string)
        elif "9205" in model_upper:
            return BK9205B(self.resource_manager, resource_string)
        elif "9130" in model_upper or "9131" in model_upper:
            return BK9130B(self.resource_manager, resource_string)
        elif "1685" in model_upper:
            return BK1685B(self.resource_manager, resource_string)
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

                # Record disconnection event for diagnostics
                from diagnostics import diagnostics_manager
                diagnostics_manager.record_disconnection(equipment_id)

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
