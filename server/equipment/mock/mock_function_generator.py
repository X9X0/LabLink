"""Mock function / arbitrary waveform generator for testing without hardware.

Behaves like a two-channel Rigol DG1000Z-class generator driven through the
``rigol_function_generator`` driver: same command names, same
``FunctionGeneratorData`` readings, same channel naming for the acquisition
engine.  State is deterministic; the frequency counter reading can be set
with ``set_simulated_counter``.
"""

import asyncio
import logging
import math
import uuid
from typing import Any, Dict, List, Optional, Sequence, Union

from shared.models.data import FunctionGeneratorData
from shared.models.equipment import (ConnectionType, EquipmentInfo,
                                     EquipmentStatus, EquipmentType)

logger = logging.getLogger(__name__)

_WAVEFORM_ALIASES = {
    "SIN": "SIN", "SINE": "SIN", "SINUSOID": "SIN",
    "SQU": "SQU", "SQUARE": "SQU",
    "RAMP": "RAMP", "TRI": "RAMP", "TRIANGLE": "RAMP",
    "PULS": "PULS", "PULSE": "PULS",
    "NOIS": "NOIS", "NOISE": "NOIS",
    "DC": "DC",
    "ARB": "ARB", "USER": "ARB", "ARBITRARY": "ARB",
    "HARM": "HARM", "HARMONIC": "HARM",
}
_MAX_FREQUENCY = {"SIN": 60e6, "SQU": 25e6, "RAMP": 1e6, "PULS": 25e6, "ARB": 20e6,
                  "HARM": 20e6, "NOIS": 60e6, "DC": 60e6}
_AMPLITUDE_TIERS_50 = [(10e6, 10.0), (30e6, 5.0), (60e6, 2.5)]
_MIN_VPP = 2e-3
_MODULATION_TYPES = ("AM", "FM", "PM", "ASK", "FSK", "PSK", "PWM")
_SWEEP_SPACINGS = {"LIN": "LIN", "LINEAR": "LIN", "LOG": "LOG", "LOGARITHMIC": "LOG",
                   "STE": "STE", "STEP": "STE"}
_BURST_MODES = {"TRIG": "TRIG", "TRIGGERED": "TRIG", "NCYC": "TRIG", "NCYCLE": "TRIG",
                "INF": "INF", "INFINITY": "INF", "INFINITE": "INF",
                "GAT": "GAT", "GATE": "GAT", "GATED": "GAT"}


def _norm_waveform(waveform: str) -> str:
    key = str(waveform).strip().upper()
    if key not in _WAVEFORM_ALIASES:
        raise ValueError(f"Unknown waveform '{waveform}'")
    return _WAVEFORM_ALIASES[key]


def _default_channel_state() -> Dict[str, Any]:
    return {
        "waveform": "SIN",
        "frequency": 1000.0,
        "amplitude": 5.0,
        "unit": "VPP",
        "offset": 0.0,
        "phase": 0.0,
        "square_duty": 50.0,
        "pulse_duty": 50.0,
        "pulse_width": 500e-6,
        "pulse_rise": 20e-9,
        "pulse_fall": 20e-9,
        "symmetry": 50.0,
        "output": False,
        "load": "50",
        "polarity": "NORMAL",
        "modulation": {"enabled": False, "type": "AM", "depth": 100.0, "deviation": 1000.0,
                       "frequency": 100.0, "source": "INTERNAL", "shape": "SIN"},
        "sweep": {"enabled": False, "start": 100.0, "stop": 1000.0, "time": 1.0, "spacing": "LIN"},
        "burst": {"enabled": False, "mode": "TRIG", "cycles": 1, "period": 0.01, "phase": 0.0},
        "arb_points": [],
        "arb_sample_rate": None,
    }


class MockFunctionGenerator:
    """Mock two-channel function/arbitrary waveform generator."""

    CHANNELS = 2

    def __init__(self, resource_manager=None, resource_string: str = "MOCK::FGEN::0"):
        self.resource_string = resource_string
        self.connected = False
        self.cached_info: Optional[EquipmentInfo] = None

        self.manufacturer = "Mock Instruments"
        self.model = "MockFGEN-1062Z"
        self.serial_number = f"MOCK{uuid.uuid4().hex[:8].upper()}"
        self.firmware_version = "v1.0.0-mock"

        self.channels: Dict[int, Dict[str, Any]] = {
            ch: _default_channel_state() for ch in range(1, self.CHANNELS + 1)
        }
        # Frequency counter simulation.
        self.counter_enabled = False
        self.simulated_counter_frequency = 1000.0
        self.simulated_counter_duty = 50.0
        self.beeper = True
        self.error_queue: List[str] = []
        self.phase_sync_count = 0
        self.burst_trigger_count = 0

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def connect(self):
        await asyncio.sleep(0.05)
        self.connected = True
        self.cached_info = await self.get_info()
        logger.info(f"Connected to mock function generator: {self.model}")

    async def disconnect(self):
        await asyncio.sleep(0.02)
        self.connected = False
        logger.info("Disconnected from mock function generator")

    def _require_connected(self):
        if not self.connected:
            raise RuntimeError("Mock function generator not connected")

    async def get_info(self) -> EquipmentInfo:
        from ..base import generate_equipment_id

        return EquipmentInfo(
            id=generate_equipment_id(self.resource_string, "fgen_"),
            type=EquipmentType.FUNCTION_GENERATOR,
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
                "channels": self.CHANNELS,
                "waveforms": ["SIN", "SQU", "RAMP", "PULS", "NOIS", "DC", "ARB", "HARM"],
                "max_frequency": dict(_MAX_FREQUENCY),
                "min_frequency": 1e-6,
                "max_amplitude_vpp_50ohm": 10.0,
                "max_amplitude_vpp_highz": 20.0,
                "amplitude_tiers_50ohm": [list(t) for t in _AMPLITUDE_TIERS_50],
                "amplitude_tiers_highz": [[f, v * 2] for f, v in _AMPLITUDE_TIERS_50],
                "min_amplitude_vpp_50ohm": _MIN_VPP,
                "sample_rate": 200e6,
                "arb_points": 8_000_000,
                "arb_upload_format": "FLOAT",
                "has_counter": True,
                "noise_bandwidth": 60e6,
                "amplitude_units": ["VPP", "VRMS", "DBM"],
                "modulation_types": list(_MODULATION_TYPES),
                "sweep_spacings": ["LINear", "LOGarithmic", "STEp"],
                "burst_modes": ["TRIGgered", "INFinity", "GATed"],
                "interfaces": ["MOCK"],
                "outputs": {ch: st["output"] for ch, st in self.channels.items()},
                "supports_acquisition": True,
                "supports_arbitrary_upload": True,
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
        self._require_connected()
        parameters = dict(parameters or {})
        handlers = {
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
            "set_output": self.set_output,
            "get_output": self.get_output,
            "set_load": self.set_load,
            "get_load": self.get_load,
            "set_polarity": self.set_polarity,
            "get_polarity": self.get_polarity,
            "set_modulation": self.set_modulation,
            "get_modulation": self.get_modulation,
            "set_sweep": self.set_sweep,
            "get_sweep": self.get_sweep,
            "set_burst": self.set_burst,
            "get_burst": self.get_burst,
            "trigger_burst": self.trigger_burst,
            "upload_arbitrary": self.upload_arbitrary,
            "set_arb_sample_rate": self.set_arb_sample_rate,
            "sync_phase": self.sync_phase,
            "get_counter": self.get_counter,
            "set_counter": self.set_counter,
            "get_readings": self.get_readings,
            "get_measurement": self.get_measurement,
            "get_measurements": self.get_measurements,
            "get_state": self.get_state,
            "set_beeper": self.set_beeper,
            "beep": self.beep,
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
    # Simulation controls (test helpers)
    # ------------------------------------------------------------------ #

    def set_simulated_counter(self, frequency: float, duty_cycle: float = 50.0):
        """Set the signal the mock's frequency counter 'sees'."""
        self.simulated_counter_frequency = float(frequency)
        self.simulated_counter_duty = float(duty_cycle)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _ch(self, channel: Any) -> Dict[str, Any]:
        self._require_connected()
        if isinstance(channel, str):
            text = channel.strip().upper()
            if text.startswith("CH"):
                text = text[2:]
            try:
                ch = int(text)
            except ValueError:
                raise ValueError(f"Invalid channel '{channel}'")
        else:
            ch = int(channel)
        if ch not in self.channels:
            raise ValueError(f"Channel must be 1..{self.CHANNELS}")
        return self.channels[ch]

    @staticmethod
    def _channel_number(channel: Any) -> int:
        if isinstance(channel, str):
            text = channel.strip().upper()
            return int(text[2:] if text.startswith("CH") else text)
        return int(channel)

    @staticmethod
    def _check_frequency(waveform: str, frequency: float) -> float:
        frequency = float(frequency)
        limit = _MAX_FREQUENCY.get(waveform, 60e6)
        if not 1e-6 <= frequency <= limit:
            raise ValueError(f"Frequency {frequency:g} Hz out of range for {waveform}: 1e-06..{limit:g} Hz")
        return frequency

    @staticmethod
    def _max_vpp(frequency: Optional[float], high_z: bool) -> float:
        for bound, vpp in _AMPLITUDE_TIERS_50:
            if frequency is None or frequency <= bound:
                return vpp * (2 if high_z else 1)
        return _AMPLITUDE_TIERS_50[-1][1] * (2 if high_z else 1)

    def _check_amplitude(self, state: Dict[str, Any], amplitude: float, frequency: Optional[float]) -> float:
        amplitude = float(amplitude)
        if state["unit"] != "VPP":
            if state["unit"] == "VRMS" and amplitude <= 0:
                raise ValueError("Amplitude in Vrms must be > 0")
            return amplitude
        high_z = state["load"] == "INF"
        max_vpp = self._max_vpp(frequency, high_z)
        min_vpp = _MIN_VPP * (2 if high_z else 1)
        if not min_vpp <= amplitude <= max_vpp:
            raise ValueError(
                f"Amplitude {amplitude:g} Vpp out of range into {'HighZ' if high_z else '50 Ohm'}: "
                f"{min_vpp:g}..{max_vpp:g} Vpp"
            )
        return amplitude

    # ------------------------------------------------------------------ #
    # Waveform / basic parameters
    # ------------------------------------------------------------------ #

    async def apply(
        self,
        channel: Any = 1,
        waveform: str = "SIN",
        frequency: Optional[float] = None,
        amplitude: Optional[float] = None,
        offset: Optional[float] = None,
        phase: Optional[float] = None,
    ) -> FunctionGeneratorData:
        state = self._ch(channel)
        wf = _norm_waveform(waveform)
        if frequency is not None and wf not in ("DC", "NOIS"):
            frequency = self._check_frequency(wf, frequency)
        if amplitude is not None and wf != "DC":
            amplitude = self._check_amplitude(state, amplitude, frequency)
        if phase is not None and not -360.0 <= float(phase) <= 360.0:
            raise ValueError("Phase must be -360..360 degrees")
        state["waveform"] = wf
        if frequency is not None:
            state["frequency"] = frequency
        if amplitude is not None:
            state["amplitude"] = amplitude
        if offset is not None:
            state["offset"] = float(offset)
        if phase is not None:
            state["phase"] = float(phase)
        # Modulation / sweep / burst are cleared by :APPLy on the real instrument.
        state["modulation"]["enabled"] = False
        state["sweep"]["enabled"] = False
        state["burst"]["enabled"] = False
        await asyncio.sleep(0.005)
        return await self.get_readings(channel)

    async def set_waveform(self, waveform: str, channel: Any = 1) -> str:
        state = self._ch(channel)
        wf = _norm_waveform(waveform)
        state["waveform"] = wf
        limit = _MAX_FREQUENCY.get(wf, 60e6)
        if state["frequency"] > limit:
            state["frequency"] = limit
        return wf

    async def get_waveform(self, channel: Any = 1) -> str:
        return self._ch(channel)["waveform"]

    async def set_frequency(self, frequency: float, channel: Any = 1) -> float:
        state = self._ch(channel)
        state["frequency"] = self._check_frequency(state["waveform"], frequency)
        return state["frequency"]

    async def get_frequency(self, channel: Any = 1) -> float:
        return self._ch(channel)["frequency"]

    async def set_amplitude(self, amplitude: float, unit: Optional[str] = None, channel: Any = 1) -> float:
        state = self._ch(channel)
        if unit is not None:
            await self.set_amplitude_unit(unit, channel)
        state["amplitude"] = self._check_amplitude(state, amplitude, state["frequency"])
        return state["amplitude"]

    async def get_amplitude(self, channel: Any = 1) -> float:
        return self._ch(channel)["amplitude"]

    async def set_amplitude_unit(self, unit: str, channel: Any = 1) -> str:
        state = self._ch(channel)
        key = str(unit).strip().upper()
        if key not in ("VPP", "VRMS", "DBM"):
            raise ValueError("Amplitude unit must be VPP, VRMS or DBM")
        if key == "DBM" and state["load"] == "INF":
            raise ValueError("dBm is not available while the output load is HighZ")
        if key != state["unit"]:
            state["amplitude"] = self._convert_amplitude(state, state["amplitude"], state["unit"], key)
            state["unit"] = key
        return key

    @staticmethod
    def _convert_amplitude(state: Dict[str, Any], value: float, src: str, dst: str) -> float:
        """Sine-based Vpp <-> Vrms <-> dBm (50 Ohm) conversion."""
        factor = 2 * math.sqrt(2) if state["waveform"] in ("SIN", "HARM", "ARB") else 2.0
        if src == "VPP":
            vpp = value
        elif src == "VRMS":
            vpp = value * factor
        else:
            vrms = math.sqrt(50.0 * 10 ** (value / 10) / 1000.0)
            vpp = vrms * factor
        if dst == "VPP":
            return vpp
        vrms = vpp / factor
        if dst == "VRMS":
            return vrms
        return 10 * math.log10(max(vrms, 1e-12) ** 2 / 50.0 * 1000.0)

    async def get_amplitude_unit(self, channel: Any = 1) -> str:
        return self._ch(channel)["unit"]

    async def set_offset(self, offset: float, channel: Any = 1) -> float:
        state = self._ch(channel)
        offset = float(offset)
        limit = self._max_vpp(None, state["load"] == "INF") / 2.0
        if abs(offset) > limit:
            raise ValueError(f"Offset must be within +/-{limit:g} V")
        state["offset"] = offset
        return offset

    async def get_offset(self, channel: Any = 1) -> float:
        return self._ch(channel)["offset"]

    async def set_phase(self, phase: float, channel: Any = 1) -> float:
        state = self._ch(channel)
        phase = float(phase)
        if not -360.0 <= phase <= 360.0:
            raise ValueError("Phase must be -360..360 degrees")
        state["phase"] = phase
        return phase

    async def get_phase(self, channel: Any = 1) -> float:
        return self._ch(channel)["phase"]

    async def set_duty_cycle(self, duty_cycle: float, channel: Any = 1, waveform: Optional[str] = None) -> float:
        state = self._ch(channel)
        duty = float(duty_cycle)
        if not 0.0 <= duty <= 100.0:
            raise ValueError("Duty cycle must be 0..100 %")
        wf = _norm_waveform(waveform) if waveform else state["waveform"]
        if wf == "PULS":
            state["pulse_duty"] = duty
            state["pulse_width"] = duty / 100.0 / state["frequency"]
        elif wf == "SQU":
            state["square_duty"] = duty
        else:
            raise ValueError(f"Duty cycle applies to SQU or PULS, channel is {wf}")
        return duty

    async def get_duty_cycle(self, channel: Any = 1, waveform: Optional[str] = None) -> Optional[float]:
        state = self._ch(channel)
        wf = _norm_waveform(waveform) if waveform else state["waveform"]
        if wf == "PULS":
            return state["pulse_duty"]
        if wf == "SQU":
            return state["square_duty"]
        return None

    async def set_symmetry(self, symmetry: float, channel: Any = 1) -> float:
        state = self._ch(channel)
        symmetry = float(symmetry)
        if not 0.0 <= symmetry <= 100.0:
            raise ValueError("Symmetry must be 0..100 %")
        state["symmetry"] = symmetry
        return symmetry

    async def get_symmetry(self, channel: Any = 1) -> float:
        return self._ch(channel)["symmetry"]

    async def set_pulse(
        self,
        width: Optional[float] = None,
        duty_cycle: Optional[float] = None,
        rise_time: Optional[float] = None,
        fall_time: Optional[float] = None,
        channel: Any = 1,
    ) -> Dict[str, Optional[float]]:
        state = self._ch(channel)
        if width is not None:
            if float(width) <= 0:
                raise ValueError("Pulse width must be > 0 s")
            state["pulse_width"] = float(width)
            state["pulse_duty"] = min(99.999, float(width) * state["frequency"] * 100.0)
        if duty_cycle is not None:
            await self.set_duty_cycle(duty_cycle, channel, "PULS")
        if rise_time is not None:
            if float(rise_time) <= 0:
                raise ValueError("Rise time must be > 0 s")
            state["pulse_rise"] = float(rise_time)
        if fall_time is not None:
            if float(fall_time) <= 0:
                raise ValueError("Fall time must be > 0 s")
            state["pulse_fall"] = float(fall_time)
        return await self.get_pulse(channel)

    async def get_pulse(self, channel: Any = 1) -> Dict[str, Optional[float]]:
        state = self._ch(channel)
        return {"width": state["pulse_width"], "duty_cycle": state["pulse_duty"],
                "rise_time": state["pulse_rise"], "fall_time": state["pulse_fall"]}

    # ------------------------------------------------------------------ #
    # Output
    # ------------------------------------------------------------------ #

    async def set_output(self, enabled: bool, channel: Any = 1) -> bool:
        state = self._ch(channel)
        state["output"] = bool(enabled)
        return state["output"]

    async def get_output(self, channel: Any = 1) -> bool:
        return self._ch(channel)["output"]

    async def set_load(self, impedance: Union[float, int, str], channel: Any = 1) -> str:
        state = self._ch(channel)
        if isinstance(impedance, str):
            key = impedance.strip().upper().replace("OHM", "").strip()
            if key in ("INF", "INFINITY", "HIGHZ", "HIGH_Z", "HIZ", "OPEN"):
                state["load"] = "INF"
                if state["unit"] == "DBM":
                    state["unit"] = "VPP"
                return "INF"
            if key == "MIN":
                impedance = 1
            elif key == "MAX":
                impedance = 10000
            else:
                impedance = float(key)
        ohms = int(round(float(impedance)))
        if not 1 <= ohms <= 10000:
            raise ValueError("Load impedance must be 1..10000 Ohm or INF (HighZ)")
        state["load"] = str(ohms)
        return state["load"]

    async def get_load(self, channel: Any = 1) -> str:
        return self._ch(channel)["load"]

    async def set_polarity(self, polarity: str = "NORMAL", channel: Any = 1) -> str:
        state = self._ch(channel)
        key = str(polarity).strip().upper()
        if key in ("NORM", "NORMAL", "POS", "POSITIVE"):
            state["polarity"] = "NORMAL"
        elif key in ("INV", "INVERTED", "INVERT", "NEG", "NEGATIVE"):
            state["polarity"] = "INVERTED"
        else:
            raise ValueError("Polarity must be NORMAL or INVERTED")
        return state["polarity"]

    async def get_polarity(self, channel: Any = 1) -> str:
        return self._ch(channel)["polarity"]

    # ------------------------------------------------------------------ #
    # Modulation / sweep / burst
    # ------------------------------------------------------------------ #

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
        state = self._ch(channel)
        mtype = str(modulation_type).strip().upper()
        mtype = {"ASKEY": "ASK", "FSKEY": "FSK", "PSKEY": "PSK"}.get(mtype, mtype)
        if mtype not in _MODULATION_TYPES:
            raise ValueError(f"Modulation type must be one of {', '.join(_MODULATION_TYPES)}")
        mod = state["modulation"]
        mod["type"] = mtype
        if depth is not None:
            if mtype != "AM":
                raise ValueError("depth only applies to AM")
            if not 0 <= float(depth) <= 120:
                raise ValueError("AM depth must be 0..120 %")
            mod["depth"] = float(depth)
        if deviation is not None:
            if mtype not in ("FM", "PM", "PWM"):
                raise ValueError("deviation only applies to FM, PM and PWM")
            mod["deviation"] = float(deviation)
        if frequency is not None:
            if float(frequency) <= 0:
                raise ValueError("Modulating frequency must be > 0 Hz")
            mod["frequency"] = float(frequency)
        if source is not None:
            key = str(source).strip().upper()
            if key not in ("INT", "INTERNAL", "EXT", "EXTERNAL"):
                raise ValueError("Modulation source must be INTERNAL or EXTERNAL")
            mod["source"] = "INTERNAL" if key.startswith("INT") else "EXTERNAL"
        if shape is not None:
            mod["shape"] = _norm_waveform(shape) if str(shape).upper() not in ("TRI", "TRIANGLE", "NRAMP") else str(shape).upper()
        mod["enabled"] = bool(enabled)
        if enabled:
            state["sweep"]["enabled"] = False
            state["burst"]["enabled"] = False
        return await self.get_modulation(channel)

    async def get_modulation(self, channel: Any = 1) -> Dict[str, Any]:
        mod = self._ch(channel)["modulation"]
        out = {"enabled": mod["enabled"], "type": mod["type"], "frequency": mod["frequency"]}
        if mod["type"] == "AM":
            out["depth"] = mod["depth"]
        elif mod["type"] in ("FM", "PM", "PWM"):
            out["deviation"] = mod["deviation"]
        return out

    async def set_sweep(
        self,
        enabled: bool = True,
        start: Optional[float] = None,
        stop: Optional[float] = None,
        time: Optional[float] = None,
        spacing: Optional[str] = None,
        channel: Any = 1,
    ) -> Dict[str, Any]:
        state = self._ch(channel)
        sweep = state["sweep"]
        if start is not None:
            sweep["start"] = self._check_frequency("SIN", start)
        if stop is not None:
            sweep["stop"] = self._check_frequency("SIN", stop)
        if time is not None:
            if float(time) <= 0:
                raise ValueError("Sweep time must be > 0 s")
            sweep["time"] = float(time)
        if spacing is not None:
            key = str(spacing).strip().upper()
            if key not in _SWEEP_SPACINGS:
                raise ValueError("Sweep spacing must be LINEAR, LOG or STEP")
            sweep["spacing"] = _SWEEP_SPACINGS[key]
        sweep["enabled"] = bool(enabled)
        if enabled:
            state["modulation"]["enabled"] = False
            state["burst"]["enabled"] = False
        return dict(sweep)

    async def get_sweep(self, channel: Any = 1) -> Dict[str, Any]:
        return dict(self._ch(channel)["sweep"])

    async def set_burst(
        self,
        enabled: bool = True,
        mode: Optional[str] = None,
        cycles: Optional[int] = None,
        period: Optional[float] = None,
        phase: Optional[float] = None,
        channel: Any = 1,
    ) -> Dict[str, Any]:
        state = self._ch(channel)
        burst = state["burst"]
        if mode is not None:
            key = str(mode).strip().upper()
            if key not in _BURST_MODES:
                raise ValueError("Burst mode must be TRIGGERED (N cycle), INFINITY or GATED")
            burst["mode"] = _BURST_MODES[key]
        if cycles is not None:
            cycles = int(cycles)
            if not 1 <= cycles <= 1_000_000:
                raise ValueError("Burst cycles must be 1..1000000")
            burst["cycles"] = cycles
        if period is not None:
            if float(period) <= 0:
                raise ValueError("Burst period must be > 0 s")
            burst["period"] = float(period)
        if phase is not None:
            if not -360.0 <= float(phase) <= 360.0:
                raise ValueError("Phase must be -360..360 degrees")
            burst["phase"] = float(phase)
        burst["enabled"] = bool(enabled)
        if enabled:
            state["modulation"]["enabled"] = False
            state["sweep"]["enabled"] = False
        return dict(burst)

    async def get_burst(self, channel: Any = 1) -> Dict[str, Any]:
        return dict(self._ch(channel)["burst"])

    async def trigger_burst(self, channel: Any = 1) -> None:
        self._ch(channel)
        self.burst_trigger_count += 1

    # ------------------------------------------------------------------ #
    # Arbitrary / phase / counter
    # ------------------------------------------------------------------ #

    async def upload_arbitrary(
        self, points: Sequence[float], channel: Any = 1, name: Optional[str] = None
    ) -> Dict[str, Any]:
        state = self._ch(channel)
        values = []
        for p in points:
            v = float(p)
            if math.isnan(v) or math.isinf(v):
                raise ValueError("Arbitrary waveform points must be finite")
            values.append(max(-1.0, min(1.0, v)))
        if len(values) < 8:
            raise ValueError("At least 8 points are required")
        if len(values) > 16384:
            raise ValueError("At most 16384 points per upload")
        state["arb_points"] = values
        state["waveform"] = "ARB"
        return {"channel": self._channel_number(channel), "points": len(values), "format": "FLOAT",
                "packets": 1, "name": name or "VOLATILE"}

    async def set_arb_sample_rate(self, sample_rate: float, channel: Any = 1) -> float:
        state = self._ch(channel)
        sample_rate = float(sample_rate)
        if not 0 < sample_rate <= 200e6:
            raise ValueError("Sample rate must be 0..2e+08 Sa/s")
        state["arb_sample_rate"] = sample_rate
        return sample_rate

    async def sync_phase(self, channel: Any = 1) -> None:
        state = self._ch(channel)
        if any(st["modulation"]["enabled"] for st in self.channels.values()):
            raise ValueError("Align phase is invalid while modulation is enabled")
        self.phase_sync_count += 1
        for st in self.channels.values():
            st["phase"] = state["phase"] if st is state else st["phase"]

    async def set_counter(self, enabled: bool = True) -> bool:
        self._require_connected()
        self.counter_enabled = bool(enabled)
        return self.counter_enabled

    async def get_counter(self) -> Dict[str, Any]:
        self._require_connected()
        nan = float("nan")
        if not self.counter_enabled:
            return {"enabled": False, "frequency": nan, "period": nan, "duty_cycle": nan,
                    "positive_width": nan, "negative_width": nan, "unit": "Hz"}
        f = self.simulated_counter_frequency
        period = 1.0 / f if f else nan
        duty = self.simulated_counter_duty
        return {
            "enabled": True,
            "frequency": f,
            "period": period,
            "duty_cycle": duty,
            "positive_width": period * duty / 100.0,
            "negative_width": period * (1 - duty / 100.0),
            "unit": "Hz",
        }

    # ------------------------------------------------------------------ #
    # Readings / hooks
    # ------------------------------------------------------------------ #

    async def get_readings(self, channel: Any = 1) -> FunctionGeneratorData:
        state = self._ch(channel)
        ch = self._channel_number(channel)
        await asyncio.sleep(0.002)
        wf = state["waveform"]
        return FunctionGeneratorData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            channel=ch,
            waveform=wf,
            frequency=None if wf in ("DC", "NOIS") else state["frequency"],
            amplitude=None if wf == "DC" else state["amplitude"],
            amplitude_unit=state["unit"],
            offset=state["offset"],
            phase=None if wf in ("DC", "NOIS") else state["phase"],
            duty_cycle=state["square_duty"] if wf == "SQU" else state["pulse_duty"] if wf == "PULS" else None,
            symmetry=state["symmetry"] if wf == "RAMP" else None,
            output_enabled=state["output"],
            load_impedance=state["load"],
            modulation=state["modulation"]["type"] if state["modulation"]["enabled"] else None,
            sweep_enabled=state["sweep"]["enabled"],
            burst_enabled=state["burst"]["enabled"],
        )

    async def get_measurement(self, channel: str = "CH1:FREQ") -> Dict[str, Any]:
        self._require_connected()
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
            return {"value": counter[name], "unit": unit, "quantity": f"COUNTER:{name.upper()}",
                    "enabled": counter["enabled"]}
        ch_part, _, what = key.partition(":")
        state = self._ch(ch_part or "1")
        ch = self._channel_number(ch_part or "1")
        what = what or "FREQ"
        if what in ("FREQ", "FREQUENCY", "F"):
            value, unit, quantity = state["frequency"], "Hz", "FREQ"
        elif what in ("AMPL", "AMP", "AMPLITUDE", "VPP", "V"):
            value, unit, quantity = state["amplitude"], state["unit"], "AMPL"
        elif what in ("OFFS", "OFFSET", "DC"):
            value, unit, quantity = state["offset"], "V", "OFFS"
        elif what in ("PHASE", "PHAS"):
            value, unit, quantity = state["phase"], "deg", "PHASE"
        elif what in ("OUTPUT", "OUTP", "ON"):
            value, unit, quantity = (1.0 if state["output"] else 0.0), "", "OUTPUT"
        else:
            raise ValueError(f"Unknown measurement '{channel}'")
        return {"value": value if value is not None else nan, "unit": unit, "channel": ch, "quantity": quantity}

    async def get_measurements(self, channel: Any = 1) -> Dict[str, Any]:
        data = await self.get_readings(channel)
        nan = float("nan")
        counter = await self.get_counter()
        return {
            "waveform": data.waveform,
            "frequency": data.frequency if data.frequency is not None else nan,
            "amplitude": data.amplitude if data.amplitude is not None else nan,
            "amplitude_unit": data.amplitude_unit,
            "offset": data.offset if data.offset is not None else nan,
            "phase": data.phase if data.phase is not None else nan,
            "output_enabled": data.output_enabled,
            "counter_frequency": counter["frequency"],
        }

    async def get_state(self) -> Dict[str, Any]:
        self._require_connected()
        state: Dict[str, Any] = {"model": self.model, "channels": {}}
        for ch, st in self.channels.items():
            state["channels"][ch] = {
                "waveform": st["waveform"],
                "frequency": st["frequency"],
                "amplitude": st["amplitude"],
                "offset": st["offset"],
                "phase": st["phase"],
                "output": st["output"],
                "load": st["load"],
                "unit": st["unit"],
                "modulation": await self.get_modulation(ch),
                "sweep": dict(st["sweep"]),
                "burst": dict(st["burst"]),
            }
        return state

    # ------------------------------------------------------------------ #
    # System
    # ------------------------------------------------------------------ #

    async def set_beeper(self, enabled: bool) -> bool:
        self._require_connected()
        self.beeper = bool(enabled)
        return self.beeper

    async def beep(self) -> None:
        self._require_connected()

    async def reset(self) -> None:
        self._require_connected()
        for ch in self.channels:
            self.channels[ch] = _default_channel_state()
        self.counter_enabled = False
        self.error_queue.clear()

    async def run_self_test(self) -> Optional[bool]:
        await asyncio.sleep(0.02)
        return True

    async def get_error(self) -> Dict[str, Any]:
        if self.error_queue:
            msg = self.error_queue.pop(0)
            return {"code": -1, "message": msg, "raw": f'-1,"{msg}"'}
        return {"code": 0, "message": "No error", "raw": '0,"No error"'}

    async def clear_errors(self) -> bool:
        self.error_queue.clear()
        return True
