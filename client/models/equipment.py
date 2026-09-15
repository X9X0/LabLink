"""Equipment data models for GUI client."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class EquipmentType(str, Enum):
    """Equipment type enumeration."""

    OSCILLOSCOPE = "oscilloscope"
    POWER_SUPPLY = "power_supply"
    ELECTRONIC_LOAD = "electronic_load"
    MULTIMETER = "multimeter"
    FUNCTION_GENERATOR = "function_generator"
    SPECTRUM_ANALYZER = "spectrum_analyzer"
    RF_SIGNAL_GENERATOR = "rf_signal_generator"
    VECTOR_NETWORK_ANALYZER = "vector_network_analyzer"
    DATA_ACQUISITION = "data_acquisition"
    UNKNOWN = "unknown"


class ConnectionStatus(str, Enum):
    """Connection status enumeration."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    ERROR = "error"


@dataclass
class Equipment:
    """Equipment model."""

    equipment_id: str
    name: str
    equipment_type: EquipmentType
    manufacturer: str
    model: str
    resource_name: str
    connection_status: ConnectionStatus
    idn: Optional[str] = None
    capabilities: List[str] = None
    current_readings: Optional[Dict[str, Any]] = None
    health_score: Optional[float] = None
    last_update: Optional[datetime] = None
    #: Which server listed this instrument. None while only one server can be
    #: connected, which is every caller that predates multi-server support.
    server_name: Optional[str] = None

    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = []

    @property
    def key(self) -> str:
        """Identity that stays unique once several servers are connected.

        Equipment ids are minted per server, so two Pis that each discovered
        a supply can hand out the same one. Anything that stores a selection
        or looks an instrument back up has to carry the server with it.
        """
        return f"{self.server_name or ''}::{self.equipment_id}"

    @classmethod
    def from_api_dict(
        cls, data: Dict[str, Any], server_name: Optional[str] = None
    ) -> "Equipment":
        """Create Equipment from API response dictionary.

        Args:
            data: One entry from the server's equipment list.
            server_name: The connection it was listed through, which the
                server itself does not know and cannot report.
        """
        # Map field names from server API response to client model
        # Server uses "id", client uses "equipment_id"
        equipment_id = data.get("id") or data.get("equipment_id", "")

        # Server uses "resource_string", client uses "resource_name"
        resource_name = data.get("resource_string") or data.get("resource_name", "")

        # Use nickname as name if available, otherwise use model
        name = data.get("nickname") or data.get("name") or data.get("model", "Unknown")

        # The list now carries instruments the server remembers from an
        # earlier session as well as the ones it currently holds open, so
        # presence no longer implies connected. Older servers send no flag
        # and only list what is open, which is why the default is True.
        if "connection_status" in data:
            connection_status = data["connection_status"]
        else:
            connection_status = (
                "connected" if data.get("connected", True) else "disconnected"
            )

        return cls(
            equipment_id=equipment_id,
            name=name,
            equipment_type=EquipmentType(data.get("type", "unknown")),
            manufacturer=data.get("manufacturer", "Unknown"),
            model=data.get("model", "Unknown"),
            resource_name=resource_name,
            connection_status=ConnectionStatus(connection_status),
            idn=data.get("idn") or data.get("serial_number"),
            capabilities=data.get("capabilities", []),
            current_readings=data.get("readings"),
            last_update=datetime.now(),
            server_name=server_name,
        )

    def update_from_api(self, data: Dict[str, Any]):
        """Update equipment from API data."""
        if "connection_status" in data:
            self.connection_status = ConnectionStatus(data["connection_status"])
        if "readings" in data:
            self.current_readings = data["readings"]
        if "idn" in data:
            self.idn = data["idn"]
        self.last_update = datetime.now()


@dataclass
class EquipmentCommand:
    """Equipment command model."""

    command: str
    label: str
    description: str
    parameters: Dict[str, Any]
    category: str = "general"
