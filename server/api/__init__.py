"""API routers for LabLink server."""

from .equipment import router as equipment_router
from .data import router as data_router

__all__ = ["equipment_router", "data_router"]
