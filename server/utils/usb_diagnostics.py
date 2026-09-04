"""USB device diagnostics for unreadable serial numbers (issue #166).

The question this answers is not "is the serial string odd" -- the caller can
see that -- but *why*, and the only way to tell the causes apart is to go and
look at the bus. So this enumerates the device with pyusb, tries the serial
descriptor itself, and reports what it found.

The distinction that matters in practice: a resource string saying ``???``
while the device answers its descriptor perfectly well means the instrument is
fine and LabLink's cached resource string is stale. That is a server rescan,
not a trip to the bench to reseat a cable.

Every finding here is evidence from a check that ran. Where a check could not
run -- no libusb backend, most often on Windows, where the instrument may be
bound to a vendor or USBTMC driver that libusb cannot see -- this says so
instead of guessing.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Descriptor reads that fail for want of permission report these. libusb
# normalises to EACCES; the errno is not always populated on Windows.
_PERMISSION_ERRNOS = {13}


def _parse_resource_string(resource_string: str) -> Optional[Dict[str, Any]]:
    """Pull vendor, product and serial out of a VISA USB resource string.

    ``USB[board]::vendor::product::serial::interface::INSTR``, where vendor
    and product are **decimal** -- ``USB0::11975::37376::...`` is the device
    ``lsusb`` calls ``2ec7:9200``.
    """
    parts = resource_string.split("::")
    if len(parts) < 5:
        return None

    def _as_int(value: str) -> Optional[int]:
        try:
            return int(value, 0)
        except (TypeError, ValueError):
            return None

    return {
        "vendor_id": parts[1],
        "product_id": parts[2],
        "serial_number": parts[3],
        "vendor_id_int": _as_int(parts[1]),
        "product_id_int": _as_int(parts[2]),
    }


def _find_device(vendor_id: Optional[int], product_id: Optional[int]):
    """Locate the device on the bus.

    Returns ``(device, error_kind, detail)``. ``error_kind`` is None when the
    lookup itself worked, whether or not it found anything.
    """
    try:
        import usb.core
    except ImportError as exc:
        return None, "pyusb_missing", str(exc)

    if vendor_id is None or product_id is None:
        return None, "unparsed_ids", "vendor/product id not numeric"

    try:
        device = usb.core.find(idVendor=vendor_id, idProduct=product_id)
    except usb.core.NoBackendError as exc:
        return None, "no_backend", str(exc)
    except Exception as exc:  # a bus that cannot be walked is a finding too
        return None, "enumeration_failed", f"{type(exc).__name__}: {exc}"

    return device, None, None


def _read_descriptor_serial(device):
    """Ask the device for its serial descriptor.

    Returns ``(serial, error_kind, detail)``. This is the read that fails in
    the field, so its failure mode is the diagnosis.
    """
    try:
        import usb.core
    except ImportError as exc:  # pragma: no cover - _find_device got here first
        return None, "pyusb_missing", str(exc)

    try:
        serial = device.serial_number
    except usb.core.USBError as exc:
        kind = ("permission_denied"
                if getattr(exc, "errno", None) in _PERMISSION_ERRNOS
                else "descriptor_read_failed")
        return None, kind, f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        return None, "descriptor_read_failed", f"{type(exc).__name__}: {exc}"

    if serial is None or not str(serial).strip():
        return None, "no_serial_descriptor", "device reports an empty serial"

    return str(serial), None, None


def diagnose_usb_device(resource_string: str) -> Dict[str, Any]:
    """Inspect a USB instrument and say why its serial may be unreadable.

    Args:
        resource_string: VISA resource string of the device

    Returns:
        A dict carrying ``usb_info``, ``serial_readable``, ``issues`` and
        ``recommendations`` (which the client renders), plus ``checks`` -- the
        list of what was actually attempted and what each attempt found.
    """
    diagnostics: Dict[str, Any] = {
        "resource_string": resource_string,
        "has_serial": False,
        "serial_readable": False,
        "usb_info": None,
        "device_present": None,
        "descriptor_serial": None,
        "checks": [],
        "issues": [],
        "recommendations": [],
    }

    def record(name: str, result: str, detail: str = "") -> None:
        diagnostics["checks"].append(
            {"check": name, "result": result, "detail": detail}
        )

    if not resource_string.startswith("USB"):
        diagnostics["issues"].append(
            f"Not a USB device: {resource_string} is addressed over another "
            "transport, so there is no USB serial descriptor to read."
        )
        record("resource_string", "not_usb", resource_string)
        return diagnostics

    parsed = _parse_resource_string(resource_string)
    if parsed is None:
        diagnostics["issues"].append(
            f"Invalid USB resource string format: {resource_string}"
        )
        record("resource_string", "unparseable", resource_string)
        return diagnostics

    claimed_serial = parsed["serial_number"]
    diagnostics["usb_info"] = {
        "vendor_id": parsed["vendor_id"],
        "product_id": parsed["product_id"],
        "serial_number": claimed_serial,
    }
    claimed_is_readable = bool(claimed_serial) and claimed_serial != "???"
    diagnostics["has_serial"] = claimed_is_readable
    record("resource_string", "parsed",
           f"vendor={parsed['vendor_id']} product={parsed['product_id']} "
           f"serial={claimed_serial}")

    device, error_kind, detail = _find_device(
        parsed["vendor_id_int"], parsed["product_id_int"]
    )

    if error_kind in ("pyusb_missing", "no_backend"):
        # Not a fault in the instrument, and saying nothing further is the
        # honest answer: without a backend nothing about the bus was observed.
        record("usb_enumeration", error_kind, detail or "")
        diagnostics["serial_readable"] = claimed_is_readable
        diagnostics["issues"].append(
            "Could not inspect the USB bus: no libusb backend is available to "
            "pyusb, so the device was not examined. This is common on Windows, "
            "where the instrument may be bound to a vendor or USBTMC driver "
            "that libusb cannot see."
        )
        diagnostics["recommendations"].append(
            "Install a libusb backend (libusb-1.0) to enable USB inspection, "
            "or run these diagnostics on the machine the instrument is "
            "attached to."
        )
        if not claimed_is_readable:
            diagnostics["recommendations"].append(
                "The resource string reports an unreadable serial (???). "
                "Without bus access this cannot be attributed; restarting the "
                "server to rebuild its device list is the usual first step."
            )
        return diagnostics

    if error_kind is not None:
        record("usb_enumeration", error_kind, detail or "")
        diagnostics["serial_readable"] = claimed_is_readable
        diagnostics["issues"].append(f"Could not enumerate the USB bus: {detail}")
        return diagnostics

    if device is None:
        diagnostics["device_present"] = False
        record("usb_enumeration", "device_absent",
               f"no device matching {parsed['vendor_id']}:{parsed['product_id']}")
        diagnostics["issues"].append(
            "The device is not on the USB bus. Whatever the resource string "
            "says, nothing is enumerated at that vendor/product id."
        )
        diagnostics["recommendations"].extend([
            "Check that the instrument is powered on and its USB cable seated",
            "Confirm it appears in the host's device list (lsusb on Linux, "
            "Device Manager on Windows)",
        ])
        return diagnostics

    diagnostics["device_present"] = True
    record("usb_enumeration", "device_present",
           f"{parsed['vendor_id']}:{parsed['product_id']}")

    serial, error_kind, detail = _read_descriptor_serial(device)

    if error_kind == "permission_denied":
        record("serial_descriptor", "permission_denied", detail or "")
        diagnostics["issues"].append(
            "The device is present, but reading its serial descriptor was "
            "refused for want of permission. This is the process's access to "
            "the device, not a fault in the instrument."
        )
        diagnostics["recommendations"].extend([
            "On Linux: add a udev rule granting access to "
            f"{parsed['vendor_id']}:{parsed['product_id']}, or run the server "
            "as a user in the right group, then replug the device",
            "On Windows: install a libusb-compatible driver for the device",
        ])
        return diagnostics

    if error_kind == "no_serial_descriptor":
        record("serial_descriptor", "empty", detail or "")
        diagnostics["issues"].append(
            "The device is present and readable, but reports no serial number "
            "of its own. Some units ship without one programmed."
        )
        diagnostics["recommendations"].append(
            "Address this instrument by its resource string rather than by "
            "serial number; a firmware update may add one."
        )
        return diagnostics

    if error_kind is not None:
        record("serial_descriptor", "read_failed", detail or "")
        diagnostics["issues"].append(
            f"The device is present, but its serial descriptor could not be "
            f"read: {detail}"
        )
        diagnostics["recommendations"].extend([
            "Unplug and replug the device to reset its USB state",
            "Try a different cable or port, avoiding hubs",
        ])
        return diagnostics

    # The descriptor read. Everything below is about whether the resource
    # string agrees with it.
    diagnostics["descriptor_serial"] = serial
    diagnostics["serial_readable"] = True
    record("serial_descriptor", "read", serial)

    if not claimed_is_readable:
        # The signature of #166: the instrument is fine and the cached
        # resource string is not.
        diagnostics["has_serial"] = True
        diagnostics["issues"].append(
            f"The resource string reports an unreadable serial ({claimed_serial}) "
            f"but the device answers with {serial!r}. The instrument is fine; "
            "the server's cached resource string is stale."
        )
        diagnostics["recommendations"].extend([
            "Re-run equipment discovery to rebuild the resource string",
            "If it persists, restart the LabLink server -- the stale entry is "
            "in the running process, not the device",
        ])
        return diagnostics

    if serial != claimed_serial:
        diagnostics["issues"].append(
            f"The resource string names serial {claimed_serial!r}, but the "
            f"device at that vendor/product id reports {serial!r}. The string "
            "may be addressing an instrument that has since been swapped."
        )
        diagnostics["recommendations"].append(
            "Re-run equipment discovery so the resource string matches the "
            "instrument actually attached"
        )
        return diagnostics

    record("serial_match", "ok", serial)
    return diagnostics


def log_usb_diagnostics(resource_string: str) -> None:
    """Log diagnostics for a device, for the connection-failure path."""
    diag = diagnose_usb_device(resource_string)
    usb_info = diag.get("usb_info") or {}

    logger.warning(f"USB Device Diagnostics for {resource_string}:")
    logger.warning(f"  Vendor ID: {usb_info.get('vendor_id', 'N/A')}")
    logger.warning(f"  Product ID: {usb_info.get('product_id', 'N/A')}")
    logger.warning(f"  Serial Number: {usb_info.get('serial_number', 'N/A')}")
    logger.warning(f"  Present on the bus: {diag.get('device_present')}")
    logger.warning(f"  Serial Readable: {diag['serial_readable']}")
    if diag.get("descriptor_serial"):
        logger.warning(f"  Device reports: {diag['descriptor_serial']}")

    for check in diag.get("checks", []):
        logger.warning(
            f"  checked {check['check']}: {check['result']}"
            + (f" ({check['detail']})" if check["detail"] else "")
        )

    if diag["issues"]:
        logger.warning("  Issues detected:")
        for issue in diag["issues"]:
            logger.warning(f"    - {issue}")

    if diag["recommendations"]:
        logger.warning("  Recommendations:")
        for rec in diag["recommendations"]:
            logger.warning(f"    - {rec}")


__all__: List[str] = ["diagnose_usb_device", "log_usb_diagnostics"]
