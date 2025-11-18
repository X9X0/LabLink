"""
Comprehensive tests for the firmware update manager.

Tests cover:
- FirmwareManager initialization
- Firmware package upload with different checksum methods
- Package retrieval and listing
- Package deletion
- Compatibility checking
- Version comparison
- Firmware file verification
- Update workflow (start, progress, history)
- Statistics tracking
"""

import pytest
import tempfile
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock

from server.firmware.manager import FirmwareManager
from shared.models.firmware import (
    FirmwareVerificationMethod,
    FirmwareUpdateStatus,
    FirmwareUpdateRequest,
)


class TestFirmwareManagerInit:
    """Test FirmwareManager initialization."""

    def test_manager_initialization(self):
        """Test manager initializes correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            assert manager.storage_dir == Path(tmpdir)
            assert manager.storage_dir.exists()
            assert isinstance(manager.packages, dict)
            assert isinstance(manager.update_history, dict)
            assert isinstance(manager.active_updates, dict)
            assert len(manager.packages) == 0

    def test_manager_creates_storage_directory(self):
        """Test manager creates storage directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "firmware" / "packages"
            manager = FirmwareManager(storage_dir=str(storage_path))

            assert storage_path.exists()


class TestFirmwareUpload:
    """Test firmware package upload."""

    @pytest.mark.asyncio
    async def test_upload_firmware_basic(self):
        """Test basic firmware upload."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            firmware_data = b"FIRMWARE_DATA_MOCK_V1.0"

            package = await manager.upload_firmware(
                file_data=firmware_data,
                equipment_type="oscilloscope",
                manufacturer="Rigol",
                model="DS1054Z",
                version="1.0.0"
            )

            assert package.manufacturer == "Rigol"
            assert package.model == "DS1054Z"
            assert package.version == "1.0.0"
            assert package.file_size == len(firmware_data)
            assert package.id in manager.packages
            # File should be saved
            assert Path(package.file_path).exists()

    @pytest.mark.asyncio
    async def test_upload_firmware_sha256(self):
        """Test firmware upload with SHA256 checksum."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            firmware_data = b"TEST_FIRMWARE"

            package = await manager.upload_firmware(
                file_data=firmware_data,
                equipment_type="power_supply",
                manufacturer="Keysight",
                model="E36312A",
                version="2.1.0",
                checksum_method=FirmwareVerificationMethod.SHA256
            )

            assert package.checksum_method == FirmwareVerificationMethod.SHA256
            assert len(package.checksum) == 64  # SHA256 produces 64 hex chars

    @pytest.mark.asyncio
    async def test_upload_firmware_sha512(self):
        """Test firmware upload with SHA512 checksum."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            firmware_data = b"TEST_FIRMWARE"

            package = await manager.upload_firmware(
                file_data=firmware_data,
                equipment_type="oscilloscope",
                manufacturer="Rigol",
                model="DS1054Z",
                version="1.0.0",
                checksum_method=FirmwareVerificationMethod.SHA512
            )

            assert package.checksum_method == FirmwareVerificationMethod.SHA512
            assert len(package.checksum) == 128  # SHA512 produces 128 hex chars

    @pytest.mark.asyncio
    async def test_upload_firmware_md5(self):
        """Test firmware upload with MD5 checksum."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            firmware_data = b"TEST_FIRMWARE"

            package = await manager.upload_firmware(
                file_data=firmware_data,
                equipment_type="oscilloscope",
                manufacturer="Rigol",
                model="DS1054Z",
                version="1.0.0",
                checksum_method=FirmwareVerificationMethod.MD5
            )

            assert package.checksum_method == FirmwareVerificationMethod.MD5
            assert len(package.checksum) == 32  # MD5 produces 32 hex chars

    @pytest.mark.asyncio
    async def test_upload_firmware_crc32(self):
        """Test firmware upload with CRC32 checksum."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            firmware_data = b"TEST_FIRMWARE"

            package = await manager.upload_firmware(
                file_data=firmware_data,
                equipment_type="oscilloscope",
                manufacturer="Rigol",
                model="DS1054Z",
                version="1.0.0",
                checksum_method=FirmwareVerificationMethod.CRC32
            )

            assert package.checksum_method == FirmwareVerificationMethod.CRC32
            assert package.checksum.startswith("0x")  # CRC32 is hex format

    @pytest.mark.asyncio
    async def test_upload_firmware_with_metadata(self):
        """Test firmware upload with complete metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            firmware_data = b"COMPLETE_FIRMWARE_PACKAGE"

            package = await manager.upload_firmware(
                file_data=firmware_data,
                equipment_type="electronic_load",
                manufacturer="BK Precision",
                model="8500",
                version="3.2.1",
                release_notes="Bug fixes and performance improvements",
                critical=True,
                compatible_models=["8500", "8502", "8510"],
                min_version="3.0.0",
                max_version="3.9.9",
                uploaded_by="admin@lab.com"
            )

            assert package.release_notes == "Bug fixes and performance improvements"
            assert package.critical is True
            assert len(package.compatible_models) == 3
            assert "8500" in package.compatible_models
            assert package.min_current_version == "3.0.0"
            assert package.max_current_version == "3.9.9"
            assert package.uploaded_by == "admin@lab.com"

    @pytest.mark.asyncio
    async def test_upload_multiple_firmware_packages(self):
        """Test uploading multiple firmware packages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            # Upload 3 different packages
            for i in range(3):
                await manager.upload_firmware(
                    file_data=f"FIRMWARE_V{i}".encode(),
                    equipment_type="oscilloscope",
                    manufacturer="Rigol",
                    model="DS1054Z",
                    version=f"1.{i}.0"
                )

            assert len(manager.packages) == 3


class TestPackageRetrieval:
    """Test firmware package retrieval."""

    @pytest.mark.asyncio
    async def test_get_package(self):
        """Test retrieving a firmware package by ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            package = await manager.upload_firmware(
                file_data=b"TEST",
                equipment_type="oscilloscope",
                manufacturer="Rigol",
                model="DS1054Z",
                version="1.0.0"
            )

            retrieved = await manager.get_package(package.id)

            assert retrieved is not None
            assert retrieved.id == package.id
            assert retrieved.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_get_nonexistent_package(self):
        """Test retrieving nonexistent package returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            retrieved = await manager.get_package("nonexistent-id")

            assert retrieved is None

    @pytest.mark.asyncio
    async def test_list_packages_all(self):
        """Test listing all packages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            # Upload 3 packages
            for i in range(3):
                await manager.upload_firmware(
                    file_data=f"FW{i}".encode(),
                    equipment_type="oscilloscope",
                    manufacturer="Rigol",
                    model="DS1054Z",
                    version=f"1.{i}.0"
                )

            packages = await manager.list_packages()

            assert len(packages) == 3

    @pytest.mark.asyncio
    async def test_list_packages_by_model(self):
        """Test listing packages filtered by model."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            # Upload packages for different models
            await manager.upload_firmware(
                file_data=b"FW1",
                equipment_type="oscilloscope",
                manufacturer="Rigol",
                model="DS1054Z",
                version="1.0.0"
            )
            await manager.upload_firmware(
                file_data=b"FW2",
                equipment_type="oscilloscope",
                manufacturer="Rigol",
                model="DS1104Z",
                version="2.0.0"
            )

            packages = await manager.list_packages(model="DS1054Z")

            assert len(packages) == 1
            assert packages[0].model == "DS1054Z"

    @pytest.mark.asyncio
    async def test_list_packages_by_manufacturer(self):
        """Test listing packages filtered by manufacturer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            # Upload packages from different manufacturers
            await manager.upload_firmware(
                file_data=b"FW1",
                equipment_type="oscilloscope",
                manufacturer="Rigol",
                model="DS1054Z",
                version="1.0.0"
            )
            await manager.upload_firmware(
                file_data=b"FW2",
                equipment_type="oscilloscope",
                manufacturer="Keysight",
                model="DSOX1204G",
                version="1.0.0"
            )

            packages = await manager.list_packages(manufacturer="Keysight")

            assert len(packages) == 1
            assert packages[0].manufacturer == "Keysight"


class TestPackageDeletion:
    """Test firmware package deletion."""

    @pytest.mark.asyncio
    async def test_delete_package(self):
        """Test deleting a firmware package."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            package = await manager.upload_firmware(
                file_data=b"TEST",
                equipment_type="oscilloscope",
                manufacturer="Rigol",
                model="DS1054Z",
                version="1.0.0"
            )

            file_path = Path(package.file_path)
            assert file_path.exists()

            # Delete package
            deleted = await manager.delete_package(package.id)

            assert deleted is True
            assert package.id not in manager.packages
            assert not file_path.exists()  # File should be deleted

    @pytest.mark.asyncio
    async def test_delete_nonexistent_package(self):
        """Test deleting nonexistent package returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            deleted = await manager.delete_package("nonexistent-id")

            assert deleted is False


class TestCompatibilityChecking:
    """Test firmware compatibility checking."""

    @pytest.mark.asyncio
    async def test_check_compatibility_compatible(self):
        """Test compatibility check passes for compatible version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            package = await manager.upload_firmware(
                file_data=b"FW",
                equipment_type="oscilloscope",
                manufacturer="Rigol",
                model="DS1054Z",
                version="2.0.0",
                min_version="1.0.0",
                max_version="1.9.9"
            )

            result = await manager.check_compatibility(
                equipment_id="TEST_SCOPE_001",
                firmware_id=package.id,
                equipment_model="DS1054Z",
                current_version="1.5.0"
            )

            assert result.compatible is True
            assert len(result.reasons) >= 0  # May have informational messages

    @pytest.mark.asyncio
    async def test_check_compatibility_version_too_low(self):
        """Test compatibility check fails when current version too low."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            package = await manager.upload_firmware(
                file_data=b"FW",
                equipment_type="oscilloscope",
                manufacturer="Rigol",
                model="DS1054Z",
                version="2.0.0",
                min_version="1.5.0"
            )

            result = await manager.check_compatibility(
                equipment_id="TEST_SCOPE_001",
                firmware_id=package.id,
                equipment_model="DS1054Z",
                current_version="1.0.0"  # Too low
            )

            assert result.compatible is False
            assert len(result.reasons) > 0

    @pytest.mark.asyncio
    async def test_check_compatibility_version_too_high(self):
        """Test compatibility check fails when current version too high."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            package = await manager.upload_firmware(
                file_data=b"FW",
                equipment_type="oscilloscope",
                manufacturer="Rigol",
                model="DS1054Z",
                version="2.0.0",
                max_version="1.9.9"
            )

            result = await manager.check_compatibility(
                equipment_id="TEST_SCOPE_001",
                firmware_id=package.id,
                equipment_model="DS1054Z",
                current_version="2.5.0"  # Too high
            )

            assert result.compatible is False

    @pytest.mark.asyncio
    async def test_check_compatibility_model_mismatch(self):
        """Test compatibility check fails for incompatible model."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            package = await manager.upload_firmware(
                file_data=b"FW",
                equipment_type="oscilloscope",
                manufacturer="Rigol",
                model="DS1054Z",
                version="2.0.0",
                compatible_models=["DS1054Z"]
            )

            result = await manager.check_compatibility(
                equipment_id="TEST_SCOPE_001",
                firmware_id=package.id,
                equipment_model="DS1104Z",  # Different model
                current_version="1.0.0"
            )

            assert result.compatible is False


class TestVersionComparison:
    """Test version comparison logic."""

    def test_compare_versions_equal(self):
        """Test comparing equal versions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            result = manager._compare_versions("1.2.3", "1.2.3")
            assert result == 0

    def test_compare_versions_less_than(self):
        """Test version1 < version2."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            assert manager._compare_versions("1.0.0", "2.0.0") < 0
            assert manager._compare_versions("1.2.0", "1.3.0") < 0
            assert manager._compare_versions("1.2.3", "1.2.4") < 0

    def test_compare_versions_greater_than(self):
        """Test version1 > version2."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            assert manager._compare_versions("2.0.0", "1.0.0") > 0
            assert manager._compare_versions("1.3.0", "1.2.0") > 0
            assert manager._compare_versions("1.2.4", "1.2.3") > 0

    def test_compare_versions_different_lengths(self):
        """Test comparing versions with different number of components."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            # "1.0" should be treated as "1.0.0"
            assert manager._compare_versions("1.0", "1.0.0") == 0
            assert manager._compare_versions("1.0", "1.0.1") < 0


class TestFirmwareVerification:
    """Test firmware file verification."""

    @pytest.mark.asyncio
    async def test_verify_firmware_file_valid(self):
        """Test verifying a valid firmware file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            firmware_data = b"VALID_FIRMWARE_DATA"

            package = await manager.upload_firmware(
                file_data=firmware_data,
                equipment_type="oscilloscope",
                manufacturer="Rigol",
                model="DS1054Z",
                version="1.0.0",
                checksum_method=FirmwareVerificationMethod.SHA256
            )

            # Verify the file
            is_valid = await manager.verify_firmware_file(package.id)

            assert is_valid is True

    @pytest.mark.asyncio
    async def test_verify_firmware_file_corrupted(self):
        """Test verifying a corrupted firmware file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            package = await manager.upload_firmware(
                file_data=b"ORIGINAL_DATA",
                equipment_type="oscilloscope",
                manufacturer="Rigol",
                model="DS1054Z",
                version="1.0.0"
            )

            # Corrupt the file
            with open(package.file_path, "wb") as f:
                f.write(b"CORRUPTED_DATA")

            # Verification should fail
            is_valid = await manager.verify_firmware_file(package.id)

            assert is_valid is False

    @pytest.mark.asyncio
    async def test_verify_nonexistent_firmware(self):
        """Test verifying nonexistent firmware file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            is_valid = await manager.verify_firmware_file("nonexistent-id")

            assert is_valid is False


class TestFirmwareUpdate:
    """Test firmware update workflow."""

    @pytest.mark.asyncio
    async def test_start_update(self):
        """Test starting a firmware update."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            package = await manager.upload_firmware(
                file_data=b"NEW_FIRMWARE",
                equipment_type="oscilloscope",
                manufacturer="Rigol",
                model="DS1054Z",
                version="2.0.0"
            )

            request = FirmwareUpdateRequest(
                firmware_id=package.id,
                equipment_id="SCOPE_001"
            )

            # Mock the equipment manager
            mock_equipment = Mock()
            mock_equipment.get_status = AsyncMock(return_value={"connected": True})
            mock_equipment.update_firmware = AsyncMock(return_value=True)

            with patch.object(manager, '_perform_update', new=AsyncMock(return_value=None)):
                update_id = await manager.start_update(request, mock_equipment)

                assert update_id is not None
                assert update_id in manager.active_updates

    @pytest.mark.asyncio
    async def test_get_update_progress(self):
        """Test getting update progress."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            package = await manager.upload_firmware(
                file_data=b"FW",
                equipment_type="oscilloscope",
                manufacturer="Rigol",
                model="DS1054Z",
                version="2.0.0"
            )

            request = FirmwareUpdateRequest(
                firmware_id=package.id,
                equipment_id="SCOPE_001"
            )

            mock_equipment = Mock()
            mock_equipment.get_status = AsyncMock(return_value={"connected": True})

            with patch.object(manager, '_perform_update', new=AsyncMock()):
                update_id = await manager.start_update(request, mock_equipment)

                # Get progress
                progress = await manager.get_update_progress(update_id)

                assert progress is not None
                assert progress.update_id == update_id
                assert progress.equipment_id == "SCOPE_001"

    @pytest.mark.asyncio
    async def test_get_update_progress_nonexistent(self):
        """Test getting progress for nonexistent update."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            progress = await manager.get_update_progress("nonexistent-id")

            assert progress is None


class TestUpdateHistory:
    """Test firmware update history."""

    @pytest.mark.asyncio
    async def test_get_update_history_empty(self):
        """Test getting history when no updates performed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            history = await manager.get_update_history(equipment_id="SCOPE_001")

            assert len(history) == 0

    @pytest.mark.asyncio
    async def test_get_update_history_all(self):
        """Test getting all update history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            # Manually add some history entries for testing
            from shared.models.firmware import FirmwareUpdateHistory

            for i in range(3):
                history_entry = FirmwareUpdateHistory(
                    id=f"update_{i}",
                    equipment_id=f"SCOPE_{i:03d}",
                    equipment_model="DS1054Z",
                    firmware_id=f"fw_{i}",
                    status=FirmwareUpdateStatus.COMPLETED,
                    started_at=datetime.now(),
                    completed_at=datetime.now(),
                    old_version=f"{i}.0.0",
                    new_version=f"{i+1}.0.0"
                )
                manager.update_history[f"update_{i}"] = history_entry

            history = await manager.get_update_history()

            assert len(history) == 3


class TestStatistics:
    """Test firmware statistics."""

    @pytest.mark.asyncio
    async def test_get_statistics(self):
        """Test getting firmware statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FirmwareManager(storage_dir=tmpdir)

            # Upload some packages
            for i in range(3):
                await manager.upload_firmware(
                    file_data=f"FW{i}".encode(),
                    equipment_type="oscilloscope",
                    manufacturer="Rigol",
                    model="DS1054Z",
                    version=f"1.{i}.0",
                    critical=(i == 0)  # Make first one critical
                )

            stats = await manager.get_statistics()

            assert stats.total_packages == 3
            assert stats.total_updates == 0  # No updates performed yet


# Mark all tests as unit tests
pytestmark = pytest.mark.unit
