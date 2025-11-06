"""Equipment data models."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class EquipmentType(str, Enum):
    """Types of supported equipment."""
    OSCILLOSCOPE = "oscilloscope"
    POWER_SUPPLY = "power_supply"
    ELECTRONIC_LOAD = "electronic_load"
    MULTIMETER = "multimeter"
    FUNCTION_GENERATOR = "function_generator"


class ConnectionType(str, Enum):
    """Types of equipment connections."""
    USB = "usb"
    SERIAL = "serial"
    ETHERNET = "ethernet"
    GPIB = "gpib"


class EquipmentInfo(BaseModel):
    """Information about a piece of equipment."""
    id: str = Field(..., description="Unique identifier for this equipment")
    type: EquipmentType = Field(..., description="Type of equipment")
    manufacturer: str = Field(..., description="Equipment manufacturer")
    model: str = Field(..., description="Equipment model number")
    serial_number: Optional[str] = Field(None, description="Serial number")
    connection_type: ConnectionType = Field(..., description="Type of connection")
    resource_string: str = Field(..., description="VISA resource string or connection info")
    nickname: Optional[str] = Field(None, description="User-defined nickname")


class EquipmentStatus(BaseModel):
    """Current status of equipment."""
    id: str = Field(..., description="Equipment ID")
    connected: bool = Field(..., description="Whether equipment is currently connected")
    error: Optional[str] = Field(None, description="Error message if connection failed")
    firmware_version: Optional[str] = Field(None, description="Firmware version")
    capabilities: dict = Field(default_factory=dict, description="Equipment-specific capabilities")


class EquipmentCommand(BaseModel):
    """Command to send to equipment."""
    equipment_id: str = Field(..., description="Target equipment ID")
    command: str = Field(..., description="Command to execute")
    parameters: dict = Field(default_factory=dict, description="Command parameters")
