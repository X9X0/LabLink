"""API endpoints for data analysis pipeline."""

from fastapi import APIRouter, HTTPException, Body
from typing import List, Dict, Any
from pydantic import BaseModel, Field
import numpy as np

from analysis.models import (
    FilterConfig,
    FilterResult,
    ResampleConfig,
    FitConfig,
    FitResult,
    SPCChartConfig,
    SPCChartResult,
    CapabilityResult,
    ReportConfig,
    Report,
    ReportSection,
    BatchJobConfig,
    BatchJobResult,
    AnalysisDataset,
)
from analysis.filters import SignalFilter
from analysis.fitting import CurveFitter
from analysis.spc import SPCAnalyzer
from analysis.resampling import DataResampler
from analysis.reports import ReportGenerator
from analysis.batch import BatchProcessor

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

# Global instances
signal_filter = SignalFilter()
curve_fitter = CurveFitter()
spc_analyzer = SPCAnalyzer()
data_resampler = DataResampler()
report_generator = ReportGenerator()
batch_processor = BatchProcessor()


# Request/Response models
class FilterRequest(BaseModel):
    """Filter request."""
    data: List[float] = Field(..., description="Signal data")
    time: List[float] = Field(..., description="Time data")
    config: FilterConfig = Field(..., description="Filter configuration")


class ResampleRequest(BaseModel):
    """Resample request."""
    x_data: List[float] = Field(..., description="X data")
    y_data: List[float] = Field(..., description="Y data")
    config: ResampleConfig = Field(..., description="Resample configuration")
    original_rate: float = Field(None, description="Original sample rate (Hz)")


class ResampleResponse(BaseModel):
    """Resample response."""
    x_data: List[float] = Field(..., description="Resampled X data")
    y_data: List[float] = Field(..., description="Resampled Y data")


class FitRequest(BaseModel):
    """Curve fit request."""
    x_data: List[float] = Field(..., description="X data")
    y_data: List[float] = Field(..., description="Y data")
    config: FitConfig = Field(..., description="Fit configuration")


class SPCChartRequest(BaseModel):
    """SPC chart request."""
    data: List[float] = Field(..., description="Process data")
    config: SPCChartConfig = Field(..., description="Chart configuration")


class CapabilityRequest(BaseModel):
    """Capability analysis request."""
    data: List[float] = Field(..., description="Process data")
    lsl: float = Field(None, description="Lower specification limit")
    usl: float = Field(None, description="Upper specification limit")
    target: float = Field(None, description="Target value")


class ReportRequest(BaseModel):
    """Report generation request."""
    sections: List[ReportSection] = Field(..., description="Report sections")
    config: ReportConfig = Field(..., description="Report configuration")


# === Signal Filtering Endpoints ===

@router.post("/filter", response_model=FilterResult)
async def apply_filter(request: FilterRequest):
    """Apply digital filter to signal data.

    Supports:
    - Filter types: lowpass, highpass, bandpass, bandstop (notch)
    - Filter methods: Butterworth, Chebyshev, Bessel, Elliptic, FIR
    - Zero-phase filtering (filtfilt)
    """
    try:
        data_array = np.array(request.data)
        time_array = np.array(request.time)

        result = signal_filter.apply_filter(data_array, time_array, request.config)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/filter/notch")
async def apply_notch_filter(
    data: List[float] = Body(...),
    frequency: float = Body(..., description="Frequency to remove (Hz)"),
    quality_factor: float = Body(..., description="Q factor"),
    sample_rate: float = Body(..., description="Sample rate (Hz)"),
):
    """Apply notch filter to remove specific frequency (e.g., 60 Hz power line noise)."""
    try:
        data_array = np.array(data)
        filtered = signal_filter.apply_notch_filter(
            data_array, frequency, quality_factor, sample_rate
        )
        return {"filtered_data": filtered.tolist()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/filter/moving-average")
async def apply_moving_average(
    data: List[float] = Body(...),
    window_size: int = Body(..., ge=2, description="Window size"),
):
    """Apply moving average smoothing filter."""
    try:
        data_array = np.array(data)
        smoothed = signal_filter.moving_average(data_array, window_size)
        return {"smoothed_data": smoothed.tolist()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/filter/savitzky-golay")
async def apply_savitzky_golay(
    data: List[float] = Body(...),
    window_size: int = Body(..., ge=3, description="Window size (must be odd)"),
    poly_order: int = Body(..., ge=1, description="Polynomial order"),
):
    """Apply Savitzky-Golay smoothing filter (preserves features better than moving average)."""
    try:
        data_array = np.array(data)
        smoothed = signal_filter.savitzky_golay(data_array, window_size, poly_order)
        return {"smoothed_data": smoothed.tolist()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# === Resampling Endpoints ===

@router.post("/resample", response_model=ResampleResponse)
async def resample_data(request: ResampleRequest):
    """Resample data to new rate or number of points.

    Supports:
    - Interpolation methods: linear, cubic, nearest, spline, Fourier
    - Anti-aliasing for downsampling
    - Upsampling and downsampling
    """
    try:
        x_array = np.array(request.x_data)
        y_array = np.array(request.y_data)

        new_x, new_y = data_resampler.resample(
            x_array, y_array, request.config, request.original_rate
        )

        return ResampleResponse(x_data=new_x.tolist(), y_data=new_y.tolist())
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/interpolate-missing")
async def interpolate_missing_points(
    x_data: List[float] = Body(...),
    y_data: List[float] = Body(..., description="Y data (may contain NaN)"),
    method: str = Body("linear", description="Interpolation method"),
):
    """Interpolate missing (NaN) data points."""
    try:
        from analysis.models import ResampleMethod

        x_array = np.array(x_data)
        y_array = np.array(y_data)
        method_enum = ResampleMethod(method)

        new_x, new_y = data_resampler.interpolate_missing_points(
            x_array, y_array, method_enum
        )

        return {"x_data": new_x.tolist(), "y_data": new_y.tolist()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# === Curve Fitting Endpoints ===

@router.post("/fit", response_model=FitResult)
async def fit_curve(request: FitRequest):
    """Fit curve to data.

    Supported fit types:
    - Linear, Polynomial
    - Exponential, Logarithmic, Power
    - Sinusoidal, Gaussian
    - Custom (Python function)

    Returns fit coefficients, R², RMSE, and residuals.
    """
    try:
        x_array = np.array(request.x_data)
        y_array = np.array(request.y_data)

        result = curve_fitter.fit(x_array, y_array, request.config)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/fit/predict")
async def predict_from_fit(
    coefficients: List[float] = Body(...),
    x_new: List[float] = Body(...),
    fit_type: str = Body(...),
):
    """Predict Y values for new X values using fit coefficients."""
    try:
        from analysis.models import FitType

        coeffs_array = np.array(coefficients)
        x_array = np.array(x_new)
        fit_type_enum = FitType(fit_type)

        y_pred = curve_fitter.predict(coeffs_array, x_array, fit_type_enum)

        return {"y_predicted": y_pred.tolist()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# === SPC Endpoints ===

@router.post("/spc/chart", response_model=SPCChartResult)
async def generate_control_chart(request: SPCChartRequest):
    """Generate statistical process control chart.

    Chart types:
    - X-bar and R chart
    - X-bar and S chart
    - Individuals (I-MR) chart
    - P chart (proportion)
    - C chart (count)
    - U chart (defects per unit)

    Detects out-of-control points and Western Electric rule violations.
    """
    try:
        data_array = np.array(request.data)
        result = spc_analyzer.generate_control_chart(data_array, request.config)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/spc/capability", response_model=CapabilityResult)
async def analyze_capability(request: CapabilityRequest):
    """Analyze process capability.

    Calculates:
    - Cp (potential capability)
    - Cpk (actual capability)
    - Pp, Ppk (performance indices)
    - Cpm (Taguchi index)
    - Expected yield and defects (PPM)

    Provides capability assessment.
    """
    try:
        data_array = np.array(request.data)
        result = spc_analyzer.calculate_capability(
            data_array, request.lsl, request.usl, request.target
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# === Report Generation Endpoints ===

@router.post("/report/generate", response_model=Report)
async def generate_report(request: ReportRequest):
    """Generate analysis report.

    Formats:
    - HTML (styled with CSS)
    - Markdown
    - JSON
    - PDF (requires additional setup)

    Supports:
    - Multiple sections
    - Plots/graphs
    - Data tables
    - Custom templates
    """
    try:
        report = report_generator.generate_report(request.sections, request.config)
        return report
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/report/section", response_model=ReportSection)
async def create_report_section(
    title: str = Body(...),
    content: str = Body(...),
    plots: List[str] = Body(default_factory=list),
    tables: List[Dict[str, Any]] = Body(default_factory=list),
):
    """Create a report section."""
    section = report_generator.create_section(title, content, plots, tables)
    return section


# === Batch Processing Endpoints ===

@router.post("/batch/submit")
async def submit_batch_job(config: BatchJobConfig):
    """Submit batch processing job.

    Process multiple files in parallel with:
    - Filtering
    - Curve fitting
    - Resampling
    - Custom operations

    Returns job ID for status tracking.
    """
    try:
        job_id = await batch_processor.submit_job(config)
        return {"job_id": job_id, "message": "Batch job submitted"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/batch/status/{job_id}", response_model=BatchJobResult)
async def get_batch_status(job_id: str):
    """Get batch job status."""
    try:
        result = batch_processor.get_job_status(job_id)
        return result
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/batch/cancel/{job_id}")
async def cancel_batch_job(job_id: str):
    """Cancel running batch job."""
    try:
        batch_processor.cancel_job(job_id)
        return {"message": f"Job {job_id} cancelled"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/batch/list", response_model=List[BatchJobResult])
async def list_batch_jobs():
    """List all batch jobs."""
    jobs = batch_processor.list_jobs()
    return jobs


# === Utility Endpoints ===

@router.post("/dataset/create", response_model=AnalysisDataset)
async def create_dataset(
    name: str = Body(...),
    x_data: List[float] = Body(...),
    y_data: List[float] = Body(...),
    x_label: str = Body("X"),
    y_label: str = Body("Y"),
    x_unit: str = Body(None),
    y_unit: str = Body(None),
    metadata: Dict[str, Any] = Body(default_factory=dict),
):
    """Create analysis dataset."""
    import uuid

    dataset = AnalysisDataset(
        dataset_id=f"dataset_{uuid.uuid4().hex[:8]}",
        name=name,
        x_data=x_data,
        y_data=y_data,
        x_label=x_label,
        y_label=y_label,
        x_unit=x_unit,
        y_unit=y_unit,
        metadata=metadata,
    )

    return dataset


@router.get("/info")
async def get_analysis_info():
    """Get analysis system information."""
    return {
        "filters": {
            "types": ["lowpass", "highpass", "bandpass", "bandstop"],
            "methods": ["butterworth", "chebyshev1", "chebyshev2", "bessel", "elliptic", "fir"],
        },
        "resampling": {
            "methods": ["linear", "cubic", "nearest", "spline", "fourier"],
        },
        "fitting": {
            "types": ["linear", "polynomial", "exponential", "logarithmic", "power", "sinusoidal", "gaussian", "custom"],
        },
        "spc": {
            "chart_types": ["xbar_r", "xbar_s", "individuals", "p_chart", "c_chart", "u_chart"],
        },
        "reports": {
            "formats": ["pdf", "html", "markdown", "json"],
        },
        "batch": {
            "operations": ["filter", "fit", "resample"],
        },
    }
