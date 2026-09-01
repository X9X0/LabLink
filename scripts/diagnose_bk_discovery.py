#!/usr/bin/env python3
"""Report what LabLink can see of the instruments plugged into this machine.

Run this on the Pi, with the instrument connected and powered on. It walks the
same path discovery walks, one layer at a time, and prints what survived each
one. When a device is missing from the final list, the last layer that still
showed it is the layer that dropped it.

    python3 scripts/diagnose_bk_discovery.py
    python3 scripts/diagnose_bk_discovery.py --all-ports   # include /dev/ttyS*
    python3 scripts/diagnose_bk_discovery.py --no-probe    # skip writing to ports

The probe writes ``*IDN?`` and ``GMAX`` to each port and reads the reply. Both
are read-only queries — nothing here changes an instrument's settings — but
``--no-probe`` skips that step entirely if a port is in use by something else.
"""

import argparse
import asyncio
import glob
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "server"))

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


def heading(number: int, title: str) -> None:
    print(f"\n{'=' * 72}\n{number}. {title}\n{'=' * 72}")


def line(status: str, message: str) -> None:
    print(f"  [{status}] {message}")


def detail(message: str) -> None:
    print(f"         {message}")


# ---------------------------------------------------------------------------
# Layer 1: the operating system
# ---------------------------------------------------------------------------

def check_os_devices() -> list:
    """What the kernel has enumerated, and whether we may open it."""
    heading(1, "Kernel device nodes")

    paths = sorted(
        glob.glob("/dev/ttyUSB*")
        + glob.glob("/dev/ttyACM*")
        + glob.glob("/dev/tty.usbserial*")
    )
    legacy = sorted(glob.glob("/dev/ttyS*"))

    if not paths:
        line(FAIL, "No USB serial device nodes (/dev/ttyUSB*, /dev/ttyACM*)")
        detail("The kernel has not enumerated a USB serial adapter at all.")
        detail("If the instrument is plugged in and on, check `dmesg | tail`")
        detail("for a cp210x/ftdi_sio/cdc_acm driver bind. In a container,")
        detail("check that /dev is actually shared from the host: LabLink's")
        detail("compose file maps /dev/bus/usb but relies on privileged mode")
        detail("for the tty nodes.")
    else:
        line(PASS, f"{len(paths)} USB serial device node(s): {', '.join(paths)}")

    if legacy:
        detail(f"Plus {len(legacy)} built-in UART(s) (/dev/ttyS*), usually empty")

    for path in paths:
        readable = os.access(path, os.R_OK)
        writable = os.access(path, os.W_OK)
        if readable and writable:
            line(PASS, f"{path} is readable and writable by uid {os.geteuid()}")
        else:
            line(FAIL, f"{path} is NOT accessible (read={readable} write={writable})")
            try:
                import grp
                group = grp.getgrgid(os.stat(path).st_gid).gr_name
                detail(f"Owned by group '{group}'. Add the service user to it:")
                detail(f"    sudo usermod -aG {group} $USER   # then re-login")
            except Exception:
                detail("Could not determine the owning group.")

    return paths


# ---------------------------------------------------------------------------
# Layer 2: sysfs USB identity
# ---------------------------------------------------------------------------

def check_sysfs_ids(paths: list) -> dict:
    """The USB VID/PID behind each port.

    This is what LabLink's `usb_only` filter keys on. A port whose VID cannot
    be read is skipped by default, so a blank here explains a missing device.
    """
    heading(2, "USB vendor/product IDs from sysfs")

    if not paths:
        line(WARN, "No ports to inspect")
        return {}

    try:
        from discovery.usb_hardware_db import (extract_usb_ids_from_serial_port,
                                               lookup_usb_device)
    except Exception as e:
        line(FAIL, f"Could not import LabLink's USB hardware database: {e}")
        return {}

    found = {}
    for path in paths:
        ids = extract_usb_ids_from_serial_port(path)
        if not ids:
            line(WARN, f"{path}: no VID:PID readable from /sys")
            detail("The default usb_only filter will SKIP this port.")
            detail("Re-run with --all-ports, or set")
            detail("LABLINK_DISCOVERY_SERIAL_PROBE_USB_ONLY=false")
            continue
        vid, pid = ids
        found[path] = ids
        known = lookup_usb_device(vid, pid)
        if known:
            line(PASS, f"{path}: {vid}:{pid} -> {known.manufacturer} {known.model}")
        else:
            line(PASS, f"{path}: {vid}:{pid} (not in the hardware database)")
            detail("Not a problem: identification falls through to *IDN?/GMAX.")
    return found


# ---------------------------------------------------------------------------
# Layer 3: pyserial, and LabLink's port filter
# ---------------------------------------------------------------------------

def check_pyserial(all_ports: bool) -> list:
    heading(3, "pyserial enumeration and LabLink's port filter")

    try:
        from serial.tools import list_ports
    except ImportError:
        line(FAIL, "pyserial is not installed — the serial probe cannot run")
        detail("pip install pyserial==3.5   (it is in server/requirements.txt)")
        return []

    ports = list(list_ports.comports())
    line(PASS, f"pyserial lists {len(ports)} port(s)")
    for port in ports:
        vid = f"{port.vid:04x}" if port.vid is not None else "----"
        pid = f"{port.pid:04x}" if port.pid is not None else "----"
        detail(f"{port.device:20s} vid={vid} pid={pid}  {port.description}")

    try:
        from discovery.bk_serial_probe import find_serial_ports
    except Exception as e:
        line(FAIL, f"Could not import the B&K serial probe: {e}")
        return []

    kept = find_serial_ports(usb_only=not all_ports)
    mode = "all ports" if all_ports else "USB-attached only"
    if kept:
        line(PASS, f"LabLink will probe {len(kept)} port(s) ({mode}): {', '.join(kept)}")
    else:
        line(FAIL, f"LabLink will probe NO ports ({mode})")
        if not all_ports:
            detail("Every port was filtered out for having no USB vendor ID.")
            detail("Re-run with --all-ports to confirm that is the cause.")
    return kept


# ---------------------------------------------------------------------------
# Layer 4: the probe itself
# ---------------------------------------------------------------------------

def check_probe(ports: list, timeout: float) -> None:
    """Open each port and ask who is there, at each candidate baud rate."""
    heading(4, "Serial probe (*IDN? then GMAX, at each baud rate)")

    if not ports:
        line(WARN, "No ports to probe")
        return

    try:
        from discovery.bk_serial_probe import (DEFAULT_BAUDS,
                                               _device_from_probe,
                                               _probe_port_blocking)
    except Exception as e:
        line(FAIL, f"Could not import the probe: {e}")
        return

    for port in ports:
        print(f"\n  --- {port} ---")
        result = _probe_port_blocking(port, tuple(DEFAULT_BAUDS), timeout)
        if not result:
            line(FAIL, f"{port}: silent at every rate {tuple(DEFAULT_BAUDS)}")
            detail("Silence means one of: wrong baud (the front-panel rate")
            detail("persists in NVRAM), a straight-through cable where the")
            detail("model wants a null modem, the port held open by another")
            detail("process, or an instrument that is simply not B&K.")
            continue

        if result.get("protocol") == "scpi":
            line(PASS, f"{port} answered *IDN? at {result['baudrate']} baud")
            detail(f"reply: {result['idn']}")
        else:
            line(PASS, f"{port} answered GMAX at {result['baudrate']} baud")
            detail(f"reply: {result['gmax']} (a legacy supply — it has no *IDN?)")

        device = _device_from_probe(result)
        if device is None:
            line(WARN, f"{port}: answered, but is not a B&K instrument")
            detail("LabLink's B&K probe ignores it; VISA may still find it.")
            continue

        line(PASS, f"identified as {device.manufacturer} {device.model}")
        detail(f"type={device.device_type.value} confidence={device.confidence_score}")
        for key in ("bk_family_name", "protocol", "usb_mode", "driver_supported",
                    "max_voltage", "max_current"):
            if key in device.metadata:
                detail(f"{key}: {device.metadata[key]}")


# ---------------------------------------------------------------------------
# Layer 5: VISA
# ---------------------------------------------------------------------------

def check_visa() -> None:
    """What VISA sees. USB-CDC instruments will not be here — that is expected."""
    heading(5, "VISA resources")

    try:
        import pyvisa
    except ImportError:
        line(FAIL, "pyvisa is not installed")
        return

    try:
        rm = pyvisa.ResourceManager("@py")
    except Exception as e:
        line(FAIL, f"Could not open a VISA resource manager: {e}")
        return

    try:
        resources = list(rm.list_resources())
    except Exception as e:
        line(FAIL, f"list_resources() failed: {e}")
        return
    finally:
        try:
            rm.close()
        except Exception:
            pass

    if resources:
        line(PASS, f"VISA lists {len(resources)} resource(s)")
        for resource in resources:
            detail(resource)
    else:
        line(WARN, "VISA lists no resources")
        detail("Expected for a USB-CDC instrument: it is a UART bridge, and")
        detail("VISA never enumerates those. Layer 4 is what finds them.")


# ---------------------------------------------------------------------------
# Layer 6: the full discovery scan
# ---------------------------------------------------------------------------

async def check_full_scan(all_ports: bool, probe: bool) -> None:
    """The whole pipeline, exactly as the server runs it."""
    heading(6, "Full discovery scan (what the client would show)")

    try:
        from discovery.manager import DiscoveryManager
        from discovery.models import DiscoveryConfig
    except Exception as e:
        line(FAIL, f"Could not import the discovery manager: {e}")
        return

    config = DiscoveryConfig(
        cache_discovered_devices=False,
        enable_serial_probe=probe,
        serial_probe_usb_only=not all_ports,
    )
    result = await DiscoveryManager(config).scan()

    if result.errors:
        for error in result.errors:
            line(FAIL, error)

    if not result.devices:
        line(FAIL, "The scan found no devices")
        detail("Compare against the layers above to see where it was lost.")
        return

    line(PASS, f"{len(result.devices)} device(s): "
               f"{result.visa_count} via VISA, {result.usb_count} via the serial probe")
    for device in result.devices:
        print()
        detail(f"{device.manufacturer or '?'} {device.model or '?'}")
        detail(f"  resource:   {device.resource_name}")
        detail(f"  type:       {device.device_type.value}")
        detail(f"  confidence: {device.confidence_score}")
        family = device.metadata.get("bk_family_name")
        if family:
            detail(f"  family:     {family}")
            detail(f"  drivable:   {device.metadata.get('driver_supported')}")
            detail(f"  interfaces: {', '.join(device.metadata.get('interfaces', []))}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-ports", action="store_true",
                        help="probe built-in UARTs too, not just USB-attached ports")
    parser.add_argument("--no-probe", action="store_true",
                        help="skip opening ports; report enumeration only")
    parser.add_argument("--timeout", type=float, default=0.6,
                        help="per-baud-rate wait for a reply (default 0.6s)")
    args = parser.parse_args()

    print("LabLink equipment discovery diagnostic")
    print(f"python {sys.version.split()[0]} on {sys.platform}, uid {os.geteuid()}")
    print(f"repo: {REPO_ROOT}")
    if Path("/.dockerenv").exists():
        print("running inside a container")

    paths = check_os_devices()
    check_sysfs_ids(paths)
    ports = check_pyserial(args.all_ports)
    if args.no_probe:
        heading(4, "Serial probe — SKIPPED (--no-probe)")
    else:
        check_probe(ports, args.timeout)
    check_visa()
    asyncio.run(check_full_scan(args.all_ports, not args.no_probe))

    print(f"\n{'=' * 72}")
    print("Read the layers in order: the last one that still showed your")
    print("instrument is the one that dropped it.")
    print(f"{'=' * 72}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
