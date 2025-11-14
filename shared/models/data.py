"""Data models for measurements and waveforms."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class WaveformData(BaseModel):
    """Oscilloscope waveform data."""

    equipment_id: str = Field(..., description="Source equipment ID")
    channel: int = Field(..., description="Channel number")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Capture timestamp"
    )
    sample_rate: float = Field(..., description="Sample rate in Hz")
    time_scale: float = Field(..., description="Time per division in seconds")
    voltage_scale: float = Field(..., description="Voltage per division in volts")
    voltage_offset: float = Field(0.0, description="Voltage offset in volts")
    num_samples: int = Field(..., description="Number of samples")
    # Actual waveform data sent separately via binary WebSocket
    data_id: str = Field(..., description="ID to match with binary data transmission")


class MeasurementData(BaseModel):
    """Generic measurement data."""

    equipment_id: str = Field(..., description="Source equipment ID")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Measurement timestamp"
    )
    measurements: dict[str, float] = Field(
        ..., description="Measurement name to value mapping"
    )
    units: dict[str, str] = Field(..., description="Measurement name to unit mapping")


class PowerSupplyData(BaseModel):
    """Power supply output data."""

    equipment_id: str = Field(..., description="Source equipment ID")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Measurement timestamp"
    )
    channel: int = Field(1, description="Channel number")
    voltage_set: float = Field(..., description="Set voltage in volts")
    current_set: float = Field(..., description="Set current in amps")
    voltage_actual: Optional[float] = Field(
        None, description="Actual output voltage in volts"
    )
    current_actual: Optional[float] = Field(
        None, description="Actual output current in amps"
    )
    output_enabled: bool = Field(..., description="Whether output is enabled")
    in_cv_mode: Optional[bool] = Field(None, description="In constant voltage mode")
    in_cc_mode: Optional[bool] = Field(None, description="In constant current mode")


class ElectronicLoadData(BaseModel):
    """Electronic load data."""

    equipment_id: str = Field(..., description="Source equipment ID")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Measurement timestamp"
    )
    mode: str = Field(..., description="Operating mode (CC, CV, CR, CP)")
    setpoint: float = Field(..., description="Mode setpoint value")
    voltage: Optional[float] = Field(None, description="Measured voltage in volts")
    current: Optional[float] = Field(None, description="Measured current in amps")
    power: Optional[float] = Field(None, description="Measured power in watts")
    load_enabled: bool = Field(..., description="Whether load is enabled")
