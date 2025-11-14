"""API endpoints for enhanced calibration management."""

from datetime import datetime, timedelta
from typing import List, Optional

from equipment.calibration_enhanced import (CalibrationCertificate,
                                            CalibrationCorrection,
                                            CalibrationProcedure,
                                            ProcedureExecution,
                                            ReferenceStandard,
                                            get_enhanced_calibration_manager)
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/calibration", tags=["calibration-enhanced"])


# ==================== Procedures ====================


@router.post("/procedures")
async def create_calibration_procedure(procedure: CalibrationProcedure):
    """Create a new calibration procedure.

    Calibration procedures define step-by-step workflows for calibrating equipment.
    """
    try:
        manager = get_enhanced_calibration_manager()
        procedure_id = manager.create_procedure(procedure)
        return {
            "procedure_id": procedure_id,
            "message": "Procedure created successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/procedures")
async def list_calibration_procedures():
    """List all calibration procedures."""
    try:
        manager = get_enhanced_calibration_manager()
        return {"procedures": list(manager.procedures.values())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/procedures/{procedure_id}")
async def get_calibration_procedure(procedure_id: str):
    """Get a specific calibration procedure."""
    try:
        manager = get_enhanced_calibration_manager()
        if procedure_id not in manager.procedures:
            raise HTTPException(status_code=404, detail="Procedure not found")
        return manager.procedures[procedure_id]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/executions/start")
async def start_procedure_execution(
    procedure_id: str, equipment_id: str, performed_by: str
):
    """Start executing a calibration procedure."""
    try:
        manager = get_enhanced_calibration_manager()
        execution = manager.start_procedure_execution(
            procedure_id, equipment_id, performed_by
        )
        return {
            "execution_id": execution.execution_id,
            "message": "Procedure execution started",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/executions/{execution_id}/step")
async def complete_procedure_step(
    execution_id: str,
    step_number: int,
    measured_value: Optional[float] = None,
    passed: bool = True,
    notes: Optional[str] = None,
):
    """Complete a step in a procedure execution."""
    try:
        manager = get_enhanced_calibration_manager()
        manager.complete_step(execution_id, step_number, measured_value, passed, notes)
        return {"message": "Step completed successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions/{execution_id}")
async def get_procedure_execution(execution_id: str):
    """Get status of a procedure execution."""
    try:
        manager = get_enhanced_calibration_manager()
        if execution_id not in manager.executions:
            raise HTTPException(status_code=404, detail="Execution not found")
        return manager.executions[execution_id]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Certificates ====================


@router.post("/certificates")
async def create_calibration_certificate(certificate: CalibrationCertificate):
    """Create a calibration certificate.

    Certificates provide official documentation of calibration results
    with traceability to national standards.
    """
    try:
        manager = get_enhanced_calibration_manager()
        certificate_id = manager.create_certificate(certificate)
        return {
            "certificate_id": certificate_id,
            "message": "Certificate created successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/certificates/{certificate_id}")
async def get_calibration_certificate(certificate_id: str):
    """Get a calibration certificate."""
    try:
        manager = get_enhanced_calibration_manager()
        certificate = manager.get_certificate(certificate_id)
        if not certificate:
            raise HTTPException(status_code=404, detail="Certificate not found")
        return certificate
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/certificates")
async def list_calibration_certificates():
    """List all calibration certificates."""
    try:
        manager = get_enhanced_calibration_manager()
        return {"certificates": list(manager.certificates.values())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Corrections ====================


@router.post("/corrections")
async def add_calibration_correction(correction: CalibrationCorrection):
    """Add a calibration correction.

    Corrections are mathematical adjustments applied to measurements
    to compensate for known systematic errors.
    """
    try:
        manager = get_enhanced_calibration_manager()
        manager.add_correction(correction)
        return {"message": "Correction added successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/corrections/{equipment_id}")
async def get_equipment_corrections(equipment_id: str):
    """Get all calibration corrections for an equipment."""
    try:
        manager = get_enhanced_calibration_manager()
        corrections = manager.corrections.get(equipment_id, [])
        return {"equipment_id": equipment_id, "corrections": corrections}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/corrections/apply")
async def apply_calibration_corrections(
    equipment_id: str, parameter: str, value: float
):
    """Apply calibration corrections to a measured value.

    Returns the corrected value after applying all applicable corrections.
    """
    try:
        manager = get_enhanced_calibration_manager()
        corrected_value = manager.apply_corrections(equipment_id, parameter, value)
        return {
            "equipment_id": equipment_id,
            "parameter": parameter,
            "raw_value": value,
            "corrected_value": corrected_value,
            "correction_applied": abs(corrected_value - value) > 1e-10,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Reference Standards ====================


@router.post("/standards")
async def add_reference_standard(standard: ReferenceStandard):
    """Add a reference standard.

    Reference standards are precision instruments used as references
    for calibrating equipment.
    """
    try:
        manager = get_enhanced_calibration_manager()
        standard_id = manager.add_standard(standard)
        return {"standard_id": standard_id, "message": "Standard added successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/standards")
async def list_reference_standards():
    """List all reference standards."""
    try:
        manager = get_enhanced_calibration_manager()
        return {"standards": list(manager.standards.values())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/standards/{standard_id}")
async def get_reference_standard(standard_id: str):
    """Get a specific reference standard."""
    try:
        manager = get_enhanced_calibration_manager()
        if standard_id not in manager.standards:
            raise HTTPException(status_code=404, detail="Standard not found")
        return manager.standards[standard_id]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/standards/{standard_id}/use")
async def record_standard_usage(standard_id: str):
    """Record usage of a reference standard."""
    try:
        manager = get_enhanced_calibration_manager()
        manager.use_standard(standard_id)
        return {"message": "Standard usage recorded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/standards/due")
async def get_due_standards(days: int = 30):
    """Get reference standards due for calibration.

    Returns standards that need calibration within the specified number of days.
    """
    try:
        manager = get_enhanced_calibration_manager()
        due_standards = manager.get_due_standards(days)
        return {"days": days, "count": len(due_standards), "standards": due_standards}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Utility Endpoints ====================


@router.get("/info")
async def get_calibration_info():
    """Get information about the enhanced calibration system."""
    return {
        "features": {
            "procedures": "Step-by-step calibration workflows",
            "certificates": "Digital calibration certificates with traceability",
            "corrections": "Mathematical corrections for systematic errors",
            "standards": "Reference standards management and tracking",
        },
        "correction_types": ["linear", "polynomial", "lookup_table", "custom"],
        "procedure_step_types": [
            "setup",
            "measurement",
            "adjustment",
            "verification",
            "documentation",
        ],
        "certificate_types": ["accredited", "non_accredited", "in_house", "factory"],
    }
