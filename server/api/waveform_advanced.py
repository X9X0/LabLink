"""API endpoints for advanced waveform analysis tools."""

from typing import List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field
from waveform.advanced_analysis import AdvancedWaveformAnalyzer
from waveform.advanced_models import (
    ComparisonResult,
    CrossCorrelationData,
    EyeDiagramConfig,
    EyeDiagramData,
    JitterConfig,
    JitterData,
    MaskDefinition,
    MaskTestResult,
    ReferenceWaveform,
    SearchConfig,
    SearchResult,
    SpectrogramConfig,
    SpectrogramData,
    TransferFunctionData,
    TrendData,
    TrendParameter,
)
from waveform.manager import WaveformManager

router = APIRouter(prefix="/api/waveform/advanced", tags=["waveform-advanced"])

# Global instances (initialized in main.py)
waveform_manager: Optional[WaveformManager] = None
advanced_analyzer: Optional[AdvancedWaveformAnalyzer] = None


def init_advanced_waveform_api(manager: WaveformManager, analyzer: AdvancedWaveformAnalyzer):
    """Initialize advanced waveform API with manager and analyzer instances."""
    global waveform_manager, advanced_analyzer
    waveform_manager = manager
    advanced_analyzer = analyzer


# === Request Models ===


class SpectrogramRequest(BaseModel):
    """Spectrogram analysis request."""

    equipment_id: str = Field(..., description="Equipment ID")
    channel: int = Field(..., description="Channel number")
    use_cached: bool = Field(True, description="Use cached waveform")
    config: SpectrogramConfig = Field(..., description="Spectrogram configuration")


class CrossCorrelationRequest(BaseModel):
    """Cross-correlation request."""

    equipment_id: str = Field(..., description="Equipment ID")
    channel1: int = Field(..., description="First channel")
    channel2: int = Field(..., description="Second channel")
    use_cached: bool = Field(True, description="Use cached waveforms")


class TransferFunctionRequest(BaseModel):
    """Transfer function request."""

    equipment_id: str = Field(..., description="Equipment ID")
    input_channel: int = Field(..., description="Input channel")
    output_channel: int = Field(..., description="Output channel")
    use_cached: bool = Field(True, description="Use cached waveforms")
    nperseg: int = Field(256, description="Segment length for Welch's method")


class JitterRequest(BaseModel):
    """Jitter analysis request."""

    equipment_id: str = Field(..., description="Equipment ID")
    channel: int = Field(..., description="Channel number")
    use_cached: bool = Field(True, description="Use cached waveform")
    config: JitterConfig = Field(..., description="Jitter configuration")


class EyeDiagramRequest(BaseModel):
    """Eye diagram request."""

    equipment_id: str = Field(..., description="Equipment ID")
    channel: int = Field(..., description="Channel number")
    use_cached: bool = Field(True, description="Use cached waveform")
    config: EyeDiagramConfig = Field(..., description="Eye diagram configuration")


class MaskTestRequest(BaseModel):
    """Mask test request."""

    equipment_id: str = Field(..., description="Equipment ID")
    channel: int = Field(..., description="Channel number")
    use_cached: bool = Field(True, description="Use cached waveform")
    mask_name: str = Field(..., description="Name of mask to test against")


class SearchRequest(BaseModel):
    """Waveform search request."""

    equipment_id: str = Field(..., description="Equipment ID")
    channel: int = Field(..., description="Channel number")
    use_cached: bool = Field(True, description="Use cached waveform")
    config: SearchConfig = Field(..., description="Search configuration")


class CompareRequest(BaseModel):
    """Reference waveform comparison request."""

    equipment_id: str = Field(..., description="Equipment ID")
    channel: int = Field(..., description="Channel number")
    use_cached: bool = Field(True, description="Use cached waveform")
    reference_name: str = Field(..., description="Name of reference waveform")


class TrendUpdateRequest(BaseModel):
    """Trend update request."""

    equipment_id: str = Field(..., description="Equipment ID")
    channel: int = Field(..., description="Channel number")
    parameter: TrendParameter = Field(..., description="Parameter to trend")
    value: float = Field(..., description="Parameter value")


# === Spectral Analysis Endpoints ===


@router.post("/spectrogram", response_model=SpectrogramData)
async def calculate_spectrogram(request: SpectrogramRequest):
    """Calculate spectrogram (time-frequency analysis).

    Performs short-time Fourier transform to show how frequency content
    changes over time.

    **Configuration:**
    - window_size: FFT window size (default: 256)
    - overlap: Window overlap in samples (default: 128)
    - window_function: Window type (hann, hamming, blackman, etc.)
    - mode: Display mode (magnitude, power, db)
    - freq_min/max: Frequency range limits

    **Use Cases:**
    - Analyze frequency modulation
    - Detect transient events
    - Chirp signal analysis
    - Time-varying spectrum visualization
    """
    if not waveform_manager or not advanced_analyzer:
        raise HTTPException(status_code=500, detail="Waveform system not initialized")

    # Get waveform
    waveform = waveform_manager.get_cached_waveform(request.equipment_id, request.channel)
    if not waveform:
        raise HTTPException(
            status_code=404,
            detail=f"No cached waveform for {request.equipment_id} channel {request.channel}",
        )

    import numpy as np

    time_data = np.array(waveform.time_data)
    voltage_data = np.array(waveform.voltage_data)

    try:
        result = advanced_analyzer.calculate_spectrogram(
            request.equipment_id,
            request.channel,
            time_data,
            voltage_data,
            waveform.sample_rate,
            request.config,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Spectrogram calculation failed: {str(e)}")


@router.post("/cross-correlation", response_model=CrossCorrelationData)
async def calculate_cross_correlation(request: CrossCorrelationRequest):
    """Calculate cross-correlation between two waveforms.

    Measures similarity and time delay between two signals.

    **Results:**
    - Correlation coefficient (-1 to 1)
    - Time lag at maximum correlation
    - Full correlation function

    **Use Cases:**
    - Measure propagation delay
    - Compare signal similarity
    - Detect phase relationships
    - Time-of-flight measurements
    """
    if not waveform_manager or not advanced_analyzer:
        raise HTTPException(status_code=500, detail="Waveform system not initialized")

    # Get both waveforms
    wf1 = waveform_manager.get_cached_waveform(request.equipment_id, request.channel1)
    wf2 = waveform_manager.get_cached_waveform(request.equipment_id, request.channel2)

    if not wf1 or not wf2:
        raise HTTPException(status_code=404, detail="One or both waveforms not cached")

    import numpy as np

    voltage1 = np.array(wf1.voltage_data)
    voltage2 = np.array(wf2.voltage_data)

    try:
        result = advanced_analyzer.calculate_cross_correlation(
            request.equipment_id,
            request.channel1,
            voltage1,
            request.channel2,
            voltage2,
            wf1.sample_rate,
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Cross-correlation calculation failed: {str(e)}"
        )


@router.post("/transfer-function", response_model=TransferFunctionData)
async def calculate_transfer_function(request: TransferFunctionRequest):
    """Calculate transfer function H(f) = Y(f)/X(f).

    Analyzes system frequency response by comparing input and output signals.

    **Results:**
    - Magnitude response (linear and dB)
    - Phase response (degrees)
    - Coherence function (quality metric)

    **Use Cases:**
    - Filter characterization
    - Amplifier frequency response
    - System identification
    - Bode plot generation
    """
    if not waveform_manager or not advanced_analyzer:
        raise HTTPException(status_code=500, detail="Waveform system not initialized")

    # Get both waveforms
    wf_in = waveform_manager.get_cached_waveform(request.equipment_id, request.input_channel)
    wf_out = waveform_manager.get_cached_waveform(request.equipment_id, request.output_channel)

    if not wf_in or not wf_out:
        raise HTTPException(status_code=404, detail="Input or output waveform not cached")

    import numpy as np

    input_voltage = np.array(wf_in.voltage_data)
    output_voltage = np.array(wf_out.voltage_data)

    try:
        result = advanced_analyzer.calculate_transfer_function(
            request.equipment_id,
            request.input_channel,
            input_voltage,
            request.output_channel,
            output_voltage,
            wf_in.sample_rate,
            request.nperseg,
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Transfer function calculation failed: {str(e)}"
        )


# === Jitter Analysis Endpoints ===


@router.post("/jitter", response_model=JitterData)
async def calculate_jitter(request: JitterRequest):
    """Calculate jitter measurements.

    Analyzes timing variations in digital signals.

    **Jitter Types:**
    - TIE: Time Interval Error
    - PERIOD: Period jitter
    - CYCLE_TO_CYCLE: Cycle-to-cycle jitter
    - HALF_PERIOD: Half-period jitter
    - N_PERIOD: N-period jitter

    **Results:**
    - Mean, RMS, and peak-to-peak jitter
    - Jitter histogram
    - Statistical distribution

    **Use Cases:**
    - Clock quality analysis
    - Serial data characterization
    - PLL performance testing
    - Compliance testing
    """
    if not waveform_manager or not advanced_analyzer:
        raise HTTPException(status_code=500, detail="Waveform system not initialized")

    # Get waveform
    waveform = waveform_manager.get_cached_waveform(request.equipment_id, request.channel)
    if not waveform:
        raise HTTPException(
            status_code=404,
            detail=f"No cached waveform for {request.equipment_id} channel {request.channel}",
        )

    import numpy as np

    time_data = np.array(waveform.time_data)
    voltage_data = np.array(waveform.voltage_data)

    try:
        result = advanced_analyzer.calculate_jitter(
            request.equipment_id,
            request.channel,
            time_data,
            voltage_data,
            request.config,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Jitter calculation failed: {str(e)}")


# === Eye Diagram Endpoints ===


@router.post("/eye-diagram", response_model=EyeDiagramData)
async def generate_eye_diagram(request: EyeDiagramRequest):
    """Generate eye diagram for serial data analysis.

    Creates overlaid display of data bits to visualize signal quality.

    **Configuration:**
    - bit_rate: Data rate in bps
    - samples_per_symbol: Resolution
    - edge_threshold: Decision threshold
    - num_traces: Number of overlays
    - persistence_mode: Enable persistence map

    **Measurements:**
    - Eye height and width
    - Crossing percentage
    - RMS and peak-to-peak jitter
    - Q-factor and SNR
    - Eye opening percentage

    **Use Cases:**
    - Serial link validation
    - Signal integrity analysis
    - Transmitter characterization
    - Standards compliance
    """
    if not waveform_manager or not advanced_analyzer:
        raise HTTPException(status_code=500, detail="Waveform system not initialized")

    # Get waveform
    waveform = waveform_manager.get_cached_waveform(request.equipment_id, request.channel)
    if not waveform:
        raise HTTPException(
            status_code=404,
            detail=f"No cached waveform for {request.equipment_id} channel {request.channel}",
        )

    import numpy as np

    time_data = np.array(waveform.time_data)
    voltage_data = np.array(waveform.voltage_data)

    try:
        result = advanced_analyzer.generate_eye_diagram(
            request.equipment_id,
            request.channel,
            time_data,
            voltage_data,
            request.config,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Eye diagram generation failed: {str(e)}")


# === Mask Testing Endpoints ===


@router.post("/mask/define", response_model=dict)
async def define_mask(mask: MaskDefinition):
    """Define a new mask for testing.

    Masks define pass/fail regions for waveforms.

    **Mask Types:**
    - POLYGON: User-defined polygon regions
    - STANDARD: Standard templates (e.g., eye diagram masks)
    - AUTO: Auto-generated from reference

    **Polygon Format:**
    - List of (time, voltage) points
    - fail_inside: True if waveform inside polygon should fail

    **Use Cases:**
    - Standards compliance testing
    - Quality control
    - Automated pass/fail testing
    - Eye diagram mask testing
    """
    if not advanced_analyzer:
        raise HTTPException(status_code=500, detail="Advanced analyzer not initialized")

    try:
        advanced_analyzer.add_mask_definition(mask)
        return {"status": "success", "mask_name": mask.name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Mask definition failed: {str(e)}")


@router.get("/mask/list", response_model=List[str])
async def list_masks():
    """List all defined masks."""
    if not advanced_analyzer:
        raise HTTPException(status_code=500, detail="Advanced analyzer not initialized")

    return list(advanced_analyzer.mask_definitions.keys())


@router.post("/mask/test", response_model=MaskTestResult)
async def test_mask(request: MaskTestRequest):
    """Test waveform against a mask.

    **Results:**
    - Overall pass/fail
    - Number of violations
    - Failure locations
    - Per-region failure counts
    - Margin analysis

    **Use Cases:**
    - Production testing
    - Design validation
    - Margin testing
    - Compliance verification
    """
    if not waveform_manager or not advanced_analyzer:
        raise HTTPException(status_code=500, detail="Waveform system not initialized")

    # Get waveform
    waveform = waveform_manager.get_cached_waveform(request.equipment_id, request.channel)
    if not waveform:
        raise HTTPException(
            status_code=404,
            detail=f"No cached waveform for {request.equipment_id} channel {request.channel}",
        )

    import numpy as np

    time_data = np.array(waveform.time_data)
    voltage_data = np.array(waveform.voltage_data)

    try:
        result = advanced_analyzer.test_mask(
            request.equipment_id,
            request.channel,
            time_data,
            voltage_data,
            request.mask_name,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Mask test failed: {str(e)}")


# === Waveform Search Endpoints ===


@router.post("/search", response_model=SearchResult)
async def search_events(request: SearchRequest):
    """Search for specific events in waveform.

    **Event Types:**
    - EDGE_RISING/FALLING: Edge detection
    - PULSE_POSITIVE/NEGATIVE: Pulse detection with width filtering
    - RUNT: Runt pulse detection
    - TIMEOUT: Timeout violation
    - GLITCH: Narrow glitch detection

    **Configuration:**
    - Threshold levels
    - Min/max pulse width
    - Timeout duration
    - Max events to find

    **Results:**
    - List of events with times and details
    - Event rate and spacing statistics

    **Use Cases:**
    - Protocol analysis
    - Anomaly detection
    - Glitch detection
    - Timing verification
    """
    if not waveform_manager or not advanced_analyzer:
        raise HTTPException(status_code=500, detail="Waveform system not initialized")

    # Get waveform
    waveform = waveform_manager.get_cached_waveform(request.equipment_id, request.channel)
    if not waveform:
        raise HTTPException(
            status_code=404,
            detail=f"No cached waveform for {request.equipment_id} channel {request.channel}",
        )

    import numpy as np

    time_data = np.array(waveform.time_data)
    voltage_data = np.array(waveform.voltage_data)

    try:
        result = advanced_analyzer.search_events(
            request.equipment_id,
            request.channel,
            time_data,
            voltage_data,
            request.config,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Event search failed: {str(e)}")


# === Reference Waveform Endpoints ===


@router.post("/reference/add", response_model=dict)
async def add_reference_waveform(reference: ReferenceWaveform):
    """Add a reference waveform for comparison.

    Reference waveforms serve as "golden" standards for comparison.

    **Tolerance Settings:**
    - voltage_tolerance_percent: Allowed voltage deviation
    - time_tolerance_percent: Allowed time deviation

    **Use Cases:**
    - Golden unit comparison
    - Production testing
    - Design validation
    - Anomaly detection
    """
    if not advanced_analyzer:
        raise HTTPException(status_code=500, detail="Advanced analyzer not initialized")

    try:
        advanced_analyzer.add_reference_waveform(reference)
        return {"status": "success", "reference_name": reference.name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reference addition failed: {str(e)}")


@router.get("/reference/list", response_model=List[str])
async def list_references():
    """List all reference waveforms."""
    if not advanced_analyzer:
        raise HTTPException(status_code=500, detail="Advanced analyzer not initialized")

    return list(advanced_analyzer.reference_waveforms.keys())


@router.post("/reference/compare", response_model=ComparisonResult)
async def compare_to_reference(request: CompareRequest):
    """Compare waveform to reference.

    **Results:**
    - Overall pass/fail
    - Similarity percentage
    - RMS, max, and mean voltage errors
    - Correlation coefficient
    - Phase shift
    - Failure point locations

    **Use Cases:**
    - Production QC
    - Design verification
    - Troubleshooting
    - Regression testing
    """
    if not waveform_manager or not advanced_analyzer:
        raise HTTPException(status_code=500, detail="Waveform system not initialized")

    # Get waveform
    waveform = waveform_manager.get_cached_waveform(request.equipment_id, request.channel)
    if not waveform:
        raise HTTPException(
            status_code=404,
            detail=f"No cached waveform for {request.equipment_id} channel {request.channel}",
        )

    import numpy as np

    time_data = np.array(waveform.time_data)
    voltage_data = np.array(waveform.voltage_data)

    try:
        result = advanced_analyzer.compare_to_reference(
            request.equipment_id,
            request.channel,
            time_data,
            voltage_data,
            request.reference_name,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reference comparison failed: {str(e)}")


# === Parameter Trending Endpoints ===


@router.post("/trend/update", response_model=TrendData)
async def update_trend(request: TrendUpdateRequest):
    """Update parameter trend with new value.

    **Trendable Parameters:**
    - Frequency, Amplitude, Vpp, Vrms
    - Rise/fall time, Duty cycle
    - Overshoot, SNR, THD
    - Jitter metrics
    - Eye diagram parameters

    **Statistics:**
    - Mean, std dev, min/max, range
    - Drift rate (linear regression)
    - Trend direction (up/down/stable)

    **Use Cases:**
    - Long-term monitoring
    - Drift detection
    - Aging analysis
    - Predictive maintenance
    """
    if not advanced_analyzer:
        raise HTTPException(status_code=500, detail="Advanced analyzer not initialized")

    try:
        result = advanced_analyzer.update_trend(
            request.equipment_id,
            request.channel,
            request.parameter,
            request.value,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trend update failed: {str(e)}")


@router.get("/trend/get/{equipment_id}/{channel}/{parameter}", response_model=TrendData)
async def get_trend(
    equipment_id: str,
    channel: int,
    parameter: TrendParameter,
):
    """Get trend data for a parameter."""
    if not advanced_analyzer:
        raise HTTPException(status_code=500, detail="Advanced analyzer not initialized")

    result = advanced_analyzer.get_trend_data(equipment_id, channel, parameter)
    if result is None:
        raise HTTPException(status_code=404, detail="Trend data not found")

    return result


@router.get("/info", response_model=dict)
async def get_advanced_info():
    """Get advanced waveform analysis system information."""
    if not advanced_analyzer:
        raise HTTPException(status_code=500, detail="Advanced analyzer not initialized")

    return {
        "reference_waveforms": len(advanced_analyzer.reference_waveforms),
        "mask_definitions": len(advanced_analyzer.mask_definitions),
        "active_trends": len(advanced_analyzer.trend_data),
        "features": [
            "Spectral Analysis (spectrogram, cross-correlation, transfer function)",
            "Jitter Analysis (TIE, period, cycle-to-cycle, half-period, N-period)",
            "Eye Diagram Generation and Analysis",
            "Mask Testing (polygon, standard, auto)",
            "Waveform Search (edges, pulses, runts, glitches)",
            "Reference Waveform Comparison",
            "Parameter Trending",
        ],
    }
