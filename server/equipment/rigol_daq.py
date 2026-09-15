"""Rigol M300 data acquisition / switch mainframe driver.

Protocol reference: RIGOL "M300 Programming Guide" (Agilent 34970A-style
SCPI).  The mainframe has five slots (channels are ``SCC``: slot 1..5, channel
01..64) and an optional MC3065 DMM module.  Plug-in modules:

    MC3065  DMM module
    MC3120  20-channel multiplexer  (4-wire pairs n / n+10)
    MC3132  32-channel multiplexer  (4-wire pairs n / n+16)
    MC3164  64-channel single-ended multiplexer (no 4-wire, no current)
    MC3324  20 voltage + 4 current channel multiplexer (21..24 = current)
    MC3416  16-channel actuator
    MC3534  multifunction (1-4 DIO, 5-8 totalizer, 9-12 DAC)
    MC3648  4x8 matrix switch (channel = row/column, e.g. 126)

Key quirks (all from the programming guide):
- ``CONFigure:...,(@list)`` *overwrites* the scan list with ``(@list)``; the
  driver re-sends ``ROUTe:SCAN`` after every ``configure_channel``.
- The instrument stores/scans channels in ascending slot/channel order
  regardless of the order given; ``READ?``/``FETCh?`` values are mapped to the
  sorted scan list.
- ``ROUTe:SCAN?`` answers as a definite-length block: ``#214(@203,204,205)``.
- Overload is reported as ``±9.9E+37``.
- ``ROUTe:CLOSe/OPEN`` on a multiplexer channel that is in the scan list is an
  error.
- ``SYSTem:CTYPe? <slot>`` takes 100..500 and answers
  ``RIGOL TECHNOLOGIES,MC3132,<serial>,<fw>`` or ``RIGOL TECHNOLOGIES,0,0,0``.

``*IDN?`` -> ``RIGOL TECHNOLOGIES,M300,<serial>,<firmware>``.
"""

import asyncio
import logging
import math
import re
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from shared.models.data import DataAcquisitionData
from shared.models.equipment import EquipmentInfo, EquipmentStatus, EquipmentType

from .base import BaseEquipment, generate_equipment_id

logger = logging.getLogger(__name__)

_OVERLOAD_THRESHOLD = 9.0e37
_NUMBER_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

# Module model -> description (M300 Programming Guide, "Document Overview").
MODULE_TABLE: Dict[str, Dict[str, Any]] = {
    "MC3065": {"description": "DMM module", "kind": "dmm", "channels": 0},
    "MC3120": {"description": "20-channel multiplexer", "kind": "mux", "channels": 20,
               "four_wire_offset": 10, "functions": ["DCV", "ACV", "RES", "FRES", "TEMP", "FREQ", "PER"]},
    "MC3132": {"description": "32-channel multiplexer", "kind": "mux", "channels": 32,
               "four_wire_offset": 16, "functions": ["DCV", "ACV", "RES", "FRES", "TEMP", "FREQ", "PER"]},
    "MC3164": {"description": "64-channel single-ended multiplexer", "kind": "mux", "channels": 64,
               "four_wire_offset": None, "functions": ["DCV", "ACV", "RES", "TEMP", "FREQ", "PER"]},
    "MC3324": {"description": "20 voltage + 4 current channel multiplexer", "kind": "mux", "channels": 24,
               "four_wire_offset": 10, "current_channels": [21, 22, 23, 24],
               "functions": ["DCV", "ACV", "DCI", "ACI", "RES", "FRES", "TEMP", "FREQ", "PER"]},
    "MC3416": {"description": "16-channel actuator", "kind": "actuator", "channels": 16},
    "MC3534": {"description": "Multifunction module (DIO/TOT/DAC)", "kind": "multifunction", "channels": 12},
    "MC3648": {"description": "4x8 matrix switch", "kind": "matrix", "channels": 32,
               "matrix": (4, 8)},
}

SLOTS = (1, 2, 3, 4, 5)

# Canonical function -> CONFigure root, unit
FUNCTIONS: Dict[str, Dict[str, str]] = {
    "DCV": {"cmd": "CONFigure:VOLTage:DC", "unit": "V"},
    "ACV": {"cmd": "CONFigure:VOLTage:AC", "unit": "V"},
    "DCI": {"cmd": "CONFigure:CURRent:DC", "unit": "A"},
    "ACI": {"cmd": "CONFigure:CURRent:AC", "unit": "A"},
    "RES": {"cmd": "CONFigure:RESistance", "unit": "Ohm"},
    "FRES": {"cmd": "CONFigure:FRESistance", "unit": "Ohm"},
    "FREQ": {"cmd": "CONFigure:FREQuency", "unit": "Hz"},
    "PER": {"cmd": "CONFigure:PERiod", "unit": "s"},
    "TEMP": {"cmd": "CONFigure:TEMPerature", "unit": "C"},
}

# Standard ranges (full scale) per function from the CONFigure sections.
RANGES: Dict[str, List[float]] = {
    "DCV": [0.2, 2.0, 20.0, 200.0, 300.0],
    "ACV": [0.2, 2.0, 20.0, 200.0, 300.0],
    "DCI": [200e-6, 2e-3, 20e-3, 200e-3, 1.0],
    "ACI": [200e-6, 2e-3, 20e-3, 200e-3, 1.0],
    "RES": [200.0, 2e3, 20e3, 200e3, 1e6, 10e6, 100e6],
    "FRES": [200.0, 2e3, 20e3, 200e3, 1e6, 10e6, 100e6],
}

_FUNCTION_ALIASES: Dict[str, str] = {
    "VOLT": "DCV", "VOLT:DC": "DCV", "VOLTAGE:DC": "DCV", "VDC": "DCV", "VOLTAGE": "DCV", "V": "DCV",
    "VOLT:AC": "ACV", "VOLTAGE:AC": "ACV", "VAC": "ACV",
    "CURR": "DCI", "CURR:DC": "DCI", "CURRENT:DC": "DCI", "IDC": "DCI", "CURRENT": "DCI",
    "CURR:AC": "ACI", "CURRENT:AC": "ACI", "IAC": "ACI",
    "RES": "RES", "RESISTANCE": "RES", "2WR": "RES", "OHM": "RES", "OHMS": "RES",
    "FRES": "FRES", "FRESISTANCE": "FRES", "4WR": "FRES",
    "FREQ": "FREQ", "FREQUENCY": "FREQ",
    "PER": "PER", "PERIOD": "PER", "PERI": "PER",
    "TEMP": "TEMP", "TEMPERATURE": "TEMP",
}

_SENSORS = {
    "TC": "TCouple", "TCOUPLE": "TCouple", "THERMOCOUPLE": "TCouple",
    "THER": "THERmistor", "THERMISTOR": "THERmistor",
    "RTD": "RTD", "FRTD": "FRTD", "RTD4": "FRTD", "4RTD": "FRTD",
}
_SENSOR_DEFAULT_TYPE = {"TCouple": "J", "THERmistor": "5000", "RTD": "85", "FRTD": "85"}
_TC_TYPES = {"B", "E", "J", "K", "N", "R", "S", "T"}

_TRIGGER_SOURCES = {
    "IMM": "IMMediate", "IMMEDIATE": "IMMediate", "AUTO": "IMMediate",
    "TIM": "TIMer", "TIMER": "TIMer", "INTERVAL": "TIMer",
    "BUS": "BUS", "MANUAL": "BUS", "MAN": "BUS",
    "EXT": "EXTernal", "EXTERNAL": "EXTernal",
    "ABS": "ABSolute", "ABSOLUTE": "ABSolute",
    "ALARM1": "ALARm1", "ALARM2": "ALARm2", "ALARM3": "ALARm3", "ALARM4": "ALARm4",
    "ALAR1": "ALARm1", "ALAR2": "ALARm2", "ALAR3": "ALARm3", "ALAR4": "ALARm4",
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def normalize_function(function: str) -> str:
    key = str(function).strip().upper().replace("_", ":")
    key = _FUNCTION_ALIASES.get(key, key)
    if key not in FUNCTIONS:
        raise ValueError(f"Unknown DAQ function '{function}'. Valid: {', '.join(FUNCTIONS)}")
    return key


def normalize_channel(channel: Union[str, int]) -> str:
    """``101`` / ``"101"`` / ``"@101"`` / ``"CH101"`` -> ``"101"``."""
    text = str(channel).strip().upper()
    text = text.replace("(", "").replace(")", "").replace("@", "")
    if text.startswith("CH"):
        text = text[2:]
    if not text.isdigit() or not 3 <= len(text) <= 3:
        raise ValueError(f"Invalid channel '{channel}' (expected SCC, e.g. 101)")
    slot = int(text[0])
    if slot not in SLOTS:
        raise ValueError(f"Invalid channel '{channel}': slot must be 1..5")
    return text


def expand_channel_list(spec: Union[str, int, Iterable[Union[str, int]]]) -> List[str]:
    """Expand ``"101:103,301"``, ``"(@101:103)"``, ``["101","102"]`` -> ["101","102","103","301"]."""
    if isinstance(spec, (str, int)):
        items: List[str] = [str(spec)]
    else:
        items = [str(s) for s in spec]
    out: List[str] = []
    for item in items:
        text = item.strip().replace("(", "").replace(")", "").replace("@", "")
        for part in text.split(","):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                lo, hi = part.split(":", 1)
                lo_c, hi_c = normalize_channel(lo), normalize_channel(hi)
                if lo_c[0] != hi_c[0]:
                    raise ValueError(f"Channel range {part} must stay within one slot")
                a, b = int(lo_c), int(hi_c)
                step = 1 if b >= a else -1
                out.extend(str(c) for c in range(a, b + step, step))
            else:
                out.append(normalize_channel(part))
    seen = set()
    unique = []
    for c in out:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def format_channel_list(channels: Union[str, int, Iterable[Union[str, int]]]) -> str:
    """Build the SCPI channel list ``(@101,102)``; contiguous runs become ``101:110``."""
    chans = expand_channel_list(channels)
    if not chans:
        return "(@)"
    nums = [int(c) for c in chans]
    parts: List[str] = []
    i = 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1 and str(nums[j + 1])[0] == str(nums[i])[0]:
            j += 1
        if j - i >= 2:
            parts.append(f"{nums[i]}:{nums[j]}")
        else:
            parts.extend(str(n) for n in nums[i:j + 1])
        i = j + 1
    return f"(@{','.join(parts)})"


def parse_channel_list_response(raw: str) -> List[str]:
    """Parse ``#214(@203,204,205)`` / ``(@101:103)`` into ["203","204","205"]."""
    text = raw.strip()
    if text.startswith("#"):
        try:
            ndig = int(text[1])
            text = text[2 + ndig:]
        except (ValueError, IndexError):
            pass
    text = text.strip()
    if text in ("", "(@)", "()"):
        return []
    return expand_channel_list(text)


def parse_reading(text: str) -> Optional[float]:
    text = text.strip().strip('"')
    m = _NUMBER_RE.search(text)
    if not m:
        return None
    value = float(m.group(0))
    if math.isnan(value) or math.isinf(value) or abs(value) >= _OVERLOAD_THRESHOLD:
        return None
    return value


def parse_readings(raw: str) -> List[Optional[float]]:
    return [parse_reading(p) for p in raw.strip().split(",") if p.strip()]


def _bool_word(enabled: bool) -> str:
    return "ON" if enabled else "OFF"


def _fmt_num(value: Union[float, int, str]) -> str:
    if isinstance(value, str):
        key = value.strip().upper()
        if key in ("AUTO", "MIN", "MAX", "DEF"):
            return key
        return f"{float(key):g}"
    return f"{float(value):g}"


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #


class RigolM300(BaseEquipment):
    """Rigol M300 mainframe with MC3xxx plug-in modules."""

    MODEL = "M300"
    INTERFACES: Sequence[str] = ("USB", "LAN", "GPIB", "RS232")
    SERIAL_BAUD = 9600
    MAX_READINGS = 100000
    MAX_TRIGGER_COUNT = 50000
    SCAN_TIMEOUT_MS = 60000

    def __init__(self, resource_manager, resource_string: str):
        super().__init__(resource_manager, resource_string)
        self.manufacturer = "Rigol"
        self.model = self.MODEL
        self.serial_number: Optional[str] = None
        self.firmware_version: Optional[str] = None
        self._modules: Dict[int, Dict[str, Any]] = {}
        self._dmm_installed: Optional[bool] = None
        self._scan_list: List[str] = []
        self._channel_config: Dict[str, Dict[str, Any]] = {}
        self._temp_units: Dict[str, str] = {}
        self._last_scan: Optional[DataAcquisitionData] = None
        #: When the last scan landed, on the monotonic clock. A wall
        #: clock steps under an NTP correction, so an age computed
        #: from it can come out negative; on Windows it also resolves
        #: only to the 15.6 ms tick, which is coarser than a scan.
        self._last_scan_time: float = 0.0
        self._consumed: set = set()
        # Serialises multi-command sequences; BaseEquipment on newer branches already
        # provides a reentrant lock of this name, so only create one if it is missing.
        if not hasattr(self, "_io_lock"):
            self._io_lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Connection / identity
    # ------------------------------------------------------------------ #

    async def connect(self):
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
                upper = self.resource_string.upper()
                if "ASRL" in upper or "COM" in upper:
                    self.instrument.baud_rate = self.SERIAL_BAUD
                    self.instrument.data_bits = 8
                    self.instrument.parity = 0
                    self.instrument.stop_bits = 10
                    self.instrument.flow_control = 0
                    self.instrument.read_termination = "\n"
                    self.instrument.write_termination = "\n"
                else:
                    try:
                        self.instrument.read_termination = "\n"
                        self.instrument.write_termination = "\n"
                    except Exception:
                        pass
                self.instrument.timeout = 15000

                idn = await self._query("*IDN?")
                logger.info(f"Connected to Rigol M300: {idn}")
                self._parse_idn(idn)
                self.connected = True
                self.cached_info = await self.get_info()
                await self._post_connect()
            except Exception as e:
                logger.error(f"Failed to connect to {self.resource_string}: {e}")
                self.connected = False
                raise
            finally:
                self._is_connecting = False

    async def _post_connect(self):
        # Plain numeric readings so READ?/FETCh? parse deterministically.
        for cmd in ("FORMat:READing:UNIT OFF", "FORMat:READing:TIME OFF",
                    "FORMat:READing:CHANnel OFF", "FORMat:READing:ALARm OFF"):
            try:
                await self._write(cmd)
            except Exception as e:  # pragma: no cover - defensive
                logger.debug(f"{cmd} failed: {e}")
        try:
            await self.get_modules()
        except Exception as e:
            logger.debug(f"Module inventory failed: {e}")
        try:
            self._scan_list = await self.get_scan_list()
        except Exception as e:
            logger.debug(f"Scan list query failed: {e}")

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

    async def get_info(self) -> EquipmentInfo:
        idn = await self._query("*IDN?")
        info = self._parse_idn(idn)
        return EquipmentInfo(
            id=generate_equipment_id(self.resource_string, "daq_"),
            type=EquipmentType.DATA_ACQUISITION,
            manufacturer=info["manufacturer"] or self.manufacturer,
            model=info["model"] or self.model,
            serial_number=info["serial"],
            connection_type=self._determine_connection_type(),
            resource_string=self.resource_string,
        )

    def _capabilities(self) -> Dict[str, Any]:
        return {
            "slots": list(SLOTS),
            "modules": {str(slot): dict(info) for slot, info in self._modules.items()},
            "module_table": {k: dict(v) for k, v in MODULE_TABLE.items()},
            "dmm_installed": self._dmm_installed,
            "functions": list(FUNCTIONS),
            "ranges": {k: list(v) for k, v in RANGES.items()},
            "temperature_sensors": ["TC", "THER", "RTD", "FRTD"],
            "thermocouple_types": sorted(_TC_TYPES),
            "trigger_sources": ["IMM", "TIMER", "BUS", "EXT", "ABS", "ALARM1", "ALARM2", "ALARM3", "ALARM4"],
            "max_readings": self.MAX_READINGS,
            "max_trigger_count": self.MAX_TRIGGER_COUNT,
            "scan_list": list(self._scan_list),
            "interfaces": list(self.INTERFACES),
            "supports_acquisition": True,
        }

    async def get_status(self) -> EquipmentStatus:
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
    # Dispatch
    # ------------------------------------------------------------------ #

    async def execute_command(self, command: str, parameters: dict) -> Any:
        parameters = dict(parameters or {})
        handlers = {
            "get_modules": self.get_modules,
            "configure_channel": self.configure_channel,
            "get_configuration": self.get_configuration,
            "set_scan_list": self.set_scan_list,
            "get_scan_list": self.get_scan_list,
            "scan": self.scan,
            "fetch": self.fetch,
            "read_channel": self.read_channel,
            "close_channel": self.close_channel,
            "open_channel": self.open_channel,
            "get_closed_channels": self.get_closed_channels,
            "set_trigger": self.set_trigger,
            "get_trigger": self.get_trigger,
            "trigger": self.trigger,
            "abort": self.abort,
            "set_temperature_unit": self.set_temperature_unit,
            "get_data_points": self.get_data_points,
            "remove_data": self.remove_data,
            "set_dmm_enabled": self.set_dmm_enabled,
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
    # Modules
    # ------------------------------------------------------------------ #

    async def get_modules(self, refresh: bool = True) -> Dict[int, Dict[str, Any]]:
        """Inventory slots 1..5 with ``SYSTem:CTYPe? <slot>00``."""
        if self._modules and not refresh:
            return self._modules
        modules: Dict[int, Dict[str, Any]] = {}
        for slot in SLOTS:
            raw = (await self._query(f"SYSTem:CTYPe? {slot}00")).strip()
            parts = [p.strip() for p in raw.split(",")]
            model = parts[1].upper() if len(parts) > 1 else ""
            if not model or model == "0":
                continue
            table = MODULE_TABLE.get(model, {"description": "Unknown module", "kind": "unknown", "channels": 0})
            modules[slot] = {
                "slot": slot,
                "model": model,
                "serial": parts[2] if len(parts) > 2 and parts[2] != "0" else None,
                "firmware": parts[3] if len(parts) > 3 and parts[3] != "0" else None,
                "description": table["description"],
                "kind": table["kind"],
                "channels": table["channels"],
                "functions": list(table.get("functions", [])),
            }
        self._modules = modules
        try:
            self._dmm_installed = (await self._query("INSTrument:DMM:INSTalled?")).strip() in ("1", "ON")
        except Exception as e:
            logger.debug(f"DMM installed query failed: {e}")
        return modules

    def _module_for_channel(self, channel: str) -> Optional[Dict[str, Any]]:
        return self._modules.get(int(channel[0]))

    def _module_channels(self, slot: int) -> List[str]:
        info = self._modules.get(slot)
        if not info:
            return []
        if info["kind"] == "matrix":
            rows, cols = MODULE_TABLE["MC3648"]["matrix"]
            return [f"{slot}{r}{c}" for r in range(1, rows + 1) for c in range(1, cols + 1)]
        return [f"{slot}{ch:02d}" for ch in range(1, info["channels"] + 1)]

    async def set_dmm_enabled(self, enabled: bool = True) -> bool:
        await self._write(f"INSTrument:DMM {_bool_word(enabled)}")
        return (await self._query("INSTrument:DMM?")).strip() in ("1", "ON")

    # ------------------------------------------------------------------ #
    # Channel configuration
    # ------------------------------------------------------------------ #

    def _validate_function_for_channel(self, channel: str, func: str) -> None:
        info = self._module_for_channel(channel)
        if info is None:
            return  # unknown inventory; let the instrument decide
        if info["kind"] != "mux":
            raise ValueError(f"Channel {channel} is on a {info['model']} ({info['description']}), not a multiplexer")
        table = MODULE_TABLE.get(info["model"], {})
        allowed = table.get("functions")
        if allowed and func not in allowed:
            raise ValueError(f"{info['model']} does not support {func}; valid: {', '.join(allowed)}")
        current_channels = table.get("current_channels")
        ch_no = int(channel[1:])
        if current_channels is not None:
            if func in ("DCI", "ACI") and ch_no not in current_channels:
                raise ValueError(f"On {info['model']} current is only measured on channels {current_channels}")
            if func not in ("DCI", "ACI") and ch_no in current_channels:
                raise ValueError(f"Channels {current_channels} of {info['model']} are current-only")
        elif func in ("DCI", "ACI"):
            raise ValueError(f"{info['model']} has no current channels")
        offset = table.get("four_wire_offset")
        if func == "FRES" and offset and ch_no > offset:
            raise ValueError(f"4-wire on {info['model']} uses channels 1..{offset} (paired with n+{offset})")

    async def configure_channel(
        self,
        channel: Union[str, int, Sequence[Union[str, int]]],
        function: str = "DCV",
        range: Optional[Union[float, str]] = None,
        resolution: Optional[Union[float, str]] = None,
        sensor: Optional[str] = None,
        sensor_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """``CONFigure:<func> [range[,resolution],](@ch)``; TEMP takes sensor/sensor_type.

        The instrument replaces the scan list with ``(@ch)``, so the previously
        set scan list is restored afterwards.
        """
        func = normalize_function(function)
        chans = expand_channel_list(channel)
        if not chans:
            raise ValueError("At least one channel is required")
        for ch in chans:
            self._validate_function_for_channel(ch, func)
        ch_list = format_channel_list(chans)
        unit = FUNCTIONS[func]["unit"]
        cfg: Dict[str, Any] = {"function": func, "range": range, "resolution": resolution, "unit": unit}

        if func == "TEMP":
            probe = _SENSORS.get(str(sensor or "TC").strip().upper())
            if probe is None:
                raise ValueError("sensor must be TC, THER, RTD or FRTD")
            stype = str(sensor_type or _SENSOR_DEFAULT_TYPE[probe]).strip().upper()
            if probe == "TCouple" and stype not in _TC_TYPES:
                raise ValueError(f"Thermocouple type must be one of {sorted(_TC_TYPES)}")
            if probe == "THERmistor" and stype not in ("2252", "3000", "5000", "10000", "30000"):
                raise ValueError("Thermistor type must be 2252, 3000, 5000, 10000 or 30000")
            if probe in ("RTD", "FRTD") and stype not in ("85", "89", "91", "92"):
                raise ValueError("RTD type must be 85, 89, 91 or 92")
            if probe == "FRTD":
                for ch in chans:
                    info = self._module_for_channel(ch)
                    if info and MODULE_TABLE.get(info["model"], {}).get("four_wire_offset") is None:
                        raise ValueError(f"{info['model']} does not support 4-wire RTD")
            # "1" stands in for <range>; resolution is accepted but ignored.
            await self._write(f"{FUNCTIONS[func]['cmd']} {probe},{stype},1,DEF,{ch_list}")
            cfg.update({"sensor": probe, "sensor_type": stype, "range": None, "resolution": None})
            for ch in chans:
                cfg_unit = self._temp_units.get(ch, "C")
                self._channel_config[ch] = dict(cfg, unit=cfg_unit)
        else:
            args = []
            if range is not None:
                args.append(_fmt_num(range))
                if resolution is not None:
                    args.append(_fmt_num(resolution))
            elif resolution is not None:
                args.extend(["AUTO", _fmt_num(resolution)])
            prefix = ",".join(args) + "," if args else ""
            await self._write(f"{FUNCTIONS[func]['cmd']} {prefix}{ch_list}")
            for ch in chans:
                self._channel_config[ch] = dict(cfg)

        # CONFigure overwrote the scan list; put ours back.
        if self._scan_list:
            await self._write(f"ROUTe:SCAN {format_channel_list(self._scan_list)}")
        self._last_scan = None
        return {"channels": chans, **cfg}

    async def get_configuration(self, channels: Optional[Union[str, Sequence[str]]] = None) -> Dict[str, Dict[str, Any]]:
        """``CONFigure? (@list)`` -> {channel: {function, range, resolution, unit}}."""
        chans = expand_channel_list(channels) if channels is not None else list(self._scan_list)
        if not chans:
            return {}
        raw = await self._query(f"CONFigure? {format_channel_list(chans)}")
        entries = [e.strip().strip('"') for e in re.findall(r'"([^"]*)"', raw)] or [raw.strip().strip('"')]
        out: Dict[str, Dict[str, Any]] = {}
        for ch, entry in zip(chans, entries):
            tokens = entry.replace(",", " ").split()
            func_token = tokens[0].upper() if tokens else ""
            func = _FUNCTION_ALIASES.get(func_token, func_token)
            cfg: Dict[str, Any] = {"function": func if func in FUNCTIONS else func_token, "raw": entry}
            nums = [float(t) for t in tokens[1:] if _NUMBER_RE.fullmatch(t)]
            if func == "TEMP":
                cfg["sensor"] = tokens[1] if len(tokens) > 1 else None
                cfg["sensor_type"] = tokens[2] if len(tokens) > 2 else None
                cfg["unit"] = self._temp_units.get(ch, "C")
            else:
                cfg["range"] = nums[0] if nums else None
                cfg["resolution"] = nums[1] if len(nums) > 1 else None
                cfg["unit"] = FUNCTIONS.get(func, {}).get("unit", "")
            out[ch] = cfg
            self._channel_config.setdefault(ch, {}).update(cfg)
        return out

    async def set_temperature_unit(self, unit: str = "C",
                                   channels: Optional[Union[str, Sequence[str]]] = None) -> str:
        key = str(unit).strip().upper().replace("°", "")
        key = {"CELSIUS": "C", "FAHRENHEIT": "F", "KELVIN": "K"}.get(key, key)
        if key not in ("C", "F", "K"):
            raise ValueError("Temperature unit must be C, F or K")
        chans = expand_channel_list(channels) if channels is not None else list(self._scan_list)
        suffix = f",{format_channel_list(chans)}" if chans else ""
        await self._write(f"UNIT:TEMPerature {key}{suffix}")
        for ch in chans:
            self._temp_units[ch] = key
            if ch in self._channel_config and self._channel_config[ch].get("function") == "TEMP":
                self._channel_config[ch]["unit"] = key
        return key

    # ------------------------------------------------------------------ #
    # Scan list / scanning
    # ------------------------------------------------------------------ #

    async def set_scan_list(self, channels: Union[str, Sequence[Union[str, int]]]) -> List[str]:
        chans = expand_channel_list(channels)
        await self._write(f"ROUTe:SCAN {format_channel_list(chans)}")
        self._scan_list = await self.get_scan_list()
        self._last_scan = None
        return self._scan_list

    async def get_scan_list(self) -> List[str]:
        raw = await self._query("ROUTe:SCAN?")
        chans = parse_channel_list_response(raw)
        # The mainframe always scans in ascending channel order.
        self._scan_list = sorted(chans, key=int)
        return list(self._scan_list)

    def _unit_for(self, ch: str) -> str:
        cfg = self._channel_config.get(ch)
        if cfg:
            return cfg.get("unit", "")
        return ""

    def _build_data(self, values: List[Optional[float]], chans: List[str]) -> DataAcquisitionData:
        readings: Dict[str, float] = {}
        units: Dict[str, str] = {}
        functions: Dict[str, str] = {}
        # No values yet (INITiate without READ?/FETCh?) -> empty readings, not NaNs.
        for i, ch in enumerate(chans if values else []):
            v = values[i] if i < len(values) else None
            readings[ch] = float("nan") if v is None else v
            units[ch] = self._unit_for(ch)
            functions[ch] = self._channel_config.get(ch, {}).get("function", "")
        return DataAcquisitionData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            readings=readings,
            units=units,
            functions=functions,
            scan_list=list(chans),
            installed_modules={str(s): m["model"] for s, m in self._modules.items()},
        )

    async def _query_long(self, cmd: str) -> str:
        old = self.instrument.timeout if self.instrument is not None else None
        if self.instrument is not None:
            self.instrument.timeout = self.SCAN_TIMEOUT_MS
        try:
            return await self._query(cmd)
        finally:
            if self.instrument is not None and old is not None:
                self.instrument.timeout = old

    async def scan(self, wait: bool = True) -> DataAcquisitionData:
        """Run one scan of the scan list.

        ``wait=True``: ``READ?`` (blocks until the scan is done, returns values).
        ``wait=False``: ``INITiate`` only; call ``fetch()`` later.  The returned
        object then has an empty ``readings`` dict.
        """
        async with self._io_lock:
            if not self._scan_list:
                self._scan_list = await self.get_scan_list()
            if not self._scan_list:
                raise ValueError("Scan list is empty; call set_scan_list first")
            chans = list(self._scan_list)
            if not wait:
                await self._write("INITiate")
                return self._build_data([], chans)
            values = parse_readings(await self._query_long("READ?"))
            data = self._build_data(values, chans)
            self._last_scan = data
            self._last_scan_time = time.perf_counter()
            self._consumed.clear()
            return data

    async def fetch(self) -> DataAcquisitionData:
        """``FETCh?`` the readings of the most recent (or running) scan."""
        async with self._io_lock:
            chans = list(self._scan_list) or await self.get_scan_list()
            values = parse_readings(await self._query_long("FETCh?"))
            data = self._build_data(values, chans)
            self._last_scan = data
            self._last_scan_time = time.perf_counter()
            self._consumed.clear()
            return data

    async def read_channel(self, channel: Union[str, int]) -> Dict[str, Any]:
        """Read one channel now (temporarily makes it the scan list)."""
        ch = normalize_channel(channel)
        async with self._io_lock:
            saved = list(self._scan_list)
            await self._write(f"ROUTe:SCAN {format_channel_list([ch])}")
            try:
                values = parse_readings(await self._query_long("READ?"))
            finally:
                if saved and saved != [ch]:
                    await self._write(f"ROUTe:SCAN {format_channel_list(saved)}")
                self._scan_list = saved
        value = values[0] if values else None
        return {
            "channel": ch,
            "value": float("nan") if value is None else value,
            "overload": value is None,
            "unit": self._unit_for(ch),
            "function": self._channel_config.get(ch, {}).get("function", ""),
        }

    async def trigger(self) -> None:
        """Software trigger (``*TRG``) for TRIGger:SOURce BUS."""
        await self._write("*TRG")

    async def abort(self) -> None:
        await self._write("ABORt")

    async def get_data_points(self) -> int:
        return int(float((await self._query("DATA:POINts?")).strip()))

    async def remove_data(self, count: int) -> List[Optional[float]]:
        count = int(count)
        if count < 1:
            raise ValueError("count must be >= 1")
        return parse_readings(await self._query(f"DATA:REMove? {count}"))

    # ------------------------------------------------------------------ #
    # Switch modules
    # ------------------------------------------------------------------ #

    def _check_switch_channels(self, chans: List[str]) -> None:
        for ch in chans:
            if ch in self._scan_list:
                raise ValueError(f"Channel {ch} is in the scan list; remove it before switching it manually")
            info = self._module_for_channel(ch)
            if info and info["kind"] not in ("mux", "actuator", "matrix", "unknown"):
                raise ValueError(f"Channel {ch} is on a {info['model']} which has no relays to switch")

    async def close_channel(self, channels: Union[str, int, Sequence[Union[str, int]]]) -> Dict[str, bool]:
        chans = expand_channel_list(channels)
        self._check_switch_channels(chans)
        await self._write(f"ROUTe:CLOSe {format_channel_list(chans)}")
        return await self._closed_state(chans)

    async def open_channel(self, channels: Union[str, int, Sequence[Union[str, int]]]) -> Dict[str, bool]:
        chans = expand_channel_list(channels)
        self._check_switch_channels(chans)
        await self._write(f"ROUTe:OPEN {format_channel_list(chans)}")
        return await self._closed_state(chans)

    async def _closed_state(self, chans: List[str]) -> Dict[str, bool]:
        raw = await self._query(f"ROUTe:CLOSe? {format_channel_list(chans)}")
        flags = [p.strip() in ("1", "ON") for p in raw.split(",") if p.strip()]
        return {ch: (flags[i] if i < len(flags) else False) for i, ch in enumerate(chans)}

    async def get_closed_channels(self, channels: Optional[Union[str, Sequence[str]]] = None) -> List[str]:
        """Closed relays among ``channels`` (default: every switchable module channel)."""
        if channels is not None:
            chans = expand_channel_list(channels)
        else:
            if not self._modules:
                await self.get_modules()
            chans = []
            for slot, info in self._modules.items():
                if info["kind"] in ("mux", "actuator", "matrix"):
                    chans.extend(c for c in self._module_channels(slot) if c not in self._scan_list)
        closed: List[str] = []
        for slot in sorted({int(c[0]) for c in chans}):
            group = [c for c in chans if int(c[0]) == slot]
            try:
                state = await self._closed_state(group)
            except Exception as e:
                logger.debug(f"ROUTe:CLOSe? failed for slot {slot}: {e}")
                continue
            closed.extend(ch for ch, is_closed in state.items() if is_closed)
        return closed

    # ------------------------------------------------------------------ #
    # Trigger
    # ------------------------------------------------------------------ #

    async def set_trigger(self, source: str = "IMM", count: Optional[Union[int, str]] = None,
                          interval: Optional[float] = None) -> Dict[str, Any]:
        word = _TRIGGER_SOURCES.get(str(source).strip().upper())
        if word is None:
            raise ValueError("Trigger source must be IMM, TIMER, BUS, EXT, ABS or ALARM1..4")
        await self._write(f"TRIGger:SOURce {word}")
        if count is not None:
            if isinstance(count, str) and count.strip().upper() in ("INF", "INFINITY", "INFINITE"):
                await self._write("TRIGger:COUNt INFinity")
            else:
                n = int(count)
                if not 1 <= n <= self.MAX_TRIGGER_COUNT:
                    raise ValueError(f"Trigger count must be 1..{self.MAX_TRIGGER_COUNT} or INFINITY")
                await self._write(f"TRIGger:COUNt {n}")
        if interval is not None:
            interval = float(interval)
            if not 0 <= interval <= 359999.999:
                raise ValueError("Trigger interval must be 0..359999.999 s")
            await self._write(f"TRIGger:TIMer {interval:g}")
        return await self.get_trigger()

    async def get_trigger(self) -> Dict[str, Any]:
        source = (await self._query("TRIGger:SOURce?")).strip().upper()
        raw_count = float((await self._query("TRIGger:COUNt?")).strip())
        count: Union[int, str] = "INFINITY" if raw_count >= _OVERLOAD_THRESHOLD else int(raw_count)
        interval = float((await self._query("TRIGger:TIMer?")).strip())
        return {"source": source, "count": count, "interval": interval}

    # ------------------------------------------------------------------ #
    # Integration hooks
    # ------------------------------------------------------------------ #

    async def get_readings(self) -> DataAcquisitionData:
        """Last scan result, or a fresh scan when none is cached."""
        if self._last_scan is not None:
            return self._last_scan
        return await self.scan()

    async def get_measurement(self, channel: str = "101") -> Dict[str, Any]:
        """Acquisition hook: ``channel`` is ``101`` / ``CH101`` / ``@101``.

        Channels in the scan list share one scan per polling cycle (a new scan
        runs once a cached value has been consumed); other channels are read
        individually with ``read_channel``.
        """
        ch = normalize_channel(channel)
        if ch in self._scan_list:
            if self._last_scan is None or ch in self._consumed or ch not in self._last_scan.readings:
                await self.scan()
            self._consumed.add(ch)
            value = self._last_scan.readings.get(ch, float("nan")) if self._last_scan else float("nan")
            return {
                "value": value,
                "unit": self._unit_for(ch),
                "function": self._channel_config.get(ch, {}).get("function", ""),
                "channel": ch,
                "overload": value != value,
            }
        return await self.read_channel(ch)

    async def get_measurements(self, channel: Any = 1) -> Dict[str, Any]:
        data = await self.get_readings()
        out: Dict[str, Any] = dict(data.readings)
        for ch, unit in data.units.items():
            out[f"{ch}_unit"] = unit
        return out

    async def get_state(self) -> Dict[str, Any]:
        state: Dict[str, Any] = {
            "scan_list": list(self._scan_list),
            "channels": {ch: dict(cfg) for ch, cfg in self._channel_config.items()},
            "modules": {str(s): m["model"] for s, m in self._modules.items()},
            "temperature_units": dict(self._temp_units),
        }
        try:
            state["trigger"] = await self.get_trigger()
        except Exception:
            state["trigger"] = None
        return state

    async def reset(self) -> None:
        """``*RST`` clears the scan list and all channel configuration."""
        await self._write("*RST")
        await asyncio.sleep(0.5)
        self._scan_list.clear()
        self._channel_config.clear()
        self._temp_units.clear()
        self._last_scan = None
        self._consumed.clear()
        await self._post_connect()

    async def get_error(self) -> Dict[str, Any]:
        raw = await self._query("SYSTem:ERRor?")
        code_str, _, message = raw.partition(",")
        try:
            code = int(float(code_str.strip()))
        except ValueError:
            code = None
        return {"code": code, "message": message.strip().strip('"'), "raw": raw}


# Model keywords used by equipment.manager.find_keyword_driver.
RigolM300.MODEL_KEYWORDS = ('M300',)
