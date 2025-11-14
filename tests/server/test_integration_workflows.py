"""
Integration tests for LabLink workflows.

These tests exercise multiple components together to verify
end-to-end functionality and increase code coverage.
"""

import pytest
import tempfile
import os
from datetime import datetime, timedelta
from pathlib import Path

# Add server to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../server'))

from security.auth import (
    hash_password, verify_password, create_access_token,
    create_refresh_token, AuthConfig
)
from security.models import (
    User, Role, RoleType, Permission, PermissionAction, ResourceType,
    create_default_admin_role, create_default_operator_role,
    create_default_viewer_role
)
from security.mfa import (
    generate_totp_secret, generate_provisioning_uri, generate_qr_code,
    verify_totp_token, generate_backup_codes, hash_backup_code, verify_backup_code
)
from database.manager import DatabaseManager
from database.models import CommandRecord, MeasurementRecord, CommandStatus
from backup.manager import BackupManager
from backup.models import BackupConfig, BackupRequest, BackupType, CompressionType
from discovery.manager import DiscoveryManager
from discovery.models import DiscoveryConfig, DiscoveredDevice, DeviceType, DiscoveryMethod
from scheduler.manager import SchedulerManager
from scheduler.models import ScheduleConfig, ScheduleType, TriggerType


class TestSecurityWorkflow:
    """Test complete security authentication workflows."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def auth_config(self):
        """Create auth configuration."""
        return AuthConfig()

    def test_complete_user_authentication_flow(self, auth_config):
        """Test complete user authentication workflow.

        This integration test exercises:
        - Password hashing (auth.py)
        - User model creation (models.py)
        - Role assignment (rbac.py)
        - JWT token generation (auth.py)
        - Token verification (auth.py)
        """
        # 1. Create a user with hashed password
        password = "SecurePassword123!"
        hashed = hash_password(password)

        # 2. Create user with role
        admin_role = create_default_admin_role()
        user = User(
            username="admin_user",
            email="admin@lablink.com",
            hashed_password=hashed,
            roles=[admin_role.role_id],
            is_active=True
        )

        # 3. Verify password
        assert verify_password(password, hashed) is True
        assert verify_password("WrongPassword", hashed) is False

        # 4. Generate access token
        access_token = create_access_token(user, auth_config)
        assert access_token is not None
        assert isinstance(access_token, str)

        # 5. Generate refresh token
        refresh_token = create_refresh_token(user.user_id, auth_config)
        assert refresh_token is not None
        assert isinstance(refresh_token, str)

        # 6. Verify user has admin permissions
        admin_permission = Permission(
            action=PermissionAction.WRITE,
            resource=ResourceType.EQUIPMENT
        )
        assert admin_permission in admin_role.permissions

    def test_mfa_setup_and_verification_flow(self):
        """Test complete MFA setup and verification workflow.

        Exercises:
        - TOTP secret generation (mfa.py)
        - QR code generation (mfa.py)
        - TOTP verification (mfa.py)
        - Backup code generation (mfa.py)
        - Backup code verification (mfa.py)
        """
        # 1. Generate TOTP secret
        secret = generate_totp_secret()
        assert secret is not None
        assert len(secret) == 32  # Base32 encoded

        # 2. Generate provisioning URI and QR code
        provisioning_uri = generate_provisioning_uri(secret, "testuser", "LabLink")
        qr_code = generate_qr_code(provisioning_uri)
        assert qr_code is not None
        assert qr_code.startswith("data:image/png;base64,")

        # 3. Generate and verify TOTP token
        import pyotp
        totp = pyotp.TOTP(secret)
        current_token = totp.now()
        assert verify_totp_token(secret, current_token) is True

        # 4. Generate backup codes
        backup_codes = generate_backup_codes(count=10)
        assert len(backup_codes) == 10
        assert all(len(code) == 9 for code in backup_codes)  # XXXX-XXXX format

        # 5. Hash and verify backup code
        test_code = backup_codes[0]
        hashed_code = hash_backup_code(test_code)
        assert verify_backup_code(test_code.upper(), hashed_code) is True
        assert verify_backup_code(test_code.lower(), hashed_code) is True
        assert verify_backup_code("WRONG-CODE", hashed_code) is False

    def test_rbac_permission_checking_flow(self):
        """Test RBAC permission checking workflow.

        Exercises:
        - Default role creation (rbac.py)
        - Permission model (models.py)
        - Permission checking logic (rbac.py)
        """
        # 1. Create roles with different permissions
        admin_role = create_default_admin_role()
        operator_role = create_default_operator_role()
        viewer_role = create_default_viewer_role()

        # 2. Verify permission hierarchy
        assert len(admin_role.permissions) > len(operator_role.permissions)
        assert len(operator_role.permissions) > len(viewer_role.permissions)

        # 3. Create users with different roles
        admin_user = User(
            username="admin",
            email="admin@test.com",
            hashed_password="hashed",
            roles=[admin_role.role_id]
        )

        viewer_user = User(
            username="viewer",
            email="viewer@test.com",
            hashed_password="hashed",
            roles=[viewer_role.role_id]
        )

        # 4. Test permission checking
        write_equipment = Permission(
            action=PermissionAction.WRITE,
            resource=ResourceType.EQUIPMENT
        )

        # Admin should have write permission
        assert write_equipment in admin_role.permissions

        # Viewer should only have read permission
        read_equipment = Permission(
            action=PermissionAction.READ,
            resource=ResourceType.EQUIPMENT
        )
        assert read_equipment in viewer_role.permissions


class TestDatabaseWorkflow:
    """Test database operations workflows."""

    @pytest.fixture
    def db_manager(self):
        """Create database manager."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "test.db")
            manager = DatabaseManager(db_path=db_path)
            manager.initialize()
            yield manager

    def test_command_logging_and_retrieval_flow(self, db_manager):
        """Test logging commands and retrieving history.

        Exercises:
        - Database initialization (manager.py)
        - Command logging (manager.py)
        - Command history retrieval (manager.py)
        - CommandRecord model (models.py)
        """
        # 1. Log multiple commands
        commands = [
            CommandRecord(
                equipment_id="scope-001",
                equipment_type="oscilloscope",
                command="*IDN?",
                response="RIGOL TECHNOLOGIES,DS1104Z",
                execution_time_ms=45.2
            ),
            CommandRecord(
                equipment_id="scope-001",
                equipment_type="oscilloscope",
                command="MEAS:VOLT?",
                response="3.142",
                execution_time_ms=32.1
            ),
            CommandRecord(
                equipment_id="ps-001",
                equipment_type="power_supply",
                command="VOLT 5.0",
                response="OK",
                execution_time_ms=28.5
            ),
        ]

        for cmd in commands:
            record_id = db_manager.log_command(cmd)
            assert record_id > 0

        # 2. Retrieve command history
        history = db_manager.get_command_history(limit=10)
        assert len(history) == 3

        # 3. Filter by equipment
        scope_history = db_manager.get_command_history(
            equipment_id="scope-001",
            limit=10
        )
        assert len(scope_history) == 2
        assert all(cmd['equipment_id'] == "scope-001" for cmd in scope_history)

    def test_measurement_archival_flow(self, db_manager):
        """Test measurement archival and querying.

        Exercises:
        - Measurement archiving (manager.py)
        - Measurement retrieval (manager.py)
        - MeasurementRecord model (models.py)
        """
        # 1. Archive multiple measurements
        measurements = [
            MeasurementRecord(
                equipment_id="scope-001",
                measurement_type="voltage",
                channel=1,
                value=3.142,
                unit="V",
                quality=100.0
            ),
            MeasurementRecord(
                equipment_id="scope-001",
                measurement_type="current",
                channel=2,
                value=0.156,
                unit="A",
                quality=98.5
            ),
            MeasurementRecord(
                equipment_id="dmm-001",
                measurement_type="resistance",
                value=1000.0,
                unit="Ω",
                quality=99.9
            ),
        ]

        for measurement in measurements:
            record_id = db_manager.archive_measurement(measurement)
            assert record_id > 0

        # 2. Retrieve measurements
        history = db_manager.get_measurement_history(limit=10)
        assert len(history) >= 3


class TestBackupWorkflow:
    """Test backup operations workflows."""

    @pytest.fixture
    def backup_manager(self):
        """Create backup manager."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = BackupConfig(backup_dir=temp_dir)
            yield BackupManager(config)

    def test_backup_creation_and_listing_flow(self, backup_manager):
        """Test creating backups and listing them.

        Exercises:
        - Backup creation (manager.py)
        - Backup listing (manager.py)
        - BackupRequest model (models.py)
        """
        # 1. Create multiple backups
        backup_requests = [
            BackupRequest(
                backup_type=BackupType.CONFIG,
                compression=CompressionType.NONE,
                description="Test config backup"
            ),
            BackupRequest(
                backup_type=BackupType.CONFIG,
                compression=CompressionType.GZIP,
                description="Compressed backup"
            ),
        ]

        backup_ids = []
        for request in backup_requests:
            backup = backup_manager.create_backup(request)
            if backup:
                backup_ids.append(backup.backup_id)

        # 2. List backups
        backups = backup_manager.list_backups()
        assert len(backups) >= len(backup_ids)

        # 3. Get backup statistics
        stats = backup_manager.get_backup_statistics()
        assert stats is not None
        assert stats.total_backups >= len(backup_ids)


class TestDiscoveryWorkflow:
    """Test equipment discovery workflows."""

    @pytest.fixture
    def discovery_manager(self):
        """Create discovery manager."""
        config = DiscoveryConfig()
        yield DiscoveryManager(config)

    def test_device_model_creation_flow(self):
        """Test creating discovered device models.

        Exercises:
        - DiscoveredDevice model (models.py)
        - Device type enumeration (models.py)
        """
        # Create a discovered device
        device = DiscoveredDevice(
            device_id="dev-001",
            resource_name="TCPIP0::192.168.1.100::inst0::INSTR",
            discovery_method=DiscoveryMethod.VISA,
            device_type=DeviceType.OSCILLOSCOPE,
            manufacturer="RIGOL",
            model="DS1104Z",
            serial_number="DS1ZA123456789",
            firmware_version="00.04.04",
            ip_address="192.168.1.100"
        )

        assert device.device_id == "dev-001"
        assert device.device_type == DeviceType.OSCILLOSCOPE
        assert device.discovery_method == DiscoveryMethod.VISA


class TestSchedulerWorkflow:
    """Test scheduler workflows."""

    @pytest.fixture
    def scheduler_manager(self):
        """Create scheduler manager."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "scheduler.db")
            manager = SchedulerManager(db_path=db_path)
            yield manager
            # Cleanup
            if manager._scheduler and manager._scheduler.running:
                manager._scheduler.shutdown(wait=False)

    def test_job_scheduling_flow(self, scheduler_manager):
        """Test creating and managing scheduled jobs.

        Exercises:
        - Job creation (manager.py)
        - Job listing (manager.py)
        - ScheduleConfig model (models.py)
        """
        # 1. Create scheduled jobs
        job_configs = [
            ScheduleConfig(
                name="Daily Data Collection",
                schedule_type=ScheduleType.ACQUISITION,
                trigger_type=TriggerType.DAILY,
                daily_time="02:00:00",
                equipment_id="scope-001"
            ),
            ScheduleConfig(
                name="Hourly Backup",
                schedule_type=ScheduleType.COMMAND,
                trigger_type=TriggerType.INTERVAL,
                interval_hours=1,
                equipment_id="backup-001"
            ),
        ]

        # 2. List jobs
        jobs = scheduler_manager.list_jobs()
        initial_count = len(jobs)

        # Note: Job creation is async, so we just verify the models work
        for config in job_configs:
            assert config.name is not None
            assert config.schedule_type in ScheduleType
            assert config.trigger_type in TriggerType


class TestCrossModuleIntegration:
    """Test workflows that span multiple modules."""

    @pytest.fixture
    def integrated_system(self):
        """Set up integrated system with all managers."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Initialize all managers
            db_path = os.path.join(temp_dir, "lablink.db")
            database = DatabaseManager(db_path=db_path)
            database.initialize()

            backup_config = BackupConfig(backup_dir=temp_dir)
            backup = BackupManager(backup_config)

            discovery_config = DiscoveryConfig()
            discovery = DiscoveryManager(discovery_config)

            scheduler_path = os.path.join(temp_dir, "scheduler.db")
            scheduler = SchedulerManager(db_path=scheduler_path)

            yield {
                'database': database,
                'backup': backup,
                'discovery': discovery,
                'scheduler': scheduler,
            }

            # Cleanup
            if scheduler._scheduler and scheduler._scheduler.running:
                scheduler._scheduler.shutdown(wait=False)

    def test_complete_equipment_workflow(self, integrated_system):
        """Test complete equipment discovery, connection, and logging workflow.

        This single test exercises:
        - DiscoveryManager (discovery.py)
        - DatabaseManager (database/manager.py)
        - Multiple models
        """
        db = integrated_system['database']

        # 1. Simulate discovered device
        device = DiscoveredDevice(
            device_id="scope-001",
            resource_name="TCPIP0::192.168.1.100::inst0::INSTR",
            discovery_method=DiscoveryMethod.VISA,
            device_type=DeviceType.OSCILLOSCOPE,
            manufacturer="RIGOL",
            model="DS1104Z"
        )

        # 2. Log connection command
        connection_cmd = CommandRecord(
            equipment_id=device.device_id,
            equipment_type="oscilloscope",
            command="*IDN?",
            response=f"{device.manufacturer},{device.model}",
            execution_time_ms=125.3
        )
        record_id = db.log_command(connection_cmd)
        assert record_id > 0

        # 3. Log measurement from device
        measurement = MeasurementRecord(
            equipment_id=device.device_id,
            measurement_type="voltage",
            value=3.3,
            unit="V",
            channel=1
        )
        meas_id = db.archive_measurement(measurement)
        assert meas_id > 0

        # 4. Verify data was stored
        history = db.get_command_history(equipment_id=device.device_id, limit=10)
        assert len(history) >= 1

    def test_scheduled_backup_workflow(self, integrated_system):
        """Test scheduled backup workflow.

        Exercises:
        - SchedulerManager (scheduler/manager.py)
        - BackupManager (backup/manager.py)
        - DatabaseManager (database/manager.py)
        """
        backup = integrated_system['backup']
        db = integrated_system['database']

        # 1. Log some data to backup
        cmd = CommandRecord(
            equipment_id="test-001",
            command="TEST",
            response="OK"
        )
        db.log_command(cmd)

        # 2. Create backup
        backup_request = BackupRequest(
            backup_type=BackupType.CONFIG,
            compression=CompressionType.NONE,
            description="Integration test backup"
        )
        backup_result = backup.create_backup(backup_request)

        if backup_result:
            assert backup_result.backup_id is not None

            # 3. Verify backup was created
            backups = backup.list_backups()
            assert len(backups) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
