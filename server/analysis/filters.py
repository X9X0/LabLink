"""Signal filtering module using scipy.signal."""

import logging
from typing import Optional, Tuple

import numpy as np
from scipy import signal

from .models import FilterConfig, FilterMethod, FilterResult, FilterType

logger = logging.getLogger(__name__)


class SignalFilter:
    """Signal filtering engine."""

    def __init__(self):
        """Initialize signal filter."""
        pass

    def apply_filter(
        self, data: np.ndarray, time: np.ndarray, config: FilterConfig
    ) -> FilterResult:
        """Apply digital filter to data.

        Args:
            data: Input signal data
            time: Time array
            config: Filter configuration

        Returns:
            FilterResult with filtered data
        """
        # Design filter
        b, a = self._design_filter(config)

        # Apply filter using filtfilt for zero-phase filtering
        filtered_data = signal.filtfilt(b, a, data)

        return FilterResult(
            filtered_data=filtered_data.tolist(),
            time_data=time.tolist(),
            config=config,
        )

    def _design_filter(self, config: FilterConfig) -> Tuple[np.ndarray, np.ndarray]:
        """Design digital filter based on configuration.

        Args:
            config: Filter configuration

        Returns:
            Tuple of (b, a) filter coefficients
        """
        # Normalize frequencies to Nyquist frequency
        nyquist = config.sample_rate / 2.0

        if config.filter_type in [FilterType.LOWPASS, FilterType.HIGHPASS]:
            if not config.cutoff_freq:
                raise ValueError(f"{config.filter_type} requires cutoff_freq")

            wn = config.cutoff_freq / nyquist

        elif config.filter_type in [FilterType.BANDPASS, FilterType.BANDSTOP]:
            if not config.cutoff_low or not config.cutoff_high:
                raise ValueError(
                    f"{config.filter_type} requires cutoff_low and cutoff_high"
                )

            wn = [config.cutoff_low / nyquist, config.cutoff_high / nyquist]

        else:
            raise ValueError(f"Unknown filter type: {config.filter_type}")

        # Design filter based on method
        if config.filter_method == FilterMethod.BUTTERWORTH:
            b, a = signal.butter(
                config.order, wn, btype=config.filter_type.value, analog=False
            )

        elif config.filter_method == FilterMethod.CHEBYSHEV1:
            ripple = config.ripple_db or 0.5  # Default 0.5 dB ripple
            b, a = signal.cheby1(
                config.order, ripple, wn, btype=config.filter_type.value, analog=False
            )

        elif config.filter_method == FilterMethod.CHEBYSHEV2:
            attenuation = config.attenuation_db or 40  # Default 40 dB attenuation
            b, a = signal.cheby2(
                config.order,
                attenuation,
                wn,
                btype=config.filter_type.value,
                analog=False,
            )

        elif config.filter_method == FilterMethod.BESSEL:
            b, a = signal.bessel(
                config.order,
                wn,
                btype=config.filter_type.value,
                analog=False,
                norm="phase",
            )

        elif config.filter_method == FilterMethod.ELLIPTIC:
            ripple = config.ripple_db or 0.5
            attenuation = config.attenuation_db or 40
            b, a = signal.ellip(
                config.order,
                ripple,
                attenuation,
                wn,
                btype=config.filter_type.value,
                analog=False,
            )

        elif config.filter_method == FilterMethod.FIR:
            # Design FIR filter using window method
            numtaps = config.order * 2 + 1  # FIR filter length
            b = signal.firwin(
                numtaps, wn, pass_zero=(config.filter_type.value == "lowpass")
            )
            a = np.array([1.0])  # FIR filters have a=1

        else:
            raise ValueError(f"Unknown filter method: {config.filter_method}")

        return b, a

    def get_frequency_response(
        self, config: FilterConfig, num_points: int = 1000
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Get frequency response of filter.

        Args:
            config: Filter configuration
            num_points: Number of frequency points

        Returns:
            Tuple of (frequencies, magnitude_db)
        """
        b, a = self._design_filter(config)

        # Calculate frequency response
        w, h = signal.freqz(b, a, worN=num_points, fs=config.sample_rate)

        # Convert to magnitude in dB
        magnitude_db = 20 * np.log10(np.abs(h) + 1e-12)

        return w, magnitude_db

    def design_notch_filter(
        self, frequency: float, quality_factor: float, sample_rate: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Design a notch (band-stop) filter for a specific frequency.

        Args:
            frequency: Frequency to notch out (Hz)
            quality_factor: Q factor (higher = narrower notch)
            sample_rate: Sample rate (Hz)

        Returns:
            Tuple of (b, a) filter coefficients
        """
        # Design notch filter
        b, a = signal.iirnotch(frequency, quality_factor, sample_rate)

        return b, a

    def apply_notch_filter(
        self,
        data: np.ndarray,
        frequency: float,
        quality_factor: float,
        sample_rate: float,
    ) -> np.ndarray:
        """Apply notch filter to remove specific frequency.

        Args:
            data: Input signal
            frequency: Frequency to remove (Hz)
            quality_factor: Q factor
            sample_rate: Sample rate (Hz)

        Returns:
            Filtered data
        """
        b, a = self.design_notch_filter(frequency, quality_factor, sample_rate)

        # Apply filter
        filtered = signal.filtfilt(b, a, data)

        return filtered

    def design_comb_filter(
        self, frequencies: list, quality_factor: float, sample_rate: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Design comb filter to remove multiple harmonics.

        Args:
            frequencies: List of frequencies to remove (Hz)
            quality_factor: Q factor for each notch
            sample_rate: Sample rate (Hz)

        Returns:
            Tuple of (b, a) filter coefficients
        """
        # Start with identity filter
        b = np.array([1.0])
        a = np.array([1.0])

        # Cascade notch filters
        for freq in frequencies:
            b_notch, a_notch = signal.iirnotch(freq, quality_factor, sample_rate)

            # Cascade filters
            b = signal.convolve(b, b_notch)
            a = signal.convolve(a, a_notch)

        return b, a

    def remove_dc_offset(self, data: np.ndarray) -> np.ndarray:
        """Remove DC offset from signal.

        Args:
            data: Input signal

        Returns:
            Signal with DC removed
        """
        return data - np.mean(data)

    def detrend(self, data: np.ndarray, order: int = 1) -> np.ndarray:
        """Remove polynomial trend from signal.

        Args:
            data: Input signal
            order: Polynomial order (1=linear, 2=quadratic, etc.)

        Returns:
            Detrended signal
        """
        # Fit polynomial
        x = np.arange(len(data))
        coeffs = np.polyfit(x, data, order)
        trend = np.polyval(coeffs, x)

        # Remove trend
        detrended = data - trend

        return detrended

    def moving_average(self, data: np.ndarray, window_size: int) -> np.ndarray:
        """Apply moving average filter.

        Args:
            data: Input signal
            window_size: Window size

        Returns:
            Smoothed signal
        """
        kernel = np.ones(window_size) / window_size
        smoothed = np.convolve(data, kernel, mode="same")

        return smoothed

    def savitzky_golay(
        self, data: np.ndarray, window_size: int, poly_order: int
    ) -> np.ndarray:
        """Apply Savitzky-Golay smoothing filter.

        Args:
            data: Input signal
            window_size: Window size (must be odd)
            poly_order: Polynomial order

        Returns:
            Smoothed signal
        """
        # Ensure window size is odd
        if window_size % 2 == 0:
            window_size += 1

        smoothed = signal.savgol_filter(data, window_size, poly_order)

        return smoothed

    def median_filter(self, data: np.ndarray, window_size: int) -> np.ndarray:
        """Apply median filter (good for impulse noise).

        Args:
            data: Input signal
            window_size: Window size

        Returns:
            Filtered signal
        """
        filtered = signal.medfilt(data, kernel_size=window_size)

        return filtered

    def wiener_filter(
        self, data: np.ndarray, noise_power: Optional[float] = None
    ) -> np.ndarray:
        """Apply Wiener filter for noise reduction.

        Args:
            data: Input signal
            noise_power: Noise power estimate (optional)

        Returns:
            Filtered signal
        """
        from scipy.signal import wiener

        filtered = wiener(data, mysize=None, noise=noise_power)

        return filtered
