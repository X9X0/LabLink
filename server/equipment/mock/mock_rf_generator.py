"""Mock RF signal generator for testing without hardware.

Behaves like a Rigol DSG830 driven through ``rigol_rf_generator.py``: same
command names, same :class:`RFGeneratorData` readings, same channel naming
for the acquisition engine. All state is kept locally; ``set_simulated_*``
hooks let tests inject an unlock/error condition.
"""

import asyncio
import logging
import math
import uuid
from typing import Any, Dict, List, Optional

from shared.models.data import RFGeneratorData
from shared.models.equipment import (ConnectionType, EquipmentInfo,
                                     EquipmentStatus, EquipmentType)

logger = logging.getLogger(__name__)

_MOD_TYPES = ("AM", "FM", "PM", "PULSE", "IQ")
_MOD_ALIASES = {
    "AM": "AM", "FM": "FM", "PM": "PM", "PHM": "PM", "PHASE": "PM",
    "PULSE": "PULSE", "PULM": "PULSE", "PUL": "PULSE", "IQ": "IQ", "I/Q": "IQ",
}
_UNIT_DISPLAY = {"DBM": "dBm", "DBMV": "dBmV", "DBUV": "dBuV", "V": "V", "W": "W"}
_SWEEP_STATES = {
    "OFF": "OFF", "NONE": "OFF", "FREQ": "FREQ", "FREQUENCY": "FREQ",
    "LEVEL": "LEV", "LEV": "LEV", "POWER": "LEV",
    "BOTH": "LEV,FREQ", "LEVEL,FREQUENCY": "LEV,FREQ", "LEV,FREQ": "LEV,FREQ",
}


def _to_dbm(level: float, unit: str) -> float:
    u = unit.upper()
    if u == "DBM":
        return level
    if u == "DBMV":
        return level - 46.99
    if u == "DBUV":
        return level - 106.99
    if u == "V":
        if level <= 0:
            raise ValueError("Voltage level must be > 0 V")
        return 10 * math.log10(level * level / 50.0 / 1e-3)
    if u == "W":
        if level <= 0:
            raise ValueError("Power level must be > 0 W")
        return 10 * math.log10(level / 1e-3)
    raise ValueError("Level unit must be dBm, dBmV, dBuV, V or W")


class MockRFGenerator:
    """Mock single-channel RF signal generator (DSG830-like, 9 kHz..3 GHz)."""

    FREQ_MIN = 9e3
    FREQ_MAX = 3e9
    LEVEL_MIN = -110.0
    LEVEL_MAX = 20.0

    def __init__(self, resource_manager=None, resource_string: str = "MOCK::RFGEN::0"):
        self.resource_string = resource_string
        self.connected = False
        self.cached_info: Optional[EquipmentInfo] = None

        self.manufacturer = "Mock Instruments"
        self.model = "MockRFGEN-830"
        self.serial_number = f"MOCK{uuid.uuid4().hex[:8].upper()}"
        self.firmware_version = "v1.0.0-mock"
        self.channels = 1

        self._init_state()

    def _init_state(self):
        self.frequency = 3e9
        self.frequency_step = 100e6
        self.level = -110.0  # dBm
        self.level_step = 10.0
        self.level_unit = "DBM"
        self.output_enabled = False
        self.alc_mode = "AUTO"
        self.modulation_master = False
        self.modulations: Dict[str, Dict[str, Any]] = {
            "AM": {"enabled": False, "depth": 50.0, "frequency": 10e3, "source": "INT", "waveform": "SINE"},
            "FM": {"enabled": False, "deviation": 10e3, "frequency": 10e3, "source": "INT", "waveform": "SINE"},
            "PM": {"enabled": False, "deviation": 1.0, "frequency": 10e3, "source": "INT", "waveform": "SINE"},
            "PULSE": {"enabled": False, "period": 1e-3, "width": 500e-6, "source": "INT",
                      "polarity": "NORMAL", "mode": "SINGLE"},
            "IQ": {"enabled": False, "source": "INT"},
        }
        self.lf_output = {"enabled": False, "frequency": 1e3, "level": 1.0, "shape": "SINE"}
        self.sweep = {
            "state": "OFF", "type": "STEP", "mode": "CONT", "direction": "FWD",
            "start_frequency": 100e6, "stop_frequency": 1e9, "start_level": -20.0, "stop_level": 0.0,
            "points": 91, "dwell": 0.1, "spacing": "LIN", "shape": "RAMP",
        }
        self.sweeps_executed = 0
        self.triggers: List[str] = []
        self.error_queue: List[str] = []
        self.unlocked = False

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def connect(self):
        await asyncio.sleep(0.05)
        self.connected = True
        self.cached_info = await self.get_info()
        logger.info(f"Connected to mock RF generator: {self.model}")

    async def disconnect(self):
        await asyncio.sleep(0.02)
        self.connected = False
        logger.info("Disconnected from mock RF generator")

    async def get_info(self) -> EquipmentInfo:
        from ..base import generate_equipment_id

        return EquipmentInfo(
            id=generate_equipment_id(self.resource_string, "rfgen_"),
            type=EquipmentType.RF_SIGNAL_GENERATOR,
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
                "channels": self.channels,
                "frequency_min": self.FREQ_MIN,
                "frequency_max": self.FREQ_MAX,
                "level_min_dbm": self.LEVEL_MIN,
                "level_max_dbm": self.LEVEL_MAX,
                "has_iq": True,
                "has_pulse": True,
                "has_alc_control": True,
                "modulation_types": list(_MOD_TYPES),
                "level_units": ["dBm", "dBmV", "dBuV", "V", "W"],
                "sweep_types": ["STEP", "LIST"],
                "interfaces": ["MOCK"],
                "measurement_channels": ["FREQ", "LEVEL", "OUTPUT"],
                "output_enabled": self.output_enabled,
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
            raise RuntimeError("Mock RF generator not connected")
        parameters = dict(parameters or {})
        handlers = {
            "set_frequency": self.set_frequency,
            "get_frequency": self.get_frequency,
            "set_frequency_step": self.set_frequency_step,
            "set_level": self.set_level,
            "get_level": self.get_level,
            "set_level_step": self.set_level_step,
            "set_level_unit": self.set_level_unit,
            "get_level_unit": self.get_level_unit,
            "set_output": self.set_output,
            "get_output": self.get_output,
            "set_all_outputs": self.set_all_outputs,
            "set_alc": self.set_alc,
            "get_alc": self.get_alc,
            "set_modulation": self.set_modulation,
            "get_modulation": self.get_modulation,
            "set_modulation_master": self.set_modulation_master,
            "get_modulation_master": self.get_modulation_master,
            "set_lf_output": self.set_lf_output,
            "set_sweep": self.set_sweep,
            "get_sweep": self.get_sweep,
            "execute_sweep": self.execute_sweep,
            "trigger": self.trigger,
            "get_readings": self.get_readings,
            "get_measurement": self.get_measurement,
            "get_measurements": self.get_measurements,
            "get_state": self.get_state,
            "reset": self.reset,
            "preset": self.preset,
            "get_error": self.get_error,
            "clear_errors": self.clear_errors,
            "get_options": self.get_options,
        }
        handler = handlers.get(command)
        if handler is None:
            raise ValueError(f"Unknown command: {command}")
        return await handler(**parameters)

    # ------------------------------------------------------------------ #
    # Simulation controls (test helpers)
    # ------------------------------------------------------------------ #

    def set_simulated_error(self, message: str):
        """Queue an error message returned by the next get_error()."""
        self.error_queue.append(message)

    def set_simulated_unlock(self, unlocked: bool = True):
        """Simulate a reference/PLL unlock; readings still work."""
        self.unlocked = bool(unlocked)

    # ------------------------------------------------------------------ #
    # Frequency / level / output
    # ------------------------------------------------------------------ #

    def _check_channel(self, channel) -> int:
        ch = int(channel) if channel is not None else 1
        if not 1 <= ch <= self.channels:
            raise ValueError(f"{self.model} has channels 1..{self.channels}")
        return ch

    async def set_frequency(self, frequency: float, channel: int = 1) -> float:
        self._check_channel(channel)
        frequency = float(frequency)
        if not self.FREQ_MIN <= frequency <= self.FREQ_MAX:
            raise ValueError(
                f"Frequency must be between {self.FREQ_MIN:g} Hz and {self.FREQ_MAX:g} Hz on the {self.model}"
            )
        self.frequency = frequency
        await asyncio.sleep(0.005)
        return self.frequency

    async def get_frequency(self, channel: int = 1) -> float:
        self._check_channel(channel)
        return self.frequency

    async def set_frequency_step(self, step: float, channel: int = 1) -> float:
        if float(step) <= 0:
            raise ValueError("Frequency step must be > 0 Hz")
        self.frequency_step = float(step)
        return self.frequency_step

    async def set_level(self, level: float, unit: str = "dBm", channel: int = 1) -> float:
        self._check_channel(channel)
        key = str(unit).strip().upper()
        if key not in _UNIT_DISPLAY:
            raise ValueError("Level unit must be dBm, dBmV, dBuV, V or W")
        dbm = _to_dbm(float(level), key)
        if not self.LEVEL_MIN - 1e-9 <= dbm <= self.LEVEL_MAX + 1e-9:
            raise ValueError(
                f"Level {level:g} {_UNIT_DISPLAY[key]} ({dbm:.2f} dBm) is outside "
                f"{self.LEVEL_MIN:g}..{self.LEVEL_MAX:g} dBm on the {self.model}"
            )
        self.level = round(dbm, 2)
        return self.level

    async def get_level(self, channel: int = 1) -> float:
        self._check_channel(channel)
        return self.level

    async def set_level_step(self, step_db: float, channel: int = 1) -> float:
        step_db = float(step_db)
        if not 0.01 <= step_db <= 100.0:
            raise ValueError("Level step must be 0.01..100 dB")
        self.level_step = step_db
        return step_db

    async def set_level_unit(self, unit: str = "dBm", channel: int = 1) -> str:
        key = str(unit).strip().upper()
        if key not in _UNIT_DISPLAY:
            raise ValueError("Level unit must be dBm, dBmV, dBuV, V or W")
        self.level_unit = key
        return _UNIT_DISPLAY[key]

    async def get_level_unit(self, channel: int = 1) -> str:
        return _UNIT_DISPLAY[self.level_unit]

    async def set_output(self, enabled: bool, channel: int = 1) -> bool:
        self._check_channel(channel)
        self.output_enabled = bool(enabled)
        await asyncio.sleep(0.005)
        return self.output_enabled

    async def get_output(self, channel: int = 1) -> bool:
        self._check_channel(channel)
        return self.output_enabled

    async def set_all_outputs(self, enabled: bool) -> Dict[int, bool]:
        self.output_enabled = bool(enabled)
        return {1: self.output_enabled}

    async def set_alc(self, enabled: bool = True, mode: Optional[str] = None) -> Optional[str]:
        if mode is not None:
            key = str(mode).strip().upper()
            if key not in ("OFF", "ON", "AUTO"):
                raise ValueError("ALC mode must be OFF, ON or AUTO")
        else:
            key = "ON" if enabled else "OFF"
        self.alc_mode = key
        return key

    async def get_alc(self) -> Optional[str]:
        return self.alc_mode

    # ------------------------------------------------------------------ #
    # Modulation
    # ------------------------------------------------------------------ #

    @staticmethod
    def _mod_type(mod_type: str) -> str:
        key = _MOD_ALIASES.get(str(mod_type).strip().upper())
        if key is None:
            raise ValueError(f"Modulation type must be one of {', '.join(_MOD_TYPES)}")
        return key

    async def set_modulation(
        self, type: str, enabled: bool = True, channel: int = 1, master: Optional[bool] = None, **params
    ) -> Dict[str, Any]:
        self._check_channel(channel)
        key = self._mod_type(type)
        mod = self.modulations[key]
        allowed = {"depth", "deviation", "frequency", "source", "waveform", "period", "width", "polarity", "mode"}
        unknown = set(params) - allowed
        if unknown:
            raise ValueError(f"Unknown modulation parameters: {', '.join(sorted(unknown))}")
        if "source" in params and params["source"] is not None:
            src = str(params["source"]).strip().upper()[:3]
            if src not in ("INT", "EXT"):
                raise ValueError("source must be INT or EXT")
            mod["source"] = src
        if key == "AM" and params.get("depth") is not None:
            depth = float(params["depth"])
            if not 0 <= depth <= 100:
                raise ValueError("AM depth must be 0..100 %")
            mod["depth"] = depth
        if key in ("FM", "PM") and params.get("deviation") is not None:
            dev = float(params["deviation"])
            if dev <= 0:
                raise ValueError("Deviation must be > 0")
            mod["deviation"] = dev
        if key in ("AM", "FM", "PM"):
            if params.get("frequency") is not None:
                mf = float(params["frequency"])
                if mf <= 0:
                    raise ValueError("Modulation frequency must be > 0 Hz")
                mod["frequency"] = mf
            if params.get("waveform") is not None:
                wf = str(params["waveform"]).strip().upper()
                if wf not in ("SINE", "SIN", "SQUARE", "SQU", "SQUA"):
                    raise ValueError("waveform must be SINE or SQUARE")
                mod["waveform"] = "SINE" if wf.startswith("SIN") else "SQUA"
        if key == "PULSE":
            if params.get("period") is not None:
                per = float(params["period"])
                if not 40e-9 <= per <= 170.0:
                    raise ValueError("Pulse period must be 40 ns..170 s")
                mod["period"] = per
            if params.get("width") is not None:
                wid = float(params["width"])
                if not 10e-9 <= wid <= 170.0:
                    raise ValueError("Pulse width must be 10 ns..170 s")
                mod["width"] = wid
            if params.get("polarity") is not None:
                pol = str(params["polarity"]).strip().upper()
                if not (pol.startswith("NORM") or pol.startswith("INV")):
                    raise ValueError("Pulse polarity must be NORMAL or INVERSE")
                mod["polarity"] = "NORMAL" if pol.startswith("NORM") else "INVERSE"
            if params.get("mode") is not None:
                pm = str(params["mode"]).strip().upper()
                if not (pm.startswith("SING") or pm.startswith("TRA")):
                    raise ValueError("Pulse mode must be SINGLE or TRAIN")
                mod["mode"] = "SINGLE" if pm.startswith("SING") else "TRAIN"
        mod["enabled"] = bool(enabled)
        if master is None:
            master = True if enabled else None
        if master is not None:
            self.modulation_master = bool(master)
        return await self.get_modulation(key, channel)

    async def get_modulation(self, type: str, channel: int = 1) -> Dict[str, Any]:
        self._check_channel(channel)
        key = self._mod_type(type)
        out = {"type": key, "channel": 1}
        out.update(self.modulations[key])
        return out

    async def set_modulation_master(self, enabled: bool, channel: int = 1) -> bool:
        self.modulation_master = bool(enabled)
        return self.modulation_master

    async def get_modulation_master(self, channel: int = 1) -> bool:
        return self.modulation_master

    async def set_lf_output(self, enabled: bool = True, frequency=None, level=None, shape=None) -> Dict[str, Any]:
        if frequency is not None:
            if not 0 <= float(frequency) <= 200e3:
                raise ValueError("LF frequency must be 0..200 kHz")
            self.lf_output["frequency"] = float(frequency)
        if level is not None:
            self.lf_output["level"] = float(level)
        if shape is not None:
            self.lf_output["shape"] = "SINE" if str(shape).upper().startswith("SIN") else "SQUA"
        self.lf_output["enabled"] = bool(enabled)
        return dict(self.lf_output)

    # ------------------------------------------------------------------ #
    # Sweep
    # ------------------------------------------------------------------ #

    async def set_sweep(
        self, mode: str = "FREQ", start_frequency=None, stop_frequency=None, start_level=None,
        stop_level=None, points=None, dwell=None, sweep_type=None, spacing=None, shape=None,
        direction=None, continuous=None, channel: int = 1,
    ) -> Dict[str, Any]:
        state = _SWEEP_STATES.get(str(mode).strip().upper())
        if state is None:
            raise ValueError("Sweep mode must be OFF, FREQ, LEVEL or BOTH")
        for name, value in (("start_frequency", start_frequency), ("stop_frequency", stop_frequency)):
            if value is not None:
                if not self.FREQ_MIN <= float(value) <= self.FREQ_MAX:
                    raise ValueError(f"{name} must be {self.FREQ_MIN:g}..{self.FREQ_MAX:g} Hz")
                self.sweep[name] = float(value)
        for name, value in (("start_level", start_level), ("stop_level", stop_level)):
            if value is not None:
                if not self.LEVEL_MIN <= float(value) <= self.LEVEL_MAX:
                    raise ValueError(f"{name} must be {self.LEVEL_MIN:g}..{self.LEVEL_MAX:g} dBm")
                self.sweep[name] = float(value)
        if points is not None:
            if not 2 <= int(points) <= 65535:
                raise ValueError("points must be 2..65535")
            self.sweep["points"] = int(points)
        if dwell is not None:
            if not 0.005 <= float(dwell) <= 100.0:
                raise ValueError("dwell must be 0.005..100 s")
            self.sweep["dwell"] = float(dwell)
        if sweep_type is not None:
            st = str(sweep_type).upper()
            if st not in ("STEP", "LIST"):
                raise ValueError("sweep_type must be STEP or LIST")
            self.sweep["type"] = st
        if spacing is not None:
            self.sweep["spacing"] = "LIN" if str(spacing).upper().startswith("LIN") else "LOG"
        if shape is not None:
            self.sweep["shape"] = "TRI" if str(shape).upper().startswith("TRI") else "RAMP"
        if direction is not None:
            self.sweep["direction"] = "FWD" if str(direction).upper().startswith("F") else "REV"
        if continuous is not None:
            self.sweep["mode"] = "CONT" if continuous else "SING"
        self.sweep["state"] = state
        return await self.get_sweep(channel)

    async def get_sweep(self, channel: int = 1) -> Dict[str, Any]:
        out = {"channel": 1, "enabled": self.sweep["state"] != "OFF"}
        out.update(self.sweep)
        return out

    async def execute_sweep(self, channel: int = 1) -> None:
        self.sweeps_executed += 1
        if self.sweep["mode"] == "CONT":
            self.sweep["mode"] = "SING"

    async def trigger(self, what: str = "SWEEP", channel: int = 1) -> None:
        key = str(what).strip().upper()
        if key not in ("SWEEP", "SWE", "PULSE", "PULM", "PUL", "IQ", "ALL", "*TRG", "ANY"):
            raise ValueError("trigger target must be SWEEP, PULSE, IQ or ALL")
        self.triggers.append(key)

    # ------------------------------------------------------------------ #
    # Readings / hooks
    # ------------------------------------------------------------------ #

    def _active_modulation(self) -> Dict[str, Any]:
        if not self.modulation_master:
            return {}
        for key in _MOD_TYPES:
            if self.modulations[key]["enabled"]:
                return {"type": key, **self.modulations[key]}
        return {}

    async def get_readings(self, channel: int = 1) -> RFGeneratorData:
        self._check_channel(channel)
        mod = self._active_modulation()
        params = {
            k: float(v) for k, v in mod.items()
            if k in ("depth", "deviation", "frequency", "period", "width") and isinstance(v, (int, float))
        }
        return RFGeneratorData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            frequency=self.frequency,
            level=self.level,
            level_unit="dBm",
            output_enabled=self.output_enabled,
            modulation_enabled=bool(mod),
            modulation_type=mod.get("type") if mod else None,
            modulation_parameters=params,
            alc_enabled=self.alc_mode != "OFF",
        )

    async def get_measurement(self, channel: str = "LEVEL") -> Dict[str, Any]:
        key = (channel or "LEVEL").strip().upper()
        if ":" in key:
            _, _, key = key.partition(":")
        elif key in ("CH1", "1"):
            key = "LEVEL"
        if key in ("", "LEVEL", "LEV", "POWER", "POW", "AMPLITUDE", "AMPL"):
            return {"value": self.level, "unit": "dBm", "quantity": "level", "channel": 1}
        if key in ("FREQ", "FREQUENCY", "CW"):
            return {"value": self.frequency, "unit": "Hz", "quantity": "frequency", "channel": 1}
        if key in ("OUTPUT", "OUTP", "RF"):
            return {"value": 1.0 if self.output_enabled else 0.0, "unit": "", "quantity": "output", "channel": 1}
        raise ValueError("Channel must be FREQ, LEVEL or OUTPUT (optionally CH<n>:FREQ)")

    async def get_measurements(self, channel: Any = 1) -> Dict[str, Any]:
        return {
            "frequency": self.frequency,
            "frequency_unit": "Hz",
            "level": self.level,
            "level_unit": "dBm",
            "output_enabled": self.output_enabled,
        }

    async def get_state(self, channel: int = 1) -> Dict[str, Any]:
        return {
            "model": self.model,
            "channel": 1,
            "frequency": self.frequency,
            "level": self.level,
            "level_unit": _UNIT_DISPLAY[self.level_unit],
            "output_enabled": self.output_enabled,
            "modulation_enabled": self.modulation_master,
            "alc": self.alc_mode,
            "modulations": {k: {"type": k, "channel": 1, **v} for k, v in self.modulations.items()},
            "sweep": await self.get_sweep(),
        }

    # ------------------------------------------------------------------ #
    # System
    # ------------------------------------------------------------------ #

    async def preset(self) -> None:
        self._init_state()

    async def reset(self) -> None:
        self._init_state()

    async def get_error(self) -> Dict[str, Any]:
        if self.error_queue:
            msg = self.error_queue.pop(0)
            return {"code": -1, "message": msg, "raw": f'-1,"{msg}"'}
        return {"code": 0, "message": "No error", "raw": '0,"No error"'}

    async def clear_errors(self) -> bool:
        self.error_queue.clear()
        return True

    async def get_options(self) -> Optional[str]:
        return "IQ,PUM,PUG"
