"""
Simple integration tests focusing on working functionality.

These tests exercise real code paths across multiple modules
to increase code coverage effectively.
"""

import pytest
import tempfile
import os
from datetime import datetime

# Add server to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../server'))

from security.auth import hash_password, verify_password, AuthConfig
from security.models import User, Role, RoleType, Permission, PermissionAction, ResourceType
from security.mfa import (
    generate_totp_secret, generate_provisioning_uri, generate_qr_code,
    generate_backup_codes, hash_backup_code
)
from database.manager import DatabaseManager
from database.models import CommandRecord, MeasurementRecord
from backup.models import BackupConfig, BackupRequest, BackupType, CompressionType
from discovery.models import DiscoveredDevice, DeviceType, DiscoveryMethod, DiscoveryConfig
from discovery.manager import DiscoveryManager
from scheduler.models import ScheduleConfig, ScheduleType, TriggerType


class TestSecurityIntegration:
    """Integration tests for security module."""

    def test_password_hashing_workflow(self):
        """Test password hashing and verification."""
        password = "TestPassword123!"
        hashed = hash_password(password)
        
        assert verify_password(password, hashed) is True
        assert verify_password("WrongPassword", hashed) is False

    def test_mfa_secret_generation(self):
        """Test MFA secret and QR code generation."""
        secret = generate_totp_secret()
        assert len(secret) == 32
        
        uri = generate_provisioning_uri(secret, "testuser", "LabLink")
        assert "testuser" in uri
        assert "LabLink" in uri
        
        qr = generate_qr_code(uri)
        assert qr.startswith("data:image/png;base64,")

    def test_backup_code_generation(self):
        """Test backup code generation."""
        codes = generate_backup_codes(count=10)
        assert len(codes) == 10
        
        test_code = codes[0]
        hashed = hash_backup_code(test_code)
        assert hashed is not None
        assert hashed.startswith("$2b$")

    def test_permission_model_creation(self):
        """Test creating permission models."""
        perm = Permission(
            action=PermissionAction.READ,
            resource=ResourceType.EQUIPMENT
        )
        
        assert perm.action == PermissionAction.READ
        assert perm.resource == ResourceType.EQUIPMENT

    def test_user_model_creation(self):
        """Test creating user models."""
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password=hash_password("password"),
            is_active=True
        )
        
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.is_active is True


class TestDatabaseIntegration:
    """Integration tests for database module."""

    @pytest.fixture
    def db(self):
        """Create database manager."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "test.db")
            manager = DatabaseManager(db_path=db_path)
            manager.initialize()
            yield manager

    def test_command_logging_workflow(self, db):
        """Test logging and retrieving commands."""
        # Log commands
        cmd1 = CommandRecord(
            equipment_id="scope-001",
            equipment_type="oscilloscope",
            command="*IDN?",
            response="RIGOL",
            execution_time_ms=45.2
        )
        cmd2 = CommandRecord(
            equipment_id="scope-001",
            equipment_type="oscilloscope",
            command="MEAS:VOLT?",
            response="3.142",
            execution_time_ms=32.1
        )
        
        id1 = db.log_command(cmd1)
        id2 = db.log_command(cmd2)
        
        assert id1 > 0
        assert id2 > 0
        
        # Retrieve history  
        result = db.get_command_history(equipment_id="scope-001", limit=10)
        assert result.total_count >= 2
        assert len(result.records) >= 2

    def test_measurement_archival_workflow(self, db):
        """Test archiving measurements."""
        measurement = MeasurementRecord(
            equipment_id="scope-001",
            measurement_type="voltage",
            channel=1,
            value=3.142,
            unit="V",
            quality=100.0
        )
        
        meas_id = db.archive_measurement(measurement)
        assert meas_id > 0

    def test_database_query_result_model(self, db):
        """Test QueryResult model works correctly."""
        cmd = CommandRecord(
            equipment_id="test-001",
            command="TEST",
            response="OK"
        )
        db.log_command(cmd)
        
        result = db.get_command_history(limit=10)
        
        # Verify QueryResult structure
        assert hasattr(result, 'records')
        assert hasattr(result, 'total_count')
        assert hasattr(result, 'page')
        assert hasattr(result, 'page_size')
        assert result.total_count > 0
        assert len(result.records) > 0


class TestModelIntegration:
    """Integration tests for model creation."""

    def test_discovered_device_creation(self):
        """Test creating discovered device models."""
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
        assert device.ip_address == "192.168.1.100"

    def test_schedule_config_creation(self):
        """Test creating schedule configurations."""
        config = ScheduleConfig(
            name="Daily Backup",
            schedule_type=ScheduleType.COMMAND,
            trigger_type=TriggerType.DAILY,
            daily_time="02:00:00",
            equipment_id="backup-001"
        )
        
        assert config.name == "Daily Backup"
        assert config.schedule_type == ScheduleType.COMMAND
        assert config.trigger_type == TriggerType.DAILY

    def test_backup_request_creation(self):
        """Test creating backup requests."""
        request = BackupRequest(
            backup_type=BackupType.CONFIG,
            compression=CompressionType.GZIP,
            description="Test backup"
        )
        
        assert request.backup_type == BackupType.CONFIG
        assert request.compression == CompressionType.GZIP


class TestDiscoveryIntegration:
    """Integration tests for discovery module."""

    def test_discovery_manager_initialization(self):
        """Test initializing discovery manager."""
        config = DiscoveryConfig()
        manager = DiscoveryManager(config)
        
        assert manager is not None
        assert manager.config is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
