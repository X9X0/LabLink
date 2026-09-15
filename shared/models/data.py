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


class MultimeterData(BaseModel):
    """Digital multimeter reading."""

    equipment_id: str = Field(..., description="Source equipment ID")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Measurement timestamp"
    )
    function: str = Field(
        ..., description="Measurement function (DCV, ACV, DCI, ACI, RES, FRES, ...)"
    )
    value: Optional[float] = Field(
        None, description="Measured value in base SI unit; None when overloaded"
    )
    unit: str = Field(..., description="Unit of the measured value (V, A, Ohm, Hz, s, F)")
    overload: bool = Field(False, description="True if the input exceeded the range")
    range_index: Optional[int] = Field(
        None, description="Vendor range index currently selected"
    )
    range_full_scale: Optional[float] = Field(
        None, description="Full-scale value of the selected range in base unit"
    )
    auto_range: Optional[bool] = Field(None, description="Whether auto-ranging is on")
    rate: Optional[str] = Field(None, description="Measurement rate (FAST, MEDIUM, SLOW)")
    secondary_function: Optional[str] = Field(
        None, description="Secondary (dual-display) function, if enabled"
    )
    secondary_value: Optional[float] = Field(
        None, description="Secondary display value, if enabled"
    )
    secondary_unit: Optional[str] = Field(None, description="Unit of secondary value")


class FunctionGeneratorData(BaseModel):
    """Function / arbitrary waveform generator channel state."""

    equipment_id: str = Field(..., description="Source equipment ID")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Query timestamp"
    )
    channel: int = Field(1, description="Output channel number")
    waveform: str = Field(..., description="Waveform shape (SIN, SQU, RAMP, PULS, NOIS, DC, ARB, ...)")
    frequency: Optional[float] = Field(None, description="Frequency in Hz")
    amplitude: Optional[float] = Field(None, description="Amplitude in the reported unit (default Vpp)")
    amplitude_unit: str = Field("VPP", description="Amplitude unit: VPP, VRMS or DBM")
    offset: Optional[float] = Field(None, description="DC offset in volts")
    phase: Optional[float] = Field(None, description="Start phase in degrees")
    duty_cycle: Optional[float] = Field(None, description="Duty cycle in percent (square/pulse)")
    symmetry: Optional[float] = Field(None, description="Ramp symmetry in percent")
    output_enabled: bool = Field(False, description="Whether the channel output is on")
    load_impedance: Optional[str] = Field(None, description="Output load (e.g. 50, INF/HighZ)")
    modulation: Optional[str] = Field(None, description="Active modulation type, if any")
    sweep_enabled: bool = Field(False, description="Sweep active")
    burst_enabled: bool = Field(False, description="Burst active")


class SpectrumData(BaseModel):
    """Spectrum / real-time analyzer trace."""

    equipment_id: str = Field(..., description="Source equipment ID")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Capture timestamp"
    )
    trace: int = Field(1, description="Trace number")
    start_frequency: float = Field(..., description="Start frequency in Hz")
    stop_frequency: float = Field(..., description="Stop frequency in Hz")
    center_frequency: Optional[float] = Field(None, description="Center frequency in Hz")
    span: Optional[float] = Field(None, description="Span in Hz")
    rbw: Optional[float] = Field(None, description="Resolution bandwidth in Hz")
    vbw: Optional[float] = Field(None, description="Video bandwidth in Hz")
    reference_level: Optional[float] = Field(None, description="Reference level")
    attenuation: Optional[float] = Field(None, description="Input attenuation in dB")
    unit: str = Field("dBm", description="Amplitude unit of the trace values")
    detector: Optional[str] = Field(None, description="Detector type")
    num_points: int = Field(..., description="Number of trace points")
    values: list[float] = Field(default_factory=list, description="Trace amplitude values")
    markers: dict[str, dict[str, float]] = Field(
        default_factory=dict, description="Marker name -> {frequency, amplitude}"
    )
    peak_frequency: Optional[float] = Field(None, description="Frequency of the trace maximum")
    peak_amplitude: Optional[float] = Field(None, description="Amplitude of the trace maximum")


class RFGeneratorData(BaseModel):
    """RF signal generator output state."""

    equipment_id: str = Field(..., description="Source equipment ID")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Query timestamp"
    )
    frequency: Optional[float] = Field(None, description="Carrier frequency in Hz")
    level: Optional[float] = Field(None, description="Output level")
    level_unit: str = Field("dBm", description="Level unit")
    output_enabled: bool = Field(False, description="RF output on")
    modulation_enabled: bool = Field(False, description="Any modulation on")
    modulation_type: Optional[str] = Field(None, description="AM, FM, PM, PULSE, IQ, ...")
    modulation_parameters: dict[str, float] = Field(
        default_factory=dict, description="Modulation depth/deviation/rate etc."
    )
    alc_enabled: Optional[bool] = Field(None, description="Automatic level control on")


class NetworkAnalyzerData(BaseModel):
    """Vector network analyzer trace (one S-parameter)."""

    equipment_id: str = Field(..., description="Source equipment ID")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Capture timestamp"
    )
    trace: int = Field(1, description="Trace number")
    parameter: str = Field(..., description="Measured parameter (S11, S21, S12, S22)")
    format: str = Field("MLOG", description="Trace format (MLOG, PHASe, SWR, SMITh, REAL, IMAG, ...)")
    start_frequency: float = Field(..., description="Start frequency in Hz")
    stop_frequency: float = Field(..., description="Stop frequency in Hz")
    num_points: int = Field(..., description="Number of sweep points")
    frequencies: list[float] = Field(default_factory=list, description="Stimulus frequencies in Hz")
    values: list[float] = Field(default_factory=list, description="Primary formatted values")
    secondary_values: list[float] = Field(
        default_factory=list, description="Secondary values (imaginary part / phase) when the format has two"
    )
    unit: str = Field("dB", description="Unit of the primary values")


class DataAcquisitionData(BaseModel):
    """Multi-channel data acquisition / switch unit scan result."""

    equipment_id: str = Field(..., description="Source equipment ID")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Scan timestamp"
    )
    readings: dict[str, float] = Field(
        default_factory=dict, description="Channel identifier (e.g. '101') -> value"
    )
    units: dict[str, str] = Field(default_factory=dict, description="Channel identifier -> unit")
    functions: dict[str, str] = Field(
        default_factory=dict, description="Channel identifier -> configured function"
    )
    scan_list: list[str] = Field(default_factory=list, description="Channels in the scan list")
    installed_modules: dict[str, str] = Field(
        default_factory=dict, description="Slot -> module model"
    )
