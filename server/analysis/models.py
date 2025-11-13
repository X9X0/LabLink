"""Data models for analysis pipeline."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


# === Filter Models ===

class FilterType(str, Enum):
    """Filter type enumeration."""
    LOWPASS = "lowpass"
    HIGHPASS = "highpass"
    BANDPASS = "bandpass"
    BANDSTOP = "bandstop"  # Notch filter


class FilterMethod(str, Enum):
    """Filter design method."""
    BUTTERWORTH = "butterworth"
    CHEBYSHEV1 = "chebyshev1"
    CHEBYSHEV2 = "chebyshev2"
    BESSEL = "bessel"
    ELLIPTIC = "elliptic"
    FIR = "fir"


class FilterConfig(BaseModel):
    """Filter configuration."""
    filter_type: FilterType = Field(..., description="Filter type")
    filter_method: FilterMethod = Field(FilterMethod.BUTTERWORTH, description="Filter design method")
    cutoff_freq: Optional[float] = Field(None, description="Cutoff frequency (Hz)")
    cutoff_low: Optional[float] = Field(None, description="Low cutoff for bandpass/stop (Hz)")
    cutoff_high: Optional[float] = Field(None, description="High cutoff for bandpass/stop (Hz)")
    order: int = Field(4, ge=1, le=10, description="Filter order")
    ripple_db: Optional[float] = Field(None, description="Passband ripple (dB) for Chebyshev")
    attenuation_db: Optional[float] = Field(None, description="Stopband attenuation (dB)")
    sample_rate: float = Field(..., description="Sample rate (Hz)")


class FilterResult(BaseModel):
    """Filter result."""
    filtered_data: List[float] = Field(..., description="Filtered data")
    time_data: List[float] = Field(..., description="Time array")
    config: FilterConfig = Field(..., description="Filter configuration used")
    timestamp: datetime = Field(default_factory=datetime.now)


# === Resampling Models ===

class ResampleMethod(str, Enum):
    """Resampling method."""
    LINEAR = "linear"
    CUBIC = "cubic"
    NEAREST = "nearest"
    SPLINE = "spline"
    FOURIER = "fourier"  # FFT-based resampling


class ResampleConfig(BaseModel):
    """Resampling configuration."""
    method: ResampleMethod = Field(ResampleMethod.LINEAR, description="Interpolation method")
    target_points: Optional[int] = Field(None, description="Target number of points")
    target_rate: Optional[float] = Field(None, description="Target sample rate (Hz)")
    anti_alias: bool = Field(True, description="Apply anti-aliasing filter")


# === Curve Fitting Models ===

class FitType(str, Enum):
    """Curve fit type."""
    POLYNOMIAL = "polynomial"
    EXPONENTIAL = "exponential"
    LOGARITHMIC = "logarithmic"
    POWER = "power"
    SINUSOIDAL = "sinusoidal"
    GAUSSIAN = "gaussian"
    LINEAR = "linear"
    CUSTOM = "custom"


class FitConfig(BaseModel):
    """Curve fitting configuration."""
    fit_type: FitType = Field(..., description="Type of curve to fit")
    degree: int = Field(1, ge=1, le=10, description="Polynomial degree")
    initial_guess: Optional[List[float]] = Field(None, description="Initial parameter guess")
    bounds: Optional[List[List[float]]] = Field(None, description="Parameter bounds [[lower], [upper]]")
    weights: Optional[List[float]] = Field(None, description="Data point weights")
    custom_function: Optional[str] = Field(None, description="Custom function (Python code)")


class FitResult(BaseModel):
    """Curve fit result."""
    coefficients: List[float] = Field(..., description="Fit coefficients/parameters")
    fitted_data: List[float] = Field(..., description="Fitted curve data")
    x_data: List[float] = Field(..., description="X data used for fitting")
    y_data: List[float] = Field(..., description="Y data used for fitting")
    r_squared: float = Field(..., description="R² coefficient of determination")
    rmse: float = Field(..., description="Root mean square error")
    residuals: List[float] = Field(..., description="Residuals (y - y_fit)")
    equation: str = Field(..., description="Equation string")
    config: FitConfig = Field(..., description="Fit configuration used")
    timestamp: datetime = Field(default_factory=datetime.now)


# === SPC Models ===

class SPCChartType(str, Enum):
    """SPC chart type."""
    XBAR_R = "xbar_r"  # X-bar and R chart
    XBAR_S = "xbar_s"  # X-bar and S chart
    INDIVIDUALS = "individuals"  # Individuals and moving range
    P_CHART = "p_chart"  # Proportion chart
    C_CHART = "c_chart"  # Count chart
    U_CHART = "u_chart"  # Defects per unit chart


class SPCChartConfig(BaseModel):
    """SPC chart configuration."""
    chart_type: SPCChartType = Field(..., description="Type of control chart")
    subgroup_size: int = Field(5, ge=1, description="Subgroup size")
    sigma_limits: float = Field(3.0, gt=0, description="Number of standard deviations for control limits")
    specification_limits: Optional[Dict[str, float]] = Field(
        None, description="Spec limits: {'lower': LSL, 'upper': USL}"
    )


class SPCChartResult(BaseModel):
    """SPC chart result."""
    chart_type: SPCChartType = Field(..., description="Chart type")
    center_line: float = Field(..., description="Process center line")
    ucl: float = Field(..., description="Upper control limit")
    lcl: float = Field(..., description="Lower control limit")
    subgroup_values: List[float] = Field(..., description="Subgroup statistics")
    out_of_control_points: List[int] = Field(..., description="Indices of out-of-control points")
    violations: List[str] = Field(..., description="Control rule violations")
    timestamp: datetime = Field(default_factory=datetime.now)


class CapabilityResult(BaseModel):
    """Process capability analysis result."""
    mean: float = Field(..., description="Process mean")
    std_dev: float = Field(..., description="Process standard deviation")
    usl: Optional[float] = Field(None, description="Upper specification limit")
    lsl: Optional[float] = Field(None, description="Lower specification limit")
    target: Optional[float] = Field(None, description="Target value")

    # Capability indices
    cp: Optional[float] = Field(None, description="Cp (potential capability)")
    cpk: Optional[float] = Field(None, description="Cpk (actual capability)")
    pp: Optional[float] = Field(None, description="Pp (performance)")
    ppk: Optional[float] = Field(None, description="Ppk (performance index)")
    cpm: Optional[float] = Field(None, description="Cpm (Taguchi index)")

    # Yield estimates
    expected_within_spec: Optional[float] = Field(None, description="% within spec limits")
    expected_defects_ppm: Optional[float] = Field(None, description="Defects per million")

    # Interpretation
    capability_assessment: str = Field(..., description="Capability assessment text")
    timestamp: datetime = Field(default_factory=datetime.now)


# === Report Models ===

class ReportFormat(str, Enum):
    """Report output format."""
    PDF = "pdf"
    HTML = "html"
    MARKDOWN = "markdown"
    JSON = "json"


class ReportConfig(BaseModel):
    """Report generation configuration."""
    title: str = Field(..., description="Report title")
    format: ReportFormat = Field(ReportFormat.PDF, description="Output format")
    include_plots: bool = Field(True, description="Include plots/graphs")
    include_statistics: bool = Field(True, description="Include statistical summaries")
    include_raw_data: bool = Field(False, description="Include raw data tables")
    template: Optional[str] = Field(None, description="Custom template name")
    author: Optional[str] = Field(None, description="Report author")
    company: Optional[str] = Field(None, description="Company name")


class ReportSection(BaseModel):
    """Report section."""
    title: str = Field(..., description="Section title")
    content: str = Field(..., description="Section content (text/HTML)")
    plots: List[str] = Field(default_factory=list, description="Plot file paths")
    tables: List[Dict[str, Any]] = Field(default_factory=list, description="Data tables")


class Report(BaseModel):
    """Generated report."""
    report_id: str = Field(..., description="Unique report ID")
    config: ReportConfig = Field(..., description="Report configuration")
    sections: List[ReportSection] = Field(..., description="Report sections")
    file_path: str = Field(..., description="Output file path")
    timestamp: datetime = Field(default_factory=datetime.now)


# === Batch Processing Models ===

class BatchJobStatus(str, Enum):
    """Batch job status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BatchJobConfig(BaseModel):
    """Batch job configuration."""
    job_name: str = Field(..., description="Job name")
    operation: str = Field(..., description="Operation to perform (filter, fit, etc.)")
    input_files: List[str] = Field(..., description="Input file paths")
    output_dir: str = Field(..., description="Output directory")
    operation_config: Dict[str, Any] = Field(..., description="Operation-specific config")
    parallel: bool = Field(True, description="Process files in parallel")
    max_workers: int = Field(4, ge=1, le=16, description="Maximum parallel workers")


class BatchJobResult(BaseModel):
    """Batch job result."""
    job_id: str = Field(..., description="Job ID")
    status: BatchJobStatus = Field(..., description="Job status")
    config: BatchJobConfig = Field(..., description="Job configuration")
    started_at: datetime = Field(..., description="Start time")
    completed_at: Optional[datetime] = Field(None, description="Completion time")
    total_files: int = Field(..., description="Total files to process")
    completed_files: int = Field(0, description="Completed files")
    failed_files: int = Field(0, description="Failed files")
    output_files: List[str] = Field(default_factory=list, description="Generated output files")
    errors: List[str] = Field(default_factory=list, description="Error messages")


# === Analysis Dataset Models ===

class AnalysisDataset(BaseModel):
    """Dataset for analysis."""
    dataset_id: str = Field(..., description="Dataset identifier")
    name: str = Field(..., description="Dataset name")
    x_data: List[float] = Field(..., description="X values (time, frequency, etc.)")
    y_data: List[float] = Field(..., description="Y values (measurements)")
    x_label: str = Field("X", description="X-axis label")
    y_label: str = Field("Y", description="Y-axis label")
    x_unit: Optional[str] = Field(None, description="X-axis unit")
    y_unit: Optional[str] = Field(None, description="Y-axis unit")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    timestamp: datetime = Field(default_factory=datetime.now)
