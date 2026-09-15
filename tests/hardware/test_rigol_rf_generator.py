"""Tests for the Rigol DSG800 / DSG3000 / DSG3000B / DSG5000 RF generator drivers.

A scripted fake instrument answers the SCPI documented in the four
programming guides. The DSG800 and DSG3000B flavours return "Number+Unit"
strings (``4.00000000MHz``), the DSG3000/DSG5000 flavours plain numbers,
and the DSG5000 flavour requires the ``:RF<n>`` channel node.
"""

import math
import sys
from unittest.mock import MagicMock

import pytest

sys.path.append("..")

from server.equipment.rigol_rf_generator import (DSG_MODELS, RigolDSG800,  # noqa: E402
                                          RigolDSG3000, RigolDSG5000,
                                          RigolDSGBase, level_to_dbm,
                                          lookup_dsg_model, parse_si)
from shared.models.equipment import ConnectionType, EquipmentType  # noqa: E402


class ScriptedDSG:
    """Minimal DSG SCPI simulator covering the four families."""

    def __init__(self, model="DSG830"):
        self.model = model
        self.session = 1
        self.timeout = 10000
        self.writes = []
        self.queries = []
        self.family = (
            "DSG5000" if model.startswith("DSG5") else
            "DSG3000B" if model.endswith("B") or "B-IQ" in model else
            "DSG3000" if model.startswith("DSG3") else "DSG800"
        )
        self.channels = int(model[-1]) if self.family == "DSG5000" else 1
        # per-channel state
        self.st = {ch: self._defaults() for ch in range(1, self.channels + 1)}
        self.unit = "DBM"
        self.alc = "AUTO"
        self.preset_count = 0
        self.rst_count = 0

    @staticmethod
    def _defaults():
        return {
            "FREQ": 3e9, "FREQ:STEP": 100e6, "LEV": -110.0, "LEV:STEP": 10.0, "OUTP": 0, "MOD": 0,
            "FMPM": "PM",
            "AM": {"STAT": 0, "DEPT": 50.0, "FREQ": 10e3, "SOUR": "INT", "WAVE": "SINE"},
            "FM": {"STAT": 0, "DEV": 10e3, "FREQ": 10e3, "SOUR": "INT", "WAVE": "SINE"},
            "PM": {"STAT": 0, "DEV": 1.0, "FREQ": 10e3, "SOUR": "INT", "WAVE": "SINE"},
            "PULM": {"STAT": 0, "PER": 1e-3, "WIDT": 500e-6, "SOUR": "INT", "POL": "NORMAL", "MODE": "SINGLE"},
            "IQ": {"STAT": 0, "MODE": "INT"},
            "SWE": {"STAT": "OFF", "TYPE": "STEP", "MODE": "CONT", "DIR": "FWD", "STAR:FREQ": 100e6,
                    "STOP:FREQ": 3e9, "STAR:LEV": -20.0, "STOP:LEV": 0.0, "POIN": 91, "DWEL": 0.1,
                    "SPAC": "LIN", "SHAP": "RAMP", "EXEC": 0},
            "TRIG": [],
        }

    # -- helpers ----------------------------------------------------------
    def _split(self, c):
        """Return (channel, tokens) for an upper-cased command."""
        toks = [t for t in c.replace("SOURCE:", "").lstrip(":").split(":") if t]
        ch = 1
        if toks and toks[0].startswith("RF") and toks[0][2:].isdigit():
            ch = int(toks[0][2:])
            toks = toks[1:]
            assert self.family == "DSG5000", f"RF<n> node only valid on DSG5000: {c}"
        elif self.family == "DSG5000" and toks and toks[0] not in ("UNIT", "SYSTEM", "TRIGGER", "RFALL"):
            # The DSG5000 accepts the channel-less form for CH1, but the
            # driver is expected to always address a channel explicitly.
            raise AssertionError(f"DSG5000 command without RF<n> node: {c}")
        return ch, toks

    def _num(self, value, unit):
        """Format a number the way the family does."""
        if self.family in ("DSG800", "DSG3000B"):
            if unit == "Hz":
                return f"{value / 1e6:.8f}MHz" if value >= 1e6 else f"{value / 1e3:.5f}kHz"
            if unit == "s":
                return f"{value:.9f}s"
            return f"{value:.2f}"
        if unit == "Hz":
            return f"{value:.0f}"
        return f"{value:g}"

    def close(self):
        pass

    # -- write ------------------------------------------------------------
    def write(self, cmd):
        self.writes.append(cmd)
        c = cmd.strip().upper()
        if c == "*RST":
            assert self.family in ("DSG3000", "DSG5000"), f"*RST not documented on {self.family}"
            self.rst_count += 1
            return
        if c == "*CLS":
            assert self.family in ("DSG3000", "DSG5000")
            return
        if c == "*TRG":
            self.st[1]["TRIG"].append("ALL")
            return
        if c == ":SYSTEM:PRESET":
            self.preset_count += 1
            return
        head, _, arg = c.partition(" ")
        if head.startswith(":UNIT"):
            self.unit = arg
            return
        if head.startswith(":SOURCE:RFALL:OUTPUT"):
            for ch in self.st:
                self.st[ch]["OUTP"] = 1 if arg in ("ON", "1") else 0
            return
        if head.startswith(":TRIGGER"):
            ch, toks = self._split(head[len(":TRIGGER"):])
            self.st[ch]["TRIG"].append(toks[0])
            return
        ch, toks = self._split(head)
        s = self.st[ch]
        key = ":".join(toks)
        if key == "OUTPUT:STATE":
            s["OUTP"] = 1 if arg in ("ON", "1") else 0
        elif key == "FREQUENCY":
            s["FREQ"] = parse_si(arg)
        elif key == "FREQUENCY:STEP":
            assert self.family != "DSG5000"
            s["FREQ:STEP"] = parse_si(arg)
        elif key == "LEVEL":
            s["LEV"] = level_to_dbm(*self._level_arg(arg))
        elif key == "LEVEL:STEP":
            assert self.family != "DSG5000"
            s["LEV:STEP"] = float(arg)
        elif key == "LEVEL:ALC:MODE":
            assert self.family == "DSG3000", "ALC only on DSG3000"
            self.alc = arg
        elif key == "MODULATION:STATE":
            s["MOD"] = 1 if arg in ("ON", "1") else 0
        elif key == "FMPM:TYPE":
            assert self.family != "DSG5000"
            s["FMPM"] = arg
        elif toks[0] in ("AM", "FM", "PM", "PULM", "IQ"):
            self._mod_write(s[toks[0]], toks[0], toks[1:], arg)
        elif toks[0] == "SWEEP":
            self._sweep_write(s["SWE"], toks[1:], arg)
        elif toks[0] == "LFOUTPUT":
            assert self.family != "DSG5000"
        else:
            raise AssertionError(f"Unscripted write: {cmd}")

    @staticmethod
    def _level_arg(arg):
        for suffix, unit in (("DBMV", "dBmV"), ("DBUV", "dBuV"), ("DBM", "dBm"), ("V", "V"), ("W", "W")):
            if arg.endswith(suffix):
                return float(arg[: -len(suffix)]), unit
        return float(arg), "dBm"

    def _mod_write(self, m, root, sub, arg):
        key = ":".join(sub)
        if root == "IQ":
            if key == "MODE:STATE":
                m["STAT"] = 1 if arg in ("ON", "1") else 0
            elif key == "MODE":
                m["MODE"] = arg[:3]
            else:
                raise AssertionError(f"Unscripted IQ write {key}")
            return
        if key == "STATE":
            m["STAT"] = 1 if arg in ("ON", "1") else 0
        elif key == "SOURCE":
            m["SOUR"] = arg[:3]
        elif key == "WAVEFORM":
            m["WAVE"] = arg
        elif key == "FREQUENCY" and root != "PULM":
            m["FREQ"] = parse_si(arg)
        elif key == "DEPTH" and root == "AM":
            m["DEPT"] = float(arg)
        elif key == "DEVIATION" and root in ("FM", "PM"):
            m["DEV"] = parse_si(arg)
        elif key == "PERIOD" and root == "PULM":
            m["PER"] = parse_si(arg)
        elif key == "WIDTH" and root == "PULM":
            m["WIDT"] = parse_si(arg)
        elif key == "POLARITY" and root == "PULM":
            m["POL"] = "NORMAL" if arg.startswith("NORM") else "INVERSE"
        elif key == "MODE" and root == "PULM":
            m["MODE"] = "SINGLE" if arg.startswith("SING") else "TRAIN"
        else:
            raise AssertionError(f"Unscripted {root} write {key}")

    def _sweep_write(self, sw, sub, arg):
        key = ":".join(sub)
        if key == "STATE":
            sw["STAT"] = {"OFF": "OFF", "FREQUENCY": "FREQ", "LEVEL": "LEV", "LEVEL,FREQUENCY": "LEV,FREQ"}[arg]
        elif key == "TYPE":
            sw["TYPE"] = arg
        elif key == "MODE":
            sw["MODE"] = arg[:4]
        elif key == "DIRECTION":
            sw["DIR"] = arg
        elif key == "EXECUTE":
            sw["EXEC"] += 1
        elif key == "STEP:START:FREQUENCY":
            sw["STAR:FREQ"] = parse_si(arg)
        elif key == "STEP:STOP:FREQUENCY":
            sw["STOP:FREQ"] = parse_si(arg)
        elif key == "STEP:START:LEVEL":
            sw["STAR:LEV"] = float(arg)
        elif key == "STEP:STOP:LEVEL":
            sw["STOP:LEV"] = float(arg)
        elif key == "STEP:POINTS":
            sw["POIN"] = int(arg)
        elif key == "STEP:DWELL":
            sw["DWEL"] = parse_si(arg)
        elif key == "STEP:SPACING":
            sw["SPAC"] = arg[:3]
        elif key == "STEP:SHAPE":
            sw["SHAP"] = arg[:3] if arg.startswith("TRI") else "RAMP"
        else:
            raise AssertionError(f"Unscripted SWEep write {key}")

    # -- query ------------------------------------------------------------
    def query(self, cmd):
        self.queries.append(cmd)
        c = cmd.strip().upper()
        if c == "*IDN?":
            if self.family == "DSG5000":
                return f"RIGOL TECHNOLOGIES,{self.model},DSG5A000001,00.00.01"
            return f"Rigol Technologies,{self.model},DSG8A170200001,00.01.01"
        if c == "*OPT?":
            assert self.family == "DSG3000"
            return "IQ-DSG3000,PUG-DSG3000"
        if c == ":SYSTEM:ERROR?":
            raise AssertionError("SYSTem:ERRor? is not documented on any DSG")
        if c.startswith(":UNIT"):
            return self.unit
        c = c[:-1]  # strip '?'
        ch, toks = self._split(c)
        s = self.st[ch]
        key = ":".join(toks)
        if key == "OUTPUT:STATE":
            return str(s["OUTP"])
        if key == "FREQUENCY":
            return self._num(s["FREQ"], "Hz")
        if key == "FREQUENCY:STEP":
            return self._num(s["FREQ:STEP"], "Hz")
        if key == "LEVEL":
            return f"{s['LEV']:.2f}"
        if key == "LEVEL:STEP":
            return f"{s['LEV:STEP']:.2f}"
        if key == "LEVEL:ALC:MODE":
            assert self.family == "DSG3000"
            return self.alc
        if key == "MODULATION:STATE":
            return str(s["MOD"])
        if toks[0] in ("AM", "FM", "PM", "PULM", "IQ"):
            return self._mod_query(s[toks[0]], toks[0], toks[1:])
        if toks[0] == "SWEEP":
            return self._sweep_query(s["SWE"], toks[1:])
        if toks[0] == "LFOUTPUT":
            return {"STATE": "1", "FREQUENCY": self._num(1e3, "Hz"), "LEVEL": "1.00"}[toks[1]]
        raise AssertionError(f"Unscripted query: {cmd}")

    def _mod_query(self, m, root, sub):
        key = ":".join(sub)
        if root == "IQ":
            return {"MODE:STATE": str(m["STAT"]), "MODE": m["MODE"]}[key]
        if key == "STATE":
            return str(m["STAT"])
        if key == "SOURCE":
            return m["SOUR"]
        if key == "WAVEFORM":
            return m["WAVE"]
        if key == "FREQUENCY":
            return self._num(m["FREQ"], "Hz")
        if key == "DEPTH":
            return f"{m['DEPT']:.2f}"
        if key == "DEVIATION":
            return self._num(m["DEV"], "Hz") if root == "FM" else f"{m['DEV']:.6f}"
        if key == "PERIOD":
            return self._num(m["PER"], "s")
        if key == "WIDTH":
            return self._num(m["WIDT"], "s")
        if key == "POLARITY":
            return m["POL"]
        if key == "MODE":
            return m["MODE"]
        raise AssertionError(f"Unscripted {root} query {key}")

    def _sweep_query(self, sw, sub):
        key = ":".join(sub)
        table = {
            "STATE": sw["STAT"], "TYPE": sw["TYPE"], "MODE": sw["MODE"], "DIRECTION": sw["DIR"],
            "STEP:START:FREQUENCY": self._num(sw["STAR:FREQ"], "Hz"),
            "STEP:STOP:FREQUENCY": self._num(sw["STOP:FREQ"], "Hz"),
            "STEP:START:LEVEL": f"{sw['STAR:LEV']:.2f}", "STEP:STOP:LEVEL": f"{sw['STOP:LEV']:.2f}",
            "STEP:POINTS": str(sw["POIN"]), "STEP:DWELL": self._num(sw["DWEL"], "s"),
            "STEP:SPACING": sw["SPAC"], "STEP:SHAPE": sw["SHAP"],
        }
        if key not in table:
            raise AssertionError(f"Unscripted SWEep query {key}")
        return table[key]


def make_driver(cls, model, resource="USB0::0x1AB1::0x0640::DSG8A170200001::INSTR"):
    inst = ScriptedDSG(model)
    rm = MagicMock()
    rm.open_resource = MagicMock(return_value=inst)
    return cls(rm, resource), inst


# --------------------------------------------------------------------------- #
# Pure helpers / model table
# --------------------------------------------------------------------------- #


def test_parse_si_handles_both_return_formats():
    assert parse_si("4.00000000MHz") == pytest.approx(4e6)
    assert parse_si("4000000") == pytest.approx(4e6)
    assert parse_si("20.00000kHz") == pytest.approx(20e3)
    assert parse_si("10mHz") == pytest.approx(0.01)  # milli, not mega
    assert parse_si("1.000000000s") == pytest.approx(1.0)
    assert parse_si("500us") == pytest.approx(500e-6)
    assert parse_si("-20.00dBm") == pytest.approx(-20.0)
    assert parse_si("281.50mV") == pytest.approx(0.2815)
    assert parse_si("2.00") == pytest.approx(2.0)
    assert parse_si("") is None and parse_si("OFF") is None


def test_level_conversion():
    assert level_to_dbm(0.0, "dBm") == 0.0
    assert level_to_dbm(48.99, "dBmV") == pytest.approx(2.0)
    assert level_to_dbm(108.99, "dBuV") == pytest.approx(2.0)
    assert level_to_dbm(0.2815, "V") == pytest.approx(2.0, abs=0.01)
    assert level_to_dbm(1.58e-3, "W") == pytest.approx(2.0, abs=0.02)
    with pytest.raises(ValueError):
        level_to_dbm(1.0, "furlongs")


def test_model_table():
    assert DSG_MODELS["DSG815"].freq_max == 1.5e9
    assert DSG_MODELS["DSG830"].freq_max == 3e9 and DSG_MODELS["DSG830"].level_max == 20.0
    assert DSG_MODELS["DSG3030"].freq_max == 3e9 and DSG_MODELS["DSG3060"].freq_max == 6e9
    assert DSG_MODELS["DSG3060"].has_alc_command is True
    assert DSG_MODELS["DSG3136B"].freq_max == 13.6e9 and DSG_MODELS["DSG3136B"].has_iq is False
    assert DSG_MODELS["DSG3136B-IQ"].has_iq is True and DSG_MODELS["DSG3065B-IQ"].freq_max == 6.5e9
    assert DSG_MODELS["DSG5208"].channels == 8 and DSG_MODELS["DSG5208"].freq_max == 20e9
    assert DSG_MODELS["DSG5122"].channels == 2 and DSG_MODELS["DSG5122"].freq_max == 12e9
    assert DSG_MODELS["DSG5208"].level_min == -30.0 and DSG_MODELS["DSG5208"].has_iq is False
    assert lookup_dsg_model("dsg3136b-iq").model == "DSG3136B-IQ"
    assert lookup_dsg_model("DSG830-PUM").model == "DSG830"
    assert lookup_dsg_model("DSG9999") is None
    for spec in DSG_MODELS.values():
        assert spec.source  # every row cites where it came from


# --------------------------------------------------------------------------- #
# Identification
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cls,model,fmax,lmin,lmax,family",
    [
        (RigolDSG800, "DSG815", 1.5e9, -110.0, 20.0, "DSG800"),
        (RigolDSG800, "DSG830", 3e9, -110.0, 20.0, "DSG800"),
        (RigolDSG3000, "DSG3030", 3e9, -140.0, 25.0, "DSG3000"),
        (RigolDSG3000, "DSG3060", 6e9, -140.0, 25.0, "DSG3000"),
        (RigolDSG3000, "DSG3065B", 6.5e9, -130.0, 27.0, "DSG3000B"),
        (RigolDSG3000, "DSG3136B-IQ", 13.6e9, -130.0, 27.0, "DSG3000B"),
        (RigolDSG5000, "DSG5204", 20e9, -30.0, 25.0, "DSG5000"),
        (RigolDSG5000, "DSG5128", 12e9, -30.0, 25.0, "DSG5000"),
    ],
)
async def test_identification(cls, model, fmax, lmin, lmax, family):
    gen, inst = make_driver(cls, model)
    await gen.connect()
    assert gen.connected is True
    info = await gen.get_info()
    assert info.type == EquipmentType.RF_SIGNAL_GENERATOR
    assert info.id.startswith("rfgen_")
    assert info.model == model
    assert info.connection_type == ConnectionType.USB
    assert info.serial_number in ("DSG8A170200001", "DSG5A000001")
    status = await gen.get_status()
    assert status.connected is True
    caps = status.capabilities
    assert caps["family"] == family
    assert caps["frequency_min"] == 9e3 and caps["frequency_max"] == fmax
    assert caps["level_min_dbm"] == lmin and caps["level_max_dbm"] == lmax
    assert caps["output_enabled"] is False
    assert caps["supports_acquisition"] is True
    assert gen.spec.model == model


@pytest.mark.asyncio
async def test_unknown_model_keeps_default_spec():
    gen, inst = make_driver(RigolDSG800, "DSG8XX")
    await gen.connect()
    assert gen.model == "DSG8XX" and gen.spec.model == "DSG830"


@pytest.mark.asyncio
async def test_subclasses_share_base():
    for cls in (RigolDSG800, RigolDSG3000, RigolDSG5000):
        assert issubclass(cls, RigolDSGBase)


# --------------------------------------------------------------------------- #
# Frequency / level / output
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_frequency_and_level_dsg800():
    gen, inst = make_driver(RigolDSG800, "DSG830")
    await gen.connect()
    assert await gen.set_frequency(4e6) == pytest.approx(4e6)
    assert ":SOURce:FREQuency 4000000" in inst.writes
    assert await gen.get_frequency() == pytest.approx(4e6)  # parsed from "4.00000000MHz"
    assert await gen.set_level(2.0) == pytest.approx(2.0)
    assert ":SOURce:LEVel 2.00" in inst.writes
    assert await gen.set_frequency_step(3e3) == pytest.approx(3e3)
    assert await gen.set_level_step(20) == pytest.approx(20.0)
    with pytest.raises(ValueError):
        await gen.set_frequency(3.1e9)  # DSG830 stops at 3 GHz
    with pytest.raises(ValueError):
        await gen.set_frequency(1e3)
    with pytest.raises(ValueError):
        await gen.set_level(21.0)
    with pytest.raises(ValueError):
        await gen.set_level(-111.0)
    with pytest.raises(ValueError):
        await gen.set_frequency(1e9, channel=2)  # single channel


@pytest.mark.asyncio
async def test_frequency_limit_depends_on_model():
    dsg815, _ = make_driver(RigolDSG800, "DSG815")
    await dsg815.connect()
    with pytest.raises(ValueError):
        await dsg815.set_frequency(2e9)
    dsg3060, i = make_driver(RigolDSG3000, "DSG3060")
    await dsg3060.connect()
    assert await dsg3060.set_frequency(5.5e9) == pytest.approx(5.5e9)  # plain-number response
    assert await dsg3060.set_level(-135.0) == pytest.approx(-135.0)
    dsg3136, _ = make_driver(RigolDSG3000, "DSG3136B")
    await dsg3136.connect()
    assert await dsg3136.set_frequency(13.6e9) == pytest.approx(13.6e9)
    assert await dsg3136.set_level(27.0) == pytest.approx(27.0)


@pytest.mark.asyncio
async def test_level_units():
    gen, inst = make_driver(RigolDSG800, "DSG830")
    await gen.connect()
    lvl = await gen.set_level(48.99, unit="dBmV")
    assert inst.writes[-1] == ":SOURce:LEVel 48.99dBmV"
    assert lvl == pytest.approx(2.0, abs=0.01)
    lvl = await gen.set_level(0.2815, unit="V")
    assert inst.writes[-1] == ":SOURce:LEVel 0.2815V"
    assert lvl == pytest.approx(2.0, abs=0.02)
    with pytest.raises(ValueError):
        await gen.set_level(10.0, unit="W")  # +40 dBm, out of range
    assert await gen.set_level_unit("dBuV") == "dBuV"
    assert ":UNIT:POWer DBUV" in inst.writes
    assert await gen.get_level_unit() == "dBuV"
    with pytest.raises(ValueError):
        await gen.set_level_unit("furlongs")


@pytest.mark.asyncio
async def test_output_switch():
    gen, inst = make_driver(RigolDSG800, "DSG830")
    await gen.connect()
    assert await gen.set_output(True) is True
    assert ":OUTPut:STATe ON" in inst.writes
    assert await gen.get_output() is True
    assert await gen.set_output(False) is False
    assert ":OUTPut:STATe OFF" in inst.writes
    assert (await gen.set_all_outputs(True)) == {1: True}


@pytest.mark.asyncio
async def test_alc_only_on_dsg3000():
    dsg3060, inst = make_driver(RigolDSG3000, "DSG3060")
    await dsg3060.connect()
    assert await dsg3060.set_alc(False) == "OFF"
    assert ":SOURce:LEVel:ALC:MODE OFF" in inst.writes
    assert await dsg3060.set_alc(mode="auto") == "AUTO"
    with pytest.raises(ValueError):
        await dsg3060.set_alc(mode="MAYBE")
    dsg830, _ = make_driver(RigolDSG800, "DSG830")
    await dsg830.connect()
    with pytest.raises(ValueError):
        await dsg830.set_alc(True)
    assert await dsg830.get_alc() is None
    dsg3136b, _ = make_driver(RigolDSG3000, "DSG3136B")
    await dsg3136b.connect()
    assert await dsg3136b.get_alc() is None


# --------------------------------------------------------------------------- #
# Modulation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_am_modulation():
    gen, inst = make_driver(RigolDSG800, "DSG830")
    await gen.connect()
    am = await gen.set_modulation("AM", True, depth=80, frequency=20e3, source="INT", waveform="square")
    assert ":SOURce:AM:DEPTh 80" in inst.writes
    assert ":SOURce:AM:FREQuency 20000" in inst.writes
    assert ":SOURce:AM:SOURce INTernal" in inst.writes
    assert ":SOURce:AM:WAVEform SQUA" in inst.writes
    assert ":SOURce:AM:STATe ON" in inst.writes
    assert ":SOURce:MODulation:STATe ON" in inst.writes  # master switch follows
    assert am["enabled"] is True and am["depth"] == 80.0
    assert am["frequency"] == pytest.approx(20e3)  # parsed from "20.00000kHz"
    assert am["waveform"] == "SQUA" and am["source"] == "INT"
    n = inst.writes.count(":SOURce:MODulation:STATe OFF")
    await gen.set_modulation("AM", False)
    assert ":SOURce:AM:STATe OFF" in inst.writes
    assert inst.writes.count(":SOURce:MODulation:STATe OFF") == n  # master left alone when disabling
    with pytest.raises(ValueError):
        await gen.set_modulation("AM", True, depth=150)
    with pytest.raises(ValueError):
        await gen.set_modulation("AM", True, colour="blue")
    with pytest.raises(ValueError):
        await gen.set_modulation("QAM", True)


@pytest.mark.asyncio
async def test_fm_pm_and_fmpm_type():
    gen, inst = make_driver(RigolDSG800, "DSG830")
    await gen.connect()
    fm = await gen.set_modulation("FM", True, deviation=20e3, frequency=1e3)
    assert ":SOURce:FMPM:TYPE FM" in inst.writes
    assert ":SOURce:FM:DEViation 20000" in inst.writes
    assert fm["deviation"] == pytest.approx(20e3) and fm["enabled"] is True
    pm = await gen.set_modulation("PM", True, deviation=2.0)
    assert ":SOURce:FMPM:TYPE PM" in inst.writes
    assert ":SOURce:PM:DEViation 2" in inst.writes
    assert pm["deviation"] == pytest.approx(2.0)
    # DSG5000 has no FMPM:TYPE and addresses channels
    d5, i5 = make_driver(RigolDSG5000, "DSG5204")
    await d5.connect()
    await d5.set_modulation("FM", True, deviation=5e3, channel=3)
    assert not any("FMPM" in w for w in i5.writes)
    assert ":SOURce:RF3:FM:DEViation 5000" in i5.writes
    assert ":SOURce:RF3:MODulation:STATe ON" in i5.writes


@pytest.mark.asyncio
async def test_pulse_and_iq_availability():
    gen, inst = make_driver(RigolDSG800, "DSG830")
    await gen.connect()
    pulse = await gen.set_modulation("PULSE", True, period=1e-3, width=200e-6, polarity="inverse", mode="single")
    assert ":SOURce:PULM:PERiod 0.001" in inst.writes
    assert ":SOURce:PULM:WIDTh 0.0002" in inst.writes
    assert ":SOURce:PULM:POLarity INVerse" in inst.writes
    assert ":SOURce:PULM:MODE SINGle" in inst.writes
    assert pulse["period"] == pytest.approx(1e-3)  # parsed from "0.001000000s"
    assert pulse["width"] == pytest.approx(200e-6) and pulse["polarity"] == "INVERSE"
    iq = await gen.set_modulation("IQ", True, source="EXT")
    assert ":SOURce:IQ:MODe EXTernal" in inst.writes
    assert ":SOURce:IQ:MODe:STATe ON" in inst.writes
    assert iq["enabled"] is True and iq["source"] == "EXT"
    with pytest.raises(ValueError):
        await gen.set_modulation("PULSE", True, period=1e-9)
    # No IQ on a DSG3136B (without -IQ) or any DSG5000
    b, _ = make_driver(RigolDSG3000, "DSG3136B")
    await b.connect()
    with pytest.raises(ValueError):
        await b.set_modulation("IQ", True)
    biq, _ = make_driver(RigolDSG3000, "DSG3136B-IQ")
    await biq.connect()
    assert (await biq.set_modulation("IQ", True))["enabled"] is True
    d5, _ = make_driver(RigolDSG5000, "DSG5202")
    await d5.connect()
    with pytest.raises(ValueError):
        await d5.set_modulation("IQ", True)


# --------------------------------------------------------------------------- #
# Sweep / trigger
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_sweep_configuration():
    gen, inst = make_driver(RigolDSG800, "DSG830")
    await gen.connect()
    sw = await gen.set_sweep(
        "FREQ", start_frequency=100e6, stop_frequency=1e9, points=11, dwell=0.05,
        sweep_type="STEP", spacing="LOG", shape="TRIANGLE", direction="FWD", continuous=False,
    )
    assert ":SOURce:SWEep:STEP:STARt:FREQuency 100000000" in inst.writes
    assert ":SOURce:SWEep:STEP:STOP:FREQuency 1000000000" in inst.writes
    assert ":SOURce:SWEep:STEP:POINts 11" in inst.writes
    assert ":SOURce:SWEep:STEP:DWELl 0.05" in inst.writes
    assert ":SOURce:SWEep:STEP:SPACing LOGarithmic" in inst.writes
    assert ":SOURce:SWEep:STEP:SHAPe TRIangle" in inst.writes
    assert ":SOURce:SWEep:MODE SINGle" in inst.writes
    assert inst.writes[-1] == ":SOURce:SWEep:STATe FREQuency"
    assert sw["enabled"] is True and sw["state"] == "FREQ"
    assert sw["start_frequency"] == pytest.approx(100e6) and sw["stop_frequency"] == pytest.approx(1e9)
    assert sw["points"] == 11 and sw["dwell"] == pytest.approx(0.05)
    assert sw["spacing"] == "LOG" and sw["shape"] == "TRI" and sw["mode"] == "SING"
    both = await gen.set_sweep("BOTH", start_level=-30, stop_level=0)
    assert inst.writes[-1] == ":SOURce:SWEep:STATe LEVel,FREQuency"
    assert both["start_level"] == -30.0 and both["stop_level"] == 0.0
    off = await gen.set_sweep("OFF")
    assert off["enabled"] is False
    await gen.execute_sweep()
    assert ":SOURce:SWEep:EXECute" in inst.writes
    await gen.trigger("SWEEP")
    assert ":TRIGger:SWEep:IMMediate" in inst.writes
    await gen.trigger("PULSE")
    assert ":TRIGger:PULSe:IMMediate" in inst.writes
    await gen.trigger("ALL")
    assert "*TRG" in inst.writes
    with pytest.raises(ValueError):
        await gen.set_sweep("FREQ", stop_frequency=4e9)
    with pytest.raises(ValueError):
        await gen.set_sweep("FREQ", points=1)
    with pytest.raises(ValueError):
        await gen.set_sweep("SIDEWAYS")


# --------------------------------------------------------------------------- #
# Multi-channel DSG5000
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_dsg5000_channels():
    gen, inst = make_driver(RigolDSG5000, "DSG5204")
    await gen.connect()
    assert await gen.set_frequency(1e9, channel=2) == pytest.approx(1e9)
    assert ":SOURce:RF2:FREQuency 1000000000" in inst.writes
    assert await gen.set_level(-20, channel=2) == pytest.approx(-20.0)
    assert ":SOURce:RF2:LEVel -20.00" in inst.writes
    assert await gen.set_output(True, channel=2) is True
    assert ":RF2:OUTPut:STATe ON" in inst.writes
    assert await gen.get_output(1) is False
    assert await gen.set_level_unit("V", channel=2) == "V"
    assert ":UNIT:RF2:POWer V" in inst.writes
    all_on = await gen.set_all_outputs(True)
    assert ":SOURce:RFALl:OUTPut:STATe ON" in inst.writes
    assert all_on == {1: True, 2: True, 3: True, 4: True}
    with pytest.raises(ValueError):
        await gen.set_frequency(1e9, channel=5)  # DSG5204 has 4 channels
    with pytest.raises(ValueError):
        await gen.set_frequency(21e9, channel=1)
    with pytest.raises(ValueError):
        await gen.set_level(-31, channel=1)  # DSG5000 floor is -30 dBm
    with pytest.raises(ValueError):
        await gen.set_frequency_step(1e6)  # no :FREQ:STEP on DSG5000
    await gen.trigger("PULSE", channel=2)
    assert ":TRIGger:RF2:PULM:IMMediate" in inst.writes
    meas = await gen.get_measurement("CH2:FREQ")
    assert meas["value"] == pytest.approx(1e9) and meas["channel"] == 2
    readings = await gen.get_readings(channel=2)
    assert readings.frequency == pytest.approx(1e9) and readings.output_enabled is True


# --------------------------------------------------------------------------- #
# Readings / acquisition hooks / dispatch / system
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_readings_reports_active_modulation():
    gen, inst = make_driver(RigolDSG800, "DSG830")
    await gen.connect()
    await gen.set_frequency(100e6)
    await gen.set_level(-10)
    await gen.set_output(True)
    r = await gen.get_readings()
    assert r.frequency == pytest.approx(100e6) and r.level == -10.0 and r.level_unit == "dBm"
    assert r.output_enabled is True and r.modulation_enabled is False and r.modulation_type is None
    assert r.alc_enabled is None  # DSG800 has no ALC command
    await gen.set_modulation("FM", True, deviation=25e3, frequency=1e3)
    r = await gen.get_readings()
    assert r.modulation_enabled is True and r.modulation_type == "FM"
    assert r.modulation_parameters["deviation"] == pytest.approx(25e3)
    assert r.modulation_parameters["frequency"] == pytest.approx(1e3)
    # Master switch off hides the modulation
    await gen.set_modulation_master(False)
    r = await gen.get_readings()
    assert r.modulation_enabled is False
    d3, _ = make_driver(RigolDSG3000, "DSG3060")
    await d3.connect()
    await d3.set_alc(False)
    assert (await d3.get_readings()).alc_enabled is False


@pytest.mark.asyncio
async def test_get_measurement_channels():
    gen, inst = make_driver(RigolDSG800, "DSG830")
    await gen.connect()
    await gen.set_frequency(2.4e9)
    await gen.set_level(-3)
    assert (await gen.get_measurement("FREQ"))["value"] == pytest.approx(2.4e9)
    assert (await gen.get_measurement("frequency"))["unit"] == "Hz"
    lvl = await gen.get_measurement("LEVEL")
    assert lvl["value"] == -3.0 and lvl["unit"] == "dBm"
    assert (await gen.get_measurement("CH1"))["quantity"] == "level"
    assert (await gen.get_measurement(""))["quantity"] == "level"
    assert (await gen.get_measurement("OUTPUT"))["value"] == 0.0
    await gen.set_output(True)
    assert (await gen.get_measurement("CH1:OUTPUT"))["value"] == 1.0
    with pytest.raises(ValueError):
        await gen.get_measurement("PHASE_OF_THE_MOON")
    meas = await gen.get_measurements()
    assert meas["frequency"] == pytest.approx(2.4e9) and meas["level"] == -3.0 and meas["output_enabled"] is True


@pytest.mark.asyncio
async def test_execute_command_dispatch_and_state():
    gen, inst = make_driver(RigolDSG800, "DSG830")
    await gen.connect()
    assert await gen.execute_command("set_frequency", {"frequency": 433.92e6}) == pytest.approx(433.92e6)
    assert await gen.execute_command("set_level", {"level": -30, "unit": "dBm"}) == -30.0
    assert await gen.execute_command("set_output", {"enabled": True}) is True
    am = await gen.execute_command("set_modulation", {"type": "AM", "enabled": True, "depth": 30})
    assert am["depth"] == 30.0
    r = await gen.execute_command("get_readings", {})
    assert r.frequency == pytest.approx(433.92e6) and r.modulation_type == "AM"
    state = await gen.execute_command("get_state", {})
    assert state["frequency"] == pytest.approx(433.92e6) and state["level"] == -30.0
    assert state["output_enabled"] is True and state["modulation_enabled"] is True
    assert state["modulations"]["AM"]["enabled"] is True and state["sweep"]["enabled"] is False
    assert state["alc"] is None
    with pytest.raises(ValueError):
        await gen.execute_command("fly_to_the_moon", {})


@pytest.mark.asyncio
async def test_reset_and_error_handling_per_family():
    dsg830, i8 = make_driver(RigolDSG800, "DSG830")
    await dsg830.connect()
    await dsg830.reset()
    assert i8.preset_count == 1 and i8.rst_count == 0  # no *RST on DSG800
    assert await dsg830.clear_errors() is False  # *CLS not documented
    err = await dsg830.get_error()  # SYSTem:ERRor? undocumented -> soft failure
    assert err["code"] is None
    assert await dsg830.get_options() is None

    dsg3060, i3 = make_driver(RigolDSG3000, "DSG3060")
    await dsg3060.connect()
    await dsg3060.reset()
    assert i3.rst_count == 1 and i3.preset_count == 0
    assert await dsg3060.clear_errors() is True
    assert await dsg3060.get_options() == "IQ-DSG3000,PUG-DSG3000"

    dsg3136b, ib = make_driver(RigolDSG3000, "DSG3136B")
    await dsg3136b.connect()
    await dsg3136b.reset()
    assert ib.preset_count == 1 and ib.rst_count == 0  # DSG3000B documents only *IDN?/*TRG

    dsg5208, i5 = make_driver(RigolDSG5000, "DSG5208")
    await dsg5208.connect()
    await dsg5208.reset()
    assert i5.rst_count == 1


@pytest.mark.asyncio
async def test_lf_output():
    gen, inst = make_driver(RigolDSG800, "DSG830")
    await gen.connect()
    lf = await gen.set_lf_output(True, frequency=1e3, level=1.0, shape="SINE")
    assert ":SOURce:LFOutput:FREQuency 1000" in inst.writes
    assert ":SOURce:LFOutput:STATe ON" in inst.writes
    assert lf["enabled"] is True and lf["frequency"] == pytest.approx(1e3)
    d5, _ = make_driver(RigolDSG5000, "DSG5202")
    await d5.connect()
    with pytest.raises(ValueError):
        await d5.set_lf_output(True)


def test_nan_safe_measurement_shape():
    # get_measurement must always return a float 'value'
    assert isinstance(float("nan"), float) and math.isnan(float("nan"))
