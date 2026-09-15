"""Tests for the Rigol DP-series power supply drivers.

They run against ``ScriptedDP``, a fake VISA instrument that answers the SCPI
documented in the DP700/DP800/DP900/DP2000/DP1308A/DP1116A programming guides
for the model it is created with, so no hardware is needed.  Anything the
driver sends that is not scripted (or not valid for that family) raises an
``AssertionError`` naming the command.
"""

import math
import re
import sys
from unittest.mock import MagicMock

import pytest

sys.path.append("..")

from equipment.rigol_power_supply import (FAMILY_DIALECTS,  # noqa: E402
                                          MODEL_TABLE, RigolDP700,
                                          RigolDP800, RigolDP900,
                                          RigolDP1116A, RigolDP1308A,
                                          RigolDP2000, RigolDPBase,
                                          parse_measurement_channel,
                                          parse_number)
from shared.models.data import PowerSupplyData  # noqa: E402
from shared.models.equipment import ConnectionType, EquipmentType  # noqa: E402

_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

_IDN = {
    "DP800": "RIGOL TECHNOLOGIES,{model},DP8C123456789,00.01.14",
    "DP700": "RIGOL TECHNOLOGIES,{model},DP7A123456789,00.01.05",
    "DP900": "Rigol Technologies,{model},DP9A123456789,00.01.02",
    "DP2000": "Rigol Technologies,{model},DP2A123456789,00.01.01",
    "DP1308A": "Rigol Technologies,DP1308A,DP1A110300105,00.01.00.00.01.02.01.01.03.00",
    # The DP1116A guide shows the fields padded with spaces.
    "DP1116A": "Rigol Technologies, DP1116A, DP1A666666666, 00.01.00.00.01.00.00.01.00.00",
}


class ScriptedDP:
    """Minimal DP-series SCPI simulator driven by MODEL_TABLE / FAMILY_DIALECTS."""

    _SOURCE_RE = re.compile(
        r"^:SOURCE(\d+)?:(VOLTAGE|CURRENT)(?::PROTECTION(?::LEVEL|:STATE|:CLEAR|:TRIPPED)?)?(\?)?$"
    )
    _BARE_SOURCE_RE = re.compile(r"^:(VOLTAGE|CURRENT)(\?)?$")

    def __init__(self, model="DP832", load_ohms=10.0):
        self.model = model
        self.spec = MODEL_TABLE[model]
        self.family = self.spec["family"]
        self.dialect = FAMILY_DIALECTS[self.family]
        self.channels = self.spec["channels"]
        n = len(self.channels)
        self.session = 1  # keeps BaseEquipment._is_instrument_valid() happy
        self.timeout = 10000
        self.writes = []
        self.queries = []
        # serial attributes pyvisa exposes
        self.baud_rate = None
        self.data_bits = None
        self.parity = None
        self.stop_bits = None
        self.flow_control = None
        self.read_termination = None
        self.write_termination = None
        # instrument state
        self.load_ohms = load_ohms
        self.selected = 1
        self.vset = [0.0] * n
        self.iset = [min(c["rated_current"], 3.0) for c in self.channels]
        self.out = [False] * n
        self.prot = {
            "OVP": {"level": [c["max_ovp"] for c in self.channels], "on": [False] * n, "trip": [False] * n},
            "OCP": {"level": [c["max_ocp"] for c in self.channels], "on": [False] * n, "trip": [False] * n},
        }
        self.track = [False] * n
        self.track_1308 = "OFF"
        self.track_mode = "SYNC" if self.family == "DP800" else "INDE"
        self.pair = "OFF"
        self.sense = [False] * n
        self.beeper = True
        self.range_label = self.spec["ranges"][0]["label"] if self.spec["ranges"] else None

    # -- helpers ----------------------------------------------------------
    def close(self):
        pass

    def trip(self, kind, channel=1):
        self.prot[kind]["trip"][channel - 1] = True

    def _split(self, cmd):
        c = cmd.strip()
        head, _, argstr = c.partition(" ")
        args = [a.strip() for a in argstr.split(",")] if argstr.strip() else []
        return head.upper(), args

    def _pop_channel(self, args):
        tokens = {}
        for i, c in enumerate(self.channels, start=1):
            tokens[c["name"]] = i
            if c["token"]:
                tokens[c["token"]] = i
        if self.dialect["channel_token"] is None:
            assert not args or args[0].upper() not in tokens, f"{self.model} takes no channel parameter"
            return 1
        if args and args[0].upper() in tokens:
            return tokens[args.pop(0).upper()]
        return self.selected

    def _measure(self, ch):
        i = ch - 1
        if not self.out[i]:
            return 0.0, 0.0, 0.0
        v, imax = abs(self.vset[i]), self.iset[i]
        cur = v / self.load_ohms
        if cur > imax:  # constant current
            cur = imax
            v = cur * self.load_ohms
        return v, cur, v * cur

    def _mode(self, ch):
        i = ch - 1
        if not self.out[i]:
            return "UR"
        return "CC" if abs(self.vset[i]) / self.load_ohms > self.iset[i] else "CV"

    def _num(self, value, unit=""):
        if self.family == "DP1116A":
            return f"{value:.3f}{unit}"
        return f"{value:.4f}"

    def _range(self, name):
        key = name.upper()
        for r in self.spec["ranges"]:
            if key == r["label"].upper() or key in r["aliases"]:
                return r
        raise AssertionError(f"Bad range {name} for {self.model}")

    # -- write ------------------------------------------------------------
    def write(self, cmd):
        self.writes.append(cmd)
        head, args = self._split(cmd)
        d = self.dialect
        if head in ("*RST", "*CLS"):
            writes, queries = self.writes, self.queries
            self.__init__(self.model, self.load_ohms)  # noqa: PLC2801 - simple reset
            self.writes, self.queries = writes, queries
            return
        if head in (":SYSTEM:REMOTE", ":SYSTEM:LOCAL"):
            return
        if head == ":INSTRUMENT:NSELECT":
            assert len(self.channels) > 1, "NSELect is only for multi-channel models"
            self.selected = int(args[0])
            return
        if head == ":APPLY":
            ch = self._pop_channel(args)
            self.selected = ch
            if args:
                self.vset[ch - 1] = float(args[0])
            if len(args) > 1:
                self.iset[ch - 1] = float(args[1])
            return
        m = self._SOURCE_RE.match(head)
        if m:
            assert d["source_prefix"], f"{self.model} has no :SOURce<n> prefix"
            ch = int(m.group(1)) if m.group(1) else self.selected
            return self._source_write(ch, m.group(2), head, args)
        m = self._BARE_SOURCE_RE.match(head)
        if m:
            assert not d["source_prefix"], f"{self.model} expects :SOURce<n>"
            return self._source_write(self.selected, m.group(1), head, args)
        if head == ":OUTPUT:STATE" or head == ":OUTPUT":
            ch = self._pop_channel(args)
            self.out[ch - 1] = args[0].upper() in ("ON", "1")
            return
        for kind in ("OVP", "OCP"):
            value_head = d[f"{kind.lower()}_value_cmd"].upper()
            if head == value_head:
                ch = self._pop_channel(args)
                self.prot[kind]["level"][ch - 1] = float(args[0])
                return
            if head == f":OUTPUT:{kind}:STATE":
                ch = self._pop_channel(args)
                self.prot[kind]["on"][ch - 1] = args[0].upper() in ("ON", "1")
                return
            if head == f":OUTPUT:{kind}:CLEAR":
                assert d["protection_clear"], f"{self.model} has no {kind} clear"
                ch = self._pop_channel(args)
                self.prot[kind]["trip"][ch - 1] = False
                return
        if head == ":OUTPUT:TRACK":
            style = d["track_style"]
            assert style is not None, f"{self.model} has no tracking"
            pair = self.spec["tracking_pair"]
            if style == "DP800":
                ch = self._pop_channel(args)
                assert ch in pair, f"CH{ch} does not support tracking on {self.model}"
                self.track[ch - 1] = args[0].upper() == "ON"
            elif style == "DP900":
                assert len(args) == 1 and args[0].upper() in ("ON", "OFF", "1", "0")
                for ch in pair:
                    self.track[ch - 1] = args[0].upper() in ("ON", "1")
            else:  # DP1308A
                assert args[0].upper() in ("P25V", "N25V", "OFF")
                self.track_1308 = args[0].upper()
            return
        if d["track_mode_cmd"] and head == d["track_mode_cmd"].upper():
            assert args[0].upper() in ("SYNC", "INDE")
            self.track_mode = args[0].upper()
            return
        if head == ":OUTPUT:PAIR":
            assert self.spec["pair"], f"{self.model} has no :OUTPut:PAIR"
            self.pair = {"OFF": "OFF", "SERIES": "SERIES", "PARALLEL": "PARALLEL"}[args[0].upper()]
            return
        if d["range_cmd"] and head == d["range_cmd"].upper():
            assert self.spec["ranges"], f"{self.model} is single range"
            self.range_label = self._range(args[0])["label"]
            return
        if d["sense_cmd"] and head == d["sense_cmd"].upper():
            ch = self._pop_channel(args)
            assert self.channels[ch - 1]["sense"], f"CH{ch} has no sense"
            self.sense[ch - 1] = args[0].upper() in ("ON", "1")
            return
        if d["beeper_cmd"] and head == d["beeper_cmd"].upper():
            self.beeper = args[0].upper() in ("ON", "1")
            return
        raise AssertionError(f"Unscripted write for {self.model}: {cmd}")

    def _source_write(self, ch, quantity, head, args):
        kind = "OVP" if quantity == "VOLTAGE" else "OCP"
        value = float(args[0]) if args and _NUM.match(args[0]) else None
        if ":PROTECTION" not in head:
            if quantity == "VOLTAGE":
                self.vset[ch - 1] = value
            else:
                self.iset[ch - 1] = value
        elif head.endswith(":STATE"):
            self.prot[kind]["on"][ch - 1] = args[0].upper() in ("ON", "1")
        elif head.endswith(":CLEAR"):
            self.prot[kind]["trip"][ch - 1] = False
        else:
            self.prot[kind]["level"][ch - 1] = value

    # -- query ------------------------------------------------------------
    def query(self, cmd):
        self.queries.append(cmd)
        head, args = self._split(cmd)
        d = self.dialect
        if head == "*IDN?":
            return _IDN[self.family].format(model=self.model)
        if head == "*TST?":
            return "Pass" if self.family in ("DP1308A", "DP1116A") else "0"
        if head == "*OPT?":
            return "0,DP8-ANALYZER,DP8-MONITOR" if self.family == "DP800" else "0"
        if head == ":INSTRUMENT:NSELECT?":
            return str(self.selected)
        if head == ":MEASURE:ALL?":
            assert d["measure_all"], f"{self.model} has no :MEASure:ALL?"
            v, i, p = self._measure(self._pop_channel(args))
            return f"{v:.4f},{i:.4f},{p:.3f}"
        if head in (":MEASURE:VOLTAGE?", ":MEASURE?"):
            return self._num(self._measure(self._pop_channel(args))[0], "V")
        if head == ":MEASURE:CURRENT?":
            return self._num(self._measure(self._pop_channel(args))[1], "A")
        if head == ":MEASURE:POWER?":
            return self._num(self._measure(self._pop_channel(args))[2], "W")
        m = self._SOURCE_RE.match(head)
        if m and m.group(3):
            assert d["source_prefix"], f"{self.model} has no :SOURce<n> prefix"
            ch = int(m.group(1)) if m.group(1) else self.selected
            return self._source_query(ch, m.group(2), head)
        m = self._BARE_SOURCE_RE.match(head)
        if m and m.group(2):
            assert not d["source_prefix"], f"{self.model} expects :SOURce<n>"
            return self._source_query(self.selected, m.group(1), head)
        if head in (":OUTPUT:STATE?", ":OUTPUT?"):
            return "ON" if self.out[self._pop_channel(args) - 1] else "OFF"
        if head in (":OUTPUT:CVCC?", ":OUTPUT:MODE?"):
            assert d["cvcc_query"], f"{self.model} has no :OUTPut:CVCC?"
            return self._mode(self._pop_channel(args))
        for kind in ("OVP", "OCP"):
            value_head = d[f"{kind.lower()}_value_cmd"].upper() + "?"
            if head == value_head:
                ch = self._pop_channel(args)
                level = self.prot[kind]["level"][ch - 1]
                return f"{level:.1f}" if self.family in ("DP1308A", "DP1116A") else f"{level:.3f}"
            if head == f":OUTPUT:{kind}:STATE?":
                return "ON" if self.prot[kind]["on"][self._pop_channel(args) - 1] else "OFF"
            if head in (f":OUTPUT:{kind}:QUES?", f":OUTPUT:{kind}:ALAR?"):
                assert d["protection_trip_query"], f"{self.model} has no {kind} trip query"
                return "YES" if self.prot[kind]["trip"][self._pop_channel(args) - 1] else "NO"
        if head == ":OUTPUT:TRACK?":
            style = d["track_style"]
            assert style is not None, f"{self.model} has no tracking"
            if style == "DP800":
                return "ON" if self.track[self._pop_channel(args) - 1] else "OFF"
            if style == "DP900":
                return "1" if any(self.track) else "0"
            return "TRACK_OFF" if self.track_1308 == "OFF" else f"TRACK_{self.track_1308[:3]}_ON"
        if d["track_mode_cmd"] and head == d["track_mode_cmd"].upper() + "?":
            return self.track_mode
        if head == ":OUTPUT:PAIR?":
            assert self.spec["pair"]
            return self.pair
        if d["range_cmd"] and head == d["range_cmd"].upper() + "?":
            r = self._range(self.range_label)
            return f"{r['rated_voltage']:g}V/{r['rated_current']:g}A"
        if d["sense_cmd"] and head == d["sense_cmd"].upper() + "?":
            ch = self._pop_channel(args)
            if not self.channels[ch - 1]["sense"]:
                return "NONE"
            return ("1" if self.sense[ch - 1] else "0") if self.family == "DP2000" else ("ON" if self.sense[ch - 1] else "OFF")
        if d["beeper_cmd"] and head == d["beeper_cmd"].upper() + "?":
            return "ON" if self.beeper else "OFF"
        if d["error_query"] and head == d["error_query"].upper():
            return '0,"No error"'
        if d["version_query"] and head == d["version_query"].upper():
            return "1999.0"
        if d["otp_query"] and head == d["otp_query"].upper():
            return "ON"
        raise AssertionError(f"Unscripted query for {self.model}: {cmd}")

    def _source_query(self, ch, quantity, head):
        kind = "OVP" if quantity == "VOLTAGE" else "OCP"
        i = ch - 1
        if ":PROTECTION" not in head:
            value = self.vset[i] if quantity == "VOLTAGE" else self.iset[i]
            if self.family == "DP1308A":
                label = "Voltage" if quantity == "VOLTAGE" else "Current"
                unit = "V" if quantity == "VOLTAGE" else "A"
                return f"{self.channels[i]['token']},Limit {label},{value:.4f}{unit}"
            if self.family == "DP1116A":
                return f"{value:.3f}{'V' if quantity == 'VOLTAGE' else 'A'}"
            return f"{value:.4f}" if quantity == "CURRENT" else f"{value:.3f}"
        if head.endswith(":STATE?"):
            return "ON" if self.prot[kind]["on"][i] else "OFF"
        if head.endswith(":TRIPPED?"):
            return "YES" if self.prot[kind]["trip"][i] else "NO"
        return f"{self.prot[kind]['level'][i]:.3f}"


def make_driver(cls, model, resource="USB0::0x1AB1::0x0E11::DP8C123456789::INSTR", **kw):
    inst = ScriptedDP(model, **kw)
    rm = MagicMock()
    rm.open_resource = MagicMock(return_value=inst)
    return cls(rm, resource), inst


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #


def test_parse_number():
    assert parse_number("5.000") == pytest.approx(5.0)
    assert parse_number("6.000A") == pytest.approx(6.0)
    assert parse_number("-27.0") == pytest.approx(-27.0)
    assert parse_number("P6V,Limit Voltage,5.1230V", last=True) == pytest.approx(5.123)
    assert parse_number("P6V,Limit Voltage,5.1230V") == pytest.approx(6.0)  # why last= exists
    assert parse_number("") is None
    assert parse_number("NONE") is None


def test_parse_measurement_channel():
    assert parse_measurement_channel("CH1", 3) == (1, "voltage")
    assert parse_measurement_channel("2", 3) == (2, "voltage")
    assert parse_measurement_channel(3, 3) == (3, "voltage")
    assert parse_measurement_channel("CH1:V", 3) == (1, "voltage")
    assert parse_measurement_channel("ch2:i", 3) == (2, "current")
    assert parse_measurement_channel("CH3:P", 3) == (3, "power")
    assert parse_measurement_channel("CH1:CURRENT", 3) == (1, "current")
    assert parse_measurement_channel("I", 1) == (1, "current")
    assert parse_measurement_channel(None, 1) == (1, "voltage")
    with pytest.raises(ValueError):
        parse_measurement_channel("CH4", 3)
    with pytest.raises(ValueError):
        parse_measurement_channel("CH1:Q", 3)
    with pytest.raises(ValueError):
        parse_measurement_channel("bogus", 3)


def test_model_table_is_consistent():
    for model, spec in MODEL_TABLE.items():
        assert spec["family"] in FAMILY_DIALECTS, model
        assert spec["channels"], model
        for ch in spec["channels"]:
            assert ch["max_voltage"] >= abs(ch["rated_voltage"]) > 0, (model, ch["name"])
            assert ch["max_current"] >= ch["rated_current"] > 0, (model, ch["name"])
            assert ch["max_ovp"] >= ch["max_voltage"], (model, ch["name"])
            assert ch["max_ocp"] >= ch["max_current"], (model, ch["name"])
        if spec["ranges"]:
            assert len(spec["channels"]) == 1, model
        if spec["family"] == "DP1308A":
            assert all(ch["token"] for ch in spec["channels"])


# --------------------------------------------------------------------------- #
# Identification
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cls,model,num_channels,manufacturer,max_v",
    [
        (RigolDP800, "DP832", 3, "RIGOL TECHNOLOGIES", 32.0),
        (RigolDP800, "DP811", 1, "RIGOL TECHNOLOGIES", 42.0),
        (RigolDP700, "DP712", 1, "RIGOL TECHNOLOGIES", 53.0),
        (RigolDP900, "DP932A", 3, "Rigol Technologies", 33.6),
        (RigolDP2000, "DP2031", 3, "Rigol Technologies", 32.0),
        (RigolDP1308A, "DP1308A", 3, "Rigol Technologies", 26.25),
        (RigolDP1116A, "DP1116A", 1, "Rigol Technologies", 33.6),
    ],
)
async def test_identification(cls, model, num_channels, manufacturer, max_v):
    psu, inst = make_driver(cls, model)
    await psu.connect()
    assert psu.connected is True
    assert psu.model == model
    assert psu.family == MODEL_TABLE[model]["family"]

    info = await psu.get_info()
    assert info.type == EquipmentType.POWER_SUPPLY
    assert info.id.startswith("ps_")
    assert info.manufacturer == manufacturer
    assert info.model == model
    assert info.serial_number and info.serial_number.startswith("DP")
    assert info.connection_type == ConnectionType.USB

    status = await psu.get_status()
    assert status.connected is True
    assert status.firmware_version.startswith("00.01")
    caps = status.capabilities
    assert caps["num_channels"] == num_channels
    assert caps["max_voltage"] == pytest.approx(max_v)
    assert caps["supports_acquisition"] is True
    assert len(caps["channels"]) == num_channels
    assert f"CH{num_channels}:P" in caps["measurement_channels"]
    assert caps["outputs"] == {f"CH{n}": False for n in range(1, num_channels + 1)}


@pytest.mark.asyncio
@pytest.mark.parametrize("model", sorted(MODEL_TABLE))
async def test_every_table_model_connects_with_generic_class(model):
    psu, inst = make_driver(RigolDPBase, model)
    await psu.connect()
    assert psu.model == model
    assert psu.spec is MODEL_TABLE[model]
    assert psu.family == MODEL_TABLE[model]["family"]
    caps = (await psu.get_status()).capabilities
    assert caps["num_channels"] == len(MODEL_TABLE[model]["channels"])


@pytest.mark.asyncio
async def test_generic_class_adopts_reported_model_limits_and_dialect():
    # A RigolDP800 instance pointed at a DP1308A must switch to the DP1308A limits and tree.
    psu, inst = make_driver(RigolDP800, "DP1308A")
    await psu.connect()
    assert psu.family == "DP1308A"
    assert psu.num_channels == 3
    with pytest.raises(ValueError):
        await psu.set_voltage(7.0, 1)  # P6V channel max is 6.3 V
    await psu.set_voltage(6.0, 1)
    assert inst.writes[-2:] == [":INSTrument:NSELect 1", ":VOLTage 6"]


@pytest.mark.asyncio
async def test_unknown_model_falls_back_to_class_default(caplog):
    psu, inst = make_driver(RigolDP800, "DP832")
    inst.model = "DP899X"  # not in the table
    await psu.connect()
    assert psu.spec is MODEL_TABLE["DP832"]
    assert psu.model == "DP899X"


@pytest.mark.asyncio
async def test_model_capabilities_differ_between_families():
    dp832, _ = make_driver(RigolDP800, "DP832")
    dp831, _ = make_driver(RigolDP800, "DP831")
    dp712, _ = make_driver(RigolDP700, "DP712")
    dp2031, _ = make_driver(RigolDP2000, "DP2031")
    for p in (dp832, dp831, dp712, dp2031):
        await p.connect()
    c832 = (await dp832.get_status()).capabilities
    c831 = (await dp831.get_status()).capabilities
    c712 = (await dp712.get_status()).capabilities
    c2031 = (await dp2031.get_status()).capabilities
    assert c832["channels"][2]["max_voltage"] == pytest.approx(5.3)
    assert c831["channels"][2]["negative"] is True and c831["tracking_channels"] == [2, 3]
    assert c832["tracking_channels"] == [1, 2]
    assert c712["interfaces"] == ["RS232"] and c712["supports_tracking"] is False
    assert c2031["supports_pair"] is True and c832["supports_pair"] is False
    assert c832["max_power"] == pytest.approx(195.0)  # 90 + 90 + 15 W


# --------------------------------------------------------------------------- #
# Connection types / serial
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_dp700_serial_connection_configures_port():
    psu, inst = make_driver(RigolDP700, "DP711", resource="ASRL/dev/ttyUSB0::INSTR")
    await psu.connect()
    assert inst.baud_rate == 9600
    assert inst.data_bits == 8
    assert inst.parity == 0
    assert inst.stop_bits == 10
    assert inst.write_termination == "\r\n"
    assert inst.read_termination == "\n"
    assert inst.timeout == 10000
    info = await psu.get_info()
    assert info.connection_type == ConnectionType.SERIAL
    caps = (await psu.get_status()).capabilities
    assert caps["interfaces"] == ["RS232"]
    assert caps["max_voltage"] == pytest.approx(32.0) and caps["max_current"] == pytest.approx(5.3)


@pytest.mark.asyncio
async def test_lan_connection_uses_newline_termination():
    psu, inst = make_driver(RigolDP800, "DP832", resource="TCPIP0::192.168.1.50::INSTR")
    await psu.connect()
    assert inst.write_termination == "\n" and inst.read_termination == "\n"
    assert inst.baud_rate is None
    assert (await psu.get_info()).connection_type == ConnectionType.ETHERNET


# --------------------------------------------------------------------------- #
# Setpoints / outputs / readings (DP800 tree)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_set_voltage_current_apply_and_setpoints():
    psu, inst = make_driver(RigolDP800, "DP832")
    await psu.connect()
    assert await psu.set_voltage(12.0, channel=2) == {"channel": 2, "voltage": 12.0}
    assert inst.writes[-1] == ":SOURce2:VOLTage 12"
    assert await psu.set_current(1.5, channel="CH2") == {"channel": 2, "current": 1.5}
    assert inst.writes[-1] == ":SOURce2:CURRent 1.5"
    sp = await psu.get_setpoints(2)
    assert sp["voltage"] == pytest.approx(12.0) and sp["current"] == pytest.approx(1.5)
    assert ":SOURce2:VOLTage?" in inst.queries and ":SOURce2:CURRent?" in inst.queries

    await psu.apply(channel=1, voltage=5, current=1)
    assert inst.writes[-1] == ":APPLy CH1,5,1"
    assert inst.vset[0] == 5.0 and inst.iset[0] == 1.0
    await psu.apply(channel="3", voltage=3.3)
    assert inst.writes[-1] == ":APPLy CH3,3.3"


@pytest.mark.asyncio
async def test_set_output_single_and_all_channels():
    psu, inst = make_driver(RigolDP800, "DP832")
    await psu.connect()
    assert await psu.set_output(True, channel=2) == {"CH2": True}
    assert inst.writes[-1] == ":OUTPut:STATe CH2,ON"
    assert await psu.get_output(2) is True and await psu.get_output(1) is False
    await psu.set_output(True, "CH1")
    # manager.disconnect_device() calls set_output(False): every channel goes off.
    result = await psu.set_output(False)
    assert result == {"CH1": False, "CH2": False, "CH3": False}
    assert inst.writes[-3:] == [":OUTPut:STATe CH1,OFF", ":OUTPut:STATe CH2,OFF", ":OUTPut:STATe CH3,OFF"]
    assert inst.out == [False, False, False]
    with pytest.raises(ValueError):
        await psu.set_output(True, channel=4)


@pytest.mark.asyncio
async def test_get_readings_cv_and_cc():
    psu, inst = make_driver(RigolDP800, "DP832", load_ohms=10.0)
    await psu.connect()
    await psu.apply(1, 5.0, 3.0)
    await psu.set_output(True, 1)
    r = await psu.get_readings(1)
    assert isinstance(r, PowerSupplyData)
    assert r.channel == 1 and r.output_enabled is True
    assert r.voltage_set == pytest.approx(5.0) and r.current_set == pytest.approx(3.0)
    assert r.voltage_actual == pytest.approx(5.0) and r.current_actual == pytest.approx(0.5)
    assert r.in_cv_mode is True and r.in_cc_mode is False
    assert ":MEASure:ALL? CH1" in inst.queries and ":OUTPut:CVCC? CH1" in inst.queries

    await psu.set_current(0.2, 1)  # 5 V into 10 ohm wants 0.5 A -> current limited
    r = await psu.get_readings("CH1")
    assert r.in_cc_mode is True and r.in_cv_mode is False
    assert r.current_actual == pytest.approx(0.2) and r.voltage_actual == pytest.approx(2.0)

    off = await psu.get_readings(3)
    assert off.output_enabled is False and off.voltage_actual == 0.0

    allr = await psu.get_all_readings()
    assert [x.channel for x in allr] == [1, 2, 3]


@pytest.mark.asyncio
async def test_get_mode_and_measurements_stream():
    psu, inst = make_driver(RigolDP900, "DP932A")
    await psu.connect()
    assert await psu.get_mode(1) == "UR"  # output off
    await psu.apply(1, 10, 3)
    await psu.set_output(True, 1)
    assert await psu.get_mode(1) == "CV"
    m = await psu.get_measurements(1)
    assert m["voltage"] == pytest.approx(10.0) and m["current"] == pytest.approx(1.0)
    assert m["power"] == pytest.approx(10.0) and m["voltage_unit"] == "V"


# --------------------------------------------------------------------------- #
# Protection
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ovp_ocp_set_query_trip_and_clear():
    psu, inst = make_driver(RigolDP800, "DP832")
    await psu.connect()
    ovp = await psu.set_ovp(30.5, channel=1, enabled=True)
    assert ":OUTPut:OVP:VALue CH1,30.5" in inst.writes
    assert ":OUTPut:OVP:STATe CH1,ON" in inst.writes
    assert ovp == {"level": pytest.approx(30.5), "enabled": True, "tripped": False}

    ocp = await psu.set_ocp(2.5, channel=1)
    assert inst.writes[-1] == ":OUTPut:OCP:VALue CH1,2.5"
    assert ocp["level"] == pytest.approx(2.5) and ocp["enabled"] is False

    ocp = await psu.set_ocp(channel=1, enabled=True)  # state only, no level write
    assert inst.writes[-1] == ":OUTPut:OCP:STATe CH1,ON"
    assert ocp["enabled"] is True and ocp["level"] == pytest.approx(2.5)

    inst.trip("OVP", 1)
    prot = await psu.get_protection(1)
    assert prot["ovp"]["tripped"] is True and prot["ocp"]["tripped"] is False
    assert ":OUTPut:OVP:QUES? CH1" in inst.queries

    prot = await psu.clear_protection(1)
    assert ":OUTPut:OVP:CLEAR CH1" in inst.writes and ":OUTPut:OCP:CLEAR CH1" in inst.writes
    assert prot["ovp"]["tripped"] is False

    with pytest.raises(ValueError):
        await psu.set_ovp(33.5, channel=1)  # Table 2-2: CH1 OVP max 33 V
    with pytest.raises(ValueError):
        await psu.set_ocp(3.4, channel=3)  # CH3 OCP max 3.3 A
    await psu.set_ovp(33.0, channel=1)
    await psu.set_ovp(5.5, channel=3)


# --------------------------------------------------------------------------- #
# Limit validation against the model table
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_setpoint_limits_per_channel_and_model():
    psu, inst = make_driver(RigolDP800, "DP832")
    await psu.connect()
    with pytest.raises(ValueError, match="between 0 and 32"):
        await psu.set_voltage(32.5, 1)
    with pytest.raises(ValueError, match="CH3 voltage must be between 0 and 5.3"):
        await psu.set_voltage(6.0, 3)
    with pytest.raises(ValueError, match="between 0 and 3.2"):
        await psu.set_current(3.3, 2)
    with pytest.raises(ValueError):
        await psu.set_voltage(-1.0, 1)
    with pytest.raises(ValueError):
        await psu.set_voltage(float("nan"), 1)
    with pytest.raises(ValueError):
        await psu.set_voltage("twelve", 1)
    with pytest.raises(ValueError):
        await psu.apply(1, 5, 9)
    n_writes = len(inst.writes)
    await psu.set_voltage(32.0, 1)
    await psu.set_current(3.2, 2)
    assert len(inst.writes) == n_writes + 2

    dp712, _ = make_driver(RigolDP700, "DP712")
    await dp712.connect()
    await dp712.set_voltage(53.0)
    with pytest.raises(ValueError):
        await dp712.set_voltage(53.5)
    with pytest.raises(ValueError):
        await dp712.set_current(3.3)


@pytest.mark.asyncio
async def test_negative_channel_programs_negative_values():
    psu, inst = make_driver(RigolDP800, "DP831")
    await psu.connect()
    assert (await psu.set_voltage(5.0, 3))["voltage"] == -5.0
    assert inst.writes[-1] == ":SOURce3:VOLTage -5"
    await psu.set_voltage(-12.0, "CH3")
    assert inst.writes[-1] == ":SOURce3:VOLTage -12"
    with pytest.raises(ValueError, match="-32"):
        await psu.set_voltage(-33.0, 3)
    with pytest.raises(ValueError):
        await psu.set_voltage(33.0, 3)
    await psu.set_ovp(30.0, channel=3)
    assert inst.writes[-1] == ":OUTPut:OVP:VALue CH3,-30"
    sp = await psu.get_setpoints(3)
    assert sp["voltage"] == pytest.approx(-12.0)


@pytest.mark.asyncio
async def test_dual_range_limits_follow_active_range():
    psu, inst = make_driver(RigolDP800, "DP811")
    await psu.connect()
    # connect() learns the range: DP811 default is P20V (20 V/10 A)
    assert ":OUTPut:RANGe?" in inst.queries
    rng = await psu.get_range()
    assert rng["label"] == "P20V" and rng["raw"] == "20V/10A"
    await psu.set_voltage(21.0)
    with pytest.raises(ValueError, match="21"):
        await psu.set_voltage(25.0)
    await psu.set_current(10.5)

    rng = await psu.set_range("HIGH")
    assert inst.writes[-1] == ":OUTPut:RANGe P40V"
    assert rng["label"] == "P40V" and rng["rated_voltage"] == 40
    await psu.set_voltage(25.0)
    with pytest.raises(ValueError, match="42"):
        await psu.set_voltage(45.0)
    with pytest.raises(ValueError, match="5.3"):
        await psu.set_current(10.0)
    with pytest.raises(ValueError):
        await psu.set_range("P8V")  # a DP813 range, not DP811

    dp832, _ = make_driver(RigolDP800, "DP832")
    await dp832.connect()
    assert await dp832.get_range() is None
    with pytest.raises(ValueError):
        await dp832.set_range("HIGH")


# --------------------------------------------------------------------------- #
# Older-tree families
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_dp1308a_dialect():
    psu, inst = make_driver(RigolDP1308A, "DP1308A")
    await psu.connect()
    # channel selection then bare :VOLTage, P6V/P25V/N25V tokens accepted
    await psu.set_voltage(5.0, "P25V")
    assert inst.writes[-2:] == [":INSTrument:NSELect 2", ":VOLTage 5"]
    await psu.set_current(1.0, 2)
    assert inst.writes[-2:] == [":INSTrument:NSELect 2", ":CURRent 1"]
    await psu.set_voltage(20.0, "N25V")  # negative channel
    assert inst.writes[-1] == ":VOLTage -20"
    with pytest.raises(ValueError):
        await psu.set_voltage(27.0, 2)  # 26.25 V max
    with pytest.raises(ValueError):
        await psu.set_current(1.1, 3)  # 1.05 A max

    sp = await psu.get_setpoints(2)  # reply "P25V,Limit Voltage,5.0000V"
    assert sp["voltage"] == pytest.approx(5.0) and sp["current"] == pytest.approx(1.0)

    await psu.set_output(True, 2)
    assert inst.writes[-1] == ":OUTPut:STATe P25V,ON"
    r = await psu.get_readings(2)
    assert ":MEASure:VOLTage? P25V" in inst.queries and ":MEASure:CURRent? P25V" in inst.queries
    assert not any(q.startswith(":MEASure:ALL") for q in inst.queries)
    assert not any(q.startswith(":OUTPut:CVCC") for q in inst.queries)
    assert r.voltage_actual == pytest.approx(5.0) and r.current_actual == pytest.approx(0.5)
    assert r.in_cv_mode is True and r.in_cc_mode is False

    ovp = await psu.set_ovp(6.5, channel=1, enabled=True)
    assert ":OUTPut:OVP P6V,6.5" in inst.writes and ":OUTPut:OVP:STATe P6V,ON" in inst.writes
    assert ovp["level"] == pytest.approx(6.5) and ovp["tripped"] is None
    with pytest.raises(ValueError):
        await psu.set_ovp(7.0, channel=1)
    ocp = await psu.set_ocp(1.2, channel=3)
    assert inst.writes[-1] == ":OUTPut:OCP N25V,1.2" and ocp["level"] == pytest.approx(1.2)
    with pytest.raises(ValueError, match="clearing protection"):
        await psu.clear_protection(1)

    trk = await psu.set_tracking("ON")
    assert inst.writes[-1] == ":OUTPut:TRACk P25V" and trk["enabled"] is True
    trk = await psu.set_tracking("OFF")
    assert inst.writes[-1] == ":OUTPut:TRACk OFF" and trk["enabled"] is False
    with pytest.raises(ValueError):
        await psu.set_tracking("ON", channel=1)

    err = await psu.get_error()
    assert err["code"] is None and "no error queue" in err["message"]
    assert not any("ERRor" in q for q in inst.queries)
    assert await psu.run_self_test() is True  # "Pass"
    assert await psu.get_version() is None


@pytest.mark.asyncio
async def test_dp1116a_dialect_and_ranges():
    psu, inst = make_driver(RigolDP1116A, "DP1116A")
    await psu.connect()
    rng = await psu.get_range()
    assert rng["label"] == "16V" and rng["raw"] == "16V/10A"
    await psu.set_voltage(12.0)
    assert inst.writes[-1] == ":VOLTage 12"
    assert not any("NSELect" in w for w in inst.writes)
    with pytest.raises(ValueError, match="16.8"):
        await psu.set_voltage(20.0)
    await psu.set_current(10.5)
    with pytest.raises(ValueError):
        await psu.set_current(10.6)

    await psu.set_range("32V")
    assert inst.writes[-1] == ":OUTPut:RANGe 32V"
    await psu.set_voltage(30.0)
    with pytest.raises(ValueError, match="5.25"):
        await psu.set_current(6.0)

    await psu.apply(1, 16, 5)
    assert inst.writes[-1] == ":APPLy 16,5"
    await psu.set_output(True)
    assert inst.writes[-1] == ":OUTPut:STATe ON"
    r = await psu.get_readings()
    assert ":MEASure:VOLTage?" in inst.queries and ":OUTPut:STATe?" in inst.queries
    assert r.voltage_actual == pytest.approx(16.0)  # parsed from "16.000V"
    assert r.current_actual == pytest.approx(1.6)  # parsed from "1.600A"
    assert r.voltage_set == pytest.approx(16.0) and r.current_set == pytest.approx(5.0)

    ovp = await psu.set_ovp(35.0, enabled=True)
    assert ":OUTPut:OVP 35" in inst.writes and ":OUTPut:OVP:STATe ON" in inst.writes
    assert ovp["level"] == pytest.approx(35.0) and ovp["tripped"] is None
    with pytest.raises(ValueError):
        await psu.set_ovp(36.0)
    with pytest.raises(ValueError):
        await psu.set_tracking("ON")
    m = await psu.get_measurement("CH1:P")
    assert m["value"] == pytest.approx(25.6) and m["unit"] == "W"  # "25.600W"


# --------------------------------------------------------------------------- #
# Tracking / pairing / sense
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_dp800_tracking_channels_and_mode():
    psu, inst = make_driver(RigolDP800, "DP831")
    await psu.connect()
    trk = await psu.set_tracking("ON")
    assert ":OUTPut:TRACk CH2,ON" in inst.writes and ":OUTPut:TRACk CH3,ON" in inst.writes
    assert trk["enabled"] == {"CH2": True, "CH3": True} and trk["mode"] == "SYNC"
    with pytest.raises(ValueError, match="CH2 and CH3"):
        await psu.set_tracking("ON", channel=1)
    trk = await psu.set_tracking("INDE")
    assert inst.writes[-1] == ":SYSTem:TRACKMode INDE" and trk["mode"] == "INDE"
    trk = await psu.set_tracking(False, channel=3)
    assert inst.writes[-1] == ":OUTPut:TRACk CH3,OFF"
    assert trk["enabled"] == {"CH2": True, "CH3": False}
    with pytest.raises(ValueError):
        await psu.set_tracking("SIDEWAYS")
    with pytest.raises(ValueError):
        await psu.set_pair("SERIES")  # DP800 has no :OUTPut:PAIR

    dp822, _ = make_driver(RigolDP800, "DP822")
    await dp822.connect()
    with pytest.raises(ValueError, match="no tracking"):
        await dp822.set_tracking("ON")
    assert (await dp822.get_tracking())["supported"] is False


@pytest.mark.asyncio
async def test_dp900_dp2000_tracking_pair_and_sense():
    psu, inst = make_driver(RigolDP900, "DP932A")
    await psu.connect()
    trk = await psu.set_tracking("ON")
    assert inst.writes[-1] == ":OUTPut:TRACk ON" and trk["enabled"] is True
    trk = await psu.set_tracking("SYNC")
    assert inst.writes[-1] == ":SYSTem:TMODe SYNC" and trk["mode"] == "SYNC"
    pair = await psu.set_pair("series")
    assert inst.writes[-1] == ":OUTPut:PAIR SERies" and pair["mode"] == "SERIES"
    pair = await psu.set_tracking("PARALLEL")  # forwarded to set_pair
    assert inst.writes[-1] == ":OUTPut:PAIR PARallel" and pair["mode"] == "PARALLEL"
    assert (await psu.set_pair("off"))["mode"] == "OFF"
    with pytest.raises(ValueError):
        await psu.set_pair("DIAGONAL")
    with pytest.raises(ValueError):
        await psu.set_sense(True, 1)  # DP900 has no remote sense

    dp2031, inst2 = make_driver(RigolDP2000, "DP2031")
    await dp2031.connect()
    assert await dp2031.set_sense(True, 1) is True
    assert inst2.writes[-1] == ":SYSTem:SENSe CH1,ON" and ":SYSTem:SENSe? CH1" in inst2.queries

    dp822, inst3 = make_driver(RigolDP800, "DP822")
    await dp822.connect()
    assert await dp822.set_sense(True, 2) is True
    assert inst3.writes[-1] == ":OUTPut:SENSe CH2,ON"
    with pytest.raises(ValueError):
        await dp822.set_sense(True, 1)


# --------------------------------------------------------------------------- #
# Acquisition hook / dispatch / state
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_measurement_channel_semantics():
    psu, inst = make_driver(RigolDP800, "DP832", load_ohms=5.0)
    await psu.connect()
    await psu.apply(1, 10.0, 3.0)
    await psu.set_output(True, 1)
    await psu.apply(2, 4.0, 3.0)
    await psu.set_output(True, 2)

    v = await psu.get_measurement("CH1")
    assert v == {"value": pytest.approx(10.0), "unit": "V", "channel": 1, "quantity": "voltage"}
    assert inst.queries[-1] == ":MEASure:VOLTage? CH1"
    assert (await psu.get_measurement("1"))["value"] == pytest.approx(10.0)
    assert (await psu.get_measurement(1))["value"] == pytest.approx(10.0)
    i = await psu.get_measurement("CH1:I")
    assert i["value"] == pytest.approx(2.0) and i["unit"] == "A" and inst.queries[-1] == ":MEASure:CURRent? CH1"
    p = await psu.get_measurement("CH2:P")
    assert p["value"] == pytest.approx(3.2) and p["unit"] == "W" and inst.queries[-1] == ":MEASure:POWEr? CH2"
    assert (await psu.get_measurement("ch2:v"))["value"] == pytest.approx(4.0)
    assert (await psu.get_measurement("V"))["channel"] == 1
    assert (await psu.get_measurement("CH3"))["value"] == 0.0  # output off
    with pytest.raises(ValueError):
        await psu.get_measurement("CH4")
    with pytest.raises(ValueError):
        await psu.get_measurement("CH1:Q")

    # Unparseable reply -> NaN, not an exception
    inst.query = lambda cmd: "NONE"
    nan = await psu.get_measurement("CH1:V")
    assert math.isnan(nan["value"])


@pytest.mark.asyncio
async def test_execute_command_dispatch():
    psu, inst = make_driver(RigolDP800, "DP832")
    await psu.connect()
    assert await psu.execute_command("set_voltage", {"voltage": 3.3, "channel": 3}) == {"channel": 3, "voltage": 3.3}
    assert inst.writes[-1] == ":SOURce3:VOLTage 3.3"
    await psu.execute_command("set_current", {"current": 1.0, "channel": 3})
    await psu.execute_command("set_output", {"enabled": True, "channel": 3})
    readings = await psu.execute_command("get_readings", {"channel": 3})
    assert isinstance(readings, PowerSupplyData) and readings.channel == 3
    assert readings.voltage_set == pytest.approx(3.3) and readings.output_enabled is True
    sp = await psu.execute_command("get_setpoints", {"channel": 3})
    assert sp["voltage"] == pytest.approx(3.3) and sp["current"] == pytest.approx(1.0)
    m = await psu.execute_command("get_measurement", {"channel": "CH3:V"})
    assert m["value"] == pytest.approx(3.3)
    prot = await psu.execute_command("set_ovp", {"voltage": 5.0, "channel": 3, "enabled": True})
    assert prot["enabled"] is True
    assert (await psu.execute_command("get_protection", {"channel": 3}))["ovp"]["level"] == pytest.approx(5.0)
    assert (await psu.execute_command("get_error", {}))["code"] == 0
    assert await psu.execute_command("self_test", {}) is True
    assert await psu.execute_command("get_version", {}) == "1999.0"
    assert await psu.execute_command("get_options", {}) == ["DP8-ANALYZER", "DP8-MONITOR"]
    assert await psu.execute_command("get_otp", {}) is True
    assert await psu.execute_command("set_beeper", {"enabled": False}) is False
    assert inst.writes[-1] == ":SYSTem:BEEPer:STATe OFF"
    assert await psu.execute_command("set_remote", {"enabled": True}) is True
    assert inst.writes[-1] == ":SYSTem:REMote"
    await psu.execute_command("reset", {})
    assert "*RST" in inst.writes and inst.out == [False, False, False]
    with pytest.raises(ValueError, match="Unknown command"):
        await psu.execute_command("make_coffee", {})
    with pytest.raises(TypeError):
        await psu.execute_command("set_voltage", {"volts": 1})


@pytest.mark.asyncio
async def test_get_state_snapshot():
    psu, inst = make_driver(RigolDP800, "DP832")
    await psu.connect()
    await psu.apply(2, 7.5, 0.25)
    await psu.set_output(True, 2)
    await psu.set_ovp(9.0, channel=2, enabled=True)
    await psu.set_tracking("ON")
    state = await psu.execute_command("get_state", {})
    assert state["model"] == "DP832" and state["family"] == "DP800"
    ch2 = state["channels"]["CH2"]
    assert ch2["voltage"] == pytest.approx(7.5) and ch2["current"] == pytest.approx(0.25)
    assert ch2["output"] is True and ch2["ovp"]["level"] == pytest.approx(9.0) and ch2["ovp"]["enabled"] is True
    assert state["channels"]["CH1"]["output"] is False
    assert state["tracking"]["enabled"] == {"CH1": True, "CH2": True}
    assert state["pair"] == {"supported": False, "mode": None}
    assert state["range"] is None

    dp811, _ = make_driver(RigolDP800, "DP811A")
    await dp811.connect()
    st = await dp811.get_state()
    assert st["range"]["label"] == "P20V" and list(st["channels"]) == ["CH1"]


@pytest.mark.asyncio
async def test_status_reports_error_when_instrument_gone():
    psu, inst = make_driver(RigolDP800, "DP832")
    await psu.connect()

    def boom(cmd):
        raise OSError("VISA session lost")

    inst.query = boom
    status = await psu.get_status()
    assert status.connected is False and "VISA session lost" in status.error
