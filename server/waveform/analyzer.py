"""Waveform analysis engine for measurements and math operations."""

import numpy as np
import logging
from typing import List, Tuple, Optional, Dict
from scipy import signal, fft, integrate
from scipy.stats import skew, kurtosis

from .models import (
    ExtendedWaveformData,
    EnhancedMeasurements,
    CursorData,
    CursorType,
    MathChannelConfig,
    MathOperation,
    MathChannelResult,
    HistogramData,
)

logger = logging.getLogger(__name__)


class WaveformAnalyzer:
    """Advanced waveform analysis engine."""

    def __init__(self):
        """Initialize waveform analyzer."""
        pass

    def calculate_enhanced_measurements(
        self, waveform: ExtendedWaveformData
    ) -> EnhancedMeasurements:
        """Calculate comprehensive automatic measurements.

        Args:
            waveform: Extended waveform data with voltage/time arrays

        Returns:
            EnhancedMeasurements object with all available measurements
        """
        if not waveform.voltage_data or not waveform.time_data:
            raise ValueError("Waveform data is empty")

        voltage = np.array(waveform.voltage_data)
        time = np.array(waveform.time_data)

        measurements = EnhancedMeasurements(
            equipment_id=waveform.equipment_id,
            channel=waveform.channel,
            timestamp=waveform.timestamp,
        )

        try:
            # Voltage measurements
            measurements.vmax = float(np.max(voltage))
            measurements.vmin = float(np.min(voltage))
            measurements.vpp = measurements.vmax - measurements.vmin
            measurements.vavg = float(np.mean(voltage))
            measurements.vrms = float(np.sqrt(np.mean(voltage**2)))
            measurements.vac_rms = float(np.sqrt(np.mean((voltage - measurements.vavg)**2)))
            measurements.std_dev = float(np.std(voltage))
            measurements.variance = float(np.var(voltage))

            # Statistical measurements
            if len(voltage) > 1:
                measurements.skewness = float(skew(voltage))
                measurements.kurtosis = float(kurtosis(voltage))

            # Top, base, amplitude (for pulse signals)
            hist, edges = np.histogram(voltage, bins=100)
            # Top is the mode of upper half
            upper_half_idx = len(hist) // 2
            top_idx = upper_half_idx + np.argmax(hist[upper_half_idx:])
            measurements.vtop = float((edges[top_idx] + edges[top_idx + 1]) / 2)
            # Base is the mode of lower half
            base_idx = np.argmax(hist[:upper_half_idx])
            measurements.vbase = float((edges[base_idx] + edges[base_idx + 1]) / 2)

            measurements.vamp = measurements.vtop - measurements.vbase
            measurements.vmid = (measurements.vtop + measurements.vbase) / 2

            # Time measurements (if periodic signal)
            measurements.period, measurements.frequency = self._calculate_period_frequency(
                time, voltage
            )

            if measurements.frequency and measurements.frequency > 0:
                # Rise/fall time
                measurements.rise_time, measurements.fall_time = self._calculate_edge_times(
                    time, voltage, measurements.vbase, measurements.vtop
                )

                # Pulse widths
                measurements.positive_width, measurements.negative_width = self._calculate_pulse_widths(
                    time, voltage, measurements.vmid
                )

                # Duty cycle
                if measurements.period and measurements.positive_width:
                    measurements.duty_cycle = float(
                        (measurements.positive_width / measurements.period) * 100
                    )

                # Edge counts
                measurements.positive_edges = self._count_edges(voltage, measurements.vmid, rising=True)
                measurements.negative_edges = self._count_edges(voltage, measurements.vmid, rising=False)

                # Pulse count and rate
                measurements.pulse_count = measurements.positive_edges
                if measurements.period:
                    measurements.pulse_rate = measurements.frequency

            # Overshoot/preshoot
            if measurements.vtop and measurements.vbase:
                measurements.overshoot = self._calculate_overshoot(
                    voltage, measurements.vtop, measurements.vbase
                )
                measurements.preshoot = self._calculate_preshoot(
                    voltage, measurements.vtop, measurements.vbase
                )

            # Area measurements
            if len(time) > 1:
                measurements.area = float(np.trapz(voltage, time))
                if measurements.period:
                    # Find one cycle
                    cycle_samples = int(measurements.period / (time[1] - time[0]))
                    if cycle_samples < len(voltage):
                        measurements.cycle_area = float(
                            np.trapz(voltage[:cycle_samples], time[:cycle_samples])
                        )

            # Slew rate
            measurements.slew_rate_rising, measurements.slew_rate_falling = self._calculate_slew_rate(
                time, voltage, measurements.vbase, measurements.vtop
            )

            # Signal quality (if applicable)
            measurements.snr = self._calculate_snr(voltage, measurements.vavg)
            measurements.thd = self._calculate_thd(voltage, measurements.frequency, waveform.sample_rate)

        except Exception as e:
            logger.error(f"Error calculating enhanced measurements: {e}")

        return measurements

    def calculate_cursor_measurements(
        self,
        waveform: ExtendedWaveformData,
        cursor_type: CursorType,
        cursor1_pos: float,
        cursor2_pos: float,
    ) -> CursorData:
        """Calculate cursor measurements.

        Args:
            waveform: Waveform data
            cursor_type: Horizontal (time) or vertical (voltage)
            cursor1_pos: Position of cursor 1
            cursor2_pos: Position of cursor 2

        Returns:
            CursorData with measurements
        """
        voltage = np.array(waveform.voltage_data)
        time = np.array(waveform.time_data)

        cursor_data = CursorData(
            cursor_type=cursor_type,
            cursor1_position=cursor1_pos,
            cursor2_position=cursor2_pos,
            delta=abs(cursor2_pos - cursor1_pos),
        )

        if cursor_type == CursorType.HORIZONTAL:
            # Time cursors
            cursor_data.delta_time = cursor_data.delta
            if cursor_data.delta_time > 0:
                cursor_data.frequency = 1.0 / cursor_data.delta_time

            # Find voltage values at cursor times
            idx1 = np.argmin(np.abs(time - cursor1_pos))
            idx2 = np.argmin(np.abs(time - cursor2_pos))
            cursor_data.cursor1_value = float(voltage[idx1])
            cursor_data.cursor2_value = float(voltage[idx2])
            cursor_data.delta_voltage = abs(cursor_data.cursor2_value - cursor_data.cursor1_value)

        else:  # VERTICAL
            # Voltage cursors
            cursor_data.delta_voltage = cursor_data.delta

            # Find first time when voltage crosses each cursor
            crossings1 = np.where(np.diff(np.sign(voltage - cursor1_pos)))[0]
            crossings2 = np.where(np.diff(np.sign(voltage - cursor2_pos)))[0]

            if len(crossings1) > 0:
                cursor_data.cursor1_value = float(time[crossings1[0]])
            if len(crossings2) > 0:
                cursor_data.cursor2_value = float(time[crossings2[0]])

            if cursor_data.cursor1_value and cursor_data.cursor2_value:
                cursor_data.delta_time = abs(cursor_data.cursor2_value - cursor_data.cursor1_value)

        return cursor_data

    def apply_math_operation(
        self,
        config: MathChannelConfig,
        waveform1: ExtendedWaveformData,
        waveform2: Optional[ExtendedWaveformData] = None,
    ) -> MathChannelResult:
        """Apply math operation to waveform(s).

        Args:
            config: Math channel configuration
            waveform1: Primary waveform
            waveform2: Secondary waveform (for binary operations)

        Returns:
            MathChannelResult with result waveform
        """
        v1 = np.array(waveform1.voltage_data)
        t1 = np.array(waveform1.time_data)

        operation = config.operation
        source_channels = [waveform1.channel]

        # Binary operations
        if operation in [MathOperation.ADD, MathOperation.SUBTRACT,
                         MathOperation.MULTIPLY, MathOperation.DIVIDE]:
            if waveform2 is None:
                raise ValueError(f"Operation {operation} requires two waveforms")

            v2 = np.array(waveform2.voltage_data)
            source_channels.append(waveform2.channel)

            # Ensure same length (interpolate if needed)
            if len(v1) != len(v2):
                min_len = min(len(v1), len(v2))
                v1 = v1[:min_len]
                v2 = v2[:min_len]
                t1 = t1[:min_len]

            if operation == MathOperation.ADD:
                result = v1 + v2
            elif operation == MathOperation.SUBTRACT:
                result = v1 - v2
            elif operation == MathOperation.MULTIPLY:
                result = v1 * v2
            elif operation == MathOperation.DIVIDE:
                result = np.divide(v1, v2, where=v2 != 0, out=np.zeros_like(v1))

        # Unary operations
        elif operation == MathOperation.INVERT:
            result = -v1

        elif operation == MathOperation.ABS:
            result = np.abs(v1)

        elif operation == MathOperation.SQRT:
            result = np.sqrt(np.abs(v1))

        elif operation == MathOperation.SQUARE:
            result = v1**2

        elif operation == MathOperation.LOG:
            result = np.log(np.abs(v1) + 1e-12)  # Avoid log(0)

        elif operation == MathOperation.EXP:
            result = np.exp(v1)

        elif operation == MathOperation.INTEGRATE:
            dt = t1[1] - t1[0] if len(t1) > 1 else 1.0
            result = integrate.cumtrapz(v1, t1, initial=0)

        elif operation == MathOperation.DIFFERENTIATE:
            dt = t1[1] - t1[0] if len(t1) > 1 else 1.0
            result = np.gradient(v1, t1)

        elif operation == MathOperation.FFT:
            return self._calculate_fft(waveform1, config)

        elif operation == MathOperation.AVERAGE:
            # Simple moving average (in practice, would accumulate multiple acquisitions)
            window = config.average_count or 10
            result = np.convolve(v1, np.ones(window) / window, mode='same')

        elif operation == MathOperation.ENVELOPE:
            # Signal envelope using Hilbert transform
            analytic_signal = signal.hilbert(v1)
            result = np.abs(analytic_signal)

        else:
            raise ValueError(f"Unknown operation: {operation}")

        # Apply scale and offset
        result = result * config.scale + config.offset

        return MathChannelResult(
            equipment_id=waveform1.equipment_id,
            operation=operation,
            source_channels=source_channels,
            result_data=result.tolist(),
            time_data=t1.tolist(),
            sample_rate=waveform1.sample_rate,
        )

    def calculate_histogram(
        self,
        waveform: ExtendedWaveformData,
        histogram_type: str = "voltage",
        num_bins: int = 100,
    ) -> HistogramData:
        """Calculate histogram for voltage or time distribution.

        Args:
            waveform: Waveform data
            histogram_type: 'voltage' or 'time'
            num_bins: Number of histogram bins

        Returns:
            HistogramData with distribution statistics
        """
        if histogram_type == "voltage":
            data = np.array(waveform.voltage_data)
        else:
            data = np.array(waveform.time_data)

        counts, edges = np.histogram(data, bins=num_bins)

        hist_data = HistogramData(
            histogram_type=histogram_type,
            bins=edges.tolist(),
            counts=counts.tolist(),
            total_samples=len(data),
            mean=float(np.mean(data)),
            std_dev=float(np.std(data)),
            min_value=float(np.min(data)),
            max_value=float(np.max(data)),
            median=float(np.median(data)),
        )

        # Mode (most common bin)
        mode_idx = np.argmax(counts)
        hist_data.mode = float((edges[mode_idx] + edges[mode_idx + 1]) / 2)

        # Distribution shape
        if len(data) > 2:
            hist_data.skewness = float(skew(data))
            hist_data.kurtosis = float(kurtosis(data))

        return hist_data

    # Helper methods
    def _calculate_period_frequency(
        self, time: np.ndarray, voltage: np.ndarray
    ) -> Tuple[Optional[float], Optional[float]]:
        """Calculate period and frequency using autocorrelation."""
        try:
            # Remove DC component
            voltage_ac = voltage - np.mean(voltage)

            # Autocorrelation
            corr = np.correlate(voltage_ac, voltage_ac, mode='full')
            corr = corr[len(corr) // 2:]

            # Find peaks in autocorrelation
            peaks, _ = signal.find_peaks(corr, height=np.max(corr) * 0.5)

            if len(peaks) > 1:
                # Period is time between first two peaks
                dt = time[1] - time[0] if len(time) > 1 else 1e-9
                period = float((peaks[1] - peaks[0]) * dt)
                frequency = 1.0 / period if period > 0 else None
                return period, frequency

        except Exception as e:
            logger.debug(f"Could not calculate period/frequency: {e}")

        return None, None

    def _calculate_edge_times(
        self, time: np.ndarray, voltage: np.ndarray, vbase: float, vtop: float
    ) -> Tuple[Optional[float], Optional[float]]:
        """Calculate rise and fall times (10%-90%)."""
        try:
            v10 = vbase + 0.1 * (vtop - vbase)
            v90 = vbase + 0.9 * (vtop - vbase)

            # Find rising edge
            rising_edges = np.where((voltage[:-1] < v10) & (voltage[1:] > v10))[0]
            if len(rising_edges) > 0:
                start_idx = rising_edges[0]
                # Find when it reaches 90%
                reach_90 = np.where(voltage[start_idx:] > v90)[0]
                if len(reach_90) > 0:
                    end_idx = start_idx + reach_90[0]
                    rise_time = float(time[end_idx] - time[start_idx])
                else:
                    rise_time = None
            else:
                rise_time = None

            # Find falling edge
            falling_edges = np.where((voltage[:-1] > v90) & (voltage[1:] < v90))[0]
            if len(falling_edges) > 0:
                start_idx = falling_edges[0]
                # Find when it reaches 10%
                reach_10 = np.where(voltage[start_idx:] < v10)[0]
                if len(reach_10) > 0:
                    end_idx = start_idx + reach_10[0]
                    fall_time = float(time[end_idx] - time[start_idx])
                else:
                    fall_time = None
            else:
                fall_time = None

            return rise_time, fall_time

        except Exception as e:
            logger.debug(f"Could not calculate edge times: {e}")
            return None, None

    def _calculate_pulse_widths(
        self, time: np.ndarray, voltage: np.ndarray, vmid: float
    ) -> Tuple[Optional[float], Optional[float]]:
        """Calculate positive and negative pulse widths."""
        try:
            # Positive pulse width (above vmid)
            above = voltage > vmid
            transitions = np.diff(above.astype(int))
            rising = np.where(transitions == 1)[0]
            falling = np.where(transitions == -1)[0]

            if len(rising) > 0 and len(falling) > 0:
                # Match each rising edge with next falling edge
                if rising[0] < falling[0]:
                    pos_width = float(time[falling[0]] - time[rising[0]])
                else:
                    pos_width = None
            else:
                pos_width = None

            # Negative pulse width (below vmid)
            if len(falling) > 0 and len(rising) > 0:
                if falling[0] < rising[0]:
                    neg_width = float(time[rising[0]] - time[falling[0]])
                elif len(rising) > 1:
                    neg_width = float(time[rising[1]] - time[falling[0]])
                else:
                    neg_width = None
            else:
                neg_width = None

            return pos_width, neg_width

        except Exception as e:
            logger.debug(f"Could not calculate pulse widths: {e}")
            return None, None

    def _count_edges(self, voltage: np.ndarray, threshold: float, rising: bool = True) -> int:
        """Count rising or falling edges."""
        try:
            if rising:
                edges = np.where((voltage[:-1] < threshold) & (voltage[1:] >= threshold))[0]
            else:
                edges = np.where((voltage[:-1] > threshold) & (voltage[1:] <= threshold))[0]
            return len(edges)
        except Exception:
            return 0

    def _calculate_overshoot(
        self, voltage: np.ndarray, vtop: float, vbase: float
    ) -> Optional[float]:
        """Calculate overshoot percentage."""
        try:
            vamp = vtop - vbase
            if vamp == 0:
                return None

            # Find maximum value after rising edge
            overshoot_v = np.max(voltage) - vtop
            if overshoot_v > 0:
                return float((overshoot_v / vamp) * 100)
            return 0.0

        except Exception:
            return None

    def _calculate_preshoot(
        self, voltage: np.ndarray, vtop: float, vbase: float
    ) -> Optional[float]:
        """Calculate preshoot percentage."""
        try:
            vamp = vtop - vbase
            if vamp == 0:
                return None

            # Find minimum value before rising edge (simplified)
            preshoot_v = vbase - np.min(voltage)
            if preshoot_v > 0:
                return float((preshoot_v / vamp) * 100)
            return 0.0

        except Exception:
            return None

    def _calculate_slew_rate(
        self, time: np.ndarray, voltage: np.ndarray, vbase: float, vtop: float
    ) -> Tuple[Optional[float], Optional[float]]:
        """Calculate slew rate on rising and falling edges."""
        try:
            # Find 20%-80% points for more accurate slew rate
            v20 = vbase + 0.2 * (vtop - vbase)
            v80 = vbase + 0.8 * (vtop - vbase)

            # Rising slew rate
            rising_20 = np.where((voltage[:-1] < v20) & (voltage[1:] >= v20))[0]
            rising_80 = np.where((voltage[:-1] < v80) & (voltage[1:] >= v80))[0]

            if len(rising_20) > 0 and len(rising_80) > 0:
                if rising_80[0] > rising_20[0]:
                    dt = time[rising_80[0]] - time[rising_20[0]]
                    dv = v80 - v20
                    rising_slew = float(dv / dt) if dt > 0 else None
                else:
                    rising_slew = None
            else:
                rising_slew = None

            # Falling slew rate
            falling_80 = np.where((voltage[:-1] > v80) & (voltage[1:] <= v80))[0]
            falling_20 = np.where((voltage[:-1] > v20) & (voltage[1:] <= v20))[0]

            if len(falling_80) > 0 and len(falling_20) > 0:
                if falling_20[0] > falling_80[0]:
                    dt = time[falling_20[0]] - time[falling_80[0]]
                    dv = v80 - v20
                    falling_slew = float(dv / dt) if dt > 0 else None
                else:
                    falling_slew = None
            else:
                falling_slew = None

            return rising_slew, falling_slew

        except Exception:
            return None, None

    def _calculate_snr(self, voltage: np.ndarray, signal_level: float) -> Optional[float]:
        """Calculate signal-to-noise ratio."""
        try:
            signal_power = signal_level**2
            noise = voltage - signal_level
            noise_power = np.mean(noise**2)

            if noise_power > 0:
                snr = 10 * np.log10(signal_power / noise_power)
                return float(snr)
        except Exception:
            pass
        return None

    def _calculate_thd(
        self, voltage: np.ndarray, fundamental_freq: Optional[float], sample_rate: float
    ) -> Optional[float]:
        """Calculate total harmonic distortion."""
        if fundamental_freq is None or fundamental_freq <= 0:
            return None

        try:
            # Perform FFT
            fft_result = fft.fft(voltage)
            freqs = fft.fftfreq(len(voltage), 1 / sample_rate)

            # Get magnitude spectrum (positive frequencies only)
            positive_freqs = freqs > 0
            freqs = freqs[positive_freqs]
            magnitude = np.abs(fft_result[positive_freqs])

            # Find fundamental and harmonics
            fundamental_idx = np.argmin(np.abs(freqs - fundamental_freq))
            fundamental_power = magnitude[fundamental_idx]**2

            # Sum harmonics (2nd through 5th)
            harmonics_power = 0
            for n in range(2, 6):
                harmonic_freq = n * fundamental_freq
                if harmonic_freq < sample_rate / 2:
                    harmonic_idx = np.argmin(np.abs(freqs - harmonic_freq))
                    harmonics_power += magnitude[harmonic_idx]**2

            if fundamental_power > 0:
                thd = 100 * np.sqrt(harmonics_power / fundamental_power)
                return float(thd)

        except Exception as e:
            logger.debug(f"Could not calculate THD: {e}")

        return None

    def _calculate_fft(
        self, waveform: ExtendedWaveformData, config: MathChannelConfig
    ) -> MathChannelResult:
        """Calculate FFT of waveform."""
        voltage = np.array(waveform.voltage_data)
        time = np.array(waveform.time_data)

        # Apply window
        window_name = config.fft_window or "hann"
        if window_name != "none":
            window = signal.get_window(window_name, len(voltage))
            voltage = voltage * window

        # Perform FFT
        fft_result = fft.fft(voltage)
        freqs = fft.fftfreq(len(voltage), 1 / waveform.sample_rate)

        # Get positive frequencies only
        positive_idx = freqs >= 0
        freqs = freqs[positive_idx]
        fft_result = fft_result[positive_idx]

        magnitude = np.abs(fft_result)
        phase = np.angle(fft_result, deg=True)

        # Select output mode
        mode = config.fft_mode or "magnitude"
        if mode == "magnitude":
            result_data = magnitude
        elif mode == "phase":
            result_data = phase
        elif mode == "real":
            result_data = np.real(fft_result)
        elif mode == "imag":
            result_data = np.imag(fft_result)
        else:
            result_data = magnitude

        return MathChannelResult(
            equipment_id=waveform.equipment_id,
            operation=MathOperation.FFT,
            source_channels=[waveform.channel],
            result_data=result_data.tolist(),
            time_data=freqs.tolist(),  # Frequency data
            sample_rate=waveform.sample_rate,
            frequency_data=freqs.tolist(),
            magnitude_data=magnitude.tolist(),
            phase_data=phase.tolist(),
        )
