"""Mock digital multimeter for testing without hardware.

Behaves like a Rigol DM3058/DM3068 driven through the RIGOL command set:
same command names, same MultimeterData readings, same channel naming for
the acquisition engine. Simulated inputs can be set per function so tests
and demos get deterministic (plus optional noise) values.
"""

import asyncio
import logging
import math
import uuid
from typing import Any, Dict, List, Optional, Union

import numpy as np

from shared.models.data import MultimeterData
from shared.models.equipment import (ConnectionType, EquipmentInfo,
                                     EquipmentStatus, EquipmentType,
                                     MultimeterFunction)

logger = logging.getLogger(__name__)

_UNITS = {
    "DCV": "V", "ACV": "V", "DCI": "A", "ACI": "A", "RES": "Ohm", "FRES": "Ohm",
    "FREQ": "Hz", "PER": "s", "CAP": "F", "CONT": "Ohm", "DIODE": "V",
}
_RANGES: Dict[str, List[float]] = {
    "DCV": [0.2, 2.0, 20.0, 200.0, 1000.0],
    "ACV": [0.2, 2.0, 20.0, 200.0, 750.0],
    "DCI": [200e-6, 2e-3, 20e-3, 200e-3, 2.0, 10.0],
    "ACI": [200e-6, 2e-3, 20e-3, 200e-3, 2.0, 10.0],
    "RES": [200.0, 2e3, 20e3, 200e3, 1e6, 10e6, 100e6],
    "FRES": [200.0, 2e3, 20e3, 200e3, 1e6, 10e6, 100e6],
    "FREQ": [0.2, 2.0, 20.0, 200.0, 750.0],
    "PER": [0.2, 2.0, 20.0, 200.0, 750.0],
    "CAP": [2e-9, 20e-9, 200e-9, 2e-6, 20e-6, 200e-6, 2e-3, 20e-3, 100e-3],
}
_RATE_ALIASES = {"F": "FAST", "FAST": "FAST", "M": "MEDIUM", "MEDIUM": "MEDIUM", "S": "SLOW", "SLOW": "SLOW"}
_FRIENDLY = {
    "VDC": "DCV", "VAC": "ACV", "IDC": "DCI", "IAC": "ACI", "OHM": "RES", "OHMS": "RES",
    "2WR": "RES", "4WR": "FRES", "PERIOD": "PER", "PERI": "PER", "CAPACITANCE": "CAP",
    "RESISTANCE": "RES", "FRESISTANCE": "FRES", "FREQUENCY": "FREQ", "CONTINUITY": "CONT",
}


def _norm(function: Union[str, MultimeterFunction]) -> str:
    if isinstance(function, MultimeterFunction):
        return function.value
    key = str(function).strip().upper()
    key = _FRIENDLY.get(key, key)
    if key not in _UNITS:
        raise ValueError(f"Unknown multimeter function '{function}'")
    return key


class MockMultimeter:
    """Mock multimeter that simulates a 6 1/2 digit bench DMM."""

    def __init__(self, resource_manager=None, resource_string: str = "MOCK::DMM::0"):
        self.resource_string = resource_string
        self.connected = False
        self.cached_info: Optional[EquipmentInfo] = None

        self.manufacturer = "Mock Instruments"
        self.model = "MockDMM-3068"
        self.serial_number = f"MOCK{uuid.uuid4().hex[:8].upper()}"
        self.firmware_version = "v1.0.0-mock"
        self.digits = 6.5

        # Simulated signal present at the terminals, per function.
        self.simulated_values: Dict[str, float] = {
            "DCV": 5.000, "ACV": 1.414, "DCI": 0.100, "ACI": 0.050,
            "RES": 1000.0, "FRES": 1000.0, "FREQ": 1000.0, "PER": 0.001,
            "CAP": 100e-9, "CONT": 0.5, "DIODE": 0.65,
        }
        # Relative noise (1 sigma) applied to every reading.
        self.noise_fraction = 1e-5
        self.overload_functions: set = set()

        # Instrument state
        self.function = "DCV"
        self.auto_range: Dict[str, bool] = {f: True for f in _UNITS}
        self.manual_range: Dict[str, int] = {f: 2 for f in _RANGES}
        self.rate: Dict[str, str] = {f: "SLOW" for f in _UNITS}
        self.secondary_function: Optional[str] = None
        self.trigger_source = "AUTO"
        self.trigger_interval_s = 0.4
        self.sample_count = 1
        self.math_function = "NONE"
        self.statistics_enabled = False
        self._stats: List[float] = []
        self.rel_offset = 0.0
        self.rel_enabled = False
        self.limits = {"lower": 0.0, "upper": 0.0, "enabled": False}
        self.dc_impedance = "10M"
        self.filter_enabled = {"DCV": False, "DCI": False}
        self.continuity_threshold = 10
        self.beeper = True
        self.brightness = 22
        self.command_set = "RIGOL"
        self.error_queue: List[str] = []

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def connect(self):
        await asyncio.sleep(0.05)
        self.connected = True
        self.cached_info = await self.get_info()
        logger.info(f"Connected to mock multimeter: {self.model}")

    async def disconnect(self):
        await asyncio.sleep(0.02)
        self.connected = False
        logger.info("Disconnected from mock multimeter")

    async def get_info(self) -> EquipmentInfo:
        from ..base import generate_equipment_id

        return EquipmentInfo(
            id=generate_equipment_id(self.resource_string, "dmm_"),
            type=EquipmentType.MULTIMETER,
            manufacturer=self.manufacturer,
            model=self.model,
            serial_number=self.serial_number,
            connection_type=ConnectionType.USB,
            resource_string=self.resource_string,
        )

    async def get_status(self) -> EquipmentStatus:
        try:
            capabilities = {
                "digits": self.digits,
                "functions": list(_UNITS.keys()),
                "secondary_functions": ["FREQ", "DCV", "ACV", "DCI", "ACI", "RES"],
                "ranges": {f: list(v) for f, v in _RANGES.items()},
                "rates": ["FAST", "MEDIUM", "SLOW"],
                "max_voltage": 1000.0,
                "max_current": 10.0,
                "interfaces": ["MOCK"],
                "function": self.function,
                "command_set": self.command_set,
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
            raise RuntimeError("Mock multimeter not connected")
        parameters = dict(parameters or {})
        handlers = {
            "measure": self.measure,
            "get_readings": self.get_readings,
            "get_measurement": self.get_measurement,
            "get_measurements": self.get_measurements,
            "read_samples": self.read_samples,
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
            "set_secondary_function": self.set_secondary_function,
            "clear_secondary_function": self.clear_secondary_function,
            "get_secondary_function": self.get_secondary_function,
            "set_trigger_source": self.set_trigger_source,
            "get_trigger_source": self.get_trigger_source,
            "set_trigger_interval": self.set_trigger_interval,
            "set_sample_count": self.set_sample_count,
            "get_sample_count": self.get_sample_count,
            "trigger": self.trigger,
            "set_math_function": self.set_math_function,
            "get_math_function": self.get_math_function,
            "get_statistics": self.get_statistics,
            "set_statistics": self.set_statistics,
            "set_rel_offset": self.set_rel_offset,
            "set_limits": self.set_limits,
            "get_limit_result": self.get_limit_result,
            "set_beeper": self.set_beeper,
            "set_display_brightness": self.set_display_brightness,
            "set_command_set": self.set_command_set,
            "get_command_set": self.get_command_set,
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
    # Simulation controls (test helpers)
    # ------------------------------------------------------------------ #

    def set_simulated_value(self, function: Union[str, MultimeterFunction], value: float):
        """Set the signal the mock 'sees' for a function."""
        self.simulated_values[_norm(function)] = float(value)

    def set_noise(self, fraction: float):
        self.noise_fraction = max(0.0, float(fraction))

    def simulate_overload(self, function: Union[str, MultimeterFunction], overloaded: bool = True):
        func = _norm(function)
        if overloaded:
            self.overload_functions.add(func)
        else:
            self.overload_functions.discard(func)

    # ------------------------------------------------------------------ #
    # Function / range / rate
    # ------------------------------------------------------------------ #

    async def set_function(self, function: Union[str, MultimeterFunction]) -> str:
        func = _norm(function)
        if func != self.function:
            self.function = func
            self._stats.clear()
            await asyncio.sleep(0.02)
        return func

    async def get_function(self) -> str:
        return self.function

    async def get_mode(self) -> str:
        return self.function

    def _range_index_for(self, func: str) -> Optional[int]:
        table = _RANGES.get(func)
        if table is None:
            return None
        if not self.auto_range.get(func, True):
            return self.manual_range[func]
        if func in ("FREQ", "PER"):
            # Range is the *input voltage* range, unrelated to the reading;
            # auto-range on the simulated ACV amplitude instead.
            value = abs(self.simulated_values.get("ACV", 0.0))
        else:
            value = abs(self.simulated_values.get(func, 0.0))
        for idx, full_scale in enumerate(table):
            if value <= full_scale:
                return idx
        return len(table) - 1

    async def set_range(self, range: Union[int, float, str], function: Optional[str] = None) -> Dict[str, Any]:
        func = await self.set_function(function) if function else self.function
        if func == "CONT":
            return await self.set_continuity_threshold(int(float(range)))
        table = _RANGES.get(func)
        if table is None:
            raise ValueError(f"Function {func} has no selectable ranges")
        if isinstance(range, str):
            key = range.strip().upper()
            if key == "AUTO":
                return await self.set_auto_range(True, func)
            if key == "MIN":
                idx = 0
            elif key == "MAX":
                idx = len(table) - 1
            elif key == "DEF":
                idx = min(2, len(table) - 1)
            else:
                idx = self._index_from_value(table, float(key), func)
        elif isinstance(range, int) and not isinstance(range, bool) and 0 <= range < len(table):
            idx = range
        else:
            idx = self._index_from_value(table, float(range), func)
        self.manual_range[func] = idx
        self.auto_range[func] = False
        return await self.get_range(func)

    @staticmethod
    def _index_from_value(table: List[float], value: float, func: str) -> int:
        for idx, full_scale in enumerate(table):
            if value <= full_scale * (1 + 1e-9):
                return idx
        raise ValueError(f"{value} exceeds the maximum {func} range of {table[-1]}")

    async def set_auto_range(self, enabled: bool = True, function: Optional[str] = None) -> Dict[str, Any]:
        func = await self.set_function(function) if function else self.function
        self.auto_range[func] = bool(enabled)
        return await self.get_range(func)

    async def get_range(self, function: Optional[str] = None) -> Dict[str, Any]:
        func = await self.set_function(function) if function else self.function
        idx = self._range_index_for(func)
        table = _RANGES.get(func, [])
        return {
            "function": func,
            "unit": _UNITS[func],
            "auto_range": self.auto_range.get(func) if func in _RANGES else None,
            "index": idx,
            "full_scale": table[idx] if idx is not None else None,
        }

    async def set_rate(self, rate: str, function: Optional[str] = None) -> str:
        func = await self.set_function(function) if function else self.function
        key = _RATE_ALIASES.get(str(rate).strip().upper())
        if key is None:
            raise ValueError("Rate must be FAST, MEDIUM or SLOW")
        self.rate[func] = key
        return key

    async def get_rate(self, function: Optional[str] = None) -> Optional[str]:
        func = await self.set_function(function) if function else self.function
        if func not in ("DCV", "ACV", "DCI", "ACI", "RES", "FRES"):
            return None
        return self.rate[func]

    async def set_dc_impedance(self, impedance: str = "10M") -> str:
        key = str(impedance).strip().upper()
        if key not in ("10M", "10G"):
            raise ValueError("Impedance must be 10M or 10G")
        self.dc_impedance = key
        return key

    async def get_dc_impedance(self) -> str:
        return self.dc_impedance

    async def set_filter(self, enabled: bool, function: Optional[str] = None) -> bool:
        func = await self.set_function(function) if function else self.function
        if func not in ("DCV", "DCI"):
            raise ValueError("Filter is only available for DCV and DCI")
        self.filter_enabled[func] = bool(enabled)
        return bool(enabled)

    async def set_continuity_threshold(self, threshold_ohms: int = 10) -> Dict[str, Any]:
        threshold = int(threshold_ohms)
        if not 1 <= threshold <= 2000:
            raise ValueError("Continuity threshold must be 1..2000 Ohm")
        await self.set_function("CONT")
        self.continuity_threshold = threshold
        return {"function": "CONT", "threshold_ohms": threshold, "unit": "Ohm"}

    # ------------------------------------------------------------------ #
    # Readings
    # ------------------------------------------------------------------ #

    def _sample(self, func: str) -> Optional[float]:
        if func in self.overload_functions:
            return None
        base = self.simulated_values.get(func, 0.0)
        idx = self._range_index_for(func)
        if (
            idx is not None
            and func not in ("FREQ", "PER")
            and abs(base) > _RANGES[func][idx] * 1.2
        ):
            return None  # manual range too small -> overload
        noise = np.random.normal(0.0, abs(base) * self.noise_fraction) if self.noise_fraction else 0.0
        value = base + noise
        if self.rel_enabled and self.math_function == "REL":
            value -= self.rel_offset
        if func in ("DCV", "ACV", "DCI", "ACI", "RES", "FRES"):
            self._stats.append(value)
            if len(self._stats) > 100000:
                del self._stats[:50000]
        return float(value)

    async def measure(self, function: Optional[str] = None, include_range: bool = True) -> MultimeterData:
        func = await self.set_function(function) if function else self.function
        await asyncio.sleep(0.005)
        value = self._sample(func)
        data = MultimeterData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            function=func,
            value=value,
            unit=_UNITS[func],
            overload=value is None,
            auto_range=self.auto_range.get(func) if func in _RANGES else None,
            rate=await self.get_rate(func),
        )
        if include_range:
            rng = await self.get_range(func)
            data.range_index = rng["index"]
            data.range_full_scale = rng["full_scale"]
        if self.secondary_function:
            data.secondary_function = self.secondary_function
            data.secondary_value = self._sample(self.secondary_function)
            data.secondary_unit = _UNITS[self.secondary_function]
        return data

    async def get_readings(self) -> MultimeterData:
        return await self.measure(None)

    async def get_measurement(self, channel: str = "CH1") -> Dict[str, Any]:
        key = (channel or "CH1").strip().upper()
        if key in ("CH1", "1", "MAIN", "PRIMARY", ""):
            data = await self.measure(None, include_range=False)
        elif key in ("CH2", "2", "SECONDARY", "FUNC2"):
            if not self.secondary_function:
                raise ValueError("Secondary display is not enabled")
            value = self._sample(self.secondary_function)
            return {
                "value": value if value is not None else float("nan"),
                "unit": _UNITS[self.secondary_function],
                "function": self.secondary_function,
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

    async def read_samples(self, count: int = 10, function: Optional[str] = None, interval_s: float = 0.0) -> Dict[str, Any]:
        count = int(count)
        if count < 1:
            raise ValueError("count must be >= 1")
        func = await self.set_function(function) if function else self.function
        values = [self._sample(func) for _ in range(count)]
        if interval_s > 0:
            await asyncio.sleep(min(interval_s * count, 0.5))
        valid = [v for v in values if v is not None]
        stats: Dict[str, Any] = {"count": len(valid), "overloads": len(values) - len(valid)}
        if valid:
            mean = sum(valid) / len(valid)
            stats.update(
                min=min(valid), max=max(valid), mean=mean,
                std=math.sqrt(sum((v - mean) ** 2 for v in valid) / len(valid)),
            )
        return {"function": func, "unit": _UNITS[func], "values": values, "stats": stats}

    # ------------------------------------------------------------------ #
    # Dual display
    # ------------------------------------------------------------------ #

    async def set_secondary_function(self, function: Union[str, MultimeterFunction]) -> str:
        func = _norm(function)
        if func in ("CONT", "DIODE"):
            raise ValueError("Secondary display cannot show CONT or DIODE")
        self.secondary_function = func
        return func

    async def clear_secondary_function(self) -> None:
        self.secondary_function = None

    async def get_secondary_function(self) -> Optional[str]:
        return self.secondary_function

    # ------------------------------------------------------------------ #
    # Trigger
    # ------------------------------------------------------------------ #

    async def set_trigger_source(self, source: str = "AUTO") -> str:
        key = {"IMM": "AUTO", "IMMEDIATE": "AUTO", "BUS": "SINGLE", "EXTERNAL": "EXT"}.get(
            str(source).strip().upper(), str(source).strip().upper()
        )
        if key not in ("AUTO", "SINGLE", "EXT"):
            raise ValueError("Trigger source must be AUTO, SINGLE or EXT")
        self.trigger_source = key
        return key

    async def get_trigger_source(self) -> str:
        return self.trigger_source

    async def set_trigger_interval(self, interval_s: float) -> float:
        interval_s = float(interval_s)
        if interval_s < 0:
            raise ValueError("Interval must be >= 0")
        self.trigger_interval_s = interval_s
        return interval_s

    async def set_sample_count(self, count: int) -> int:
        count = int(count)
        if not 1 <= count <= 50000:
            raise ValueError("Sample count must be 1..50000")
        self.sample_count = count
        return count

    async def get_sample_count(self) -> int:
        return self.sample_count

    async def trigger(self) -> None:
        await asyncio.sleep(0.005)

    # ------------------------------------------------------------------ #
    # Math
    # ------------------------------------------------------------------ #

    async def set_math_function(self, math_function: str = "NONE") -> str:
        key = {"AVG": "AVERAGE", "MEAN": "AVERAGE", "NULL": "REL", "LIMIT": "PF", "OFF": "NONE"}.get(
            str(math_function).strip().upper(), str(math_function).strip().upper()
        )
        if key not in {"NONE", "REL", "DB", "DBM", "MIN", "MAX", "AVERAGE", "TOTAL", "PF"}:
            raise ValueError(f"Unsupported math function {math_function}")
        self.math_function = key
        if key in ("MIN", "MAX", "AVERAGE", "TOTAL"):
            self.statistics_enabled = True
            self._stats.clear()
        return key

    async def get_math_function(self) -> str:
        return self.math_function

    async def set_statistics(self, enabled: bool = True) -> bool:
        self.statistics_enabled = bool(enabled)
        if enabled:
            self._stats.clear()
        return self.statistics_enabled

    async def get_statistics(self) -> Dict[str, Optional[float]]:
        if not self._stats:
            return {"min": None, "max": None, "average": None, "count": 0}
        return {
            "min": min(self._stats),
            "max": max(self._stats),
            "average": sum(self._stats) / len(self._stats),
            "count": float(len(self._stats)),
        }

    async def set_rel_offset(self, offset: Union[float, str] = "CURR", enabled: bool = True) -> Dict[str, Any]:
        self.math_function = "REL"
        if isinstance(offset, str) and offset.strip().upper() == "CURR":
            self.rel_offset = self.simulated_values.get(self.function, 0.0)
        elif isinstance(offset, str) and offset.strip().upper() in ("MIN", "MAX", "DEF"):
            self.rel_offset = 0.0
        else:
            self.rel_offset = float(offset)
        self.rel_enabled = bool(enabled)
        return {"offset": self.rel_offset, "enabled": self.rel_enabled}

    async def set_limits(self, lower: float, upper: float, enabled: bool = True) -> Dict[str, Any]:
        lower, upper = float(lower), float(upper)
        if lower > upper:
            raise ValueError("lower must be <= upper")
        self.math_function = "PF"
        self.limits = {"lower": lower, "upper": upper, "enabled": bool(enabled)}
        return dict(self.limits)

    async def get_limit_result(self) -> str:
        value = self._sample(self.function)
        if value is None or not self.limits["enabled"]:
            return "FAIL" if value is None else "OFF"
        return "PASS" if self.limits["lower"] <= value <= self.limits["upper"] else "FAIL"

    # ------------------------------------------------------------------ #
    # System
    # ------------------------------------------------------------------ #

    async def set_beeper(self, enabled: bool) -> bool:
        self.beeper = bool(enabled)
        return self.beeper

    async def set_display_brightness(self, level: int) -> int:
        level = int(level)
        if not 0 <= level <= 32:
            raise ValueError("Brightness must be 0..32")
        self.brightness = level
        return level

    async def set_command_set(self, name: str = "RIGOL") -> str:
        name = name.upper()
        if name not in ("RIGOL", "AGILENT", "FLUKE"):
            raise ValueError("Command set must be RIGOL, AGILENT or FLUKE")
        self.command_set = name
        return name

    async def get_command_set(self) -> str:
        return self.command_set

    async def reset(self) -> None:
        self.__init__(None, self.resource_string)
        self.connected = True
        self.cached_info = await self.get_info()

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

    async def get_state(self) -> Dict[str, Any]:
        return {
            "function": self.function,
            "range": await self.get_range(),
            "rate": await self.get_rate(),
            "trigger_source": self.trigger_source,
            "math_function": self.math_function,
            "secondary_function": self.secondary_function,
        }
