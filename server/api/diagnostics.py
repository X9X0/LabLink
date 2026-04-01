"""API endpoints for equipment diagnostics."""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException

from server.diagnostics import DiagnosticCategory, diagnostics_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Equipment Health Endpoints ====================


@router.get("/diagnostics/health/{equipment_id}", summary="Get equipment health")
async def get_equipment_health(equipment_id: str):
    """Get comprehensive health status for equipment."""
    try:
        health = await diagnostics_manager.check_equipment_health(equipment_id)

        return {"success": True, "health": health.dict()}

    except Exception as e:
        logger.error(f"Error checking equipment health: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check health: {str(e)}")


@router.get("/diagnostics/health", summary="Get all equipment health")
async def get_all_equipment_health():
    """Get health status for all equipment."""
    from equipment.manager import equipment_manager

    try:
        equipment_ids = list(equipment_manager.equipment.keys())
        health_status = {}

        for eq_id in equipment_ids:
            health = await diagnostics_manager.check_equipment_health(eq_id)
            health_status[eq_id] = health.dict()

        return {
            "success": True,
            "count": len(health_status),
            "equipment_health": health_status,
        }

    except Exception as e:
        logger.error(f"Error checking all equipment health: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check health: {str(e)}")


@router.get("/diagnostics/health/{equipment_id}/cached", summary="Get cached health")
async def get_cached_health(equipment_id: str):
    """Get cached health status (faster, but may be outdated)."""
    health = diagnostics_manager.get_health_cache(equipment_id)

    if health is None:
        raise HTTPException(
            status_code=404, detail=f"No cached health data for {equipment_id}"
        )

    return {"success": True, "health": health.dict(), "cached": True}


# ==================== Connection Diagnostics ====================


@router.get("/diagnostics/connection/{equipment_id}", summary="Check connection")
async def check_connection(equipment_id: str):
    """Check connection status and quality."""
    try:
        connection_diag = await diagnostics_manager._check_connection(equipment_id)

        return {"success": True, "connection": connection_diag.dict()}

    except Exception as e:
        logger.error(f"Error checking connection: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to check connection: {str(e)}"
        )


# ==================== Communication Diagnostics ====================


@router.get(
    "/diagnostics/communication/{equipment_id}", summary="Get communication stats"
)
async def get_communication_diagnostics(equipment_id: str):
    """Get communication statistics and diagnostics."""
    try:
        comm_diag = await diagnostics_manager._check_communication(equipment_id)

        return {"success": True, "communication": comm_diag.dict()}

    except Exception as e:
        logger.error(f"Error checking communication: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to check communication: {str(e)}"
        )


# ==================== Performance Benchmarking ====================


@router.post(
    "/diagnostics/benchmark/{equipment_id}", summary="Run performance benchmark"
)
async def run_benchmark(equipment_id: str):
    """Run performance benchmark on equipment."""
    try:
        benchmark = await diagnostics_manager._run_performance_benchmark(equipment_id)

        if benchmark is None:
            raise HTTPException(
                status_code=404, detail=f"Equipment {equipment_id} not found"
            )

        return {"success": True, "benchmark": benchmark.dict()}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running benchmark: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to run benchmark: {str(e)}"
        )


@router.get(
    "/diagnostics/benchmark/{equipment_id}/history", summary="Get benchmark history"
)
async def get_benchmark_history(equipment_id: str, limit: int = 100):
    """Get historical benchmark data."""
    try:
        history = diagnostics_manager.get_benchmark_history(equipment_id, limit)

        return {
            "success": True,
            "count": len(history),
            "benchmarks": [b.dict() for b in history],
        }

    except Exception as e:
        logger.error(f"Error getting benchmark history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get history: {str(e)}")


# ==================== Diagnostic Reports ====================


@router.post("/diagnostics/report", summary="Generate diagnostic report")
async def generate_diagnostic_report(
    equipment_ids: Optional[List[str]] = None, categories: Optional[List[str]] = None
):
    """Generate comprehensive diagnostic report."""
    try:
        # Convert category strings to enums
        category_enums = None
        if categories:
            try:
                category_enums = [DiagnosticCategory(c) for c in categories]
            except ValueError as e:
                raise HTTPException(
                    status_code=400, detail=f"Invalid category: {str(e)}"
                )

        report = await diagnostics_manager.generate_diagnostic_report(
            equipment_ids=equipment_ids, categories=category_enums
        )

        return {"success": True, "report": report.dict()}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to generate report: {str(e)}"
        )


# ==================== System Diagnostics ====================


@router.get("/diagnostics/system", summary="Get system diagnostics")
async def get_system_diagnostics():
    """Get system-wide diagnostics and health."""
    try:
        system_diag = await diagnostics_manager.get_system_diagnostics()

        return {"success": True, "system": system_diag.dict()}

    except Exception as e:
        logger.error(f"Error getting system diagnostics: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get system diagnostics: {str(e)}"
        )


# ==================== Enhanced Diagnostics (v0.12.0) ====================


@router.get(
    "/diagnostics/temperature/{equipment_id}", summary="Check equipment temperature"
)
async def check_equipment_temperature(equipment_id: str):
    """Check equipment temperature."""
    try:
        temperature = await diagnostics_manager.check_temperature(equipment_id)

        return {
            "success": True,
            "equipment_id": equipment_id,
            "temperature_celsius": temperature,
            "supported": temperature is not None,
        }

    except Exception as e:
        logger.error(f"Error checking temperature: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to check temperature: {str(e)}"
        )


@router.get("/diagnostics/errors/{equipment_id}", summary="Check equipment error codes")
async def check_equipment_errors(equipment_id: str):
    """Check equipment error codes and get interpretation."""
    try:
        error_info = await diagnostics_manager.check_error_codes(equipment_id)

        return {"success": True, "equipment_id": equipment_id, **error_info}

    except Exception as e:
        logger.error(f"Error checking error codes: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to check error codes: {str(e)}"
        )


@router.post("/diagnostics/self-test/{equipment_id}", summary="Run self-test")
async def run_equipment_self_test(equipment_id: str):
    """Run equipment built-in self-test (BIST)."""
    try:
        result = await diagnostics_manager.run_self_test(equipment_id)

        return {"success": True, "test_result": result.dict()}

    except Exception as e:
        logger.error(f"Error running self-test: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to run self-test: {str(e)}"
        )


@router.get(
    "/diagnostics/calibration/{equipment_id}", summary="Check calibration status"
)
async def check_calibration_status(equipment_id: str):
    """Check equipment calibration status."""
    try:
        cal_status = await diagnostics_manager.check_calibration_status(equipment_id)

        return {"success": True, "equipment_id": equipment_id, **cal_status}

    except Exception as e:
        logger.error(f"Error checking calibration status: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to check calibration: {str(e)}"
        )


@router.get(
    "/diagnostics/comprehensive/{equipment_id}", summary="Get comprehensive diagnostics"
)
async def get_comprehensive_diagnostics(equipment_id: str):
    """Get all diagnostic information for equipment (temperature, errors, calibration, etc.)."""
    try:
        diagnostics = await diagnostics_manager.get_equipment_diagnostics(equipment_id)

        return {"success": True, **diagnostics}

    except Exception as e:
        logger.error(f"Error getting comprehensive diagnostics: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get diagnostics: {str(e)}"
        )


# ==================== Statistics Recording ====================


@router.post(
    "/diagnostics/stats/connection/{equipment_id}", summary="Record connection"
)
async def record_connection_event(equipment_id: str):
    """Record equipment connection event."""
    diagnostics_manager.record_connection(equipment_id)

    return {"success": True, "message": "Connection event recorded"}


@router.post(
    "/diagnostics/stats/disconnection/{equipment_id}", summary="Record disconnection"
)
async def record_disconnection_event(equipment_id: str, error: Optional[str] = None):
    """Record equipment disconnection event."""
    diagnostics_manager.record_disconnection(equipment_id, error)

    return {"success": True, "message": "Disconnection event recorded"}


# ==================== System Diagnostics Script ====================


@router.post("/diagnostics/pi-diagnostics", summary="Run Pi diagnostic script")
async def run_pi_diagnostics():
    """Run comprehensive Raspberry Pi diagnostic script on the host system.

    This endpoint executes the diagnose-pi.sh script ON THE HOST (not in container) to check:
    - System information
    - Network status
    - Docker status
    - LabLink installation
    - Service status
    - Container status
    - Port listeners
    - Recent logs

    The script runs on the host using Docker API and nsenter to break out of
    the container's isolation and access the actual Pi's system.

    Returns:
        Script output and recommendations
    """
    import asyncio
    from pathlib import Path

    try:
        # Verify /opt/lablink is mounted (this is only available on Pi deployments)
        lablink_dir = Path("/opt/lablink")
        if not lablink_dir.exists():
            raise HTTPException(
                status_code=503,
                detail="Pi diagnostics only available on Raspberry Pi deployments. "
                       "/opt/lablink directory not found (not mounted in docker-compose.yml)"
            )

        # Verify script exists on host (mounted at /opt/lablink)
        script_path = lablink_dir / "diagnose-pi.sh"
        if not script_path.exists():
            raise HTTPException(
                status_code=404,
                detail="Diagnostic script not found at /opt/lablink/diagnose-pi.sh on host. "
                       "Please ensure the script is installed on the Pi."
            )

        # Use Docker API to run the script on the host
        # We run in a separate thread to avoid blocking the async event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _run_diagnostic_on_host, str(script_path))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running Pi diagnostics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to run diagnostics: {str(e)}"
        )


def _run_diagnostic_on_host(script_path: str) -> dict:
    """Execute diagnostic script on the host system using Docker API.

    This function uses the Docker Python API to run a privileged container that:
    1. Shares the host's PID namespace (pid_mode='host')
    2. Uses nsenter to enter the host's mount namespace
    3. Executes the diagnostic script in the host's context

    Args:
        script_path: Path to the diagnostic script on the host

    Returns:
        Dict with success status, output, and return code
    """
    import docker

    try:
        client = docker.from_env()

        # Run a privileged Alpine container that uses nsenter to execute the script
        # on the actual host (not in container isolation)
        #
        # Explanation of the command:
        # - nsenter enters the namespaces of another process (PID 1 = host init)
        # - --target 1: Target PID 1 (the host's init process)
        # - --mount: Enter the host's mount namespace (filesystem)
        # - --uts: Enter the host's UTS namespace (hostname)
        # - --ipc: Enter the host's IPC namespace
        # - --net: Enter the host's network namespace
        # - --pid: Enter the host's PID namespace
        # - Then execute the script in that context
        container_output = client.containers.run(
            image="alpine:latest",
            command=[
                "nsenter", "--target", "1",
                "--mount", "--uts", "--ipc", "--net", "--pid",
                "--", "/bin/sh", script_path
            ],
            remove=True,
            privileged=True,
            pid_mode="host",
            stdout=True,
            stderr=True,
            detach=False
        )

        # Decode output
        output = container_output.decode('utf-8', errors='replace')

        return {
            "success": True,
            "output": output,
            "return_code": 0,
            "script_path": script_path
        }

    except docker.errors.ContainerError as e:
        # Container exited with non-zero code
        # Handle both bytes and string stderr
        if e.stderr:
            if isinstance(e.stderr, bytes):
                output = e.stderr.decode('utf-8', errors='replace')
            else:
                output = str(e.stderr)
        else:
            output = str(e)

        return {
            "success": False,
            "output": output,
            "return_code": e.exit_status,
            "script_path": script_path
        }
    except docker.errors.ImageNotFound:
        raise HTTPException(
            status_code=500,
            detail="Alpine Docker image not found. Please pull alpine:latest first."
        )
    except docker.errors.APIError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Docker API error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error running diagnostic on host: {str(e)}"
        )
