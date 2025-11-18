"""
Comprehensive tests for the equipment calibration module.

Tests cover:
- CalibrationStatus, CalibrationType, CalibrationResult enums
- CalibrationRecord model
- CalibrationSchedule model
- CalibrationManager class:
  - Record management (add, get, delete)
  - Status checking and validation
  - Schedule management
  - Due calibration tracking
  - Report generation
  - Persistence (save/load)
"""

import asyncio
import json
import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from server.equipment.calibration import (
    CalibrationStatus,
    CalibrationType,
    CalibrationResult,
    CalibrationRecord,
    CalibrationSchedule,
    CalibrationManager,
    get_calibration_manager,
    initialize_calibration_manager,
)


class TestCalibrationEnums:
    """Test calibration enumeration types."""

    def test_calibration_status_values(self):
        """Test CalibrationStatus enum has all expected values."""
        assert CalibrationStatus.CURRENT == "current"
        assert CalibrationStatus.DUE_SOON == "due_soon"
        assert CalibrationStatus.DUE == "due"
        assert CalibrationStatus.OVERDUE == "overdue"
        assert CalibrationStatus.NEVER_CALIBRATED == "never_calibrated"
        assert CalibrationStatus.UNKNOWN == "unknown"

    def test_calibration_type_values(self):
        """Test CalibrationType enum has all expected values."""
        assert CalibrationType.FULL == "full"
        assert CalibrationType.PARTIAL == "partial"
        assert CalibrationType.VERIFICATION == "verification"
        assert CalibrationType.ADJUSTMENT == "adjustment"
        assert CalibrationType.FACTORY == "factory"
        assert CalibrationType.IN_HOUSE == "in_house"

    def test_calibration_result_values(self):
        """Test CalibrationResult enum has all expected values."""
        assert CalibrationResult.PASS == "pass"
        assert CalibrationResult.PASS_WITH_ADJUSTMENT == "pass_with_adjustment"
        assert CalibrationResult.FAIL == "fail"
        assert CalibrationResult.INCOMPLETE == "incomplete"
        assert CalibrationResult.ABORTED == "aborted"


class TestCalibrationRecord:
    """Test CalibrationRecord model."""

    def test_minimal_calibration_record(self):
        """Test creating minimal calibration record."""
        record = CalibrationRecord(
            equipment_id="SCOPE_001",
            equipment_type="oscilloscope",
            equipment_model="DS1054Z",
            calibration_type=CalibrationType.FULL,
            due_date=datetime.now() + timedelta(days=365),
            result=CalibrationResult.PASS,
            performed_by="John Doe"
        )

        assert record.equipment_id == "SCOPE_001"
        assert record.equipment_type == "oscilloscope"
        assert record.equipment_model == "DS1054Z"
        assert record.calibration_type == CalibrationType.FULL
        assert record.result == CalibrationResult.PASS
        assert record.performed_by == "John Doe"
        assert record.calibration_id.startswith("cal_")
        assert isinstance(record.calibration_date, datetime)
        assert isinstance(record.created_at, datetime)

    def test_calibration_record_with_measurements(self):
        """Test calibration record with pre/post measurements."""
        record = CalibrationRecord(
            equipment_id="PSU_001",
            equipment_type="power_supply",
            equipment_model="E36312A",
            calibration_type=CalibrationType.FULL,
            due_date=datetime.now() + timedelta(days=365),
            result=CalibrationResult.PASS_WITH_ADJUSTMENT,
            performed_by="Jane Smith",
            pre_calibration_measurements={
                "voltage_ch1": {"setpoint": 5.0, "measured": 5.05},
                "current_ch1": {"setpoint": 1.0, "measured": 1.01}
            },
            post_calibration_measurements={
                "voltage_ch1": {"setpoint": 5.0, "measured": 5.00},
                "current_ch1": {"setpoint": 1.0, "measured": 1.00}
            }
        )

        assert record.result == CalibrationResult.PASS_WITH_ADJUSTMENT
        assert record.pre_calibration_measurements["voltage_ch1"]["measured"] == 5.05
        assert record.post_calibration_measurements["voltage_ch1"]["measured"] == 5.00

    def test_calibration_record_with_standards(self):
        """Test calibration record with calibration standards."""
        record = CalibrationRecord(
            equipment_id="DMM_001",
            equipment_type="multimeter",
            equipment_model="34465A",
            calibration_type=CalibrationType.FULL,
            due_date=datetime.now() + timedelta(days=365),
            result=CalibrationResult.PASS,
            performed_by="Cal Lab",
            standards_used=[
                {"name": "Fluke 5720A", "cert": "CERT-2024-001", "due": "2025-06-01"},
                {"name": "Keysight 3458A", "cert": "CERT-2024-002", "due": "2025-05-15"}
            ]
        )

        assert len(record.standards_used) == 2
        assert record.standards_used[0]["name"] == "Fluke 5720A"

    def test_calibration_record_with_environmental_data(self):
        """Test calibration record with environmental conditions."""
        record = CalibrationRecord(
            equipment_id="SCOPE_001",
            equipment_type="oscilloscope",
            equipment_model="DS1054Z",
            calibration_type=CalibrationType.VERIFICATION,
            due_date=datetime.now() + timedelta(days=365),
            result=CalibrationResult.PASS,
            performed_by="Tech1",
            temperature_celsius=23.5,
            humidity_percent=45.0
        )

        assert record.temperature_celsius == 23.5
        assert record.humidity_percent == 45.0

    def test_calibration_record_with_adjustments(self):
        """Test calibration record with adjustments and findings."""
        record = CalibrationRecord(
            equipment_id="LOAD_001",
            equipment_type="electronic_load",
            equipment_model="BK8500",
            calibration_type=CalibrationType.ADJUSTMENT,
            due_date=datetime.now() + timedelta(days=365),
            result=CalibrationResult.PASS_WITH_ADJUSTMENT,
            performed_by="Tech2",
            adjustments_made=[
                "Adjusted voltage reference",
                "Calibrated current sense resistor"
            ],
            out_of_tolerance_items=[
                "Voltage accuracy at 10V: +0.15% (spec: ±0.1%)"
            ]
        )

        assert len(record.adjustments_made) == 2
        assert len(record.out_of_tolerance_items) == 1
        assert "voltage reference" in record.adjustments_made[0]

    def test_calibration_record_json_serialization(self):
        """Test CalibrationRecord can be serialized to JSON."""
        record = CalibrationRecord(
            equipment_id="SCOPE_001",
            equipment_type="oscilloscope",
            equipment_model="DS1054Z",
            calibration_type=CalibrationType.FULL,
            due_date=datetime.now() + timedelta(days=365),
            result=CalibrationResult.PASS,
            performed_by="Tech1"
        )

        json_str = record.model_dump_json()
        data = json.loads(json_str)

        assert data["equipment_id"] == "SCOPE_001"
        assert data["calibration_type"] == "full"
        assert data["result"] == "pass"


class TestCalibrationSchedule:
    """Test CalibrationSchedule model."""

    def test_minimal_schedule(self):
        """Test creating minimal calibration schedule."""
        schedule = CalibrationSchedule(
            equipment_id="SCOPE_001",
            interval_days=365
        )

        assert schedule.equipment_id == "SCOPE_001"
        assert schedule.interval_days == 365
        assert schedule.warning_days == 30  # Default
        assert schedule.auto_schedule is True  # Default
        assert schedule.enabled is True  # Default
        assert schedule.schedule_id.startswith("sched_")

    def test_schedule_with_notifications(self):
        """Test schedule with notification settings."""
        schedule = CalibrationSchedule(
            equipment_id="PSU_001",
            interval_days=180,
            warning_days=14,
            notify_due_soon=True,
            notify_overdue=True,
            notification_emails=["admin@lab.com", "tech@lab.com"]
        )

        assert schedule.interval_days == 180
        assert schedule.warning_days == 14
        assert schedule.notify_due_soon is True
        assert len(schedule.notification_emails) == 2
        assert "admin@lab.com" in schedule.notification_emails

    def test_schedule_disabled(self):
        """Test creating disabled schedule."""
        schedule = CalibrationSchedule(
            equipment_id="LOAD_001",
            interval_days=365,
            enabled=False
        )

        assert schedule.enabled is False


class TestCalibrationManagerInit:
    """Test CalibrationManager initialization."""

    def test_manager_initialization(self):
        """Test CalibrationManager initializes correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            assert manager.storage_path == Path(tmpdir)
            assert isinstance(manager._records, dict)
            assert isinstance(manager._schedules, dict)
            assert manager.storage_path.exists()

    def test_manager_creates_storage_directory(self):
        """Test manager creates storage directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "calibration" / "data"
            manager = CalibrationManager(storage_path=str(storage_path))

            assert storage_path.exists()


class TestCalibrationManagerRecords:
    """Test CalibrationManager record management."""

    @pytest.mark.asyncio
    async def test_add_calibration_record(self):
        """Test adding a calibration record."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            record = CalibrationRecord(
                equipment_id="SCOPE_001",
                equipment_type="oscilloscope",
                equipment_model="DS1054Z",
                calibration_type=CalibrationType.FULL,
                due_date=datetime.now() + timedelta(days=365),
                result=CalibrationResult.PASS,
                performed_by="Tech1"
            )

            added_record = await manager.add_calibration_record(record)

            assert added_record.equipment_id == "SCOPE_001"
            assert "SCOPE_001" in manager._records
            assert len(manager._records["SCOPE_001"]) == 1

    @pytest.mark.asyncio
    async def test_add_multiple_records_same_equipment(self):
        """Test adding multiple records for same equipment."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            # Add first record
            record1 = CalibrationRecord(
                equipment_id="SCOPE_001",
                equipment_type="oscilloscope",
                equipment_model="DS1054Z",
                calibration_type=CalibrationType.FULL,
                due_date=datetime.now() + timedelta(days=365),
                result=CalibrationResult.PASS,
                performed_by="Tech1"
            )
            await manager.add_calibration_record(record1)

            # Add second record
            record2 = CalibrationRecord(
                equipment_id="SCOPE_001",
                equipment_type="oscilloscope",
                equipment_model="DS1054Z",
                calibration_type=CalibrationType.VERIFICATION,
                due_date=datetime.now() + timedelta(days=365),
                result=CalibrationResult.PASS,
                performed_by="Tech2"
            )
            await manager.add_calibration_record(record2)

            assert len(manager._records["SCOPE_001"]) == 2

    @pytest.mark.asyncio
    async def test_get_calibration_history(self):
        """Test retrieving calibration history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            # Add records with different dates
            for i in range(3):
                record = CalibrationRecord(
                    equipment_id="SCOPE_001",
                    equipment_type="oscilloscope",
                    equipment_model="DS1054Z",
                    calibration_type=CalibrationType.VERIFICATION,
                    calibration_date=datetime.now() - timedelta(days=(3-i)*30),
                    due_date=datetime.now() + timedelta(days=365),
                    result=CalibrationResult.PASS,
                    performed_by=f"Tech{i}"
                )
                await manager.add_calibration_record(record)

            history = await manager.get_calibration_history("SCOPE_001")

            assert len(history) == 3
            # Should be sorted by date, most recent first
            assert history[0].performed_by == "Tech2"  # Most recent
            assert history[2].performed_by == "Tech0"  # Oldest

    @pytest.mark.asyncio
    async def test_get_calibration_history_with_limit(self):
        """Test retrieving calibration history with limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            # Add 5 records
            for i in range(5):
                record = CalibrationRecord(
                    equipment_id="SCOPE_001",
                    equipment_type="oscilloscope",
                    equipment_model="DS1054Z",
                    calibration_type=CalibrationType.VERIFICATION,
                    due_date=datetime.now() + timedelta(days=365),
                    result=CalibrationResult.PASS,
                    performed_by=f"Tech{i}"
                )
                await manager.add_calibration_record(record)

            history = await manager.get_calibration_history("SCOPE_001", limit=2)

            assert len(history) == 2

    @pytest.mark.asyncio
    async def test_get_calibration_history_no_records(self):
        """Test retrieving history for equipment with no records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            history = await manager.get_calibration_history("UNKNOWN_001")

            assert history == []

    @pytest.mark.asyncio
    async def test_get_latest_calibration(self):
        """Test getting most recent calibration record."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            # Add records
            for i in range(3):
                record = CalibrationRecord(
                    equipment_id="SCOPE_001",
                    equipment_type="oscilloscope",
                    equipment_model="DS1054Z",
                    calibration_type=CalibrationType.VERIFICATION,
                    calibration_date=datetime.now() - timedelta(days=(3-i)*30),
                    due_date=datetime.now() + timedelta(days=365),
                    result=CalibrationResult.PASS,
                    performed_by=f"Tech{i}"
                )
                await manager.add_calibration_record(record)

            latest = await manager.get_latest_calibration("SCOPE_001")

            assert latest is not None
            assert latest.performed_by == "Tech2"  # Most recent

    @pytest.mark.asyncio
    async def test_get_latest_calibration_never_calibrated(self):
        """Test getting latest calibration for never-calibrated equipment."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            latest = await manager.get_latest_calibration("UNKNOWN_001")

            assert latest is None

    @pytest.mark.asyncio
    async def test_delete_calibration_record(self):
        """Test deleting a calibration record."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            record = CalibrationRecord(
                equipment_id="SCOPE_001",
                equipment_type="oscilloscope",
                equipment_model="DS1054Z",
                calibration_type=CalibrationType.FULL,
                due_date=datetime.now() + timedelta(days=365),
                result=CalibrationResult.PASS,
                performed_by="Tech1"
            )
            await manager.add_calibration_record(record)

            # Delete the record
            deleted = await manager.delete_calibration_record(
                "SCOPE_001",
                record.calibration_id
            )

            assert deleted is True
            assert len(manager._records["SCOPE_001"]) == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_record(self):
        """Test deleting a nonexistent record returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            deleted = await manager.delete_calibration_record(
                "UNKNOWN_001",
                "cal_nonexistent"
            )

            assert deleted is False


class TestCalibrationManagerStatus:
    """Test CalibrationManager status checking."""

    @pytest.mark.asyncio
    async def test_status_current(self):
        """Test status is CURRENT for calibration well before due date."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            record = CalibrationRecord(
                equipment_id="SCOPE_001",
                equipment_type="oscilloscope",
                equipment_model="DS1054Z",
                calibration_type=CalibrationType.FULL,
                calibration_date=datetime.now() - timedelta(days=30),
                due_date=datetime.now() + timedelta(days=200),  # Far in future
                result=CalibrationResult.PASS,
                performed_by="Tech1"
            )
            await manager.add_calibration_record(record)

            status = await manager.get_calibration_status("SCOPE_001")

            assert status == CalibrationStatus.CURRENT

    @pytest.mark.asyncio
    async def test_status_due_soon(self):
        """Test status is DUE_SOON when approaching due date."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            # Set up schedule with 30-day warning
            schedule = CalibrationSchedule(
                equipment_id="SCOPE_001",
                interval_days=365,
                warning_days=30
            )
            await manager.set_calibration_schedule(schedule)

            record = CalibrationRecord(
                equipment_id="SCOPE_001",
                equipment_type="oscilloscope",
                equipment_model="DS1054Z",
                calibration_type=CalibrationType.FULL,
                calibration_date=datetime.now() - timedelta(days=350),
                due_date=datetime.now() + timedelta(days=15),  # Within warning period
                result=CalibrationResult.PASS,
                performed_by="Tech1"
            )
            await manager.add_calibration_record(record)

            status = await manager.get_calibration_status("SCOPE_001")

            assert status == CalibrationStatus.DUE_SOON

    @pytest.mark.asyncio
    async def test_status_due(self):
        """Test status is DUE when calibration is due today."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            record = CalibrationRecord(
                equipment_id="SCOPE_001",
                equipment_type="oscilloscope",
                equipment_model="DS1054Z",
                calibration_type=CalibrationType.FULL,
                calibration_date=datetime.now() - timedelta(days=365),
                due_date=datetime.now(),  # Due today
                result=CalibrationResult.PASS,
                performed_by="Tech1"
            )
            await manager.add_calibration_record(record)

            status = await manager.get_calibration_status("SCOPE_001")

            assert status == CalibrationStatus.DUE

    @pytest.mark.asyncio
    async def test_status_overdue(self):
        """Test status is OVERDUE when past due date."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            record = CalibrationRecord(
                equipment_id="SCOPE_001",
                equipment_type="oscilloscope",
                equipment_model="DS1054Z",
                calibration_type=CalibrationType.FULL,
                calibration_date=datetime.now() - timedelta(days=400),
                due_date=datetime.now() - timedelta(days=30),  # Overdue by 30 days
                result=CalibrationResult.PASS,
                performed_by="Tech1"
            )
            await manager.add_calibration_record(record)

            status = await manager.get_calibration_status("SCOPE_001")

            assert status == CalibrationStatus.OVERDUE

    @pytest.mark.asyncio
    async def test_status_never_calibrated(self):
        """Test status is NEVER_CALIBRATED for equipment with no records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            status = await manager.get_calibration_status("SCOPE_001")

            assert status == CalibrationStatus.NEVER_CALIBRATED

    @pytest.mark.asyncio
    async def test_is_calibration_current_true(self):
        """Test is_calibration_current returns True for current calibration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            record = CalibrationRecord(
                equipment_id="SCOPE_001",
                equipment_type="oscilloscope",
                equipment_model="DS1054Z",
                calibration_type=CalibrationType.FULL,
                due_date=datetime.now() + timedelta(days=200),
                result=CalibrationResult.PASS,
                performed_by="Tech1"
            )
            await manager.add_calibration_record(record)

            is_current = await manager.is_calibration_current("SCOPE_001")

            assert is_current is True

    @pytest.mark.asyncio
    async def test_is_calibration_current_false_overdue(self):
        """Test is_calibration_current returns False for overdue calibration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            record = CalibrationRecord(
                equipment_id="SCOPE_001",
                equipment_type="oscilloscope",
                equipment_model="DS1054Z",
                calibration_type=CalibrationType.FULL,
                due_date=datetime.now() - timedelta(days=30),
                result=CalibrationResult.PASS,
                performed_by="Tech1"
            )
            await manager.add_calibration_record(record)

            is_current = await manager.is_calibration_current("SCOPE_001")

            assert is_current is False

    @pytest.mark.asyncio
    async def test_get_days_until_due_positive(self):
        """Test getting days until due (positive value)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            record = CalibrationRecord(
                equipment_id="SCOPE_001",
                equipment_type="oscilloscope",
                equipment_model="DS1054Z",
                calibration_type=CalibrationType.FULL,
                due_date=datetime.now() + timedelta(days=45),
                result=CalibrationResult.PASS,
                performed_by="Tech1"
            )
            await manager.add_calibration_record(record)

            days_until_due = await manager.get_days_until_due("SCOPE_001")

            assert days_until_due is not None
            assert 44 <= days_until_due <= 45  # Account for timing

    @pytest.mark.asyncio
    async def test_get_days_until_due_negative(self):
        """Test getting days until due (negative when overdue)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            record = CalibrationRecord(
                equipment_id="SCOPE_001",
                equipment_type="oscilloscope",
                equipment_model="DS1054Z",
                calibration_type=CalibrationType.FULL,
                due_date=datetime.now() - timedelta(days=15),
                result=CalibrationResult.PASS,
                performed_by="Tech1"
            )
            await manager.add_calibration_record(record)

            days_until_due = await manager.get_days_until_due("SCOPE_001")

            assert days_until_due is not None
            assert days_until_due < 0

    @pytest.mark.asyncio
    async def test_get_days_until_due_never_calibrated(self):
        """Test getting days until due returns None for never-calibrated equipment."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            days_until_due = await manager.get_days_until_due("SCOPE_001")

            assert days_until_due is None


class TestCalibrationManagerSchedule:
    """Test CalibrationManager schedule management."""

    @pytest.mark.asyncio
    async def test_set_calibration_schedule(self):
        """Test setting a calibration schedule."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            schedule = CalibrationSchedule(
                equipment_id="SCOPE_001",
                interval_days=365,
                warning_days=30
            )

            await manager.set_calibration_schedule(schedule)

            assert "SCOPE_001" in manager._schedules
            assert manager._schedules["SCOPE_001"].interval_days == 365

    @pytest.mark.asyncio
    async def test_get_calibration_schedule(self):
        """Test retrieving a calibration schedule."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            schedule = CalibrationSchedule(
                equipment_id="SCOPE_001",
                interval_days=180
            )
            await manager.set_calibration_schedule(schedule)

            retrieved = await manager.get_calibration_schedule("SCOPE_001")

            assert retrieved is not None
            assert retrieved.interval_days == 180

    @pytest.mark.asyncio
    async def test_get_nonexistent_schedule(self):
        """Test retrieving nonexistent schedule returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            retrieved = await manager.get_calibration_schedule("UNKNOWN_001")

            assert retrieved is None

    @pytest.mark.asyncio
    async def test_delete_calibration_schedule(self):
        """Test deleting a calibration schedule."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            schedule = CalibrationSchedule(
                equipment_id="SCOPE_001",
                interval_days=365
            )
            await manager.set_calibration_schedule(schedule)

            deleted = await manager.delete_calibration_schedule("SCOPE_001")

            assert deleted is True
            assert "SCOPE_001" not in manager._schedules

    @pytest.mark.asyncio
    async def test_delete_nonexistent_schedule(self):
        """Test deleting nonexistent schedule returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            deleted = await manager.delete_calibration_schedule("UNKNOWN_001")

            assert deleted is False


class TestCalibrationManagerDueList:
    """Test CalibrationManager due calibrations tracking."""

    @pytest.mark.asyncio
    async def test_get_due_calibrations_empty(self):
        """Test getting due calibrations when none are due."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            # Add current calibration
            record = CalibrationRecord(
                equipment_id="SCOPE_001",
                equipment_type="oscilloscope",
                equipment_model="DS1054Z",
                calibration_type=CalibrationType.FULL,
                due_date=datetime.now() + timedelta(days=200),
                result=CalibrationResult.PASS,
                performed_by="Tech1"
            )
            await manager.add_calibration_record(record)

            due_list = await manager.get_due_calibrations()

            assert len(due_list) == 0

    @pytest.mark.asyncio
    async def test_get_due_calibrations_overdue(self):
        """Test getting overdue calibrations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            record = CalibrationRecord(
                equipment_id="SCOPE_001",
                equipment_type="oscilloscope",
                equipment_model="DS1054Z",
                calibration_type=CalibrationType.FULL,
                due_date=datetime.now() - timedelta(days=30),
                result=CalibrationResult.PASS,
                performed_by="Tech1"
            )
            await manager.add_calibration_record(record)

            due_list = await manager.get_due_calibrations()

            assert len(due_list) == 1
            assert due_list[0]["equipment_id"] == "SCOPE_001"
            assert due_list[0]["status"] == "overdue"
            assert due_list[0]["days_until_due"] < 0

    @pytest.mark.asyncio
    async def test_get_due_calibrations_excluding_due_soon(self):
        """Test getting due calibrations excluding due_soon."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            # Set up schedule
            schedule = CalibrationSchedule(
                equipment_id="SCOPE_001",
                interval_days=365,
                warning_days=30
            )
            await manager.set_calibration_schedule(schedule)

            # Add calibration due soon
            record = CalibrationRecord(
                equipment_id="SCOPE_001",
                equipment_type="oscilloscope",
                equipment_model="DS1054Z",
                calibration_type=CalibrationType.FULL,
                due_date=datetime.now() + timedelta(days=15),
                result=CalibrationResult.PASS,
                performed_by="Tech1"
            )
            await manager.add_calibration_record(record)

            due_list = await manager.get_due_calibrations(include_due_soon=False)

            assert len(due_list) == 0  # Should exclude due_soon

    @pytest.mark.asyncio
    async def test_get_due_calibrations_sorted(self):
        """Test due calibrations are sorted by urgency."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            # Add multiple due calibrations
            equipment_data = [
                ("SCOPE_001", -30),  # Most overdue
                ("PSU_001", -10),
                ("LOAD_001", 0),     # Due today
            ]

            for eq_id, days_offset in equipment_data:
                record = CalibrationRecord(
                    equipment_id=eq_id,
                    equipment_type="equipment",
                    equipment_model="Model",
                    calibration_type=CalibrationType.FULL,
                    due_date=datetime.now() + timedelta(days=days_offset),
                    result=CalibrationResult.PASS,
                    performed_by="Tech1"
                )
                await manager.add_calibration_record(record)

            due_list = await manager.get_due_calibrations(include_due_soon=False)

            assert len(due_list) == 3
            # Most overdue should be first
            assert due_list[0]["equipment_id"] == "SCOPE_001"
            assert due_list[2]["equipment_id"] == "LOAD_001"


class TestCalibrationManagerReporting:
    """Test CalibrationManager report generation."""

    @pytest.mark.asyncio
    async def test_generate_calibration_report_all_equipment(self):
        """Test generating report for all equipment."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            # Add various calibration statuses
            equipment = [
                ("SCOPE_001", 200, CalibrationResult.PASS),  # Current
                ("PSU_001", 15, CalibrationResult.PASS),      # Due soon
                ("LOAD_001", -10, CalibrationResult.PASS),    # Overdue
            ]

            for eq_id, days_offset, result in equipment:
                record = CalibrationRecord(
                    equipment_id=eq_id,
                    equipment_type="equipment",
                    equipment_model="Model",
                    calibration_type=CalibrationType.FULL,
                    due_date=datetime.now() + timedelta(days=days_offset),
                    result=result,
                    performed_by="Tech1"
                )
                await manager.add_calibration_record(record)

            report = await manager.generate_calibration_report()

            assert report["total_equipment"] == 3
            assert isinstance(report["generated_at"], datetime)
            assert len(report["equipment_details"]) == 3
            # Check status summary
            assert report["status_summary"]["current"] >= 1
            assert report["status_summary"]["overdue"] >= 1

    @pytest.mark.asyncio
    async def test_generate_calibration_report_specific_equipment(self):
        """Test generating report for specific equipment."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CalibrationManager(storage_path=tmpdir)

            # Add multiple equipment
            for i in range(5):
                record = CalibrationRecord(
                    equipment_id=f"SCOPE_{i:03d}",
                    equipment_type="oscilloscope",
                    equipment_model="DS1054Z",
                    calibration_type=CalibrationType.FULL,
                    due_date=datetime.now() + timedelta(days=200),
                    result=CalibrationResult.PASS,
                    performed_by="Tech1"
                )
                await manager.add_calibration_record(record)

            # Generate report for specific equipment only
            report = await manager.generate_calibration_report(
                equipment_ids=["SCOPE_000", "SCOPE_001"]
            )

            assert report["total_equipment"] == 2
            assert len(report["equipment_details"]) == 2


class TestCalibrationManagerPersistence:
    """Test CalibrationManager data persistence."""

    @pytest.mark.asyncio
    async def test_records_persistence(self):
        """Test calibration records are saved and loaded correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create manager and add record
            manager1 = CalibrationManager(storage_path=tmpdir)

            record = CalibrationRecord(
                equipment_id="SCOPE_001",
                equipment_type="oscilloscope",
                equipment_model="DS1054Z",
                calibration_type=CalibrationType.FULL,
                due_date=datetime.now() + timedelta(days=365),
                result=CalibrationResult.PASS,
                performed_by="Tech1",
                notes="Test calibration"
            )
            await manager1.add_calibration_record(record)

            # Create new manager instance (should load saved data)
            manager2 = CalibrationManager(storage_path=tmpdir)

            loaded_record = await manager2.get_latest_calibration("SCOPE_001")
            assert loaded_record is not None
            assert loaded_record.notes == "Test calibration"

    @pytest.mark.asyncio
    async def test_schedules_persistence(self):
        """Test calibration schedules are saved and loaded correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create manager and add schedule
            manager1 = CalibrationManager(storage_path=tmpdir)

            schedule = CalibrationSchedule(
                equipment_id="SCOPE_001",
                interval_days=180,
                warning_days=14
            )
            await manager1.set_calibration_schedule(schedule)

            # Create new manager instance (should load saved data)
            manager2 = CalibrationManager(storage_path=tmpdir)

            loaded_schedule = await manager2.get_calibration_schedule("SCOPE_001")
            assert loaded_schedule is not None
            assert loaded_schedule.interval_days == 180
            assert loaded_schedule.warning_days == 14


class TestGlobalCalibrationManager:
    """Test global calibration manager functions."""

    def test_initialize_calibration_manager(self):
        """Test initializing global calibration manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = initialize_calibration_manager(storage_path=tmpdir)

            assert manager is not None
            assert isinstance(manager, CalibrationManager)

            # Get the global instance
            global_manager = get_calibration_manager()
            assert global_manager is manager

    def test_get_calibration_manager_before_init(self):
        """Test getting calibration manager before initialization."""
        # This test depends on global state, so we just check it returns something
        # (it may be None or a previously initialized manager)
        result = get_calibration_manager()
        # Just verify the function works
        assert result is None or isinstance(result, CalibrationManager)


# Mark all tests as unit tests
pytestmark = pytest.mark.unit
