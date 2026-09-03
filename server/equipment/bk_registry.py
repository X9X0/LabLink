"""B&K Precision model registry.

Interface and protocol facts for every model family B&K publishes an English
programming manual for (64 families, ~130 SKUs). Sourced from those manuals.

Three things make B&K hardware hard to auto-detect, and this module exists to
handle all three:

1. **The manufacturer field is not one string.** Across the published manuals
   ``*IDN?`` returns ``B&K Precision``, ``B&KPrecision``, ``B&KPRECISION``,
   ``BK Precision``, ``B&K PRECISION`` or bare ``BK``. Matching on any one
   spelling misses most of the line — see :func:`is_bk_manufacturer`.

2. **The model field is a SKU, not a family.** A 9241 is a 9240-series supply,
   a 2569B-MSO is a 2560B scope, a MR40003 is an MR supply. The programming
   manuals are written per family, so a SKU has to be resolved back to one
   before its command set is known — see :func:`resolve_model`.

3. **USB means two incompatible things.** Some models are USBTMC (a real
   Test & Measurement Class device, reachable through VISA); others are
   USB-CDC, a USB-to-UART bridge that enumerates as ``/dev/ttyUSB0`` and needs
   a baud rate. VISA never enumerates the second kind, which is the single
   most common reason a connected B&K instrument appears to be missing. The
   ``usb`` field records which one a model is.

There are also three protocol families, not one. Assuming SCPI against a
``fixed`` model fails silently: the instrument ignores the command and there is
no error queue to ask.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Protocol families
# ---------------------------------------------------------------------------

PROTOCOL_SCPI = "scpi"        # IEEE 488.2 / SCPI, *IDN? works
PROTOCOL_SIGLENT = "siglent"  # comma-delimited "C1:BSWV WVTP,SINE" style
PROTOCOL_FIXED = "fixed"      # fixed-width ASCII, CR terminated, no *IDN?
PROTOCOL_PROPRIETARY = "proprietary"  # *IDN? works, but the subsystem
                                      # commands are vendor-specific, not SCPI

# USB modes
USB_TMC = "tmc"  # USB Test & Measurement Class -> open through VISA
USB_CDC = "cdc"  # USB-to-UART bridge -> open as a serial port at `baud`

#: Baud rates offered by most models with a selectable serial rate.
STD_BAUDS: Tuple[int, ...] = (4800, 9600, 19200, 38400, 57600, 115200)

#: Default raw-socket (SCPI-RAW) port used when a model documents no other.
SCPI_RAW_PORT = 5025


@dataclass(frozen=True)
class BKModel:
    """Interface and protocol facts for one B&K model family."""

    key: str                            # canonical family key, e.g. "9140"
    name: str                           # human label, e.g. "9140 Series"
    category: str                       # see CATEGORY_TO_EQUIPMENT_TYPE
    protocol: str = PROTOCOL_SCPI
    skus: Tuple[str, ...] = ()          # documented SKUs in this family
    usb: Optional[str] = None           # USB_TMC | USB_CDC | None
    baud: int = 9600                    # default serial / USB-CDC rate
    bauds: Tuple[int, ...] = ()         # selectable rates, empty if fixed
    lan: bool = False
    gpib: bool = False
    rs232: bool = False
    rs485: bool = False
    ports: Tuple[int, ...] = ()         # documented raw-socket ports
    channels: int = 1
    max_voltage: Optional[float] = None
    max_current: Optional[float] = None
    # Fixed-width protocol dialect (see bk_power_supply.FixedWidthDialect)
    dialect: Optional[str] = None
    notes: str = ""

    @property
    def interfaces(self) -> List[str]:
        """Human-readable interface list, in bring-up order."""
        out: List[str] = []
        if self.rs232:
            out.append("RS-232")
        if self.rs485:
            out.append("RS-485")
        if self.usb == USB_TMC:
            out.append("USBTMC")
        elif self.usb == USB_CDC:
            out.append("USB-CDC")
        if self.gpib:
            out.append("GPIB")
        if self.lan:
            out.append("LAN")
        return out

    @property
    def socket_port(self) -> int:
        """Preferred raw-socket port for LAN models."""
        return self.ports[0] if self.ports else SCPI_RAW_PORT

    @property
    def supports_idn(self) -> bool:
        """Whether ``*IDN?`` is answered.

        The fixed-width families have no query syntax at all, so discovery has
        to fall back to a protocol-specific probe (``GETD``/``GMAX``).
        """
        return self.protocol != PROTOCOL_FIXED


# ---------------------------------------------------------------------------
# Category mapping
# ---------------------------------------------------------------------------

#: B&K category -> LabLink EquipmentType value. Categories absent from this
#: map are catalogued and identified during discovery but have no driver, so
#: they cannot be connected: LabLink has no equipment type for a data recorder
#: or an LCR meter.
CATEGORY_TO_EQUIPMENT_TYPE: Dict[str, str] = {
    "psu": "power_supply",
    "battery_sim": "power_supply",  # BCS sources and sinks; a supply in practice
    "load": "electronic_load",
    "dmm": "multimeter",
    "scope": "oscilloscope",
    "awg": "function_generator",
}

CATEGORY_LABELS: Dict[str, str] = {
    "psu": "Power Supply",
    "load": "DC Electronic Load",
    "dmm": "Multimeter",
    "scope": "Oscilloscope",
    "awg": "Waveform Generator",
    "counter": "Frequency Counter",
    "lcr": "LCR Meter",
    "battery": "Battery Analyzer",
    "battery_sim": "Battery Simulator",
    "daq": "Data Acquisition",
    "recorder": "Data Recorder",
    "rf": "RF Power Meter",
    "power_meter": "Power Meter",
}

MANUFACTURER = "B&K Precision"

# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

MODELS: Dict[str, BKModel] = {}


def _add(key: str, name: str, category: str, **kw) -> None:
    MODELS[key] = BKModel(key=key, name=name, category=category, **kw)


# --- Power supplies --------------------------------------------------------
_add("1685B", "1685B Series", "psu", protocol=PROTOCOL_FIXED,
     skus=("1685B", "1687B", "1688B"), usb=USB_CDC, baud=9600,
     dialect="sout_inverted",
     notes="Fixed-width ASCII, CR terminated. Current is two decimals on the "
           "1685B and one on the 1687B/1688B; getting this wrong commands a "
           "tenfold different current")
_add("1900B", "1900B Series", "psu", protocol=PROTOCOL_FIXED,
     skus=("1900B", "1901B", "1902B"), usb=USB_CDC, baud=9600,
     dialect="sout_inverted",
     notes="Fixed-width ASCII, CR terminated. Current is one decimal")
_add("1820B", "1820B Series", "counter", protocol=PROTOCOL_PROPRIETARY,
     skus=("1820B", "1821B", "1822B", "1823B"), usb=USB_CDC, baud=115200,
     notes="Universal frequency counter, not a supply — B&K's own matrix "
           "files it under power supplies, but the manual documents "
           "single-letter counter commands (R, S?, I?) alongside the IEEE "
           "488.2 common set. FTDI virtual COM at 115200 8N1, not the 9600 "
           "the rest of the legacy line uses")
_add("1696", "1696/1697/1698", "psu", protocol=PROTOCOL_FIXED,
     skus=("1696", "1697", "1698"), rs232=True, rs485=True, baud=9600,
     dialect="sout_inverted",
     notes="Straight-through serial cable, 9600 8N1, no appended line feeds")
_add("1696B", "1696B Series", "psu", skus=("1696B", "1697B", "1698B"),
     rs485=True, baud=9600, notes="Reports as 169XB in *IDN?")
_add("9103", "9103/9104", "psu", protocol=PROTOCOL_FIXED, skus=("9103", "9104"),
     usb=USB_CDC, baud=9600, dialect="preset_indexed",
     notes="Fixed-width, but a different dialect: VOLT/CURR take a leading "
           "preset index and four-digit two-decimal fields, and SOUT is not "
           "inverted (1 enables the output)")
_add("9115", "9115 Series", "psu", skus=("9115", "9116"), usb=USB_TMC,
     rs232=True, rs485=True, gpib=True, bauds=STD_BAUDS,
     notes="RS-485 multi-drop on a separate rear DB-9 from RS-232")
_add("9129B", "9129B", "psu", usb=USB_CDC, rs232=True,
     bauds=(4800, 9600, 38400), channels=3,
     notes="Reduced baud set; triple output")
_add("9130B", "9130B Series", "psu", skus=("9130B", "9131B", "9132B"),
     usb=USB_CDC, rs232=True, gpib=True, bauds=STD_BAUDS, channels=3,
     max_voltage=30.0, max_current=3.0,
     notes="Triple output; up to 32 units addressable over IEEE-488.2")
_add("9130C", "9130C Series", "psu", skus=("9130C", "9131C", "9132C"),
     usb=USB_CDC, rs232=True, gpib=True, bauds=STD_BAUDS, channels=3,
     max_voltage=30.0, max_current=3.0)
_add("9140", "9140 Series", "psu", skus=("9140", "9141"), usb=USB_CDC,
     gpib=True, lan=True, channels=3,
     notes="Triple output, list mode, data logger, output pairing")
_add("9240", "9240 Series", "psu", skus=("9240", "9241", "9242"), usb=USB_CDC,
     gpib=True, lan=True)
_add("9200B", "9200B Series", "psu", skus=("9205B", "9206B"), usb=USB_TMC,
     rs232=True, lan=True, bauds=STD_BAUDS, max_voltage=120.0, max_current=10.0,
     notes="Multi-range: 60V/10A or 120V/5A. B&K publishes no programming "
           "manual for this series; the SCPI set here is the one LabLink's "
           "existing 9205B/9206B driver was written against")
_add("9800", "9800 Series", "psu", usb=USB_TMC, rs232=True, lan=True,
     bauds=STD_BAUDS, notes="Programmable AC source")
_add("9810", "9810 Series", "psu", usb=USB_CDC, gpib=True, lan=True)
_add("MR", "MR Series", "psu", skus=("MR25080", "MR50040", "MR100020", "MR40003"),
     gpib=True, lan=True, notes="Multi-range; select the range before setting a level")
_add("MPS", "MPS Series", "psu", skus=("MPS1001", "MPS1101", "MPS1102"),
     gpib=True, lan=True, ports=(SCPI_RAW_PORT,))
_add("HPS", "HPS Series", "psu", protocol=PROTOCOL_PROPRIETARY, rs232=True,
     lan=True, bauds=(9600, 115200), ports=(SCPI_RAW_PORT,),
     notes="Answers the IEEE 488.2 common commands, but its Source/Current/"
           "Limit/List/Script subsystems are proprietary, not SCPI — VOLT and "
           "MEAS:VOLT? do not exist. Carried over VISA or raw socket 5025")
_add("HVL", "HVL Series", "psu", skus=("HVL100025",), gpib=True, lan=True,
     ports=(5000, SCPI_RAW_PORT),
     notes="SKUs are also written hyphenated, e.g. HVL-1000-25")
_add("HMR", "HMR Series", "psu", skus=("HMR130023", "HMR195027"), gpib=True,
     lan=True, ports=(5000, SCPI_RAW_PORT))

# --- DC electronic loads ---------------------------------------------------
_add("8500B", "8500B Series", "load", rs232=True, gpib=True, bauds=STD_BAUDS)
_add("8600", "8600 Series", "load",
     skus=("8600", "8601", "8602", "8610", "8612", "8614", "8616"),
     usb=USB_TMC, rs232=True, gpib=True, lan=True, bauds=STD_BAUDS,
     notes="RTS/CTS and XON/XOFF flow control available. Enabling parity "
           "drops the frame to 7 data bits and corrupts bytes above ASCII 127")
_add("8460", "8460", "load", rs232=True, lan=True)
_add("8550", "8550 Series", "load", rs232=True, bauds=STD_BAUDS)
_add("MDL", "MDL Series", "load",
     skus=("MDL001", "MDL002", "MDL200", "MDL252", "MDL305", "MDL400", "MDL505"),
     usb=USB_TMC, rs232=True, gpib=True, lan=True, bauds=STD_BAUDS)
_add("MDL4U", "MDL4U Series", "load", skus=("MDL4U001", "MDL4U002"),
     usb=USB_TMC, rs232=True, gpib=True, lan=True, bauds=STD_BAUDS)
_add("MDL4UB", "MDL4UB Series", "load", skus=("MDL4UB001", "MDL4UB002"),
     usb=USB_TMC, rs232=True, gpib=True, lan=True, bauds=STD_BAUDS)
_add("DML", "DML Series", "load", skus=("DML1102",), gpib=True, lan=True,
     ports=(SCPI_RAW_PORT,))

# --- Multimeters, counters, analyzers --------------------------------------
_add("2840", "2840 Series", "dmm", skus=("2840", "2841"), usb=USB_CDC,
     rs232=True, gpib=True, lan=True, bauds=STD_BAUDS)
_add("5490C", "5490C Series", "dmm", skus=("5491C", "5492C", "5493C"),
     rs232=True, lan=True, bauds=STD_BAUDS,
     notes="Reports as 549XC in *IDN?")
_add("2680", "2680 Series", "dmm", skus=("2680", "2681", "2682"), lan=True)
_add("5335B", "5335B", "counter", rs232=True, gpib=True, bauds=STD_BAUDS)
_add("894", "894/895", "lcr", skus=("894", "895"), usb=USB_TMC, rs232=True,
     gpib=True, lan=True, bauds=(9600, 19200, 38400, 57600, 115200))
_add("BA6010", "BA6010 Series", "battery", skus=("BA6010", "BA6011"))
_add("BA8100", "BA8100", "battery")
_add("9830", "9830 Series", "battery", skus=("9831", "9832", "9833"),
     usb=USB_TMC, rs232=True, gpib=True, lan=True, ports=(5000,))
_add("9830B", "9830B Series", "battery", skus=("9831B", "9832B", "9833B"),
     usb=USB_TMC, rs232=True, gpib=True, lan=True, ports=(5000,))
_add("BCS", "BCS Series", "battery_sim", skus=("BCS6402",), usb=USB_CDC,
     gpib=True, lan=True, ports=(SCPI_RAW_PORT,))
_add("DAQ3120", "DAQ3120 Series", "daq", usb=USB_CDC, gpib=True, lan=True,
     ports=(5000, 5024, SCPI_RAW_PORT),
     notes="Telnet on 5024; the control socket port must be queried at runtime")

# --- Oscilloscopes and generators ------------------------------------------
_add("2510B", "2510B Series", "scope", usb=USB_CDC, lan=True, ports=(5000,))
_add("2560B", "2560B Series", "scope",
     skus=("2565B", "2566B", "2567B", "2568B", "2569B"),
     usb=USB_CDC, lan=True, ports=(5000,),
     notes="Mixed-signal SKUs append -MSO in *IDN?, e.g. 2569B-MSO")
_add("2190D", "2190D", "scope", protocol=PROTOCOL_SIGLENT, usb=USB_TMC,
     rs232=True, gpib=True, ports=(5000, 5001))
_add("2190E", "2190E", "scope", protocol=PROTOCOL_SIGLENT, usb=USB_TMC,
     rs232=True, gpib=True, ports=(5000, 5001))
_add("2550", "2550 Series", "scope", protocol=PROTOCOL_SIGLENT,
     skus=("2552", "2553", "2554", "2555", "2556", "2557", "2558", "2559"),
     usb=USB_TMC, rs232=True, gpib=True, ports=(5000, 5001))
_add("2560", "2560 Series", "scope", protocol=PROTOCOL_SIGLENT, usb=USB_TMC,
     rs232=True, gpib=True, ports=(5000,))
_add("2194", "2194", "scope", usb=USB_CDC, ports=(5000,),
     bauds=(2400, 4800, 9600, 19200, 38400, 115200))
_add("4050B", "4050B Series", "awg", protocol=PROTOCOL_SIGLENT,
     skus=("4053B", "4054B", "4055B"), lan=True,
     notes="Siglent-style waveform commands, but LAN configuration is SCPI")
_add("4050", "4050 Series", "awg", protocol=PROTOCOL_SIGLENT,
     skus=("4052", "4053", "4054", "4055"))
_add("4060B", "4060B Series", "awg", protocol=PROTOCOL_SIGLENT,
     skus=("4063B", "4064B", "4065B"), lan=True)
_add("4060", "4060 Series", "awg", protocol=PROTOCOL_SIGLENT,
     skus=("4063", "4064", "4065"))
_add("4088", "4088 Series", "awg", usb=USB_CDC, rs232=True, gpib=True,
     lan=True, bauds=STD_BAUDS)

# --- RF, power meters, recorders -------------------------------------------
_add("RFM3000", "RFM3000 Series", "rf", gpib=True, lan=True)
_add("RFP3000", "RFP3000 Series", "rf", usb=USB_CDC)
_add("9814", "9814", "power_meter", protocol=PROTOCOL_FIXED)
_add("9816B", "9816B", "power_meter", protocol=PROTOCOL_FIXED, usb=USB_CDC,
     rs232=True)
for _das in ("DAS30", "DAS50", "DAS60", "DAS220", "DAS240", "DAS700", "DAS701",
             "DAS1700"):
    _add(_das, _das, "recorder", rs232=True, lan=True)


# ---------------------------------------------------------------------------
# Manufacturer recognition
# ---------------------------------------------------------------------------

#: Every manufacturer spelling seen in a B&K ``*IDN?`` example, reduced to
#: alphanumerics. ``BK`` alone is used by the 2680 series.
_BK_MANUFACTURER_FORMS = frozenset({
    "BKPRECISION",   # "B&K Precision", "B&KPrecision", "BK Precision", ...
    "BKPREC",
    "BK",
    "BANDKPRECISION",
})


def _squash(text: str) -> str:
    """Reduce a field to bare uppercase alphanumerics for comparison."""
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def is_bk_manufacturer(manufacturer: Optional[str]) -> bool:
    """Whether an ``*IDN?`` manufacturer field is B&K, in any of its spellings.

    The published manuals show at least six: ``B&K Precision``,
    ``B&KPrecision``, ``B&KPRECISION``, ``BK Precision``, ``B&K PRECISION``
    and bare ``BK``. All reduce to the same alphanumeric stem.
    """
    return _squash(manufacturer) in _BK_MANUFACTURER_FORMS


# ---------------------------------------------------------------------------
# Model resolution
# ---------------------------------------------------------------------------

#: SKU -> family key, built once from the registry.
_SKU_INDEX: Dict[str, str] = {}
for _key, _model in MODELS.items():
    _SKU_INDEX.setdefault(_squash(_key), _key)
    for _sku in _model.skus:
        _SKU_INDEX.setdefault(_squash(_sku), _key)

#: Families addressed by an alphabetic prefix followed by a numeric SKU code,
#: longest first so MDL4U wins over MDL.
_ALPHA_PREFIX_FAMILIES: Tuple[str, ...] = tuple(sorted(
    (k for k in MODELS if re.fullmatch(r"[A-Z]+", k)),
    key=len, reverse=True,
))

_STEM_RE = re.compile(r"^([A-Z]*)(\d+)([A-Z]*)$")


def _decade_match(candidate: str) -> Optional[str]:
    """Resolve a SKU to a family documented per decade.

    B&K names a family after the lowest SKU in it and then ships neighbours:
    9241 belongs to the 9240 series, 2682 to the 2680, 4054 to the 4050,
    9131B to the 9130B. A candidate matches when its alphabetic prefix and
    suffix are identical and its digits agree except in the last place.

    The suffix must match exactly, which is what keeps 2194 (its own family)
    away from 2190D, and 9816B away from the 9810 series.
    """
    m = _STEM_RE.match(candidate)
    if not m:
        return None
    prefix, digits, suffix = m.groups()
    for key, model in MODELS.items():
        km = _STEM_RE.match(_squash(key))
        if not km:
            continue
        kprefix, kdigits, ksuffix = km.groups()
        if (prefix, suffix) != (kprefix, ksuffix):
            continue
        if len(digits) != len(kdigits) or not kdigits.endswith("0"):
            continue
        if digits[:-1] == kdigits[:-1]:
            return key
    return None


def _wildcard_match(candidate: str) -> Optional[str]:
    """Resolve a model string that uses X as a digit placeholder.

    Some firmware reports the family rather than the SKU — ``549XC`` for a
    5490C-series meter, ``169XB`` for a 1696B, ``HMRxxxx`` for an HMR.
    """
    if "X" not in candidate:
        return None
    # A run of trailing placeholders on an all-alphabetic family, e.g. HMRXXXX.
    trimmed = candidate.rstrip("X")
    if trimmed and trimmed != candidate and _squash(trimmed) in _SKU_INDEX:
        return _SKU_INDEX[_squash(trimmed)]
    pattern = re.compile("^" + candidate.replace("X", ".") + "$")
    for squashed, key in _SKU_INDEX.items():
        if pattern.match(squashed):
            return key
    return None


def resolve_model(model: Optional[str]) -> Optional[BKModel]:
    """Resolve a model or SKU string to its B&K family, or None.

    Tolerates the forms that actually turn up in ``*IDN?`` replies and in
    user-typed model fields: SKUs (``9241``), family names (``9240 Series``),
    a redundant ``BK`` prefix (``BK1823B``), variant suffixes
    (``2569B-MSO``), hyphenation (``HVL-1000-25``), digit placeholders
    (``549XC``) and a leading manufacturer (``B&K Precision 9130B``).
    """
    if not model:
        return None

    raw = model.strip().upper()

    # A full "B&K Precision 9130B" string: drop the manufacturer words.
    raw = re.sub(r"^B\s*(&|AND)?\s*K\b[\s.]*(PRECISION)?", " ", raw)

    candidates: List[str] = []

    def _push(text: str) -> None:
        squashed = _squash(text)
        if squashed and squashed not in candidates:
            candidates.append(squashed)

    _push(raw)
    # "894/895" and similar: try each side.
    for part in re.split(r"[/,]", raw):
        _push(part)
    # Drop a trailing "SERIES" and any parenthesised or dashed variant tag.
    stripped = re.sub(r"\bSERIES\b|\(.*?\)", " ", raw)
    _push(stripped)
    _push(re.split(r"-", stripped)[0])

    resolved: List[str] = []
    for candidate in list(candidates):
        # A bare "BK" prefix is decoration on some SKUs (BK1823B).
        if candidate.startswith("BK") and len(candidate) > 2:
            resolved.append(candidate[2:])
    candidates.extend(c for c in resolved if c not in candidates)

    # 1. Exact family key or documented SKU.
    for candidate in candidates:
        if candidate in _SKU_INDEX:
            return MODELS[_SKU_INDEX[candidate]]

    # 2. Digit placeholders (549XC, 169XB, HMRxxxx).
    for candidate in candidates:
        key = _wildcard_match(candidate)
        if key:
            return MODELS[key]

    # 3. Alphabetic-prefix families with a numeric SKU code (MR40003, MPS1102).
    for candidate in candidates:
        for prefix in _ALPHA_PREFIX_FAMILIES:
            if candidate.startswith(prefix) and candidate[len(prefix):].isdigit():
                return MODELS[prefix]

    # 4. Same family, neighbouring SKU (9241 -> 9240, 2569B -> 2560B).
    for candidate in candidates:
        key = _decade_match(candidate)
        if key:
            return MODELS[key]

    return None


def resolve_idn(idn: Optional[str]) -> Tuple[Dict[str, Optional[str]], Optional[BKModel]]:
    """Parse an ``*IDN?`` reply and resolve its model against the registry.

    Returns the parsed fields plus the matching :class:`BKModel`, or None when
    the reply is not from a B&K instrument or names a model with no published
    manual.
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

    if not is_bk_manufacturer(fields["manufacturer"]):
        return fields, None
    return fields, resolve_model(fields["model"])


# ---------------------------------------------------------------------------
# Lookups used by discovery, the manager and the API
# ---------------------------------------------------------------------------

def equipment_type_for(model: BKModel) -> Optional[str]:
    """LabLink EquipmentType value for a family, or None if unsupported."""
    return CATEGORY_TO_EQUIPMENT_TYPE.get(model.category)


#: Fixed-width families LabLink implements a driver for. The rest of the
#: fixed-width line, and every Siglent-style model, is catalogued but not
#: drivable — assuming SCPI against one of those fails silently.
DRIVEN_FIXED_FAMILIES = frozenset({"1685B", "1900B", "1696", "9103"})


#: Categories LabLink ships a B&K driver for. Scopes and generators are
#: identified during discovery but have no B&K driver yet.
DRIVEN_CATEGORIES = frozenset({"psu", "battery_sim", "load", "dmm"})


def is_drivable(model: BKModel) -> bool:
    """Whether LabLink has a driver that can actually talk to this family."""
    if model.category not in DRIVEN_CATEGORIES:
        return False
    if model.protocol == PROTOCOL_SCPI:
        return True
    return model.protocol == PROTOCOL_FIXED and model.key in DRIVEN_FIXED_FAMILIES


def usb_mode(model: str) -> Optional[str]:
    """``"tmc"``, ``"cdc"`` or None for a model's USB port."""
    info = resolve_model(model)
    return info.usb if info else None


def default_baud(model: str, fallback: int = 9600) -> int:
    """Documented power-on baud rate for a model's serial / USB-CDC link.

    A rate changed from the front panel persists in NVRAM and wins over this,
    so treat it as a starting point for probing rather than a guarantee.
    """
    info = resolve_model(model)
    return info.baud if info else fallback


def candidate_bauds(model: Optional[str] = None) -> Tuple[int, ...]:
    """Baud rates worth trying for a model, most likely first."""
    info = resolve_model(model) if model else None
    if info:
        ordered = [info.baud] + [b for b in (info.bauds or STD_BAUDS) if b != info.baud]
        return tuple(ordered)
    # Unknown model: 9600 covers the legacy line, 115200 the 1820B and HPS.
    return (9600, 115200, 38400, 57600, 19200, 4800)


def models_by_category(category: Optional[str] = None) -> List[BKModel]:
    """Registry contents, optionally filtered by category, sorted by key."""
    items = MODELS.values()
    if category:
        items = [m for m in items if m.category == category]
    return sorted(items, key=lambda m: m.key)


def connectable_models() -> List[BKModel]:
    """Families LabLink has a driver for."""
    return [m for m in models_by_category() if equipment_type_for(m)]


def catalog() -> List[dict]:
    """Serialisable catalogue of every documented family, for the API/UI."""
    entries = []
    for model in models_by_category():
        entries.append({
            "key": model.key,
            "name": model.name,
            "manufacturer": MANUFACTURER,
            "category": model.category,
            "category_label": CATEGORY_LABELS.get(model.category, model.category),
            "equipment_type": equipment_type_for(model),
            "protocol": model.protocol,
            "skus": list(model.skus),
            "usb_mode": model.usb,
            "interfaces": model.interfaces,
            "default_baud": model.baud,
            "selectable_bauds": list(model.bauds),
            "socket_ports": list(model.ports),
            "channels": model.channels,
            "max_voltage": model.max_voltage,
            "max_current": model.max_current,
            "supports_idn": model.supports_idn,
            "supported": is_drivable(model),
            "notes": model.notes,
        })
    return entries
