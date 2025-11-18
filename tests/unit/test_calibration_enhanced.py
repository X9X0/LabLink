"""
Comprehensive tests for the enhanced calibration module.

Tests cover:
- Procedure enums (ProcedureStepType, ProcedureStepStatus, CertificateType, etc.)
- CalibrationProcedureStep and CalibrationProcedure models
- ProcedureExecution model and workflow
- CalibrationCertificate model
- CalibrationCorrection model and all correction types
- ReferenceStandard model and status tracking
- EnhancedCalibrationManager class
"""

import pytest
import tempfile
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from server.equipment.calibration_enhanced import (
    ProcedureStepType,
    ProcedureStepStatus,
    CertificateType,
    CorrectionType,
    StandardStatus,
    CalibrationProcedureStep,
    CalibrationProcedure,
    ProcedureExecution,
    CalibrationCertificate,
    CalibrationCorrection,
    ReferenceStandard,
    EnhancedCalibrationManager,
    initialize_enhanced_calibration_manager,
    get_enhanced_calibration_manager,
)


class TestProcedureEnums:
    """Test procedure-related enumerations."""

    def test_procedure_step_type_values(self):
        """Test ProcedureStepType enum values."""
        assert ProcedureStepType.SETUP == "setup"
        assert ProcedureStepType.MEASUREMENT == "measurement"
        assert ProcedureStepType.ADJUSTMENT == "adjustment"
        assert ProcedureStepType.VERIFICATION == "verification"
        assert ProcedureStepType.DOCUMENTATION == "documentation"

    def test_procedure_step_status_values(self):
        """Test ProcedureStepStatus enum values."""
        assert ProcedureStepStatus.PENDING == "pending"
        assert ProcedureStepStatus.IN_PROGRESS == "in_progress"
        assert ProcedureStepStatus.COMPLETED == "completed"
        assert ProcedureStepStatus.FAILED == "failed"
        assert ProcedureStepStatus.SKIPPED == "skipped"

    def test_certificate_type_values(self):
        """Test CertificateType enum values."""
        assert CertificateType.ACCREDITED == "accredited"
        assert CertificateType.NON_ACCREDITED == "non_accredited"
        assert CertificateType.IN_HOUSE == "in_house"
        assert CertificateType.FACTORY == "factory"

    def test_correction_type_values(self):
        """Test CorrectionType enum values."""
        assert CorrectionType.LINEAR == "linear"
        assert CorrectionType.POLYNOMIAL == "polynomial"
        assert CorrectionType.LOOKUP_TABLE == "lookup_table"
        assert CorrectionType.CUSTOM == "custom"

    def test_standard_status_values(self):
        """Test StandardStatus enum values."""
        assert StandardStatus.CURRENT == "current"
        assert StandardStatus.DUE_SOON == "due_soon"
        assert StandardStatus.OVERDUE == "overdue"
        assert StandardStatus.RETIRED == "retired"


class TestCalibrationProcedureStep:
    """Test CalibrationProcedureStep model."""

    def test_minimal_procedure_step(self):
        """Test creating minimal procedure step."""
        step = CalibrationProcedureStep(
            step_number=1,
            step_type=ProcedureStepType.SETUP,
            title="Initial Setup",
            description="Connect equipment and warm up for 30 minutes"
        )

        assert step.step_number == 1
        assert step.step_type == ProcedureStepType.SETUP
        assert step.title == "Initial Setup"
        assert step.status == ProcedureStepStatus.PENDING
        assert step.step_id.startswith("step_")

    def test_procedure_step_with_requirements(self):
        """Test procedure step with equipment and standards requirements."""
        step = CalibrationProcedureStep(
            step_number=2,
            step_type=ProcedureStepType.MEASUREMENT,
            title="Voltage Measurement",
            description="Measure voltage at 5V setpoint",
            required_equipment=["DMM", "Power Supply"],
            required_standards=["Fluke 5720A"],
            expected_range={"min": 4.99, "max": 5.01, "nominal": 5.0},
            tolerance=0.01
        )

        assert len(step.required_equipment) == 2
        assert "DMM" in step.required_equipment
        assert len(step.required_standards) == 1
        assert step.expected_range["nominal"] == 5.0
        assert step.tolerance == 0.01

    def test_procedure_step_completion(self):
        """Test marking procedure step as completed."""
        step = CalibrationProcedureStep(
            step_number=1,
            step_type=ProcedureStepType.MEASUREMENT,
            title="Test Measurement",
            description="Measure output"
        )

        step.status = ProcedureStepStatus.COMPLETED
        step.measured_value = 5.002
        step.passed = True
        step.notes = "Within tolerance"
        step.completed_at = datetime.now()
        step.completed_by = "Tech1"

        assert step.status == ProcedureStepStatus.COMPLETED
        assert step.measured_value == 5.002
        assert step.passed is True
        assert step.notes == "Within tolerance"
        assert step.completed_by == "Tech1"


class TestCalibrationProcedure:
    """Test CalibrationProcedure model."""

    def test_minimal_procedure(self):
        """Test creating minimal calibration procedure."""
        procedure = CalibrationProcedure(
            name="Voltage Calibration",
            equipment_type="power_supply"
        )

        assert procedure.name == "Voltage Calibration"
        assert procedure.equipment_type == "power_supply"
        assert procedure.version == "1.0"
        assert procedure.approved is False
        assert procedure.procedure_id.startswith("proc_")

    def test_procedure_with_steps(self):
        """Test procedure with multiple steps."""
        steps = [
            CalibrationProcedureStep(
                step_number=1,
                step_type=ProcedureStepType.SETUP,
                title="Setup",
                description="Initial setup"
            ),
            CalibrationProcedureStep(
                step_number=2,
                step_type=ProcedureStepType.MEASUREMENT,
                title="Measure",
                description="Take measurements"
            ),
            CalibrationProcedureStep(
                step_number=3,
                step_type=ProcedureStepType.VERIFICATION,
                title="Verify",
                description="Verify results"
            )
        ]

        procedure = CalibrationProcedure(
            name="Full Calibration",
            equipment_type="oscilloscope",
            steps=steps,
            required_standards=["Fluke 5720A", "Keysight 3458A"],
            required_tools=["BNC cables", "Terminator"],
            estimated_duration_minutes=120
        )

        assert len(procedure.steps) == 3
        assert procedure.steps[0].step_number == 1
        assert len(procedure.required_standards) == 2
        assert procedure.estimated_duration_minutes == 120

    def test_procedure_with_environmental_requirements(self):
        """Test procedure with environmental requirements."""
        procedure = CalibrationProcedure(
            name="Precision Calibration",
            equipment_type="multimeter",
            temp_range={"min": 20.0, "max": 25.0},
            humidity_range={"min": 30.0, "max": 60.0}
        )

        assert procedure.temp_range["min"] == 20.0
        assert procedure.humidity_range["max"] == 60.0

    def test_procedure_approval(self):
        """Test procedure approval workflow."""
        procedure = CalibrationProcedure(
            name="Approved Procedure",
            equipment_type="power_supply"
        )

        procedure.approved = True
        procedure.approved_by = "Lab Manager"
        procedure.approved_at = datetime.now()

        assert procedure.approved is True
        assert procedure.approved_by == "Lab Manager"
        assert isinstance(procedure.approved_at, datetime)


class TestProcedureExecution:
    """Test ProcedureExecution model."""

    def test_procedure_execution_creation(self):
        """Test creating procedure execution."""
        execution = ProcedureExecution(
            procedure_id="proc_12345678",
            equipment_id="SCOPE_001",
            performed_by="Tech1"
        )

        assert execution.procedure_id == "proc_12345678"
        assert execution.equipment_id == "SCOPE_001"
        assert execution.performed_by == "Tech1"
        assert execution.status == "in_progress"
        assert execution.current_step == 0
        assert execution.execution_id.startswith("exec_")

    def test_procedure_execution_with_steps(self):
        """Test execution with procedure steps."""
        steps = [
            CalibrationProcedureStep(
                step_number=1,
                step_type=ProcedureStepType.SETUP,
                title="Setup",
                description="Setup"
            ),
            CalibrationProcedureStep(
                step_number=2,
                step_type=ProcedureStepType.MEASUREMENT,
                title="Measure",
                description="Measure"
            )
        ]

        execution = ProcedureExecution(
            procedure_id="proc_12345678",
            equipment_id="PSU_001",
            performed_by="Tech2",
            steps=steps
        )

        assert len(execution.steps) == 2
        assert execution.steps[0].status == ProcedureStepStatus.PENDING

    def test_procedure_execution_completion(self):
        """Test completing procedure execution."""
        execution = ProcedureExecution(
            procedure_id="proc_12345678",
            equipment_id="LOAD_001",
            performed_by="Tech3"
        )

        execution.status = "completed"
        execution.completed_at = datetime.now()
        execution.overall_result = "pass"

        assert execution.status == "completed"
        assert isinstance(execution.completed_at, datetime)
        assert execution.overall_result == "pass"


class TestCalibrationCertificate:
    """Test CalibrationCertificate model."""

    def test_minimal_certificate(self):
        """Test creating minimal calibration certificate."""
        cert = CalibrationCertificate(
            certificate_number="CERT-2025-001",
            certificate_type=CertificateType.ACCREDITED,
            equipment_id="SCOPE_001",
            equipment_model="DS1054Z",
            equipment_serial="SN123456",
            manufacturer="Rigol",
            calibration_date=datetime.now(),
            due_date=datetime.now() + timedelta(days=365),
            performed_by="Cal Lab Tech",
            organization="Accredited Cal Lab"
        )

        assert cert.certificate_number == "CERT-2025-001"
        assert cert.certificate_type == CertificateType.ACCREDITED
        assert cert.equipment_id == "SCOPE_001"
        assert cert.manufacturer == "Rigol"
        assert cert.certificate_id.startswith("cert_")

    def test_certificate_with_calibration_data(self):
        """Test certificate with detailed calibration data."""
        cert = CalibrationCertificate(
            certificate_number="CERT-2025-002",
            certificate_type=CertificateType.ACCREDITED,
            equipment_id="PSU_001",
            equipment_model="E36312A",
            equipment_serial="SN789012",
            manufacturer="Keysight",
            calibration_date=datetime.now(),
            due_date=datetime.now() + timedelta(days=365),
            performed_by="Tech1",
            organization="ISO17025 Lab",
            accreditation="ISO/IEC 17025:2017",
            calibration_points=[
                {"setpoint": 5.0, "measured": 5.001, "error": 0.001},
                {"setpoint": 10.0, "measured": 10.002, "error": 0.002}
            ],
            uncertainty_values={"voltage": 0.0015, "current": 0.0005},
            reference_standards=[
                {"name": "Fluke 5720A", "cert": "CERT-STD-001"}
            ]
        )

        assert len(cert.calibration_points) == 2
        assert cert.calibration_points[0]["setpoint"] == 5.0
        assert cert.uncertainty_values["voltage"] == 0.0015
        assert len(cert.reference_standards) == 1
        assert cert.accreditation == "ISO/IEC 17025:2017"

    def test_certificate_with_environmental_data(self):
        """Test certificate with environmental conditions."""
        cert = CalibrationCertificate(
            certificate_number="CERT-2025-003",
            certificate_type=CertificateType.IN_HOUSE,
            equipment_id="DMM_001",
            equipment_model="34465A",
            equipment_serial="SN345678",
            manufacturer="Keysight",
            calibration_date=datetime.now(),
            due_date=datetime.now() + timedelta(days=365),
            performed_by="Tech2",
            organization="In-House Lab",
            temperature=23.5,
            humidity=45.0,
            pressure=1013.25
        )

        assert cert.temperature == 23.5
        assert cert.humidity == 45.0
        assert cert.pressure == 1013.25

    def test_certificate_with_signature(self):
        """Test certificate with digital signature."""
        cert = CalibrationCertificate(
            certificate_number="CERT-2025-004",
            certificate_type=CertificateType.ACCREDITED,
            equipment_id="SCOPE_002",
            equipment_model="RTB2004",
            equipment_serial="SN901234",
            manufacturer="Rohde & Schwarz",
            calibration_date=datetime.now(),
            due_date=datetime.now() + timedelta(days=365),
            performed_by="Tech3",
            organization="Accredited Lab",
            signed=True,
            signature_data="SHA256:abcdef123456",
            signature_timestamp=datetime.now()
        )

        assert cert.signed is True
        assert cert.signature_data == "SHA256:abcdef123456"
        assert isinstance(cert.signature_timestamp, datetime)


class TestCalibrationCorrection:
    """Test CalibrationCorrection model and correction functions."""

    def test_linear_correction(self):
        """Test linear correction (y = mx + b)."""
        correction = CalibrationCorrection(
            equipment_id="PSU_001",
            parameter="voltage",
            correction_type=CorrectionType.LINEAR,
            coefficients=[1.0, 0.05],  # y = 1.0*x + 0.05
            valid_from=datetime.now(),
            valid_until=datetime.now() + timedelta(days=365),
            enabled=True
        )

        # Test correction: value 5.0 should become 5.05
        corrected = correction.apply_correction(5.0)
        assert abs(corrected - 5.05) < 0.0001

    def test_polynomial_correction(self):
        """Test polynomial correction."""
        correction = CalibrationCorrection(
            equipment_id="PSU_001",
            parameter="voltage",
            correction_type=CorrectionType.POLYNOMIAL,
            coefficients=[0.1, 0.9, 0.01],  # y = 0.1 + 0.9*x + 0.01*x^2
            valid_from=datetime.now(),
            valid_until=datetime.now() + timedelta(days=365),
            enabled=True
        )

        # Test correction: 5.0 -> 0.1 + 0.9*5 + 0.01*25 = 0.1 + 4.5 + 0.25 = 4.85
        corrected = correction.apply_correction(5.0)
        assert abs(corrected - 4.85) < 0.0001

    def test_lookup_table_correction_exact_match(self):
        """Test lookup table correction with exact match."""
        correction = CalibrationCorrection(
            equipment_id="DMM_001",
            parameter="voltage",
            correction_type=CorrectionType.LOOKUP_TABLE,
            lookup_table={1.0: 1.002, 5.0: 5.005, 10.0: 10.01},
            valid_from=datetime.now(),
            valid_until=datetime.now() + timedelta(days=365),
            enabled=True
        )

        # Exact match
        corrected = correction.apply_correction(5.0)
        assert corrected == 5.005

    def test_lookup_table_correction_interpolation(self):
        """Test lookup table correction with interpolation."""
        correction = CalibrationCorrection(
            equipment_id="DMM_001",
            parameter="voltage",
            correction_type=CorrectionType.LOOKUP_TABLE,
            lookup_table={0.0: 0.0, 10.0: 10.01},
            valid_from=datetime.now(),
            valid_until=datetime.now() + timedelta(days=365),
            enabled=True
        )

        # Interpolation: 5.0 is halfway between 0 and 10
        # Should interpolate between 0.0 and 10.01
        corrected = correction.apply_correction(5.0)
        expected = 0.0 + (10.01 - 0.0) * (5.0 - 0.0) / (10.0 - 0.0)
        assert abs(corrected - expected) < 0.0001

    def test_lookup_table_correction_out_of_range(self):
        """Test lookup table correction outside range."""
        correction = CalibrationCorrection(
            equipment_id="DMM_001",
            parameter="voltage",
            correction_type=CorrectionType.LOOKUP_TABLE,
            lookup_table={1.0: 1.002, 10.0: 10.01},
            valid_from=datetime.now(),
            valid_until=datetime.now() + timedelta(days=365),
            enabled=True
        )

        # Below range - should return first value
        corrected = correction.apply_correction(0.5)
        assert corrected == 1.002

        # Above range - should return last value
        corrected = correction.apply_correction(15.0)
        assert corrected == 10.01

    def test_custom_correction(self):
        """Test custom correction function."""
        correction = CalibrationCorrection(
            equipment_id="SCOPE_001",
            parameter="voltage",
            correction_type=CorrectionType.CUSTOM,
            custom_function="x * 1.05 + 0.1",  # Custom formula
            valid_from=datetime.now(),
            valid_until=datetime.now() + timedelta(days=365),
            enabled=True
        )

        # Test: 5.0 -> 5.0 * 1.05 + 0.1 = 5.35
        corrected = correction.apply_correction(5.0)
        assert abs(corrected - 5.35) < 0.0001

    def test_correction_disabled(self):
        """Test that disabled correction is not applied."""
        correction = CalibrationCorrection(
            equipment_id="PSU_001",
            parameter="voltage",
            correction_type=CorrectionType.LINEAR,
            coefficients=[1.0, 0.5],
            valid_from=datetime.now(),
            valid_until=datetime.now() + timedelta(days=365),
            enabled=False  # Disabled
        )

        # Should return original value
        corrected = correction.apply_correction(5.0)
        assert corrected == 5.0

    def test_correction_range_limits(self):
        """Test correction respects range limits."""
        correction = CalibrationCorrection(
            equipment_id="PSU_001",
            parameter="voltage",
            correction_type=CorrectionType.LINEAR,
            coefficients=[1.0, 0.1],
            valid_from=datetime.now(),
            valid_until=datetime.now() + timedelta(days=365),
            range_min=1.0,
            range_max=10.0,
            enabled=True
        )

        # Below range
        corrected = correction.apply_correction(0.5)
        assert corrected == 0.5  # Should not apply correction

        # Within range
        corrected = correction.apply_correction(5.0)
        assert abs(corrected - 5.1) < 0.0001  # Should apply correction

        # Above range
        corrected = correction.apply_correction(15.0)
        assert corrected == 15.0  # Should not apply correction


class TestReferenceStandard:
    """Test ReferenceStandard model."""

    def test_minimal_standard(self):
        """Test creating minimal reference standard."""
        standard = ReferenceStandard(
            name="Voltage Standard",
            standard_type="voltage",
            manufacturer="Fluke",
            model="5720A",
            serial_number="SN123456",
            nominal_value=10.0,
            unit="V",
            accuracy=0.0015,
            uncertainty=0.0005,
            traceability="NIST"
        )

        assert standard.name == "Voltage Standard"
        assert standard.nominal_value == 10.0
        assert standard.unit == "V"
        assert standard.traceability == "NIST"
        assert standard.standard_id.startswith("std_")

    def test_standard_with_calibration_info(self):
        """Test standard with calibration information."""
        cal_date = datetime.now() - timedelta(days=30)
        due_date = datetime.now() + timedelta(days=335)

        standard = ReferenceStandard(
            name="Multimeter Standard",
            standard_type="multimeter",
            manufacturer="Keysight",
            model="3458A",
            serial_number="SN789012",
            nominal_value=1.0,
            unit="V",
            accuracy=0.0001,
            uncertainty=0.00005,
            traceability="NIST",
            calibration_date=cal_date,
            due_date=due_date,
            calibration_interval_days=365,
            calibration_certificate="CERT-STD-001"
        )

        assert standard.calibration_date == cal_date
        assert standard.due_date == due_date
        assert standard.calibration_interval_days == 365

    def test_standard_status_current(self):
        """Test standard status is CURRENT when not near due date."""
        standard = ReferenceStandard(
            name="Standard",
            standard_type="voltage",
            manufacturer="Fluke",
            model="732B",
            serial_number="SN001",
            nominal_value=10.0,
            unit="V",
            accuracy=0.001,
            uncertainty=0.0001,
            traceability="NIST",
            due_date=datetime.now() + timedelta(days=200)
        )

        status = standard.get_status()
        assert status == StandardStatus.CURRENT

    def test_standard_status_due_soon(self):
        """Test standard status is DUE_SOON when approaching due date."""
        standard = ReferenceStandard(
            name="Standard",
            standard_type="voltage",
            manufacturer="Fluke",
            model="732B",
            serial_number="SN002",
            nominal_value=10.0,
            unit="V",
            accuracy=0.001,
            uncertainty=0.0001,
            traceability="NIST",
            due_date=datetime.now() + timedelta(days=15)  # Within 30 days
        )

        status = standard.get_status()
        assert status == StandardStatus.DUE_SOON

    def test_standard_status_overdue(self):
        """Test standard status is OVERDUE when past due date."""
        standard = ReferenceStandard(
            name="Standard",
            standard_type="voltage",
            manufacturer="Fluke",
            model="732B",
            serial_number="SN003",
            nominal_value=10.0,
            unit="V",
            accuracy=0.001,
            uncertainty=0.0001,
            traceability="NIST",
            due_date=datetime.now() - timedelta(days=10)
        )

        status = standard.get_status()
        assert status == StandardStatus.OVERDUE

    def test_standard_usage_tracking(self):
        """Test recording standard usage."""
        standard = ReferenceStandard(
            name="Standard",
            standard_type="resistance",
            manufacturer="Fluke",
            model="742A",
            serial_number="SN004",
            nominal_value=100000.0,
            unit="Ω",
            accuracy=0.001,
            uncertainty=0.0005,
            traceability="NIST"
        )

        assert standard.usage_count == 0
        assert standard.last_used is None

        # Record usage
        standard.record_usage()

        assert standard.usage_count == 1
        assert isinstance(standard.last_used, datetime)

        # Record again
        standard.record_usage()
        assert standard.usage_count == 2


class TestEnhancedCalibrationManager:
    """Test EnhancedCalibrationManager class."""

    def test_manager_initialization(self):
        """Test manager initializes correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = EnhancedCalibrationManager(storage_path=tmpdir)

            assert manager.storage_path == Path(tmpdir)
            assert isinstance(manager.procedures, dict)
            assert isinstance(manager.executions, dict)
            assert isinstance(manager.certificates, dict)
            assert isinstance(manager.corrections, dict)
            assert isinstance(manager.standards, dict)

    def test_create_procedure(self):
        """Test creating a calibration procedure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = EnhancedCalibrationManager(storage_path=tmpdir)

            procedure = CalibrationProcedure(
                name="Voltage Calibration",
                equipment_type="power_supply"
            )

            proc_id = manager.create_procedure(procedure)

            assert proc_id == procedure.procedure_id
            assert proc_id in manager.procedures

    def test_start_procedure_execution(self):
        """Test starting procedure execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = EnhancedCalibrationManager(storage_path=tmpdir)

            # Create procedure with steps
            procedure = CalibrationProcedure(
                name="Test Procedure",
                equipment_type="oscilloscope",
                steps=[
                    CalibrationProcedureStep(
                        step_number=1,
                        step_type=ProcedureStepType.SETUP,
                        title="Setup",
                        description="Setup equipment"
                    )
                ]
            )
            proc_id = manager.create_procedure(procedure)

            # Start execution
            execution = manager.start_procedure_execution(
                proc_id, "SCOPE_001", "Tech1"
            )

            assert execution.procedure_id == proc_id
            assert execution.equipment_id == "SCOPE_001"
            assert execution.performed_by == "Tech1"
            assert len(execution.steps) == 1
            assert execution.execution_id in manager.executions

    def test_start_execution_nonexistent_procedure(self):
        """Test starting execution with nonexistent procedure raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = EnhancedCalibrationManager(storage_path=tmpdir)

            with pytest.raises(ValueError, match="Procedure .* not found"):
                manager.start_procedure_execution(
                    "nonexistent", "SCOPE_001", "Tech1"
                )

    def test_complete_step(self):
        """Test completing a procedure step."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = EnhancedCalibrationManager(storage_path=tmpdir)

            # Create and start procedure
            procedure = CalibrationProcedure(
                name="Test Procedure",
                equipment_type="power_supply",
                steps=[
                    CalibrationProcedureStep(
                        step_number=1,
                        step_type=ProcedureStepType.MEASUREMENT,
                        title="Measure Voltage",
                        description="Measure 5V"
                    )
                ]
            )
            proc_id = manager.create_procedure(procedure)
            execution = manager.start_procedure_execution(
                proc_id, "PSU_001", "Tech2"
            )

            # Complete the step
            manager.complete_step(
                execution.execution_id,
                step_number=1,
                measured_value=5.002,
                passed=True,
                notes="Within tolerance"
            )

            # Verify step was completed
            updated_execution = manager.executions[execution.execution_id]
            assert updated_execution.steps[0].status == ProcedureStepStatus.COMPLETED
            assert updated_execution.steps[0].measured_value == 5.002
            assert updated_execution.steps[0].passed is True

    def test_complete_step_invalid_execution(self):
        """Test completing step with invalid execution ID raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = EnhancedCalibrationManager(storage_path=tmpdir)

            with pytest.raises(ValueError, match="Execution .* not found"):
                manager.complete_step("invalid_id", 1)

    def test_create_certificate(self):
        """Test creating a calibration certificate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = EnhancedCalibrationManager(storage_path=tmpdir)

            cert = CalibrationCertificate(
                certificate_number="CERT-001",
                certificate_type=CertificateType.ACCREDITED,
                equipment_id="SCOPE_001",
                equipment_model="DS1054Z",
                equipment_serial="SN123",
                manufacturer="Rigol",
                calibration_date=datetime.now(),
                due_date=datetime.now() + timedelta(days=365),
                performed_by="Cal Lab",
                organization="ISO Lab"
            )

            cert_id = manager.create_certificate(cert)

            assert cert_id == cert.certificate_id
            assert cert_id in manager.certificates

    def test_get_certificate(self):
        """Test retrieving a certificate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = EnhancedCalibrationManager(storage_path=tmpdir)

            cert = CalibrationCertificate(
                certificate_number="CERT-002",
                certificate_type=CertificateType.IN_HOUSE,
                equipment_id="PSU_001",
                equipment_model="E36312A",
                equipment_serial="SN456",
                manufacturer="Keysight",
                calibration_date=datetime.now(),
                due_date=datetime.now() + timedelta(days=365),
                performed_by="Tech",
                organization="Our Lab"
            )
            cert_id = manager.create_certificate(cert)

            retrieved = manager.get_certificate(cert_id)

            assert retrieved is not None
            assert retrieved.certificate_number == "CERT-002"

    def test_get_nonexistent_certificate(self):
        """Test retrieving nonexistent certificate returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = EnhancedCalibrationManager(storage_path=tmpdir)

            retrieved = manager.get_certificate("nonexistent")

            assert retrieved is None

    def test_add_correction(self):
        """Test adding a calibration correction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = EnhancedCalibrationManager(storage_path=tmpdir)

            correction = CalibrationCorrection(
                equipment_id="PSU_001",
                parameter="voltage",
                correction_type=CorrectionType.LINEAR,
                coefficients=[1.0, 0.05],
                valid_from=datetime.now(),
                valid_until=datetime.now() + timedelta(days=365)
            )

            manager.add_correction(correction)

            assert "PSU_001" in manager.corrections
            assert len(manager.corrections["PSU_001"]) == 1

    def test_apply_corrections(self):
        """Test applying corrections to a value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = EnhancedCalibrationManager(storage_path=tmpdir)

            # Add correction
            correction = CalibrationCorrection(
                equipment_id="DMM_001",
                parameter="voltage",
                correction_type=CorrectionType.LINEAR,
                coefficients=[1.0, 0.1],  # Add 0.1V
                valid_from=datetime.now(),
                valid_until=datetime.now() + timedelta(days=365),
                enabled=True
            )
            manager.add_correction(correction)

            # Apply correction
            corrected = manager.apply_corrections("DMM_001", "voltage", 5.0)

            assert abs(corrected - 5.1) < 0.0001

    def test_apply_corrections_no_match(self):
        """Test applying corrections returns original value when no match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = EnhancedCalibrationManager(storage_path=tmpdir)

            # No corrections for this equipment
            corrected = manager.apply_corrections("UNKNOWN", "voltage", 5.0)

            assert corrected == 5.0

    def test_add_standard(self):
        """Test adding a reference standard."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = EnhancedCalibrationManager(storage_path=tmpdir)

            standard = ReferenceStandard(
                name="Voltage Ref",
                standard_type="voltage",
                manufacturer="Fluke",
                model="732B",
                serial_number="SN001",
                nominal_value=10.0,
                unit="V",
                accuracy=0.001,
                uncertainty=0.0001,
                traceability="NIST"
            )

            std_id = manager.add_standard(standard)

            assert std_id == standard.standard_id
            assert std_id in manager.standards

    def test_use_standard(self):
        """Test recording standard usage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = EnhancedCalibrationManager(storage_path=tmpdir)

            standard = ReferenceStandard(
                name="Current Ref",
                standard_type="current",
                manufacturer="Fluke",
                model="742A",
                serial_number="SN002",
                nominal_value=1.0,
                unit="A",
                accuracy=0.001,
                uncertainty=0.0001,
                traceability="NIST"
            )
            std_id = manager.add_standard(standard)

            # Record usage
            manager.use_standard(std_id)

            # Verify usage was recorded
            assert manager.standards[std_id].usage_count == 1

    def test_get_due_standards(self):
        """Test getting standards due for calibration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = EnhancedCalibrationManager(storage_path=tmpdir)

            # Add standards with different due dates
            std1 = ReferenceStandard(
                name="Overdue Standard",
                standard_type="voltage",
                manufacturer="Fluke",
                model="732B",
                serial_number="SN001",
                nominal_value=10.0,
                unit="V",
                accuracy=0.001,
                uncertainty=0.0001,
                traceability="NIST",
                due_date=datetime.now() - timedelta(days=10)  # Overdue
            )
            manager.add_standard(std1)

            std2 = ReferenceStandard(
                name="Due Soon Standard",
                standard_type="voltage",
                manufacturer="Fluke",
                model="732B",
                serial_number="SN002",
                nominal_value=10.0,
                unit="V",
                accuracy=0.001,
                uncertainty=0.0001,
                traceability="NIST",
                due_date=datetime.now() + timedelta(days=15)  # Due soon
            )
            manager.add_standard(std2)

            std3 = ReferenceStandard(
                name="Current Standard",
                standard_type="voltage",
                manufacturer="Fluke",
                model="732B",
                serial_number="SN003",
                nominal_value=10.0,
                unit="V",
                accuracy=0.001,
                uncertainty=0.0001,
                traceability="NIST",
                due_date=datetime.now() + timedelta(days=200)  # Current
            )
            manager.add_standard(std3)

            # Get due standards (within 30 days)
            due_standards = manager.get_due_standards(days=30)

            assert len(due_standards) == 2  # Overdue and due soon


class TestGlobalEnhancedManager:
    """Test global enhanced calibration manager functions."""

    def test_initialize_enhanced_manager(self):
        """Test initializing global enhanced manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = initialize_enhanced_calibration_manager(storage_path=tmpdir)

            assert manager is not None
            assert isinstance(manager, EnhancedCalibrationManager)

    def test_get_enhanced_manager_after_init(self):
        """Test getting enhanced manager after initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            initialized = initialize_enhanced_calibration_manager(storage_path=tmpdir)
            retrieved = get_enhanced_calibration_manager()

            assert retrieved is initialized

    def test_get_enhanced_manager_before_init_raises(self):
        """Test getting manager before initialization raises error."""
        # Reset global state
        import server.equipment.calibration_enhanced as cal_mod
        cal_mod._enhanced_calibration_manager = None

        with pytest.raises(RuntimeError, match="not initialized"):
            get_enhanced_calibration_manager()


# Mark all tests as unit tests
pytestmark = pytest.mark.unit
