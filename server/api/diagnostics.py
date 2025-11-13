"""API endpoints for equipment diagnostics."""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException

from server.diagnostics import (
    diagnostics_manager,
    DiagnosticCategory,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Equipment Health Endpoints ====================


@router.get("/diagnostics/health/{equipment_id}", summary="Get equipment health")
async def get_equipment_health(equipment_id: str):
    """Get comprehensive health status for equipment."""
    try:
        health = await diagnostics_manager.check_equipment_health(equipment_id)

        return {
            "success": True,
            "health": health.dict()
        }

    except Exception as e:
        logger.error(f"Error checking equipment health: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check health: {str(e)}")


@router.get("/diagnostics/health", summary="Get all equipment health")
async def get_all_equipment_health():
    """Get health status for all equipment."""
    from equipment.manager import equipment_manager

    try:
        equipment_ids = list(equipment_manager._equipment.keys())
        health_status = {}

        for eq_id in equipment_ids:
            health = await diagnostics_manager.check_equipment_health(eq_id)
            health_status[eq_id] = health.dict()

        return {
            "success": True,
            "count": len(health_status),
            "equipment_health": health_status
        }

    except Exception as e:
        logger.error(f"Error checking all equipment health: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check health: {str(e)}")


@router.get("/diagnostics/health/{equipment_id}/cached", summary="Get cached health")
async def get_cached_health(equipment_id: str):
    """Get cached health status (faster, but may be outdated)."""
    health = diagnostics_manager.get_health_cache(equipment_id)

    if health is None:
        raise HTTPException(status_code=404, detail=f"No cached health data for {equipment_id}")

    return {
        "success": True,
        "health": health.dict(),
        "cached": True
    }


# ==================== Connection Diagnostics ====================


@router.get("/diagnostics/connection/{equipment_id}", summary="Check connection")
async def check_connection(equipment_id: str):
    """Check connection status and quality."""
    try:
        connection_diag = await diagnostics_manager._check_connection(equipment_id)

        return {
            "success": True,
            "connection": connection_diag.dict()
        }

    except Exception as e:
        logger.error(f"Error checking connection: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check connection: {str(e)}")


# ==================== Communication Diagnostics ====================


@router.get("/diagnostics/communication/{equipment_id}", summary="Get communication stats")
async def get_communication_diagnostics(equipment_id: str):
    """Get communication statistics and diagnostics."""
    try:
        comm_diag = await diagnostics_manager._check_communication(equipment_id)

        return {
            "success": True,
            "communication": comm_diag.dict()
        }

    except Exception as e:
        logger.error(f"Error checking communication: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check communication: {str(e)}")


# ==================== Performance Benchmarking ====================


@router.post("/diagnostics/benchmark/{equipment_id}", summary="Run performance benchmark")
async def run_benchmark(equipment_id: str):
    """Run performance benchmark on equipment."""
    try:
        benchmark = await diagnostics_manager._run_performance_benchmark(equipment_id)

        if benchmark is None:
            raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

        return {
            "success": True,
            "benchmark": benchmark.dict()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running benchmark: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to run benchmark: {str(e)}")


@router.get("/diagnostics/benchmark/{equipment_id}/history", summary="Get benchmark history")
async def get_benchmark_history(equipment_id: str, limit: int = 100):
    """Get historical benchmark data."""
    try:
        history = diagnostics_manager.get_benchmark_history(equipment_id, limit)

        return {
            "success": True,
            "count": len(history),
            "benchmarks": [b.dict() for b in history]
        }

    except Exception as e:
        logger.error(f"Error getting benchmark history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get history: {str(e)}")


# ==================== Diagnostic Reports ====================


@router.post("/diagnostics/report", summary="Generate diagnostic report")
async def generate_diagnostic_report(
    equipment_ids: Optional[List[str]] = None,
    categories: Optional[List[str]] = None
):
    """Generate comprehensive diagnostic report."""
    try:
        # Convert category strings to enums
        category_enums = None
        if categories:
            try:
                category_enums = [DiagnosticCategory(c) for c in categories]
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid category: {str(e)}")

        report = await diagnostics_manager.generate_diagnostic_report(
            equipment_ids=equipment_ids,
            categories=category_enums
        )

        return {
            "success": True,
            "report": report.dict()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


# ==================== System Diagnostics ====================


@router.get("/diagnostics/system", summary="Get system diagnostics")
async def get_system_diagnostics():
    """Get system-wide diagnostics and health."""
    try:
        system_diag = await diagnostics_manager.get_system_diagnostics()

        return {
            "success": True,
            "system": system_diag.dict()
        }

    except Exception as e:
        logger.error(f"Error getting system diagnostics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get system diagnostics: {str(e)}")


# ==================== Statistics Recording ====================


@router.post("/diagnostics/stats/connection/{equipment_id}", summary="Record connection")
async def record_connection_event(equipment_id: str):
    """Record equipment connection event."""
    diagnostics_manager.record_connection(equipment_id)

    return {
        "success": True,
        "message": "Connection event recorded"
    }


@router.post("/diagnostics/stats/disconnection/{equipment_id}", summary="Record disconnection")
async def record_disconnection_event(equipment_id: str, error: Optional[str] = None):
    """Record equipment disconnection event."""
    diagnostics_manager.record_disconnection(equipment_id, error)

    return {
        "success": True,
        "message": "Disconnection event recorded"
    }
