"""Generic SCPI drivers for B&K Precision instruments.

Roughly forty of the sixty-three documented B&K families speak plain SCPI over
whichever interface they carry, and differ only in the limits and channel count
the registry already records. One driver per category covers all of them, with
:mod:`server.equipment.bk_registry` supplying the per-model facts.

Two behaviours here are worth knowing about:

**Errors are checked, not assumed.** A SCPI instrument accepts a malformed
command silently and queues an error rather than refusing it, so a setter that
did nothing looks exactly like one that worked. Every setter drains
``SYST:ERR?`` afterwards and raises, unless ``check_errors`` is off.

**Setpoint and measurement are different questions.** ``VOLT?`` returns what was
programmed; ``MEAS:VOLT?`` returns what the hardware is doing. They diverge the
moment a supply enters constant-current mode, which is usually the condition a
test exists to detect.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from server.config.settings import settings
from shared.models.data import (ElectronicLoadData, MeasurementData,
                                PowerSupplyData)
from shared.models.equipment import (EquipmentInfo, EquipmentStatus,
                                     EquipmentType)

from .base import BaseEquipment, generate_equipment_id
from .bk_registry import MANUFACTURER, BKModel, resolve_model
from .safety import (SafetyLimits, SafetyValidator, emergency_stop_manager,
                     get_default_limits)

logger = logging.getLogger(__name__)


class BKInstrumentError(RuntimeError):
    """The instrument reported an error in its queue after a command."""


class BKSCPIBase(BaseEquipment):
    """Base for every SCPI-speaking B&K instrument.

    Owns the transport setup, the error queue, and the identity handling that
    works before anything model-specific is known.
    """

    #: Prefix for the generated equipment ID; overridden per category.
    id_prefix = "bk_"
    equipment_type = EquipmentType.POWER_SUPPLY

    def __init__(self, resource_manager, resource_string: str,
                 model: Optional[str] = None, check_errors: bool = True):
        super().__init__(resource_manager, resource_string)
        self.manufacturer = MANUFACTURER
        self.info: Optional[BKModel] = resolve_model(model)
        self.model = self.info.key if self.info else (model or "Unknown")
        self.check_errors = check_errors
        self.num_channels = self.info.channels if self.info else 1
        self.max_voltage = (self.info.max_voltage if self.info else None) or 60.0
        self.max_current = (self.info.max_current if self.info else None) or 5.0
        self.safety_validator: Optional[SafetyValidator] = None
        self._current_voltage = 0.0
        self._current_current = 0.0
        self._serial_number: Optional[str] = None
        self._firmware_version: Optional[str] = None

    # -- transport ---------------------------------------------------------
    def _configure_serial(self) -> None:
        """Apply 8N1 framing at the model's documented rate.

        A rate changed from the front panel persists in NVRAM and wins over
        this, which is why a garbled reply almost always means a baud
        mismatch rather than a broken cable.
        """
        if "ASRL" not in self.resource_string.upper():
            return
        baud = self.info.baud if self.info else 9600
        self.instrument.baud_rate = baud
        self.instrument.data_bits = 8
        self.instrument.parity = 0      # None: parity would cost a data bit
        self.instrument.stop_bits = 10  # pyvisa constant for one stop bit
        self.instrument.flow_control = 0
        logger.info(
            f"Configured {self.model} serial port: {baud} 8N1 "
            f"({self.resource_string})"
        )

    async def connect(self):
        """Open the instrument and prove the link with ``*IDN?``."""
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
                self.instrument.timeout = 10000
                self.instrument.write_termination = "\n"
                self.instrument.read_termination = "\n"
                self._configure_serial()

                idn = await self._query("*IDN?")
                logger.info(f"Connected to B&K device: {idn}")
                self._absorb_idn(idn)

                self.connected = True
                self.cached_info = await self.get_info()

            except Exception as e:
                logger.error(f"Failed to connect to {self.resource_string}: {e}")
                self.connected = False
                raise
            finally:
                self._is_connecting = False

    async def disconnect(self):
        """Return the front panel to local control, then close the link.

        Without this the instrument is left locked out and the next person at
        the bench cannot use its knobs.
        """
        try:
            if self.instrument is not None and self.connected:
                await self._write("SYST:LOC")
        except Exception as e:
            logger.debug(f"Could not return {self.model} to local control: {e}")
        await super().disconnect()

    def _absorb_idn(self, idn: str) -> None:
        """Fill in identity fields, and the model when it was not given."""
        parts = [p.strip() for p in (idn or "").split(",")]
        if len(parts) > 1 and parts[1]:
            reported = resolve_model(parts[1])
            if reported and not self.info:
                self.info = reported
                self.num_channels = reported.channels
                if reported.max_voltage:
                    self.max_voltage = reported.max_voltage
                if reported.max_current:
                    self.max_current = reported.max_current
            # Prefer the SKU the instrument reports over the family key.
            self.model = parts[1]
        if len(parts) > 2:
            self._serial_number = parts[2] or None
        if len(parts) > 3:
            self._firmware_version = parts[3] or None

    # -- error queue -------------------------------------------------------
    async def next_error(self) -> Tuple[int, str]:
        raw = await self._query("SYST:ERR?")
        code, _, text = raw.partition(",")
        try:
            return int(code.strip()), text.strip().strip('"')
        except ValueError:
            return 0, raw

    async def drain_errors(self) -> List[Tuple[int, str]]:
        """Read the error queue empty, bounded so a stuck queue cannot spin."""
        found: List[Tuple[int, str]] = []
        for _ in range(32):
            try:
                code, text = await self.next_error()
            except Exception as e:
                logger.debug(f"Error queue unreadable on {self.model}: {e}")
                break
            if code == 0:
                break
            found.append((code, text))
        return found

    async def _after_write(self) -> None:
        if not self.check_errors:
            return
        errors = await self.drain_errors()
        if errors:
            joined = "; ".join(f"{c}: {t}" for c, t in errors)
            raise BKInstrumentError(f"{self.model} reported {joined}")

    # -- safety ------------------------------------------------------------
    def _initialize_safety(self, equipment_id: str, category: str) -> None:
        if not settings.enable_safety_limits:
            logger.info(f"Safety limits disabled for {equipment_id}")
            return

        defaults = get_default_limits(category)
        limits = SafetyLimits(
            max_voltage=self.max_voltage,
            max_current=self.max_current,
            max_power=defaults.max_power,
            voltage_slew_rate=(
                defaults.voltage_slew_rate if settings.enforce_slew_rate else None
            ),
            current_slew_rate=(
                defaults.current_slew_rate if settings.enforce_slew_rate else None
            ),
            require_interlock=False,
        )
        self.safety_validator = SafetyValidator(limits, equipment_id)
        logger.info(f"Safety validator initialized for {equipment_id}")

    # -- info / status -----------------------------------------------------
    def _capabilities(self) -> Dict[str, Any]:
        caps: Dict[str, Any] = {
            "num_channels": self.num_channels,
            "max_voltage": self.max_voltage,
            "max_current": self.max_current,
        }
        if self.info:
            caps.update({
                "family": self.info.key,
                "protocol": self.info.protocol,
                "interfaces": self.info.interfaces,
                "usb_mode": self.info.usb,
                "socket_ports": list(self.info.ports),
            })
        return caps

    async def get_info(self) -> EquipmentInfo:
        equipment_id = generate_equipment_id(self.resource_string, self.id_prefix)
        self._initialize_safety(equipment_id, self.equipment_type.value)
        return EquipmentInfo(
            id=equipment_id,
            type=self.equipment_type,
            manufacturer=self.manufacturer,
            model=self.model,
            serial_number=self._serial_number,
            connection_type=self._determine_connection_type(),
            resource_string=self.resource_string,
        )

    async def get_status(self) -> EquipmentStatus:
        firmware = self._firmware_version
        try:
            idn = await self._query("*IDN?")
            parts = idn.split(",")
            if len(parts) > 3:
                firmware = parts[3].strip()
        except Exception:
            pass  # An unreachable identity does not invalidate the rest

        return EquipmentStatus(
            id=self.cached_info.id if self.cached_info else "unknown",
            connected=self.connected,
            firmware_version=firmware,
            capabilities=self._capabilities(),
        )

    async def run_self_test(self) -> Optional[dict]:
        """IEEE 488.2 ``*TST?``; a leading 0 means the instrument passed."""
        try:
            result = (await self._query("*TST?")).strip()
        except Exception as e:
            logger.debug(f"Self-test not available on {self.model}: {e}")
            return None
        passed = result.startswith("0")
        return {
            "passed": passed,
            "tests": [{"name": "built-in self test", "passed": passed,
                       "details": result}],
        }


class BKSCPIPowerSupply(BKSCPIBase):
    """SCPI power supplies: 9115, 9129B, 9130B/C, 9140, 9200B, 9240, 9800,
    9810, 1820B, 1696B, MR, MPS, HPS, HVL, HMR, BCS."""

    id_prefix = "ps_"
    equipment_type = EquipmentType.POWER_SUPPLY

    async def execute_command(self, command: str, parameters: dict) -> Any:
        handlers = {
            "set_voltage": self.set_voltage,
            "set_current": self.set_current,
            "set_output": self.set_output,
            "get_readings": self.get_readings,
            "get_setpoints": self.get_setpoints,
            "set_ovp": self.set_ovp,
            "set_ocp": self.set_ocp,
        }
        if command not in handlers:
            raise ValueError(f"Unknown command: {command}")
        return await handlers[command](**parameters)

    async def _select_channel(self, channel: int) -> None:
        if channel < 1 or channel > self.num_channels:
            raise ValueError(
                f"Invalid channel {channel} for {self.model} "
                f"({self.num_channels} channel(s))"
            )
        if self.num_channels > 1:
            await self._write(f"INST:NSEL {channel}")

    def channel_max_voltage(self, channel: int) -> float:
        """Per-channel ceiling. Uniform unless a subclass says otherwise."""
        return self.max_voltage

    async def set_voltage(self, voltage: float, channel: int = 1):
        if emergency_stop_manager.is_active():
            raise RuntimeError("Emergency stop is active - operation blocked")

        ceiling = self.channel_max_voltage(channel)
        if voltage < 0 or voltage > ceiling:
            raise ValueError(
                f"Voltage must be between 0 and {ceiling}V for channel {channel}"
            )

        if self.safety_validator and settings.enable_safety_limits:
            self.safety_validator.check_voltage(voltage)
            if settings.enforce_slew_rate:
                voltage = await self.safety_validator.apply_voltage_slew_limit(
                    voltage, self._current_voltage
                )

        await self._select_channel(channel)
        await self._write(f"VOLT {voltage:g}")
        await self._after_write()
        self._current_voltage = voltage

    async def set_current(self, current: float, channel: int = 1):
        if emergency_stop_manager.is_active():
            raise RuntimeError("Emergency stop is active - operation blocked")

        if current < 0 or current > self.max_current:
            raise ValueError(f"Current must be between 0 and {self.max_current}A")

        if self.safety_validator and settings.enable_safety_limits:
            self.safety_validator.check_current(current)
            if settings.enforce_slew_rate:
                current = await self.safety_validator.apply_current_slew_limit(
                    current, self._current_current
                )

        await self._select_channel(channel)
        await self._write(f"CURR {current:g}")
        await self._after_write()
        self._current_current = current

    async def set_output(self, enabled: bool, channel: int = 1):
        if enabled and emergency_stop_manager.is_active():
            raise RuntimeError("Emergency stop is active - cannot enable output")
        await self._select_channel(channel)
        await self._write(f"OUTP {'ON' if enabled else 'OFF'}")
        await self._after_write()

    async def set_ovp(self, voltage: float, channel: int = 1,
                      enabled: bool = True):
        """Set the over-voltage trip point."""
        await self._select_channel(channel)
        await self._write(f"VOLT:PROT {voltage:g}")
        await self._write(f"VOLT:PROT:STAT {'ON' if enabled else 'OFF'}")
        await self._after_write()

    async def set_ocp(self, current: float, channel: int = 1,
                      delay: Optional[float] = None, enabled: bool = True):
        """Set the over-current trip point.

        ``delay`` blanks the trip through inrush. Without it, OCP fires on the
        charging transient of a perfectly healthy capacitive load every time
        the output is enabled.
        """
        await self._select_channel(channel)
        await self._write(f"CURR:PROT {current:g}")
        if delay is not None:
            await self._write(f"CURR:PROT:DEL {delay:g}")
        await self._write(f"CURR:PROT:STAT {'ON' if enabled else 'OFF'}")
        await self._after_write()

    async def get_setpoints(self, channel: int = 1) -> Dict[str, float]:
        await self._select_channel(channel)
        return {
            "voltage": float(await self._query("VOLT?")),
            "current": float(await self._query("CURR?")),
        }

    async def get_readings(self, channel: int = 1) -> PowerSupplyData:
        await self._select_channel(channel)

        voltage_set = float(await self._query("VOLT?"))
        current_set = float(await self._query("CURR?"))
        voltage_actual = float(await self._query("MEAS:VOLT?"))
        current_actual = float(await self._query("MEAS:CURR?"))
        output_enabled = (await self._query("OUTP?")).strip().upper() in ("1", "ON")

        # A supply pushed into current limit reads below its voltage setpoint;
        # that difference is the CV/CC flag, and it is what most tests watch.
        in_cc_mode = output_enabled and current_set > 0 and (
            voltage_actual < voltage_set * 0.98
        )

        return PowerSupplyData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            channel=channel,
            voltage_set=voltage_set,
            current_set=current_set,
            voltage_actual=voltage_actual,
            current_actual=current_actual,
            output_enabled=output_enabled,
            in_cv_mode=output_enabled and not in_cc_mode,
            in_cc_mode=in_cc_mode,
        )


class BK9130Series(BKSCPIPowerSupply):
    """9130B/9130C triple output.

    Channels 1 and 2 reach 30 V; channel 3 is the 5 V logic rail.
    """

    def channel_max_voltage(self, channel: int) -> float:
        return 5.0 if channel == 3 else self.max_voltage


class BKSCPIElectronicLoad(BKSCPIBase):
    """SCPI DC loads: 8500B, 8550, 8600, 8460, MDL, MDL4U/4UB, DML.

    Mirrors the supply with INPut in place of OUTPut, plus a mode selection
    that has to be made before a setpoint means anything.
    """

    id_prefix = "load_"
    equipment_type = EquipmentType.ELECTRONIC_LOAD

    #: Mode name as the UI uses it -> SCPI function mnemonic.
    MODES = {
        "CC": "CURRent", "CV": "VOLTage",
        "CR": "RESistance", "CP": "POWer",
    }
    _SETPOINT_COMMAND = {"CC": "CURR", "CV": "VOLT", "CR": "RES", "CP": "POW"}

    def __init__(self, resource_manager, resource_string: str,
                 model: Optional[str] = None, check_errors: bool = True):
        super().__init__(resource_manager, resource_string, model, check_errors)
        self.max_power = 200.0
        self._mode = "CC"

    async def execute_command(self, command: str, parameters: dict) -> Any:
        handlers = {
            "set_mode": self.set_mode,
            "set_current": self.set_current,
            "set_voltage": self.set_voltage,
            "set_resistance": self.set_resistance,
            "set_power": self.set_power,
            "set_input": self.set_input,
            "get_readings": self.get_readings,
        }
        if command not in handlers:
            raise ValueError(f"Unknown command: {command}")
        return await handlers[command](**parameters)

    def _normalize_mode(self, mode: str) -> str:
        key = (mode or "").strip().upper()
        if key in self.MODES:
            return key
        # Accept the SCPI spellings too: CURRENT, VOLT, RESISTANCE, POWER.
        for short, full in self.MODES.items():
            if full.upper().startswith(key) and key:
                return short
        raise ValueError(
            f"mode must be one of {sorted(self.MODES)}, got {mode!r}"
        )

    async def set_mode(self, mode: str):
        normalized = self._normalize_mode(mode)
        await self._write(f"FUNC {self.MODES[normalized]}")
        await self._after_write()
        self._mode = normalized

    async def set_input(self, enabled: bool):
        if enabled and emergency_stop_manager.is_active():
            raise RuntimeError("Emergency stop is active - cannot enable load input")
        await self._write(f"INP {'ON' if enabled else 'OFF'}")
        await self._after_write()

    async def _set_level(self, command: str, value: float, limit: float,
                         unit: str):
        if emergency_stop_manager.is_active():
            raise RuntimeError("Emergency stop is active - operation blocked")
        if value < 0 or value > limit:
            raise ValueError(f"Value must be between 0 and {limit}{unit}")
        await self._write(f"{command} {value:g}")
        await self._after_write()

    async def set_current(self, current: float):
        await self._set_level("CURR", current, self.max_current, "A")

    async def set_voltage(self, voltage: float):
        await self._set_level("VOLT", voltage, self.max_voltage, "V")

    async def set_resistance(self, resistance: float):
        await self._set_level("RES", resistance, 1e6, "Ohm")

    async def set_power(self, power: float):
        await self._set_level("POW", power, self.max_power, "W")

    async def set_transient(self, level_a: float, width_a: float,
                            level_b: float, width_b: float,
                            mode: str = "CONTinuous"):
        """Configure CC transient (dynamic) mode.

        The load alternates between two current levels on hardware timing,
        which exercises a supply's regulation loop far faster than host round
        trips can.
        """
        await self._write(f"CURR:TRAN:MODE {mode}")
        await self._write(f"CURR:TRAN:ALEV {level_a:g}")
        await self._write(f"CURR:TRAN:AWID {width_a:g}")
        await self._write(f"CURR:TRAN:BLEV {level_b:g}")
        await self._write(f"CURR:TRAN:BWID {width_b:g}")
        await self._after_write()

    async def get_readings(self) -> ElectronicLoadData:
        try:
            self._mode = self._normalize_mode(await self._query("FUNC?"))
        except Exception:
            pass  # Keep the last known mode rather than failing the reading

        setpoint_cmd = self._SETPOINT_COMMAND[self._mode]
        setpoint = float(await self._query(f"{setpoint_cmd}?"))
        voltage = float(await self._query("MEAS:VOLT?"))
        current = float(await self._query("MEAS:CURR?"))
        try:
            power = float(await self._query("MEAS:POW?"))
        except Exception:
            power = voltage * current

        enabled = (await self._query("INP?")).strip().upper() in ("1", "ON")

        return ElectronicLoadData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            mode=self._mode,
            setpoint=setpoint,
            voltage=voltage,
            current=current,
            power=power,
            load_enabled=enabled,
        )

    def _capabilities(self) -> Dict[str, Any]:
        caps = super()._capabilities()
        caps["max_power"] = self.max_power
        caps["modes"] = sorted(self.MODES)
        return caps


class BKSCPIMultimeter(BKSCPIBase):
    """SCPI meters and counters: 2680, 2840, 5490C, 5335B.

    Two ways to read. ``measure()`` configures, triggers and fetches in one
    round trip; ``configure()`` once followed by repeated ``read()`` is much
    faster in a loop because it skips reconfiguration each time.
    """

    id_prefix = "dmm_"
    equipment_type = EquipmentType.MULTIMETER

    FUNCTIONS = {
        "voltage_dc": "VOLT:DC", "voltage_ac": "VOLT:AC",
        "current_dc": "CURR:DC", "current_ac": "CURR:AC",
        "resistance": "RES", "resistance_4w": "FRES",
        "capacitance": "CAP", "frequency": "FREQ", "period": "PER",
        "temperature": "TEMP", "diode": "DIOD", "continuity": "CONT",
    }
    UNITS = {
        "voltage_dc": "V", "voltage_ac": "V", "current_dc": "A",
        "current_ac": "A", "resistance": "Ohm", "resistance_4w": "Ohm",
        "capacitance": "F", "frequency": "Hz", "period": "s",
        "temperature": "C", "diode": "V", "continuity": "Ohm",
    }

    def __init__(self, resource_manager, resource_string: str,
                 model: Optional[str] = None, check_errors: bool = True):
        super().__init__(resource_manager, resource_string, model, check_errors)
        self._function = "voltage_dc"

    def _mnemonic(self, function: str) -> str:
        try:
            return self.FUNCTIONS[function]
        except KeyError:
            raise ValueError(
                f"unknown function {function!r}; expected one of "
                f"{sorted(self.FUNCTIONS)}"
            ) from None

    async def execute_command(self, command: str, parameters: dict) -> Any:
        handlers = {
            "measure": self.measure,
            "configure": self.configure,
            "read": self.read,
            "get_readings": self.get_readings,
        }
        if command not in handlers:
            raise ValueError(f"Unknown command: {command}")
        return await handlers[command](**parameters)

    async def measure(self, function: str = "voltage_dc") -> float:
        """Configure, trigger and read in one command."""
        value = float(await self._query(f"MEAS:{self._mnemonic(function)}?"))
        self._function = function
        return value

    async def configure(self, function: str = "voltage_dc",
                        range_: Optional[Any] = None,
                        resolution: Optional[Any] = None):
        command = f"CONF:{self._mnemonic(function)}"
        args = [str(a) for a in (range_, resolution) if a is not None]
        if args:
            command += " " + ",".join(args)
        await self._write(command)
        await self._after_write()
        self._function = function

    async def read(self) -> float:
        """Initiate and fetch — a fresh reading with the current setup."""
        return float(await self._query("READ?"))

    async def fetch(self) -> float:
        """Re-read the last reading without triggering a new one."""
        return float(await self._query("FETC?"))

    async def get_readings(self) -> MeasurementData:
        value = await self.read()
        return MeasurementData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            measurements={self._function: value},
            units={self._function: self.UNITS.get(self._function, "")},
        )

    def _capabilities(self) -> Dict[str, Any]:
        caps = super()._capabilities()
        caps["functions"] = sorted(self.FUNCTIONS)
        return caps
