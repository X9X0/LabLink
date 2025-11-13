"""API endpoints for automated test sequences."""

from fastapi import APIRouter, HTTPException
from typing import List, Optional
from datetime import datetime

from testing import (
    get_test_executor,
    TestSequence,
    TestStep,
    TestExecution,
    TestStatus,
)
from testing.templates import TestTemplateLibrary

router = APIRouter(prefix="/api/testing", tags=["testing"])


# ==================== Test Sequences ====================


@router.post("/sequences")
async def create_test_sequence(sequence: TestSequence):
    """Create a new test sequence."""
    # In production, save to database
    return {"sequence_id": sequence.sequence_id, "message": "Test sequence created"}


@router.get("/sequences/{sequence_id}")
async def get_test_sequence(sequence_id: str):
    """Get a test sequence by ID."""
    raise HTTPException(status_code=404, detail="Sequence not found")


@router.get("/templates")
async def list_test_templates():
    """List available test templates."""
    templates = TestTemplateLibrary.get_all_templates()
    return {"templates": templates}


@router.post("/templates/{template_name}")
async def create_from_template(
    template_name: str,
    equipment_id: str,
    test_points: Optional[List[float]] = None,
    start_freq: Optional[float] = None,
    stop_freq: Optional[float] = None,
):
    """Create test sequence from template."""
    try:
        if template_name == "voltage_accuracy":
            if not test_points:
                raise ValueError("test_points required for voltage_accuracy template")
            sequence = TestTemplateLibrary.voltage_accuracy_test(equipment_id, test_points)
        elif template_name == "frequency_response":
            if not start_freq or not stop_freq:
                raise ValueError("start_freq and stop_freq required")
            sequence = TestTemplateLibrary.frequency_response_sweep(equipment_id, start_freq, stop_freq)
        else:
            raise HTTPException(status_code=404, detail=f"Template not found: {template_name}")

        return sequence
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== Test Execution ====================


@router.post("/execute")
async def execute_test_sequence(
    sequence: TestSequence,
    executed_by: str,
    environment: Optional[dict] = None
):
    """Execute a test sequence."""
    try:
        executor = get_test_executor()
        execution = await executor.execute_sequence(sequence, executed_by, environment)
        return {"execution_id": execution.execution_id, "status": execution.status}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions/{execution_id}")
async def get_execution_status(execution_id: str):
    """Get status of a test execution."""
    try:
        executor = get_test_executor()
        execution = executor.get_execution(execution_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")
        return execution
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/executions/{execution_id}/abort")
async def abort_test_execution(execution_id: str):
    """Abort a running test execution."""
    try:
        executor = get_test_executor()
        executor.abort_test(execution_id)
        return {"message": "Abort requested"}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/executions/active")
async def get_active_executions():
    """Get all active test executions."""
    try:
        executor = get_test_executor()
        active = executor.get_active_executions()
        return {"count": len(active), "executions": list(active.values())}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


# ==================== Utility ====================


@router.get("/info")
async def get_testing_info():
    """Get information about the test automation system."""
    return {
        "features": {
            "sequences": "Create and manage automated test sequences",
            "execution": "Execute tests with real-time progress tracking",
            "templates": "Pre-built templates for common tests",
            "sweeps": "Parameter sweeping for characterization",
            "validation": "Pass/fail criteria validation",
            "archival": "Test result archival and trending"
        },
        "step_types": [
            "setup", "command", "measurement", "delay",
            "validation", "sweep", "conditional", "loop", "cleanup"
        ],
        "templates": TestTemplateLibrary.get_all_templates(),
    }
