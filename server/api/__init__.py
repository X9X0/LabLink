"""API routers for LabLink server."""

from .equipment import router as equipment_router
from .data import router as data_router
from .profiles import router as profiles_router
from .safety import router as safety_router
from .locks import router as locks_router
from .state import router as state_router
from .acquisition import router as acquisition_router
from .alarms import router as alarms_router
from .scheduler import router as scheduler_router
from .diagnostics import router as diagnostics_router

__all__ = ["equipment_router", "data_router", "profiles_router", "safety_router", "locks_router", "state_router", "acquisition_router", "alarms_router", "scheduler_router", "diagnostics_router"]
