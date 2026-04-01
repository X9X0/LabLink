"""USB Device Diagnostics for troubleshooting serial number reading issues."""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def diagnose_usb_device(resource_string: str) -> Dict[str, any]:
    """
    Diagnose USB device and provide detailed information about why
    serial number might not be readable.

    Args:
        resource_string: VISA resource string of the device

    Returns:
        Dictionary with diagnostic information
    """
    diagnostics = {
        "resource_string": resource_string,
        "has_serial": False,
        "serial_readable": False,
        "usb_info": None,
        "issues": [],
        "recommendations": []
    }

    # Check if this is a USB device
    if not resource_string.startswith("USB"):
        diagnostics["issues"].append("Not a USB device")
        return diagnostics

    # Parse USB resource string
    # Format: USB[board]::vendor::product::serial::interface::INSTR
    parts = resource_string.split("::")
    if len(parts) < 5:
        diagnostics["issues"].append(f"Invalid USB resource string format: {resource_string}")
        return diagnostics

    vendor_id = parts[1] if len(parts) > 1 else None
    product_id = parts[2] if len(parts) > 2 else None
    serial = parts[3] if len(parts) > 3 else None

    diagnostics["usb_info"] = {
        "vendor_id": vendor_id,
        "product_id": product_id,
        "serial_number": serial
    }

    # Check if serial number is present and readable
    if serial and serial != "???":
        diagnostics["has_serial"] = True
        diagnostics["serial_readable"] = True
    elif serial == "???":
        diagnostics["has_serial"] = False
        diagnostics["serial_readable"] = False
        diagnostics["issues"].append("USB serial number descriptor cannot be read")

        # Add detailed root cause analysis
        diagnostics["issues"].extend([
            "Possible causes:",
            "1. USB communication issue - device may need to be unplugged/replugged",
            "2. Long server uptime - USB subsystem may be in stale state",
            "3. Device firmware issue - serial number descriptor may be corrupt",
            "4. PyUSB/libusb backend issue - driver may not support reading this descriptor",
            "5. USB permissions - process may not have permission to read device descriptors"
        ])

        # Add recommendations
        diagnostics["recommendations"].extend([
            "Try unplugging and replugging the USB device",
            "Restart the LabLink server to refresh USB subsystem",
            "Check USB cable and connection quality",
            "Update device firmware if available",
            "On Linux: check udev rules and user permissions for USB devices",
            "On Windows: check if libusb drivers are properly installed"
        ])
    else:
        diagnostics["has_serial"] = False
        diagnostics["serial_readable"] = False
        diagnostics["issues"].append("No serial number in resource string")

    return diagnostics


def log_usb_diagnostics(resource_string: str) -> None:
    """Log comprehensive USB diagnostics for a device."""
    diag = diagnose_usb_device(resource_string)

    logger.warning(f"USB Device Diagnostics for {resource_string}:")
    logger.warning(f"  Vendor ID: {diag['usb_info']['vendor_id'] if diag['usb_info'] else 'N/A'}")
    logger.warning(f"  Product ID: {diag['usb_info']['product_id'] if diag['usb_info'] else 'N/A'}")
    logger.warning(f"  Serial Number: {diag['usb_info']['serial_number'] if diag['usb_info'] else 'N/A'}")
    logger.warning(f"  Serial Readable: {diag['serial_readable']}")

    if diag['issues']:
        logger.warning("  Issues detected:")
        for issue in diag['issues']:
            logger.warning(f"    - {issue}")

    if diag['recommendations']:
        logger.warning("  Recommendations:")
        for rec in diag['recommendations']:
            logger.warning(f"    - {rec}")
