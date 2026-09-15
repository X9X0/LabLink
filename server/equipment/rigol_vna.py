"""Rigol vector network analyzer drivers.

Two very different SCPI trees are covered by one public API:

* ``RigolRSAN`` -- the VNA *mode* of the RSA3000N / RSA5000N spectrum analyzer
  combos (RSA3015N, RSA3030N, RSA3045N, RSA5032N, RSA5065N).  Protocol
  reference: RIGOL "VNA Programming Guide, applicable to RSA5000N/RSA3000N"
  (Jul. 2020, PGD24100-1110).  The tree is un-indexed (``:SENSe:FREQuency:...``),
  the measured parameter is selected per *function* with ``:CONFigure S11|S21``,
  the format per trace with ``:DISPlay:TRACe<n>:FORMat``, trace data is always
  complex (``:TRACe<n>:DATA?`` -> ``(re,im)(re,im)...``) and calibration uses
  ``:CALibration:S11:OPEN|SHORt|LOAD|SAVE`` / ``:CALibration:S21:THROugh|SAVE``.
  The mode must be selected with ``:INSTrument:SELect VNA`` first.

* ``RigolDNA6000`` -- the DNA6000 and DNA6000-R bench VNAs (DNA6082/6084,
  6142/6144, 6202/6204, 6262/6264 and their ``-R`` variants).  Protocol
  reference: RIGOL "DNA6000 Programming Guide" and "DNA6000-R Series
  Programming Guide" (2026).  Channel-indexed tree (``:SENSe<cn>``,
  ``:SOURce<cn>``, ``:CALCulate<cn>:MEASure<mn>:...``), formatted data via
  ``:CALCulate<cn>:MEASure<mn>:DATA:FDATA?``, complex via ``:SDATA?``, stimulus
  via ``:DATA:X?`` / ``:SENSe<cn>:FREQuency:DATA?``, calibration via
  ``:SENSe<cn>:CORRection:COLLect:METHod / [:ACQuire] / :SAVE``.

Both return ``Rigol Technologies,<model>,<serial>,<firmware>`` (RSA-N) or
``RIGOL TECHNOLOGIES,<model>,<serial>,<firmware>`` (DNA6000) for ``*IDN?``.
"""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from shared.models.data import NetworkAnalyzerData
from shared.models.equipment import EquipmentInfo, EquipmentStatus, EquipmentType

from .base import BaseEquipment, generate_equipment_id

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Model tables
# --------------------------------------------------------------------------- #

# RSA-N: frequency limits from the VNA Programming Guide, [:SENSe]:FREQuency:
# STARt (min 100 kHz) / :STOP (Fmax per model, remark on p.2-59); points from
# [:SENSe]:SWEep:POINts (101..10001); power from :SOURce:POWer (-40..0 dBm);
# IF BW from [:SENSe]:BANDwidth (1 kHz..10 MHz, 1-3-10 steps); markers 1..8
# (:CALCulate:MARKer<n>); traces 1..4 (:DISPlay:TRACe<n>:FORMat).  The VNA
# option measures reflection (S11) on port 1 and transmission (S21) with the
# tracking generator, so only S11 and S21 exist.
_RSAN_COMMON = {
    "family": "RSA-N",
    "freq_min": 100e3,
    "min_points": 101,
    "max_points": 10001,
    "ports": 2,
    "parameters": ["S11", "S21"],
    "power_min": -40.0,
    "power_max": 0.0,
    "ifbw_min": 1e3,
    "ifbw_max": 10e6,
    "max_markers": 8,
    "max_traces": 4,
}

# DNA6000: model/frequency/port table from the DNA6000 Programming Guide
# "Content Conventions" (p.1-2) and the DNA6000-R guide (same table with -R);
# points from :SENSe<cn>:SWEep:POINts (1..100001); power from
# :SOURce<cn>:POWer (-40..+10 dBm); IF BW from :SENSe<cn>:BANDwidth
# (1 Hz..10 MHz); markers 1..16 (:CALCulate<cn>:MARKer<mk>).
_DNA_COMMON = {
    "family": "DNA6000",
    "freq_min": 5e3,
    "min_points": 1,
    "max_points": 100001,
    "power_min": -40.0,
    "power_max": 10.0,
    "ifbw_min": 1.0,
    "ifbw_max": 10e6,
    "max_markers": 16,
    "max_traces": 16,
}


def _dna(freq_max: float, ports: int) -> Dict[str, Any]:
    spec = dict(_DNA_COMMON)
    spec["freq_max"] = freq_max
    spec["ports"] = ports
    spec["parameters"] = [f"S{i}{j}" for i in range(1, ports + 1) for j in range(1, ports + 1)]
    return spec


MODEL_TABLE: Dict[str, Dict[str, Any]] = {
    "RSA3015N": dict(_RSAN_COMMON, freq_max=1.5e9),
    "RSA3030N": dict(_RSAN_COMMON, freq_max=3.0e9),
    "RSA3045N": dict(_RSAN_COMMON, freq_max=4.5e9),
    "RSA5032N": dict(_RSAN_COMMON, freq_max=3.2e9),
    "RSA5065N": dict(_RSAN_COMMON, freq_max=6.5e9),
    "DNA6082": _dna(8.5e9, 2),
    "DNA6084": _dna(8.5e9, 4),
    "DNA6142": _dna(14e9, 2),
    "DNA6144": _dna(14e9, 4),
    "DNA6202": _dna(20e9, 2),
    "DNA6204": _dna(20e9, 4),
    "DNA6262": _dna(26.5e9, 2),
    "DNA6264": _dna(26.5e9, 4),
}
# -R (rack) variants share the base model's limits.
for _base in list(MODEL_TABLE):
    if _base.startswith("DNA"):
        MODEL_TABLE[f"{_base}-R"] = dict(MODEL_TABLE[_base], rack=True)


# Canonical format -> (SCPI long form, unit, two values per point?)
FORMATS: Dict[str, Tuple[str, str, bool]] = {
    "MLOG": ("MLOGarithmic", "dB", False),
    "MLIN": ("MLINear", "U", False),
    "PHAS": ("PHASe", "deg", False),
    "UPH": ("UPHase", "deg", False),
    "PPH": ("PPHase", "deg", False),
    "SWR": ("SWR", "", False),
    "REAL": ("REAL", "U", False),
    "IMAG": ("IMAGinary", "U", False),
    "GDEL": ("GDELay", "s", False),
    "SMIT": ("SMITh", "U", True),
    "SADM": ("SADMittance", "U", True),
    "POL": ("POLar", "U", True),
    # RSA-N only
    "SLIN": ("SLINear", "U", False),
    "SLOG": ("SLOGarithmic", "dB", False),
    "SCOM": ("SCOMplex", "U", True),
    "PLIN": ("PLINear", "U", False),
    "PLOG": ("PLOGarithmic", "dB", False),
}

_FORMAT_ALIASES: Dict[str, str] = {
    "MLOGARITHMIC": "MLOG", "LOGMAG": "MLOG", "LOG": "MLOG", "DB": "MLOG", "MAG": "MLOG",
    "MLINEAR": "MLIN", "LINMAG": "MLIN", "LIN": "MLIN",
    "PHASE": "PHAS",
    "UPHASE": "UPH", "UNWRAPPED": "UPH",
    "PPHASE": "PPH",
    "VSWR": "SWR",
    "IMAGINARY": "IMAG",
    "GDELAY": "GDEL", "GROUP_DELAY": "GDEL", "DELAY": "GDEL",
    "SMITH": "SMIT",
    "SADMITTANCE": "SADM", "ISMITH": "SADM",
    "POLAR": "POL",
    "SLINEAR": "SLIN", "SLOGARITHMIC": "SLOG", "SCOMPLEX": "SCOM",
    "PLINEAR": "PLIN", "PLOGARITHMIC": "PLOG",
}

_SPARAM_RE = re.compile(r"^S(\d)(\d)$")
_NUMBER_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

_CAL_STANDARDS = {
    "OPEN": "OPEN", "SHORT": "SHORt", "SHOR": "SHORt", "LOAD": "LOAD",
    "THRU": "THRU", "THROUGH": "THRU", "THRO": "THRU",
}


def normalize_format(fmt: str) -> str:
    key = str(fmt).strip().upper()
    key = _FORMAT_ALIASES.get(key, key)
    if key not in FORMATS:
        raise ValueError(f"Unknown trace format '{fmt}'. Valid: {', '.join(FORMATS)}")
    return key


def normalize_sparam(param: str) -> str:
    key = str(param).strip().upper().replace("_", "")
    if not _SPARAM_RE.match(key):
        raise ValueError(f"Invalid S-parameter '{param}' (expected S11, S21, S12, S22, ...)")
    return key


def parse_float_list(raw: str) -> List[float]:
    """Parse a comma separated (or ``(re,im)(re,im)``) ASCII list into floats."""
    text = raw.strip()
    if text.startswith("#"):
        # Definite-length block header "#<n><len>" -- strip it (FORM:DATA ASCII
        # should never produce it, but be tolerant).
        try:
            ndig = int(text[1])
            text = text[2 + ndig:]
        except (ValueError, IndexError):
            pass
    return [float(m) for m in _NUMBER_RE.findall(text)]


def parse_complex_list(raw: str) -> List[complex]:
    """Parse interleaved real/imag pairs into complex numbers."""
    flat = parse_float_list(raw)
    if len(flat) % 2:
        flat = flat[:-1]
    return [complex(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]


def format_complex(
    values: Sequence[complex], fmt: str, frequencies: Optional[Sequence[float]] = None
) -> Tuple[List[float], List[float]]:
    """Convert complex S-parameter data to a display format (primary, secondary)."""
    z = np.asarray(values, dtype=complex)
    if z.size == 0:
        return [], []
    mag = np.abs(z)
    if fmt in ("MLOG", "SLOG", "PLOG"):
        with np.errstate(divide="ignore"):
            out = 20.0 * np.log10(np.where(mag > 0, mag, 1e-30))
        return out.tolist(), []
    if fmt in ("MLIN", "SLIN", "PLIN"):
        return mag.tolist(), []
    if fmt == "PHAS":
        return np.degrees(np.angle(z)).tolist(), []
    if fmt == "UPH":
        return np.degrees(np.unwrap(np.angle(z))).tolist(), []
    if fmt == "PPH":
        return (np.degrees(np.angle(z)) % 360.0).tolist(), []
    if fmt == "SWR":
        with np.errstate(divide="ignore", invalid="ignore"):
            swr = (1.0 + mag) / (1.0 - mag)
        swr = np.where((mag >= 1.0) | ~np.isfinite(swr), 1e6, swr)
        return swr.tolist(), []
    if fmt == "REAL":
        return z.real.tolist(), []
    if fmt == "IMAG":
        return z.imag.tolist(), []
    if fmt == "GDEL":
        phase = np.unwrap(np.angle(z))
        if frequencies is None or len(frequencies) != z.size or z.size < 2:
            return [0.0] * z.size, []
        omega = 2.0 * np.pi * np.asarray(frequencies, dtype=float)
        return (-np.gradient(phase, omega)).tolist(), []
    if fmt == "SADM":
        with np.errstate(divide="ignore", invalid="ignore"):
            y = (1.0 - z) / (1.0 + z)
        y = np.where(np.isfinite(y), y, 0.0)
        return y.real.tolist(), y.imag.tolist()
    # SMIT / POL / SCOM: raw complex
    return z.real.tolist(), z.imag.tolist()


def _bool_word(enabled: bool) -> str:
    return "ON" if enabled else "OFF"


# --------------------------------------------------------------------------- #
# Base driver
# --------------------------------------------------------------------------- #


class RigolVNABase(BaseEquipment):
    """Common API for Rigol VNAs; subclasses supply the SCPI dialect."""

    MODEL = "VNA"
    DEFAULT_SPEC: Dict[str, Any] = dict(_DNA_COMMON, freq_max=8.5e9, ports=2,
                                        parameters=["S11", "S12", "S21", "S22"])
    INTERFACES: Sequence[str] = ("USB", "LAN")
    FORMATS_BY_PARAM: Optional[Dict[str, Sequence[str]]] = None  # None -> FORMATS
    HAS_CORRECTION_STATE = True
    HAS_RF_OUTPUT = False
    SWEEP_TIMEOUT_MS = 120000
    CALIBRATION_METHODS: Sequence[str] = ()

    def __init__(self, resource_manager, resource_string: str):
        super().__init__(resource_manager, resource_string)
        self.manufacturer = "Rigol"
        self.model = self.MODEL
        self.serial_number: Optional[str] = None
        self.firmware_version: Optional[str] = None
        self._trace_params: Dict[int, str] = {}
        self._trace_formats: Dict[int, str] = {}
        self._marker_trace: Dict[int, int] = {}
        self._cal_method: Optional[str] = None
        self._cal_param: Optional[str] = None
        self._io_lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Identity
    # ------------------------------------------------------------------ #

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
        return info

    def spec(self) -> Dict[str, Any]:
        """Per-model limits (frequency, points, ports, power) from MODEL_TABLE."""
        key = (self.model or "").strip().upper()
        if key in MODEL_TABLE:
            return MODEL_TABLE[key]
        for name, entry in MODEL_TABLE.items():
            if key.startswith(name):
                return entry
        return self.DEFAULT_SPEC

    async def connect(self):
        await super().connect()
        try:
            await self._post_connect()
        except Exception as e:  # pragma: no cover - defensive
            logger.debug(f"VNA post-connect setup failed: {e}")

    async def _post_connect(self):
        """Hook for dialect specific setup after *IDN? (mode switch, data format)."""

    async def get_info(self) -> EquipmentInfo:
        idn = await self._query("*IDN?")
        info = self._parse_idn(idn)
        return EquipmentInfo(
            id=generate_equipment_id(self.resource_string, "vna_"),
            type=EquipmentType.VECTOR_NETWORK_ANALYZER,
            manufacturer=info["manufacturer"] or self.manufacturer,
            model=info["model"] or self.model,
            serial_number=info["serial"],
            connection_type=self._determine_connection_type(),
            resource_string=self.resource_string,
        )

    def _capabilities(self) -> Dict[str, Any]:
        spec = self.spec()
        formats = list(FORMATS) if self.FORMATS_BY_PARAM is None else sorted(
            {f for fl in self.FORMATS_BY_PARAM.values() for f in fl}
        )
        return {
            "family": spec["family"],
            "frequency_min": spec["freq_min"],
            "frequency_max": spec["freq_max"],
            "min_points": spec["min_points"],
            "max_points": spec["max_points"],
            "ports": spec["ports"],
            "parameters": list(spec["parameters"]),
            "power_min_dbm": spec["power_min"],
            "power_max_dbm": spec["power_max"],
            "ifbw_min": spec["ifbw_min"],
            "ifbw_max": spec["ifbw_max"],
            "max_markers": spec["max_markers"],
            "max_traces": spec["max_traces"],
            "formats": formats,
            "calibration_methods": list(self.CALIBRATION_METHODS),
            "calibration_standards": ["OPEN", "SHORT", "LOAD", "THRU"],
            "has_correction_state": self.HAS_CORRECTION_STATE,
            "has_rf_output_control": self.HAS_RF_OUTPUT,
            "interfaces": list(self.INTERFACES),
            "supports_acquisition": True,
        }

    async def get_status(self) -> EquipmentStatus:
        try:
            idn = await self._query("*IDN?")
            info = self._parse_idn(idn)
            capabilities = self._capabilities()
            try:
                capabilities["sweep"] = await self.get_sweep()
            except Exception as e:
                logger.debug(f"Sweep query failed: {e}")
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
            # sweep
            "set_sweep": self.set_sweep,
            "get_sweep": self.get_sweep,
            "set_start_stop": self.set_start_stop,
            "set_center_span": self.set_center_span,
            "set_points": self.set_points,
            "set_power": self.set_power,
            "set_if_bandwidth": self.set_if_bandwidth,
            "set_continuous": self.set_continuous,
            "sweep_single": self.sweep_single,
            "trigger": self.sweep_single,
            # traces
            "set_parameter": self.set_parameter,
            "get_parameter": self.get_parameter,
            "set_format": self.set_format,
            "get_format": self.get_format,
            "list_traces": self.list_traces,
            "get_trace": self.get_trace,
            "get_complex_trace": self.get_complex_trace,
            # markers
            "set_marker": self.set_marker,
            "get_marker": self.get_marker,
            "marker_search": self.marker_search,
            # calibration
            "calibrate_start": self.calibrate_start,
            "calibrate_acquire": self.calibrate_acquire,
            "calibrate_save": self.calibrate_save,
            "calibrate_abort": self.calibrate_abort,
            "set_correction": self.set_correction,
            "get_correction": self.get_correction,
            # hooks
            "get_readings": self.get_readings,
            "get_measurement": self.get_measurement,
            "get_measurements": self.get_measurements,
            "get_state": self.get_state,
            "set_mode": self.set_mode,
            "reset": self.reset,
            "get_error": self.get_error,
            "clear_errors": self.clear_errors,
        }
        if self.HAS_RF_OUTPUT:
            handlers["set_rf_output"] = self.set_rf_output
            handlers["get_rf_output"] = self.get_rf_output
        handler = handlers.get(command)
        if handler is None:
            raise ValueError(f"Unknown command: {command}")
        return await handler(**parameters)

    # ------------------------------------------------------------------ #
    # Dialect hooks (override in subclasses)
    # ------------------------------------------------------------------ #

    def _freq_cmd(self, key: str, channel: int) -> str:
        raise NotImplementedError

    def _points_cmd(self, channel: int) -> str:
        raise NotImplementedError

    def _power_cmd(self, channel: int) -> str:
        raise NotImplementedError

    def _ifbw_cmd(self, channel: int) -> str:
        raise NotImplementedError

    async def _write_parameter(self, trace: int, sparam: str, channel: int) -> None:
        raise NotImplementedError

    async def _read_parameter(self, trace: int, channel: int) -> str:
        raise NotImplementedError

    async def _write_format(self, trace: int, fmt: str, channel: int) -> None:
        raise NotImplementedError

    async def _read_format(self, trace: int, channel: int) -> str:
        raise NotImplementedError

    async def _read_stimulus(self, trace: int, channel: int, points: int,
                             start: float, stop: float) -> List[float]:
        return np.linspace(start, stop, points).tolist() if points > 0 else []

    async def _read_complex(self, trace: int, channel: int) -> List[complex]:
        raise NotImplementedError

    async def _read_formatted(self, trace: int, channel: int, fmt: str,
                              freqs: List[float]) -> Tuple[List[float], List[float]]:
        """Default: derive the formatted data from the complex data."""
        return format_complex(await self._read_complex(trace, channel), fmt, freqs)

    async def _single_sweep_cmd(self, channel: int) -> None:
        raise NotImplementedError

    def _continuous_cmd(self, channel: int) -> str:
        return ":INITiate:CONTinuous"

    async def _marker_enable(self, marker: int, trace: int, channel: int) -> None:
        raise NotImplementedError

    def _marker_x_cmd(self, marker: int, trace: int, channel: int) -> str:
        raise NotImplementedError

    def _marker_y_cmd(self, marker: int, trace: int, channel: int) -> str:
        raise NotImplementedError

    async def _marker_search_cmd(self, marker: int, kind: str, trace: int, channel: int) -> None:
        raise NotImplementedError

    async def _ensure_mode(self) -> None:
        """RSA-N only: make sure the VNA mode is active."""

    # ------------------------------------------------------------------ #
    # Validation helpers
    # ------------------------------------------------------------------ #

    def _check_freq(self, value: float, name: str) -> float:
        spec = self.spec()
        value = float(value)
        if not spec["freq_min"] <= value <= spec["freq_max"]:
            raise ValueError(
                f"{name} {value:g} Hz outside {self.model} range "
                f"{spec['freq_min']:g}..{spec['freq_max']:g} Hz"
            )
        return value

    def _check_trace(self, trace: int) -> int:
        trace = int(trace)
        if not 1 <= trace <= self.spec()["max_traces"]:
            raise ValueError(f"Trace must be 1..{self.spec()['max_traces']}")
        return trace

    def _check_marker(self, marker: int) -> int:
        marker = int(marker)
        if not 1 <= marker <= self.spec()["max_markers"]:
            raise ValueError(f"Marker must be 1..{self.spec()['max_markers']}")
        return marker

    def _check_param(self, sparam: str) -> str:
        key = normalize_sparam(sparam)
        if key not in self.spec()["parameters"]:
            raise ValueError(
                f"{self.model} supports parameters {', '.join(self.spec()['parameters'])}"
            )
        return key

    # ------------------------------------------------------------------ #
    # Sweep
    # ------------------------------------------------------------------ #

    async def set_start_stop(self, start: float, stop: float, channel: int = 1) -> Dict[str, Any]:
        start = self._check_freq(start, "Start frequency")
        stop = self._check_freq(stop, "Stop frequency")
        if start >= stop:
            raise ValueError("start must be below stop")
        await self._write(f"{self._freq_cmd('STARt', channel)} {start:.0f}")
        await self._write(f"{self._freq_cmd('STOP', channel)} {stop:.0f}")
        return await self.get_sweep(channel)

    async def set_center_span(self, center: float, span: float, channel: int = 1) -> Dict[str, Any]:
        center = float(center)
        span = float(span)
        if span <= 0:
            raise ValueError("span must be > 0")
        self._check_freq(center - span / 2, "Start frequency")
        self._check_freq(center + span / 2, "Stop frequency")
        await self._write(f"{self._freq_cmd('CENTer', channel)} {center:.0f}")
        await self._write(f"{self._freq_cmd('SPAN', channel)} {span:.0f}")
        return await self.get_sweep(channel)

    async def set_points(self, points: int, channel: int = 1) -> int:
        spec = self.spec()
        points = int(points)
        if not spec["min_points"] <= points <= spec["max_points"]:
            raise ValueError(f"Points must be {spec['min_points']}..{spec['max_points']}")
        await self._write(f"{self._points_cmd(channel)} {points}")
        return int(float(await self._query(f"{self._points_cmd(channel)}?")))

    async def set_power(self, power: float, channel: int = 1) -> float:
        spec = self.spec()
        power = float(power)
        if not spec["power_min"] <= power <= spec["power_max"]:
            raise ValueError(f"Power must be {spec['power_min']:g}..{spec['power_max']:g} dBm")
        await self._write(f"{self._power_cmd(channel)} {power:g}")
        return float(await self._query(f"{self._power_cmd(channel)}?"))

    async def set_if_bandwidth(self, bandwidth: float, channel: int = 1) -> float:
        spec = self.spec()
        bandwidth = float(bandwidth)
        if not spec["ifbw_min"] <= bandwidth <= spec["ifbw_max"]:
            raise ValueError(f"IF bandwidth must be {spec['ifbw_min']:g}..{spec['ifbw_max']:g} Hz")
        await self._write(f"{self._ifbw_cmd(channel)} {bandwidth:g}")
        return float(await self._query(f"{self._ifbw_cmd(channel)}?"))

    async def set_sweep(
        self,
        start: Optional[float] = None,
        stop: Optional[float] = None,
        points: Optional[int] = None,
        power: Optional[float] = None,
        if_bandwidth: Optional[float] = None,
        channel: int = 1,
    ) -> Dict[str, Any]:
        """Configure the stimulus in one call; ``None`` leaves a setting unchanged."""
        if start is not None or stop is not None:
            cur = await self.get_sweep(channel) if (start is None or stop is None) else {}
            await self.set_start_stop(
                cur["start_frequency"] if start is None else start,
                cur["stop_frequency"] if stop is None else stop,
                channel,
            )
        if points is not None:
            await self.set_points(points, channel)
        if power is not None:
            await self.set_power(power, channel)
        if if_bandwidth is not None:
            await self.set_if_bandwidth(if_bandwidth, channel)
        return await self.get_sweep(channel)

    async def get_sweep(self, channel: int = 1) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "channel": channel,
            "start_frequency": float(await self._query(f"{self._freq_cmd('STARt', channel)}?")),
            "stop_frequency": float(await self._query(f"{self._freq_cmd('STOP', channel)}?")),
            "points": int(float(await self._query(f"{self._points_cmd(channel)}?"))),
        }
        for key, cmd in (("power_dbm", self._power_cmd(channel)), ("if_bandwidth", self._ifbw_cmd(channel))):
            try:
                out[key] = float(await self._query(f"{cmd}?"))
            except Exception as e:
                logger.debug(f"{key} query failed: {e}")
                out[key] = None
        try:
            out["continuous"] = (await self._query(f"{self._continuous_cmd(channel)}?")).strip() in ("1", "ON")
        except Exception:
            out["continuous"] = None
        return out

    async def set_continuous(self, enabled: bool = True, channel: int = 1) -> bool:
        await self._write(f"{self._continuous_cmd(channel)} {_bool_word(enabled)}")
        return (await self._query(f"{self._continuous_cmd(channel)}?")).strip() in ("1", "ON")

    async def sweep_single(self, channel: int = 1, wait: bool = True) -> bool:
        """Run one sweep and (optionally) block on *OPC? until it completes."""
        async with self._io_lock:
            await self._single_sweep_cmd(channel)
            if not wait:
                return True
            old = self.instrument.timeout if self.instrument is not None else None
            if self.instrument is not None:
                self.instrument.timeout = self.SWEEP_TIMEOUT_MS
            try:
                result = (await self._query("*OPC?")).strip()
            finally:
                if self.instrument is not None and old is not None:
                    self.instrument.timeout = old
            return result in ("1", "+1")

    # ------------------------------------------------------------------ #
    # Traces
    # ------------------------------------------------------------------ #

    async def set_parameter(self, trace: int, s_param: str, channel: int = 1) -> str:
        trace = self._check_trace(trace)
        sparam = self._check_param(s_param)
        await self._write_parameter(trace, sparam, channel)
        self._trace_params[trace] = sparam
        return sparam

    async def get_parameter(self, trace: int = 1, channel: int = 1) -> str:
        trace = self._check_trace(trace)
        raw = (await self._read_parameter(trace, channel)).strip().strip('"').upper()
        try:
            sparam = normalize_sparam(raw)
        except ValueError:
            sparam = raw
        self._trace_params[trace] = sparam
        return sparam

    def _allowed_formats(self, sparam: Optional[str]) -> Sequence[str]:
        if self.FORMATS_BY_PARAM is None:
            return list(FORMATS)
        if sparam and sparam in self.FORMATS_BY_PARAM:
            return self.FORMATS_BY_PARAM[sparam]
        return sorted({f for fl in self.FORMATS_BY_PARAM.values() for f in fl})

    async def set_format(self, trace: int, fmt: str, channel: int = 1) -> str:
        trace = self._check_trace(trace)
        key = normalize_format(fmt)
        sparam = self._trace_params.get(trace)
        if self.FORMATS_BY_PARAM is not None and sparam is None:
            try:
                sparam = await self.get_parameter(trace, channel)
            except Exception:
                sparam = None
        allowed = self._allowed_formats(sparam)
        if key not in allowed:
            raise ValueError(
                f"Format {key} not available for {sparam or 'this trace'} on {self.model}; "
                f"valid: {', '.join(allowed)}"
            )
        await self._write_format(trace, key, channel)
        self._trace_formats[trace] = key
        return key

    async def get_format(self, trace: int = 1, channel: int = 1) -> str:
        trace = self._check_trace(trace)
        raw = (await self._read_format(trace, channel)).strip().upper()
        key = _FORMAT_ALIASES.get(raw, raw)
        if key not in FORMATS:
            key = "MLOG"
        self._trace_formats[trace] = key
        return key

    async def list_traces(self, channel: int = 1) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def get_complex_trace(self, trace: int = 1, channel: int = 1) -> Dict[str, Any]:
        """Raw complex S-parameter data as parallel real/imag lists."""
        trace = self._check_trace(trace)
        sweep = await self.get_sweep(channel)
        z = await self._read_complex(trace, channel)
        freqs = await self._read_stimulus(trace, channel, len(z), sweep["start_frequency"], sweep["stop_frequency"])
        return {
            "trace": trace,
            "parameter": await self.get_parameter(trace, channel),
            "frequencies": freqs,
            "real": [c.real for c in z],
            "imag": [c.imag for c in z],
        }

    async def get_trace(self, trace: int = 1, channel: int = 1, single: bool = False) -> NetworkAnalyzerData:
        """Read one trace as formatted data (``single=True`` runs a sweep first)."""
        trace = self._check_trace(trace)
        if single:
            await self.sweep_single(channel)
        sparam = await self.get_parameter(trace, channel)
        fmt = await self.get_format(trace, channel)
        sweep = await self.get_sweep(channel)
        points = sweep["points"]
        freqs = await self._read_stimulus(trace, channel, points, sweep["start_frequency"], sweep["stop_frequency"])
        values, secondary = await self._read_formatted(trace, channel, fmt, freqs)
        n = len(values)
        if len(freqs) != n and n > 0:
            freqs = np.linspace(sweep["start_frequency"], sweep["stop_frequency"], n).tolist()
        return NetworkAnalyzerData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            trace=trace,
            parameter=sparam,
            format=fmt,
            start_frequency=sweep["start_frequency"],
            stop_frequency=sweep["stop_frequency"],
            num_points=n or points,
            frequencies=freqs,
            values=values,
            secondary_values=secondary,
            unit=FORMATS[fmt][1],
        )

    # ------------------------------------------------------------------ #
    # Markers
    # ------------------------------------------------------------------ #

    async def set_marker(self, marker: int = 1, frequency: Optional[float] = None,
                         trace: int = 1, channel: int = 1) -> Dict[str, Any]:
        marker = self._check_marker(marker)
        trace = self._check_trace(trace)
        await self._marker_enable(marker, trace, channel)
        if frequency is not None:
            await self._write(f"{self._marker_x_cmd(marker, trace, channel)} {float(frequency):.0f}")
        self._marker_trace[marker] = trace
        return await self.get_marker(marker, trace, channel)

    async def get_marker(self, marker: int = 1, trace: Optional[int] = None, channel: int = 1) -> Dict[str, Any]:
        """Marker X/Y; ``trace`` defaults to the trace the marker was last placed on."""
        marker = self._check_marker(marker)
        trace = self._check_trace(self._marker_trace.get(marker, 1) if trace is None else trace)
        x = float(await self._query(f"{self._marker_x_cmd(marker, trace, channel)}?"))
        ys = parse_float_list(await self._query(f"{self._marker_y_cmd(marker, trace, channel)}?"))
        return {
            "marker": marker,
            "trace": trace,
            "frequency": x,
            "value": ys[0] if ys else float("nan"),
            "secondary": ys[1] if len(ys) > 1 else None,
            "unit": FORMATS.get(self._trace_formats.get(trace, "MLOG"), ("", "", False))[1],
        }

    async def marker_search(self, marker: int = 1, kind: str = "MAX", trace: int = 1,
                            channel: int = 1) -> Dict[str, Any]:
        marker = self._check_marker(marker)
        trace = self._check_trace(trace)
        key = str(kind).strip().upper()
        key = {"PEAK": "MAX", "MAXIMUM": "MAX", "MINIMUM": "MIN"}.get(key, key)
        if key not in ("MAX", "MIN"):
            raise ValueError("Marker search kind must be MAX or MIN")
        await self._marker_enable(marker, trace, channel)
        await self._marker_search_cmd(marker, key, trace, channel)
        self._marker_trace[marker] = trace
        return await self.get_marker(marker, trace, channel)

    # ------------------------------------------------------------------ #
    # Calibration (dialect specific)
    # ------------------------------------------------------------------ #

    async def calibrate_start(self, method: str = "SOL", channel: int = 1) -> Dict[str, Any]:
        raise NotImplementedError

    async def calibrate_acquire(self, standard: str, channel: int = 1) -> str:
        raise NotImplementedError

    async def calibrate_save(self, channel: int = 1) -> bool:
        raise NotImplementedError

    async def calibrate_abort(self, channel: int = 1) -> bool:
        raise NotImplementedError

    async def set_correction(self, enabled: bool, channel: int = 1) -> Optional[bool]:
        raise NotImplementedError

    async def get_correction(self, channel: int = 1) -> Optional[bool]:
        raise NotImplementedError

    async def set_rf_output(self, enabled: bool) -> bool:
        raise ValueError(f"{self.model} has no remote RF output switch")

    async def get_rf_output(self) -> Optional[bool]:
        return None

    async def set_mode(self, mode: str = "VNA", wait: bool = True) -> str:
        return "VNA"

    # ------------------------------------------------------------------ #
    # Integration hooks
    # ------------------------------------------------------------------ #

    async def get_readings(self) -> NetworkAnalyzerData:
        return await self.get_trace(1)

    async def _trace_for_parameter(self, sparam: str, channel: int) -> int:
        sparam = self._check_param(sparam)
        for tr, p in self._trace_params.items():
            if p == sparam:
                return tr
        try:
            for entry in await self.list_traces(channel):
                if entry.get("parameter") == sparam:
                    self._trace_params[entry["trace"]] = sparam
                    return entry["trace"]
        except Exception as e:
            logger.debug(f"list_traces failed: {e}")
        await self.set_parameter(1, sparam, channel)
        return 1

    async def get_measurement(self, channel: str = "TRACE1:MIN") -> Dict[str, Any]:
        """Acquisition hook.  Channel names:

        - ``TRACE<n>[:MIN|MAX|MEAN|PTP|MIN_FREQ|MAX_FREQ|AT:<hz>]`` (default MIN)
        - ``S11:MIN``, ``S21:MAX``, ``S21:AT:2.4e9`` ... (trace carrying that parameter)
        - ``MARKER<n>`` -> marker Y value, ``frequency`` = marker X
        """
        key = (channel or "TRACE1:MIN").strip().upper().replace(" ", "")
        if key.startswith("MARKER") or key.startswith("MKR"):
            n = int(re.sub(r"\D", "", key) or 1)
            mk = await self.get_marker(n)
            return {"value": mk["value"], "frequency": mk["frequency"], "unit": mk["unit"],
                    "marker": n, "trace": mk["trace"]}
        parts = key.split(":")
        target = parts[0] or "TRACE1"
        stat = parts[1] if len(parts) > 1 and parts[1] else "MIN"
        if target.startswith("TRACE") or target.startswith("TR"):
            trace = int(re.sub(r"\D", "", target) or 1)
        else:
            trace = await self._trace_for_parameter(target, 1)
        data = await self.get_trace(trace)
        vals = np.asarray(data.values, dtype=float)
        freqs = np.asarray(data.frequencies, dtype=float)
        out: Dict[str, Any] = {
            "value": float("nan"), "frequency": None, "unit": data.unit,
            "parameter": data.parameter, "format": data.format, "trace": trace, "stat": stat,
        }
        if vals.size == 0:
            return out
        if stat == "AT":
            if len(parts) < 3:
                raise ValueError("Use <target>:AT:<frequency_hz>")
            f = float(parts[2])
            out["value"] = float(np.interp(f, freqs, vals)) if freqs.size == vals.size else float("nan")
            out["frequency"] = f
        elif stat in ("MIN", "MIN_FREQ"):
            i = int(np.nanargmin(vals))
            out["value"] = float(freqs[i]) if stat == "MIN_FREQ" and freqs.size == vals.size else float(vals[i])
            out["frequency"] = float(freqs[i]) if freqs.size == vals.size else None
            if stat == "MIN_FREQ":
                out["unit"] = "Hz"
        elif stat in ("MAX", "MAX_FREQ"):
            i = int(np.nanargmax(vals))
            out["value"] = float(freqs[i]) if stat == "MAX_FREQ" and freqs.size == vals.size else float(vals[i])
            out["frequency"] = float(freqs[i]) if freqs.size == vals.size else None
            if stat == "MAX_FREQ":
                out["unit"] = "Hz"
        elif stat in ("MEAN", "AVG", "AVERAGE"):
            out["value"] = float(np.nanmean(vals))
        elif stat in ("PTP", "PEAK_TO_PEAK"):
            out["value"] = float(np.nanmax(vals) - np.nanmin(vals))
        else:
            raise ValueError(f"Unknown statistic '{stat}' (MIN, MAX, MEAN, PTP, MIN_FREQ, MAX_FREQ, AT:<hz>)")
        return out

    async def get_measurements(self, channel: Any = 1) -> Dict[str, Any]:
        try:
            trace = int(re.sub(r"\D", "", str(channel)) or 1)
        except ValueError:
            trace = 1
        data = await self.get_trace(trace)
        vals = np.asarray(data.values, dtype=float)
        if vals.size == 0:
            return {"parameter": data.parameter, "format": data.format, "unit": data.unit}
        imin, imax = int(np.nanargmin(vals)), int(np.nanargmax(vals))
        return {
            "parameter": data.parameter,
            "format": data.format,
            "unit": data.unit,
            "min": float(vals[imin]),
            "max": float(vals[imax]),
            "mean": float(np.nanmean(vals)),
            "min_frequency": data.frequencies[imin] if len(data.frequencies) == vals.size else None,
            "max_frequency": data.frequencies[imax] if len(data.frequencies) == vals.size else None,
            "points": int(vals.size),
        }

    async def get_state(self, channel: int = 1) -> Dict[str, Any]:
        state: Dict[str, Any] = {"model": self.model, "sweep": await self.get_sweep(channel), "traces": {}}
        try:
            traces = await self.list_traces(channel)
        except Exception:
            traces = [{"trace": 1}]
        for entry in traces:
            tr = entry["trace"]
            try:
                state["traces"][tr] = {
                    "parameter": await self.get_parameter(tr, channel),
                    "format": await self.get_format(tr, channel),
                }
            except Exception as e:
                logger.debug(f"Trace {tr} state failed: {e}")
        try:
            state["correction"] = await self.get_correction(channel)
        except Exception:
            state["correction"] = None
        return state

    async def reset(self) -> None:
        await self._write("*RST")
        await asyncio.sleep(0.5)
        self._trace_params.clear()
        self._trace_formats.clear()
        self._marker_trace.clear()
        self._cal_method = None
        self._cal_param = None
        await self._ensure_mode()

    async def get_error(self) -> Dict[str, Any]:
        raw = await self._query(":SYSTem:ERRor?")
        code_str, _, message = raw.partition(",")
        try:
            code = int(float(code_str.strip()))
        except ValueError:
            code = None
        return {"code": code, "message": message.strip().strip('"'), "raw": raw}


# --------------------------------------------------------------------------- #
# RSA3000N / RSA5000N VNA mode
# --------------------------------------------------------------------------- #


class RigolRSAN(RigolVNABase):
    """VNA mode of the RSA3000N / RSA5000N spectrum analyzers.

    Quirks (VNA Programming Guide, 2020):
    - The measured parameter is a mode-wide *function* (``:CONFigure S11|S21``),
      all four traces show the same parameter.  S12/S22 do not exist.
    - ``:TRACe<n>:DATA?`` always returns complex ``(re,im)`` pairs; the driver
      derives the display format numerically (``format_complex``).
    - No stimulus query; frequencies are linearly spaced start..stop.
    - No ``:SENSe:CORRection:STATe``; calibration is OPEN/SHORT/LOAD then
      ``:CALibration:S11:SAVE`` (S11) or THROugh then ``:CALibration:S21:SAVE``.
    - Rigol recommends an 8 s pause after switching modes.
    """

    MODEL = "RSA5065N"
    DEFAULT_SPEC = MODEL_TABLE["RSA5065N"]
    INTERFACES = ("USB", "LAN")
    HAS_CORRECTION_STATE = False
    HAS_RF_OUTPUT = False
    MODE_SWITCH_DELAY_S = 8.0
    CALIBRATION_METHODS = ("SOL", "THRU")
    FORMATS_BY_PARAM = {
        "S11": ("MLOG", "PHAS", "GDEL", "SLIN", "SLOG", "SCOM", "SMIT", "SADM",
                "PLIN", "PLOG", "POL", "MLIN", "SWR", "REAL", "IMAG", "UPH", "PPH"),
        "S21": ("MLOG", "PHAS", "GDEL", "MLIN", "UPH", "PPH"),
    }

    async def _post_connect(self):
        await self._ensure_mode()

    async def _ensure_mode(self) -> None:
        try:
            current = (await self._query(":INSTrument:SELect?")).strip().upper()
        except Exception:
            current = ""
        if current not in ("VNA", "5"):
            await self.set_mode("VNA", wait=True)

    async def set_mode(self, mode: str = "VNA", wait: bool = True) -> str:
        """Select the RSA working mode (``:INSTrument:SELect SA|RTSA|VSA|EMI|VNA``)."""
        key = str(mode).strip().upper()
        if key not in ("SA", "RTSA", "VSA", "EMI", "VNA"):
            raise ValueError("Mode must be SA, RTSA, VSA, EMI or VNA")
        await self._write(f":INSTrument:SELect {key}")
        if wait:
            await asyncio.sleep(self.MODE_SWITCH_DELAY_S)
        return (await self._query(":INSTrument:SELect?")).strip().upper()

    # --- dialect ----------------------------------------------------------
    def _freq_cmd(self, key: str, channel: int) -> str:
        return f":SENSe:FREQuency:{key}"

    def _points_cmd(self, channel: int) -> str:
        return ":SENSe:SWEep:POINts"

    def _power_cmd(self, channel: int) -> str:
        return ":SOURce:EXTernal:POWer:LEVel:IMMediate:AMPLitude"

    def _ifbw_cmd(self, channel: int) -> str:
        return ":SENSe:BANDwidth:RESolution"

    async def _write_parameter(self, trace: int, sparam: str, channel: int) -> None:
        await self._write(f":CONFigure {sparam}")
        for tr in list(self._trace_params):
            self._trace_params[tr] = sparam

    async def _read_parameter(self, trace: int, channel: int) -> str:
        return await self._query(":CONFigure?")

    async def _write_format(self, trace: int, fmt: str, channel: int) -> None:
        await self._write(f":DISPlay:TRACe{trace}:FORMat {FORMATS[fmt][0]}")

    async def _read_format(self, trace: int, channel: int) -> str:
        return await self._query(f":DISPlay:TRACe{trace}:FORMat?")

    async def _read_complex(self, trace: int, channel: int) -> List[complex]:
        return parse_complex_list(await self._query(f":TRACe{trace}:DATA?"))

    async def _single_sweep_cmd(self, channel: int) -> None:
        await self._write(":INITiate:IMMediate")

    async def _marker_enable(self, marker: int, trace: int, channel: int) -> None:
        mode = (await self._query(f":CALCulate:MARKer{marker}:MODE?")).strip().upper()
        if mode.startswith("OFF") or not mode:
            await self._write(f":CALCulate:MARKer{marker}:MODE POSition")

    def _marker_x_cmd(self, marker: int, trace: int, channel: int) -> str:
        return f":CALCulate:MARKer{marker}:X"

    def _marker_y_cmd(self, marker: int, trace: int, channel: int) -> str:
        return f":CALCulate:MARKer{marker}:Y"

    async def _marker_search_cmd(self, marker: int, kind: str, trace: int, channel: int) -> None:
        await self._write(f":CALCulate:MARKer{marker}:{'MAXimum:MAX' if kind == 'MAX' else 'MINimum'}")

    async def list_traces(self, channel: int = 1) -> List[Dict[str, Any]]:
        sparam = await self.get_parameter(1, channel)
        return [{"trace": tr, "parameter": sparam, "name": f"TRACE{tr}"}
                for tr in range(1, self.spec()["max_traces"] + 1)]

    # --- calibration --------------------------------------------------------
    async def calibrate_start(self, method: str = "SOL", channel: int = 1) -> Dict[str, Any]:
        """Begin a calibration: ``SOL``/``S11``/``1PORT`` (open-short-load) or ``THRU``/``S21``."""
        key = str(method).strip().upper()
        if key in ("SOL", "OSL", "S11", "1PORT", "REFLECTION", "BASIC", "FULL"):
            self._cal_method, self._cal_param = "SOL", "S11"
        elif key in ("THRU", "THROUGH", "S21", "RESPONSE", "RESP", "TRANSMISSION"):
            self._cal_method, self._cal_param = "THRU", "S21"
        else:
            raise ValueError("Calibration method must be SOL (S11 open/short/load) or THRU (S21)")
        await self.set_parameter(1, self._cal_param, channel)
        standards = ["OPEN", "SHORT", "LOAD"] if self._cal_method == "SOL" else ["THRU"]
        return {"method": self._cal_method, "parameter": self._cal_param, "standards": standards}

    async def calibrate_acquire(self, standard: str, channel: int = 1) -> str:
        std = _CAL_STANDARDS.get(str(standard).strip().upper())
        if std is None:
            raise ValueError("Standard must be OPEN, SHORT, LOAD or THRU")
        if std == "THRU":
            if self._cal_method not in (None, "THRU"):
                raise ValueError("THRU belongs to the S21 calibration; call calibrate_start('THRU')")
            self._cal_method, self._cal_param = "THRU", "S21"
            await self._write(":CALibration:S21:THROugh")
        else:
            if self._cal_method not in (None, "SOL"):
                raise ValueError(f"{std.upper()} belongs to the S11 calibration; call calibrate_start('SOL')")
            self._cal_method, self._cal_param = "SOL", "S11"
            await self._write(f":CALibration:S11:{std}")
        return std.upper()

    async def calibrate_save(self, channel: int = 1) -> bool:
        if self._cal_method is None:
            raise ValueError("No calibration in progress")
        await self._write(f":CALibration:{self._cal_param}:SAVE")
        self._cal_method = None
        return True

    async def calibrate_abort(self, channel: int = 1) -> bool:
        param = self._cal_param or "S11"
        await self._write(f":CALibration:{param}:ABORt")
        self._cal_method = None
        return True

    async def calibrate_clear(self) -> bool:
        await self._write(":CALibration:CLEAr")
        return True

    async def set_correction(self, enabled: bool, channel: int = 1) -> Optional[bool]:
        if enabled:
            raise ValueError("RSA-N applies correction automatically after :CALibration:...:SAVE")
        await self.calibrate_clear()
        return False

    async def get_correction(self, channel: int = 1) -> Optional[bool]:
        return None  # not queryable on the RSA-N VNA mode

    async def execute_command(self, command: str, parameters: dict) -> Any:
        if command == "calibrate_clear":
            return await self.calibrate_clear()
        return await super().execute_command(command, parameters)


# --------------------------------------------------------------------------- #
# DNA6000 / DNA6000-R
# --------------------------------------------------------------------------- #


class RigolDNA6000(RigolVNABase):
    """DNA6000 and DNA6000-R series (channel/measurement indexed SCPI).

    Quirks:
    - ``<mn>`` (trace) must already exist; the power-on default is trace 1
      (``CH1_S11_1``).  ``list_traces`` parses ``:CALCulate<cn>:PARameter:
      CATalog:EXTended? DEFine``.
    - ``:CALCulate<cn>:MEASure<mn>:MARKer<mk>:Y?`` returns two numbers; the
      second is 0 for scalar formats.
    - ``:SENSe<cn>:CORRection:COLLect[:ACQuire] <char>`` takes an undocumented
      string; the driver sends OPEN|SHORt|LOAD|THRU.
    - ``:FORM:DATA`` exists only in the non-R guide; ASCII,0 is the default on
      both so the driver only *tries* to set it.
    """

    MODEL = "DNA6082"
    DEFAULT_SPEC = MODEL_TABLE["DNA6082"]
    INTERFACES = ("USB", "LAN", "GPIB")
    HAS_CORRECTION_STATE = True
    HAS_RF_OUTPUT = True
    CALIBRATION_METHODS = ("BASIC", "RESPONSE", "POWER", "NONE")
    FORMATS_BY_PARAM = None
    _DNA_FORMATS = ("MLOG", "MLIN", "PHAS", "UPH", "IMAG", "REAL", "POL", "SMIT", "SADM", "SWR", "GDEL", "PPH")

    def _allowed_formats(self, sparam: Optional[str]) -> Sequence[str]:
        return self._DNA_FORMATS

    async def _post_connect(self):
        try:
            await self._write(":FORM:DATA ASCII,0")
        except Exception as e:
            logger.debug(f":FORM:DATA not accepted ({e}); assuming ASCII default")

    # --- dialect ----------------------------------------------------------
    def _freq_cmd(self, key: str, channel: int) -> str:
        return f":SENSe{int(channel)}:FREQuency:{key}"

    def _points_cmd(self, channel: int) -> str:
        return f":SENSe{int(channel)}:SWEep:POINts"

    def _power_cmd(self, channel: int) -> str:
        return f":SOURce{int(channel)}:POWer"

    def _ifbw_cmd(self, channel: int) -> str:
        return f":SENSe{int(channel)}:BANDwidth"

    def _meas(self, trace: int, channel: int) -> str:
        return f":CALCulate{int(channel)}:MEASure{int(trace)}"

    async def _write_parameter(self, trace: int, sparam: str, channel: int) -> None:
        await self._write(f":CALCulate{int(channel)}:PARameter{trace}:DEFine {sparam}")

    async def _read_parameter(self, trace: int, channel: int) -> str:
        return await self._query(f":CALCulate{int(channel)}:PARameter{trace}:DEFine?")

    async def _write_format(self, trace: int, fmt: str, channel: int) -> None:
        await self._write(f"{self._meas(trace, channel)}:FORMat {FORMATS[fmt][0]}")

    async def _read_format(self, trace: int, channel: int) -> str:
        return await self._query(f"{self._meas(trace, channel)}:FORMat?")

    async def _read_stimulus(self, trace: int, channel: int, points: int,
                             start: float, stop: float) -> List[float]:
        try:
            freqs = parse_float_list(await self._query(f"{self._meas(trace, channel)}:DATA:X?"))
            if freqs:
                return freqs
        except Exception as e:
            logger.debug(f"DATA:X? failed: {e}")
        try:
            freqs = parse_float_list(await self._query(f":SENSe{int(channel)}:FREQuency:DATA?"))
            if freqs:
                return freqs
        except Exception as e:
            logger.debug(f"FREQuency:DATA? failed: {e}")
        return await super()._read_stimulus(trace, channel, points, start, stop)

    async def _read_complex(self, trace: int, channel: int) -> List[complex]:
        return parse_complex_list(await self._query(f"{self._meas(trace, channel)}:DATA:SDATA?"))

    async def _read_formatted(self, trace: int, channel: int, fmt: str,
                              freqs: List[float]) -> Tuple[List[float], List[float]]:
        flat = parse_float_list(await self._query(f"{self._meas(trace, channel)}:DATA:FDATA?"))
        if FORMATS[fmt][2] and len(flat) == 2 * len(freqs) and freqs:
            return flat[0::2], flat[1::2]
        if FORMATS[fmt][2] and not freqs and len(flat) % 2 == 0:
            return flat[0::2], flat[1::2]
        return flat, []

    async def _single_sweep_cmd(self, channel: int) -> None:
        await self._write(f":SENSe{int(channel)}:SWEep:MODE SINGle")

    async def _marker_enable(self, marker: int, trace: int, channel: int) -> None:
        state = (await self._query(f"{self._meas(trace, channel)}:MARKer{marker}?")).strip()
        if state not in ("1", "ON"):
            await self._write(f"{self._meas(trace, channel)}:MARKer{marker} ON")

    def _marker_x_cmd(self, marker: int, trace: int, channel: int) -> str:
        return f"{self._meas(trace, channel)}:MARKer{marker}:X"

    def _marker_y_cmd(self, marker: int, trace: int, channel: int) -> str:
        return f"{self._meas(trace, channel)}:MARKer{marker}:Y"

    async def _marker_search_cmd(self, marker: int, kind: str, trace: int, channel: int) -> None:
        word = "MAXimum" if kind == "MAX" else "MINimum"
        await self._write(f"{self._meas(trace, channel)}:MARKer{marker}:FUNCtion:EXECute {word}")

    async def list_traces(self, channel: int = 1) -> List[Dict[str, Any]]:
        raw = (await self._query(f":CALCulate{int(channel)}:PARameter:CATalog:EXTended? DEFine")).strip().strip('"')
        items = [p.strip() for p in raw.split(",") if p.strip()]
        traces: List[Dict[str, Any]] = []
        for i in range(0, len(items) - 1, 2):
            name, param = items[i], items[i + 1].upper()
            m = re.search(r"_(\d+)$", name)
            trace = int(m.group(1)) if m else len(traces) + 1
            traces.append({"trace": trace, "parameter": param, "name": name})
            self._trace_params[trace] = param
        return traces

    async def create_trace(self, s_param: str, channel: int = 1) -> List[Dict[str, Any]]:
        """Add a trace (``:DISPlay:TRACe:NEW 0``) then define its parameter."""
        sparam = self._check_param(s_param)
        await self._write(":DISPlay:TRACe:NEW 0")
        traces = await self.list_traces(channel)
        if traces:
            newest = max(t["trace"] for t in traces)
            await self.set_parameter(newest, sparam, channel)
            traces = await self.list_traces(channel)
        return traces

    # --- trigger / output ---------------------------------------------------
    async def set_trigger_source(self, source: str = "IMMediate") -> str:
        key = str(source).strip().upper()
        aliases = {"IMM": "IMMediate", "IMMEDIATE": "IMMediate", "INT": "IMMediate", "INTERNAL": "IMMediate",
                   "EXT": "EXTernal", "EXTERNAL": "EXTernal", "MAN": "MANual", "MANUAL": "MANual", "BUS": "MANual"}
        word = aliases.get(key)
        if word is None:
            raise ValueError("Trigger source must be IMMediate, EXTernal or MANual")
        await self._write(f":TRIGger:SOURce {word}")
        return (await self._query(":TRIGger:SOURce?")).strip().upper()

    async def manual_trigger(self, channel: int = 1) -> None:
        """``:INITiate<cn>:IMMediate`` (requires trigger source MANual)."""
        await self._write(f":INITiate{int(channel)}:IMMediate")

    async def abort(self) -> None:
        await self._write(":ABORt")

    async def set_rf_output(self, enabled: bool) -> bool:
        await self._write(f":OUTPut:STATe {_bool_word(enabled)}")
        return (await self._query(":OUTPut:STATe?")).strip() in ("1", "ON")

    async def get_rf_output(self) -> Optional[bool]:
        return (await self._query(":OUTPut:STATe?")).strip() in ("1", "ON")

    # --- calibration --------------------------------------------------------
    _METHODS = {
        "BASIC": "BASic", "BAS": "BASic", "SOL": "BASic", "OSL": "BASic", "SOLT": "BASic", "FULL": "BASic",
        "1PORT": "BASic", "2PORT": "BASic",
        "RESPONSE": "RESP", "RESP": "RESP", "THRU": "RESP", "S21": "RESP",
        "POWER": "RPOWer", "RPOW": "RPOWer", "RPOWER": "RPOWer",
        "NONE": "NONE",
    }

    async def calibrate_start(self, method: str = "BASIC", channel: int = 1,
                              s_param: Optional[str] = None) -> Dict[str, Any]:
        word = self._METHODS.get(str(method).strip().upper())
        if word is None:
            raise ValueError("Method must be BASIC, RESPONSE, POWER or NONE")
        if s_param is not None:
            await self.set_parameter(1, s_param, channel)
        await self._write(f":SENSe{int(channel)}:CORRection:COLLect:METHod {word}")
        current = (await self._query(f":SENSe{int(channel)}:CORRection:COLLect:METHod?")).strip().upper()
        self._cal_method = current
        return {"method": current, "channel": channel,
                "standards": ["OPEN", "SHORT", "LOAD", "THRU"] if current.startswith("BAS") else ["THRU"]}

    async def calibrate_acquire(self, standard: str, channel: int = 1) -> str:
        std = _CAL_STANDARDS.get(str(standard).strip().upper())
        if std is None:
            raise ValueError("Standard must be OPEN, SHORT, LOAD or THRU")
        await self._write(f":SENSe{int(channel)}:CORRection:COLLect:ACQuire {std}")
        return std.upper()

    async def calibrate_save(self, channel: int = 1) -> bool:
        await self._write(f":SENSe{int(channel)}:CORRection:COLLect:SAVE")
        self._cal_method = None
        return True

    async def calibrate_abort(self, channel: int = 1) -> bool:
        await self._write(f":SENSe{int(channel)}:CORRection:COLLect:METHod NONE")
        self._cal_method = None
        return True

    async def set_correction(self, enabled: bool, channel: int = 1) -> Optional[bool]:
        await self._write(f":SENSe{int(channel)}:CORRection:STATe {_bool_word(enabled)}")
        return await self.get_correction(channel)

    async def get_correction(self, channel: int = 1) -> Optional[bool]:
        return (await self._query(f":SENSe{int(channel)}:CORRection:STATe?")).strip() in ("1", "ON")

    async def execute_command(self, command: str, parameters: dict) -> Any:
        extra = {
            "create_trace": self.create_trace,
            "set_trigger_source": self.set_trigger_source,
            "manual_trigger": self.manual_trigger,
            "abort": self.abort,
        }
        if command in extra:
            return await extra[command](**dict(parameters or {}))
        return await super().execute_command(command, parameters)


# Model keywords used by equipment.manager.find_keyword_driver.
RigolRSAN.MODEL_KEYWORDS = ('RSA3015N', 'RSA3030N', 'RSA3045N', 'RSA5032N', 'RSA5065N')
RigolDNA6000.MODEL_KEYWORDS = ('DNA6082-R', 'DNA6084-R', 'DNA6142-R', 'DNA6144-R', 'DNA6202-R', 'DNA6204-R', 'DNA6262-R', 'DNA6264-R', 'DNA6082', 'DNA6084', 'DNA6142', 'DNA6144', 'DNA6202', 'DNA6204', 'DNA6262', 'DNA6264', 'DNA6')
