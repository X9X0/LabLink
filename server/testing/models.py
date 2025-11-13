"""Data models for automated test sequences."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum
from pydantic import BaseModel, Field
import uuid


class TestStatus(str, Enum):
    """Test execution status."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ABORTED = "aborted"
    ERROR = "error"


class StepType(str, Enum):
    """Type of test step."""
    SETUP = "setup"  # Equipment setup/configuration
    COMMAND = "command"  # Send command to equipment
    MEASUREMENT = "measurement"  # Take measurement
    DELAY = "delay"  # Wait for specified time
    VALIDATION = "validation"  # Validate measurement against criteria
    SWEEP = "sweep"  # Parameter sweep
    CONDITIONAL = "conditional"  # Conditional branching
    LOOP = "loop"  # Loop over steps
    CLEANUP = "cleanup"  # Cleanup/reset


class ValidationOperator(str, Enum):
    """Validation comparison operators."""
    EQUAL = "=="
    NOT_EQUAL = "!="
    LESS_THAN = "<"
    LESS_EQUAL = "<="
    GREATER_THAN = ">"
    GREATER_EQUAL = ">="
    IN_RANGE = "in_range"
    OUT_OF_RANGE = "out_of_range"


class TestStep(BaseModel):
    """Single step in a test sequence."""
    step_id: str = Field(default_factory=lambda: f"step_{uuid.uuid4().hex[:8]}")
    step_number: int = Field(..., description="Step number in sequence")
    step_type: StepType
    name: str = Field(..., description="Step name")
    description: Optional[str] = None

    # Equipment
    equipment_id: Optional[str] = None

    # Command execution
    command: Optional[str] = None  # SCPI command to send
    expected_response: Optional[str] = None

    # Measurement
    measurement_type: Optional[str] = None  # voltage, current, frequency, etc.
    measurement_params: Dict[str, Any] = Field(default_factory=dict)

    # Validation criteria
    validation_operator: Optional[ValidationOperator] = None
    validation_value: Optional[float] = None
    validation_range: Optional[Dict[str, float]] = None  # {min, max}
    tolerance_percent: float = 0.0

    # Delay
    delay_seconds: float = 0.0

    # Sweep parameters
    sweep_parameter: Optional[str] = None
    sweep_start: Optional[float] = None
    sweep_stop: Optional[float] = None
    sweep_step: Optional[float] = None
    sweep_points: Optional[int] = None

    # Conditional
    condition_expression: Optional[str] = None
    if_true_step: Optional[int] = None
    if_false_step: Optional[int] = None

    # Loop
    loop_count: Optional[int] = None
    loop_start_step: Optional[int] = None

    # Execution state
    status: TestStatus = TestStatus.PENDING
    measured_value: Optional[float] = None
    passed: Optional[bool] = None
    error_message: Optional[str] = None
    executed_at: Optional[datetime] = None
    duration_seconds: float = 0.0

    # Metadata
    retry_on_fail: bool = False
    max_retries: int = 0
    critical: bool = True  # If True, abort test on failure
    log_data: bool = True


class ParameterSweep(BaseModel):
    """Parameter sweep configuration."""
    sweep_id: str = Field(default_factory=lambda: f"sweep_{uuid.uuid4().hex[:8]}")
    parameter_name: str = Field(..., description="Parameter to sweep")
    start_value: float
    stop_value: float
    step_size: Optional[float] = None
    num_points: Optional[int] = None
    scale: str = "linear"  # linear or log

    # For each sweep point
    measurement_type: str = Field(..., description="What to measure")
    settling_time: float = 0.1  # Time to wait after setting parameter

    # Results
    sweep_points: List[float] = Field(default_factory=list)
    measured_values: List[float] = Field(default_factory=list)

    def generate_sweep_points(self) -> List[float]:
        """Generate sweep points based on configuration."""
        import numpy as np

        if self.num_points:
            if self.scale == "log":
                points = np.logspace(
                    np.log10(self.start_value),
                    np.log10(self.stop_value),
                    self.num_points
                )
            else:
                points = np.linspace(
                    self.start_value,
                    self.stop_value,
                    self.num_points
                )
        elif self.step_size:
            points = np.arange(
                self.start_value,
                self.stop_value + self.step_size,
                self.step_size
            )
        else:
            raise ValueError("Must specify either num_points or step_size")

        self.sweep_points = points.tolist()
        return self.sweep_points


class TestSequence(BaseModel):
    """Complete automated test sequence."""
    sequence_id: str = Field(default_factory=lambda: f"seq_{uuid.uuid4().hex[:12]}")
    name: str = Field(..., description="Test sequence name")
    version: str = Field(default="1.0")
    description: Optional[str] = None

    # Equipment
    equipment_ids: List[str] = Field(default_factory=list, description="Equipment used in test")

    # Steps
    steps: List[TestStep] = Field(default_factory=list)

    # Configuration
    abort_on_fail: bool = True  # Abort entire test on first failure
    max_duration_seconds: Optional[float] = None
    repeat_count: int = 1  # Number of times to repeat sequence

    # Pass/fail criteria
    required_pass_rate: float = 100.0  # Percentage of steps that must pass

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    created_by: str = Field(default="system")
    category: Optional[str] = None  # acceptance, characterization, regression, etc.
    tags: List[str] = Field(default_factory=list)

    # Template
    is_template: bool = False
    template_name: Optional[str] = None


class TestExecution(BaseModel):
    """Test sequence execution instance."""
    execution_id: str = Field(default_factory=lambda: f"exec_{uuid.uuid4().hex[:12]}")
    sequence_id: str
    sequence_name: str

    # Execution state
    status: TestStatus = TestStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0

    # Steps (copy of sequence steps with execution data)
    steps: List[TestStep] = Field(default_factory=list)
    current_step: int = 0

    # Results
    total_steps: int = 0
    passed_steps: int = 0
    failed_steps: int = 0
    pass_rate: float = 0.0

    # Data
    measurements: Dict[str, List[float]] = Field(default_factory=dict)
    sweep_results: List[ParameterSweep] = Field(default_factory=list)

    # Metadata
    executed_by: str = Field(..., description="User who executed test")
    environment: Dict[str, Any] = Field(default_factory=dict)  # temp, humidity, etc.
    notes: Optional[str] = None

    def calculate_results(self):
        """Calculate test results from steps."""
        self.total_steps = len(self.steps)
        self.passed_steps = sum(1 for step in self.steps if step.passed)
        self.failed_steps = sum(1 for step in self.steps if step.passed == False)

        if self.total_steps > 0:
            self.pass_rate = (self.passed_steps / self.total_steps) * 100
        else:
            self.pass_rate = 0.0

        # Determine overall status
        if self.status == TestStatus.RUNNING:
            pass  # Still running
        elif self.failed_steps > 0:
            self.status = TestStatus.FAILED
        elif self.passed_steps == self.total_steps:
            self.status = TestStatus.PASSED
        else:
            self.status = TestStatus.ERROR


class TestResult(BaseModel):
    """Test result summary for archival."""
    result_id: str = Field(default_factory=lambda: f"result_{uuid.uuid4().hex[:12]}")
    execution_id: str
    sequence_id: str
    sequence_name: str

    # Results
    status: TestStatus
    started_at: datetime
    completed_at: datetime
    duration_seconds: float

    # Statistics
    total_steps: int
    passed_steps: int
    failed_steps: int
    pass_rate: float

    # Data
    measurements: Dict[str, Any] = Field(default_factory=dict)
    sweep_results: List[Dict[str, Any]] = Field(default_factory=list)

    # Metadata
    executed_by: str
    equipment_ids: List[str] = Field(default_factory=list)
    environment: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None

    # Archival
    archived_at: datetime = Field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "result_id": self.result_id,
            "execution_id": self.execution_id,
            "sequence_id": self.sequence_id,
            "sequence_name": self.sequence_name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "total_steps": self.total_steps,
            "passed_steps": self.passed_steps,
            "failed_steps": self.failed_steps,
            "pass_rate": self.pass_rate,
            "measurements": self.measurements,
            "sweep_results": self.sweep_results,
            "executed_by": self.executed_by,
            "equipment_ids": self.equipment_ids,
            "environment": self.environment,
            "notes": self.notes,
            "archived_at": self.archived_at.isoformat(),
        }


class TestReport(BaseModel):
    """Comprehensive test report."""
    report_id: str = Field(default_factory=lambda: f"report_{uuid.uuid4().hex[:12]}")
    title: str

    # Results summary
    executions: List[TestResult] = Field(default_factory=list)
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    overall_pass_rate: float = 0.0

    # Time range
    start_date: datetime
    end_date: datetime

    # Analysis
    trends: Dict[str, Any] = Field(default_factory=dict)
    statistics: Dict[str, Any] = Field(default_factory=dict)

    # Report generation
    generated_at: datetime = Field(default_factory=datetime.now)
    generated_by: str = Field(default="system")
    format: str = "html"  # html, pdf, json
