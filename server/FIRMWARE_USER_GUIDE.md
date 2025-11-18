# Firmware Update System - User Guide

## Table of Contents
1. [Overview](#overview)
2. [Features](#features)
3. [Architecture](#architecture)
4. [API Reference](#api-reference)
5. [Usage Examples](#usage-examples)
6. [Safety and Best Practices](#safety-and-best-practices)
7. [Equipment Support](#equipment-support)
8. [Troubleshooting](#troubleshooting)

---

## Overview

The LabLink Firmware Update System provides a centralized, secure way to manage and deploy firmware updates to connected laboratory equipment. This system enables you to:

- **Upload and store** firmware packages for different equipment types
- **Verify integrity** of firmware files using cryptographic checksums
- **Check compatibility** before attempting updates
- **Track update progress** in real-time
- **Maintain history** of all firmware updates
- **Schedule updates** for later execution
- **Automatic rollback** on update failures

**Version**: v0.28.0
**Status**: Production Ready
**API Endpoints**: 11
**Features**: Version tracking, verification, compatibility checking, rollback support

---

## Features

### 1. Firmware Package Management

**Upload Firmware Packages**
- Support for binary firmware files of any size
- Multiple checksum algorithms (SHA-256, SHA-512, MD5, CRC32)
- Automatic integrity verification
- Version constraint support (min/max version requirements)
- Compatible model specifications
- Critical update flags
- Release notes and changelog support

**Package Organization**
- Filter by equipment type, manufacturer, or model
- Automatic sorting by release date
- Package metadata tracking
- User attribution (who uploaded what)

### 2. Compatibility Checking

Before any update, the system performs comprehensive compatibility checks:
- **Model matching**: Ensures firmware is for the correct equipment model
- **Version constraints**: Checks current version against min/max requirements
- **Equipment state**: Verifies equipment is in a suitable state for updates
- **Warnings**: Provides critical update notifications

### 3. Update Process

**Multi-Stage Update Pipeline**:
1. **Validation**: Verify firmware file integrity (checksum verification)
2. **Compatibility**: Confirm firmware matches equipment
3. **Backup**: Optionally create firmware backup (if supported)
4. **Upload**: Transfer firmware to equipment
5. **Installation**: Execute equipment-specific update procedure
6. **Verification**: Confirm successful installation
7. **Completion**: Update status and record history

**Progress Tracking**:
- Real-time status updates (9 status types)
- Progress percentage (0-100%)
- Current step descriptions
- Error reporting with detailed messages

### 4. Safety Features

**Automatic Rollback**
- Configurable auto-rollback on update failure
- Restore previous firmware version
- Protect against bricked equipment

**Pre-Update Verification**
- Optional firmware integrity check before upload
- Compatibility validation
- Equipment health check

**Update History**
- Complete audit trail of all updates
- Success/failure tracking
- Duration metrics
- User attribution

### 5. Statistics and Monitoring

**System-Wide Metrics**:
- Total firmware packages available
- Update success/failure rates
- Average update duration
- Updates by equipment
- Updates by status

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────┐
│                   Client Application                │
│              (GUI Client / Web Dashboard)           │
└─────────────────────┬───────────────────────────────┘
                      │ HTTP/REST API
┌─────────────────────▼───────────────────────────────┐
│              Firmware API Router (/api/firmware)    │
│  - Upload packages    - Start updates               │
│  - List packages      - Track progress              │
│  - Check compatibility- View history                │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│              Firmware Manager                       │
│  - Package storage    - Update orchestration        │
│  - Checksum verification - Progress tracking        │
│  - Compatibility checks - History recording         │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│              Equipment Base Class                   │
│  - update_firmware()   - supports_firmware_update() │
│  - backup_firmware()   - restore_firmware()         │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│         Equipment-Specific Implementation           │
│  (Rigol, BK Precision, etc. - when supported)      │
└─────────────────────────────────────────────────────┘
```

### Data Models

**FirmwarePackage**
- Package metadata (version, model, manufacturer)
- File information (path, size, checksum)
- Compatibility constraints
- Release information

**FirmwareUpdateProgress**
- Update ID and equipment ID
- Current status and progress percentage
- Step descriptions and timestamps
- Version information (old/new)

**FirmwareUpdateHistory**
- Complete update record
- Success/failure status
- Duration metrics
- User attribution

---

## API Reference

### Endpoints

#### 1. Upload Firmware Package
```http
POST /api/firmware/packages
Content-Type: multipart/form-data

Parameters:
- file: Binary firmware file
- equipment_type: Equipment type (e.g., "oscilloscope")
- manufacturer: Manufacturer name
- model: Model number
- version: Firmware version string
- release_notes: (Optional) Release notes
- critical: (Optional) Critical update flag
- compatible_models: (Optional) Comma-separated model list
- min_version: (Optional) Minimum current version
- max_version: (Optional) Maximum current version
- checksum_method: (Optional) sha256, sha512, md5, crc32
- uploaded_by: (Optional) Username

Response: FirmwarePackage object
```

#### 2. List Firmware Packages
```http
GET /api/firmware/packages?equipment_type=oscilloscope&model=DS1104

Response: Array of FirmwarePackage objects
```

#### 3. Get Firmware Package
```http
GET /api/firmware/packages/{firmware_id}

Response: FirmwarePackage object
```

#### 4. Delete Firmware Package
```http
DELETE /api/firmware/packages/{firmware_id}

Response: { "status": "success", "message": "..." }
```

#### 5. Verify Firmware Package
```http
POST /api/firmware/packages/{firmware_id}/verify

Response: { "verified": true/false, "message": "..." }
```

#### 6. Check Compatibility
```http
POST /api/firmware/compatibility/check

Body: {
  "equipment_id": "scope_001",
  "firmware_id": "firmware_abc123"
}

Response: FirmwareCompatibilityCheck object
```

#### 7. Start Firmware Update
```http
POST /api/firmware/updates

Body: {
  "equipment_id": "scope_001",
  "firmware_id": "firmware_abc123",
  "scheduled_time": null,  // null = immediate
  "verify_before_update": true,
  "create_backup": true,
  "auto_rollback_on_failure": true,
  "reboot_after_update": true,
  "notes": "Updating to fix bug XYZ"
}

Response: FirmwareUpdateProgress object
```

#### 8. Get Update Progress
```http
GET /api/firmware/updates/{update_id}

Response: FirmwareUpdateProgress object
```

#### 9. Get Update History
```http
GET /api/firmware/history?equipment_id=scope_001&limit=50

Response: Array of FirmwareUpdateHistory objects
```

#### 10. Get Statistics
```http
GET /api/firmware/statistics

Response: FirmwareStatistics object
```

#### 11. Get Equipment Firmware Info
```http
GET /api/firmware/equipment/{equipment_id}/info

Response: FirmwareInfo object
```

---

## Usage Examples

### Example 1: Upload and Deploy Firmware

```python
import requests

BASE_URL = "http://localhost:8000/api/firmware"

# Step 1: Upload firmware package
with open("rigol_ds1104_v1.2.5.bin", "rb") as f:
    files = {"file": f}
    data = {
        "equipment_type": "oscilloscope",
        "manufacturer": "Rigol",
        "model": "DS1104",
        "version": "1.2.5",
        "release_notes": "Bug fixes and performance improvements",
        "critical": False,
        "compatible_models": "DS1104,DS1102",
        "min_version": "1.0.0",
        "checksum_method": "sha256",
        "uploaded_by": "admin"
    }

    response = requests.post(f"{BASE_URL}/packages", files=files, data=data)
    package = response.json()
    print(f"Package uploaded: {package['id']}")

# Step 2: Verify firmware integrity
response = requests.post(f"{BASE_URL}/packages/{package['id']}/verify")
verification = response.json()
print(f"Verification: {verification}")

# Step 3: Check compatibility
response = requests.post(f"{BASE_URL}/compatibility/check", json={
    "equipment_id": "scope_001",
    "firmware_id": package['id']
})
compatibility = response.json()

if compatibility['compatible']:
    print("Firmware is compatible!")

    # Step 4: Start update
    update_request = {
        "equipment_id": "scope_001",
        "firmware_id": package['id'],
        "verify_before_update": True,
        "create_backup": True,
        "auto_rollback_on_failure": True,
        "reboot_after_update": True,
        "notes": "Scheduled maintenance update"
    }

    response = requests.post(f"{BASE_URL}/updates", json=update_request)
    progress = response.json()
    update_id = progress['update_id']
    print(f"Update started: {update_id}")

    # Step 5: Monitor progress
    import time
    while True:
        response = requests.get(f"{BASE_URL}/updates/{update_id}")
        progress = response.json()

        print(f"Status: {progress['status']} - {progress['progress_percent']}%")
        print(f"Current step: {progress['current_step']}")

        if progress['status'] in ['completed', 'failed', 'rolled_back']:
            break

        time.sleep(2)

    print(f"Final status: {progress['status']}")
    if progress['status'] == 'completed':
        print(f"Updated from {progress['old_version']} to {progress['new_version']}")
else:
    print(f"Firmware not compatible: {compatibility['reasons']}")
```

### Example 2: List Available Updates

```python
import requests

BASE_URL = "http://localhost:8000/api/firmware"
equipment_id = "scope_001"

# Get current firmware info
response = requests.get(f"{BASE_URL}/equipment/{equipment_id}/info")
info = response.json()

print(f"Current version: {info['current_version']}")
if info['update_available']:
    print(f"Update available: {info['latest_version']}")
    if info['update_critical']:
        print("⚠️  This is a CRITICAL update!")
else:
    print("Equipment is up to date")
```

### Example 3: View Update History

```python
import requests

BASE_URL = "http://localhost:8000/api/firmware"

# Get all update history
response = requests.get(f"{BASE_URL}/history?limit=100")
history = response.json()

print(f"Total updates: {len(history)}")
for record in history:
    status_icon = "✓" if record['status'] == 'completed' else "✗"
    print(f"{status_icon} {record['equipment_id']}: "
          f"{record['old_version']} → {record['new_version']} "
          f"({record['duration_seconds']:.1f}s)")
```

### Example 4: Get Statistics

```python
import requests

BASE_URL = "http://localhost:8000/api/firmware"

response = requests.get(f"{BASE_URL}/statistics")
stats = response.json()

print(f"Total firmware packages: {stats['total_packages']}")
print(f"Total updates: {stats['total_updates']}")
print(f"Success rate: {stats['successful_updates']/stats['total_updates']*100:.1f}%")
print(f"Average duration: {stats['average_duration_seconds']:.1f}s")

print("\nUpdates by equipment:")
for equipment_id, count in stats['updates_by_equipment'].items():
    print(f"  {equipment_id}: {count} updates")
```

---

## Safety and Best Practices

### Before Updating

1. **Backup Configuration**
   - Save equipment profiles and configurations
   - Document current settings

2. **Verify Compatibility**
   - Always check compatibility before updating
   - Review release notes for breaking changes

3. **Schedule Appropriately**
   - Update during maintenance windows
   - Avoid updates during critical operations

4. **Test on Non-Critical Equipment**
   - Deploy to test equipment first
   - Verify functionality before rolling out

### During Updates

1. **Monitor Progress**
   - Watch update status in real-time
   - Don't interrupt power or connections

2. **Maintain Connectivity**
   - Ensure stable network connection
   - Avoid disconnecting equipment

3. **Allow Time**
   - Firmware updates can take several minutes
   - Don't force shutdown during update

### After Updates

1. **Verify Functionality**
   - Test basic equipment functions
   - Run diagnostic tests
   - Compare before/after measurements

2. **Document Results**
   - Record new version number
   - Note any behavioral changes
   - Update equipment logs

3. **Report Issues**
   - If problems occur, check rollback capability
   - Contact vendor support if needed
   - Document issues in update history

### Security Considerations

1. **Firmware Source**
   - Only upload firmware from trusted sources
   - Verify checksums from vendor documentation
   - Use HTTPS for firmware downloads

2. **Access Control**
   - Restrict firmware upload to authorized users
   - Implement role-based access control
   - Audit all firmware operations

3. **Integrity Verification**
   - Always verify firmware before updating
   - Use strong checksum algorithms (SHA-256+)
   - Re-verify after storage

---

## Equipment Support

### Firmware Update Support by Equipment

| Equipment | Manufacturer | Update Support | Notes |
|-----------|-------------|----------------|-------|
| DS1104 | Rigol | Not implemented | May require vendor software |
| DS1102D | Rigol | Not implemented | May require vendor software |
| MSO2072A | Rigol | Not implemented | May require vendor software |
| DL3021A | Rigol | Not implemented | May require vendor software |
| 9206B | BK Precision | Not implemented | May require vendor software |
| 9205B | BK Precision | Not implemented | May require vendor software |
| 9130 | BK Precision | Not implemented | May require vendor software |
| 1902B | BK Precision | Not implemented | May require vendor software |
| 1685B | BK Precision | Not implemented | May require vendor software |

**Note**: The firmware update system infrastructure is complete and production-ready. However, individual equipment drivers need to implement the `update_firmware()` method with vendor-specific update protocols. Most laboratory equipment require proprietary software or special procedures for firmware updates.

### Implementing Equipment-Specific Updates

To add firmware update support to an equipment driver:

```python
from server.equipment.base import BaseEquipment

class MyEquipment(BaseEquipment):

    async def supports_firmware_update(self) -> bool:
        """Override to indicate firmware update support."""
        return True

    async def update_firmware(self, firmware_data: bytes) -> bool:
        """Implement vendor-specific firmware update procedure."""
        try:
            # 1. Put equipment in firmware update mode
            await self._write("SYST:FIRM:MODE UPDATE")

            # 2. Transfer firmware data
            # (Implementation depends on equipment protocol)
            chunk_size = 1024
            for i in range(0, len(firmware_data), chunk_size):
                chunk = firmware_data[i:i+chunk_size]
                await self._write_binary(chunk)

            # 3. Trigger firmware installation
            await self._write("SYST:FIRM:INSTALL")

            # 4. Wait for completion
            import asyncio
            await asyncio.sleep(30)  # Typical reboot time

            # 5. Verify new version
            new_version = await self.get_firmware_version()
            logger.info(f"Firmware updated to {new_version}")

            return True

        except Exception as e:
            logger.error(f"Firmware update failed: {e}")
            return False

    async def backup_firmware(self) -> Optional[bytes]:
        """Optional: Implement firmware backup if supported."""
        try:
            # Read current firmware from equipment
            firmware_data = await self._query_binary("SYST:FIRM:READ?")
            return firmware_data
        except:
            return None
```

---

## Troubleshooting

### Common Issues

#### 1. Checksum Verification Failed

**Symptom**: Firmware verification returns `verified: false`

**Causes**:
- File corruption during upload
- Incorrect checksum in firmware package
- Storage media errors

**Solutions**:
- Re-upload firmware file
- Verify source file checksum
- Check disk space and permissions

#### 2. Incompatible Firmware

**Symptom**: Compatibility check fails

**Causes**:
- Wrong equipment model
- Current version too old/new
- Firmware package misconfigured

**Solutions**:
- Verify equipment model number
- Check current firmware version
- Review firmware package compatible_models list

#### 3. Update Fails or Hangs

**Symptom**: Update status shows "failed" or stuck at low percentage

**Causes**:
- Equipment not responding
- Network connectivity issues
- Equipment already in use
- Insufficient equipment resources

**Solutions**:
- Check equipment connection
- Ensure equipment is idle
- Restart equipment and retry
- Review equipment error logs

#### 4. Equipment Not Responsive After Update

**Symptom**: Equipment doesn't respond after firmware update

**Causes**:
- Update still in progress (reboot cycle)
- Failed update corrupted firmware
- Equipment needs manual intervention

**Solutions**:
- Wait 5-10 minutes for reboot cycle
- Attempt auto-rollback if configured
- Power cycle equipment manually
- Contact vendor support

### Logging and Diagnostics

The firmware system logs all operations to the server log:

```bash
# View firmware-related logs
grep "firmware" /path/to/server/logs/lablink.log

# Monitor update progress
tail -f /path/to/server/logs/lablink.log | grep "Firmware update"
```

**Key Log Messages**:
- `"Firmware package uploaded"` - Package successfully stored
- `"Firmware file verified"` - Integrity check passed
- `"Started firmware update"` - Update initiated
- `"Firmware update completed"` - Update successful
- `"Firmware update failed"` - Update encountered error

### Getting Help

1. **Check API Documentation**: http://localhost:8000/docs#/firmware
2. **Review Server Logs**: Look for error messages and stack traces
3. **Test with Mock Equipment**: Verify system works with mock devices
4. **Consult Vendor Documentation**: Equipment-specific update procedures
5. **Report Issues**: GitHub issues with logs and reproduction steps

---

## Appendix

### Update Status Types

| Status | Description |
|--------|-------------|
| `pending` | Update queued, not started |
| `downloading` | Downloading firmware (if remote) |
| `validating` | Verifying firmware integrity |
| `uploading` | Transferring firmware to equipment |
| `updating` | Installing firmware on equipment |
| `verifying` | Confirming successful installation |
| `completed` | Update finished successfully |
| `failed` | Update encountered error |
| `rolled_back` | Update failed and was rolled back |

### Checksum Methods

| Method | Security | Speed | Use Case |
|--------|----------|-------|----------|
| SHA-256 | High | Medium | Recommended for production |
| SHA-512 | Very High | Medium | Maximum security |
| MD5 | Low | Fast | Legacy support only |
| CRC32 | None | Very Fast | Corruption detection only |

### Version Comparison Rules

The system compares version strings by splitting on `.` and comparing numerically:
- `1.0.0 < 1.0.1` (patch increment)
- `1.0.9 < 1.1.0` (minor increment)
- `1.9.9 < 2.0.0` (major increment)
- `1.10.0 > 1.9.0` (numeric, not string comparison)

---

**Document Version**: 1.0
**Last Updated**: 2025-11-18
**Author**: LabLink Development Team
