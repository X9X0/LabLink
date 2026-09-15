"""Mock data acquisition / switch unit for testing without hardware.

Behaves like the Rigol M300 driver (``rigol_daq.py``): same command names,
same ``DataAcquisitionData`` scans, same ``get_measurement`` channel naming.
Slots 1 and 2 hold simulated MC3120 20-channel multiplexers with a
per-channel simulated input (``set_simulated_value``); slot 3 holds an MC3416
actuator so relay commands have a target.
"""

import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np

from shared.models.data import DataAcquisitionData
from shared.models.equipment import (ConnectionType, EquipmentInfo,
                                     EquipmentStatus, EquipmentType)

from ..rigol_daq import (FUNCTIONS, MODULE_TABLE, RANGES, expand_channel_list,
                         normalize_channel, normalize_function)

logger = logging.getLogger(__name__)

_MOCK_MODULES = {1: "MC3120", 2: "MC3120", 3: "MC3416"}
_TEMP_CONVERT = {"C": lambda c: c, "F": lambda c: c * 9.0 / 5.0 + 32.0, "K": lambda c: c + 273.15}


class MockDAQ:
    """Mock M300-style mainframe: 2 x 20-channel multiplexers + 1 actuator."""

    def __init__(self, resource_manager=None, resource_string: str = "MOCK::DAQ::0"):
        self.resource_string = resource_string
        self.connected = False
        self.cached_info: Optional[EquipmentInfo] = None

        self.manufacturer = "Mock Instruments"
        self.model = "MockDAQ-300"
        self.serial_number = f"MOCK{uuid.uuid4().hex[:8].upper()}"
        self.firmware_version = "v1.0.0-mock"

        self.modules: Dict[int, Dict[str, Any]] = {}
        for slot, model in _MOCK_MODULES.items():
            table = MODULE_TABLE[model]
            self.modules[slot] = {
                "slot": slot, "model": model, "serial": f"MM3{slot:02d}00000000", "firmware": "00.01.01.01",
                "description": table["description"], "kind": table["kind"], "channels": table["channels"],
                "functions": list(table.get("functions", [])),
            }
        self.dmm_installed = True

        # Simulated inputs: slot 1 = a voltage ladder, slot 2 = a temperature ladder (in C).
        self.simulated_values: Dict[str, float] = {}
        for ch in range(1, 21):
            self.simulated_values[f"1{ch:02d}"] = round(1.0 + 0.1 * (ch - 1), 6)
            self.simulated_values[f"2{ch:02d}"] = round(20.0 + 0.5 * (ch - 1), 6)
        self.noise_fraction = 1e-5
        self.overload_channels: set = set()

        self._init_state()

    def _init_state(self):
        self.channel_config: Dict[str, Dict[str, Any]] = {}
        for slot in (1, 2):
            for ch in range(1, 21):
                self.channel_config[f"{slot}{ch:02d}"] = {"function": "DCV", "range": None, "resolution": None, "unit": "V"}
        self.scan_list: List[str] = []
        self.closed_channels: set = set()
        self.trigger = {"source": "IMM", "count": 1, "interval": 0.0}
        self.temp_units: Dict[str, str] = {}
        self.last_scan: Optional[DataAcquisitionData] = None
        self.reading_memory: List[float] = []
        self.scan_count = 0
        self._consumed: set = set()
        self.error_queue: List[str] = []

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def connect(self):
        await asyncio.sleep(0.05)
        self.connected = True
        self.cached_info = await self.get_info()
        logger.info(f"Connected to mock DAQ: {self.model}")

    async def disconnect(self):
        await asyncio.sleep(0.02)
        self.connected = False
        logger.info("Disconnected from mock DAQ")

    async def get_info(self) -> EquipmentInfo:
        from ..base import generate_equipment_id

        return EquipmentInfo(
            id=generate_equipment_id(self.resource_string, "daq_"),
            type=EquipmentType.DATA_ACQUISITION,
            manufacturer=self.manufacturer,
            model=self.model,
            serial_number=self.serial_number,
            connection_type=ConnectionType.USB,
            resource_string=self.resource_string,
        )

    async def get_status(self) -> EquipmentStatus:
        try:
            capabilities = {
                "slots": [1, 2, 3, 4, 5],
                "modules": {str(s): dict(m) for s, m in self.modules.items()},
                "module_table": {k: dict(v) for k, v in MODULE_TABLE.items()},
                "dmm_installed": self.dmm_installed,
                "functions": list(FUNCTIONS),
                "ranges": {k: list(v) for k, v in RANGES.items()},
                "temperature_sensors": ["TC", "THER", "RTD", "FRTD"],
                "thermocouple_types": ["B", "E", "J", "K", "N", "R", "S", "T"],
                "trigger_sources": ["IMM", "TIMER", "BUS", "EXT", "ABS", "ALARM1", "ALARM2", "ALARM3", "ALARM4"],
                "max_readings": 100000,
                "max_trigger_count": 50000,
                "scan_list": list(self.scan_list),
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
            raise RuntimeError("Mock DAQ not connected")
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
            "trigger": self.trigger_scan,
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

    def set_simulated_value(self, channel: Union[str, int], value: float):
        """Set the signal present at a multiplexer channel (V, Ohm, Hz, degC ... as configured)."""
        ch = normalize_channel(channel)
        self._require_mux(ch)
        self.simulated_values[ch] = float(value)

    def set_noise(self, fraction: float):
        self.noise_fraction = max(0.0, float(fraction))

    def simulate_overload(self, channel: Union[str, int], overloaded: bool = True):
        ch = normalize_channel(channel)
        if overloaded:
            self.overload_channels.add(ch)
        else:
            self.overload_channels.discard(ch)

    # ------------------------------------------------------------------ #
    # Modules / channels
    # ------------------------------------------------------------------ #

    def _module_for(self, ch: str) -> Optional[Dict[str, Any]]:
        return self.modules.get(int(ch[0]))

    def _require_mux(self, ch: str) -> Dict[str, Any]:
        info = self._module_for(ch)
        if info is None:
            raise ValueError(f"Slot {ch[0]} is empty")
        if info["kind"] != "mux":
            raise ValueError(f"Channel {ch} is on a {info['model']} ({info['description']}), not a multiplexer")
        if not 1 <= int(ch[1:]) <= info["channels"]:
            raise ValueError(f"{info['model']} has channels 01..{info['channels']:02d}")
        return info

    def _require_switch(self, ch: str) -> Dict[str, Any]:
        info = self._module_for(ch)
        if info is None:
            raise ValueError(f"Slot {ch[0]} is empty")
        if info["kind"] not in ("mux", "actuator", "matrix"):
            raise ValueError(f"Channel {ch} has no relay")
        if not 1 <= int(ch[1:]) <= info["channels"]:
            raise ValueError(f"{info['model']} has channels 01..{info['channels']:02d}")
        return info

    async def get_modules(self, refresh: bool = True) -> Dict[int, Dict[str, Any]]:
        return {slot: dict(info) for slot, info in self.modules.items()}

    async def set_dmm_enabled(self, enabled: bool = True) -> bool:
        self.dmm_installed = bool(enabled)
        return self.dmm_installed

    async def configure_channel(self, channel: Union[str, int, Sequence[Union[str, int]]], function: str = "DCV",
                                range: Optional[Union[float, str]] = None,
                                resolution: Optional[Union[float, str]] = None,
                                sensor: Optional[str] = None, sensor_type: Optional[str] = None) -> Dict[str, Any]:
        func = normalize_function(function)
        chans = expand_channel_list(channel)
        if not chans:
            raise ValueError("At least one channel is required")
        for ch in chans:
            info = self._require_mux(ch)
            if func not in MODULE_TABLE[info["model"]]["functions"]:
                raise ValueError(f"{info['model']} does not support {func}")
            if func == "FRES" and int(ch[1:]) > MODULE_TABLE[info["model"]]["four_wire_offset"]:
                raise ValueError(f"4-wire on {info['model']} uses channels 1..{MODULE_TABLE[info['model']]['four_wire_offset']}")
        cfg: Dict[str, Any] = {"function": func, "range": None, "resolution": None, "unit": FUNCTIONS[func]["unit"]}
        if func == "TEMP":
            probe = str(sensor or "TC").strip().upper()
            probe = {"TCOUPLE": "TC", "THERMOCOUPLE": "TC", "THERMISTOR": "THER"}.get(probe, probe)
            if probe not in ("TC", "THER", "RTD", "FRTD"):
                raise ValueError("sensor must be TC, THER, RTD or FRTD")
            default = {"TC": "J", "THER": "5000", "RTD": "85", "FRTD": "85"}[probe]
            stype = str(sensor_type or default).strip().upper()
            if probe == "TC" and stype not in ("B", "E", "J", "K", "N", "R", "S", "T"):
                raise ValueError("Thermocouple type must be B, E, J, K, N, R, S or T")
            cfg.update({"sensor": probe, "sensor_type": stype})
        else:
            if isinstance(range, str) and range.strip().upper() in ("AUTO", "DEF"):
                range = None
            cfg["range"] = None if range is None else float(range)
            cfg["resolution"] = None if resolution is None else (resolution if isinstance(resolution, str) else float(resolution))
        for ch in chans:
            unit = self.temp_units.get(ch, "C") if func == "TEMP" else cfg["unit"]
            self.channel_config[ch] = dict(cfg, unit=unit)
        self.last_scan = None
        return {"channels": chans, **cfg}

    async def get_configuration(self, channels: Optional[Union[str, Sequence[str]]] = None) -> Dict[str, Dict[str, Any]]:
        chans = expand_channel_list(channels) if channels is not None else list(self.scan_list)
        return {ch: dict(self.channel_config.get(ch, {})) for ch in chans}

    async def set_temperature_unit(self, unit: str = "C", channels: Optional[Union[str, Sequence[str]]] = None) -> str:
        key = str(unit).strip().upper().replace("°", "")
        key = {"CELSIUS": "C", "FAHRENHEIT": "F", "KELVIN": "K"}.get(key, key)
        if key not in ("C", "F", "K"):
            raise ValueError("Temperature unit must be C, F or K")
        chans = expand_channel_list(channels) if channels is not None else list(self.scan_list)
        for ch in chans:
            if self.channel_config.get(ch, {}).get("function") != "TEMP":
                raise ValueError(f"Channel {ch} is not configured for temperature")
            self.temp_units[ch] = key
            self.channel_config[ch]["unit"] = key
        return key

    # ------------------------------------------------------------------ #
    # Scan list / scanning
    # ------------------------------------------------------------------ #

    async def set_scan_list(self, channels: Union[str, Sequence[Union[str, int]]]) -> List[str]:
        chans = expand_channel_list(channels)
        for ch in chans:
            self._require_mux(ch)
        self.scan_list = sorted(chans, key=int)  # the M300 stores ascending order
        self.last_scan = None
        return list(self.scan_list)

    async def get_scan_list(self) -> List[str]:
        return list(self.scan_list)

    def _sample(self, ch: str) -> Optional[float]:
        if ch in self.overload_channels:
            return None
        cfg = self.channel_config.get(ch, {"function": "DCV"})
        base = self.simulated_values.get(ch, 0.0)
        rng = cfg.get("range")
        if rng is not None and abs(base) > float(rng) * 1.1:
            return None
        noise = np.random.normal(0.0, abs(base) * self.noise_fraction) if self.noise_fraction else 0.0
        value = base + noise
        if cfg.get("function") == "TEMP":
            value = _TEMP_CONVERT[self.temp_units.get(ch, "C")](value)
        return float(value)

    def _build(self, chans: List[str], values: List[Optional[float]]) -> DataAcquisitionData:
        return DataAcquisitionData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            readings={ch: (float("nan") if v is None else v) for ch, v in zip(chans, values)},
            units={ch: self.channel_config.get(ch, {}).get("unit", "") for ch in chans},
            functions={ch: self.channel_config.get(ch, {}).get("function", "") for ch in chans},
            scan_list=list(chans),
            installed_modules={str(s): m["model"] for s, m in self.modules.items()},
        )

    async def scan(self, wait: bool = True) -> DataAcquisitionData:
        if not self.scan_list:
            raise ValueError("Scan list is empty; call set_scan_list first")
        if not self.dmm_installed:
            raise RuntimeError("DMM module disabled; multiplexer scan not possible")
        chans = list(self.scan_list)
        await asyncio.sleep(min(0.2, 0.002 * len(chans)))
        values = [self._sample(ch) for ch in chans]
        self.reading_memory = [v for v in values if v is not None]
        self.scan_count += 1
        data = self._build(chans, values)
        self.last_scan = data
        self._consumed.clear()
        if not wait:
            return self._build(chans, [])
        return data

    async def fetch(self) -> DataAcquisitionData:
        if self.last_scan is None:
            return await self.scan()
        return self.last_scan

    async def read_channel(self, channel: Union[str, int]) -> Dict[str, Any]:
        ch = normalize_channel(channel)
        self._require_mux(ch)
        await asyncio.sleep(0.002)
        value = self._sample(ch)
        cfg = self.channel_config.get(ch, {})
        return {"channel": ch, "value": float("nan") if value is None else value, "overload": value is None,
                "unit": cfg.get("unit", ""), "function": cfg.get("function", "")}

    async def trigger_scan(self) -> None:
        if self.trigger["source"] == "BUS" and self.scan_list:
            await self.scan()

    async def abort(self) -> None:
        pass

    async def get_data_points(self) -> int:
        return len(self.reading_memory)

    async def remove_data(self, count: int) -> List[Optional[float]]:
        count = int(count)
        if count < 1 or count > len(self.reading_memory):
            raise ValueError(f"count must be 1..{len(self.reading_memory)}")
        out, self.reading_memory = self.reading_memory[:count], self.reading_memory[count:]
        return out

    # ------------------------------------------------------------------ #
    # Switch modules
    # ------------------------------------------------------------------ #

    async def close_channel(self, channels: Union[str, int, Sequence[Union[str, int]]]) -> Dict[str, bool]:
        chans = expand_channel_list(channels)
        for ch in chans:
            self._require_switch(ch)
            if ch in self.scan_list:
                raise ValueError(f"Channel {ch} is in the scan list; remove it before switching it manually")
        self.closed_channels.update(chans)
        return {ch: True for ch in chans}

    async def open_channel(self, channels: Union[str, int, Sequence[Union[str, int]]]) -> Dict[str, bool]:
        chans = expand_channel_list(channels)
        for ch in chans:
            self._require_switch(ch)
            if ch in self.scan_list:
                raise ValueError(f"Channel {ch} is in the scan list; remove it before switching it manually")
        self.closed_channels.difference_update(chans)
        return {ch: False for ch in chans}

    async def get_closed_channels(self, channels: Optional[Union[str, Sequence[str]]] = None) -> List[str]:
        if channels is None:
            return sorted(self.closed_channels, key=int)
        return [ch for ch in expand_channel_list(channels) if ch in self.closed_channels]

    # ------------------------------------------------------------------ #
    # Trigger
    # ------------------------------------------------------------------ #

    async def set_trigger(self, source: str = "IMM", count: Optional[Union[int, str]] = None,
                          interval: Optional[float] = None) -> Dict[str, Any]:
        key = str(source).strip().upper()
        aliases = {"IMMEDIATE": "IMM", "AUTO": "IMM", "TIM": "TIMER", "INTERVAL": "TIMER", "MANUAL": "BUS",
                   "MAN": "BUS", "EXTERNAL": "EXT", "ABSOLUTE": "ABS"}
        key = aliases.get(key, key)
        if key not in ("IMM", "TIMER", "BUS", "EXT", "ABS", "ALARM1", "ALARM2", "ALARM3", "ALARM4"):
            raise ValueError("Trigger source must be IMM, TIMER, BUS, EXT, ABS or ALARM1..4")
        self.trigger["source"] = key
        if count is not None:
            if isinstance(count, str) and count.strip().upper().startswith("INF"):
                self.trigger["count"] = "INFINITY"
            else:
                n = int(count)
                if not 1 <= n <= 50000:
                    raise ValueError("Trigger count must be 1..50000 or INFINITY")
                self.trigger["count"] = n
        if interval is not None:
            interval = float(interval)
            if not 0 <= interval <= 359999.999:
                raise ValueError("Trigger interval must be 0..359999.999 s")
            self.trigger["interval"] = interval
        return await self.get_trigger()

    async def get_trigger(self) -> Dict[str, Any]:
        return dict(self.trigger)

    # ------------------------------------------------------------------ #
    # Integration hooks
    # ------------------------------------------------------------------ #

    async def get_readings(self) -> DataAcquisitionData:
        if self.last_scan is not None:
            return self.last_scan
        return await self.scan()

    async def get_measurement(self, channel: str = "101") -> Dict[str, Any]:
        ch = normalize_channel(channel)
        if ch in self.scan_list:
            if self.last_scan is None or ch in self._consumed:
                await self.scan()
            self._consumed.add(ch)
            value = self.last_scan.readings[ch]
            cfg = self.channel_config.get(ch, {})
            return {"value": value, "unit": cfg.get("unit", ""), "function": cfg.get("function", ""),
                    "channel": ch, "overload": value != value}
        return await self.read_channel(ch)

    async def get_measurements(self, channel: Any = 1) -> Dict[str, Any]:
        data = await self.get_readings()
        out: Dict[str, Any] = dict(data.readings)
        for ch, unit in data.units.items():
            out[f"{ch}_unit"] = unit
        return out

    async def get_state(self) -> Dict[str, Any]:
        return {
            "scan_list": list(self.scan_list),
            "channels": {ch: dict(cfg) for ch, cfg in self.channel_config.items() if ch in self.scan_list},
            "modules": {str(s): m["model"] for s, m in self.modules.items()},
            "temperature_units": dict(self.temp_units),
            "trigger": dict(self.trigger),
            "closed_channels": sorted(self.closed_channels, key=int),
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
