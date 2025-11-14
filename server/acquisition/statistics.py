"""Advanced statistical analysis for acquisition data."""

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import fft, signal


class TrendType(str, Enum):
    """Trend detection types."""

    RISING = "rising"
    FALLING = "falling"
    STABLE = "stable"
    NOISY = "noisy"
    UNKNOWN = "unknown"


@dataclass
class RollingStats:
    """Rolling statistical metrics."""

    mean: float
    std: float
    min: float
    max: float
    median: float
    rms: float
    peak_to_peak: float
    num_samples: int


@dataclass
class FrequencyAnalysis:
    """Frequency domain analysis results."""

    frequencies: np.ndarray
    magnitudes: np.ndarray
    phases: np.ndarray
    dominant_frequency: float
    fundamental_amplitude: float
    thd: float  # Total Harmonic Distortion
    snr: float  # Signal-to-Noise Ratio


@dataclass
class TrendAnalysis:
    """Trend detection results."""

    trend: TrendType
    slope: float
    r_squared: float  # Goodness of fit
    confidence: float  # 0.0 to 1.0


@dataclass
class DataQuality:
    """Data quality metrics."""

    noise_level: float
    stability_score: float  # 0.0 (unstable) to 1.0 (stable)
    outlier_count: int
    missing_count: int
    valid_percentage: float


@dataclass
class PeakInfo:
    """Peak detection information."""

    indices: np.ndarray
    values: np.ndarray
    count: int


class StatisticsEngine:
    """Engine for computing advanced statistics on acquisition data."""

    def __init__(self, window_size: int = 1000):
        """
        Initialize statistics engine.

        Args:
            window_size: Number of samples for rolling calculations
        """
        self.window_size = window_size
        self._data_buffer = deque(maxlen=window_size)

    def compute_rolling_stats(self, data: np.ndarray) -> RollingStats:
        """
        Compute rolling statistics over a data window.

        Args:
            data: 1D array of measurements

        Returns:
            RollingStats object with computed metrics
        """
        if len(data) == 0:
            return RollingStats(
                mean=0.0,
                std=0.0,
                min=0.0,
                max=0.0,
                median=0.0,
                rms=0.0,
                peak_to_peak=0.0,
                num_samples=0,
            )

        return RollingStats(
            mean=float(np.mean(data)),
            std=float(np.std(data)),
            min=float(np.min(data)),
            max=float(np.max(data)),
            median=float(np.median(data)),
            rms=float(np.sqrt(np.mean(data**2))),
            peak_to_peak=float(np.ptp(data)),
            num_samples=len(data),
        )

    def compute_fft(
        self, data: np.ndarray, sample_rate: float, window: str = "hann"
    ) -> FrequencyAnalysis:
        """
        Perform FFT analysis on time-domain data.

        Args:
            data: 1D array of measurements
            sample_rate: Sampling rate in Hz
            window: Window function to apply ('hann', 'hamming', 'blackman', etc.)

        Returns:
            FrequencyAnalysis object with frequency domain metrics
        """
        if len(data) < 4:
            # Not enough data for meaningful FFT
            return FrequencyAnalysis(
                frequencies=np.array([]),
                magnitudes=np.array([]),
                phases=np.array([]),
                dominant_frequency=0.0,
                fundamental_amplitude=0.0,
                thd=0.0,
                snr=0.0,
            )

        # Apply window function
        if window == "hann":
            windowed_data = data * np.hanning(len(data))
        elif window == "hamming":
            windowed_data = data * np.hamming(len(data))
        elif window == "blackman":
            windowed_data = data * np.blackman(len(data))
        else:
            windowed_data = data

        # Compute FFT
        fft_result = fft.fft(windowed_data)
        n = len(fft_result)

        # Only use positive frequencies
        frequencies = fft.fftfreq(n, 1.0 / sample_rate)[: n // 2]
        magnitudes = np.abs(fft_result)[: n // 2] * (2.0 / n)
        phases = np.angle(fft_result)[: n // 2]

        # Find dominant frequency
        if len(magnitudes) > 0:
            dominant_idx = np.argmax(magnitudes)
            dominant_freq = frequencies[dominant_idx]
            fundamental_amp = magnitudes[dominant_idx]
        else:
            dominant_freq = 0.0
            fundamental_amp = 0.0

        # Compute THD (Total Harmonic Distortion)
        thd = self._compute_thd(magnitudes, dominant_idx if len(magnitudes) > 0 else 0)

        # Compute SNR (Signal-to-Noise Ratio)
        snr = self._compute_snr(magnitudes, dominant_idx if len(magnitudes) > 0 else 0)

        return FrequencyAnalysis(
            frequencies=frequencies,
            magnitudes=magnitudes,
            phases=phases,
            dominant_frequency=float(dominant_freq),
            fundamental_amplitude=float(fundamental_amp),
            thd=float(thd),
            snr=float(snr),
        )

    def detect_trend(
        self, data: np.ndarray, timestamps: Optional[np.ndarray] = None
    ) -> TrendAnalysis:
        """
        Detect trend in time-series data.

        Args:
            data: 1D array of measurements
            timestamps: Optional timestamps for each data point

        Returns:
            TrendAnalysis object with trend information
        """
        if len(data) < 3:
            return TrendAnalysis(
                trend=TrendType.UNKNOWN, slope=0.0, r_squared=0.0, confidence=0.0
            )

        # Use indices as x-values if no timestamps provided
        if timestamps is None:
            x = np.arange(len(data))
        else:
            x = timestamps

        # Fit linear regression
        coeffs = np.polyfit(x, data, 1)
        slope = coeffs[0]

        # Compute R-squared
        y_pred = np.polyval(coeffs, x)
        ss_res = np.sum((data - y_pred) ** 2)
        ss_tot = np.sum((data - np.mean(data)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0.0

        # Determine trend type
        std_dev = np.std(data)
        mean_val = np.mean(data)

        # Normalized slope (per sample)
        if mean_val != 0:
            normalized_slope = abs(slope) / abs(mean_val)
        else:
            normalized_slope = abs(slope)

        # Classification thresholds
        noise_threshold = 0.1
        trend_threshold = 0.001

        if r_squared < 0.5:
            # Poor fit, likely noisy
            trend_type = TrendType.NOISY
            confidence = 1.0 - r_squared
        elif normalized_slope < trend_threshold:
            # Stable signal
            trend_type = TrendType.STABLE
            confidence = r_squared
        elif slope > 0:
            # Rising trend
            trend_type = TrendType.RISING
            confidence = r_squared
        else:
            # Falling trend
            trend_type = TrendType.FALLING
            confidence = r_squared

        return TrendAnalysis(
            trend=trend_type,
            slope=float(slope),
            r_squared=float(r_squared),
            confidence=float(confidence),
        )

    def assess_data_quality(
        self, data: np.ndarray, outlier_threshold: float = 3.0
    ) -> DataQuality:
        """
        Assess the quality of acquired data.

        Args:
            data: 1D array of measurements
            outlier_threshold: Number of std deviations for outlier detection

        Returns:
            DataQuality object with quality metrics
        """
        if len(data) == 0:
            return DataQuality(
                noise_level=0.0,
                stability_score=0.0,
                outlier_count=0,
                missing_count=0,
                valid_percentage=0.0,
            )

        # Check for missing/invalid data (NaN or Inf)
        valid_mask = np.isfinite(data)
        valid_data = data[valid_mask]
        missing_count = len(data) - len(valid_data)

        if len(valid_data) == 0:
            return DataQuality(
                noise_level=0.0,
                stability_score=0.0,
                outlier_count=0,
                missing_count=missing_count,
                valid_percentage=0.0,
            )

        # Compute noise level (normalized std deviation)
        mean_val = np.mean(valid_data)
        std_val = np.std(valid_data)

        if mean_val != 0:
            noise_level = std_val / abs(mean_val)
        else:
            noise_level = std_val

        # Detect outliers using z-score method
        if std_val > 0:
            z_scores = np.abs((valid_data - mean_val) / std_val)
            outlier_count = np.sum(z_scores > outlier_threshold)
        else:
            outlier_count = 0

        # Compute stability score (inverse of coefficient of variation)
        if noise_level > 0:
            stability_score = min(1.0, 1.0 / (1.0 + noise_level))
        else:
            stability_score = 1.0

        # Valid data percentage
        valid_percentage = (len(valid_data) / len(data)) * 100.0

        return DataQuality(
            noise_level=float(noise_level),
            stability_score=float(stability_score),
            outlier_count=int(outlier_count),
            missing_count=int(missing_count),
            valid_percentage=float(valid_percentage),
        )

    def detect_peaks(
        self,
        data: np.ndarray,
        prominence: Optional[float] = None,
        distance: Optional[int] = None,
        height: Optional[float] = None,
    ) -> PeakInfo:
        """
        Detect peaks in signal data.

        Args:
            data: 1D array of measurements
            prominence: Required prominence of peaks
            distance: Minimum distance between peaks (in samples)
            height: Minimum height of peaks

        Returns:
            PeakInfo object with peak locations and values
        """
        if len(data) < 3:
            return PeakInfo(indices=np.array([]), values=np.array([]), count=0)

        # Use scipy's find_peaks with specified parameters
        peak_indices, _ = signal.find_peaks(
            data, prominence=prominence, distance=distance, height=height
        )

        peak_values = data[peak_indices]

        return PeakInfo(
            indices=peak_indices, values=peak_values, count=len(peak_indices)
        )

    def detect_threshold_crossings(
        self, data: np.ndarray, threshold: float, direction: str = "both"
    ) -> Dict[str, np.ndarray]:
        """
        Detect threshold crossings in data.

        Args:
            data: 1D array of measurements
            threshold: Threshold value
            direction: 'rising', 'falling', or 'both'

        Returns:
            Dictionary with 'rising' and/or 'falling' indices
        """
        if len(data) < 2:
            return {"rising": np.array([]), "falling": np.array([])}

        # Find crossings by comparing consecutive points
        above = data > threshold

        # Rising crossings: goes from below to above
        rising = np.where(np.diff(above.astype(int)) > 0)[0]

        # Falling crossings: goes from above to below
        falling = np.where(np.diff(above.astype(int)) < 0)[0]

        if direction == "rising":
            return {"rising": rising, "falling": np.array([])}
        elif direction == "falling":
            return {"rising": np.array([]), "falling": falling}
        else:
            return {"rising": rising, "falling": falling}

    def compute_histogram(
        self, data: np.ndarray, bins: int = 50
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute histogram of data values.

        Args:
            data: 1D array of measurements
            bins: Number of histogram bins

        Returns:
            Tuple of (bin_edges, counts)
        """
        if len(data) == 0:
            return np.array([]), np.array([])

        counts, bin_edges = np.histogram(data, bins=bins)
        return bin_edges, counts

    def _compute_thd(self, magnitudes: np.ndarray, fundamental_idx: int) -> float:
        """Compute Total Harmonic Distortion."""
        if len(magnitudes) == 0 or fundamental_idx >= len(magnitudes):
            return 0.0

        fundamental = magnitudes[fundamental_idx]
        if fundamental == 0:
            return 0.0

        # Sum power of harmonics (2f, 3f, 4f, ...)
        harmonic_power = 0.0
        for n in range(2, 10):  # Up to 9th harmonic
            harmonic_idx = n * fundamental_idx
            if harmonic_idx < len(magnitudes):
                harmonic_power += magnitudes[harmonic_idx] ** 2

        thd = np.sqrt(harmonic_power) / fundamental
        return float(thd * 100.0)  # Return as percentage

    def _compute_snr(
        self, magnitudes: np.ndarray, signal_idx: int, bandwidth: int = 5
    ) -> float:
        """Compute Signal-to-Noise Ratio."""
        if len(magnitudes) == 0 or signal_idx >= len(magnitudes):
            return 0.0

        # Signal power (around the peak)
        start_idx = max(0, signal_idx - bandwidth)
        end_idx = min(len(magnitudes), signal_idx + bandwidth + 1)
        signal_power = np.sum(magnitudes[start_idx:end_idx] ** 2)

        # Noise power (everything else)
        noise_mask = np.ones(len(magnitudes), dtype=bool)
        noise_mask[start_idx:end_idx] = False
        noise_power = np.sum(magnitudes[noise_mask] ** 2)

        if noise_power == 0:
            return float("inf")

        snr = 10 * np.log10(signal_power / noise_power)
        return float(snr)


# Global statistics engine instance
stats_engine = StatisticsEngine()
