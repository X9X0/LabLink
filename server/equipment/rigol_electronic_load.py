"""Rigol DL3000 series DC electronic load drivers.

Protocol reference: RIGOL "DL3000 Programming Guide" (the text takes the
DL3031A as its example; the command tree is identical across the family)
and the "DL3000 Data Sheet" for the per-model ratings:

=========  ========  ========  =======  ==========  ==========  ============
Model      Voltage   Current   Power    CC ranges   CV ranges   CR ranges
=========  ========  ========  =======  ==========  ==========  ============
DL3021     150 V     40 A      200 W    4 A / 40 A  15 / 150 V  15 / 15k Ohm
DL3021A    150 V     40 A      200 W    4 A / 40 A  15 / 150 V  15 / 15k Ohm
DL3031     150 V     60 A      350 W    6 A / 60 A  15 / 150 V  15 / 15k Ohm
DL3031A    150 V     60 A      350 W    6 A / 60 A  15 / 150 V  15 / 15k Ohm
DL3041     200 V     70 A      450 W    7 A / 70 A  25 / 200 V  15 / 15k Ohm
=========  ========  ========  =======  ==========  ==========  ============

Sources: DL3000 Programming Guide, "Content Conventions" model table
(DL3021/DL3021A: DC 150 V, 40 A, 200 W; DL3031/DL3031A: DC 150 V, 60 A,
350 W), ``:SOUR:CURR:RANG 60`` / ``:SOUR:VOLT:RANG 150`` /
``:SOUR:RES:RANG 15000`` examples and the List-mode range note
"CC: 0-6 A/0-60 A, CV: 0-15 V/0-150 V, CR: 0-15 Ohm/0-15000 Ohm"; DL3000
Data Sheet "Rated Input", "CC Mode", "CV Mode", "CR Mode" tables (DL3041
row added from the same data sheet). The "A" models differ from the plain
models only in accuracy, dynamic-mode frequency (30 kHz vs 15 kHz) and the
options installed at the factory (LAN, list, battery, OCP/OPP); the SCPI
tree and the ratings are the same.

*IDN? returns ``RIGOL TECHNOLOGIES,<model>,<serial>,<firmware>``.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from shared.models.data import ElectronicLoadData
from shared.models.equipment import (EquipmentInfo, EquipmentStatus,
                                     EquipmentType)

from .base import (BaseEquipment, SetpointRefused,
                    generate_equipment_id)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DL3000ModelSpec:
    """Ratings of one DL3000 model (all from the DL3000 data sheet)."""

    model: str
    max_voltage: float  # V
    max_current: float  # A
    max_power: float  # W
    low_current_range: float  # A, low CC range full scale
    low_voltage_range: float  # V, low CV range full scale
    min_resistance: float = 0.08  # Ohm, low CR range lower limit
    max_resistance: float = 15000.0  # Ohm, high CR range upper limit
    low_resistance_range: float = 15.0  # Ohm, low CR range full scale
    max_dynamic_frequency: float = 15e3  # Hz, continuous transient mode
    lan_standard: bool = False  # LAN fitted at the factory ("A" models)


DL3000_MODELS: Dict[str, DL3000ModelSpec] = {
    "DL3021": DL3000ModelSpec("DL3021", 150.0, 40.0, 200.0, 4.0, 15.0),
    "DL3021A": DL3000ModelSpec(
        "DL3021A", 150.0, 40.0, 200.0, 4.0, 15.0,
        max_dynamic_frequency=30e3, lan_standard=True,
    ),
    "DL3031": DL3000ModelSpec("DL3031", 150.0, 60.0, 350.0, 6.0, 15.0),
    "DL3031A": DL3000ModelSpec(
        "DL3031A", 150.0, 60.0, 350.0, 6.0, 15.0,
        max_dynamic_frequency=30e3, lan_standard=True,
    ),
    "DL3041": DL3000ModelSpec(
        "DL3041", 200.0, 70.0, 450.0, 7.0, 25.0,
        max_dynamic_frequency=30e3, lan_standard=True,
    ),
}

_MODES = ("CC", "CV", "CR", "CP")
# :SOURce:FUNCtion? returns CC/CV/CR/CP; the setting keyword is the long form.
_MODE_TO_FUNCTION = {"CC": "CURRent", "CV": "VOLTage", "CR": "RESistance", "CP": "POWer"}
_FUNCTION_TO_MODE = {
    "CC": "CC", "CURR": "CC", "CURRENT": "CC",
    "CV": "CV", "VOLT": "CV", "VOLTAGE": "CV",
    "CR": "CR", "RES": "CR", "RESISTANCE": "CR",
    "CP": "CP", "POW": "CP", "POWER": "CP",
}
_SETPOINT_QUERIES = {
    "CC": ":SOUR:CURR:LEV:IMM?",
    "CV": ":SOUR:VOLT:LEV:IMM?",
    "CR": ":SOUR:RES:LEV:IMM?",
    "CP": ":SOUR:POW:LEV:IMM?",
}


def lookup_dl3000_model(model: Optional[str]) -> Optional[DL3000ModelSpec]:
    """Return the spec for a model string from *IDN? (case-insensitive)."""
    if not model:
        return None
    key = model.strip().upper()
    if key in DL3000_MODELS:
        return DL3000_MODELS[key]
    # Tolerate suffixes such as "DL3021A-xx".
    for name, spec in DL3000_MODELS.items():
        if key.startswith(name) and (len(key) == len(name) or not key[len(name)].isalnum()):
            return spec
    return None


class RigolDL3000Base(BaseEquipment):
    """Common implementation for the Rigol DL3000 family.

    The concrete rating row is chosen from the model field of ``*IDN?`` at
    connect time; ``MODEL`` is only the default used before identification
    or when the reported model is not in :data:`DL3000_MODELS`.
    """

    MODEL = "DL3021A"

    def __init__(self, resource_manager, resource_string: str):
        super().__init__(resource_manager, resource_string)
        self.manufacturer = "Rigol"
        self.model = self.MODEL
        self.serial_number: Optional[str] = None
        self.firmware_version: Optional[str] = None
        self.spec: DL3000ModelSpec = DL3000_MODELS[self.MODEL]
        self._apply_spec(self.spec)

    # ------------------------------------------------------------------ #
    # Model table
    # ------------------------------------------------------------------ #

    def _apply_spec(self, spec: DL3000ModelSpec) -> None:
        self.spec = spec
        # Kept as plain attributes for backwards compatibility with code
        # (and tests) that read load.max_voltage / max_current / max_power.
        self.max_voltage = spec.max_voltage
        self.max_current = spec.max_current
        self.max_power = spec.max_power
        self.min_resistance = spec.min_resistance
        self.max_resistance = spec.max_resistance

    def _parse_idn(self, idn: str) -> Dict[str, Optional[str]]:
        parts = [p.strip() for p in idn.split(",")]
        info = {
            "manufacturer": parts[0] if len(parts) > 0 and parts[0] else self.manufacturer,
            "model": parts[1] if len(parts) > 1 and parts[1] else self.model,
            "serial": parts[2] if len(parts) > 2 and parts[2] else None,
            "firmware": parts[3] if len(parts) > 3 and parts[3] else None,
        }
        spec = lookup_dl3000_model(info["model"])
        if spec is not None:
            if spec.model != self.spec.model:
                logger.info(f"Identified {info['model']}: using {spec.model} ratings")
            self._apply_spec(spec)
        elif info["model"] != self.model:
            logger.warning(
                f"Unknown DL3000 model '{info['model']}', keeping {self.spec.model} ratings"
            )
        self.model = info["model"] or self.model
        self.serial_number = info["serial"]
        self.firmware_version = info["firmware"]
        return info

    # ------------------------------------------------------------------ #
    # Identity / status
    # ------------------------------------------------------------------ #

    async def get_info(self) -> EquipmentInfo:
        """Identify the load from *IDN? and pick its rating row."""
        idn = await self._query("*IDN?")
        info = self._parse_idn(idn)
        return EquipmentInfo(
            id=generate_equipment_id(self.resource_string, "load_"),
            type=EquipmentType.ELECTRONIC_LOAD,
            manufacturer=info["manufacturer"] or self.manufacturer,
            model=info["model"] or self.model,
            serial_number=info["serial"],
            connection_type=self._determine_connection_type(),
            resource_string=self.resource_string,
        )

    def _capabilities(self) -> Dict[str, Any]:
        s = self.spec
        return {
            "max_voltage": s.max_voltage,
            "max_current": s.max_current,
            "max_power": s.max_power,
            "min_resistance": s.min_resistance,
            "max_resistance": s.max_resistance,
            "current_ranges": [s.low_current_range, s.max_current],
            "voltage_ranges": [s.low_voltage_range, s.max_voltage],
            "resistance_ranges": [s.low_resistance_range, s.max_resistance],
            "max_dynamic_frequency": s.max_dynamic_frequency,
            "modes": list(_MODES),
            "measurement_channels": ["V", "I", "P", "R"],
            "supports_acquisition": True,
        }

    async def get_status(self) -> EquipmentStatus:
        """Report connection state, firmware and the model's ratings."""
        try:
            idn = await self._query("*IDN?")
            info = self._parse_idn(idn)
            return EquipmentStatus(
                id=self.cached_info.id if self.cached_info else "unknown",
                connected=self.connected,
                firmware_version=info["firmware"],
                capabilities=self._capabilities(),
            )
        except Exception as e:
            return EquipmentStatus(
                id=self.cached_info.id if self.cached_info else "unknown",
                connected=False,
                error=str(e),
            )

    # ------------------------------------------------------------------ #
    # Command dispatch
    # ------------------------------------------------------------------ #

    async def execute_command(self, command: str, parameters: dict) -> Any:
        """Dispatch a LabLink command name to the matching driver method."""
        parameters = dict(parameters or {})
        handlers = {
            "set_mode": self.set_mode,
            "get_mode": self.get_mode,
            "set_current": self.set_current,
            "set_voltage": self.set_voltage,
            "set_resistance": self.set_resistance,
            "set_power": self.set_power,
            "get_setpoint": self.get_setpoint,
            "set_input": self.set_input,
            "get_input": self.get_input,
            "set_current_range": self.set_current_range,
            "set_voltage_range": self.set_voltage_range,
            "set_resistance_range": self.set_resistance_range,
            "get_ranges": self.get_ranges,
            "get_readings": self.get_readings,
            "get_measurement": self.get_measurement,
            "get_measurements": self.get_measurements,
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
    # Mode / setpoints
    # ------------------------------------------------------------------ #

    async def set_mode(self, mode: str):
        """Set the static operating mode (CC, CV, CR, CP).

        ``:SOURce:FUNCtion`` is asymmetric on these loads: the query
        answers with the short form, CC/CV/CR/CP, but the setting takes
        the long keyword, CURRent/VOLTage/RESistance/POWer. This sent
        the short form back, which the instrument does not accept -- and
        SCPI faults go to the error queue rather than the response, so
        nothing looked wrong. On the bench: set_mode returned success for
        CV, CR and CP in turn and :SOUR:FUNC? kept answering CC, which
        an operator sees as the mode selector doing nothing at all.

        _MODE_TO_FUNCTION was written for this, with a comment saying so,
        and then never used.
        """
        mode_upper = str(mode).upper()
        if mode_upper not in _MODES:
            raise ValueError("Mode must be CC, CV, CR, or CP")
        await self._write(f":SOUR:FUNC {_MODE_TO_FUNCTION[mode_upper]}")

    async def get_mode(self) -> str:
        """Query the static operating mode (:SOURce:FUNCtion? -> CC/CV/CR/CP)."""
        raw = (await self._query(":SOUR:FUNC?")).strip().upper()
        mode = _FUNCTION_TO_MODE.get(raw)
        if mode is None:
            raise ValueError(f"Unexpected :SOUR:FUNC? response: {raw!r}")
        return mode

    async def set_current(self, current: float):
        """Set the CC-mode current in amps (0 .. model maximum)."""
        current = float(current)
        if current < 0 or current > self.max_current:
            raise SetpointRefused(f"Current must be between 0 and {self.max_current}A")
        await self._write(f":SOUR:CURR:LEV:IMM {current}")

    async def set_voltage(self, voltage: float):
        """Set the CV-mode voltage in volts (0 .. model maximum)."""
        voltage = float(voltage)
        if voltage < 0 or voltage > self.max_voltage:
            raise SetpointRefused(f"Voltage must be between 0 and {self.max_voltage}V")
        await self._write(f":SOUR:VOLT:LEV:IMM {voltage}")

    async def set_resistance(self, resistance: float):
        """Set the CR-mode resistance in ohms (0.08 Ohm .. 15 kOhm)."""
        resistance = float(resistance)
        if resistance <= 0:
            raise SetpointRefused("Resistance must be greater than 0")
        if resistance < self.min_resistance or resistance > self.max_resistance:
            raise SetpointRefused(
                f"Resistance must be between {self.min_resistance} and {self.max_resistance} Ohm"
            )
        await self._write(f":SOUR:RES:LEV:IMM {resistance}")

    async def set_power(self, power: float):
        """Set the CP-mode power in watts (0 .. model maximum)."""
        power = float(power)
        if power < 0 or power > self.max_power:
            raise SetpointRefused(f"Power must be between 0 and {self.max_power}W")
        await self._write(f":SOUR:POW:LEV:IMM {power}")

    async def get_setpoint(self, mode: Optional[str] = None) -> Dict[str, Any]:
        """Return the setpoint of the given (or active) mode."""
        mode_key = str(mode).upper() if mode else await self.get_mode()
        if mode_key not in _SETPOINT_QUERIES:
            raise ValueError("Mode must be CC, CV, CR, or CP")
        raw = await self._query(_SETPOINT_QUERIES[mode_key])
        units = {"CC": "A", "CV": "V", "CR": "Ohm", "CP": "W"}
        return {"mode": mode_key, "setpoint": float(raw), "unit": units[mode_key]}

    async def set_input(self, enabled: bool):
        """Turn the load input on or off (:SOURce:INPut:STATe)."""
        await self._write(f":SOUR:INP:STAT {'ON' if enabled else 'OFF'}")

    async def get_input(self) -> bool:
        raw = (await self._query(":SOUR:INP:STAT?")).strip().upper()
        return raw in ("1", "ON")

    # ------------------------------------------------------------------ #
    # Ranges
    # ------------------------------------------------------------------ #

    def _range_word(self, value, low: float, high: float, what: str) -> str:
        """Turn a range request into the numeric value the load expects."""
        if isinstance(value, str):
            key = value.strip().upper()
            if key in ("MIN", "LOW"):
                return "MIN"
            if key in ("MAX", "HIGH"):
                return "MAX"
            if key == "DEF":
                return "DEF"
            value = float(key)
        value = float(value)
        if value <= low:
            return f"{low:g}"
        if value <= high:
            return f"{high:g}"
        raise ValueError(f"{what} range must be <= {high:g}")

    async def set_current_range(self, current_range) -> float:
        """Select the CC current range (low/high, MIN/MAX, or a value in A)."""
        word = self._range_word(current_range, self.spec.low_current_range, self.spec.max_current, "Current")
        await self._write(f":SOUR:CURR:RANG {word}")
        return float(await self._query(":SOUR:CURR:RANG?"))

    async def set_voltage_range(self, voltage_range) -> float:
        """Select the CV voltage range (low/high, MIN/MAX, or a value in V)."""
        word = self._range_word(voltage_range, self.spec.low_voltage_range, self.spec.max_voltage, "Voltage")
        await self._write(f":SOUR:VOLT:RANG {word}")
        return float(await self._query(":SOUR:VOLT:RANG?"))

    async def set_resistance_range(self, resistance_range) -> float:
        """Select the CR resistance range (low/high, MIN/MAX, or a value in Ohm)."""
        word = self._range_word(
            resistance_range, self.spec.low_resistance_range, self.spec.max_resistance, "Resistance"
        )
        await self._write(f":SOUR:RES:RANG {word}")
        return float(await self._query(":SOUR:RES:RANG?"))

    async def get_ranges(self) -> Dict[str, Optional[float]]:
        out: Dict[str, Optional[float]] = {}
        for key, cmd in (
            ("current_range", ":SOUR:CURR:RANG?"),
            ("voltage_range", ":SOUR:VOLT:RANG?"),
            ("resistance_range", ":SOUR:RES:RANG?"),
        ):
            try:
                out[key] = float(await self._query(cmd))
            except Exception as e:
                logger.debug(f"{key} query failed: {e}")
                out[key] = None
        return out

    # ------------------------------------------------------------------ #
    # Readings
    # ------------------------------------------------------------------ #

    async def get_readings(self) -> ElectronicLoadData:
        """Mode, setpoint, measured V/I/P and input state."""
        raw_mode = (await self._query(":SOUR:FUNC?")).strip().upper()
        mode = _FUNCTION_TO_MODE.get(raw_mode)
        if mode is None:
            setpoint_str = "0"
            mode = "CC"
        else:
            setpoint_str = await self._query(_SETPOINT_QUERIES[mode])
        setpoint = float(setpoint_str)

        voltage = float(await self._query(":MEAS:VOLT?"))
        current = float(await self._query(":MEAS:CURR?"))
        power = float(await self._query(":MEAS:POW?"))

        input_state = (await self._query(":SOUR:INP:STAT?")).strip().upper()
        load_enabled = input_state in ("1", "ON")

        return ElectronicLoadData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            mode=mode,
            setpoint=setpoint,
            voltage=voltage,
            current=current,
            power=power,
            load_enabled=load_enabled,
        )

    _MEASUREMENT_CHANNELS = {
        "V": (":MEAS:VOLT?", "V", "voltage"),
        "VOLT": (":MEAS:VOLT?", "V", "voltage"),
        "VOLTAGE": (":MEAS:VOLT?", "V", "voltage"),
        "I": (":MEAS:CURR?", "A", "current"),
        "CURR": (":MEAS:CURR?", "A", "current"),
        "CURRENT": (":MEAS:CURR?", "A", "current"),
        "P": (":MEAS:POW?", "W", "power"),
        "POW": (":MEAS:POW?", "W", "power"),
        "POWER": (":MEAS:POW?", "W", "power"),
        "R": (":MEAS:RES?", "Ohm", "resistance"),
        "RES": (":MEAS:RES?", "Ohm", "resistance"),
        "RESISTANCE": (":MEAS:RES?", "Ohm", "resistance"),
    }

    async def get_measurement(self, channel: str = "V") -> Dict[str, Any]:
        """Acquisition-engine hook.

        ``channel`` is ``V``, ``I``, ``P`` or ``R`` (also ``VOLT``/``CURR``/
        ``POW``/``RES`` and their long forms, optionally prefixed with
        ``CH1:``). Returns ``{"value": float, "unit": str, "quantity": str}``;
        the value is NaN if the load returns something unparsable.
        """
        key = (channel or "V").strip().upper()
        if ":" in key:
            key = key.rsplit(":", 1)[1]
        if key in ("CH1", "1", ""):
            key = "V"
        entry = self._MEASUREMENT_CHANNELS.get(key)
        if entry is None:
            raise ValueError(
                "Channel must be one of V, I, P, R (or VOLT/CURR/POW/RES), optionally as CH1:V"
            )
        cmd, unit, quantity = entry
        raw = await self._query(cmd)
        try:
            value = float(raw)
        except ValueError:
            value = float("nan")
        return {"value": value, "unit": unit, "quantity": quantity}

    async def get_measurements(self, channel: Any = 1) -> Dict[str, float]:
        """Streaming hook: all measured quantities keyed by name."""
        out: Dict[str, float] = {}
        for name, cmd in (
            ("voltage", ":MEAS:VOLT?"),
            ("current", ":MEAS:CURR?"),
            ("power", ":MEAS:POW?"),
            ("resistance", ":MEAS:RES?"),
        ):
            try:
                out[name] = float(await self._query(cmd))
            except Exception as e:
                logger.debug(f"{name} measurement failed: {e}")
                out[name] = float("nan")
        return out

    # ------------------------------------------------------------------ #
    # State / system
    # ------------------------------------------------------------------ #

    async def get_state(self) -> Dict[str, Any]:
        """Snapshot of settings for the state capture/restore system."""
        state: Dict[str, Any] = {"model": self.spec.model}
        try:
            mode = await self.get_mode()
            state["mode"] = mode
            state["setpoint"] = float(await self._query(_SETPOINT_QUERIES[mode]))
        except Exception as e:
            logger.debug(f"Mode/setpoint query failed: {e}")
            state["mode"] = None
            state["setpoint"] = None
        try:
            state["input_enabled"] = await self.get_input()
        except Exception:
            state["input_enabled"] = None
        state.update(await self.get_ranges())
        return state

    async def reset(self) -> None:
        """*RST: factory defaults, input off, error queue cleared."""
        await self._write("*RST")

    async def get_error(self) -> Dict[str, Any]:
        raw = await self._query(":SYSTem:ERRor?")
        code_str, _, message = raw.partition(",")
        try:
            code = int(float(code_str.strip()))
        except ValueError:
            code = None
        return {"code": code, "message": message.strip().strip('"'), "raw": raw}


class RigolDL3021A(RigolDL3000Base):
    """Rigol DL3021 / DL3021A: 150 V, 40 A, 200 W single-channel load."""

    MODEL = "DL3021A"


class RigolDL3031A(RigolDL3000Base):
    """Rigol DL3031 / DL3031A: 150 V, 60 A, 350 W single-channel load."""

    MODEL = "DL3031A"


# Model keywords used by equipment.manager.find_keyword_driver.
RigolDL3031A.MODEL_KEYWORDS = ('DL3031A', 'DL3031', 'DL3041')
RigolDL3021A.MODEL_KEYWORDS = ('DL3021A', 'DL3021')
