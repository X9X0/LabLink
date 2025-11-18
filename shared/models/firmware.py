"""Firmware update data models."""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class FirmwareUpdateStatus(str, Enum):
    """Status of a firmware update."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    VALIDATING = "validating"
    UPLOADING = "uploading"
    UPDATING = "updating"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class FirmwareVerificationMethod(str, Enum):
    """Methods for verifying firmware integrity."""

    MD5 = "md5"
    SHA256 = "sha256"
    SHA512 = "sha512"
    CRC32 = "crc32"


class FirmwarePackage(BaseModel):
    """Firmware package information."""

    id: str = Field(..., description="Unique identifier for this firmware package")
    equipment_type: str = Field(..., description="Type of equipment (e.g., 'oscilloscope', 'power_supply')")
    manufacturer: str = Field(..., description="Equipment manufacturer")
    model: str = Field(..., description="Equipment model number")
    version: str = Field(..., description="Firmware version string")
    release_date: datetime = Field(..., description="Firmware release date")
    file_path: str = Field(..., description="Path to firmware file")
    file_size: int = Field(..., description="File size in bytes")
    checksum: str = Field(..., description="Checksum for verification")
    checksum_method: FirmwareVerificationMethod = Field(
        default=FirmwareVerificationMethod.SHA256,
        description="Checksum algorithm used"
    )
    min_current_version: Optional[str] = Field(
        None,
        description="Minimum current version required for this update"
    )
    max_current_version: Optional[str] = Field(
        None,
        description="Maximum current version this update can be applied to"
    )
    release_notes: Optional[str] = Field(None, description="Release notes/changelog")
    critical: bool = Field(default=False, description="Whether this is a critical update")
    compatible_models: List[str] = Field(
        default_factory=list,
        description="List of compatible model numbers"
    )
    uploaded_at: datetime = Field(
        default_factory=datetime.now,
        description="When the package was uploaded"
    )
    uploaded_by: Optional[str] = Field(None, description="User who uploaded the package")


class FirmwareUpdateRequest(BaseModel):
    """Request to update equipment firmware."""

    equipment_id: str = Field(..., description="ID of equipment to update")
    firmware_id: str = Field(..., description="ID of firmware package to install")
    scheduled_time: Optional[datetime] = Field(
        None,
        description="When to perform the update (None = immediate)"
    )
    verify_before_update: bool = Field(
        default=True,
        description="Verify firmware integrity before updating"
    )
    create_backup: bool = Field(
        default=True,
        description="Create backup of current firmware if possible"
    )
    auto_rollback_on_failure: bool = Field(
        default=True,
        description="Automatically rollback if update fails"
    )
    reboot_after_update: bool = Field(
        default=True,
        description="Reboot equipment after successful update"
    )
    notes: Optional[str] = Field(None, description="Notes about this update")


class FirmwareUpdateProgress(BaseModel):
    """Progress information for a firmware update."""

    update_id: str = Field(..., description="Unique ID for this update operation")
    equipment_id: str = Field(..., description="Equipment being updated")
    firmware_id: str = Field(..., description="Firmware package being installed")
    status: FirmwareUpdateStatus = Field(..., description="Current status")
    progress_percent: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Progress percentage (0-100)"
    )
    current_step: str = Field(default="", description="Description of current step")
    started_at: datetime = Field(
        default_factory=datetime.now,
        description="When the update started"
    )
    completed_at: Optional[datetime] = Field(None, description="When the update completed")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    old_version: Optional[str] = Field(None, description="Version before update")
    new_version: Optional[str] = Field(None, description="Version after update")


class FirmwareUpdateHistory(BaseModel):
    """Historical record of a firmware update."""

    id: str = Field(..., description="Unique ID for this history record")
    equipment_id: str = Field(..., description="Equipment that was updated")
    equipment_model: str = Field(..., description="Equipment model")
    firmware_id: str = Field(..., description="Firmware package that was installed")
    old_version: str = Field(..., description="Version before update")
    new_version: str = Field(..., description="Version after update")
    status: FirmwareUpdateStatus = Field(..., description="Final status of update")
    started_at: datetime = Field(..., description="When the update started")
    completed_at: Optional[datetime] = Field(None, description="When the update completed")
    duration_seconds: Optional[float] = Field(None, description="Duration in seconds")
    initiated_by: Optional[str] = Field(None, description="User who initiated the update")
    notes: Optional[str] = Field(None, description="Notes about the update")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    rolled_back: bool = Field(default=False, description="Whether update was rolled back")


class FirmwareCompatibilityCheck(BaseModel):
    """Result of checking firmware compatibility with equipment."""

    compatible: bool = Field(..., description="Whether firmware is compatible")
    equipment_id: str = Field(..., description="Equipment ID")
    equipment_model: str = Field(..., description="Equipment model")
    current_version: str = Field(..., description="Current firmware version")
    firmware_id: str = Field(..., description="Firmware package ID")
    firmware_version: str = Field(..., description="Firmware package version")
    reasons: List[str] = Field(
        default_factory=list,
        description="Reasons for compatibility/incompatibility"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings about the update"
    )


class FirmwareInfo(BaseModel):
    """Information about firmware installed on equipment."""

    equipment_id: str = Field(..., description="Equipment ID")
    current_version: str = Field(..., description="Currently installed version")
    manufacturer: str = Field(..., description="Equipment manufacturer")
    model: str = Field(..., description="Equipment model")
    last_updated: Optional[datetime] = Field(None, description="Last update timestamp")
    update_available: bool = Field(default=False, description="Whether update is available")
    latest_version: Optional[str] = Field(None, description="Latest available version")
    update_critical: bool = Field(default=False, description="Whether available update is critical")


class FirmwareStatistics(BaseModel):
    """Statistics about firmware updates."""

    total_packages: int = Field(default=0, description="Total firmware packages available")
    total_updates: int = Field(default=0, description="Total updates performed")
    successful_updates: int = Field(default=0, description="Successful updates")
    failed_updates: int = Field(default=0, description="Failed updates")
    rolled_back_updates: int = Field(default=0, description="Updates that were rolled back")
    average_duration_seconds: Optional[float] = Field(
        None,
        description="Average update duration in seconds"
    )
    last_update: Optional[datetime] = Field(None, description="Most recent update")
    updates_by_equipment: Dict[str, int] = Field(
        default_factory=dict,
        description="Update count by equipment ID"
    )
    updates_by_status: Dict[str, int] = Field(
        default_factory=dict,
        description="Update count by status"
    )
