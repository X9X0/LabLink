"""API endpoints for Backup & Restore system."""

from typing import List, Optional

from backup import (BackupInfo, BackupMetadata, BackupRequest,
                    BackupStatistics, BackupType, BackupVerificationResult,
                    RestoreRequest, RestoreResult, get_backup_manager)
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/backup", tags=["backup"])


# === Backup Management Endpoints ===


@router.post("/create", response_model=BackupMetadata)
async def create_backup(request: BackupRequest):
    """Create a new backup.

    Creates a backup based on the specified type and options. Supports full,
    config-only, profiles-only, data-only, and database-only backups.

    **Request Body:**
    - backup_type: Type of backup (full, config, profiles, data, database, incremental)
    - description: Optional backup description
    - tags: Optional list of tags
    - compression: Compression method (overrides config)
    - verify_after_backup: Verify backup after creation (overrides config)
    - include_*: Override what to include in backup

    **Returns:**
    - Complete backup metadata including file path, size, status, and verification

    **Example:**
    ```json
    {
      "backup_type": "full",
      "description": "Pre-upgrade backup",
      "tags": ["manual", "pre-upgrade"],
      "verify_after_backup": true
    }
    ```
    """
    try:
        manager = get_backup_manager()
        metadata = await manager.create_backup(request)
        return metadata
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list", response_model=List[BackupInfo])
async def list_backups(
    backup_type: Optional[str] = Query(None, description="Filter by backup type"),
    verified_only: bool = Query(False, description="Only return verified backups"),
):
    """List available backups.

    Returns a list of all backups with optional filtering.

    **Query Parameters:**
    - backup_type: Filter by backup type (full, config, profiles, data, database)
    - verified_only: Only return backups that have been verified

    **Returns:**
    - List of backup info with ID, type, creation time, size, status, verification

    **Example Response:**
    ```json
    [
      {
        "backup_id": "backup_20231113_143022",
        "backup_type": "full",
        "created_at": "2023-11-13T14:30:22",
        "file_size_mb": 125.4,
        "status": "verified",
        "verified": true,
        "description": "Pre-upgrade backup"
      }
    ]
    ```
    """
    try:
        manager = get_backup_manager()

        # Convert string to enum if provided
        backup_type_enum = None
        if backup_type:
            try:
                backup_type_enum = BackupType(backup_type)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"Invalid backup type: {backup_type}"
                )

        backups = manager.list_backups(
            backup_type=backup_type_enum, verified_only=verified_only
        )
        return backups
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{backup_id}", response_model=BackupMetadata)
async def get_backup(backup_id: str):
    """Get detailed backup metadata.

    Returns complete metadata for a specific backup including all content
    information, verification status, and file details.

    **Path Parameters:**
    - backup_id: Backup identifier

    **Returns:**
    - Complete backup metadata

    **Raises:**
    - 404: Backup not found
    """
    try:
        manager = get_backup_manager()
        metadata = manager.get_backup(backup_id)

        if metadata is None:
            raise HTTPException(status_code=404, detail="Backup not found")

        return metadata
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{backup_id}")
async def delete_backup(backup_id: str):
    """Delete a backup.

    Permanently deletes a backup file and its metadata. This operation
    cannot be undone.

    **Path Parameters:**
    - backup_id: Backup to delete

    **Returns:**
    - Success message

    **Raises:**
    - 404: Backup not found
    - 500: Deletion failed
    """
    try:
        manager = get_backup_manager()
        manager.delete_backup(backup_id)
        return {"message": f"Backup deleted successfully: {backup_id}"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics/summary", response_model=BackupStatistics)
async def get_backup_statistics():
    """Get backup statistics.

    Returns comprehensive statistics about all backups including counts,
    sizes, status distribution, and retention information.

    **Returns:**
    - total_backups: Total number of backups
    - total_size_bytes/mb: Total backup storage used
    - full_backups/config_backups/data_backups: Counts by type
    - completed_backups/failed_backups/verified_backups: Counts by status
    - oldest_backup/newest_backup: Date range
    - backups_to_cleanup: Number of backups exceeding retention period

    **Example Response:**
    ```json
    {
      "total_backups": 15,
      "total_size_mb": 2450.8,
      "full_backups": 10,
      "config_backups": 3,
      "data_backups": 2,
      "completed_backups": 14,
      "failed_backups": 1,
      "verified_backups": 13,
      "oldest_backup": "2023-10-15T10:00:00",
      "newest_backup": "2023-11-13T14:30:22",
      "backups_to_cleanup": 2
    }
    ```
    """
    try:
        manager = get_backup_manager()
        stats = manager.get_statistics()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Restore Endpoints ===


@router.post("/restore", response_model=RestoreResult)
async def restore_backup(request: RestoreRequest):
    """Restore from a backup.

    Restores data from a backup with granular control over what to restore.
    Can optionally create a pre-restore backup and verify before restoring.

    **Request Body:**
    - backup_id: Backup to restore from (required)
    - restore_config/profiles/states/database/acquisitions/logs/calibration: What to restore
    - overwrite_existing: Overwrite existing files
    - create_backup_before_restore: Create safety backup first (recommended)
    - verify_before_restore: Verify backup integrity before restoring

    **Returns:**
    - Restore result with status, statistics, and any errors

    **Example:**
    ```json
    {
      "backup_id": "backup_20231113_143022",
      "restore_config": true,
      "restore_profiles": true,
      "restore_database": true,
      "create_backup_before_restore": true,
      "verify_before_restore": true
    }
    ```

    **⚠️ Warning:**
    Restoring will overwrite existing data. It's highly recommended to:
    - Set create_backup_before_restore=true
    - Set verify_before_restore=true
    - Review backup contents before restoring
    """
    try:
        manager = get_backup_manager()
        result = await manager.restore_backup(request)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Verification Endpoints ===


@router.post("/{backup_id}/verify", response_model=BackupVerificationResult)
async def verify_backup(backup_id: str):
    """Verify backup integrity.

    Performs comprehensive verification of a backup including:
    - File existence and readability
    - File size match
    - Checksum verification (SHA-256)
    - Archive integrity check
    - Compression validity

    **Path Parameters:**
    - backup_id: Backup to verify

    **Returns:**
    - Verification result with detailed status

    **Raises:**
    - 404: Backup not found
    - 500: Verification failed

    **Example Response:**
    ```json
    {
      "backup_id": "backup_20231113_143022",
      "verified": true,
      "verification_time": "2023-11-13T15:00:00",
      "checksum_match": true,
      "file_readable": true,
      "file_size_match": true,
      "compression_valid": true,
      "files_checked": 156,
      "files_valid": 156,
      "files_corrupted": 0,
      "messages": ["Backup verification successful"],
      "errors": []
    }
    ```
    """
    try:
        manager = get_backup_manager()
        result = await manager.verify_backup(backup_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Maintenance Endpoints ===


@router.post("/cleanup")
async def cleanup_old_backups():
    """Clean up old backups.

    Removes backups that exceed the retention policy based on:
    - Age (older than retention_days)
    - Count (exceeds max_backup_count)

    Oldest backups are deleted first. Failed backups are prioritized for deletion.

    **Returns:**
    - deleted_count: Number of backups deleted
    - message: Summary message

    **Example Response:**
    ```json
    {
      "deleted_count": 3,
      "message": "Cleaned up 3 old backups"
    }
    ```
    """
    try:
        manager = get_backup_manager()
        deleted_count = await manager.cleanup_old_backups()
        return {
            "deleted_count": deleted_count,
            "message": f"Cleaned up {deleted_count} old backups",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/info")
async def get_backup_info():
    """Get backup system information.

    Returns configuration and capabilities of the backup system.

    **Returns:**
    - Configuration settings
    - Supported backup types
    - Supported compression methods
    - Retention policy
    - Auto-backup settings

    **Example Response:**
    ```json
    {
      "backup_dir": "./data/backups",
      "enable_auto_backup": true,
      "auto_backup_interval_hours": 24,
      "retention_days": 30,
      "max_backup_count": 10,
      "compression": "tar.gz",
      "verify_after_backup": true,
      "supported_backup_types": ["full", "config", "profiles", "data", "database", "incremental"],
      "supported_compression": ["none", "gzip", "zip", "tar.gz"]
    }
    ```
    """
    try:
        manager = get_backup_manager()
        config = manager.config

        return {
            "backup_dir": config.backup_dir,
            "enable_auto_backup": config.enable_auto_backup,
            "auto_backup_interval_hours": config.auto_backup_interval_hours,
            "retention_days": config.retention_days,
            "max_backup_count": config.max_backup_count,
            "compression": config.compression,
            "verify_after_backup": config.verify_after_backup,
            "calculate_checksums": config.calculate_checksums,
            "includes": {
                "config": config.include_config,
                "profiles": config.include_profiles,
                "states": config.include_states,
                "database": config.include_database,
                "acquisitions": config.include_acquisitions,
                "logs": config.include_logs,
                "calibration": config.include_calibration,
            },
            "supported_backup_types": [t.value for t in BackupType],
            "supported_compression": ["none", "gzip", "zip", "tar.gz"],
            "features": {
                "automatic_backup": "Scheduled automatic backups",
                "verification": "SHA-256 checksum and integrity verification",
                "retention_policy": "Automatic cleanup of old backups",
                "compression": "Multiple compression methods supported",
                "selective_restore": "Restore only specific components",
                "pre_restore_backup": "Safety backup before restoring",
                "metadata_tracking": "Complete backup history and statistics",
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
