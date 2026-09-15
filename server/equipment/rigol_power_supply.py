"""Rigol DP-series programmable DC power supply drivers.

Families covered (one concrete class each, all sharing :class:`RigolDPBase`):

===========  ==========================================  ==============================
Class        Models                                      Protocol reference
===========  ==========================================  ==============================
RigolDP800   DP811/A DP813/A DP821/A DP822/A DP831/A     DP800 Programming Guide
             DP832/A
RigolDP700   DP711 DP712                                 DP700 Programming Guide
RigolDP900   DP932A DP932U DP932E                        DP900 Programming Guide
RigolDP2000  DP2031                                      DP2000 Programming Guide
RigolDP1308A DP1308A                                     DP1308A Programming Guide (2009)
RigolDP1116A DP1116A                                     DP1116A Programming Guide (2010)
===========  ==========================================  ==============================

The DP700/DP800/DP900/DP2000 tree is the same core SCPI set: ``:APPLy``,
``:INSTrument:NSELect``, ``[:SOURce<n>]:VOLTage|CURRent`` (+ ``:PROTection``),
``:OUTPut[:STATe]``, ``:OUTPut:OVP|OCP:VALue|STATe|QUES?|CLEAR``, ``:OUTPut:CVCC?``,
``:MEASure[:VOLTage|:CURRent|:POWEr|:ALL]?`` and ``:SYSTem:...``. The 2009/2010
DP1308A/DP1116A tree is older: channels are named ``P6V|P25V|N25V`` (DP1308A) or
not named at all (single-range DP1116A), OVP/OCP levels are set with
``OUTPut:OVP <value>`` (no ``:VALue`` leaf), there is no ``:MEASure:ALL?``,
``:OUTPut:CVCC?``, trip query/clear or ``:SYSTem:ERRor?``. The per-family
differences are captured in :data:`FAMILY_DIALECTS`; per-model channel counts and
limits in :data:`MODEL_TABLE`.

Interfaces: USB-TMC (VID 0x1AB1), LAN (VXI-11), RS-232 (9600 8N1 default, ``\\r\\n``
terminated) and GPIB depending on model - see ``INTERFACES`` in the model table.
DP700 is RS-232 only.

*IDN? returns ``<manufacturer>,<model>,<serial>,<firmware>``; the manufacturer is
spelled ``RIGOL TECHNOLOGIES`` on DP700/DP800 and ``Rigol Technologies`` on the
others (DP1116A pads the fields with spaces).
"""

import asyncio
import logging
import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from shared.models.data import PowerSupplyData
from shared.models.equipment import EquipmentInfo, EquipmentStatus, EquipmentType

from .base import BaseEquipment, generate_equipment_id

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Model table
# --------------------------------------------------------------------------- #
#
# Every entry gives, per channel: the rated (nameplate) voltage/current, the
# remotely settable maximum voltage/current, and the maximum OVP/OCP level.
# max_power is rated_v * rated_i.  Negative channels (DP831 CH3, DP1308A N25V)
# are programmed with negative values (see the OVP tables: "-1mV to -33V").
#
# Sources:
#   [DP800]  DP800 Programming Guide, Table 2-1 (voltage/current ranges) and
#            Table 2-2 (OVP/OCP ranges); ":OUTPut:RANGe" for the DP811/DP813
#            ranges; ":OUTPut:TRACk" for the tracking channels; ":OUTPut:SENSe".
#            Note[1] of Table 2-1: non-A models with the high-resolution option
#            share the A-model ranges, so DP83x and DP83xA rows are identical.
#   [DP700]  DP700 Programming Guide, Ch.1 model list (30 V/5 A, 50 V/3 A) and
#            the :APPLy / :OUTPut:OVP:VALue / :OUTPut:OCP:VALue parameter tables.
#   [DP900]  DP900 Programming Guide, model list, Table 4.9 and Table 4.33.
#   [DP2000] DP2000 Programming Guide, model list, Table 4.9 and Table 4.33.
#            CH3 has an optional 6 V/10 A range (DP2000-10A); when active CH1/CH2
#            drop to 32 V/2 A.  No remote command to switch it is documented, so
#            the standard range is used for validation.
#   [DP1308A] DP1308A Programming Guide: [SOURce:]VOLTage/CURRent ranges
#            (6.3 V/5.25 A, +-26.25 V/1.05 A), OUTPut:OVP (6.5 V, +-27 V),
#            OUTPut:OCP (5.5 A, 1.2 A), OUTPut:TRACk {P25V|N25V|OFF}.
#   [DP1116A] DP1116A Programming Guide: APPLy ranges (16.8 V/10.5 A and
#            33.6 V/5.25 A), OUTPut:RANGe {16V|32V}, OUTPut:OVP 0.1-35.2 V,
#            OUTPut:OCP 0.1-11 A.


def _ch(
    name: str,
    rated_v: float,
    rated_i: float,
    max_v: float,
    max_i: float,
    max_ovp: float,
    max_ocp: float,
    token: Optional[str] = None,
    negative: bool = False,
    tracking: bool = False,
    sense: bool = False,
) -> Dict[str, Any]:
    return {
        "name": name,
        "token": token,  # SCPI channel token when it is not CH<n>
        "rated_voltage": rated_v,
        "rated_current": rated_i,
        "max_voltage": max_v,
        "max_current": max_i,
        "max_power": round(rated_v * rated_i, 3),
        "max_ovp": max_ovp,
        "max_ocp": max_ocp,
        "negative": negative,
        "tracking": tracking,
        "sense": sense,
    }


def _rng(
    label: str,
    aliases: Sequence[str],
    rated_v: float,
    rated_i: float,
    max_v: float,
    max_i: float,
    max_ovp: float,
    max_ocp: float,
) -> Dict[str, Any]:
    return {
        "label": label,  # token sent with :OUTPut:RANGe
        "aliases": tuple(a.upper() for a in aliases),
        "rated_voltage": rated_v,
        "rated_current": rated_i,
        "max_voltage": max_v,
        "max_current": max_i,
        "max_power": round(rated_v * rated_i, 3),
        "max_ovp": max_ovp,
        "max_ocp": max_ocp,
    }


def _single_range_channel(ranges: Sequence[Dict[str, Any]], sense: bool = False) -> Dict[str, Any]:
    """Channel spec for a single-output dual-range model: widest limits of its ranges."""
    return _ch(
        "CH1",
        max(r["rated_voltage"] for r in ranges),
        max(r["rated_current"] for r in ranges),
        max(r["max_voltage"] for r in ranges),
        max(r["max_current"] for r in ranges),
        max(r["max_ovp"] for r in ranges),
        max(r["max_ocp"] for r in ranges),
        sense=sense,
    )


_IF_DP800 = ("USB", "LAN", "RS232", "GPIB")  # LAN/RS232 optional on non-A models
_IF_DP700 = ("RS232",)
_IF_DP900 = ("USB", "LAN", "RS232")  # RS232 not on DP932U; GPIB via USB-GPIB adaptor
_IF_DP2000 = ("USB", "LAN", "RS232", "GPIB")
_IF_DP1300 = ("USB", "LAN", "GPIB")

# [DP800] Table 2-1 / 2-2
_DP832_CHANNELS = [
    _ch("CH1", 30, 3, 32.0, 3.2, 33.0, 3.3, tracking=True),
    _ch("CH2", 30, 3, 32.0, 3.2, 33.0, 3.3, tracking=True),
    # Table 2-1 prints "0V to -5.3V" for CH3 but the channel token is P5V and the
    # datasheet rates it +5 V/3 A: treated as a positive channel.
    _ch("CH3", 5, 3, 5.3, 3.2, 5.5, 3.3),
]
_DP831_CHANNELS = [
    _ch("CH1", 8, 5, 8.4, 5.3, 8.8, 5.5),
    _ch("CH2", 30, 2, 32.0, 2.1, 33.0, 2.2, tracking=True),
    _ch("CH3", -30, 2, 32.0, 2.1, 33.0, 2.2, negative=True, tracking=True),
]
_DP822_CHANNELS = [
    _ch("CH1", 20, 5, 21.0, 5.3, 22.0, 5.5),
    _ch("CH2", 5, 16, 5.3, 16.4, 5.5, 16.8, sense=True),
]
_DP821_CHANNELS = [
    _ch("CH1", 60, 1, 63.0, 1.05, 66.0, 1.1),
    _ch("CH2", 8, 10, 8.4, 10.5, 8.8, 11.0, sense=True),
]
_DP813_RANGES = [
    _rng("P8V", ("P8V", "LOW", "8V", "8V/20A"), 8, 20, 8.4, 21.0, 8.8, 22.0),
    _rng("P20V", ("P20V", "HIGH", "20V", "20V/10A"), 20, 10, 21.0, 10.5, 22.0, 11.0),
]
_DP811_RANGES = [
    _rng("P20V", ("P20V", "LOW", "20V", "20V/10A"), 20, 10, 21.0, 10.5, 22.0, 11.0),
    _rng("P40V", ("P40V", "HIGH", "40V", "40V/5A"), 40, 5, 42.0, 5.3, 44.0, 5.5),
]

# [DP900] Table 4.9 / 4.33
_DP932A_CHANNELS = [
    _ch("CH1", 32, 3, 33.6, 3.15, 35.2, 3.3, tracking=True),
    _ch("CH2", 32, 3, 33.6, 3.15, 35.2, 3.3, tracking=True),
    _ch("CH3", 6, 3, 6.3, 3.15, 6.6, 3.3),
]
_DP932E_CHANNELS = [
    _ch("CH1", 30, 3, 31.5, 3.15, 33.0, 3.3, tracking=True),
    _ch("CH2", 30, 3, 31.5, 3.15, 33.0, 3.3, tracking=True),
    _ch("CH3", 6, 3, 6.3, 3.15, 6.6, 3.3),
]

# [DP2000] Table 4.9 / 4.33 (standard range 1)
_DP2031_CHANNELS = [
    _ch("CH1", 32, 3, 32.0, 3.0, 35.2, 3.3, tracking=True, sense=True),
    _ch("CH2", 32, 3, 32.0, 3.0, 35.2, 3.3, tracking=True, sense=True),
    _ch("CH3", 6, 5, 6.0, 5.0, 6.6, 5.5, sense=True),
]

# [DP1308A]
_DP1308A_CHANNELS = [
    _ch("CH1", 6, 5, 6.3, 5.25, 6.5, 5.5, token="P6V"),
    _ch("CH2", 25, 1, 26.25, 1.05, 27.0, 1.2, token="P25V", tracking=True),
    _ch("CH3", -25, 1, 26.25, 1.05, 27.0, 1.2, token="N25V", negative=True, tracking=True),
]

# [DP1116A]
_DP1116A_RANGES = [
    _rng("16V", ("16V", "LOW", "16V/10A"), 16, 10, 16.8, 10.5, 35.2, 11.0),
    _rng("32V", ("32V", "HIGH", "32V/5A"), 32, 5, 33.6, 5.25, 35.2, 11.0),
]


def _model(
    family: str,
    channels: Sequence[Dict[str, Any]],
    interfaces: Sequence[str],
    ranges: Optional[Sequence[Dict[str, Any]]] = None,
    tracking_pair: Optional[Tuple[int, int]] = None,
    pair: bool = False,
) -> Dict[str, Any]:
    return {
        "family": family,
        "channels": list(channels),
        "ranges": list(ranges) if ranges else None,
        "interfaces": tuple(interfaces),
        "tracking_pair": tracking_pair,  # channels that support :OUTPut:TRACk
        "pair": pair,  # :OUTPut:PAIR SERies|PARallel (CH1+CH2)
    }


MODEL_TABLE: Dict[str, Dict[str, Any]] = {
    # ---- DP800 ---------------------------------------------------------- #
    "DP832A": _model("DP800", _DP832_CHANNELS, _IF_DP800, tracking_pair=(1, 2)),
    "DP832": _model("DP800", _DP832_CHANNELS, _IF_DP800, tracking_pair=(1, 2)),
    "DP831A": _model("DP800", _DP831_CHANNELS, _IF_DP800, tracking_pair=(2, 3)),
    "DP831": _model("DP800", _DP831_CHANNELS, _IF_DP800, tracking_pair=(2, 3)),
    "DP822A": _model("DP800", _DP822_CHANNELS, _IF_DP800),
    "DP822": _model("DP800", _DP822_CHANNELS, _IF_DP800),
    "DP821A": _model("DP800", _DP821_CHANNELS, _IF_DP800),
    "DP821": _model("DP800", _DP821_CHANNELS, _IF_DP800),
    "DP813A": _model("DP800", [_single_range_channel(_DP813_RANGES, sense=True)], _IF_DP800, ranges=_DP813_RANGES),
    "DP813": _model("DP800", [_single_range_channel(_DP813_RANGES, sense=True)], _IF_DP800, ranges=_DP813_RANGES),
    "DP811A": _model("DP800", [_single_range_channel(_DP811_RANGES, sense=True)], _IF_DP800, ranges=_DP811_RANGES),
    "DP811": _model("DP800", [_single_range_channel(_DP811_RANGES, sense=True)], _IF_DP800, ranges=_DP811_RANGES),
    # ---- DP700 ---------------------------------------------------------- #
    "DP711": _model("DP700", [_ch("CH1", 30, 5, 32.0, 5.3, 33.0, 5.5, token="CH1")], _IF_DP700),
    "DP712": _model("DP700", [_ch("CH1", 50, 3, 53.0, 3.2, 55.0, 3.3, token="CH1")], _IF_DP700),
    # ---- DP900 ---------------------------------------------------------- #
    "DP932A": _model("DP900", _DP932A_CHANNELS, _IF_DP900, tracking_pair=(1, 2), pair=True),
    "DP932U": _model("DP900", _DP932A_CHANNELS, ("USB", "LAN"), tracking_pair=(1, 2), pair=True),
    "DP932E": _model("DP900", _DP932E_CHANNELS, _IF_DP900, tracking_pair=(1, 2), pair=True),
    # ---- DP2000 --------------------------------------------------------- #
    "DP2031": _model("DP2000", _DP2031_CHANNELS, _IF_DP2000, tracking_pair=(1, 2), pair=True),
    # ---- DP1308A / DP1116A ---------------------------------------------- #
    "DP1308A": _model("DP1308A", _DP1308A_CHANNELS, _IF_DP1300, tracking_pair=(2, 3)),
    "DP1116A": _model("DP1116A", [_single_range_channel(_DP1116A_RANGES)], _IF_DP1300, ranges=_DP1116A_RANGES),
}


# --------------------------------------------------------------------------- #
# Family dialects (command-tree differences)
# --------------------------------------------------------------------------- #

FAMILY_DIALECTS: Dict[str, Dict[str, Any]] = {
    "DP800": {
        "channel_token": "CH",  # CH<n>
        "source_prefix": True,  # :SOURce<n>:VOLTage
        "measure_all": True,
        "cvcc_query": True,
        "ovp_value_cmd": ":OUTPut:OVP:VALue",
        "ocp_value_cmd": ":OUTPut:OCP:VALue",
        "protection_trip_query": True,  # :OUTPut:OVP:QUES?
        "protection_clear": True,  # :OUTPut:OVP:CLEAR
        "error_query": ":SYSTem:ERRor?",
        "track_style": "DP800",  # :OUTPut:TRACk CH<n>,ON
        "track_mode_cmd": ":SYSTem:TRACKMode",
        "onoff_sync_cmd": ":SYSTem:ONOFFSync",
        "range_cmd": ":OUTPut:RANGe",
        "sense_cmd": ":OUTPut:SENSe",
        "beeper_cmd": ":SYSTem:BEEPer:STATe",
        "version_query": ":SYSTem:VERSion?",
        "otp_query": ":SYSTem:OTP?",
        "serial_baud": 9600,
    },
    "DP700": {
        "channel_token": "CH",
        "source_prefix": True,
        "measure_all": True,
        "cvcc_query": True,
        "ovp_value_cmd": ":OUTPut:OVP:VALue",
        "ocp_value_cmd": ":OUTPut:OCP:VALue",
        "protection_trip_query": True,
        "protection_clear": True,
        "error_query": ":SYSTem:ERRor?",
        "track_style": None,
        "track_mode_cmd": None,
        "onoff_sync_cmd": None,
        "range_cmd": None,
        "sense_cmd": None,
        "beeper_cmd": ":SYSTem:BEEPer:STATe",
        "version_query": ":SYSTem:VERSion?",
        "otp_query": None,
        "serial_baud": 9600,
    },
    "DP900": {
        "channel_token": "CH",
        "source_prefix": True,
        "measure_all": True,
        "cvcc_query": True,
        "ovp_value_cmd": ":OUTPut:OVP:VALue",
        "ocp_value_cmd": ":OUTPut:OCP:VALue",
        "protection_trip_query": True,
        "protection_clear": True,
        "error_query": ":SYSTem:ERRor?",
        "track_style": "DP900",  # :OUTPut:TRACk ON (no channel)
        "track_mode_cmd": ":SYSTem:TMODe",
        "onoff_sync_cmd": ":SYSTem:SYNC",
        "range_cmd": None,
        "sense_cmd": None,
        "beeper_cmd": ":SYSTem:BEEPer:STATe",
        "version_query": ":SYSTem:VERSion?",
        "otp_query": None,
        "serial_baud": 9600,
    },
    "DP2000": {
        "channel_token": "CH",
        "source_prefix": True,
        "measure_all": True,
        "cvcc_query": True,
        "ovp_value_cmd": ":OUTPut:OVP:VALue",
        "ocp_value_cmd": ":OUTPut:OCP:VALue",
        "protection_trip_query": True,
        "protection_clear": True,
        "error_query": ":SYSTem:ERRor?",
        "track_style": "DP900",
        "track_mode_cmd": ":SYSTem:TMODe",
        "onoff_sync_cmd": ":SYSTem:SYNC",
        "range_cmd": None,
        "sense_cmd": ":SYSTem:SENSe",
        "beeper_cmd": ":SYSTem:BEEPer:STATe",
        "version_query": ":SYSTem:VERSion?",
        "otp_query": None,
        "serial_baud": 9600,
    },
    "DP1308A": {
        "channel_token": "TOKEN",  # P6V | P25V | N25V from the channel spec
        "source_prefix": False,  # INST:NSEL n then :VOLTage
        "measure_all": False,
        "cvcc_query": False,
        "ovp_value_cmd": ":OUTPut:OVP",
        "ocp_value_cmd": ":OUTPut:OCP",
        "protection_trip_query": False,
        "protection_clear": False,
        "error_query": None,
        "track_style": "DP1308A",  # OUTPut:TRACk {P25V|N25V|OFF}
        "track_mode_cmd": None,
        "onoff_sync_cmd": None,
        "range_cmd": None,
        "sense_cmd": None,
        "beeper_cmd": None,
        "version_query": None,
        "otp_query": ":SYSTem:OTP?",
        "serial_baud": 9600,
    },
    "DP1116A": {
        "channel_token": None,  # single output, no channel parameter at all
        "source_prefix": False,
        "measure_all": False,
        "cvcc_query": False,
        "ovp_value_cmd": ":OUTPut:OVP",
        "ocp_value_cmd": ":OUTPut:OCP",
        "protection_trip_query": False,
        "protection_clear": False,
        "error_query": None,
        "track_style": None,
        "track_mode_cmd": None,
        "onoff_sync_cmd": None,
        "range_cmd": ":OUTPut:RANGe",
        "sense_cmd": None,
        "beeper_cmd": None,
        "version_query": None,
        "otp_query": ":SYSTem:OTP?",
        "serial_baud": 9600,
    },
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_NUM_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

_QUANTITY_ALIASES: Dict[str, str] = {
    "V": "voltage", "VOLT": "voltage", "VOLTAGE": "voltage", "U": "voltage",
    "I": "current", "A": "current", "CURR": "current", "CURRENT": "current", "AMP": "current",
    "P": "power", "W": "power", "POW": "power", "POWER": "power",
}
_QUANTITY_UNITS = {"voltage": "V", "current": "A", "power": "W"}


def parse_number(text: str, last: bool = False) -> Optional[float]:
    """Extract a float from an instrument reply.

    ``last=True`` takes the last numeric token, which is what the DP1308A needs
    for replies such as ``P6V,Limit Voltage,5.0000V`` (the ``6`` in ``P6V`` would
    otherwise win).  Unit suffixes (``6.000A``) are ignored.
    """
    if text is None:
        return None
    matches = _NUM_RE.findall(text.strip().strip('"'))
    if not matches:
        return None
    try:
        return float(matches[-1] if last else matches[0])
    except ValueError:
        return None


def parse_bool(text: str) -> bool:
    return str(text).strip().strip('"').upper() in ("1", "ON", "YES", "TRUE")


def _on_off(enabled: bool) -> str:
    return "ON" if enabled else "OFF"


def parse_measurement_channel(channel: Union[str, int, None], num_channels: int) -> Tuple[int, str]:
    """Turn ``CH1`` / ``1`` / ``CH1:V`` / ``2:I`` / ``CH3:P`` / ``V`` into (channel, quantity).

    The quantity defaults to voltage; the channel defaults to 1 when only a
    quantity is given.
    """
    if channel is None:
        return 1, "voltage"
    if isinstance(channel, int):
        ch, qty = channel, "voltage"
    else:
        text = str(channel).strip().upper().replace(" ", "")
        if not text:
            return 1, "voltage"
        head, _, tail = text.partition(":")
        if not tail and head in _QUANTITY_ALIASES:
            ch, qty = 1, _QUANTITY_ALIASES[head]
        else:
            digits = re.sub(r"[^0-9]", "", head)
            if not digits:
                raise ValueError(
                    f"Invalid channel '{channel}'. Use CH<n>, <n>, or CH<n>:V|I|P"
                )
            ch = int(digits)
            if tail:
                qty = _QUANTITY_ALIASES.get(tail)
                if qty is None:
                    raise ValueError(
                        f"Unknown quantity '{tail}' in '{channel}'. Use V, I or P"
                    )
            else:
                qty = "voltage"
    if not 1 <= ch <= num_channels:
        raise ValueError(f"Channel must be 1..{num_channels}")
    return ch, qty


# --------------------------------------------------------------------------- #
# Base driver
# --------------------------------------------------------------------------- #


class RigolDPBase(BaseEquipment):
    """Common implementation for every Rigol DP-series power supply.

    Subclasses only set ``FAMILY`` / ``DEFAULT_MODEL`` / ``MODEL_KEYWORDS``.
    After ``*IDN?`` the reported model is looked up in :data:`MODEL_TABLE`, and
    both the channel limits and the family dialect follow the *reported* model,
    so a generic instance still validates against the right limits.
    """

    FAMILY = "DP800"
    DEFAULT_MODEL = "DP832"
    # Model keywords for manager registration, most specific first.
    MODEL_KEYWORDS: Sequence[str] = tuple(MODEL_TABLE.keys())

    def __init__(self, resource_manager, resource_string: str):
        super().__init__(resource_manager, resource_string)
        self.manufacturer = "Rigol"
        self.model = self.DEFAULT_MODEL
        self.serial_number: Optional[str] = None
        self.firmware_version: Optional[str] = None
        self.spec: Dict[str, Any] = MODEL_TABLE[self.DEFAULT_MODEL]
        self.family: str = self.spec["family"]
        self._dialect: Dict[str, Any] = FAMILY_DIALECTS[self.family]
        self._active_range: Optional[str] = None  # label of the selected range
        # Serialises multi-command sequences; BaseEquipment on newer branches already
        # provides a reentrant lock of this name, so only create one if it is missing.
        if not hasattr(self, "_io_lock"):
            self._io_lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #

    async def connect(self):
        """Open the VISA resource, configure RS-232 if needed, verify *IDN?."""
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

                res = self.resource_string.upper()
                if res.startswith("ASRL") or res.startswith("COM") or "ASRL" in res:
                    # DP RS-232 default: 9600 8N1, commands terminated with CR+LF.
                    self.instrument.baud_rate = self._dialect["serial_baud"]
                    self.instrument.data_bits = 8
                    self.instrument.parity = 0
                    self.instrument.stop_bits = 10  # pyvisa constant: one stop bit
                    self.instrument.flow_control = 0
                    self.instrument.read_termination = "\n"
                    self.instrument.write_termination = "\r\n"
                    logger.info(
                        f"Configured serial port {self.resource_string}: "
                        f"{self._dialect['serial_baud']} 8N1, CRLF termination"
                    )
                else:
                    try:
                        self.instrument.read_termination = "\n"
                        self.instrument.write_termination = "\n"
                    except Exception:
                        pass

                self.instrument.timeout = 10000

                idn = await self._query("*IDN?")
                logger.info(f"Connected to Rigol power supply: {idn}")
                self._parse_idn(idn)

                self.connected = True
                self.cached_info = await self.get_info()

                if self.spec["ranges"]:
                    try:
                        await self.get_range()
                    except Exception as e:  # pragma: no cover - defensive
                        logger.debug(f"Could not read initial range: {e}")

            except Exception as e:
                logger.error(f"Failed to connect to {self.resource_string}: {e}")
                self.connected = False
                raise
            finally:
                self._is_connecting = False

    def _parse_idn(self, idn: str) -> Dict[str, Optional[str]]:
        parts = [p.strip() for p in idn.split(",")]
        info = {
            "manufacturer": parts[0] if len(parts) > 0 and parts[0] else self.manufacturer,
            "model": parts[1] if len(parts) > 1 and parts[1] else self.model,
            "serial": parts[2] if len(parts) > 2 and parts[2] else None,
            "firmware": parts[3] if len(parts) > 3 and parts[3] else None,
        }
        self.serial_number = info["serial"]
        self.firmware_version = info["firmware"]
        self._apply_model(info["model"] or self.model)
        return info

    def _apply_model(self, model: str) -> None:
        """Select the MODEL_TABLE row (and dialect) for the reported model."""
        key = (model or "").strip().upper()
        spec = MODEL_TABLE.get(key)
        if spec is None:
            # e.g. "DP832A-XYZ" or lowercase suffixes: longest table key that prefixes it.
            for cand in sorted(MODEL_TABLE, key=len, reverse=True):
                if key.startswith(cand):
                    spec = MODEL_TABLE[cand]
                    break
        if spec is None:
            logger.warning(
                f"Unknown Rigol DP model '{model}', using {self.DEFAULT_MODEL} limits"
            )
            spec = MODEL_TABLE[self.DEFAULT_MODEL]
        self.model = key or self.DEFAULT_MODEL
        self.spec = spec
        self.family = spec["family"]
        self._dialect = FAMILY_DIALECTS[self.family]

    # ------------------------------------------------------------------ #
    # Identity / status
    # ------------------------------------------------------------------ #

    @property
    def num_channels(self) -> int:
        return len(self.spec["channels"])

    async def get_info(self) -> EquipmentInfo:
        idn = await self._query("*IDN?")
        info = self._parse_idn(idn)
        return EquipmentInfo(
            id=generate_equipment_id(self.resource_string, "ps_"),
            type=EquipmentType.POWER_SUPPLY,
            manufacturer=info["manufacturer"] or self.manufacturer,
            model=info["model"] or self.model,
            serial_number=info["serial"],
            connection_type=self._determine_connection_type(),
            resource_string=self.resource_string,
        )

    def _capabilities(self) -> Dict[str, Any]:
        channels = self.spec["channels"]
        meas_channels: List[str] = []
        for idx in range(1, len(channels) + 1):
            meas_channels += [f"CH{idx}", f"CH{idx}:V", f"CH{idx}:I", f"CH{idx}:P"]
        return {
            "family": self.family,
            "num_channels": len(channels),
            "channels": [dict(c) for c in channels],
            "max_voltage": max(c["max_voltage"] for c in channels),
            "max_current": max(c["max_current"] for c in channels),
            "max_power": sum(c["max_power"] for c in channels),
            "ranges": [dict(r) for r in self.spec["ranges"]] if self.spec["ranges"] else None,
            "active_range": self._active_range,
            "interfaces": list(self.spec["interfaces"]),
            "supports_tracking": self._dialect["track_style"] is not None
            and self.spec["tracking_pair"] is not None,
            "tracking_channels": list(self.spec["tracking_pair"] or ()),
            "supports_pair": bool(self.spec["pair"]),
            "supports_protection_clear": self._dialect["protection_clear"],
            "supports_error_query": self._dialect["error_query"] is not None,
            "measurement_channels": meas_channels,
            "supports_acquisition": True,
        }

    async def get_status(self) -> EquipmentStatus:
        try:
            idn = await self._query("*IDN?")
            info = self._parse_idn(idn)
            capabilities = self._capabilities()
            try:
                capabilities["outputs"] = {
                    f"CH{n}": await self.get_output(n) for n in range(1, self.num_channels + 1)
                }
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

    async def run_self_test(self) -> Optional[bool]:
        """*TST?; DP700/800/900/2000 answer 0 on pass, DP1308A/DP1116A 'Pass'."""
        try:
            old = self.instrument.timeout if self.instrument else None
            if self.instrument is not None:
                self.instrument.timeout = 30000
            try:
                result = await self._query("*TST?")
            finally:
                if self.instrument is not None and old is not None:
                    self.instrument.timeout = old
            return result.strip().strip('"').upper() in ("0", "+0", "PASS")
        except Exception as e:
            logger.error(f"Self test failed on {self.resource_string}: {e}")
            return None

    async def reset(self) -> None:
        await self._write("*RST")
        await asyncio.sleep(0.5)
        self._active_range = None

    # ------------------------------------------------------------------ #
    # Command dispatch
    # ------------------------------------------------------------------ #

    async def execute_command(self, command: str, parameters: dict) -> Any:
        parameters = dict(parameters or {})
        handlers = {
            # setpoints / output (shared power-supply vocabulary)
            "set_voltage": self.set_voltage,
            "set_current": self.set_current,
            "apply": self.apply,
            "set_output": self.set_output,
            "get_output": self.get_output,
            "get_readings": self.get_readings,
            "get_all_readings": self.get_all_readings,
            "get_setpoints": self.get_setpoints,
            "get_measurement": self.get_measurement,
            "get_measurements": self.get_measurements,
            "get_mode": self.get_mode,
            # protection
            "set_ovp": self.set_ovp,
            "set_ocp": self.set_ocp,
            "get_protection": self.get_protection,
            "clear_protection": self.clear_protection,
            # tracking / pairing / range / sense
            "set_tracking": self.set_tracking,
            "get_tracking": self.get_tracking,
            "set_pair": self.set_pair,
            "get_pair": self.get_pair,
            "set_range": self.set_range,
            "get_range": self.get_range,
            "set_sense": self.set_sense,
            # system
            "set_beeper": self.set_beeper,
            "set_remote": self.set_remote,
            "get_version": self.get_version,
            "get_options": self.get_options,
            "get_otp": self.get_otp,
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
    # Channel / limit helpers
    # ------------------------------------------------------------------ #

    def _channel_index(self, channel: Union[int, str, None]) -> int:
        """Accept 1 / 'CH1' / '1' / a vendor token such as P6V or P30V."""
        if channel is None:
            return 1
        if isinstance(channel, bool):
            raise ValueError("Channel must be a number or CH<n>")
        if isinstance(channel, int):
            idx = channel
        else:
            text = str(channel).strip().upper()
            for i, spec in enumerate(self.spec["channels"], start=1):
                if text in (spec["name"], spec["token"]):
                    return i
            digits = re.sub(r"[^0-9]", "", text)
            if not digits:
                raise ValueError(f"Invalid channel '{channel}'")
            idx = int(digits)
        if not 1 <= idx <= self.num_channels:
            raise ValueError(f"{self.model} has channels 1..{self.num_channels}")
        return idx

    def _channel_spec(self, n: int) -> Dict[str, Any]:
        return self.spec["channels"][n - 1]

    def _token(self, n: int) -> Optional[str]:
        """SCPI channel parameter for channel n, or None when the family has none."""
        style = self._dialect["channel_token"]
        if style is None:
            return None
        if style == "TOKEN":
            return self._channel_spec(n)["token"]
        return f"CH{n}"

    def _cmd(self, root: str, n: Optional[int] = None, *args: Any, query: bool = False) -> str:
        params: List[str] = []
        if n is not None:
            tok = self._token(n)
            if tok:
                params.append(tok)
        params.extend(str(a) for a in args)
        head = root + ("?" if query else "")
        return head + (" " + ",".join(params) if params else "")

    def _limits(self, n: int) -> Dict[str, Any]:
        """Effective limits for channel n (active range on dual-range models)."""
        spec = self._channel_spec(n)
        ranges = self.spec["ranges"]
        if ranges and self._active_range:
            for r in ranges:
                if r["label"] == self._active_range:
                    merged = dict(spec)
                    merged.update({k: r[k] for k in (
                        "rated_voltage", "rated_current", "max_voltage",
                        "max_current", "max_power", "max_ovp", "max_ocp")})
                    return merged
        return spec

    def _check_voltage(self, voltage: float, n: int, limit_key: str = "max_voltage") -> float:
        lim = self._limits(n)
        try:
            value = float(voltage)
        except (TypeError, ValueError):
            raise ValueError(f"Voltage must be a number, got {voltage!r}")
        if math.isnan(value) or math.isinf(value):
            raise ValueError("Voltage must be finite")
        max_v = lim[limit_key]
        if lim["negative"]:
            # Negative channels are programmed with negative values; accept a
            # positive magnitude too and negate it.
            magnitude = abs(value)
            if magnitude > max_v:
                raise ValueError(
                    f"{self.model} CH{n} voltage must be between 0 and -{max_v} V"
                )
            return -magnitude
        if value < 0 or value > max_v:
            raise ValueError(f"{self.model} CH{n} voltage must be between 0 and {max_v} V")
        return value

    def _check_current(self, current: float, n: int, limit_key: str = "max_current") -> float:
        lim = self._limits(n)
        try:
            value = float(current)
        except (TypeError, ValueError):
            raise ValueError(f"Current must be a number, got {current!r}")
        if math.isnan(value) or math.isinf(value) or value < 0 or value > lim[limit_key]:
            raise ValueError(
                f"{self.model} CH{n} current must be between 0 and {lim[limit_key]} A"
            )
        return value

    @staticmethod
    def _fmt(value: float) -> str:
        return f"{value:.4f}".rstrip("0").rstrip(".") if value != 0 else "0"

    # ------------------------------------------------------------------ #
    # SOURce access (two dialects)
    # ------------------------------------------------------------------ #

    async def _select_channel(self, n: int) -> None:
        if self.num_channels > 1:
            await self._write(f":INSTrument:NSELect {n}")

    async def _source_write(self, n: int, leaf: str, value: str) -> None:
        if self._dialect["source_prefix"]:
            await self._write(f":SOURce{n}{leaf} {value}")
        else:
            await self._select_channel(n)
            await self._write(f"{leaf} {value}")

    async def _source_query(self, n: int, leaf: str) -> Optional[float]:
        if self._dialect["source_prefix"]:
            raw = await self._query(f":SOURce{n}{leaf}?")
        else:
            await self._select_channel(n)
            raw = await self._query(f"{leaf}?")
        return parse_number(raw, last=True)

    # ------------------------------------------------------------------ #
    # Setpoints
    # ------------------------------------------------------------------ #

    async def set_voltage(self, voltage: float, channel: Union[int, str] = 1) -> Dict[str, Any]:
        """Program the voltage setpoint of a channel ([:SOURce<n>]:VOLTage)."""
        n = self._channel_index(channel)
        value = self._check_voltage(voltage, n)
        async with self._io_lock:
            await self._source_write(n, ":VOLTage", self._fmt(value))
        return {"channel": n, "voltage": value}

    async def set_current(self, current: float, channel: Union[int, str] = 1) -> Dict[str, Any]:
        """Program the current limit of a channel ([:SOURce<n>]:CURRent)."""
        n = self._channel_index(channel)
        value = self._check_current(current, n)
        async with self._io_lock:
            await self._source_write(n, ":CURRent", self._fmt(value))
        return {"channel": n, "current": value}

    async def apply(
        self,
        channel: Union[int, str] = 1,
        voltage: Optional[float] = None,
        current: Optional[float] = None,
    ) -> Dict[str, Any]:
        """:APPLy CH<n>,<volt>,<curr> - set both values in one command."""
        n = self._channel_index(channel)
        if voltage is None:
            raise ValueError("apply() requires at least a voltage")
        v = self._check_voltage(voltage, n)
        args: List[str] = [self._fmt(v)]
        result = {"channel": n, "voltage": v}
        if current is not None:
            i = self._check_current(current, n)
            args.append(self._fmt(i))
            result["current"] = i
        async with self._io_lock:
            await self._write(self._cmd(":APPLy", n, *args))
        return result

    async def get_setpoints(self, channel: Union[int, str] = 1) -> Dict[str, float]:
        """Programmed voltage and current of a channel."""
        n = self._channel_index(channel)
        async with self._io_lock:
            v = await self._source_query(n, ":VOLTage")
            i = await self._source_query(n, ":CURRent")
        return {
            "channel": n,
            "voltage": v if v is not None else float("nan"),
            "current": i if i is not None else float("nan"),
        }

    # ------------------------------------------------------------------ #
    # Output
    # ------------------------------------------------------------------ #

    async def set_output(self, enabled: bool, channel: Union[int, str, None] = None) -> Dict[str, bool]:
        """Enable/disable a channel output; ``channel=None`` addresses every channel.

        ``manager.disconnect_device`` calls ``set_output(False)`` to reach a safe
        state, which therefore turns off all outputs.
        """
        if channel is None or (isinstance(channel, str) and channel.strip().upper() == "ALL"):
            targets = list(range(1, self.num_channels + 1))
        else:
            targets = [self._channel_index(channel)]
        async with self._io_lock:
            for n in targets:
                await self._write(self._cmd(":OUTPut:STATe", n, _on_off(bool(enabled))))
        return {f"CH{n}": bool(enabled) for n in targets}

    async def get_output(self, channel: Union[int, str] = 1) -> bool:
        n = self._channel_index(channel)
        return parse_bool(await self._query(self._cmd(":OUTPut:STATe", n, query=True)))

    async def get_mode(self, channel: Union[int, str] = 1) -> Optional[str]:
        """Regulation mode CV / CC / UR (:OUTPut:CVCC?); None where unsupported."""
        n = self._channel_index(channel)
        if not self._dialect["cvcc_query"]:
            return None
        return (await self._query(self._cmd(":OUTPut:CVCC", n, query=True))).strip().upper()

    # ------------------------------------------------------------------ #
    # Measurements
    # ------------------------------------------------------------------ #

    async def _measure_all(self, n: int) -> Tuple[float, float, float]:
        nan = float("nan")
        if self._dialect["measure_all"]:
            raw = await self._query(self._cmd(":MEASure:ALL", n, query=True))
            parts = [parse_number(p) for p in raw.split(",")]
            while len(parts) < 3:
                parts.append(None)
            v, i, p = parts[:3]
        else:
            v = parse_number(await self._query(self._cmd(":MEASure:VOLTage", n, query=True)))
            i = parse_number(await self._query(self._cmd(":MEASure:CURRent", n, query=True)))
            p = parse_number(await self._query(self._cmd(":MEASure:POWEr", n, query=True)))
        return (
            v if v is not None else nan,
            i if i is not None else nan,
            p if p is not None else nan,
        )

    async def get_readings(self, channel: Union[int, str] = 1) -> PowerSupplyData:
        """Measured V/I plus setpoints, output state and CV/CC mode for a channel."""
        n = self._channel_index(channel)
        async with self._io_lock:
            v_act, i_act, _ = await self._measure_all(n)
            v_set = await self._source_query(n, ":VOLTage")
            i_set = await self._source_query(n, ":CURRent")
            output = parse_bool(await self._query(self._cmd(":OUTPut:STATe", n, query=True)))
            mode = None
            if self._dialect["cvcc_query"]:
                mode = (await self._query(self._cmd(":OUTPut:CVCC", n, query=True))).strip().upper()
        v_set = v_set if v_set is not None else float("nan")
        i_set = i_set if i_set is not None else float("nan")
        if mode is None:
            # Older tree: infer from readings.
            in_cc = output and not math.isnan(i_act) and abs(i_act - i_set) < 0.01 and i_act > 0.01
            in_cv = output and not in_cc and not math.isnan(v_act) and abs(v_act - v_set) < 0.1
        else:
            in_cv = mode == "CV"
            in_cc = mode == "CC"
        return PowerSupplyData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            channel=n,
            voltage_set=v_set,
            current_set=i_set,
            voltage_actual=None if math.isnan(v_act) else v_act,
            current_actual=None if math.isnan(i_act) else i_act,
            output_enabled=output,
            in_cv_mode=in_cv,
            in_cc_mode=in_cc,
        )

    async def get_all_readings(self) -> List[PowerSupplyData]:
        return [await self.get_readings(n) for n in range(1, self.num_channels + 1)]

    async def get_measurement(self, channel: Union[str, int] = "CH1") -> Dict[str, Any]:
        """Acquisition-engine hook.

        ``channel`` accepts ``CH1``, ``1``, ``CH1:V`` (voltage, default),
        ``CH1:I`` (current), ``CH1:P`` (power); also ``V``/``I``/``P`` for CH1.
        Returns NaN when the instrument reply cannot be parsed.
        """
        n, qty = parse_measurement_channel(channel, self.num_channels)
        leaf = {"voltage": ":MEASure:VOLTage", "current": ":MEASure:CURRent", "power": ":MEASure:POWEr"}[qty]
        async with self._io_lock:
            raw = await self._query(self._cmd(leaf, n, query=True))
        value = parse_number(raw)
        return {
            "value": value if value is not None else float("nan"),
            "unit": _QUANTITY_UNITS[qty],
            "channel": n,
            "quantity": qty,
        }

    async def get_measurements(self, channel: Union[str, int] = 1) -> Dict[str, Any]:
        """Streaming hook: voltage / current / power of one channel."""
        n, _ = parse_measurement_channel(channel, self.num_channels)
        async with self._io_lock:
            v, i, p = await self._measure_all(n)
        return {"channel": n, "voltage": v, "current": i, "power": p,
                "voltage_unit": "V", "current_unit": "A", "power_unit": "W"}

    # ------------------------------------------------------------------ #
    # Protection
    # ------------------------------------------------------------------ #

    async def set_ovp(
        self,
        voltage: Optional[float] = None,
        channel: Union[int, str] = 1,
        enabled: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Set the OVP level and/or enable state of a channel."""
        n = self._channel_index(channel)
        async with self._io_lock:
            if voltage is not None:
                level = self._check_voltage(voltage, n, limit_key="max_ovp")
                await self._write(self._cmd(self._dialect["ovp_value_cmd"], n, self._fmt(level)))
            if enabled is not None:
                await self._write(self._cmd(":OUTPut:OVP:STATe", n, _on_off(bool(enabled))))
        return (await self.get_protection(n))["ovp"]

    async def set_ocp(
        self,
        current: Optional[float] = None,
        channel: Union[int, str] = 1,
        enabled: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Set the OCP level and/or enable state of a channel."""
        n = self._channel_index(channel)
        async with self._io_lock:
            if current is not None:
                level = self._check_current(current, n, limit_key="max_ocp")
                await self._write(self._cmd(self._dialect["ocp_value_cmd"], n, self._fmt(level)))
            if enabled is not None:
                await self._write(self._cmd(":OUTPut:OCP:STATe", n, _on_off(bool(enabled))))
        return (await self.get_protection(n))["ocp"]

    async def get_protection(self, channel: Union[int, str] = 1) -> Dict[str, Any]:
        """OVP/OCP level, enable state and (where queryable) tripped flag."""
        n = self._channel_index(channel)
        out: Dict[str, Any] = {"channel": n}
        async with self._io_lock:
            for kind in ("ovp", "ocp"):
                value_cmd = self._dialect[f"{kind}_value_cmd"]
                level = parse_number(await self._query(self._cmd(value_cmd, n, query=True)), last=True)
                enabled = parse_bool(
                    await self._query(self._cmd(f":OUTPut:{kind.upper()}:STATe", n, query=True))
                )
                tripped: Optional[bool] = None
                if self._dialect["protection_trip_query"]:
                    tripped = parse_bool(
                        await self._query(self._cmd(f":OUTPut:{kind.upper()}:QUES", n, query=True))
                    )
                out[kind] = {"level": level, "enabled": enabled, "tripped": tripped}
        return out

    async def clear_protection(self, channel: Union[int, str] = 1) -> Dict[str, Any]:
        """Clear a tripped OVP/OCP (:OUTPut:OVP:CLEAR / :OUTPut:OCP:CLEAR)."""
        if not self._dialect["protection_clear"]:
            raise ValueError(f"{self.model} does not support clearing protection remotely")
        n = self._channel_index(channel)
        async with self._io_lock:
            await self._write(self._cmd(":OUTPut:OVP:CLEAR", n))
            await self._write(self._cmd(":OUTPut:OCP:CLEAR", n))
        return await self.get_protection(n)

    # ------------------------------------------------------------------ #
    # Tracking / pairing / range / sense
    # ------------------------------------------------------------------ #

    async def set_tracking(self, mode: Union[str, bool], channel: Union[int, str, None] = None) -> Dict[str, Any]:
        """Configure channel tracking.

        ``mode``: ``ON``/``OFF`` (or bool) enables/disables tracking; ``SYNC`` /
        ``INDE`` selects the track mode where the family has one (DP800
        ``:SYSTem:TRACKMode``, DP900/DP2000 ``:SYSTem:TMODe``); ``SERIES`` /
        ``PARALLEL`` are forwarded to :meth:`set_pair`.
        """
        style = self._dialect["track_style"]
        pair = self.spec["tracking_pair"]
        key = ("ON" if mode else "OFF") if isinstance(mode, bool) else str(mode).strip().upper()
        aliases = {"1": "ON", "0": "OFF", "TRUE": "ON", "FALSE": "OFF", "ENABLE": "ON", "DISABLE": "OFF",
                   "INDEPENDENT": "INDE", "SYNCHRONOUS": "SYNC", "SER": "SERIES", "PAR": "PARALLEL"}
        key = aliases.get(key, key)
        if key in ("SERIES", "PARALLEL"):
            return await self.set_pair(key)
        if style is None or pair is None:
            raise ValueError(f"{self.model} has no tracking function")
        async with self._io_lock:
            if key in ("SYNC", "INDE"):
                cmd = self._dialect["track_mode_cmd"]
                if cmd is None:
                    raise ValueError(f"{self.model} has no track mode setting")
                await self._write(f"{cmd} {key}")
            elif key in ("ON", "OFF"):
                if style == "DP800":
                    targets = [self._channel_index(channel)] if channel is not None else list(pair)
                    for n in targets:
                        if n not in pair:
                            raise ValueError(
                                f"{self.model} tracking is only available on CH{pair[0]} and CH{pair[1]}"
                            )
                        await self._write(self._cmd(":OUTPut:TRACk", n, key))
                elif style == "DP900":
                    await self._write(f":OUTPut:TRACk {key}")
                elif style == "DP1308A":
                    if key == "OFF":
                        await self._write(":OUTPut:TRACk OFF")
                    else:
                        n = self._channel_index(channel) if channel is not None else pair[0]
                        if n not in pair:
                            raise ValueError(f"{self.model} tracking is only available on P25V/N25V")
                        await self._write(f":OUTPut:TRACk {self._token(n)}")
            else:
                raise ValueError("Tracking mode must be ON, OFF, SYNC, INDE, SERIES or PARALLEL")
        return await self.get_tracking()

    async def get_tracking(self) -> Dict[str, Any]:
        style = self._dialect["track_style"]
        pair = self.spec["tracking_pair"]
        out: Dict[str, Any] = {"supported": style is not None and pair is not None, "channels": list(pair or ())}
        if not out["supported"]:
            return out
        async with self._io_lock:
            if style == "DP800":
                out["enabled"] = {
                    f"CH{n}": parse_bool(await self._query(self._cmd(":OUTPut:TRACk", n, query=True)))
                    for n in pair
                }
            elif style == "DP900":
                out["enabled"] = parse_bool(await self._query(":OUTPut:TRACk?"))
            elif style == "DP1308A":
                raw = (await self._query(":OUTPut:TRACk?")).strip().upper()
                out["raw"] = raw
                out["enabled"] = "ON" in raw and "OFF" not in raw
            cmd = self._dialect["track_mode_cmd"]
            if cmd:
                out["mode"] = (await self._query(f"{cmd}?")).strip().upper()
        return out

    async def set_pair(self, mode: str = "OFF") -> Dict[str, Any]:
        """Internal series/parallel connection of CH1+CH2 (:OUTPut:PAIR, DP900/DP2000)."""
        if not self.spec["pair"]:
            raise ValueError(f"{self.model} has no internal series/parallel pairing")
        key = str(mode).strip().upper()
        key = {"SER": "SERIES", "SERIES": "SERIES", "PAR": "PARALLEL", "PARALLEL": "PARALLEL",
               "OFF": "OFF", "NONE": "OFF", "INDEPENDENT": "OFF"}.get(key)
        if key is None:
            raise ValueError("Pair mode must be OFF, SERIES or PARALLEL")
        token = {"OFF": "OFF", "SERIES": "SERies", "PARALLEL": "PARallel"}[key]
        async with self._io_lock:
            await self._write(f":OUTPut:PAIR {token}")
        return await self.get_pair()

    async def get_pair(self) -> Dict[str, Any]:
        if not self.spec["pair"]:
            return {"supported": False, "mode": None}
        raw = (await self._query(":OUTPut:PAIR?")).strip().upper()
        return {"supported": True, "mode": raw}

    def _find_range(self, name: str) -> Dict[str, Any]:
        key = str(name).strip().upper()
        for r in self.spec["ranges"] or ():
            if key == r["label"].upper() or key in r["aliases"]:
                return r
        labels = ", ".join(r["label"] for r in self.spec["ranges"] or ())
        raise ValueError(f"{self.model} ranges: {labels}")

    async def set_range(self, range: str) -> Dict[str, Any]:
        """Select the output range on dual-range models (:OUTPut:RANGe)."""
        cmd = self._dialect["range_cmd"]
        if not self.spec["ranges"] or cmd is None:
            raise ValueError(f"{self.model} has a single output range")
        r = self._find_range(range)
        async with self._io_lock:
            await self._write(f"{cmd} {r['label']}")
        self._active_range = r["label"]
        return await self.get_range()

    async def get_range(self) -> Optional[Dict[str, Any]]:
        """Active range (rated V/A and limits), or None on single-range models."""
        cmd = self._dialect["range_cmd"]
        if not self.spec["ranges"] or cmd is None:
            return None
        raw = (await self._query(f"{cmd}?")).strip().upper()
        nums = [float(x) for x in _NUM_RE.findall(raw)]
        match = None
        for r in self.spec["ranges"]:
            if raw == r["label"].upper() or raw in r["aliases"]:
                match = r
                break
            if len(nums) >= 2 and nums[0] == r["rated_voltage"] and nums[1] == r["rated_current"]:
                match = r
                break
            if len(nums) == 1 and nums[0] == r["rated_voltage"]:
                match = r
                break
        if match is None:
            logger.warning(f"Unrecognised range reply {raw!r} from {self.model}")
            self._active_range = None
            return {"label": None, "raw": raw}
        self._active_range = match["label"]
        out = dict(match)
        out["raw"] = raw
        return out

    async def set_sense(self, enabled: bool, channel: Union[int, str] = 1) -> bool:
        """Remote-sense on/off where the channel supports it."""
        cmd = self._dialect["sense_cmd"]
        n = self._channel_index(channel)
        if cmd is None or not self._channel_spec(n)["sense"]:
            raise ValueError(f"{self.model} CH{n} has no remote sense")
        async with self._io_lock:
            await self._write(self._cmd(cmd, n, _on_off(bool(enabled))))
            raw = await self._query(self._cmd(cmd, n, query=True))
        return parse_bool(raw)

    # ------------------------------------------------------------------ #
    # System
    # ------------------------------------------------------------------ #

    async def set_beeper(self, enabled: bool) -> bool:
        cmd = self._dialect["beeper_cmd"]
        if cmd is None:
            raise ValueError(f"{self.model} beeper cannot be controlled remotely")
        await self._write(f"{cmd} {_on_off(bool(enabled))}")
        return parse_bool(await self._query(f"{cmd}?"))

    async def set_remote(self, enabled: bool = True) -> bool:
        await self._write(":SYSTem:REMote" if enabled else ":SYSTem:LOCal")
        return bool(enabled)

    async def get_version(self) -> Optional[str]:
        cmd = self._dialect["version_query"]
        if cmd is None:
            return None
        return (await self._query(cmd)).strip()

    async def get_options(self) -> List[str]:
        raw = (await self._query("*OPT?")).strip()
        return [p.strip() for p in raw.split(",") if p.strip() and p.strip() != "0"]

    async def get_otp(self) -> Optional[bool]:
        cmd = self._dialect["otp_query"]
        if cmd is None:
            return None
        return parse_bool(await self._query(cmd))

    async def get_error(self) -> Dict[str, Any]:
        cmd = self._dialect["error_query"]
        if cmd is None:
            return {"code": None, "message": f"{self.model} has no error queue query", "raw": None}
        raw = await self._query(cmd)
        code_str, _, message = raw.partition(",")
        try:
            code = int(float(code_str.strip()))
        except ValueError:
            code = None
        return {"code": code, "message": message.strip().strip('"'), "raw": raw}

    async def get_error_code(self) -> Optional[int]:
        if self._dialect["error_query"] is None:
            return None
        return (await self.get_error())["code"]

    async def get_error_message(self) -> Optional[str]:
        if self._dialect["error_query"] is None:
            return None
        return (await self.get_error())["message"]

    async def get_state(self) -> Dict[str, Any]:
        """Snapshot for the state capture/restore system."""
        state: Dict[str, Any] = {"model": self.model, "family": self.family, "channels": {}}
        for n in range(1, self.num_channels + 1):
            ch: Dict[str, Any] = {}
            try:
                ch.update(await self.get_setpoints(n))
            except Exception as e:
                logger.debug(f"CH{n} setpoints unavailable: {e}")
            try:
                ch["output"] = await self.get_output(n)
            except Exception:
                ch["output"] = None
            try:
                prot = await self.get_protection(n)
                ch["ovp"] = prot["ovp"]
                ch["ocp"] = prot["ocp"]
            except Exception as e:
                logger.debug(f"CH{n} protection unavailable: {e}")
            state["channels"][f"CH{n}"] = ch
        for key, coro in (("tracking", self.get_tracking()), ("pair", self.get_pair()), ("range", self.get_range())):
            try:
                state[key] = await coro
            except Exception:
                state[key] = None
        return state


# --------------------------------------------------------------------------- #
# Concrete families
# --------------------------------------------------------------------------- #


class RigolDP800(RigolDPBase):
    """DP811/A, DP813/A, DP821/A, DP822/A, DP831/A, DP832/A (USB/LAN/RS232/GPIB)."""

    FAMILY = "DP800"
    DEFAULT_MODEL = "DP832"
    MODEL_KEYWORDS = ("DP832A", "DP832", "DP831A", "DP831", "DP822A", "DP822",
                      "DP821A", "DP821", "DP813A", "DP813", "DP811A", "DP811")


class RigolDP700(RigolDPBase):
    """DP711 (30 V/5 A) and DP712 (50 V/3 A): single output, RS-232 only (9600 8N1)."""

    FAMILY = "DP700"
    DEFAULT_MODEL = "DP711"
    MODEL_KEYWORDS = ("DP712", "DP711")


class RigolDP900(RigolDPBase):
    """DP932A / DP932U / DP932E triple-output supplies (USB/LAN, RS232 on A/E)."""

    FAMILY = "DP900"
    DEFAULT_MODEL = "DP932A"
    MODEL_KEYWORDS = ("DP932A", "DP932U", "DP932E", "DP932")


class RigolDP2000(RigolDPBase):
    """DP2031 triple-output supply (USB/LAN/RS232, GPIB adaptor)."""

    FAMILY = "DP2000"
    DEFAULT_MODEL = "DP2031"
    MODEL_KEYWORDS = ("DP2031",)


class RigolDP1308A(RigolDPBase):
    """DP1308A triple output (P6V 6 V/5 A, P25V 25 V/1 A, N25V -25 V/1 A); 2009 tree."""

    FAMILY = "DP1308A"
    DEFAULT_MODEL = "DP1308A"
    MODEL_KEYWORDS = ("DP1308A",)


class RigolDP1116A(RigolDPBase):
    """DP1116A single output, two ranges 16 V/10 A and 32 V/5 A; 2010 tree."""

    FAMILY = "DP1116A"
    DEFAULT_MODEL = "DP1116A"
    MODEL_KEYWORDS = ("DP1116A",)
