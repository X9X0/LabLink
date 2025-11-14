"""Waveform data models for advanced oscilloscope features."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np
from pydantic import BaseModel, Field


class CursorType(str, Enum):
    """Cursor type enumeration."""

    HORIZONTAL = "horizontal"  # Time cursors
    VERTICAL = "vertical"  # Voltage cursors


class MathOperation(str, Enum):
    """Math channel operations."""

    ADD = "add"  # Ch1 + Ch2
    SUBTRACT = "subtract"  # Ch1 - Ch2
    MULTIPLY = "multiply"  # Ch1 * Ch2
    DIVIDE = "divide"  # Ch1 / Ch2
    FFT = "fft"  # FFT of channel
    INTEGRATE = "integrate"  # Integration
    DIFFERENTIATE = "differentiate"  # Differentiation
    INVERT = "invert"  # -Ch1
    AVERAGE = "average"  # Running average
    ENVELOPE = "envelope"  # Signal envelope
    ABS = "abs"  # Absolute value
    SQRT = "sqrt"  # Square root
    SQUARE = "square"  # Square
    LOG = "log"  # Natural logarithm
    EXP = "exp"  # Exponential


class PersistenceMode(str, Enum):
    """Persistence display modes."""

    OFF = "off"  # No persistence
    INFINITE = "infinite"  # Accumulate all waveforms
    VARIABLE = "variable"  # Variable persistence with decay
    ENVELOPE = "envelope"  # Show min/max envelope


class ExtendedWaveformData(BaseModel):
    """Extended waveform data with actual voltage and time arrays."""

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
    data_id: str = Field(..., description="Unique data identifier")

    # Actual waveform data (serialized as lists for JSON)
    time_data: List[float] = Field(
        default_factory=list, description="Time values in seconds"
    )
    voltage_data: List[float] = Field(
        default_factory=list, description="Voltage values in volts"
    )

    # Acquisition metadata
    trigger_time: Optional[float] = Field(None, description="Trigger time in seconds")
    pre_trigger_samples: Optional[int] = Field(
        None, description="Number of pre-trigger samples"
    )

    class Config:
        json_encoders = {
            np.ndarray: lambda v: v.tolist() if isinstance(v, np.ndarray) else v
        }


class CursorData(BaseModel):
    """Cursor measurement data."""

    cursor_type: CursorType = Field(
        ..., description="Cursor type (horizontal/vertical)"
    )
    cursor1_position: float = Field(..., description="Position of cursor 1")
    cursor2_position: float = Field(..., description="Position of cursor 2")
    delta: float = Field(..., description="Delta between cursors")

    # For horizontal cursors (time)
    delta_time: Optional[float] = Field(None, description="Time difference (seconds)")
    frequency: Optional[float] = Field(
        None, description="Frequency from delta time (Hz)"
    )

    # For vertical cursors (voltage)
    delta_voltage: Optional[float] = Field(None, description="Voltage difference (V)")

    # Values at cursor positions
    cursor1_value: Optional[float] = Field(
        None, description="Waveform value at cursor 1"
    )
    cursor2_value: Optional[float] = Field(
        None, description="Waveform value at cursor 2"
    )


class MathChannelConfig(BaseModel):
    """Math channel configuration."""

    operation: MathOperation = Field(..., description="Math operation")
    source_channel1: int = Field(..., description="Primary source channel")
    source_channel2: Optional[int] = Field(
        None, description="Secondary source channel (for binary ops)"
    )
    scale: float = Field(1.0, description="Output scale factor")
    offset: float = Field(0.0, description="Output offset")

    # FFT-specific parameters
    fft_window: Optional[str] = Field("hann", description="FFT window function")
    fft_mode: Optional[str] = Field(
        "magnitude", description="FFT mode (magnitude/phase/real/imag)"
    )

    # Average-specific parameters
    average_count: Optional[int] = Field(
        10, description="Number of waveforms to average"
    )

    # Filter parameters
    filter_cutoff: Optional[float] = Field(
        None, description="Filter cutoff frequency (Hz)"
    )


class PersistenceConfig(BaseModel):
    """Persistence mode configuration."""

    mode: PersistenceMode = Field(..., description="Persistence mode")
    decay_time: Optional[float] = Field(
        1.0, description="Decay time for variable persistence (seconds)"
    )
    max_waveforms: Optional[int] = Field(
        100, description="Maximum waveforms to accumulate"
    )
    color_grading: bool = Field(True, description="Use color grading for intensity")


class HistogramData(BaseModel):
    """Histogram data for voltage or time distribution."""

    histogram_type: str = Field(..., description="Type: 'voltage' or 'time'")
    bins: List[float] = Field(..., description="Histogram bin edges")
    counts: List[int] = Field(..., description="Counts per bin")
    total_samples: int = Field(..., description="Total number of samples")
    mean: float = Field(..., description="Mean value")
    std_dev: float = Field(..., description="Standard deviation")
    min_value: float = Field(..., description="Minimum value")
    max_value: float = Field(..., description="Maximum value")

    # Additional statistics
    median: Optional[float] = Field(None, description="Median value")
    mode: Optional[float] = Field(None, description="Mode (most common value)")
    skewness: Optional[float] = Field(None, description="Distribution skewness")
    kurtosis: Optional[float] = Field(None, description="Distribution kurtosis")


class XYPlotData(BaseModel):
    """XY plot data (channel vs channel)."""

    equipment_id: str = Field(..., description="Source equipment ID")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Capture timestamp"
    )
    x_channel: int = Field(..., description="X-axis channel")
    y_channel: int = Field(..., description="Y-axis channel")
    x_data: List[float] = Field(..., description="X-axis data points")
    y_data: List[float] = Field(..., description="Y-axis data points")
    num_points: int = Field(..., description="Number of data points")


class EnhancedMeasurements(BaseModel):
    """Enhanced automatic measurements."""

    equipment_id: str = Field(..., description="Source equipment ID")
    channel: int = Field(..., description="Channel number")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Measurement timestamp"
    )

    # Voltage measurements
    vpp: Optional[float] = Field(None, description="Peak-to-peak voltage (V)")
    vmax: Optional[float] = Field(None, description="Maximum voltage (V)")
    vmin: Optional[float] = Field(None, description="Minimum voltage (V)")
    vamp: Optional[float] = Field(None, description="Amplitude (V)")
    vtop: Optional[float] = Field(None, description="Top voltage (V)")
    vbase: Optional[float] = Field(None, description="Base voltage (V)")
    vmid: Optional[float] = Field(None, description="Middle voltage (V)")
    vavg: Optional[float] = Field(None, description="Average voltage (V)")
    vrms: Optional[float] = Field(None, description="RMS voltage (V)")
    vac_rms: Optional[float] = Field(None, description="AC RMS voltage (V)")

    # Overshoot/preshoot
    overshoot: Optional[float] = Field(None, description="Overshoot (%)")
    preshoot: Optional[float] = Field(None, description="Preshoot (%)")

    # Time measurements
    period: Optional[float] = Field(None, description="Period (s)")
    frequency: Optional[float] = Field(None, description="Frequency (Hz)")
    rise_time: Optional[float] = Field(None, description="Rise time 10%-90% (s)")
    fall_time: Optional[float] = Field(None, description="Fall time 90%-10% (s)")
    positive_width: Optional[float] = Field(
        None, description="Positive pulse width (s)"
    )
    negative_width: Optional[float] = Field(
        None, description="Negative pulse width (s)"
    )
    duty_cycle: Optional[float] = Field(None, description="Duty cycle (%)")

    # Phase and delay
    phase: Optional[float] = Field(None, description="Phase (degrees)")
    delay: Optional[float] = Field(None, description="Delay (s)")

    # Edge counts
    positive_edges: Optional[int] = Field(None, description="Number of positive edges")
    negative_edges: Optional[int] = Field(None, description="Number of negative edges")

    # Area measurements
    area: Optional[float] = Field(None, description="Waveform area (V*s)")
    cycle_area: Optional[float] = Field(None, description="Single cycle area (V*s)")

    # Advanced measurements
    slew_rate_rising: Optional[float] = Field(
        None, description="Slew rate on rising edge (V/s)"
    )
    slew_rate_falling: Optional[float] = Field(
        None, description="Slew rate on falling edge (V/s)"
    )

    # Signal quality
    snr: Optional[float] = Field(None, description="Signal-to-noise ratio (dB)")
    thd: Optional[float] = Field(None, description="Total harmonic distortion (%)")
    sinad: Optional[float] = Field(None, description="SINAD (dB)")
    enob: Optional[float] = Field(None, description="Effective number of bits")

    # Statistical
    std_dev: Optional[float] = Field(None, description="Standard deviation (V)")
    variance: Optional[float] = Field(None, description="Variance (V²)")
    skewness: Optional[float] = Field(None, description="Skewness")
    kurtosis: Optional[float] = Field(None, description="Kurtosis")

    # Pulse parameters
    pulse_count: Optional[int] = Field(None, description="Number of pulses")
    pulse_rate: Optional[float] = Field(None, description="Pulse rate (Hz)")


class WaveformCaptureConfig(BaseModel):
    """Configuration for waveform capture."""

    channel: int = Field(..., description="Channel to capture")
    num_averages: int = Field(1, description="Number of waveforms to average")
    high_resolution: bool = Field(False, description="Enable high-resolution mode")
    interpolation: bool = Field(False, description="Enable interpolation")

    # Acquisition mode
    single_shot: bool = Field(False, description="Single-shot acquisition")

    # Advanced options
    reduce_points: Optional[int] = Field(
        None, description="Reduce to N points (decimation)"
    )
    apply_smoothing: bool = Field(False, description="Apply smoothing filter")


class MathChannelResult(BaseModel):
    """Result from math channel operation."""

    equipment_id: str = Field(..., description="Source equipment ID")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Calculation timestamp"
    )
    operation: MathOperation = Field(..., description="Math operation performed")
    source_channels: List[int] = Field(..., description="Source channel numbers")
    result_data: List[float] = Field(..., description="Result waveform data")
    time_data: List[float] = Field(..., description="Time data for result")
    sample_rate: float = Field(..., description="Sample rate of result (Hz)")

    # For FFT results
    frequency_data: Optional[List[float]] = Field(
        None, description="Frequency data (for FFT)"
    )
    magnitude_data: Optional[List[float]] = Field(
        None, description="Magnitude data (for FFT)"
    )
    phase_data: Optional[List[float]] = Field(None, description="Phase data (for FFT)")
