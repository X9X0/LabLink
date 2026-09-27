"""Siglent model registry.

Identification for Siglent's catalogue, and the protocol facts a driver
needs before it opens a connection.

Three things about Siglent make this worth a module rather than a
handful of substring tests:

1. **Siglent speaks two languages, not one.** The supplies, loads and
   multimeters (SPD, SDL, SDM) are conventional SCPI: mixed-case
   keywords where the uppercase run is the legal abbreviation, exactly
   as IEEE 488.2 intends. The oscilloscopes and generators (SDS, SDG)
   are not. They use Siglent's own paired short and long forms --
   ``BSWV`` for ``BASIC_WAVE``, ``C1:BSWV WVTP,SINE`` -- published as
   an explicit per-command table and not derivable from capitalisation.
   Assuming either dialect against the other family fails. See
   :data:`PROTOCOL_SCPI` and :data:`PROTOCOL_SIGLENT_SHORT`.

2. **The model field is a SKU, and the suffix changes the instrument.**
   SPD3303X and SPD3303X-E are different products sharing a command
   set; SDS1104X-E and SDS1104X-U are different command sets. A
   registry keyed on families, with the SKU resolved back to one,
   is the only way a suffix cannot be quietly ignored.

3. **The catalogue is larger than anyone's driver collection, and it
   grows.** Rather than answer "unknown" for every model nobody has
   written an entry for, :func:`resolve_model` falls back to Siglent's
   own prefix scheme -- SPD is a supply, SDL is a load, SDM is a
   meter -- so an instrument from a family this file has never heard
   of is still identified as the right *kind* of instrument. It will
   not be marked drivable; being able to say "that is a Siglent
   spectrum analyser we have no driver for" is the point.

Verified on the bench where it says so. Everything else is catalogued
from Siglent's published model line and should be treated as
identification only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Protocol dialects
# ---------------------------------------------------------------------------

#: Conventional SCPI. Mixed-case keywords, the uppercase run is the legal
#: abbreviation, and anything else is an "Undefined header". The SPD, SDL
#: and SDM lines are this.
PROTOCOL_SCPI = "scpi"

#: Siglent's own short/long pairs, published per command rather than
#: derived from capitalisation: BSWV <-> BASIC_WAVE, WVTP, C1:. The SDS
#: and SDG lines are this. The uppercase-run rule does not apply and
#: guessing an abbreviation from the spelling will not work.
PROTOCOL_SIGLENT_SHORT = "siglent_short"

# Connection kinds
USB_TMC = "tmc"       # USB Test & Measurement Class, opened through VISA
USB_CDC = "cdc"       # USB-to-UART bridge, opened as a serial port

#: Raw-socket port Siglent documents for LAN instruments.
SCPI_RAW_PORT = 5025

MANUFACTURER = "Siglent Technologies"


@dataclass(frozen=True)
class SiglentModel:
    """Interface and protocol facts for one Siglent family."""

    key: str                        # canonical family key, e.g. "SPD3000X"
    name: str                       # human label
    category: str                   # see CATEGORY_TO_EQUIPMENT_TYPE
    protocol: str = PROTOCOL_SCPI
    skus: Tuple[str, ...] = ()      # SKUs known to be in this family
    usb: Optional[str] = USB_TMC
    lan: bool = False
    channels: int = 1
    max_voltage: Optional[float] = None
    max_current: Optional[float] = None
    #: True only where a driver in this tree has been run against the
    #: real command set. Catalogued-but-unverified is the default.
    verified: bool = False
    notes: str = ""

    @property
    def interfaces(self) -> List[str]:
        out: List[str] = []
        if self.usb == USB_TMC:
            out.append("USBTMC")
        elif self.usb == USB_CDC:
            out.append("USB-CDC")
        if self.lan:
            out.append("LAN")
        return out


# ---------------------------------------------------------------------------
# Category mapping
# ---------------------------------------------------------------------------

#: Siglent category -> LabLink EquipmentType value. A category absent from
#: this map is identified but cannot be connected: there is no LabLink
#: equipment type for it.
CATEGORY_TO_EQUIPMENT_TYPE: Dict[str, str] = {
    "psu": "power_supply",
    "load": "electronic_load",
    "dmm": "multimeter",
    "scope": "oscilloscope",
    "awg": "function_generator",
    "spectrum": "spectrum_analyzer",
    "vna": "vector_network_analyzer",
}

CATEGORY_LABELS: Dict[str, str] = {
    "psu": "Power Supply",
    "load": "DC Electronic Load",
    "dmm": "Multimeter",
    "scope": "Oscilloscope",
    "awg": "Waveform Generator",
    "spectrum": "Spectrum Analyzer",
    "vna": "Network Analyzer",
    "rf_source": "RF Signal Generator",
}

# ---------------------------------------------------------------------------
# Prefix scheme
# ---------------------------------------------------------------------------

#: Siglent numbers its catalogue systematically, and the leading letters
#: say what an instrument is. This is the fallback that lets a model no
#: entry below has ever named still be identified as the right kind of
#: instrument -- longest prefix first, so SPD beats SP.
PREFIX_CATEGORIES: Tuple[Tuple[str, str, str], ...] = (
    ("SPD", "psu", PROTOCOL_SCPI),
    ("SPS", "psu", PROTOCOL_SCPI),
    ("SPE", "psu", PROTOCOL_SCPI),
    ("SDL", "load", PROTOCOL_SCPI),
    ("SDM", "dmm", PROTOCOL_SCPI),
    ("SDS", "scope", PROTOCOL_SIGLENT_SHORT),
    ("SHS", "scope", PROTOCOL_SIGLENT_SHORT),
    ("SDG", "awg", PROTOCOL_SIGLENT_SHORT),
    ("SSA", "spectrum", PROTOCOL_SCPI),
    ("SVA", "vna", PROTOCOL_SCPI),
    ("SNA", "vna", PROTOCOL_SCPI),
    ("SSG", "rf_source", PROTOCOL_SCPI),
)

# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

MODELS: Dict[str, SiglentModel] = {}


def _add(key: str, name: str, category: str, **kw) -> None:
    MODELS[key] = SiglentModel(key=key, name=name, category=category, **kw)


# --- Power supplies --------------------------------------------------------
# SPD3303X-E verified on the bench at 192.168.91.191 (USB f4ec:1430),
# *IDN? "Siglent Technologies,SPD3303X-E,SPD3XJGCA01014,
# 1.01.01.03.12R1 V6.2". Command set from the SPD3000X Quick Start
# (E02A), which is where Siglent publishes it -- there is no separate
# SPD programming guide.
_add("SPD3000X", "SPD3000X Series", "psu",
     skus=("SPD3303X", "SPD3303X-E", "SPD3303C"),
     lan=True, channels=3, max_voltage=32.0, max_current=3.2,
     verified=True,
     notes="CH1 and CH2 are 0-32 V / 0-3.2 A and programmable; CH3 is a "
           "fixed 2.5/3.3/5 V rail selected by a front-panel switch and "
           "can only be switched on and off. MEASure and the channel "
           "prefix accept CH1 and CH2 only")
_add("SPD1000X", "SPD1000X Series", "psu",
     skus=("SPD1168X", "SPD1305X"),
     lan=True, channels=1,
     notes="Single channel; shares the SPD3000X command set without the "
           "channel prefix")
_add("SPS5000X", "SPS5000X Series", "psu", lan=True, channels=1,
     notes="Wide-range programmable supply")

# --- Electronic loads ------------------------------------------------------
_add("SDL1000X", "SDL1000X Series", "load",
     skus=("SDL1020X", "SDL1030X", "SDL1020X-E", "SDL1030X-E"),
     lan=True, channels=1)

# --- Multimeters -----------------------------------------------------------
_add("SDM3000", "SDM3000 Series", "dmm",
     skus=("SDM3045X", "SDM3055", "SDM3055A", "SDM3065X"),
     lan=True)

# --- Oscilloscopes ---------------------------------------------------------
_add("SDS1000X-E", "SDS1000X-E Series", "scope",
     protocol=PROTOCOL_SIGLENT_SHORT,
     skus=("SDS1202X-E", "SDS1104X-E", "SDS1204X-E"), lan=True, channels=4)
_add("SDS2000X", "SDS2000X / X-E / Plus Series", "scope",
     protocol=PROTOCOL_SIGLENT_SHORT, lan=True, channels=4)
_add("SDS_HD", "SDS X HD Series", "scope",
     protocol=PROTOCOL_SIGLENT_SHORT,
     skus=("SDS800X HD", "SDS1000X HD", "SDS2000X HD", "SDS3000X HD"),
     lan=True, channels=4)
_add("SDS5000X", "SDS5000X Series", "scope",
     protocol=PROTOCOL_SIGLENT_SHORT, lan=True, channels=4)
_add("SDS6000", "SDS6000A / Pro Series", "scope",
     protocol=PROTOCOL_SIGLENT_SHORT, lan=True, channels=4)
_add("SHS800X", "SHS800X / SHS1000X Handheld", "scope",
     protocol=PROTOCOL_SIGLENT_SHORT, channels=2)

# --- Generators ------------------------------------------------------------
_add("SDG1000X", "SDG1000X Series", "awg",
     protocol=PROTOCOL_SIGLENT_SHORT, lan=True, channels=2)
_add("SDG2000X", "SDG2000X Series", "awg",
     protocol=PROTOCOL_SIGLENT_SHORT, lan=True, channels=2)
_add("SDG6000X", "SDG6000X Series", "awg",
     protocol=PROTOCOL_SIGLENT_SHORT, lan=True, channels=2)
_add("SDG800", "SDG800 / SDG1000 Series", "awg",
     protocol=PROTOCOL_SIGLENT_SHORT, channels=2)

# --- Spectrum and network analysers ---------------------------------------
_add("SSA3000X", "SSA3000X / X-E / Plus Series", "spectrum", lan=True)
_add("SSA5000A", "SSA5000A Series", "spectrum", lan=True)
_add("SVA1000X", "SVA1000X Series", "vna", lan=True)
_add("SNA5000A", "SNA5000A Series", "vna", lan=True)
_add("SSG3000X", "SSG3000X / SSG5000X Series", "rf_source", lan=True)


# ---------------------------------------------------------------------------
# Identification
# ---------------------------------------------------------------------------

def _squash(text: str) -> str:
    """Upper-case, with every separator removed.

    Lets "Siglent Technologies Co., Ltd" and "SIGLENT TECHNOLOGIES"
    compare equal, and "SDS800X HD" match "SDS800XHD".
    """
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


#: Every spelling of the vendor seen in an *IDN? reply or on a USB
#: descriptor. "Atten" is there because Siglent's USB vendor id
#: (0xF4EC) is still registered to Atten Electronics, so that is what
#: lsusb and some VISA layers report.
_MANUFACTURER_MARKERS = ("SIGLENT", "ATTEN")


def is_siglent_manufacturer(manufacturer: Optional[str]) -> bool:
    """Whether an *IDN? manufacturer field names Siglent."""
    squashed = _squash(manufacturer)
    return any(marker in squashed for marker in _MANUFACTURER_MARKERS)


def _prefix_match(candidate: str) -> Optional[SiglentModel]:
    """Identify by Siglent's prefix scheme when no entry names the SKU.

    Produces a synthetic family so an instrument nobody has catalogued
    is still reported as the right kind of instrument, with the right
    dialect. Never verified, so never drivable.
    """
    for prefix, category, protocol in sorted(
        PREFIX_CATEGORIES, key=lambda p: -len(p[0])
    ):
        if candidate.startswith(prefix):
            return SiglentModel(
                key=candidate, name=candidate, category=category,
                protocol=protocol, skus=(candidate,),
                notes="Identified from the model prefix; no catalogue entry "
                      "names this SKU, so its command set is unconfirmed")
    return None


def resolve_model(model: Optional[str]) -> Optional[SiglentModel]:
    """Resolve a model string to a family.

    Tries, in order: an exact family key, a SKU named by some family,
    a squashed comparison so spacing and hyphens cannot matter, then
    the prefix scheme.
    """
    if not model:
        return None
    candidate = model.strip().upper()
    if not candidate:
        return None

    if candidate in MODELS:
        return MODELS[candidate]

    squashed = _squash(candidate)
    for entry in MODELS.values():
        for sku in entry.skus:
            if _squash(sku) == squashed:
                return entry
    for key, entry in MODELS.items():
        if _squash(key) == squashed:
            return entry

    # A longer SKU inside a known family: SPD3303X-E-something. Longest
    # SKU first, so a more specific one is never shadowed by a prefix
    # of itself.
    for entry in sorted(MODELS.values(),
                        key=lambda m: -max((len(s) for s in m.skus), default=0)):
        for sku in sorted(entry.skus, key=len, reverse=True):
            if squashed.startswith(_squash(sku)):
                return entry

    return _prefix_match(squashed)


def resolve_idn(
    idn: Optional[str],
) -> Tuple[Dict[str, Optional[str]], Optional[SiglentModel]]:
    """Parse an ``*IDN?`` reply and resolve its model.

    Returns the parsed fields plus the family, or None for the family
    when the reply is not Siglent's.

    The firmware field is left as the instrument gave it. The SPD3303X-E
    answers "1.01.01.03.12R1 V6.2" in one comma-delimited field --
    software and hardware version together, space separated -- which is
    not what the other three fields do and is not worth pretending is
    tidy.
    """
    fields: Dict[str, Optional[str]] = {
        "manufacturer": None, "model": None,
        "serial_number": None, "firmware_version": None,
        "raw_idn": idn,
    }
    if not idn:
        return fields, None

    parts = [p.strip() for p in idn.split(",")]
    for name, value in zip(
        ("manufacturer", "model", "serial_number", "firmware_version"), parts
    ):
        fields[name] = value or None

    # USB descriptors on these instruments are NUL padded, and the
    # padding survives into the resource string and sometimes into the
    # serial field. Seen on the bench: the SPD3303X-E enumerates as
    # USB0::62700::5168::SPD3XJGCA01014\x00\x00\x00\x00::0::INSTR.
    for name in ("serial_number", "model", "manufacturer"):
        if fields[name]:
            fields[name] = fields[name].replace("\x00", "").strip() or None

    if not is_siglent_manufacturer(fields["manufacturer"]):
        return fields, None
    return fields, resolve_model(fields["model"])


# ---------------------------------------------------------------------------
# Lookups used by discovery, the manager and the API
# ---------------------------------------------------------------------------

def equipment_type_for(model: SiglentModel) -> Optional[str]:
    """LabLink EquipmentType value for a family, or None if unsupported."""
    return CATEGORY_TO_EQUIPMENT_TYPE.get(model.category)


#: Families LabLink ships a driver for. Everything else in this file is
#: catalogued so it can be named, not driven.
DRIVEN_FAMILIES = frozenset({"SPD3000X", "SPD1000X"})


def is_drivable(model: SiglentModel) -> bool:
    """Whether LabLink has a driver that can talk to this family."""
    return model.key in DRIVEN_FAMILIES


def why_not_drivable(model: SiglentModel) -> str:
    """A sentence saying what is missing, for the operator.

    Discovery that says only "unsupported" sends somebody looking for a
    cable fault.
    """
    if is_drivable(model):
        return ""
    if model.protocol == PROTOCOL_SIGLENT_SHORT:
        return (
            f"{model.name} speaks Siglent's short-form protocol (BSWV for "
            f"BASIC_WAVE), which LabLink has no driver for. It is identified "
            f"but cannot be connected."
        )
    if equipment_type_for(model) is None:
        label = CATEGORY_LABELS.get(model.category, model.category)
        return (
            f"{model.name} is a {label}; LabLink has no equipment type for "
            f"one, so it cannot be connected."
        )
    return (
        f"{model.name} is identified, but LabLink has no Siglent driver for "
        f"it yet."
    )


def models_by_category(category: Optional[str] = None) -> List[SiglentModel]:
    entries = list(MODELS.values())
    if category:
        entries = [m for m in entries if m.category == category]
    return sorted(entries, key=lambda m: m.key)


def catalog() -> List[dict]:
    """The registry as plain dicts, for the API."""
    return [
        {
            "key": m.key,
            "name": m.name,
            "category": m.category,
            "category_label": CATEGORY_LABELS.get(m.category, m.category),
            "protocol": m.protocol,
            "skus": list(m.skus),
            "interfaces": m.interfaces,
            "channels": m.channels,
            "equipment_type": equipment_type_for(m),
            "drivable": is_drivable(m),
            "verified": m.verified,
            "notes": m.notes,
        }
        for m in models_by_category()
    ]
