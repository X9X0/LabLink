"""Rigol DSA / RSA spectrum and real-time spectrum analyzer drivers.

Families covered (one subclass each, sharing :class:`RigolSABase`):

======================  ==========================================================================
Class                   Models / programming guide
======================  ==========================================================================
``RigolDSA800``         DSA815/832/875 (+ -TG), DSA832E (+ -TG), DSA705/710
                        ("DSA800 Programming Guide", "DSA800E Programming Guide",
                        "DSA700 Programming manual")
``RigolDSA1000``        DSA1030 / DSA1030A (+ -TG) legacy tree
                        ("DSA1000 Programming Guide", "DSA1000A Programming Guide")
``RigolRSA3000``        RSA3015E/3030E (+ -TG), RSA3015N, RSA3030/3045 (+ -TG, N)
                        ("RSA3000 Programming Manual", "RSA3000E Programming Manual")
``RigolRSA5000``        RSA5032 / RSA5065 (+ -TG, N) ("RSA5000 Programming Manual")
``RigolRSA800``         RSA804 / RSA808 / RSA814 ("RSA800 Programming Guide")
``RigolRSA6000``        RSA6085 / RSA6140 / RSA6265 ("RSA6000 Series Programming Guide")
======================  ==========================================================================

All families share the SCPI tree rooted at ``[:SENSe]:FREQuency``,
``[:SENSe]:BANDwidth``, ``[:SENSe]:POWer[:RF]``, ``[:SENSe]:SWEep``,
``:TRACe``, ``:CALCulate:MARKer<n>``, ``:INITiate``, ``:UNIT:POWer`` and
``:DISPlay:WINdow:TRACe:Y[:SCALe]:RLEVel``.  The differences that matter are
kept in class constants and in :data:`MODEL_TABLE`; there are no
``if model == ...`` chains inside the methods.

Trace data
----------
``:TRACe:DATA? TRACE<n>`` answers in the format selected with
``:FORMat[:TRACe][:DATA]``:

* ``ASCii`` - comma separated scientific notation.  DSA800/DSA1000 firmware
  prefixes the list with an IEEE definite-length header (``#9000009014 ...``,
  DSA800 guide 2-188); RSA firmware returns the bare list.  Both are parsed.
* ``REAL,32`` - IEEE ``#<d><len>`` block of 32-bit floats.  ``:FORMat:BORDer``
  defaults to ``NORMal`` which the DSA800 guide defines as MSB first, so the
  driver sends ``:FORMat:BORDer SWAPped`` and unpacks little-endian.
  RSA800/RSA6000 guides document ASCII only; the driver stays in ASCII there.

*IDN? returns ``Rigol Technologies,<model>,<serial>,<firmware>``.
"""

import asyncio
import functools
import logging
import math
import re
import struct
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Union

from shared.models.data import SpectrumData
from shared.models.equipment import (EquipmentInfo, EquipmentStatus,
                                     EquipmentType)

from .base import BaseEquipment, generate_equipment_id

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Per-model table
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SAModelSpec:
    """Static facts about one analyzer model (datasheet + programming guide)."""

    model: str
    family: str
    freq_min: float
    freq_max: float
    rbw_min: float
    rbw_max: float
    max_points: int
    tracking_generator: bool
    rtsa: bool
    rtsa_bandwidth: Optional[float]
    screenshot: bool
    preamp: bool
    markers: int
    traces: int
    attenuation_max: float
    ref_level_min: float
    ref_level_max: float
    tg_level_min: float
    tg_level_max: float
    points_settable: bool = True


def _dsa800(model: str, fmax: float, tg: bool, preamp: bool = True) -> SAModelSpec:
    # DSA800/E datasheet: 9 kHz .. 1.5/3.2/7.5 GHz, RBW 10 Hz..1 MHz, preamp on
    # DSA832/875/832E (DSA815 preamp is the PA-DSA815 option). DSA800 guide:
    # points 101..3001, atten 0..30 dB, RLEV -100..20 dBm, TG -40..0 dBm.
    return SAModelSpec(model, "DSA800", 9e3, fmax, 10.0, 1e6, 3001, tg, False, None,
                       False, preamp, 4, 3, 30.0, -100.0, 20.0, -40.0, 0.0)


def _dsa700(model: str, fmax: float) -> SAModelSpec:
    # DSA700 datasheet: 100 kHz .. 500 MHz / 1 GHz, RBW 100 Hz..1 MHz, no TG.
    # DSA700 guide has no [:SENSe]:SWEep:POINts (fixed 601 points).
    return SAModelSpec(model, "DSA800", 100e3, fmax, 100.0, 1e6, 601, False, False, None,
                       False, True, 4, 3, 30.0, -100.0, 20.0, 0.0, 0.0, points_settable=False)


def _dsa1000(model: str, tg: bool, rbw_min: float) -> SAModelSpec:
    # DSA1000/A datasheet: 9 kHz..3 GHz, RBW 100 Hz (DSA1030) / 10 Hz (DSA1030A).
    # DSA1000 guide: points 101..3001, atten 0..50 dB, RLEV -100..30 dBm,
    # TG level -20..0 dBm (DSA1030-TG).
    return SAModelSpec(model, "DSA1000", 9e3, 3e9, rbw_min, 1e6, 3001, tg, False, None,
                       False, True, 4, 3, 50.0, -100.0, 30.0, -20.0, 0.0)


def _rsa3000(model: str, fmax: float, tg: bool, rtbw: float) -> SAModelSpec:
    # RSA3000/3000E datasheets: 9 kHz..1.5/3/4.5 GHz, RBW 1 Hz..10 MHz,
    # RTSA 10 MHz (3000E) / 40 MHz (3000 with B40).  Guide: points 101..10001,
    # atten 0..50 dB, RLEV -170..30 dBm, TG -40..0 dBm.
    return SAModelSpec(model, "RSA3000", 9e3, fmax, 1.0, 10e6, 10001, tg, True, rtbw,
                       False, True, 8, 6, 50.0, -170.0, 30.0, -40.0, 0.0)


def _rsa5000(model: str, fmax: float, tg: bool) -> SAModelSpec:
    # RSA5000 datasheet: 9 kHz..3.2/6.5 GHz, RBW 1 Hz, RTSA 25 MHz (40 MHz opt).
    return SAModelSpec(model, "RSA5000", 9e3, fmax, 1.0, 10e6, 10001, tg, True, 40e6,
                       False, True, 8, 6, 50.0, -170.0, 30.0, -40.0, 0.0)


def _rsa800(model: str, fmax: float) -> SAModelSpec:
    # RSA800 datasheet: 5 kHz..4.5/8.5/14 GHz, RBW 1 Hz..10 MHz, RTBW 40 MHz,
    # TG built in (-40..0 dBm).  :MMEMory:STORe:SCReen:DATA? documented.
    return SAModelSpec(model, "RSA800", 5e3, fmax, 1.0, 10e6, 10001, True, True, 40e6,
                       True, True, 8, 6, 50.0, -170.0, 30.0, -40.0, 0.0)


def _rsa6000(model: str, fmax: float) -> SAModelSpec:
    # RSA6000 datasheet: 5 kHz..8.5/14/26.5 GHz, RBW 1 Hz..10 MHz, RTBW 80 MHz
    # (200 MHz opt).  TG is the RSA6000-TG variant.
    return SAModelSpec(model, "RSA6000", 5e3, fmax, 1.0, 10e6, 10001, False, True, 80e6,
                       True, True, 8, 6, 50.0, -170.0, 30.0, -40.0, 0.0)


MODEL_TABLE: Dict[str, SAModelSpec] = {
    # DSA700 (DSA700 Data Sheet)
    "DSA705": _dsa700("DSA705", 500e6),
    "DSA710": _dsa700("DSA710", 1e9),
    # DSA800 / DSA800E (DSA800/E Series Datasheet)
    "DSA815": _dsa800("DSA815", 1.5e9, False, preamp=False),
    "DSA815-TG": _dsa800("DSA815-TG", 1.5e9, True, preamp=False),
    "DSA832": _dsa800("DSA832", 3.2e9, False),
    "DSA832-TG": _dsa800("DSA832-TG", 3.2e9, True),
    "DSA875": _dsa800("DSA875", 7.5e9, False),
    "DSA875-TG": _dsa800("DSA875-TG", 7.5e9, True),
    "DSA832E": _dsa800("DSA832E", 3.2e9, False),
    "DSA832E-TG": _dsa800("DSA832E-TG", 3.2e9, True),
    # DSA1000 / DSA1000A (DSA1000A Datasheet)
    "DSA1030": _dsa1000("DSA1030", False, 100.0),
    "DSA1030-TG": _dsa1000("DSA1030-TG", True, 100.0),
    "DSA1030A": _dsa1000("DSA1030A", False, 10.0),
    "DSA1030A-TG": _dsa1000("DSA1030A-TG", True, 10.0),
    # RSA3000E / RSA3000 (datasheets)
    "RSA3015E": _rsa3000("RSA3015E", 1.5e9, False, 10e6),
    "RSA3015E-TG": _rsa3000("RSA3015E-TG", 1.5e9, True, 10e6),
    "RSA3030E": _rsa3000("RSA3030E", 3e9, False, 10e6),
    "RSA3030E-TG": _rsa3000("RSA3030E-TG", 3e9, True, 10e6),
    "RSA3015N": _rsa3000("RSA3015N", 1.5e9, False, 40e6),
    "RSA3030": _rsa3000("RSA3030", 3e9, False, 40e6),
    "RSA3030-TG": _rsa3000("RSA3030-TG", 3e9, True, 40e6),
    "RSA3030N": _rsa3000("RSA3030N", 3e9, False, 40e6),
    "RSA3045": _rsa3000("RSA3045", 4.5e9, False, 40e6),
    "RSA3045-TG": _rsa3000("RSA3045-TG", 4.5e9, True, 40e6),
    "RSA3045N": _rsa3000("RSA3045N", 4.5e9, False, 40e6),
    # RSA5000 (datasheet)
    "RSA5032": _rsa5000("RSA5032", 3.2e9, False),
    "RSA5032-TG": _rsa5000("RSA5032-TG", 3.2e9, True),
    "RSA5032N": _rsa5000("RSA5032N", 3.2e9, False),
    "RSA5065": _rsa5000("RSA5065", 6.5e9, False),
    "RSA5065-TG": _rsa5000("RSA5065-TG", 6.5e9, True),
    "RSA5065N": _rsa5000("RSA5065N", 6.5e9, False),
    # RSA800 (datasheet)
    "RSA804": _rsa800("RSA804", 4.5e9),
    "RSA808": _rsa800("RSA808", 8.5e9),
    "RSA814": _rsa800("RSA814", 14e9),
    # RSA6000 (datasheet)
    "RSA6085": _rsa6000("RSA6085", 8.5e9),
    "RSA6140": _rsa6000("RSA6140", 14e9),
    "RSA6265": _rsa6000("RSA6265", 26.5e9),
}


def lookup_model(model: str, default: str) -> SAModelSpec:
    """Find the table row for an *IDN? model string (case/whitespace tolerant)."""
    key = (model or "").strip().upper().replace(" ", "")
    if key in MODEL_TABLE:
        return MODEL_TABLE[key]
    # RSA6000-TG style suffixes not in the table: fall back to the base row
    # but keep the TG flag.
    if key.endswith("-TG") and key[:-3] in MODEL_TABLE:
        base = MODEL_TABLE[key[:-3]]
        return SAModelSpec(**{**base.__dict__, "model": key, "tracking_generator": True})
    return MODEL_TABLE[default]


# --------------------------------------------------------------------------- #
# Vocabulary normalisation
# --------------------------------------------------------------------------- #

_UNIT_NAMES = {"DBM": "dBm", "DBMV": "dBmV", "DBUV": "dBuV", "V": "V", "W": "W",
               "DBMA": "dBmA", "DBUA": "dBuA"}
_UNIT_KEYWORDS = {"DBM": "DBM", "DBMV": "DBMV", "DBUV": "DBUV", "V": "V", "W": "W",
                  "VOLT": "V", "VOLTS": "V", "WATT": "W", "WATTS": "W"}

_DETECTOR_ALIASES = {
    "POS": "POSitive", "POSITIVE": "POSitive", "PEAK": "POSitive",
    "NEG": "NEGative", "NEGATIVE": "NEGative",
    "NORM": "NORMal", "NORMAL": "NORMal",
    "SAMP": "SAMPle", "SAMPLE": "SAMPle",
    "RMS": "RMS", "RAV": "RMS", "RAVERAGE": "RMS",
    "VAV": "VAVerage", "VAVERAGE": "VAVerage", "AVER": "VAVerage", "AVERAGE": "VAVerage",
    "QPE": "QPEak", "QPEAK": "QPEak", "QUASI": "QPEak", "QUASIPEAK": "QPEak",
}
# Instrument replies -> canonical short names reported to callers.
_DETECTOR_REPLIES = {
    "POS": "POSITIVE", "POSITIVE": "POSITIVE",
    "NEG": "NEGATIVE", "NEGATIVE": "NEGATIVE",
    "NORM": "NORMAL", "NORMAL": "NORMAL",
    "SAMP": "SAMPLE", "SAMPLE": "SAMPLE",
    "RMS": "RMS", "RAV": "RMS", "RAVERAGE": "RMS",
    "VAV": "VAVERAGE", "VAVERAGE": "VAVERAGE", "AVER": "VAVERAGE", "AVERAGE": "VAVERAGE",
    "QPE": "QPEAK", "QPEAK": "QPEAK",
}

_TRACE_MODE_ALIASES = {
    "WRITE": "WRITE", "WRIT": "WRITE", "CLEARWRITE": "WRITE", "CLEAR_WRITE": "WRITE",
    "MAXHOLD": "MAXHOLD", "MAXH": "MAXHOLD", "MAX": "MAXHOLD",
    "MINHOLD": "MINHOLD", "MINH": "MINHOLD", "MIN": "MINHOLD",
    "VIEW": "VIEW", "FREEZE": "VIEW",
    "BLANK": "BLANK", "BLAN": "BLANK", "OFF": "BLANK",
    "AVERAGE": "AVERAGE", "AVER": "AVERAGE", "AVG": "AVERAGE",
    "VIDEOAVG": "VIDEOAVG", "VID": "VIDEOAVG", "POWERAVG": "POWERAVG", "POW": "POWERAVG",
}

_OVERLOAD = 9.0e37


def parse_number(raw: str) -> Optional[float]:
    """Parse a numeric reply; None when empty/invalid/overload."""
    text = (raw or "").strip().strip('"').split(",")[0].strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        m = re.match(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text)
        if not m:
            return None
        value = float(m.group(0))
    if math.isnan(value) or math.isinf(value) or abs(value) >= _OVERLOAD:
        return None
    return value


def _strip_block_header(text: str) -> str:
    """Remove a leading IEEE ``#<d><len>`` header from an ASCII reply, if any."""
    text = text.lstrip()
    if not text.startswith("#") or len(text) < 2 or not text[1].isdigit():
        return text
    ndigits = int(text[1])
    if ndigits == 0:
        # #0 = indefinite length block, data follows directly
        return text[2:]
    return text[2 + ndigits:]


def parse_ascii_trace(text: str) -> List[float]:
    """Parse ``:TRACe:DATA?`` ASCII output (with or without ``#9<len>`` header)."""
    body = _strip_block_header(text)
    values: List[float] = []
    for token in body.replace(";", ",").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            values.append(float(token))
        except ValueError:
            # tolerate a trailing unit or stray character on some firmware
            m = re.match(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", token)
            if m:
                values.append(float(m.group(0)))
    return values


def parse_binary_trace(payload: bytes, fmt: str = "REAL,32", little_endian: bool = True) -> List[float]:
    """Unpack the payload of a ``#<d><len>`` block (header already removed).

    If ``payload`` still carries the header it is stripped here too.
    """
    data = bytes(payload)
    if data[:1] == b"#" and len(data) > 1 and chr(data[1]).isdigit():
        nd = int(chr(data[1]))
        length = int(data[2:2 + nd]) if nd else len(data) - 2
        data = data[2 + nd:2 + nd + length]
    code = {"REAL,32": "f", "REAL,64": "d", "INTEGER,32": "i", "INT,32": "i"}[fmt.upper()]
    size = struct.calcsize(code)
    count = len(data) // size
    order = "<" if little_endian else ">"
    values = list(struct.unpack(f"{order}{count}{code}", data[:count * size]))
    if code == "i":
        # INTeger,32 is the amplitude in 0.001 dB units on RSA firmware (not
        # documented in detail); expose the raw scaled value.
        values = [v / 1000.0 for v in values]
    return [float(v) for v in values]


def compute_frequencies(start: float, stop: float, count: int) -> List[float]:
    """Frequency axis for ``count`` evenly spaced points from start to stop."""
    if count <= 1:
        return [start] * max(count, 0)
    step = (stop - start) / (count - 1)
    return [start + i * step for i in range(count)]


def _to_bool_word(enabled: bool) -> str:
    return "ON" if enabled else "OFF"


def _is_on(reply: str) -> bool:
    return reply.strip().upper() in ("1", "ON", "TRUE")


# --------------------------------------------------------------------------- #
# Base driver
# --------------------------------------------------------------------------- #


class RigolSABase(BaseEquipment):
    """Common implementation of the Rigol spectrum-analyzer SCPI tree."""

    # ---- family constants (overridden by subclasses) ----------------------
    FAMILY = "DSA800"
    DEFAULT_MODEL = "DSA815"
    INTERFACES: Sequence[str] = ("USB", "LAN")
    # Trace type command: DSA uses :TRACe<n>:MODE, RSA800/6000 only :TRACe<n>:TYPE
    # (RSA3000/5000 accept both).
    TRACE_MODE_CMD = ":TRACe{n}:MODE"
    TRACE_MODE_KEYWORDS: Dict[str, str] = {
        "WRITE": "WRITe", "MAXHOLD": "MAXHold", "MINHOLD": "MINHold", "VIEW": "VIEW",
        "BLANK": "BLANk", "VIDEOAVG": "VIDeoavg", "POWERAVG": "POWeravg",
    }
    # RSA firmware has no VIEW/BLANk trace type; emulate with DISPlay/UPDate.
    TRACE_VIEW_VIA_UPDATE = False
    # Peak search mode lives under MARKer<n> on DSA, under MARKer on RSA.
    PEAK_SEARCH_MODE_CMD = ":CALCulate:MARKer{n}:PEAK:SEARch:MODE"
    AVERAGE_COUNT_CMD = ":TRACe:AVERage:COUNt"
    AVERAGE_RESET_CMD = ":TRACe:AVERage:RESet"
    DETECTOR_CMD = ":SENSe:DETector:FUNCtion"
    DETECTOR_PER_TRACE = False
    DETECTOR_KEYWORDS: Sequence[str] = ("POSitive", "NEGative", "NORMal", "SAMPle", "RMS", "VAVerage", "QPEak")
    TG_OUTPUT_CMD = ":OUTPut:STATe"
    TG_LEVEL_CMD = ":SOURce:POWer:LEVel:IMMediate:AMPLitude"
    ZERO_SPAN_CMD = ":SENSe:FREQuency:SPAN 0"
    # DSA marker types (RSA: POSition|DELTa|FIXed|OFF)
    MARKER_MODES: Sequence[str] = ("POSition", "DELTa", "BAND", "SPAN")
    HAS_OPERATION_CONDITION = True  # :STATus:OPERation:CONDition? (bit 3 = SWEeping)
    HAS_MODE_SELECT = False  # :INSTrument:SELect
    MODE_KEYWORDS: Dict[str, str] = {}
    # CHPOWER strategy: "DSA" (:CONFigure:CHPower + :FETCh:CHPower?),
    # "RSA_MODE" (:INSTrument:SELect GPSA_CHPower + :FETCh:CHPower1?) or None
    # (no instrument measurement; integrate the trace in software).
    CHPOWER_METHOD: Optional[str] = "DSA"
    BINARY_FORMATS: Sequence[str] = ("REAL,32",)
    SCREENSHOT_CMD: Optional[str] = None
    # Sweep time range from the guides (s).
    SWEEP_TIME_MIN = 20e-6
    SWEEP_TIME_MAX = 7500.0
    # Delay after :INSTrument:SELect (guides recommend 8 s).
    MODE_SWITCH_DELAY_S = 8.0

    def __init__(self, resource_manager, resource_string: str):
        super().__init__(resource_manager, resource_string)
        self.manufacturer = "Rigol"
        self.model = self.DEFAULT_MODEL
        self.serial_number: Optional[str] = None
        self.firmware_version: Optional[str] = None
        self.spec: SAModelSpec = MODEL_TABLE[self.DEFAULT_MODEL]
        self._tg_override: Optional[bool] = None
        self._data_format = "ASCII"
        self._little_endian = False
        self._mode: Optional[str] = None
        self._io_lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Connection / identity
    # ------------------------------------------------------------------ #

    async def connect(self):
        """Open the resource, identify the model and select ASCII trace format."""
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
                # Long sweeps (narrow RBW) can exceed 10 s; single_sweep() adjusts.
                self.instrument.timeout = 15000

                idn = await self._query("*IDN?")
                logger.info(f"Connected to Rigol spectrum analyzer: {idn}")
                self._parse_idn(idn)
                self.connected = True
                self.cached_info = await self.get_info()

                # Known starting point for trace transfers (families with a
                # :FORMat command only; RSA800/6000 are ASCII-only).
                if self.BINARY_FORMATS:
                    try:
                        await self.set_data_format("ASCII")
                    except Exception as e:  # pragma: no cover - defensive
                        logger.debug(f"Could not set trace format: {e}")
                if self.HAS_MODE_SELECT:
                    try:
                        await self.get_mode()
                    except Exception as e:  # pragma: no cover - defensive
                        logger.debug(f"Could not read mode: {e}")
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
        self.spec = lookup_model(self.model, self.DEFAULT_MODEL)
        return info

    async def get_info(self) -> EquipmentInfo:
        idn = await self._query("*IDN?")
        info = self._parse_idn(idn)
        return EquipmentInfo(
            id=generate_equipment_id(self.resource_string, "sa_"),
            type=EquipmentType.SPECTRUM_ANALYZER,
            manufacturer=info["manufacturer"] or self.manufacturer,
            model=info["model"] or self.model,
            serial_number=info["serial"],
            connection_type=self._determine_connection_type(),
            resource_string=self.resource_string,
        )

    @property
    def has_tracking_generator(self) -> bool:
        if self._tg_override is not None:
            return self._tg_override
        return self.spec.tracking_generator

    def _capabilities(self) -> Dict[str, Any]:
        s = self.spec
        return {
            "family": self.FAMILY,
            "model_table_entry": s.model,
            "frequency_min": s.freq_min,
            "frequency_max": s.freq_max,
            "rbw_min": s.rbw_min,
            "rbw_max": s.rbw_max,
            "max_points": s.max_points,
            "points_settable": s.points_settable,
            "has_tracking_generator": self.has_tracking_generator,
            "tracking_generator_level_range": [s.tg_level_min, s.tg_level_max] if self.has_tracking_generator else None,
            "supports_rtsa": s.rtsa,
            "rtsa_bandwidth": s.rtsa_bandwidth,
            "supports_screenshot": s.screenshot and self.SCREENSHOT_CMD is not None,
            "has_preamp": s.preamp,
            "markers": s.markers,
            "traces": s.traces,
            "attenuation_range": [0.0, s.attenuation_max],
            "reference_level_range": [s.ref_level_min, s.ref_level_max],
            "detectors": [d.upper() for d in self.DETECTOR_KEYWORDS],
            "trace_modes": list(self.TRACE_MODE_KEYWORDS.keys()) + (["VIEW", "BLANK"] if self.TRACE_VIEW_VIA_UPDATE else []),
            "marker_modes": [m.upper() for m in self.MARKER_MODES],
            "data_formats": ["ASCII"] + list(self.BINARY_FORMATS),
            "supports_mode_select": self.HAS_MODE_SELECT,
            "modes": sorted(set(self.MODE_KEYWORDS.values())) if self.HAS_MODE_SELECT else [],
            "channel_power_method": self.CHPOWER_METHOD or "trace_integration",
            "measurement_channels": ["PEAK", "PEAK_FREQ", "MARKER1..MARKER%d" % s.markers,
                                     "MARKER1_FREQ", "CHPOWER", "TRACE1:MAX", "TRACE1:MIN", "TRACE1:MEAN"],
            "interfaces": list(self.INTERFACES),
            "supports_acquisition": True,
        }

    async def get_status(self) -> EquipmentStatus:
        try:
            idn = await self._query("*IDN?")
            info = self._parse_idn(idn)
            capabilities = self._capabilities()
            if self.HAS_MODE_SELECT:
                capabilities["mode"] = self._mode
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

    def set_tracking_generator_fitted(self, fitted: Optional[bool]) -> bool:
        """Override TG detection (``None`` returns to the model-table value).

        *IDN? may report ``DSA815`` for a DSA815-TG; use this when the option
        is fitted but the model string does not say so.
        """
        self._tg_override = None if fitted is None else bool(fitted)
        return self.has_tracking_generator

    async def reset(self):
        await self._write("*RST")
        await asyncio.sleep(1.0)
        self._data_format = "ASCII"
        self._little_endian = False

    async def get_error(self) -> Dict[str, Any]:
        raw = await self._query(":SYSTem:ERRor?")
        code_str, _, message = raw.partition(",")
        try:
            code = int(float(code_str.strip()))
        except ValueError:
            code = None
        return {"code": code, "message": message.strip().strip('"'), "raw": raw}

    # ------------------------------------------------------------------ #
    # Command dispatch
    # ------------------------------------------------------------------ #

    async def execute_command(self, command: str, parameters: dict) -> Any:
        parameters = dict(parameters or {})
        handlers = {
            # frequency
            "set_frequency": self.set_frequency,
            "set_start_stop": self.set_start_stop,
            "get_frequency": self.get_frequency,
            "set_full_span": self.set_full_span,
            "set_zero_span": self.set_zero_span,
            # bandwidth
            "set_rbw": self.set_rbw,
            "set_vbw": self.set_vbw,
            "get_bandwidth": self.get_bandwidth,
            # amplitude
            "set_reference_level": self.set_reference_level,
            "set_attenuation": self.set_attenuation,
            "set_preamp": self.set_preamp,
            "set_unit": self.set_unit,
            "get_amplitude": self.get_amplitude,
            # sweep
            "set_sweep": self.set_sweep,
            "get_sweep": self.get_sweep,
            "single_sweep": self.single_sweep,
            "continuous": self.set_continuous,
            "set_continuous": self.set_continuous,
            "trigger_sweep": self.trigger_sweep,
            # detector / trace / average
            "set_detector": self.set_detector,
            "get_detector": self.get_detector,
            "set_trace_mode": self.set_trace_mode,
            "get_trace_mode": self.get_trace_mode,
            "set_average": self.set_average,
            "set_data_format": self.set_data_format,
            "get_trace": self.get_trace,
            "get_readings": self.get_readings,
            "get_measurement": self.get_measurement,
            "get_measurements": self.get_measurements,
            # markers
            "peak_search": self.peak_search,
            "next_peak": self.next_peak,
            "set_marker": self.set_marker,
            "get_marker": self.get_marker,
            "marker_off": self.marker_off,
            "all_markers_off": self.all_markers_off,
            "marker_to_center": self.marker_to_center,
            "set_peak_search_mode": self.set_peak_search_mode,
            # TG / measurements / mode
            "set_tracking_generator": self.set_tracking_generator,
            "get_tracking_generator": self.get_tracking_generator,
            "measure_channel_power": self.measure_channel_power,
            "measure_obw": self.measure_obw,
            "set_mode": self.set_mode,
            "get_mode": self.get_mode,
            "get_screenshot": self.get_screenshot,
            # system
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
    # Frequency
    # ------------------------------------------------------------------ #

    def _check_frequency(self, value: float, name: str) -> float:
        value = float(value)
        if not 0.0 <= value <= self.spec.freq_max:
            raise ValueError(
                f"{name} must be 0..{self.spec.freq_max:g} Hz on {self.spec.model}"
            )
        return value

    async def set_frequency(self, center: Optional[float] = None, span: Optional[float] = None) -> Dict[str, float]:
        """Set center frequency and/or span (Hz)."""
        if center is not None:
            center = self._check_frequency(center, "center")
            await self._write(f":SENSe:FREQuency:CENTer {center:.0f}")
        if span is not None:
            span = float(span)
            if span < 0 or span > self.spec.freq_max:
                raise ValueError(f"span must be 0..{self.spec.freq_max:g} Hz")
            if span == 0:
                await self._write(self.ZERO_SPAN_CMD)
            else:
                await self._write(f":SENSe:FREQuency:SPAN {span:.0f}")
        return await self.get_frequency()

    async def set_start_stop(self, start: float, stop: float) -> Dict[str, float]:
        start = self._check_frequency(start, "start")
        stop = self._check_frequency(stop, "stop")
        if stop < start:
            raise ValueError("stop must be >= start")
        await self._write(f":SENSe:FREQuency:STARt {start:.0f}")
        await self._write(f":SENSe:FREQuency:STOP {stop:.0f}")
        return await self.get_frequency()

    async def set_full_span(self) -> Dict[str, float]:
        await self._write(":SENSe:FREQuency:SPAN:FULL")
        return await self.get_frequency()

    async def set_zero_span(self) -> Dict[str, float]:
        await self._write(self.ZERO_SPAN_CMD)
        return await self.get_frequency()

    async def get_frequency(self) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for key, cmd in (("center", ":SENSe:FREQuency:CENTer?"), ("span", ":SENSe:FREQuency:SPAN?"),
                         ("start", ":SENSe:FREQuency:STARt?"), ("stop", ":SENSe:FREQuency:STOP?")):
            out[key] = float((await self._query(cmd)).strip())
        return out

    # ------------------------------------------------------------------ #
    # Bandwidth
    # ------------------------------------------------------------------ #

    async def set_rbw(self, rbw: Union[float, str], auto: bool = False) -> Dict[str, Any]:
        """Resolution bandwidth in Hz (1-3-10 steps), or auto coupling."""
        if auto or (isinstance(rbw, str) and rbw.strip().upper() == "AUTO"):
            await self._write(":SENSe:BANDwidth:RESolution:AUTO ON")
        else:
            rbw = float(rbw)
            if not self.spec.rbw_min <= rbw <= self.spec.rbw_max:
                raise ValueError(
                    f"RBW must be {self.spec.rbw_min:g}..{self.spec.rbw_max:g} Hz on {self.spec.model}"
                )
            await self._write(":SENSe:BANDwidth:RESolution:AUTO OFF")
            await self._write(f":SENSe:BANDwidth:RESolution {rbw:.0f}")
        return await self.get_bandwidth()

    async def set_vbw(self, vbw: Union[float, str], auto: bool = False) -> Dict[str, Any]:
        """Video bandwidth in Hz (1-3-10 steps), or auto coupling."""
        if auto or (isinstance(vbw, str) and vbw.strip().upper() == "AUTO"):
            await self._write(":SENSe:BANDwidth:VIDeo:AUTO ON")
        else:
            vbw = float(vbw)
            if vbw < 1.0 or vbw > 10e6:
                raise ValueError("VBW must be 1 Hz..10 MHz")
            await self._write(":SENSe:BANDwidth:VIDeo:AUTO OFF")
            await self._write(f":SENSe:BANDwidth:VIDeo {vbw:.0f}")
        return await self.get_bandwidth()

    async def get_bandwidth(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "rbw": float((await self._query(":SENSe:BANDwidth:RESolution?")).strip()),
            "vbw": float((await self._query(":SENSe:BANDwidth:VIDeo?")).strip()),
        }
        for key, cmd in (("rbw_auto", ":SENSe:BANDwidth:RESolution:AUTO?"),
                         ("vbw_auto", ":SENSe:BANDwidth:VIDeo:AUTO?")):
            try:
                out[key] = _is_on(await self._query(cmd))
            except Exception:
                out[key] = None
        return out

    # ------------------------------------------------------------------ #
    # Amplitude
    # ------------------------------------------------------------------ #

    async def set_reference_level(self, level: float) -> Dict[str, Any]:
        level = float(level)
        if not self.spec.ref_level_min <= level <= self.spec.ref_level_max:
            raise ValueError(
                f"Reference level must be {self.spec.ref_level_min:g}..{self.spec.ref_level_max:g} dBm"
            )
        await self._write(f":DISPlay:WINdow:TRACe:Y:SCALe:RLEVel {level:g}")
        return await self.get_amplitude()

    async def set_attenuation(self, db: Optional[float] = None, auto: bool = False) -> Dict[str, Any]:
        if auto or db is None:
            await self._write(":SENSe:POWer:RF:ATTenuation:AUTO ON")
        else:
            db = float(db)
            if not 0.0 <= db <= self.spec.attenuation_max:
                raise ValueError(f"Attenuation must be 0..{self.spec.attenuation_max:g} dB")
            await self._write(":SENSe:POWer:RF:ATTenuation:AUTO OFF")
            await self._write(f":SENSe:POWer:RF:ATTenuation {db:g}")
        return await self.get_amplitude()

    async def set_preamp(self, enabled: bool) -> bool:
        if not self.spec.preamp:
            raise ValueError(f"{self.spec.model} has no preamplifier")
        await self._write(f":SENSe:POWer:RF:GAIN:STATe {_to_bool_word(enabled)}")
        return _is_on(await self._query(":SENSe:POWer:RF:GAIN:STATe?"))

    async def set_unit(self, unit: str) -> str:
        key = _UNIT_KEYWORDS.get(str(unit).strip().upper().replace("μ", "U"))
        if key is None:
            raise ValueError("Unit must be one of DBM, DBMV, DBUV, V, W")
        await self._write(f":UNIT:POWer {key}")
        return await self.get_unit()

    async def get_unit(self) -> str:
        raw = (await self._query(":UNIT:POWer?")).strip().upper()
        return _UNIT_NAMES.get(raw, raw or "dBm")

    async def get_amplitude(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "reference_level": float((await self._query(":DISPlay:WINdow:TRACe:Y:SCALe:RLEVel?")).strip()),
            "attenuation": float((await self._query(":SENSe:POWer:RF:ATTenuation?")).strip()),
        }
        for key, cmd in (("attenuation_auto", ":SENSe:POWer:RF:ATTenuation:AUTO?"),
                         ("preamp", ":SENSe:POWer:RF:GAIN:STATe?")):
            try:
                out[key] = _is_on(await self._query(cmd))
            except Exception:
                out[key] = None
        try:
            out["unit"] = await self.get_unit()
        except Exception:
            out["unit"] = "dBm"
        return out

    # ------------------------------------------------------------------ #
    # Sweep
    # ------------------------------------------------------------------ #

    async def set_sweep(
        self,
        points: Optional[int] = None,
        time: Optional[Union[float, str]] = None,
        continuous: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Sweep points, sweep time (s or 'AUTO') and continuous/single mode."""
        if points is not None:
            if not self.spec.points_settable:
                raise ValueError(f"{self.spec.model} has a fixed {self.spec.max_points}-point sweep")
            points = int(points)
            if not 101 <= points <= self.spec.max_points:
                raise ValueError(f"Sweep points must be 101..{self.spec.max_points}")
            await self._write(f":SENSe:SWEep:POINts {points}")
        if time is not None:
            if isinstance(time, str) and time.strip().upper() == "AUTO":
                await self._write(":SENSe:SWEep:TIME:AUTO ON")
            else:
                t = float(time)
                if not self.SWEEP_TIME_MIN <= t <= self.SWEEP_TIME_MAX:
                    raise ValueError(f"Sweep time must be {self.SWEEP_TIME_MIN:g}..{self.SWEEP_TIME_MAX:g} s")
                await self._write(":SENSe:SWEep:TIME:AUTO OFF")
                await self._write(f":SENSe:SWEep:TIME {t:g}")
        if continuous is not None:
            await self._write(f":INITiate:CONTinuous {_to_bool_word(continuous)}")
        return await self.get_sweep()

    async def set_continuous(self, enabled: bool = True) -> bool:
        await self._write(f":INITiate:CONTinuous {_to_bool_word(enabled)}")
        return _is_on(await self._query(":INITiate:CONTinuous?"))

    async def trigger_sweep(self) -> None:
        """Start one sweep (:INITiate:IMMediate) without waiting."""
        await self._write(":INITiate:IMMediate")

    async def get_sweep(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if self.spec.points_settable:
            out["points"] = int(float((await self._query(":SENSe:SWEep:POINts?")).strip()))
        else:
            out["points"] = self.spec.max_points
        out["time"] = float((await self._query(":SENSe:SWEep:TIME?")).strip())
        for key, cmd in (("time_auto", ":SENSe:SWEep:TIME:AUTO?"), ("continuous", ":INITiate:CONTinuous?")):
            try:
                out[key] = _is_on(await self._query(cmd))
            except Exception:
                out[key] = None
        return out

    async def _sweep_in_progress(self) -> bool:
        raw = await self._query(":STATus:OPERation:CONDition?")
        return bool(int(float(raw.strip())) & 0x08)  # bit 3 = SWEeping

    async def single_sweep(self, timeout_s: Optional[float] = None) -> bool:
        """Switch to single mode, run one sweep and wait for it to finish.

        Uses ``*OPC?`` and, where the family has it, polls
        ``:STATus:OPERation:CONDition?`` until the SWEeping bit clears.
        Returns True when the sweep finished inside ``timeout_s``.
        """
        async with self._io_lock:
            await self._write(":INITiate:CONTinuous OFF")
            if timeout_s is None:
                try:
                    sweep_time = float((await self._query(":SENSe:SWEep:TIME?")).strip())
                except Exception:
                    sweep_time = 1.0
                timeout_s = max(5.0, sweep_time * 3 + 2.0)
            old_timeout = self.instrument.timeout if self.instrument is not None else None
            if self.instrument is not None:
                self.instrument.timeout = int(max(timeout_s, 1.0) * 1000) + 1000
            try:
                await self._write(":INITiate:IMMediate")
                opc = (await self._query("*OPC?")).strip()
                done = opc in ("1", "+1")
                if self.HAS_OPERATION_CONDITION:
                    deadline = asyncio.get_event_loop().time() + timeout_s
                    while await self._sweep_in_progress():
                        if asyncio.get_event_loop().time() > deadline:
                            return False
                        await asyncio.sleep(0.05)
                    done = True
                return done
            finally:
                if self.instrument is not None and old_timeout is not None:
                    self.instrument.timeout = old_timeout

    # ------------------------------------------------------------------ #
    # Detector / trace mode / averaging / data format
    # ------------------------------------------------------------------ #

    def _detector_keyword(self, detector: str) -> str:
        key = str(detector).strip().upper().replace("-", "").replace("_", "")
        canon = _DETECTOR_ALIASES.get(key)
        if canon is None or canon not in self.DETECTOR_KEYWORDS:
            raise ValueError(f"Detector must be one of {[d.upper() for d in self.DETECTOR_KEYWORDS]}")
        return canon

    async def set_detector(self, detector: str, trace: int = 1) -> str:
        keyword = self._detector_keyword(detector)
        if self.DETECTOR_PER_TRACE:
            self._check_trace(trace)
            await self._write(f":SENSe:DETector:TRACe{trace} {keyword}")
        else:
            await self._write(f"{self.DETECTOR_CMD} {keyword}")
        return await self.get_detector(trace)

    async def get_detector(self, trace: int = 1) -> str:
        if self.DETECTOR_PER_TRACE:
            raw = await self._query(f":SENSe:DETector:TRACe{trace}?")
        else:
            raw = await self._query(f"{self.DETECTOR_CMD}?")
        raw = raw.strip().upper()
        return _DETECTOR_REPLIES.get(raw, raw)

    def _check_trace(self, trace: int) -> int:
        trace = int(trace)
        if not 1 <= trace <= self.spec.traces:
            raise ValueError(f"Trace must be 1..{self.spec.traces}")
        return trace

    async def set_trace_mode(self, trace: int = 1, mode: str = "WRITE") -> str:
        """Trace type: WRITE, MAXHOLD, MINHOLD, VIEW, BLANK, AVERAGE (family dependent)."""
        trace = self._check_trace(trace)
        key = _TRACE_MODE_ALIASES.get(str(mode).strip().upper().replace(" ", ""))
        if key is None:
            raise ValueError(f"Unknown trace mode '{mode}'")
        if key in self.TRACE_MODE_KEYWORDS:
            await self._write(self.TRACE_MODE_CMD.format(n=trace) + " " + self.TRACE_MODE_KEYWORDS[key])
            if self.TRACE_VIEW_VIA_UPDATE:
                await self._write(f":TRACe{trace}:DISPlay:STATe ON")
                await self._write(f":TRACe{trace}:UPDate:STATe ON")
        elif self.TRACE_VIEW_VIA_UPDATE and key == "VIEW":
            await self._write(f":TRACe{trace}:DISPlay:STATe ON")
            await self._write(f":TRACe{trace}:UPDate:STATe OFF")
        elif self.TRACE_VIEW_VIA_UPDATE and key == "BLANK":
            await self._write(f":TRACe{trace}:DISPlay:STATe OFF")
            await self._write(f":TRACe{trace}:UPDate:STATe OFF")
        elif key == "AVERAGE" and "VIDEOAVG" in self.TRACE_MODE_KEYWORDS:
            # DSA family spells trace averaging as video average.
            await self._write(self.TRACE_MODE_CMD.format(n=trace) + " " + self.TRACE_MODE_KEYWORDS["VIDEOAVG"])
        else:
            raise ValueError(
                f"{self.spec.model} trace modes: {sorted(self._capabilities()['trace_modes'])}"
            )
        return await self.get_trace_mode(trace)

    async def get_trace_mode(self, trace: int = 1) -> str:
        trace = self._check_trace(trace)
        raw = (await self._query(self.TRACE_MODE_CMD.format(n=trace) + "?")).strip().upper()
        mode = _TRACE_MODE_ALIASES.get(raw, raw)
        if self.TRACE_VIEW_VIA_UPDATE:
            try:
                shown = _is_on(await self._query(f":TRACe{trace}:DISPlay:STATe?"))
                updating = _is_on(await self._query(f":TRACe{trace}:UPDate:STATe?"))
                if not shown:
                    return "BLANK"
                if not updating:
                    return "VIEW"
            except Exception:
                pass
        return mode

    async def set_average(self, count: int = 100, trace: int = 1, enabled: bool = True) -> Dict[str, Any]:
        """Trace averaging: set the count and put ``trace`` in average mode."""
        count = int(count)
        if not 1 <= count <= 10000:
            raise ValueError("Average count must be 1..10000")
        await self._write(f"{self.AVERAGE_COUNT_CMD} {count}")
        if enabled:
            await self.set_trace_mode(trace, "AVERAGE")
            try:
                await self._write(self.AVERAGE_RESET_CMD)
            except Exception:
                pass
        else:
            await self.set_trace_mode(trace, "WRITE")
        current = int(float((await self._query(f"{self.AVERAGE_COUNT_CMD}?")).strip()))
        return {"count": current, "trace": trace, "enabled": bool(enabled)}

    async def set_data_format(self, fmt: str = "ASCII") -> str:
        """Trace transfer format: ASCII or one of the family's binary formats."""
        key = str(fmt).strip().upper().replace(" ", "")
        if key in ("ASCII", "ASC", "ASCII,8", "ASC,8"):
            await self._write(":FORMat:TRACe:DATA ASCii")
            self._data_format = "ASCII"
        else:
            key = {"REAL": "REAL,32", "REAL32": "REAL,32", "REAL64": "REAL,64", "INT32": "INTEGER,32",
                   "INT,32": "INTEGER,32", "INTEGER32": "INTEGER,32"}.get(key, key)
            if key not in [b.upper() for b in self.BINARY_FORMATS]:
                raise ValueError(f"{self.spec.model} supports formats: ASCII, {', '.join(self.BINARY_FORMATS)}")
            scpi = {"REAL,32": "REAL,32", "REAL,64": "REAL,64", "INTEGER,32": "INTeger,32"}[key]
            await self._write(f":FORMat:TRACe:DATA {scpi}")
            # NORMal is MSB-first per the DSA800 guide; ask for LSB-first.
            await self._write(":FORMat:BORDer SWAPped")
            self._little_endian = True
            self._data_format = key
        return self._data_format

    # ------------------------------------------------------------------ #
    # Trace acquisition
    # ------------------------------------------------------------------ #

    async def _query_block(self, command: str) -> bytes:
        """Query an IEEE definite-length block and return its payload bytes.

        Uses pyvisa's ``query_binary_values(datatype='B')`` (header stripped)
        via ``functools.partial`` because ``run_in_executor`` takes no
        keyword arguments; falls back to ``write`` + ``read_raw``.
        """
        await self._ensure_connected()
        if not self.instrument:
            raise RuntimeError("Equipment not connected")
        loop = asyncio.get_event_loop()
        if hasattr(self.instrument, "query_binary_values"):
            fn = functools.partial(self.instrument.query_binary_values, command, datatype="B")
            return bytes(await loop.run_in_executor(None, fn))
        await loop.run_in_executor(None, self.instrument.write, command)
        raw = await loop.run_in_executor(None, self.instrument.read_raw)
        return bytes(raw)

    async def _read_trace_values(self, trace: int) -> List[float]:
        cmd = f":TRACe:DATA? TRACE{trace}"
        if self._data_format == "ASCII":
            return parse_ascii_trace(await self._query(cmd))
        payload = await self._query_block(cmd)
        return parse_binary_trace(payload, self._data_format, self._little_endian)

    async def get_trace(self, trace: int = 1, sweep: bool = False) -> SpectrumData:
        """Read a trace and return it with a derived frequency axis and peak.

        ``sweep=True`` runs a single sweep first (blocking until complete).
        """
        trace = self._check_trace(trace)
        if sweep:
            await self.single_sweep()
        async with self._io_lock:
            freq = await self.get_frequency()
            values = await self._read_trace_values(trace)
            meta: Dict[str, Any] = {}
            try:
                bw = await self.get_bandwidth()
                meta["rbw"], meta["vbw"] = bw["rbw"], bw["vbw"]
            except Exception as e:
                logger.debug(f"Bandwidth query failed: {e}")
            try:
                amp = await self.get_amplitude()
                meta["reference_level"] = amp["reference_level"]
                meta["attenuation"] = amp["attenuation"]
                meta["unit"] = amp.get("unit", "dBm")
            except Exception as e:
                logger.debug(f"Amplitude query failed: {e}")
            try:
                meta["detector"] = await self.get_detector(trace)
            except Exception as e:
                logger.debug(f"Detector query failed: {e}")

        start, stop = freq["start"], freq["stop"]
        frequencies = compute_frequencies(start, stop, len(values))
        peak_f = peak_a = None
        if values:
            idx = max(range(len(values)), key=values.__getitem__)
            peak_a = values[idx]
            peak_f = frequencies[idx]
        return SpectrumData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            trace=trace,
            start_frequency=start,
            stop_frequency=stop,
            center_frequency=freq["center"],
            span=freq["span"],
            rbw=meta.get("rbw"),
            vbw=meta.get("vbw"),
            reference_level=meta.get("reference_level"),
            attenuation=meta.get("attenuation"),
            unit=meta.get("unit", "dBm"),
            detector=meta.get("detector"),
            num_points=len(values),
            values=values,
            peak_frequency=peak_f,
            peak_amplitude=peak_a,
        )

    async def get_readings(self) -> SpectrumData:
        """REST / WebSocket readings hook: the current trace 1."""
        return await self.get_trace(1)

    # ------------------------------------------------------------------ #
    # Acquisition-engine hooks
    # ------------------------------------------------------------------ #

    async def get_measurement(self, channel: str = "PEAK") -> Dict[str, Any]:
        """Return ``{"value": float, ...}`` for a channel name.

        Accepted channels (case-insensitive):

        - ``PEAK`` (default) / ``PEAK_FREQ``: amplitude / frequency of the
          trace-1 maximum (computed from the trace, no marker moved)
        - ``MARKER<n>`` / ``MARKER<n>_FREQ``: Y / X readout of marker n
        - ``CHPOWER``: channel power (see :meth:`measure_channel_power`)
        - ``TRACE<n>:MAX`` / ``:MIN`` / ``:MEAN`` / ``:PEAK_FREQ``: trace statistics
        """
        key = (channel or "PEAK").strip().upper().replace(" ", "")
        if key in ("", "PEAK", "CH1", "1", "TRACE1:PEAK", "TRACE1"):
            data = await self.get_trace(1)
            return self._result(data.peak_amplitude, data.unit, "PEAK", frequency=data.peak_frequency)
        if key in ("PEAK_FREQ", "PEAKFREQ", "PEAK:FREQ"):
            data = await self.get_trace(1)
            return self._result(data.peak_frequency, "Hz", "PEAK_FREQ", amplitude=data.peak_amplitude)
        m = re.fullmatch(r"MARKER(\d+)(?:[_:](FREQ|X|Y|AMPL))?", key)
        if m:
            n = int(m.group(1))
            marker = await self.get_marker(n)
            if m.group(2) in ("FREQ", "X"):
                return self._result(marker["frequency"], "Hz", f"MARKER{n}_FREQ")
            return self._result(marker["amplitude"], marker.get("unit", "dBm"), f"MARKER{n}",
                                frequency=marker["frequency"])
        if key in ("CHPOWER", "CHP", "CHANNEL_POWER"):
            chp = await self.measure_channel_power()
            return self._result(chp["power"], chp.get("unit", "dBm"), "CHPOWER",
                                density=chp.get("density"), method=chp.get("method"))
        m = re.fullmatch(r"TRACE(\d+):(MAX|MIN|MEAN|AVG|PEAK_FREQ|PEAKFREQ)", key)
        if m:
            n, stat = int(m.group(1)), m.group(2)
            data = await self.get_trace(n)
            if not data.values:
                return self._result(None, data.unit, key)
            if stat == "MAX":
                value = max(data.values)
            elif stat == "MIN":
                value = min(data.values)
            elif stat in ("MEAN", "AVG"):
                value = sum(data.values) / len(data.values)
            else:
                return self._result(data.peak_frequency, "Hz", key)
            return self._result(value, data.unit, key)
        raise ValueError(
            f"Unknown measurement channel '{channel}'. Use PEAK, PEAK_FREQ, MARKER1..{self.spec.markers}, "
            "MARKER1_FREQ, CHPOWER, TRACE1:MAX, TRACE1:MIN, TRACE1:MEAN"
        )

    @staticmethod
    def _result(value: Optional[float], unit: str, channel: str, **extra: Any) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "value": float(value) if value is not None else float("nan"),
            "unit": unit,
            "channel": channel,
        }
        out.update({k: v for k, v in extra.items() if v is not None})
        return out

    async def get_measurements(self, channel: Any = 1) -> Dict[str, Any]:
        """Streaming hook: peak, min, mean and marker readouts in one dict."""
        trace = int(channel) if str(channel).isdigit() else 1
        data = await self.get_trace(trace)
        out: Dict[str, Any] = {
            "peak": data.peak_amplitude if data.peak_amplitude is not None else float("nan"),
            "peak_frequency": data.peak_frequency if data.peak_frequency is not None else float("nan"),
            "min": min(data.values) if data.values else float("nan"),
            "mean": sum(data.values) / len(data.values) if data.values else float("nan"),
            "unit": data.unit,
            "num_points": data.num_points,
        }
        return out

    # ------------------------------------------------------------------ #
    # Markers
    # ------------------------------------------------------------------ #

    def _check_marker(self, marker: int) -> int:
        marker = int(marker)
        if not 1 <= marker <= self.spec.markers:
            raise ValueError(f"Marker must be 1..{self.spec.markers}")
        return marker

    async def _marker_on(self, marker: int) -> None:
        await self._write(f":CALCulate:MARKer{marker}:STATe ON")

    async def peak_search(self, marker: int = 1, trace: Optional[int] = None) -> Dict[str, Any]:
        """Move ``marker`` to the trace maximum (:CALCulate:MARKer<n>:MAXimum:MAX)."""
        marker = self._check_marker(marker)
        await self._marker_on(marker)
        if trace is not None:
            await self._write(f":CALCulate:MARKer{marker}:TRACe {self._check_trace(trace)}")
        await self._write(f":CALCulate:MARKer{marker}:MAXimum:MAX")
        return await self.get_marker(marker)

    async def next_peak(self, marker: int = 1, direction: str = "NEXT") -> Dict[str, Any]:
        """Next / left / right peak relative to the marker's current peak."""
        marker = self._check_marker(marker)
        key = {"NEXT": "NEXT", "LEFT": "LEFT", "RIGHT": "RIGHt", "MIN": None}.get(str(direction).strip().upper(), "")
        if key == "":
            raise ValueError("direction must be NEXT, LEFT, RIGHT or MIN")
        if key is None:
            await self._write(f":CALCulate:MARKer{marker}:MINimum")
        else:
            await self._write(f":CALCulate:MARKer{marker}:MAXimum:{key}")
        return await self.get_marker(marker)

    async def set_marker(self, marker: int = 1, frequency: Optional[float] = None,
                         mode: Optional[str] = None, trace: Optional[int] = None) -> Dict[str, Any]:
        """Enable a marker and place it at ``frequency`` (Hz)."""
        marker = self._check_marker(marker)
        await self._marker_on(marker)
        if mode is not None:
            key = str(mode).strip().upper()
            valid = {m.upper(): m for m in self.MARKER_MODES}
            aliases = {"NORMAL": "POSITION", "POS": "POSITION", "DELTA": "DELTA", "DELT": "DELTA",
                       "FIX": "FIXED", "DELTAPAIR": "BAND", "SPANPAIR": "SPAN"}
            key = aliases.get(key, key)
            if key not in valid:
                raise ValueError(f"Marker mode must be one of {sorted(valid)}")
            await self._write(f":CALCulate:MARKer{marker}:MODE {valid[key]}")
        if trace is not None:
            await self._write(f":CALCulate:MARKer{marker}:TRACe {self._check_trace(trace)}")
        if frequency is not None:
            frequency = self._check_frequency(frequency, "marker frequency")
            await self._write(f":CALCulate:MARKer{marker}:X {frequency:.0f}")
        return await self.get_marker(marker)

    async def get_marker(self, marker: int = 1) -> Dict[str, Any]:
        marker = self._check_marker(marker)
        out: Dict[str, Any] = {"marker": marker}
        try:
            out["enabled"] = _is_on(await self._query(f":CALCulate:MARKer{marker}:STATe?"))
        except Exception:
            out["enabled"] = None
        out["frequency"] = parse_number(await self._query(f":CALCulate:MARKer{marker}:X?"))
        out["amplitude"] = parse_number(await self._query(f":CALCulate:MARKer{marker}:Y?"))
        try:
            out["mode"] = (await self._query(f":CALCulate:MARKer{marker}:MODE?")).strip().upper()
        except Exception:
            out["mode"] = None
        try:
            out["unit"] = await self.get_unit()
        except Exception:
            out["unit"] = "dBm"
        return out

    async def marker_off(self, marker: int = 1) -> None:
        marker = self._check_marker(marker)
        await self._write(f":CALCulate:MARKer{marker}:STATe OFF")

    async def all_markers_off(self) -> None:
        await self._write(":CALCulate:MARKer:AOFF")

    async def marker_to_center(self, marker: int = 1, peak: bool = False) -> Dict[str, float]:
        """Marker -> CF (:CALCulate:MARKer<n>:SET:CENTer); ``peak=True`` first
        does a peak search (DSA ``:PEAK:SET:CF`` semantics)."""
        marker = self._check_marker(marker)
        if peak:
            await self.peak_search(marker)
        await self._write(f":CALCulate:MARKer{marker}:SET:CENTer")
        return await self.get_frequency()

    async def set_peak_search_mode(self, mode: str = "MAXIMUM", marker: int = 1) -> str:
        """PARameter (excursion/threshold search) or MAXimum."""
        key = {"MAX": "MAXimum", "MAXIMUM": "MAXimum", "PAR": "PARameter", "PARAMETER": "PARameter"}.get(
            str(mode).strip().upper()
        )
        if key is None:
            raise ValueError("Peak search mode must be MAXIMUM or PARAMETER")
        cmd = self.PEAK_SEARCH_MODE_CMD.format(n=self._check_marker(marker))
        await self._write(f"{cmd} {key}")
        return (await self._query(f"{cmd}?")).strip().upper()

    # ------------------------------------------------------------------ #
    # Tracking generator
    # ------------------------------------------------------------------ #

    def _require_tg(self) -> None:
        if not self.has_tracking_generator:
            raise ValueError(
                f"{self.spec.model} has no tracking generator (use set_tracking_generator_fitted(True) "
                "if the -TG option is installed)"
            )

    async def set_tracking_generator(self, enabled: bool, level: Optional[float] = None) -> Dict[str, Any]:
        """Tracking generator output on/off and level in dBm (when fitted)."""
        self._require_tg()
        if level is not None:
            level = float(level)
            if not self.spec.tg_level_min <= level <= self.spec.tg_level_max:
                raise ValueError(
                    f"TG level must be {self.spec.tg_level_min:g}..{self.spec.tg_level_max:g} dBm"
                )
            await self._write(f"{self.TG_LEVEL_CMD} {level:g}")
        await self._write(f"{self.TG_OUTPUT_CMD} {_to_bool_word(enabled)}")
        return await self.get_tracking_generator()

    async def get_tracking_generator(self) -> Dict[str, Any]:
        self._require_tg()
        return {
            "enabled": _is_on(await self._query(f"{self.TG_OUTPUT_CMD}?")),
            "level": parse_number(await self._query(f"{self.TG_LEVEL_CMD}?")),
            "unit": "dBm",
        }

    async def set_output(self, enabled: bool, channel: int = 1) -> Optional[Dict[str, Any]]:
        """Safe-state hook: the manager calls ``set_output(False)`` on disconnect.

        Only touches the instrument when a tracking generator is fitted.
        """
        if not self.has_tracking_generator:
            return None
        return await self.set_tracking_generator(enabled)

    # ------------------------------------------------------------------ #
    # Built-in measurements
    # ------------------------------------------------------------------ #

    async def measure_channel_power(self, bandwidth: Optional[float] = None,
                                    span: Optional[float] = None) -> Dict[str, Any]:
        """Channel power (and density) around the center frequency.

        DSA: ``:CONFigure:CHPower`` + ``:READ:CHPower?`` -> ``power,density``.
        RSA800/6000: ``:INSTrument:SELect GPSA_CHPower`` + ``:FETCh:CHPower1?``.
        RSA3000/5000 (no CHPower command set): integrate trace 1 over
        ``bandwidth`` (default: the span) with an RBW noise-bandwidth
        correction; ``method`` says which path was used.
        """
        if self.CHPOWER_METHOD == "DSA":
            await self._write(":CONFigure:CHPower")
            if bandwidth is not None:
                await self._write(f":SENSe:CHPower:BANDwidth:INTegration {float(bandwidth):.0f}")
            if span is not None:
                await self._write(f":SENSe:CHPower:FREQuency:SPAN {float(span):.0f}")
            raw = await self._query(":READ:CHPower?")
            parts = [parse_number(p) for p in raw.split(",")]
            unit = await self.get_unit()
            return {"power": parts[0] if parts else None,
                    "density": parts[1] if len(parts) > 1 else None,
                    "unit": unit, "density_unit": f"{unit}/Hz", "method": "instrument"}
        if self.CHPOWER_METHOD == "RSA_MODE":
            await self.set_mode("GPSA_CHPOWER")
            if bandwidth is not None:
                await self._write(f":SENSe:CHPower:BANDwidth:INTegration {float(bandwidth):.0f}")
            power = parse_number(await self._query(":FETCh:CHPower1?"))
            try:
                density = parse_number(await self._query(":FETCh:CHPower:DENSity1?"))
            except Exception:
                density = None
            unit = await self.get_unit()
            return {"power": power, "density": density, "unit": unit,
                    "density_unit": f"{unit}/Hz", "method": "instrument"}
        return await self._channel_power_from_trace(bandwidth)

    async def _channel_power_from_trace(self, bandwidth: Optional[float]) -> Dict[str, Any]:
        data = await self.get_trace(1)
        if not data.values or data.center_frequency is None or not data.rbw:
            return {"power": None, "density": None, "unit": data.unit, "method": "trace_integration"}
        bw = float(bandwidth) if bandwidth else (data.stop_frequency - data.start_frequency)
        lo, hi = data.center_frequency - bw / 2, data.center_frequency + bw / 2
        freqs = compute_frequencies(data.start_frequency, data.stop_frequency, data.num_points)
        bin_hz = (data.stop_frequency - data.start_frequency) / max(data.num_points - 1, 1)
        if data.unit.lower() not in ("dbm",):
            logger.warning("Trace-integrated channel power assumes dBm units")
        total_mw = 0.0
        for f, v in zip(freqs, data.values):
            if lo <= f <= hi:
                total_mw += 10 ** (v / 10.0)
        if total_mw <= 0 or bin_hz <= 0:
            return {"power": None, "density": None, "unit": data.unit, "method": "trace_integration"}
        # Each bin already reflects power in one RBW; scale by bin/RBW ratio.
        power = 10 * math.log10(total_mw * bin_hz / data.rbw)
        density = power - 10 * math.log10(bw) if bw > 0 else None
        return {"power": power, "density": density, "unit": "dBm", "density_unit": "dBm/Hz",
                "bandwidth": bw, "method": "trace_integration"}

    async def measure_obw(self, percent: Optional[float] = None) -> Dict[str, Any]:
        """Occupied bandwidth (:CONFigure:OBWidth + :READ:OBWidth?)."""
        if self.CHPOWER_METHOD == "RSA_MODE":
            await self.set_mode("GPSA_OBW")
        else:
            await self._write(":CONFigure:OBWidth")
        if percent is not None:
            percent = float(percent)
            if not 1.0 <= percent <= 99.99:
                raise ValueError("OBW percent must be 1..99.99")
            await self._write(f":SENSe:OBWidth:PERCent {percent:g}")
        if self.CHPOWER_METHOD == "RSA_MODE":
            raw = await self._query(":FETCh:OBWidth?")
        else:
            raw = await self._query(":READ:OBWidth?")
        parts = [parse_number(p) for p in raw.split(",")]
        return {"obw": parts[0] if parts else None,
                "transmit_frequency_error": parts[1] if len(parts) > 1 else None,
                "unit": "Hz"}

    # ------------------------------------------------------------------ #
    # RSA working mode
    # ------------------------------------------------------------------ #

    async def set_mode(self, mode: str = "GPSA") -> str:
        """Select GPSA (swept) / RTSA (real-time) etc. via :INSTrument:SELect."""
        if not self.HAS_MODE_SELECT:
            raise ValueError(f"{self.spec.model} has a single (swept) mode")
        key = str(mode).strip().upper().replace("-", "_")
        keyword = self.MODE_KEYWORDS.get(key)
        if keyword is None:
            raise ValueError(f"Mode must be one of {sorted(set(self.MODE_KEYWORDS))}")
        if self._mode == keyword.upper():
            return self._mode
        old_timeout = self.instrument.timeout if self.instrument is not None else None
        if self.instrument is not None:
            self.instrument.timeout = max(int(self.MODE_SWITCH_DELAY_S * 1000) + 2000, old_timeout or 0)
        try:
            await self._write(f":INSTrument:SELect {keyword}")
            # The guides recommend waiting ~8 s after a mode switch; *OPC?
            # returns once the switch is done on current firmware.
            try:
                await self._query("*OPC?")
            except Exception:
                await asyncio.sleep(self.MODE_SWITCH_DELAY_S)
        finally:
            if self.instrument is not None and old_timeout is not None:
                self.instrument.timeout = old_timeout
        return await self.get_mode()

    async def get_mode(self) -> Optional[str]:
        if not self.HAS_MODE_SELECT:
            return "GPSA"
        raw = (await self._query(":INSTrument:SELect?")).strip().upper()
        self._mode = {"1": "SA", "2": "RTSA", "3": "VSA", "4": "EMI"}.get(raw, raw)
        return self._mode

    # ------------------------------------------------------------------ #
    # Screenshot
    # ------------------------------------------------------------------ #

    async def get_screenshot(self) -> bytes:
        """Screen image bytes where the guide documents a data query."""
        if not (self.SCREENSHOT_CMD and self.spec.screenshot):
            raise ValueError(
                f"{self.spec.model} has no screenshot query (only :MMEMory:STORe:SCReen to a file on the instrument)"
            )
        return await self._query_block(self.SCREENSHOT_CMD)

    # ------------------------------------------------------------------ #
    # State
    # ------------------------------------------------------------------ #

    async def get_state(self) -> Dict[str, Any]:
        """Snapshot of settings for the state capture/restore system."""
        state: Dict[str, Any] = {}
        for key, coro in (
            ("frequency", self.get_frequency()),
            ("bandwidth", self.get_bandwidth()),
            ("amplitude", self.get_amplitude()),
            ("sweep", self.get_sweep()),
            ("detector", self.get_detector(1)),
            ("trace1_mode", self.get_trace_mode(1)),
        ):
            try:
                state[key] = await coro
            except Exception as e:
                logger.debug(f"State item {key} failed: {e}")
                state[key] = None
        if self.HAS_MODE_SELECT:
            try:
                state["mode"] = await self.get_mode()
            except Exception:
                state["mode"] = None
        if self.has_tracking_generator:
            try:
                state["tracking_generator"] = await self.get_tracking_generator()
            except Exception:
                state["tracking_generator"] = None
        state["data_format"] = self._data_format
        return state

    async def get_range(self) -> Dict[str, Any]:
        """Alias used by the generic state-capture code."""
        return await self.get_frequency()


# --------------------------------------------------------------------------- #
# Concrete families
# --------------------------------------------------------------------------- #


class RigolDSA800(RigolSABase):
    """DSA815/832/875 (+TG), DSA832E (+TG), DSA705/710.

    Differences handled through :data:`MODEL_TABLE`: DSA700 has no TG, no
    ``:SENSe:SWEep:POINts`` (fixed 601 points) and RBW >= 100 Hz; DSA800E has
    the TG but no power-sweep commands (not used here).
    """

    FAMILY = "DSA800"
    DEFAULT_MODEL = "DSA815"
    INTERFACES = ("USB", "LAN", "GPIB")  # GPIB via USB-GPIB adapter


class RigolDSA1000(RigolSABase):
    """DSA1030 / DSA1030A legacy tree.

    The DSA1000 guide documents ``[:SENSe]:BANDwidth:RESolution`` (RESolution
    mandatory) and abbreviates ``[:SENSe]`` in its examples
    (``:FREQ:CENT``); the driver always sends the full ``:SENSe:...`` forms,
    which both firmwares accept.  Attenuation goes to 50 dB, reference level
    to +30 dBm, TG level -20..0 dBm, RBW >= 100 Hz (10 Hz on DSA1030A).
    """

    FAMILY = "DSA1000"
    DEFAULT_MODEL = "DSA1030"
    INTERFACES = ("USB", "LAN", "GPIB")
    # DSA1000 has :INPut:IMPedance 50|75 (not on DSA800).
    SWEEP_TIME_MIN = 20e-6
    SWEEP_TIME_MAX = 3000.0

    async def set_input_impedance(self, ohms: int = 50) -> int:
        ohms = int(ohms)
        if ohms not in (50, 75):
            raise ValueError("Input impedance must be 50 or 75 Ohm")
        await self._write(f":INPut:IMPedance {ohms}")
        return int(float((await self._query(":INPut:IMPedance?")).strip()))

    async def execute_command(self, command: str, parameters: dict) -> Any:
        if command == "set_input_impedance":
            return await self.set_input_impedance(**dict(parameters or {}))
        return await super().execute_command(command, parameters)


class _RigolRSABase(RigolSABase):
    """Shared RSA (real-time) constants: GPSA/RTSA mode select, 8 markers,
    6 traces, ``:TRACe<n>:TYPE`` vocabulary, EXTernal TG tree."""

    INTERFACES = ("USB", "LAN")
    TRACE_MODE_KEYWORDS = {"WRITE": "WRITe", "AVERAGE": "AVERage", "MAXHOLD": "MAXHold", "MINHOLD": "MINHold"}
    TRACE_VIEW_VIA_UPDATE = True
    PEAK_SEARCH_MODE_CMD = ":CALCulate:MARKer:PEAK:SEARch:MODE"
    AVERAGE_COUNT_CMD = ":SENSe:AVERage:COUNt"
    AVERAGE_RESET_CMD = ":SENSe:AVERage:CLEar"
    DETECTOR_KEYWORDS = ("POSitive", "NEGative", "NORMal", "SAMPle", "RMS", "VAVerage", "QPEak")
    TG_OUTPUT_CMD = ":OUTPut:EXTernal:STATe"
    TG_LEVEL_CMD = ":SOURce:EXTernal:POWer:LEVel:IMMediate:AMPLitude"
    ZERO_SPAN_CMD = ":SENSe:FREQuency:SPAN:ZERO"
    MARKER_MODES = ("POSition", "DELTa", "FIXed", "OFF")
    HAS_MODE_SELECT = True
    MODE_KEYWORDS = {"GPSA": "SA", "SA": "SA", "SWEPT": "SA", "RTSA": "RTSA", "REALTIME": "RTSA", "REAL_TIME": "RTSA"}
    SWEEP_TIME_MIN = 1e-6
    SWEEP_TIME_MAX = 6000.0


class RigolRSA3000(_RigolRSABase):
    """RSA3015E/3030E (+TG), RSA3015N/3030/3045 (+TG/N).

    RSA3000 guide: ``:INSTrument:SELect SA|RTSA``; RSA3000E adds ``VSA|EMI``.
    No ``CHPower`` command set (only ``:CONFigure:MCHPower`` without a FETCh),
    so channel power is integrated from the trace.  Binary trace formats
    REAL,32 / REAL,64 / INTeger,32; ``:STATus:OPERation:CONDition?`` present.
    """

    FAMILY = "RSA3000"
    DEFAULT_MODEL = "RSA3030"
    TRACE_MODE_CMD = ":TRACe{n}:MODE"  # guide lists MODE and TYPE as synonyms
    CHPOWER_METHOD = None
    BINARY_FORMATS = ("REAL,32", "REAL,64", "INTEGER,32")
    MODE_KEYWORDS = {**_RigolRSABase.MODE_KEYWORDS, "VSA": "VSA", "EMI": "EMI"}


class RigolRSA5000(_RigolRSABase):
    """RSA5032 / RSA5065 (+TG, N). Same tree as RSA3000 (RSA5000 guide)."""

    FAMILY = "RSA5000"
    DEFAULT_MODEL = "RSA5065"
    TRACE_MODE_CMD = ":TRACe{n}:MODE"
    CHPOWER_METHOD = None
    BINARY_FORMATS = ("REAL,32", "REAL,64", "INTEGER,32")


class RigolRSA800(_RigolRSABase):
    """RSA804 / RSA808 / RSA814 (RSA800 guide, 2023 firmware tree).

    Trace type only via ``:TRACe<n>:TYPE``; detector is per trace
    (``[:SENSe]:DETector:TRACe<n>``); no ``:FORMat`` command (ASCII traces
    only); no ``:STATus:OPERation`` register (``*OPC?`` only); measurements
    are working modes (``:INSTrument:SELect GPSA_CHPower`` ...);
    ``:MMEMory:STORe:SCReen:DATA?`` returns the screen image.  TG built in.
    """

    FAMILY = "RSA800"
    DEFAULT_MODEL = "RSA814"
    TRACE_MODE_CMD = ":TRACe{n}:TYPE"
    DETECTOR_PER_TRACE = True
    HAS_OPERATION_CONDITION = False
    CHPOWER_METHOD = "RSA_MODE"
    BINARY_FORMATS = ()
    SCREENSHOT_CMD = ":MMEMory:STORe:SCReen:DATA?"
    MODE_KEYWORDS = {
        **_RigolRSABase.MODE_KEYWORDS,
        "GPSA_TG": "GPSA_TG", "TG": "GPSA_TG", "RTSA_UFS": "RTSA_UFS",
        "GPSA_ACP": "GPSA_ACP", "GPSA_CNR": "GPSA_CNR", "GPSA_CHPOWER": "GPSA_CHPower",
        "GPSA_CHP": "GPSA_CHPower", "GPSA_TOI": "GPSA_TOI", "GPSA_HARMODIST": "GPSA_HARModist",
        "GPSA_OBW": "GPSA_OBW", "GPSA_TPOWER": "GPSA_TPOWer", "EMI": "EMI", "VSA": "VSA",
        "AM": "AM", "FM": "FM", "PM": "PM", "PNOISE": "PNOISE",
    }


class RigolRSA6000(RigolRSA800):
    """RSA6085 / RSA6140 / RSA6265: same 2023 tree as RSA800 (RSA6000 guide).

    TG only on the RSA6000-TG variant (``has_tracking_generator`` follows the
    model string / override).  No VSA/PNOISE modes in the guide (VMA instead).
    """

    FAMILY = "RSA6000"
    DEFAULT_MODEL = "RSA6140"
    MODE_KEYWORDS = {k: v for k, v in RigolRSA800.MODE_KEYWORDS.items() if k not in ("VSA", "PNOISE")}
    MODE_KEYWORDS["VMA"] = "VMA"


# Model keywords used by equipment.manager.find_keyword_driver (the manager orders
# the most specific classes first).
RigolRSA6000.MODEL_KEYWORDS = ('RSA6265', 'RSA6140', 'RSA6085', 'RSA6000')
RigolRSA800.MODEL_KEYWORDS = ('RSA814', 'RSA808', 'RSA804', 'RSA800')
RigolRSA5000.MODEL_KEYWORDS = ('RSA5065', 'RSA5032', 'RSA5000')
RigolRSA3000.MODEL_KEYWORDS = ('RSA3045', 'RSA3030E', 'RSA3030', 'RSA3015E', 'RSA3015', 'RSA3000E', 'RSA3000')
RigolDSA1000.MODEL_KEYWORDS = ('DSA1030A', 'DSA1030', 'DSA1000')
RigolDSA800.MODEL_KEYWORDS = ('DSA875', 'DSA832E', 'DSA832', 'DSA815', 'DSA710', 'DSA705', 'DSA800E', 'DSA800', 'DSA700')
