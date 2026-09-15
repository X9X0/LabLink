"""Mock vector network analyzer for testing without hardware.

Behaves like the Rigol DNA6000 / RSA-N drivers in ``rigol_vna.py``: same
command names, same ``NetworkAnalyzerData`` traces, same ``get_measurement``
channel naming.  The simulated DUT is a 50 Ohm-ish termination on port 1
(S11 ~ -20 dB, adjustable with ``set_simulated_return_loss``) feeding a
Butterworth low-pass to port 2 (S21, cutoff adjustable with
``set_simulated_cutoff``).
"""

import asyncio
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

import numpy as np

from shared.models.data import NetworkAnalyzerData
from shared.models.equipment import (ConnectionType, EquipmentInfo,
                                     EquipmentStatus, EquipmentType)

from ..rigol_vna import (FORMATS, format_complex, normalize_format,
                         normalize_sparam)

logger = logging.getLogger(__name__)

_SPEC = {
    "family": "MOCK",
    "freq_min": 5e3,
    "freq_max": 8.5e9,
    "min_points": 2,
    "max_points": 100001,
    "ports": 2,
    "parameters": ["S11", "S12", "S21", "S22"],
    "power_min": -40.0,
    "power_max": 10.0,
    "ifbw_min": 1.0,
    "ifbw_max": 10e6,
    "max_markers": 16,
    "max_traces": 8,
}
_MOCK_FORMATS = ("MLOG", "MLIN", "PHAS", "UPH", "PPH", "IMAG", "REAL", "POL", "SMIT", "SADM", "SWR", "GDEL")


class MockVNA:
    """Two-port mock VNA (5 kHz .. 8.5 GHz)."""

    def __init__(self, resource_manager=None, resource_string: str = "MOCK::VNA::0"):
        self.resource_string = resource_string
        self.connected = False
        self.cached_info: Optional[EquipmentInfo] = None

        self.manufacturer = "Mock Instruments"
        self.model = "MockVNA-6000"
        self.serial_number = f"MOCK{uuid.uuid4().hex[:8].upper()}"
        self.firmware_version = "v1.0.0-mock"

        # Simulated DUT
        self.simulated_cutoff = 100e6          # S21 low-pass -3 dB point
        self.simulated_order = 3               # Butterworth order
        self.simulated_return_loss_db = -20.0  # |S11| in dB
        self.simulated_delay_s = 1.0e-9        # electrical delay of the path
        self.noise_db = 0.0                    # 1-sigma magnitude noise (dB)

        self._init_state()

    def _init_state(self):
        self.start_frequency = 1e6
        self.stop_frequency = 1e9
        self.points = 201
        self.power_dbm = -5.0
        self.if_bandwidth = 1e3
        self.continuous = True
        self.rf_output = True
        self.mode = "VNA"
        self.traces: Dict[int, Dict[str, str]] = {
            1: {"parameter": "S11", "format": "MLOG"},
            2: {"parameter": "S21", "format": "MLOG"},
        }
        self.markers: Dict[int, Dict[str, Any]] = {}
        self.cal_method: Optional[str] = None
        self.cal_acquired: List[str] = []
        self.correction = False
        self.trigger_source = "IMM"
        self.sweep_count = 0
        self.error_queue: List[str] = []

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def connect(self):
        await asyncio.sleep(0.05)
        self.connected = True
        self.cached_info = await self.get_info()
        logger.info(f"Connected to mock VNA: {self.model}")

    async def disconnect(self):
        await asyncio.sleep(0.02)
        self.connected = False
        logger.info("Disconnected from mock VNA")

    async def get_info(self) -> EquipmentInfo:
        from ..base import generate_equipment_id

        return EquipmentInfo(
            id=generate_equipment_id(self.resource_string, "vna_"),
            type=EquipmentType.VECTOR_NETWORK_ANALYZER,
            manufacturer=self.manufacturer,
            model=self.model,
            serial_number=self.serial_number,
            connection_type=ConnectionType.USB,
            resource_string=self.resource_string,
        )

    def spec(self) -> Dict[str, Any]:
        return dict(_SPEC)

    async def get_status(self) -> EquipmentStatus:
        try:
            capabilities = {
                "family": _SPEC["family"],
                "frequency_min": _SPEC["freq_min"],
                "frequency_max": _SPEC["freq_max"],
                "min_points": _SPEC["min_points"],
                "max_points": _SPEC["max_points"],
                "ports": _SPEC["ports"],
                "parameters": list(_SPEC["parameters"]),
                "power_min_dbm": _SPEC["power_min"],
                "power_max_dbm": _SPEC["power_max"],
                "ifbw_min": _SPEC["ifbw_min"],
                "ifbw_max": _SPEC["ifbw_max"],
                "max_markers": _SPEC["max_markers"],
                "max_traces": _SPEC["max_traces"],
                "formats": list(_MOCK_FORMATS),
                "calibration_methods": ["BASIC", "RESPONSE", "POWER", "NONE"],
                "calibration_standards": ["OPEN", "SHORT", "LOAD", "THRU"],
                "has_correction_state": True,
                "has_rf_output_control": True,
                "interfaces": ["MOCK"],
                "sweep": await self.get_sweep(),
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
            raise RuntimeError("Mock VNA not connected")
        parameters = dict(parameters or {})
        handlers = {
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
            "set_parameter": self.set_parameter,
            "get_parameter": self.get_parameter,
            "set_format": self.set_format,
            "get_format": self.get_format,
            "list_traces": self.list_traces,
            "create_trace": self.create_trace,
            "get_trace": self.get_trace,
            "get_complex_trace": self.get_complex_trace,
            "set_marker": self.set_marker,
            "get_marker": self.get_marker,
            "marker_search": self.marker_search,
            "calibrate_start": self.calibrate_start,
            "calibrate_acquire": self.calibrate_acquire,
            "calibrate_save": self.calibrate_save,
            "calibrate_abort": self.calibrate_abort,
            "set_correction": self.set_correction,
            "get_correction": self.get_correction,
            "set_rf_output": self.set_rf_output,
            "get_rf_output": self.get_rf_output,
            "set_trigger_source": self.set_trigger_source,
            "manual_trigger": self.manual_trigger,
            "abort": self.abort,
            "set_mode": self.set_mode,
            "get_readings": self.get_readings,
            "get_measurement": self.get_measurement,
            "get_measurements": self.get_measurements,
            "get_state": self.get_state,
            "reset": self.reset,
            "self_test": self.run_self_test,
            "get_error": self.get_error,
            "clear_errors": self.clear_errors,
        }
        handler = handlers.get(command)
        if handler is None:
            raise ValueError(f"Unknown command: {command}")
        return await handler(**parameters)

    # ------------------------------------------------------------------ #
    # Simulation controls
    # ------------------------------------------------------------------ #

    def set_simulated_cutoff(self, frequency: float, order: Optional[int] = None):
        """Set the S21 low-pass -3 dB frequency (Hz) and optional filter order."""
        frequency = float(frequency)
        if frequency <= 0:
            raise ValueError("Cutoff frequency must be > 0")
        self.simulated_cutoff = frequency
        if order is not None:
            self.simulated_order = max(1, int(order))

    def set_simulated_return_loss(self, db: float):
        """Set |S11| (and |S22|) in dB; must be negative."""
        db = float(db)
        if db > 0:
            raise ValueError("Return loss must be <= 0 dB")
        self.simulated_return_loss_db = db

    def set_noise(self, db: float):
        self.noise_db = max(0.0, float(db))

    def _frequencies(self) -> np.ndarray:
        return np.linspace(self.start_frequency, self.stop_frequency, self.points)

    def _sparam(self, param: str, freqs: np.ndarray) -> np.ndarray:
        w = 2.0 * np.pi * freqs
        delay = np.exp(-1j * w * self.simulated_delay_s)
        if param in ("S11", "S22"):
            mag = 10 ** (self.simulated_return_loss_db / 20.0)
            z = mag * delay
        else:
            ratio = freqs / self.simulated_cutoff
            mag = 1.0 / np.sqrt(1.0 + ratio ** (2 * self.simulated_order))
            phase = -self.simulated_order * np.arctan(ratio)
            z = mag * np.exp(1j * phase) * delay
        if self.noise_db:
            z = z * 10 ** (np.random.normal(0.0, self.noise_db, size=z.shape) / 20.0)
        return z

    # ------------------------------------------------------------------ #
    # Sweep
    # ------------------------------------------------------------------ #

    def _check_freq(self, value: float, name: str) -> float:
        value = float(value)
        if not _SPEC["freq_min"] <= value <= _SPEC["freq_max"]:
            raise ValueError(f"{name} {value:g} Hz outside {_SPEC['freq_min']:g}..{_SPEC['freq_max']:g} Hz")
        return value

    async def set_start_stop(self, start: float, stop: float, channel: int = 1) -> Dict[str, Any]:
        start = self._check_freq(start, "Start frequency")
        stop = self._check_freq(stop, "Stop frequency")
        if start >= stop:
            raise ValueError("start must be below stop")
        self.start_frequency, self.stop_frequency = start, stop
        return await self.get_sweep()

    async def set_center_span(self, center: float, span: float, channel: int = 1) -> Dict[str, Any]:
        if span <= 0:
            raise ValueError("span must be > 0")
        return await self.set_start_stop(center - span / 2, center + span / 2)

    async def set_points(self, points: int, channel: int = 1) -> int:
        points = int(points)
        if not _SPEC["min_points"] <= points <= _SPEC["max_points"]:
            raise ValueError(f"Points must be {_SPEC['min_points']}..{_SPEC['max_points']}")
        self.points = points
        return points

    async def set_power(self, power: float, channel: int = 1) -> float:
        power = float(power)
        if not _SPEC["power_min"] <= power <= _SPEC["power_max"]:
            raise ValueError(f"Power must be {_SPEC['power_min']:g}..{_SPEC['power_max']:g} dBm")
        self.power_dbm = power
        return power

    async def set_if_bandwidth(self, bandwidth: float, channel: int = 1) -> float:
        bandwidth = float(bandwidth)
        if not _SPEC["ifbw_min"] <= bandwidth <= _SPEC["ifbw_max"]:
            raise ValueError(f"IF bandwidth must be {_SPEC['ifbw_min']:g}..{_SPEC['ifbw_max']:g} Hz")
        self.if_bandwidth = bandwidth
        return bandwidth

    async def set_sweep(self, start: Optional[float] = None, stop: Optional[float] = None,
                        points: Optional[int] = None, power: Optional[float] = None,
                        if_bandwidth: Optional[float] = None, channel: int = 1) -> Dict[str, Any]:
        if start is not None or stop is not None:
            await self.set_start_stop(
                self.start_frequency if start is None else start,
                self.stop_frequency if stop is None else stop,
            )
        if points is not None:
            await self.set_points(points)
        if power is not None:
            await self.set_power(power)
        if if_bandwidth is not None:
            await self.set_if_bandwidth(if_bandwidth)
        return await self.get_sweep()

    async def get_sweep(self, channel: int = 1) -> Dict[str, Any]:
        return {
            "channel": channel,
            "start_frequency": self.start_frequency,
            "stop_frequency": self.stop_frequency,
            "points": self.points,
            "power_dbm": self.power_dbm,
            "if_bandwidth": self.if_bandwidth,
            "continuous": self.continuous,
        }

    async def set_continuous(self, enabled: bool = True, channel: int = 1) -> bool:
        self.continuous = bool(enabled)
        return self.continuous

    async def sweep_single(self, channel: int = 1, wait: bool = True) -> bool:
        await asyncio.sleep(min(0.2, 0.0005 * self.points))
        self.sweep_count += 1
        return True

    # ------------------------------------------------------------------ #
    # Traces
    # ------------------------------------------------------------------ #

    def _check_trace(self, trace: int) -> int:
        trace = int(trace)
        if trace not in self.traces:
            raise ValueError(f"Trace {trace} does not exist; traces: {sorted(self.traces)}")
        return trace

    def _check_param(self, s_param: str) -> str:
        key = normalize_sparam(s_param)
        if key not in _SPEC["parameters"]:
            raise ValueError(f"Mock VNA supports {', '.join(_SPEC['parameters'])}")
        return key

    async def set_parameter(self, trace: int, s_param: str, channel: int = 1) -> str:
        trace = self._check_trace(trace)
        self.traces[trace]["parameter"] = self._check_param(s_param)
        return self.traces[trace]["parameter"]

    async def get_parameter(self, trace: int = 1, channel: int = 1) -> str:
        return self.traces[self._check_trace(trace)]["parameter"]

    async def set_format(self, trace: int, fmt: str, channel: int = 1) -> str:
        trace = self._check_trace(trace)
        key = normalize_format(fmt)
        if key not in _MOCK_FORMATS:
            raise ValueError(f"Format {key} not available; valid: {', '.join(_MOCK_FORMATS)}")
        self.traces[trace]["format"] = key
        return key

    async def get_format(self, trace: int = 1, channel: int = 1) -> str:
        return self.traces[self._check_trace(trace)]["format"]

    async def list_traces(self, channel: int = 1) -> List[Dict[str, Any]]:
        return [{"trace": tr, "parameter": cfg["parameter"], "name": f"CH1_{cfg['parameter']}_{tr}"}
                for tr, cfg in sorted(self.traces.items())]

    async def create_trace(self, s_param: str, channel: int = 1) -> List[Dict[str, Any]]:
        if len(self.traces) >= _SPEC["max_traces"]:
            raise ValueError(f"At most {_SPEC['max_traces']} traces")
        new = max(self.traces) + 1
        self.traces[new] = {"parameter": self._check_param(s_param), "format": "MLOG"}
        return await self.list_traces()

    async def get_complex_trace(self, trace: int = 1, channel: int = 1) -> Dict[str, Any]:
        trace = self._check_trace(trace)
        freqs = self._frequencies()
        z = self._sparam(self.traces[trace]["parameter"], freqs)
        return {"trace": trace, "parameter": self.traces[trace]["parameter"],
                "frequencies": freqs.tolist(), "real": z.real.tolist(), "imag": z.imag.tolist()}

    async def get_trace(self, trace: int = 1, channel: int = 1, single: bool = False) -> NetworkAnalyzerData:
        trace = self._check_trace(trace)
        if single:
            await self.sweep_single()
        else:
            await asyncio.sleep(0.005)
        cfg = self.traces[trace]
        freqs = self._frequencies()
        z = self._sparam(cfg["parameter"], freqs)
        values, secondary = format_complex(z, cfg["format"], freqs)
        return NetworkAnalyzerData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            trace=trace,
            parameter=cfg["parameter"],
            format=cfg["format"],
            start_frequency=self.start_frequency,
            stop_frequency=self.stop_frequency,
            num_points=self.points,
            frequencies=freqs.tolist(),
            values=values,
            secondary_values=secondary,
            unit=FORMATS[cfg["format"]][1],
        )

    # ------------------------------------------------------------------ #
    # Markers
    # ------------------------------------------------------------------ #

    def _check_marker(self, marker: int) -> int:
        marker = int(marker)
        if not 1 <= marker <= _SPEC["max_markers"]:
            raise ValueError(f"Marker must be 1..{_SPEC['max_markers']}")
        return marker

    async def set_marker(self, marker: int = 1, frequency: Optional[float] = None,
                         trace: int = 1, channel: int = 1) -> Dict[str, Any]:
        marker = self._check_marker(marker)
        trace = self._check_trace(trace)
        mk = self.markers.setdefault(marker, {"frequency": self.start_frequency, "trace": trace})
        mk["trace"] = trace
        if frequency is not None:
            mk["frequency"] = float(np.clip(frequency, self.start_frequency, self.stop_frequency))
        return await self.get_marker(marker, trace)

    async def get_marker(self, marker: int = 1, trace: int = 1, channel: int = 1) -> Dict[str, Any]:
        marker = self._check_marker(marker)
        trace = self._check_trace(trace)
        mk = self.markers.get(marker)
        if mk is None:
            raise ValueError(f"Marker {marker} is off")
        data = await self.get_trace(mk.get("trace", trace))
        f = mk["frequency"]
        value = float(np.interp(f, data.frequencies, data.values))
        secondary = float(np.interp(f, data.frequencies, data.secondary_values)) if data.secondary_values else None
        return {"marker": marker, "trace": mk.get("trace", trace), "frequency": f,
                "value": value, "secondary": secondary, "unit": data.unit}

    async def marker_search(self, marker: int = 1, kind: str = "MAX", trace: int = 1,
                            channel: int = 1) -> Dict[str, Any]:
        marker = self._check_marker(marker)
        trace = self._check_trace(trace)
        key = {"PEAK": "MAX", "MAXIMUM": "MAX", "MINIMUM": "MIN"}.get(str(kind).upper(), str(kind).upper())
        if key not in ("MAX", "MIN"):
            raise ValueError("Marker search kind must be MAX or MIN")
        data = await self.get_trace(trace)
        vals = np.asarray(data.values)
        idx = int(np.argmax(vals) if key == "MAX" else np.argmin(vals))
        self.markers[marker] = {"frequency": data.frequencies[idx], "trace": trace}
        return await self.get_marker(marker, trace)

    # ------------------------------------------------------------------ #
    # Calibration / output / trigger
    # ------------------------------------------------------------------ #

    async def calibrate_start(self, method: str = "BASIC", channel: int = 1,
                              s_param: Optional[str] = None) -> Dict[str, Any]:
        key = str(method).strip().upper()
        aliases = {"SOL": "BAS", "OSL": "BAS", "SOLT": "BAS", "FULL": "BAS", "BASIC": "BAS", "1PORT": "BAS",
                   "2PORT": "BAS", "RESPONSE": "RESP", "THRU": "RESP", "S21": "RESP",
                   "POWER": "RPOW", "RPOWER": "RPOW", "NONE": "NONE", "S11": "BAS"}
        word = aliases.get(key, key)
        if word not in ("BAS", "RESP", "RPOW", "NONE"):
            raise ValueError("Method must be BASIC, RESPONSE, POWER or NONE")
        if s_param is not None:
            await self.set_parameter(1, s_param)
        self.cal_method = word
        self.cal_acquired = []
        return {"method": word, "channel": channel,
                "standards": ["OPEN", "SHORT", "LOAD", "THRU"] if word == "BAS" else ["THRU"]}

    async def calibrate_acquire(self, standard: str, channel: int = 1) -> str:
        std = str(standard).strip().upper()
        std = {"THROUGH": "THRU", "SHOR": "SHORT"}.get(std, std)
        if std not in ("OPEN", "SHORT", "LOAD", "THRU"):
            raise ValueError("Standard must be OPEN, SHORT, LOAD or THRU")
        if self.cal_method is None:
            raise ValueError("Call calibrate_start first")
        await asyncio.sleep(0.01)
        self.cal_acquired.append(std)
        return std

    async def calibrate_save(self, channel: int = 1) -> bool:
        if self.cal_method is None:
            raise ValueError("No calibration in progress")
        needed = {"BAS": {"OPEN", "SHORT", "LOAD"}, "RESP": {"THRU"}, "RPOW": set(), "NONE": set()}[self.cal_method]
        if not needed.issubset(self.cal_acquired):
            raise ValueError(f"Missing standards: {sorted(needed - set(self.cal_acquired))}")
        self.correction = True
        self.cal_method = None
        return True

    async def calibrate_abort(self, channel: int = 1) -> bool:
        self.cal_method = None
        self.cal_acquired = []
        return True

    async def set_correction(self, enabled: bool, channel: int = 1) -> Optional[bool]:
        self.correction = bool(enabled)
        return self.correction

    async def get_correction(self, channel: int = 1) -> Optional[bool]:
        return self.correction

    async def set_rf_output(self, enabled: bool) -> bool:
        self.rf_output = bool(enabled)
        return self.rf_output

    async def get_rf_output(self) -> Optional[bool]:
        return self.rf_output

    async def set_trigger_source(self, source: str = "IMMediate") -> str:
        key = str(source).strip().upper()[:3]
        if key not in ("IMM", "EXT", "MAN", "BUS", "INT"):
            raise ValueError("Trigger source must be IMMediate, EXTernal or MANual")
        self.trigger_source = {"BUS": "MAN", "INT": "IMM"}.get(key, key)
        return self.trigger_source

    async def manual_trigger(self, channel: int = 1) -> None:
        await self.sweep_single()

    async def abort(self) -> None:
        pass

    async def set_mode(self, mode: str = "VNA", wait: bool = True) -> str:
        key = str(mode).strip().upper()
        if key not in ("SA", "RTSA", "VSA", "EMI", "VNA"):
            raise ValueError("Mode must be SA, RTSA, VSA, EMI or VNA")
        self.mode = key
        return key

    # ------------------------------------------------------------------ #
    # Integration hooks
    # ------------------------------------------------------------------ #

    async def get_readings(self) -> NetworkAnalyzerData:
        return await self.get_trace(1)

    async def _trace_for_parameter(self, s_param: str) -> int:
        sparam = self._check_param(s_param)
        for tr, cfg in sorted(self.traces.items()):
            if cfg["parameter"] == sparam:
                return tr
        await self.set_parameter(1, sparam)
        return 1

    async def get_measurement(self, channel: str = "TRACE1:MIN") -> Dict[str, Any]:
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
            trace = await self._trace_for_parameter(target)
        data = await self.get_trace(trace)
        vals = np.asarray(data.values, dtype=float)
        freqs = np.asarray(data.frequencies, dtype=float)
        out: Dict[str, Any] = {"value": float("nan"), "frequency": None, "unit": data.unit,
                               "parameter": data.parameter, "format": data.format, "trace": trace, "stat": stat}
        if stat == "AT":
            if len(parts) < 3:
                raise ValueError("Use <target>:AT:<frequency_hz>")
            f = float(parts[2])
            out["value"] = float(np.interp(f, freqs, vals))
            out["frequency"] = f
        elif stat in ("MIN", "MIN_FREQ"):
            i = int(np.argmin(vals))
            out["value"], out["frequency"] = (float(freqs[i]) if stat == "MIN_FREQ" else float(vals[i])), float(freqs[i])
            if stat == "MIN_FREQ":
                out["unit"] = "Hz"
        elif stat in ("MAX", "MAX_FREQ"):
            i = int(np.argmax(vals))
            out["value"], out["frequency"] = (float(freqs[i]) if stat == "MAX_FREQ" else float(vals[i])), float(freqs[i])
            if stat == "MAX_FREQ":
                out["unit"] = "Hz"
        elif stat in ("MEAN", "AVG", "AVERAGE"):
            out["value"] = float(np.mean(vals))
        elif stat in ("PTP", "PEAK_TO_PEAK"):
            out["value"] = float(np.max(vals) - np.min(vals))
        else:
            raise ValueError(f"Unknown statistic '{stat}' (MIN, MAX, MEAN, PTP, MIN_FREQ, MAX_FREQ, AT:<hz>)")
        return out

    async def get_measurements(self, channel: Any = 1) -> Dict[str, Any]:
        trace = int(re.sub(r"\D", "", str(channel)) or 1)
        data = await self.get_trace(trace)
        vals = np.asarray(data.values)
        imin, imax = int(np.argmin(vals)), int(np.argmax(vals))
        return {"parameter": data.parameter, "format": data.format, "unit": data.unit,
                "min": float(vals[imin]), "max": float(vals[imax]), "mean": float(np.mean(vals)),
                "min_frequency": data.frequencies[imin], "max_frequency": data.frequencies[imax],
                "points": int(vals.size)}

    async def get_state(self, channel: int = 1) -> Dict[str, Any]:
        return {
            "model": self.model,
            "sweep": await self.get_sweep(),
            "traces": {tr: dict(cfg) for tr, cfg in self.traces.items()},
            "correction": self.correction,
            "rf_output": self.rf_output,
            "mode": self.mode,
        }

    async def reset(self) -> None:
        self._init_state()

    async def run_self_test(self) -> Optional[bool]:
        await asyncio.sleep(0.05)
        return True

    async def get_error(self) -> Dict[str, Any]:
        if self.error_queue:
            msg = self.error_queue.pop(0)
            return {"code": -1, "message": msg, "raw": f"-1,\"{msg}\""}
        return {"code": 0, "message": "No error", "raw": '0,"No error"'}

    async def clear_errors(self) -> bool:
        self.error_queue.clear()
        return True
