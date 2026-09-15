"""Rigol DM858 / DM858E digital multimeter driver.

Protocol reference: RIGOL "DM858 Series Programming Guide". Unlike the
DM3058/DM3068 (RIGOL command set, see ``rigol_multimeter.py``) the DM858
speaks a standard SCPI DMM tree:

=====================  =====================================================
LabLink                SCPI
=====================  =====================================================
set_function           ``[SENSe]:FUNCtion "<VOLT|VOLT:AC|CURR|CURR:AC|RES|FRES|FREQ|PER|CAP|CONT|DIOD|TEMP>"``
configure              ``CONFigure:<func> [range[,resolution]]`` / ``CONFigure?``
set_range              ``[SENSe]:<func>:RANGe <value>`` (FREQ/PER: ``:FREQuency:VOLTage:RANGe``)
set_auto_range         ``[SENSe]:<func>:RANGe:AUTO ON|OFF``
set_rate               ``[SENSe]:<func>:NPLC 0.4|5|20`` (FAST/MEDIUM/SLOW; DCV, DCI, RES, FRES only)
set_resolution         ``[SENSe]:<func>:RESolution``
measure / get_readings ``READ?`` (or ``MEASure:<func>?`` when a range is given)
read_samples           ``TRIGger:SOURce BUS`` + ``SAMPle:COUNt`` + ``INITiate`` + ``*TRG`` + ``FETCh?``
trigger                ``TRIGger:SOURce IMMediate|BUS|EXTernal``, ``TRIGger:COUNt``, ``SAMPle:COUNt``, ``*TRG``, ``INITiate``, ``FETCh?``, ``ABORt``
reading memory         ``DATA:POINts?``, ``DATA:REMove? <n>``, ``DATA:LAST?``, ``R? [n]``
math                   ``[SENSe]:<func>:NULL:STATe/VALue/VALue:AUTO``, ``CALCulate:AVERage:*``, ``CALCulate:LIMit:*``, ``CALCulate:SCALe:*``
secondary display      ``[SENSe]:<func>:SECondary "<OFF|CALCulate:DATA|FREQuency|PERiod|VOLTage:AC>"``, ``[SENSe]:DATA2?``
temperature            ``CONFigure:TEMPerature <probe>,<type>``, ``UNIT:TEMPerature C|F|K``
system                 ``SYSTem:BEEPer[:IMMediate]``, ``SYSTem:BEEPer:STATe``, ``SYSTem:ERRor?``, ``SYSTem:VERSion?``, ``*RST``, ``*OPC?``, ``HCOPy:SDUMp:DATA?``
=====================  =====================================================

Model differences (DM858 Programming Guide + DM858 Series Data Sheet):

=========  =======  ==========  ============  ==============  ============
Model      Digits   Max current Max cap.      Reading memory  Rate (rdg/s)
=========  =======  ==========  ============  ==============  ============
DM858      5 1/2    10 A        10 mF         500,000         125
DM858E     5 1/2    3 A         1 mF          20,000          80
=========  =======  ==========  ============  ==============  ============

Quirks:

* ``READ?`` blocks until the trigger condition is met; the driver keeps the
  trigger source at IMMediate except inside :meth:`read_samples`.
* ``CONFigure:<func>`` resets range/resolution/trigger parameters to their
  defaults; plain function switching therefore uses ``SENSe:FUNCtion``.
* Only DCV, DCI, RES and FRES have an ``NPLC`` command; AC functions,
  FREQ/PER, CAP, CONT, DIODE and TEMP have no selectable rate.
* Limit results are not reported by a query; they set bits 11 ("Lower Limit
  Failed") and 12 ("Upper Limit Failed") of ``STATus:QUEStionable:CONDition?``.
* No ``TRIGger:DELay``, ``*TST?`` or display command is documented.

*IDN? returns ``RIGOL TECHNOLOGIES,<model>,<serial>,<software version>``.
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
# Static command tables
# --------------------------------------------------------------------------- #

# Canonical function -> SENSe/CONFigure/MEASure keyword.
FUNCTION_KEYWORDS: Dict[str, str] = {
    "DCV": "VOLTage:DC",
    "ACV": "VOLTage:AC",
    "DCI": "CURRent:DC",
    "ACI": "CURRent:AC",
    "RES": "RESistance",
    "FRES": "FRESistance",
    "FREQ": "FREQuency",
    "PER": "PERiod",
    "CAP": "CAPacitance",
    "CONT": "CONTinuity",
    "DIODE": "DIODe",
    "TEMP": "TEMPerature",
}

# Canonical function -> SENSe sub-tree that holds RANGe/NULL/SECondary.
SENSE_ROOTS: Dict[str, str] = {
    "DCV": "SENSe:VOLTage:DC",
    "ACV": "SENSe:VOLTage:AC",
    "DCI": "SENSe:CURRent:DC",
    "ACI": "SENSe:CURRent:AC",
    "RES": "SENSe:RESistance",
    "FRES": "SENSe:FRESistance",
    "FREQ": "SENSe:FREQuency",
    "PER": "SENSe:PERiod",
    "CAP": "SENSe:CAPacitance",
}

# Functions with a RANGe command; FREQ/PER range is the input *voltage* range.
RANGE_CMDS: Dict[str, str] = {
    "DCV": "SENSe:VOLTage:DC:RANGe",
    "ACV": "SENSe:VOLTage:AC:RANGe",
    "DCI": "SENSe:CURRent:DC:RANGe",
    "ACI": "SENSe:CURRent:AC:RANGe",
    "RES": "SENSe:RESistance:RANGe",
    "FRES": "SENSe:FRESistance:RANGe",
    "FREQ": "SENSe:FREQuency:VOLTage:RANGe",
    "PER": "SENSe:PERiod:VOLTage:RANGe",
    "CAP": "SENSe:CAPacitance:RANGe",
}

# Functions with an NPLC command (guide: VOLTage:DC, CURRent:DC, RESistance, FRESistance).
NPLC_CMDS: Dict[str, str] = {
    "DCV": "SENSe:VOLTage:DC:NPLC",
    "DCI": "SENSe:CURRent:DC:NPLC",
    "RES": "SENSe:RESistance:NPLC",
    "FRES": "SENSe:FRESistance:NPLC",
}

# Functions with a RESolution command.
RESOLUTION_CMDS: Dict[str, str] = {
    "DCV": "SENSe:VOLTage:DC:RESolution",
    "DCI": "SENSe:CURRent:DC:RESolution",
    "RES": "SENSe:RESistance:RESolution",
    "FRES": "SENSe:FRESistance:RESolution",
}

UNITS: Dict[str, str] = {
    "DCV": "V", "ACV": "V", "DCI": "A", "ACI": "A", "RES": "Ohm", "FRES": "Ohm",
    "FREQ": "Hz", "PER": "s", "CAP": "F", "CONT": "Ohm", "DIODE": "V", "TEMP": "degC",
}

# Table 3.14 "Resolution, Measurement Speed, and Integration Time".
RATE_TO_NPLC: Dict[str, float] = {"FAST": 0.4, "MEDIUM": 5.0, "SLOW": 20.0}
NPLC_TO_RATE: Dict[float, str] = {0.4: "FAST", 5.0: "MEDIUM", 20.0: "SLOW"}
RATE_RESOLUTION_PPM: Dict[str, float] = {"FAST": 1000.0, "MEDIUM": 100.0, "SLOW": 10.0}

# Strings returned by SENSe:FUNCtion? / CONFigure? -> canonical function.
_FUNCTION_ALIASES: Dict[str, str] = {
    "VOLT": "DCV", "VOLT:DC": "DCV", "VOLTAGE": "DCV", "VOLTAGE:DC": "DCV",
    "VOLT:AC": "ACV", "VOLTAGE:AC": "ACV",
    "CURR": "DCI", "CURR:DC": "DCI", "CURRENT": "DCI", "CURRENT:DC": "DCI",
    "CURR:AC": "ACI", "CURRENT:AC": "ACI",
    "RES": "RES", "RESISTANCE": "RES",
    "FRES": "FRES", "FRESISTANCE": "FRES",
    "FREQ": "FREQ", "FREQUENCY": "FREQ",
    "PER": "PER", "PERIOD": "PER",
    "CAP": "CAP", "CAPACITANCE": "CAP",
    "CONT": "CONT", "CONTINUITY": "CONT",
    "DIOD": "DIODE", "DIODE": "DIODE",
    "TEMP": "TEMP", "TEMPERATURE": "TEMP",
    # LabLink canonical names and friendly aliases
    "DCV": "DCV", "ACV": "ACV", "DCI": "DCI", "ACI": "ACI",
    "VDC": "DCV", "VAC": "ACV", "IDC": "DCI", "IAC": "ACI",
    "OHM": "RES", "OHMS": "RES", "2WR": "RES", "4WR": "FRES",
    "RESISTANCE_2W": "RES", "RESISTANCE_4W": "FRES",
}

_RATE_ALIASES = {"F": "FAST", "FAST": "FAST", "M": "MEDIUM", "MEDIUM": "MEDIUM", "S": "SLOW", "SLOW": "SLOW"}
_TRIGGER_SOURCES = {"IMM": "IMMediate", "BUS": "BUS", "EXT": "EXTernal"}
_TRIGGER_ALIASES = {
    "IMM": "IMM", "IMMEDIATE": "IMM", "AUTO": "IMM", "INT": "IMM", "INTERNAL": "IMM",
    "BUS": "BUS", "SINGLE": "BUS", "SOFTWARE": "BUS",
    "EXT": "EXT", "EXTERNAL": "EXT",
}
_MATH_FUNCTIONS = {"NONE", "REL", "DB", "DBM", "MIN", "MAX", "AVERAGE", "TOTAL", "PF"}
_TEMP_PROBES = {"FRTD", "RTD", "FTHERMISTOR", "THERMISTOR", "TCOUPLE"}
_TEMP_PROBE_SCPI = {"FRTD": "FRTD", "RTD": "RTD", "FTHERMISTOR": "FTHermistor",
                    "THERMISTOR": "THERmistor", "TCOUPLE": "TCouple"}
_TEMP_TYPES = {"385", "389", "391", "392", "2200", "3000", "5000", "10000", "30000",
               "B", "E", "J", "K", "N", "R", "S", "T"}

# Readings at or beyond this magnitude are treated as overload / invalid.
_OVERLOAD_THRESHOLD = 9.0e37

# Per-function range tables (full-scale value in base unit), from the
# CONFigure:<func> parameter tables of the DM858 Programming Guide.
_DCV_RANGES = [0.1, 1.0, 10.0, 100.0, 1000.0]
_ACV_RANGES = [0.1, 1.0, 10.0, 100.0, 750.0]
_RES_RANGES = [100.0, 1e3, 10e3, 100e3, 1e6, 10e6, 50e6]
_CURRENT_RANGES_DM858 = [100e-6, 1e-3, 10e-3, 100e-3, 1.0, 10.0]
_CURRENT_RANGES_DM858E = [100e-6, 1e-3, 10e-3, 100e-3, 1.0, 3.0]
_CAP_RANGES_DM858 = [1e-9, 10e-9, 100e-9, 1e-6, 10e-6, 100e-6, 1e-3, 10e-3]
_CAP_RANGES_DM858E = [1e-9, 10e-9, 100e-9, 1e-6, 10e-6, 100e-6, 1e-3]


def normalize_function(function: Union[str, MultimeterFunction]) -> str:
    """Map any user/instrument spelling of a function to its canonical name."""
    if isinstance(function, MultimeterFunction):
        return function.value
    key = str(function).strip().strip('"').upper().replace(" ", "")
    if key in _FUNCTION_ALIASES:
        return _FUNCTION_ALIASES[key]
    raise ValueError(
        f"Unknown multimeter function '{function}'. Valid: {', '.join(FUNCTION_KEYWORDS)}"
    )


def parse_reading(raw: str) -> Optional[float]:
    """Parse the first value of a READ?/FETCh? response; None for overload."""
    text = str(raw).strip().strip('"').split(",")[0].strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if math.isnan(value) or math.isinf(value) or abs(value) >= _OVERLOAD_THRESHOLD:
        return None
    return value


def parse_readings(raw: str) -> List[Optional[float]]:
    """Parse a comma-separated block of readings."""
    out: List[Optional[float]] = []
    for item in str(raw).strip().split(","):
        item = item.strip()
        if item:
            out.append(parse_reading(item))
    return out


def _to_bool_word(enabled: bool) -> str:
    return "ON" if enabled else "OFF"


def _fmt(value: float) -> str:
    return f"{float(value):.8E}"


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #


class RigolDM858(BaseEquipment):
    """Rigol DM858 (5 1/2 digit, 10 A, USB + LAN). ``RigolDM858E`` is the 3 A variant.

    The model row is picked from ``*IDN?``; ``MODEL`` is only the default.
    """

    MODEL = "DM858"
    DIGITS = 5.5
    INTERFACES: Sequence[str] = ("USB", "LAN")

    # Per-model rows (DM858 Programming Guide notes on 3 A/10 A, 1 mF/10 mF,
    # 20,000/500,000 readings; DM858 Series Data Sheet for the reading rate).
    MODEL_TABLE: Dict[str, Dict[str, Any]] = {
        "DM858": {
            "max_current": 10.0,
            "current_ranges": _CURRENT_RANGES_DM858,
            "cap_ranges": _CAP_RANGES_DM858,
            "memory_points": 500_000,
            "readings_per_second": 125.0,
        },
        "DM858E": {
            "max_current": 3.0,
            "current_ranges": _CURRENT_RANGES_DM858E,
            "cap_ranges": _CAP_RANGES_DM858E,
            "memory_points": 20_000,
            "readings_per_second": 80.0,
        },
    }
    MAX_SAMPLE_COUNT = 2000
    MAX_TRIGGER_COUNT = 1000

    def __init__(self, resource_manager, resource_string: str):
        super().__init__(resource_manager, resource_string)
        self.manufacturer = "Rigol"
        self.model = self.MODEL
        self.serial_number: Optional[str] = None
        self.firmware_version: Optional[str] = None
        self._row: Dict[str, Any] = dict(self.MODEL_TABLE[self.MODEL])
        self._function: Optional[str] = None
        self._secondary_function: Optional[str] = None
        self._temperature_unit = "C"
        # Serialises multi-command sequences; BaseEquipment on newer branches already
        # provides a reentrant lock of this name, so only create one if it is missing.
        if not hasattr(self, "_io_lock"):
            self._io_lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Model table / identity
    # ------------------------------------------------------------------ #

    @property
    def RANGES(self) -> Dict[str, List[float]]:  # noqa: N802 - mirrors RigolDMMBase
        row = self._row
        return {
            "DCV": _DCV_RANGES,
            "ACV": _ACV_RANGES,
            "DCI": row["current_ranges"],
            "ACI": row["current_ranges"],
            "RES": _RES_RANGES,
            "FRES": _RES_RANGES,
            "FREQ": _ACV_RANGES,
            "PER": _ACV_RANGES,
            "CAP": row["cap_ranges"],
        }

    def _apply_model(self, model: Optional[str]) -> None:
        key = (model or "").strip().upper()
        # "DM858E" must win over "DM858": try the longest name first.
        match = None
        for name in sorted(self.MODEL_TABLE, key=len, reverse=True):
            if key.startswith(name):
                match = name
                break
        if match is None:
            if key and key != self.MODEL:
                logger.warning(f"Unknown DM858-series model '{model}', keeping {self.MODEL} limits")
            return
        self._row = dict(self.MODEL_TABLE[match])
        self._row["model"] = match

    def _parse_idn(self, idn: str) -> Dict[str, Optional[str]]:
        parts = [p.strip() for p in idn.split(",")]
        info = {
            "manufacturer": parts[0] if len(parts) > 0 and parts[0] else self.manufacturer,
            "model": parts[1] if len(parts) > 1 and parts[1] else self.model,
            "serial": parts[2] if len(parts) > 2 and parts[2] else None,
            "firmware": parts[3] if len(parts) > 3 and parts[3] else None,
        }
        self._apply_model(info["model"])
        self.model = info["model"] or self.model
        self.serial_number = info["serial"]
        self.firmware_version = info["firmware"]
        return info

    async def connect(self):
        """Standard connect, then learn the current function (best effort)."""
        await super().connect()
        try:
            await self.get_function()
        except Exception as e:  # pragma: no cover - defensive
            logger.debug(f"Could not read initial function: {e}")

    async def get_info(self) -> EquipmentInfo:
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
        row = self._row
        return {
            "digits": self.DIGITS,
            "functions": list(FUNCTION_KEYWORDS.keys()),
            "secondary_functions": ["FREQ", "PER", "ACV", "RAW"],
            "ranges": {func: list(vals) for func, vals in self.RANGES.items()},
            "rates": list(RATE_TO_NPLC.keys()),
            "rate_nplc": dict(RATE_TO_NPLC),
            "rate_functions": list(NPLC_CMDS.keys()),
            "readings_per_second": row["readings_per_second"],
            "memory_points": row["memory_points"],
            "max_voltage": 1000.0,
            "max_current": row["max_current"],
            "max_sample_count": self.MAX_SAMPLE_COUNT,
            "max_trigger_count": self.MAX_TRIGGER_COUNT,
            "interfaces": list(self.INTERFACES),
            "trigger_sources": ["IMM", "BUS", "EXT"],
            "math_functions": sorted(_MATH_FUNCTIONS),
            "temperature_probes": sorted(_TEMP_PROBES),
            "supports_dual_display": True,
            "supports_acquisition": True,
        }

    async def get_status(self) -> EquipmentStatus:
        try:
            idn = await self._query("*IDN?")
            info = self._parse_idn(idn)
            capabilities = self._capabilities()
            try:
                capabilities["function"] = await self.get_function()
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

    async def reset(self):
        """*RST (factory defaults; the error queue is *not* cleared by *RST)."""
        await self._write("*RST")
        await asyncio.sleep(0.5)
        self._function = None
        self._secondary_function = None

    async def run_self_test(self) -> Optional[bool]:
        """The DM858 guide documents no *TST?; report 'not supported'."""
        return None

    # ------------------------------------------------------------------ #
    # Command dispatch
    # ------------------------------------------------------------------ #

    async def execute_command(self, command: str, parameters: dict) -> Any:
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
            "configure": self.configure,
            "get_configuration": self.get_configuration,
            "set_range": self.set_range,
            "get_range": self.get_range,
            "set_auto_range": self.set_auto_range,
            "set_rate": self.set_rate,
            "get_rate": self.get_rate,
            "set_nplc": self.set_nplc,
            "set_resolution": self.set_resolution,
            "set_temperature_sensor": self.set_temperature_sensor,
            "set_temperature_unit": self.set_temperature_unit,
            # dual display
            "set_secondary_function": self.set_secondary_function,
            "clear_secondary_function": self.clear_secondary_function,
            "get_secondary_function": self.get_secondary_function,
            # trigger / memory
            "set_trigger_source": self.set_trigger_source,
            "get_trigger_source": self.get_trigger_source,
            "set_trigger_count": self.set_trigger_count,
            "get_trigger_count": self.get_trigger_count,
            "set_sample_count": self.set_sample_count,
            "get_sample_count": self.get_sample_count,
            "trigger": self.trigger,
            "initiate": self.initiate,
            "fetch": self.fetch,
            "abort": self.abort,
            "get_data_points": self.get_data_points,
            "remove_data": self.remove_data,
            "get_last_reading": self.get_last_reading,
            # math
            "set_math_function": self.set_math_function,
            "get_math_function": self.get_math_function,
            "get_statistics": self.get_statistics,
            "set_statistics": self.set_statistics,
            "clear_statistics": self.clear_statistics,
            "set_rel_offset": self.set_rel_offset,
            "set_limits": self.set_limits,
            "get_limit_result": self.get_limit_result,
            "set_db_reference": self.set_db_reference,
            # system
            "set_beeper": self.set_beeper,
            "beep": self.beep,
            "get_screenshot": self.get_screenshot,
            "get_scpi_version": self.get_scpi_version,
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
        """Select the measurement function without touching range/trigger (SENSe:FUNCtion)."""
        func = normalize_function(function)
        if self._function != func:
            await self._write(f'SENSe:FUNCtion "{FUNCTION_KEYWORDS[func]}"')
            await asyncio.sleep(0.2)
            self._function = func
            self._secondary_function = None
        return func

    async def get_function(self) -> str:
        raw = (await self._query("SENSe:FUNCtion?")).strip().strip('"').upper()
        func = _FUNCTION_ALIASES.get(raw)
        if func is None:
            raise ValueError(f"Unexpected SENSe:FUNCtion? response: {raw!r}")
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

    async def configure(
        self,
        function: Union[str, MultimeterFunction],
        range: Optional[Union[float, str]] = None,
        resolution: Optional[Union[float, str]] = None,
    ) -> str:
        """CONFigure:<func> [range[,resolution]] - presets and resets trigger params."""
        func = normalize_function(function)
        cmd = f"CONFigure:{FUNCTION_KEYWORDS[func]}"
        args: List[str] = []
        if range is not None:
            if func not in RANGE_CMDS:
                raise ValueError(f"Function {func} has no selectable range")
            args.append(self._range_argument(func, range))
        if resolution is not None:
            if func not in RESOLUTION_CMDS and func not in ("ACV", "ACI"):
                raise ValueError(f"Function {func} has no selectable resolution")
            if not args:
                args.append("DEF")
            args.append(self._lim_or_number(resolution))
        if args:
            cmd += " " + ",".join(args)
        await self._write(cmd)
        await asyncio.sleep(0.2)
        self._function = func
        self._secondary_function = None
        return await self.get_configuration()

    async def get_configuration(self) -> str:
        """CONFigure? -> e.g. 'VOLT 1.00000000E+01,1.00000000E-03'."""
        raw = (await self._query("CONFigure?")).strip().strip('"')
        head = raw.split(" ")[0].strip().upper()
        func = _FUNCTION_ALIASES.get(head)
        if func:
            self._function = func
        return raw

    # ------------------------------------------------------------------ #
    # Range / rate / resolution
    # ------------------------------------------------------------------ #

    @staticmethod
    def _lim_or_number(value: Union[float, str]) -> str:
        if isinstance(value, str):
            key = value.strip().upper()
            if key in ("MIN", "MAX", "DEF", "AUTO"):
                return key
            return _fmt(float(key))
        return _fmt(float(value))

    def _range_argument(self, function: str, range_value: Union[int, float, str]) -> str:
        """Turn an index, keyword or full-scale value into the SCPI argument."""
        table = self.RANGES.get(function)
        if table is None:
            raise ValueError(f"Function {function} has no selectable ranges")
        if isinstance(range_value, bool):
            raise ValueError("Range must be an index, a value, or MIN/MAX/DEF/AUTO")
        if isinstance(range_value, str):
            key = range_value.strip().upper()
            if key in ("MIN", "MAX", "DEF", "AUTO"):
                return key
            try:
                range_value = float(key)
            except ValueError:
                raise ValueError(f"Invalid range '{range_value}' for {function}")
        if isinstance(range_value, int) and 0 <= range_value < len(table):
            return _fmt(table[range_value])
        value = float(range_value)
        for full_scale in table:
            if value <= full_scale * (1 + 1e-9):
                return _fmt(full_scale)
        raise ValueError(
            f"{value} exceeds the maximum {function} range of {table[-1]} {UNITS[function]}"
        )

    def _index_of(self, function: str, full_scale: float) -> Optional[int]:
        table = self.RANGES.get(function, [])
        for idx, fs in enumerate(table):
            if math.isclose(fs, full_scale, rel_tol=1e-6):
                return idx
        return None

    async def set_range(
        self,
        range: Union[int, float, str],
        function: Optional[Union[str, MultimeterFunction]] = None,
    ) -> Dict[str, Any]:
        """Manual range (index, MIN/MAX/DEF, or full-scale value) or AUTO."""
        func = await self._ensure_function(function)
        if func in ("CONT", "DIODE", "TEMP"):
            raise ValueError(f"{func} has a fixed range")
        arg = self._range_argument(func, range)
        if arg == "AUTO":
            return await self.set_auto_range(True, func)
        await self._write(f"{RANGE_CMDS[func]} {arg}")
        await asyncio.sleep(0.1)
        return await self.get_range(func)

    async def set_auto_range(
        self, enabled: bool = True, function: Optional[Union[str, MultimeterFunction]] = None
    ) -> Dict[str, Any]:
        func = await self._ensure_function(function)
        if func not in RANGE_CMDS:
            raise ValueError(f"{func} has no auto-range setting")
        await self._write(f"{RANGE_CMDS[func]}:AUTO {_to_bool_word(enabled)}")
        await asyncio.sleep(0.1)
        return await self.get_range(func)

    async def get_range(self, function: Optional[Union[str, MultimeterFunction]] = None) -> Dict[str, Any]:
        func = await self._ensure_function(function)
        result: Dict[str, Any] = {"function": func, "unit": UNITS[func]}
        if func not in RANGE_CMDS:
            result.update({"auto_range": None, "index": None, "full_scale": None})
            return result
        raw = (await self._query(f"{RANGE_CMDS[func]}?")).strip()
        try:
            full_scale: Optional[float] = float(raw)
        except ValueError:
            full_scale = None
        try:
            auto_raw = (await self._query(f"{RANGE_CMDS[func]}:AUTO?")).strip().upper()
            auto: Optional[bool] = auto_raw in ("1", "ON")
        except Exception:
            auto = None
        result["auto_range"] = auto
        result["full_scale"] = full_scale
        result["index"] = self._index_of(func, full_scale) if full_scale is not None else None
        return result

    async def set_rate(
        self, rate: str, function: Optional[Union[str, MultimeterFunction]] = None
    ) -> str:
        """FAST/MEDIUM/SLOW (F/M/S) -> NPLC 0.4 / 5 / 20 (Table 3.14)."""
        func = await self._ensure_function(function)
        if func not in NPLC_CMDS:
            raise ValueError(f"Function {func} has no selectable rate (NPLC only on DCV, DCI, RES, FRES)")
        key = _RATE_ALIASES.get(str(rate).strip().upper())
        if key is None:
            raise ValueError("Rate must be FAST, MEDIUM or SLOW")
        await self._write(f"{NPLC_CMDS[func]} {RATE_TO_NPLC[key]:g}")
        await asyncio.sleep(0.1)
        return await self.get_rate(func) or key

    async def set_nplc(self, nplc: float, function: Optional[Union[str, MultimeterFunction]] = None) -> float:
        """Integration time in power-line cycles: 0.4, 5 or 20."""
        func = await self._ensure_function(function)
        if func not in NPLC_CMDS:
            raise ValueError(f"Function {func} has no NPLC setting")
        nplc = float(nplc)
        if not any(math.isclose(nplc, v) for v in NPLC_TO_RATE):
            raise ValueError("NPLC must be 0.4, 5 or 20")
        await self._write(f"{NPLC_CMDS[func]} {nplc:g}")
        raw = await self._query(f"{NPLC_CMDS[func]}?")
        return float(raw)

    async def get_rate(self, function: Optional[Union[str, MultimeterFunction]] = None) -> Optional[str]:
        func = await self._ensure_function(function)
        if func not in NPLC_CMDS:
            return None
        raw = (await self._query(f"{NPLC_CMDS[func]}?")).strip()
        try:
            nplc = float(raw)
        except ValueError:
            return None
        for value, name in NPLC_TO_RATE.items():
            if math.isclose(nplc, value, rel_tol=1e-3):
                return name
        return f"NPLC{nplc:g}"

    async def set_resolution(
        self, resolution: Union[float, str], function: Optional[Union[str, MultimeterFunction]] = None
    ) -> float:
        """Resolution in the function's base unit (or MIN/MAX/DEF)."""
        func = await self._ensure_function(function)
        if func not in RESOLUTION_CMDS:
            raise ValueError(f"Function {func} has no RESolution command")
        await self._write(f"{RESOLUTION_CMDS[func]} {self._lim_or_number(resolution)}")
        return float(await self._query(f"{RESOLUTION_CMDS[func]}?"))

    async def set_temperature_sensor(self, probe_type: str = "TCOUPLE", sensor_type: Optional[str] = None) -> str:
        """CONFigure:TEMPerature <probe>,<type>.

        probe_type: FRTD, RTD, FTHERMISTOR, THERMISTOR or TCOUPLE.
        sensor_type: RTD coefficient (385/389/391/392), thermistor resistance
        (2200/3000/5000/10000/30000) or thermocouple letter (B E J K N R S T).
        """
        probe = str(probe_type).strip().upper()
        if probe not in _TEMP_PROBES:
            raise ValueError(f"probe_type must be one of {sorted(_TEMP_PROBES)}")
        cmd = f"CONFigure:TEMPerature {_TEMP_PROBE_SCPI[probe]}"
        if sensor_type is not None:
            st = str(sensor_type).strip().upper()
            if st not in _TEMP_TYPES:
                raise ValueError(f"sensor_type must be one of {sorted(_TEMP_TYPES)}")
            cmd += f",{st}"
        await self._write(cmd)
        await asyncio.sleep(0.2)
        self._function = "TEMP"
        self._secondary_function = None
        return await self.get_configuration()

    async def set_temperature_unit(self, unit: str = "C") -> str:
        key = str(unit).strip().upper().replace("°", "").replace("DEG", "")
        key = {"CELSIUS": "C", "FAHRENHEIT": "F", "KELVIN": "K"}.get(key, key)
        if key not in ("C", "F", "K"):
            raise ValueError("Temperature unit must be C, F or K")
        await self._write(f"UNIT:TEMPerature {key}")
        raw = (await self._query("UNIT:TEMPerature?")).strip().upper()
        self._temperature_unit = raw if raw in ("C", "F", "K") else key
        return self._temperature_unit

    def _unit_for(self, func: str) -> str:
        if func == "TEMP":
            return {"C": "degC", "F": "degF", "K": "K"}[self._temperature_unit]
        return UNITS[func]

    # ------------------------------------------------------------------ #
    # Readings
    # ------------------------------------------------------------------ #

    async def measure(
        self,
        function: Optional[Union[str, MultimeterFunction]] = None,
        include_range: bool = True,
    ) -> MultimeterData:
        """Take one reading with READ?, switching function first if requested."""
        async with self._io_lock:
            func = await self._ensure_function(function)
            value = parse_reading(await self._query("READ?"))
            data = MultimeterData(
                equipment_id=self.cached_info.id if self.cached_info else "unknown",
                function=func,
                value=value,
                unit=self._unit_for(func),
                overload=value is None,
            )
            if include_range and func in RANGE_CMDS:
                try:
                    rng = await self.get_range(func)
                    data.range_index = rng.get("index")
                    data.range_full_scale = rng.get("full_scale")
                    data.auto_range = rng.get("auto_range")
                except Exception as e:
                    logger.debug(f"Range query failed: {e}")
            if include_range and func in NPLC_CMDS:
                try:
                    data.rate = await self.get_rate(func)
                except Exception:
                    pass
            if self._secondary_function:
                try:
                    raw2 = await self._query("SENSe:DATA2?")
                    data.secondary_function = self._secondary_function
                    data.secondary_value = parse_reading(raw2)
                    data.secondary_unit = self._secondary_unit()
                except Exception as e:
                    logger.debug(f"Secondary display read failed: {e}")
            return data

    async def get_readings(self) -> MultimeterData:
        return await self.measure(None)

    async def get_measurement(self, channel: str = "CH1") -> Dict[str, Any]:
        """Acquisition-engine hook.

        - ``CH1`` / ``1`` / ``MAIN`` / ``PRIMARY``: active function
        - ``CH2`` / ``2`` / ``SECONDARY``: the secondary display value
        - any function name (``DCV``, ``TEMP``, ...): switch to it and read
        """
        key = (channel or "CH1").strip().upper()
        if key in ("CH1", "1", "MAIN", "PRIMARY", ""):
            data = await self.measure(None, include_range=False)
        elif key in ("CH2", "2", "SECONDARY", "FUNC2"):
            if not self._secondary_function:
                raise ValueError("Secondary display is not enabled")
            value = parse_reading(await self._query("SENSe:DATA2?"))
            return {
                "value": value if value is not None else float("nan"),
                "unit": self._secondary_unit(),
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
        """Take ``count`` readings and return them with summary statistics.

        With ``interval_s == 0`` the block is captured by the meter
        (``TRIGger:SOURce BUS`` / ``SAMPle:COUNt`` / ``INITiate`` / ``*TRG`` /
        ``FETCh?``) and the trigger source is restored afterwards; with an
        interval the driver loops over ``READ?`` instead.
        """
        count = int(count)
        if count < 1:
            raise ValueError("count must be >= 1")
        if count > self.MAX_SAMPLE_COUNT:
            raise ValueError(f"count must be <= {self.MAX_SAMPLE_COUNT}")
        func = await self._ensure_function(function)
        values: List[Optional[float]] = []
        if interval_s > 0:
            for _ in range(count):
                async with self._io_lock:
                    values.append(parse_reading(await self._query("READ?")))
                await asyncio.sleep(interval_s)
        else:
            async with self._io_lock:
                previous = await self.get_trigger_source()
                try:
                    await self._write("TRIGger:SOURce BUS")
                    await self._write("TRIGger:COUNt 1")
                    await self._write(f"SAMPle:COUNt {count}")
                    await self._write("INITiate")
                    await self._write("*TRG")
                    values = parse_readings(await self._query("FETCh?"))
                finally:
                    await self._write("SAMPle:COUNt 1")
                    await self._write(f"TRIGger:SOURce {_TRIGGER_SOURCES.get(previous, 'IMMediate')}")
        valid = [v for v in values if v is not None]
        stats: Dict[str, Any] = {"count": len(valid), "overloads": len(values) - len(valid)}
        if valid:
            mean = sum(valid) / len(valid)
            stats.update(
                min=min(valid), max=max(valid), mean=mean,
                std=math.sqrt(sum((v - mean) ** 2 for v in valid) / len(valid)),
            )
        return {"function": func, "unit": self._unit_for(func), "values": values, "stats": stats}

    # ------------------------------------------------------------------ #
    # Secondary display
    # ------------------------------------------------------------------ #

    # Main function -> allowed secondary parameters (guide [SENSe]:<func>:SECondary).
    _SECONDARY_OPTIONS: Dict[str, Dict[str, str]] = {
        "DCV": {"RAW": "CALCulate:DATA"},
        "DCI": {"RAW": "CALCulate:DATA"},
        "RES": {"RAW": "CALCulate:DATA"},
        "FRES": {"RAW": "CALCulate:DATA"},
        "CAP": {"RAW": "CALCulate:DATA"},
        "ACV": {"RAW": "CALCulate:DATA", "FREQ": "FREQuency", "PER": "PERiod"},
        "ACI": {"RAW": "CALCulate:DATA", "FREQ": "FREQuency", "PER": "PERiod"},
        "FREQ": {"RAW": "CALCulate:DATA", "ACV": "VOLTage:AC"},
        "PER": {"RAW": "CALCulate:DATA", "ACV": "VOLTage:AC"},
    }
    _SECONDARY_RESPONSES = {"CALC:DATA": "RAW", "FREQ": "FREQ", "PER": "PER", "VOLT:AC": "ACV"}

    def _secondary_unit(self) -> str:
        sec = self._secondary_function
        if sec == "RAW":
            return self._unit_for(self._function or "DCV")
        return UNITS.get(sec or "", "")

    async def set_secondary_function(self, function: Union[str, MultimeterFunction]) -> str:
        """Secondary display: FREQ/PER (with ACV/ACI main), ACV (with FREQ/PER main)
        or RAW (the pre-math value, any function with a SENSe sub-tree)."""
        main = await self._ensure_function(None)
        key = str(function).strip().upper()
        if key in ("CALC:DATA", "CALCULATE:DATA", "PREMATH"):
            key = "RAW"
        elif key != "RAW":
            key = normalize_function(function)
        options = self._SECONDARY_OPTIONS.get(main, {})
        if key not in options:
            raise ValueError(
                f"With {main} on the main display the secondary display supports: "
                f"{', '.join(options) or 'nothing'}"
            )
        await self._write(f'{SENSE_ROOTS[main]}:SECondary "{options[key]}"')
        await asyncio.sleep(0.1)
        self._secondary_function = key
        return key

    async def clear_secondary_function(self) -> None:
        main = await self._ensure_function(None)
        if main in SENSE_ROOTS:
            await self._write(f'{SENSE_ROOTS[main]}:SECondary "OFF"')
        self._secondary_function = None

    async def get_secondary_function(self) -> Optional[str]:
        main = await self._ensure_function(None)
        if main not in SENSE_ROOTS:
            self._secondary_function = None
            return None
        raw = (await self._query(f"{SENSE_ROOTS[main]}:SECondary?")).strip().strip('"').upper()
        self._secondary_function = self._SECONDARY_RESPONSES.get(raw)
        return self._secondary_function

    # ------------------------------------------------------------------ #
    # Trigger / reading memory
    # ------------------------------------------------------------------ #

    async def set_trigger_source(self, source: str = "IMM") -> str:
        key = _TRIGGER_ALIASES.get(str(source).strip().upper())
        if key is None:
            raise ValueError("Trigger source must be IMM (AUTO), BUS (SINGLE) or EXT")
        await self._write(f"TRIGger:SOURce {_TRIGGER_SOURCES[key]}")
        return await self.get_trigger_source()

    async def get_trigger_source(self) -> str:
        raw = (await self._query("TRIGger:SOURce?")).strip().upper()
        return _TRIGGER_ALIASES.get(raw, raw[:3])

    async def set_trigger_count(self, count: int) -> int:
        count = int(count)
        if not 1 <= count <= self.MAX_TRIGGER_COUNT:
            raise ValueError(f"Trigger count must be 1..{self.MAX_TRIGGER_COUNT}")
        await self._write(f"TRIGger:COUNt {count}")
        return await self.get_trigger_count()

    async def get_trigger_count(self) -> int:
        return int(float((await self._query("TRIGger:COUNt?")).strip()))

    async def set_sample_count(self, count: int) -> int:
        count = int(count)
        if not 1 <= count <= self.MAX_SAMPLE_COUNT:
            raise ValueError(f"Sample count must be 1..{self.MAX_SAMPLE_COUNT}")
        await self._write(f"SAMPle:COUNt {count}")
        return await self.get_sample_count()

    async def get_sample_count(self) -> int:
        return int(float((await self._query("SAMPle:COUNt?")).strip()))

    async def trigger(self) -> None:
        """Software trigger (*TRG); valid with TRIGger:SOURce BUS."""
        await self._write("*TRG")

    async def initiate(self) -> None:
        """INITiate: idle -> wait-for-trigger; readings go to memory."""
        await self._write("INITiate")

    async def fetch(self) -> List[Optional[float]]:
        """FETCh?: readings in memory (does not clear them)."""
        return parse_readings(await self._query("FETCh?"))

    async def abort(self) -> None:
        await self._write("ABORt")

    async def get_data_points(self) -> int:
        return int(float((await self._query("DATA:POINts?")).strip()))

    async def remove_data(self, count: int, wait: bool = False) -> List[Optional[float]]:
        """DATA:REMove? <n>[,WAIT]: read and delete the oldest n readings."""
        count = int(count)
        if not 1 <= count <= self._row["memory_points"]:
            raise ValueError(f"count must be 1..{self._row['memory_points']}")
        cmd = f"DATA:REMove? {count}" + (",WAIT" if wait else "")
        return parse_readings(await self._query(cmd))

    async def get_last_reading(self) -> Optional[float]:
        return parse_reading(await self._query("DATA:LAST?"))

    # ------------------------------------------------------------------ #
    # Math / statistics / limits
    # ------------------------------------------------------------------ #

    async def set_math_function(self, math_function: str = "NONE") -> str:
        """NONE, REL (null), DB, DBM, MIN/MAX/AVERAGE/TOTAL (statistics) or PF (limits)."""
        key = str(math_function).strip().upper()
        aliases = {"AVG": "AVERAGE", "MEAN": "AVERAGE", "NULL": "REL", "LIMIT": "PF", "OFF": "NONE", "STAT": "AVERAGE"}
        key = aliases.get(key, key)
        if key not in _MATH_FUNCTIONS:
            raise ValueError(f"Math function must be one of {sorted(_MATH_FUNCTIONS)}")
        func = await self._ensure_function(None)
        if key == "REL" and func not in SENSE_ROOTS:
            raise ValueError(f"{func} has no relative (null) function")
        # The meter can run null, scaling, statistics and limits at the same
        # time; LabLink's math_function is single-valued, so selecting one
        # switches the others off (like :CALCulate:FUNCtion on the DM3058).
        if func in SENSE_ROOTS:
            await self._write(f"{SENSE_ROOTS[func]}:NULL:STATe {_to_bool_word(key == 'REL')}")
        if key in ("DB", "DBM"):
            await self._write(f"CALCulate:SCALe:FUNCtion {key}")
        await self._write(f"CALCulate:SCALe:STATe {_to_bool_word(key in ('DB', 'DBM'))}")
        await self._write(f"CALCulate:AVERage:STATe {_to_bool_word(key in ('MIN', 'MAX', 'AVERAGE', 'TOTAL'))}")
        await self._write(f"CALCulate:LIMit:STATe {_to_bool_word(key == 'PF')}")
        return await self.get_math_function()

    async def get_math_function(self) -> str:
        """First active math operation: REL, DB/DBM, AVERAGE, PF or NONE."""
        func = await self._ensure_function(None)
        if func in SENSE_ROOTS:
            try:
                if (await self._query(f"{SENSE_ROOTS[func]}:NULL:STATe?")).strip().upper() in ("1", "ON"):
                    return "REL"
            except Exception:
                pass
        if (await self._query("CALCulate:SCALe:STATe?")).strip().upper() in ("1", "ON"):
            return (await self._query("CALCulate:SCALe:FUNCtion?")).strip().upper()
        if (await self._query("CALCulate:AVERage:STATe?")).strip().upper() in ("1", "ON"):
            return "AVERAGE"
        if (await self._query("CALCulate:LIMit:STATe?")).strip().upper() in ("1", "ON"):
            return "PF"
        return "NONE"

    async def set_statistics(self, enabled: bool = True) -> bool:
        await self._write(f"CALCulate:AVERage:STATe {_to_bool_word(enabled)}")
        raw = (await self._query("CALCulate:AVERage:STATe?")).strip().upper()
        return raw in ("1", "ON")

    async def clear_statistics(self) -> None:
        await self._write("CALCulate:AVERage:CLEar")

    async def get_statistics(self) -> Dict[str, Optional[float]]:
        """min / max / average / std / count from CALCulate:AVERage."""
        out: Dict[str, Optional[float]] = {}
        for name, cmd in (
            ("min", "CALCulate:AVERage:MINimum?"),
            ("max", "CALCulate:AVERage:MAXimum?"),
            ("average", "CALCulate:AVERage:AVERage?"),
            ("std", "CALCulate:AVERage:SDEViation?"),
            ("count", "CALCulate:AVERage:COUNt?"),
        ):
            try:
                out[name] = parse_reading(await self._query(cmd))
            except Exception as e:
                logger.debug(f"Statistic {name} unavailable: {e}")
                out[name] = None
        return out

    async def set_rel_offset(self, offset: Union[float, str] = "CURR", enabled: bool = True) -> Dict[str, Any]:
        """Relative (null) measurement on the active function.

        ``offset`` may be a value, or CURR (use the present reading:
        ``NULL:VALue:AUTO ON``), MIN, MAX or DEF.
        """
        func = await self._ensure_function(None)
        if func not in SENSE_ROOTS:
            raise ValueError(f"{func} has no relative (null) function")
        root = SENSE_ROOTS[func]
        if isinstance(offset, str) and offset.strip().upper() == "CURR":
            await self._write(f"{root}:NULL:VALue:AUTO ON")
        else:
            await self._write(f"{root}:NULL:VALue:AUTO OFF")
            await self._write(f"{root}:NULL:VALue {self._lim_or_number(offset)}")
        await self._write(f"{root}:NULL:STATe {_to_bool_word(enabled)}")
        raw = await self._query(f"{root}:NULL:VALue?")
        return {"offset": parse_reading(raw), "enabled": bool(enabled)}

    async def set_limits(self, lower: float, upper: float, enabled: bool = True) -> Dict[str, Any]:
        lower, upper = float(lower), float(upper)
        if lower > upper:
            raise ValueError("lower must be <= upper")
        await self._write("CALCulate:LIMit:CLEar")
        await self._write(f"CALCulate:LIMit:LOWer {_fmt(lower)}")
        await self._write(f"CALCulate:LIMit:UPPer {_fmt(upper)}")
        await self._write(f"CALCulate:LIMit:STATe {_to_bool_word(enabled)}")
        return {"lower": lower, "upper": upper, "enabled": bool(enabled)}

    async def get_limit_result(self) -> str:
        """PASS / FAIL_LOW / FAIL_HIGH / FAIL from the Questionable Data register
        (bit 11 = lower limit failed, bit 12 = upper limit failed)."""
        raw = (await self._query("STATus:QUEStionable:CONDition?")).strip()
        try:
            bits = int(float(raw))
        except ValueError:
            return "UNKNOWN"
        low = bool(bits & (1 << 11))
        high = bool(bits & (1 << 12))
        if low and high:
            return "FAIL"
        if low:
            return "FAIL_LOW"
        if high:
            return "FAIL_HIGH"
        return "PASS"

    async def set_db_reference(self, reference: float, dbm: bool = False) -> float:
        """Reference for the dB (value) or dBm (impedance) scaling operation."""
        node = "DBM" if dbm else "DB"
        await self._write(f"CALCulate:SCALe:{node}:REFerence {_fmt(reference)}")
        return float(await self._query(f"CALCulate:SCALe:{node}:REFerence?"))

    # ------------------------------------------------------------------ #
    # System
    # ------------------------------------------------------------------ #

    async def set_beeper(self, enabled: bool) -> bool:
        await self._write(f"SYSTem:BEEPer:STATe {_to_bool_word(enabled)}")
        raw = (await self._query("SYSTem:BEEPer:STATe?")).strip().upper()
        return raw in ("1", "ON")

    async def beep(self) -> None:
        await self._write("SYSTem:BEEPer:IMMediate")

    async def get_screenshot(self, image_format: str = "PNG") -> bytes:
        """Front-panel screenshot via HCOPy:SDUMp:DATA? (BMP or PNG)."""
        fmt = str(image_format).strip().upper()
        if fmt not in ("BMP", "PNG"):
            raise ValueError("Image format must be BMP or PNG")
        await self._write(f"HCOPy:SDUMp:DATA:FORMat {fmt}")
        return await self._query_binary("HCOPy:SDUMp:DATA?")

    async def get_scpi_version(self) -> str:
        return (await self._query("SYSTem:VERSion?")).strip()

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
        state: Dict[str, Any] = {"model": self._row.get("model", self.MODEL), "function": func}
        for key, coro in (
            ("range", self.get_range(func)),
            ("rate", self.get_rate(func)),
            ("trigger_source", self.get_trigger_source()),
            ("sample_count", self.get_sample_count()),
            ("trigger_count", self.get_trigger_count()),
            ("math_function", self.get_math_function()),
            ("secondary_function", self.get_secondary_function()),
        ):
            try:
                state[key] = await coro
            except Exception as e:
                logger.debug(f"{key} query failed: {e}")
                state[key] = None
        return state


class RigolDM858E(RigolDM858):
    """Rigol DM858E: DM858 with 3 A current, 1 mF capacitance, 20k memory."""

    MODEL = "DM858E"


# Model keywords used by equipment.manager.find_keyword_driver.
RigolDM858E.MODEL_KEYWORDS = ('DM858E',)
RigolDM858.MODEL_KEYWORDS = ('DM858',)
