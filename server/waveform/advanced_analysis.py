"""Advanced waveform analysis implementation.

This module provides advanced analysis features for oscilloscope waveforms:
- Spectral analysis (spectrograms, cross-correlation, transfer functions)
- Jitter analysis (TIE, period, cycle-to-cycle)
- Eye diagram generation and analysis
- Mask testing
- Waveform search and event detection
- Reference waveform comparison
- Parameter trending
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import signal, stats
from scipy.fft import fft, fftfreq
from scipy.interpolate import interp1d
from waveform.advanced_models import (
    ComparisonResult,
    CrossCorrelationData,
    EyeDiagramConfig,
    EyeDiagramData,
    EyeParameters,
    JitterConfig,
    JitterData,
    JitterType,
    MaskDefinition,
    MaskPoint,
    MaskPolygon,
    MaskTestResult,
    ReferenceWaveform,
    SearchConfig,
    SearchEvent,
    SearchEventType,
    SearchResult,
    SpectrogramConfig,
    SpectrogramData,
    SpectrogramMode,
    TransferFunctionData,
    TrendConfig,
    TrendData,
    TrendDataPoint,
    TrendParameter,
)


class AdvancedWaveformAnalyzer:
    """Advanced waveform analysis tools."""

    def __init__(self):
        """Initialize advanced analyzer."""
        # Storage for reference waveforms
        self.reference_waveforms: Dict[str, ReferenceWaveform] = {}

        # Storage for trend data
        self.trend_data: Dict[Tuple[str, int, TrendParameter], TrendData] = {}

        # Storage for mask definitions
        self.mask_definitions: Dict[str, MaskDefinition] = {}

    # === Spectral Analysis Methods ===

    def calculate_spectrogram(
        self,
        equipment_id: str,
        channel: int,
        time_data: np.ndarray,
        voltage_data: np.ndarray,
        sample_rate: float,
        config: SpectrogramConfig,
    ) -> SpectrogramData:
        """Calculate spectrogram (time-frequency analysis).

        Args:
            equipment_id: Equipment identifier
            channel: Channel number
            time_data: Time array
            voltage_data: Voltage array
            sample_rate: Sample rate in Hz
            config: Spectrogram configuration

        Returns:
            SpectrogramData with time-frequency representation
        """
        # Validate window size
        if config.window_size > len(voltage_data):
            config.window_size = len(voltage_data) // 4

        # Get window function
        window = signal.get_window(config.window_function, config.window_size)

        # Calculate spectrogram
        frequencies, times, Sxx = signal.spectrogram(
            voltage_data,
            fs=sample_rate,
            window=window,
            nperseg=config.window_size,
            noverlap=config.overlap,
            mode="magnitude" if config.mode == SpectrogramMode.MAGNITUDE else "psd",
        )

        # Apply mode transformation
        if config.mode == SpectrogramMode.DB:
            Sxx = 20 * np.log10(Sxx + 1e-10)  # Add small value to avoid log(0)
        elif config.mode == SpectrogramMode.POWER:
            Sxx = Sxx**2

        # Apply frequency limits
        if config.freq_min is not None or config.freq_max is not None:
            freq_min = config.freq_min if config.freq_min is not None else 0
            freq_max = (
                config.freq_max if config.freq_max is not None else frequencies[-1]
            )
            freq_mask = (frequencies >= freq_min) & (frequencies <= freq_max)
            frequencies = frequencies[freq_mask]
            Sxx = Sxx[freq_mask, :]

        return SpectrogramData(
            equipment_id=equipment_id,
            channel=channel,
            frequencies=frequencies.tolist(),
            times=times.tolist(),
            power_matrix=Sxx.T.tolist(),  # Transpose for [time][freq] ordering
            sample_rate=sample_rate,
            window_size=config.window_size,
            overlap=config.overlap,
        )

    def calculate_cross_correlation(
        self,
        equipment_id: str,
        channel1: int,
        voltage1: np.ndarray,
        channel2: int,
        voltage2: np.ndarray,
        sample_rate: float,
    ) -> CrossCorrelationData:
        """Calculate cross-correlation between two waveforms.

        Args:
            equipment_id: Equipment identifier
            channel1: First channel number
            voltage1: First channel voltage data
            channel2: Second channel number
            voltage2: Second channel voltage data
            sample_rate: Sample rate in Hz

        Returns:
            CrossCorrelationData with correlation analysis
        """
        # Ensure same length
        min_len = min(len(voltage1), len(voltage2))
        v1 = voltage1[:min_len]
        v2 = voltage2[:min_len]

        # Calculate cross-correlation
        correlation = signal.correlate(v1, v2, mode="full", method="fft")
        correlation = correlation / np.max(np.abs(correlation))  # Normalize

        # Calculate lags
        lags = signal.correlation_lags(len(v1), len(v2), mode="full")
        lags_time = lags / sample_rate

        # Find maximum correlation
        max_idx = np.argmax(np.abs(correlation))
        max_correlation = correlation[max_idx]
        lag_at_max = lags_time[max_idx]

        # Calculate Pearson correlation coefficient (at zero lag)
        zero_lag_idx = len(correlation) // 2
        pearson_corr = np.corrcoef(v1, v2)[0, 1]

        return CrossCorrelationData(
            equipment_id=equipment_id,
            channel1=channel1,
            channel2=channel2,
            lags=lags_time.tolist(),
            correlation=correlation.tolist(),
            max_correlation=float(max_correlation),
            lag_at_max=float(lag_at_max),
            correlation_coefficient=float(pearson_corr),
        )

    def calculate_transfer_function(
        self,
        equipment_id: str,
        input_channel: int,
        input_voltage: np.ndarray,
        output_channel: int,
        output_voltage: np.ndarray,
        sample_rate: float,
        nperseg: int = 256,
    ) -> TransferFunctionData:
        """Calculate transfer function H(f) = Y(f)/X(f).

        Args:
            equipment_id: Equipment identifier
            input_channel: Input channel number
            input_voltage: Input signal
            output_channel: Output channel number
            output_voltage: Output signal
            sample_rate: Sample rate in Hz
            nperseg: Segment length for Welch's method

        Returns:
            TransferFunctionData with frequency response
        """
        # Ensure same length
        min_len = min(len(input_voltage), len(output_voltage))
        x = input_voltage[:min_len]
        y = output_voltage[:min_len]

        # Calculate cross-spectral density and power spectral densities
        f, Pxy = signal.csd(x, y, fs=sample_rate, nperseg=nperseg)
        _, Pxx = signal.welch(x, fs=sample_rate, nperseg=nperseg)
        _, Pyy = signal.welch(y, fs=sample_rate, nperseg=nperseg)

        # Calculate transfer function
        H = Pxy / (Pxx + 1e-10)  # Add small value to avoid division by zero

        # Extract magnitude and phase
        magnitude = np.abs(H)
        phase = np.angle(H, deg=True)
        magnitude_db = 20 * np.log10(magnitude + 1e-10)

        # Calculate coherence
        coherence = np.abs(Pxy) ** 2 / (Pxx * Pyy + 1e-10)

        return TransferFunctionData(
            equipment_id=equipment_id,
            input_channel=input_channel,
            output_channel=output_channel,
            frequencies=f.tolist(),
            magnitude=magnitude.tolist(),
            phase=phase.tolist(),
            magnitude_db=magnitude_db.tolist(),
            coherence=coherence.tolist(),
        )

    # === Jitter Analysis Methods ===

    def calculate_jitter(
        self,
        equipment_id: str,
        channel: int,
        time_data: np.ndarray,
        voltage_data: np.ndarray,
        config: JitterConfig,
    ) -> JitterData:
        """Calculate jitter measurements.

        Args:
            equipment_id: Equipment identifier
            channel: Channel number
            time_data: Time array
            voltage_data: Voltage array
            config: Jitter configuration

        Returns:
            JitterData with jitter analysis results
        """
        # Determine threshold if not provided
        if config.threshold is None:
            threshold = (np.max(voltage_data) + np.min(voltage_data)) / 2
        else:
            threshold = config.threshold

        # Find edge crossings
        if config.edge_type == "rising":
            crossings = np.where(
                (voltage_data[:-1] < threshold) & (voltage_data[1:] >= threshold)
            )[0]
        else:  # falling
            crossings = np.where(
                (voltage_data[:-1] > threshold) & (voltage_data[1:] <= threshold)
            )[0]

        if len(crossings) < 2:
            raise ValueError("Not enough edge crossings found for jitter analysis")

        # Interpolate to get precise crossing times
        crossing_times = []
        for idx in crossings:
            # Linear interpolation between samples
            t1, v1 = time_data[idx], voltage_data[idx]
            t2, v2 = time_data[idx + 1], voltage_data[idx + 1]
            t_cross = t1 + (threshold - v1) * (t2 - t1) / (v2 - v1)
            crossing_times.append(t_cross)

        crossing_times = np.array(crossing_times)

        # Calculate jitter based on type
        if config.jitter_type == JitterType.TIE:
            # Time Interval Error: deviation from ideal edge positions
            periods = np.diff(crossing_times)
            ideal_period = np.median(periods)
            ideal_times = crossing_times[0] + np.arange(len(crossing_times)) * ideal_period
            jitter_values = crossing_times - ideal_times
            jitter_times = crossing_times

        elif config.jitter_type == JitterType.PERIOD:
            # Period jitter: deviation of period from mean
            periods = np.diff(crossing_times)
            mean_period = np.mean(periods)
            jitter_values = periods - mean_period
            jitter_times = crossing_times[1:]

        elif config.jitter_type == JitterType.CYCLE_TO_CYCLE:
            # Cycle-to-cycle jitter: difference between consecutive periods
            periods = np.diff(crossing_times)
            jitter_values = np.diff(periods)
            jitter_times = crossing_times[2:]

        elif config.jitter_type == JitterType.HALF_PERIOD:
            # Half-period jitter (for both edges)
            jitter_values = np.diff(crossing_times)
            mean_half_period = np.mean(jitter_values)
            jitter_values = jitter_values - mean_half_period
            jitter_times = crossing_times[1:]

        elif config.jitter_type == JitterType.N_PERIOD:
            # N-period jitter
            n = config.n_periods
            if len(crossing_times) < n + 1:
                raise ValueError(
                    f"Not enough edges for {n}-period jitter (need {n+1})"
                )
            periods = crossing_times[n:] - crossing_times[:-n]
            mean_n_period = np.mean(periods)
            jitter_values = periods - mean_n_period
            jitter_times = crossing_times[n:]

        else:
            raise ValueError(f"Unknown jitter type: {config.jitter_type}")

        # Calculate statistics
        mean_jitter = float(np.mean(jitter_values))
        rms_jitter = float(np.sqrt(np.mean(jitter_values**2)))
        pk_pk_jitter = float(np.max(jitter_values) - np.min(jitter_values))
        std_dev = float(np.std(jitter_values))

        # Create histogram
        num_bins = min(50, len(jitter_values) // 10 + 10)
        hist_counts, hist_edges = np.histogram(jitter_values, bins=num_bins)

        # Determine ideal period
        if config.jitter_type in [JitterType.PERIOD, JitterType.HALF_PERIOD]:
            ideal_period = float(np.median(np.diff(crossing_times)))
        else:
            ideal_period = None

        return JitterData(
            equipment_id=equipment_id,
            channel=channel,
            jitter_type=config.jitter_type,
            jitter_values=jitter_values.tolist(),
            jitter_times=jitter_times.tolist(),
            mean_jitter=mean_jitter,
            rms_jitter=rms_jitter,
            pk_pk_jitter=pk_pk_jitter,
            std_dev=std_dev,
            histogram_bins=hist_edges.tolist(),
            histogram_counts=hist_counts.tolist(),
            n_edges=len(crossings),
            ideal_period=ideal_period,
        )

    # === Eye Diagram Methods ===

    def generate_eye_diagram(
        self,
        equipment_id: str,
        channel: int,
        time_data: np.ndarray,
        voltage_data: np.ndarray,
        config: EyeDiagramConfig,
    ) -> EyeDiagramData:
        """Generate eye diagram for serial data.

        Args:
            equipment_id: Equipment identifier
            channel: Channel number
            time_data: Time array
            voltage_data: Voltage array
            config: Eye diagram configuration

        Returns:
            EyeDiagramData with eye diagram and measurements
        """
        # Calculate symbol period
        symbol_period = 1.0 / config.bit_rate

        # Determine threshold
        if config.edge_threshold is None:
            threshold = (np.max(voltage_data) + np.min(voltage_data)) / 2
        else:
            threshold = config.edge_threshold

        # Find edge crossings (rising edges for clock recovery)
        crossings_idx = np.where(
            (voltage_data[:-1] < threshold) & (voltage_data[1:] >= threshold)
        )[0]

        if len(crossings_idx) < 3:
            raise ValueError("Not enough edge crossings for eye diagram")

        # Extract symbol traces
        sample_rate = 1.0 / np.mean(np.diff(time_data))
        samples_per_symbol = int(symbol_period * sample_rate)

        # Create normalized time axis (0 to 2 symbol periods for full eye)
        time_axis = np.linspace(0, 2, config.samples_per_symbol)

        traces = []
        for i in range(len(crossings_idx) - 2):
            start_idx = crossings_idx[i]
            end_idx = start_idx + 2 * samples_per_symbol

            if end_idx < len(voltage_data):
                # Extract trace
                trace_data = voltage_data[start_idx:end_idx]

                # Resample to standard length
                if len(trace_data) != config.samples_per_symbol:
                    x_old = np.linspace(0, 2, len(trace_data))
                    interp_func = interp1d(x_old, trace_data, kind="linear")
                    trace_data = interp_func(time_axis)

                traces.append(trace_data.tolist())

                if config.num_traces and len(traces) >= config.num_traces:
                    break

        traces_array = np.array(traces)

        # Calculate eye parameters
        eye_params = self._calculate_eye_parameters(
            traces_array, time_axis, config.bit_rate
        )

        # Create persistence map if requested
        persistence_map = None
        if config.persistence_mode:
            # Create 2D histogram
            voltage_bins = 100
            time_bins = config.samples_per_symbol

            v_min, v_max = np.min(traces_array), np.max(traces_array)
            persistence_map = np.zeros((voltage_bins, time_bins), dtype=int)

            for trace in traces_array:
                for t_idx, voltage in enumerate(trace):
                    v_bin = int(
                        (voltage - v_min) / (v_max - v_min + 1e-10) * (voltage_bins - 1)
                    )
                    v_bin = np.clip(v_bin, 0, voltage_bins - 1)
                    persistence_map[v_bin, t_idx] += 1

            persistence_map = persistence_map.tolist()

        return EyeDiagramData(
            equipment_id=equipment_id,
            channel=channel,
            bit_rate=config.bit_rate,
            time_axis=time_axis.tolist(),
            traces=[trace for trace in traces],
            persistence_map=persistence_map,
            parameters=eye_params,
            sample_point_time=eye_params.crossing_percent / 100.0,  # Normalized
            sample_point_voltage=(eye_params.one_level + eye_params.zero_level) / 2,
            num_traces=len(traces),
            num_bits_analyzed=len(traces),
        )

    def _calculate_eye_parameters(
        self, traces: np.ndarray, time_axis: np.ndarray, bit_rate: float
    ) -> EyeParameters:
        """Calculate eye diagram parameters from traces.

        Args:
            traces: Array of overlaid traces [num_traces, num_samples]
            time_axis: Normalized time axis
            bit_rate: Bit rate in bps

        Returns:
            EyeParameters with measurements
        """
        # Find center of eye (around 50% of time axis)
        center_idx = len(time_axis) // 2
        center_region = slice(
            max(0, center_idx - 10), min(len(time_axis), center_idx + 10)
        )

        # Separate logic levels (simple k-means with k=2)
        center_voltages = traces[:, center_region].flatten()
        sorted_v = np.sort(center_voltages)
        mid_point = len(sorted_v) // 2

        zero_level_data = sorted_v[:mid_point]
        one_level_data = sorted_v[mid_point:]

        zero_level = float(np.mean(zero_level_data))
        one_level = float(np.mean(one_level_data))

        # Eye height and amplitude
        eye_height = float(one_level - zero_level)
        eye_amplitude = float(np.max(traces) - np.min(traces))

        # Crossing percentage (find where traces cross 50% level)
        mid_voltage = (one_level + zero_level) / 2
        crossing_times = []

        for trace in traces:
            # Find crossing in first half
            crossings = np.where(
                (trace[:-1] < mid_voltage) & (trace[1:] >= mid_voltage)
            )[0]
            if len(crossings) > 0:
                crossing_times.append(time_axis[crossings[0]])

        if crossing_times:
            crossing_percent = float(np.mean(crossing_times) * 50)  # Convert to %
        else:
            crossing_percent = 50.0

        # Eye width (measure at mid-voltage level)
        eye_width = float(1.0 / bit_rate)  # One bit period

        # Jitter measurements (variation at crossing points)
        if len(crossing_times) > 1:
            crossing_times_arr = np.array(crossing_times)
            rms_jitter = float(np.std(crossing_times_arr))
            pk_pk_jitter = float(np.max(crossing_times_arr) - np.min(crossing_times_arr))
        else:
            rms_jitter = 0.0
            pk_pk_jitter = 0.0

        # Noise measurements
        zero_noise = float(np.std(zero_level_data))
        one_noise = float(np.std(one_level_data))
        rms_noise = float((zero_noise + one_noise) / 2)

        # Q-factor
        if rms_noise > 0:
            q_factor = eye_height / (2 * rms_noise)
        else:
            q_factor = float("inf")

        # SNR
        if rms_noise > 0:
            snr = 20 * np.log10(eye_amplitude / (2 * rms_noise))
        else:
            snr = float("inf")

        # Eye opening percentage
        usable_height = eye_height - 6 * rms_noise  # 3-sigma margins
        eye_opening = float(max(0, min(100, (usable_height / eye_amplitude) * 100)))

        # Rise/fall times (estimate from averaged trace)
        avg_trace = np.mean(traces, axis=0)
        rise_indices = np.where(
            (avg_trace[:-1] < mid_voltage) & (avg_trace[1:] >= mid_voltage)
        )[0]

        if len(rise_indices) > 0:
            # Find 10% and 90% points
            rise_start_v = zero_level + 0.1 * (one_level - zero_level)
            rise_end_v = zero_level + 0.9 * (one_level - zero_level)

            # Simple estimation
            rise_time = float(eye_width * 0.1)  # Typical value
            fall_time = float(eye_width * 0.1)
        else:
            rise_time = 0.0
            fall_time = 0.0

        return EyeParameters(
            eye_height=eye_height,
            eye_width=eye_width,
            eye_amplitude=eye_amplitude,
            crossing_percent=crossing_percent,
            rms_jitter=rms_jitter,
            pk_pk_jitter=pk_pk_jitter,
            rms_noise=rms_noise,
            q_factor=float(q_factor),
            snr=float(snr),
            eye_opening=eye_opening,
            one_level=one_level,
            zero_level=zero_level,
            rise_time=rise_time,
            fall_time=fall_time,
        )

    # === Mask Testing Methods ===

    def add_mask_definition(self, mask: MaskDefinition) -> None:
        """Add a mask definition for testing.

        Args:
            mask: Mask definition
        """
        self.mask_definitions[mask.name] = mask

    def test_mask(
        self,
        equipment_id: str,
        channel: int,
        time_data: np.ndarray,
        voltage_data: np.ndarray,
        mask_name: str,
    ) -> MaskTestResult:
        """Test waveform against a mask.

        Args:
            equipment_id: Equipment identifier
            channel: Channel number
            time_data: Time array
            voltage_data: Voltage array
            mask_name: Name of mask to test against

        Returns:
            MaskTestResult with pass/fail and violation details
        """
        if mask_name not in self.mask_definitions:
            raise ValueError(f"Mask '{mask_name}' not found")

        mask = self.mask_definitions[mask_name]

        # Normalize coordinates if needed
        if mask.normalized:
            time_norm = (time_data - time_data[0]) / (time_data[-1] - time_data[0])
            voltage_norm = (voltage_data - np.min(voltage_data)) / (
                np.max(voltage_data) - np.min(voltage_data)
            )
        else:
            time_norm = time_data
            voltage_norm = voltage_data

        # Test each polygon
        failure_times = []
        failure_voltages = []
        region_failures: Dict[str, int] = {}

        for polygon in mask.polygons:
            # Extract polygon points
            poly_time = np.array([p.time for p in polygon.points])
            poly_voltage = np.array([p.voltage for p in polygon.points])

            # Test each waveform point
            failures = 0
            for t, v in zip(time_norm, voltage_norm):
                inside = self._point_in_polygon(t, v, poly_time, poly_voltage)

                # Check if this violates the mask
                if (inside and polygon.fail_inside) or (
                    not inside and not polygon.fail_inside
                ):
                    failures += 1
                    failure_times.append(float(t))
                    failure_voltages.append(float(v))

            region_failures[polygon.name] = failures

        # Calculate results
        total_samples = len(time_data)
        failed_samples = len(failure_times)
        failure_rate = failed_samples / total_samples if total_samples > 0 else 0.0
        passed = failed_samples == 0

        # Calculate margin (distance to nearest mask boundary)
        margins = []
        for t, v in zip(time_norm[:100], voltage_norm[:100]):  # Sample 100 points
            min_dist = float("inf")
            for polygon in mask.polygons:
                poly_time = np.array([p.time for p in polygon.points])
                poly_voltage = np.array([p.voltage for p in polygon.points])
                for i in range(len(polygon.points)):
                    p1_t, p1_v = poly_time[i], poly_voltage[i]
                    p2_t, p2_v = poly_time[(i + 1) % len(polygon.points)], poly_voltage[
                        (i + 1) % len(polygon.points)
                    ]
                    dist = self._point_to_segment_distance(t, v, p1_t, p1_v, p2_t, p2_v)
                    min_dist = min(min_dist, dist)
            margins.append(min_dist)

        min_margin = float(np.min(margins)) if margins else 0.0
        mean_margin = float(np.mean(margins)) if margins else 0.0

        return MaskTestResult(
            equipment_id=equipment_id,
            channel=channel,
            mask_name=mask_name,
            passed=passed,
            total_samples=total_samples,
            failed_samples=failed_samples,
            failure_rate=failure_rate,
            failure_times=failure_times,
            failure_voltages=failure_voltages,
            region_failures=region_failures,
            min_margin=min_margin,
            mean_margin=mean_margin,
        )

    def _point_in_polygon(
        self, x: float, y: float, poly_x: np.ndarray, poly_y: np.ndarray
    ) -> bool:
        """Check if point is inside polygon using ray casting algorithm."""
        n = len(poly_x)
        inside = False

        p1x, p1y = poly_x[0], poly_y[0]
        for i in range(1, n + 1):
            p2x, p2y = poly_x[i % n], poly_y[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y

        return inside

    def _point_to_segment_distance(
        self, px: float, py: float, x1: float, y1: float, x2: float, y2: float
    ) -> float:
        """Calculate minimum distance from point to line segment."""
        # Vector from segment start to point
        dx, dy = px - x1, py - y1
        # Vector of segment
        sx, sy = x2 - x1, y2 - y1

        # Project point onto segment
        seg_len_sq = sx * sx + sy * sy
        if seg_len_sq == 0:
            return np.sqrt(dx * dx + dy * dy)

        t = max(0, min(1, (dx * sx + dy * sy) / seg_len_sq))

        # Find closest point on segment
        closest_x = x1 + t * sx
        closest_y = y1 + t * sy

        # Distance to closest point
        return np.sqrt((px - closest_x) ** 2 + (py - closest_y) ** 2)

    # === Waveform Search Methods ===

    def search_events(
        self,
        equipment_id: str,
        channel: int,
        time_data: np.ndarray,
        voltage_data: np.ndarray,
        config: SearchConfig,
    ) -> SearchResult:
        """Search for specific events in waveform.

        Args:
            equipment_id: Equipment identifier
            channel: Channel number
            time_data: Time array
            voltage_data: Voltage array
            config: Search configuration

        Returns:
            SearchResult with found events
        """
        start_time = datetime.now()
        events: List[SearchEvent] = []

        if config.event_type == SearchEventType.EDGE_RISING:
            events = self._search_rising_edges(
                time_data, voltage_data, config.upper_threshold
            )

        elif config.event_type == SearchEventType.EDGE_FALLING:
            events = self._search_falling_edges(
                time_data, voltage_data, config.lower_threshold
            )

        elif config.event_type == SearchEventType.PULSE_POSITIVE:
            events = self._search_positive_pulses(
                time_data, voltage_data, config.upper_threshold, config.min_width, config.max_width
            )

        elif config.event_type == SearchEventType.PULSE_NEGATIVE:
            events = self._search_negative_pulses(
                time_data, voltage_data, config.lower_threshold, config.min_width, config.max_width
            )

        elif config.event_type == SearchEventType.RUNT:
            events = self._search_runts(
                time_data,
                voltage_data,
                config.upper_threshold,
                config.lower_threshold,
            )

        elif config.event_type == SearchEventType.GLITCH:
            events = self._search_glitches(
                time_data, voltage_data, config.max_width
            )

        else:
            raise ValueError(f"Unsupported event type: {config.event_type}")

        # Limit number of events
        events = events[: config.max_events]

        # Calculate statistics
        duration = (datetime.now() - start_time).total_seconds()
        total_events = len(events)

        if total_events > 1:
            event_times = [e.time for e in events]
            time_diffs = np.diff(event_times)
            mean_time_between = float(np.mean(time_diffs))
            event_rate = 1.0 / mean_time_between if mean_time_between > 0 else 0.0
        else:
            mean_time_between = None
            event_rate = None

        return SearchResult(
            equipment_id=equipment_id,
            channel=channel,
            event_type=config.event_type,
            events=events,
            total_events=total_events,
            search_duration=duration,
            mean_time_between_events=mean_time_between,
            event_rate=event_rate,
        )

    def _search_rising_edges(
        self, time_data: np.ndarray, voltage_data: np.ndarray, threshold: Optional[float]
    ) -> List[SearchEvent]:
        """Search for rising edges."""
        if threshold is None:
            threshold = (np.max(voltage_data) + np.min(voltage_data)) / 2

        crossings = np.where(
            (voltage_data[:-1] < threshold) & (voltage_data[1:] >= threshold)
        )[0]

        events = []
        for idx in crossings:
            events.append(
                SearchEvent(
                    event_type=SearchEventType.EDGE_RISING,
                    time=float(time_data[idx]),
                    index=int(idx),
                    amplitude=float(voltage_data[idx + 1] - voltage_data[idx]),
                )
            )
        return events

    def _search_falling_edges(
        self, time_data: np.ndarray, voltage_data: np.ndarray, threshold: Optional[float]
    ) -> List[SearchEvent]:
        """Search for falling edges."""
        if threshold is None:
            threshold = (np.max(voltage_data) + np.min(voltage_data)) / 2

        crossings = np.where(
            (voltage_data[:-1] > threshold) & (voltage_data[1:] <= threshold)
        )[0]

        events = []
        for idx in crossings:
            events.append(
                SearchEvent(
                    event_type=SearchEventType.EDGE_FALLING,
                    time=float(time_data[idx]),
                    index=int(idx),
                    amplitude=float(voltage_data[idx] - voltage_data[idx + 1]),
                )
            )
        return events

    def _search_positive_pulses(
        self,
        time_data: np.ndarray,
        voltage_data: np.ndarray,
        threshold: Optional[float],
        min_width: Optional[float],
        max_width: Optional[float],
    ) -> List[SearchEvent]:
        """Search for positive pulses."""
        if threshold is None:
            threshold = (np.max(voltage_data) + np.min(voltage_data)) / 2

        # Find rising and falling edges
        rising = np.where(
            (voltage_data[:-1] < threshold) & (voltage_data[1:] >= threshold)
        )[0]
        falling = np.where(
            (voltage_data[:-1] > threshold) & (voltage_data[1:] <= threshold)
        )[0]

        events = []
        for rise_idx in rising:
            # Find next falling edge
            fall_candidates = falling[falling > rise_idx]
            if len(fall_candidates) == 0:
                continue

            fall_idx = fall_candidates[0]
            width = time_data[fall_idx] - time_data[rise_idx]

            # Check width constraints
            if min_width is not None and width < min_width:
                continue
            if max_width is not None and width > max_width:
                continue

            amplitude = np.max(voltage_data[rise_idx:fall_idx])

            events.append(
                SearchEvent(
                    event_type=SearchEventType.PULSE_POSITIVE,
                    time=float(time_data[rise_idx]),
                    index=int(rise_idx),
                    amplitude=float(amplitude),
                    width=float(width),
                )
            )

        return events

    def _search_negative_pulses(
        self,
        time_data: np.ndarray,
        voltage_data: np.ndarray,
        threshold: Optional[float],
        min_width: Optional[float],
        max_width: Optional[float],
    ) -> List[SearchEvent]:
        """Search for negative pulses."""
        if threshold is None:
            threshold = (np.max(voltage_data) + np.min(voltage_data)) / 2

        # Find falling and rising edges
        falling = np.where(
            (voltage_data[:-1] > threshold) & (voltage_data[1:] <= threshold)
        )[0]
        rising = np.where(
            (voltage_data[:-1] < threshold) & (voltage_data[1:] >= threshold)
        )[0]

        events = []
        for fall_idx in falling:
            # Find next rising edge
            rise_candidates = rising[rising > fall_idx]
            if len(rise_candidates) == 0:
                continue

            rise_idx = rise_candidates[0]
            width = time_data[rise_idx] - time_data[fall_idx]

            # Check width constraints
            if min_width is not None and width < min_width:
                continue
            if max_width is not None and width > max_width:
                continue

            amplitude = np.min(voltage_data[fall_idx:rise_idx])

            events.append(
                SearchEvent(
                    event_type=SearchEventType.PULSE_NEGATIVE,
                    time=float(time_data[fall_idx]),
                    index=int(fall_idx),
                    amplitude=float(amplitude),
                    width=float(width),
                )
            )

        return events

    def _search_runts(
        self,
        time_data: np.ndarray,
        voltage_data: np.ndarray,
        upper_threshold: Optional[float],
        lower_threshold: Optional[float],
    ) -> List[SearchEvent]:
        """Search for runt pulses (pulses that don't cross both thresholds)."""
        if upper_threshold is None or lower_threshold is None:
            vmin, vmax = np.min(voltage_data), np.max(voltage_data)
            mid = (vmin + vmax) / 2
            upper_threshold = mid + (vmax - mid) * 0.5
            lower_threshold = mid - (mid - vmin) * 0.5

        mid_threshold = (upper_threshold + lower_threshold) / 2

        # Find edges at mid level
        rising = np.where(
            (voltage_data[:-1] < mid_threshold) & (voltage_data[1:] >= mid_threshold)
        )[0]
        falling = np.where(
            (voltage_data[:-1] > mid_threshold) & (voltage_data[1:] <= mid_threshold)
        )[0]

        events = []

        # Check positive runts
        for rise_idx in rising:
            fall_candidates = falling[falling > rise_idx]
            if len(fall_candidates) == 0:
                continue
            fall_idx = fall_candidates[0]

            # Check if pulse reaches upper threshold
            max_v = np.max(voltage_data[rise_idx:fall_idx])
            if max_v < upper_threshold:
                events.append(
                    SearchEvent(
                        event_type=SearchEventType.RUNT,
                        time=float(time_data[rise_idx]),
                        index=int(rise_idx),
                        amplitude=float(max_v),
                        width=float(time_data[fall_idx] - time_data[rise_idx]),
                        details={"runt_type": "positive"},
                    )
                )

        # Check negative runts
        for fall_idx in falling:
            rise_candidates = rising[rising > fall_idx]
            if len(rise_candidates) == 0:
                continue
            rise_idx = rise_candidates[0]

            # Check if pulse reaches lower threshold
            min_v = np.min(voltage_data[fall_idx:rise_idx])
            if min_v > lower_threshold:
                events.append(
                    SearchEvent(
                        event_type=SearchEventType.RUNT,
                        time=float(time_data[fall_idx]),
                        index=int(fall_idx),
                        amplitude=float(min_v),
                        width=float(time_data[rise_idx] - time_data[fall_idx]),
                        details={"runt_type": "negative"},
                    )
                )

        return events

    def _search_glitches(
        self,
        time_data: np.ndarray,
        voltage_data: np.ndarray,
        max_width: Optional[float],
    ) -> List[SearchEvent]:
        """Search for glitches (very narrow pulses)."""
        # Use derivative to find rapid changes
        derivative = np.diff(voltage_data)
        threshold = np.std(derivative) * 3  # 3-sigma threshold

        # Find significant spikes
        spikes = np.where(np.abs(derivative) > threshold)[0]

        events = []
        if max_width is None:
            max_width = (time_data[-1] - time_data[0]) / len(time_data) * 10

        i = 0
        while i < len(spikes):
            spike_idx = spikes[i]
            # Look for return to baseline
            j = i + 1
            while j < len(spikes) and spikes[j] - spikes[j - 1] <= 2:
                j += 1

            if j < len(spikes):
                end_idx = spikes[j - 1]
                width = time_data[end_idx] - time_data[spike_idx]

                if width <= max_width:
                    events.append(
                        SearchEvent(
                            event_type=SearchEventType.GLITCH,
                            time=float(time_data[spike_idx]),
                            index=int(spike_idx),
                            amplitude=float(np.abs(derivative[spike_idx])),
                            width=float(width),
                        )
                    )

            i = j

        return events

    # === Reference Waveform Methods ===

    def add_reference_waveform(self, reference: ReferenceWaveform) -> None:
        """Add a reference waveform.

        Args:
            reference: Reference waveform definition
        """
        self.reference_waveforms[reference.name] = reference

    def compare_to_reference(
        self,
        equipment_id: str,
        channel: int,
        time_data: np.ndarray,
        voltage_data: np.ndarray,
        reference_name: str,
    ) -> ComparisonResult:
        """Compare waveform to reference.

        Args:
            equipment_id: Equipment identifier
            channel: Channel number
            time_data: Time array
            voltage_data: Voltage array
            reference_name: Name of reference waveform

        Returns:
            ComparisonResult with comparison metrics
        """
        if reference_name not in self.reference_waveforms:
            raise ValueError(f"Reference '{reference_name}' not found")

        ref = self.reference_waveforms[reference_name]

        # Resample test waveform to match reference length
        ref_time = np.array(ref.time_data)
        ref_voltage = np.array(ref.voltage_data)

        # Interpolate test data to reference time points
        interp_func = interp1d(
            time_data, voltage_data, kind="linear", fill_value="extrapolate"
        )
        test_voltage = interp_func(ref_time)

        # Calculate voltage errors
        voltage_error = test_voltage - ref_voltage
        voltage_rms_error = float(np.sqrt(np.mean(voltage_error**2)))
        voltage_max_error = float(np.max(np.abs(voltage_error)))
        voltage_mean_error = float(np.mean(np.abs(voltage_error)))

        # Calculate correlation
        correlation = float(np.corrcoef(ref_voltage, test_voltage)[0, 1])

        # Find phase shift using cross-correlation
        cross_corr = signal.correlate(ref_voltage, test_voltage, mode="same")
        lag = np.argmax(cross_corr) - len(ref_voltage) // 2
        phase_shift = float(lag / ref.sample_rate)

        # Calculate similarity percentage
        max_deviation = np.max(ref_voltage) - np.min(ref_voltage)
        if max_deviation > 0:
            similarity = max(0, 100 * (1 - voltage_rms_error / max_deviation))
        else:
            similarity = 100.0

        # Check tolerances
        voltage_tolerance = ref.voltage_tolerance_percent / 100 * max_deviation
        failed_samples = np.sum(np.abs(voltage_error) > voltage_tolerance)

        # Find failure points
        failure_mask = np.abs(voltage_error) > voltage_tolerance
        failure_indices = np.where(failure_mask)[0]

        failure_times = [float(ref_time[i]) for i in failure_indices[:100]]  # Limit to 100
        failure_errors = [float(voltage_error[i]) for i in failure_indices[:100]]

        passed = failed_samples == 0

        return ComparisonResult(
            equipment_id=equipment_id,
            channel=channel,
            reference_name=reference_name,
            passed=passed,
            similarity_percent=float(similarity),
            voltage_rms_error=voltage_rms_error,
            voltage_max_error=voltage_max_error,
            voltage_mean_error=voltage_mean_error,
            correlation=correlation,
            phase_shift=phase_shift,
            failed_samples=int(failed_samples),
            failure_times=failure_times,
            failure_errors=failure_errors,
        )

    # === Parameter Trending Methods ===

    def update_trend(
        self,
        equipment_id: str,
        channel: int,
        parameter: TrendParameter,
        value: float,
    ) -> TrendData:
        """Update parameter trend with new measurement.

        Args:
            equipment_id: Equipment identifier
            channel: Channel number
            parameter: Parameter being trended
            value: New parameter value

        Returns:
            Updated TrendData
        """
        key = (equipment_id, channel, parameter)

        # Get or create trend data
        if key not in self.trend_data:
            self.trend_data[key] = TrendData(
                equipment_id=equipment_id,
                channel=channel,
                parameter=parameter,
                start_time=datetime.now(),
                last_update=datetime.now(),
                data_points=[],
                mean=value,
                std_dev=0.0,
                min_value=value,
                max_value=value,
                range=0.0,
                drift_rate=0.0,
                trend_direction="stable",
            )

        trend = self.trend_data[key]

        # Add new data point
        new_point = TrendDataPoint(
            timestamp=datetime.now(),
            value=value,
            sequence_number=len(trend.data_points),
        )
        trend.data_points.append(new_point)

        # Update statistics
        values = np.array([p.value for p in trend.data_points])
        trend.mean = float(np.mean(values))
        trend.std_dev = float(np.std(values))
        trend.min_value = float(np.min(values))
        trend.max_value = float(np.max(values))
        trend.range = trend.max_value - trend.min_value

        # Calculate drift rate (linear regression)
        if len(trend.data_points) >= 3:
            times = np.array(
                [(p.timestamp - trend.start_time).total_seconds() for p in trend.data_points]
            )
            slope, _ = np.polyfit(times, values, 1)
            trend.drift_rate = float(slope)

            # Determine trend direction
            if abs(slope) < trend.std_dev / (times[-1] - times[0]):
                trend.trend_direction = "stable"
            elif slope > 0:
                trend.trend_direction = "up"
            else:
                trend.trend_direction = "down"

        trend.last_update = datetime.now()

        return trend

    def get_trend_data(
        self, equipment_id: str, channel: int, parameter: TrendParameter
    ) -> Optional[TrendData]:
        """Get trend data for a parameter.

        Args:
            equipment_id: Equipment identifier
            channel: Channel number
            parameter: Parameter being trended

        Returns:
            TrendData or None if not found
        """
        key = (equipment_id, channel, parameter)
        return self.trend_data.get(key)
