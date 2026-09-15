"""Rigol DM3058 / DM3058E / DM3068 digital multimeter drivers.

Protocol reference: RIGOL "DM3058/DM3058E Programming Guide" (Nov 2021) and
"DM3068 Programming Guide" (CHM). Both meters expose three command sets
selectable with ``CMDSET {RIGOL|AGILENT|FLUKE}``; the RIGOL set is the
power-on default and is the one used here. It is the same tree on both
models, differing only in a few range tables, the rate figures, the unit of
the auto-trigger interval and a handful of DM3068-only SYSTem queries.

Interfaces: USB-TMC (VID 0x1AB1), LAN (VXI-11 / LXI-C), GPIB and RS-232
(default 9600 8N1, ``\\r\\n`` terminated). The DM3058E has USB and RS-232
only.

*IDN? returns ``Rigol Technologies,<model>,<serial>,<firmware>``.
"""

import asyncio
import logging
import math
from typing import Any, Dict, List, Optional, Sequence, Union

from shared.models.data import MultimeterData
from shared.models.equipment import (EquipmentInfo, EquipmentStatus,
                                     EquipmentType, MultimeterFunction)

from .base import BaseEquipment, generate_equipment_id

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Static command tables (RIGOL command set, shared by DM3058 and DM3068)
# --------------------------------------------------------------------------- #

# Canonical function -> command that enables it on the main display.
FUNCTION_CMDS: Dict[str, str] = {
    "DCV": ":FUNCtion:VOLTage:DC",
    "ACV": ":FUNCtion:VOLTage:AC",
    "DCI": ":FUNCtion:CURRent:DC",
    "ACI": ":FUNCtion:CURRent:AC",
    "RES": ":FUNCtion:RESistance",
    "FRES": ":FUNCtion:FRESistance",
    "FREQ": ":FUNCtion:FREQuency",
    "PER": ":FUNCtion:PERiod",
    "CAP": ":FUNCtion:CAPacitance",
    "CONT": ":FUNCtion:CONTinuity",
    "DIODE": ":FUNCtion:DIODe",
}

# Canonical function -> :MEASure sub-tree root (value query is root + "?").
MEASURE_ROOTS: Dict[str, str] = {
    "DCV": ":MEASure:VOLTage:DC",
    "ACV": ":MEASure:VOLTage:AC",
    "DCI": ":MEASure:CURRent:DC",
    "ACI": ":MEASure:CURRent:AC",
    "RES": ":MEASure:RESistance",
    "FRES": ":MEASure:FRESistance",
    "FREQ": ":MEASure:FREQuency",
    "PER": ":MEASure:PERiod",
    "CAP": ":MEASure:CAPacitance",
    "CONT": ":MEASure:CONTinuity",
    "DIODE": ":MEASure:DIODe",
}

# Functions that have a :RATE command.
RATE_CMDS: Dict[str, str] = {
    "DCV": ":RATE:VOLTage:DC",
    "ACV": ":RATE:VOLTage:AC",
    "DCI": ":RATE:CURRent:DC",
    "ACI": ":RATE:CURRent:AC",
    "RES": ":RATE:RESistance",
    "FRES": ":RATE:FRESistance",
}

UNITS: Dict[str, str] = {
    "DCV": "V",
    "ACV": "V",
    "DCI": "A",
    "ACI": "A",
    "RES": "Ohm",
    "FRES": "Ohm",
    "FREQ": "Hz",
    "PER": "s",
    "CAP": "F",
    "CONT": "Ohm",
    "DIODE": "V",
}

# Strings returned by :FUNCtion? / :FUNCtion2? -> canonical function.
_FUNCTION_ALIASES: Dict[str, str] = {
    "DCV": "DCV",
    "ACV": "ACV",
    "DCI": "DCI",
    "ACI": "ACI",
    "2WR": "RES",
    "RESISTANCE": "RES",
    "RES": "RES",
    "4WR": "FRES",
    "FRESISTANCE": "FRES",
    "FRES": "FRES",
    "FREQ": "FREQ",
    "FREQUENCY": "FREQ",
    "PERI": "PER",
    "PERIOD": "PER",
    "PER": "PER",
    "CAP": "CAP",
    "CAPACITANCE": "CAP",
    "CONT": "CONT",
    "CONTINUITY": "CONT",
    "DIODE": "DIODE",
    "SENSOR": "SENSOR",
}

_RATE_ALIASES: Dict[str, str] = {
    "F": "FAST",
    "FAST": "FAST",
    "M": "MEDIUM",
    "MEDIUM": "MEDIUM",
    "S": "SLOW",
    "SLOW": "SLOW",
}

_MATH_FUNCTIONS = {"NONE", "REL", "DB", "DBM", "MIN", "MAX", "AVERAGE", "TOTAL", "PF"}
_TRIGGER_SOURCES = {"AUTO", "SINGLE", "EXT"}
_EXT_TRIGGER_TYPES = {"RISE", "FALL", "HIGH", "LOW"}

# Readings at or beyond this magnitude are treated as overload / invalid.
_OVERLOAD_THRESHOLD = 9.0e37

# Shared range tables (full-scale value in base unit, indexed by vendor range code).
_DCV_RANGES = [0.2, 2.0, 20.0, 200.0, 1000.0]
_ACV_RANGES = [0.2, 2.0, 20.0, 200.0, 750.0]
_DCI_RANGES = [200e-6, 2e-3, 20e-3, 200e-3, 2.0, 10.0]
_RES_RANGES = [200.0, 2e3, 20e3, 200e3, 1e6, 10e6, 100e6]


def normalize_function(function: Union[str, MultimeterFunction]) -> str:
    """Map any user/instrument spelling of a function to its canonical name."""
    if isinstance(function, MultimeterFunction):
        return function.value
    key = str(function).strip().upper()
    # Allow a few friendly aliases in addition to instrument responses.
    friendly = {
        "VDC": "DCV",
        "VOLTAGE_DC": "DCV",
        "VOLTAGE:DC": "DCV",
        "VAC": "ACV",
        "VOLTAGE_AC": "ACV",
        "IDC": "DCI",
        "CURRENT_DC": "DCI",
        "IAC": "ACI",
        "CURRENT_AC": "ACI",
        "OHM": "RES",
        "OHMS": "RES",
        "RESISTANCE_2W": "RES",
        "RESISTANCE_4W": "FRES",
        "PERIOD": "PER",
        "CAPACITANCE": "CAP",
    }
    if key in friendly:
        return friendly[key]
    if key in _FUNCTION_ALIASES:
        return _FUNCTION_ALIASES[key]
    raise ValueError(
        f"Unknown multimeter function '{function}'. "
        f"Valid: {', '.join(FUNCTION_CMDS)}"
    )


def parse_reading(raw: str) -> Optional[float]:
    """Parse a scientific-notation reading; return None for overload/invalid."""
    text = raw.strip().strip('"').split(",")[0].strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        # Some firmware appends a unit token; keep the leading numeric part.
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
    if math.isnan(value) or math.isinf(value) or abs(value) >= _OVERLOAD_THRESHOLD:
        return None
    return value


def _to_bool_word(enabled: bool) -> str:
    return "ON" if enabled else "OFF"


# --------------------------------------------------------------------------- #
# Base driver
# --------------------------------------------------------------------------- #


class RigolDMMBase(BaseEquipment):
    """Common implementation for the Rigol DM30xx family (RIGOL command set)."""

    # ---- per-model constants (overridden in subclasses) -------------------
    MODEL = "DM30xx"
    DIGITS = 5.5
    INTERFACES: Sequence[str] = ("USB", "LAN", "GPIB", "RS232")
    # Range tables per function (full-scale, base unit). FREQ/PER use the
    # ACV voltage ranges because the range there is the input voltage range.
    RANGES: Dict[str, List[float]] = {
        "DCV": _DCV_RANGES,
        "ACV": _ACV_RANGES,
        "DCI": _DCI_RANGES,
        "ACI": [20e-3, 200e-3, 2.0, 10.0],
        "RES": _RES_RANGES,
        "FRES": _RES_RANGES,
        "FREQ": _ACV_RANGES,
        "PER": _ACV_RANGES,
        "CAP": [2e-9, 20e-9, 200e-9, 2e-6, 200e-6, 10e-3],
    }
    # Approximate readings/second for F, M, S at 50 Hz mains.
    RATE_READINGS_PER_SECOND: Dict[str, float] = {"FAST": 123.0, "MEDIUM": 20.0, "SLOW": 2.5}
    # Unit expected by :TRIGger:AUTO:INTErval ("ms" on DM3058, "s" on DM3068).
    TRIGGER_INTERVAL_UNIT = "ms"
    # Functions selectable on the secondary display via :FUNCtion2:<func>.
    SECONDARY_FUNCTIONS: Sequence[str] = (
        "DCV", "ACV", "DCI", "ACI", "FREQ", "PER", "RES", "FRES", "CAP",
    )
    # Max samples accepted by :TRIGger:SINGle.
    MAX_SINGLE_TRIGGER_SAMPLES = 2000
    # Whether :SYSTem:TYPE? / :SYSTem:SERIal? / :SYSTem:EDITion? exist.
    HAS_SYSTEM_IDENTITY_QUERIES = False

    # Serial defaults from the user guide (both models).
    SERIAL_BAUD = 9600

    def __init__(self, resource_manager, resource_string: str):
        super().__init__(resource_manager, resource_string)
        self.manufacturer = "Rigol"
        self.model = self.MODEL
        self.serial_number: Optional[str] = None
        self.firmware_version: Optional[str] = None
        # Locally tracked state (the RIGOL set has no AUTO/MANU query).
        self._function: Optional[str] = None
        self._auto_range: Dict[str, bool] = {}
        self._secondary_function: Optional[str] = None
        self._command_set: Optional[str] = None
        self._io_lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #

    async def connect(self):
        """Open the VISA resource, configure RS-232 if needed, verify *IDN?.

        Mirrors :meth:`BaseEquipment.connect` but inserts serial-port setup
        and forces the RIGOL command set so the driver's SCPI tree is valid
        regardless of what a previous user left selected on the front panel.
        """
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

                self.instrument = self.resource_manager.open_resource(
                    self.resource_string
                )

                if "ASRL" in self.resource_string.upper() or "COM" in self.resource_string.upper():
                    # DM3058/DM3068 RS-232: 9600 8N1 by default, CR+LF terminated.
                    self.instrument.baud_rate = self.SERIAL_BAUD
                    self.instrument.data_bits = 8
                    self.instrument.parity = 0
                    self.instrument.stop_bits = 10  # pyvisa constant: one stop bit
                    self.instrument.flow_control = 0
                    self.instrument.read_termination = "\n"
                    self.instrument.write_termination = "\r\n"
                    logger.info(
                        f"Configured serial port {self.resource_string}: "
                        f"{self.SERIAL_BAUD} 8N1, CRLF termination"
                    )
                else:
                    # USB-TMC / VXI-11 / GPIB: newline terminated.
                    try:
                        self.instrument.read_termination = "\n"
                        self.instrument.write_termination = "\n"
                    except Exception:
                        pass

                # Slow-rate readings on the DM3068 integrate for ~2 s; allow margin.
                self.instrument.timeout = 10000

                idn = await self._query("*IDN?")
                logger.info(f"Connected to Rigol multimeter: {idn}")
                self._parse_idn(idn)

                # Make sure the RIGOL command tree is active.
                await self._select_command_set("RIGOL")

                self.connected = True
                self.cached_info = await self.get_info()

                # Learn the current front-panel function (best effort).
                try:
                    await self.get_function()
                except Exception as e:  # pragma: no cover - defensive
                    logger.debug(f"Could not read initial function: {e}")

            except Exception as e:
                logger.error(f"Failed to connect to {self.resource_string}: {e}")
                self.connected = False
                raise
            finally:
                self._is_connecting = False

    async def _select_command_set(self, name: str = "RIGOL"):
        """Switch the meter to a command set (RIGOL, AGILENT or FLUKE)."""
        name = name.upper()
        if name not in {"RIGOL", "AGILENT", "FLUKE"}:
            raise ValueError("Command set must be RIGOL, AGILENT or FLUKE")
        try:
            current = (await self._query("CMDSET?")).strip().upper()
        except Exception:
            current = ""
        if current != name:
            await self._write(f"CMDSET {name}")
            await asyncio.sleep(0.1)
        self._command_set = name

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

    # ------------------------------------------------------------------ #
    # Identity / status
    # ------------------------------------------------------------------ #

    async def get_info(self) -> EquipmentInfo:
        """Identify the meter from *IDN? and build its EquipmentInfo."""
        idn = await self._query("*IDN?")
        info = self._parse_idn(idn)
        return EquipmentInfo(
            id=generate_equipment_id(self.resource_string, "dmm_"),
            type=EquipmentType.MULTIMETER,
            manufacturer=info["manufacturer"] or self.manufacturer,
            model=info["model"] or self.model,
            serial_number=info["serial"],
            connection_type=self._determine_connection_type(),
            resource_string=self.resource_string,
        )

    def _capabilities(self) -> Dict[str, Any]:
        return {
            "digits": self.DIGITS,
            "functions": list(FUNCTION_CMDS.keys()),
            "secondary_functions": list(self.SECONDARY_FUNCTIONS),
            "ranges": {func: list(vals) for func, vals in self.RANGES.items()},
            "rates": list(self.RATE_READINGS_PER_SECOND.keys()),
            "rate_readings_per_second": dict(self.RATE_READINGS_PER_SECOND),
            "max_voltage": 1000.0,
            "max_current": 10.0,
            "interfaces": list(self.INTERFACES),
            "trigger_sources": sorted(_TRIGGER_SOURCES),
            "math_functions": sorted(_MATH_FUNCTIONS),
            "command_sets": ["RIGOL", "AGILENT", "FLUKE"],
            "supports_dual_display": bool(self.SECONDARY_FUNCTIONS),
            "supports_acquisition": True,
        }

    async def get_status(self) -> EquipmentStatus:
        """Report connection state, firmware and capabilities."""
        try:
            idn = await self._query("*IDN?")
            info = self._parse_idn(idn)
            capabilities = self._capabilities()
            try:
                capabilities["function"] = await self.get_function()
            except Exception:
                pass
            capabilities["command_set"] = self._command_set
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
        """Run *TST?; the meter returns 0 on pass."""
        try:
            async with self._io_lock:
                old_timeout = self.instrument.timeout if self.instrument else None
                if self.instrument is not None:
                    self.instrument.timeout = 30000
                try:
                    result = await self._query("*TST?")
                finally:
                    if self.instrument is not None and old_timeout is not None:
                        self.instrument.timeout = old_timeout
            return result.strip() in ("0", "+0", "PASS")
        except Exception as e:
            logger.error(f"Self test failed on {self.resource_string}: {e}")
            return None

    async def reset(self):
        """*RST then re-select the RIGOL command set."""
        await self._write("*RST")
        await asyncio.sleep(0.5)
        await self._select_command_set("RIGOL")
        self._function = None
        self._auto_range.clear()
        self._secondary_function = None

    # ------------------------------------------------------------------ #
    # Command dispatch
    # ------------------------------------------------------------------ #

    async def execute_command(self, command: str, parameters: dict) -> Any:
        """Dispatch a LabLink command name to the matching driver method."""
        parameters = dict(parameters or {})
        handlers = {
            # readings
            "measure": self.measure,
            "get_readings": self.get_readings,
            "get_measurement": self.get_measurement,
            "get_measurements": self.get_measurements,
            "read_samples": self.read_samples,
            # function / range / rate
            "set_function": self.set_function,
            "get_function": self.get_function,
            "set_range": self.set_range,
            "get_range": self.get_range,
            "set_auto_range": self.set_auto_range,
            "set_rate": self.set_rate,
            "get_rate": self.get_rate,
            "set_dc_impedance": self.set_dc_impedance,
            "get_dc_impedance": self.get_dc_impedance,
            "set_filter": self.set_filter,
            "set_continuity_threshold": self.set_continuity_threshold,
            # dual display
            "set_secondary_function": self.set_secondary_function,
            "clear_secondary_function": self.clear_secondary_function,
            "get_secondary_function": self.get_secondary_function,
            # trigger
            "set_trigger_source": self.set_trigger_source,
            "get_trigger_source": self.get_trigger_source,
            "set_trigger_interval": self.set_trigger_interval,
            "set_sample_count": self.set_sample_count,
            "get_sample_count": self.get_sample_count,
            "trigger": self.trigger,
            "set_external_trigger": self.set_external_trigger,
            "set_auto_hold": self.set_auto_hold,
            # math
            "set_math_function": self.set_math_function,
            "get_math_function": self.get_math_function,
            "get_statistics": self.get_statistics,
            "set_statistics": self.set_statistics,
            "set_rel_offset": self.set_rel_offset,
            "set_limits": self.set_limits,
            "get_limit_result": self.get_limit_result,
            # system
            "set_beeper": self.set_beeper,
            "set_display_brightness": self.set_display_brightness,
            "set_command_set": self._select_command_set,
            "get_command_set": self.get_command_set,
            "get_interface_config": self.get_interface_config,
            "reset": self.reset,
            "self_test": self.run_self_test,
            "get_error": self.get_error,
            "clear_errors": self.clear_errors,
            "get_state": self.get_state,
        }
        handler = handlers.get(command)
        if handler is None:
            raise ValueError(f"Unknown command: {command}")
        return await handler(**parameters)

    # ------------------------------------------------------------------ #
    # Function selection
    # ------------------------------------------------------------------ #

    async def set_function(self, function: Union[str, MultimeterFunction]) -> str:
        """Select the main-display measurement function."""
        func = normalize_function(function)
        if func not in FUNCTION_CMDS:
            raise ValueError(f"Function {func} cannot be enabled remotely")
        if self._function != func:
            await self._write(FUNCTION_CMDS[func])
            # Function relays need a moment before the first valid reading.
            await asyncio.sleep(0.2)
            self._function = func
        return func

    async def get_function(self) -> str:
        """Query the main-display function (:FUNCtion?)."""
        raw = (await self._query(":FUNCtion?")).strip().upper()
        func = _FUNCTION_ALIASES.get(raw)
        if func is None:
            raise ValueError(f"Unexpected :FUNCtion? response: {raw!r}")
        self._function = func
        return func

    async def get_mode(self) -> str:
        """Alias used by the generic state-capture code."""
        return await self.get_function()

    async def _ensure_function(self, function: Optional[Union[str, MultimeterFunction]]) -> str:
        if function is None:
            if self._function is None:
                await self.get_function()
            return self._function or "DCV"
        return await self.set_function(function)

    # ------------------------------------------------------------------ #
    # Range / rate
    # ------------------------------------------------------------------ #

    def _resolve_range_index(self, function: str, range_value: Union[int, float, str]) -> Union[int, str]:
        """Turn an index, keyword or full-scale value into a vendor range code."""
        table = self.RANGES.get(function)
        if table is None:
            raise ValueError(f"Function {function} has no selectable ranges")
        if isinstance(range_value, str):
            key = range_value.strip().upper()
            if key in ("MIN", "MAX", "DEF"):
                return key
            if key == "AUTO":
                return "AUTO"
            try:
                range_value = float(key)
            except ValueError:
                raise ValueError(f"Invalid range '{range_value}' for {function}")
        if isinstance(range_value, bool):
            raise ValueError("Range must be an index, a value, or MIN/MAX/DEF/AUTO")
        if isinstance(range_value, int) and 0 <= range_value < len(table):
            return range_value
        value = float(range_value)
        # Treat any float (or out-of-index int) as a desired full-scale value.
        for idx, full_scale in enumerate(table):
            if value <= full_scale * (1 + 1e-9):
                return idx
        raise ValueError(
            f"{value} exceeds the maximum {function} range of {table[-1]} {UNITS[function]}"
        )

    async def set_range(
        self,
        range: Union[int, float, str],
        function: Optional[Union[str, MultimeterFunction]] = None,
    ) -> Dict[str, Any]:
        """Set a manual range (index, MIN/MAX/DEF, or full-scale value) or AUTO."""
        func = await self._ensure_function(function)
        if func == "CONT":
            # Continuity's "range" is the short-circuit threshold in ohms.
            return await self.set_continuity_threshold(int(float(range)))
        if func == "DIODE":
            raise ValueError("Diode test has a fixed range")
        code = self._resolve_range_index(func, range)
        if code == "AUTO":
            return await self.set_auto_range(True, func)
        await self._write(f"{MEASURE_ROOTS[func]} {code}")
        self._auto_range[func] = False
        await asyncio.sleep(0.1)
        return await self.get_range(func)

    async def set_auto_range(
        self, enabled: bool = True, function: Optional[Union[str, MultimeterFunction]] = None
    ) -> Dict[str, Any]:
        """Enable or disable auto-ranging for the active function (:MEASure AUTO|MANU)."""
        func = await self._ensure_function(function)
        await self._write(":MEASure AUTO" if enabled else ":MEASure MANU")
        self._auto_range[func] = bool(enabled)
        await asyncio.sleep(0.1)
        return await self.get_range(func)

    async def get_range(self, function: Optional[Union[str, MultimeterFunction]] = None) -> Dict[str, Any]:
        """Query the active range index and translate it to a full-scale value."""
        func = await self._ensure_function(function)
        result: Dict[str, Any] = {
            "function": func,
            "unit": UNITS[func],
            "auto_range": self._auto_range.get(func),
        }
        if func == "CONT" or func == "DIODE":
            result.update({"index": None, "full_scale": None})
            return result
        raw = (await self._query(f"{MEASURE_ROOTS[func]}:RANGe?")).strip()
        try:
            idx = int(float(raw))
        except ValueError:
            idx = None
        table = self.RANGES.get(func, [])
        result["index"] = idx
        result["full_scale"] = table[idx] if idx is not None and 0 <= idx < len(table) else None
        return result

    async def set_rate(
        self, rate: str, function: Optional[Union[str, MultimeterFunction]] = None
    ) -> str:
        """Set measurement rate: FAST/MEDIUM/SLOW (or F/M/S)."""
        func = await self._ensure_function(function)
        if func not in RATE_CMDS:
            raise ValueError(f"Function {func} has no selectable rate")
        key = _RATE_ALIASES.get(str(rate).strip().upper())
        if key is None:
            raise ValueError("Rate must be FAST, MEDIUM or SLOW")
        await self._write(f"{RATE_CMDS[func]} {key[0]}")
        await asyncio.sleep(0.1)
        return await self.get_rate(func)

    async def get_rate(self, function: Optional[Union[str, MultimeterFunction]] = None) -> Optional[str]:
        """Query measurement rate; normalises F/M/S and FAST/MEDIUM/SLOW."""
        func = await self._ensure_function(function)
        if func not in RATE_CMDS:
            return None
        raw = (await self._query(f"{RATE_CMDS[func]}?")).strip().upper()
        return _RATE_ALIASES.get(raw, raw or None)

    async def set_dc_impedance(self, impedance: str = "10M") -> str:
        """DC voltage input impedance: '10M' or '10G' (>10 GOhm on low ranges)."""
        key = str(impedance).strip().upper().replace("OHM", "").replace("Ω", "")
        if key not in ("10M", "10G"):
            raise ValueError("Impedance must be 10M or 10G")
        await self._ensure_function("DCV")
        await self._write(f":MEASure:VOLTage:DC:IMPEdance {key}")
        return await self.get_dc_impedance()

    async def get_dc_impedance(self) -> str:
        return (await self._query(":MEASure:VOLTage:DC:IMPEdance?")).strip().upper()

    async def set_filter(self, enabled: bool, function: Optional[str] = None) -> bool:
        """AC filter on DC voltage / DC current measurements."""
        func = await self._ensure_function(function)
        if func not in ("DCV", "DCI"):
            raise ValueError("Filter is only available for DCV and DCI")
        await self._write(f"{MEASURE_ROOTS[func]}:FILTer:STATe {_to_bool_word(enabled)}")
        raw = (await self._query(f"{MEASURE_ROOTS[func]}:FILTer:STATe?")).strip().upper()
        return raw in ("1", "ON")

    async def set_continuity_threshold(self, threshold_ohms: int = 10) -> Dict[str, Any]:
        """Short-circuit resistance threshold for continuity, 1..2000 Ohm."""
        threshold = int(threshold_ohms)
        if not 1 <= threshold <= 2000:
            raise ValueError("Continuity threshold must be 1..2000 Ohm")
        await self._ensure_function("CONT")
        await self._write(f":MEASure:CONTinuity {threshold}")
        return {"function": "CONT", "threshold_ohms": threshold, "unit": "Ohm"}

    # ------------------------------------------------------------------ #
    # Readings
    # ------------------------------------------------------------------ #

    async def _read_value(self, func: str) -> Optional[float]:
        raw = await self._query(f"{MEASURE_ROOTS[func]}?")
        return parse_reading(raw)

    async def measure(
        self,
        function: Optional[Union[str, MultimeterFunction]] = None,
        include_range: bool = True,
    ) -> MultimeterData:
        """Take one reading, switching function first if requested."""
        async with self._io_lock:
            func = await self._ensure_function(function)
            value = await self._read_value(func)
            data = MultimeterData(
                equipment_id=self.cached_info.id if self.cached_info else "unknown",
                function=func,
                value=value,
                unit=UNITS[func],
                overload=value is None,
                auto_range=self._auto_range.get(func),
            )
            if include_range and func not in ("CONT", "DIODE"):
                try:
                    rng = await self.get_range(func)
                    data.range_index = rng.get("index")
                    data.range_full_scale = rng.get("full_scale")
                except Exception as e:
                    logger.debug(f"Range query failed: {e}")
                try:
                    data.rate = await self.get_rate(func)
                except Exception:
                    pass
            if self._secondary_function:
                try:
                    raw2 = await self._query(":FUNCtion2:VALUe2?")
                    data.secondary_function = self._secondary_function
                    data.secondary_value = parse_reading(raw2)
                    data.secondary_unit = UNITS.get(self._secondary_function)
                except Exception as e:
                    logger.debug(f"Secondary display read failed: {e}")
            return data

    async def get_readings(self) -> MultimeterData:
        """Current reading on the active function (used by streaming + REST)."""
        return await self.measure(None)

    async def get_measurement(self, channel: str = "CH1") -> Dict[str, Any]:
        """Acquisition-engine hook: return {'value': float} for a channel name.

        Channel naming:
        - ``CH1`` / ``1`` / ``MAIN`` / ``PRIMARY``: whatever function is active
        - ``CH2`` / ``2`` / ``SECONDARY``: the dual-display value
        - any function name (``DCV``, ``RES``, ...): switch to it and read
        """
        key = (channel or "CH1").strip().upper()
        if key in ("CH1", "1", "MAIN", "PRIMARY", ""):
            data = await self.measure(None, include_range=False)
        elif key in ("CH2", "2", "SECONDARY", "FUNC2"):
            if not self._secondary_function:
                raise ValueError("Secondary display is not enabled")
            raw = await self._query(":FUNCtion2:VALUe2?")
            value = parse_reading(raw)
            return {
                "value": value if value is not None else float("nan"),
                "unit": UNITS.get(self._secondary_function, ""),
                "function": self._secondary_function,
                "overload": value is None,
            }
        else:
            data = await self.measure(key, include_range=False)
        return {
            "value": data.value if data.value is not None else float("nan"),
            "unit": data.unit,
            "function": data.function,
            "overload": data.overload,
        }

    async def get_measurements(self, channel: Any = 1) -> Dict[str, Any]:
        """Streaming hook: primary (and secondary) values keyed by function."""
        data = await self.measure(None)
        out: Dict[str, Any] = {
            data.function: data.value if data.value is not None else float("nan"),
            f"{data.function}_unit": data.unit,
            "overload": data.overload,
        }
        if data.secondary_function:
            out[data.secondary_function] = (
                data.secondary_value if data.secondary_value is not None else float("nan")
            )
            out[f"{data.secondary_function}_unit"] = data.secondary_unit
        return out

    async def read_samples(
        self,
        count: int = 10,
        function: Optional[Union[str, MultimeterFunction]] = None,
        interval_s: float = 0.0,
    ) -> Dict[str, Any]:
        """Take ``count`` consecutive readings and return them with summary stats."""
        count = int(count)
        if count < 1:
            raise ValueError("count must be >= 1")
        func = await self._ensure_function(function)
        values: List[Optional[float]] = []
        for _ in range(count):
            async with self._io_lock:
                values.append(await self._read_value(func))
            if interval_s > 0:
                await asyncio.sleep(interval_s)
        valid = [v for v in values if v is not None]
        stats: Dict[str, Any] = {"count": len(valid), "overloads": len(values) - len(valid)}
        if valid:
            mean = sum(valid) / len(valid)
            stats.update(
                {
                    "min": min(valid),
                    "max": max(valid),
                    "mean": mean,
                    "std": math.sqrt(sum((v - mean) ** 2 for v in valid) / len(valid)),
                }
            )
        return {"function": func, "unit": UNITS[func], "values": values, "stats": stats}

    # ------------------------------------------------------------------ #
    # Dual display
    # ------------------------------------------------------------------ #

    async def set_secondary_function(self, function: Union[str, MultimeterFunction]) -> str:
        """Enable a function on the secondary display (:FUNCtion2:<func>)."""
        func = normalize_function(function)
        if func not in self.SECONDARY_FUNCTIONS:
            raise ValueError(
                f"{self.model} secondary display supports: {', '.join(self.SECONDARY_FUNCTIONS)}"
            )
        cmd = FUNCTION_CMDS[func].replace(":FUNCtion:", ":FUNCtion2:")
        await self._write(cmd)
        await asyncio.sleep(0.2)
        self._secondary_function = func
        return func

    async def clear_secondary_function(self) -> None:
        await self._write(":FUNCtion2:CLEar")
        self._secondary_function = None

    async def get_secondary_function(self) -> Optional[str]:
        """Query the secondary display function, or None if off."""
        try:
            on = (await self._query(":FUNCtion2:ON?")).strip().upper()
            if on in ("0", "OFF", "FALSE"):
                self._secondary_function = None
                return None
        except Exception:
            pass
        raw = (await self._query(":FUNCtion2?")).strip().upper()
        func = _FUNCTION_ALIASES.get(raw)
        self._secondary_function = func
        return func

    # ------------------------------------------------------------------ #
    # Trigger
    # ------------------------------------------------------------------ #

    async def set_trigger_source(self, source: str = "AUTO") -> str:
        key = str(source).strip().upper()
        aliases = {"IMM": "AUTO", "IMMEDIATE": "AUTO", "BUS": "SINGLE", "EXTERNAL": "EXT"}
        key = aliases.get(key, key)
        if key not in _TRIGGER_SOURCES:
            raise ValueError("Trigger source must be AUTO, SINGLE or EXT")
        await self._write(f":TRIGger:SOURce {key}")
        return await self.get_trigger_source()

    async def get_trigger_source(self) -> str:
        return (await self._query(":TRIGger:SOURce?")).strip().upper()

    async def set_trigger_interval(self, interval_s: float) -> float:
        """Auto-trigger interval in seconds (converted to the model's native unit)."""
        interval_s = float(interval_s)
        if interval_s < 0:
            raise ValueError("Interval must be >= 0")
        if self.TRIGGER_INTERVAL_UNIT == "ms":
            await self._write(f":TRIGger:AUTO:INTErval {int(round(interval_s * 1000))}")
        else:
            await self._write(f":TRIGger:AUTO:INTErval {interval_s:g}")
        raw = (await self._query(":TRIGger:AUTO:INTErval?")).strip()
        value = float(raw)
        return value / 1000.0 if self.TRIGGER_INTERVAL_UNIT == "ms" else value

    async def set_sample_count(self, count: int) -> int:
        """Samples per single trigger (:TRIGger:SINGle)."""
        count = int(count)
        if not 1 <= count <= self.MAX_SINGLE_TRIGGER_SAMPLES:
            raise ValueError(f"Sample count must be 1..{self.MAX_SINGLE_TRIGGER_SAMPLES}")
        await self._write(f":TRIGger:SINGle {count}")
        return await self.get_sample_count()

    async def get_sample_count(self) -> int:
        return int(float((await self._query(":TRIGger:SINGle?")).strip()))

    async def trigger(self) -> None:
        """Fire one single trigger (equivalent to the front-panel Single key)."""
        await self._write(":TRIGger:SINGle:TRIGgered")

    async def set_external_trigger(self, edge: str = "RISE") -> str:
        key = str(edge).strip().upper()
        if key not in _EXT_TRIGGER_TYPES:
            raise ValueError("External trigger must be RISE, FALL, HIGH or LOW")
        await self._write(f":TRIGger:EXT {key}")
        return (await self._query(":TRIGger:EXT?")).strip().upper()

    async def set_auto_hold(self, enabled: bool, sensitivity: Optional[int] = None) -> bool:
        """Reading-hold under auto trigger, optional sensitivity index 0..3."""
        await self._write(f":TRIGger:AUTO:HOLD {_to_bool_word(enabled)}")
        if sensitivity is not None:
            sensitivity = int(sensitivity)
            if not 0 <= sensitivity <= 3:
                raise ValueError("Hold sensitivity index must be 0..3")
            await self._write(f":TRIGger:AUTO:HOLD:SENSitivity {sensitivity}")
        raw = (await self._query(":TRIGger:AUTO:HOLD?")).strip().upper()
        return raw in ("1", "ON")

    # ------------------------------------------------------------------ #
    # Math / statistics / limits
    # ------------------------------------------------------------------ #

    async def set_math_function(self, math_function: str = "NONE") -> str:
        key = str(math_function).strip().upper()
        aliases = {"AVG": "AVERAGE", "MEAN": "AVERAGE", "NULL": "REL", "LIMIT": "PF", "OFF": "NONE"}
        key = aliases.get(key, key)
        if key not in _MATH_FUNCTIONS:
            raise ValueError(f"Math function must be one of {sorted(_MATH_FUNCTIONS)}")
        await self._write(f":CALCulate:FUNCtion {key}")
        return await self.get_math_function()

    async def get_math_function(self) -> str:
        return (await self._query(":CALCulate:FUNCtion?")).strip().upper()

    async def set_statistics(self, enabled: bool = True) -> bool:
        await self._write(f":CALCulate:STATistic:STATe {_to_bool_word(enabled)}")
        raw = (await self._query(":CALCulate:STATistic:STATe?")).strip().upper()
        return raw in ("1", "ON")

    async def get_statistics(self) -> Dict[str, Optional[float]]:
        """MIN / MAX / AVERAGE / COUNT from the meter's statistics engine."""
        out: Dict[str, Optional[float]] = {}
        for name, cmd in (
            ("min", ":CALCulate:STATistic:MIN?"),
            ("max", ":CALCulate:STATistic:MAX?"),
            ("average", ":CALCulate:STATistic:AVERage?"),
            ("count", ":CALCulate:STATistic:COUNt?"),
        ):
            try:
                out[name] = parse_reading(await self._query(cmd))
            except Exception as e:
                logger.debug(f"Statistic {name} unavailable: {e}")
                out[name] = None
        return out

    async def set_rel_offset(self, offset: Union[float, str] = "CURR", enabled: bool = True) -> Dict[str, Any]:
        """Relative (null) measurement. offset may be a value or CURR/MIN/MAX/DEF."""
        await self._write(":CALCulate:FUNCtion REL")
        if isinstance(offset, str):
            key = offset.strip().upper()
            if key not in ("CURR", "MIN", "MAX", "DEF"):
                key = f"{float(key):g}"
        else:
            key = f"{float(offset):g}"
        await self._write(f":CALCulate:REL:OFFSet {key}")
        await self._write(f":CALCulate:REL:STATe {_to_bool_word(enabled)}")
        raw = await self._query(":CALCulate:REL:OFFSet?")
        return {"offset": parse_reading(raw), "enabled": bool(enabled)}

    async def set_limits(self, lower: float, upper: float, enabled: bool = True) -> Dict[str, Any]:
        """Pass/fail limit test."""
        lower, upper = float(lower), float(upper)
        if lower > upper:
            raise ValueError("lower must be <= upper")
        await self._write(":CALCulate:FUNCtion PF")
        await self._write(f":CALCulate:PF:LOWEr {lower:g}")
        await self._write(f":CALCulate:PF:UPPEr {upper:g}")
        await self._write(f":CALCulate:PF:STATe {_to_bool_word(enabled)}")
        return {"lower": lower, "upper": upper, "enabled": bool(enabled)}

    async def get_limit_result(self) -> str:
        return (await self._query(":CALCulate:PF?")).strip().upper()

    # ------------------------------------------------------------------ #
    # System
    # ------------------------------------------------------------------ #

    async def set_beeper(self, enabled: bool) -> bool:
        await self._write(f"SYSTem:BEEPer:STATe {_to_bool_word(enabled)}")
        raw = (await self._query("SYSTem:BEEPer:STATe?")).strip().upper()
        return raw in ("1", "ON")

    async def set_display_brightness(self, level: int) -> int:
        level = int(level)
        if not 0 <= level <= 32:
            raise ValueError("Brightness must be 0..32")
        await self._write(f":SYSTem:DISPlay:BRIGht {level}")
        return int(float((await self._query(":SYSTem:DISPlay:BRIGht?")).strip()))

    async def get_command_set(self) -> str:
        cs = (await self._query("CMDSET?")).strip().upper()
        self._command_set = cs
        return cs

    async def get_interface_config(self) -> Dict[str, Any]:
        """Read back LAN / GPIB / RS-232 settings the meter will accept."""
        cfg: Dict[str, Any] = {}
        queries = {
            "rs232_baud": ":UTILity:INTErface:RS232:BAUD?",
            "rs232_parity": ":UTILity:INTErface:RS232:PARIty?",
        }
        if "LAN" in self.INTERFACES:
            queries.update(
                {
                    "lan_dhcp": ":UTILity:INTErface:LAN:DHCP?",
                    "lan_ip": ":UTILity:INTErface:LAN:IP?",
                    "lan_mask": ":UTILity:INTErface:LAN:MASK?",
                    "lan_gateway": ":UTILity:INTErface:LAN:GATEway?",
                }
            )
        if "GPIB" in self.INTERFACES:
            queries["gpib_address"] = ":UTILity:INTErface:GPIB:ADDRess?"
        for key, cmd in queries.items():
            try:
                cfg[key] = (await self._query(cmd)).strip()
            except Exception as e:
                logger.debug(f"{key} query failed: {e}")
                cfg[key] = None
        return cfg

    async def get_error(self) -> Dict[str, Any]:
        raw = await self._query("SYSTem:ERRor?")
        code_str, _, message = raw.partition(",")
        try:
            code = int(float(code_str.strip()))
        except ValueError:
            code = None
        return {"code": code, "message": message.strip().strip('"'), "raw": raw}

    async def get_state(self) -> Dict[str, Any]:
        """Snapshot of settings for the state capture/restore system."""
        func = await self.get_function()
        state: Dict[str, Any] = {"function": func}
        try:
            state["range"] = await self.get_range(func)
        except Exception:
            state["range"] = None
        try:
            state["rate"] = await self.get_rate(func)
        except Exception:
            state["rate"] = None
        for key, coro in (
            ("trigger_source", self.get_trigger_source()),
            ("math_function", self.get_math_function()),
            ("secondary_function", self.get_secondary_function()),
        ):
            try:
                state[key] = await coro
            except Exception:
                state[key] = None
        return state


# --------------------------------------------------------------------------- #
# Concrete models
# --------------------------------------------------------------------------- #


class RigolDM3058(RigolDMMBase):
    """Rigol DM3058: 5 1/2 digit bench DMM with USB, LAN, GPIB and RS-232."""

    MODEL = "DM3058"
    DIGITS = 5.5
    INTERFACES = ("USB", "LAN", "GPIB", "RS232")
    TRIGGER_INTERVAL_UNIT = "ms"
    MAX_SINGLE_TRIGGER_SAMPLES = 2000
    RATE_READINGS_PER_SECOND = {"FAST": 123.0, "MEDIUM": 20.0, "SLOW": 2.5}
    RANGES = {
        "DCV": _DCV_RANGES,
        "ACV": _ACV_RANGES,
        "DCI": _DCI_RANGES,
        "ACI": [20e-3, 200e-3, 2.0, 10.0],
        "RES": _RES_RANGES,
        "FRES": _RES_RANGES,
        "FREQ": _ACV_RANGES,
        "PER": _ACV_RANGES,
        "CAP": [2e-9, 20e-9, 200e-9, 2e-6, 200e-6, 10e-3],
    }


class RigolDM3058E(RigolDM3058):
    """Rigol DM3058E: DM3058 without the LAN and GPIB interfaces."""

    MODEL = "DM3058E"
    INTERFACES = ("USB", "RS232")


class RigolDM3068(RigolDMMBase):
    """Rigol DM3068: 6 1/2 digit bench DMM, LXI-C, USB/LAN/GPIB/RS-232."""

    MODEL = "DM3068"
    DIGITS = 6.5
    INTERFACES = ("USB", "LAN", "GPIB", "RS232")
    TRIGGER_INTERVAL_UNIT = "s"
    MAX_SINGLE_TRIGGER_SAMPLES = 50000
    HAS_SYSTEM_IDENTITY_QUERIES = True
    # Only frequency can be shown on the secondary display (with ACV/ACI main).
    SECONDARY_FUNCTIONS = ("FREQ",)
    RATE_READINGS_PER_SECOND = {"FAST": 2500.0, "MEDIUM": 250.0, "SLOW": 0.5}
    RANGES = {
        "DCV": _DCV_RANGES,
        "ACV": _ACV_RANGES,
        "DCI": _DCI_RANGES,
        "ACI": _DCI_RANGES,
        "RES": _RES_RANGES,
        "FRES": _RES_RANGES,
        "FREQ": _ACV_RANGES,
        "PER": _ACV_RANGES,
        "CAP": [2e-9, 20e-9, 200e-9, 2e-6, 20e-6, 200e-6, 2e-3, 20e-3, 100e-3],
    }

    async def get_info(self) -> EquipmentInfo:
        """Use the dedicated identity queries when *IDN? is incomplete."""
        info = await super().get_info()
        if info.serial_number is None:
            try:
                serial = (await self._query(":SYSTem:SERIal?")).strip()
                if serial:
                    info.serial_number = serial
                    self.serial_number = serial
            except Exception:
                pass
        return info
