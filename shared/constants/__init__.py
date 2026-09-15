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
    "RIGOL": [
        "MSO2072A",
        "DS1054Z",
        "DS2000",
        "DS1102D",
        "DL3021A",
        "DM3058",
        "DM3058E",
        "DM3068",
        "DM858",
        "DL3031A",
        "DP800",
        "DP700",
        "DP900",
        "DP2000",
        "DHO800",
        "DHO1000",
        "DHO5000",
        "MHO900",
        "MSO5000",
        "MSO7000",
        "MSO8000",
        "DS8000-R",
        "DS4000",
        "DS6000",
        "DS70000",
        "DS1000Z-E",
        "DG800",
        "DG900",
        "DG1000Z",
        "DG2000",
        "DG4000",
        "DG5000",
        "DG800 Pro",
        "DG5000 Pro",
        "DG6000",
        "DSA800",
        "DSA1000",
        "RSA3000",
        "RSA5000",
        "RSA800",
        "RSA6000",
        "DSG800",
        "DSG3000",
        "DSG5000",
        "RSA3000N",
        "DNA6000",
        "M300",
    ],
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
