"""Rigol DG-series function / arbitrary waveform generator drivers.

Two SCPI dialects are covered:

``RigolDGBase`` - the "classic" DG tree shared by DG800, DG900, DG1000Z and
DG2000 (RIGOL "DG1000Z Programming Guide", "DG800 Programming Guide",
"DG900 Programming Guide", "DG2000 Programming Guide") and, with small
quirks, the older DG4000 and DG5000 (CHM programming guides).  Channel
parameters live under ``[:SOURce<n>]``, modulation under
``[:SOURce<n>][:MOD]`` (the ``:MOD`` node is mandatory on DG4000/DG5000 and
optional elsewhere, so the driver always sends it), outputs under
``:OUTPut<n>``.

``RigolDGProBase`` - the "Pro" platform (DG800 Pro / DG900 Pro, DG5000 Pro,
DG6000; RIGOL "DG800 Pro/DG900 Pro Programming Guide", "DG5000 Pro
Programming Guide", "DG6000 Programming Guide").  Same ``:SOURce<n>`` /
``:OUTPut<n>`` skeleton, but modulation is enabled per type
(``:SOURce<n>:AM:STATe`` - there is no ``:MOD:TYPe``), pulse parameters live
under ``:FUNCtion:PULSe``, arbitrary uploads use
``:TRACe:DATA:DAC16 <type>,<flag>,<data>`` and burst triggering moved to
``:TRIGger<n>``.

Not covered: DG70000 (a pure AWG with a sequencer-centric command set and no
:APPLy tree) and the legacy DG1022/DG1000 (non-SCPI style command set).

*IDN? returns ``Rigol Technologies,<model>,<serial>,<firmware>`` (classic) or
``RIGOL TECHNOLOGIES,<model>,<serial>,<firmware>`` (Pro).
"""

import asyncio
import logging
import math
import struct
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from shared.models.data import FunctionGeneratorData
from shared.models.equipment import EquipmentInfo, EquipmentStatus, EquipmentType

from .base import BaseEquipment, generate_equipment_id

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Waveform vocabulary
# --------------------------------------------------------------------------- #

# Canonical waveform codes used throughout LabLink.
WAVEFORMS: Tuple[str, ...] = ("SIN", "SQU", "RAMP", "PULS", "NOIS", "DC", "ARB", "HARM")

# Any user / instrument spelling -> canonical code.  Includes the strings the
# instruments return from :APPLy? and :FUNCtion? (SIN, SQU, RAMP, PULSE, NOISE,
# DC, USER on the classic tree; PULS, NOIS, ARB, HARM, SEQ on the Pro tree).
_WAVEFORM_ALIASES: Dict[str, str] = {
    "SIN": "SIN", "SINE": "SIN", "SINUSOID": "SIN", "SINUS": "SIN",
    "SQU": "SQU", "SQUARE": "SQU",
    "RAMP": "RAMP", "TRI": "RAMP", "TRIANGLE": "RAMP", "TRIANG": "RAMP",
    "PULS": "PULS", "PULSE": "PULS",
    "NOIS": "NOIS", "NOISE": "NOIS",
    "DC": "DC",
    "ARB": "ARB", "USER": "ARB", "ARBITRARY": "ARB", "CUSTOM": "ARB", "VOLATILE": "ARB",
    "HARM": "HARM", "HARMONIC": "HARM",
    "SEQ": "SEQ", "SEQUENCE": "SEQ",
}

# Canonical -> long SCPI keyword used with :APPLy:<kw> and :FUNCtion <kw>.
_APPLY_KEYWORDS_CLASSIC: Dict[str, str] = {
    "SIN": "SINusoid", "SQU": "SQUare", "RAMP": "RAMP", "PULS": "PULSe",
    "NOIS": "NOISe", "DC": "DC", "ARB": "USER", "HARM": "HARMonic",
}
_APPLY_KEYWORDS_PRO: Dict[str, str] = dict(_APPLY_KEYWORDS_CLASSIC, ARB="ARBitrary")

_AMPLITUDE_UNITS = ("VPP", "VRMS", "DBM")
_MODULATION_TYPES = ("AM", "FM", "PM", "ASK", "FSK", "PSK", "PWM")
_SWEEP_SPACINGS = {"LIN": "LINear", "LINEAR": "LINear", "LOG": "LOGarithmic",
                   "LOGARITHMIC": "LOGarithmic", "STE": "STEp", "STEP": "STEp"}
_BURST_MODES = {"TRIG": "TRIGgered", "TRIGGERED": "TRIGgered", "NCYC": "TRIGgered",
                "NCYCLE": "TRIGgered", "INF": "INFinity", "INFINITY": "INFinity",
                "INFINITE": "INFinity", "GAT": "GATed", "GATE": "GATed", "GATED": "GATed"}
_MOD_SHAPES = {"SIN": "SINusoid", "SINE": "SINusoid", "SQU": "SQUare", "SQUARE": "SQUare",
               "TRI": "TRIangle", "TRIANGLE": "TRIangle", "RAMP": "RAMP", "UPRAMP": "RAMP",
               "NRAMP": "NRAMp", "DNRAMP": "NRAMp", "NOIS": "NOISe", "NOISE": "NOISe",
               "ARB": "ARBitrary", "USER": "USER"}

# :OUTPut<n>:LOAD? reports HighZ as 9.9E37 (DG1000Z tree, Pro) or "INFINITY" (DG4000/DG5000).
_HIGHZ_THRESHOLD = 1e30
_MIN_FREQUENCY_HZ = 1e-6


def normalize_waveform(waveform: str) -> str:
    """Map any spelling of a waveform to its canonical LabLink code."""
    key = str(waveform).strip().strip('"').upper()
    if key in _WAVEFORM_ALIASES:
        return _WAVEFORM_ALIASES[key]
    raise ValueError(
        f"Unknown waveform '{waveform}'. Valid: {', '.join(WAVEFORMS)}"
    )


def parse_number(raw: Optional[str]) -> Optional[float]:
    """Parse a SCPI numeric reply; None for DEF/empty/unparseable."""
    if raw is None:
        return None
    text = str(raw).strip().strip('"').strip()
    if not text or text.upper().startswith("DEF"):
        return None
    try:
        value = float(text)
    except ValueError:
        numeric = ""
        for ch in text:
            if ch in "+-.0123456789eE":
                numeric += ch
            else:
                break
        try:
            value = float(numeric)
        except ValueError:
            return None
    if math.isnan(value):
        return None
    return value


def parse_bool(raw: Optional[str]) -> bool:
    """ON/OFF, 1/0 and the counter's RUN/STOP/SINGLE states -> bool."""
    if raw is None:
        return False
    key = str(raw).strip().strip('"').upper()
    return key not in ("", "0", "OFF", "FALSE")


def parse_apply_response(raw: str) -> Dict[str, Any]:
    """Parse ``"SQU,1.000000E+03,2.000000E+00,3.000000E+00,4.000000E+00"``.

    The five comma separated fields are waveform name, frequency (Hz),
    amplitude (Vpp), offset (Vdc) and phase (deg); absent items are ``DEF``
    (e.g. ``"NOISE,DEF,5.000000E+00,0.000000E+00,DEF"``).
    """
    parts = [p.strip() for p in raw.strip().strip('"').split(",")]
    while len(parts) < 5:
        parts.append("DEF")
    try:
        waveform = normalize_waveform(parts[0])
    except ValueError:
        waveform = parts[0].upper() or "UNKNOWN"
    return {
        "waveform": waveform,
        "frequency": parse_number(parts[1]),
        "amplitude": parse_number(parts[2]),
        "offset": parse_number(parts[3]),
        "phase": parse_number(parts[4]),
    }


def parse_load(raw: str) -> str:
    """Normalise :OUTPut:LOAD? replies to ``"50"`` style strings or ``"INF"``."""
    text = raw.strip().strip('"').upper()
    if text.startswith("INF") or text.startswith("HIGH"):
        return "INF"
    value = parse_number(text)
    if value is None:
        return text
    if value >= _HIGHZ_THRESHOLD:
        return "INF"
    return f"{value:g}"


def _fmt(value: Union[int, float]) -> str:
    """Compact numeric formatting for SCPI parameters."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.12g}"


def _on_off(enabled: bool) -> str:
    return "ON" if enabled else "OFF"


# --------------------------------------------------------------------------- #
# Model table
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ModelSpec:
    """Static limits for one generator model.

    ``amplitude_tiers_*`` are ``(upper_frequency_hz, max_vpp)`` pairs sorted by
    frequency; the first tier whose frequency bound is >= the set frequency
    applies.  ``max_frequency`` is keyed by canonical waveform code.
    """

    family: str
    channels: int
    max_frequency: Dict[str, float]
    amplitude_tiers_50: Tuple[Tuple[float, float], ...]
    amplitude_tiers_hiz: Tuple[Tuple[float, float], ...]
    min_vpp_50: float
    sample_rate: float
    arb_points: int
    has_counter: bool
    interfaces: Tuple[str, ...] = ("USB", "LAN")
    noise_bandwidth: Optional[float] = None
    notes: str = ""

    def max_amplitude(self, frequency: Optional[float], high_z: bool) -> float:
        tiers = self.amplitude_tiers_hiz if high_z else self.amplitude_tiers_50
        if frequency is None:
            return tiers[0][1]
        for bound, vpp in tiers:
            if frequency <= bound * (1 + 1e-9):
                return vpp
        return tiers[-1][1]


def _tiers(*pairs: Tuple[float, float]) -> Tuple[Tuple[float, float], ...]:
    return tuple(pairs)


def _double(tiers: Tuple[Tuple[float, float], ...]) -> Tuple[Tuple[float, float], ...]:
    """HighZ amplitude limit is twice the 50 Ohm limit on every family."""
    return tuple((f, v * 2) for f, v in tiers)


def _freqs(sin, squ, ramp, puls, arb, harm) -> Dict[str, float]:
    return {"SIN": sin, "SQU": squ, "RAMP": ramp, "PULS": puls, "ARB": arb,
            "HARM": harm, "NOIS": sin, "DC": sin}


_MHZ = 1e6
_KHZ = 1e3

# --- DG800 (DG800 Programming Guide Table 2-1; DG800 Datasheet p.7) ----------
# Odd model numbers (DG811/821/831) are single channel, the DG800-DCH option
# adds the second channel.  Amplitude: <=10 MHz 10 Vpp, <=30 MHz 5 Vpp,
# <=35 MHz 2.5 Vpp into 50 Ohm; 1 mVpp minimum.  125 MSa/s, 2 Mpts (8 Mpts opt.).
_DG800_AMP = _tiers((10 * _MHZ, 10.0), (30 * _MHZ, 5.0), (35 * _MHZ, 2.5))
_DG800_COMMON = dict(family="DG800", amplitude_tiers_50=_DG800_AMP,
                     amplitude_tiers_hiz=_double(_DG800_AMP), min_vpp_50=1e-3,
                     sample_rate=125 * _MHZ, arb_points=2_000_000, has_counter=True,
                     interfaces=("USB",), noise_bandwidth=100 * _MHZ)
# --- DG900 / DG2000 (DG900 & DG2000 Programming Guides Table 2-1; datasheets) --
# Identical frequency tables; DG2000 adds LAN (LXI).  Amplitude <=10 MHz 10 Vpp,
# <=30 MHz 5 Vpp, <=60 MHz 2.5 Vpp, >60 MHz 1 Vpp.  250 MSa/s, 16 Mpts.
_DG900_AMP = _tiers((10 * _MHZ, 10.0), (30 * _MHZ, 5.0), (60 * _MHZ, 2.5), (100 * _MHZ, 1.0))
_DG900_COMMON = dict(family="DG900", channels=2, amplitude_tiers_50=_DG900_AMP,
                     amplitude_tiers_hiz=_double(_DG900_AMP), min_vpp_50=1e-3,
                     sample_rate=250 * _MHZ, arb_points=16_000_000, has_counter=True,
                     interfaces=("USB",), noise_bandwidth=100 * _MHZ)
_DG2000_COMMON = dict(_DG900_COMMON, family="DG2000", interfaces=("USB", "LAN"))
# --- DG1000Z (DG1000Z Programming Guide Table 2-1; DG1000Z Datasheet) ----------
# Amplitude <=10 MHz 10 Vpp, <=30 MHz 5 Vpp, <=60 MHz 2.5 Vpp into 50 Ohm.
# Datasheet says 1.0 mVpp minimum, the programming guide says 2 mVpp - the
# guide's figure is used because the firmware clamps to it.  200 MSa/s.
_DG1000Z_AMP = _tiers((10 * _MHZ, 10.0), (30 * _MHZ, 5.0), (60 * _MHZ, 2.5))
_DG1000Z_COMMON = dict(family="DG1000Z", channels=2, amplitude_tiers_50=_DG1000Z_AMP,
                       amplitude_tiers_hiz=_double(_DG1000Z_AMP), min_vpp_50=2e-3,
                       sample_rate=200 * _MHZ, has_counter=True,
                       interfaces=("USB", "LAN"))
# --- DG4000 (DG4000 Datasheet specifications table) ----------------------------
# Amplitude <=20 MHz 10 Vpp, <=70 MHz 5 Vpp, <=120 MHz 2.5 Vpp, <=200 MHz 1 Vpp.
# 500 MSa/s, 16 kpts arb memory, 14 bit.
_DG4000_AMP = _tiers((20 * _MHZ, 10.0), (70 * _MHZ, 5.0), (120 * _MHZ, 2.5), (200 * _MHZ, 1.0))
_DG4000_COMMON = dict(family="DG4000", channels=2, amplitude_tiers_50=_DG4000_AMP,
                      amplitude_tiers_hiz=_double(_DG4000_AMP), min_vpp_50=1e-3,
                      sample_rate=500 * _MHZ, arb_points=16_384, has_counter=True,
                      interfaces=("USB", "LAN"))
# --- DG5000 (DG5000 Datasheet; DG5000 Programming Guide, DG5352 example) --------
# Datasheet: 5 mVpp to 10 Vpp into 50 Ohm, 1 GSa/s, 512 kpts editable.  Only
# the 70 MHz column survives PDF extraction; the guide gives DG5352 limits
# (sine 350 MHz, square 120 MHz, ramp 5 MHz, pulse 50 MHz, arb 50 MHz).  The
# 100/250 MHz models are interpolated from those two - treat as approximate.
_DG5000_AMP = _tiers((350 * _MHZ, 10.0))
_DG5000_COMMON = dict(family="DG5000", amplitude_tiers_50=_DG5000_AMP,
                      amplitude_tiers_hiz=_double(_DG5000_AMP), min_vpp_50=5e-3,
                      sample_rate=1e9, arb_points=524_288, has_counter=False,
                      interfaces=("USB", "LAN", "GPIB"))
# --- DG800 Pro / DG900 Pro (Pro Programming Guide Tables 3.64/3.66; datasheets) --
# 50 Ohm: <=50 MHz 10 Vpp, <=100 MHz 5 Vpp, <=200 MHz 2 Vpp; HighZ double.
_DGPRO_AMP = _tiers((50 * _MHZ, 10.0), (100 * _MHZ, 5.0), (200 * _MHZ, 2.0))
_DG800PRO_COMMON = dict(family="DG800Pro", amplitude_tiers_50=_DGPRO_AMP,
                        amplitude_tiers_hiz=_double(_DGPRO_AMP), min_vpp_50=1e-3,
                        sample_rate=625 * _MHZ, arb_points=2_000_000, has_counter=True,
                        interfaces=("USB", "LAN"), noise_bandwidth=250 * _MHZ)
_DG900PRO_COMMON = dict(_DG800PRO_COMMON, family="DG900Pro", channels=2,
                        sample_rate=1.25e9, arb_points=16_000_000)
# --- DG5000 Pro / DG6000 (guides Table 3.59/3.61; datasheets) -------------------
# 50 Ohm: <=100 MHz 10 Vpp, <=250 MHz 5 Vpp, <=350 MHz 2 Vpp, <=500 MHz 1 Vpp.
# Square 170 MHz with fast transition (120 MHz without), pulse 120 MHz,
# ramp 5 MHz, arb 100 MHz.  2.5 GSa/s.  No frequency counter commands.
_DG5KPRO_AMP = _tiers((100 * _MHZ, 10.0), (250 * _MHZ, 5.0), (350 * _MHZ, 2.0), (500 * _MHZ, 1.0))
_DG5000PRO_COMMON = dict(family="DG5000Pro", amplitude_tiers_50=_DG5KPRO_AMP,
                         amplitude_tiers_hiz=_double(_DG5KPRO_AMP), min_vpp_50=1e-3,
                         sample_rate=2.5e9, arb_points=64_000_000, has_counter=False,
                         interfaces=("USB", "LAN"))
_DG6000_COMMON = dict(_DG5000PRO_COMMON, family="DG6000", arb_points=256_000_000,
                      noise_bandwidth=500 * _MHZ)


def _spec(common: dict, **overrides) -> ModelSpec:
    return ModelSpec(**dict(common, **overrides))


MODEL_SPECS: Dict[str, ModelSpec] = {
    # DG800
    "DG811": _spec(_DG800_COMMON, channels=1, max_frequency=_freqs(10 * _MHZ, 5 * _MHZ, 200 * _KHZ, 5 * _MHZ, 5 * _MHZ, 5 * _MHZ)),
    "DG812": _spec(_DG800_COMMON, channels=2, max_frequency=_freqs(10 * _MHZ, 5 * _MHZ, 200 * _KHZ, 5 * _MHZ, 5 * _MHZ, 5 * _MHZ)),
    "DG821": _spec(_DG800_COMMON, channels=1, max_frequency=_freqs(25 * _MHZ, 10 * _MHZ, 500 * _KHZ, 10 * _MHZ, 10 * _MHZ, 10 * _MHZ)),
    "DG822": _spec(_DG800_COMMON, channels=2, max_frequency=_freqs(25 * _MHZ, 10 * _MHZ, 500 * _KHZ, 10 * _MHZ, 10 * _MHZ, 10 * _MHZ)),
    "DG831": _spec(_DG800_COMMON, channels=1, max_frequency=_freqs(35 * _MHZ, 10 * _MHZ, 1 * _MHZ, 10 * _MHZ, 10 * _MHZ, 15 * _MHZ)),
    "DG832": _spec(_DG800_COMMON, channels=2, max_frequency=_freqs(35 * _MHZ, 10 * _MHZ, 1 * _MHZ, 10 * _MHZ, 10 * _MHZ, 15 * _MHZ)),
    # DG900
    "DG952": _spec(_DG900_COMMON, max_frequency=_freqs(50 * _MHZ, 15 * _MHZ, 1.5 * _MHZ, 15 * _MHZ, 15 * _MHZ, 20 * _MHZ)),
    "DG972": _spec(_DG900_COMMON, max_frequency=_freqs(70 * _MHZ, 20 * _MHZ, 1.5 * _MHZ, 20 * _MHZ, 20 * _MHZ, 20 * _MHZ)),
    "DG992": _spec(_DG900_COMMON, max_frequency=_freqs(100 * _MHZ, 25 * _MHZ, 2 * _MHZ, 25 * _MHZ, 20 * _MHZ, 25 * _MHZ)),
    # DG2000
    "DG2052": _spec(_DG2000_COMMON, max_frequency=_freqs(50 * _MHZ, 15 * _MHZ, 1.5 * _MHZ, 15 * _MHZ, 15 * _MHZ, 20 * _MHZ)),
    "DG2072": _spec(_DG2000_COMMON, max_frequency=_freqs(70 * _MHZ, 20 * _MHZ, 1.5 * _MHZ, 20 * _MHZ, 20 * _MHZ, 20 * _MHZ)),
    "DG2102": _spec(_DG2000_COMMON, max_frequency=_freqs(100 * _MHZ, 25 * _MHZ, 2 * _MHZ, 25 * _MHZ, 20 * _MHZ, 25 * _MHZ)),
    # DG1000Z
    "DG1022Z": _spec(_DG1000Z_COMMON, arb_points=2_000_000, noise_bandwidth=25 * _MHZ,
                     max_frequency=_freqs(25 * _MHZ, 25 * _MHZ, 500 * _KHZ, 15 * _MHZ, 10 * _MHZ, 10 * _MHZ)),
    "DG1032Z": _spec(_DG1000Z_COMMON, arb_points=8_000_000, noise_bandwidth=30 * _MHZ,
                     max_frequency=_freqs(30 * _MHZ, 25 * _MHZ, 500 * _KHZ, 15 * _MHZ, 10 * _MHZ, 10 * _MHZ)),
    "DG1062Z": _spec(_DG1000Z_COMMON, arb_points=8_000_000, noise_bandwidth=60 * _MHZ,
                     max_frequency=_freqs(60 * _MHZ, 25 * _MHZ, 1 * _MHZ, 25 * _MHZ, 20 * _MHZ, 20 * _MHZ)),
    # DG4000
    "DG4062": _spec(_DG4000_COMMON, noise_bandwidth=60 * _MHZ,
                    max_frequency=_freqs(60 * _MHZ, 25 * _MHZ, 1 * _MHZ, 15 * _MHZ, 15 * _MHZ, 30 * _MHZ)),
    "DG4102": _spec(_DG4000_COMMON, noise_bandwidth=80 * _MHZ,
                    max_frequency=_freqs(100 * _MHZ, 40 * _MHZ, 3 * _MHZ, 25 * _MHZ, 25 * _MHZ, 50 * _MHZ)),
    "DG4162": _spec(_DG4000_COMMON, noise_bandwidth=120 * _MHZ,
                    max_frequency=_freqs(160 * _MHZ, 50 * _MHZ, 4 * _MHZ, 40 * _MHZ, 40 * _MHZ, 80 * _MHZ)),
    "DG4202": _spec(_DG4000_COMMON, noise_bandwidth=120 * _MHZ,
                    max_frequency=_freqs(200 * _MHZ, 60 * _MHZ, 5 * _MHZ, 50 * _MHZ, 50 * _MHZ, 100 * _MHZ)),
    # DG5000 (odd = single channel, even = dual channel)
    "DG5071": _spec(_DG5000_COMMON, channels=1, max_frequency=_freqs(70 * _MHZ, 70 * _MHZ, 3 * _MHZ, 50 * _MHZ, 50 * _MHZ, 70 * _MHZ)),
    "DG5072": _spec(_DG5000_COMMON, channels=2, max_frequency=_freqs(70 * _MHZ, 70 * _MHZ, 3 * _MHZ, 50 * _MHZ, 50 * _MHZ, 70 * _MHZ)),
    "DG5101": _spec(_DG5000_COMMON, channels=1, notes="square/ramp limits interpolated",
                    max_frequency=_freqs(100 * _MHZ, 100 * _MHZ, 3 * _MHZ, 50 * _MHZ, 50 * _MHZ, 100 * _MHZ)),
    "DG5102": _spec(_DG5000_COMMON, channels=2, notes="square/ramp limits interpolated",
                    max_frequency=_freqs(100 * _MHZ, 100 * _MHZ, 3 * _MHZ, 50 * _MHZ, 50 * _MHZ, 100 * _MHZ)),
    "DG5251": _spec(_DG5000_COMMON, channels=1, notes="square/ramp limits interpolated",
                    max_frequency=_freqs(250 * _MHZ, 120 * _MHZ, 5 * _MHZ, 50 * _MHZ, 50 * _MHZ, 250 * _MHZ)),
    "DG5252": _spec(_DG5000_COMMON, channels=2, notes="square/ramp limits interpolated",
                    max_frequency=_freqs(250 * _MHZ, 120 * _MHZ, 5 * _MHZ, 50 * _MHZ, 50 * _MHZ, 250 * _MHZ)),
    "DG5351": _spec(_DG5000_COMMON, channels=1, max_frequency=_freqs(350 * _MHZ, 120 * _MHZ, 5 * _MHZ, 50 * _MHZ, 50 * _MHZ, 250 * _MHZ)),
    "DG5352": _spec(_DG5000_COMMON, channels=2, max_frequency=_freqs(350 * _MHZ, 120 * _MHZ, 5 * _MHZ, 50 * _MHZ, 50 * _MHZ, 250 * _MHZ)),
    # DG800 Pro / DG900 Pro (IDN model strings are normalised: "DG822 Pro" -> "DG822PRO")
    "DG821PRO": _spec(_DG800PRO_COMMON, channels=1, max_frequency=_freqs(25 * _MHZ, 20 * _MHZ, 1 * _MHZ, 10 * _MHZ, 10 * _MHZ, 10 * _MHZ)),
    "DG822PRO": _spec(_DG800PRO_COMMON, channels=2, max_frequency=_freqs(25 * _MHZ, 20 * _MHZ, 1 * _MHZ, 10 * _MHZ, 10 * _MHZ, 10 * _MHZ)),
    "DG852PRO": _spec(_DG800PRO_COMMON, channels=2, max_frequency=_freqs(50 * _MHZ, 40 * _MHZ, 1 * _MHZ, 25 * _MHZ, 15 * _MHZ, 25 * _MHZ)),
    "DG902PRO": _spec(_DG900PRO_COMMON, max_frequency=_freqs(70 * _MHZ, 60 * _MHZ, 3 * _MHZ, 50 * _MHZ, 30 * _MHZ, 35 * _MHZ)),
    "DG912PRO": _spec(_DG900PRO_COMMON, max_frequency=_freqs(150 * _MHZ, 60 * _MHZ, 5 * _MHZ, 50 * _MHZ, 50 * _MHZ, 75 * _MHZ)),
    "DG922PRO": _spec(_DG900PRO_COMMON, max_frequency=_freqs(200 * _MHZ, 60 * _MHZ, 5 * _MHZ, 50 * _MHZ, 50 * _MHZ, 100 * _MHZ)),
    # DG5000 Pro (last digit = channel count)
    "DG5252PRO": _spec(_DG5000PRO_COMMON, channels=2, max_frequency=_freqs(250 * _MHZ, 170 * _MHZ, 5 * _MHZ, 120 * _MHZ, 100 * _MHZ, 125 * _MHZ)),
    "DG5254PRO": _spec(_DG5000PRO_COMMON, channels=4, max_frequency=_freqs(250 * _MHZ, 170 * _MHZ, 5 * _MHZ, 120 * _MHZ, 100 * _MHZ, 125 * _MHZ)),
    "DG5258PRO": _spec(_DG5000PRO_COMMON, channels=8, max_frequency=_freqs(250 * _MHZ, 170 * _MHZ, 5 * _MHZ, 120 * _MHZ, 100 * _MHZ, 125 * _MHZ)),
    "DG5352PRO": _spec(_DG5000PRO_COMMON, channels=2, max_frequency=_freqs(350 * _MHZ, 170 * _MHZ, 5 * _MHZ, 120 * _MHZ, 100 * _MHZ, 175 * _MHZ)),
    "DG5354PRO": _spec(_DG5000PRO_COMMON, channels=4, max_frequency=_freqs(350 * _MHZ, 170 * _MHZ, 5 * _MHZ, 120 * _MHZ, 100 * _MHZ, 175 * _MHZ)),
    "DG5358PRO": _spec(_DG5000PRO_COMMON, channels=8, max_frequency=_freqs(350 * _MHZ, 170 * _MHZ, 5 * _MHZ, 120 * _MHZ, 100 * _MHZ, 175 * _MHZ)),
    "DG5502PRO": _spec(_DG5000PRO_COMMON, channels=2, max_frequency=_freqs(500 * _MHZ, 170 * _MHZ, 5 * _MHZ, 120 * _MHZ, 100 * _MHZ, 250 * _MHZ)),
    "DG5504PRO": _spec(_DG5000PRO_COMMON, channels=4, max_frequency=_freqs(500 * _MHZ, 170 * _MHZ, 5 * _MHZ, 120 * _MHZ, 100 * _MHZ, 250 * _MHZ)),
    "DG5508PRO": _spec(_DG5000PRO_COMMON, channels=8, max_frequency=_freqs(500 * _MHZ, 170 * _MHZ, 5 * _MHZ, 120 * _MHZ, 100 * _MHZ, 250 * _MHZ)),
    # DG6000 (sine limit is the HBW output type; SND/AMP outputs stop at 350/500 MHz)
    "DG6052": _spec(_DG6000_COMMON, channels=2, max_frequency=_freqs(500 * _MHZ, 300 * _MHZ, 5 * _MHZ, 120 * _MHZ, 100 * _MHZ, 175 * _MHZ)),
    "DG6054": _spec(_DG6000_COMMON, channels=4, max_frequency=_freqs(500 * _MHZ, 300 * _MHZ, 5 * _MHZ, 120 * _MHZ, 100 * _MHZ, 175 * _MHZ)),
    "DG6102": _spec(_DG6000_COMMON, channels=2, max_frequency=_freqs(1e9, 300 * _MHZ, 5 * _MHZ, 120 * _MHZ, 100 * _MHZ, 250 * _MHZ)),
    "DG6104": _spec(_DG6000_COMMON, channels=4, max_frequency=_freqs(1e9, 300 * _MHZ, 5 * _MHZ, 120 * _MHZ, 100 * _MHZ, 250 * _MHZ)),
}


def normalize_model(model: str) -> str:
    """``"DG822 Pro"`` -> ``"DG822PRO"``; strips spaces, hyphens and quotes."""
    return "".join(ch for ch in str(model).upper() if ch.isalnum())


def lookup_model_spec(model: str, family: Optional[str] = None) -> Optional[ModelSpec]:
    """Find the spec for an *IDN? model string (exact, then prefix match)."""
    key = normalize_model(model)
    if key in MODEL_SPECS:
        return MODEL_SPECS[key]
    candidates = [k for k in MODEL_SPECS if key.startswith(k) or k.startswith(key)]
    if family:
        candidates = [k for k in candidates if MODEL_SPECS[k].family == family] or candidates
    if len(candidates) == 1:
        return MODEL_SPECS[candidates[0]]
    return None


# --------------------------------------------------------------------------- #
# Classic DG tree (DG800 / DG900 / DG1000Z / DG2000, DG4000, DG5000)
# --------------------------------------------------------------------------- #


class RigolDGBase(BaseEquipment):
    """Common implementation for Rigol DG generators using the classic tree."""

    # ---- per-family constants (overridden in subclasses) ------------------
    FAMILY = "DG1000Z"
    MODEL = "DG1000Z"
    DEFAULT_MODEL = "DG1062Z"          # spec used when *IDN? model is unknown
    APPLY_KEYWORDS: Dict[str, str] = _APPLY_KEYWORDS_CLASSIC
    FUNCTION_KEYWORDS: Dict[str, str] = _APPLY_KEYWORDS_CLASSIC
    # Root of the pulse parameter tree (":PULSe" classic, ":FUNCtion:PULSe" Pro).
    PULSE_ROOT = ":PULSe"
    # ":MOD" node between :SOURce<n> and AM/FM/PM (optional on DG1000Z tree,
    # mandatory on DG4000/DG5000, absent on the Pro platform).
    MOD_NODE = ":MOD"
    # Align-phase command: :PHASe:SYNChronize (DG800/900/1000Z/2000 and Pro) or
    # :PHASe:INITiate (DG4000/DG5000; also accepted by the DG1000Z tree).
    PHASE_ALIGN_CMD = ":PHASe:SYNChronize"
    # Whether :APPLy:PULSe takes <phase> as 4th parameter (DG4000/DG5000 take <delay>).
    PULSE_APPLY_HAS_PHASE = True
    # Burst modes accepted by :BURSt:MODE.
    BURST_MODES: Tuple[str, ...] = ("TRIGgered", "INFinity", "GATed")
    # How upload_arbitrary() transfers data:
    #   FLOAT     - :SOURce<n>:TRACe:DATA VOLATILE,<f>,<f>,...   (-1..1, DG1000Z)
    #   FLOAT_CH0 - :TRACe:DATA VOLATILE,<f>,...  no channel node (DG4000/DG5000)
    #   DAC16     - :SOURce<n>:TRACe:DATA:DAC16 VOLATILE,<CON|END>,#<block>  (DG800/900/2000)
    #   PRO       - :SOURce<n>:TRACe:DATA:DAC16 VOLTage,<HEADer|CONTinue|END>,<f>,...
    ARB_UPLOAD_FORMAT = "FLOAT"
    ARB_MIN_POINTS = 8
    ARB_MAX_POINTS_PER_WRITE = 16_384
    # Byte order of DAC16 binary blocks. Not stated in any guide; little-endian
    # matches the DDR word layout used by Rigol's own Ultra Station uploads.
    DAC16_BYTE_ORDER = "<"
    # Does the family document :FUNCtion:ARBitrary:MODE/:SRATe (sample-rate mode)?
    HAS_ARB_SAMPLE_RATE = False
    TIMEOUT_MS = 10000

    def __init__(self, resource_manager, resource_string: str):
        super().__init__(resource_manager, resource_string)
        self.manufacturer = "Rigol"
        self.model = self.MODEL
        self.serial_number: Optional[str] = None
        self.firmware_version: Optional[str] = None
        self.spec: ModelSpec = MODEL_SPECS[self.DEFAULT_MODEL]
        # Serialises multi-command sequences; BaseEquipment on newer branches already
        # provides a reentrant lock of this name, so only create one if it is missing.
        if not hasattr(self, "_io_lock"):
            self._io_lock = asyncio.Lock()
        # Locally cached settings used for validation (refreshed by queries).
        self._load: Dict[int, str] = {}
        self._unit: Dict[int, str] = {}

    # ------------------------------------------------------------------ #
    # Connection / identity
    # ------------------------------------------------------------------ #

    async def connect(self):
        """Open the VISA resource, verify *IDN? and resolve the model table entry."""
        async with self._lock:
            try:
                self._is_connecting = True
                self._refresh_resource_manager()
                if self.instrument is not None:
                    try:
                        self.instrument.close()
                    except Exception:
                        pass
                    self.instrument = None

                self.instrument = self.resource_manager.open_resource(self.resource_string)
                try:
                    self.instrument.read_termination = "\n"
                    self.instrument.write_termination = "\n"
                except Exception:
                    pass
                self.instrument.timeout = self.TIMEOUT_MS

                idn = await self._query("*IDN?")
                logger.info(f"Connected to Rigol function generator: {idn}")
                self._parse_idn(idn)
                self.connected = True
                self.cached_info = await self.get_info()
            except Exception as e:
                logger.error(f"Failed to connect to {self.resource_string}: {e}")
                self.connected = False
                raise
            finally:
                self._is_connecting = False

    def _parse_idn(self, idn: str) -> Dict[str, Optional[str]]:
        parts = [p.strip() for p in idn.split(",")]
        info = {
            "manufacturer": parts[0] if len(parts) > 0 and parts[0] else self.manufacturer,
            "model": parts[1] if len(parts) > 1 and parts[1] else self.model,
            "serial": parts[2] if len(parts) > 2 and parts[2] else None,
            "firmware": parts[3] if len(parts) > 3 and parts[3] else None,
        }
        self.model = info["model"] or self.model
        self.serial_number = info["serial"]
        self.firmware_version = info["firmware"]
        spec = lookup_model_spec(self.model, self.FAMILY)
        if spec is None:
            logger.warning(
                f"Unknown {self.FAMILY} model '{self.model}', using {self.DEFAULT_MODEL} limits"
            )
            spec = MODEL_SPECS[self.DEFAULT_MODEL]
        self.spec = spec
        return info

    async def get_info(self) -> EquipmentInfo:
        idn = await self._query("*IDN?")
        info = self._parse_idn(idn)
        return EquipmentInfo(
            id=generate_equipment_id(self.resource_string, "fgen_"),
            type=EquipmentType.FUNCTION_GENERATOR,
            manufacturer=info["manufacturer"] or self.manufacturer,
            model=info["model"] or self.model,
            serial_number=info["serial"],
            connection_type=self._determine_connection_type(),
            resource_string=self.resource_string,
        )

    def _capabilities(self) -> Dict[str, Any]:
        spec = self.spec
        return {
            "family": self.FAMILY,
            "channels": spec.channels,
            "waveforms": list(self.APPLY_KEYWORDS.keys()),
            "max_frequency": dict(spec.max_frequency),
            "min_frequency": _MIN_FREQUENCY_HZ,
            "max_amplitude_vpp_50ohm": spec.amplitude_tiers_50[0][1],
            "max_amplitude_vpp_highz": spec.amplitude_tiers_hiz[0][1],
            "amplitude_tiers_50ohm": [list(t) for t in spec.amplitude_tiers_50],
            "amplitude_tiers_highz": [list(t) for t in spec.amplitude_tiers_hiz],
            "min_amplitude_vpp_50ohm": spec.min_vpp_50,
            "sample_rate": spec.sample_rate,
            "arb_points": spec.arb_points,
            "arb_upload_format": self.ARB_UPLOAD_FORMAT,
            "has_counter": spec.has_counter,
            "noise_bandwidth": spec.noise_bandwidth,
            "amplitude_units": list(_AMPLITUDE_UNITS),
            "modulation_types": list(_MODULATION_TYPES),
            "sweep_spacings": ["LINear", "LOGarithmic", "STEp"],
            "burst_modes": list(self.BURST_MODES),
            "interfaces": list(spec.interfaces),
            "notes": spec.notes,
            "supports_acquisition": True,
            "supports_arbitrary_upload": True,
        }

    async def get_status(self) -> EquipmentStatus:
        try:
            idn = await self._query("*IDN?")
            info = self._parse_idn(idn)
            capabilities = self._capabilities()
            try:
                capabilities["outputs"] = {
                    ch: await self.get_output(ch) for ch in range(1, self.spec.channels + 1)
                }
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

    async def run_self_test(self) -> Optional[bool]:
        try:
            result = await self._query("*TST?")
            return result.strip() in ("0", "+0", "PASS")
        except Exception as e:
            logger.error(f"Self test failed on {self.resource_string}: {e}")
            return None

    async def reset(self) -> None:
        """*RST (outputs off, 1 kHz / 5 Vpp sine on every channel)."""
        await self._write("*RST")
        await asyncio.sleep(0.5)
        self._load.clear()
        self._unit.clear()

    # ------------------------------------------------------------------ #
    # Command dispatch
    # ------------------------------------------------------------------ #

    def _handlers(self) -> Dict[str, Any]:
        return {
            # waveform / basic parameters
            "apply": self.apply,
            "set_waveform": self.set_waveform,
            "get_waveform": self.get_waveform,
            "set_frequency": self.set_frequency,
            "get_frequency": self.get_frequency,
            "set_amplitude": self.set_amplitude,
            "get_amplitude": self.get_amplitude,
            "set_amplitude_unit": self.set_amplitude_unit,
            "get_amplitude_unit": self.get_amplitude_unit,
            "set_offset": self.set_offset,
            "get_offset": self.get_offset,
            "set_phase": self.set_phase,
            "get_phase": self.get_phase,
            "set_duty_cycle": self.set_duty_cycle,
            "get_duty_cycle": self.get_duty_cycle,
            "set_symmetry": self.set_symmetry,
            "get_symmetry": self.get_symmetry,
            "set_pulse": self.set_pulse,
            "get_pulse": self.get_pulse,
            # output
            "set_output": self.set_output,
            "get_output": self.get_output,
            "set_load": self.set_load,
            "get_load": self.get_load,
            "set_polarity": self.set_polarity,
            "get_polarity": self.get_polarity,
            # modulation / sweep / burst
            "set_modulation": self.set_modulation,
            "get_modulation": self.get_modulation,
            "set_sweep": self.set_sweep,
            "get_sweep": self.get_sweep,
            "set_burst": self.set_burst,
            "get_burst": self.get_burst,
            "trigger_burst": self.trigger_burst,
            # arbitrary / phase / counter
            "upload_arbitrary": self.upload_arbitrary,
            "set_arb_sample_rate": self.set_arb_sample_rate,
            "sync_phase": self.sync_phase,
            "get_counter": self.get_counter,
            "set_counter": self.set_counter,
            # readings / hooks
            "get_readings": self.get_readings,
            "get_measurement": self.get_measurement,
            "get_measurements": self.get_measurements,
            "get_state": self.get_state,
            # system
            "set_beeper": self.set_beeper,
            "beep": self.beep,
            "reset": self.reset,
            "self_test": self.run_self_test,
            "get_error": self.get_error,
            "clear_errors": self.clear_errors,
        }

    async def execute_command(self, command: str, parameters: dict) -> Any:
        """Dispatch a LabLink command name to the matching driver method."""
        parameters = dict(parameters or {})
        handler = self._handlers().get(command)
        if handler is None:
            raise ValueError(f"Unknown command: {command}")
        return await handler(**parameters)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _channel(self, channel: Any) -> int:
        """Accept 1, "1", "CH1", "ch2" ...; validate against the model's channel count."""
        if isinstance(channel, str):
            text = channel.strip().upper()
            if text.startswith("CH"):
                text = text[2:]
            if text.startswith("SOUR"):
                text = text.replace("SOURCE", "").replace("SOUR", "")
            try:
                ch = int(text)
            except ValueError:
                raise ValueError(f"Invalid channel '{channel}'")
        else:
            ch = int(channel)
        if not 1 <= ch <= self.spec.channels:
            raise ValueError(
                f"{self.model} has {self.spec.channels} channel(s); channel must be 1..{self.spec.channels}"
            )
        return ch

    def _src(self, channel: int) -> str:
        return f":SOURce{channel}"

    def _mod(self, channel: int) -> str:
        return f"{self._src(channel)}{self.MOD_NODE}"

    def _check_frequency(self, waveform: Optional[str], frequency: float) -> float:
        frequency = float(frequency)
        limit = self.spec.max_frequency.get(waveform or "SIN", self.spec.max_frequency["SIN"])
        if not _MIN_FREQUENCY_HZ <= frequency <= limit:
            raise ValueError(
                f"Frequency {frequency:g} Hz out of range for {self.model} "
                f"{waveform or 'SIN'}: {_MIN_FREQUENCY_HZ:g}..{limit:g} Hz"
            )
        return frequency

    def _high_z(self, channel: int) -> bool:
        return self._load.get(channel, "50") == "INF"

    def _check_amplitude(self, amplitude: float, unit: str, frequency: Optional[float], channel: int) -> float:
        amplitude = float(amplitude)
        if unit != "VPP":
            # Vrms / dBm limits depend on the waveform shape; only sanity check the sign.
            if unit == "VRMS" and amplitude <= 0:
                raise ValueError("Amplitude in Vrms must be > 0")
            return amplitude
        high_z = self._high_z(channel)
        max_vpp = self.spec.max_amplitude(frequency, high_z)
        min_vpp = self.spec.min_vpp_50 * (2 if high_z else 1)
        if not min_vpp <= amplitude <= max_vpp:
            load = "HighZ" if high_z else "50 Ohm"
            at = f" at {frequency:g} Hz" if frequency is not None else ""
            raise ValueError(
                f"Amplitude {amplitude:g} Vpp out of range for {self.model} into {load}{at}: "
                f"{min_vpp:g}..{max_vpp:g} Vpp"
            )
        return amplitude

    @staticmethod
    def _check_percent(value: float, name: str, lo: float = 0.0, hi: float = 100.0) -> float:
        value = float(value)
        if not lo <= value <= hi:
            raise ValueError(f"{name} must be {lo:g}..{hi:g} %")
        return value

    @staticmethod
    def _check_phase(phase: float) -> float:
        phase = float(phase)
        if not -360.0 <= phase <= 360.0:
            raise ValueError("Phase must be -360..360 degrees")
        return phase

    async def _query_number(self, cmd: str) -> Optional[float]:
        return parse_number(await self._query(cmd))

    async def _query_bool(self, cmd: str) -> bool:
        return parse_bool(await self._query(cmd))

    async def _write_raw(self, payload: bytes) -> None:
        """Send a raw byte string (used for #-prefixed binary blocks)."""
        await self._ensure_connected()
        if not self.instrument:
            raise RuntimeError("Equipment not connected")
        writer = getattr(self.instrument, "write_raw", None)
        if writer is None:
            raise RuntimeError("VISA session does not support binary writes")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, writer, payload)

    # ------------------------------------------------------------------ #
    # Waveform / basic parameters
    # ------------------------------------------------------------------ #

    def _apply_arguments(self, waveform: str, frequency, amplitude, offset, phase) -> List[str]:
        """Build the comma separated :APPLy argument list for the classic tree."""
        f = _fmt(frequency) if frequency is not None else "DEF"
        a = _fmt(amplitude) if amplitude is not None else "DEF"
        o = _fmt(offset) if offset is not None else "DEF"
        p = _fmt(phase) if phase is not None else "DEF"
        if waveform == "DC":
            # DG1000Z guide: ":SOUR1:APPL:DC 1,1,2" - first two are placeholders.
            return ["1", "1", o]
        if waveform == "NOIS":
            return [a, o]
        if waveform == "PULS" and not self.PULSE_APPLY_HAS_PHASE:
            return [f, a, o]
        return [f, a, o, p]

    async def apply(
        self,
        channel: Any = 1,
        waveform: str = "SIN",
        frequency: Optional[float] = None,
        amplitude: Optional[float] = None,
        offset: Optional[float] = None,
        phase: Optional[float] = None,
    ) -> FunctionGeneratorData:
        """One-shot ``:SOURce<n>:APPLy:<wave> <freq>,<amp>,<offset>,<phase>``.

        Omitted values are sent as ``DEF`` (instrument defaults: 1 kHz, 5 Vpp,
        0 V, 0 deg).  Amplitude is interpreted in the channel's current unit.
        """
        ch = self._channel(channel)
        wf = normalize_waveform(waveform)
        keyword = self.APPLY_KEYWORDS.get(wf)
        if keyword is None:
            raise ValueError(f"{wf} cannot be selected with :APPLy on {self.model}")
        if frequency is not None and wf not in ("DC", "NOIS"):
            frequency = self._check_frequency(wf, frequency)
        if amplitude is not None and wf != "DC":
            unit = self._unit.get(ch, "VPP")
            amplitude = self._check_amplitude(amplitude, unit, frequency, ch)
        if phase is not None:
            phase = self._check_phase(phase)
        if offset is not None:
            offset = float(offset)
        args = self._apply_arguments(wf, frequency, amplitude, offset, phase)
        async with self._io_lock:
            await self._write(f"{self._src(ch)}:APPLy:{keyword} {','.join(args)}")
        return await self.get_readings(ch)

    async def set_waveform(self, waveform: str, channel: Any = 1) -> str:
        """``:SOURce<n>:FUNCtion <shape>`` keeping the other parameters."""
        ch = self._channel(channel)
        wf = normalize_waveform(waveform)
        keyword = self.FUNCTION_KEYWORDS.get(wf)
        if keyword is None:
            raise ValueError(f"Waveform {wf} is not selectable on {self.model}")
        await self._write(f"{self._src(ch)}:FUNCtion {keyword}")
        return await self.get_waveform(ch)

    async def get_waveform(self, channel: Any = 1) -> str:
        ch = self._channel(channel)
        raw = await self._query(f"{self._src(ch)}:FUNCtion?")
        try:
            return normalize_waveform(raw)
        except ValueError:
            return raw.strip().upper()

    async def set_frequency(self, frequency: float, channel: Any = 1) -> float:
        """``:SOURce<n>:FREQuency <hz>`` validated against the model table."""
        ch = self._channel(channel)
        try:
            wf = await self.get_waveform(ch)
        except Exception:
            wf = "SIN"
        frequency = self._check_frequency(wf if wf in self.spec.max_frequency else "SIN", frequency)
        await self._write(f"{self._src(ch)}:FREQuency {_fmt(frequency)}")
        return await self.get_frequency(ch)

    async def get_frequency(self, channel: Any = 1) -> Optional[float]:
        ch = self._channel(channel)
        return await self._query_number(f"{self._src(ch)}:FREQuency?")

    async def set_amplitude(self, amplitude: float, unit: Optional[str] = None, channel: Any = 1) -> float:
        """``:SOURce<n>:VOLTage <value>`` (optionally switching the unit first)."""
        ch = self._channel(channel)
        if unit is not None:
            await self.set_amplitude_unit(unit, ch)
        unit_now = self._unit.get(ch)
        if unit_now is None:
            unit_now = await self.get_amplitude_unit(ch)
        try:
            frequency = await self.get_frequency(ch)
        except Exception:
            frequency = None
        amplitude = self._check_amplitude(amplitude, unit_now, frequency, ch)
        await self._write(f"{self._src(ch)}:VOLTage {_fmt(amplitude)}")
        return await self.get_amplitude(ch)

    async def get_amplitude(self, channel: Any = 1) -> Optional[float]:
        ch = self._channel(channel)
        return await self._query_number(f"{self._src(ch)}:VOLTage?")

    async def set_amplitude_unit(self, unit: str, channel: Any = 1) -> str:
        """``:SOURce<n>:VOLTage:UNIT {VPP|VRMS|DBM}`` (dBm needs a finite load)."""
        ch = self._channel(channel)
        key = str(unit).strip().upper().replace(" ", "")
        if key not in _AMPLITUDE_UNITS:
            raise ValueError("Amplitude unit must be VPP, VRMS or DBM")
        if key == "DBM" and self._high_z(ch):
            raise ValueError("dBm is not available while the output load is HighZ")
        await self._write(f"{self._src(ch)}:VOLTage:UNIT {key}")
        return await self.get_amplitude_unit(ch)

    async def get_amplitude_unit(self, channel: Any = 1) -> str:
        ch = self._channel(channel)
        raw = (await self._query(f"{self._src(ch)}:VOLTage:UNIT?")).strip().upper()
        unit = raw if raw in _AMPLITUDE_UNITS else "VPP"
        self._unit[ch] = unit
        return unit

    async def set_offset(self, offset: float, channel: Any = 1) -> float:
        """``:SOURce<n>:VOLTage:OFFSet <volts>``."""
        ch = self._channel(channel)
        offset = float(offset)
        limit = self.spec.max_amplitude(None, self._high_z(ch)) / 2.0
        if abs(offset) > limit:
            raise ValueError(f"Offset must be within +/-{limit:g} V for {self.model}")
        await self._write(f"{self._src(ch)}:VOLTage:OFFSet {_fmt(offset)}")
        return await self.get_offset(ch)

    async def get_offset(self, channel: Any = 1) -> Optional[float]:
        ch = self._channel(channel)
        return await self._query_number(f"{self._src(ch)}:VOLTage:OFFSet?")

    async def set_phase(self, phase: float, channel: Any = 1) -> float:
        """``:SOURce<n>:PHASe <degrees>``."""
        ch = self._channel(channel)
        phase = self._check_phase(phase)
        await self._write(f"{self._src(ch)}:PHASe {_fmt(phase)}")
        return await self.get_phase(ch)

    async def get_phase(self, channel: Any = 1) -> Optional[float]:
        ch = self._channel(channel)
        return await self._query_number(f"{self._src(ch)}:PHASe?")

    async def set_duty_cycle(self, duty_cycle: float, channel: Any = 1, waveform: Optional[str] = None) -> float:
        """Square (``:FUNCtion:SQUare:DCYCle``) or pulse (``:PULSe:DCYCle``) duty in %."""
        ch = self._channel(channel)
        duty = self._check_percent(duty_cycle, "Duty cycle")
        wf = normalize_waveform(waveform) if waveform else await self.get_waveform(ch)
        if wf == "PULS":
            await self._write(f"{self._src(ch)}{self.PULSE_ROOT}:DCYCle {_fmt(duty)}")
        elif wf == "SQU":
            await self._write(f"{self._src(ch)}:FUNCtion:SQUare:DCYCle {_fmt(duty)}")
        else:
            raise ValueError(f"Duty cycle applies to SQU or PULS, channel {ch} is {wf}")
        return await self.get_duty_cycle(ch, wf)

    async def get_duty_cycle(self, channel: Any = 1, waveform: Optional[str] = None) -> Optional[float]:
        ch = self._channel(channel)
        wf = normalize_waveform(waveform) if waveform else await self.get_waveform(ch)
        if wf == "PULS":
            return await self._query_number(f"{self._src(ch)}{self.PULSE_ROOT}:DCYCle?")
        if wf == "SQU":
            return await self._query_number(f"{self._src(ch)}:FUNCtion:SQUare:DCYCle?")
        return None

    async def set_symmetry(self, symmetry: float, channel: Any = 1) -> float:
        """Ramp symmetry ``:FUNCtion:RAMP:SYMMetry`` in %."""
        ch = self._channel(channel)
        symmetry = self._check_percent(symmetry, "Symmetry")
        await self._write(f"{self._src(ch)}:FUNCtion:RAMP:SYMMetry {_fmt(symmetry)}")
        return await self.get_symmetry(ch)

    async def get_symmetry(self, channel: Any = 1) -> Optional[float]:
        ch = self._channel(channel)
        return await self._query_number(f"{self._src(ch)}:FUNCtion:RAMP:SYMMetry?")

    async def set_pulse(
        self,
        width: Optional[float] = None,
        duty_cycle: Optional[float] = None,
        rise_time: Optional[float] = None,
        fall_time: Optional[float] = None,
        channel: Any = 1,
    ) -> Dict[str, Optional[float]]:
        """Pulse width (s), duty (%), leading/trailing edge times (s)."""
        ch = self._channel(channel)
        root = f"{self._src(ch)}{self.PULSE_ROOT}"
        if width is not None:
            width = float(width)
            if width <= 0:
                raise ValueError("Pulse width must be > 0 s")
            await self._write(f"{root}:WIDTh {_fmt(width)}")
        if duty_cycle is not None:
            await self._write(f"{root}:DCYCle {_fmt(self._check_percent(duty_cycle, 'Duty cycle'))}")
        if rise_time is not None:
            if float(rise_time) <= 0:
                raise ValueError("Rise time must be > 0 s")
            await self._write(f"{root}:TRANsition:LEADing {_fmt(float(rise_time))}")
        if fall_time is not None:
            if float(fall_time) <= 0:
                raise ValueError("Fall time must be > 0 s")
            await self._write(f"{root}:TRANsition:TRAiling {_fmt(float(fall_time))}")
        return await self.get_pulse(ch)

    async def get_pulse(self, channel: Any = 1) -> Dict[str, Optional[float]]:
        ch = self._channel(channel)
        root = f"{self._src(ch)}{self.PULSE_ROOT}"
        out: Dict[str, Optional[float]] = {}
        for key, cmd in (("width", "WIDTh"), ("duty_cycle", "DCYCle"),
                         ("rise_time", "TRANsition:LEADing"), ("fall_time", "TRANsition:TRAiling")):
            try:
                out[key] = await self._query_number(f"{root}:{cmd}?")
            except Exception as e:
                logger.debug(f"Pulse {key} query failed: {e}")
                out[key] = None
        return out

    # ------------------------------------------------------------------ #
    # Output
    # ------------------------------------------------------------------ #

    async def set_output(self, enabled: bool, channel: Any = 1) -> bool:
        """``:OUTPut<n> ON|OFF`` - called with False by the manager on disconnect."""
        ch = self._channel(channel)
        await self._write(f":OUTPut{ch} {_on_off(bool(enabled))}")
        return await self.get_output(ch)

    async def get_output(self, channel: Any = 1) -> bool:
        ch = self._channel(channel)
        return await self._query_bool(f":OUTPut{ch}?")

    async def set_load(self, impedance: Union[float, int, str], channel: Any = 1) -> str:
        """``:OUTPut<n>:LOAD {<1..10000 ohm>|INFinity}``; returns ``"50"`` or ``"INF"``."""
        ch = self._channel(channel)
        if isinstance(impedance, str):
            key = impedance.strip().upper().replace("OHM", "").replace("Ω", "").strip()
            if key in ("INF", "INFINITY", "HIGHZ", "HIGH_Z", "HIZ", "OPEN"):
                arg = "INFinity"
            elif key in ("MIN", "MAX"):
                arg = key
            else:
                arg = None
                impedance = float(key)
        else:
            arg = None
        if arg is None:
            ohms = int(round(float(impedance)))
            if not 1 <= ohms <= 10000:
                raise ValueError("Load impedance must be 1..10000 Ohm or INF (HighZ)")
            arg = str(ohms)
        await self._write(f":OUTPut{ch}:LOAD {arg}")
        return await self.get_load(ch)

    async def get_load(self, channel: Any = 1) -> str:
        ch = self._channel(channel)
        load = parse_load(await self._query(f":OUTPut{ch}:LOAD?"))
        self._load[ch] = load
        return load

    async def set_polarity(self, polarity: str = "NORMAL", channel: Any = 1) -> str:
        """``:OUTPut<n>:POLarity {NORMal|INVerted}``."""
        ch = self._channel(channel)
        key = str(polarity).strip().upper()
        if key in ("NORM", "NORMAL", "POS", "POSITIVE"):
            arg = "NORMal"
        elif key in ("INV", "INVERTED", "INVERT", "NEG", "NEGATIVE"):
            arg = "INVerted"
        else:
            raise ValueError("Polarity must be NORMAL or INVERTED")
        await self._write(f":OUTPut{ch}:POLarity {arg}")
        return await self.get_polarity(ch)

    async def get_polarity(self, channel: Any = 1) -> str:
        ch = self._channel(channel)
        raw = (await self._query(f":OUTPut{ch}:POLarity?")).strip().upper()
        return "INVERTED" if raw.startswith("INV") else "NORMAL"

    # ------------------------------------------------------------------ #
    # Modulation
    # ------------------------------------------------------------------ #

    @staticmethod
    def _mod_type(modulation_type: str) -> str:
        key = str(modulation_type).strip().upper()
        aliases = {"ASKEY": "ASK", "FSKEY": "FSK", "PSKEY": "PSK"}
        key = aliases.get(key, key)
        if key not in _MODULATION_TYPES:
            raise ValueError(f"Modulation type must be one of {', '.join(_MODULATION_TYPES)}")
        return key

    async def _write_mod_params(
        self, ch: int, mtype: str, depth, deviation, frequency, source, shape
    ) -> None:
        """Shared AM/FM/PM/PWM parameter writes (node differs per platform)."""
        root = f"{self._mod(ch)}:{mtype}"
        if depth is not None:
            if mtype == "AM":
                await self._write(f"{root}:DEPTh {_fmt(self._check_percent(depth, 'AM depth', 0, 120))}")
            else:
                raise ValueError("depth only applies to AM")
        if deviation is not None:
            deviation = float(deviation)
            if mtype == "FM":
                if deviation < 0:
                    raise ValueError("FM deviation must be >= 0 Hz")
                await self._write(f"{root}:DEViation {_fmt(deviation)}")
            elif mtype == "PM":
                await self._write(f"{root}:DEViation {_fmt(self._check_percent(deviation, 'PM deviation', 0, 360))}")
            elif mtype == "PWM":
                await self._write(f"{root}:DEViation:DCYCle {_fmt(deviation)}")
            else:
                raise ValueError("deviation only applies to FM, PM and PWM")
        if frequency is not None:
            frequency = float(frequency)
            if frequency <= 0:
                raise ValueError("Modulating frequency must be > 0 Hz")
            if mtype in ("ASK", "FSK", "PSK"):
                await self._write(f"{root}:INTernal:RATE {_fmt(frequency)}")
            else:
                await self._write(f"{root}:INTernal:FREQuency {_fmt(frequency)}")
        if source is not None:
            key = str(source).strip().upper()
            if key not in ("INT", "INTERNAL", "EXT", "EXTERNAL"):
                raise ValueError("Modulation source must be INTERNAL or EXTERNAL")
            await self._write(f"{root}:SOURce {'INTernal' if key.startswith('INT') else 'EXTernal'}")
        if shape is not None:
            key = str(shape).strip().upper()
            if key not in _MOD_SHAPES:
                raise ValueError(f"Modulating shape must be one of {sorted(set(_MOD_SHAPES))}")
            await self._write(f"{root}:INTernal:FUNCtion {_MOD_SHAPES[key]}")

    async def set_modulation(
        self,
        enabled: bool = True,
        modulation_type: str = "AM",
        depth: Optional[float] = None,
        deviation: Optional[float] = None,
        frequency: Optional[float] = None,
        source: Optional[str] = None,
        shape: Optional[str] = None,
        channel: Any = 1,
    ) -> Dict[str, Any]:
        """Configure and enable/disable modulation.

        ``depth`` (AM, %), ``deviation`` (FM Hz / PM deg / PWM duty %),
        ``frequency`` (modulating frequency Hz, or rate for ASK/FSK/PSK),
        ``source`` INTERNAL/EXTERNAL, ``shape`` modulating waveform.
        Classic tree: ``:SOURce<n>:MOD:TYPe`` + ``:MOD:STATe``.
        """
        ch = self._channel(channel)
        mtype = self._mod_type(modulation_type)
        async with self._io_lock:
            await self._write(f"{self._mod(ch)}:TYPe {mtype}")
            await self._write_mod_params(ch, mtype, depth, deviation, frequency, source, shape)
            await self._write(f"{self._mod(ch)}:STATe {_on_off(bool(enabled))}")
        return await self.get_modulation(ch)

    async def get_modulation(self, channel: Any = 1) -> Dict[str, Any]:
        ch = self._channel(channel)
        enabled = await self._query_bool(f"{self._mod(ch)}:STATe?")
        mtype = (await self._query(f"{self._mod(ch)}:TYPe?")).strip().upper()
        out: Dict[str, Any] = {"enabled": enabled, "type": mtype or None}
        if mtype in ("AM", "FM", "PM", "PWM"):
            root = f"{self._mod(ch)}:{mtype}"
            try:
                if mtype == "AM":
                    out["depth"] = await self._query_number(f"{root}:DEPTh?")
                elif mtype == "PWM":
                    out["deviation"] = await self._query_number(f"{root}:DEViation:DCYCle?")
                else:
                    out["deviation"] = await self._query_number(f"{root}:DEViation?")
                out["frequency"] = await self._query_number(f"{root}:INTernal:FREQuency?")
            except Exception as e:
                logger.debug(f"Modulation parameter query failed: {e}")
        return out

    # ------------------------------------------------------------------ #
    # Sweep
    # ------------------------------------------------------------------ #

    async def set_sweep(
        self,
        enabled: bool = True,
        start: Optional[float] = None,
        stop: Optional[float] = None,
        time: Optional[float] = None,
        spacing: Optional[str] = None,
        channel: Any = 1,
    ) -> Dict[str, Any]:
        """``:FREQuency:STARt/STOP``, ``:SWEep:TIME``, ``:SWEep:SPACing``, ``:SWEep:STATe``."""
        ch = self._channel(channel)
        src = self._src(ch)
        async with self._io_lock:
            if start is not None:
                await self._write(f"{src}:FREQuency:STARt {_fmt(self._check_frequency('SIN', start))}")
            if stop is not None:
                await self._write(f"{src}:FREQuency:STOP {_fmt(self._check_frequency('SIN', stop))}")
            if time is not None:
                time = float(time)
                if time <= 0:
                    raise ValueError("Sweep time must be > 0 s")
                await self._write(f"{src}:SWEep:TIME {_fmt(time)}")
            if spacing is not None:
                key = str(spacing).strip().upper()
                if key not in _SWEEP_SPACINGS:
                    raise ValueError("Sweep spacing must be LINEAR, LOG or STEP")
                await self._write(f"{src}:SWEep:SPACing {_SWEEP_SPACINGS[key]}")
            await self._write(f"{src}:SWEep:STATe {_on_off(bool(enabled))}")
        return await self.get_sweep(ch)

    async def get_sweep(self, channel: Any = 1) -> Dict[str, Any]:
        ch = self._channel(channel)
        src = self._src(ch)
        out: Dict[str, Any] = {"enabled": await self._query_bool(f"{src}:SWEep:STATe?")}
        for key, cmd in (("start", ":FREQuency:STARt?"), ("stop", ":FREQuency:STOP?"),
                         ("time", ":SWEep:TIME?")):
            try:
                out[key] = await self._query_number(f"{src}{cmd}")
            except Exception:
                out[key] = None
        try:
            out["spacing"] = (await self._query(f"{src}:SWEep:SPACing?")).strip().upper()
        except Exception:
            out["spacing"] = None
        return out

    # ------------------------------------------------------------------ #
    # Burst
    # ------------------------------------------------------------------ #

    async def set_burst(
        self,
        enabled: bool = True,
        mode: Optional[str] = None,
        cycles: Optional[int] = None,
        period: Optional[float] = None,
        phase: Optional[float] = None,
        channel: Any = 1,
    ) -> Dict[str, Any]:
        """``:BURSt:MODE``, ``:BURSt:NCYCles``, ``:BURSt:INTernal:PERiod``, ``:BURSt:PHASe``, ``:BURSt:STATe``."""
        ch = self._channel(channel)
        src = self._src(ch)
        async with self._io_lock:
            if mode is not None:
                key = str(mode).strip().upper()
                if key not in _BURST_MODES:
                    raise ValueError("Burst mode must be TRIGGERED (N cycle), INFINITY or GATED")
                await self._write_burst_mode(ch, _BURST_MODES[key])
            if cycles is not None:
                cycles = int(cycles)
                if not 1 <= cycles <= 1_000_000:
                    raise ValueError("Burst cycles must be 1..1000000")
                await self._write(f"{src}:BURSt:NCYCles {cycles}")
            if period is not None:
                period = float(period)
                if period <= 0:
                    raise ValueError("Burst period must be > 0 s")
                await self._write(f"{src}:BURSt:INTernal:PERiod {_fmt(period)}")
            if phase is not None:
                await self._write(f"{src}:BURSt:PHASe {_fmt(self._check_phase(phase))}")
            await self._write(f"{src}:BURSt:STATe {_on_off(bool(enabled))}")
        return await self.get_burst(ch)

    async def _write_burst_mode(self, ch: int, keyword: str) -> None:
        if keyword not in self.BURST_MODES:
            raise ValueError(f"{self.model} supports burst modes {', '.join(self.BURST_MODES)}")
        await self._write(f"{self._src(ch)}:BURSt:MODE {keyword}")

    async def get_burst(self, channel: Any = 1) -> Dict[str, Any]:
        ch = self._channel(channel)
        src = self._src(ch)
        out: Dict[str, Any] = {"enabled": await self._query_bool(f"{src}:BURSt:STATe?")}
        try:
            out["mode"] = (await self._query(f"{src}:BURSt:MODE?")).strip().upper()
        except Exception:
            out["mode"] = None
        for key, cmd in (("cycles", ":BURSt:NCYCles?"), ("period", ":BURSt:INTernal:PERiod?"),
                         ("phase", ":BURSt:PHASe?")):
            try:
                value = await self._query_number(f"{src}{cmd}")
                out[key] = int(value) if key == "cycles" and value is not None and value < 1e15 else value
            except Exception:
                out[key] = None
        return out

    async def trigger_burst(self, channel: Any = 1) -> None:
        """Manual burst trigger ``:SOURce<n>:BURSt:TRIGger``."""
        ch = self._channel(channel)
        await self._write(f"{self._src(ch)}:BURSt:TRIGger")

    # ------------------------------------------------------------------ #
    # Arbitrary waveforms
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalise_points(points: Sequence[float]) -> List[float]:
        values: List[float] = []
        for p in points:
            v = float(p)
            if math.isnan(v) or math.isinf(v):
                raise ValueError("Arbitrary waveform points must be finite")
            values.append(max(-1.0, min(1.0, v)))
        return values

    async def upload_arbitrary(
        self, points: Sequence[float], channel: Any = 1, name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Download normalised (-1..1) samples to the channel's volatile memory.

        The instrument switches the channel to the volatile arbitrary waveform
        automatically once the transfer completes (classic tree).  The data
        format depends on ``ARB_UPLOAD_FORMAT`` (see class docstring); the
        DG1000Z accepts ``:SOURce<n>:TRACe:DATA VOLATILE,<f>,...`` with 8 to
        16384 points per command.
        """
        ch = self._channel(channel)
        values = self._normalise_points(points)
        if len(values) < 1:
            raise ValueError("At least one point is required")
        if len(values) > self.spec.arb_points:
            raise ValueError(f"{self.model} arbitrary memory holds at most {self.spec.arb_points} points")
        fmt = self.ARB_UPLOAD_FORMAT
        async with self._io_lock:
            if fmt in ("FLOAT", "FLOAT_CH0"):
                if len(values) > self.ARB_MAX_POINTS_PER_WRITE:
                    raise ValueError(
                        f"{self.model} accepts at most {self.ARB_MAX_POINTS_PER_WRITE} points per :DATA command"
                    )
                if fmt == "FLOAT" and len(values) < self.ARB_MIN_POINTS:
                    raise ValueError(f"{self.model} needs at least {self.ARB_MIN_POINTS} points")
                prefix = f"{self._src(ch)}:TRACe:DATA" if fmt == "FLOAT" else ":TRACe:DATA"
                if fmt == "FLOAT_CH0" and ch != 1:
                    logger.warning(
                        f"{self.model}: :TRACe:DATA has no channel node; the data goes to the "
                        "channel currently selected on the front panel"
                    )
                await self._write(f"{prefix} VOLATILE,{','.join(_fmt(round(v, 6)) for v in values)}")
                packets = 1
            elif fmt == "DAC16":
                packets = await self._upload_dac16(ch, values)
            else:
                raise RuntimeError(f"Unsupported arbitrary upload format {fmt}")
        return {"channel": ch, "points": len(values), "format": fmt, "packets": packets,
                "name": name or "VOLATILE"}

    async def _upload_dac16(self, ch: int, values: List[float]) -> int:
        """``:SOURce<n>:TRACe:DATA:DAC16 VOLATILE,<CON|END>,#<len><block>`` in 16 kpt packets.

        Each point is a 14 bit code 0x0000..0x3FFF in two bytes (DG800/DG900/
        DG2000/DG1000Z guides).  Blocks shorter than 8 points are padded by
        repeating the last sample.
        """
        if len(values) < self.ARB_MIN_POINTS:
            values = values + [values[-1]] * (self.ARB_MIN_POINTS - len(values))
        chunk = self.ARB_MAX_POINTS_PER_WRITE
        packets = [values[i:i + chunk] for i in range(0, len(values), chunk)]
        for index, packet in enumerate(packets):
            if len(packet) < self.ARB_MIN_POINTS:
                packet = packet + [packet[-1]] * (self.ARB_MIN_POINTS - len(packet))
            codes = [int(round((v + 1.0) / 2.0 * 0x3FFF)) for v in packet]
            data = struct.pack(f"{self.DAC16_BYTE_ORDER}{len(codes)}H", *codes)
            flag = "END" if index == len(packets) - 1 else "CON"
            length = str(len(data))
            header = f"{self._src(ch)}:TRACe:DATA:DAC16 VOLATILE,{flag},#{len(length)}{length}"
            await self._write_raw(header.encode("ascii") + data + b"\n")
        return len(packets)

    async def set_arb_sample_rate(self, sample_rate: float, channel: Any = 1) -> Optional[float]:
        """Sample-rate output mode: ``:FUNCtion:ARBitrary:MODE SRATe`` + ``:FUNCtion:ARBitrary:SRATe``.

        Documented for DG1000Z only.
        """
        if not self.HAS_ARB_SAMPLE_RATE:
            raise ValueError(f"{self.model} does not document a sample-rate arbitrary mode")
        ch = self._channel(channel)
        sample_rate = float(sample_rate)
        if not 0 < sample_rate <= self.spec.sample_rate:
            raise ValueError(f"Sample rate must be 0..{self.spec.sample_rate:g} Sa/s")
        await self._write(f"{self._src(ch)}:FUNCtion:ARBitrary:MODE SRATe")
        await self._write(f"{self._src(ch)}:FUNCtion:ARBitrary:SRATe {_fmt(sample_rate)}")
        return await self._query_number(f"{self._src(ch)}:FUNCtion:ARBitrary:SRATe?")

    # ------------------------------------------------------------------ #
    # Phase alignment / counter
    # ------------------------------------------------------------------ #

    async def sync_phase(self, channel: Any = 1) -> None:
        """Align the phase of both channels (invalid while modulation is on)."""
        ch = self._channel(channel)
        await self._write(f"{self._src(ch)}{self.PHASE_ALIGN_CMD}")

    async def set_counter(self, enabled: bool = True) -> bool:
        """``:COUNter:STATe ON|OFF`` (turning it on disables CH2 sync output)."""
        if not self.spec.has_counter:
            raise ValueError(f"{self.model} has no frequency counter")
        await self._write(f":COUNter:STATe {_on_off(bool(enabled))}")
        return await self._query_bool(":COUNter:STATe?")

    async def get_counter(self) -> Dict[str, Any]:
        """``:COUNter:MEASure?`` -> frequency, period, duty, +width, -width.

        Returns NaN values when the counter is off (the instrument answers 0s).
        """
        if not self.spec.has_counter:
            raise ValueError(f"{self.model} has no frequency counter")
        enabled = await self._query_bool(":COUNter:STATe?")
        raw = await self._query(":COUNter:MEASure?")
        parts = [parse_number(p) for p in raw.strip().strip('"').split(",")]
        while len(parts) < 5:
            parts.append(None)
        nan = float("nan")

        def pick(i: int) -> float:
            v = parts[i]
            if not enabled or v is None:
                return nan
            return v

        return {
            "enabled": enabled,
            "frequency": pick(0),
            "period": pick(1),
            "duty_cycle": pick(2),
            "positive_width": pick(3),
            "negative_width": pick(4),
            "unit": "Hz",
        }

    # ------------------------------------------------------------------ #
    # Readings / hooks
    # ------------------------------------------------------------------ #

    async def get_readings(self, channel: Any = 1) -> FunctionGeneratorData:
        """Channel snapshot built from ``:APPLy?`` plus output/load/mod/sweep/burst."""
        ch = self._channel(channel)
        src = self._src(ch)
        applied = parse_apply_response(await self._query(f"{src}:APPLy?"))
        data = FunctionGeneratorData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            channel=ch,
            waveform=applied["waveform"],
            frequency=applied["frequency"],
            amplitude=applied["amplitude"],
            offset=applied["offset"],
            phase=applied["phase"],
        )
        try:
            data.output_enabled = await self.get_output(ch)
        except Exception as e:
            logger.debug(f"Output query failed: {e}")
        try:
            data.load_impedance = await self.get_load(ch)
        except Exception as e:
            logger.debug(f"Load query failed: {e}")
        try:
            data.amplitude_unit = await self.get_amplitude_unit(ch)
        except Exception:
            data.amplitude_unit = self._unit.get(ch, "VPP")
        try:
            mod = await self.get_modulation(ch)
            data.modulation = mod["type"] if mod["enabled"] else None
        except Exception as e:
            logger.debug(f"Modulation query failed: {e}")
        try:
            data.sweep_enabled = await self._query_bool(f"{src}:SWEep:STATe?")
        except Exception:
            pass
        try:
            data.burst_enabled = await self._query_bool(f"{src}:BURSt:STATe?")
        except Exception:
            pass
        try:
            if data.waveform in ("SQU", "PULS"):
                data.duty_cycle = await self.get_duty_cycle(ch, data.waveform)
            elif data.waveform == "RAMP":
                data.symmetry = await self.get_symmetry(ch)
        except Exception as e:
            logger.debug(f"Duty/symmetry query failed: {e}")
        return data

    async def get_measurement(self, channel: str = "CH1:FREQ") -> Dict[str, Any]:
        """Acquisition-engine hook.

        Channel names:
        - ``COUNTER`` / ``COUNT`` / ``COUNTER:FREQ`` - frequency counter reading (Hz)
        - ``COUNTER:PERIOD`` / ``COUNTER:DUTY`` / ``COUNTER:PWIDTH`` / ``COUNTER:NWIDTH``
        - ``CH<n>`` / ``<n>`` / ``CH<n>:FREQ`` - set frequency of channel n
        - ``CH<n>:AMPL`` (``AMP``, ``VPP``) - set amplitude
        - ``CH<n>:OFFS`` - offset, ``CH<n>:PHASE`` - phase, ``CH<n>:OUTPUT`` - 1/0
        Invalid or unavailable values are returned as NaN.
        """
        key = (channel or "CH1:FREQ").strip().upper().replace(" ", "")
        nan = float("nan")
        if key.startswith("COUNT"):
            _, _, what = key.partition(":")
            counter = await self.get_counter()
            field_map = {
                "": ("frequency", "Hz"), "FREQ": ("frequency", "Hz"), "FREQUENCY": ("frequency", "Hz"),
                "PERIOD": ("period", "s"), "PER": ("period", "s"),
                "DUTY": ("duty_cycle", "%"), "DCYC": ("duty_cycle", "%"),
                "PWIDTH": ("positive_width", "s"), "PWID": ("positive_width", "s"),
                "NWIDTH": ("negative_width", "s"), "NWID": ("negative_width", "s"),
            }
            if what not in field_map:
                raise ValueError(f"Unknown counter quantity '{what}'")
            name, unit = field_map[what]
            value = counter.get(name)
            return {"value": value if value is not None else nan, "unit": unit,
                    "quantity": f"COUNTER:{name.upper()}", "enabled": counter["enabled"]}

        ch_part, _, what = key.partition(":")
        ch = self._channel(ch_part or "1")
        what = what or "FREQ"
        if what in ("FREQ", "FREQUENCY", "F"):
            value, unit, quantity = await self.get_frequency(ch), "Hz", "FREQ"
        elif what in ("AMPL", "AMP", "AMPLITUDE", "VPP", "V"):
            value = await self.get_amplitude(ch)
            unit = self._unit.get(ch) or await self.get_amplitude_unit(ch)
            quantity = "AMPL"
        elif what in ("OFFS", "OFFSET", "DC"):
            value, unit, quantity = await self.get_offset(ch), "V", "OFFS"
        elif what in ("PHASE", "PHAS"):
            value, unit, quantity = await self.get_phase(ch), "deg", "PHASE"
        elif what in ("OUTPUT", "OUTP", "ON"):
            value, unit, quantity = (1.0 if await self.get_output(ch) else 0.0), "", "OUTPUT"
        else:
            raise ValueError(f"Unknown measurement '{channel}' (use CHn:FREQ, CHn:AMPL, CHn:OFFS, CHn:PHASE, COUNTER)")
        return {"value": value if value is not None else nan, "unit": unit,
                "channel": ch, "quantity": quantity}

    async def get_measurements(self, channel: Any = 1) -> Dict[str, Any]:
        """Streaming hook: settings of one channel plus the counter frequency."""
        data = await self.get_readings(channel)
        nan = float("nan")
        out: Dict[str, Any] = {
            "waveform": data.waveform,
            "frequency": data.frequency if data.frequency is not None else nan,
            "amplitude": data.amplitude if data.amplitude is not None else nan,
            "amplitude_unit": data.amplitude_unit,
            "offset": data.offset if data.offset is not None else nan,
            "phase": data.phase if data.phase is not None else nan,
            "output_enabled": data.output_enabled,
        }
        if self.spec.has_counter:
            try:
                counter = await self.get_counter()
                out["counter_frequency"] = counter["frequency"]
            except Exception:
                out["counter_frequency"] = nan
        return out

    async def get_state(self) -> Dict[str, Any]:
        """Snapshot of every channel for state capture/restore."""
        state: Dict[str, Any] = {"model": self.model, "channels": {}}
        for ch in range(1, self.spec.channels + 1):
            entry: Dict[str, Any] = {}
            try:
                entry.update(parse_apply_response(await self._query(f"{self._src(ch)}:APPLy?")))
            except Exception as e:
                entry["error"] = str(e)
            for key, coro in (
                ("output", self.get_output(ch)),
                ("load", self.get_load(ch)),
                ("unit", self.get_amplitude_unit(ch)),
                ("modulation", self.get_modulation(ch)),
                ("sweep", self.get_sweep(ch)),
                ("burst", self.get_burst(ch)),
            ):
                try:
                    entry[key] = await coro
                except Exception:
                    entry[key] = None
            state["channels"][ch] = entry
        return state

    # ------------------------------------------------------------------ #
    # System
    # ------------------------------------------------------------------ #

    async def set_beeper(self, enabled: bool) -> bool:
        await self._write(f":SYSTem:BEEPer:STATe {_on_off(bool(enabled))}")
        return await self._query_bool(":SYSTem:BEEPer:STATe?")

    async def beep(self) -> None:
        await self._write(":SYSTem:BEEPer")

    async def get_error(self) -> Dict[str, Any]:
        raw = await self._query(":SYSTem:ERRor?")
        code_str, _, message = raw.partition(",")
        try:
            code = int(float(code_str.strip()))
        except ValueError:
            code = None
        return {"code": code, "message": message.strip().strip('"'), "raw": raw}


# --------------------------------------------------------------------------- #
# Classic-tree families
# --------------------------------------------------------------------------- #


class RigolDG1000Z(RigolDGBase):
    """DG1022Z / DG1032Z / DG1062Z: 2 channels, 200 MSa/s, float :DATA upload."""

    FAMILY = "DG1000Z"
    MODEL = "DG1000Z"
    DEFAULT_MODEL = "DG1062Z"
    ARB_UPLOAD_FORMAT = "FLOAT"
    HAS_ARB_SAMPLE_RATE = True


class RigolDG800(RigolDGBase):
    """DG811/812/821/822/831/832: 125 MSa/s, 16 bit, DAC16 binary upload only."""

    FAMILY = "DG800"
    MODEL = "DG800"
    DEFAULT_MODEL = "DG832"
    ARB_UPLOAD_FORMAT = "DAC16"


class RigolDG900(RigolDGBase):
    """DG952/972/992: 250 MSa/s, 16 bit, DAC16 binary upload only."""

    FAMILY = "DG900"
    MODEL = "DG900"
    DEFAULT_MODEL = "DG992"
    ARB_UPLOAD_FORMAT = "DAC16"


class RigolDG2000(RigolDGBase):
    """DG2052/2072/2102: DG900 with LAN (LXI); same command tree."""

    FAMILY = "DG2000"
    MODEL = "DG2000"
    DEFAULT_MODEL = "DG2102"
    ARB_UPLOAD_FORMAT = "DAC16"


class RigolDG4000(RigolDGBase):
    """DG4062/4102/4162/4202 (older tree).

    Quirks: ``:MOD`` node mandatory, align phase is ``:PHASe:INITiate``,
    ``:APPLy:PULSe`` takes ``<delay>`` instead of ``<phase>``, ``:TRACe:DATA``
    has no channel node (targets the active channel), 16 kpts arb memory,
    ``:OUTPut:LOAD?`` may answer ``INFINITY``.
    """

    FAMILY = "DG4000"
    MODEL = "DG4000"
    DEFAULT_MODEL = "DG4162"
    PHASE_ALIGN_CMD = ":PHASe:INITiate"
    PULSE_APPLY_HAS_PHASE = False
    ARB_UPLOAD_FORMAT = "FLOAT_CH0"
    ARB_MIN_POINTS = 1


class RigolDG5000(RigolDG4000):
    """DG5071..DG5352 (older tree, 1 GSa/s).

    Same quirks as DG4000; no frequency counter; odd model numbers are
    single channel.
    """

    FAMILY = "DG5000"
    MODEL = "DG5000"
    DEFAULT_MODEL = "DG5352"


# --------------------------------------------------------------------------- #
# Pro platform (DG800 Pro / DG900 Pro, DG5000 Pro, DG6000)
# --------------------------------------------------------------------------- #


class RigolDGProBase(RigolDGBase):
    """Rigol "Pro" platform generators.

    Differences from the classic tree handled here:
    - ``:APPLy:ARBitrary`` (not USER), ``:FUNCtion ARB``; ``:APPLy:NOISe`` and
      ``:APPLy:DC`` take four placeholder-able parameters.
    - Modulation is per type: ``:SOURce<n>:AM:STATe``, ``:AM:DEPTh``,
      ``:FM:DEViation`` ... (no ``:MOD`` node, no ``:MOD:TYPe``).
    - Pulse parameters under ``:FUNCtion:PULSe:{DCYCle|WIDTh|TRANsition:LEADing|TRAiling}``.
    - Burst modes TRIGgered|GATed only (infinite = ``:BURSt:NCYCles INFinity``);
      manual trigger via ``:TRIGger<n>``.
    - Arbitrary upload ``:SOURce<n>:TRACe:DATA:DAC16 VOLTage,<HEADer|CONTinue|END>,<f>,...``
      with normalised floats, chunked to ~20 kB packets.
    - Boolean queries answer 0/1; phase range -360..360.
    """

    FAMILY = "DG800Pro"
    MODEL = "DG800 Pro"
    DEFAULT_MODEL = "DG852PRO"
    APPLY_KEYWORDS = _APPLY_KEYWORDS_PRO
    FUNCTION_KEYWORDS = {"SIN": "SINusoid", "SQU": "SQUare", "RAMP": "RAMP", "PULS": "PULSe",
                         "NOIS": "NOISe", "ARB": "ARB", "HARM": "HARMonic"}
    PULSE_ROOT = ":FUNCtion:PULSe"
    MOD_NODE = ""
    PHASE_ALIGN_CMD = ":PHASe:SYNChronize"
    BURST_MODES = ("TRIGgered", "GATed")
    ARB_UPLOAD_FORMAT = "PRO"
    ARB_MIN_POINTS = 1
    # ~20 kB per packet recommended by the guide; 8 chars per float.
    ARB_MAX_POINTS_PER_WRITE = 2048

    def _apply_arguments(self, waveform: str, frequency, amplitude, offset, phase) -> List[str]:
        f = _fmt(frequency) if frequency is not None else "DEF"
        a = _fmt(amplitude) if amplitude is not None else "DEF"
        o = _fmt(offset) if offset is not None else "DEF"
        p = _fmt(phase) if phase is not None else "DEF"
        if waveform == "DC":
            return ["DEF", "DEF", o]
        if waveform == "NOIS":
            return ["DEF", a, o]
        return [f, a, o, p]

    async def set_modulation(
        self,
        enabled: bool = True,
        modulation_type: str = "AM",
        depth: Optional[float] = None,
        deviation: Optional[float] = None,
        frequency: Optional[float] = None,
        source: Optional[str] = None,
        shape: Optional[str] = None,
        channel: Any = 1,
    ) -> Dict[str, Any]:
        """Pro tree: parameters under ``:SOURce<n>:<TYPE>``, enable via ``:<TYPE>:STATe``."""
        ch = self._channel(channel)
        mtype = self._mod_type(modulation_type)
        node = {"ASK": "ASKey", "FSK": "FSKey", "PSK": "PSKey"}.get(mtype, mtype)
        async with self._io_lock:
            await self._write_mod_params(ch, node, depth, deviation, frequency, source, shape)
            if enabled:
                # Only one modulation can be active; the instrument switches off
                # the others when a new :STATe ON arrives.
                await self._write(f"{self._src(ch)}:{node}:STATe ON")
            else:
                await self._write(f"{self._src(ch)}:{node}:STATe OFF")
        return await self.get_modulation(ch)

    async def get_modulation(self, channel: Any = 1) -> Dict[str, Any]:
        """Poll each modulation's :STATe? to find the active one."""
        ch = self._channel(channel)
        active: Optional[str] = None
        for mtype in _MODULATION_TYPES:
            node = {"ASK": "ASKey", "FSK": "FSKey", "PSK": "PSKey"}.get(mtype, mtype)
            try:
                if await self._query_bool(f"{self._src(ch)}:{node}:STATe?"):
                    active = mtype
                    break
            except Exception as e:
                logger.debug(f"{mtype} state query failed: {e}")
        out: Dict[str, Any] = {"enabled": active is not None, "type": active}
        if active in ("AM", "FM", "PM", "PWM"):
            root = f"{self._src(ch)}:{active}"
            try:
                if active == "AM":
                    out["depth"] = await self._query_number(f"{root}:DEPTh?")
                elif active == "PWM":
                    out["deviation"] = await self._query_number(f"{root}:DEViation:DCYCle?")
                else:
                    out["deviation"] = await self._query_number(f"{root}:DEViation?")
                out["frequency"] = await self._query_number(f"{root}:INTernal:FREQuency?")
            except Exception as e:
                logger.debug(f"Modulation parameter query failed: {e}")
        return out

    async def _write_burst_mode(self, ch: int, keyword: str) -> None:
        if keyword == "INFinity":
            # Pro has no INFinity mode; infinite burst = N cycle with INFinity count.
            await self._write(f"{self._src(ch)}:BURSt:MODE TRIGgered")
            await self._write(f"{self._src(ch)}:BURSt:NCYCles INFinity")
            return
        await super()._write_burst_mode(ch, keyword)

    async def trigger_burst(self, channel: Any = 1) -> None:
        """Pro platform manual trigger ``:TRIGger<n>:IMMediate``."""
        ch = self._channel(channel)
        await self._write(f":TRIGger{ch}:IMMediate")

    async def upload_arbitrary(
        self, points: Sequence[float], channel: Any = 1, name: Optional[str] = None
    ) -> Dict[str, Any]:
        """``:SOURce<n>:TRACe:DATA:DAC16 VOLTage,<flag>,<f>,<f>,...`` in packets.

        Flags: HEADer (first of several), CONTinue (middle), END (last / only).
        Floats are normalised by the instrument; we clip to -1..1.  Select the
        volatile waveform afterwards with ``set_waveform("ARB")`` if the
        channel is not already outputting an Arb.
        """
        ch = self._channel(channel)
        values = self._normalise_points(points)
        if not values:
            raise ValueError("At least one point is required")
        if len(values) > self.spec.arb_points:
            raise ValueError(f"{self.model} arbitrary memory holds at most {self.spec.arb_points} points")
        chunk = self.ARB_MAX_POINTS_PER_WRITE
        packets = [values[i:i + chunk] for i in range(0, len(values), chunk)]
        async with self._io_lock:
            for index, packet in enumerate(packets):
                if len(packets) == 1:
                    flag = "END"
                elif index == 0:
                    flag = "HEADer"
                elif index == len(packets) - 1:
                    flag = "END"
                else:
                    flag = "CONTinue"
                payload = ",".join(_fmt(round(v, 6)) for v in packet)
                await self._write(f"{self._src(ch)}:TRACe:DATA:DAC16 VOLTage,{flag},{payload}")
        return {"channel": ch, "points": len(values), "format": self.ARB_UPLOAD_FORMAT,
                "packets": len(packets), "name": name or "VOLATILE"}

    async def set_arb_sample_rate(self, sample_rate: float, channel: Any = 1) -> Optional[float]:
        raise ValueError(
            f"{self.model}: arbitrary sample rate is set per sequence/advanced-arb "
            "(:FUNCtion:SEQuence:ARB:SRATe), not supported by this driver"
        )


class RigolDG800Pro(RigolDGProBase):
    """DG821 Pro / DG822 Pro / DG852 Pro and DG902 Pro / DG912 Pro / DG922 Pro.

    One programming guide covers both series; the model table distinguishes
    them (625 MSa/s, 2 Mpts vs 1.25 GSa/s, 16 Mpts).
    """

    FAMILY = "DG800Pro"
    MODEL = "DG800 Pro"
    DEFAULT_MODEL = "DG852PRO"


class RigolDG5000Pro(RigolDGProBase):
    """DG5252/5254/5258 Pro, DG5352/5354/5358 Pro, DG5502/5504/5508 Pro.

    2/4/8 isolated channels, 2.5 GSa/s, 64 Mpts; no frequency counter.
    """

    FAMILY = "DG5000Pro"
    MODEL = "DG5000 Pro"
    DEFAULT_MODEL = "DG5508PRO"


class RigolDG6000(RigolDGProBase):
    """DG6052 / DG6054 / DG6102 / DG6104: 2/4 channels, 2.5 GSa/s, 256 Mpts.

    Same Pro tree as DG5000 Pro (guides are near-identical); sine limits in
    the model table are for the HBW output type.
    """

    FAMILY = "DG6000"
    MODEL = "DG6000"
    DEFAULT_MODEL = "DG6104"


# Model keywords used by equipment.manager.find_keyword_driver (most specific classes
# are ordered first in the manager's KEYWORD_DRIVER_CLASSES list).
RigolDG5000Pro.MODEL_KEYWORDS = ('DG5252 PRO', 'DG5252PRO', 'DG5252-PRO', 'DG5254 PRO', 'DG5254PRO', 'DG5254-PRO', 'DG5258 PRO', 'DG5258PRO', 'DG5258-PRO', 'DG5352 PRO', 'DG5352PRO', 'DG5352-PRO', 'DG5354 PRO', 'DG5354PRO', 'DG5354-PRO', 'DG5358 PRO', 'DG5358PRO', 'DG5358-PRO', 'DG5502 PRO', 'DG5502PRO', 'DG5502-PRO', 'DG5504 PRO', 'DG5504PRO', 'DG5504-PRO', 'DG5508 PRO', 'DG5508PRO', 'DG5508-PRO')
RigolDG800Pro.MODEL_KEYWORDS = ('DG821 PRO', 'DG821PRO', 'DG821-PRO', 'DG822 PRO', 'DG822PRO', 'DG822-PRO', 'DG852 PRO', 'DG852PRO', 'DG852-PRO', 'DG902 PRO', 'DG902PRO', 'DG902-PRO', 'DG912 PRO', 'DG912PRO', 'DG912-PRO', 'DG922 PRO', 'DG922PRO', 'DG922-PRO')
RigolDG6000.MODEL_KEYWORDS = ('DG6052', 'DG6054', 'DG6102', 'DG6104')
RigolDG5000.MODEL_KEYWORDS = ('DG5071', 'DG5072', 'DG5101', 'DG5102', 'DG5251', 'DG5252', 'DG5351', 'DG5352')
RigolDG4000.MODEL_KEYWORDS = ('DG4062', 'DG4102', 'DG4162', 'DG4202')
RigolDG2000.MODEL_KEYWORDS = ('DG2052', 'DG2072', 'DG2102')
RigolDG1000Z.MODEL_KEYWORDS = ('DG1022Z', 'DG1032Z', 'DG1062Z')
RigolDG900.MODEL_KEYWORDS = ('DG952', 'DG972', 'DG992')
RigolDG800.MODEL_KEYWORDS = ('DG811', 'DG812', 'DG821', 'DG822', 'DG831', 'DG832')
