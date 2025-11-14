"""Data resampling and interpolation module."""

import logging
from typing import Optional, Tuple

import numpy as np
from scipy import interpolate, signal

from .models import ResampleConfig, ResampleMethod

logger = logging.getLogger(__name__)


class DataResampler:
    """Data resampling and interpolation engine."""

    def __init__(self):
        """Initialize data resampler."""
        pass

    def resample(
        self,
        x_data: np.ndarray,
        y_data: np.ndarray,
        config: ResampleConfig,
        original_rate: Optional[float] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Resample data to new rate or number of points.

        Args:
            x_data: Input X values
            y_data: Input Y values
            config: Resampling configuration
            original_rate: Original sample rate (Hz)

        Returns:
            Tuple of (new_x, new_y)
        """
        if config.target_points:
            # Resample to specific number of points
            return self._resample_to_points(
                x_data, y_data, config.target_points, config.method
            )

        elif config.target_rate and original_rate:
            # Resample to specific rate
            return self._resample_to_rate(
                x_data, y_data, original_rate, config.target_rate, config
            )

        else:
            raise ValueError("Must specify either target_points or target_rate")

    def _resample_to_points(
        self,
        x_data: np.ndarray,
        y_data: np.ndarray,
        num_points: int,
        method: ResampleMethod,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Resample to specific number of points.

        Args:
            x_data: Input X values
            y_data: Input Y values
            num_points: Target number of points
            method: Interpolation method

        Returns:
            Tuple of (new_x, new_y)
        """
        # Create new X array
        new_x = np.linspace(x_data[0], x_data[-1], num_points)

        # Interpolate Y values
        if method == ResampleMethod.LINEAR:
            interp_func = interpolate.interp1d(x_data, y_data, kind="linear")
            new_y = interp_func(new_x)

        elif method == ResampleMethod.CUBIC:
            interp_func = interpolate.interp1d(x_data, y_data, kind="cubic")
            new_y = interp_func(new_x)

        elif method == ResampleMethod.NEAREST:
            interp_func = interpolate.interp1d(x_data, y_data, kind="nearest")
            new_y = interp_func(new_x)

        elif method == ResampleMethod.SPLINE:
            # Cubic spline interpolation
            tck = interpolate.splrep(x_data, y_data, s=0)
            new_y = interpolate.splev(new_x, tck)

        elif method == ResampleMethod.FOURIER:
            # FFT-based resampling
            new_y = signal.resample(y_data, num_points)

        else:
            raise ValueError(f"Unknown resampling method: {method}")

        return new_x, new_y

    def _resample_to_rate(
        self,
        x_data: np.ndarray,
        y_data: np.ndarray,
        original_rate: float,
        target_rate: float,
        config: ResampleConfig,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Resample to specific sample rate.

        Args:
            x_data: Input X values
            y_data: Input Y values
            original_rate: Original sample rate (Hz)
            target_rate: Target sample rate (Hz)
            config: Resampling configuration

        Returns:
            Tuple of (new_x, new_y)
        """
        # Calculate new number of points
        duration = x_data[-1] - x_data[0]
        num_points = int(duration * target_rate)

        # Downsample with anti-aliasing if needed
        if target_rate < original_rate and config.anti_alias:
            # Apply low-pass filter before downsampling
            from .filters import SignalFilter
            from .models import FilterConfig, FilterMethod, FilterType

            filter_config = FilterConfig(
                filter_type=FilterType.LOWPASS,
                filter_method=FilterMethod.BUTTERWORTH,
                cutoff_freq=target_rate / 2.5,  # Anti-aliasing cutoff
                order=6,
                sample_rate=original_rate,
            )

            signal_filter = SignalFilter()
            filtered_result = signal_filter.apply_filter(y_data, x_data, filter_config)
            y_data = np.array(filtered_result.filtered_data)

        # Resample to new number of points
        return self._resample_to_points(x_data, y_data, num_points, config.method)

    def interpolate_missing_points(
        self,
        x_data: np.ndarray,
        y_data: np.ndarray,
        method: ResampleMethod = ResampleMethod.LINEAR,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Interpolate missing (NaN) data points.

        Args:
            x_data: Input X values
            y_data: Input Y values (may contain NaN)
            method: Interpolation method

        Returns:
            Tuple of (x_data, interpolated_y)
        """
        # Find valid (non-NaN) points
        valid_mask = ~np.isnan(y_data)
        valid_x = x_data[valid_mask]
        valid_y = y_data[valid_mask]

        if len(valid_x) < 2:
            raise ValueError("Need at least 2 valid points for interpolation")

        # Interpolate
        if method == ResampleMethod.LINEAR:
            interp_func = interpolate.interp1d(
                valid_x, valid_y, kind="linear", fill_value="extrapolate"
            )
        elif method == ResampleMethod.CUBIC:
            interp_func = interpolate.interp1d(
                valid_x, valid_y, kind="cubic", fill_value="extrapolate"
            )
        elif method == ResampleMethod.NEAREST:
            interp_func = interpolate.interp1d(
                valid_x, valid_y, kind="nearest", fill_value="extrapolate"
            )
        elif method == ResampleMethod.SPLINE:
            tck = interpolate.splrep(valid_x, valid_y, s=0)
            interp_func = lambda x: interpolate.splev(x, tck)
        else:
            raise ValueError(
                f"Unsupported method for missing point interpolation: {method}"
            )

        # Interpolate all points
        interpolated_y = interp_func(x_data)

        return x_data, interpolated_y

    def decimate(self, data: np.ndarray, factor: int, ftype: str = "iir") -> np.ndarray:
        """Decimate signal by integer factor with anti-aliasing.

        Args:
            data: Input signal
            factor: Decimation factor
            ftype: Filter type ('iir' or 'fir')

        Returns:
            Decimated signal
        """
        decimated = signal.decimate(data, factor, ftype=ftype, zero_phase=True)

        return decimated

    def upsample(
        self, data: np.ndarray, factor: int, method: str = "linear"
    ) -> np.ndarray:
        """Upsample signal by integer factor.

        Args:
            data: Input signal
            factor: Upsampling factor
            method: Interpolation method

        Returns:
            Upsampled signal
        """
        # Create upsampled array with zeros
        upsampled_length = len(data) * factor
        upsampled = np.zeros(upsampled_length)

        # Insert original samples
        upsampled[::factor] = data

        # Interpolate
        if method == "linear":
            x_orig = np.arange(0, upsampled_length, factor)
            x_new = np.arange(upsampled_length)
            interp_func = interpolate.interp1d(x_orig, data, kind="linear")
            upsampled = interp_func(x_new)
        elif method == "cubic":
            x_orig = np.arange(0, upsampled_length, factor)
            x_new = np.arange(upsampled_length)
            interp_func = interpolate.interp1d(x_orig, data, kind="cubic")
            upsampled = interp_func(x_new)
        else:
            # Use FFT-based resampling
            upsampled = signal.resample(data, upsampled_length)

        return upsampled

    def align_signals(
        self,
        signal1: np.ndarray,
        signal2: np.ndarray,
        max_shift: Optional[int] = None,
    ) -> Tuple[int, np.ndarray, np.ndarray]:
        """Align two signals using cross-correlation.

        Args:
            signal1: First signal
            signal2: Second signal
            max_shift: Maximum shift to search (None = full range)

        Returns:
            Tuple of (shift, aligned_signal1, aligned_signal2)
        """
        # Compute cross-correlation
        correlation = signal.correlate(signal1, signal2, mode="full")

        # Find peak
        if max_shift:
            center = len(correlation) // 2
            start = max(0, center - max_shift)
            end = min(len(correlation), center + max_shift)
            peak_idx = start + np.argmax(correlation[start:end])
        else:
            peak_idx = np.argmax(correlation)

        # Calculate shift
        shift = peak_idx - (len(signal2) - 1)

        # Align signals
        if shift > 0:
            # signal2 is ahead, shift signal1 forward
            aligned_signal1 = np.pad(signal1, (shift, 0), mode="constant")[
                : len(signal1)
            ]
            aligned_signal2 = signal2
        elif shift < 0:
            # signal1 is ahead, shift signal2 forward
            aligned_signal1 = signal1
            aligned_signal2 = np.pad(signal2, (-shift, 0), mode="constant")[
                : len(signal2)
            ]
        else:
            aligned_signal1 = signal1
            aligned_signal2 = signal2

        return shift, aligned_signal1, aligned_signal2
