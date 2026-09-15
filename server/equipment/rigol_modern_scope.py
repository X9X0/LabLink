"""Rigol "modern SCPI tree" oscilloscope drivers.

One base class (:class:`RigolModernScopeBase`) implements the command tree that
Rigol has used on every bench scope since the DS1000Z/DS4000/DS6000 generation:

* ``:CHANnel<n>:SCALe/OFFSet/COUPling/PROBe/BWLimit/DISPlay/INVert``
* ``:TIMebase:MAIN:SCALe/OFFSet``, ``:TIMebase:MODE``
* ``:TRIGger:MODE``, ``:TRIGger:SWEep``, ``:TRIGger:STATus?``, ``:TRIGger:EDGE:SOURce/LEVel/SLOPe``
* ``:RUN`` / ``:STOP`` / ``:SINGle`` / ``:TFORce`` / ``:CLEar`` and ``:AUToscale`` or ``:AUToset``
* ``:ACQuire:TYPE/AVERages/MDEPth/SRATe?``
* ``:MEASure:ITEM <item>,CHAN<n>`` (or the per-item ``:MEASure:VPP? CHAN<n>`` form on
  DS4000/DS6000)
* ``:WAVeform:SOURce/MODE/FORMat/STARt/STOP/POINts/PREamble?/DATA?``
* ``:DISPlay:DATA?`` screenshots and ``:LA:`` digital-channel control on MSO models

Family differences that matter for a driver are captured in :class:`FamilySpec`
and per-model facts (channel counts, bandwidth, sample rate, memory depth,
bandwidth-limit options) in :data:`MODEL_TABLE`.  After ``*IDN?`` the driver
picks the matching row, so even the generic base class reports the right
channel count for any listed model.  The thin subclasses at the bottom only pin
the *default* family used when a model string is not recognised.

Sources: the Rigol programming guides for DHO800/DHO900, DHO1000/DHO4000,
DHO/MHO5000, MHO900, MHO98, MHO2000, MSO5000, MSO5000-E, MSO/DS7000, MSO8000,
MSO8000A, DS8000-R, DS4000E, DS6000, DS70000, DS80000 and DS1000Z-E (see
``docs/RIGOL_SCOPES.md`` for the per-family notes and the contradictions found).

*IDN? returns ``RIGOL TECHNOLOGIES,<model>,<serial>,<firmware>``.
"""

import asyncio
import logging
import math
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from shared.models.data import WaveformData
from shared.models.equipment import (EquipmentInfo, EquipmentStatus,
                                     EquipmentType)

from .base import BaseEquipment, generate_equipment_id

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Static tables
# --------------------------------------------------------------------------- #

# Friendly measurement name -> SCPI item mnemonic.  The mnemonic is the same
# token in ":MEASure:ITEM? <item>,CHANn" (modern) and ":MEASure:<item>? CHANn"
# (DS4000/DS6000 legacy form), so one table serves both styles.
MEASURE_ITEMS: Dict[str, str] = {
    "VPP": "VPP",
    "VMAX": "VMAX",
    "VMIN": "VMIN",
    "VAVG": "VAVG",
    "VRMS": "VRMS",
    "VTOP": "VTOP",
    "VBASE": "VBASe",
    "VAMP": "VAMP",
    "VUPPER": "VUPPer",
    "VMID": "VMID",
    "VLOWER": "VLOWer",
    "OVERSHOOT": "OVERshoot",
    "PRESHOOT": "PREShoot",
    "FREQ": "FREQuency",
    "PERIOD": "PERiod",
    "RISE": "RTIMe",
    "FALL": "FTIMe",
    "PWIDTH": "PWIDth",
    "NWIDTH": "NWIDth",
    "DUTY": "PDUTy",
    "NDUTY": "NDUTy",
    "AREA": "MARea",
    "PAREA": "MPARea",
    "VARIANCE": "VARiance",
    "PVRMS": "PVRMs",
    "TVMAX": "TVMAX",
    "TVMIN": "TVMIN",
    "PSLEW": "PSLewrate",
    "NSLEW": "NSLewrate",
    "PPULSES": "PPULses",
    "NPULSES": "NPULses",
    "PEDGES": "PEDGes",
    "NEDGES": "NEDGes",
}

# Alternate spellings users type in acquisition channel strings.
_MEASURE_ALIASES: Dict[str, str] = {
    "PK2PK": "VPP",
    "PKPK": "VPP",
    "PEAK": "VPP",
    "PTP": "VPP",
    "MAX": "VMAX",
    "MIN": "VMIN",
    "AVG": "VAVG",
    "MEAN": "VAVG",
    "AVERAGE": "VAVG",
    "RMS": "VRMS",
    "TOP": "VTOP",
    "BASE": "VBASE",
    "AMP": "VAMP",
    "AMPLITUDE": "VAMP",
    "FREQUENCY": "FREQ",
    "F": "FREQ",
    "PER": "PERIOD",
    "T": "PERIOD",
    "RTIME": "RISE",
    "RISE_TIME": "RISE",
    "RISETIME": "RISE",
    "FTIME": "FALL",
    "FALL_TIME": "FALL",
    "FALLTIME": "FALL",
    "PDUTY": "DUTY",
    "DUTY_CYCLE": "DUTY",
    "POSITIVE_WIDTH": "PWIDTH",
    "NEGATIVE_WIDTH": "NWIDTH",
    "OVER": "OVERSHOOT",
    "PRE": "PRESHOOT",
    "MAREA": "AREA",
    "MPAREA": "PAREA",
    "PSLEWRATE": "PSLEW",
    "NSLEWRATE": "NSLEW",
}

_VOLT_ITEMS = {"VPP", "VMAX", "VMIN", "VAVG", "VRMS", "VTOP", "VBASE", "VAMP",
               "VUPPER", "VMID", "VLOWER", "PVRMS"}
_TIME_ITEMS = {"PERIOD", "RISE", "FALL", "PWIDTH", "NWIDTH", "TVMAX", "TVMIN"}
_RATIO_ITEMS = {"DUTY", "NDUTY", "OVERSHOOT", "PRESHOOT"}

# Items returned by get_measurements(), in the key names the existing
# rigol_scope.py drivers use so the scope UI works unchanged.
_STREAM_ITEMS: Sequence[Tuple[str, str]] = (
    ("vpp", "VPP"),
    ("vmax", "VMAX"),
    ("vmin", "VMIN"),
    ("vavg", "VAVG"),
    ("vrms", "VRMS"),
    ("freq", "FREQ"),
    ("period", "PERIOD"),
    ("rise_time", "RISE"),
    ("fall_time", "FALL"),
    ("positive_width", "PWIDTH"),
    ("negative_width", "NWIDTH"),
    ("duty_cycle", "DUTY"),
)

# Values at/above this magnitude mean "no valid measurement" (the guides
# document 9.9E37 for DS4000E; the modern families return the same sentinel).
_INVALID_THRESHOLD = 9.0e37

_TRIGGER_MODES = {"EDGE", "PULS", "SLOP", "VID", "PATT", "DUR", "TIM", "RUNT",
                  "WIND", "DEL", "SET", "NEDG", "RS232", "IIC", "SPI", "CAN",
                  "LIN", "FLEX", "USB", "SHOL"}
_TRIGGER_MODE_ALIASES = {
    "PULSE": "PULS", "SLOPE": "SLOP", "VIDEO": "VID", "PATTERN": "PATT",
    "DURATION": "DUR", "TIMEOUT": "TIM", "WINDOW": "WIND", "WINDOWS": "WIND",
    "DELAY": "DEL", "SETUP": "SET", "NEDGE": "NEDG", "FLEXRAY": "FLEX",
    "SHOLD": "SHOL",
}
_SWEEP_MODES = {"AUTO": "AUTO", "NORM": "NORMal", "NORMAL": "NORMal",
                "SING": "SINGle", "SINGLE": "SINGle"}
_SLOPES = {"POS": "POSitive", "POSITIVE": "POSitive", "RISING": "POSitive", "RISE": "POSitive",
           "NEG": "NEGative", "NEGATIVE": "NEGative", "FALLING": "NEGative", "FALL": "NEGative",
           "RFAL": "RFALl", "RFALL": "RFALl", "EITHER": "RFALl", "BOTH": "RFALl"}
_COUPLINGS = {"AC", "DC", "GND"}
_WAVEFORM_MODES = {"NORM": "NORMal", "NORMAL": "NORMal", "SCREEN": "NORMal",
                   "RAW": "RAW", "MEMORY": "RAW", "MAX": "MAXimum", "MAXIMUM": "MAXimum"}


def parse_measurement(raw: str) -> float:
    """Parse a measurement reply; NaN when invalid/overloaded/unparsable."""
    text = (raw or "").strip().strip('"').split(",")[0].strip()
    if not text:
        return float("nan")
    try:
        value = float(text)
    except ValueError:
        return float("nan")
    if math.isnan(value) or math.isinf(value) or abs(value) >= _INVALID_THRESHOLD:
        return float("nan")
    return value


def parse_tmc_block(data: bytes) -> Tuple[bytes, int]:
    """Split an IEEE-488.2 definite-length block (``#9000001000<bytes>``).

    Returns ``(payload, missing)`` where ``missing`` is the number of payload
    bytes not yet received (0 when the block is complete).  Data without a
    ``#`` header is returned as-is with trailing line terminators removed.
    """
    if not data:
        return b"", 0
    start = data.find(b"#")
    if start < 0 or len(data) < start + 2:
        return data.rstrip(b"\r\n"), 0
    data = data[start:]
    try:
        ndigits = int(chr(data[1]))
    except ValueError:
        return data.rstrip(b"\r\n"), 0
    if ndigits == 0:
        # Indefinite-length block: everything up to the terminator.
        return data[2:].rstrip(b"\r\n"), 0
    header_len = 2 + ndigits
    if len(data) < header_len:
        return b"", header_len - len(data)
    try:
        length = int(data[2:header_len])
    except ValueError:
        return data[header_len:].rstrip(b"\r\n"), 0
    payload = data[header_len:header_len + length]
    return payload, max(0, length - len(payload))


def parse_preamble(raw: str) -> Dict[str, float]:
    """Parse ``:WAVeform:PREamble?`` (10 comma separated fields)."""
    parts = [p.strip() for p in raw.strip().split(",")]
    if len(parts) < 10:
        raise ValueError(f"Invalid waveform preamble: {raw!r}")
    return {
        "format": int(float(parts[0])),
        "type": int(float(parts[1])),
        "points": int(float(parts[2])),
        "count": int(float(parts[3])),
        "x_increment": float(parts[4]),
        "x_origin": float(parts[5]),
        "x_reference": float(parts[6]),
        "y_increment": float(parts[7]),
        "y_origin": float(parts[8]),
        "y_reference": float(parts[9]),
    }


def raw_to_volts(raw: bytes, preamble: Dict[str, float], fmt: str = "BYTE") -> np.ndarray:
    """Convert BYTE/WORD waveform bytes to volts.

    Every guide documents the same formula:
    ``V = (code - YORigin - YREFerence) * YINCrement``.
    WORD data is taken little-endian (the guides do not state the byte order;
    on the 8-bit families only the low byte is significant so either order
    gives the same result after masking on those models).
    """
    if fmt.upper().startswith("WORD"):
        codes = np.frombuffer(raw[: len(raw) - (len(raw) % 2)], dtype="<u2").astype(np.float64)
    else:
        codes = np.frombuffer(raw, dtype=np.uint8).astype(np.float64)
    return (codes - preamble["y_origin"] - preamble["y_reference"]) * preamble["y_increment"]


def normalize_measure_item(item: str) -> str:
    key = (item or "").strip().upper().replace("-", "_").replace(" ", "_")
    key = _MEASURE_ALIASES.get(key, key)
    if key not in MEASURE_ITEMS:
        raise ValueError(
            f"Unknown measurement item '{item}'. Valid: {', '.join(MEASURE_ITEMS)}"
        )
    return key


def measure_unit(item_key: str) -> str:
    if item_key in _VOLT_ITEMS:
        return "V"
    if item_key in _TIME_ITEMS:
        return "s"
    if item_key == "FREQ":
        return "Hz"
    if item_key in _RATIO_ITEMS:
        return "ratio"
    if item_key in ("AREA", "PAREA"):
        return "Vs"
    if item_key in ("PSLEW", "NSLEW"):
        return "V/s"
    if item_key == "VARIANCE":
        return "V^2"
    return ""


def _on_off(value: Union[bool, str, int]) -> str:
    if isinstance(value, str):
        return "ON" if value.strip().upper() in ("1", "ON", "TRUE", "YES") else "OFF"
    return "ON" if value else "OFF"


def _fmt_num(value: float) -> str:
    return f"{float(value):.9g}"


# --------------------------------------------------------------------------- #
# Family / model descriptors
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FamilySpec:
    """Command-tree differences between Rigol scope families."""

    name: str
    autoset_command: str = ":AUToscale"        # ":AUToset" on DHO/MHO/DS80000
    measure_style: str = "ITEM"                 # "ITEM" (:MEAS:ITEM?) or "LEGACY" (:MEAS:VPP?)
    raw_read_flow: str = "RANGE"                # "RANGE" (STARt/STOP) or "STATUS" (RESet/BEGin/STATus/END)
    max_points_per_read: int = 250_000          # chunk size for RAW reads
    screen_points: int = 1000                   # points returned in NORMal mode
    screenshot_query: str = ":DISP:DATA?"       # exact query for a screenshot
    screenshot_format: str = "bmp"
    screenshot_formats: Tuple[str, ...] = ("bmp",)
    acquisition_types: Tuple[str, ...] = ("NORMal", "AVERages", "PEAK", "HRESolution")
    la_enable_cmd: Optional[str] = None          # ":LA:ENAB" (DHO) / ":LA:STAT" (MSO5000-era)
    la_channel_cmd: Optional[str] = None         # ":LA:DIG:ENAB" (DHO) / ":LA:DIG:DISP" (MSO5000-era)
    edge_sources_extra: Tuple[str, ...] = ()     # "EXT", "ACL"
    trigger_status_values: Tuple[str, ...] = ("TD", "WAIT", "RUN", "AUTO", "STOP")
    raw_requires_stop: bool = True
    supports_word_format: bool = True
    programming_guide: str = ""


FAMILIES: Dict[str, FamilySpec] = {
    "DHO800": FamilySpec(
        name="DHO800", autoset_command=":AUToset", max_points_per_read=1_000_000,
        screenshot_query=":DISP:DATA? PNG", screenshot_format="png",
        screenshot_formats=("bmp", "png", "jpg"),
        acquisition_types=("NORMal", "PEAK", "AVERages", "ULTRa"),
        la_enable_cmd=":LA:ENAB", la_channel_cmd=":LA:DIG:ENAB",
        edge_sources_extra=("EXT",),
        programming_guide="DHO800/DHO900 Programming Guide",
    ),
    "DHO1000": FamilySpec(
        name="DHO1000", autoset_command=":AUToset", max_points_per_read=1_000_000,
        screenshot_query=":DISP:DATA? PNG", screenshot_format="png",
        screenshot_formats=("bmp", "png", "jpg"),
        acquisition_types=("NORMal", "PEAK", "AVERages", "ULTRa"),
        edge_sources_extra=("EXT", "ACL"),
        programming_guide="DHO (DHO1000/DHO4000) Programming Guide",
    ),
    "DHO5000": FamilySpec(
        name="DHO5000", autoset_command=":AUToset", max_points_per_read=1_000_000,
        screenshot_query=":DISP:DATA? PNG", screenshot_format="png",
        screenshot_formats=("bmp", "png", "jpg"),
        acquisition_types=("NORMal", "PEAK", "AVERages", "ULTRa"),
        la_enable_cmd=":LA:ENAB", la_channel_cmd=":LA:DIG:ENAB",
        edge_sources_extra=("EXT", "ACL"),
        programming_guide="DHO/MHO5000 Series Programming Guide",
    ),
    "MHO900": FamilySpec(
        name="MHO900", autoset_command=":AUToset", max_points_per_read=1_000_000,
        screenshot_query=":DISP:DATA? PNG", screenshot_format="png",
        screenshot_formats=("bmp", "png", "jpg"),
        acquisition_types=("NORMal", "PEAK", "AVERages", "ULTRa"),
        la_enable_cmd=":LA:ENAB", la_channel_cmd=":LA:DIG:ENAB",
        edge_sources_extra=("EXT", "ACL"),
        programming_guide="MHO900 / MHO98 / MHO2000 Programming Guides",
    ),
    "MSO5000": FamilySpec(
        name="MSO5000", autoset_command=":AUToscale", max_points_per_read=250_000,
        screenshot_query=":DISP:DATA?", screenshot_format="bmp",
        acquisition_types=("NORMal", "AVERages", "PEAK", "HRESolution"),
        la_enable_cmd=":LA:STAT", la_channel_cmd=":LA:DIG:DISP",
        edge_sources_extra=("ACL",),
        programming_guide="MSO5000 / MSO5000-E Programming Guide",
    ),
    "MSO7000": FamilySpec(
        name="MSO7000", autoset_command=":AUToscale", max_points_per_read=250_000,
        screenshot_query=":DISP:DATA?", screenshot_format="bmp",
        acquisition_types=("NORMal", "AVERages", "PEAK"),
        la_enable_cmd=":LA:STAT", la_channel_cmd=":LA:DIG:DISP",
        edge_sources_extra=("ACL", "EXT"),
        programming_guide="MSO7000/DS7000 Programming Guide",
    ),
    "MSO8000": FamilySpec(
        name="MSO8000", autoset_command=":AUToscale", max_points_per_read=1_000_000,
        screenshot_query=":DISP:DATA?", screenshot_format="png",
        screenshot_formats=("png",),
        acquisition_types=("NORMal", "AVERages", "PEAK", "HRESolution"),
        la_enable_cmd=":LA:STAT", la_channel_cmd=":LA:DIG:DISP",
        edge_sources_extra=("ACL", "EXT"),
        programming_guide="MSO8000 / MSO8000A Programming Guide",
    ),
    "DS8000R": FamilySpec(
        name="DS8000R", autoset_command=":AUToscale", max_points_per_read=250_000,
        screenshot_query=":DISP:DATA?", screenshot_format="bmp",
        acquisition_types=("NORMal", "AVERages", "PEAK", "HRESolution"),
        edge_sources_extra=("ACL", "EXT"),
        programming_guide="DS8000-R Programming Guide",
    ),
    "DS4000": FamilySpec(
        name="DS4000", autoset_command=":AUToscale", measure_style="LEGACY",
        raw_read_flow="STATUS", max_points_per_read=250_000, screen_points=1400,
        screenshot_query=":DISP:DATA?", screenshot_format="bmp",
        acquisition_types=("NORMal", "AVERages", "PEAK", "HRESolution"),
        edge_sources_extra=("EXT", "EXT5", "ACL"),
        programming_guide="DS4000E Programming Guide",
    ),
    "DS6000": FamilySpec(
        name="DS6000", autoset_command=":AUToscale", measure_style="LEGACY",
        raw_read_flow="STATUS", max_points_per_read=250_000, screen_points=1400,
        screenshot_query=":DISP:DATA?", screenshot_format="bmp",
        acquisition_types=("NORMal", "AVERages", "PEAK", "HRESolution"),
        edge_sources_extra=("EXT", "EXT5", "ACL"),
        trigger_status_values=("TD", "WAIT", "RUN", "AUTO", "FIN", "STOP"),
        supports_word_format=True,
        programming_guide="DS6000 Programming Manual (CHM)",
    ),
    "DS70000": FamilySpec(
        name="DS70000", autoset_command=":AUToscale", max_points_per_read=1_000_000,
        screenshot_query=":DISP:DATA? PNG", screenshot_format="png",
        screenshot_formats=("bmp", "png", "jpg"),
        acquisition_types=("NORMal", "PEAK", "AVERages", "ULTRa"),
        edge_sources_extra=("EXT", "ACL"),
        programming_guide="DS70000 Series Programming Guide",
    ),
    "DS80000": FamilySpec(
        name="DS80000", autoset_command=":AUToset", max_points_per_read=1_000_000,
        screenshot_query=":DISP:DATA? PNG", screenshot_format="png",
        screenshot_formats=("bmp", "png", "jpg"),
        acquisition_types=("NORMal", "PEAK", "AVERages", "ULTRa"),
        edge_sources_extra=("EXT", "ACL"),
        programming_guide="DS80000 Series Programming Guide",
    ),
    "DS1000ZE": FamilySpec(
        name="DS1000ZE", autoset_command=":AUToscale", max_points_per_read=250_000,
        screen_points=1200,
        screenshot_query=":DISP:DATA? ON,OFF,PNG", screenshot_format="png",
        screenshot_formats=("bmp24", "bmp8", "png", "jpeg", "tiff"),
        acquisition_types=("NORMal", "AVERages", "PEAK", "HRESolution"),
        edge_sources_extra=("AC",),
        programming_guide="DS1000Z-E Programming Guide",
    ),
}


@dataclass(frozen=True)
class ModelSpec:
    """Per-model facts (from the datasheets and programming guides)."""

    model: str
    family: str
    analog_channels: int
    digital_channels: int
    bandwidth_hz: float
    max_sample_rate: float
    max_memory_depth: float
    bw_limits: Tuple[str, ...] = ("OFF", "20M")
    has_ext_trigger: bool = True
    note: str = ""

    @property
    def family_spec(self) -> FamilySpec:
        return FAMILIES[self.family]


def _m(pattern: str, family: str, analog: int, digital: int, bw: float, srate: float,
       depth: float, bw_limits: Tuple[str, ...] = ("OFF", "20M"), ext: bool = True,
       note: str = "") -> Tuple["re.Pattern[str]", ModelSpec]:
    return (
        re.compile(pattern, re.IGNORECASE),
        ModelSpec(pattern, family, analog, digital, bw, srate, depth, bw_limits, ext, note),
    )


_BW20 = ("OFF", "20M")
_BW20_250 = ("OFF", "20M", "250M")
_BW20_100 = ("OFF", "20M", "100M")

# Most specific patterns first.  Patterns are matched with re.search against
# the upper-cased *IDN? model field.
MODEL_TABLE: List[Tuple["re.Pattern[str]", ModelSpec]] = [
    # ---- DHO800 / DHO900 (12-bit, :AUToset) ------------------------------
    _m(r"^DHO802", "DHO800", 2, 0, 70e6, 1.25e9, 25e6, _BW20),
    _m(r"^DHO804", "DHO800", 4, 0, 70e6, 1.25e9, 25e6, _BW20, ext=False),
    _m(r"^DHO812", "DHO800", 2, 0, 100e6, 1.25e9, 25e6, _BW20),
    _m(r"^DHO814", "DHO800", 4, 0, 100e6, 1.25e9, 25e6, _BW20, ext=False),
    _m(r"^DHO914S?", "DHO800", 4, 16, 125e6, 1.25e9, 50e6, _BW20, ext=False),
    _m(r"^DHO924S?", "DHO800", 4, 16, 250e6, 1.25e9, 50e6, _BW20, ext=False),
    # ---- DHO1000 / DHO4000 ---------------------------------------------
    _m(r"^DHO1072", "DHO1000", 2, 0, 70e6, 2e9, 100e6, _BW20),
    _m(r"^DHO1074", "DHO1000", 4, 0, 70e6, 2e9, 100e6, _BW20),
    _m(r"^DHO1102", "DHO1000", 2, 0, 100e6, 2e9, 100e6, _BW20),
    _m(r"^DHO1104", "DHO1000", 4, 0, 100e6, 2e9, 100e6, _BW20),
    _m(r"^DHO1202", "DHO1000", 2, 0, 200e6, 2e9, 100e6, _BW20),
    _m(r"^DHO1204", "DHO1000", 4, 0, 200e6, 2e9, 100e6, _BW20),
    _m(r"^DHO4204", "DHO1000", 4, 0, 200e6, 4e9, 500e6, _BW20_250),
    _m(r"^DHO4404", "DHO1000", 4, 0, 400e6, 4e9, 500e6, _BW20_250),
    _m(r"^DHO4804", "DHO1000", 4, 0, 800e6, 4e9, 500e6, _BW20_250),
    # ---- DHO5000 / MHO5000 ----------------------------------------------
    _m(r"^DHO5054", "DHO5000", 4, 0, 500e6, 4e9, 500e6, _BW20_250),
    _m(r"^DHO5058", "DHO5000", 8, 0, 500e6, 4e9, 500e6, _BW20_250),
    _m(r"^DHO5104", "DHO5000", 4, 0, 1e9, 4e9, 500e6, _BW20_250),
    _m(r"^DHO5108", "DHO5000", 8, 0, 1e9, 4e9, 500e6, _BW20_250),
    _m(r"^MHO5054", "DHO5000", 4, 16, 500e6, 4e9, 500e6, _BW20_250),
    _m(r"^MHO5056", "DHO5000", 6, 16, 500e6, 4e9, 500e6, _BW20_250),
    _m(r"^MHO5104", "DHO5000", 4, 16, 1e9, 4e9, 500e6, _BW20_250),
    _m(r"^MHO5106", "DHO5000", 6, 16, 1e9, 4e9, 500e6, _BW20_250),
    # ---- MHO900 / MHO98 / MHO2000 -----------------------------------------
    _m(r"^MHO934", "MHO900", 4, 16, 350e6, 4e9, 500e6, _BW20_250),
    _m(r"^MHO954", "MHO900", 4, 16, 500e6, 4e9, 500e6, _BW20_250),
    _m(r"^MHO984", "MHO900", 4, 16, 800e6, 4e9, 500e6, _BW20_250),
    _m(r"^MHO98\b", "MHO900", 4, 16, 1e9, 4e9, 500e6, _BW20_250,
       note="Datasheet lists the single model 'MHO98' (1 GHz, 4 GSa/s, 500 Mpts)"),
    _m(r"^MHO2024", "MHO900", 4, 16, 200e6, 2e9, 500e6, _BW20_250),
    _m(r"^MHO2034", "MHO900", 4, 16, 350e6, 2e9, 500e6, _BW20_250),
    # ---- MSO5000 / MSO5000-E ---------------------------------------------
    _m(r"^MSO5072", "MSO5000", 2, 16, 70e6, 8e9, 200e6, _BW20, ext=False),
    _m(r"^MSO5074", "MSO5000", 4, 16, 70e6, 8e9, 200e6, _BW20, ext=False),
    _m(r"^MSO5102", "MSO5000", 2, 16, 100e6, 8e9, 200e6, _BW20, ext=False),
    _m(r"^MSO5104", "MSO5000", 4, 16, 100e6, 8e9, 200e6, _BW20, ext=False),
    _m(r"^MSO5204", "MSO5000", 4, 16, 200e6, 8e9, 200e6, _BW20_100, ext=False),
    _m(r"^MSO5354", "MSO5000", 4, 16, 350e6, 8e9, 200e6, ("OFF", "20M", "100M", "200M"), ext=False),
    _m(r"^MSO5152-?E", "MSO5000", 2, 16, 150e6, 4e9, 100e6, _BW20, ext=False),
    # ---- MSO7000 / DS7000 ------------------------------------------------
    _m(r"^MSO7014", "MSO7000", 4, 16, 100e6, 10e9, 500e6, _BW20),
    _m(r"^MSO7024", "MSO7000", 4, 16, 200e6, 10e9, 500e6, _BW20),
    _m(r"^MSO7034", "MSO7000", 4, 16, 350e6, 10e9, 500e6, _BW20_250),
    _m(r"^MSO7054", "MSO7000", 4, 16, 500e6, 10e9, 500e6, _BW20_250),
    _m(r"^DS7014", "MSO7000", 4, 0, 100e6, 10e9, 500e6, _BW20),
    _m(r"^DS7024", "MSO7000", 4, 0, 200e6, 10e9, 500e6, _BW20),
    _m(r"^DS7034", "MSO7000", 4, 0, 350e6, 10e9, 500e6, _BW20_250),
    _m(r"^DS7054", "MSO7000", 4, 0, 500e6, 10e9, 500e6, _BW20_250),
    # ---- MSO8000 / MSO8000A ---------------------------------------------
    _m(r"^MSO8064", "MSO8000", 4, 16, 600e6, 10e9, 500e6, _BW20_250),
    _m(r"^MSO8104", "MSO8000", 4, 16, 1e9, 10e9, 500e6, _BW20_250),
    _m(r"^MSO8204A", "MSO8000", 4, 16, 2e9, 10e9, 500e6, _BW20_250),
    _m(r"^MSO8204", "MSO8000", 4, 16, 2e9, 10e9, 500e6, _BW20_250),
    _m(r"^MSO8074A", "MSO8000", 4, 16, 750e6, 10e9, 500e6, _BW20_250),
    _m(r"^MSO8154A", "MSO8000", 4, 16, 1.5e9, 10e9, 500e6, _BW20_250),
    _m(r"^MSO8304A", "MSO8000", 4, 16, 3e9, 10e9, 500e6, _BW20_250,
       note="Named in the MSO8000A programming guide; the MSO8000A datasheet tops out at MSO8204A (2 GHz)"),
    # ---- DS8000-R ---------------------------------------------------------
    _m(r"^DS8034-?R", "DS8000R", 4, 0, 350e6, 5e9, 500e6, _BW20_250),
    _m(r"^DS8104-?R", "DS8000R", 4, 0, 1e9, 10e9, 500e6, ("OFF", "20M", "250M", "500M")),
    _m(r"^DS8204-?R", "DS8000R", 4, 0, 2e9, 10e9, 500e6, ("OFF", "20M", "250M", "500M")),
    # ---- DS4000E / DS4000 / MSO4000 ---------------------------------------
    _m(r"^DS4014E", "DS4000", 4, 0, 100e6, 2e9, 14e6, _BW20),
    _m(r"^DS4024E", "DS4000", 4, 0, 200e6, 2e9, 14e6, _BW20_100),
    _m(r"^(DS|MSO)4012", "DS4000", 2, 16, 100e6, 4e9, 140e6, _BW20,
       note="DS/MSO4000 (non-E) assumed to share the DS4000E tree"),
    _m(r"^(DS|MSO)4014", "DS4000", 4, 16, 100e6, 4e9, 140e6, _BW20),
    _m(r"^(DS|MSO)4022", "DS4000", 2, 16, 200e6, 4e9, 140e6, _BW20_100),
    _m(r"^(DS|MSO)4024", "DS4000", 4, 16, 200e6, 4e9, 140e6, _BW20_100),
    _m(r"^(DS|MSO)4032", "DS4000", 2, 16, 350e6, 4e9, 140e6, _BW20_100),
    _m(r"^(DS|MSO)4034", "DS4000", 4, 16, 350e6, 4e9, 140e6, _BW20_100),
    _m(r"^(DS|MSO)4052", "DS4000", 2, 16, 500e6, 4e9, 140e6, _BW20_100),
    _m(r"^(DS|MSO)4054", "DS4000", 4, 16, 500e6, 4e9, 140e6, _BW20_100),
    # ---- DS6000 ------------------------------------------------------------
    _m(r"^DS6062", "DS6000", 2, 0, 600e6, 5e9, 140e6, _BW20_250),
    _m(r"^DS6064", "DS6000", 4, 0, 600e6, 5e9, 140e6, _BW20_250),
    _m(r"^DS6102", "DS6000", 2, 0, 1e9, 5e9, 140e6, _BW20_250),
    _m(r"^DS6104", "DS6000", 4, 0, 1e9, 5e9, 140e6, _BW20_250),
    # ---- DS70000 / DS80000 ---------------------------------------------------
    _m(r"^DS70304", "DS70000", 4, 0, 3e9, 20e9, 2e9, ("OFF", "20M", "250M", "1G", "2G")),
    _m(r"^DS70504", "DS70000", 4, 0, 5e9, 20e9, 2e9, ("OFF", "20M", "250M", "1G", "2G")),
    _m(r"^DS80604", "DS80000", 4, 0, 6e9, 40e9, 4e9, ("OFF", "500M", "1G", "2G", "3G", "4G", "5G")),
    _m(r"^DS80804", "DS80000", 4, 0, 8e9, 40e9, 4e9, ("OFF", "500M", "1G", "2G", "3G", "4G", "5G", "6G", "7G")),
    _m(r"^DS81004", "DS80000", 4, 0, 10e9, 40e9, 4e9, ("OFF", "500M", "1G", "2G", "3G", "4G", "5G", "6G", "7G", "8G", "9G")),
    _m(r"^DS81304", "DS80000", 4, 0, 13e9, 40e9, 4e9,
       ("OFF", "500M", "1G", "2G", "3G", "4G", "5G", "6G", "7G", "8G", "9G", "10G", "11G", "12G")),
    # ---- DS1000Z-E ---------------------------------------------------------
    _m(r"^DS1102Z-?E", "DS1000ZE", 2, 0, 100e6, 1e9, 24e6, _BW20, ext=False),
    _m(r"^DS1202Z-?E", "DS1000ZE", 2, 0, 200e6, 1e9, 24e6, _BW20, ext=False),
    # ---- family fallbacks (unknown member of a known family) -----------------
    _m(r"^DHO8\d\d", "DHO800", 4, 0, 100e6, 1.25e9, 25e6, _BW20),
    _m(r"^DHO9\d\d", "DHO800", 4, 16, 250e6, 1.25e9, 50e6, _BW20),
    _m(r"^DHO1\d{3}", "DHO1000", 4, 0, 200e6, 2e9, 100e6, _BW20),
    _m(r"^DHO4\d{3}", "DHO1000", 4, 0, 800e6, 4e9, 500e6, _BW20_250),
    _m(r"^DHO5\d{3}", "DHO5000", 4, 0, 1e9, 4e9, 500e6, _BW20_250),
    _m(r"^MHO5\d{3}", "DHO5000", 4, 16, 1e9, 4e9, 500e6, _BW20_250),
    _m(r"^MHO9\d\d", "MHO900", 4, 16, 800e6, 4e9, 500e6, _BW20_250),
    _m(r"^MHO2\d{3}", "MHO900", 4, 16, 350e6, 2e9, 500e6, _BW20_250),
    _m(r"^MSO5\d{3}", "MSO5000", 4, 16, 350e6, 8e9, 200e6, _BW20),
    _m(r"^(MSO|DS)7\d{3}", "MSO7000", 4, 16, 500e6, 10e9, 500e6, _BW20_250),
    _m(r"^MSO8\d{3}", "MSO8000", 4, 16, 2e9, 10e9, 500e6, _BW20_250),
    _m(r"^DS8\d{3}-?R", "DS8000R", 4, 0, 2e9, 10e9, 500e6, _BW20_250),
    _m(r"^(DS|MSO)4\d{3}", "DS4000", 4, 16, 500e6, 4e9, 140e6, _BW20_100),
    _m(r"^DS6\d{3}", "DS6000", 4, 0, 1e9, 5e9, 140e6, _BW20_250),
    _m(r"^DS7\d{4}", "DS70000", 4, 0, 5e9, 20e9, 2e9, _BW20_250),
    _m(r"^DS8\d{4}", "DS80000", 4, 0, 13e9, 40e9, 4e9, ("OFF", "500M", "1G")),
    _m(r"^DS1\d{3}Z-?E", "DS1000ZE", 2, 0, 200e6, 1e9, 24e6, _BW20),
]


def resolve_model(model: str) -> Optional[ModelSpec]:
    """Return the :class:`ModelSpec` for an *IDN? model string, or None."""
    key = (model or "").strip().upper()
    for pattern, spec in MODEL_TABLE:
        if pattern.search(key):
            return spec
    return None


def _guess_channels(model: str, default: int) -> int:
    digits = re.findall(r"\d", model or "")
    if digits and digits[-1] in "2468":
        return int(digits[-1])
    return default


# --------------------------------------------------------------------------- #
# Base driver
# --------------------------------------------------------------------------- #


class RigolModernScopeBase(BaseEquipment):
    """Driver for Rigol scopes that speak the modern ``:WAVeform``/``:MEASure:ITEM`` tree.

    Subclasses only change :attr:`DEFAULT_FAMILY` / :attr:`MODEL` (used when the
    ``*IDN?`` model string is not in :data:`MODEL_TABLE`).  Everything else is
    driven by the resolved :class:`ModelSpec` and :class:`FamilySpec`.

    ``get_measurement(channel)`` (acquisition-engine hook) accepts
    ``CH1``, ``1``, ``CHAN1``, ``CH1:VPP``, ``CH2:FREQ``, ``MATH1:VRMS`` ...
    A bare channel (``CH1``) means **VAVG** (mean of the record): it is the
    closest analogue to a DC voltmeter reading and what a slow logger usually
    wants; ask for ``CH1:VRMS`` explicitly for AC quantities.
    """

    MODEL = "DHO800"
    DEFAULT_FAMILY = "DHO800"
    DEFAULT_ANALOG_CHANNELS = 4
    DEFAULT_DIGITAL_CHANNELS = 0
    WAVEFORM_TIMEOUT_MS = 30000
    SCREENSHOT_TIMEOUT_MS = 30000

    def __init__(self, resource_manager, resource_string: str):
        super().__init__(resource_manager, resource_string)
        self.manufacturer = "Rigol"
        self.model = self.MODEL
        self.serial_number: Optional[str] = None
        self.firmware_version: Optional[str] = None
        self.spec: ModelSpec = resolve_model(self.MODEL) or self._default_spec(self.MODEL)
        self.family: FamilySpec = self.spec.family_spec
        self.num_channels = self.spec.analog_channels
        self.num_digital = self.spec.digital_channels
        self._io_lock = asyncio.Lock()
        self._last_waveform: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------ #
    # Identity
    # ------------------------------------------------------------------ #

    def _default_spec(self, model: str) -> ModelSpec:
        return ModelSpec(
            model=model or self.MODEL,
            family=self.DEFAULT_FAMILY,
            analog_channels=_guess_channels(model, self.DEFAULT_ANALOG_CHANNELS),
            digital_channels=self.DEFAULT_DIGITAL_CHANNELS,
            bandwidth_hz=0.0,
            max_sample_rate=0.0,
            max_memory_depth=0.0,
            note="Model not in table; family defaults used",
        )

    def _apply_model(self, model: str) -> ModelSpec:
        spec = resolve_model(model)
        if spec is None:
            spec = self._default_spec(model)
            logger.warning(f"Unknown Rigol scope model {model!r}; using {self.DEFAULT_FAMILY} defaults")
        self.spec = spec
        self.family = spec.family_spec
        self.num_channels = spec.analog_channels
        self.num_digital = spec.digital_channels
        return spec

    def _parse_idn(self, idn: str) -> Dict[str, Optional[str]]:
        parts = [p.strip() for p in idn.split(",")]
        info = {
            "manufacturer": parts[0] if len(parts) > 0 and parts[0] else self.manufacturer,
            "model": parts[1] if len(parts) > 1 and parts[1] else self.model,
            "serial": parts[2] if len(parts) > 2 and parts[2] else None,
            "firmware": parts[3] if len(parts) > 3 and parts[3] else None,
        }
        if info["model"] != self.model or self.spec.bandwidth_hz == 0.0:
            self._apply_model(info["model"] or self.model)
        self.model = info["model"] or self.model
        self.serial_number = info["serial"]
        self.firmware_version = info["firmware"]
        return info

    async def get_info(self) -> EquipmentInfo:
        idn = await self._query("*IDN?")
        info = self._parse_idn(idn)
        return EquipmentInfo(
            id=generate_equipment_id(self.resource_string, "scope_"),
            type=EquipmentType.OSCILLOSCOPE,
            manufacturer=info["manufacturer"] or self.manufacturer,
            model=info["model"] or self.model,
            serial_number=info["serial"],
            connection_type=self._determine_connection_type(),
            resource_string=self.resource_string,
        )

    def _capabilities(self) -> Dict[str, Any]:
        spec, fam = self.spec, self.family
        return {
            "family": fam.name,
            "programming_guide": fam.programming_guide,
            "num_channels": spec.analog_channels,
            "num_digital": spec.digital_channels,
            "bandwidth": spec.bandwidth_hz,
            "sample_rate": spec.max_sample_rate,
            "memory_depth": spec.max_memory_depth,
            "bandwidth_limits": list(spec.bw_limits),
            "has_ext_trigger": spec.has_ext_trigger,
            "autoset_command": fam.autoset_command,
            "measure_style": fam.measure_style,
            "measurement_items": list(MEASURE_ITEMS),
            "acquisition_types": list(fam.acquisition_types),
            "waveform_modes": ["NORMal", "MAXimum", "RAW"],
            "waveform_formats": ["BYTE", "WORD"] if fam.supports_word_format else ["BYTE"],
            "max_points_per_read": fam.max_points_per_read,
            "screen_points": fam.screen_points,
            "screenshot_format": fam.screenshot_format,
            "supports_screenshot": True,
            "supports_digital": spec.digital_channels > 0 and fam.la_enable_cmd is not None,
            "supports_acquisition": True,
            "model_note": spec.note,
        }

    async def get_status(self) -> EquipmentStatus:
        try:
            idn = await self._query("*IDN?")
            info = self._parse_idn(idn)
            capabilities = self._capabilities()
            try:
                capabilities["trigger_status"] = await self.get_trigger_status()
            except Exception:
                pass
            return EquipmentStatus(
                id=self.cached_info.id if self.cached_info else "unknown",
                connected=self.connected,
                firmware_version=info["firmware"],
                capabilities=capabilities,
            )
        except Exception as e:
            return EquipmentStatus(
                id=self.cached_info.id if self.cached_info else "unknown",
                connected=False,
                error=str(e),
            )

    # ------------------------------------------------------------------ #
    # Dispatch
    # ------------------------------------------------------------------ #

    async def execute_command(self, command: str, parameters: dict) -> Any:
        parameters = dict(parameters or {})
        handlers = {
            # waveform
            "get_waveform": self.get_waveform,
            "get_waveform_raw": self.get_waveform_raw,
            "get_waveform_data": self.get_waveform_data,
            # vertical / horizontal
            "set_channel": self.set_channel,
            "get_channel": self.get_channel,
            "set_timebase": self.set_timebase,
            "get_timebase": self.get_timebase,
            # trigger
            "set_trigger": self.set_trigger,
            "get_trigger": self.get_trigger,
            "get_trigger_status": self.get_trigger_status,
            "force_trigger": self.force_trigger,
            "trigger_single": self.single,
            "single": self.single,
            "trigger_run": self.run,
            "run": self.run,
            "trigger_stop": self.stop,
            "stop": self.stop,
            "autoscale": self.autoscale,
            "autoset": self.autoscale,
            "clear": self.clear,
            # acquisition
            "set_acquisition": self.set_acquisition,
            "get_acquisition": self.get_acquisition,
            # measurements
            "get_measurements": self.get_measurements,
            "get_measurement": self.get_measurement,
            "get_readings": self.get_readings,
            # digital
            "set_digital": self.set_digital,
            "get_digital": self.get_digital,
            "set_digital_threshold": self.set_digital_threshold,
            # misc
            "get_screenshot": self.get_screenshot,
            "get_state": self.get_state,
            "reset": self.reset,
            "get_error": self.get_error,
            "clear_errors": self.clear_errors,
        }
        handler = handlers.get(command)
        if handler is None:
            raise ValueError(f"Unknown command: {command}")
        return await handler(**parameters)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _check_channel(self, channel: Any) -> int:
        try:
            ch = int(str(channel).upper().replace("CHAN", "").replace("CH", ""))
        except ValueError:
            raise ValueError(f"Invalid channel: {channel}")
        if ch < 1 or ch > self.num_channels:
            raise ValueError(
                f"Invalid channel: {channel} ({self.model} has channels 1..{self.num_channels})"
            )
        return ch

    def _normalize_source(self, source: Any, allow_digital: bool = True,
                          allow_math: bool = True, allow_extra: bool = True) -> str:
        """Map CH1 / 1 / CHAN1 / D3 / MATH1 / EXT / ACL to the SCPI source token."""
        text = str(source).strip().upper().replace(" ", "")
        if text.isdigit():
            return f"CHAN{self._check_channel(text)}"
        m = re.fullmatch(r"(?:CH|CHAN|CHANNEL)(\d+)", text)
        if m:
            return f"CHAN{self._check_channel(m.group(1))}"
        m = re.fullmatch(r"D(\d{1,2})", text)
        if m and allow_digital:
            if self.num_digital == 0:
                raise ValueError(f"{self.model} has no digital channels")
            if int(m.group(1)) >= self.num_digital:
                raise ValueError(f"Digital channel {text} out of range (D0..D{self.num_digital - 1})")
            return text
        m = re.fullmatch(r"MATH(\d?)", text)
        if m and allow_math:
            return f"MATH{m.group(1) or '1'}"
        if allow_extra:
            extra = {"EXT": "EXT", "EXTERNAL": "EXT", "EXT5": "EXT5",
                     "AC": "ACL", "ACL": "ACL", "ACLINE": "ACL", "LINE": "ACL"}
            if text in extra:
                tok = extra[text]
                if tok == "ACL" and "AC" in self.family.edge_sources_extra:
                    return "AC"  # DS1000Z spells it AC
                return tok
        raise ValueError(f"Invalid source: {source}")

    async def _query_float(self, command: str) -> float:
        return parse_measurement(await self._query(command))

    async def _query_bool(self, command: str) -> bool:
        return (await self._query(command)).strip().upper() in ("1", "ON")

    def _read_block_sync(self, command: str, timeout_ms: int) -> bytes:
        """Write ``command`` and read one definite-length binary block."""
        inst = self.instrument
        if inst is None:
            raise RuntimeError("Equipment not connected")
        old_timeout = getattr(inst, "timeout", None)
        try:
            if timeout_ms and (old_timeout is None or timeout_ms > old_timeout):
                inst.timeout = timeout_ms
            inst.write(command)
            data = bytes(inst.read_raw())
            payload, missing = parse_tmc_block(data)
            guard = 0
            while missing > 0 and guard < 100000:
                more = inst.read_raw()
                if not more:
                    break
                data += bytes(more)
                payload, missing = parse_tmc_block(data)
                guard += 1
            return payload
        finally:
            if old_timeout is not None:
                try:
                    inst.timeout = old_timeout
                except Exception:
                    pass

    async def _query_block(self, command: str, timeout_ms: Optional[int] = None) -> bytes:
        await self._ensure_connected()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._read_block_sync, command, timeout_ms or self.WAVEFORM_TIMEOUT_MS
        )

    # ------------------------------------------------------------------ #
    # Run control
    # ------------------------------------------------------------------ #

    async def run(self) -> None:
        await self._write(":RUN")

    async def stop(self) -> None:
        await self._write(":STOP")

    async def single(self) -> None:
        await self._write(":SING")

    async def force_trigger(self) -> None:
        await self._write(":TFOR")

    async def clear(self) -> None:
        await self._write(":CLE")

    async def autoscale(self) -> str:
        """Front-panel AUTO (``:AUToscale`` or ``:AUToset`` depending on family)."""
        await self._write(self.family.autoset_command)
        return self.family.autoset_command

    async def reset(self) -> None:
        await self._write("*RST")
        await asyncio.sleep(1.0)

    # ------------------------------------------------------------------ #
    # Vertical
    # ------------------------------------------------------------------ #

    def _bw_limit_token(self, value: Any) -> str:
        if isinstance(value, bool):
            return "20M" if value else "OFF"
        if isinstance(value, (int, float)):
            if value <= 0:
                return "OFF"
            return f"{int(round(value / 1e9))}G" if value >= 1e9 else f"{int(round(value / 1e6))}M"
        text = str(value).strip().upper().replace("HZ", "")
        if text in ("", "0", "OFF", "FALSE", "NONE", "FULL"):
            return "OFF"
        if text in ("ON", "TRUE", "1"):
            return "20M"
        if re.fullmatch(r"\d+(M|G)", text):
            return text
        raise ValueError(f"Invalid bandwidth limit: {value} (valid: {', '.join(self.spec.bw_limits)})")

    async def set_channel(
        self,
        channel: int = 1,
        scale: Optional[float] = None,
        offset: Optional[float] = None,
        coupling: Optional[str] = None,
        probe: Optional[float] = None,
        bandwidth_limit: Optional[Union[str, float, bool]] = None,
        enabled: Optional[bool] = None,
        invert: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Configure an analog channel; only the given parameters are written."""
        ch = self._check_channel(channel)
        pre = f":CHAN{ch}"
        if enabled is not None:
            await self._write(f"{pre}:DISP {_on_off(enabled)}")
        if probe is not None:
            probe = float(probe)
            if probe <= 0:
                raise ValueError("Probe ratio must be > 0")
            await self._write(f"{pre}:PROB {_fmt_num(probe)}")
        if coupling is not None:
            cpl = str(coupling).strip().upper()
            if cpl not in _COUPLINGS:
                raise ValueError(f"Invalid coupling: {coupling} (must be AC, DC or GND)")
            await self._write(f"{pre}:COUP {cpl}")
        if scale is not None:
            scale = float(scale)
            if scale <= 0:
                raise ValueError("Vertical scale must be > 0 V/div")
            await self._write(f"{pre}:SCAL {_fmt_num(scale)}")
        if offset is not None:
            await self._write(f"{pre}:OFFS {_fmt_num(float(offset))}")
        if bandwidth_limit is not None:
            token = self._bw_limit_token(bandwidth_limit)
            if self.spec.bw_limits and token not in self.spec.bw_limits and token != "OFF":
                raise ValueError(
                    f"Bandwidth limit {token} not available on {self.model} "
                    f"(valid: {', '.join(self.spec.bw_limits)})"
                )
            await self._write(f"{pre}:BWL {token}")
        if invert is not None:
            await self._write(f"{pre}:INV {_on_off(invert)}")
        return await self.get_channel(ch)

    async def get_channel(self, channel: int = 1) -> Dict[str, Any]:
        ch = self._check_channel(channel)
        pre = f":CHAN{ch}"
        result: Dict[str, Any] = {"channel": ch}
        result["enabled"] = await self._query_bool(f"{pre}:DISP?")
        result["scale"] = await self._query_float(f"{pre}:SCAL?")
        result["offset"] = await self._query_float(f"{pre}:OFFS?")
        result["coupling"] = (await self._query(f"{pre}:COUP?")).strip().upper()
        result["probe"] = await self._query_float(f"{pre}:PROB?")
        for key, cmd in (("bandwidth_limit", f"{pre}:BWL?"), ("invert", f"{pre}:INV?")):
            try:
                raw = (await self._query(cmd)).strip().upper()
                result[key] = raw in ("1", "ON") if key == "invert" else raw
            except Exception as e:
                logger.debug(f"{cmd} failed: {e}")
                result[key] = None
        return result

    # ------------------------------------------------------------------ #
    # Horizontal
    # ------------------------------------------------------------------ #

    async def set_timebase(
        self, scale: Optional[float] = None, offset: Optional[float] = None,
        mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        if mode is not None:
            key = str(mode).strip().upper()
            token = {"MAIN": "MAIN", "YT": "MAIN", "XY": "XY", "ROLL": "ROLL"}.get(key)
            if token is None:
                raise ValueError(f"Invalid timebase mode: {mode} (must be MAIN/YT, XY or ROLL)")
            await self._write(f":TIM:MODE {token}")
        if scale is not None:
            scale = float(scale)
            if scale <= 0:
                raise ValueError("Timebase scale must be > 0 s/div")
            await self._write(f":TIM:MAIN:SCAL {_fmt_num(scale)}")
        if offset is not None:
            await self._write(f":TIM:MAIN:OFFS {_fmt_num(float(offset))}")
        return await self.get_timebase()

    async def get_timebase(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "scale": await self._query_float(":TIM:MAIN:SCAL?"),
            "offset": await self._query_float(":TIM:MAIN:OFFS?"),
        }
        try:
            result["mode"] = (await self._query(":TIM:MODE?")).strip().upper()
        except Exception:
            result["mode"] = None
        return result

    # ------------------------------------------------------------------ #
    # Trigger
    # ------------------------------------------------------------------ #

    async def set_trigger(
        self,
        source: Optional[str] = None,
        level: Optional[float] = None,
        slope: Optional[str] = None,
        mode: Optional[str] = None,
        sweep: Optional[str] = None,
        coupling: Optional[str] = None,
        holdoff: Optional[float] = None,
        noise_reject: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Configure the (edge) trigger.

        ``mode`` is the trigger *type* (EDGE, PULSe, SLOPe, ...); ``sweep`` is
        AUTO / NORMal / SINGle.  Source/level/slope are written to the EDGE
        trigger, which is what every family shares.
        """
        if mode is not None:
            key = str(mode).strip().upper()
            key = _TRIGGER_MODE_ALIASES.get(key, key)
            if key not in _TRIGGER_MODES:
                raise ValueError(f"Invalid trigger mode: {mode}")
            await self._write(f":TRIG:MODE {key}")
        if sweep is not None:
            token = _SWEEP_MODES.get(str(sweep).strip().upper())
            if token is None:
                raise ValueError(f"Invalid trigger sweep: {sweep} (must be AUTO, NORMal or SINGle)")
            await self._write(f":TRIG:SWE {token}")
        if coupling is not None:
            cpl = str(coupling).strip().upper()
            cpl = {"HF": "HFReject", "HFREJECT": "HFReject", "LF": "LFReject", "LFREJECT": "LFReject"}.get(cpl, cpl)
            if cpl not in ("AC", "DC", "HFReject", "LFReject"):
                raise ValueError(f"Invalid trigger coupling: {coupling}")
            await self._write(f":TRIG:COUP {cpl}")
        if holdoff is not None:
            await self._write(f":TRIG:HOLD {_fmt_num(float(holdoff))}")
        if noise_reject is not None:
            await self._write(f":TRIG:NREJ {_on_off(noise_reject)}")
        if source is not None:
            src = self._normalize_source(source, allow_math=False)
            if src in ("EXT", "EXT5") and not self.spec.has_ext_trigger:
                raise ValueError(f"{self.model} has no external trigger input")
            await self._write(f":TRIG:EDGE:SOUR {src}")
        if slope is not None:
            token = _SLOPES.get(str(slope).strip().upper())
            if token is None:
                raise ValueError(f"Invalid trigger slope: {slope} (POSitive, NEGative or RFALl)")
            await self._write(f":TRIG:EDGE:SLOP {token}")
        if level is not None:
            await self._write(f":TRIG:EDGE:LEV {_fmt_num(float(level))}")
        return await self.get_trigger()

    async def get_trigger(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "mode": (await self._query(":TRIG:MODE?")).strip().upper(),
            "sweep": (await self._query(":TRIG:SWE?")).strip().upper(),
            "source": (await self._query(":TRIG:EDGE:SOUR?")).strip().upper(),
            "slope": (await self._query(":TRIG:EDGE:SLOP?")).strip().upper(),
            "level": await self._query_float(":TRIG:EDGE:LEV?"),
        }
        for key, cmd in (("coupling", ":TRIG:COUP?"), ("holdoff", ":TRIG:HOLD?")):
            try:
                raw = (await self._query(cmd)).strip()
                result[key] = float(raw) if key == "holdoff" else raw.upper()
            except Exception:
                result[key] = None
        try:
            result["status"] = await self.get_trigger_status()
        except Exception:
            result["status"] = None
        return result

    async def get_trigger_status(self) -> str:
        """``:TRIGger:STATus?`` -> TD, WAIT, RUN, AUTO, STOP (DS6000 adds FIN)."""
        return (await self._query(":TRIG:STAT?")).strip().upper()

    # ------------------------------------------------------------------ #
    # Acquisition
    # ------------------------------------------------------------------ #

    def _acq_type_token(self, mode: str) -> str:
        key = str(mode).strip().upper()
        aliases = {"NORM": "NORMal", "NORMAL": "NORMal", "AVER": "AVERages", "AVERAGE": "AVERages",
                   "AVERAGES": "AVERages", "PEAK": "PEAK", "PEAKDETECT": "PEAK", "HRES": "HRESolution",
                   "HRESOLUTION": "HRESolution", "HIGHRES": "HRESolution", "ULTRA": "ULTRa", "ULTR": "ULTRa"}
        token = aliases.get(key)
        if token is None or token not in self.family.acquisition_types:
            raise ValueError(
                f"Invalid acquisition mode: {mode} (valid on {self.family.name}: "
                f"{', '.join(self.family.acquisition_types)})"
            )
        return token

    async def set_acquisition(
        self, mode: Optional[str] = None, memory_depth: Optional[Union[int, float, str]] = None,
        averages: Optional[int] = None,
    ) -> Dict[str, Any]:
        if mode is not None:
            await self._write(f":ACQ:TYPE {self._acq_type_token(mode)}")
        if averages is not None:
            averages = int(averages)
            if averages < 2 or averages > 65536 or (averages & (averages - 1)):
                raise ValueError("Averages must be a power of two between 2 and 65536")
            await self._write(f":ACQ:AVER {averages}")
        if memory_depth is not None:
            if isinstance(memory_depth, str) and memory_depth.strip().upper() == "AUTO":
                await self._write(":ACQ:MDEP AUTO")
            else:
                depth = int(float(memory_depth))
                if depth < 1:
                    raise ValueError("Memory depth must be >= 1 point or AUTO")
                if self.spec.max_memory_depth and depth > self.spec.max_memory_depth:
                    raise ValueError(
                        f"Memory depth {depth} exceeds {self.model} maximum of "
                        f"{int(self.spec.max_memory_depth)} points"
                    )
                await self._write(f":ACQ:MDEP {depth}")
        return await self.get_acquisition()

    async def get_acquisition(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"mode": (await self._query(":ACQ:TYPE?")).strip().upper()}
        raw_depth = (await self._query(":ACQ:MDEP?")).strip().upper()
        result["memory_depth"] = raw_depth if raw_depth == "AUTO" else self._parse_depth(raw_depth)
        result["sample_rate"] = await self._query_float(":ACQ:SRAT?")
        try:
            result["averages"] = int(await self._query_float(":ACQ:AVER?"))
        except Exception:
            result["averages"] = None
        return result

    @staticmethod
    def _parse_depth(raw: str) -> Optional[float]:
        text = raw.strip().upper()
        m = re.fullmatch(r"([\d.]+(?:E[+-]?\d+)?)\s*([KMG]?)(?:PTS)?", text)
        if not m:
            return None
        value = float(m.group(1))
        return value * {"": 1, "K": 1e3, "M": 1e6, "G": 1e9}[m.group(2)]

    # ------------------------------------------------------------------ #
    # Measurements
    # ------------------------------------------------------------------ #

    async def _measure_item(self, item_key: str, source: str) -> float:
        item = MEASURE_ITEMS[item_key]
        if self.family.measure_style == "LEGACY":
            raw = await self._query(f":MEAS:{item}? {source}")
        else:
            raw = await self._query(f":MEAS:ITEM? {item},{source}")
        return parse_measurement(raw)

    async def get_measurements(self, channel: int = 1) -> Dict[str, float]:
        """Streaming hook: common voltage/time parameters for one channel."""
        ch = self._check_channel(channel)
        source = f"CHAN{ch}"
        measurements: Dict[str, float] = {}
        for key, item in _STREAM_ITEMS:
            try:
                measurements[key] = await self._measure_item(item, source)
            except Exception as e:
                logger.debug(f"Measurement {item} on {source} failed: {e}")
                measurements[key] = float("nan")
        return measurements

    async def get_readings(self, channel: int = 1) -> Dict[str, Any]:
        data = await self.get_measurements(channel)
        data["channel"] = channel
        return data

    def _parse_measure_channel(self, channel: str) -> Tuple[str, str]:
        text = (channel or "CH1").strip().upper()
        if ":" in text:
            src, item = text.split(":", 1)
        elif "." in text:
            src, item = text.split(".", 1)
        else:
            src, item = text, "VAVG"
        return self._normalize_source(src, allow_extra=False), normalize_measure_item(item)

    async def get_measurement(self, channel: str = "CH1") -> Dict[str, Any]:
        """Acquisition-engine hook.

        ``channel`` examples: ``CH1`` (= VAVG), ``CH1:VPP``, ``2:FREQ``,
        ``CHAN3:RISE``, ``MATH1:VRMS``, ``D0:FREQ`` (MSO models).  Invalid or
        unavailable measurements return NaN.
        """
        source, item_key = self._parse_measure_channel(channel)
        value = await self._measure_item(item_key, source)
        return {
            "value": value,
            "unit": measure_unit(item_key),
            "item": item_key,
            "source": source,
            "valid": not math.isnan(value),
        }

    # ------------------------------------------------------------------ #
    # Waveform transfer
    # ------------------------------------------------------------------ #

    def _waveform_mode_token(self, mode: str) -> str:
        token = _WAVEFORM_MODES.get(str(mode).strip().upper())
        if token is None:
            raise ValueError(f"Invalid waveform mode: {mode} (NORMal, MAXimum or RAW)")
        return token

    async def _setup_waveform_read(self, source: str, mode: str, fmt: str) -> None:
        await self._write(f":WAV:SOUR {source}")
        await self._write(f":WAV:MODE {mode}")
        await self._write(f":WAV:FORM {fmt}")

    async def _read_waveform_bytes(self, source: str, mode: str, fmt: str,
                                   points: Optional[int]) -> Tuple[Dict[str, float], bytes]:
        """Configure the :WAVeform subsystem, read the preamble and all data bytes."""
        if mode == "RAW" and self.family.raw_requires_stop:
            status = await self.get_trigger_status()
            if status != "STOP":
                await self.stop()
        await self._setup_waveform_read(source, mode, fmt)
        preamble = parse_preamble(await self._query(":WAV:PRE?"))
        bytes_per_point = 2 if fmt == "WORD" else 1

        if mode != "RAW":
            if points is not None and mode == "NORMal":
                # Not all families accept POINts in NORMal mode; ignore failures.
                try:
                    await self._write(f":WAV:POIN {int(points)}")
                except Exception:
                    pass
            data = await self._query_block(":WAV:DATA?")
            return preamble, data

        total = preamble["points"]
        if points is not None:
            total = min(total, int(points)) if total > 0 else int(points)
        if total <= 0:
            depth = self._parse_depth(await self._query(":ACQ:MDEP?"))
            total = int(depth or 0)
        if total <= 0:
            raise ValueError("Cannot determine memory depth for RAW waveform read")

        chunk = max(1, self.family.max_points_per_read // bytes_per_point)
        buf = bytearray()
        if self.family.raw_read_flow == "STATUS":
            # DS4000/DS6000: POINts + RESet/BEGin, poll STATus? until IDLE, END.
            await self._write(f":WAV:POIN {min(total, chunk)}")
            await self._write(":WAV:RES")
            await self._write(":WAV:BEG")
            guard = 0
            while guard < 100000:
                status = (await self._query(":WAV:STAT?")).strip().upper()
                block = await self._query_block(":WAV:DATA?")
                buf.extend(block)
                guard += 1
                if status.startswith("IDLE") or len(buf) >= total * bytes_per_point or not block:
                    break
            await self._write(":WAV:END")
        else:
            # Modern families: STARt/STOP windows, each at most max_points_per_read.
            start = 1
            while start <= total:
                stop = min(start + chunk - 1, total)
                await self._write(f":WAV:STAR {start}")
                await self._write(f":WAV:STOP {stop}")
                block = await self._query_block(":WAV:DATA?")
                if not block:
                    break
                buf.extend(block)
                start = stop + 1
        data = bytes(buf[: total * bytes_per_point])
        return preamble, data

    async def capture_waveform(
        self, channel: Any = 1, mode: str = "NORMal", points: Optional[int] = None,
        format: str = "BYTE",
    ) -> Tuple[WaveformData, np.ndarray, np.ndarray]:
        """Read a waveform and scale it; returns (metadata, time_s, volts)."""
        source = self._normalize_source(channel, allow_extra=False)
        mode_token = self._waveform_mode_token(mode)
        fmt = str(format).strip().upper()
        if fmt not in ("BYTE", "WORD"):
            raise ValueError("Waveform format must be BYTE or WORD")
        if fmt == "WORD" and not self.family.supports_word_format:
            fmt = "BYTE"
        if source.startswith("MATH") and mode_token != "NORMal":
            mode_token = "NORMal"  # guides: MATH sources only support NORMal

        async with self._io_lock:
            preamble, data = await self._read_waveform_bytes(source, mode_token, fmt, points)
            time_scale = await self._query_float(":TIM:MAIN:SCAL?")
            if source.startswith("CHAN"):
                volt_scale = await self._query_float(f":{source}:SCAL?")
                volt_offset = await self._query_float(f":{source}:OFFS?")
            else:
                volt_scale = preamble["y_increment"] * 25.0
                volt_offset = 0.0

        volts = raw_to_volts(data, preamble, fmt)
        n = len(volts)
        x_inc = preamble["x_increment"]
        times = preamble["x_origin"] + (np.arange(n, dtype=np.float64) - preamble["x_reference"]) * x_inc
        sample_rate = 1.0 / x_inc if x_inc > 0 else (self.spec.max_sample_rate or 1e9)

        channel_number = int(re.sub(r"\D", "", source) or 0)
        meta = WaveformData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            channel=channel_number,
            sample_rate=sample_rate,
            time_scale=time_scale,
            voltage_scale=volt_scale,
            voltage_offset=volt_offset,
            num_samples=n,
            data_id=f"waveform_{uuid.uuid4().hex[:8]}",
        )
        self._last_waveform = {
            "meta": meta, "time": times, "voltage": volts, "raw": data,
            "preamble": preamble, "source": source, "mode": mode_token, "format": fmt,
        }
        return meta, times, volts

    async def get_waveform(self, channel: Any = 1, mode: str = "NORMal",
                           points: Optional[int] = None, format: str = "BYTE") -> WaveformData:
        """Scope-UI hook: same return type as ``rigol_scope.RigolDS1104.get_waveform``.

        The scaled samples of the most recent capture are kept in
        ``self.last_waveform`` (``time``/``voltage`` numpy arrays) so callers
        that want the data without a second transfer can read them.
        """
        meta, _, _ = await self.capture_waveform(channel, mode, points, format)
        return meta

    async def get_waveform_raw(self, channel: Any = 1, mode: str = "NORMal",
                               points: Optional[int] = None) -> bytes:
        """Raw BYTE-format sample codes (TMC header stripped)."""
        source = self._normalize_source(channel, allow_extra=False)
        mode_token = self._waveform_mode_token(mode)
        async with self._io_lock:
            _, data = await self._read_waveform_bytes(source, mode_token, "BYTE", points)
        return data

    async def get_waveform_data(self, channel: Any = 1, mode: str = "NORMal",
                                points: Optional[int] = None, format: str = "BYTE") -> Dict[str, Any]:
        """JSON-friendly waveform: metadata plus time/voltage lists."""
        meta, times, volts = await self.capture_waveform(channel, mode, points, format)
        pre = self._last_waveform["preamble"] if self._last_waveform else {}
        return {
            "equipment_id": meta.equipment_id,
            "channel": meta.channel,
            "source": self._last_waveform["source"] if self._last_waveform else None,
            "mode": mode,
            "sample_rate": meta.sample_rate,
            "time_scale": meta.time_scale,
            "voltage_scale": meta.voltage_scale,
            "voltage_offset": meta.voltage_offset,
            "num_samples": meta.num_samples,
            "x_origin": pre.get("x_origin"),
            "x_increment": pre.get("x_increment"),
            "y_increment": pre.get("y_increment"),
            "data_id": meta.data_id,
            "time": times.tolist(),
            "voltage": volts.tolist(),
        }

    @property
    def last_waveform(self) -> Optional[Dict[str, Any]]:
        return self._last_waveform

    # ------------------------------------------------------------------ #
    # Digital channels (MSO models)
    # ------------------------------------------------------------------ #

    def _require_digital(self) -> None:
        if self.num_digital == 0 or self.family.la_enable_cmd is None:
            raise ValueError(f"{self.model} has no digital (LA) channels")

    async def set_digital(self, enabled: bool = True,
                          channels: Optional[Sequence[Union[int, str]]] = None) -> Dict[str, Any]:
        """Enable/disable the logic analyzer and optionally individual D<n> lines."""
        self._require_digital()
        await self._write(f"{self.family.la_enable_cmd} {_on_off(enabled)}")
        if channels:
            for item in channels:
                d = self._normalize_source(item, allow_math=False, allow_extra=False)
                if not d.startswith("D"):
                    raise ValueError(f"{item} is not a digital channel")
                await self._write(f"{self.family.la_channel_cmd} {d},{_on_off(enabled)}")
        return await self.get_digital()

    async def get_digital(self) -> Dict[str, Any]:
        self._require_digital()
        result: Dict[str, Any] = {"enabled": await self._query_bool(f"{self.family.la_enable_cmd}?")}
        channels: Dict[str, bool] = {}
        for n in range(self.num_digital):
            try:
                channels[f"D{n}"] = await self._query_bool(f"{self.family.la_channel_cmd}? D{n}")
            except Exception:
                channels[f"D{n}"] = False
        result["channels"] = channels
        return result

    async def set_digital_threshold(self, pod: int = 1, threshold: float = 1.4) -> float:
        """``:LA:POD<n>:THReshold`` (POD1 = D0-D7, POD2 = D8-D15)."""
        self._require_digital()
        pod = int(pod)
        if pod not in (1, 2):
            raise ValueError("Pod must be 1 (D0-D7) or 2 (D8-D15)")
        threshold = float(threshold)
        if not -20.0 <= threshold <= 20.0:
            raise ValueError("Threshold must be within -20 V .. +20 V")
        await self._write(f":LA:POD{pod}:THR {_fmt_num(threshold)}")
        return await self._query_float(f":LA:POD{pod}:THR?")

    # ------------------------------------------------------------------ #
    # Screenshot / state / errors
    # ------------------------------------------------------------------ #

    async def get_screenshot(self, format: Optional[str] = None) -> bytes:
        """Return the screen image bytes (PNG or BMP depending on family/format)."""
        query = self.family.screenshot_query
        if format is not None:
            fmt = str(format).strip().upper()
            if fmt not in tuple(f.upper() for f in self.family.screenshot_formats):
                raise ValueError(
                    f"{self.family.name} screenshot formats: {', '.join(self.family.screenshot_formats)}"
                )
            if self.family.name == "DS1000ZE":
                query = f":DISP:DATA? ON,OFF,{fmt}"
            elif len(self.family.screenshot_formats) > 1:
                query = f":DISP:DATA? {fmt}"
        async with self._io_lock:
            data = await self._query_block(query, self.SCREENSHOT_TIMEOUT_MS)
        return data

    async def get_state(self) -> Dict[str, Any]:
        """Snapshot for the state capture/restore system."""
        state: Dict[str, Any] = {"model": self.model, "family": self.family.name, "channels": {}}
        for ch in range(1, self.num_channels + 1):
            try:
                state["channels"][str(ch)] = await self.get_channel(ch)
            except Exception as e:
                state["channels"][str(ch)] = {"error": str(e)}
        for key, coro in (("timebase", self.get_timebase()), ("trigger", self.get_trigger()),
                          ("acquisition", self.get_acquisition())):
            try:
                state[key] = await coro
            except Exception as e:
                state[key] = {"error": str(e)}
        if self.num_digital and self.family.la_enable_cmd:
            try:
                state["digital"] = await self.get_digital()
            except Exception:
                state["digital"] = None
        return state

    async def get_error(self) -> Dict[str, Any]:
        raw = await self._query(":SYST:ERR?")
        code_str, _, message = raw.partition(",")
        try:
            code = int(float(code_str.strip()))
        except ValueError:
            code = None
        return {"code": code, "message": message.strip().strip('"'), "raw": raw}


# --------------------------------------------------------------------------- #
# Family subclasses (defaults used only when the model is not in MODEL_TABLE)
# --------------------------------------------------------------------------- #


class RigolDHO800(RigolModernScopeBase):
    """DHO802/804/812/814 and DHO914(S)/924(S). 12-bit, ``:AUToset``."""
    MODEL = "DHO804"
    DEFAULT_FAMILY = "DHO800"
    DEFAULT_ANALOG_CHANNELS = 4


class RigolDHO1000(RigolModernScopeBase):
    """DHO1072..DHO1204 and DHO4204/4404/4804 (one shared programming guide)."""
    MODEL = "DHO1204"
    DEFAULT_FAMILY = "DHO1000"
    DEFAULT_ANALOG_CHANNELS = 4


class RigolDHO5000(RigolModernScopeBase):
    """DHO5054/5058/5104/5108 and MHO5054/5056/5104/5106 (4/6/8 channels)."""
    MODEL = "DHO5104"
    DEFAULT_FAMILY = "DHO5000"
    DEFAULT_ANALOG_CHANNELS = 4


class RigolMHO900(RigolModernScopeBase):
    """MHO934/954/984, MHO98 and MHO2024/2034 (same tree as DHO800, plus LA)."""
    MODEL = "MHO984"
    DEFAULT_FAMILY = "MHO900"
    DEFAULT_ANALOG_CHANNELS = 4
    DEFAULT_DIGITAL_CHANNELS = 16


class RigolMSO5000(RigolModernScopeBase):
    """MSO5072..MSO5354 and MSO5152-E. ``:AUToscale``, BMP screenshots."""
    MODEL = "MSO5074"
    DEFAULT_FAMILY = "MSO5000"
    DEFAULT_ANALOG_CHANNELS = 4
    DEFAULT_DIGITAL_CHANNELS = 16


class RigolMSO7000(RigolModernScopeBase):
    """MSO7014..MSO7054 and DS7014..DS7054."""
    MODEL = "MSO7054"
    DEFAULT_FAMILY = "MSO7000"
    DEFAULT_ANALOG_CHANNELS = 4
    DEFAULT_DIGITAL_CHANNELS = 16


class RigolMSO8000(RigolModernScopeBase):
    """MSO8064/8104/8204 and MSO8074A/8154A/8204A/8304A. PNG screenshots."""
    MODEL = "MSO8204"
    DEFAULT_FAMILY = "MSO8000"
    DEFAULT_ANALOG_CHANNELS = 4
    DEFAULT_DIGITAL_CHANNELS = 16


class RigolDS8000R(RigolModernScopeBase):
    """DS8034-R / DS8104-R / DS8204-R rack scopes (MSO5000-style tree, no LA)."""
    MODEL = "DS8204-R"
    DEFAULT_FAMILY = "DS8000R"
    DEFAULT_ANALOG_CHANNELS = 4


class RigolDS4000(RigolModernScopeBase):
    """DS4014E/DS4024E and DS/MSO4000. Legacy ``:MEASure:<item>?`` and RESet/BEGin RAW flow."""
    MODEL = "DS4024E"
    DEFAULT_FAMILY = "DS4000"
    DEFAULT_ANALOG_CHANNELS = 4


class RigolDS6000(RigolModernScopeBase):
    """DS6062/6064/6102/6104 (CHM programming manual)."""
    MODEL = "DS6104"
    DEFAULT_FAMILY = "DS6000"
    DEFAULT_ANALOG_CHANNELS = 4


class RigolDS70000(RigolModernScopeBase):
    """DS70304 / DS70504 (``:AUToscale``; otherwise the DHO-style tree)."""
    MODEL = "DS70504"
    DEFAULT_FAMILY = "DS70000"
    DEFAULT_ANALOG_CHANNELS = 4


class RigolDS80000(RigolDS70000):
    """DS80604..DS81304: same tree as DS70000 but AUTO is ``:AUToset``."""
    MODEL = "DS81304"
    DEFAULT_FAMILY = "DS80000"


class RigolDS1000ZE(RigolModernScopeBase):
    """DS1102Z-E / DS1202Z-E (2 channels, 250 kpts per RAW read)."""
    MODEL = "DS1202Z-E"
    DEFAULT_FAMILY = "DS1000ZE"
    DEFAULT_ANALOG_CHANNELS = 2


__all__ = [
    "FAMILIES",
    "FamilySpec",
    "MEASURE_ITEMS",
    "MODEL_TABLE",
    "ModelSpec",
    "RigolDHO1000",
    "RigolDHO5000",
    "RigolDHO800",
    "RigolDS1000ZE",
    "RigolDS4000",
    "RigolDS6000",
    "RigolDS70000",
    "RigolDS80000",
    "RigolDS8000R",
    "RigolMHO900",
    "RigolMSO5000",
    "RigolMSO7000",
    "RigolMSO8000",
    "RigolModernScopeBase",
    "normalize_measure_item",
    "parse_measurement",
    "parse_preamble",
    "parse_tmc_block",
    "raw_to_volts",
    "resolve_model",
]


# Model keywords used by equipment.manager.find_keyword_driver (the manager orders
# the most specific classes first).
RigolDS1000ZE.MODEL_KEYWORDS = ('DS1202Z-E', 'DS1102Z-E')
RigolDS80000.MODEL_KEYWORDS = ('DS81304', 'DS81004', 'DS80804', 'DS80604')
RigolDS70000.MODEL_KEYWORDS = ('DS70504', 'DS70304')
RigolDS8000R.MODEL_KEYWORDS = ('DS8204-R', 'DS8104-R', 'DS8034-R', 'DS8000-R')
RigolMSO8000.MODEL_KEYWORDS = ('MSO8304A', 'MSO8204A', 'MSO8154A', 'MSO8074A', 'MSO8204', 'MSO8104', 'MSO8064', 'MSO8000')
RigolMSO7000.MODEL_KEYWORDS = ('MSO7054', 'MSO7034', 'MSO7024', 'MSO7014', 'DS7054', 'DS7034', 'DS7024', 'DS7014', 'MSO7000', 'DS7000')
RigolMSO5000.MODEL_KEYWORDS = ('MSO5152-E', 'MSO5354', 'MSO5204', 'MSO5104', 'MSO5102', 'MSO5074', 'MSO5072', 'MSO5000')
RigolDHO5000.MODEL_KEYWORDS = ('MHO5106', 'MHO5104', 'MHO5056', 'MHO5054', 'DHO5108', 'DHO5104', 'DHO5058', 'DHO5054', 'DHO5000', 'MHO5000')
RigolMHO900.MODEL_KEYWORDS = ('MHO984', 'MHO954', 'MHO934', 'MHO98', 'MHO2034', 'MHO2024', 'MHO900', 'MHO2000')
RigolDHO1000.MODEL_KEYWORDS = ('DHO4804', 'DHO4404', 'DHO4204', 'DHO1204', 'DHO1202', 'DHO1104', 'DHO1102', 'DHO1074', 'DHO1072', 'DHO1000', 'DHO4000')
RigolDHO800.MODEL_KEYWORDS = ('DHO924S', 'DHO924', 'DHO914S', 'DHO914', 'DHO814', 'DHO812', 'DHO804', 'DHO802', 'DHO800', 'DHO900')
RigolDS6000.MODEL_KEYWORDS = ('DS6104', 'DS6102', 'DS6064', 'DS6062', 'DS6000')
RigolDS4000.MODEL_KEYWORDS = ('DS4024E', 'DS4014E', 'MSO4054', 'MSO4034', 'MSO4024', 'MSO4014', 'DS4054', 'DS4034', 'DS4024', 'DS4014', 'DS4000', 'MSO4000')
