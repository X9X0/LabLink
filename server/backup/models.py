"""Backup & Restore system data models."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class BackupType(str, Enum):
    """Type of backup."""

    FULL = "full"  # Complete backup of all data
    CONFIG = "config"  # Configuration and settings only
    PROFILES = "profiles"  # Equipment profiles only
    DATA = "data"  # Acquisition data and logs only
    DATABASE = "database"  # Database files only
    INCREMENTAL = "incremental"  # Changes since last backup


class BackupStatus(str, Enum):
    """Status of a backup operation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    CORRUPTED = "corrupted"


class CompressionType(str, Enum):
    """Compression method for backups."""

    NONE = "none"
    GZIP = "gzip"
    ZIP = "zip"
    TAR_GZ = "tar.gz"


class BackupConfig(BaseModel):
    """Configuration for backup operations."""

    # Backup settings
    backup_dir: str = Field("./data/backups", description="Directory to store backups")
    enable_auto_backup: bool = Field(True, description="Enable automatic scheduled backups")
    auto_backup_interval_hours: int = Field(24, ge=1, le=168, description="Interval between auto backups (1-168 hours)")

    # Retention policy
    retention_days: int = Field(30, ge=1, le=365, description="Days to keep backups")
    max_backup_count: int = Field(10, ge=1, le=100, description="Maximum number of backups to keep")

    # Backup content
    include_config: bool = Field(True, description="Include configuration files")
    include_profiles: bool = Field(True, description="Include equipment profiles")
    include_states: bool = Field(True, description="Include saved equipment states")
    include_database: bool = Field(True, description="Include database files")
    include_acquisitions: bool = Field(False, description="Include acquisition data files")
    include_logs: bool = Field(False, description="Include log files")
    include_calibration: bool = Field(True, description="Include calibration data")

    # Compression
    compression: CompressionType = Field(CompressionType.TAR_GZ, description="Compression method")

    # Verification
    verify_after_backup: bool = Field(True, description="Verify backup integrity after creation")
    calculate_checksums: bool = Field(True, description="Calculate file checksums")


class BackupMetadata(BaseModel):
    """Metadata for a backup."""

    backup_id: str = Field(..., description="Unique backup identifier")
    backup_type: BackupType = Field(..., description="Type of backup")
    created_at: datetime = Field(..., description="Backup creation timestamp")
    created_by: Optional[str] = Field(None, description="User who created backup")

    # Backup content
    file_path: str = Field(..., description="Path to backup file")
    file_size_bytes: int = Field(..., description="Backup file size")
    compression: CompressionType = Field(..., description="Compression method used")

    # Status
    status: BackupStatus = Field(BackupStatus.PENDING, description="Backup status")
    error_message: Optional[str] = Field(None, description="Error message if failed")

    # Content summary
    includes_config: bool = Field(False, description="Contains configuration")
    includes_profiles: bool = Field(False, description="Contains profiles")
    includes_states: bool = Field(False, description="Contains states")
    includes_database: bool = Field(False, description="Contains database")
    includes_acquisitions: bool = Field(False, description="Contains acquisition data")
    includes_logs: bool = Field(False, description="Contains logs")
    includes_calibration: bool = Field(False, description="Contains calibration data")

    # File counts
    file_count: int = Field(0, description="Number of files in backup")
    directory_count: int = Field(0, description="Number of directories in backup")

    # Verification
    verified: bool = Field(False, description="Backup has been verified")
    checksum: Optional[str] = Field(None, description="SHA-256 checksum of backup file")
    verification_time: Optional[datetime] = Field(None, description="When backup was verified")

    # Version info
    server_version: str = Field(..., description="LabLink server version")
    python_version: str = Field(..., description="Python version")

    # Notes
    description: Optional[str] = Field(None, description="Backup description")
    tags: List[str] = Field(default_factory=list, description="Backup tags")


class BackupInfo(BaseModel):
    """Summary information about a backup."""

    backup_id: str
    backup_type: BackupType
    created_at: datetime
    file_size_mb: float
    status: BackupStatus
    verified: bool
    description: Optional[str] = None


class BackupRequest(BaseModel):
    """Request to create a backup."""

    backup_type: BackupType = Field(BackupType.FULL, description="Type of backup to create")
    description: Optional[str] = Field(None, description="Backup description")
    tags: List[str] = Field(default_factory=list, description="Backup tags")

    # Override config settings
    compression: Optional[CompressionType] = Field(None, description="Compression method (overrides config)")
    verify_after_backup: Optional[bool] = Field(None, description="Verify after creation (overrides config)")

    # Content overrides
    include_config: Optional[bool] = None
    include_profiles: Optional[bool] = None
    include_states: Optional[bool] = None
    include_database: Optional[bool] = None
    include_acquisitions: Optional[bool] = None
    include_logs: Optional[bool] = None
    include_calibration: Optional[bool] = None


class RestoreRequest(BaseModel):
    """Request to restore from a backup."""

    backup_id: str = Field(..., description="Backup ID to restore from")

    # What to restore
    restore_config: bool = Field(True, description="Restore configuration")
    restore_profiles: bool = Field(True, description="Restore equipment profiles")
    restore_states: bool = Field(True, description="Restore equipment states")
    restore_database: bool = Field(True, description="Restore database")
    restore_acquisitions: bool = Field(True, description="Restore acquisition data")
    restore_logs: bool = Field(False, description="Restore log files")
    restore_calibration: bool = Field(True, description="Restore calibration data")

    # Restore options
    overwrite_existing: bool = Field(False, description="Overwrite existing files")
    create_backup_before_restore: bool = Field(True, description="Create backup before restoring")
    verify_before_restore: bool = Field(True, description="Verify backup before restoring")


class RestoreResult(BaseModel):
    """Result of a restore operation."""

    backup_id: str
    status: str  # "success", "partial", "failed"
    started_at: datetime
    completed_at: datetime
    duration_seconds: float

    # What was restored
    restored_config: bool = False
    restored_profiles: bool = False
    restored_states: bool = False
    restored_database: bool = False
    restored_acquisitions: bool = False
    restored_logs: bool = False
    restored_calibration: bool = False

    # Statistics
    files_restored: int = 0
    files_skipped: int = 0
    files_failed: int = 0

    # Pre-restore backup
    pre_restore_backup_id: Optional[str] = None

    # Messages
    messages: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class BackupStatistics(BaseModel):
    """Statistics about backups."""

    total_backups: int
    total_size_bytes: int
    total_size_mb: float

    # By type
    full_backups: int
    config_backups: int
    data_backups: int

    # By status
    completed_backups: int
    failed_backups: int
    verified_backups: int

    # Oldest and newest
    oldest_backup: Optional[datetime] = None
    newest_backup: Optional[datetime] = None

    # Retention
    backups_to_cleanup: int = 0


class BackupVerificationResult(BaseModel):
    """Result of backup verification."""

    backup_id: str
    verified: bool
    verification_time: datetime

    # Checksum verification
    checksum_match: bool
    expected_checksum: Optional[str] = None
    actual_checksum: Optional[str] = None

    # File integrity
    file_readable: bool
    file_size_match: bool
    compression_valid: bool

    # Content verification
    files_checked: int = 0
    files_valid: int = 0
    files_corrupted: int = 0

    # Messages
    messages: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class CloudBackupConfig(BaseModel):
    """Configuration for cloud backup integration."""

    enabled: bool = Field(False, description="Enable cloud backup")
    provider: str = Field("s3", description="Cloud provider (s3, azure, gcp)")

    # S3/Compatible
    endpoint_url: Optional[str] = Field(None, description="S3 endpoint URL")
    bucket_name: Optional[str] = Field(None, description="Bucket name")
    access_key: Optional[str] = Field(None, description="Access key")
    secret_key: Optional[str] = Field(None, description="Secret key")
    region: Optional[str] = Field(None, description="Region")

    # Upload settings
    auto_upload: bool = Field(False, description="Automatically upload backups")
    upload_after_verification: bool = Field(True, description="Upload only verified backups")
    retention_days_cloud: int = Field(90, description="Cloud backup retention days")
