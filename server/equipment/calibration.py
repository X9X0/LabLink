"""
Equipment Calibration Tracking System
=====================================

Manages calibration scheduling, record-keeping, and verification for lab equipment.
Ensures equipment meets accuracy requirements and regulatory compliance.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CalibrationStatus(str, Enum):
    """Calibration status of equipment."""

    CURRENT = "current"  # Calibration is valid
    DUE_SOON = "due_soon"  # Calibration due within warning period
    DUE = "due"  # Calibration is due now
    OVERDUE = "overdue"  # Calibration is overdue
    NEVER_CALIBRATED = "never_calibrated"  # Equipment has never been calibrated
    UNKNOWN = "unknown"  # Calibration status cannot be determined


class CalibrationType(str, Enum):
    """Types of calibration procedures."""

    FULL = "full"  # Complete calibration of all parameters
    PARTIAL = "partial"  # Calibration of specific parameters
    VERIFICATION = "verification"  # Verification only (no adjustments)
    ADJUSTMENT = "adjustment"  # Adjustment based on verification
    FACTORY = "factory"  # Factory calibration
    IN_HOUSE = "in_house"  # Internal calibration


class CalibrationResult(str, Enum):
    """Result of calibration procedure."""

    PASS = "pass"  # Calibration passed
    PASS_WITH_ADJUSTMENT = "pass_with_adjustment"  # Passed after adjustment
    FAIL = "fail"  # Calibration failed
    INCOMPLETE = "incomplete"  # Calibration not completed
    ABORTED = "aborted"  # Calibration aborted


class CalibrationRecord(BaseModel):
    """Record of a calibration event."""

    calibration_id: str = Field(default_factory=lambda: f"cal_{uuid.uuid4().hex[:12]}")
    equipment_id: str = Field(..., description="Equipment identifier")
    equipment_type: str = Field(..., description="Type of equipment")
    equipment_model: str = Field(..., description="Equipment model")

    # Calibration details
    calibration_type: CalibrationType = Field(..., description="Type of calibration")
    calibration_date: datetime = Field(default_factory=datetime.now)
    due_date: datetime = Field(..., description="Next calibration due date")
    result: CalibrationResult = Field(..., description="Calibration result")

    # Personnel and location
    performed_by: str = Field(..., description="Name/ID of calibrator")
    organization: Optional[str] = Field(None, description="Calibration organization")
    location: Optional[str] = Field(None, description="Calibration location")

    # Pre-calibration measurements
    pre_calibration_measurements: Dict[str, Any] = Field(
        default_factory=dict, description="Measurements before calibration"
    )

    # Post-calibration measurements
    post_calibration_measurements: Dict[str, Any] = Field(
        default_factory=dict, description="Measurements after calibration"
    )

    # Calibration standards used
    standards_used: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Calibration standards and traceable references",
    )

    # Environmental conditions
    temperature_celsius: Optional[float] = Field(
        None, description="Ambient temperature"
    )
    humidity_percent: Optional[float] = Field(None, description="Ambient humidity")

    # Results and notes
    adjustments_made: List[str] = Field(
        default_factory=list, description="Adjustments performed"
    )
    out_of_tolerance_items: List[str] = Field(
        default_factory=list, description="Out-of-tolerance findings"
    )
    notes: Optional[str] = Field(None, description="Additional notes")
    certificate_number: Optional[str] = Field(
        None, description="Calibration certificate number"
    )
    certificate_file_path: Optional[str] = Field(
        None, description="Path to certificate file"
    )

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class CalibrationSchedule(BaseModel):
    """Calibration schedule for equipment."""

    schedule_id: str = Field(default_factory=lambda: f"sched_{uuid.uuid4().hex[:8]}")
    equipment_id: str = Field(..., description="Equipment identifier")

    # Schedule parameters
    interval_days: int = Field(..., description="Calibration interval in days")
    warning_days: int = Field(default=30, description="Days before due to warn")
    auto_schedule: bool = Field(
        default=True, description="Automatically schedule next calibration"
    )

    # Notification settings
    notify_due_soon: bool = Field(default=True, description="Notify when due soon")
    notify_overdue: bool = Field(default=True, description="Notify when overdue")
    notification_emails: List[str] = Field(
        default_factory=list, description="Email addresses for notifications"
    )

    # Metadata
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)


class CalibrationManager:
    """Manages equipment calibration records and schedules."""

    def __init__(self, storage_path: str = "data/calibration"):
        """
        Initialize calibration manager.

        Args:
            storage_path: Directory for storing calibration data
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self._records: Dict[str, List[CalibrationRecord]] = (
            {}
        )  # equipment_id -> records
        self._schedules: Dict[str, CalibrationSchedule] = {}  # equipment_id -> schedule

        # Load existing data
        self._load_records()
        self._load_schedules()

        logger.info(
            f"Calibration manager initialized with {len(self._records)} equipment records"
        )

    # ==================== Record Management ====================

    async def add_calibration_record(
        self, record: CalibrationRecord
    ) -> CalibrationRecord:
        """
        Add a new calibration record.

        Args:
            record: Calibration record to add

        Returns:
            Added calibration record
        """
        equipment_id = record.equipment_id

        if equipment_id not in self._records:
            self._records[equipment_id] = []

        self._records[equipment_id].append(record)
        self._save_records(equipment_id)

        logger.info(
            f"Added calibration record {record.calibration_id} for equipment {equipment_id}"
        )

        # Auto-schedule next calibration if enabled
        if (
            equipment_id in self._schedules
            and self._schedules[equipment_id].auto_schedule
        ):
            await self._auto_schedule_next(equipment_id, record)

        return record

    async def get_calibration_history(
        self, equipment_id: str, limit: Optional[int] = None
    ) -> List[CalibrationRecord]:
        """
        Get calibration history for equipment.

        Args:
            equipment_id: Equipment identifier
            limit: Maximum number of records to return (most recent first)

        Returns:
            List of calibration records
        """
        records = self._records.get(equipment_id, [])

        # Sort by date (most recent first)
        records = sorted(records, key=lambda r: r.calibration_date, reverse=True)

        if limit:
            records = records[:limit]

        return records

    async def get_latest_calibration(
        self, equipment_id: str
    ) -> Optional[CalibrationRecord]:
        """
        Get the most recent calibration record.

        Args:
            equipment_id: Equipment identifier

        Returns:
            Most recent calibration record, or None if never calibrated
        """
        records = await self.get_calibration_history(equipment_id, limit=1)
        return records[0] if records else None

    async def delete_calibration_record(
        self, equipment_id: str, calibration_id: str
    ) -> bool:
        """
        Delete a calibration record.

        Args:
            equipment_id: Equipment identifier
            calibration_id: Calibration record ID

        Returns:
            True if deleted, False if not found
        """
        if equipment_id not in self._records:
            return False

        original_count = len(self._records[equipment_id])
        self._records[equipment_id] = [
            r for r in self._records[equipment_id] if r.calibration_id != calibration_id
        ]

        if len(self._records[equipment_id]) < original_count:
            self._save_records(equipment_id)
            logger.info(f"Deleted calibration record {calibration_id}")
            return True

        return False

    # ==================== Status Checking ====================

    async def get_calibration_status(self, equipment_id: str) -> CalibrationStatus:
        """
        Get current calibration status for equipment.

        Args:
            equipment_id: Equipment identifier

        Returns:
            Current calibration status
        """
        latest = await self.get_latest_calibration(equipment_id)

        if not latest:
            return CalibrationStatus.NEVER_CALIBRATED

        if not latest.due_date:
            return CalibrationStatus.UNKNOWN

        schedule = self._schedules.get(equipment_id)
        warning_days = schedule.warning_days if schedule else 30

        now = datetime.now()
        days_until_due = (latest.due_date - now).days

        if days_until_due < 0:
            return CalibrationStatus.OVERDUE
        elif days_until_due == 0:
            return CalibrationStatus.DUE
        elif days_until_due <= warning_days:
            return CalibrationStatus.DUE_SOON
        else:
            return CalibrationStatus.CURRENT

    async def is_calibration_current(self, equipment_id: str) -> bool:
        """
        Check if equipment calibration is current.

        Args:
            equipment_id: Equipment identifier

        Returns:
            True if calibration is current, False otherwise
        """
        status = await self.get_calibration_status(equipment_id)
        return status in [CalibrationStatus.CURRENT, CalibrationStatus.DUE_SOON]

    async def get_days_until_due(self, equipment_id: str) -> Optional[int]:
        """
        Get number of days until calibration is due.

        Args:
            equipment_id: Equipment identifier

        Returns:
            Days until due (negative if overdue), None if never calibrated
        """
        latest = await self.get_latest_calibration(equipment_id)

        if not latest or not latest.due_date:
            return None

        return (latest.due_date - datetime.now()).days

    # ==================== Schedule Management ====================

    async def set_calibration_schedule(self, schedule: CalibrationSchedule):
        """
        Set calibration schedule for equipment.

        Args:
            schedule: Calibration schedule
        """
        schedule.last_updated = datetime.now()
        self._schedules[schedule.equipment_id] = schedule
        self._save_schedules()

        logger.info(
            f"Set calibration schedule for {schedule.equipment_id}: {schedule.interval_days} days"
        )

    async def get_calibration_schedule(
        self, equipment_id: str
    ) -> Optional[CalibrationSchedule]:
        """
        Get calibration schedule for equipment.

        Args:
            equipment_id: Equipment identifier

        Returns:
            Calibration schedule, or None if not scheduled
        """
        return self._schedules.get(equipment_id)

    async def delete_calibration_schedule(self, equipment_id: str) -> bool:
        """
        Delete calibration schedule.

        Args:
            equipment_id: Equipment identifier

        Returns:
            True if deleted, False if not found
        """
        if equipment_id in self._schedules:
            del self._schedules[equipment_id]
            self._save_schedules()
            logger.info(f"Deleted calibration schedule for {equipment_id}")
            return True
        return False

    async def get_due_calibrations(
        self, include_due_soon: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get list of equipment with calibrations due.

        Args:
            include_due_soon: Include equipment with calibrations due soon

        Returns:
            List of equipment with due calibrations
        """
        due_list = []

        for equipment_id in self._records.keys():
            status = await self.get_calibration_status(equipment_id)
            days_until_due = await self.get_days_until_due(equipment_id)
            latest = await self.get_latest_calibration(equipment_id)

            include = False
            if status == CalibrationStatus.OVERDUE or status == CalibrationStatus.DUE:
                include = True
            elif include_due_soon and status == CalibrationStatus.DUE_SOON:
                include = True

            if include:
                due_list.append(
                    {
                        "equipment_id": equipment_id,
                        "status": status.value,
                        "days_until_due": days_until_due,
                        "due_date": latest.due_date if latest else None,
                        "last_calibration": latest.calibration_date if latest else None,
                    }
                )

        # Sort by days until due (most overdue first)
        due_list.sort(
            key=lambda x: x["days_until_due"] if x["days_until_due"] is not None else 0
        )

        return due_list

    async def _auto_schedule_next(self, equipment_id: str, record: CalibrationRecord):
        """Automatically schedule next calibration based on current record."""
        schedule = self._schedules.get(equipment_id)
        if not schedule:
            return

        # Due date should already be set in the record
        logger.info(
            f"Next calibration auto-scheduled for {equipment_id} on "
            f"{record.due_date.strftime('%Y-%m-%d')}"
        )

    # ==================== Reporting ====================

    async def generate_calibration_report(
        self, equipment_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Generate calibration status report.

        Args:
            equipment_ids: List of equipment IDs to include (None for all)

        Returns:
            Calibration report
        """
        if equipment_ids is None:
            equipment_ids = list(self._records.keys())

        report = {
            "generated_at": datetime.now(),
            "total_equipment": len(equipment_ids),
            "status_summary": {
                "current": 0,
                "due_soon": 0,
                "due": 0,
                "overdue": 0,
                "never_calibrated": 0,
                "unknown": 0,
            },
            "equipment_details": [],
        }

        for equipment_id in equipment_ids:
            status = await self.get_calibration_status(equipment_id)
            latest = await self.get_latest_calibration(equipment_id)
            days_until_due = await self.get_days_until_due(equipment_id)

            # Update summary
            report["status_summary"][status.value] += 1

            # Add details
            report["equipment_details"].append(
                {
                    "equipment_id": equipment_id,
                    "status": status.value,
                    "days_until_due": days_until_due,
                    "last_calibration_date": (
                        latest.calibration_date if latest else None
                    ),
                    "next_due_date": latest.due_date if latest else None,
                    "last_result": latest.result.value if latest else None,
                }
            )

        return report

    # ==================== Persistence ====================

    def _load_records(self):
        """Load calibration records from disk."""
        records_file = self.storage_path / "records.json"
        if records_file.exists():
            try:
                with open(records_file, "r") as f:
                    data = json.load(f)

                for equipment_id, records in data.items():
                    self._records[equipment_id] = [
                        CalibrationRecord(**record) for record in records
                    ]

                logger.info(
                    f"Loaded {len(self._records)} equipment calibration records"
                )
            except Exception as e:
                logger.error(f"Error loading calibration records: {e}")

    def _save_records(self, equipment_id: str):
        """Save calibration records for specific equipment."""
        records_file = self.storage_path / "records.json"

        # Load all records
        all_records = {}
        if records_file.exists():
            with open(records_file, "r") as f:
                all_records = json.load(f)

        # Update records for this equipment
        all_records[equipment_id] = [
            json.loads(record.model_dump_json())
            for record in self._records.get(equipment_id, [])
        ]

        # Save back
        with open(records_file, "w") as f:
            json.dump(all_records, f, indent=2, default=str)

    def _load_schedules(self):
        """Load calibration schedules from disk."""
        schedules_file = self.storage_path / "schedules.json"
        if schedules_file.exists():
            try:
                with open(schedules_file, "r") as f:
                    data = json.load(f)

                for equipment_id, schedule in data.items():
                    self._schedules[equipment_id] = CalibrationSchedule(**schedule)

                logger.info(f"Loaded {len(self._schedules)} calibration schedules")
            except Exception as e:
                logger.error(f"Error loading calibration schedules: {e}")

    def _save_schedules(self):
        """Save all calibration schedules to disk."""
        schedules_file = self.storage_path / "schedules.json"

        data = {
            equipment_id: json.loads(schedule.model_dump_json())
            for equipment_id, schedule in self._schedules.items()
        }

        with open(schedules_file, "w") as f:
            json.dump(data, f, indent=2, default=str)


# Global calibration manager instance
calibration_manager: Optional[CalibrationManager] = None


def get_calibration_manager() -> Optional[CalibrationManager]:
    """Get the global calibration manager instance."""
    return calibration_manager


def initialize_calibration_manager(
    storage_path: str = "data/calibration",
) -> CalibrationManager:
    """
    Initialize the global calibration manager.

    Args:
        storage_path: Directory for storing calibration data

    Returns:
        Initialized calibration manager
    """
    global calibration_manager
    calibration_manager = CalibrationManager(storage_path)
    return calibration_manager
