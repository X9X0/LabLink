"""Scheduler data models."""

from enum import Enum
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


class ScheduleType(str, Enum):
    """Type of scheduled job."""
    ACQUISITION = "acquisition"          # Start data acquisition
    STATE_CAPTURE = "state_capture"      # Capture equipment state
    EQUIPMENT_TEST = "equipment_test"    # Run equipment test
    MEASUREMENT = "measurement"          # Take single measurement
    COMMAND = "command"                  # Execute equipment command
    SCRIPT = "script"                    # Run custom script


class JobStatus(str, Enum):
    """Job execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class TriggerType(str, Enum):
    """Schedule trigger types."""
    CRON = "cron"                # Cron expression
    INTERVAL = "interval"        # Fixed interval
    DATE = "date"                # One-time at specific date/time
    DAILY = "daily"              # Daily at specific time
    WEEKLY = "weekly"            # Weekly on specific day/time
    MONTHLY = "monthly"          # Monthly on specific day/time


class ScheduleConfig(BaseModel):
    """Configuration for a scheduled job."""
    job_id: str = Field(default_factory=lambda: f"job_{uuid.uuid4().hex[:8]}")
    name: str = Field(..., description="Job name")
    description: Optional[str] = Field(None, description="Job description")

    # Job type and target
    schedule_type: ScheduleType = Field(..., description="Type of scheduled job")
    equipment_id: Optional[str] = Field(None, description="Target equipment ID")

    # Trigger configuration
    trigger_type: TriggerType = Field(..., description="Type of schedule trigger")

    # Cron expression (for CRON trigger)
    cron_expression: Optional[str] = Field(None, description="Cron expression (e.g., '0 */6 * * *')")

    # Interval settings (for INTERVAL trigger)
    interval_seconds: Optional[int] = Field(None, description="Interval in seconds")
    interval_minutes: Optional[int] = Field(None, description="Interval in minutes")
    interval_hours: Optional[int] = Field(None, description="Interval in hours")
    interval_days: Optional[int] = Field(None, description="Interval in days")

    # Date/time settings (for DATE, DAILY, WEEKLY, MONTHLY)
    run_date: Optional[datetime] = Field(None, description="Specific date/time to run")
    time_of_day: Optional[str] = Field(None, description="Time of day (HH:MM:SS)")
    day_of_week: Optional[int] = Field(None, description="Day of week (0=Monday, 6=Sunday)")
    day_of_month: Optional[int] = Field(None, description="Day of month (1-31)")

    # Job-specific parameters
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Job-specific parameters")

    # Control settings
    enabled: bool = Field(default=True, description="Whether job is enabled")
    max_instances: int = Field(default=1, description="Maximum concurrent instances")
    misfire_grace_time: int = Field(default=300, description="Grace time for missed runs (seconds)")
    coalesce: bool = Field(default=True, description="Coalesce missed runs")

    # Execution limits
    start_date: Optional[datetime] = Field(None, description="Start date for schedule")
    end_date: Optional[datetime] = Field(None, description="End date for schedule")
    max_executions: Optional[int] = Field(None, description="Maximum number of executions")

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    created_by: Optional[str] = Field(None, description="User who created job")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")

    # Integration settings (v0.14.0)
    profile_id: Optional[str] = Field(None, description="Equipment profile to apply before execution")
    on_failure_alarm: bool = Field(default=False, description="Create alarm on job failure")
    conflict_policy: str = Field(default="skip", description="Policy when job conflicts occur (skip, queue, replace)")


class JobExecution(BaseModel):
    """A job execution instance."""
    execution_id: str = Field(default_factory=lambda: f"exec_{uuid.uuid4().hex[:8]}")
    job_id: str = Field(..., description="Associated job ID")

    # Execution details
    status: JobStatus = Field(default=JobStatus.PENDING)
    started_at: Optional[datetime] = Field(None)
    completed_at: Optional[datetime] = Field(None)
    duration_seconds: Optional[float] = Field(None)

    # Results
    result: Optional[Dict[str, Any]] = Field(None, description="Execution result")
    error: Optional[str] = Field(None, description="Error message if failed")
    output: Optional[str] = Field(None, description="Job output/logs")

    # Context
    scheduled_time: datetime = Field(..., description="When job was scheduled to run")
    actual_time: Optional[datetime] = Field(None, description="When job actually ran")
    trigger_info: Dict[str, Any] = Field(default_factory=dict)


class JobHistory(BaseModel):
    """Historical record of job executions."""
    job_id: str
    job_name: str
    total_executions: int = 0
    successful: int = 0
    failed: int = 0
    cancelled: int = 0
    average_duration: float = 0.0
    last_execution: Optional[datetime] = None
    last_status: Optional[JobStatus] = None
    next_run: Optional[datetime] = None


class ScheduleStatistics(BaseModel):
    """Scheduler statistics."""
    total_jobs: int = 0
    active_jobs: int = 0
    disabled_jobs: int = 0
    running_executions: int = 0
    total_executions_today: int = 0
    successful_today: int = 0
    failed_today: int = 0
    by_type: Dict[str, int] = Field(default_factory=dict)
    upcoming_jobs: List[Dict[str, Any]] = Field(default_factory=list)
