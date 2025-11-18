"""Advanced waveform analysis data models."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from pydantic import BaseModel, Field


class JitterType(str, Enum):
    """Jitter measurement types."""

    TIE = "tie"  # Time Interval Error
    PERIOD = "period"  # Period jitter
    CYCLE_TO_CYCLE = "cycle_to_cycle"  # Cycle-to-cycle jitter
    HALF_PERIOD = "half_period"  # Half-period jitter
    N_PERIOD = "n_period"  # N-period jitter


class SearchEventType(str, Enum):
    """Waveform search event types."""

    EDGE_RISING = "edge_rising"
    EDGE_FALLING = "edge_falling"
    PULSE_POSITIVE = "pulse_positive"
    PULSE_NEGATIVE = "pulse_negative"
    RUNT = "runt"
    TIMEOUT = "timeout"
    GLITCH = "glitch"
    SETUP_HOLD = "setup_hold"
    PATTERN = "pattern"


class SpectrogramMode(str, Enum):
    """Spectrogram display modes."""

    MAGNITUDE = "magnitude"
    POWER = "power"
    DB = "db"  # dB scale


class MaskMode(str, Enum):
    """Mask test modes."""

    POLYGON = "polygon"  # User-defined polygon
    STANDARD = "standard"  # Standard template (e.g., eye diagram masks)
    AUTO = "auto"  # Auto-generated from reference waveform


# === Spectral Analysis Models ===


class SpectrogramConfig(BaseModel):
    """Spectrogram configuration."""

    window_size: int = Field(256, description="FFT window size")
    overlap: int = Field(128, description="Window overlap samples")
    window_function: str = Field("hann", description="Window function")
    mode: SpectrogramMode = Field(
        SpectrogramMode.MAGNITUDE, description="Display mode"
    )
    freq_min: Optional[float] = Field(None, description="Minimum frequency (Hz)")
    freq_max: Optional[float] = Field(None, description="Maximum frequency (Hz)")


class SpectrogramData(BaseModel):
    """Spectrogram analysis result."""

    equipment_id: str = Field(..., description="Source equipment ID")
    channel: int = Field(..., description="Channel number")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Analysis timestamp"
    )
    frequencies: List[float] = Field(..., description="Frequency bins (Hz)")
    times: List[float] = Field(..., description="Time segments (s)")
    power_matrix: List[List[float]] = Field(
        ..., description="Power/magnitude matrix [time][freq]"
    )
    sample_rate: float = Field(..., description="Original sample rate (Hz)")
    window_size: int = Field(..., description="FFT window size")
    overlap: int = Field(..., description="Window overlap")


class CrossCorrelationData(BaseModel):
    """Cross-correlation analysis result."""

    equipment_id: str = Field(..., description="Source equipment ID")
    channel1: int = Field(..., description="First channel")
    channel2: int = Field(..., description="Second channel")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Analysis timestamp"
    )
    lags: List[float] = Field(..., description="Time lags (s)")
    correlation: List[float] = Field(..., description="Correlation values")
    max_correlation: float = Field(..., description="Maximum correlation value")
    lag_at_max: float = Field(..., description="Lag at maximum correlation (s)")
    correlation_coefficient: float = Field(..., description="Pearson correlation coefficient")


class TransferFunctionData(BaseModel):
    """Transfer function analysis result (H(f) = Y(f)/X(f))."""

    equipment_id: str = Field(..., description="Source equipment ID")
    input_channel: int = Field(..., description="Input channel")
    output_channel: int = Field(..., description="Output channel")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Analysis timestamp"
    )
    frequencies: List[float] = Field(..., description="Frequency points (Hz)")
    magnitude: List[float] = Field(..., description="Magnitude response")
    phase: List[float] = Field(..., description="Phase response (degrees)")
    magnitude_db: List[float] = Field(..., description="Magnitude in dB")
    coherence: List[float] = Field(
        ..., description="Coherence function (0-1)"
    )


# === Jitter Analysis Models ===


class JitterConfig(BaseModel):
    """Jitter analysis configuration."""

    jitter_type: JitterType = Field(..., description="Type of jitter measurement")
    edge_type: str = Field("rising", description="Edge type: 'rising' or 'falling'")
    threshold: Optional[float] = Field(
        None, description="Threshold voltage (auto if None)"
    )
    n_periods: int = Field(1, description="Number of periods for N-period jitter")


class JitterData(BaseModel):
    """Jitter analysis results."""

    equipment_id: str = Field(..., description="Source equipment ID")
    channel: int = Field(..., description="Channel number")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Analysis timestamp"
    )
    jitter_type: JitterType = Field(..., description="Type of jitter")

    # Jitter values
    jitter_values: List[float] = Field(..., description="Jitter measurements (s)")
    jitter_times: List[float] = Field(..., description="Time points for jitter values (s)")

    # Statistics
    mean_jitter: float = Field(..., description="Mean jitter (s)")
    rms_jitter: float = Field(..., description="RMS jitter (s)")
    pk_pk_jitter: float = Field(..., description="Peak-to-peak jitter (s)")
    std_dev: float = Field(..., description="Standard deviation (s)")

    # Distribution
    histogram_bins: List[float] = Field(..., description="Histogram bin edges (s)")
    histogram_counts: List[int] = Field(..., description="Histogram counts")

    # Additional metrics
    n_edges: int = Field(..., description="Number of edges analyzed")
    ideal_period: Optional[float] = Field(None, description="Ideal period (s)")


# === Eye Diagram Models ===


class EyeDiagramConfig(BaseModel):
    """Eye diagram configuration."""

    bit_rate: float = Field(..., description="Bit rate (bps)")
    samples_per_symbol: int = Field(
        100, description="Samples per symbol for reconstruction"
    )
    edge_threshold: Optional[float] = Field(
        None, description="Threshold for edge detection (auto if None)"
    )
    num_traces: Optional[int] = Field(
        None, description="Max traces to overlay (None = all)"
    )
    persistence_mode: bool = Field(
        True, description="Use persistence for visualization"
    )


class EyeParameters(BaseModel):
    """Eye diagram measurement parameters."""

    eye_height: float = Field(..., description="Eye height (V)")
    eye_width: float = Field(..., description="Eye width (s)")
    eye_amplitude: float = Field(..., description="Eye amplitude (V)")
    crossing_percent: float = Field(..., description="Crossing percentage (%)")

    # Jitter and noise
    rms_jitter: float = Field(..., description="RMS jitter (s)")
    pk_pk_jitter: float = Field(..., description="Peak-to-peak jitter (s)")
    rms_noise: float = Field(..., description="RMS noise (V)")

    # Quality metrics
    q_factor: float = Field(..., description="Q-factor")
    snr: float = Field(..., description="Signal-to-noise ratio (dB)")
    eye_opening: float = Field(
        ..., description="Eye opening percentage (0-100%)"
    )

    # Level measurements
    one_level: float = Field(..., description="Logic 1 level (V)")
    zero_level: float = Field(..., description="Logic 0 level (V)")

    # Rise/fall times
    rise_time: float = Field(..., description="Rise time (s)")
    fall_time: float = Field(..., description="Fall time (s)")


class EyeDiagramData(BaseModel):
    """Eye diagram data and measurements."""

    equipment_id: str = Field(..., description="Source equipment ID")
    channel: int = Field(..., description="Channel number")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Analysis timestamp"
    )
    bit_rate: float = Field(..., description="Bit rate (bps)")

    # Eye diagram data
    time_axis: List[float] = Field(..., description="Time axis (normalized)")
    traces: List[List[float]] = Field(..., description="Overlaid traces")
    persistence_map: Optional[List[List[int]]] = Field(
        None, description="2D persistence map"
    )

    # Measurements
    parameters: EyeParameters = Field(..., description="Eye diagram parameters")

    # Sampling points
    sample_point_time: float = Field(..., description="Optimal sample point time")
    sample_point_voltage: float = Field(..., description="Voltage at sample point")

    # Metadata
    num_traces: int = Field(..., description="Number of traces overlaid")
    num_bits_analyzed: int = Field(..., description="Number of bits analyzed")


# === Mask Testing Models ===


class MaskPoint(BaseModel):
    """Single point in a mask polygon."""

    time: float = Field(..., description="Time value (s or normalized)")
    voltage: float = Field(..., description="Voltage value (V or normalized)")


class MaskPolygon(BaseModel):
    """Mask polygon definition."""

    name: str = Field(..., description="Mask region name")
    points: List[MaskPoint] = Field(..., description="Polygon vertices")
    fail_inside: bool = Field(
        True, description="Fail if waveform inside (True) or outside (False)"
    )


class MaskDefinition(BaseModel):
    """Complete mask definition."""

    name: str = Field(..., description="Mask name")
    description: Optional[str] = Field(None, description="Mask description")
    mode: MaskMode = Field(..., description="Mask mode")
    polygons: List[MaskPolygon] = Field(..., description="Mask regions")
    normalized: bool = Field(
        False, description="Whether coordinates are normalized (0-1)"
    )


class MaskTestResult(BaseModel):
    """Mask test results."""

    equipment_id: str = Field(..., description="Source equipment ID")
    channel: int = Field(..., description="Channel number")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Test timestamp"
    )
    mask_name: str = Field(..., description="Mask name")

    # Test results
    passed: bool = Field(..., description="Overall pass/fail")
    total_samples: int = Field(..., description="Total samples tested")
    failed_samples: int = Field(..., description="Number of failed samples")
    failure_rate: float = Field(..., description="Failure rate (0-1)")

    # Failure locations
    failure_times: List[float] = Field(..., description="Times of failures (s)")
    failure_voltages: List[float] = Field(..., description="Voltages of failures (V)")

    # Per-region results
    region_failures: Dict[str, int] = Field(
        ..., description="Failures per mask region"
    )

    # Margin analysis
    min_margin: float = Field(..., description="Minimum margin to mask")
    mean_margin: float = Field(..., description="Mean margin to mask")


# === Waveform Search Models ===


class SearchConfig(BaseModel):
    """Waveform search configuration."""

    event_type: SearchEventType = Field(..., description="Event type to search for")

    # Threshold settings
    upper_threshold: Optional[float] = Field(None, description="Upper threshold (V)")
    lower_threshold: Optional[float] = Field(None, description="Lower threshold (V)")

    # Time settings (for pulses, glitches, timeouts)
    min_width: Optional[float] = Field(None, description="Minimum pulse width (s)")
    max_width: Optional[float] = Field(None, description="Maximum pulse width (s)")
    timeout_duration: Optional[float] = Field(None, description="Timeout duration (s)")

    # Pattern matching
    pattern: Optional[List[int]] = Field(
        None, description="Digital pattern (list of 0/1)"
    )

    # Search limits
    max_events: int = Field(1000, description="Maximum events to find")


class SearchEvent(BaseModel):
    """Single search event."""

    event_type: SearchEventType = Field(..., description="Event type")
    time: float = Field(..., description="Event time (s)")
    index: int = Field(..., description="Sample index")
    amplitude: Optional[float] = Field(None, description="Event amplitude (V)")
    width: Optional[float] = Field(None, description="Pulse width (s)")
    details: Dict[str, Any] = Field(
        default_factory=dict, description="Additional event details"
    )


class SearchResult(BaseModel):
    """Waveform search results."""

    equipment_id: str = Field(..., description="Source equipment ID")
    channel: int = Field(..., description="Channel number")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Search timestamp"
    )
    event_type: SearchEventType = Field(..., description="Event type searched")

    # Results
    events: List[SearchEvent] = Field(..., description="Found events")
    total_events: int = Field(..., description="Total events found")
    search_duration: float = Field(..., description="Search duration (s)")

    # Statistics
    mean_time_between_events: Optional[float] = Field(
        None, description="Mean time between events (s)"
    )
    event_rate: Optional[float] = Field(None, description="Event rate (Hz)")


# === Reference Waveform Models ===


class ReferenceWaveform(BaseModel):
    """Reference waveform definition."""

    name: str = Field(..., description="Reference name")
    description: Optional[str] = Field(None, description="Description")
    equipment_id: str = Field(..., description="Source equipment ID")
    channel: int = Field(..., description="Channel number")
    timestamp: datetime = Field(..., description="Capture timestamp")

    # Waveform data
    time_data: List[float] = Field(..., description="Time values (s)")
    voltage_data: List[float] = Field(..., description="Voltage values (V)")
    sample_rate: float = Field(..., description="Sample rate (Hz)")

    # Tolerance settings
    voltage_tolerance_percent: float = Field(
        5.0, description="Voltage tolerance (%)"
    )
    time_tolerance_percent: float = Field(
        5.0, description="Time tolerance (%)"
    )


class ComparisonResult(BaseModel):
    """Waveform comparison result."""

    equipment_id: str = Field(..., description="Test equipment ID")
    channel: int = Field(..., description="Channel number")
    reference_name: str = Field(..., description="Reference waveform name")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Comparison timestamp"
    )

    # Overall results
    passed: bool = Field(..., description="Overall pass/fail")
    similarity_percent: float = Field(
        ..., description="Similarity percentage (0-100%)"
    )

    # Voltage comparison
    voltage_rms_error: float = Field(..., description="RMS voltage error (V)")
    voltage_max_error: float = Field(..., description="Max voltage error (V)")
    voltage_mean_error: float = Field(..., description="Mean voltage error (V)")

    # Time/shape comparison
    correlation: float = Field(..., description="Cross-correlation coefficient")
    phase_shift: float = Field(..., description="Phase shift (s)")

    # Failure points
    failed_samples: int = Field(..., description="Number of failed samples")
    failure_times: List[float] = Field(..., description="Times of failures (s)")
    failure_errors: List[float] = Field(..., description="Error values at failures (V)")


# === Parameter Trending Models ===


class TrendParameter(str, Enum):
    """Parameters that can be trended."""

    FREQUENCY = "frequency"
    AMPLITUDE = "amplitude"
    VPP = "vpp"
    VRMS = "vrms"
    RISE_TIME = "rise_time"
    FALL_TIME = "fall_time"
    DUTY_CYCLE = "duty_cycle"
    OVERSHOOT = "overshoot"
    SNR = "snr"
    THD = "thd"
    JITTER_RMS = "jitter_rms"
    EYE_HEIGHT = "eye_height"
    EYE_WIDTH = "eye_width"


class TrendConfig(BaseModel):
    """Parameter trending configuration."""

    parameter: TrendParameter = Field(..., description="Parameter to trend")
    max_samples: int = Field(1000, description="Maximum trend samples to store")
    update_interval: float = Field(1.0, description="Update interval (s)")
    alert_enabled: bool = Field(False, description="Enable alerts")
    alert_threshold_min: Optional[float] = Field(
        None, description="Minimum threshold for alerts"
    )
    alert_threshold_max: Optional[float] = Field(
        None, description="Maximum threshold for alerts"
    )


class TrendDataPoint(BaseModel):
    """Single trend data point."""

    timestamp: datetime = Field(..., description="Measurement timestamp")
    value: float = Field(..., description="Parameter value")
    sequence_number: int = Field(..., description="Sequence number")


class TrendData(BaseModel):
    """Parameter trend data."""

    equipment_id: str = Field(..., description="Source equipment ID")
    channel: int = Field(..., description="Channel number")
    parameter: TrendParameter = Field(..., description="Trended parameter")
    start_time: datetime = Field(..., description="Trend start time")
    last_update: datetime = Field(..., description="Last update time")

    # Trend data
    data_points: List[TrendDataPoint] = Field(..., description="Trend data points")

    # Statistics
    mean: float = Field(..., description="Mean value")
    std_dev: float = Field(..., description="Standard deviation")
    min_value: float = Field(..., description="Minimum value")
    max_value: float = Field(..., description="Maximum value")
    range: float = Field(..., description="Value range")

    # Drift analysis
    drift_rate: float = Field(..., description="Drift rate (units/s)")
    trend_direction: str = Field(..., description="Trend direction: up/down/stable")

    # Alerts
    alerts_triggered: int = Field(0, description="Number of alerts triggered")
