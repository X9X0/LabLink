"""Tests for the Rigol modern-SCPI oscilloscope driver family.

A scripted fake instrument answers the SCPI the driver sends the way the
programming guides document it (including ``#9`` definite-length binary
blocks for ``:WAV:DATA?`` and ``:DISP:DATA?``), so no hardware is needed.
"""

import dataclasses
import math
import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.path.append("..")

from server.equipment.rigol_modern_scope import (  # noqa: E402
    FAMILIES, MEASURE_ITEMS, RigolDHO800, RigolDHO1000, RigolDHO5000,
    RigolDS1000ZE, RigolDS4000, RigolDS6000, RigolDS70000, RigolDS80000,
    RigolDS8000R, RigolMHO900, RigolModernScopeBase, RigolMSO5000,
    RigolMSO7000, RigolMSO8000, normalize_measure_item, parse_measurement,
    parse_preamble, parse_tmc_block, raw_to_volts, resolve_model)
from shared.models.data import WaveformData  # noqa: E402
from shared.models.equipment import ConnectionType, EquipmentType  # noqa: E402

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def tmc_block(payload: bytes) -> bytes:
    return b"#9%09d" % len(payload) + payload + b"\n"


class ScriptedScope:
    """Minimal Rigol scope SCPI simulator (modern tree + DS4000/DS6000 legacy bits)."""

    SERIAL = "DHO9A254800123"
    FIRMWARE = "00.01.02.00.01"
    SCREEN_POINTS = 1000
    MEASUREMENTS = {
        "VPP": "3.200000E+00",
        "VMAX": "1.600000E+00",
        "VMIN": "-1.600000E+00",
        "VAVG": "1.000000E-02",
        "VRMS": "1.131000E+00",
        "VTOP": "1.500000E+00",
        "VBASE": "-1.500000E+00",
        "VAMP": "3.000000E+00",
        "FREQUENCY": "1.000000E+03",
        "PERIOD": "1.000000E-03",
        "RTIME": "1.200000E-06",
        "FTIME": "1.300000E-06",
        "PWIDTH": "5.000000E-04",
        "NWIDTH": "5.000000E-04",
        "PDUTY": "5.000000E-01",
        "NDUTY": "5.000000E-01",
        "OVERSHOOT": "8.888889E-03",
    }

    def __init__(self, model="DHO924S", memory_depth=6000):
        self.model = model
        self.session = 1  # keeps BaseEquipment._is_instrument_valid() happy
        self.timeout = 10000
        self.writes = []
        self.queries = []
        self.memory_depth = memory_depth
        self.chan = {
            n: {"DISP": "1" if n == 1 else "0", "SCAL": "1.000000E+00", "OFFS": "0.000000E+00",
                "COUP": "DC", "PROB": "1", "BWL": "OFF", "INV": "0"}
            for n in range(1, 9)
        }
        self.tim = {"SCAL": "1.000000E-06", "OFFS": "0.000000E+00", "MODE": "MAIN"}
        self.trig = {"MODE": "EDGE", "SWE": "AUTO", "COUP": "DC", "HOLD": "1.600000E-08",
                     "NREJ": "0", "SOUR": "CHAN1", "SLOP": "POS", "LEV": "0.000000E+00",
                     "STAT": "RUN"}
        self.acq = {"TYPE": "NORM", "AVER": "2", "MDEP": "1.000E+4", "SRAT": "1.00000E+9"}
        self.wav = {"SOUR": "CHAN1", "MODE": "NORM", "FORM": "BYTE", "STAR": 1, "STOP": 1000, "POIN": 1000}
        self.la_enabled = "0"
        self.la_channels = {f"D{n}": "0" for n in range(16)}
        self.la_thresholds = {1: "1.40E+00", 2: "1.40E+00"}
        self._pending = None
        self._status_flow_offset = 0
        self.autos = []

    # -- helpers ----------------------------------------------------------
    def close(self):
        pass

    @staticmethod
    def _short(value, table):
        v = value.upper()
        for long, short in table.items():
            if v.startswith(long[:4]) or v == short:
                return short
        return v

    def raw_sample(self, index_1based: int) -> int:
        return (index_1based * 7) % 256

    def screen_sample(self, index: int) -> int:
        return index % 256

    def screen_payload(self) -> bytes:
        return bytes(self.screen_sample(i) for i in range(self.SCREEN_POINTS))

    def preamble(self) -> str:
        if self.wav["MODE"] == "RAW":
            return f"0,2,{self.memory_depth},1,1.000000E-9,-3.000000E-6,0.000000E-12,4.000000E-03,0,128"
        return f"0,0,{self.SCREEN_POINTS},1,1.000000E-8,-5.000000E-6,0.000000E-12,4.000000E-03,0,128"

    # -- pyvisa surface ---------------------------------------------------
    def write(self, cmd):
        self.writes.append(cmd)
        c = cmd.strip()
        head, _, arg = c.partition(" ")
        head_u, arg_u = head.upper(), arg.strip().upper()
        if head_u.endswith("?"):
            self.queries.append(cmd)
            self._pending = self._answer(head_u[:-1], arg_u)
        else:
            self._apply(head_u, arg_u)

    def read_raw(self):
        data, self._pending = self._pending, None
        if data is None:
            raise AssertionError("read_raw() with no pending response")
        return data

    def query(self, cmd):
        self.write(cmd)
        return self.read_raw().decode("latin-1")

    # -- command handling -------------------------------------------------
    def _apply(self, head, arg):
        if head in (":RUN",):
            self.trig["STAT"] = "RUN"
        elif head == ":STOP":
            self.trig["STAT"] = "STOP"
        elif head == ":SING":
            self.trig["STAT"] = "WAIT"
        elif head in (":TFOR", ":CLE", "*RST", "*CLS"):
            pass
        elif head in (":AUTOSCALE", ":AUTOSET", ":AUT"):
            self.autos.append(head)
        elif head.startswith(":CHAN"):
            n, sub = self._chan_parts(head)
            table = self.chan[n]
            assert sub in table, f"unscripted channel command {head}"
            if sub in ("DISP", "INV"):
                table[sub] = "1" if arg in ("ON", "1") else "0"
            elif sub == "PROB":
                table[sub] = arg
            elif sub in ("SCAL", "OFFS"):
                table[sub] = f"{float(arg):.6E}"
            else:
                table[sub] = arg
        elif head == ":TIM:MAIN:SCAL":
            self.tim["SCAL"] = f"{float(arg):.6E}"
        elif head == ":TIM:MAIN:OFFS":
            self.tim["OFFS"] = f"{float(arg):.6E}"
        elif head == ":TIM:MODE":
            self.tim["MODE"] = arg
        elif head == ":TRIG:MODE":
            self.trig["MODE"] = arg
        elif head == ":TRIG:SWE":
            self.trig["SWE"] = self._short(arg, {"AUTO": "AUTO", "NORMAL": "NORM", "SINGLE": "SING"})
        elif head == ":TRIG:COUP":
            self.trig["COUP"] = arg
        elif head == ":TRIG:HOLD":
            self.trig["HOLD"] = f"{float(arg):.6E}"
        elif head == ":TRIG:NREJ":
            self.trig["NREJ"] = "1" if arg in ("ON", "1") else "0"
        elif head == ":TRIG:EDGE:SOUR":
            self.trig["SOUR"] = arg
        elif head == ":TRIG:EDGE:SLOP":
            self.trig["SLOP"] = self._short(arg, {"POSITIVE": "POS", "NEGATIVE": "NEG", "RFALL": "RFAL"})
        elif head == ":TRIG:EDGE:LEV":
            self.trig["LEV"] = f"{float(arg):.6E}"
        elif head == ":ACQ:TYPE":
            self.acq["TYPE"] = self._short(arg, {"NORMAL": "NORM", "AVERAGES": "AVER", "PEAK": "PEAK",
                                                 "HRESOLUTION": "HRES", "ULTRA": "ULTR"})
        elif head == ":ACQ:AVER":
            self.acq["AVER"] = arg
        elif head == ":ACQ:MDEP":
            self.acq["MDEP"] = "AUTO" if arg == "AUTO" else f"{float(arg):.3E}"
        elif head == ":WAV:SOUR":
            self.wav["SOUR"] = arg
        elif head == ":WAV:MODE":
            self.wav["MODE"] = self._short(arg, {"NORMAL": "NORM", "RAW": "RAW", "MAXIMUM": "MAX"})
        elif head == ":WAV:FORM":
            self.wav["FORM"] = arg
        elif head in (":WAV:STAR", ":WAV:STOP", ":WAV:POIN"):
            self.wav[head[5:]] = int(arg)
        elif head == ":WAV:RES":
            self._status_flow_offset = 0
        elif head in (":WAV:BEG", ":WAV:END"):
            pass
        elif head in (":LA:ENAB", ":LA:STAT"):
            self.la_enabled = "1" if arg in ("ON", "1") else "0"
        elif head in (":LA:DIG:ENAB", ":LA:DIG:DISP"):
            d, _, state = arg.partition(",")
            self.la_channels[d.strip()] = "1" if state.strip() in ("ON", "1") else "0"
        elif head.startswith(":LA:POD") and head.endswith(":THR"):
            self.la_thresholds[int(head[7])] = f"{float(arg):.2E}"
        else:
            raise AssertionError(f"Unscripted write: {head} {arg}")

    @staticmethod
    def _chan_parts(head):
        rest = head[5:]
        num, _, sub = rest.partition(":")
        return int(num), sub

    def _answer(self, head, arg) -> bytes:
        text = None
        if head == "*IDN":
            text = f"RIGOL TECHNOLOGIES,{self.model},{self.SERIAL},{self.FIRMWARE}"
        elif head.startswith(":CHAN"):
            n, sub = self._chan_parts(head)
            text = self.chan[n][sub]
        elif head in (":TIM:MAIN:SCAL", ":TIM:MAIN:OFFS", ":TIM:MODE"):
            text = self.tim[head.split(":")[-1]]
        elif head.startswith(":TRIG:EDGE:"):
            text = self.trig[head.split(":")[-1]]
        elif head.startswith(":TRIG:"):
            text = self.trig[head.split(":")[-1]]
        elif head.startswith(":ACQ:"):
            text = self.acq[head.split(":")[-1]]
        elif head == ":MEAS:ITEM":
            item, _, src = arg.partition(",")
            text = self._measurement(item, src)
        elif head.startswith(":MEAS:"):
            text = self._measurement(head[6:], arg)
        elif head == ":WAV:PRE":
            text = self.preamble()
        elif head == ":WAV:STAT":
            remaining = self.memory_depth - self._status_flow_offset
            text = "READ" if remaining > self.wav["POIN"] else "IDLE"
        elif head == ":WAV:DATA":
            return tmc_block(self._waveform_payload())
        elif head == ":DISP:DATA":
            fmt = arg.split(",")[-1] if arg else ""
            if fmt in ("PNG",) or (not arg and self.model.startswith("MSO8")):
                return tmc_block(PNG_MAGIC + b"\x00" * 200)
            return tmc_block(b"BM" + b"\x00" * 200)
        elif head == ":SYST:ERR":
            text = '0,"No error"'
        elif head in (":LA:ENAB", ":LA:STAT"):
            text = self.la_enabled
        elif head in (":LA:DIG:ENAB", ":LA:DIG:DISP"):
            text = self.la_channels[arg]
        elif head.startswith(":LA:POD") and head.endswith(":THR"):
            text = self.la_thresholds[int(head[7])]
        if text is None:
            raise AssertionError(f"Unscripted query: {head}? {arg}")
        return (text + "\n").encode()

    def _measurement(self, item, src):
        item = item.upper()
        if src == "CHAN2" and item == "VPP":
            return "9.9E37"  # invalid / clipped measurement sentinel
        for key, value in self.MEASUREMENTS.items():
            if key.startswith(item[:4]) or item.startswith(key[:4]):
                return value
        raise AssertionError(f"Unscripted measurement item {item}")

    def _waveform_payload(self) -> bytes:
        if self.wav["MODE"] != "RAW":
            return self.screen_payload()
        assert self.trig["STAT"] == "STOP", "RAW memory reads require the STOP state"
        if self.model.startswith(("DS6", "DS4")):
            # DS4000/DS6000 flow: successive :WAV:DATA? calls return the next buffer.
            start = self._status_flow_offset + 1
            stop = min(self.memory_depth, self._status_flow_offset + self.wav["POIN"])
            self._status_flow_offset = stop
        else:
            start, stop = self.wav["STAR"], self.wav["STOP"]
        return bytes(self.raw_sample(i) for i in range(start, stop + 1))


def make_driver(cls, model, resource="USB0::0x1AB1::0x044C::DHO9A254800123::INSTR", **kw):
    inst = ScriptedScope(model, **kw)
    rm = MagicMock()
    rm.open_resource = MagicMock(return_value=inst)
    return cls(rm, resource), inst


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #


def test_parse_tmc_block():
    payload = bytes(range(10))
    assert parse_tmc_block(tmc_block(payload)) == (payload, 0)
    partial = tmc_block(payload)[:14]  # 11-byte header + 3 payload bytes
    got, missing = parse_tmc_block(partial)
    assert got == payload[:3] and missing == 7
    assert parse_tmc_block(b"#900")[1] == 7  # header itself incomplete (11 bytes needed)
    assert parse_tmc_block(b"BM\x00\x01\n") == (b"BM\x00\x01", 0)
    assert parse_tmc_block(b"#0abc\n") == (b"abc", 0)


def test_parse_preamble_and_scaling():
    pre = parse_preamble("0,0,1000,1,1.000000E-8,-5.000000E-6,0.000000E-12,4.000000E-03,0,128")
    assert pre["points"] == 1000 and pre["x_increment"] == pytest.approx(1e-8)
    volts = raw_to_volts(bytes([0, 128, 255]), pre)
    assert volts.tolist() == pytest.approx([-0.512, 0.0, 0.508])
    words = np.array([0, 128, 255], dtype="<u2").tobytes()
    assert raw_to_volts(words, pre, "WORD").tolist() == pytest.approx([-0.512, 0.0, 0.508])
    with pytest.raises(ValueError):
        parse_preamble("1,2,3")


def test_measurement_helpers():
    assert parse_measurement("3.089000e+00") == pytest.approx(3.089)
    assert math.isnan(parse_measurement("9.9E37"))
    assert math.isnan(parse_measurement(""))
    assert normalize_measure_item("pk2pk") == "VPP"
    assert normalize_measure_item("rise_time") == "RISE"
    assert normalize_measure_item("FREQuency") == "FREQ"
    assert MEASURE_ITEMS[normalize_measure_item("duty")] == "PDUTy"
    with pytest.raises(ValueError):
        normalize_measure_item("SPARKLE")


def test_resolve_model_table():
    assert resolve_model("DHO924S").analog_channels == 4
    assert resolve_model("DHO924S").digital_channels == 16
    assert resolve_model("MSO5152-E").bandwidth_hz == pytest.approx(150e6)
    assert resolve_model("DS8104-R").family == "DS8000R"
    assert resolve_model("MHO5056").analog_channels == 6
    assert resolve_model("DHO5058").analog_channels == 8
    assert resolve_model("DS1102Z-E").analog_channels == 2
    assert resolve_model("MSO4034").digital_channels == 16 and resolve_model("DS4034").family == "DS4000"
    assert resolve_model("DHO1999").family == "DHO1000"  # family fallback
    assert resolve_model("DM3058") is None


# --------------------------------------------------------------------------- #
# Identification: one model per subclass (plus a few extra rows)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "cls,model,analog,digital,autoset,bandwidth",
    [
        (RigolDHO800, "DHO924S", 4, 16, ":AUToset", 250e6),
        (RigolDHO800, "DHO812", 2, 0, ":AUToset", 100e6),
        (RigolDHO1000, "DHO1072", 2, 0, ":AUToset", 70e6),
        (RigolDHO1000, "DHO4804", 4, 0, ":AUToset", 800e6),
        (RigolDHO5000, "DHO5058", 8, 0, ":AUToset", 500e6),
        (RigolDHO5000, "MHO5106", 6, 16, ":AUToset", 1e9),
        (RigolMHO900, "MHO984", 4, 16, ":AUToset", 800e6),
        (RigolMHO900, "MHO2034", 4, 16, ":AUToset", 350e6),
        (RigolMSO5000, "MSO5072", 2, 16, ":AUToscale", 70e6),
        (RigolMSO5000, "MSO5152-E", 2, 16, ":AUToscale", 150e6),
        (RigolMSO7000, "DS7034", 4, 0, ":AUToscale", 350e6),
        (RigolMSO7000, "MSO7054", 4, 16, ":AUToscale", 500e6),
        (RigolMSO8000, "MSO8154A", 4, 16, ":AUToscale", 1.5e9),
        (RigolDS8000R, "DS8104-R", 4, 0, ":AUToscale", 1e9),
        (RigolDS4000, "DS4024E", 4, 0, ":AUToscale", 200e6),
        (RigolDS6000, "DS6062", 2, 0, ":AUToscale", 600e6),
        (RigolDS70000, "DS70304", 4, 0, ":AUToscale", 3e9),
        (RigolDS80000, "DS81304", 4, 0, ":AUToset", 13e9),
        (RigolDS1000ZE, "DS1202Z-E", 2, 0, ":AUToscale", 200e6),
    ],
)
async def test_identification(cls, model, analog, digital, autoset, bandwidth):
    scope, inst = make_driver(cls, model)
    await scope.connect()
    assert scope.connected is True

    info = await scope.get_info()
    assert info.type == EquipmentType.OSCILLOSCOPE
    assert info.id.startswith("scope_")
    assert info.manufacturer == "RIGOL TECHNOLOGIES"
    assert info.model == model
    assert info.serial_number == ScriptedScope.SERIAL
    assert info.connection_type == ConnectionType.USB
    assert scope.num_channels == analog
    assert scope.num_digital == digital

    status = await scope.get_status()
    assert status.connected is True
    assert status.firmware_version == ScriptedScope.FIRMWARE
    caps = status.capabilities
    assert caps["num_channels"] == analog
    assert caps["num_digital"] == digital
    assert caps["autoset_command"] == autoset
    assert caps["bandwidth"] == pytest.approx(bandwidth)
    assert caps["supports_acquisition"] is True
    assert caps["trigger_status"] == "RUN"
    assert "VPP" in caps["measurement_items"]


async def test_generic_base_resolves_model_from_idn():
    scope, inst = make_driver(RigolModernScopeBase, "MSO5354")
    await scope.connect()
    assert scope.family.name == "MSO5000"
    assert scope.num_channels == 4 and scope.num_digital == 16
    assert scope.spec.bw_limits == ("OFF", "20M", "100M", "200M")
    await scope.autoscale()
    assert inst.writes[-1] == ":AUToscale"


async def test_unknown_model_falls_back_to_class_defaults():
    scope, _ = make_driver(RigolDHO800, "DHO888")  # unknown DHO800-series member
    await scope.connect()
    assert scope.family.name == "DHO800" and scope.num_channels == 4
    scope2, _ = make_driver(RigolMSO5000, "RIGOLTEST2")
    await scope2.connect()
    assert scope2.family.name == "MSO5000"
    assert scope2.num_channels == 2  # guessed from the trailing digit
    assert (await scope2.get_status()).capabilities["model_note"].startswith("Model not in table")


# --------------------------------------------------------------------------- #
# Setters
# --------------------------------------------------------------------------- #


async def test_set_channel():
    scope, inst = make_driver(RigolDHO800, "DHO812")
    await scope.connect()
    result = await scope.set_channel(2, scale=0.5, offset=-0.25, coupling="ac", probe=10,
                                     bandwidth_limit=True, enabled=True, invert=False)
    for expected in (":CHAN2:DISP ON", ":CHAN2:PROB 10", ":CHAN2:COUP AC", ":CHAN2:SCAL 0.5",
                     ":CHAN2:OFFS -0.25", ":CHAN2:BWL 20M", ":CHAN2:INV OFF"):
        assert expected in inst.writes
    assert result == {"channel": 2, "enabled": True, "scale": 0.5, "offset": -0.25,
                      "coupling": "AC", "probe": 10.0, "bandwidth_limit": "20M", "invert": False}
    with pytest.raises(ValueError):
        await scope.set_channel(3, scale=1.0)  # DHO812 has two channels
    with pytest.raises(ValueError):
        await scope.set_channel(1, coupling="HF")
    with pytest.raises(ValueError):
        await scope.set_channel(1, bandwidth_limit="250M")  # not on DHO800
    with pytest.raises(ValueError):
        await scope.set_channel(1, scale=0)

    big, inst2 = make_driver(RigolDHO5000, "DHO5058")
    await big.connect()
    await big.set_channel(8, enabled=True, bandwidth_limit=250e6)
    assert ":CHAN8:BWL 250M" in inst2.writes


async def test_set_timebase():
    scope, inst = make_driver(RigolMSO5000, "MSO5074")
    await scope.connect()
    result = await scope.set_timebase(scale=2e-3, offset=1e-4, mode="yt")
    assert ":TIM:MODE MAIN" in inst.writes
    assert ":TIM:MAIN:SCAL 0.002" in inst.writes
    assert ":TIM:MAIN:OFFS 0.0001" in inst.writes
    assert result == {"scale": pytest.approx(2e-3), "offset": pytest.approx(1e-4), "mode": "MAIN"}
    with pytest.raises(ValueError):
        await scope.set_timebase(scale=-1)
    with pytest.raises(ValueError):
        await scope.set_timebase(mode="SIDEWAYS")


async def test_set_trigger():
    scope, inst = make_driver(RigolMSO5000, "MSO5074")
    await scope.connect()
    result = await scope.set_trigger(source="ch2", level=0.16, slope="rising", mode="edge",
                                     sweep="normal", coupling="dc", holdoff=1e-6, noise_reject=True)
    for expected in (":TRIG:MODE EDGE", ":TRIG:SWE NORMal", ":TRIG:COUP DC", ":TRIG:HOLD 1e-06",
                     ":TRIG:NREJ ON", ":TRIG:EDGE:SOUR CHAN2", ":TRIG:EDGE:SLOP POSitive",
                     ":TRIG:EDGE:LEV 0.16"):
        assert expected in inst.writes
    assert result["source"] == "CHAN2" and result["slope"] == "POS" and result["sweep"] == "NORM"
    assert result["level"] == pytest.approx(0.16) and result["status"] == "RUN"

    await scope.set_trigger(source="ACLine", slope="RFAL")
    assert ":TRIG:EDGE:SOUR ACL" in inst.writes and ":TRIG:EDGE:SLOP RFALl" in inst.writes
    await scope.set_trigger(source="D3")
    assert ":TRIG:EDGE:SOUR D3" in inst.writes
    with pytest.raises(ValueError):
        await scope.set_trigger(source="EXT")  # MSO5000 has no EXT input
    with pytest.raises(ValueError):
        await scope.set_trigger(slope="diagonal")
    with pytest.raises(ValueError):
        await scope.set_trigger(sweep="TWICE")
    with pytest.raises(ValueError):
        await scope.set_trigger(source="D16")

    # DHO802 has EXT, no digital; DS1000Z-E spells AC line "AC"
    dho, inst_dho = make_driver(RigolDHO800, "DHO802")
    await dho.connect()
    await dho.set_trigger(source="EXT", mode="pulse")
    assert ":TRIG:EDGE:SOUR EXT" in inst_dho.writes and ":TRIG:MODE PULS" in inst_dho.writes
    with pytest.raises(ValueError):
        await dho.set_trigger(source="D0")
    ds, inst_ds = make_driver(RigolDS1000ZE, "DS1202Z-E")
    await ds.connect()
    await ds.set_trigger(source="ACLINE")
    assert ":TRIG:EDGE:SOUR AC" in inst_ds.writes


async def test_run_control_and_autoset_vs_autoscale():
    cases = [
        (RigolDHO800, "DHO924S", ":AUToset"),
        (RigolDHO1000, "DHO4204", ":AUToset"),
        (RigolMHO900, "MHO954", ":AUToset"),
        (RigolMSO5000, "MSO5104", ":AUToscale"),
        (RigolMSO7000, "MSO7024", ":AUToscale"),
        (RigolMSO8000, "MSO8064", ":AUToscale"),
        (RigolDS8000R, "DS8204-R", ":AUToscale"),
        (RigolDS4000, "DS4014E", ":AUToscale"),
        (RigolDS6000, "DS6104", ":AUToscale"),
        (RigolDS70000, "DS70504", ":AUToscale"),
        (RigolDS80000, "DS80604", ":AUToset"),
        (RigolDS1000ZE, "DS1102Z-E", ":AUToscale"),
    ]
    for cls, model, expected in cases:
        scope, inst = make_driver(cls, model)
        await scope.connect()
        assert await scope.autoscale() == expected
        assert inst.writes[-1] == expected, model
        await scope.run()
        assert await scope.get_trigger_status() == "RUN"
        await scope.single()
        assert await scope.get_trigger_status() == "WAIT"
        await scope.stop()
        assert await scope.get_trigger_status() == "STOP"
        await scope.force_trigger()
        assert ":TFOR" in inst.writes


async def test_acquisition():
    scope, inst = make_driver(RigolDHO800, "DHO924S")
    await scope.connect()
    result = await scope.set_acquisition(mode="average", averages=16, memory_depth=1e6)
    assert ":ACQ:TYPE AVERages" in inst.writes
    assert ":ACQ:AVER 16" in inst.writes
    assert ":ACQ:MDEP 1000000" in inst.writes
    assert result == {"mode": "AVER", "memory_depth": pytest.approx(1e6),
                      "sample_rate": pytest.approx(1e9), "averages": 16}
    result = await scope.set_acquisition(mode="ultra", memory_depth="AUTO")
    assert ":ACQ:TYPE ULTRa" in inst.writes and result["memory_depth"] == "AUTO"
    with pytest.raises(ValueError):
        await scope.set_acquisition(averages=3)
    with pytest.raises(ValueError):
        await scope.set_acquisition(memory_depth=1e9)  # DHO900 tops out at 50 Mpts
    mso, _ = make_driver(RigolMSO5000, "MSO5074")
    await mso.connect()
    with pytest.raises(ValueError):
        await mso.set_acquisition(mode="ULTRa")  # no UltraAcquire on MSO5000
    assert (await mso.set_acquisition(mode="hres"))["mode"] == "HRES"
    assert RigolModernScopeBase._parse_depth("1M") == pytest.approx(1e6)
    assert RigolModernScopeBase._parse_depth("2.5e7") == pytest.approx(25e6)


# --------------------------------------------------------------------------- #
# Waveforms
# --------------------------------------------------------------------------- #


async def test_waveform_normal_mode_decode():
    scope, inst = make_driver(RigolDHO800, "DHO924S")
    await scope.connect()
    meta = await scope.get_waveform(channel=1)
    assert isinstance(meta, WaveformData)
    assert ":WAV:SOUR CHAN1" in inst.writes and ":WAV:MODE NORMal" in inst.writes
    assert ":WAV:FORM BYTE" in inst.writes and ":WAV:PRE?" in inst.queries
    assert meta.channel == 1 and meta.num_samples == 1000
    assert meta.sample_rate == pytest.approx(1e8)  # 1 / XINCrement
    assert meta.time_scale == pytest.approx(1e-6)
    assert meta.voltage_scale == pytest.approx(1.0) and meta.voltage_offset == 0.0
    assert meta.data_id.startswith("waveform_")
    assert meta.equipment_id == scope.cached_info.id
    # Known bytes -> volts: (code - YORigin - YREFerence) * YINCrement with 0 / 128 / 4e-3
    volts = scope.last_waveform["voltage"]
    assert len(volts) == 1000
    assert volts[0] == pytest.approx(-0.512)
    assert volts[128] == pytest.approx(0.0)
    assert volts[255] == pytest.approx(0.508)
    times = scope.last_waveform["time"]
    assert times[0] == pytest.approx(-5e-6) and times[1] - times[0] == pytest.approx(1e-8)
    # RUN state must not be disturbed by a screen read
    assert ":STOP" not in inst.writes

    raw = await scope.get_waveform_raw(channel="CH1")
    assert raw == inst.screen_payload()
    data = await scope.get_waveform_data(channel=1)
    assert data["num_samples"] == 1000 and data["voltage"][255] == pytest.approx(0.508)
    assert data["x_increment"] == pytest.approx(1e-8)
    with pytest.raises(ValueError):
        await scope.get_waveform(channel=5)
    with pytest.raises(ValueError):
        await scope.get_waveform(channel=1, mode="SIDEWAYS")


async def test_waveform_raw_mode_chunked_start_stop_flow():
    scope, inst = make_driver(RigolMSO5000, "MSO5074", memory_depth=6000)
    await scope.connect()
    scope.family = dataclasses.replace(scope.family, max_points_per_read=2500)
    meta, times, volts = await scope.capture_waveform(channel=2, mode="RAW")
    # Memory reads need STOP; the driver stops the scope first.
    assert inst.writes.index(":STOP") < inst.writes.index(":WAV:MODE RAW")
    assert ":WAV:SOUR CHAN2" in inst.writes
    assert [w for w in inst.writes if w.startswith(":WAV:STAR")] == [":WAV:STAR 1", ":WAV:STAR 2501", ":WAV:STAR 5001"]
    assert [w for w in inst.writes if w.startswith(":WAV:STOP")] == [":WAV:STOP 2500", ":WAV:STOP 5000", ":WAV:STOP 6000"]
    assert inst.queries.count(":WAV:DATA?") == 3
    assert meta.num_samples == 6000 and len(volts) == 6000
    assert meta.sample_rate == pytest.approx(1e9)
    expected = np.array([inst.raw_sample(i) for i in range(1, 6001)], dtype=float)
    assert np.allclose(volts, (expected - 128) * 4e-3)
    assert scope.last_waveform["raw"] == bytes(inst.raw_sample(i) for i in range(1, 6001))
    # Explicit point limit reads only the first window
    n_before = inst.queries.count(":WAV:DATA?")
    meta2, _, volts2 = await scope.capture_waveform(channel=2, mode="RAW", points=1000)
    assert meta2.num_samples == 1000 and len(volts2) == 1000
    assert ":WAV:STOP 1000" in inst.writes
    assert inst.queries.count(":WAV:DATA?") == n_before + 1


async def test_waveform_raw_mode_status_flow_ds6000():
    scope, inst = make_driver(RigolDS6000, "DS6104", memory_depth=6000)
    await scope.connect()
    scope.family = dataclasses.replace(scope.family, max_points_per_read=2500)
    meta, _, volts = await scope.capture_waveform(channel=1, mode="RAW")
    for expected in (":STOP", ":WAV:POIN 2500", ":WAV:RES", ":WAV:BEG", ":WAV:END"):
        assert expected in inst.writes
    assert not any(w.startswith(":WAV:STAR") for w in inst.writes)
    assert inst.queries.count(":WAV:STAT?") == 3 and inst.queries.count(":WAV:DATA?") == 3
    assert meta.num_samples == 6000
    assert volts[6] == pytest.approx((inst.raw_sample(7) - 128) * 4e-3)


# --------------------------------------------------------------------------- #
# Measurements / acquisition hook
# --------------------------------------------------------------------------- #


async def test_get_measurements_stream_dict():
    scope, inst = make_driver(RigolDHO800, "DHO924S")
    await scope.connect()
    meas = await scope.get_measurements(channel=1)
    assert ":MEAS:ITEM? VPP,CHAN1" in inst.queries
    assert ":MEAS:ITEM? FREQuency,CHAN1" in inst.queries
    assert meas["vpp"] == pytest.approx(3.2) and meas["vmax"] == pytest.approx(1.6)
    assert meas["vmin"] == pytest.approx(-1.6) and meas["vavg"] == pytest.approx(0.01)
    assert meas["vrms"] == pytest.approx(1.131) and meas["freq"] == pytest.approx(1000.0)
    assert meas["period"] == pytest.approx(1e-3)
    assert meas["rise_time"] == pytest.approx(1.2e-6) and meas["fall_time"] == pytest.approx(1.3e-6)
    assert meas["positive_width"] == pytest.approx(5e-4) and meas["duty_cycle"] == pytest.approx(0.5)
    with pytest.raises(ValueError):
        await scope.get_measurements(channel=9)


async def test_get_measurement_channel_semantics():
    scope, inst = make_driver(RigolDHO800, "DHO924S")
    await scope.connect()
    dc = await scope.get_measurement("CH1")  # bare channel = VAVG
    assert inst.queries[-1] == ":MEAS:ITEM? VAVG,CHAN1"
    assert dc == {"value": pytest.approx(0.01), "unit": "V", "item": "VAVG", "source": "CHAN1", "valid": True}
    freq = await scope.get_measurement("2:FREQ")
    assert inst.queries[-1] == ":MEAS:ITEM? FREQuency,CHAN2"
    assert freq["value"] == pytest.approx(1000.0) and freq["unit"] == "Hz"
    rise = await scope.get_measurement("chan1.rise_time")
    assert rise["item"] == "RISE" and rise["unit"] == "s"
    duty = await scope.get_measurement("CH1:DUTY")
    assert duty["unit"] == "ratio"
    invalid = await scope.get_measurement("CH2:VPP")  # scripted 9.9E37
    assert math.isnan(invalid["value"]) and invalid["valid"] is False
    digital = await scope.get_measurement("D3:FREQ")
    assert inst.queries[-1] == ":MEAS:ITEM? FREQuency,D3"
    math1 = await scope.get_measurement("MATH1:VRMS")
    assert inst.queries[-1] == ":MEAS:ITEM? VRMS,MATH1" and math1["source"] == "MATH1"
    with pytest.raises(ValueError):
        await scope.get_measurement("CH7:VPP")
    with pytest.raises(ValueError):
        await scope.get_measurement("CH1:WOBBLE")


async def test_legacy_measure_style_ds4000():
    scope, inst = make_driver(RigolDS4000, "DS4024E")
    await scope.connect()
    vpp = await scope.get_measurement("CH1:VPP")
    assert inst.queries[-1] == ":MEAS:VPP? CHAN1"
    assert vpp["value"] == pytest.approx(3.2)
    meas = await scope.get_measurements(1)
    assert ":MEAS:FREQuency? CHAN1" in inst.queries and meas["freq"] == pytest.approx(1000.0)
    assert not any(q.startswith(":MEAS:ITEM") for q in inst.queries)


# --------------------------------------------------------------------------- #
# Digital channels, screenshots, state, dispatch
# --------------------------------------------------------------------------- #


async def test_digital_channels_by_family():
    mso, inst = make_driver(RigolMSO5000, "MSO5074")
    await mso.connect()
    result = await mso.set_digital(True, channels=["D0", "d3"])
    assert ":LA:STAT ON" in inst.writes and ":LA:DIG:DISP D3,ON" in inst.writes
    assert result["enabled"] is True and result["channels"]["D3"] is True and result["channels"]["D1"] is False
    assert await mso.set_digital_threshold(2, 3.3) == pytest.approx(3.3)
    assert ":LA:POD2:THR 3.3" in inst.writes

    dho, inst_dho = make_driver(RigolDHO800, "DHO924S")
    await dho.connect()
    await dho.set_digital(True, channels=["D5"])
    assert ":LA:ENAB ON" in inst_dho.writes and ":LA:DIG:ENAB D5,ON" in inst_dho.writes

    plain, _ = make_driver(RigolDHO800, "DHO804")
    await plain.connect()
    with pytest.raises(ValueError):
        await plain.set_digital(True)
    with pytest.raises(ValueError):
        await mso.set_digital_threshold(3, 1.0)


async def test_screenshot_by_family():
    dho, inst = make_driver(RigolDHO800, "DHO924S")
    await dho.connect()
    png = await dho.get_screenshot()
    assert inst.queries[-1] == ":DISP:DATA? PNG" and png.startswith(PNG_MAGIC)
    bmp = await dho.get_screenshot(format="bmp")
    assert inst.queries[-1] == ":DISP:DATA? BMP" and bmp.startswith(b"BM")
    with pytest.raises(ValueError):
        await dho.get_screenshot(format="gif")

    mso, inst_mso = make_driver(RigolMSO5000, "MSO5074")
    await mso.connect()
    assert (await mso.get_screenshot()).startswith(b"BM") and inst_mso.queries[-1] == ":DISP:DATA?"

    mso8, inst_8 = make_driver(RigolMSO8000, "MSO8204")
    await mso8.connect()
    assert (await mso8.get_screenshot()).startswith(PNG_MAGIC) and inst_8.queries[-1] == ":DISP:DATA?"

    ds, inst_ds = make_driver(RigolDS1000ZE, "DS1202Z-E")
    await ds.connect()
    assert (await ds.get_screenshot()).startswith(PNG_MAGIC)
    assert inst_ds.queries[-1] == ":DISP:DATA? ON,OFF,PNG"


async def test_execute_command_dispatch_state_and_errors():
    scope, inst = make_driver(RigolMSO5000, "MSO5074")
    await scope.connect()
    readings = await scope.execute_command("get_readings", {"channel": 1})
    assert readings["vpp"] == pytest.approx(3.2) and readings["channel"] == 1
    meta = await scope.execute_command("get_waveform", {"channel": 1})
    assert isinstance(meta, WaveformData) and meta.num_samples == 1000
    raw = await scope.execute_command("get_waveform_raw", {"channel": 1})
    assert isinstance(raw, bytes) and len(raw) == 1000
    assert (await scope.execute_command("get_measurement", {"channel": "CH1:VRMS"}))["value"] == pytest.approx(1.131)
    assert (await scope.execute_command("set_channel", {"channel": 1, "scale": 0.2}))["scale"] == pytest.approx(0.2)
    assert (await scope.execute_command("set_timebase", {"scale": 1e-3}))["scale"] == pytest.approx(1e-3)
    assert (await scope.execute_command("set_trigger", {"source": "CH1", "level": 0.5}))["level"] == pytest.approx(0.5)
    await scope.execute_command("trigger_single", {})
    assert ":SING" in inst.writes
    assert await scope.execute_command("autoscale", {}) == ":AUToscale"

    state = await scope.execute_command("get_state", {})
    assert set(state["channels"]) == {"1", "2", "3", "4"}
    assert state["channels"]["1"]["scale"] == pytest.approx(0.2)
    assert state["timebase"]["scale"] == pytest.approx(1e-3)
    assert state["trigger"]["source"] == "CHAN1" and state["trigger"]["level"] == pytest.approx(0.5)
    assert state["acquisition"]["sample_rate"] == pytest.approx(1e9)
    assert state["digital"]["enabled"] is False

    err = await scope.execute_command("get_error", {})
    assert err["code"] == 0 and err["message"] == "No error"
    assert await scope.execute_command("clear_errors", {}) is True
    with pytest.raises(ValueError):
        await scope.execute_command("levitate", {})


def test_family_table_consistency():
    for name, fam in FAMILIES.items():
        assert fam.name == name
        assert fam.autoset_command in (":AUToset", ":AUToscale")
        assert fam.measure_style in ("ITEM", "LEGACY")
        assert fam.raw_read_flow in ("RANGE", "STATUS")
        assert fam.max_points_per_read > 0
        assert fam.screenshot_query.startswith(":DISP:DATA?")
