"""Waveform capture and analysis module.

This module provides advanced oscilloscope waveform capture, analysis,
and visualization capabilities including:
- High-speed waveform acquisition
- Enhanced automatic measurements (30+ types)
- Cursor measurements (horizontal and vertical)
- Math channels (add, subtract, FFT, integrate, etc.)
- Persistence mode
- Histogram display
- XY mode
"""

from .analyzer import WaveformAnalyzer
from .manager import WaveformManager
from .models import (CursorData, CursorType, EnhancedMeasurements,
                     ExtendedWaveformData, HistogramData, MathChannelConfig,
                     MathOperation, PersistenceConfig, PersistenceMode,
                     XYPlotData)

__all__ = [
    "ExtendedWaveformData",
    "CursorData",
    "CursorType",
    "MathChannelConfig",
    "MathOperation",
    "PersistenceConfig",
    "PersistenceMode",
    "HistogramData",
    "XYPlotData",
    "EnhancedMeasurements",
    "WaveformAnalyzer",
    "WaveformManager",
]
