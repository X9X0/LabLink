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
options installed at the factory; the SCPI tree and the ratings are the
same.

Those options are high slew rate, high frequency, high readback
resolution, LAN and Digital I/O -- the five ``*OPT?`` reports, which the
A models ship with and the plain ones can have added with ``:LIC:SET``.
This used to say the options were "LAN, list, battery, OCP/OPP", which
sent someone looking for a way to ask whether List and the OCP/OPP and
battery tests were present before writing any UI for them. They are not
optional: they are standard on every model, and ``:FUNCtion:MODE`` takes
``{FIXed|LIST|WAVe|BATTery|OCP|OPP}`` unconditionally.

*IDN? returns ``RIGOL TECHNOLOGIES,<model>,<serial>,<firmware>``.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from shared.models.data import ElectronicLoadData
from shared.models.equipment import (EquipmentInfo, EquipmentStatus,
                                     EquipmentType)

from .base import (BaseEquipment, CommandRejected, SetpointRefused,
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


#: What :FUNCtion:MODE accepts, and what its query gives back.
#:
#: Asymmetric in the same way :SOURce:FUNCtion is, and for the same
#: reason it bit us before: the setting takes {FIXed|LIST|WAVe|BATTery|
#: OCP|OPP} but the query "returns FIX, LIST, WAV, BATT, OCP, or OPP".
#: Feeding a query's answer straight back would send WAV where WAVe was
#: wanted. Short forms are sent throughout, which every SCPI parser
#: accepts and which sidesteps the spelling problem below.
_FUNCTION_MODES = ("FIX", "LIST", "WAV", "BATT", "OCP", "OPP")

#: Long names for the function modes, for messages and for callers who
#: would rather say what they mean.
_FUNCTION_MODE_NAMES = {
    "FIX": "fixed",
    "LIST": "list",
    "WAV": "waveform",
    "BATT": "battery",
    "OCP": "over-current protection test",
    "OPP": "over-power protection test",
}

#: The tunable parameters of the function modes: LabLink name mapped to
#: the SCPI tail, the unit, and which rating bounds it.
#:
#: Note ":SOUR:BATT:..." throughout. Rigol's own tree spells the
#: subsystem BATTary while :FUNCtion:MODE spells the same mode BATTery.
#: Both abbreviate to BATT, so the short form is right whichever way
#: the firmware reads it -- which is the only reason this does not have
#: to be discovered on the bench.
#:
#: "limit" names the attribute holding the ceiling, or None where the
#: guide gives no rating to check against and the load is left to
#: refuse for itself.
_FUNCTION_PARAMETERS = {
    # Battery discharge
    "battery_level":      (":SOUR:BATT", "A", "max_current"),
    "battery_range":      (":SOUR:BATT:RANG", "A", "max_current"),
    "battery_von":        (":SOUR:BATT:VON", "V", "max_voltage"),
    "battery_stop_volts": (":SOUR:BATT:VST", "V", "max_voltage"),
    "battery_stop_ah":    (":SOUR:BATT:CST", "Ah", None),
    "battery_stop_time":  (":SOUR:BATT:TIM", "s", None),
    # Over-current protection test
    "ocp_range":          (":SOUR:OCP:RANG", "A", "max_current"),
    "ocp_von":            (":SOUR:OCP:VON", "V", "max_voltage"),
    "ocp_von_delay":      (":SOUR:OCP:VOND", "s", None),
    "ocp_start":          (":SOUR:OCP:ISET", "A", "max_current"),
    "ocp_step":           (":SOUR:OCP:IST", "A", "max_current"),
    "ocp_step_delay":     (":SOUR:OCP:IDEL", "s", None),
    "ocp_max":            (":SOUR:OCP:IMAX", "A", "max_current"),
    "ocp_min":            (":SOUR:OCP:IMIN", "A", "max_current"),
    "ocp_trip_volts":     (":SOUR:OCP:VOCP", "V", "max_voltage"),
    "ocp_timeout":        (":SOUR:OCP:TOCP", "s", None),
    # Over-power protection test
    "opp_von":            (":SOUR:OPP:VON", "V", "max_voltage"),
    "opp_von_delay":      (":SOUR:OPP:VOND", "s", None),
    "opp_start":          (":SOUR:OPP:PSET", "W", "max_power"),
    "opp_step":           (":SOUR:OPP:PST", "W", "max_power"),
    "opp_step_delay":     (":SOUR:OPP:PDEL", "s", None),
    "opp_max":            (":SOUR:OPP:PMAX", "W", "max_power"),
    "opp_min":            (":SOUR:OPP:PMIN", "W", "max_power"),
    "opp_trip_volts":     (":SOUR:OPP:VOPP", "V", "max_voltage"),
    "opp_timeout":        (":SOUR:OPP:TOPP", "s", None),
    # List
    "list_range":         (":SOUR:LIST:RANG", "", None),
    "list_count":         (":SOUR:LIST:COUN", "cycles", None),
    "list_steps":         (":SOUR:LIST:STEP", "steps", None),
}

#: Battery results, read while the discharge runs or after it stops.
#: These are measurements, not settings, so they have no setter.
_BATTERY_RESULTS = {
    "capacity_ah": ":MEAS:CAP?",
    "watt_hours": ":MEAS:WATT?",
    "discharge_seconds": ":MEAS:DISC?",
}

#: Range setters among the parameters above. Switching range moves the
#: shunt whatever mode asked for it, so the user guide's CAUTION covers
#: these exactly as it covers :SOUR:CURR:RANG.
_FUNCTION_RANGE_PARAMETERS = {
    "battery_range": "battery current range",
    "ocp_range": "OCP current range",
    "list_range": "List range",
}



#: Bits of the questionable status register, by weight.
#:
#: Only the ones the programming guide prints unambiguously, one per
#: line, are named here. Its Table 1-1 wraps the name and description
#: columns across rows for bits 9 to 14, and the two readings that
#: survive that wrapping disagree about which of RRV/LRV/UNR/OV/PS/VON
#: goes with which weight. Guessing would put a wrong name on a
#: protection-shutdown flag, so the raw value is returned alongside and
#: the rest are left to be confirmed against an instrument.
_QUESTIONABLE_BITS = {
    1: ("voltage_fault", "Overvoltage or reverse voltage occurred"),
    2: ("over_current", "Overcurrent occurred"),
    4: ("remote_sense", "Remote sense terminals connected"),
    8: ("over_power", "Overpower occurred"),
    128: ("list_running", "Running in List mode"),
}


#: Transient operation modes, short name to the SCPI keyword. These are
#: the Con / Pul / Tog keys on the front panel.
_TRANSIENT_MODES = {
    "CON": "CONTinuous", "PUL": "PULSe", "TOG": "TOGGle",
}

#: Trigger sources. MANUal is the default and means the front-panel TRAN
#: key, so a software trigger needs BUS.
_TRIGGER_SOURCES = {
    "BUS": "BUS", "EXT": "EXTernal", "EXTERNAL": "EXTernal",
    "MAN": "MANUal", "MANUAL": "MANUal",
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
            # CC mode carries two parameters beyond its level, both
            # listed under the CC key in the user guide.
            "supports_slew_rate": True,
            "supports_von": True,
            "supports_transient": True,
            "transient_modes": list(_TRANSIENT_MODES),
            "supports_acquisition": True,
            # List, battery discharge and the two protection tests are
            # standard on every DL3000 -- *OPT? gates none of them, and
            # :FUNCtion:MODE takes all six unconditionally.
            "function_modes": list(_FUNCTION_MODES),
            "function_mode_names": dict(_FUNCTION_MODE_NAMES),
            "function_parameters": {
                name: {"scpi": scpi, "unit": unit, "limit": limit}
                for name, (scpi, unit, limit) in _FUNCTION_PARAMETERS.items()
            },
            "battery_results": list(_BATTERY_RESULTS),
            # There is no SCPI command for the short-circuit function on
            # this load. The only remote route is :SYSTem:KEY 33, which
            # presses the front-panel SHORT key: a blind toggle with no
            # readback. Advertised as absent rather than implemented as
            # a button that cannot say what it did.
            "supports_short_circuit": False,
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
            "get_protection_status": self.get_protection_status,
            "set_function_mode": self.set_function_mode,
            "get_function_mode": self.get_function_mode,
            "set_function_parameter": self.set_function_parameter,
            "get_function_parameter": self.get_function_parameter,
            "set_battery_cutoffs": self.set_battery_cutoffs,
            "get_battery_cutoffs": self.get_battery_cutoffs,
            "get_battery_results": self.get_battery_results,
            "set_list_step": self.set_list_step,
            "get_list_step": self.get_list_step,
            "set_list_mode": self.set_list_mode,
            "get_list_mode": self.get_list_mode,
            "set_list_end_state": self.set_list_end_state,
            "get_list_end_state": self.get_list_end_state,
            "get_slew_limits": self.get_slew_limits,
            "get_options": self.get_options,
            "set_slew_rate": self.set_slew_rate,
            "get_slew_rate": self.get_slew_rate,
            "set_von": self.set_von,
            "get_von": self.get_von,
            "set_transient_enabled": self.set_transient_enabled,
            "get_transient_enabled": self.get_transient_enabled,
            "set_transient_mode": self.set_transient_mode,
            "get_transient_mode": self.get_transient_mode,
            "set_transient_levels": self.set_transient_levels,
            "set_transient_widths": self.set_transient_widths,
            "set_transient_frequency": self.set_transient_frequency,
            "set_transient_duty": self.set_transient_duty,
            "set_transient_slew": self.set_transient_slew,
            "get_transient": self.get_transient,
            "set_trigger_source": self.set_trigger_source,
            "get_trigger_source": self.get_trigger_source,
            "trigger": self.trigger,
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
    # Writing, and finding out whether the load agreed
    # ------------------------------------------------------------------ #

    async def _command(self, command: str):
        """Send a control command and ask the load what it made of it.

        SCPI puts a syntax or range fault in the error queue, not in the
        reply, so a write that the instrument throws away is
        indistinguishable from one it obeyed. That is exactly how
        :SOUR:FUNC CV -- the short form, where the setting wants
        VOLTage -- reported success for CV, CR and CP while the load sat
        in CC the whole time. Nothing above the wire could see it, and
        it took reading the mode back on the bench to find.

        The queue is cleared first, and that is not tidiness. It is
        cumulative: whatever is sitting in it when the write goes out
        will be read back afterwards and blamed on this command. Found
        on the bench within a minute of the feature going live --
        :SOUR:CURR:LEV:IMM 0.2 was reported as rejected with "Parameter
        error" while the setpoint plainly changed to 0.2 A, because the
        queue still held errors from the short-form :SOUR:FUNC CV
        commands this load refused before that bug was fixed. Reading
        the queue six times returned the same error six times; *CLS
        emptied it and it stayed empty.

        So an unexplained error from days ago becomes a false report
        about whatever you do next, which is worse than the silence it
        replaced.

        Two extra exchanges per control command, a write and a query.
        Only control commands go through here: those happen when an
        operator does something, where a round trip is nothing, rather
        than on the readings poll, where it would triple the traffic.
        """
        # Not clear_errors(): that swallows its own failure, and a
        # clear that silently did not happen puts us back to blaming
        # this command for an older one.
        await self._write("*CLS")
        await self._write(command)
        try:
            fault = await self.get_error()
        except Exception as e:
            # Not being able to ask is not the same as the command
            # failing, so it must not be reported as one.
            logger.debug(f"{self.resource_string}: could not read the "
                         f"error queue after {command!r}: {e}")
            return
        if fault.get("code"):
            raise CommandRejected(
                f"{self.model} rejected {command!r}: "
                f"{fault.get('message') or fault.get('raw')}"
            )

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
        await self._command(f":SOUR:FUNC {_MODE_TO_FUNCTION[mode_upper]}")

    async def get_mode(self) -> Optional[str]:
        """The static regulation mode: CC, CV, CR or CP.

        None when a function mode owns the setpoint. In battery
        discharge the load answers :SOUR:FUNC? with NONE, which is not a
        fault and not an unexpected reply -- it is the load saying the
        FUNCtion command is not in charge at the moment. Raising on it
        made get_mode fail for the whole time a battery test ran, and
        took get_readings with it.
        """
        raw = (await self._query(":SOUR:FUNC?")).strip().upper()
        if raw.startswith("NONE"):
            return None
        mode = _FUNCTION_TO_MODE.get(raw)
        if mode is None:
            raise ValueError(f"Unexpected :SOUR:FUNC? response: {raw!r}")
        return mode

    async def set_current(self, current: float):
        """Set the CC-mode current in amps (0 .. model maximum)."""
        current = float(current)
        if current < 0 or current > self.max_current:
            raise SetpointRefused(f"Current must be between 0 and {self.max_current}A")
        await self._command(f":SOUR:CURR:LEV:IMM {current}")

    async def set_voltage(self, voltage: float):
        """Set the CV-mode voltage in volts (0 .. model maximum)."""
        voltage = float(voltage)
        if voltage < 0 or voltage > self.max_voltage:
            raise SetpointRefused(f"Voltage must be between 0 and {self.max_voltage}V")
        await self._command(f":SOUR:VOLT:LEV:IMM {voltage}")

    async def set_resistance(self, resistance: float):
        """Set the CR-mode resistance in ohms (0.08 Ohm .. 15 kOhm)."""
        resistance = float(resistance)
        if resistance <= 0:
            raise SetpointRefused("Resistance must be greater than 0")
        if resistance < self.min_resistance or resistance > self.max_resistance:
            raise SetpointRefused(
                f"Resistance must be between {self.min_resistance} and {self.max_resistance} Ohm"
            )
        await self._command(f":SOUR:RES:LEV:IMM {resistance}")

    async def set_power(self, power: float):
        """Set the CP-mode power in watts (0 .. model maximum)."""
        power = float(power)
        if power < 0 or power > self.max_power:
            raise SetpointRefused(f"Power must be between 0 and {self.max_power}W")
        await self._command(f":SOUR:POW:LEV:IMM {power}")

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
        await self._command(f":SOUR:INP:STAT {'ON' if enabled else 'OFF'}")

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
        await self._refuse_if_sinking("current range")
        word = self._range_word(current_range, self.spec.low_current_range, self.spec.max_current, "Current")
        await self._command(f":SOUR:CURR:RANG {word}")
        return float(await self._query(":SOUR:CURR:RANG?"))

    async def set_voltage_range(self, voltage_range) -> float:
        """Select the CV voltage range (low/high, MIN/MAX, or a value in V)."""
        await self._refuse_if_sinking("voltage range")
        word = self._range_word(voltage_range, self.spec.low_voltage_range, self.spec.max_voltage, "Voltage")
        await self._command(f":SOUR:VOLT:RANG {word}")
        return float(await self._query(":SOUR:VOLT:RANG?"))

    async def set_resistance_range(self, resistance_range) -> float:
        """Select the CR resistance range (low/high, MIN/MAX, or a value in Ohm)."""
        await self._refuse_if_sinking("resistance range")
        word = self._range_word(
            resistance_range, self.spec.low_resistance_range, self.spec.max_resistance, "Resistance"
        )
        await self._command(f":SOUR:RES:RANG {word}")
        return float(await self._query(":SOUR:RES:RANG?"))

    # ------------------------------------------------------------------ #
    # CC mode extras: slew rate and starting voltage
    # ------------------------------------------------------------------ #

    async def set_slew_rate(self, slew_rate: float) -> None:
        """Set the CC-mode rising and falling slew rate, in A/us.

        ``:CURRent:SLEW[:BOTH]`` is the CC-mode rate and sets both
        directions at once. ``:SLEW:POSitive`` and ``:SLEW:NEGative``
        look like the obvious pair to use and are not: the guide gives
        them as the rising and falling rates in *transient* operation,
        a different mode with its own levels. Writing those here would
        have set something real and not this.

        No ceiling is checked. The rate a given model allows is not in
        the data the driver holds, and inventing a limit is how a supply
        ended up with three different wrong floors this week. The
        instrument knows, and since control commands now read the error
        queue it will say so.
        """
        slew_rate = float(slew_rate)
        if slew_rate <= 0:
            raise SetpointRefused("Slew rate must be greater than 0 A/us")
        await self._command(f":SOUR:CURR:SLEW {slew_rate}")

    async def get_slew_rate(self) -> float:
        return float(await self._query(":SOUR:CURR:SLEW?"))

    async def set_von(self, von: float) -> None:
        """Set the CC-mode starting voltage, in volts.

        The load begins sinking once the input rises above this and
        stops when it falls back below. On a battery or a supply with a
        slow rise this is what keeps the load off until the source is
        actually up.
        """
        von = float(von)
        if von < 0 or von > self.max_voltage:
            raise SetpointRefused(
                f"Starting voltage must be between 0 and {self.max_voltage}V")
        await self._command(f":SOUR:CURR:VON {von}")

    async def get_von(self) -> float:
        return float(await self._query(":SOUR:CURR:VON?"))

    # ------------------------------------------------------------------ #
    # Transient (dynamic) operation: Con / Pul / Tog
    # ------------------------------------------------------------------ #

    async def set_transient_enabled(self, enabled: bool) -> None:
        """Turn the transient generator on or off.

        :SOURce:TRANsient[:STATe]. The guide says running it is the same
        as pressing the TRAN key. Setting levels and timings does
        nothing visible until this is on, which is exactly the kind of
        thing that reads as "the command did not work".
        """
        state = "ON" if enabled else "OFF"
        await self._command(":SOUR:TRAN:STAT " + state)

    async def get_transient_enabled(self) -> bool:
        answer = (await self._query(":SOUR:TRAN:STAT?")).strip().upper()
        return answer in ("1", "ON")

    async def set_transient_mode(self, mode: str) -> None:
        """CONTinuous, PULSe or TOGGle: the Con/Pul/Tog front-panel keys.

        CONTinuous repeats a pulse stream after a trigger, PULSe gives a
        single pulse, TOGGle alternates between the two levels. All
        three are transient operation *within* CC mode.
        """
        word = _TRANSIENT_MODES.get(str(mode).strip().upper()[:3])
        if word is None:
            raise SetpointRefused(
                "Transient mode must be one of %s"
                % sorted(_TRANSIENT_MODES))
        await self._command(":SOUR:CURR:TRAN:MODE " + word)

    async def get_transient_mode(self) -> str:
        raw = (await self._query(":SOUR:CURR:TRAN:MODE?")).strip().upper()
        for short, long in _TRANSIENT_MODES.items():
            if raw.startswith(long.upper()[:4]) or raw.startswith(short):
                return short
        raise ValueError("Unexpected transient mode: %r" % raw)

    async def set_transient_levels(self, level_a: float,
                                   level_b: float) -> None:
        """Level A is the high value, Level B the low one, both in amps."""
        for name, value in (("Level A", level_a), ("Level B", level_b)):
            if float(value) < 0 or float(value) > self.max_current:
                raise SetpointRefused(
                    "%s must be between 0 and %sA" % (name, self.max_current))
        await self._command(":SOUR:CURR:TRAN:ALEV %s" % float(level_a))
        await self._command(":SOUR:CURR:TRAN:BLEV %s" % float(level_b))

    async def set_transient_widths(self, a_width_ms: float,
                                   b_width_ms: float) -> None:
        """How long each level is held, in milliseconds.

        Continuous and pulsed operation; in toggle the load alternates
        on triggers rather than on a clock.
        """
        for name, value in (("Level A width", a_width_ms),
                            ("Level B width", b_width_ms)):
            if float(value) <= 0:
                raise SetpointRefused("%s must be greater than 0 ms" % name)
        await self._command(":SOUR:CURR:TRAN:AWID %s" % float(a_width_ms))
        await self._command(":SOUR:CURR:TRAN:BWID %s" % float(b_width_ms))

    async def set_transient_frequency(self, frequency_khz: float) -> None:
        """Continuous-mode frequency, in kHz: the guide's unit, not Hz.

        The ceiling is per model, 15 kHz on the plain models and 30 on
        the "A" ones, and the spec table has it -- so unlike the CC slew
        rate this one can be checked here rather than left to the load.
        """
        frequency_khz = float(frequency_khz)
        ceiling = self.spec.max_dynamic_frequency / 1000.0
        if frequency_khz <= 0 or frequency_khz > ceiling:
            raise SetpointRefused(
                "Frequency must be between 0 and %g kHz on the %s"
                % (ceiling, self.spec.model))
        await self._command(":SOUR:CURR:TRAN:FREQ %s" % frequency_khz)

    async def set_transient_duty(self, duty_percent: float) -> None:
        """Continuous-mode duty cycle: the share of the period at Level A.

        The guide gives the range as an integer from 1 to 100.
        """
        duty = float(duty_percent)
        if duty < 1 or duty > 100:
            raise SetpointRefused("Duty cycle must be between 1 and 100%")
        await self._command(":SOUR:CURR:TRAN:ADUT %s" % duty)

    async def set_transient_slew(self, rising: float,
                                 falling: float) -> None:
        """Transient rising and falling rates, in A/us.

        :SLEW:POSitive and :SLEW:NEGative are the *transient* rates. CC
        mode has its own, :SLEW[:BOTH], which sets both directions
        together -- see set_slew_rate. Mixing the two up writes
        something real and unrelated, and reports success doing it.
        """
        for name, value in (("Rising rate", rising),
                            ("Falling rate", falling)):
            if float(value) <= 0:
                raise SetpointRefused("%s must be greater than 0 A/us" % name)
        await self._command(":SOUR:CURR:SLEW:POS %s" % float(rising))
        await self._command(":SOUR:CURR:SLEW:NEG %s" % float(falling))

    async def get_transient(self) -> Dict[str, Any]:
        """Everything the transient generator is currently set to."""
        out: Dict[str, Any] = {}
        fields = (
            ("enabled", ":SOUR:TRAN:STAT?"),
            ("mode", ":SOUR:CURR:TRAN:MODE?"),
            ("level_a", ":SOUR:CURR:TRAN:ALEV?"),
            ("level_b", ":SOUR:CURR:TRAN:BLEV?"),
            ("a_width_ms", ":SOUR:CURR:TRAN:AWID?"),
            ("b_width_ms", ":SOUR:CURR:TRAN:BWID?"),
            ("frequency_khz", ":SOUR:CURR:TRAN:FREQ?"),
            ("duty_percent", ":SOUR:CURR:TRAN:ADUT?"),
            ("rising_slew", ":SOUR:CURR:SLEW:POS?"),
            ("falling_slew", ":SOUR:CURR:SLEW:NEG?"),
        )
        for key, query in fields:
            try:
                raw = (await self._query(query)).strip()
                if key == "enabled":
                    out[key] = raw.upper() in ("1", "ON")
                elif key == "mode":
                    out[key] = self._transient_mode_from(raw)
                else:
                    out[key] = float(raw)
            except Exception as e:
                # One unreadable field must not lose the other nine.
                logger.debug("%s query failed: %s" % (key, e))
                out[key] = None
        return out

    @staticmethod
    def _transient_mode_from(raw: str) -> str:
        upper = raw.strip().upper()
        for short, long in _TRANSIENT_MODES.items():
            if upper.startswith(long.upper()[:4]) or upper.startswith(short):
                return short
        return raw

    # ------------------------------------------------------------------ #
    # Triggering
    # ------------------------------------------------------------------ #

    async def set_trigger_source(self, source: str) -> None:
        """BUS, EXTernal or MANUal."""
        word = _TRIGGER_SOURCES.get(str(source).strip().upper())
        if word is None:
            raise SetpointRefused(
                "Trigger source must be one of %s"
                % sorted(set(_TRIGGER_SOURCES.values())))
        await self._command(":TRIG:SOUR " + word)

    async def get_trigger_source(self) -> str:
        return (await self._query(":TRIG:SOUR?")).strip().upper()

    async def trigger(self) -> None:
        """Fire one trigger, selecting the bus source only if needed.

        The default source is MANUal, the front-panel TRAN key, and
        :TRIGger on a load still set to MANUal is accepted and does
        nothing -- so the source does have to be BUS. The first version
        of this set it unconditionally, immediately before firing, and
        that was worse than the problem it solved.

        Changing the trigger source disarms the transient generator. On
        the bench: enabling gave a flag of True and the load parked at
        Level B, which the user guide says is exactly right -- "the load
        sinks the current of Level B, and then waits trigger to occur" --
        and then trigger() set the source, the flag went False, and the
        current never left Level B. Arming and then disarming in the act
        of firing, every time, so the generator could never run.

        Reading it first costs one query and only writes when the
        source is actually wrong, which after the first call it never
        is.
        """
        try:
            source = await self.get_trigger_source()
        except Exception as e:
            # Not knowing is a reason to set it, not to skip it.
            logger.debug("%s: could not read the trigger source: %s"
                         % (self.resource_string, e))
            source = ""
        if not source.strip().upper().startswith("BUS"):
            await self.set_trigger_source("BUS")
        await self._command(":TRIG")

    async def get_options(self) -> Dict[str, Any]:
        """What ``*OPT?`` says is installed.

        The five are high slew rate, high frequency, high readback
        resolution, LAN and Digital I/O. The A models ship with all of
        them; a plain DL3021 or DL3031 can have them added with
        :LIC:SET. An uninstalled option comes back as "0", so the reply
        is positional-ish rather than a clean list, and the names are
        the instrument's own.

        Worth having for one reason in particular: "high frequency" is
        what decides whether the transient generator reaches 30 kHz or
        15, which is the ceiling set_transient_frequency enforces from
        the model table. A plain model with the option fitted is a case
        the table alone gets wrong.

        This is not a gate on List, the battery test or OCP/OPP. Those
        are standard on every model -- see the note at the top of this
        module, which used to say otherwise.
        """
        raw = (await self._query("*OPT?")).strip()
        installed = [
            part.strip() for part in raw.split(",")
            if part.strip() and part.strip() != "0"
        ]
        return {"raw": raw, "installed": installed}

    async def _refuse_if_sinking(self, what: str) -> None:
        """Stop a range change while current is flowing.

        The user guide is explicit, under Set Range: "Before switching
        the current range, please disable the channel input to avoid
        causing damage to the instrument or the DUT." Switching range
        moves the shunt the load regulates against, and doing that with
        the input live is what the caution is about.

        Refused here rather than warned about in one panel, so it holds
        for anything that drives this instrument. Refusing rather than
        turning the input off on the caller's behalf: disabling a load
        mid-test changes what the DUT sees, and that is the operator's
        decision, not a side effect of asking for a different range.
        """
        try:
            live = await self.get_input()
        except Exception as e:
            # Not knowing means not being able to promise it is safe.
            raise SetpointRefused(
                "Cannot tell whether the input is on, so %s is refused: %s"
                % (what, e))
        if live:
            raise SetpointRefused(
                "Disable the load input before changing the %s. Switching "
                "range with current flowing can damage the load or the "
                "device under test." % what)

    async def get_slew_limits(self) -> Dict[str, Optional[float]]:
        """The slew rates this load will currently accept, from the load.

        :CURRent:SLEW? takes MINimum and MAXimum, so the limits can be
        asked for rather than guessed -- and they have to be, because
        they move with the current range. On the bench in the 4 A range
        the CC rate took 0.24 A/us and refused 0.5; a number written
        into the driver per model would have been wrong the moment
        somebody switched range.
        """
        out: Dict[str, Optional[float]] = {}
        for key, query in (
            ("cc_min", ":SOUR:CURR:SLEW? MIN"),
            ("cc_max", ":SOUR:CURR:SLEW? MAX"),
            ("transient_min", ":SOUR:CURR:SLEW:POS? MIN"),
            ("transient_max", ":SOUR:CURR:SLEW:POS? MAX"),
        ):
            try:
                value = float((await self._query(query)).strip())
            except Exception as e:
                logger.debug("%s query failed: %s" % (key, e))
                out[key] = None
                continue
            # A maximum of zero is the load declining to answer, not a
            # limit. The transient pair reads 0.0 for both until a
            # transient mode has been set -- seen on the bench, where
            # :SLEW:POS? MIN|MAX returned 0.0/0.0 in plain CC and
            # 0.001/0.3 the moment CON was selected. Handing a caller a
            # range of zero to zero would range a control to nothing.
            out[key] = None if (key.endswith("_max") and value == 0) else value
        return out

    # ------------------------------------------------------------------ #
    # Function modes: list, battery discharge, OCP and OPP
    # ------------------------------------------------------------------ #

    async def set_function_mode(self, function_mode: str) -> None:
        """Choose which subsystem drives the input.

        This is a different axis from set_mode. set_mode picks the
        regulation law -- CC, CV, CR, CP -- while this picks what is
        allowed to move the setpoint: the fixed level, a list, the
        battery discharge, or one of the protection tests. The guide
        puts it as "what controls the input regulation mode".

        Leaving a test mode means coming back to FIX, which is why that
        is spelled out rather than being something a caller has to know.
        """
        wanted = str(function_mode).strip().upper()
        # Accept the long spellings the guide prints for the setting,
        # since a caller reading the manual will type those.
        wanted = {"FIXED": "FIX", "WAVE": "WAV", "WAVEFORM": "WAV",
                  "BATTERY": "BATT", "BATTARY": "BATT"}.get(wanted, wanted)
        if wanted not in _FUNCTION_MODES:
            raise SetpointRefused(
                "Unknown function mode %r. This load has: %s"
                % (function_mode, ", ".join(_FUNCTION_MODES)))
        await self._command(f":SOUR:FUNC:MODE {wanted}")

        # Read it back, because this command lies. On the bench the load
        # went into LIST and then BATT happily, and from BATT it took
        # :SOUR:FUNC:MODE OCP, then OPP, then FIX without a murmur --
        # accepted each one, left the error queue clean, and stayed in
        # BATT throughout. An unchecked write here is a mode switch that
        # reports success and does nothing, which is how the trigger and
        # the short-form :SOUR:FUNC bugs both looked.
        #
        # The way out of a mode is to assert the one you want: issuing
        # the owning subsystem's command reclaims the setpoint, and
        # set_mode is what does that for fixed operation. Said in the
        # message, because whoever hits this needs to know it.
        try:
            arrived = await self.get_function_mode()
        except Exception as e:
            logger.debug("%s: could not confirm the function mode: %s"
                         % (self.resource_string, e))
            return
        if arrived != wanted:
            raise CommandRejected(
                "%s stayed in %s when asked for %s. This load accepts "
                ":SOUR:FUNC:MODE and ignores it when it will not leave the "
                "mode it is in -- to go back to fixed operation, set the "
                "regulation mode (set_mode) instead, which reclaims the "
                "setpoint for the FUNCtion command."
                % (self.model, _FUNCTION_MODE_NAMES.get(arrived, arrived),
                   _FUNCTION_MODE_NAMES.get(wanted, wanted)))

    async def get_function_mode(self) -> str:
        """Which subsystem is driving the input: FIX, LIST, WAV, BATT,
        OCP or OPP."""
        raw = (await self._query(":SOUR:FUNC:MODE?")).strip().upper()
        for known in _FUNCTION_MODES:
            if raw.startswith(known):
                return known
        raise ValueError(f"Unexpected :SOUR:FUNC:MODE? response: {raw!r}")

    def _function_parameter(self, name: str):
        try:
            return _FUNCTION_PARAMETERS[name]
        except KeyError:
            raise SetpointRefused(
                "Unknown function-mode parameter %r" % (name,))

    async def set_function_parameter(self, name: str, value: float) -> None:
        """Set one parameter of a function mode, checked against the
        load's ratings.

        One method rather than twenty-eight near-identical ones: they
        are all a scalar with a unit and a ceiling, and writing them out
        by hand would be twenty-eight chances to paste the wrong SCPI
        tail.
        """
        scpi, unit, limit_attr = self._function_parameter(name)
        value = float(value)
        if name in _FUNCTION_RANGE_PARAMETERS:
            await self._refuse_if_sinking(_FUNCTION_RANGE_PARAMETERS[name])
        if value < 0:
            raise SetpointRefused(
                "%s cannot be negative" % name.replace("_", " ").capitalize())
        if limit_attr is not None:
            ceiling = getattr(self, limit_attr)
            if value > ceiling:
                raise SetpointRefused(
                    "%s must be between 0 and %g%s"
                    % (name.replace("_", " ").capitalize(), ceiling, unit))
        await self._command(f"{scpi} {value}")

    async def get_function_parameter(self, name: str) -> float:
        """Read one function-mode parameter back from the load."""
        scpi, _unit, _limit = self._function_parameter(name)
        return float((await self._query(f"{scpi}?")).strip())

    async def set_battery_cutoffs(
        self,
        volts: Optional[bool] = None,
        capacity: Optional[bool] = None,
        time: Optional[bool] = None,
    ) -> None:
        """Arm or disarm each battery discharge cut-off.

        Three independent switches, and a discharge with all three off
        runs until something else stops it. They are separate commands
        on the load, so they are separate arguments here -- passing None
        leaves one alone rather than quietly turning it off.
        """
        for value, scpi in ((volts, ":SOUR:BATT:VENabstop"),
                            (capacity, ":SOUR:BATT:CENabstop"),
                            (time, ":SOUR:BATT:TENabstop")):
            if value is None:
                continue
            await self._command(f"{scpi} {1 if value else 0}")

    async def get_battery_cutoffs(self) -> Dict[str, Optional[bool]]:
        """Which battery cut-offs are armed."""
        out: Dict[str, Optional[bool]] = {}
        for key, scpi in (("volts", ":SOUR:BATT:VENabstop?"),
                          ("capacity", ":SOUR:BATT:CENabstop?"),
                          ("time", ":SOUR:BATT:TENabstop?")):
            try:
                out[key] = (await self._query(scpi)).strip() in ("1", "ON")
            except Exception as e:
                logger.debug("%s cut-off query failed: %s" % (key, e))
                out[key] = None
        return out

    async def get_battery_results(self) -> Dict[str, Optional[float]]:
        """What the discharge has measured so far.

        Live during the run, and still readable after it stops, which is
        the only way to get the result out: the load shows it on the
        front panel and has no "test finished" query.
        """
        out: Dict[str, Optional[float]] = {}
        for key, scpi in _BATTERY_RESULTS.items():
            try:
                out[key] = float((await self._query(scpi)).strip())
            except Exception as e:
                logger.debug("%s query failed: %s" % (key, e))
                out[key] = None
        return out

    async def set_list_step(
        self,
        step: int,
        level: Optional[float] = None,
        width: Optional[float] = None,
        slew: Optional[float] = None,
    ) -> None:
        """Set one step of the list.

        :LIST:LEVel, :WIDth and :SLEW all take <step>,<value>, so a step
        is the unit a caller thinks in. Steps are numbered from 1, as
        the front panel numbers them.
        """
        step = int(step)
        if step < 1:
            raise SetpointRefused("List steps are numbered from 1")
        for value, scpi in ((level, ":SOUR:LIST:LEV"),
                            (width, ":SOUR:LIST:WID"),
                            (slew, ":SOUR:LIST:SLEW")):
            if value is None:
                continue
            await self._command(f"{scpi} {step},{float(value)}")

    async def get_list_step(self, step: int) -> Dict[str, Optional[float]]:
        """Read one step of the list back."""
        step = int(step)
        out: Dict[str, Optional[float]] = {}
        for key, scpi in (("level", ":SOUR:LIST:LEV?"),
                          ("width", ":SOUR:LIST:WID?"),
                          ("slew", ":SOUR:LIST:SLEW?")):
            try:
                out[key] = float((await self._query(f"{scpi} {step}")).strip())
            except Exception as e:
                logger.debug("list step %d %s query failed: %s"
                             % (step, key, e))
                out[key] = None
        return out

    async def set_list_mode(self, mode: str) -> None:
        """The regulation law the list runs under: CC, CV, CR or CP."""
        mode_upper = str(mode).strip().upper()
        if mode_upper not in _MODE_TO_FUNCTION:
            raise SetpointRefused(
                "Unknown list mode %r. This load has: %s"
                % (mode, ", ".join(_MODE_TO_FUNCTION)))
        await self._command(f":SOUR:LIST:MODE {mode_upper}")

    async def get_list_mode(self) -> str:
        raw = (await self._query(":SOUR:LIST:MODE?")).strip().upper()
        mode = _FUNCTION_TO_MODE.get(raw)
        if mode is None:
            raise ValueError(f"Unexpected :SOUR:LIST:MODE? response: {raw!r}")
        return mode

    async def set_list_end_state(self, hold_last: bool) -> None:
        """What the input does when the list finishes: hold the last
        step, or switch off."""
        await self._command(
            f":SOUR:LIST:END {'LAST' if hold_last else 'OFF'}")

    async def get_list_end_state(self) -> bool:
        raw = (await self._query(":SOUR:LIST:END?")).strip().upper()
        return raw.startswith("LAST")

    async def get_protection_status(self) -> Dict[str, Any]:
        """What the load's questionable status register is reporting.

        This is the closest thing to a result the protection tests
        have. OCP and OPP are all setters in the command tree -- there
        is no query for the current or power a device under test tripped
        at, and no pass/fail -- so the register's overcurrent and
        overpower flags are what a caller can actually read back.

        ``raw`` is returned as well as the decoded flags because the
        guide's bit table is only legible for the low bits; see
        _QUESTIONABLE_BITS.
        """
        raw = int(float((await self._query(":STAT:QUES:COND?")).strip()))
        flags = {name: bool(raw & weight)
                 for weight, (name, _why) in _QUESTIONABLE_BITS.items()}
        return {"raw": raw, **flags}

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
        await self._command("*RST")

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
