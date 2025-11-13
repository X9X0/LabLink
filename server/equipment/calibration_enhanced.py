"""Enhanced calibration management features.

Extends the base calibration system with:
- Calibration procedures and workflows
- Certificate management
- Calibration corrections
- Reference standards tracking
"""

import logging
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from enum import Enum
from pydantic import BaseModel, Field
import uuid
import numpy as np
from pathlib import Path
import json

logger = logging.getLogger(__name__)


# ==================== Calibration Procedures ====================


class ProcedureStepType(str, Enum):
    """Type of procedure step."""
    SETUP = "setup"
    MEASUREMENT = "measurement"
    ADJUSTMENT = "adjustment"
    VERIFICATION = "verification"
    DOCUMENTATION = "documentation"


class ProcedureStepStatus(str, Enum):
    """Status of procedure step."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class CalibrationProcedureStep(BaseModel):
    """Single step in a calibration procedure."""
    step_id: str = Field(default_factory=lambda: f"step_{uuid.uuid4().hex[:8]}")
    step_number: int = Field(..., description="Step number in sequence")
    step_type: ProcedureStepType
    title: str = Field(..., description="Step title")
    description: str = Field(..., description="Detailed instructions")

    # Parameters
    required_equipment: List[str] = Field(default_factory=list)
    required_standards: List[str] = Field(default_factory=list)
    expected_range: Optional[Dict[str, float]] = None  # min, max, nominal
    tolerance: Optional[float] = None

    # Execution
    status: ProcedureStepStatus = ProcedureStepStatus.PENDING
    measured_value: Optional[float] = None
    adjusted_value: Optional[float] = None
    passed: Optional[bool] = None
    notes: Optional[str] = None
    completed_at: Optional[datetime] = None
    completed_by: Optional[str] = None


class CalibrationProcedure(BaseModel):
    """Complete calibration procedure with steps."""
    procedure_id: str = Field(default_factory=lambda: f"proc_{uuid.uuid4().hex[:8]}")
    name: str = Field(..., description="Procedure name")
    version: str = Field(default="1.0", description="Procedure version")
    equipment_type: str = Field(..., description="Applicable equipment type")

    # Procedure steps
    steps: List[CalibrationProcedureStep] = Field(default_factory=list)

    # Requirements
    required_standards: List[str] = Field(default_factory=list)
    required_tools: List[str] = Field(default_factory=list)
    estimated_duration_minutes: int = Field(default=60)

    # Environmental requirements
    temp_range: Optional[Dict[str, float]] = None  # min, max
    humidity_range: Optional[Dict[str, float]] = None

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    created_by: str = Field(default="system")
    approved: bool = Field(default=False)
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


class ProcedureExecution(BaseModel):
    """Execution instance of a calibration procedure."""
    execution_id: str = Field(default_factory=lambda: f"exec_{uuid.uuid4().hex[:12]}")
    procedure_id: str
    equipment_id: str

    # Execution state
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    status: str = Field(default="in_progress")  # in_progress, completed, failed, aborted

    # Steps (copy of procedure steps with execution data)
    steps: List[CalibrationProcedureStep] = Field(default_factory=list)
    current_step: int = 0

    # Results
    overall_result: Optional[str] = None
    performed_by: str = Field(..., description="Technician performing calibration")
    notes: Optional[str] = None


# ==================== Calibration Certificates ====================


class CertificateType(str, Enum):
    """Type of calibration certificate."""
    ACCREDITED = "accredited"  # ISO/IEC 17025 accredited
    NON_ACCREDITED = "non_accredited"
    IN_HOUSE = "in_house"
    FACTORY = "factory"


class CalibrationCertificate(BaseModel):
    """Digital calibration certificate."""
    certificate_id: str = Field(default_factory=lambda: f"cert_{uuid.uuid4().hex[:12]}")
    certificate_number: str = Field(..., description="Official certificate number")
    certificate_type: CertificateType

    # Equipment information
    equipment_id: str
    equipment_model: str
    equipment_serial: str
    manufacturer: str

    # Calibration information
    calibration_date: datetime
    due_date: datetime
    performed_by: str
    organization: str
    accreditation: Optional[str] = None  # e.g., "ISO/IEC 17025:2017"

    # Calibration data
    calibration_points: List[Dict[str, Any]] = Field(default_factory=list)
    uncertainty_values: Dict[str, float] = Field(default_factory=dict)
    reference_standards: List[Dict[str, str]] = Field(default_factory=list)

    # Environmental conditions
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None

    # Files
    pdf_path: Optional[str] = None
    attachments: List[str] = Field(default_factory=list)

    # Digital signature (optional)
    signed: bool = False
    signature_data: Optional[str] = None
    signature_timestamp: Optional[datetime] = None

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    notes: Optional[str] = None


# ==================== Calibration Corrections ====================


class CorrectionType(str, Enum):
    """Type of calibration correction."""
    LINEAR = "linear"  # y = mx + b
    POLYNOMIAL = "polynomial"  # y = a0 + a1*x + a2*x^2 + ...
    LOOKUP_TABLE = "lookup_table"  # Interpolated from table
    CUSTOM = "custom"  # Custom correction function


class CalibrationCorrection(BaseModel):
    """Calibration correction to apply to measurements."""
    correction_id: str = Field(default_factory=lambda: f"corr_{uuid.uuid4().hex[:8]}")
    equipment_id: str
    parameter: str = Field(..., description="Parameter to correct (e.g., 'voltage', 'current')")

    # Correction method
    correction_type: CorrectionType
    coefficients: List[float] = Field(default_factory=list)  # For linear/polynomial
    lookup_table: Optional[Dict[float, float]] = None  # For table-based
    custom_function: Optional[str] = None  # Python expression

    # Validity
    valid_from: datetime = Field(default_factory=datetime.now)
    valid_until: datetime
    range_min: Optional[float] = None
    range_max: Optional[float] = None

    # Uncertainty
    uncertainty_percent: float = 0.0
    uncertainty_absolute: float = 0.0

    # Metadata
    calibration_id: Optional[str] = None  # Link to calibration record
    created_at: datetime = Field(default_factory=datetime.now)
    created_by: str = Field(default="system")
    enabled: bool = True
    notes: Optional[str] = None

    def apply_correction(self, value: float) -> float:
        """Apply correction to a measured value.

        Args:
            value: Raw measured value

        Returns:
            Corrected value
        """
        if not self.enabled:
            return value

        # Check range
        if self.range_min is not None and value < self.range_min:
            logger.warning(f"Value {value} below correction range [{self.range_min}, {self.range_max}]")
            return value
        if self.range_max is not None and value > self.range_max:
            logger.warning(f"Value {value} above correction range [{self.range_min}, {self.range_max}]")
            return value

        if self.correction_type == CorrectionType.LINEAR:
            if len(self.coefficients) >= 2:
                m, b = self.coefficients[0], self.coefficients[1]
                return m * value + b
            return value

        elif self.correction_type == CorrectionType.POLYNOMIAL:
            corrected = 0.0
            for i, coeff in enumerate(self.coefficients):
                corrected += coeff * (value ** i)
            return corrected

        elif self.correction_type == CorrectionType.LOOKUP_TABLE:
            if not self.lookup_table:
                return value
            # Linear interpolation
            keys = sorted(self.lookup_table.keys())
            if value <= keys[0]:
                return self.lookup_table[keys[0]]
            if value >= keys[-1]:
                return self.lookup_table[keys[-1]]
            # Find surrounding points
            for i in range(len(keys) - 1):
                if keys[i] <= value <= keys[i + 1]:
                    x0, x1 = keys[i], keys[i + 1]
                    y0, y1 = self.lookup_table[x0], self.lookup_table[x1]
                    return y0 + (y1 - y0) * (value - x0) / (x1 - x0)
            return value

        elif self.correction_type == CorrectionType.CUSTOM:
            if self.custom_function:
                try:
                    # Safe evaluation with numpy
                    result = eval(self.custom_function, {"np": np, "x": value})
                    return float(result)
                except Exception as e:
                    logger.error(f"Error applying custom correction: {e}")
                    return value
            return value

        return value


# ==================== Reference Standards ====================


class StandardStatus(str, Enum):
    """Status of reference standard."""
    CURRENT = "current"
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"
    RETIRED = "retired"


class ReferenceStandard(BaseModel):
    """Reference standard used for calibration."""
    standard_id: str = Field(default_factory=lambda: f"std_{uuid.uuid4().hex[:8]}")
    name: str = Field(..., description="Standard name/designation")
    standard_type: str = Field(..., description="Type (e.g., 'voltage', 'resistance')")

    # Identification
    manufacturer: str
    model: str
    serial_number: str
    asset_number: Optional[str] = None

    # Specifications
    nominal_value: float
    unit: str
    accuracy: float = Field(..., description="Accuracy specification")
    uncertainty: float = Field(..., description="Measurement uncertainty")

    # Calibration
    calibration_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    calibration_interval_days: int = 365
    calibration_certificate: Optional[str] = None
    traceability: str = Field(..., description="Traceability chain (e.g., 'NIST')")

    # Usage tracking
    usage_count: int = 0
    last_used: Optional[datetime] = None
    max_usage_count: Optional[int] = None

    # Maintenance
    maintenance_history: List[Dict[str, Any]] = Field(default_factory=list)
    condition: str = Field(default="good")  # good, fair, poor

    # Storage
    storage_location: Optional[str] = None
    environmental_requirements: Dict[str, Any] = Field(default_factory=dict)

    # Metadata
    status: StandardStatus = StandardStatus.CURRENT
    acquired_date: Optional[datetime] = None
    purchase_cost: Optional[float] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)

    def get_status(self) -> StandardStatus:
        """Get current status based on due date."""
        if not self.due_date:
            return StandardStatus.CURRENT

        now = datetime.now()
        if now > self.due_date:
            return StandardStatus.OVERDUE
        elif (self.due_date - now).days <= 30:
            return StandardStatus.DUE_SOON
        return StandardStatus.CURRENT

    def record_usage(self):
        """Record usage of this standard."""
        self.usage_count += 1
        self.last_used = datetime.now()


# ==================== Enhanced Calibration Manager ====================


class EnhancedCalibrationManager:
    """Enhanced calibration manager with procedures, certificates, corrections, and standards."""

    def __init__(self, storage_path: str = "data/calibration_enhanced"):
        """Initialize enhanced calibration manager."""
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Storage
        self.procedures: Dict[str, CalibrationProcedure] = {}
        self.executions: Dict[str, ProcedureExecution] = {}
        self.certificates: Dict[str, CalibrationCertificate] = {}
        self.corrections: Dict[str, List[CalibrationCorrection]] = {}  # equipment_id -> corrections
        self.standards: Dict[str, ReferenceStandard] = {}

        # Load data
        self._load_all_data()

        logger.info("Enhanced calibration manager initialized")

    # ==================== Procedures ====================

    def create_procedure(self, procedure: CalibrationProcedure) -> str:
        """Create a new calibration procedure."""
        self.procedures[procedure.procedure_id] = procedure
        self._save_procedure(procedure.procedure_id)
        logger.info(f"Created calibration procedure: {procedure.name}")
        return procedure.procedure_id

    def start_procedure_execution(
        self,
        procedure_id: str,
        equipment_id: str,
        performed_by: str
    ) -> ProcedureExecution:
        """Start executing a calibration procedure."""
        if procedure_id not in self.procedures:
            raise ValueError(f"Procedure {procedure_id} not found")

        procedure = self.procedures[procedure_id]

        # Create execution instance
        execution = ProcedureExecution(
            procedure_id=procedure_id,
            equipment_id=equipment_id,
            performed_by=performed_by,
            steps=[step.copy() for step in procedure.steps]  # Copy steps
        )

        self.executions[execution.execution_id] = execution
        self._save_execution(execution.execution_id)

        logger.info(f"Started procedure execution {execution.execution_id}")
        return execution

    def complete_step(
        self,
        execution_id: str,
        step_number: int,
        measured_value: Optional[float] = None,
        passed: bool = True,
        notes: Optional[str] = None
    ):
        """Complete a procedure step."""
        if execution_id not in self.executions:
            raise ValueError(f"Execution {execution_id} not found")

        execution = self.executions[execution_id]

        for step in execution.steps:
            if step.step_number == step_number:
                step.status = ProcedureStepStatus.COMPLETED
                step.measured_value = measured_value
                step.passed = passed
                step.notes = notes
                step.completed_at = datetime.now()
                break

        execution.current_step = step_number
        self._save_execution(execution_id)

    # ==================== Certificates ====================

    def create_certificate(self, certificate: CalibrationCertificate) -> str:
        """Create a calibration certificate."""
        self.certificates[certificate.certificate_id] = certificate
        self._save_certificate(certificate.certificate_id)
        logger.info(f"Created certificate: {certificate.certificate_number}")
        return certificate.certificate_id

    def get_certificate(self, certificate_id: str) -> Optional[CalibrationCertificate]:
        """Get a calibration certificate."""
        return self.certificates.get(certificate_id)

    # ==================== Corrections ====================

    def add_correction(self, correction: CalibrationCorrection):
        """Add a calibration correction."""
        equipment_id = correction.equipment_id
        if equipment_id not in self.corrections:
            self.corrections[equipment_id] = []

        self.corrections[equipment_id].append(correction)
        self._save_corrections(equipment_id)
        logger.info(f"Added correction for {equipment_id}: {correction.parameter}")

    def apply_corrections(self, equipment_id: str, parameter: str, value: float) -> float:
        """Apply all applicable corrections to a measured value."""
        if equipment_id not in self.corrections:
            return value

        corrected_value = value
        now = datetime.now()

        for correction in self.corrections[equipment_id]:
            # Check if correction is applicable
            if (correction.parameter == parameter and
                correction.enabled and
                correction.valid_from <= now <= correction.valid_until):
                corrected_value = correction.apply_correction(corrected_value)

        return corrected_value

    # ==================== Reference Standards ====================

    def add_standard(self, standard: ReferenceStandard) -> str:
        """Add a reference standard."""
        self.standards[standard.standard_id] = standard
        self._save_standard(standard.standard_id)
        logger.info(f"Added reference standard: {standard.name}")
        return standard.standard_id

    def use_standard(self, standard_id: str):
        """Record usage of a standard."""
        if standard_id in self.standards:
            self.standards[standard_id].record_usage()
            self._save_standard(standard_id)

    def get_due_standards(self, days: int = 30) -> List[ReferenceStandard]:
        """Get standards due for calibration within specified days."""
        due_standards = []
        cutoff = datetime.now() + timedelta(days=days)

        for standard in self.standards.values():
            if standard.due_date and standard.due_date <= cutoff:
                due_standards.append(standard)

        return due_standards

    # ==================== Persistence ====================

    def _load_all_data(self):
        """Load all data from storage."""
        # Implement loading from JSON files
        pass

    def _save_procedure(self, procedure_id: str):
        """Save procedure to storage."""
        path = self.storage_path / "procedures" / f"{procedure_id}.json"
        path.parent.mkdir(exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.procedures[procedure_id].dict(), f, indent=2, default=str)

    def _save_execution(self, execution_id: str):
        """Save execution to storage."""
        path = self.storage_path / "executions" / f"{execution_id}.json"
        path.parent.mkdir(exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.executions[execution_id].dict(), f, indent=2, default=str)

    def _save_certificate(self, certificate_id: str):
        """Save certificate to storage."""
        path = self.storage_path / "certificates" / f"{certificate_id}.json"
        path.parent.mkdir(exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.certificates[certificate_id].dict(), f, indent=2, default=str)

    def _save_corrections(self, equipment_id: str):
        """Save corrections to storage."""
        path = self.storage_path / "corrections" / f"{equipment_id}.json"
        path.parent.mkdir(exist_ok=True)
        with open(path, 'w') as f:
            corrections_data = [c.dict() for c in self.corrections[equipment_id]]
            json.dump(corrections_data, f, indent=2, default=str)

    def _save_standard(self, standard_id: str):
        """Save standard to storage."""
        path = self.storage_path / "standards" / f"{standard_id}.json"
        path.parent.mkdir(exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.standards[standard_id].dict(), f, indent=2, default=str)


# Global instance
_enhanced_calibration_manager = None


def initialize_enhanced_calibration_manager(storage_path: str = "data/calibration_enhanced") -> EnhancedCalibrationManager:
    """Initialize the global enhanced calibration manager."""
    global _enhanced_calibration_manager
    _enhanced_calibration_manager = EnhancedCalibrationManager(storage_path)
    return _enhanced_calibration_manager


def get_enhanced_calibration_manager() -> EnhancedCalibrationManager:
    """Get the global enhanced calibration manager."""
    if _enhanced_calibration_manager is None:
        raise RuntimeError("Enhanced calibration manager not initialized")
    return _enhanced_calibration_manager
