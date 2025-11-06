"""Shared constants for LabLink."""

# API Configuration
DEFAULT_API_PORT = 8000
DEFAULT_WS_PORT = 8001

# Raspberry Pi MAC OUI prefixes
RASPBERRY_PI_OUI = [
    "B8:27:EB",  # Raspberry Pi Foundation
    "DC:A6:32",  # Raspberry Pi Trading Ltd
    "E4:5F:01",  # Raspberry Pi (Trading) Ltd
    "28:CD:C1",  # Raspberry Pi Trading Ltd
]

# Equipment Manufacturers
SUPPORTED_MANUFACTURERS = {
    "RIGOL": ["MSO2072A", "DS1054Z", "DS2000"],
    "BK_PRECISION": ["9206B", "9130B", "9131B", "1902B"],
}

# VISA Resource Patterns
VISA_USB_PATTERN = "USB?*INSTR"
VISA_SERIAL_PATTERN = "ASRL?*INSTR"
VISA_TCPIP_PATTERN = "TCPIP?*INSTR"

# Data Buffer Configuration
DEFAULT_BUFFER_SIZE = 1000
MAX_BUFFER_SIZE = 100000
MIN_STREAM_INTERVAL_MS = 10
MAX_STREAM_INTERVAL_MS = 10000

# File Formats
SUPPORTED_DATA_FORMATS = ["csv", "hdf5", "npy"]
DEFAULT_DATA_FORMAT = "hdf5"
