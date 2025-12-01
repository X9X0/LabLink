"""USB Hardware ID Database for automatic device identification.

This database maps USB Vendor ID (VID) and Product ID (PID) to equipment
information, allowing automatic device identification even when *IDN? queries fail.
"""

from typing import Optional

from .models import DeviceType


class USBDeviceInfo:
    """USB device information."""

    def __init__(
        self,
        vid: str,
        pid: str,
        manufacturer: str,
        model: str,
        device_type: DeviceType,
        description: str = "",
        max_voltage: Optional[float] = None,
        max_current: Optional[float] = None,
    ):
        """Initialize USB device info.

        Args:
            vid: USB Vendor ID (hex string, e.g., "2ec7")
            pid: USB Product ID (hex string, e.g., "9200")
            manufacturer: Manufacturer name
            model: Model number/name
            device_type: Type of equipment
            description: Additional description
            max_voltage: Maximum voltage (for power supplies)
            max_current: Maximum current (for power supplies/loads)
        """
        self.vid = vid.lower()
        self.pid = pid.lower()
        self.manufacturer = manufacturer
        self.model = model
        self.device_type = device_type
        self.description = description
        self.max_voltage = max_voltage
        self.max_current = max_current

    def __repr__(self):
        return f"USBDeviceInfo({self.vid}:{self.pid}, {self.manufacturer} {self.model})"


# USB Hardware Database
# Format: (VID, PID): USBDeviceInfo
USB_HARDWARE_DB = {
    # B&K Precision Power Supplies
    ("2ec7", "9200"): USBDeviceInfo(
        vid="2ec7",
        pid="9200",
        manufacturer="B&K Precision",
        model="9205B",
        device_type=DeviceType.POWER_SUPPLY,
        description="Multi-range DC power supply, 120V/5A or 60V/10A",
        max_voltage=120.0,
        max_current=10.0,
    ),
    ("2ec7", "9206"): USBDeviceInfo(
        vid="2ec7",
        pid="9206",
        manufacturer="B&K Precision",
        model="9206B",
        device_type=DeviceType.POWER_SUPPLY,
        description="Multi-range DC power supply, 60V/10A or 120V/5A",
        max_voltage=120.0,
        max_current=10.0,
    ),
    ("2ec7", "1685"): USBDeviceInfo(
        vid="2ec7",
        pid="1685",
        manufacturer="B&K Precision",
        model="1685B",
        device_type=DeviceType.POWER_SUPPLY,
        description="DC power supply, 18V/5A",
        max_voltage=18.0,
        max_current=5.0,
    ),
    ("2ec7", "9130"): USBDeviceInfo(
        vid="2ec7",
        pid="9130",
        manufacturer="B&K Precision",
        model="9130B",
        device_type=DeviceType.POWER_SUPPLY,
        description="Triple output DC power supply",
        max_voltage=30.0,
        max_current=3.0,
    ),
    ("2ec7", "1902"): USBDeviceInfo(
        vid="2ec7",
        pid="1902",
        manufacturer="B&K Precision",
        model="1902B",
        device_type=DeviceType.ELECTRONIC_LOAD,
        description="Programmable DC electronic load",
        max_voltage=150.0,
        max_current=30.0,
    ),
    # Rigol Oscilloscopes
    ("1ab1", "04ce"): USBDeviceInfo(
        vid="1ab1",
        pid="04ce",
        manufacturer="Rigol",
        model="DS1000Z",
        device_type=DeviceType.OSCILLOSCOPE,
        description="Digital oscilloscope, DS1000Z series",
    ),
    ("1ab1", "04b0"): USBDeviceInfo(
        vid="1ab1",
        pid="04b0",
        manufacturer="Rigol",
        model="MSO2072A",
        device_type=DeviceType.OSCILLOSCOPE,
        description="Mixed signal oscilloscope, 70 MHz, 2 channels",
    ),
    ("1ab1", "0588"): USBDeviceInfo(
        vid="1ab1",
        pid="0588",
        manufacturer="Rigol",
        model="DS1102D",
        device_type=DeviceType.OSCILLOSCOPE,
        description="Digital oscilloscope, 100 MHz, 2 channels",
    ),
    # Rigol Function Generators
    ("1ab1", "0640"): USBDeviceInfo(
        vid="1ab1",
        pid="0640",
        manufacturer="Rigol",
        model="DG4000",
        device_type=DeviceType.FUNCTION_GENERATOR,
        description="Arbitrary waveform generator",
    ),
    # Rigol Electronic Loads
    ("1ab1", "0e11"): USBDeviceInfo(
        vid="1ab1",
        pid="0e11",
        manufacturer="Rigol",
        model="DL3021A",
        device_type=DeviceType.ELECTRONIC_LOAD,
        description="DC electronic load, 200W",
        max_voltage=150.0,
        max_current=40.0,
    ),
    # Keysight/Agilent
    ("0957", "0588"): USBDeviceInfo(
        vid="0957",
        pid="0588",
        manufacturer="Keysight",
        model="34450A",
        device_type=DeviceType.MULTIMETER,
        description="5.5 digit multimeter",
    ),
    ("0957", "1f07"): USBDeviceInfo(
        vid="0957",
        pid="1f07",
        manufacturer="Keysight",
        model="MSO-X 3000",
        device_type=DeviceType.OSCILLOSCOPE,
        description="Mixed signal oscilloscope, 3000 X-Series",
    ),
    # Silicon Labs CP210x UART Bridge (common USB-to-Serial chip)
    # These are harder to identify automatically as they're used in many devices
    ("10c4", "ea60"): USBDeviceInfo(
        vid="10c4",
        pid="ea60",
        manufacturer="Silicon Labs",
        model="CP210x UART Bridge",
        device_type=DeviceType.UNKNOWN,
        description="USB-to-Serial converter (used in various equipment)",
    ),
    # FTDI USB-to-Serial (also very common)
    ("0403", "6001"): USBDeviceInfo(
        vid="0403",
        pid="6001",
        manufacturer="FTDI",
        model="FT232 USB-UART",
        device_type=DeviceType.UNKNOWN,
        description="USB-to-Serial converter (used in various equipment)",
    ),
}


def lookup_usb_device(vid: str, pid: str) -> Optional[USBDeviceInfo]:
    """Look up USB device by VID:PID.

    Args:
        vid: USB Vendor ID (hex string, case insensitive)
        pid: USB Product ID (hex string, case insensitive)

    Returns:
        USBDeviceInfo if found, None otherwise
    """
    key = (vid.lower(), pid.lower())
    return USB_HARDWARE_DB.get(key)


def extract_usb_ids_from_resource(resource_name: str) -> Optional[tuple[str, str]]:
    """Extract VID:PID from VISA USB resource string.

    Args:
        resource_name: VISA resource name (e.g., "USB0::0x2ec7::0x9200::SERIAL::INSTR")

    Returns:
        Tuple of (vid, pid) without 0x prefix, or None if not a USB resource
    """
    if not resource_name.startswith("USB"):
        return None

    import re

    # Match USB resource format: USB[board]::VID::PID::serial[::INSTR]
    # VID and PID can be decimal or hex (0x prefix)
    pattern = r"USB\d*::(0x)?([0-9a-fA-F]+)::(0x)?([0-9a-fA-F]+)"
    match = re.match(pattern, resource_name)

    if match:
        vid = match.group(2)  # Group 2 is VID without 0x
        pid = match.group(4)  # Group 4 is PID without 0x
        return (vid.lower(), pid.lower())

    return None


def get_device_info_from_resource(resource_name: str) -> Optional[USBDeviceInfo]:
    """Get device info from VISA resource string.

    Args:
        resource_name: VISA resource name

    Returns:
        USBDeviceInfo if found in database, None otherwise
    """
    usb_ids = extract_usb_ids_from_resource(resource_name)
    if not usb_ids:
        return None

    vid, pid = usb_ids
    return lookup_usb_device(vid, pid)
