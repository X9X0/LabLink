"""Visualization widgets for LabLink GUI."""

try:
    from .plot_widget import RealTimePlotWidget
    from .power_chart_widget import PowerChartWidget
    from .waveform_display import WaveformDisplay

    __all__ = [
        "RealTimePlotWidget",
        "WaveformDisplay",
        "PowerChartWidget",
    ]
except ImportError as e:
    # pyqtgraph or PyQt6 not available
    __all__ = []
    import warnings

    warnings.warn(f"Visualization widgets not available: {e}")
