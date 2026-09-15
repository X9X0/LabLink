"""Mock spectrum analyzer for testing without hardware.

Behaves like a Rigol DSA815 driven through ``rigol_spectrum_analyzer.py``:
same command names, same ``SpectrumData`` traces, same acquisition channel
names.  The simulated input is a -95 dBm noise floor (at 1 MHz RBW; it drops
10 dB per decade of RBW) plus any number of CW tones added with
:meth:`set_simulated_signal`.  All methods raise ``RuntimeError`` when the
mock is not connected.
"""

import asyncio
import logging
import math
import re
import uuid
from typing import Any, Dict, List, Optional, Union

import numpy as np

from shared.models.data import SpectrumData
from shared.models.equipment import (ConnectionType, EquipmentInfo,
                                     EquipmentStatus, EquipmentType)

logger = logging.getLogger(__name__)

_DETECTORS = ("POSITIVE", "NEGATIVE", "NORMAL", "SAMPLE", "RMS", "VAVERAGE", "QPEAK")
_DETECTOR_ALIASES = {"POS": "POSITIVE", "PEAK": "POSITIVE", "NEG": "NEGATIVE", "NORM": "NORMAL",
                     "SAMP": "SAMPLE", "RAV": "RMS", "RAVERAGE": "RMS", "VAV": "VAVERAGE",
                     "AVERAGE": "VAVERAGE", "AVER": "VAVERAGE", "QPE": "QPEAK", "QUASIPEAK": "QPEAK"}
_TRACE_MODES = ("WRITE", "MAXHOLD", "MINHOLD", "VIEW", "BLANK", "AVERAGE", "VIDEOAVG", "POWERAVG")
_TRACE_MODE_ALIASES = {"WRIT": "WRITE", "CLEARWRITE": "WRITE", "MAXH": "MAXHOLD", "MAX": "MAXHOLD",
                       "MINH": "MINHOLD", "MIN": "MINHOLD", "BLAN": "BLANK", "OFF": "BLANK",
                       "AVER": "AVERAGE", "AVG": "AVERAGE", "VID": "VIDEOAVG", "POW": "POWERAVG"}
_UNITS = {"DBM": "dBm", "DBMV": "dBmV", "DBUV": "dBuV", "V": "V", "W": "W"}
_MARKER_MODES = ("POSITION", "DELTA", "BAND", "SPAN")

_NOISE_FLOOR_DBM_AT_1MHZ = -95.0


def _requires_connection(method):
    async def wrapper(self, *args, **kwargs):
        if not self.connected:
            raise RuntimeError("Mock spectrum analyzer not connected")
        return await method(self, *args, **kwargs)

    wrapper.__name__ = method.__name__
    wrapper.__doc__ = method.__doc__
    return wrapper


class MockSpectrumAnalyzer:
    """Mock 9 kHz - 1.5 GHz swept spectrum analyzer with tracking generator."""

    FREQ_MIN = 9e3
    FREQ_MAX = 1.5e9
    RBW_MIN = 10.0
    RBW_MAX = 1e6
    MAX_POINTS = 3001
    MARKERS = 4
    TRACES = 3

    def __init__(self, resource_manager=None, resource_string: str = "MOCK::SA::0"):
        self.resource_string = resource_string
        self.connected = False
        self.cached_info: Optional[EquipmentInfo] = None

        self.manufacturer = "Mock Instruments"
        self.model = "MockSA-815"
        self.serial_number = f"MOCK{uuid.uuid4().hex[:8].upper()}"
        self.firmware_version = "v1.0.0-mock"
        self.has_tracking_generator = True

        # Simulated RF input: frequency (Hz) -> amplitude (dBm)
        self.signals: Dict[float, float] = {100e6: -20.0}
        self.noise_floor_dbm = _NOISE_FLOOR_DBM_AT_1MHZ
        self.noise_sigma_db = 0.5
        self._rng = np.random.default_rng(815)

        # Instrument state (DSA815 defaults)
        self.center = (self.FREQ_MIN + self.FREQ_MAX) / 2
        self.span = self.FREQ_MAX - self.FREQ_MIN
        self.rbw = 1e6
        self.vbw = 1e6
        self.rbw_auto = True
        self.vbw_auto = True
        self.reference_level = 0.0
        self.attenuation = 10.0
        self.attenuation_auto = True
        self.preamp = False
        self.unit = "DBM"
        self.points = 601
        self.sweep_time = 0.0375
        self.sweep_time_auto = True
        self.continuous = True
        self.detector = "POSITIVE"
        self.trace_modes: Dict[int, str] = {1: "WRITE", 2: "BLANK", 3: "BLANK"}
        self.average_count = 100
        self.peak_search_mode = "MAXIMUM"
        self.markers: Dict[int, Dict[str, Any]] = {
            n: {"enabled": False, "frequency": self.center, "mode": "POSITION", "trace": 1}
            for n in range(1, self.MARKERS + 1)
        }
        self.tg_enabled = False
        self.tg_level = -20.0
        self.data_format = "ASCII"
        self.mode = "GPSA"
        self._held: Dict[int, Optional[List[float]]] = {1: None, 2: None, 3: None}
        self.error_queue: List[str] = []
        self.sweeps = 0

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def connect(self):
        await asyncio.sleep(0.05)
        self.connected = True
        self.cached_info = await self.get_info()
        logger.info(f"Connected to mock spectrum analyzer: {self.model}")

    async def disconnect(self):
        await asyncio.sleep(0.02)
        self.connected = False
        logger.info("Disconnected from mock spectrum analyzer")

    async def get_info(self) -> EquipmentInfo:
        from ..base import generate_equipment_id

        return EquipmentInfo(
            id=generate_equipment_id(self.resource_string, "sa_"),
            type=EquipmentType.SPECTRUM_ANALYZER,
            manufacturer=self.manufacturer,
            model=self.model,
            serial_number=self.serial_number,
            connection_type=ConnectionType.USB,
            resource_string=self.resource_string,
        )

    async def get_status(self) -> EquipmentStatus:
        try:
            capabilities = {
                "family": "MOCK",
                "model_table_entry": self.model,
                "frequency_min": self.FREQ_MIN,
                "frequency_max": self.FREQ_MAX,
                "rbw_min": self.RBW_MIN,
                "rbw_max": self.RBW_MAX,
                "max_points": self.MAX_POINTS,
                "points_settable": True,
                "has_tracking_generator": self.has_tracking_generator,
                "tracking_generator_level_range": [-40.0, 0.0],
                "supports_rtsa": False,
                "rtsa_bandwidth": None,
                "supports_screenshot": False,
                "has_preamp": True,
                "markers": self.MARKERS,
                "traces": self.TRACES,
                "attenuation_range": [0.0, 30.0],
                "reference_level_range": [-100.0, 20.0],
                "detectors": list(_DETECTORS),
                "trace_modes": list(_TRACE_MODES),
                "marker_modes": list(_MARKER_MODES),
                "data_formats": ["ASCII", "REAL,32"],
                "supports_mode_select": False,
                "modes": [],
                "channel_power_method": "instrument",
                "measurement_channels": ["PEAK", "PEAK_FREQ", "MARKER1..MARKER4", "MARKER1_FREQ",
                                         "CHPOWER", "TRACE1:MAX", "TRACE1:MIN", "TRACE1:MEAN"],
                "interfaces": ["MOCK"],
                "supports_acquisition": True,
                "mock": True,
            }
            return EquipmentStatus(
                id=self.cached_info.id if self.cached_info else "unknown",
                connected=self.connected,
                firmware_version=self.firmware_version,
                capabilities=capabilities,
            )
        except Exception as e:
            return EquipmentStatus(
                id=self.cached_info.id if self.cached_info else "unknown",
                connected=False,
                error=str(e),
            )

    async def execute_command(self, command: str, parameters: dict) -> Any:
        if not self.connected:
            raise RuntimeError("Mock spectrum analyzer not connected")
        parameters = dict(parameters or {})
        handlers = {
            "set_frequency": self.set_frequency,
            "set_start_stop": self.set_start_stop,
            "get_frequency": self.get_frequency,
            "set_full_span": self.set_full_span,
            "set_zero_span": self.set_zero_span,
            "set_rbw": self.set_rbw,
            "set_vbw": self.set_vbw,
            "get_bandwidth": self.get_bandwidth,
            "set_reference_level": self.set_reference_level,
            "set_attenuation": self.set_attenuation,
            "set_preamp": self.set_preamp,
            "set_unit": self.set_unit,
            "get_amplitude": self.get_amplitude,
            "set_sweep": self.set_sweep,
            "get_sweep": self.get_sweep,
            "single_sweep": self.single_sweep,
            "continuous": self.set_continuous,
            "set_continuous": self.set_continuous,
            "trigger_sweep": self.trigger_sweep,
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
            "peak_search": self.peak_search,
            "next_peak": self.next_peak,
            "set_marker": self.set_marker,
            "get_marker": self.get_marker,
            "marker_off": self.marker_off,
            "all_markers_off": self.all_markers_off,
            "marker_to_center": self.marker_to_center,
            "set_peak_search_mode": self.set_peak_search_mode,
            "set_tracking_generator": self.set_tracking_generator,
            "get_tracking_generator": self.get_tracking_generator,
            "measure_channel_power": self.measure_channel_power,
            "measure_obw": self.measure_obw,
            "set_mode": self.set_mode,
            "get_mode": self.get_mode,
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
    # Simulation controls (test helpers)
    # ------------------------------------------------------------------ #

    def set_simulated_signal(self, frequency: float, amplitude: Optional[float]) -> None:
        """Add/replace a CW tone at ``frequency`` (Hz) with ``amplitude`` (dBm);
        ``amplitude=None`` removes it."""
        frequency = float(frequency)
        if amplitude is None:
            self.signals.pop(frequency, None)
        else:
            self.signals[frequency] = float(amplitude)

    def clear_simulated_signals(self) -> None:
        self.signals.clear()

    def set_noise(self, sigma_db: float) -> None:
        """Gaussian amplitude noise (1 sigma, dB) added to every trace point."""
        self.noise_sigma_db = max(0.0, float(sigma_db))

    def set_noise_floor(self, dbm_at_1mhz_rbw: float) -> None:
        self.noise_floor_dbm = float(dbm_at_1mhz_rbw)

    # ------------------------------------------------------------------ #
    # Frequency
    # ------------------------------------------------------------------ #

    @property
    def start(self) -> float:
        return self.center - self.span / 2

    @property
    def stop(self) -> float:
        return self.center + self.span / 2

    def _check_frequency(self, value: float, name: str) -> float:
        value = float(value)
        if not 0.0 <= value <= self.FREQ_MAX:
            raise ValueError(f"{name} must be 0..{self.FREQ_MAX:g} Hz on {self.model}")
        return value

    def _clamp(self) -> None:
        # Like the real instrument: the center wins and the span shrinks so
        # that start >= 0 and stop <= FREQ_MAX.
        self.center = min(max(self.center, 0.0), self.FREQ_MAX)
        self.span = min(self.span, 2 * self.center, 2 * (self.FREQ_MAX - self.center))
        self._held = {n: None for n in self._held}

    @_requires_connection
    async def set_frequency(self, center: Optional[float] = None, span: Optional[float] = None) -> Dict[str, float]:
        if center is not None:
            self.center = self._check_frequency(center, "center")
        if span is not None:
            span = float(span)
            if span < 0 or span > self.FREQ_MAX:
                raise ValueError(f"span must be 0..{self.FREQ_MAX:g} Hz")
            self.span = span
        self._clamp()
        return await self.get_frequency()

    @_requires_connection
    async def set_start_stop(self, start: float, stop: float) -> Dict[str, float]:
        start = self._check_frequency(start, "start")
        stop = self._check_frequency(stop, "stop")
        if stop < start:
            raise ValueError("stop must be >= start")
        self.center, self.span = (start + stop) / 2, stop - start
        self._clamp()
        return await self.get_frequency()

    @_requires_connection
    async def set_full_span(self) -> Dict[str, float]:
        self.center, self.span = (self.FREQ_MIN + self.FREQ_MAX) / 2, self.FREQ_MAX - self.FREQ_MIN
        self._clamp()
        return await self.get_frequency()

    @_requires_connection
    async def set_zero_span(self) -> Dict[str, float]:
        self.span = 0.0
        self._clamp()
        return await self.get_frequency()

    @_requires_connection
    async def get_frequency(self) -> Dict[str, float]:
        return {"center": self.center, "span": self.span, "start": self.start, "stop": self.stop}

    # ------------------------------------------------------------------ #
    # Bandwidth
    # ------------------------------------------------------------------ #

    @staticmethod
    def _snap_1_3_10(value: float) -> float:
        decade = 10 ** math.floor(math.log10(value))
        mant = value / decade
        snapped = 1 if mant < 2 else 3 if mant < 6.5 else 10
        return snapped * decade

    @_requires_connection
    async def set_rbw(self, rbw: Union[float, str], auto: bool = False) -> Dict[str, Any]:
        if auto or (isinstance(rbw, str) and rbw.strip().upper() == "AUTO"):
            self.rbw_auto = True
            self.rbw = self._snap_1_3_10(max(self.RBW_MIN, min(self.RBW_MAX, self.span / 100 or self.RBW_MIN)))
        else:
            rbw = float(rbw)
            if not self.RBW_MIN <= rbw <= self.RBW_MAX:
                raise ValueError(f"RBW must be {self.RBW_MIN:g}..{self.RBW_MAX:g} Hz on {self.model}")
            self.rbw_auto = False
            self.rbw = self._snap_1_3_10(rbw)
        if self.vbw_auto:
            self.vbw = self.rbw
        self._held = {n: None for n in self._held}
        return await self.get_bandwidth()

    @_requires_connection
    async def set_vbw(self, vbw: Union[float, str], auto: bool = False) -> Dict[str, Any]:
        if auto or (isinstance(vbw, str) and vbw.strip().upper() == "AUTO"):
            self.vbw_auto = True
            self.vbw = self.rbw
        else:
            vbw = float(vbw)
            if vbw < 1.0 or vbw > 3e6:
                raise ValueError("VBW must be 1 Hz..3 MHz")
            self.vbw_auto = False
            self.vbw = self._snap_1_3_10(vbw)
        return await self.get_bandwidth()

    @_requires_connection
    async def get_bandwidth(self) -> Dict[str, Any]:
        return {"rbw": self.rbw, "vbw": self.vbw, "rbw_auto": self.rbw_auto, "vbw_auto": self.vbw_auto}

    # ------------------------------------------------------------------ #
    # Amplitude
    # ------------------------------------------------------------------ #

    @_requires_connection
    async def set_reference_level(self, level: float) -> Dict[str, Any]:
        level = float(level)
        if not -100.0 <= level <= 20.0:
            raise ValueError("Reference level must be -100..20 dBm")
        self.reference_level = level
        if self.attenuation_auto:
            self.attenuation = float(max(0, min(30, round((level + 20) / 10) * 10)))
        return await self.get_amplitude()

    @_requires_connection
    async def set_attenuation(self, db: Optional[float] = None, auto: bool = False) -> Dict[str, Any]:
        if auto or db is None:
            self.attenuation_auto = True
        else:
            db = float(db)
            if not 0.0 <= db <= 30.0:
                raise ValueError("Attenuation must be 0..30 dB")
            self.attenuation_auto = False
            self.attenuation = db
        return await self.get_amplitude()

    @_requires_connection
    async def set_preamp(self, enabled: bool) -> bool:
        self.preamp = bool(enabled)
        return self.preamp

    @_requires_connection
    async def set_unit(self, unit: str) -> str:
        key = str(unit).strip().upper()
        if key not in _UNITS:
            raise ValueError("Unit must be one of DBM, DBMV, DBUV, V, W")
        self.unit = key
        return _UNITS[key]

    @_requires_connection
    async def get_unit(self) -> str:
        return _UNITS[self.unit]

    @_requires_connection
    async def get_amplitude(self) -> Dict[str, Any]:
        return {
            "reference_level": self.reference_level,
            "attenuation": self.attenuation,
            "attenuation_auto": self.attenuation_auto,
            "preamp": self.preamp,
            "unit": _UNITS[self.unit],
        }

    # ------------------------------------------------------------------ #
    # Sweep
    # ------------------------------------------------------------------ #

    @_requires_connection
    async def set_sweep(self, points: Optional[int] = None, time: Optional[Union[float, str]] = None,
                        continuous: Optional[bool] = None) -> Dict[str, Any]:
        if points is not None:
            points = int(points)
            if not 101 <= points <= self.MAX_POINTS:
                raise ValueError(f"Sweep points must be 101..{self.MAX_POINTS}")
            self.points = points
            self._held = {n: None for n in self._held}
        if time is not None:
            if isinstance(time, str) and time.strip().upper() == "AUTO":
                self.sweep_time_auto = True
                self.sweep_time = max(0.0375, self.span / (self.rbw * self.vbw) * 2) if self.rbw else 0.0375
            else:
                t = float(time)
                if not 20e-6 <= t <= 7500.0:
                    raise ValueError("Sweep time must be 2e-05..7500 s")
                self.sweep_time_auto = False
                self.sweep_time = t
        if continuous is not None:
            self.continuous = bool(continuous)
        return await self.get_sweep()

    @_requires_connection
    async def set_continuous(self, enabled: bool = True) -> bool:
        self.continuous = bool(enabled)
        return self.continuous

    @_requires_connection
    async def trigger_sweep(self) -> None:
        self.sweeps += 1
        await asyncio.sleep(0.001)

    @_requires_connection
    async def get_sweep(self) -> Dict[str, Any]:
        return {"points": self.points, "time": self.sweep_time, "time_auto": self.sweep_time_auto,
                "continuous": self.continuous}

    @_requires_connection
    async def single_sweep(self, timeout_s: Optional[float] = None) -> bool:
        self.continuous = False
        self.sweeps += 1
        await asyncio.sleep(min(self.sweep_time, 0.05))
        return True

    # ------------------------------------------------------------------ #
    # Detector / trace / average / format
    # ------------------------------------------------------------------ #

    @_requires_connection
    async def set_detector(self, detector: str, trace: int = 1) -> str:
        key = str(detector).strip().upper().replace("-", "").replace("_", "")
        key = _DETECTOR_ALIASES.get(key, key)
        if key not in _DETECTORS:
            raise ValueError(f"Detector must be one of {list(_DETECTORS)}")
        self.detector = key
        return key

    @_requires_connection
    async def get_detector(self, trace: int = 1) -> str:
        return self.detector

    def _check_trace(self, trace: int) -> int:
        trace = int(trace)
        if not 1 <= trace <= self.TRACES:
            raise ValueError(f"Trace must be 1..{self.TRACES}")
        return trace

    @_requires_connection
    async def set_trace_mode(self, trace: int = 1, mode: str = "WRITE") -> str:
        trace = self._check_trace(trace)
        key = str(mode).strip().upper().replace(" ", "")
        key = _TRACE_MODE_ALIASES.get(key, key)
        if key not in _TRACE_MODES:
            raise ValueError(f"Unknown trace mode '{mode}'")
        if key != "VIEW":
            self._held[trace] = None
        self.trace_modes[trace] = key
        return key

    @_requires_connection
    async def get_trace_mode(self, trace: int = 1) -> str:
        return self.trace_modes[self._check_trace(trace)]

    @_requires_connection
    async def set_average(self, count: int = 100, trace: int = 1, enabled: bool = True) -> Dict[str, Any]:
        count = int(count)
        if not 1 <= count <= 10000:
            raise ValueError("Average count must be 1..10000")
        self.average_count = count
        await self.set_trace_mode(trace, "AVERAGE" if enabled else "WRITE")
        return {"count": count, "trace": trace, "enabled": bool(enabled)}

    @_requires_connection
    async def set_data_format(self, fmt: str = "ASCII") -> str:
        key = str(fmt).strip().upper().replace(" ", "")
        if key in ("ASCII", "ASC"):
            self.data_format = "ASCII"
        elif key in ("REAL,32", "REAL32", "REAL"):
            self.data_format = "REAL,32"
        else:
            raise ValueError("MockSA-815 supports formats: ASCII, REAL,32")
        return self.data_format

    # ------------------------------------------------------------------ #
    # Trace synthesis
    # ------------------------------------------------------------------ #

    def _frequencies(self) -> np.ndarray:
        if self.span <= 0:
            return np.full(self.points, self.center)
        return np.linspace(self.start, self.stop, self.points)

    def _noise_floor(self) -> float:
        floor = self.noise_floor_dbm + 10 * math.log10(self.rbw / 1e6)
        if self.preamp:
            floor -= 10.0
        floor += self.attenuation - 10.0  # DSA815 DANL is specified at 10 dB attenuation
        return floor

    def _synthesise(self) -> List[float]:
        freqs = self._frequencies()
        floor = self._noise_floor()
        trace = np.full(self.points, floor, dtype=float)
        if self.noise_sigma_db > 0:
            trace += self._rng.normal(0.0, self.noise_sigma_db, self.points)
        if self.detector == "NEGATIVE":
            trace -= 2.0
        elif self.detector in ("SAMPLE", "RMS", "VAVERAGE"):
            trace -= 1.0
        half = max(self.rbw / 2, 1e-9)
        for f0, amp in self.signals.items():
            if self.span <= 0:
                if abs(f0 - self.center) <= half:
                    trace = np.maximum(trace, amp - 3.0 * ((f0 - self.center) / half) ** 2)
                continue
            # Gaussian-ish RBW filter response, -3 dB at +/- RBW/2, -60 dB at +/- 2.2 RBW.
            response = amp - 3.0 * ((freqs - f0) / half) ** 2
            trace = np.maximum(trace, response)
        # Anything above the reference level + 10 dB is clipped like a real front end.
        trace = np.minimum(trace, self.reference_level + 10.0)
        return [float(v) for v in trace]

    def _trace_values(self, trace: int) -> List[float]:
        mode = self.trace_modes[trace]
        if mode == "BLANK":
            return []
        fresh = self._synthesise()
        if mode == "VIEW":
            if self._held[trace] is None:
                self._held[trace] = fresh
            return list(self._held[trace])
        if mode == "MAXHOLD":
            prev = self._held[trace]
            held = fresh if prev is None or len(prev) != len(fresh) else [max(a, b) for a, b in zip(prev, fresh)]
            self._held[trace] = held
            return list(held)
        if mode == "MINHOLD":
            prev = self._held[trace]
            held = fresh if prev is None or len(prev) != len(fresh) else [min(a, b) for a, b in zip(prev, fresh)]
            self._held[trace] = held
            return list(held)
        return fresh

    def _convert_unit(self, values: List[float]) -> List[float]:
        if self.unit == "DBM":
            return values
        if self.unit == "DBMV":
            return [v + 46.99 for v in values]
        if self.unit == "DBUV":
            return [v + 106.99 for v in values]
        if self.unit == "W":
            return [10 ** (v / 10) / 1000.0 for v in values]
        return [math.sqrt(10 ** (v / 10) / 1000.0 * 50.0) for v in values]  # V into 50 Ohm

    @_requires_connection
    async def get_trace(self, trace: int = 1, sweep: bool = False) -> SpectrumData:
        trace = self._check_trace(trace)
        if sweep:
            await self.single_sweep()
        else:
            await asyncio.sleep(0.002)
        values = self._convert_unit(self._trace_values(trace))
        freqs = self._frequencies()
        peak_f = peak_a = None
        if values:
            idx = int(np.argmax(values))
            peak_a, peak_f = values[idx], float(freqs[idx])
        markers = {}
        for n, m in self.markers.items():
            if m["enabled"]:
                markers[f"M{n}"] = {"frequency": m["frequency"], "amplitude": self._amplitude_at(m["frequency"])}
        return SpectrumData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            trace=trace,
            start_frequency=self.start,
            stop_frequency=self.stop,
            center_frequency=self.center,
            span=self.span,
            rbw=self.rbw,
            vbw=self.vbw,
            reference_level=self.reference_level,
            attenuation=self.attenuation,
            unit=_UNITS[self.unit],
            detector=self.detector,
            num_points=len(values),
            values=values,
            markers=markers,
            peak_frequency=peak_f,
            peak_amplitude=peak_a,
        )

    @_requires_connection
    async def get_readings(self) -> SpectrumData:
        return await self.get_trace(1)

    # ------------------------------------------------------------------ #
    # Acquisition hooks
    # ------------------------------------------------------------------ #

    @_requires_connection
    async def get_measurement(self, channel: str = "PEAK") -> Dict[str, Any]:
        key = (channel or "PEAK").strip().upper().replace(" ", "")
        unit = _UNITS[self.unit]
        if key in ("", "PEAK", "CH1", "1", "TRACE1:PEAK", "TRACE1"):
            data = await self.get_trace(1)
            return self._result(data.peak_amplitude, unit, "PEAK", frequency=data.peak_frequency)
        if key in ("PEAK_FREQ", "PEAKFREQ", "PEAK:FREQ"):
            data = await self.get_trace(1)
            return self._result(data.peak_frequency, "Hz", "PEAK_FREQ", amplitude=data.peak_amplitude)
        m = re.fullmatch(r"MARKER(\d+)(?:[_:](FREQ|X|Y|AMPL))?", key)
        if m:
            n = int(m.group(1))
            marker = await self.get_marker(n)
            if m.group(2) in ("FREQ", "X"):
                return self._result(marker["frequency"], "Hz", f"MARKER{n}_FREQ")
            return self._result(marker["amplitude"], unit, f"MARKER{n}", frequency=marker["frequency"])
        if key in ("CHPOWER", "CHP", "CHANNEL_POWER"):
            chp = await self.measure_channel_power()
            return self._result(chp["power"], chp["unit"], "CHPOWER", density=chp["density"], method=chp["method"])
        m = re.fullmatch(r"TRACE(\d+):(MAX|MIN|MEAN|AVG|PEAK_FREQ|PEAKFREQ)", key)
        if m:
            n, stat = int(m.group(1)), m.group(2)
            data = await self.get_trace(n)
            if not data.values:
                return self._result(None, unit, key)
            if stat == "MAX":
                return self._result(max(data.values), unit, key)
            if stat == "MIN":
                return self._result(min(data.values), unit, key)
            if stat in ("MEAN", "AVG"):
                return self._result(sum(data.values) / len(data.values), unit, key)
            return self._result(data.peak_frequency, "Hz", key)
        raise ValueError(
            f"Unknown measurement channel '{channel}'. Use PEAK, PEAK_FREQ, MARKER1..{self.MARKERS}, "
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

    @_requires_connection
    async def get_measurements(self, channel: Any = 1) -> Dict[str, Any]:
        trace = int(channel) if str(channel).isdigit() else 1
        data = await self.get_trace(trace)
        return {
            "peak": data.peak_amplitude if data.peak_amplitude is not None else float("nan"),
            "peak_frequency": data.peak_frequency if data.peak_frequency is not None else float("nan"),
            "min": min(data.values) if data.values else float("nan"),
            "mean": sum(data.values) / len(data.values) if data.values else float("nan"),
            "unit": data.unit,
            "num_points": data.num_points,
        }

    # ------------------------------------------------------------------ #
    # Markers
    # ------------------------------------------------------------------ #

    def _check_marker(self, marker: int) -> int:
        marker = int(marker)
        if not 1 <= marker <= self.MARKERS:
            raise ValueError(f"Marker must be 1..{self.MARKERS}")
        return marker

    def _amplitude_at(self, frequency: float) -> float:
        values = self._synthesise()
        freqs = self._frequencies()
        idx = int(np.argmin(np.abs(freqs - frequency)))
        return self._convert_unit([values[idx]])[0]

    def _peaks(self) -> List[tuple]:
        """(frequency, amplitude) of local maxima above the noise floor + 6 dB."""
        values = self._synthesise()
        freqs = self._frequencies()
        floor = self._noise_floor() + 6.0
        peaks = []
        for i in range(1, len(values) - 1):
            if values[i] > floor and values[i] >= values[i - 1] and values[i] > values[i + 1]:
                peaks.append((float(freqs[i]), values[i]))
        if not peaks and values:
            i = int(np.argmax(values))
            peaks.append((float(freqs[i]), values[i]))
        return sorted(peaks, key=lambda p: p[1], reverse=True)

    @_requires_connection
    async def peak_search(self, marker: int = 1, trace: Optional[int] = None) -> Dict[str, Any]:
        marker = self._check_marker(marker)
        m = self.markers[marker]
        m["enabled"] = True
        if trace is not None:
            m["trace"] = self._check_trace(trace)
        peaks = self._peaks()
        m["frequency"] = peaks[0][0]
        m["_peak_index"] = 0
        return await self.get_marker(marker)

    @_requires_connection
    async def next_peak(self, marker: int = 1, direction: str = "NEXT") -> Dict[str, Any]:
        marker = self._check_marker(marker)
        m = self.markers[marker]
        peaks = self._peaks()
        d = str(direction).strip().upper()
        if d == "NEXT":
            idx = m.get("_peak_index", -1) + 1
            if idx < len(peaks):
                m["frequency"], m["_peak_index"] = peaks[idx][0], idx
        elif d in ("LEFT", "RIGHT"):
            cands = [p for p in peaks if (p[0] < m["frequency"] if d == "LEFT" else p[0] > m["frequency"])]
            if cands:
                best = max(cands, key=lambda p: p[0]) if d == "LEFT" else min(cands, key=lambda p: p[0])
                m["frequency"] = best[0]
        elif d == "MIN":
            values = self._synthesise()
            m["frequency"] = float(self._frequencies()[int(np.argmin(values))])
        else:
            raise ValueError("direction must be NEXT, LEFT, RIGHT or MIN")
        m["enabled"] = True
        return await self.get_marker(marker)

    @_requires_connection
    async def set_marker(self, marker: int = 1, frequency: Optional[float] = None,
                         mode: Optional[str] = None, trace: Optional[int] = None) -> Dict[str, Any]:
        marker = self._check_marker(marker)
        m = self.markers[marker]
        m["enabled"] = True
        if mode is not None:
            key = {"NORMAL": "POSITION", "POS": "POSITION", "DELT": "DELTA", "DELTAPAIR": "BAND",
                   "SPANPAIR": "SPAN"}.get(str(mode).strip().upper(), str(mode).strip().upper())
            if key not in _MARKER_MODES:
                raise ValueError(f"Marker mode must be one of {list(_MARKER_MODES)}")
            m["mode"] = key
        if trace is not None:
            m["trace"] = self._check_trace(trace)
        if frequency is not None:
            m["frequency"] = float(min(max(self._check_frequency(frequency, "marker frequency"), self.start), self.stop))
        return await self.get_marker(marker)

    @_requires_connection
    async def get_marker(self, marker: int = 1) -> Dict[str, Any]:
        marker = self._check_marker(marker)
        m = self.markers[marker]
        return {
            "marker": marker,
            "enabled": m["enabled"],
            "frequency": m["frequency"],
            "amplitude": self._amplitude_at(m["frequency"]) if m["enabled"] else None,
            "mode": m["mode"],
            "unit": _UNITS[self.unit],
        }

    @_requires_connection
    async def marker_off(self, marker: int = 1) -> None:
        self.markers[self._check_marker(marker)]["enabled"] = False

    @_requires_connection
    async def all_markers_off(self) -> None:
        for m in self.markers.values():
            m["enabled"] = False

    @_requires_connection
    async def marker_to_center(self, marker: int = 1, peak: bool = False) -> Dict[str, float]:
        marker = self._check_marker(marker)
        if peak:
            await self.peak_search(marker)
        self.center = self.markers[marker]["frequency"]
        self._clamp()
        return await self.get_frequency()

    @_requires_connection
    async def set_peak_search_mode(self, mode: str = "MAXIMUM", marker: int = 1) -> str:
        key = {"MAX": "MAXIMUM", "MAXIMUM": "MAXIMUM", "PAR": "PARAMETER", "PARAMETER": "PARAMETER"}.get(
            str(mode).strip().upper()
        )
        if key is None:
            raise ValueError("Peak search mode must be MAXIMUM or PARAMETER")
        self.peak_search_mode = key
        return key

    # ------------------------------------------------------------------ #
    # Tracking generator / measurements / mode
    # ------------------------------------------------------------------ #

    def _require_tg(self) -> None:
        if not self.has_tracking_generator:
            raise ValueError(f"{self.model} has no tracking generator")

    @_requires_connection
    async def set_tracking_generator(self, enabled: bool, level: Optional[float] = None) -> Dict[str, Any]:
        self._require_tg()
        if level is not None:
            level = float(level)
            if not -40.0 <= level <= 0.0:
                raise ValueError("TG level must be -40..0 dBm")
            self.tg_level = level
        self.tg_enabled = bool(enabled)
        return await self.get_tracking_generator()

    @_requires_connection
    async def get_tracking_generator(self) -> Dict[str, Any]:
        self._require_tg()
        return {"enabled": self.tg_enabled, "level": self.tg_level, "unit": "dBm"}

    async def set_output(self, enabled: bool, channel: int = 1) -> Optional[Dict[str, Any]]:
        if not self.connected or not self.has_tracking_generator:
            return None
        return await self.set_tracking_generator(enabled)

    @_requires_connection
    async def measure_channel_power(self, bandwidth: Optional[float] = None,
                                    span: Optional[float] = None) -> Dict[str, Any]:
        values = self._synthesise()
        freqs = self._frequencies()
        bw = float(bandwidth) if bandwidth else self.span
        lo, hi = self.center - bw / 2, self.center + bw / 2
        bin_hz = self.span / max(self.points - 1, 1) if self.span > 0 else self.rbw
        total = sum(10 ** (v / 10) for f, v in zip(freqs, values) if lo <= f <= hi)
        if total <= 0:
            return {"power": None, "density": None, "unit": "dBm", "method": "instrument"}
        power = 10 * math.log10(total * bin_hz / self.rbw)
        return {"power": power, "density": power - 10 * math.log10(bw) if bw > 0 else None,
                "unit": "dBm", "density_unit": "dBm/Hz", "bandwidth": bw, "method": "instrument"}

    @_requires_connection
    async def measure_obw(self, percent: Optional[float] = None) -> Dict[str, Any]:
        pct = float(percent) if percent is not None else 99.0
        if not 1.0 <= pct <= 99.99:
            raise ValueError("OBW percent must be 1..99.99")
        values = self._synthesise()
        freqs = self._frequencies()
        lin = np.array([10 ** (v / 10) for v in values])
        cum = np.cumsum(lin) / lin.sum()
        lo = float(freqs[int(np.searchsorted(cum, (1 - pct / 100) / 2))])
        hi = float(freqs[min(int(np.searchsorted(cum, 1 - (1 - pct / 100) / 2)), len(freqs) - 1)])
        return {"obw": hi - lo, "transmit_frequency_error": (hi + lo) / 2 - self.center, "unit": "Hz"}

    @_requires_connection
    async def set_mode(self, mode: str = "GPSA") -> str:
        raise ValueError(f"{self.model} has a single (swept) mode")

    @_requires_connection
    async def get_mode(self) -> str:
        return self.mode

    # ------------------------------------------------------------------ #
    # System
    # ------------------------------------------------------------------ #

    @_requires_connection
    async def reset(self) -> None:
        signals = dict(self.signals)
        self.__init__(None, self.resource_string)
        self.signals = signals
        self.connected = True
        self.cached_info = await self.get_info()

    @_requires_connection
    async def get_error(self) -> Dict[str, Any]:
        if self.error_queue:
            msg = self.error_queue.pop(0)
            return {"code": -1, "message": msg, "raw": f"-1,\"{msg}\""}
        return {"code": 0, "message": "No error", "raw": '0,"No error"'}

    @_requires_connection
    async def clear_errors(self) -> bool:
        self.error_queue.clear()
        return True

    @_requires_connection
    async def get_state(self) -> Dict[str, Any]:
        return {
            "frequency": await self.get_frequency(),
            "bandwidth": await self.get_bandwidth(),
            "amplitude": await self.get_amplitude(),
            "sweep": await self.get_sweep(),
            "detector": self.detector,
            "trace1_mode": self.trace_modes[1],
            "tracking_generator": await self.get_tracking_generator(),
            "data_format": self.data_format,
        }

    async def get_range(self) -> Dict[str, Any]:
        return await self.get_frequency()
