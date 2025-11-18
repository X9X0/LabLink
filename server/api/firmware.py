"""Firmware update API endpoints."""

import logging
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from equipment.manager import equipment_manager
from firmware import firmware_manager
from shared.models.firmware import (
    FirmwareCompatibilityCheck,
    FirmwareInfo,
    FirmwarePackage,
    FirmwareStatistics,
    FirmwareUpdateHistory,
    FirmwareUpdateProgress,
    FirmwareUpdateRequest,
    FirmwareVerificationMethod,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/firmware", tags=["Firmware Management"])


@router.post("/packages", response_model=FirmwarePackage)
async def upload_firmware_package(
    file: UploadFile = File(..., description="Firmware binary file"),
    equipment_type: str = Form(..., description="Equipment type"),
    manufacturer: str = Form(..., description="Manufacturer name"),
    model: str = Form(..., description="Model number"),
    version: str = Form(..., description="Firmware version"),
    release_notes: Optional[str] = Form(None, description="Release notes"),
    critical: bool = Form(False, description="Critical update flag"),
    compatible_models: Optional[str] = Form(
        None, description="Comma-separated list of compatible models"
    ),
    min_version: Optional[str] = Form(None, description="Minimum current version"),
    max_version: Optional[str] = Form(None, description="Maximum current version"),
    checksum_method: str = Form("sha256", description="Checksum method (sha256, sha512, md5, crc32)"),
    uploaded_by: Optional[str] = Form(None, description="User uploading the firmware"),
):
    """
    Upload a new firmware package.

    This endpoint allows uploading firmware files that can later be used to
    update compatible equipment. The firmware file is stored securely and
    verified with a checksum.

    **Security**: Only authorized users should have access to this endpoint.
    """
    try:
        # Read file data
        file_data = await file.read()

        if len(file_data) == 0:
            raise HTTPException(status_code=400, detail="Empty firmware file")

        # Parse compatible models
        models_list = None
        if compatible_models:
            models_list = [m.strip() for m in compatible_models.split(",")]

        # Validate checksum method
        try:
            checksum_enum = FirmwareVerificationMethod(checksum_method.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid checksum method. Must be one of: sha256, sha512, md5, crc32"
            )

        # Upload firmware
        package = await firmware_manager.upload_firmware(
            file_data=file_data,
            equipment_type=equipment_type,
            manufacturer=manufacturer,
            model=model,
            version=version,
            release_notes=release_notes,
            critical=critical,
            compatible_models=models_list,
            min_version=min_version,
            max_version=max_version,
            checksum_method=checksum_enum,
            uploaded_by=uploaded_by,
        )

        logger.info(
            f"Firmware package uploaded: {package.id} ({package.manufacturer} "
            f"{package.model} v{package.version}, {package.file_size} bytes)"
        )

        return package

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading firmware: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/packages", response_model=List[FirmwarePackage])
async def list_firmware_packages(
    equipment_type: Optional[str] = None,
    manufacturer: Optional[str] = None,
    model: Optional[str] = None,
):
    """
    List available firmware packages with optional filters.

    Returns all firmware packages that match the specified criteria.
    Results are sorted by release date (newest first).
    """
    try:
        packages = await firmware_manager.list_packages(
            equipment_type=equipment_type,
            manufacturer=manufacturer,
            model=model,
        )
        return packages

    except Exception as e:
        logger.error(f"Error listing firmware packages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/packages/{firmware_id}", response_model=FirmwarePackage)
async def get_firmware_package(firmware_id: str):
    """
    Get details of a specific firmware package.

    Returns complete information about a firmware package including
    version, size, checksum, and compatibility information.
    """
    try:
        package = await firmware_manager.get_package(firmware_id)
        if not package:
            raise HTTPException(status_code=404, detail="Firmware package not found")

        return package

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting firmware package: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/packages/{firmware_id}")
async def delete_firmware_package(firmware_id: str):
    """
    Delete a firmware package.

    Removes the firmware package from storage. This operation cannot be undone.

    **Security**: Only authorized users should be able to delete firmware packages.
    """
    try:
        success = await firmware_manager.delete_package(firmware_id)
        if not success:
            raise HTTPException(status_code=404, detail="Firmware package not found")

        logger.info(f"Firmware package deleted: {firmware_id}")
        return {"status": "success", "message": "Firmware package deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting firmware package: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/packages/{firmware_id}/verify")
async def verify_firmware_package(firmware_id: str):
    """
    Verify integrity of a firmware package.

    Checks that the firmware file exists and its checksum matches
    the expected value. This should be done before attempting to
    update equipment.
    """
    try:
        valid = await firmware_manager.verify_firmware_file(firmware_id)

        if not valid:
            return {
                "verified": False,
                "message": "Firmware verification failed - checksum mismatch or file not found"
            }

        return {
            "verified": True,
            "message": "Firmware file verified successfully"
        }

    except Exception as e:
        logger.error(f"Error verifying firmware: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compatibility/check", response_model=FirmwareCompatibilityCheck)
async def check_firmware_compatibility(
    equipment_id: str,
    firmware_id: str,
):
    """
    Check if a firmware package is compatible with equipment.

    Verifies that the firmware can be safely installed on the specified
    equipment by checking model compatibility, version constraints, and
    other requirements.

    **Important**: Always check compatibility before attempting an update.
    """
    try:
        # Get equipment
        equipment = equipment_manager.equipment.get(equipment_id)
        if not equipment:
            raise HTTPException(status_code=404, detail="Equipment not found")

        # Get equipment info
        info = await equipment.get_info()
        status = await equipment.get_status()

        # Check compatibility
        result = await firmware_manager.check_compatibility(
            equipment_id=equipment_id,
            firmware_id=firmware_id,
            current_version=status.firmware_version or "unknown",
            equipment_model=info.model,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking compatibility: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/updates", response_model=FirmwareUpdateProgress)
async def start_firmware_update(request: FirmwareUpdateRequest):
    """
    Start a firmware update operation.

    Initiates a firmware update for the specified equipment. The update
    runs asynchronously in the background. Use the update ID to track
    progress via the `/updates/{update_id}` endpoint.

    **Warning**: Firmware updates can take several minutes and may require
    equipment reboot. Ensure the equipment is not in use before updating.

    **Safety**: The update process includes verification, optional backup,
    and automatic rollback on failure (if enabled in the request).
    """
    try:
        # Get equipment
        equipment = equipment_manager.equipment.get(request.equipment_id)
        if not equipment:
            raise HTTPException(status_code=404, detail="Equipment not found")

        # Check if equipment supports firmware updates
        if not await equipment.supports_firmware_update():
            # Check if update_firmware raises NotImplementedError
            try:
                # This will raise NotImplementedError for unsupported equipment
                await equipment.update_firmware(b"")
            except NotImplementedError as e:
                raise HTTPException(
                    status_code=400,
                    detail=str(e)
                )

        # Verify firmware package exists
        package = await firmware_manager.get_package(request.firmware_id)
        if not package:
            raise HTTPException(status_code=404, detail="Firmware package not found")

        # Check compatibility
        info = await equipment.get_info()
        status = await equipment.get_status()

        compat = await firmware_manager.check_compatibility(
            equipment_id=request.equipment_id,
            firmware_id=request.firmware_id,
            current_version=status.firmware_version or "unknown",
            equipment_model=info.model,
        )

        if not compat.compatible:
            raise HTTPException(
                status_code=400,
                detail=f"Firmware not compatible: {', '.join(compat.reasons)}"
            )

        # Start update
        progress = await firmware_manager.start_update(request, equipment)

        logger.info(
            f"Firmware update started: {progress.update_id} for equipment "
            f"{request.equipment_id}"
        )

        return progress

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting firmware update: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/updates/{update_id}", response_model=FirmwareUpdateProgress)
async def get_update_progress(update_id: str):
    """
    Get progress of a firmware update operation.

    Returns the current status, progress percentage, and detailed
    information about an ongoing or completed firmware update.
    """
    try:
        progress = await firmware_manager.get_update_progress(update_id)
        if not progress:
            raise HTTPException(status_code=404, detail="Update not found")

        return progress

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting update progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", response_model=List[FirmwareUpdateHistory])
async def get_update_history(
    equipment_id: Optional[str] = None,
    limit: int = 100,
):
    """
    Get firmware update history.

    Returns historical records of firmware updates, optionally filtered
    by equipment. Useful for auditing and troubleshooting.
    """
    try:
        history = await firmware_manager.get_update_history(
            equipment_id=equipment_id,
            limit=limit,
        )
        return history

    except Exception as e:
        logger.error(f"Error getting update history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics", response_model=FirmwareStatistics)
async def get_firmware_statistics():
    """
    Get firmware update statistics.

    Returns aggregate statistics about firmware packages and updates,
    including success rates, durations, and update counts by equipment.
    """
    try:
        stats = await firmware_manager.get_statistics()
        return stats

    except Exception as e:
        logger.error(f"Error getting firmware statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/equipment/{equipment_id}/info", response_model=FirmwareInfo)
async def get_equipment_firmware_info(equipment_id: str):
    """
    Get firmware information for specific equipment.

    Returns current firmware version and information about available updates.
    """
    try:
        # Get equipment
        equipment = equipment_manager.equipment.get(equipment_id)
        if not equipment:
            raise HTTPException(status_code=404, detail="Equipment not found")

        # Get current version and info
        info = await equipment.get_info()
        status = await equipment.get_status()
        current_version = status.firmware_version or "unknown"

        # Check for available updates
        packages = await firmware_manager.list_packages(
            manufacturer=info.manufacturer,
            model=info.model,
        )

        update_available = False
        latest_version = None
        update_critical = False

        if packages:
            # Get latest compatible package
            latest = packages[0]  # Already sorted by date
            latest_version = latest.version

            # Compare versions
            if current_version != latest_version:
                update_available = True
                update_critical = latest.critical

        firmware_info = FirmwareInfo(
            equipment_id=equipment_id,
            current_version=current_version,
            manufacturer=info.manufacturer,
            model=info.model,
            update_available=update_available,
            latest_version=latest_version,
            update_critical=update_critical,
        )

        return firmware_info

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting equipment firmware info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Export router
firmware_router = router
