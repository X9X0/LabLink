"""Tests for firmware update system."""

import hashlib
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from server.firmware.manager import FirmwareManager
from shared.models.firmware import (
    FirmwareUpdateRequest,
    FirmwareUpdateStatus,
    FirmwareVerificationMethod,
)


class MockEquipment:
    """Mock equipment for testing."""

    def __init__(self, model="MockScope-2000", firmware_version="v1.0.0"):
        self.model = model
        self.firmware_version = firmware_version
        self.update_called = False
        self.update_data = None

    async def get_info(self):
        """Get mock equipment info."""
        from shared.models.equipment import (
            ConnectionType,
            EquipmentInfo,
            EquipmentType,
        )

        return EquipmentInfo(
            id="test_equipment",
            type=EquipmentType.OSCILLOSCOPE,
            manufacturer="Mock Instruments",
            model=self.model,
            serial_number="MOCK12345",
            connection_type=ConnectionType.USB,
            resource_string="MOCK::USB::INST",
        )

    async def get_status(self):
        """Get mock equipment status."""
        from shared.models.equipment import EquipmentStatus

        return EquipmentStatus(
            id="test_equipment",
            connected=True,
            firmware_version=self.firmware_version,
        )

    async def supports_firmware_update(self):
        """Check if firmware update is supported."""
        return True

    async def update_firmware(self, firmware_data: bytes) -> bool:
        """Mock firmware update."""
        self.update_called = True
        self.update_data = firmware_data
        # Simulate successful update
        self.firmware_version = "v2.0.0"
        return True


@pytest.fixture
def firmware_manager():
    """Create a firmware manager with temporary storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = FirmwareManager(storage_dir=tmpdir)
        yield manager


@pytest.mark.asyncio
async def test_upload_firmware(firmware_manager):
    """Test uploading a firmware package."""
    firmware_data = b"MOCK_FIRMWARE_DATA_v2.0.0"

    package = await firmware_manager.upload_firmware(
        file_data=firmware_data,
        equipment_type="oscilloscope",
        manufacturer="Mock Instruments",
        model="MockScope-2000",
        version="2.0.0",
        release_notes="Bug fixes and improvements",
        critical=False,
        checksum_method=FirmwareVerificationMethod.SHA256,
    )

    assert package is not None
    assert package.version == "2.0.0"
    assert package.model == "MockScope-2000"
    assert package.file_size == len(firmware_data)
    assert package.checksum == hashlib.sha256(firmware_data).hexdigest()
    assert os.path.exists(package.file_path)


@pytest.mark.asyncio
async def test_list_packages(firmware_manager):
    """Test listing firmware packages."""
    # Upload multiple packages
    for version in ["1.0.0", "2.0.0", "3.0.0"]:
        await firmware_manager.upload_firmware(
            file_data=f"FIRMWARE_{version}".encode(),
            equipment_type="oscilloscope",
            manufacturer="Mock Instruments",
            model="MockScope-2000",
            version=version,
        )

    # List all packages
    packages = await firmware_manager.list_packages()
    assert len(packages) == 3

    # List filtered by model
    packages = await firmware_manager.list_packages(model="MockScope-2000")
    assert len(packages) == 3

    # List filtered by non-existent model
    packages = await firmware_manager.list_packages(model="NonExistent")
    assert len(packages) == 0


@pytest.mark.asyncio
async def test_delete_package(firmware_manager):
    """Test deleting a firmware package."""
    firmware_data = b"MOCK_FIRMWARE_DATA"

    package = await firmware_manager.upload_firmware(
        file_data=firmware_data,
        equipment_type="oscilloscope",
        manufacturer="Mock Instruments",
        model="MockScope-2000",
        version="1.0.0",
    )

    # Verify package exists
    assert await firmware_manager.get_package(package.id) is not None

    # Delete package
    success = await firmware_manager.delete_package(package.id)
    assert success is True

    # Verify package is deleted
    assert await firmware_manager.get_package(package.id) is None


@pytest.mark.asyncio
async def test_verify_firmware_file(firmware_manager):
    """Test firmware file verification."""
    firmware_data = b"MOCK_FIRMWARE_DATA"

    package = await firmware_manager.upload_firmware(
        file_data=firmware_data,
        equipment_type="oscilloscope",
        manufacturer="Mock Instruments",
        model="MockScope-2000",
        version="1.0.0",
        checksum_method=FirmwareVerificationMethod.SHA256,
    )

    # Verify valid firmware
    valid = await firmware_manager.verify_firmware_file(package.id)
    assert valid is True

    # Corrupt the file
    with open(package.file_path, "wb") as f:
        f.write(b"CORRUPTED_DATA")

    # Verify corrupted firmware
    valid = await firmware_manager.verify_firmware_file(package.id)
    assert valid is False


@pytest.mark.asyncio
async def test_check_compatibility(firmware_manager):
    """Test firmware compatibility checking."""
    firmware_data = b"MOCK_FIRMWARE_DATA"

    # Upload firmware for MockScope-2000 v1.0.0+
    package = await firmware_manager.upload_firmware(
        file_data=firmware_data,
        equipment_type="oscilloscope",
        manufacturer="Mock Instruments",
        model="MockScope-2000",
        version="2.0.0",
        compatible_models=["MockScope-2000"],
        min_version="1.0.0",
    )

    # Check compatibility with compatible equipment
    compat = await firmware_manager.check_compatibility(
        equipment_id="test_eq",
        firmware_id=package.id,
        current_version="1.5.0",
        equipment_model="MockScope-2000",
    )
    assert compat.compatible is True

    # Check compatibility with incompatible model
    compat = await firmware_manager.check_compatibility(
        equipment_id="test_eq",
        firmware_id=package.id,
        current_version="1.5.0",
        equipment_model="DifferentModel",
    )
    assert compat.compatible is False
    assert any("not in compatible models" in reason for reason in compat.reasons)

    # Check compatibility with version too old
    compat = await firmware_manager.check_compatibility(
        equipment_id="test_eq",
        firmware_id=package.id,
        current_version="0.5.0",
        equipment_model="MockScope-2000",
    )
    assert compat.compatible is False
    assert any("below minimum" in reason for reason in compat.reasons)


@pytest.mark.asyncio
async def test_version_comparison(firmware_manager):
    """Test version string comparison."""
    assert firmware_manager._compare_versions("1.0.0", "2.0.0") == -1
    assert firmware_manager._compare_versions("2.0.0", "1.0.0") == 1
    assert firmware_manager._compare_versions("1.5.0", "1.5.0") == 0
    assert firmware_manager._compare_versions("1.10.0", "1.9.0") == 1
    assert firmware_manager._compare_versions("2.0", "2.0.0") == 0


@pytest.mark.asyncio
async def test_firmware_update_flow(firmware_manager):
    """Test complete firmware update flow."""
    firmware_data = b"MOCK_FIRMWARE_v2.0.0"

    # Upload firmware
    package = await firmware_manager.upload_firmware(
        file_data=firmware_data,
        equipment_type="oscilloscope",
        manufacturer="Mock Instruments",
        model="MockScope-2000",
        version="2.0.0",
    )

    # Create mock equipment
    equipment = MockEquipment(model="MockScope-2000", firmware_version="1.0.0")

    # Create update request
    request = FirmwareUpdateRequest(
        equipment_id="test_equipment",
        firmware_id=package.id,
        verify_before_update=True,
        create_backup=False,
        auto_rollback_on_failure=True,
    )

    # Start update
    progress = await firmware_manager.start_update(request, equipment)

    assert progress is not None
    assert progress.equipment_id == "test_equipment"
    assert progress.firmware_id == package.id
    assert progress.old_version == "1.0.0"

    # Wait a bit for update to process
    import asyncio

    await asyncio.sleep(1)

    # Check progress
    updated_progress = await firmware_manager.get_update_progress(progress.update_id)
    assert updated_progress is not None


@pytest.mark.asyncio
async def test_statistics(firmware_manager):
    """Test firmware statistics."""
    # Upload some packages
    for i in range(3):
        await firmware_manager.upload_firmware(
            file_data=f"FIRMWARE_{i}".encode(),
            equipment_type="oscilloscope",
            manufacturer="Mock Instruments",
            model="MockScope-2000",
            version=f"{i}.0.0",
        )

    stats = await firmware_manager.get_statistics()

    assert stats.total_packages == 3
    assert stats.total_updates == 0  # No updates performed yet
    assert stats.successful_updates == 0
    assert stats.failed_updates == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
