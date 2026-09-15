"""Catalogue of Rigol families LabLink can drive, for the models API/UI.

Built from the driver classes themselves: every class that declares
``MODEL_KEYWORDS`` (and the hand-registered legacy scope/load/DMM classes)
contributes one entry in the same shape as ``bk_registry.catalog()`` so the
connect dialog can list them next to the B&K families.
"""

import re
from typing import Dict, List, Optional

from shared.models.equipment import EquipmentType

MANUFACTURER = "Rigol"

# Human-readable family names and the keyword-less legacy classes.
_FAMILY_NAMES: Dict[str, str] = {
    "RigolDM3058": "DM3058 5½-digit multimeter",
    "RigolDM3058E": "DM3058E 5½-digit multimeter",
    "RigolDM3068": "DM3068 6½-digit multimeter",
    "RigolDM858": "DM858 5½-digit multimeter",
    "RigolDM858E": "DM858E 5½-digit multimeter",
    "RigolDL3021A": "DL3000 DC electronic load (DL3021/DL3021A)",
    "RigolDL3031A": "DL3000 DC electronic load (DL3031/DL3031A/DL3041)",
    "RigolDP800": "DP800 programmable DC power supply",
    "RigolDP700": "DP700 programmable DC power supply",
    "RigolDP900": "DP900 programmable DC power supply",
    "RigolDP2000": "DP2000 programmable DC power supply",
    "RigolDP1308A": "DP1308A programmable DC power supply",
    "RigolDP1116A": "DP1116A programmable DC power supply",
    "RigolMSO2072A": "MSO2000A / DS2000A oscilloscope",
    "RigolDS1104": "DS1000Z oscilloscope",
    "RigolDS1102D": "DS1000D/E oscilloscope",
    "RigolDS1000ZE": "DS1000Z-E oscilloscope",
    "RigolDHO800": "DHO800 / DHO900 oscilloscope",
    "RigolDHO1000": "DHO1000 / DHO4000 oscilloscope",
    "RigolDHO5000": "DHO5000 / MHO5000 oscilloscope",
    "RigolMHO900": "MHO900 / MHO98 / MHO2000 oscilloscope",
    "RigolMSO5000": "MSO5000 oscilloscope",
    "RigolMSO7000": "MSO7000 / DS7000 oscilloscope",
    "RigolMSO8000": "MSO8000 / MSO8000A oscilloscope",
    "RigolDS8000R": "DS8000-R oscilloscope",
    "RigolDS4000": "DS4000 / MSO4000 oscilloscope",
    "RigolDS6000": "DS6000 oscilloscope",
    "RigolDS70000": "DS70000 oscilloscope",
    "RigolDS80000": "DS80000 oscilloscope",
    "RigolDG800": "DG800 function/arbitrary waveform generator",
    "RigolDG900": "DG900 function/arbitrary waveform generator",
    "RigolDG1000Z": "DG1000Z function/arbitrary waveform generator",
    "RigolDG2000": "DG2000 function/arbitrary waveform generator",
    "RigolDG4000": "DG4000 function/arbitrary waveform generator",
    "RigolDG5000": "DG5000 function/arbitrary waveform generator",
    "RigolDG800Pro": "DG800 Pro / DG900 Pro function/arbitrary waveform generator",
    "RigolDG5000Pro": "DG5000 Pro function/arbitrary waveform generator",
    "RigolDG6000": "DG6000 function/arbitrary waveform generator",
    "RigolDSA800": "DSA700 / DSA800 spectrum analyzer",
    "RigolDSA1000": "DSA1000 spectrum analyzer",
    "RigolRSA3000": "RSA3000 real-time spectrum analyzer",
    "RigolRSA5000": "RSA5000 real-time spectrum analyzer",
    "RigolRSA800": "RSA800 real-time spectrum analyzer",
    "RigolRSA6000": "RSA6000 real-time spectrum analyzer",
    "RigolDSG800": "DSG800 RF signal generator",
    "RigolDSG3000": "DSG3000 / DSG3000B RF signal generator",
    "RigolDSG5000": "DSG5000 RF signal generator",
    "RigolRSAN": "RSA3000N / RSA5000N vector network analyzer",
    "RigolDNA6000": "DNA6000 vector network analyzer",
    "RigolM300": "M300 data acquisition / switch mainframe",
}

# Keywords for the hand-registered classes in manager._create_equipment_instance.
_LEGACY_KEYWORDS: Dict[str, List[str]] = {
    "RigolDM3068": ["DM3068"],
    "RigolDM3058E": ["DM3058E"],
    "RigolDM3058": ["DM3058"],
    "RigolMSO2072A": ["MSO2072A", "MSO2102A", "MSO2202A", "MSO2302A", "DS2072A", "DS2102A", "DS2202A", "DS2302A"],
    "RigolDS1104": ["DS1054Z", "DS1074Z", "DS1104Z"],
    "RigolDS1102D": ["DS1052D", "DS1102D", "DS1052E", "DS1102E"],
    "RigolDL3021A": ["DL3021", "DL3021A"],
}

_CATEGORY_LABELS = {
    "oscilloscope": "Oscilloscopes",
    "power_supply": "Power Supplies",
    "electronic_load": "Electronic Loads",
    "multimeter": "Multimeters",
    "function_generator": "Function Generators",
    "spectrum_analyzer": "Spectrum Analyzers",
    "rf_signal_generator": "RF Signal Generators",
    "vector_network_analyzer": "Vector Network Analyzers",
    "data_acquisition": "Data Acquisition",
}


def _equipment_type_of(cls) -> str:
    """Infer the equipment type from the class's id prefix / module name."""
    module = cls.__module__.rsplit(".", 1)[-1]
    mapping = {
        "rigol_multimeter": EquipmentType.MULTIMETER,
        "rigol_multimeter_dm858": EquipmentType.MULTIMETER,
        "rigol_electronic_load": EquipmentType.ELECTRONIC_LOAD,
        "rigol_power_supply": EquipmentType.POWER_SUPPLY,
        "rigol_scope": EquipmentType.OSCILLOSCOPE,
        "rigol_modern_scope": EquipmentType.OSCILLOSCOPE,
        "rigol_function_generator": EquipmentType.FUNCTION_GENERATOR,
        "rigol_spectrum_analyzer": EquipmentType.SPECTRUM_ANALYZER,
        "rigol_rf_generator": EquipmentType.RF_SIGNAL_GENERATOR,
        "rigol_vna": EquipmentType.VECTOR_NETWORK_ANALYZER,
        "rigol_daq": EquipmentType.DATA_ACQUISITION,
    }
    return mapping.get(module, EquipmentType.OSCILLOSCOPE).value


def _driver_classes():
    # Imported lazily: manager imports every driver module.
    from . import manager as _manager
    from .rigol_electronic_load import RigolDL3021A
    from .rigol_multimeter import RigolDM3058, RigolDM3058E, RigolDM3068
    from .rigol_scope import RigolDS1102D, RigolDS1104, RigolMSO2072A

    legacy = [RigolDM3068, RigolDM3058E, RigolDM3058, RigolMSO2072A, RigolDS1104,
              RigolDS1102D, RigolDL3021A]
    seen, out = set(), []
    for cls in list(_manager.KEYWORD_DRIVER_CLASSES) + legacy:
        if cls.__name__ in seen:
            continue
        seen.add(cls.__name__)
        out.append(cls)
    return out


_FAMILY_PREFIX = re.compile(r"^(?:DSG|DNA|DSA|RSA|DHO|MHO|MSO|DG|DS|DP|DL|DM)\d{0,2}$")


def _skus(cls) -> List[str]:
    """Concrete model numbers for a class, without bare family prefixes.

    ``MODEL_KEYWORDS`` also carries matching helpers such as ``"DSG3"`` and the
    ``"DG822PRO"`` / ``"DG822-PRO"`` spellings of a Pro model; the catalogue
    lists each model once, in its printed form.
    """
    keywords = list(getattr(cls, "MODEL_KEYWORDS", ())) or _LEGACY_KEYWORDS.get(cls.__name__, [])
    skus = []
    for k in keywords:
        k = str(k).strip()
        if _FAMILY_PREFIX.match(k.upper()):
            continue
        upper = k.upper()
        if upper.endswith("PRO") and not upper.endswith(" PRO"):
            continue  # "DG822PRO" / "DG822-PRO": keep only "DG822 Pro"
        skus.append(k.replace(" PRO", " Pro"))
    return list(dict.fromkeys(skus))


def catalog() -> List[dict]:
    """Serialisable catalogue of Rigol families with a LabLink driver."""
    entries = []
    for cls in _driver_classes():
        etype = _equipment_type_of(cls)
        interfaces = list(getattr(cls, "INTERFACES", ())) or ["USB", "LAN"]
        entries.append({
            "key": cls.__name__.replace("Rigol", ""),
            "name": _FAMILY_NAMES.get(cls.__name__, cls.__name__),
            "manufacturer": MANUFACTURER,
            "category": etype,
            "category_label": _CATEGORY_LABELS.get(etype, etype),
            "equipment_type": etype,
            "protocol": "scpi",
            "skus": _skus(cls),
            "usb_mode": "usbtmc",
            "interfaces": [i.replace("RS232", "RS-232") for i in interfaces],
            "default_baud": 9600,
            "selectable_bauds": [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200],
            "socket_ports": [5555],
            "channels": getattr(cls, "NUM_CHANNELS", None),
            "max_voltage": None,
            "max_current": None,
            "supports_idn": True,
            "supported": True,
            "driver": cls.__name__,
            "notes": f"Driver {cls.__module__}.{cls.__name__}; see docs/RIGOL_EQUIPMENT_CATALOG.md",
        })
    return entries


def resolve_model(model: str) -> Optional[dict]:
    """Find the catalogue entry whose SKUs match a reported model string."""
    m = (model or "").upper().replace("RIGOL TECHNOLOGIES", "").replace("RIGOL", "").strip(" ,")
    for entry in catalog():
        for sku in entry["skus"]:
            if sku.upper().replace(" ", "") in m.replace(" ", ""):
                return entry
    return None


def category_labels() -> Dict[str, str]:
    return dict(_CATEGORY_LABELS)
