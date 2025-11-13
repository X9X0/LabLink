"""Backup & Restore system manager."""

import os
import json
import hashlib
import shutil
import tarfile
import zipfile
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import sys
import asyncio

from .models import (
    BackupConfig,
    BackupMetadata,
    BackupRequest,
    RestoreRequest,
    RestoreResult,
    BackupInfo,
    BackupStatistics,
    BackupVerificationResult,
    BackupType,
    BackupStatus,
    CompressionType,
)

logger = logging.getLogger(__name__)


class BackupManager:
    """Manages backup and restore operations."""

    def __init__(self, config: BackupConfig):
        """Initialize backup manager.

        Args:
            config: Backup configuration
        """
        self.config = config
        self.backup_dir = Path(config.backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Metadata storage
        self.metadata_file = self.backup_dir / "backups.json"
        self.metadata: Dict[str, BackupMetadata] = {}
        self._load_metadata()

        # Auto-backup task
        self._auto_backup_task: Optional[asyncio.Task] = None

    def _load_metadata(self):
        """Load backup metadata from disk."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, "r") as f:
                    data = json.load(f)
                    for backup_id, meta_dict in data.items():
                        self.metadata[backup_id] = BackupMetadata(**meta_dict)
                logger.info(f"Loaded metadata for {len(self.metadata)} backups")
            except Exception as e:
                logger.error(f"Failed to load backup metadata: {e}")
        else:
            logger.info("No existing backup metadata found")

    def _save_metadata(self):
        """Save backup metadata to disk."""
        try:
            data = {
                backup_id: meta.model_dump(mode="json")
                for backup_id, meta in self.metadata.items()
            }
            with open(self.metadata_file, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save backup metadata: {e}")

    async def create_backup(
        self, request: BackupRequest, created_by: Optional[str] = None
    ) -> BackupMetadata:
        """Create a new backup.

        Args:
            request: Backup request
            created_by: User creating backup

        Returns:
            Backup metadata

        Raises:
            Exception: If backup creation fails
        """
        # Generate backup ID
        backup_id = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        logger.info(f"Creating backup: {backup_id} ({request.backup_type})")

        # Determine what to include
        includes = self._get_includes(request)

        # Create backup metadata
        metadata = BackupMetadata(
            backup_id=backup_id,
            backup_type=request.backup_type,
            created_at=datetime.now(),
            created_by=created_by,
            file_path="",  # Will be set after creation
            file_size_bytes=0,  # Will be set after creation
            compression=request.compression or self.config.compression,
            status=BackupStatus.IN_PROGRESS,
            **includes,
            server_version=self._get_server_version(),
            python_version=self._get_python_version(),
            description=request.description,
            tags=request.tags,
        )

        try:
            # Create backup file
            backup_file = await self._create_backup_file(
                backup_id, request.backup_type, includes, metadata.compression
            )

            # Update metadata
            metadata.file_path = str(backup_file)
            metadata.file_size_bytes = backup_file.stat().st_size
            metadata.status = BackupStatus.COMPLETED

            # Count files and directories
            file_count, dir_count = self._count_archive_contents(
                backup_file, metadata.compression
            )
            metadata.file_count = file_count
            metadata.directory_count = dir_count

            # Verify if requested
            verify = (
                request.verify_after_backup
                if request.verify_after_backup is not None
                else self.config.verify_after_backup
            )
            if verify:
                verification = await self.verify_backup(backup_id)
                metadata.verified = verification.verified
                metadata.checksum = verification.actual_checksum
                metadata.verification_time = verification.verification_time

            # Save metadata
            self.metadata[backup_id] = metadata
            self._save_metadata()

            logger.info(
                f"Backup created successfully: {backup_id} ({metadata.file_size_bytes / 1024 / 1024:.2f} MB)"
            )

            return metadata

        except Exception as e:
            logger.error(f"Failed to create backup {backup_id}: {e}")
            metadata.status = BackupStatus.FAILED
            metadata.error_message = str(e)
            self.metadata[backup_id] = metadata
            self._save_metadata()
            raise

    def _get_includes(self, request: BackupRequest) -> Dict[str, bool]:
        """Determine what to include in backup based on request and config.

        Args:
            request: Backup request

        Returns:
            Dictionary of include flags
        """
        # Start with config defaults
        includes = {
            "includes_config": self.config.include_config,
            "includes_profiles": self.config.include_profiles,
            "includes_states": self.config.include_states,
            "includes_database": self.config.include_database,
            "includes_acquisitions": self.config.include_acquisitions,
            "includes_logs": self.config.include_logs,
            "includes_calibration": self.config.include_calibration,
        }

        # Override with request-specific settings
        if request.include_config is not None:
            includes["includes_config"] = request.include_config
        if request.include_profiles is not None:
            includes["includes_profiles"] = request.include_profiles
        if request.include_states is not None:
            includes["includes_states"] = request.include_states
        if request.include_database is not None:
            includes["includes_database"] = request.include_database
        if request.include_acquisitions is not None:
            includes["includes_acquisitions"] = request.include_acquisitions
        if request.include_logs is not None:
            includes["includes_logs"] = request.include_logs
        if request.include_calibration is not None:
            includes["includes_calibration"] = request.include_calibration

        # Adjust based on backup type
        if request.backup_type == BackupType.CONFIG:
            includes = {k: False for k in includes}
            includes["includes_config"] = True
        elif request.backup_type == BackupType.PROFILES:
            includes = {k: False for k in includes}
            includes["includes_profiles"] = True
        elif request.backup_type == BackupType.DATA:
            includes["includes_config"] = False
            includes["includes_profiles"] = False
        elif request.backup_type == BackupType.DATABASE:
            includes = {k: False for k in includes}
            includes["includes_database"] = True

        return includes

    async def _create_backup_file(
        self,
        backup_id: str,
        backup_type: BackupType,
        includes: Dict[str, bool],
        compression: CompressionType,
    ) -> Path:
        """Create the backup archive file.

        Args:
            backup_id: Backup identifier
            backup_type: Type of backup
            includes: What to include in backup
            compression: Compression method

        Returns:
            Path to created backup file
        """
        # Determine file extension
        if compression == CompressionType.ZIP:
            ext = ".zip"
        elif compression == CompressionType.TAR_GZ:
            ext = ".tar.gz"
        elif compression == CompressionType.GZIP:
            ext = ".tar.gz"
        else:
            ext = ".tar"

        backup_file = self.backup_dir / f"{backup_id}{ext}"

        # Create archive
        if compression == CompressionType.ZIP:
            await self._create_zip_backup(backup_file, includes)
        else:
            await self._create_tar_backup(backup_file, includes, compression)

        return backup_file

    async def _create_tar_backup(
        self, backup_file: Path, includes: Dict[str, bool], compression: CompressionType
    ):
        """Create tar-based backup.

        Args:
            backup_file: Output file path
            includes: What to include
            compression: Compression method
        """
        mode = "w"
        if compression in (CompressionType.TAR_GZ, CompressionType.GZIP):
            mode = "w:gz"

        with tarfile.open(backup_file, mode) as tar:
            # Add files based on includes
            if includes["includes_config"]:
                self._add_to_tar(tar, "config", ".")
                self._add_to_tar(tar, ".env", ".", optional=True)

            if includes["includes_profiles"]:
                self._add_to_tar(tar, "profiles", ".")

            if includes["includes_states"]:
                self._add_to_tar(tar, "states", ".")

            if includes["includes_database"]:
                self._add_to_tar(tar, "data/lablink.db", ".", optional=True)
                self._add_to_tar(tar, "data/scheduler.db", ".", optional=True)
                self._add_to_tar(tar, "data/performance.db", ".", optional=True)

            if includes["includes_acquisitions"]:
                self._add_to_tar(tar, "data/acquisitions", ".")

            if includes["includes_logs"]:
                self._add_to_tar(tar, "logs", ".")

            if includes["includes_calibration"]:
                self._add_to_tar(tar, "data/calibration", ".")
                self._add_to_tar(tar, "data/calibration_enhanced", ".")

    def _add_to_tar(
        self, tar: tarfile.TarFile, path: str, base: str, optional: bool = False
    ):
        """Add file or directory to tar archive.

        Args:
            tar: Tar file object
            path: Path to add (relative to base)
            base: Base directory
            optional: Don't fail if path doesn't exist
        """
        full_path = Path(base) / path
        if full_path.exists():
            tar.add(full_path, arcname=path)
            logger.debug(f"Added to backup: {path}")
        elif not optional:
            logger.warning(f"Path not found for backup: {path}")

    async def _create_zip_backup(self, backup_file: Path, includes: Dict[str, bool]):
        """Create ZIP-based backup.

        Args:
            backup_file: Output file path
            includes: What to include
        """
        with zipfile.ZipFile(backup_file, "w", zipfile.ZIP_DEFLATED) as zf:
            # Add files based on includes
            if includes["includes_config"]:
                self._add_to_zip(zf, "config", ".")
                self._add_to_zip(zf, ".env", ".", optional=True)

            if includes["includes_profiles"]:
                self._add_to_zip(zf, "profiles", ".")

            if includes["includes_states"]:
                self._add_to_zip(zf, "states", ".")

            if includes["includes_database"]:
                self._add_to_zip(zf, "data/lablink.db", ".", optional=True)
                self._add_to_zip(zf, "data/scheduler.db", ".", optional=True)
                self._add_to_zip(zf, "data/performance.db", ".", optional=True)

            if includes["includes_acquisitions"]:
                self._add_to_zip(zf, "data/acquisitions", ".")

            if includes["includes_logs"]:
                self._add_to_zip(zf, "logs", ".")

            if includes["includes_calibration"]:
                self._add_to_zip(zf, "data/calibration", ".")
                self._add_to_zip(zf, "data/calibration_enhanced", ".")

    def _add_to_zip(
        self, zf: zipfile.ZipFile, path: str, base: str, optional: bool = False
    ):
        """Add file or directory to ZIP archive.

        Args:
            zf: ZIP file object
            path: Path to add
            base: Base directory
            optional: Don't fail if path doesn't exist
        """
        full_path = Path(base) / path
        if full_path.exists():
            if full_path.is_file():
                zf.write(full_path, arcname=path)
                logger.debug(f"Added to backup: {path}")
            elif full_path.is_dir():
                for file in full_path.rglob("*"):
                    if file.is_file():
                        arcname = str(file.relative_to(base))
                        zf.write(file, arcname=arcname)
                        logger.debug(f"Added to backup: {arcname}")
        elif not optional:
            logger.warning(f"Path not found for backup: {path}")

    def _count_archive_contents(
        self, backup_file: Path, compression: CompressionType
    ) -> tuple[int, int]:
        """Count files and directories in archive.

        Args:
            backup_file: Backup archive file
            compression: Compression method

        Returns:
            Tuple of (file_count, directory_count)
        """
        file_count = 0
        dir_count = 0

        try:
            if compression == CompressionType.ZIP:
                with zipfile.ZipFile(backup_file, "r") as zf:
                    for info in zf.infolist():
                        if info.is_dir():
                            dir_count += 1
                        else:
                            file_count += 1
            else:
                with tarfile.open(backup_file, "r") as tar:
                    for member in tar.getmembers():
                        if member.isdir():
                            dir_count += 1
                        else:
                            file_count += 1
        except Exception as e:
            logger.error(f"Failed to count archive contents: {e}")

        return file_count, dir_count

    async def restore_backup(self, request: RestoreRequest) -> RestoreResult:
        """Restore from a backup.

        Args:
            request: Restore request

        Returns:
            Restore result

        Raises:
            ValueError: If backup not found
            Exception: If restore fails
        """
        # Get backup metadata
        if request.backup_id not in self.metadata:
            raise ValueError(f"Backup not found: {request.backup_id}")

        metadata = self.metadata[request.backup_id]
        started_at = datetime.now()

        logger.info(f"Restoring backup: {request.backup_id}")

        # Verify backup if requested
        if request.verify_before_restore and not metadata.verified:
            verification = await self.verify_backup(request.backup_id)
            if not verification.verified:
                raise ValueError(f"Backup verification failed: {request.backup_id}")

        # Create pre-restore backup if requested
        pre_restore_backup_id = None
        if request.create_backup_before_restore:
            try:
                pre_restore_request = BackupRequest(
                    backup_type=BackupType.FULL,
                    description=f"Pre-restore backup before restoring {request.backup_id}",
                    tags=["pre-restore", "automatic"],
                )
                pre_restore_meta = await self.create_backup(
                    pre_restore_request, created_by="system"
                )
                pre_restore_backup_id = pre_restore_meta.backup_id
                logger.info(f"Created pre-restore backup: {pre_restore_backup_id}")
            except Exception as e:
                logger.error(f"Failed to create pre-restore backup: {e}")

        # Perform restore
        result = RestoreResult(
            backup_id=request.backup_id,
            status="in_progress",
            started_at=started_at,
            completed_at=datetime.now(),
            duration_seconds=0.0,
            pre_restore_backup_id=pre_restore_backup_id,
        )

        try:
            backup_file = Path(metadata.file_path)

            # Extract based on compression type
            if metadata.compression == CompressionType.ZIP:
                await self._restore_from_zip(backup_file, request, result)
            else:
                await self._restore_from_tar(backup_file, request, result)

            result.status = "success"
            result.messages.append("Restore completed successfully")

        except Exception as e:
            logger.error(f"Restore failed: {e}")
            result.status = "failed"
            result.errors.append(str(e))

        # Update timing
        result.completed_at = datetime.now()
        result.duration_seconds = (
            result.completed_at - result.started_at
        ).total_seconds()

        logger.info(f"Restore completed: {request.backup_id} ({result.status})")

        return result

    async def _restore_from_tar(
        self, backup_file: Path, request: RestoreRequest, result: RestoreResult
    ):
        """Restore from tar archive.

        Args:
            backup_file: Backup file path
            request: Restore request
            result: Result object to update
        """
        with tarfile.open(backup_file, "r") as tar:
            for member in tar.getmembers():
                if self._should_restore_member(member.name, request):
                    try:
                        tar.extract(member, path=".")
                        result.files_restored += 1
                        self._update_restore_flags(member.name, request, result)
                    except Exception as e:
                        logger.error(f"Failed to restore {member.name}: {e}")
                        result.files_failed += 1
                        result.errors.append(f"Failed to restore {member.name}: {e}")
                else:
                    result.files_skipped += 1

    async def _restore_from_zip(
        self, backup_file: Path, request: RestoreRequest, result: RestoreResult
    ):
        """Restore from ZIP archive.

        Args:
            backup_file: Backup file path
            request: Restore request
            result: Result object to update
        """
        with zipfile.ZipFile(backup_file, "r") as zf:
            for info in zf.infolist():
                if self._should_restore_member(info.filename, request):
                    try:
                        zf.extract(info, path=".")
                        result.files_restored += 1
                        self._update_restore_flags(info.filename, request, result)
                    except Exception as e:
                        logger.error(f"Failed to restore {info.filename}: {e}")
                        result.files_failed += 1
                        result.errors.append(
                            f"Failed to restore {info.filename}: {e}"
                        )
                else:
                    result.files_skipped += 1

    def _should_restore_member(self, member_path: str, request: RestoreRequest) -> bool:
        """Check if archive member should be restored.

        Args:
            member_path: Path within archive
            request: Restore request

        Returns:
            True if should restore
        """
        if member_path.startswith("config/") or member_path == ".env":
            return request.restore_config
        elif member_path.startswith("profiles/"):
            return request.restore_profiles
        elif member_path.startswith("states/"):
            return request.restore_states
        elif "lablink.db" in member_path or "scheduler.db" in member_path:
            return request.restore_database
        elif member_path.startswith("data/acquisitions/"):
            return request.restore_acquisitions
        elif member_path.startswith("logs/"):
            return request.restore_logs
        elif member_path.startswith("data/calibration"):
            return request.restore_calibration

        return True  # Default: restore

    def _update_restore_flags(
        self, member_path: str, request: RestoreRequest, result: RestoreResult
    ):
        """Update restore result flags based on restored file.

        Args:
            member_path: Path that was restored
            request: Restore request
            result: Result object to update
        """
        if member_path.startswith("config/"):
            result.restored_config = True
        elif member_path.startswith("profiles/"):
            result.restored_profiles = True
        elif member_path.startswith("states/"):
            result.restored_states = True
        elif "lablink.db" in member_path:
            result.restored_database = True
        elif member_path.startswith("data/acquisitions/"):
            result.restored_acquisitions = True
        elif member_path.startswith("logs/"):
            result.restored_logs = True
        elif member_path.startswith("data/calibration"):
            result.restored_calibration = True

    async def verify_backup(self, backup_id: str) -> BackupVerificationResult:
        """Verify backup integrity.

        Args:
            backup_id: Backup to verify

        Returns:
            Verification result

        Raises:
            ValueError: If backup not found
        """
        if backup_id not in self.metadata:
            raise ValueError(f"Backup not found: {backup_id}")

        metadata = self.metadata[backup_id]
        backup_file = Path(metadata.file_path)

        result = BackupVerificationResult(
            backup_id=backup_id,
            verified=False,
            verification_time=datetime.now(),
            checksum_match=False,
            file_readable=False,
            file_size_match=False,
            compression_valid=False,
        )

        try:
            # Check file exists and is readable
            if not backup_file.exists():
                result.errors.append("Backup file not found")
                return result

            result.file_readable = True

            # Check file size
            actual_size = backup_file.stat().st_size
            if actual_size == metadata.file_size_bytes:
                result.file_size_match = True
            else:
                result.errors.append(
                    f"File size mismatch: expected {metadata.file_size_bytes}, got {actual_size}"
                )

            # Calculate checksum
            actual_checksum = self._calculate_checksum(backup_file)
            result.actual_checksum = actual_checksum

            if metadata.checksum:
                result.expected_checksum = metadata.checksum
                result.checksum_match = actual_checksum == metadata.checksum
                if not result.checksum_match:
                    result.errors.append("Checksum mismatch")
            else:
                result.checksum_match = True  # No stored checksum to compare

            # Verify archive can be opened
            try:
                if metadata.compression == CompressionType.ZIP:
                    with zipfile.ZipFile(backup_file, "r") as zf:
                        bad_file = zf.testzip()
                        if bad_file:
                            result.errors.append(f"Corrupted file in archive: {bad_file}")
                        else:
                            result.compression_valid = True
                            result.files_checked = len(zf.namelist())
                            result.files_valid = result.files_checked
                else:
                    with tarfile.open(backup_file, "r") as tar:
                        result.compression_valid = True
                        result.files_checked = len(tar.getmembers())
                        result.files_valid = result.files_checked
            except Exception as e:
                result.errors.append(f"Failed to open archive: {e}")

            # Overall verification
            result.verified = (
                result.file_readable
                and result.file_size_match
                and result.checksum_match
                and result.compression_valid
                and len(result.errors) == 0
            )

            if result.verified:
                result.messages.append("Backup verification successful")
                # Update metadata
                metadata.verified = True
                metadata.checksum = actual_checksum
                metadata.verification_time = result.verification_time
                metadata.status = BackupStatus.VERIFIED
                self._save_metadata()
            else:
                metadata.status = BackupStatus.CORRUPTED
                self._save_metadata()

        except Exception as e:
            logger.error(f"Backup verification failed: {e}")
            result.errors.append(str(e))

        return result

    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA-256 checksum of file.

        Args:
            file_path: File to checksum

        Returns:
            Hex digest of checksum
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()

    def list_backups(
        self, backup_type: Optional[BackupType] = None, verified_only: bool = False
    ) -> List[BackupInfo]:
        """List available backups.

        Args:
            backup_type: Filter by backup type
            verified_only: Only return verified backups

        Returns:
            List of backup info
        """
        backups = []
        for metadata in self.metadata.values():
            # Apply filters
            if backup_type and metadata.backup_type != backup_type:
                continue
            if verified_only and not metadata.verified:
                continue

            info = BackupInfo(
                backup_id=metadata.backup_id,
                backup_type=metadata.backup_type,
                created_at=metadata.created_at,
                file_size_mb=metadata.file_size_bytes / 1024 / 1024,
                status=metadata.status,
                verified=metadata.verified,
                description=metadata.description,
            )
            backups.append(info)

        # Sort by creation time (newest first)
        backups.sort(key=lambda x: x.created_at, reverse=True)

        return backups

    def get_backup(self, backup_id: str) -> Optional[BackupMetadata]:
        """Get backup metadata.

        Args:
            backup_id: Backup ID

        Returns:
            Backup metadata or None
        """
        return self.metadata.get(backup_id)

    def delete_backup(self, backup_id: str) -> bool:
        """Delete a backup.

        Args:
            backup_id: Backup to delete

        Returns:
            True if deleted successfully

        Raises:
            ValueError: If backup not found
        """
        if backup_id not in self.metadata:
            raise ValueError(f"Backup not found: {backup_id}")

        metadata = self.metadata[backup_id]

        try:
            # Delete backup file
            backup_file = Path(metadata.file_path)
            if backup_file.exists():
                backup_file.unlink()
                logger.info(f"Deleted backup file: {backup_file}")

            # Remove from metadata
            del self.metadata[backup_id]
            self._save_metadata()

            logger.info(f"Deleted backup: {backup_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete backup {backup_id}: {e}")
            raise

    def get_statistics(self) -> BackupStatistics:
        """Get backup statistics.

        Returns:
            Backup statistics
        """
        total_size = sum(m.file_size_bytes for m in self.metadata.values())

        # Count by type
        type_counts = {
            BackupType.FULL: 0,
            BackupType.CONFIG: 0,
            BackupType.DATA: 0,
        }
        for metadata in self.metadata.values():
            if metadata.backup_type in type_counts:
                type_counts[metadata.backup_type] += 1

        # Count by status
        completed = sum(
            1 for m in self.metadata.values() if m.status == BackupStatus.COMPLETED
        )
        failed = sum(
            1 for m in self.metadata.values() if m.status == BackupStatus.FAILED
        )
        verified = sum(1 for m in self.metadata.values() if m.verified)

        # Find oldest and newest
        if self.metadata:
            dates = [m.created_at for m in self.metadata.values()]
            oldest = min(dates)
            newest = max(dates)
        else:
            oldest = newest = None

        # Count backups to cleanup
        cutoff_date = datetime.now() - timedelta(days=self.config.retention_days)
        to_cleanup = sum(1 for m in self.metadata.values() if m.created_at < cutoff_date)

        return BackupStatistics(
            total_backups=len(self.metadata),
            total_size_bytes=total_size,
            total_size_mb=total_size / 1024 / 1024,
            full_backups=type_counts[BackupType.FULL],
            config_backups=type_counts[BackupType.CONFIG],
            data_backups=type_counts[BackupType.DATA],
            completed_backups=completed,
            failed_backups=failed,
            verified_backups=verified,
            oldest_backup=oldest,
            newest_backup=newest,
            backups_to_cleanup=to_cleanup,
        )

    async def cleanup_old_backups(self) -> int:
        """Clean up old backups based on retention policy.

        Returns:
            Number of backups deleted
        """
        deleted_count = 0
        cutoff_date = datetime.now() - timedelta(days=self.config.retention_days)

        # Get backups to delete
        to_delete = [
            backup_id
            for backup_id, metadata in self.metadata.items()
            if metadata.created_at < cutoff_date
        ]

        # Also check max count
        if len(self.metadata) > self.config.max_backup_count:
            # Sort by creation date (oldest first)
            sorted_backups = sorted(
                self.metadata.items(), key=lambda x: x[1].created_at
            )
            # Add oldest backups to deletion list
            excess_count = len(self.metadata) - self.config.max_backup_count
            for backup_id, _ in sorted_backups[:excess_count]:
                if backup_id not in to_delete:
                    to_delete.append(backup_id)

        # Delete backups
        for backup_id in to_delete:
            try:
                self.delete_backup(backup_id)
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to delete backup {backup_id}: {e}")

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old backups")

        return deleted_count

    async def start_auto_backup(self):
        """Start automatic backup task."""
        if not self.config.enable_auto_backup:
            logger.info("Auto-backup is disabled")
            return

        if self._auto_backup_task and not self._auto_backup_task.done():
            logger.warning("Auto-backup task is already running")
            return

        logger.info(
            f"Starting auto-backup task (interval: {self.config.auto_backup_interval_hours} hours)"
        )
        self._auto_backup_task = asyncio.create_task(self._auto_backup_loop())

    async def stop_auto_backup(self):
        """Stop automatic backup task."""
        if self._auto_backup_task and not self._auto_backup_task.done():
            self._auto_backup_task.cancel()
            try:
                await self._auto_backup_task
            except asyncio.CancelledError:
                pass
            logger.info("Auto-backup task stopped")

    async def _auto_backup_loop(self):
        """Automatic backup loop."""
        while True:
            try:
                # Wait for interval
                await asyncio.sleep(self.config.auto_backup_interval_hours * 3600)

                # Create automatic backup
                logger.info("Creating automatic backup...")
                request = BackupRequest(
                    backup_type=BackupType.FULL,
                    description="Automatic scheduled backup",
                    tags=["automatic"],
                )
                metadata = await self.create_backup(request, created_by="system")
                logger.info(f"Automatic backup created: {metadata.backup_id}")

                # Cleanup old backups
                await self.cleanup_old_backups()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Auto-backup failed: {e}")

    def _get_server_version(self) -> str:
        """Get LabLink server version.

        Returns:
            Server version string
        """
        try:
            # Try to get version from main.py
            main_file = Path(__file__).parent.parent / "main.py"
            if main_file.exists():
                with open(main_file, "r") as f:
                    for line in f:
                        if "version=" in line:
                            # Extract version from FastAPI app definition
                            parts = line.split("version=")
                            if len(parts) > 1:
                                version = parts[1].split('"')[1]
                                return version
            return "unknown"
        except:
            return "unknown"

    def _get_python_version(self) -> str:
        """Get Python version.

        Returns:
            Python version string
        """
        return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


# Global backup manager instance
_backup_manager: Optional[BackupManager] = None


def initialize_backup_manager(config: BackupConfig) -> BackupManager:
    """Initialize global backup manager.

    Args:
        config: Backup configuration

    Returns:
        Backup manager instance
    """
    global _backup_manager
    _backup_manager = BackupManager(config)
    return _backup_manager


def get_backup_manager() -> BackupManager:
    """Get global backup manager instance.

    Returns:
        Backup manager

    Raises:
        RuntimeError: If manager not initialized
    """
    if _backup_manager is None:
        raise RuntimeError("Backup manager not initialized")
    return _backup_manager
