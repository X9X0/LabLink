"""Vendor model-number knowledge used to classify discovered instruments.

The generic keyword matching in the scanners is loose ("ds" matches DSA/DSG
spectrum instruments, "dho"/"mho" matches nothing). This module holds an
explicit, prefix-anchored table built from the vendor download catalogue
(see docs/RIGOL_EQUIPMENT_CATALOG.md) so a model string classifies
correctly before the keyword fallback runs.
"""

import re
from typing import Optional

from .models import DeviceType

# Order matters: longer / more specific prefixes first.
RIGOL_MODEL_FAMILIES = [
    # Digital multimeters
    (r"DM3\d{3}", DeviceType.MULTIMETER),
    (r"DM8\d{2}", DeviceType.MULTIMETER),
    # Spectrum / real-time / vector network analyzers (before DS* scopes)
    (r"DSA\d{3,4}", DeviceType.SPECTRUM_ANALYZER),
    (r"RSA\d{4}N", DeviceType.VECTOR_NETWORK_ANALYZER),  # RSA3000N/RSA5000N VNA variants
    (r"RSA\d{3,4}", DeviceType.SPECTRUM_ANALYZER),
    (r"DNA\d{3,4}", DeviceType.VECTOR_NETWORK_ANALYZER),
    # RF signal generators (before DS* scopes)
    (r"DSG\d{3,4}", DeviceType.RF_SIGNAL_GENERATOR),
    # Arbitrary / function generators
    (r"DG\d{3,5}", DeviceType.FUNCTION_GENERATOR),
    # Oscilloscopes
    (r"(?:MSO|DS|DHO|MHO)\d{2,5}", DeviceType.OSCILLOSCOPE),
    # Programmable DC power supplies
    (r"DP\d{3,4}", DeviceType.POWER_SUPPLY),
    # DC electronic loads
    (r"DL\d{4}", DeviceType.ELECTRONIC_LOAD),
    # Data acquisition / switch mainframe
    (r"M300", DeviceType.DATA_ACQUISITION),
]

_RIGOL_MANUFACTURER = re.compile(r"rigol", re.I)


def infer_rigol_device_type(
    model: Optional[str], manufacturer: Optional[str] = None
) -> Optional[DeviceType]:
    """Classify a Rigol model number; returns None if not recognised.

    ``manufacturer`` is optional: Rigol model prefixes are distinctive enough
    to match on their own, but when a manufacturer is given and it is clearly
    not Rigol, None is returned so other vendors' rules can apply.
    """
    if not model:
        return None
    if manufacturer and manufacturer.strip() and not _RIGOL_MANUFACTURER.search(manufacturer):
        return None
    m = model.strip().upper()
    # Strip a leading vendor word, e.g. "Rigol DS1054Z"
    m = re.sub(r"^RIGOL(?:\s+TECHNOLOGIES)?[\s,]*", "", m)
    for pattern, dtype in RIGOL_MODEL_FAMILIES:
        if re.match(pattern, m):
            return dtype
    return None
