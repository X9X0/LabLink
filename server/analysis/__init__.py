"""Data analysis pipeline module.

This module provides advanced signal processing, statistical analysis,
and reporting capabilities including:
- Signal filtering (low-pass, high-pass, band-pass, notch)
- Data resampling and interpolation
- Curve fitting and regression analysis
- Statistical process control (SPC)
- Automated report generation
- Batch processing
"""

from .batch import BatchProcessor
from .filters import SignalFilter
from .fitting import CurveFitter
from .models import (BatchJobConfig, BatchJobStatus, CapabilityResult,
                     FilterConfig, FilterMethod, FilterResult, FilterType,
                     FitConfig, FitResult, FitType, ReportConfig, ReportFormat,
                     ResampleConfig, ResampleMethod, SPCChartConfig,
                     SPCChartResult, SPCChartType)
from .reports import ReportGenerator
from .resampling import DataResampler
from .spc import SPCAnalyzer

__all__ = [
    # Models
    "FilterConfig",
    "FilterType",
    "FilterMethod",
    "FilterResult",
    "ResampleConfig",
    "ResampleMethod",
    "FitConfig",
    "FitType",
    "FitResult",
    "SPCChartType",
    "SPCChartConfig",
    "SPCChartResult",
    "CapabilityResult",
    "ReportConfig",
    "ReportFormat",
    "BatchJobConfig",
    "BatchJobStatus",
    # Classes
    "SignalFilter",
    "CurveFitter",
    "SPCAnalyzer",
    "DataResampler",
    "ReportGenerator",
    "BatchProcessor",
]
