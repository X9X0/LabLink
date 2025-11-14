"""Command and response models."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class Command(BaseModel):
    """Generic command structure."""

    command_id: str = Field(..., description="Unique command identifier")
    equipment_id: str = Field(..., description="Target equipment ID")
    action: str = Field(..., description="Action to perform")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Action parameters"
    )
    session_id: Optional[str] = Field(
        None, description="Session ID for lock verification"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Command timestamp"
    )


class CommandResponse(BaseModel):
    """Response to a command."""

    command_id: str = Field(..., description="ID of command this responds to")
    success: bool = Field(..., description="Whether command succeeded")
    data: Optional[Any] = Field(None, description="Response data if any")
    error: Optional[str] = Field(None, description="Error message if failed")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Response timestamp"
    )


class DataStreamConfig(BaseModel):
    """Configuration for data streaming."""

    equipment_id: str = Field(..., description="Equipment to stream from")
    stream_type: str = Field(
        ..., description="Type of data to stream (waveform, measurements, etc)"
    )
    interval_ms: int = Field(
        100, description="Update interval in milliseconds", ge=10, le=10000
    )
    enabled: bool = Field(True, description="Whether streaming is enabled")
    buffer_size: int = Field(
        1000, description="Number of samples to buffer before writing"
    )
