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


def _keyword_matches(keyword: str, model_upper: str) -> bool:
    """Whether a model keyword appears as a model name, not mid-word.

    A plain substring test is not enough. B&K's RFM3000 contains "M300", so
    it matched the Rigol M300 data acquisition driver -- and because the
    keyword registry is consulted before the B&K one, a B&K instrument would
    have been driven as a Rigol.

    Only the leading edge can be anchored: keywords are a mix of whole model
    names ("M300") and family prefixes ("DSG3", which has to match DSG3060),
    so requiring a boundary after the keyword would break the prefixes.
    """
    start = 0
    while True:
        index = model_upper.find(keyword, start)
        if index == -1:
            return False
        # A model name does not begin in the middle of a longer word.
        if index == 0 or not model_upper[index - 1].isalnum():
            return True
        start = index + 1


def find_keyword_driver(model_upper: str):
    """Return the first keyword-registered driver class matching a model string."""
    for cls in KEYWORD_DRIVER_CLASSES:
        keywords = getattr(cls, "MODEL_KEYWORDS", ())
        if any(_keyword_matches(k.upper(), model_upper) for k in keywords):
            return cls
    return None


class EquipmentManager:
    """Manages all connected equipment."""

    def __init__(self):
        """Initialize equipment manager."""
        self.equipment: Dict[str, BaseEquipment] = {}

        # What this server has identified before. Held on the data volume,
        # so it survives the container restart an upgrade performs -- the
        # list used to be emptied by every one of those, and rediscovering
        # a 1685B means inferring it from a USB bridge again.
        from server.equipment.inventory import EquipmentInventory

        self.inventory = EquipmentInventory()
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
        """Shut down, applying the disconnect policy to every instrument.

        This used to call `equipment.disconnect()` directly, which closes the
        port and sends nothing -- so an explicit disconnect through the API
        disabled a supply's output while stopping the server left it live.
        The same policy now governs both, because "what happens to the bench
        when LabLink goes away" should not depend on how it went away.
        """
        policy = self.default_disconnect_policy()
        async with self._lock:
            for equipment_id, equipment in self.equipment.items():
                try:
                    if policy == "off":
                        try:
                            if hasattr(equipment, "set_output"):
                                await equipment.set_output(False)
                            elif hasattr(equipment, "set_input"):
                                await equipment.set_input(False)
                            logger.info(f"Safe state applied to {equipment_id}")
                        except Exception as e:
                            # A shutdown must still shut down.
                            logger.error(
                                f"Error putting {equipment_id} into safe state: {e}"
                            )

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

    def _already_open(self, resource_string: str):
        """The id of a live instrument on this resource, if there is one.

        An entry that is present but no longer connected is dropped rather
        than returned: the instrument was unplugged or the link died, and the
        caller does want a fresh open in that case.
        """
        for equipment_id, equipment in list(self.equipment.items()):
            if getattr(equipment, "resource_string", None) != resource_string:
                continue
            if getattr(equipment, "connected", False):
                return equipment_id
            logger.info(
                "Dropping stale entry %s for %s before reconnecting",
                equipment_id, resource_string,
            )
            self.equipment.pop(equipment_id, None)
        return None

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

                # Already open? Opening the same resource twice is what
                # produces "[Errno 16] Resource busy": the refusal comes from
                # the server's own handle holding the USB interface, not from
                # anything being wrong with the instrument. Connecting
                # something that is already connected should hand back what is
                # already there.
                #
                # This matters most right after a restart, when the bench is
                # reconnected and the operator presses Connect on an
                # instrument the server has already opened.
                existing_id = self._already_open(resource_string)
                if existing_id is not None:
                    logger.info(
                        "%s is already open as %s; returning it",
                        resource_string, existing_id,
                    )
                    return existing_id

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

                # Remember what it is, so a restart does not lose the bench.
                self.inventory.remember(info)

                # Record connection event for diagnostics
                from server.diagnostics import diagnostics_manager
                diagnostics_manager.record_connection(equipment_id)

                self._notify_discovery(resource_string, equipment_id, connected=True)

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
        keyword_driver = find_keyword_driver(model_upper)
        if keyword_driver is not None:
            return keyword_driver(self.resource_manager, resource_string)

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

    # What to leave an instrument doing when LabLink lets go of it.
    #
    # "off" disables the output; "hold" leaves the instrument exactly as it is.
    # The default comes from settings.safe_state_on_disconnect, which has
    # always meant "off" -- this only gives the operator a way to say otherwise
    # for one disconnect, without changing the server's default for everyone.
    DISCONNECT_POLICIES = ("off", "hold")

    def default_disconnect_policy(self) -> str:
        """The policy used when a caller does not name one."""
        from server.config.settings import settings

        return "off" if settings.safe_state_on_disconnect else "hold"

    async def disconnect_device(self, equipment_id: str, policy: Optional[str] = None):
        """Disconnect a device, leaving it in the requested state.

        Args:
            equipment_id: the device to disconnect
            policy: "off" to disable the output first, "hold" to leave the
                instrument as it is. Defaults to the server's configured
                behaviour.

        Note that "hold" asks LabLink to send nothing. It is not a promise
        about the instrument: a supply whose serial port has `hupcl` set may
        still see DTR drop when the port closes. What this controls is whether
        LabLink itself turns the output off, which -- contrary to issue #198 --
        is what was actually happening.
        """
        if policy is None:
            policy = self.default_disconnect_policy()
        if policy not in self.DISCONNECT_POLICIES:
            raise ValueError(
                f"Unknown disconnect policy {policy!r}; "
                f"expected one of {', '.join(self.DISCONNECT_POLICIES)}"
            )

        async with self._lock:
            if equipment_id in self.equipment:
                equipment = self.equipment[equipment_id]

                if policy == "off":
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
                else:
                    # Worth a line of its own: "the output was still on when we
                    # let go" is exactly the thing someone reads the log for.
                    logger.info(
                        f"Leaving {equipment_id} as it is on disconnect "
                        f"(policy 'hold'); its output state is unchanged"
                    )

                await equipment.disconnect()
                del self.equipment[equipment_id]

                # Record disconnection event for diagnostics
                from server.diagnostics import diagnostics_manager
                diagnostics_manager.record_disconnection(equipment_id)

                self._notify_discovery(
                    equipment.resource_string, equipment_id, connected=False
                )

                logger.info(f"Disconnected device {equipment_id}")

    @staticmethod
    def _notify_discovery(
        resource_string: str, equipment_id: str, connected: bool
    ) -> None:
        """Tell discovery a resource changed hands, so its cache says so too.

        Best effort: discovery is bookkeeping, and a connection must not fail
        because the bookkeeping did (or because discovery is not running, as
        in the unit tests).
        """
        try:
            from server.discovery import get_discovery_manager

            manager = get_discovery_manager()
            if connected:
                manager.mark_connected_resource(resource_string, equipment_id)
            else:
                manager.mark_disconnected_resource(resource_string)
        except Exception as e:
            logger.debug(f"Discovery not updated for {resource_string}: {e}")

    def get_equipment(self, equipment_id: str) -> Optional[BaseEquipment]:
        """Get equipment by ID."""
        return self.equipment.get(equipment_id)

    async def get_connected_devices(self) -> List[EquipmentInfo]:
        """Every instrument this server knows, open or merely remembered.

        Remembered ones carry connected=False. They are listed so an
        operator can reconnect a bench that was identified in an earlier
        session instead of rediscovering it -- no port is opened by
        appearing here.
        """
        async with self._lock:
            devices = []
            open_ids = set()
            for equipment in self.equipment.values():
                if equipment.cached_info:
                    info = equipment.cached_info.model_copy(
                        update={"connected": True}
                    )
                    devices.append(info)
                    open_ids.add(info.id)

            for entry in self.inventory.entries():
                if entry.get("id") in open_ids:
                    continue
                try:
                    devices.append(EquipmentInfo(**{**entry, "connected": False}))
                except Exception as e:
                    # A remembered entry that no longer fits the model is
                    # not worth failing the whole list for.
                    equipment_id = entry.get("id")
                    logger.warning(f"Skipping remembered {equipment_id}: {e}")

            return devices

    async def get_device_status(self, equipment_id: str) -> Optional[EquipmentStatus]:
        """Get status of a specific device."""
        equipment = self.get_equipment(equipment_id)
        if equipment:
            return await equipment.get_status()
        return None


# Global equipment manager instance
equipment_manager = EquipmentManager()
