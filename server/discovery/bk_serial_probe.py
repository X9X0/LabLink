"""Serial probing for B&K instruments that discovery would otherwise miss.

Two classes of B&K device never turn up in a normal scan:

**USB-CDC instruments.** Roughly half the line puts a USB-to-UART bridge behind
the USB socket rather than a USBTMC endpoint. VISA does not enumerate those at
all — they are serial ports — so a perfectly healthy 9140 or 2840 looks absent.
They also have no discovery protocol: the only way to find one is to open the
port and ask, and the baud rate is unknown until it answers.

**Legacy fixed-width supplies.** The 1685B, 1900B, 1696 and 9103 lines have no
``*IDN?`` and no query syntax at all, so even an open port stays silent to the
standard probe. They do answer ``GMAX``, which returns their rated voltage and
current — enough to identify the family *and* learn its limits in one command.

Probing is deliberately conservative: it opens a port, writes, waits briefly
for a reply, and closes. It never writes a setting.
"""

import asyncio
import glob
import logging
import sys
from typing import Dict, List, Optional

from equipment.bk_registry import (MANUFACTURER, PROTOCOL_FIXED,
                                   CATEGORY_LABELS,
                                   CATEGORY_TO_EQUIPMENT_TYPE, BKModel,
                                   candidate_bauds, is_bk_manufacturer,
                                   is_drivable, resolve_model)

from .models import (ConnectionStatus, DeviceType, DiscoveredDevice,
                     DiscoveryMethod)

logger = logging.getLogger(__name__)

#: Baud rates tried per port, most likely first. 9600 covers the legacy line
#: and most of the SCPI models; 115200 covers the 1820B and HPS.
DEFAULT_BAUDS = candidate_bauds()

#: Seconds to wait for a reply before moving to the next baud rate. Long
#: enough for a legacy supply to answer, short enough that sweeping six rates
#: across a handful of ports stays quick.
PROBE_TIMEOUT = 0.6


def find_serial_ports(usb_only: bool = True) -> List[str]:
    """List candidate serial ports, USB-backed ones first.

    ``usb_only`` skips the motherboard's built-in UARTs. A Linux host
    typically exposes 32 ``/dev/ttyS*`` devices that nothing is plugged into,
    and probing each one at six baud rates costs far more time than it can
    ever repay. Pass False to sweep them anyway — an RS-232 instrument on a
    real serial card does live there.
    """
    try:
        from serial.tools import list_ports
    except ImportError:
        logger.debug("pyserial not installed; falling back to device globs")
        if sys.platform.startswith("win"):
            return []
        usb_ports = sorted(
            glob.glob("/dev/ttyUSB*")
            + glob.glob("/dev/ttyACM*")
            + glob.glob("/dev/tty.usbserial*")
        )
        if usb_only:
            return usb_ports
        return usb_ports + sorted(glob.glob("/dev/ttyS*"))

    ports = list(list_ports.comports())
    if usb_only:
        # `vid` is set only for USB-attached ports, which is exactly the
        # distinction we want, and it works on Windows COM ports too.
        ports = [p for p in ports if p.vid is not None]
    return [port.device for port in ports]


def _probe_port_blocking(port: str, bauds, timeout: float) -> Optional[Dict]:
    """Ask one port who it is, trying each baud rate in turn.

    Runs the SCPI probe and the legacy probe at every rate before moving on,
    because a wrong baud and a wrong protocol look identical from here: both
    are silence.
    """
    try:
        import serial
    except ImportError:
        logger.debug("pyserial not installed; cannot probe %s", port)
        return None

    for baud in bauds:
        handle = None
        try:
            handle = serial.Serial(
                port=port, baudrate=baud, bytesize=8, parity="N",
                stopbits=1, timeout=timeout,
            )
        except Exception as e:
            logger.debug(f"Cannot open {port} at {baud}: {e}")
            return None  # The port itself is unusable; other rates won't help

        try:
            # A model may leave a banner or a stale reply in the buffer.
            handle.reset_input_buffer()

            # 1. SCPI. Answers from every model except the fixed-width line.
            handle.write(b"*IDN?\n")
            handle.flush()
            reply = handle.read_until(b"\n").decode("ascii", "replace").strip()
            if reply and "," in reply:
                return {"port": port, "baudrate": baud, "idn": reply,
                        "protocol": "scpi"}

            # 2. Legacy fixed-width. GMAX returns VVVCCC then OK, both CR
            #    terminated, and is read-only.
            handle.reset_input_buffer()
            handle.write(b"GMAX\r")
            handle.flush()
            raw = handle.read_until(b"OK\r").decode("ascii", "replace").strip()
            digits = raw.replace("OK", "").strip()
            if len(digits) >= 6 and digits[:6].isdigit():
                return {"port": port, "baudrate": baud, "gmax": digits[:6],
                        "protocol": PROTOCOL_FIXED}

        except Exception as e:
            logger.debug(f"Probe of {port} at {baud} failed: {e}")
        finally:
            try:
                handle.close()
            except Exception:
                pass

    return None


def _device_type_for(model: Optional[BKModel]) -> DeviceType:
    if not model:
        return DeviceType.UNKNOWN
    equipment_type = CATEGORY_TO_EQUIPMENT_TYPE.get(model.category)
    return DeviceType(equipment_type) if equipment_type else DeviceType.UNKNOWN


def _device_from_probe(result: Dict) -> Optional[DiscoveredDevice]:
    """Turn a probe result into a DiscoveredDevice, or None if it is not B&K."""
    port = result["port"]
    resource_name = f"ASRL{port}::INSTR"
    device = DiscoveredDevice(
        device_id=f"bkserial_{port.replace('/', '_').lower()}",
        resource_name=resource_name,
        discovery_method=DiscoveryMethod.USB,
        status=ConnectionStatus.AVAILABLE,
    )
    device.metadata["serial_port"] = port
    device.metadata["baudrate"] = result["baudrate"]

    if result["protocol"] == "scpi":
        parts = [p.strip() for p in result["idn"].split(",")]
        if not is_bk_manufacturer(parts[0] if parts else None):
            return None  # Someone else's instrument on this port
        device.manufacturer = MANUFACTURER
        device.metadata["reported_manufacturer"] = parts[0]
        device.model = parts[1] if len(parts) > 1 else None
        device.serial_number = parts[2] if len(parts) > 2 else None
        device.firmware_version = parts[3] if len(parts) > 3 else None
        device.metadata["raw_idn"] = result["idn"]
        bk_model = resolve_model(device.model)
        device.confidence_score = 0.95 if bk_model else 0.8
    else:
        # A GMAX reply is proof of the legacy protocol but not of which model:
        # every supply in the family answers it. The rated limits it returns
        # are the useful part, and they narrow the field for the operator.
        digits = result["gmax"]
        max_voltage = int(digits[:3]) / 10.0
        max_current = int(digits[3:6]) / 10.0
        device.manufacturer = MANUFACTURER
        device.model = "Legacy fixed-width supply"
        device.device_type = DeviceType.POWER_SUPPLY
        device.metadata.update({
            "protocol": PROTOCOL_FIXED,
            "max_voltage": max_voltage,
            "max_current": max_current,
            "gmax": digits,
            "note": "Answered GMAX but not *IDN?. This is a 1685B/1687B/"
                    "1688B, 1900B/1901B/1902B, 1696/1697/1698 or 9103/9104; "
                    "the protocol carries no model number, so pick the exact "
                    "model when connecting — the current field scaling and "
                    "the SOUT polarity differ between them",
        })
        device.confidence_score = 0.6
        device.capabilities = ["RS-232", "USB-CDC"]
        return device

    bk_model = resolve_model(device.model)
    device.device_type = _device_type_for(bk_model)
    if bk_model:
        device.metadata.update({
            "bk_family": bk_model.key,
            "bk_family_name": bk_model.name,
            "bk_category": CATEGORY_LABELS.get(bk_model.category,
                                               bk_model.category),
            "protocol": bk_model.protocol,
            "usb_mode": bk_model.usb,
            "interfaces": bk_model.interfaces,
            "driver_supported": is_drivable(bk_model),
        })
        if bk_model.notes:
            device.metadata["notes"] = bk_model.notes
        device.capabilities = bk_model.interfaces
    return device


async def probe_serial_ports(
    ports: Optional[List[str]] = None,
    bauds=DEFAULT_BAUDS,
    timeout: float = PROBE_TIMEOUT,
    max_concurrency: int = 4,
    usb_only: bool = True,
) -> List[DiscoveredDevice]:
    """Find B&K instruments on serial and USB-CDC ports.

    Ports are probed concurrently, but each port is held by exactly one probe
    at a time — two probes on the same port would read each other's replies.
    """
    ports = ports if ports is not None else find_serial_ports(usb_only=usb_only)
    if not ports:
        logger.debug("No serial ports to probe for B&K instruments")
        return []

    logger.info(f"Probing {len(ports)} serial port(s) for B&K instruments")
    semaphore = asyncio.Semaphore(max_concurrency)
    loop = asyncio.get_running_loop()

    async def probe(port: str) -> Optional[DiscoveredDevice]:
        async with semaphore:
            try:
                result = await loop.run_in_executor(
                    None, _probe_port_blocking, port, tuple(bauds), timeout
                )
            except Exception as e:
                logger.debug(f"Probe of {port} raised: {e}")
                return None
            if not result:
                return None
            device = _device_from_probe(result)
            if device:
                logger.info(
                    f"Found B&K {device.model} on {port} at "
                    f"{result['baudrate']} baud"
                )
            return device

    results = await asyncio.gather(*(probe(p) for p in ports))
    return [d for d in results if d is not None]
