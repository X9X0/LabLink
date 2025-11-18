"""API routers for LabLink server."""

from .acquisition import router as acquisition_router
from .alarms import router as alarms_router
from .analysis import router as analysis_router
from .backup import router as backup_router
from .calibration import router as calibration_router
from .calibration_enhanced import router as calibration_enhanced_router
from .data import router as data_router
from .database import router as database_router
from .diagnostics import router as diagnostics_router
from .discovery import router as discovery_router
from .equipment import router as equipment_router
from .firmware import router as firmware_router
from .locks import router as locks_router
from .performance import router as performance_router
from .profiles import router as profiles_router
from .safety import router as safety_router
from .scheduler import router as scheduler_router
from .security import router as security_router
from .state import router as state_router
from .testing import router as testing_router
from .waveform import router as waveform_router

__all__ = [
    "equipment_router",
    "data_router",
    "profiles_router",
    "safety_router",
    "locks_router",
    "state_router",
    "acquisition_router",
    "alarms_router",
    "scheduler_router",
    "diagnostics_router",
    "calibration_router",
    "performance_router",
    "waveform_router",
    "analysis_router",
    "database_router",
    "calibration_enhanced_router",
    "testing_router",
    "backup_router",
    "discovery_router",
    "security_router",
    "firmware_router",
]
