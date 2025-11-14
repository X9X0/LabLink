"""Performance benchmarks for critical LabLink operations.

Run with: pytest tests/performance/ --benchmark-only
View results: pytest tests/performance/ --benchmark-only --benchmark-autosave
"""

import tempfile
from pathlib import Path

import pytest

from server.security.auth import hash_password, verify_password
from server.security.mfa import generate_totp_secret, verify_totp_token
from server.database.manager import DatabaseManager
from server.database.models import CommandRecord, CommandStatus, DatabaseConfig
from server.backup.manager import BackupManager
from server.backup.models import BackupConfig, BackupRequest, BackupType, CompressionType


# ====================================================================================
# Security Benchmarks
# ====================================================================================


class TestSecurityBenchmarks:
    """Benchmark security operations."""

    def test_password_hashing(self, benchmark):
        """Benchmark password hashing (bcrypt)."""
        password = "TestPassword123!"
        result = benchmark(hash_password, password)
        assert result is not None

    def test_password_verification(self, benchmark):
        """Benchmark password verification."""
        password = "TestPassword123!"
        hashed = hash_password(password)
        result = benchmark(verify_password, password, hashed)
        assert result is True

    def test_totp_generation(self, benchmark):
        """Benchmark TOTP secret generation."""
        result = benchmark(generate_totp_secret)
        assert len(result) == 32

    def test_totp_verification(self, benchmark):
        """Benchmark TOTP token verification."""
        from server.security.mfa import get_current_totp_token

        secret = generate_totp_secret()

        def verify_current_token():
            # Generate fresh token for each benchmark iteration to avoid expiration
            token = get_current_totp_token(secret)
            return verify_totp_token(secret, token)  # Correct order: secret, token

        # Benchmark runs the function multiple times, just ensure it completes
        benchmark(verify_current_token)

        # Verify functionality works (separate from benchmark)
        test_token = get_current_totp_token(secret)
        assert verify_totp_token(secret, test_token) is True  # Correct order: secret, token


# ====================================================================================
# Database Benchmarks
# ====================================================================================


class TestDatabaseBenchmarks:
    """Benchmark database operations."""

    @pytest.fixture
    def db_manager(self):
        """Create temporary database manager."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "benchmark.db")
            config = DatabaseConfig(db_path=db_path)
            manager = DatabaseManager(config=config)
            manager.initialize()
            yield manager

    def test_command_logging(self, benchmark, db_manager):
        """Benchmark command logging."""
        record = CommandRecord(
            equipment_id="scope-001",
            equipment_type="oscilloscope",
            command="*IDN?",
            response="RIGOL TECHNOLOGIES",
            execution_time_ms=42.5
        )

        result = benchmark(db_manager.log_command, record)
        assert result > 0

    def test_command_history_query(self, benchmark, db_manager):
        """Benchmark command history retrieval."""
        # Pre-populate with data
        for i in range(100):
            record = CommandRecord(
                equipment_id=f"device-{i % 10}",
                equipment_type="oscilloscope",
                command="*IDN?",
                response=f"Device {i}",
                execution_time_ms=float(i)
            )
            db_manager.log_command(record)

        result = benchmark(
            db_manager.get_command_history,
            equipment_id="device-0",
            limit=10
        )
        assert result.total_count > 0


# ====================================================================================
# Backup Benchmarks
# ====================================================================================


class TestBackupBenchmarks:
    """Benchmark backup operations."""

    @pytest.fixture
    def backup_manager(self):
        """Create temporary backup manager."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create dummy data to backup
            config_dir = Path(temp_dir) / "config"
            config_dir.mkdir()
            (config_dir / "settings.json").write_text('{"test": true}')
            (config_dir / "profiles.json").write_text('{"profiles": []}')

            config = BackupConfig(backup_dir=temp_dir)
            yield BackupManager(config)

    @pytest.mark.asyncio
    async def test_backup_creation_no_compression(self, benchmark, backup_manager):
        """Benchmark backup creation without compression."""
        request = BackupRequest(
            backup_type=BackupType.CONFIG,
            compression=CompressionType.NONE,
            description="Benchmark test",
            verify_after_backup=False
        )

        result = await benchmark.pedantic(
            backup_manager.create_backup,
            args=(request,),
            iterations=5,
            rounds=3
        )
        assert result is not None

    def test_backup_listing(self, benchmark, backup_manager):
        """Benchmark backup listing."""
        result = benchmark(backup_manager.list_backups)
        assert isinstance(result, list)


# ====================================================================================
# Model Validation Benchmarks
# ====================================================================================


class TestModelBenchmarks:
    """Benchmark Pydantic model validation."""

    def test_command_record_creation(self, benchmark):
        """Benchmark CommandRecord model validation."""
        result = benchmark(
            CommandRecord,
            equipment_id="scope-001",
            equipment_type="oscilloscope",
            command="*IDN?",
            response="RIGOL",
            execution_time_ms=45.2
        )
        assert result is not None

    def test_backup_request_creation(self, benchmark):
        """Benchmark BackupRequest model validation."""
        result = benchmark(
            BackupRequest,
            backup_type=BackupType.CONFIG,
            compression=CompressionType.GZIP,
            description="Test backup"
        )
        assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "--benchmark-only", "-v"])
