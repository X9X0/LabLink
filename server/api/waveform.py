"""API endpoints for advanced waveform capture and analysis."""

from typing import List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field
from waveform.analyzer import WaveformAnalyzer
from waveform.manager import WaveformManager
from waveform.models import (CursorData, CursorType, EnhancedMeasurements,
                             ExtendedWaveformData, HistogramData,
                             MathChannelConfig, MathChannelResult,
                             PersistenceConfig, PersistenceMode,
                             WaveformCaptureConfig, XYPlotData)

router = APIRouter(prefix="/api/waveform", tags=["waveform"])

# Global waveform manager (initialized in main.py)
waveform_manager: Optional[WaveformManager] = None
waveform_analyzer: Optional[WaveformAnalyzer] = None


def init_waveform_api(manager: WaveformManager):
    """Initialize waveform API with manager instance."""
    global waveform_manager, waveform_analyzer
    waveform_manager = manager
    waveform_analyzer = manager.analyzer


# Request/Response models
class CaptureRequest(BaseModel):
    """Waveform capture request."""

    equipment_id: str = Field(..., description="Equipment ID")
    config: WaveformCaptureConfig = Field(..., description="Capture configuration")


class MeasurementsRequest(BaseModel):
    """Enhanced measurements request."""

    equipment_id: str = Field(..., description="Equipment ID")
    channel: int = Field(..., description="Channel number")
    use_cached: bool = Field(True, description="Use cached waveform if available")


class CursorRequest(BaseModel):
    """Cursor measurement request."""

    equipment_id: str = Field(..., description="Equipment ID")
    channel: int = Field(..., description="Channel number")
    cursor_type: CursorType = Field(..., description="Cursor type")
    cursor1_position: float = Field(..., description="Cursor 1 position")
    cursor2_position: float = Field(..., description="Cursor 2 position")


class MathRequest(BaseModel):
    """Math channel request."""

    equipment_id: str = Field(..., description="Equipment ID")
    config: MathChannelConfig = Field(..., description="Math configuration")
    channel2: Optional[int] = Field(
        None, description="Secondary channel for binary ops"
    )


class PersistenceRequest(BaseModel):
    """Persistence mode request."""

    equipment_id: str = Field(..., description="Equipment ID")
    channel: int = Field(..., description="Channel number")
    config: PersistenceConfig = Field(..., description="Persistence configuration")


class HistogramRequest(BaseModel):
    """Histogram request."""

    equipment_id: str = Field(..., description="Equipment ID")
    channel: int = Field(..., description="Channel number")
    histogram_type: str = Field("voltage", description="Type: 'voltage' or 'time'")
    num_bins: int = Field(100, description="Number of bins")


class XYPlotRequest(BaseModel):
    """XY plot request."""

    equipment_id: str = Field(..., description="Equipment ID")
    x_channel: int = Field(..., description="X-axis channel")
    y_channel: int = Field(..., description="Y-axis channel")


class ContinuousAcquisitionRequest(BaseModel):
    """Continuous acquisition request."""

    equipment_id: str = Field(..., description="Equipment ID")
    channel: int = Field(..., description="Channel number")
    rate_hz: float = Field(10.0, description="Acquisition rate in Hz")


class AcquisitionResponse(BaseModel):
    """Continuous acquisition response."""

    task_id: str = Field(..., description="Acquisition task ID")
    message: str = Field(..., description="Status message")


# === Waveform Capture Endpoints ===


@router.post("/capture", response_model=ExtendedWaveformData)
async def capture_waveform(request: CaptureRequest):
    """Capture waveform with advanced options.

    Supports:
    - Averaging multiple acquisitions
    - High-resolution mode
    - Decimation and smoothing
    - Single-shot acquisition
    """
    if not waveform_manager:
        raise HTTPException(status_code=500, detail="Waveform manager not initialized")

    try:
        waveform = await waveform_manager.capture_waveform(
            request.equipment_id, request.config
        )
        return waveform
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/cached/{equipment_id}/{channel}", response_model=ExtendedWaveformData)
async def get_cached_waveform(equipment_id: str, channel: int):
    """Get cached waveform for equipment/channel."""
    if not waveform_manager:
        raise HTTPException(status_code=500, detail="Waveform manager not initialized")

    waveform = waveform_manager.get_cached_waveform(equipment_id, channel)
    if not waveform:
        raise HTTPException(status_code=404, detail="No cached waveform found")

    return waveform


@router.delete("/cache/{equipment_id}")
async def clear_waveform_cache(equipment_id: Optional[str] = None):
    """Clear waveform cache."""
    if not waveform_manager:
        raise HTTPException(status_code=500, detail="Waveform manager not initialized")

    waveform_manager.clear_cache(equipment_id)
    return {"message": "Cache cleared successfully"}


# === Enhanced Measurements Endpoints ===


@router.post("/measurements", response_model=EnhancedMeasurements)
async def get_enhanced_measurements(request: MeasurementsRequest):
    """Get comprehensive automatic measurements (30+ types).

    Includes:
    - Voltage measurements (Vpp, Vmax, Vmin, Vrms, etc.)
    - Time measurements (period, frequency, rise/fall time)
    - Overshoot/preshoot
    - Edge counts
    - Area measurements
    - Slew rate
    - Signal quality (SNR, THD)
    - Statistical measurements
    """
    if not waveform_manager or not waveform_analyzer:
        raise HTTPException(status_code=500, detail="Waveform system not initialized")

    try:
        # Get waveform (from cache or capture new)
        if request.use_cached:
            waveform = waveform_manager.get_cached_waveform(
                request.equipment_id, request.channel
            )
            if not waveform:
                # Capture new waveform
                config = WaveformCaptureConfig(channel=request.channel)
                waveform = await waveform_manager.capture_waveform(
                    request.equipment_id, config
                )
        else:
            # Always capture new
            config = WaveformCaptureConfig(channel=request.channel)
            waveform = await waveform_manager.capture_waveform(
                request.equipment_id, config
            )

        # Calculate measurements
        measurements = waveform_analyzer.calculate_enhanced_measurements(waveform)
        return measurements

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/measurements/{equipment_id}/{channel}", response_model=EnhancedMeasurements
)
async def get_measurements_for_channel(equipment_id: str, channel: int):
    """Get enhanced measurements for cached waveform."""
    request = MeasurementsRequest(
        equipment_id=equipment_id,
        channel=channel,
        use_cached=True,
    )
    return await get_enhanced_measurements(request)


# === Cursor Measurement Endpoints ===


@router.post("/cursor", response_model=CursorData)
async def calculate_cursor_measurements(request: CursorRequest):
    """Calculate cursor measurements.

    Supports:
    - Horizontal cursors (time measurements)
    - Vertical cursors (voltage measurements)
    - Delta calculations
    - Value readouts at cursor positions
    """
    if not waveform_manager or not waveform_analyzer:
        raise HTTPException(status_code=500, detail="Waveform system not initialized")

    try:
        # Get cached waveform
        waveform = waveform_manager.get_cached_waveform(
            request.equipment_id, request.channel
        )
        if not waveform:
            raise HTTPException(
                status_code=404, detail="No waveform cached. Capture first."
            )

        # Calculate cursor measurements
        cursor_data = waveform_analyzer.calculate_cursor_measurements(
            waveform,
            request.cursor_type,
            request.cursor1_position,
            request.cursor2_position,
        )
        return cursor_data

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# === Math Channel Endpoints ===


@router.post("/math", response_model=MathChannelResult)
async def apply_math_operation(request: MathRequest):
    """Apply math operation to waveform(s).

    Supported operations:
    - Binary: add, subtract, multiply, divide
    - Unary: invert, abs, sqrt, square, log, exp
    - Transform: FFT, integrate, differentiate
    - Processing: average, envelope

    FFT provides magnitude, phase, real, and imaginary components.
    """
    if not waveform_manager or not waveform_analyzer:
        raise HTTPException(status_code=500, detail="Waveform system not initialized")

    try:
        # Get primary waveform
        waveform1 = waveform_manager.get_cached_waveform(
            request.equipment_id, request.config.source_channel1
        )
        if not waveform1:
            raise HTTPException(
                status_code=404,
                detail=f"No waveform cached for channel {request.config.source_channel1}",
            )

        # Get secondary waveform if needed
        waveform2 = None
        if request.config.source_channel2:
            waveform2 = waveform_manager.get_cached_waveform(
                request.equipment_id, request.config.source_channel2
            )
            if not waveform2:
                raise HTTPException(
                    status_code=404,
                    detail=f"No waveform cached for channel {request.config.source_channel2}",
                )

        # Apply math operation
        result = waveform_analyzer.apply_math_operation(
            request.config, waveform1, waveform2
        )
        return result

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# === Persistence Mode Endpoints ===


@router.post("/persistence/enable")
async def enable_persistence(request: PersistenceRequest):
    """Enable persistence mode for a channel.

    Modes:
    - INFINITE: Accumulate all waveforms
    - ENVELOPE: Show min/max envelope
    - VARIABLE: Variable persistence with decay
    """
    if not waveform_manager:
        raise HTTPException(status_code=500, detail="Waveform manager not initialized")

    try:
        waveform_manager.enable_persistence(
            request.equipment_id, request.channel, request.config
        )
        return {"message": "Persistence enabled"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/persistence/disable")
async def disable_persistence(equipment_id: str = Body(...), channel: int = Body(...)):
    """Disable persistence mode for a channel."""
    if not waveform_manager:
        raise HTTPException(status_code=500, detail="Waveform manager not initialized")

    waveform_manager.disable_persistence(equipment_id, channel)
    return {"message": "Persistence disabled"}


@router.get(
    "/persistence/{equipment_id}/{channel}", response_model=ExtendedWaveformData
)
async def get_persistence_data(equipment_id: str, channel: int):
    """Get accumulated persistence data."""
    if not waveform_manager:
        raise HTTPException(status_code=500, detail="Waveform manager not initialized")

    data = waveform_manager.get_persistence_data(equipment_id, channel)
    if not data:
        raise HTTPException(status_code=404, detail="No persistence data available")

    return data


# === Histogram Endpoints ===


@router.post("/histogram", response_model=HistogramData)
async def calculate_histogram(request: HistogramRequest):
    """Calculate voltage or time histogram.

    Provides:
    - Distribution bins and counts
    - Statistical measures (mean, std dev, median, mode)
    - Shape metrics (skewness, kurtosis)
    """
    if not waveform_manager or not waveform_analyzer:
        raise HTTPException(status_code=500, detail="Waveform system not initialized")

    try:
        # Get cached waveform
        waveform = waveform_manager.get_cached_waveform(
            request.equipment_id, request.channel
        )
        if not waveform:
            raise HTTPException(
                status_code=404, detail="No waveform cached. Capture first."
            )

        # Calculate histogram
        histogram = waveform_analyzer.calculate_histogram(
            waveform, request.histogram_type, request.num_bins
        )
        return histogram

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# === XY Plot Endpoints ===


@router.post("/xy-plot", response_model=XYPlotData)
async def create_xy_plot(request: XYPlotRequest):
    """Create XY plot from two channels.

    Plots X-channel voltage vs Y-channel voltage.
    Both channels must be captured first.
    """
    if not waveform_manager:
        raise HTTPException(status_code=500, detail="Waveform manager not initialized")

    try:
        xy_plot = await waveform_manager.create_xy_plot(
            request.equipment_id, request.x_channel, request.y_channel
        )
        return xy_plot
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# === Continuous Acquisition Endpoints ===


@router.post("/continuous/start", response_model=AcquisitionResponse)
async def start_continuous_acquisition(request: ContinuousAcquisitionRequest):
    """Start continuous high-speed waveform acquisition.

    Continuously captures waveforms at the specified rate.
    Returns a task ID that can be used to stop the acquisition.
    """
    if not waveform_manager:
        raise HTTPException(status_code=500, detail="Waveform manager not initialized")

    try:
        task_id = await waveform_manager.start_continuous_acquisition(
            request.equipment_id, request.channel, request.rate_hz
        )
        return AcquisitionResponse(
            task_id=task_id,
            message=f"Started continuous acquisition at {request.rate_hz} Hz",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/continuous/stop")
async def stop_continuous_acquisition(task_id: str = Body(..., embed=True)):
    """Stop continuous acquisition."""
    if not waveform_manager:
        raise HTTPException(status_code=500, detail="Waveform manager not initialized")

    try:
        await waveform_manager.stop_continuous_acquisition(task_id)
        return {"message": "Acquisition stopped"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/continuous/list")
async def list_continuous_acquisitions():
    """List active continuous acquisitions."""
    if not waveform_manager:
        raise HTTPException(status_code=500, detail="Waveform manager not initialized")

    task_ids = list(waveform_manager.acquisition_tasks.keys())
    return {"active_acquisitions": task_ids, "count": len(task_ids)}


# === Statistics and Info Endpoints ===


@router.get("/info")
async def get_waveform_info():
    """Get waveform system information."""
    if not waveform_manager:
        raise HTTPException(status_code=500, detail="Waveform manager not initialized")

    # Count cached waveforms
    cached_count = sum(
        len(channels) for channels in waveform_manager.waveform_cache.values()
    )

    # Count persistence buffers
    persistence_count = len(waveform_manager.persistence_configs)

    # Count active acquisitions
    acquisition_count = len(waveform_manager.acquisition_tasks)

    return {
        "cached_waveforms": cached_count,
        "persistence_channels": persistence_count,
        "active_acquisitions": acquisition_count,
        "xy_plots_cached": len(waveform_manager.xy_plot_cache),
    }
