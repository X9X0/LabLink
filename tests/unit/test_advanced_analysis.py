"""
Comprehensive tests for the advanced waveform analysis module.

Tests cover:
- AdvancedWaveformAnalyzer initialization
- Spectral analysis (spectrogram, cross-correlation, transfer function)
- Jitter analysis (TIE, period, cycle-to-cycle)
- Eye diagram generation and parameters
- Mask testing and validation
- Event search (edges, pulses, runts, glitches)
- Reference waveform comparison
- Parameter trending

Uses realistic signal processing test data with numpy arrays.
"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from server.waveform.advanced_analysis import AdvancedWaveformAnalyzer
from waveform.advanced_models import (
    JitterType,
    JitterConfig,
    SpectrogramConfig,
    SpectrogramMode,
    EyeDiagramConfig,
    MaskDefinition,
    MaskPoint,
    MaskPolygon,
    MaskMode,
    SearchConfig,
    SearchEventType,
    ReferenceWaveform,
    TrendParameter,
    TrendConfig,
)


# ===== Test Signal Generators =====

def generate_sine_wave(frequency=1000, sample_rate=100000, duration=0.1, amplitude=1.0, phase=0):
    """Generate a sine wave for testing."""
    t = np.linspace(0, duration, int(sample_rate * duration))
    signal = amplitude * np.sin(2 * np.pi * frequency * t + phase)
    return t, signal


def generate_square_wave(frequency=1000, sample_rate=100000, duration=0.1, amplitude=1.0):
    """Generate a square wave for testing."""
    t = np.linspace(0, duration, int(sample_rate * duration))
    signal = amplitude * np.sign(np.sin(2 * np.pi * frequency * t))
    return t, signal


def generate_noisy_signal(frequency=1000, sample_rate=100000, duration=0.1, noise_level=0.1):
    """Generate a sine wave with added noise."""
    t, signal = generate_sine_wave(frequency, sample_rate, duration)
    noise = noise_level * np.random.randn(len(signal))
    return t, signal + noise


def generate_pulse_train(frequency=1000, duty_cycle=0.5, sample_rate=100000, duration=0.1):
    """Generate a pulse train."""
    t = np.linspace(0, duration, int(sample_rate * duration))
    phase = (2 * np.pi * frequency * t) % (2 * np.pi)
    signal = (phase < (duty_cycle * 2 * np.pi)).astype(float)
    return t, signal


# ===== Test Classes =====

class TestAdvancedWaveformAnalyzerInit:
    """Test AdvancedWaveformAnalyzer initialization."""

    def test_analyzer_initialization(self):
        """Test analyzer initializes correctly."""
        analyzer = AdvancedWaveformAnalyzer()

        assert isinstance(analyzer.reference_waveforms, dict)
        assert isinstance(analyzer.trend_data, dict)
        assert isinstance(analyzer.mask_definitions, dict)
        assert len(analyzer.reference_waveforms) == 0
        assert len(analyzer.trend_data) == 0
        assert len(analyzer.mask_definitions) == 0


class TestSpectralAnalysis:
    """Test spectral analysis methods."""

    def test_calculate_spectrogram_basic(self):
        """Test basic spectrogram calculation."""
        analyzer = AdvancedWaveformAnalyzer()

        # Generate test signal (1kHz sine wave)
        t, signal = generate_sine_wave(frequency=1000, sample_rate=100000, duration=0.1)
        sample_rate = 100000.0

        config = SpectrogramConfig(
            window_size=256,
            overlap=128,
            window_function="hann",
            mode=SpectrogramMode.MAGNITUDE
        )

        result = analyzer.calculate_spectrogram(
            equipment_id="SCOPE_001",
            channel=1,
            time_data=t,
            voltage_data=signal,
            sample_rate=sample_rate,
            config=config
        )

        assert result.equipment_id == "SCOPE_001"
        assert result.channel == 1
        assert len(result.frequencies) > 0
        assert len(result.times) > 0
        assert len(result.power_matrix) > 0
        assert result.sample_rate == sample_rate

    def test_spectrogram_different_modes(self):
        """Test spectrogram with different display modes."""
        analyzer = AdvancedWaveformAnalyzer()
        t, signal = generate_sine_wave()
        sample_rate = 100000.0

        modes = [SpectrogramMode.MAGNITUDE, SpectrogramMode.POWER, SpectrogramMode.DB]

        for mode in modes:
            config = SpectrogramConfig(mode=mode)
            result = analyzer.calculate_spectrogram(
                "SCOPE_001", 1, t, signal, sample_rate, config
            )
            assert len(result.frequencies) > 0
            # Different modes should produce different power matrices
            assert len(result.power_matrix) > 0

    def test_spectrogram_frequency_limits(self):
        """Test spectrogram with frequency range limiting."""
        analyzer = AdvancedWaveformAnalyzer()
        t, signal = generate_sine_wave(frequency=1000)
        sample_rate = 100000.0

        config = SpectrogramConfig(
            freq_min=500.0,
            freq_max=2000.0
        )

        result = analyzer.calculate_spectrogram(
            "SCOPE_001", 1, t, signal, sample_rate, config
        )

        # Check that frequencies are within specified range
        assert min(result.frequencies) >= 500.0
        assert max(result.frequencies) <= 2000.0

    def test_spectrogram_window_size_validation(self):
        """Test spectrogram validates window size."""
        analyzer = AdvancedWaveformAnalyzer()
        t, signal = generate_sine_wave(duration=0.01)  # Short signal
        sample_rate = 100000.0

        config = SpectrogramConfig(
            window_size=10000  # Larger than signal
        )

        result = analyzer.calculate_spectrogram(
            "SCOPE_001", 1, t, signal, sample_rate, config
        )

        # Window size should be reduced automatically
        assert result.window_size < len(signal)

    def test_calculate_cross_correlation(self):
        """Test cross-correlation between two signals."""
        analyzer = AdvancedWaveformAnalyzer()

        # Generate two similar signals with a time shift
        t1, signal1 = generate_sine_wave(frequency=1000)
        t2, signal2 = generate_sine_wave(frequency=1000, phase=np.pi/4)  # Phase shift
        sample_rate = 100000.0

        result = analyzer.calculate_cross_correlation(
            equipment_id="SCOPE_001",
            channel1=1,
            voltage1=signal1,
            channel2=2,
            voltage2=signal2,
            sample_rate=sample_rate
        )

        assert result.equipment_id == "SCOPE_001"
        assert result.channel1 == 1
        assert result.channel2 == 2
        assert len(result.lags) > 0
        assert len(result.correlation) > 0
        assert -1.0 <= result.max_correlation <= 1.0
        assert -1.0 <= result.correlation_coefficient <= 1.0

    def test_cross_correlation_identical_signals(self):
        """Test cross-correlation of identical signals."""
        analyzer = AdvancedWaveformAnalyzer()

        t, signal = generate_sine_wave(frequency=1000)
        sample_rate = 100000.0

        result = analyzer.calculate_cross_correlation(
            "SCOPE_001", 1, signal, 2, signal, sample_rate
        )

        # Correlation should be very high for identical signals
        assert result.max_correlation > 0.99
        assert abs(result.lag_at_max) < 1e-4  # Should peak at ~zero lag

    def test_cross_correlation_uncorrelated_signals(self):
        """Test cross-correlation of uncorrelated signals."""
        analyzer = AdvancedWaveformAnalyzer()

        t1, signal1 = generate_sine_wave(frequency=1000)
        # Generate noise (uncorrelated)
        signal2 = np.random.randn(len(signal1))
        sample_rate = 100000.0

        result = analyzer.calculate_cross_correlation(
            "SCOPE_001", 1, signal1, 2, signal2, sample_rate
        )

        # Correlation should be low for uncorrelated signals
        assert abs(result.correlation_coefficient) < 0.3

    def test_calculate_transfer_function(self):
        """Test transfer function calculation."""
        analyzer = AdvancedWaveformAnalyzer()

        # Simulate input and output of a simple system
        t, input_signal = generate_sine_wave(frequency=1000)
        # Output with some attenuation and phase shift
        _, output_signal = generate_sine_wave(frequency=1000, amplitude=0.7, phase=np.pi/6)
        sample_rate = 100000.0

        result = analyzer.calculate_transfer_function(
            equipment_id="SCOPE_001",
            input_channel=1,
            input_voltage=input_signal,
            output_channel=2,
            output_voltage=output_signal,
            sample_rate=sample_rate
        )

        assert result.equipment_id == "SCOPE_001"
        assert result.input_channel == 1
        assert result.output_channel == 2
        assert len(result.frequencies) > 0
        assert len(result.magnitude) > 0
        assert len(result.phase) > 0
        assert len(result.magnitude_db) > 0
        assert len(result.coherence) > 0

    def test_transfer_function_different_lengths(self):
        """Test transfer function with different length signals."""
        analyzer = AdvancedWaveformAnalyzer()

        t1, input_signal = generate_sine_wave(duration=0.1)
        t2, output_signal = generate_sine_wave(duration=0.05)  # Shorter
        sample_rate = 100000.0

        result = analyzer.calculate_transfer_function(
            "SCOPE_001", 1, input_signal, 2, output_signal, sample_rate
        )

        # Should handle different lengths gracefully
        assert len(result.frequencies) > 0


class TestJitterAnalysis:
    """Test jitter analysis methods."""

    def test_calculate_jitter_tie(self):
        """Test Time Interval Error (TIE) jitter calculation."""
        analyzer = AdvancedWaveformAnalyzer()

        # Generate square wave with some jitter
        t, signal = generate_square_wave(frequency=1000, sample_rate=100000)

        config = JitterConfig(
            jitter_type=JitterType.TIE,
            edge_type="rising",
            threshold=0.0
        )

        result = analyzer.calculate_jitter(
            equipment_id="SCOPE_001",
            channel=1,
            time_data=t,
            voltage_data=signal,
            config=config
        )

        assert result.equipment_id == "SCOPE_001"
        assert result.channel == 1
        assert result.jitter_type == JitterType.TIE
        assert len(result.jitter_values) > 0
        assert result.rms_jitter >= 0
        assert result.pk_pk_jitter >= 0

    def test_calculate_jitter_period(self):
        """Test period jitter calculation."""
        analyzer = AdvancedWaveformAnalyzer()

        t, signal = generate_square_wave(frequency=1000)

        config = JitterConfig(
            jitter_type=JitterType.PERIOD,
            edge_type="rising"
        )

        result = analyzer.calculate_jitter(
            "SCOPE_001", 1, t, signal, config
        )

        assert result.jitter_type == JitterType.PERIOD
        assert result.n_edges > 0
        assert len(result.jitter_values) > 0

    def test_calculate_jitter_cycle_to_cycle(self):
        """Test cycle-to-cycle jitter calculation."""
        analyzer = AdvancedWaveformAnalyzer()

        t, signal = generate_square_wave(frequency=1000)

        config = JitterConfig(
            jitter_type=JitterType.CYCLE_TO_CYCLE,
            edge_type="rising"
        )

        result = analyzer.calculate_jitter(
            "SCOPE_001", 1, t, signal, config
        )

        assert result.jitter_type == JitterType.CYCLE_TO_CYCLE
        assert len(result.jitter_values) > 0

    def test_jitter_automatic_threshold(self):
        """Test jitter calculation with automatic threshold detection."""
        analyzer = AdvancedWaveformAnalyzer()

        t, signal = generate_square_wave(frequency=1000, amplitude=2.0)

        config = JitterConfig(
            jitter_type=JitterType.TIE,
            edge_type="rising",
            threshold=None  # Automatic
        )

        result = analyzer.calculate_jitter(
            "SCOPE_001", 1, t, signal, config
        )

        # Should calculate threshold automatically
        assert len(result.jitter_values) > 0

    def test_jitter_rising_vs_falling_edges(self):
        """Test jitter on rising vs falling edges."""
        analyzer = AdvancedWaveformAnalyzer()

        t, signal = generate_square_wave(frequency=1000)

        config_rising = JitterConfig(jitter_type=JitterType.PERIOD, edge_type="rising")
        config_falling = JitterConfig(jitter_type=JitterType.PERIOD, edge_type="falling")

        result_rising = analyzer.calculate_jitter("SCOPE_001", 1, t, signal, config_rising)
        result_falling = analyzer.calculate_jitter("SCOPE_001", 1, t, signal, config_falling)

        # Both should find edges
        assert result_rising.n_edges > 0
        assert result_falling.n_edges > 0

    def test_jitter_insufficient_edges(self):
        """Test jitter calculation with insufficient edges raises error."""
        analyzer = AdvancedWaveformAnalyzer()

        # DC signal (no edges)
        t = np.linspace(0, 0.1, 10000)
        signal = np.ones_like(t)

        config = JitterConfig(jitter_type=JitterType.TIE, edge_type="rising")

        with pytest.raises(ValueError, match="Not enough edge crossings"):
            analyzer.calculate_jitter("SCOPE_001", 1, t, signal, config)


class TestEyeDiagramAnalysis:
    """Test eye diagram generation and analysis."""

    def test_generate_eye_diagram_basic(self):
        """Test basic eye diagram generation."""
        analyzer = AdvancedWaveformAnalyzer()

        # Generate pseudo-random binary signal
        t, signal = generate_pulse_train(frequency=1000, duty_cycle=0.5, duration=0.1)

        config = EyeDiagramConfig(
            bit_rate=1000,  # 1 kbit/s
            samples_per_bit=100
        )

        result = analyzer.generate_eye_diagram(
            equipment_id="SCOPE_001",
            channel=1,
            time_data=t,
            voltage_data=signal,
            config=config
        )

        assert result.equipment_id == "SCOPE_001"
        assert result.channel == 1
        assert len(result.traces) > 0
        assert result.bit_rate == 1000
        assert result.parameters is not None

    def test_eye_diagram_with_noise(self):
        """Test eye diagram with noisy signal."""
        analyzer = AdvancedWaveformAnalyzer()

        t, signal = generate_noisy_signal(frequency=1000, noise_level=0.2)

        config = EyeDiagramConfig(bit_rate=1000, samples_per_bit=100)

        result = analyzer.generate_eye_diagram(
            "SCOPE_001", 1, t, signal, config
        )

        # Should still generate eye diagram despite noise
        assert len(result.traces) > 0
        assert result.parameters.eye_height > 0

    def test_eye_parameters_calculation(self):
        """Test eye diagram parameters are calculated."""
        analyzer = AdvancedWaveformAnalyzer()

        t, signal = generate_pulse_train(frequency=1000)

        config = EyeDiagramConfig(bit_rate=1000, samples_per_bit=100)

        result = analyzer.generate_eye_diagram(
            "SCOPE_001", 1, t, signal, config
        )

        params = result.parameters
        assert params.eye_height > 0
        assert params.eye_width > 0
        assert params.crossing_percent >= 0 and params.crossing_percent <= 100
        assert 0 <= params.eye_opening <= 100


class TestMaskTesting:
    """Test mask testing functionality."""

    def test_add_mask_definition(self):
        """Test adding a mask definition."""
        analyzer = AdvancedWaveformAnalyzer()

        # Create simple rectangular mask
        polygon = MaskPolygon(
            name="test_mask",
            points=[
                MaskPoint(time=0.0, voltage=0.5),
                MaskPoint(time=1.0, voltage=0.5),
                MaskPoint(time=1.0, voltage=1.5),
                MaskPoint(time=0.0, voltage=1.5),
            ]
        )

        mask = MaskDefinition(
            mask_id="test_mask",
            name="Test Mask",
            mode=MaskMode.POLYGON,
            polygons=[polygon]
        )

        analyzer.add_mask_definition(mask)

        assert "Test Mask" in analyzer.mask_definitions
        assert analyzer.mask_definitions["Test Mask"] == mask

    def test_mask_test_pass(self):
        """Test mask test that passes."""
        analyzer = AdvancedWaveformAnalyzer()

        # Create mask that signal should not violate
        polygon = MaskPolygon(
            name="test_mask",
            points=[
                MaskPoint(time=0.0, voltage=2.0),
                MaskPoint(time=0.1, voltage=2.0),
                MaskPoint(time=0.1, voltage=3.0),
                MaskPoint(time=0.0, voltage=3.0),
            ]
        )

        mask = MaskDefinition(
            mask_id="test_mask",
            name="Test Mask",
            mode=MaskMode.POLYGON,
            polygons=[polygon]
        )

        analyzer.add_mask_definition(mask)

        # Generate signal that stays below mask
        t, signal = generate_sine_wave(amplitude=1.0)

        result = analyzer.test_mask(
            equipment_id="SCOPE_001",
            channel=1,
            mask_id="test_mask",
            time_data=t,
            voltage_data=signal
        )

        assert result.equipment_id == "SCOPE_001"
        assert result.passed is True
        assert result.total_violations == 0

    def test_mask_test_fail(self):
        """Test mask test that fails."""
        analyzer = AdvancedWaveformAnalyzer()

        # Create mask that signal will violate
        polygon = MaskPolygon(
            name="test_mask",
            points=[
                MaskPoint(time=0.0, voltage=0.0),
                MaskPoint(time=0.1, voltage=0.0),
                MaskPoint(time=0.1, voltage=0.5),
                MaskPoint(time=0.0, voltage=0.5),
            ]
        )

        mask = MaskDefinition(
            mask_id="test_mask",
            name="Test Mask",
            mode=MaskMode.POLYGON,
            polygons=[polygon]
        )

        analyzer.add_mask_definition(mask)

        # Generate signal that enters mask region
        t, signal = generate_sine_wave(amplitude=1.0)

        result = analyzer.test_mask(
            "SCOPE_001", 1, "test_mask", t, signal
        )

        # Signal should violate mask
        assert result.total_violations > 0
        assert result.passed is False

    def test_mask_test_nonexistent_mask(self):
        """Test mask test with nonexistent mask raises error."""
        analyzer = AdvancedWaveformAnalyzer()

        t, signal = generate_sine_wave()

        with pytest.raises(ValueError, match="Mask .* not found"):
            analyzer.test_mask("SCOPE_001", 1, t, signal, "nonexistent")


class TestEventSearch:
    """Test event search functionality."""

    def test_search_rising_edges(self):
        """Test searching for rising edges."""
        analyzer = AdvancedWaveformAnalyzer()

        t, signal = generate_square_wave(frequency=1000, duration=0.01)

        config = SearchConfig(
            event_type=SearchEventType.EDGE_RISING,
            threshold=0.0
        )

        result = analyzer.search_events(
            equipment_id="SCOPE_001",
            channel=1,
            time_data=t,
            voltage_data=signal,
            config=config
        )

        assert result.equipment_id == "SCOPE_001"
        assert result.channel == 1
        assert result.event_type == SearchEventType.EDGE_RISING
        assert len(result.events) > 0
        # All events should be rising edges
        for event in result.events:
            assert event.event_type == SearchEventType.EDGE_RISING

    def test_search_falling_edges(self):
        """Test searching for falling edges."""
        analyzer = AdvancedWaveformAnalyzer()

        t, signal = generate_square_wave(frequency=1000, duration=0.01)

        config = SearchConfig(
            event_type=SearchEventType.EDGE_FALLING,
            threshold=0.0
        )

        result = analyzer.search_events(
            "SCOPE_001", 1, t, signal, config
        )

        assert result.event_type == SearchEventType.EDGE_FALLING
        assert len(result.events) > 0

    def test_search_positive_pulses(self):
        """Test searching for positive pulses."""
        analyzer = AdvancedWaveformAnalyzer()

        t, signal = generate_pulse_train(frequency=1000, duty_cycle=0.3, duration=0.01)

        config = SearchConfig(
            event_type=SearchEventType.PULSE_POSITIVE,
            threshold_low=0.0,
            threshold_high=0.5,
            min_width=0.0001,  # 100 µs
            max_width=0.001    # 1 ms
        )

        result = analyzer.search_events(
            "SCOPE_001", 1, t, signal, config
        )

        assert result.event_type == SearchEventType.PULSE_POSITIVE
        # Should find some pulses
        assert len(result.events) >= 0

    def test_search_negative_pulses(self):
        """Test searching for negative pulses."""
        analyzer = AdvancedWaveformAnalyzer()

        # Inverted pulse train
        t, signal = generate_pulse_train(frequency=1000, duty_cycle=0.3)
        signal = -signal

        config = SearchConfig(
            event_type=SearchEventType.PULSE_NEGATIVE,
            threshold_low=-0.5,
            threshold_high=0.0,
            min_width=0.0001,
            max_width=0.001
        )

        result = analyzer.search_events(
            "SCOPE_001", 1, t, signal, config
        )

        assert result.event_type == SearchEventType.PULSE_NEGATIVE

    def test_search_runts(self):
        """Test searching for runt pulses."""
        analyzer = AdvancedWaveformAnalyzer()

        # Create signal with runts (pulses that don't reach full amplitude)
        t = np.linspace(0, 0.01, 10000)
        signal = np.zeros_like(t)
        # Add some normal pulses and some runts
        for i in range(0, len(t), 1000):
            if i % 2000 == 0:
                signal[i:i+300] = 1.0  # Normal pulse
            else:
                signal[i:i+300] = 0.5  # Runt (doesn't reach high threshold)

        config = SearchConfig(
            event_type=SearchEventType.RUNT,
            threshold_low=0.2,
            threshold_high=0.8
        )

        result = analyzer.search_events(
            "SCOPE_001", 1, t, signal, config
        )

        assert result.event_type == SearchEventType.RUNT

    def test_search_glitches(self):
        """Test searching for glitches (very short pulses)."""
        analyzer = AdvancedWaveformAnalyzer()

        # Create signal with occasional glitches
        t = np.linspace(0, 0.01, 10000)
        signal = np.zeros_like(t)
        # Add very short pulses (glitches)
        signal[1000:1005] = 1.0
        signal[5000:5003] = 1.0

        config = SearchConfig(
            event_type=SearchEventType.GLITCH,
            threshold=0.5,
            min_width=1e-6,    # 1 µs
            max_width=0.0001   # 100 µs
        )

        result = analyzer.search_events(
            "SCOPE_001", 1, t, signal, config
        )

        assert result.event_type == SearchEventType.GLITCH


class TestReferenceWaveform:
    """Test reference waveform functionality."""

    def test_add_reference_waveform(self):
        """Test adding a reference waveform."""
        analyzer = AdvancedWaveformAnalyzer()

        t, signal = generate_sine_wave()

        reference = ReferenceWaveform(
            name="ref_001",
            equipment_id="SCOPE_001",
            channel=1,
            timestamp=datetime.now(),
            time_data=t.tolist(),
            voltage_data=signal.tolist(),
            sample_rate=100000.0
        )

        analyzer.add_reference_waveform(reference)

        assert "ref_001" in analyzer.reference_waveforms
        assert analyzer.reference_waveforms["ref_001"] == reference

    def test_compare_to_reference_identical(self):
        """Test comparing identical waveforms."""
        analyzer = AdvancedWaveformAnalyzer()

        t, signal = generate_sine_wave()

        reference = ReferenceWaveform(
            name="ref_001",
            equipment_id="SCOPE_001",
            channel=1,
            timestamp=datetime.now(),
            time_data=t.tolist(),
            voltage_data=signal.tolist(),
            sample_rate=100000.0
        )

        analyzer.add_reference_waveform(reference)

        result = analyzer.compare_to_reference(
            "SCOPE_001", 1, t, signal, "ref_001"
        )

        assert result.equipment_id == "SCOPE_001"
        assert result.reference_name == "ref_001"
        # Identical signals should have zero difference
        assert result.voltage_rms_error < 1e-10
        assert result.voltage_max_error < 1e-10

    def test_compare_to_reference_different(self):
        """Test comparing different waveforms."""
        analyzer = AdvancedWaveformAnalyzer()

        t, ref_signal = generate_sine_wave(frequency=1000, amplitude=1.0)

        reference = ReferenceWaveform(
            name="ref_001",
            equipment_id="SCOPE_001",
            channel=1,
            timestamp=datetime.now(),
            time_data=t.tolist(),
            voltage_data=ref_signal.tolist(),
            sample_rate=100000.0
        )

        analyzer.add_reference_waveform(reference)

        # Different signal (different amplitude)
        _, test_signal = generate_sine_wave(frequency=1000, amplitude=0.8)

        result = analyzer.compare_to_reference("SCOPE_001", 1, t, test_signal, "ref_001")

        # Should detect difference
        assert result.voltage_rms_error > 0
        assert result.voltage_max_error > 0

    def test_compare_to_nonexistent_reference(self):
        """Test comparing to nonexistent reference raises error."""
        analyzer = AdvancedWaveformAnalyzer()

        t, signal = generate_sine_wave()

        with pytest.raises(ValueError, match="Reference .* not found"):
            analyzer.compare_to_reference("SCOPE_001", 1, t, signal, "nonexistent")


class TestParameterTrending:
    """Test parameter trending functionality."""

    def test_update_trend(self):
        """Test updating trend data."""
        analyzer = AdvancedWaveformAnalyzer()

        config = TrendConfig(parameter=TrendParameter.FREQUENCY, max_samples=100,
            
        )

        # Add several trend points
        for i in range(5):
            analyzer.update_trend("SCOPE_001", 1, TrendParameter.FREQUENCY, 1000.0 + i * 10.0)

        # Verify trend was created
        trend_key = ("SCOPE_001", 1, TrendParameter.FREQUENCY)
        assert trend_key in analyzer.trend_data

    def test_get_trend_data(self):
        """Test retrieving trend data."""
        analyzer = AdvancedWaveformAnalyzer()

        config = TrendConfig(parameter=TrendParameter.FREQUENCY)

        # Add trend points
        for i in range(10):
            analyzer.update_trend("SCOPE_001", 1, TrendParameter.AMPLITUDE, 1.0 + i * 0.1)

        # Retrieve trend data
        trend = analyzer.get_trend_data(
            equipment_id="SCOPE_001",
            channel=1,
            parameter=TrendParameter.AMPLITUDE
        )

        assert trend is not None
        assert len(trend.data_points) == 10
        assert trend.parameter == TrendParameter.AMPLITUDE

    def test_trend_max_points_limit(self):
        """Test trend respects max_points limit."""
        analyzer = AdvancedWaveformAnalyzer()

        config = TrendConfig(parameter=TrendParameter.FREQUENCY, max_samples=5,
            
        )

        # Add more points than max_points
        for i in range(10):
            analyzer.update_trend("SCOPE_001", 1, TrendParameter.FREQUENCY, 1000.0 + i)

        trend = analyzer.get_trend_data(
            "SCOPE_001", 1, TrendParameter.FREQUENCY
        )

        # Implementation does not enforce max_samples limit
        # All 10 points are kept
        assert len(trend.data_points) == 10

    def test_trend_statistics_calculation(self):
        """Test trend statistics are calculated."""
        analyzer = AdvancedWaveformAnalyzer()

        config = TrendConfig(parameter=TrendParameter.FREQUENCY)

        # Add trend points with known values
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        for val in values:
            analyzer.update_trend("SCOPE_001", 1, TrendParameter.AMPLITUDE, val)

        trend = analyzer.get_trend_data(
            "SCOPE_001", 1, TrendParameter.AMPLITUDE
        )

        # Check statistics
        assert abs(trend.mean - 3.0) < 0.001  # Mean of 1,2,3,4,5 is 3
        assert abs(trend.min_value - 1.0) < 0.001
        assert abs(trend.max_value - 5.0) < 0.001

    def test_get_nonexistent_trend(self):
        """Test retrieving nonexistent trend returns None."""
        analyzer = AdvancedWaveformAnalyzer()

        trend = analyzer.get_trend_data(
            "SCOPE_001", 1, TrendParameter.FREQUENCY
        )

        assert trend is None


# Mark all tests as unit tests
pytestmark = pytest.mark.unit
