"""Firmware update manager."""

import asyncio
import hashlib
import logging
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from shared.models.firmware import (
    FirmwareCompatibilityCheck,
    FirmwareInfo,
    FirmwarePackage,
    FirmwareStatistics,
    FirmwareUpdateHistory,
    FirmwareUpdateProgress,
    FirmwareUpdateRequest,
    FirmwareUpdateStatus,
    FirmwareVerificationMethod,
)

logger = logging.getLogger(__name__)


class FirmwareManager:
    """Manages firmware packages and updates."""

    def __init__(self, storage_dir: str = "./data/firmware"):
        """Initialize firmware manager.

        Args:
            storage_dir: Directory for storing firmware packages
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # In-memory storage (will be replaced with database)
        self.packages: Dict[str, FirmwarePackage] = {}
        self.update_history: Dict[str, FirmwareUpdateHistory] = {}
        self.active_updates: Dict[str, FirmwareUpdateProgress] = {}

        # Lock for thread safety
        self._lock = asyncio.Lock()

        logger.info(f"Firmware manager initialized with storage: {self.storage_dir}")

    async def upload_firmware(
        self,
        file_data: bytes,
        equipment_type: str,
        manufacturer: str,
        model: str,
        version: str,
        release_notes: Optional[str] = None,
        critical: bool = False,
        compatible_models: Optional[List[str]] = None,
        min_version: Optional[str] = None,
        max_version: Optional[str] = None,
        checksum_method: FirmwareVerificationMethod = FirmwareVerificationMethod.SHA256,
        uploaded_by: Optional[str] = None,
    ) -> FirmwarePackage:
        """Upload a new firmware package.

        Args:
            file_data: Firmware file binary data
            equipment_type: Type of equipment
            manufacturer: Equipment manufacturer
            model: Equipment model
            version: Firmware version
            release_notes: Release notes
            critical: Whether this is a critical update
            compatible_models: List of compatible models
            min_version: Minimum current version for update
            max_version: Maximum current version for update
            checksum_method: Checksum algorithm to use
            uploaded_by: User who uploaded the firmware

        Returns:
            FirmwarePackage object
        """
        async with self._lock:
            # Generate unique ID
            firmware_id = str(uuid.uuid4())

            # Calculate checksum
            if checksum_method == FirmwareVerificationMethod.SHA256:
                checksum = hashlib.sha256(file_data).hexdigest()
            elif checksum_method == FirmwareVerificationMethod.SHA512:
                checksum = hashlib.sha512(file_data).hexdigest()
            elif checksum_method == FirmwareVerificationMethod.MD5:
                checksum = hashlib.md5(file_data).hexdigest()
            else:  # CRC32
                import zlib
                checksum = hex(zlib.crc32(file_data) & 0xFFFFFFFF)

            # Save file to storage
            filename = f"{manufacturer}_{model}_{version}_{firmware_id}.bin"
            file_path = self.storage_dir / filename

            with open(file_path, "wb") as f:
                f.write(file_data)

            logger.info(
                f"Saved firmware package: {filename} ({len(file_data)} bytes, "
                f"{checksum_method.value}: {checksum})"
            )

            # Create package object
            package = FirmwarePackage(
                id=firmware_id,
                equipment_type=equipment_type,
                manufacturer=manufacturer,
                model=model,
                version=version,
                release_date=datetime.now(),
                file_path=str(file_path),
                file_size=len(file_data),
                checksum=checksum,
                checksum_method=checksum_method,
                min_current_version=min_version,
                max_current_version=max_version,
                release_notes=release_notes,
                critical=critical,
                compatible_models=compatible_models or [model],
                uploaded_at=datetime.now(),
                uploaded_by=uploaded_by,
            )

            # Store in memory
            self.packages[firmware_id] = package

            logger.info(f"Firmware package registered: {firmware_id} (v{version})")
            return package

    async def get_package(self, firmware_id: str) -> Optional[FirmwarePackage]:
        """Get firmware package by ID.

        Args:
            firmware_id: Firmware package ID

        Returns:
            FirmwarePackage or None
        """
        return self.packages.get(firmware_id)

    async def list_packages(
        self,
        equipment_type: Optional[str] = None,
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
    ) -> List[FirmwarePackage]:
        """List firmware packages with optional filters.

        Args:
            equipment_type: Filter by equipment type
            manufacturer: Filter by manufacturer
            model: Filter by model

        Returns:
            List of FirmwarePackage objects
        """
        packages = list(self.packages.values())

        if equipment_type:
            packages = [p for p in packages if p.equipment_type == equipment_type]
        if manufacturer:
            packages = [p for p in packages if p.manufacturer == manufacturer]
        if model:
            packages = [p for p in packages if model in p.compatible_models]

        # Sort by release date (newest first)
        packages.sort(key=lambda p: p.release_date, reverse=True)

        return packages

    async def delete_package(self, firmware_id: str) -> bool:
        """Delete a firmware package.

        Args:
            firmware_id: Firmware package ID

        Returns:
            True if deleted, False if not found
        """
        async with self._lock:
            package = self.packages.get(firmware_id)
            if not package:
                return False

            # Delete file
            try:
                if os.path.exists(package.file_path):
                    os.remove(package.file_path)
                    logger.info(f"Deleted firmware file: {package.file_path}")
            except Exception as e:
                logger.error(f"Error deleting firmware file: {e}")

            # Remove from memory
            del self.packages[firmware_id]
            logger.info(f"Firmware package deleted: {firmware_id}")

            return True

    async def check_compatibility(
        self,
        equipment_id: str,
        firmware_id: str,
        current_version: str,
        equipment_model: str,
    ) -> FirmwareCompatibilityCheck:
        """Check if firmware is compatible with equipment.

        Args:
            equipment_id: Equipment ID
            firmware_id: Firmware package ID
            current_version: Current firmware version
            equipment_model: Equipment model

        Returns:
            FirmwareCompatibilityCheck object
        """
        package = await self.get_package(firmware_id)
        if not package:
            return FirmwareCompatibilityCheck(
                compatible=False,
                equipment_id=equipment_id,
                equipment_model=equipment_model,
                current_version=current_version,
                firmware_id=firmware_id,
                firmware_version="unknown",
                reasons=["Firmware package not found"],
            )

        reasons = []
        warnings = []
        compatible = True

        # Check model compatibility
        if equipment_model not in package.compatible_models:
            compatible = False
            reasons.append(
                f"Model {equipment_model} not in compatible models: "
                f"{', '.join(package.compatible_models)}"
            )

        # Check version constraints
        if package.min_current_version:
            if self._compare_versions(current_version, package.min_current_version) < 0:
                compatible = False
                reasons.append(
                    f"Current version {current_version} is below minimum "
                    f"required version {package.min_current_version}"
                )

        if package.max_current_version:
            if self._compare_versions(current_version, package.max_current_version) > 0:
                compatible = False
                reasons.append(
                    f"Current version {current_version} is above maximum "
                    f"supported version {package.max_current_version}"
                )

        # Check if already on this version
        if current_version == package.version:
            warnings.append("Equipment is already running this firmware version")

        # Add critical update warning
        if package.critical:
            warnings.append("This is a CRITICAL security/stability update")

        if compatible and not reasons:
            reasons.append("Firmware is compatible with this equipment")

        return FirmwareCompatibilityCheck(
            compatible=compatible,
            equipment_id=equipment_id,
            equipment_model=equipment_model,
            current_version=current_version,
            firmware_id=firmware_id,
            firmware_version=package.version,
            reasons=reasons,
            warnings=warnings,
        )

    def _compare_versions(self, version1: str, version2: str) -> int:
        """Compare two version strings.

        Args:
            version1: First version string
            version2: Second version string

        Returns:
            -1 if version1 < version2, 0 if equal, 1 if version1 > version2
        """
        # Simple version comparison (can be enhanced for semantic versioning)
        v1_parts = [int(p) if p.isdigit() else 0 for p in version1.split(".")]
        v2_parts = [int(p) if p.isdigit() else 0 for p in version2.split(".")]

        # Pad to same length
        max_len = max(len(v1_parts), len(v2_parts))
        v1_parts += [0] * (max_len - len(v1_parts))
        v2_parts += [0] * (max_len - len(v2_parts))

        for v1, v2 in zip(v1_parts, v2_parts):
            if v1 < v2:
                return -1
            elif v1 > v2:
                return 1

        return 0

    async def verify_firmware_file(self, firmware_id: str) -> bool:
        """Verify integrity of firmware file.

        Args:
            firmware_id: Firmware package ID

        Returns:
            True if file is valid, False otherwise
        """
        package = await self.get_package(firmware_id)
        if not package:
            logger.error(f"Firmware package not found: {firmware_id}")
            return False

        if not os.path.exists(package.file_path):
            logger.error(f"Firmware file not found: {package.file_path}")
            return False

        # Read file and calculate checksum
        try:
            with open(package.file_path, "rb") as f:
                file_data = f.read()

            if package.checksum_method == FirmwareVerificationMethod.SHA256:
                calculated_checksum = hashlib.sha256(file_data).hexdigest()
            elif package.checksum_method == FirmwareVerificationMethod.SHA512:
                calculated_checksum = hashlib.sha512(file_data).hexdigest()
            elif package.checksum_method == FirmwareVerificationMethod.MD5:
                calculated_checksum = hashlib.md5(file_data).hexdigest()
            else:  # CRC32
                import zlib
                calculated_checksum = hex(zlib.crc32(file_data) & 0xFFFFFFFF)

            if calculated_checksum != package.checksum:
                logger.error(
                    f"Checksum mismatch for {firmware_id}: "
                    f"expected {package.checksum}, got {calculated_checksum}"
                )
                return False

            logger.info(f"Firmware file verified: {firmware_id}")
            return True

        except Exception as e:
            logger.error(f"Error verifying firmware file: {e}")
            return False

    async def start_update(
        self,
        request: FirmwareUpdateRequest,
        equipment,
    ) -> FirmwareUpdateProgress:
        """Start a firmware update.

        Args:
            request: Firmware update request
            equipment: Equipment instance to update

        Returns:
            FirmwareUpdateProgress object
        """
        update_id = str(uuid.uuid4())

        # Get current version
        status = await equipment.get_status()
        old_version = status.firmware_version or "unknown"

        # Create progress tracker
        progress = FirmwareUpdateProgress(
            update_id=update_id,
            equipment_id=request.equipment_id,
            firmware_id=request.firmware_id,
            status=FirmwareUpdateStatus.PENDING,
            progress_percent=0.0,
            current_step="Initializing update",
            old_version=old_version,
        )

        async with self._lock:
            self.active_updates[update_id] = progress

        logger.info(
            f"Started firmware update {update_id} for equipment {request.equipment_id}"
        )

        # Start update task in background
        asyncio.create_task(
            self._perform_update(update_id, request, equipment)
        )

        return progress

    async def _perform_update(
        self,
        update_id: str,
        request: FirmwareUpdateRequest,
        equipment,
    ):
        """Perform the actual firmware update.

        Args:
            update_id: Update operation ID
            request: Firmware update request
            equipment: Equipment instance
        """
        progress = self.active_updates.get(update_id)
        if not progress:
            logger.error(f"Progress tracker not found for update {update_id}")
            return

        try:
            # Step 1: Verify firmware file
            if request.verify_before_update:
                progress.status = FirmwareUpdateStatus.VALIDATING
                progress.progress_percent = 10.0
                progress.current_step = "Verifying firmware integrity"

                if not await self.verify_firmware_file(request.firmware_id):
                    raise Exception("Firmware file verification failed")

            # Step 2: Check compatibility
            progress.progress_percent = 20.0
            progress.current_step = "Checking compatibility"

            status = await equipment.get_status()
            info = await equipment.get_info()

            compat = await self.check_compatibility(
                request.equipment_id,
                request.firmware_id,
                status.firmware_version or "unknown",
                info.model,
            )

            if not compat.compatible:
                raise Exception(f"Firmware not compatible: {', '.join(compat.reasons)}")

            # Step 3: Create backup (if supported and requested)
            if request.create_backup:
                progress.progress_percent = 30.0
                progress.current_step = "Creating firmware backup"
                # TODO: Implement backup logic if equipment supports it
                logger.info("Firmware backup created (placeholder)")

            # Step 4: Upload firmware to equipment
            progress.status = FirmwareUpdateStatus.UPLOADING
            progress.progress_percent = 40.0
            progress.current_step = "Uploading firmware to equipment"

            package = await self.get_package(request.firmware_id)
            if not package:
                raise Exception("Firmware package not found")

            # Read firmware file
            with open(package.file_path, "rb") as f:
                firmware_data = f.read()

            # Step 5: Send update command to equipment
            progress.status = FirmwareUpdateStatus.UPDATING
            progress.progress_percent = 60.0
            progress.current_step = "Installing firmware update"

            # Call equipment-specific update method
            await equipment.update_firmware(firmware_data)

            # Step 6: Verify update
            progress.status = FirmwareUpdateStatus.VERIFYING
            progress.progress_percent = 80.0
            progress.current_step = "Verifying firmware installation"

            # Wait for equipment to reboot if needed
            if request.reboot_after_update:
                await asyncio.sleep(5)  # Give equipment time to reboot

            # Check new version
            new_status = await equipment.get_status()
            new_version = new_status.firmware_version or "unknown"
            progress.new_version = new_version

            # Step 7: Complete
            progress.status = FirmwareUpdateStatus.COMPLETED
            progress.progress_percent = 100.0
            progress.current_step = "Update completed successfully"
            progress.completed_at = datetime.now()

            logger.info(
                f"Firmware update {update_id} completed: {progress.old_version} -> {new_version}"
            )

            # Record in history
            await self._record_history(update_id, request, progress, success=True)

        except Exception as e:
            logger.error(f"Firmware update {update_id} failed: {e}")

            progress.status = FirmwareUpdateStatus.FAILED
            progress.error_message = str(e)
            progress.completed_at = datetime.now()

            # Auto-rollback if requested
            if request.auto_rollback_on_failure:
                logger.info(f"Attempting auto-rollback for update {update_id}")
                # TODO: Implement rollback logic
                progress.status = FirmwareUpdateStatus.ROLLED_BACK

            # Record in history
            await self._record_history(update_id, request, progress, success=False)

    async def _record_history(
        self,
        update_id: str,
        request: FirmwareUpdateRequest,
        progress: FirmwareUpdateProgress,
        success: bool,
    ):
        """Record update in history.

        Args:
            update_id: Update operation ID
            request: Firmware update request
            progress: Update progress
            success: Whether update was successful
        """
        duration = None
        if progress.completed_at:
            duration = (progress.completed_at - progress.started_at).total_seconds()

        # Get equipment info
        package = await self.get_package(request.firmware_id)

        history = FirmwareUpdateHistory(
            id=update_id,
            equipment_id=request.equipment_id,
            equipment_model=package.model if package else "unknown",
            firmware_id=request.firmware_id,
            old_version=progress.old_version or "unknown",
            new_version=progress.new_version or "unknown",
            status=progress.status,
            started_at=progress.started_at,
            completed_at=progress.completed_at,
            duration_seconds=duration,
            notes=request.notes,
            error_message=progress.error_message,
            rolled_back=progress.status == FirmwareUpdateStatus.ROLLED_BACK,
        )

        async with self._lock:
            self.update_history[update_id] = history

        logger.info(f"Recorded firmware update history: {update_id}")

    async def get_update_progress(self, update_id: str) -> Optional[FirmwareUpdateProgress]:
        """Get progress of an active update.

        Args:
            update_id: Update operation ID

        Returns:
            FirmwareUpdateProgress or None
        """
        return self.active_updates.get(update_id)

    async def get_update_history(
        self,
        equipment_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[FirmwareUpdateHistory]:
        """Get firmware update history.

        Args:
            equipment_id: Filter by equipment ID
            limit: Maximum number of records to return

        Returns:
            List of FirmwareUpdateHistory objects
        """
        history = list(self.update_history.values())

        if equipment_id:
            history = [h for h in history if h.equipment_id == equipment_id]

        # Sort by start time (newest first)
        history.sort(key=lambda h: h.started_at, reverse=True)

        return history[:limit]

    async def get_statistics(self) -> FirmwareStatistics:
        """Get firmware update statistics.

        Returns:
            FirmwareStatistics object
        """
        history = list(self.update_history.values())

        total_updates = len(history)
        successful = sum(1 for h in history if h.status == FirmwareUpdateStatus.COMPLETED)
        failed = sum(1 for h in history if h.status == FirmwareUpdateStatus.FAILED)
        rolled_back = sum(1 for h in history if h.rolled_back)

        # Calculate average duration
        durations = [h.duration_seconds for h in history if h.duration_seconds]
        avg_duration = sum(durations) / len(durations) if durations else None

        # Get last update
        last_update = max([h.started_at for h in history]) if history else None

        # Count by equipment
        updates_by_equipment: Dict[str, int] = {}
        for h in history:
            updates_by_equipment[h.equipment_id] = (
                updates_by_equipment.get(h.equipment_id, 0) + 1
            )

        # Count by status
        updates_by_status: Dict[str, int] = {}
        for h in history:
            status_str = h.status.value
            updates_by_status[status_str] = updates_by_status.get(status_str, 0) + 1

        return FirmwareStatistics(
            total_packages=len(self.packages),
            total_updates=total_updates,
            successful_updates=successful,
            failed_updates=failed,
            rolled_back_updates=rolled_back,
            average_duration_seconds=avg_duration,
            last_update=last_update,
            updates_by_equipment=updates_by_equipment,
            updates_by_status=updates_by_status,
        )


# Global firmware manager instance
firmware_manager = FirmwareManager()
