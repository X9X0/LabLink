"""Equipment data models."""

from enum import Enum
from typing import Optional, List
from datetime import datetime
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

    # Diagnostic fields (v0.12.0)
    temperature_celsius: Optional[float] = Field(None, description="Current equipment temperature in Celsius")
    operating_hours: Optional[float] = Field(None, description="Cumulative operating hours")
    error_code: Optional[int] = Field(None, description="Last equipment error code")
    error_message: Optional[str] = Field(None, description="Last equipment error message")
    last_calibration_date: Optional[datetime] = Field(None, description="Date of last calibration")
    calibration_due_date: Optional[datetime] = Field(None, description="Date calibration is due")
    calibration_status: Optional[str] = Field(None, description="Calibration status (current, due, overdue)")
    self_test_status: Optional[str] = Field(None, description="Built-in self-test status")
    self_test_last_run: Optional[datetime] = Field(None, description="Last self-test execution time")
    health_score: Optional[float] = Field(None, description="Equipment health score (0-100)")
    last_error_messages: List[str] = Field(default_factory=list, description="Recent error messages")


class EquipmentCommand(BaseModel):
    """Command to send to equipment."""
    equipment_id: str = Field(..., description="Target equipment ID")
    command: str = Field(..., description="Command to execute")
    parameters: dict = Field(default_factory=dict, description="Command parameters")
