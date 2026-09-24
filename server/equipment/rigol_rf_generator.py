"""Rigol DSG800 / DSG3000 / DSG3000B / DSG5000 RF signal generator drivers.

Protocol references (text in ``~/Manuals/Rigol/_text_extracted``):

* "DSG800 Programming Guide" (primary; DSG815/DSG830 examples)
* "DSG3000 Programming Guide" (DSG3030/DSG3060)
* "DSG3000B Programming Guide" (DSG3065B/DSG3136B and -IQ variants)
* "DSG5000 Programming Guide" (DSG51xx / DSG52xx multi-channel microwave
  generators; every SOURce command takes an optional ``[:RF<channel>]`` node)
* the four family data sheets for the setting ranges in the model table.

Command tree used here (identical across the families unless noted):

=============================  ==================================================
LabLink                        SCPI
=============================  ==================================================
frequency                      ``[:SOURce]:FREQuency <value>`` / ``?``
frequency step                 ``[:SOURce]:FREQuency:STEP`` (not on DSG5000)
level                          ``[:SOURce]:LEVel <value>[unit]`` / ``?`` (dBm)
level step                     ``[:SOURce]:LEVel:STEP`` (not on DSG5000)
level unit                     ``:UNIT:POWer DBM|DBMV|DBUV|V|W``
RF output                      ``:OUTPut[:STATe]`` (DSG5000: ``[:RF<n>]:OUTPut``)
ALC                            ``[:SOURce]:LEVel:ALC:MODE OFF|ON|AUTO`` (DSG3000 only)
modulation master switch       ``[:SOURce]:MODulation:STATe``
AM                             ``:AM:STATe / :AM[:DEPTh] / :AM:FREQuency / :AM:SOURce / :AM:WAVEform``
FM                             ``:FM:STATe / :FM[:DEViation] / :FM:FREQuency / :FM:SOURce / :FM:WAVEform``
PM (phase)                     ``:PM:STATe / :PM[:DEViation] / :PM:FREQuency / :PM:SOURce / :PM:WAVEform``
FM/PM selector                 ``:FMPM:TYPE FM|PM`` (DSG800/3000/3000B)
pulse modulation               ``:PULM:STATe / :PULM:SOURce / :PULM:PERiod / :PULM:WIDTh / :PULM:POLarity / :PULM:MODE``
IQ modulation                  ``:IQ:MODe:STATe / :IQ:MODe INTernal|EXTernal`` (option on DSG800/3000, -IQ on 3000B)
sweep                          ``:SWEep:STATe OFF|FREQuency|LEVel|LEVel,FREQuency``, ``:SWEep:TYPE LIST|STEP``,
                               ``:SWEep:MODE CONTinue|SINGle``, ``:SWEep:STEP:STARt/STOP:FREQuency/LEVel``,
                               ``:SWEep:STEP:POINts / :DWELl / :SPACing / :SHAPe``, ``:SWEep:DIRection``, ``:SWEep:EXECute``
trigger                        ``*TRG``, ``:TRIGger[:SWEep][:IMMediate]``, ``:TRIGger:PULSe[:IMMediate]``
preset                         ``:SYSTem:PRESet`` (all); ``*RST`` (DSG3000, DSG5000 only)
=============================  ==================================================

Quirks:

* The DSG800 and DSG3000B return "Number + Unit" strings for most queries
  (``:FREQ?`` -> ``4.00000000MHz``, ``:AM:FREQ?`` -> ``20.00000kHz``,
  ``:PULM:PER?`` -> ``1.000000000s``) while the DSG3000 and DSG5000 return
  plain numbers (``4000000``). :func:`parse_si` handles both; note ``mHz`` is
  milli-hertz and ``MHz`` is mega-hertz, so the suffix is case sensitive.
* ``:LEVel?`` always returns dBm regardless of ``:UNIT:POWer``.
* None of the four guides documents ``:SYSTem:ERRor?``; :meth:`get_error`
  is best effort and returns ``code=None`` when the query fails.
* The DSG800 and DSG3000B document only ``*IDN?`` and ``*TRG`` as IEEE-488.2
  common commands; reset uses ``:SYSTem:PRESet`` on those families.

*IDN? returns ``Rigol Technologies,<model>,<serial>,<firmware>`` (DSG5000:
``RIGOL TECHNOLOGIES,...``).
"""

import logging
import math
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from shared.models.data import RFGeneratorData
from shared.models.equipment import (EquipmentInfo, EquipmentStatus,
                                     EquipmentType)

from .base import (BaseEquipment, SetpointRefused,
                    generate_equipment_id)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Model table
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DSGModelSpec:
    """Setting ranges and feature flags of one DSG model."""

    model: str
    family: str  # DSG800 | DSG3000 | DSG3000B | DSG5000
    freq_min: float  # Hz
    freq_max: float  # Hz
    level_min: float  # dBm, setting range lower limit
    level_max: float  # dBm, setting range upper limit
    has_iq: bool  # IQ modulation fitted (or orderable as an option)
    has_pulse: bool  # pulse modulation fitted (or orderable as an option)
    channels: int = 1
    iq_is_option: bool = False
    pulse_is_option: bool = False
    has_alc_command: bool = False  # [:SOURce]:LEVel:ALC:MODE documented
    has_ieee_reset: bool = False  # *RST / *CLS documented
    has_fmpm_type: bool = True  # [:SOURce]:FMPM:TYPE documented
    has_step_commands: bool = True  # :FREQuency:STEP / :LEVel:STEP documented
    has_lf_output: bool = True  # [:SOURce]:LFOutput documented
    channel_prefixed: bool = False  # commands take [:RF<n>] (DSG5000)
    source: str = ""


def _dsg800(model: str, fmax: float) -> DSGModelSpec:
    # DSG800 Programming Guide: :FREQ 9 kHz..3 GHz (DSG830), :LEV -110..+20 dBm;
    # DSG800 Data Sheet "Frequency Range" table (DSG815 1.5 GHz, DSG821(A)
    # 2.1 GHz, DSG830 3 GHz, DSG836(A) 3.6 GHz) and "Amplitude / Setting
    # range" -110 dBm..+20 dBm. Pulse needs DSG800-PUM, IQ needs DSG800-IQ.
    return DSGModelSpec(
        model, "DSG800", 9e3, fmax, -110.0, 20.0,
        has_iq=True, has_pulse=True, iq_is_option=True, pulse_is_option=True,
        has_alc_command=False, has_ieee_reset=False,
        source="DSG800 Programming Guide [:SOURce]:FREQuency / [:SOURce]:LEVel; DSG800 Data Sheet",
    )


def _dsg3000(model: str, fmax: float) -> DSGModelSpec:
    # DSG3000 Programming Guide: :FREQ 9 kHz..6 GHz (DSG3060), :LEV -140..+20 dBm;
    # DSG3000 Data Sheet "Level / Setting range": -140 dBm to +25 dBm
    # (1 MHz..3 GHz). The data sheet setting range is used as the upper limit;
    # see docs/RIGOL_DSG.md for the contradiction. Pulse modulation standard,
    # IQ needs the IQ-DSG3000 option.
    return DSGModelSpec(
        model, "DSG3000", 9e3, fmax, -140.0, 25.0,
        has_iq=True, has_pulse=True, iq_is_option=True, pulse_is_option=False,
        has_alc_command=True, has_ieee_reset=True,
        source="DSG3000 Programming Guide [:SOURce]:FREQuency / [:SOURce]:LEVel; DSG3000 Data Sheet",
    )


def _dsg3000b(model: str, fmax: float, iq: bool) -> DSGModelSpec:
    # DSG3000B Programming Guide: :FREQ 9 kHz..13.6 GHz (DSG3136B), :LEV -130..+27 dBm;
    # model table: DSG3065B 6.5 GHz, DSG3136B 13.6 GHz, "-IQ" suffix = IQ fitted.
    return DSGModelSpec(
        model, "DSG3000B", 9e3, fmax, -130.0, 27.0,
        has_iq=iq, has_pulse=True, iq_is_option=False, pulse_is_option=False,
        has_alc_command=False, has_ieee_reset=False,
        source="DSG3000B Programming Guide model table, [:SOURce]:FREQuency / [:SOURce]:LEVel; DSG3000B Data Sheet",
    )


def _dsg5000(model: str, fmax: float, channels: int) -> DSGModelSpec:
    # DSG5000 Programming Guide: model table (DSG51xx 12 GHz, DSG52xx 20 GHz,
    # 2/4/6/8 channels), [:SOURce][:RF]:LEVel -30..+25 dBm, [:RF<n>] prefix,
    # *RST/*CLS documented, no IQ subsystem, pulse needs DSG5000-PUL.
    return DSGModelSpec(
        model, "DSG5000", 9e3, fmax, -30.0, 25.0,
        has_iq=False, has_pulse=True, pulse_is_option=True, channels=channels,
        has_alc_command=False, has_ieee_reset=True, has_fmpm_type=False,
        has_step_commands=False, has_lf_output=False, channel_prefixed=True,
        source="DSG5000 Programming Guide 'Content Conventions' model table, [:SOURce][:RF]:LEVel; DSG5000 Data Sheet",
    )


DSG_MODELS: Dict[str, DSGModelSpec] = {
    # DSG800
    "DSG815": _dsg800("DSG815", 1.5e9),
    "DSG821": _dsg800("DSG821", 2.1e9),
    "DSG821A": _dsg800("DSG821A", 2.1e9),
    "DSG830": _dsg800("DSG830", 3.0e9),
    "DSG836": _dsg800("DSG836", 3.6e9),
    "DSG836A": _dsg800("DSG836A", 3.6e9),
    # DSG3000
    "DSG3030": _dsg3000("DSG3030", 3.0e9),
    "DSG3060": _dsg3000("DSG3060", 6.0e9),
    # DSG3000B
    "DSG3065B": _dsg3000b("DSG3065B", 6.5e9, iq=False),
    "DSG3065B-IQ": _dsg3000b("DSG3065B-IQ", 6.5e9, iq=True),
    "DSG3136B": _dsg3000b("DSG3136B", 13.6e9, iq=False),
    "DSG3136B-IQ": _dsg3000b("DSG3136B-IQ", 13.6e9, iq=True),
    # DSG5000
    "DSG5122": _dsg5000("DSG5122", 12e9, 2),
    "DSG5124": _dsg5000("DSG5124", 12e9, 4),
    "DSG5126": _dsg5000("DSG5126", 12e9, 6),
    "DSG5128": _dsg5000("DSG5128", 12e9, 8),
    "DSG5202": _dsg5000("DSG5202", 20e9, 2),
    "DSG5204": _dsg5000("DSG5204", 20e9, 4),
    "DSG5206": _dsg5000("DSG5206", 20e9, 6),
    "DSG5208": _dsg5000("DSG5208", 20e9, 8),
}


def lookup_dsg_model(model: Optional[str]) -> Optional[DSGModelSpec]:
    """Find the spec for a model string from *IDN? (case-insensitive)."""
    if not model:
        return None
    key = model.strip().upper().replace(" ", "")
    if key in DSG_MODELS:
        return DSG_MODELS[key]
    # Longest matching prefix, e.g. "DSG3136B-IQ(xx)" or "DSG830-PUM".
    for name in sorted(DSG_MODELS, key=len, reverse=True):
        if key.startswith(name):
            return DSG_MODELS[name]
    return None


# --------------------------------------------------------------------------- #
# Value parsing / formatting
# --------------------------------------------------------------------------- #

_SI_PREFIX = {
    "": 1.0, "G": 1e9, "M": 1e6, "k": 1e3, "K": 1e3, "m": 1e-3,
    "u": 1e-6, "µ": 1e-6, "μ": 1e-6, "n": 1e-9, "p": 1e-12,
}
# Unit words in the order they must be tried (longest first).
_UNIT_WORDS = ("dBmV", "dBuV", "dBµV", "dBμV", "dBm", "dB", "Hz", "rad", "deg", "s", "V", "W", "%")
_NUM_RE = re.compile(r"^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*([A-Za-zµμ%]*)\s*$")


def parse_si(text: str) -> Optional[float]:
    """Parse ``4.00000000MHz``, ``20.00000kHz``, ``1.000000000s``, ``2.00``,
    ``-20.00dBm``, ``281.50mV`` or a plain number into a float in base units.

    Returns None if the text is not numeric. SI prefixes are case sensitive
    (``m`` milli, ``M`` mega) because the DSG guides use both ``mHz`` and
    ``MHz``.
    """
    if text is None:
        return None
    m = _NUM_RE.match(str(text).strip().strip('"'))
    if not m:
        return None
    number, suffix = m.group(1), m.group(2)
    try:
        value = float(number)
    except ValueError:
        return None
    if not suffix:
        return value
    # Strip the unit word (longest match first); what is left is the SI prefix.
    prefix = None
    for word in _UNIT_WORDS:
        if suffix.endswith(word):
            prefix = suffix[: -len(word)]
            break
    if prefix is None:
        # No unit word: accept a bare prefix ("k") and ignore anything else.
        prefix = suffix if suffix in _SI_PREFIX else ""
    return value * _SI_PREFIX.get(prefix, 1.0)


def parse_bool(text: str) -> bool:
    return str(text).strip().upper() in ("1", "ON", "TRUE")


def fmt_number(value: float) -> str:
    """Format a value for the instrument without exponent surprises."""
    value = float(value)
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return f"{value:.12g}"


def level_to_dbm(level: float, unit: str = "dBm") -> float:
    """Convert a level in dBm/dBmV/dBuV/V/W (50 Ohm) to dBm for validation."""
    u = str(unit).strip().upper().replace("Μ", "U").replace("µ", "U")
    level = float(level)
    if u in ("DBM", ""):
        return level
    if u == "DBMV":
        return level - 46.99
    if u in ("DBUV", "DBµV", "DBΜV"):
        return level - 106.99
    if u == "V":
        if level <= 0:
            raise ValueError("Voltage level must be > 0 V")
        return 10.0 * math.log10(level * level / 50.0 / 1e-3)
    if u == "W":
        if level <= 0:
            raise ValueError("Power level must be > 0 W")
        return 10.0 * math.log10(level / 1e-3)
    raise ValueError("Level unit must be dBm, dBmV, dBuV, V or W")


_UNIT_SCPI = {"DBM": "DBM", "DBMV": "DBMV", "DBUV": "DBUV", "V": "V", "W": "W"}
_UNIT_SUFFIX = {"DBM": "dBm", "DBMV": "dBmV", "DBUV": "dBuV", "V": "V", "W": "W"}
_UNIT_DISPLAY = {"DBM": "dBm", "DBMV": "dBmV", "DBUV": "dBuV", "V": "V", "W": "W"}


def normalize_level_unit(unit: str) -> str:
    key = str(unit).strip().upper().replace("µ", "U").replace("Μ", "U")
    if key not in _UNIT_SCPI:
        raise ValueError("Level unit must be dBm, dBmV, dBuV, V or W")
    return key


_MOD_TYPES = ("AM", "FM", "PM", "PULSE", "IQ")
_MOD_ALIASES = {
    "AM": "AM", "FM": "FM", "PM": "PM", "PHM": "PM", "ΦM": "PM", "PHASE": "PM",
    "PULSE": "PULSE", "PULM": "PULSE", "PUL": "PULSE", "IQ": "IQ", "I/Q": "IQ", "VECTOR": "IQ",
}
_MOD_ROOT = {"AM": "AM", "FM": "FM", "PM": "PM", "PULSE": "PULM", "IQ": "IQ"}
_SOURCES = {"INT": "INTernal", "INTERNAL": "INTernal", "EXT": "EXTernal", "EXTERNAL": "EXTernal"}
_WAVEFORMS = {"SINE": "SINE", "SIN": "SINE", "SQUARE": "SQUA", "SQU": "SQUA", "SQUA": "SQUA"}
_SWEEP_STATES = {
    "OFF": "OFF", "NONE": "OFF",
    "FREQ": "FREQuency", "FREQUENCY": "FREQuency",
    "LEVEL": "LEVel", "LEV": "LEVel", "POWER": "LEVel",
    "BOTH": "LEVel,FREQuency", "LEVEL,FREQUENCY": "LEVel,FREQuency", "LEV,FREQ": "LEVel,FREQuency",
    "FREQ,LEV": "LEVel,FREQuency", "FREQUENCY,LEVEL": "LEVel,FREQuency",
}


# --------------------------------------------------------------------------- #
# Base driver
# --------------------------------------------------------------------------- #


class RigolDSGBase(BaseEquipment):
    """Common implementation for all Rigol DSG RF signal generators.

    The concrete :class:`DSGModelSpec` is chosen from ``*IDN?`` at connect
    time; ``DEFAULT_MODEL`` is used before identification or when the model
    is unknown.
    """

    DEFAULT_MODEL = "DSG830"
    INTERFACES: Sequence[str] = ("USB", "LAN")

    def __init__(self, resource_manager, resource_string: str):
        super().__init__(resource_manager, resource_string)
        self.manufacturer = "Rigol"
        self.model = self.DEFAULT_MODEL
        self.serial_number: Optional[str] = None
        self.firmware_version: Optional[str] = None
        self.spec: DSGModelSpec = DSG_MODELS[self.DEFAULT_MODEL]
        self._level_unit: str = "DBM"

    # ------------------------------------------------------------------ #
    # Identification
    # ------------------------------------------------------------------ #

    def _parse_idn(self, idn: str) -> Dict[str, Optional[str]]:
        parts = [p.strip() for p in idn.split(",")]
        info = {
            "manufacturer": parts[0] if len(parts) > 0 and parts[0] else self.manufacturer,
            "model": parts[1] if len(parts) > 1 and parts[1] else self.model,
            "serial": parts[2] if len(parts) > 2 and parts[2] else None,
            "firmware": parts[3] if len(parts) > 3 and parts[3] else None,
        }
        spec = lookup_dsg_model(info["model"])
        if spec is not None:
            if spec.model != self.spec.model:
                logger.info(f"Identified {info['model']}: using {spec.model} limits")
            self.spec = spec
        elif info["model"] != self.model:
            logger.warning(f"Unknown DSG model '{info['model']}', keeping {self.spec.model} limits")
        self.model = info["model"] or self.model
        self.serial_number = info["serial"]
        self.firmware_version = info["firmware"]
        return info

    async def get_info(self) -> EquipmentInfo:
        idn = await self._query("*IDN?")
        info = self._parse_idn(idn)
        return EquipmentInfo(
            id=generate_equipment_id(self.resource_string, "rfgen_"),
            type=EquipmentType.RF_SIGNAL_GENERATOR,
            manufacturer=info["manufacturer"] or self.manufacturer,
            model=info["model"] or self.model,
            serial_number=info["serial"],
            connection_type=self._determine_connection_type(),
            resource_string=self.resource_string,
        )

    def _capabilities(self) -> Dict[str, Any]:
        s = self.spec
        mods = ["AM", "FM", "PM"]
        if s.has_pulse:
            mods.append("PULSE")
        if s.has_iq:
            mods.append("IQ")
        return {
            "family": s.family,
            "channels": s.channels,
            "frequency_min": s.freq_min,
            "frequency_max": s.freq_max,
            "level_min_dbm": s.level_min,
            "level_max_dbm": s.level_max,
            "has_iq": s.has_iq,
            "iq_is_option": s.iq_is_option,
            "has_pulse": s.has_pulse,
            "pulse_is_option": s.pulse_is_option,
            "has_alc_control": s.has_alc_command,
            "modulation_types": mods,
            "level_units": ["dBm", "dBmV", "dBuV", "V", "W"],
            "sweep_types": ["STEP", "LIST"],
            "interfaces": list(self.INTERFACES),
            "measurement_channels": ["FREQ", "LEVEL", "OUTPUT"],
            "supports_acquisition": True,
        }

    async def get_status(self) -> EquipmentStatus:
        try:
            idn = await self._query("*IDN?")
            info = self._parse_idn(idn)
            capabilities = self._capabilities()
            try:
                capabilities["output_enabled"] = await self.get_output()
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

    # ------------------------------------------------------------------ #
    # Command helpers
    # ------------------------------------------------------------------ #

    def _check_channel(self, channel: Any) -> int:
        try:
            ch = int(channel) if channel is not None else 1
        except (TypeError, ValueError):
            raise ValueError(f"Channel must be an integer 1..{self.spec.channels}")
        if not 1 <= ch <= self.spec.channels:
            raise ValueError(f"{self.spec.model} has channels 1..{self.spec.channels}")
        return ch

    def _src(self, channel: int = 1) -> str:
        """``:SOURce`` root, with the ``:RF<n>`` node on multi-channel models."""
        if self.spec.channel_prefixed:
            return f":SOURce:RF{channel}"
        return ":SOURce"

    def _outp(self, channel: int = 1) -> str:
        if self.spec.channel_prefixed:
            return f":RF{channel}:OUTPut:STATe"
        return ":OUTPut:STATe"

    def _unit_cmd(self, channel: int = 1) -> str:
        if self.spec.channel_prefixed:
            return f":UNIT:RF{channel}:POWer"
        return ":UNIT:POWer"

    async def _query_float(self, cmd: str) -> Optional[float]:
        return parse_si(await self._query(cmd))

    # ------------------------------------------------------------------ #
    # Command dispatch
    # ------------------------------------------------------------------ #

    async def execute_command(self, command: str, parameters: dict) -> Any:
        parameters = dict(parameters or {})
        handlers = {
            # carrier
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
            # modulation
            "set_modulation": self.set_modulation,
            "get_modulation": self.get_modulation,
            "set_modulation_master": self.set_modulation_master,
            "get_modulation_master": self.get_modulation_master,
            "set_lf_output": self.set_lf_output,
            # sweep
            "set_sweep": self.set_sweep,
            "get_sweep": self.get_sweep,
            "execute_sweep": self.execute_sweep,
            "trigger": self.trigger,
            # readings / hooks
            "get_readings": self.get_readings,
            "get_measurement": self.get_measurement,
            "get_measurements": self.get_measurements,
            "get_state": self.get_state,
            # system
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
    # Frequency / level / output
    # ------------------------------------------------------------------ #

    async def set_frequency(self, frequency: float, channel: int = 1) -> float:
        """Set the carrier frequency in Hz (validated against the model)."""
        ch = self._check_channel(channel)
        frequency = float(frequency)
        s = self.spec
        if not s.freq_min <= frequency <= s.freq_max:
            raise SetpointRefused(
                f"Frequency must be between {s.freq_min:g} Hz and {s.freq_max:g} Hz on the {s.model}"
            )
        await self._write(f"{self._src(ch)}:FREQuency {fmt_number(frequency)}")
        return await self.get_frequency(ch)

    async def get_frequency(self, channel: int = 1) -> float:
        ch = self._check_channel(channel)
        value = await self._query_float(f"{self._src(ch)}:FREQuency?")
        if value is None:
            raise ValueError("Unexpected :FREQuency? response")
        return value

    async def set_frequency_step(self, step: float, channel: int = 1) -> float:
        """Knob/step increment for the frequency (DSG800/3000/3000B)."""
        ch = self._check_channel(channel)
        if not self.spec.has_step_commands:
            raise ValueError(f"{self.spec.model} does not document :FREQuency:STEP")
        step = float(step)
        if step <= 0:
            raise ValueError("Frequency step must be > 0 Hz")
        await self._write(f"{self._src(ch)}:FREQuency:STEP {fmt_number(step)}")
        value = await self._query_float(f"{self._src(ch)}:FREQuency:STEP?")
        return value if value is not None else step

    async def set_level(self, level: float, unit: str = "dBm", channel: int = 1) -> float:
        """Set the output level; ``unit`` is dBm (default), dBmV, dBuV, V or W.

        The value is validated in dBm against the model's setting range and
        sent in "Number + Unit" form. Returns the level in dBm as read back.
        """
        ch = self._check_channel(channel)
        key = normalize_level_unit(unit)
        level = float(level)
        dbm = level_to_dbm(level, key)
        s = self.spec
        if not s.level_min - 1e-9 <= dbm <= s.level_max + 1e-9:
            raise ValueError(
                f"Level {level:g} {_UNIT_DISPLAY[key]} ({dbm:.2f} dBm) is outside "
                f"{s.level_min:g}..{s.level_max:g} dBm on the {s.model}"
            )
        if key == "DBM":
            await self._write(f"{self._src(ch)}:LEVel {level:.2f}")
        else:
            await self._write(f"{self._src(ch)}:LEVel {fmt_number(level)}{_UNIT_SUFFIX[key]}")
        return await self.get_level(ch)

    async def get_level(self, channel: int = 1) -> float:
        """Output level in dBm (the query always returns dBm)."""
        ch = self._check_channel(channel)
        value = await self._query_float(f"{self._src(ch)}:LEVel?")
        if value is None:
            raise ValueError("Unexpected :LEVel? response")
        return value

    async def set_level_step(self, step_db: float, channel: int = 1) -> float:
        ch = self._check_channel(channel)
        if not self.spec.has_step_commands:
            raise ValueError(f"{self.spec.model} does not document :LEVel:STEP")
        step_db = float(step_db)
        if not 0.01 <= step_db <= 100.0:
            raise ValueError("Level step must be 0.01..100 dB")
        await self._write(f"{self._src(ch)}:LEVel:STEP {step_db:g}")
        value = await self._query_float(f"{self._src(ch)}:LEVel:STEP?")
        return value if value is not None else step_db

    async def set_level_unit(self, unit: str = "dBm", channel: int = 1) -> str:
        """Display/entry unit for the level (:UNIT:POWer)."""
        ch = self._check_channel(channel)
        key = normalize_level_unit(unit)
        await self._write(f"{self._unit_cmd(ch)} {_UNIT_SCPI[key]}")
        return await self.get_level_unit(ch)

    async def get_level_unit(self, channel: int = 1) -> str:
        ch = self._check_channel(channel)
        raw = (await self._query(f"{self._unit_cmd(ch)}?")).strip().upper()
        key = raw.replace("µ", "U")
        self._level_unit = key if key in _UNIT_DISPLAY else "DBM"
        return _UNIT_DISPLAY.get(key, raw)

    async def set_output(self, enabled: bool, channel: int = 1) -> bool:
        """RF output on/off. Called with False by the manager on disconnect."""
        ch = self._check_channel(channel)
        await self._write(f"{self._outp(ch)} {'ON' if enabled else 'OFF'}")
        return await self.get_output(ch)

    async def get_output(self, channel: int = 1) -> bool:
        ch = self._check_channel(channel)
        return parse_bool(await self._query(f"{self._outp(ch)}?"))

    async def set_all_outputs(self, enabled: bool) -> Dict[int, bool]:
        """Every channel's RF output (DSG5000 ``:RFALl:OUTPut``; loop elsewhere)."""
        if self.spec.channel_prefixed:
            await self._write(f":SOURce:RFALl:OUTPut:STATe {'ON' if enabled else 'OFF'}")
        else:
            await self._write(f"{self._outp(1)} {'ON' if enabled else 'OFF'}")
        return {ch: await self.get_output(ch) for ch in range(1, self.spec.channels + 1)}

    async def set_alc(self, enabled: bool = True, mode: Optional[str] = None) -> Optional[str]:
        """Automatic level control (DSG3000: ``:LEVel:ALC:MODE OFF|ON|AUTO``).

        ``mode`` overrides ``enabled`` and may be OFF, ON or AUTO. Raises
        ValueError on families whose guide has no ALC command.
        """
        if not self.spec.has_alc_command:
            raise ValueError(f"{self.spec.model} has no remote ALC control (only the DSG3000 documents :LEVel:ALC:MODE)")
        if mode is not None:
            key = str(mode).strip().upper()
            if key not in ("OFF", "ON", "AUTO"):
                raise ValueError("ALC mode must be OFF, ON or AUTO")
        else:
            key = "ON" if enabled else "OFF"
        await self._write(f":SOURce:LEVel:ALC:MODE {key}")
        return await self.get_alc()

    async def get_alc(self) -> Optional[str]:
        """ALC mode (OFF/ON/AUTO) or None when the model has no ALC command."""
        if not self.spec.has_alc_command:
            return None
        return (await self._query(":SOURce:LEVel:ALC:MODE?")).strip().upper()

    # ------------------------------------------------------------------ #
    # Modulation
    # ------------------------------------------------------------------ #

    def _mod_type(self, mod_type: str) -> str:
        key = _MOD_ALIASES.get(str(mod_type).strip().upper())
        if key is None:
            raise ValueError(f"Modulation type must be one of {', '.join(_MOD_TYPES)}")
        if key == "PULSE" and not self.spec.has_pulse:
            raise ValueError(f"{self.spec.model} has no pulse modulation")
        if key == "IQ" and not self.spec.has_iq:
            raise ValueError(f"{self.spec.model} has no IQ modulation")
        return key

    async def set_modulation(
        self,
        type: str,
        enabled: bool = True,
        channel: int = 1,
        master: Optional[bool] = None,
        **params: Any,
    ) -> Dict[str, Any]:
        """Configure and switch one modulation.

        ``type``: AM, FM, PM, PULSE or IQ. Parameters (all optional):

        * AM: ``depth`` (%), ``frequency`` (Hz), ``source`` (INT/EXT), ``waveform`` (SINE/SQUARE)
        * FM: ``deviation`` (Hz), ``frequency``, ``source``, ``waveform``
        * PM: ``deviation`` (rad), ``frequency``, ``source``, ``waveform``
        * PULSE: ``period`` (s), ``width`` (s), ``source``, ``polarity`` (NORMAL/INVERSE), ``mode`` (SINGLE/TRAIN)
        * IQ: ``source`` (INT/EXT)

        ``master`` controls the global Mod on/off switch; by default it is
        turned on together with the modulation and left alone when disabling.
        """
        ch = self._check_channel(channel)
        key = self._mod_type(type)
        root = f"{self._src(ch)}:{_MOD_ROOT[key]}"

        unknown = set(params) - {"depth", "deviation", "frequency", "source", "waveform",
                                 "period", "width", "polarity", "mode"}
        if unknown:
            raise ValueError(f"Unknown modulation parameters: {', '.join(sorted(unknown))}")

        if key in ("FM", "PM") and self.spec.has_fmpm_type:
            await self._write(f"{self._src(ch)}:FMPM:TYPE {key}")

        source = params.get("source")
        if source is not None:
            src = _SOURCES.get(str(source).strip().upper())
            if src is None:
                raise ValueError("source must be INT or EXT")
            if key == "IQ":
                await self._write(f"{root}:MODe {src}")
            else:
                await self._write(f"{root}:SOURce {src}")

        if key == "AM" and params.get("depth") is not None:
            depth = float(params["depth"])
            if not 0.0 <= depth <= 100.0:
                raise ValueError("AM depth must be 0..100 %")
            await self._write(f"{root}:DEPTh {depth:g}")
        if key in ("FM", "PM") and params.get("deviation") is not None:
            dev = float(params["deviation"])
            if dev <= 0:
                raise ValueError("Deviation must be > 0")
            await self._write(f"{root}:DEViation {fmt_number(dev)}")
        if key in ("AM", "FM", "PM") and params.get("frequency") is not None:
            mf = float(params["frequency"])
            if mf <= 0:
                raise ValueError("Modulation frequency must be > 0 Hz")
            await self._write(f"{root}:FREQuency {fmt_number(mf)}")
        if key in ("AM", "FM", "PM") and params.get("waveform") is not None:
            wf = _WAVEFORMS.get(str(params["waveform"]).strip().upper())
            if wf is None:
                raise ValueError("waveform must be SINE or SQUARE")
            await self._write(f"{root}:WAVEform {wf}")
        if key == "PULSE":
            if params.get("mode") is not None:
                pm = str(params["mode"]).strip().upper()
                if pm not in ("SINGLE", "SING", "TRAIN", "TRA"):
                    raise ValueError("Pulse mode must be SINGLE or TRAIN")
                await self._write(f"{root}:MODE {'SINGle' if pm.startswith('SING') else 'TRAin'}")
            if params.get("period") is not None:
                per = float(params["period"])
                if not 40e-9 <= per <= 170.0:
                    raise ValueError("Pulse period must be 40 ns..170 s")
                await self._write(f"{root}:PERiod {fmt_number(per)}")
            if params.get("width") is not None:
                wid = float(params["width"])
                if not 10e-9 <= wid <= 170.0:
                    raise ValueError("Pulse width must be 10 ns..170 s")
                await self._write(f"{root}:WIDTh {fmt_number(wid)}")
            if params.get("polarity") is not None:
                pol = str(params["polarity"]).strip().upper()
                if pol not in ("NORMAL", "NORM", "INVERSE", "INV", "INVERTED"):
                    raise ValueError("Pulse polarity must be NORMAL or INVERSE")
                await self._write(f"{root}:POLarity {'NORMal' if pol.startswith('NORM') else 'INVerse'}")

        state_cmd = f"{root}:MODe:STATe" if key == "IQ" else f"{root}:STATe"
        await self._write(f"{state_cmd} {'ON' if enabled else 'OFF'}")

        if master is None:
            master = True if enabled else None
        if master is not None:
            await self.set_modulation_master(master, ch)

        return await self.get_modulation(key, ch)

    async def get_modulation(self, type: str, channel: int = 1) -> Dict[str, Any]:
        """Current state and parameters of one modulation type."""
        ch = self._check_channel(channel)
        key = self._mod_type(type)
        root = f"{self._src(ch)}:{_MOD_ROOT[key]}"
        out: Dict[str, Any] = {"type": key, "channel": ch}
        if key == "IQ":
            out["enabled"] = parse_bool(await self._query(f"{root}:MODe:STATe?"))
            out["source"] = (await self._query(f"{root}:MODe?")).strip().upper()[:3]
            return out
        out["enabled"] = parse_bool(await self._query(f"{root}:STATe?"))
        out["source"] = (await self._query(f"{root}:SOURce?")).strip().upper()[:3]
        if key == "AM":
            out["depth"] = await self._query_float(f"{root}:DEPTh?")
        elif key in ("FM", "PM"):
            out["deviation"] = await self._query_float(f"{root}:DEViation?")
        if key in ("AM", "FM", "PM"):
            out["frequency"] = await self._query_float(f"{root}:FREQuency?")
            out["waveform"] = (await self._query(f"{root}:WAVEform?")).strip().upper()
        else:  # PULSE
            out["period"] = await self._query_float(f"{root}:PERiod?")
            out["width"] = await self._query_float(f"{root}:WIDTh?")
            out["polarity"] = (await self._query(f"{root}:POLarity?")).strip().upper()
        return out

    async def set_modulation_master(self, enabled: bool, channel: int = 1) -> bool:
        """Global modulation on/off switch ([:SOURce]:MODulation:STATe)."""
        ch = self._check_channel(channel)
        await self._write(f"{self._src(ch)}:MODulation:STATe {'ON' if enabled else 'OFF'}")
        return await self.get_modulation_master(ch)

    async def get_modulation_master(self, channel: int = 1) -> bool:
        ch = self._check_channel(channel)
        return parse_bool(await self._query(f"{self._src(ch)}:MODulation:STATe?"))

    async def set_lf_output(
        self,
        enabled: bool = True,
        frequency: Optional[float] = None,
        level: Optional[float] = None,
        shape: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Low-frequency generator output (DSG800/3000/3000B)."""
        if not self.spec.has_lf_output:
            raise ValueError(f"{self.spec.model} does not document [:SOURce]:LFOutput")
        if frequency is not None:
            f = float(frequency)
            if not 0 <= f <= 200e3:
                raise ValueError("LF frequency must be 0..200 kHz")
            await self._write(f":SOURce:LFOutput:FREQuency {fmt_number(f)}")
        if level is not None:
            await self._write(f":SOURce:LFOutput:LEVel {fmt_number(float(level))}")
        if shape is not None:
            wf = _WAVEFORMS.get(str(shape).strip().upper())
            if wf is None:
                raise ValueError("LF shape must be SINE or SQUARE")
            await self._write(f":SOURce:LFOutput:SHAPe {wf}")
        await self._write(f":SOURce:LFOutput:STATe {'ON' if enabled else 'OFF'}")
        return {
            "enabled": parse_bool(await self._query(":SOURce:LFOutput:STATe?")),
            "frequency": await self._query_float(":SOURce:LFOutput:FREQuency?"),
            "level": await self._query_float(":SOURce:LFOutput:LEVel?"),
        }

    # ------------------------------------------------------------------ #
    # Sweep
    # ------------------------------------------------------------------ #

    async def set_sweep(
        self,
        mode: str = "FREQ",
        start_frequency: Optional[float] = None,
        stop_frequency: Optional[float] = None,
        start_level: Optional[float] = None,
        stop_level: Optional[float] = None,
        points: Optional[int] = None,
        dwell: Optional[float] = None,
        sweep_type: Optional[str] = None,
        spacing: Optional[str] = None,
        shape: Optional[str] = None,
        direction: Optional[str] = None,
        continuous: Optional[bool] = None,
        channel: int = 1,
    ) -> Dict[str, Any]:
        """Configure the step sweep and select the sweep manner.

        ``mode``: OFF, FREQ, LEVEL or BOTH (``:SWEep:STATe``). Frequencies in
        Hz, levels in dBm, dwell in seconds (20 ms..100 s), points 2..65535.
        """
        ch = self._check_channel(channel)
        root = f"{self._src(ch)}:SWEep"
        state = _SWEEP_STATES.get(str(mode).strip().upper())
        if state is None:
            raise ValueError("Sweep mode must be OFF, FREQ, LEVEL or BOTH")
        s = self.spec
        for name, value in (("start_frequency", start_frequency), ("stop_frequency", stop_frequency)):
            if value is not None and not s.freq_min <= float(value) <= s.freq_max:
                raise ValueError(f"{name} must be {s.freq_min:g}..{s.freq_max:g} Hz")
        for name, value in (("start_level", start_level), ("stop_level", stop_level)):
            if value is not None and not s.level_min <= float(value) <= s.level_max:
                raise ValueError(f"{name} must be {s.level_min:g}..{s.level_max:g} dBm")
        if sweep_type is not None:
            st = str(sweep_type).strip().upper()
            if st not in ("STEP", "LIST"):
                raise ValueError("sweep_type must be STEP or LIST")
            await self._write(f"{root}:TYPE {st}")
        if start_frequency is not None:
            await self._write(f"{root}:STEP:STARt:FREQuency {fmt_number(float(start_frequency))}")
        if stop_frequency is not None:
            await self._write(f"{root}:STEP:STOP:FREQuency {fmt_number(float(stop_frequency))}")
        if start_level is not None:
            await self._write(f"{root}:STEP:STARt:LEVel {float(start_level):.2f}")
        if stop_level is not None:
            await self._write(f"{root}:STEP:STOP:LEVel {float(stop_level):.2f}")
        if points is not None:
            pts = int(points)
            if not 2 <= pts <= 65535:
                raise ValueError("points must be 2..65535")
            await self._write(f"{root}:STEP:POINts {pts}")
        if dwell is not None:
            dw = float(dwell)
            if not 0.005 <= dw <= 100.0:
                raise ValueError("dwell must be 0.005..100 s (20 ms minimum on DSG800/3000)")
            await self._write(f"{root}:STEP:DWELl {fmt_number(dw)}")
        if spacing is not None:
            sp = str(spacing).strip().upper()
            if sp not in ("LIN", "LINEAR", "LOG", "LOGARITHMIC"):
                raise ValueError("spacing must be LIN or LOG")
            await self._write(f"{root}:STEP:SPACing {'LINear' if sp.startswith('LIN') else 'LOGarithmic'}")
        if shape is not None:
            sh = str(shape).strip().upper()
            if sh not in ("TRI", "TRIANGLE", "RAMP"):
                raise ValueError("shape must be TRIANGLE or RAMP")
            await self._write(f"{root}:STEP:SHAPe {'TRIangle' if sh.startswith('TRI') else 'RAMP'}")
        if direction is not None:
            d = str(direction).strip().upper()
            if d not in ("FWD", "FORWARD", "REV", "REVERSE", "DOWN"):
                raise ValueError("direction must be FWD or REV")
            await self._write(f"{root}:DIRection {'FWD' if d.startswith('F') else 'REV'}")
        if continuous is not None:
            await self._write(f"{root}:MODE {'CONTinue' if continuous else 'SINGle'}")
        await self._write(f"{root}:STATe {state}")
        return await self.get_sweep(ch)

    async def get_sweep(self, channel: int = 1) -> Dict[str, Any]:
        ch = self._check_channel(channel)
        root = f"{self._src(ch)}:SWEep"
        raw_state = (await self._query(f"{root}:STATe?")).strip().upper()
        out: Dict[str, Any] = {
            "channel": ch,
            "state": raw_state,
            "enabled": raw_state not in ("OFF", "0", ""),
        }
        for key, cmd, kind in (
            ("type", "TYPE?", "str"),
            ("mode", "MODE?", "str"),
            ("direction", "DIRection?", "str"),
            ("start_frequency", "STEP:STARt:FREQuency?", "num"),
            ("stop_frequency", "STEP:STOP:FREQuency?", "num"),
            ("start_level", "STEP:STARt:LEVel?", "num"),
            ("stop_level", "STEP:STOP:LEVel?", "num"),
            ("points", "STEP:POINts?", "int"),
            ("dwell", "STEP:DWELl?", "num"),
            ("spacing", "STEP:SPACing?", "str"),
            ("shape", "STEP:SHAPe?", "str"),
        ):
            try:
                raw = await self._query(f"{root}:{cmd}")
                if kind == "str":
                    out[key] = raw.strip().upper()
                elif kind == "int":
                    val = parse_si(raw)
                    out[key] = int(val) if val is not None else None
                else:
                    out[key] = parse_si(raw)
            except Exception as e:
                logger.debug(f"Sweep {key} query failed: {e}")
                out[key] = None
        return out

    async def execute_sweep(self, channel: int = 1) -> None:
        """Start a single sweep ([:SOURce]:SWEep:EXECute)."""
        ch = self._check_channel(channel)
        await self._write(f"{self._src(ch)}:SWEep:EXECute")

    async def trigger(self, what: str = "SWEEP", channel: int = 1) -> None:
        """Bus trigger: SWEEP, PULSE or IQ (or ALL -> ``*TRG``)."""
        ch = self._check_channel(channel)
        key = str(what).strip().upper()
        if key in ("ALL", "*TRG", "ANY"):
            await self._write("*TRG")
            return
        # DSG800/3000/3000B: :TRIGger:PULSe / :TRIGger:SWEep / :TRIGger:IQ.
        # DSG5000: :TRIGger[:RF<n>]:PULM / :TRIGger[:RF<n>][:SWEep].
        prefix = f":TRIGger:RF{ch}" if self.spec.channel_prefixed else ":TRIGger"
        if key in ("SWEEP", "SWE"):
            await self._write(f"{prefix}:SWEep:IMMediate")
        elif key in ("PULSE", "PULM", "PUL"):
            if not self.spec.has_pulse:
                raise ValueError(f"{self.spec.model} has no pulse modulation")
            node = "PULM" if self.spec.channel_prefixed else "PULSe"
            await self._write(f"{prefix}:{node}:IMMediate")
        elif key == "IQ":
            if not self.spec.has_iq:
                raise ValueError(f"{self.spec.model} has no IQ modulation")
            await self._write(f"{prefix}:IQ:IMMediate")
        else:
            raise ValueError("trigger target must be SWEEP, PULSE, IQ or ALL")

    # ------------------------------------------------------------------ #
    # Readings / hooks
    # ------------------------------------------------------------------ #

    async def _active_modulation(self, ch: int) -> Dict[str, Any]:
        """First enabled modulation (AM, FM, PM, PULSE, IQ) with its parameters."""
        for key in _MOD_TYPES:
            if key == "PULSE" and not self.spec.has_pulse:
                continue
            if key == "IQ" and not self.spec.has_iq:
                continue
            try:
                mod = await self.get_modulation(key, ch)
            except Exception as e:
                logger.debug(f"{key} query failed: {e}")
                continue
            if mod.get("enabled"):
                return mod
        return {}

    async def get_readings(self, channel: int = 1) -> RFGeneratorData:
        """Frequency, level, output and modulation state of one channel."""
        ch = self._check_channel(channel)
        frequency = await self.get_frequency(ch)
        level = await self.get_level(ch)
        output = await self.get_output(ch)
        try:
            master = await self.get_modulation_master(ch)
        except Exception:
            master = False
        mod = await self._active_modulation(ch) if master else {}
        params = {
            k: float(v)
            for k, v in mod.items()
            if k in ("depth", "deviation", "frequency", "period", "width") and isinstance(v, (int, float))
        }
        alc: Optional[bool] = None
        if self.spec.has_alc_command:
            try:
                alc_mode = await self.get_alc()
                alc = None if alc_mode is None else alc_mode != "OFF"
            except Exception:
                alc = None
        return RFGeneratorData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            frequency=frequency,
            level=level,
            level_unit="dBm",
            output_enabled=output,
            modulation_enabled=bool(master and mod),
            modulation_type=mod.get("type") if mod else None,
            modulation_parameters=params,
            alc_enabled=alc,
        )

    async def get_measurement(self, channel: str = "LEVEL") -> Dict[str, Any]:
        """Acquisition-engine hook.

        ``channel`` is ``FREQ`` (Hz), ``LEVEL`` (dBm) or ``OUTPUT`` (1/0),
        optionally prefixed with the RF channel on multi-channel models:
        ``CH2:FREQ``. A bare ``CH1``/``1``/empty string means LEVEL.
        """
        key = (channel or "LEVEL").strip().upper()
        ch = 1
        if ":" in key:
            head, _, key = key.partition(":")
            head = head.replace("CH", "").replace("RF", "")
            ch = self._check_channel(head or 1)
        elif key.startswith("CH") and key[2:].isdigit():
            ch = self._check_channel(key[2:])
            key = "LEVEL"
        elif key.isdigit():
            ch = self._check_channel(key)
            key = "LEVEL"
        if key in ("", "LEVEL", "LEV", "POWER", "POW", "AMPLITUDE", "AMPL"):
            return {"value": await self.get_level(ch), "unit": "dBm", "quantity": "level", "channel": ch}
        if key in ("FREQ", "FREQUENCY", "CW"):
            return {"value": await self.get_frequency(ch), "unit": "Hz", "quantity": "frequency", "channel": ch}
        if key in ("OUTPUT", "OUTP", "RF"):
            return {"value": 1.0 if await self.get_output(ch) else 0.0, "unit": "", "quantity": "output", "channel": ch}
        raise ValueError("Channel must be FREQ, LEVEL or OUTPUT (optionally CH<n>:FREQ)")

    async def get_measurements(self, channel: Any = 1) -> Dict[str, Any]:
        """Streaming hook: frequency / level / output for one channel."""
        try:
            ch = self._check_channel(channel)
        except ValueError:
            ch = 1
        return {
            "frequency": await self.get_frequency(ch),
            "frequency_unit": "Hz",
            "level": await self.get_level(ch),
            "level_unit": "dBm",
            "output_enabled": await self.get_output(ch),
        }

    async def get_state(self, channel: int = 1) -> Dict[str, Any]:
        """Snapshot of settings for the state capture/restore system."""
        ch = self._check_channel(channel)
        state: Dict[str, Any] = {"model": self.spec.model, "channel": ch}
        for key, coro in (
            ("frequency", self.get_frequency(ch)),
            ("level", self.get_level(ch)),
            ("level_unit", self.get_level_unit(ch)),
            ("output_enabled", self.get_output(ch)),
            ("modulation_enabled", self.get_modulation_master(ch)),
            ("alc", self.get_alc()),
        ):
            try:
                state[key] = await coro
            except Exception as e:
                logger.debug(f"{key} query failed: {e}")
                state[key] = None
        state["modulations"] = {}
        for key in _MOD_TYPES:
            if key == "PULSE" and not self.spec.has_pulse:
                continue
            if key == "IQ" and not self.spec.has_iq:
                continue
            try:
                state["modulations"][key] = await self.get_modulation(key, ch)
            except Exception as e:
                logger.debug(f"{key} query failed: {e}")
        try:
            state["sweep"] = await self.get_sweep(ch)
        except Exception:
            state["sweep"] = None
        return state

    # ------------------------------------------------------------------ #
    # System
    # ------------------------------------------------------------------ #

    async def preset(self) -> None:
        """Factory preset (:SYSTem:PRESet); turns RF and modulation off."""
        await self._write(":SYSTem:PRESet")

    async def reset(self) -> None:
        """*RST where documented (DSG3000/DSG5000), otherwise :SYSTem:PRESet."""
        if self.spec.has_ieee_reset:
            await self._write("*RST")
        else:
            await self.preset()

    async def clear_errors(self) -> bool:
        if not self.spec.has_ieee_reset:
            # *CLS is not documented on DSG800/DSG3000B.
            return False
        return await super().clear_errors()

    async def get_error(self) -> Dict[str, Any]:
        """Best-effort :SYSTem:ERRor? (not documented in any DSG guide)."""
        try:
            raw = await self._query(":SYSTem:ERRor?")
        except Exception as e:
            return {"code": None, "message": f"error query unsupported: {e}", "raw": None}
        code_str, _, message = raw.partition(",")
        try:
            code = int(float(code_str.strip()))
        except ValueError:
            code = None
        return {"code": code, "message": message.strip().strip('"'), "raw": raw}

    async def get_options(self) -> Optional[str]:
        """Installed options (*OPT?, DSG3000 only)."""
        if self.spec.family != "DSG3000":
            return None
        return (await self._query("*OPT?")).strip()


# --------------------------------------------------------------------------- #
# Concrete families
# --------------------------------------------------------------------------- #


class RigolDSG800(RigolDSGBase):
    """Rigol DSG815 / DSG821 / DSG830 / DSG836: 9 kHz..1.5-3.6 GHz, -110..+20 dBm."""

    DEFAULT_MODEL = "DSG830"
    INTERFACES = ("USB", "LAN")


class RigolDSG3000(RigolDSGBase):
    """Rigol DSG3030 / DSG3060 and DSG3065B / DSG3136B (-IQ): 9 kHz..3-13.6 GHz."""

    DEFAULT_MODEL = "DSG3060"
    INTERFACES = ("USB", "LAN", "GPIB")


class RigolDSG5000(RigolDSGBase):
    """Rigol DSG51xx / DSG52xx: 2-8 channel 12/20 GHz microwave generators."""

    DEFAULT_MODEL = "DSG5208"
    INTERFACES = ("USB", "LAN")


# Model keywords used by equipment.manager.find_keyword_driver.
RigolDSG5000.MODEL_KEYWORDS = ('DSG5208', 'DSG5206', 'DSG5204', 'DSG5202', 'DSG5128', 'DSG5126', 'DSG5124', 'DSG5122', 'DSG5')
RigolDSG3000.MODEL_KEYWORDS = ('DSG3136B-IQ', 'DSG3065B-IQ', 'DSG3136B', 'DSG3065B', 'DSG3060', 'DSG3030', 'DSG3')
RigolDSG800.MODEL_KEYWORDS = ('DSG836A', 'DSG836', 'DSG830', 'DSG821A', 'DSG821', 'DSG815', 'DSG8')
