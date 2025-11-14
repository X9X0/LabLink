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

    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = []

    @classmethod
    def from_api_dict(cls, data: Dict[str, Any]) -> "Equipment":
        """Create Equipment from API response dictionary."""
        return cls(
            equipment_id=data.get("equipment_id", ""),
            name=data.get("name", "Unknown"),
            equipment_type=EquipmentType(data.get("type", "unknown")),
            manufacturer=data.get("manufacturer", "Unknown"),
            model=data.get("model", "Unknown"),
            resource_name=data.get("resource_name", ""),
            connection_status=ConnectionStatus(
                data.get("connection_status", "disconnected")
            ),
            idn=data.get("idn"),
            capabilities=data.get("capabilities", []),
            current_readings=data.get("readings"),
            last_update=datetime.now(),
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
