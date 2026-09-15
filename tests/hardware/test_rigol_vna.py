"""Tests for the Rigol VNA drivers (RSA3000N/RSA5000N VNA mode and DNA6000).

Scripted fake instruments answer the SCPI documented in the RSA-N "VNA
Programming Guide" and the "DNA6000 / DNA6000-R Programming Guide"; anything
unscripted raises so the test names the command the driver sent.
"""

import math
import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.path.append("..")

from server.equipment.rigol_vna import (MODEL_TABLE, RigolDNA6000,  # noqa: E402
                                 RigolRSAN, format_complex,
                                 normalize_format, normalize_sparam,
                                 parse_complex_list, parse_float_list)
from shared.models.data import NetworkAnalyzerData  # noqa: E402
from shared.models.equipment import ConnectionType, EquipmentType  # noqa: E402


def _dut(param: str, freqs: np.ndarray) -> np.ndarray:
    """Simulated DUT: -20 dB match on S11/S22, 3rd-order 100 MHz low-pass on S21/S12."""
    if param in ("S11", "S22"):
        return 0.1 * np.exp(-1j * 2 * np.pi * freqs * 1e-9)
    ratio = freqs / 100e6
    return (1.0 / np.sqrt(1.0 + ratio ** 6)) * np.exp(-1j * 3 * np.arctan(ratio))


def _fmt(values: np.ndarray, fmt: str, freqs) -> str:
    prim, sec = format_complex(values, fmt, freqs)
    if sec:
        flat = [x for pair in zip(prim, sec) for x in pair]
    else:
        flat = prim
    return ",".join(f"{v:+.11E}" for v in flat)


class _Scripted:
    def __init__(self, model):
        self.model = model
        self.session = 1
        self.timeout = 10000
        self.writes = []
        self.queries = []
        self.read_termination = None
        self.write_termination = None
        self.start, self.stop, self.points = 10e6, 1e9, 201
        self.power = -5.0
        self.ifbw = 1e3
        self.continuous = "1"

    def close(self):
        pass

    def freqs(self):
        return np.linspace(self.start, self.stop, self.points)


class ScriptedRSAN(_Scripted):
    """RSA5000N/RSA3000N in (or switching to) VNA mode."""

    def __init__(self, model="RSA5065N", mode="VNA"):
        super().__init__(model)
        self.mode = mode
        self.function = "S11"
        self.formats = {n: "MLOG" for n in range(1, 5)}
        self.marker_mode = {n: "OFF" for n in range(1, 9)}
        self.marker_x = {n: 0.0 for n in range(1, 9)}
        self.power = -10.0

    def write(self, cmd):
        self.writes.append(cmd)
        c = cmd.strip().upper()
        head, _, arg = c.partition(" ")
        if head == ":INSTRUMENT:SELECT":
            self.mode = arg
        elif head == ":CONFIGURE":
            self.function = arg
        elif head == ":SENSE:FREQUENCY:START":
            self.start = float(arg)
        elif head == ":SENSE:FREQUENCY:STOP":
            self.stop = float(arg)
        elif head == ":SENSE:FREQUENCY:CENTER":
            span = self.stop - self.start
            self.start, self.stop = float(arg) - span / 2, float(arg) + span / 2
        elif head == ":SENSE:FREQUENCY:SPAN":
            center = (self.start + self.stop) / 2
            self.start, self.stop = center - float(arg) / 2, center + float(arg) / 2
        elif head == ":SENSE:SWEEP:POINTS":
            self.points = int(arg)
        elif head == ":SOURCE:EXTERNAL:POWER:LEVEL:IMMEDIATE:AMPLITUDE":
            self.power = float(arg)
        elif head == ":SENSE:BANDWIDTH:RESOLUTION":
            self.ifbw = float(arg)
        elif head == ":INITIATE:CONTINUOUS":
            self.continuous = "1" if arg in ("ON", "1") else "0"
        elif head == ":INITIATE:IMMEDIATE":
            pass
        elif head.startswith(":DISPLAY:TRACE") and head.endswith(":FORMAT"):
            n = int(head[len(":DISPLAY:TRACE"):-len(":FORMAT")])
            self.formats[n] = {"MLOGARITHMIC": "MLOG", "PHASE": "PHAS", "SWR": "SWR", "SMITH": "SMIT",
                               "REAL": "REAL", "IMAGINARY": "IMAG", "GDELAY": "GDEL", "MLINEAR": "MLIN",
                               "UPHASE": "UPH", "PPHASE": "PPH"}[arg]
        elif head.startswith(":CALCULATE:MARKER") and head.endswith(":MODE"):
            self.marker_mode[int(head[len(":CALCULATE:MARKER"):-len(":MODE")])] = arg[:3]
        elif head.startswith(":CALCULATE:MARKER") and head.endswith(":X"):
            self.marker_x[int(head[len(":CALCULATE:MARKER"):-2])] = float(arg)
        elif head.startswith(":CALCULATE:MARKER") and (head.endswith(":MAXIMUM:MAX") or head.endswith(":MINIMUM")):
            n = int(head.split(":MARKER")[1].split(":")[0])
            data = format_complex(_dut(self.function, self.freqs()), "MLOG")[0]
            idx = int(np.argmax(data)) if "MAX" in head else int(np.argmin(data))
            self.marker_x[n] = float(self.freqs()[idx])
        elif head.startswith(":CALIBRATION:"):
            pass
        elif head == "*RST":
            self.mode = "SA"
        else:
            raise AssertionError(f"Unscripted write: {cmd}")

    def query(self, cmd):
        self.queries.append(cmd)
        c = cmd.strip().upper()
        if c == "*IDN?":
            return f"Rigol Technologies,{self.model},RSA5F222900001,00.03.00"
        if c == ":INSTRUMENT:SELECT?":
            return self.mode
        if c == ":CONFIGURE?":
            return self.function
        if c == ":SENSE:FREQUENCY:START?":
            return f"{self.start:.9e}"
        if c == ":SENSE:FREQUENCY:STOP?":
            return f"{self.stop:.9e}"
        if c == ":SENSE:SWEEP:POINTS?":
            return str(self.points)
        if c == ":SOURCE:EXTERNAL:POWER:LEVEL:IMMEDIATE:AMPLITUDE?":
            return f"{self.power:.9e}"
        if c == ":SENSE:BANDWIDTH:RESOLUTION?":
            return f"{self.ifbw:.9e}"
        if c == ":INITIATE:CONTINUOUS?":
            return self.continuous
        if c.startswith(":DISPLAY:TRACE") and c.endswith(":FORMAT?"):
            return self.formats[int(c[len(":DISPLAY:TRACE"):-len(":FORMAT?")])]
        if c.startswith(":TRACE") and c.endswith(":DATA?"):
            z = _dut(self.function, self.freqs())
            return "".join(f"({v.real:.9E},{v.imag:.9E})" for v in z)
        if c.startswith(":CALCULATE:MARKER") and c.endswith(":MODE?"):
            return self.marker_mode[int(c[len(":CALCULATE:MARKER"):-len(":MODE?")])]
        if c.startswith(":CALCULATE:MARKER") and c.endswith(":X?"):
            return f"{self.marker_x[int(c[len(':CALCULATE:MARKER'):-3])]:.9e}"
        if c.startswith(":CALCULATE:MARKER") and c.endswith(":Y?"):
            n = int(c[len(":CALCULATE:MARKER"):-3])
            z = _dut(self.function, self.freqs())
            y = np.interp(self.marker_x[n], self.freqs(), format_complex(z, "MLOG")[0])
            return f"{y:.2f},-114.36"
        if c == "*OPC?":
            return "1"
        if c == ":SYSTEM:ERROR?":
            return '0,"No error"'
        raise AssertionError(f"Unscripted query: {cmd}")


class ScriptedDNA(_Scripted):
    """DNA6000 / DNA6000-R with one channel and traces 1 (S11) and 2 (S21)."""

    def __init__(self, model="DNA6082"):
        super().__init__(model)
        self.traces = {1: {"param": "S11", "fmt": "MLOG"}, 2: {"param": "S21", "fmt": "MLOG"}}
        self.markers = {}  # (trace, mk) -> {"on": bool, "x": float}
        self.correction = "0"
        self.method = "NONE"
        self.output = "1"
        self.trig_source = "IMM"
        self.form = "ASCII0"
        self.sweep_mode = "CONT"

    def _fmt_word(self, arg):
        return {"MLOGARITHMIC": "MLOG", "MLINEAR": "MLIN", "PHASE": "PHAS", "UPHASE": "UPH",
                "IMAGINARY": "IMAG", "REAL": "REAL", "POLAR": "POL", "SMITH": "SMIT",
                "SADMITTANCE": "SADM", "SWR": "SWR", "GDELAY": "GDEL", "PPHASE": "PPH"}[arg]

    def write(self, cmd):
        self.writes.append(cmd)
        c = cmd.strip().upper()
        head, _, arg = c.partition(" ")
        if head == ":FORM:DATA":
            if self.model.endswith("-R"):
                raise RuntimeError("Undefined header")  # not documented for the -R series
            self.form = arg.replace(",", "")
        elif head == ":SENSE1:FREQUENCY:START":
            self.start = float(arg)
        elif head == ":SENSE1:FREQUENCY:STOP":
            self.stop = float(arg)
        elif head == ":SENSE1:FREQUENCY:CENTER":
            span = self.stop - self.start
            self.start, self.stop = float(arg) - span / 2, float(arg) + span / 2
        elif head == ":SENSE1:FREQUENCY:SPAN":
            center = (self.start + self.stop) / 2
            self.start, self.stop = center - float(arg) / 2, center + float(arg) / 2
        elif head == ":SENSE1:SWEEP:POINTS":
            self.points = int(arg)
        elif head == ":SOURCE1:POWER":
            self.power = float(arg)
        elif head == ":SENSE1:BANDWIDTH":
            self.ifbw = float(arg)
        elif head == ":INITIATE:CONTINUOUS":
            self.continuous = "1" if arg in ("ON", "1") else "0"
        elif head == ":SENSE1:SWEEP:MODE":
            self.sweep_mode = arg[:4]
        elif head.startswith(":CALCULATE1:PARAMETER") and head.endswith(":DEFINE"):
            n = int(head[len(":CALCULATE1:PARAMETER"):-len(":DEFINE")])
            if n not in self.traces:
                raise RuntimeError("trace does not exist")
            self.traces[n]["param"] = arg
        elif head.startswith(":CALCULATE1:MEASURE") and head.endswith(":FORMAT"):
            n = int(head[len(":CALCULATE1:MEASURE"):-len(":FORMAT")])
            self.traces[n]["fmt"] = self._fmt_word(arg)
        elif head.startswith(":CALCULATE1:MEASURE") and ":MARKER" in head:
            tr = int(head.split(":MEASURE")[1].split(":")[0])
            rest = head.split(":MARKER")[1]
            mk = int(rest.split(":")[0])
            key = (tr, mk)
            self.markers.setdefault(key, {"on": False, "x": self.start})
            if rest.isdigit():
                self.markers[key]["on"] = arg in ("ON", "1")
            elif rest.endswith(":X"):
                self.markers[key]["x"] = float(arg)
            elif rest.endswith(":FUNCTION:EXECUTE"):
                data = format_complex(_dut(self.traces[tr]["param"], self.freqs()), self.traces[tr]["fmt"], self.freqs())[0]
                idx = int(np.argmax(data)) if arg.startswith("MAX") else int(np.argmin(data))
                self.markers[key]["x"] = float(self.freqs()[idx])
            else:
                raise AssertionError(f"Unscripted write: {cmd}")
        elif head == ":SENSE1:CORRECTION:COLLECT:METHOD":
            self.method = {"BASIC": "BAS", "RESP": "RESP", "RPOWER": "RPOW", "NONE": "NONE"}[arg]
        elif head == ":SENSE1:CORRECTION:COLLECT:ACQUIRE":
            assert arg in ("OPEN", "SHORT", "LOAD", "THRU")
        elif head == ":SENSE1:CORRECTION:COLLECT:SAVE":
            self.correction = "1"
        elif head == ":SENSE1:CORRECTION:STATE":
            self.correction = "1" if arg in ("ON", "1") else "0"
        elif head == ":OUTPUT:STATE":
            self.output = "1" if arg in ("ON", "1") else "0"
        elif head == ":TRIGGER:SOURCE":
            self.trig_source = arg[:3]
        elif head in (":INITIATE1:IMMEDIATE", ":ABORT", "*RST"):
            pass
        elif head == ":DISPLAY:TRACE:NEW":
            n = max(self.traces) + 1
            self.traces[n] = {"param": "S11", "fmt": "MLOG"}
        else:
            raise AssertionError(f"Unscripted write: {cmd}")

    def query(self, cmd):
        self.queries.append(cmd)
        c = cmd.strip().upper()
        if c == "*IDN?":
            return f"RIGOL TECHNOLOGIES,{self.model},DNA6A000000001,00.01.00"
        if c == ":SENSE1:FREQUENCY:START?":
            return f"{self.start:.2e}"
        if c == ":SENSE1:FREQUENCY:STOP?":
            return f"{self.stop:.2e}"
        if c == ":SENSE1:SWEEP:POINTS?":
            return str(self.points)
        if c == ":SOURCE1:POWER?":
            return f"{self.power:.2e}"
        if c == ":SENSE1:BANDWIDTH?":
            return f"{self.ifbw:.2e}"
        if c == ":INITIATE:CONTINUOUS?":
            return self.continuous
        if c.startswith(":CALCULATE1:PARAMETER") and c.endswith(":DEFINE?"):
            return self.traces[int(c[len(":CALCULATE1:PARAMETER"):-len(":DEFINE?")])]["param"]
        if c == ":CALCULATE1:PARAMETER:CATALOG:EXTENDED? DEFINE":
            return ",".join(f"CH1_{t['param']}_{n},{t['param']}" for n, t in sorted(self.traces.items()))
        if c.startswith(":CALCULATE1:MEASURE"):
            tr = int(c.split(":MEASURE")[1].split(":")[0])
            rest = c.split(":MEASURE")[1][len(str(tr)):]
            t = self.traces[tr]
            z = _dut(t["param"], self.freqs())
            if rest == ":FORMAT?":
                return t["fmt"]
            if rest == ":DATA:X?":
                return ",".join(f"{f:+.11E}" for f in self.freqs())
            if rest == ":DATA:FDATA?":
                return _fmt(z, t["fmt"], self.freqs())
            if rest == ":DATA:SDATA?":
                return ",".join(f"{v.real:+.11E},{v.imag:+.11E}" for v in z)
            if rest.startswith(":MARKER"):
                mk = int(rest[len(":MARKER"):].split(":")[0].rstrip("?"))
                m = self.markers.get((tr, mk), {"on": False, "x": self.start})
                if rest.endswith(":X?"):
                    return f"{m['x']:.2e}"
                if rest.endswith(":Y?"):
                    y = np.interp(m["x"], self.freqs(), format_complex(z, t["fmt"], self.freqs())[0])
                    return f"{y:+.11E},+0.00000000000E+00"
                return "1" if m["on"] else "0"
        if c == ":SENSE1:CORRECTION:COLLECT:METHOD?":
            return self.method
        if c == ":SENSE1:CORRECTION:STATE?":
            return self.correction
        if c == ":OUTPUT:STATE?":
            return self.output
        if c == ":TRIGGER:SOURCE?":
            return self.trig_source
        if c == "*OPC?":
            return "1"
        if c == ":SYSTEM:ERROR?":
            return '0,"No error"'
        raise AssertionError(f"Unscripted query: {cmd}")


def make_driver(cls, model, resource="TCPIP::192.168.1.50::INSTR", **kw):
    inst = ScriptedRSAN(model, **kw) if cls is RigolRSAN else ScriptedDNA(model, **kw)
    rm = MagicMock()
    rm.open_resource = MagicMock(return_value=inst)
    drv = cls(rm, resource)
    if cls is RigolRSAN:
        drv.MODE_SWITCH_DELAY_S = 0.0  # don't sleep 8 s in tests
    return drv, inst


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #


def test_normalizers_and_parsers():
    assert normalize_format("logmag") == "MLOG"
    assert normalize_format("MLOGarithmic") == "MLOG"
    assert normalize_format("smith") == "SMIT"
    assert normalize_sparam("s21") == "S21"
    with pytest.raises(ValueError):
        normalize_format("BANANA")
    with pytest.raises(ValueError):
        normalize_sparam("Z11")
    assert parse_float_list("+1.0E+07,+5.0E+07") == [1e7, 5e7]
    assert parse_float_list("#212+1.0E+00,2.0") == [1.0, 2.0]
    z = parse_complex_list("(1.776848172E-03,4.068690594E-03)(2.462049746E-03,4.538272688E-03)")
    assert z == [complex(1.776848172e-3, 4.068690594e-3), complex(2.462049746e-3, 4.538272688e-3)]


def test_format_complex_math():
    z = [0.1 + 0j, 0.5j, -0.25]
    mlog, sec = format_complex(z, "MLOG")
    assert mlog == pytest.approx([-20.0, -6.0206, -12.0412], abs=1e-3) and sec == []
    assert format_complex(z, "PHAS")[0] == pytest.approx([0.0, 90.0, 180.0])
    assert format_complex(z, "SWR")[0][0] == pytest.approx(1.1 / 0.9)
    re_, im_ = format_complex(z, "SMIT")
    assert re_ == pytest.approx([0.1, 0.0, -0.25]) and im_ == pytest.approx([0.0, 0.5, 0.0])
    freqs = np.linspace(1e6, 1e9, 5)
    delay = format_complex(np.exp(-1j * 2 * np.pi * freqs * 2e-9), "GDEL", freqs)[0]
    assert delay == pytest.approx([2e-9] * 5, rel=1e-6)


# --------------------------------------------------------------------------- #
# Identification / model table
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cls,model,fmax,ports",
    [
        (RigolRSAN, "RSA3015N", 1.5e9, 2), (RigolRSAN, "RSA3030N", 3.0e9, 2),
        (RigolRSAN, "RSA3045N", 4.5e9, 2), (RigolRSAN, "RSA5032N", 3.2e9, 2),
        (RigolRSAN, "RSA5065N", 6.5e9, 2),
        (RigolDNA6000, "DNA6082", 8.5e9, 2), (RigolDNA6000, "DNA6084", 8.5e9, 4),
        (RigolDNA6000, "DNA6142", 14e9, 2), (RigolDNA6000, "DNA6204", 20e9, 4),
        (RigolDNA6000, "DNA6264", 26.5e9, 4), (RigolDNA6000, "DNA6264-R", 26.5e9, 4),
    ],
)
async def test_identification(cls, model, fmax, ports):
    vna, inst = make_driver(cls, model)
    await vna.connect()
    assert vna.connected is True
    info = await vna.get_info()
    assert info.type == EquipmentType.VECTOR_NETWORK_ANALYZER
    assert info.id.startswith("vna_")
    assert info.model == model
    assert info.connection_type == ConnectionType.ETHERNET
    status = await vna.get_status()
    caps = status.capabilities
    assert status.connected is True
    assert caps["frequency_max"] == fmax and caps["ports"] == ports
    assert caps["supports_acquisition"] is True
    assert len(caps["parameters"]) == ports * ports if cls is RigolDNA6000 else caps["parameters"] == ["S11", "S21"]
    assert caps["sweep"]["points"] == 201
    assert model.rstrip("-R") in MODEL_TABLE or model in MODEL_TABLE


@pytest.mark.asyncio
async def test_rsan_connect_switches_to_vna_mode_only_when_needed():
    vna, inst = make_driver(RigolRSAN, "RSA3030N", mode="SA")
    await vna.connect()
    assert ":INSTrument:SELect VNA" in inst.writes and inst.mode == "VNA"
    vna2, inst2 = make_driver(RigolRSAN, "RSA3030N", mode="VNA")
    await vna2.connect()
    assert not any(w.startswith(":INSTrument:SELect") for w in inst2.writes)
    assert await vna2.set_mode("VNA", wait=False) == "VNA"
    with pytest.raises(ValueError):
        await vna2.set_mode("RADIO")


@pytest.mark.asyncio
async def test_dna_form_data_only_tried():
    dna, inst = make_driver(RigolDNA6000, "DNA6082")
    await dna.connect()
    assert ":FORM:DATA ASCII,0" in inst.writes and inst.form == "ASCII0"
    rack, inst_r = make_driver(RigolDNA6000, "DNA6264-R")
    await rack.connect()  # the -R fake rejects :FORM:DATA; connect must still succeed
    assert rack.connected is True


# --------------------------------------------------------------------------- #
# Sweep setup
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("cls,model", [(RigolRSAN, "RSA5065N"), (RigolDNA6000, "DNA6082")])
async def test_set_sweep(cls, model):
    vna, inst = make_driver(cls, model)
    await vna.connect()
    sweep = await vna.set_sweep(start=1e6, stop=500e6, points=401, power=-10.0, if_bandwidth=10e3)
    assert sweep["start_frequency"] == 1e6 and sweep["stop_frequency"] == 500e6
    assert sweep["points"] == 401 and sweep["power_dbm"] == -10.0 and sweep["if_bandwidth"] == 10e3
    if cls is RigolRSAN:
        assert ":SENSe:FREQuency:STARt 1000000" in inst.writes
        assert ":SENSe:SWEep:POINts 401" in inst.writes
        assert ":SOURce:EXTernal:POWer:LEVel:IMMediate:AMPLitude -10" in inst.writes
        assert ":SENSe:BANDwidth:RESolution 10000" in inst.writes
    else:
        assert ":SENSe1:FREQuency:STARt 1000000" in inst.writes
        assert ":SENSe1:SWEep:POINts 401" in inst.writes
        assert ":SOURce1:POWer -10" in inst.writes
        assert ":SENSe1:BANDwidth 10000" in inst.writes
    sweep = await vna.set_center_span(100e6, 20e6)
    assert sweep["start_frequency"] == pytest.approx(90e6) and sweep["stop_frequency"] == pytest.approx(110e6)
    with pytest.raises(ValueError):
        await vna.set_start_stop(500e6, 100e6)
    assert await vna.set_continuous(False) is False
    assert await vna.sweep_single() is True
    assert "*OPC?" in inst.queries


@pytest.mark.asyncio
async def test_model_limits_differ():
    rsan, _ = make_driver(RigolRSAN, "RSA3030N")
    dna, _ = make_driver(RigolDNA6000, "DNA6264")
    await rsan.connect()
    await dna.connect()
    with pytest.raises(ValueError):
        await rsan.set_start_stop(1e6, 4e9)  # RSA3030N stops at 3 GHz
    await dna.set_start_stop(1e6, 4e9)  # fine on a 26.5 GHz DNA6264
    with pytest.raises(ValueError):
        await rsan.set_points(20001)  # 10001 max
    assert await dna.set_points(20001) == 20001
    with pytest.raises(ValueError):
        await rsan.set_power(5.0)  # 0 dBm max on the tracking generator
    assert await dna.set_power(5.0) == 5.0
    with pytest.raises(ValueError):
        await rsan.set_if_bandwidth(100.0)  # 1 kHz minimum
    assert await dna.set_if_bandwidth(100.0) == 100.0
    with pytest.raises(ValueError):
        await rsan.set_parameter(1, "S12")  # only S11/S21 on the RSA-N
    assert await dna.set_parameter(1, "S12") == "S12"
    dna2, _ = make_driver(RigolDNA6000, "DNA6082")
    await dna2.connect()
    with pytest.raises(ValueError):
        await dna2.set_parameter(1, "S33")  # 2-port model


# --------------------------------------------------------------------------- #
# Traces / formats / data
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_rsan_parameter_format_and_trace():
    vna, inst = make_driver(RigolRSAN, "RSA5065N")
    await vna.connect()
    assert await vna.set_parameter(1, "s21") == "S21"
    assert ":CONFigure S21" in inst.writes
    assert await vna.set_format(1, "MLOG") == "MLOG"
    assert ":DISPlay:TRACe1:FORMat MLOGarithmic" in inst.writes
    with pytest.raises(ValueError):
        await vna.set_format(1, "SWR")  # SWR is an S11-only format on the RSA-N
    trace = await vna.get_trace(1)
    assert isinstance(trace, NetworkAnalyzerData)
    assert trace.parameter == "S21" and trace.format == "MLOG" and trace.unit == "dB"
    assert trace.num_points == 201 == len(trace.values) == len(trace.frequencies)
    assert trace.frequencies[0] == 10e6 and trace.frequencies[-1] == 1e9
    # low-pass: -3 dB at 100 MHz, deep attenuation at 1 GHz
    at_fc = np.interp(100e6, trace.frequencies, trace.values)
    assert at_fc == pytest.approx(-3.01, abs=0.1)
    assert trace.values[-1] < -55
    await vna.set_parameter(1, "S11")
    assert await vna.set_format(2, "smith") == "SMIT"
    smith = await vna.get_trace(2)
    assert len(smith.secondary_values) == 201 and abs(complex(smith.values[0], smith.secondary_values[0])) == pytest.approx(0.1)
    traces = await vna.list_traces()
    assert len(traces) == 4 and all(t["parameter"] == "S11" for t in traces)


@pytest.mark.asyncio
async def test_dna_parameter_format_and_trace():
    dna, inst = make_driver(RigolDNA6000, "DNA6082")
    await dna.connect()
    assert await dna.set_parameter(2, "S21") == "S21"
    assert ":CALCulate1:PARameter2:DEFine S21" in inst.writes
    assert await dna.set_format(2, "phase") == "PHAS"
    assert ":CALCulate1:MEASure2:FORMat PHASe" in inst.writes
    trace = await dna.get_trace(2)
    assert trace.parameter == "S21" and trace.format == "PHAS" and trace.unit == "deg"
    assert len(trace.values) == 201 and trace.frequencies[0] == pytest.approx(10e6)
    assert ":CALCulate1:MEASure2:DATA:FDATA?" in inst.queries and ":CALCulate1:MEASure2:DATA:X?" in inst.queries
    await dna.set_format(1, "MLOG")
    s11 = await dna.get_trace(1)
    assert s11.values == pytest.approx([-20.0] * 201, abs=1e-6)
    await dna.set_format(1, "POLAR")
    pol = await dna.get_trace(1)
    assert len(pol.values) == 201 and len(pol.secondary_values) == 201
    raw = await dna.get_complex_trace(2)
    assert len(raw["real"]) == 201 and ":CALCulate1:MEASure2:DATA:SDATA?" in inst.queries
    traces = await dna.list_traces()
    assert [(t["trace"], t["parameter"]) for t in traces] == [(1, "S11"), (2, "S21")]
    traces = await dna.create_trace("S22")
    assert traces[-1]["trace"] == 3 and traces[-1]["parameter"] == "S22"


# --------------------------------------------------------------------------- #
# Markers
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_markers_both_dialects():
    rsan, i1 = make_driver(RigolRSAN, "RSA5065N")
    await rsan.connect()
    await rsan.set_parameter(1, "S21")
    mk = await rsan.set_marker(1, frequency=100e6)
    assert ":CALCulate:MARKer1:MODE POSition" in i1.writes and ":CALCulate:MARKer1:X 100000000" in i1.writes
    assert mk["frequency"] == 100e6 and mk["value"] == pytest.approx(-3.01, abs=0.05)
    mk = await rsan.marker_search(2, "MIN")
    assert ":CALCulate:MARKer2:MINimum" in i1.writes and mk["frequency"] == 1e9

    dna, i2 = make_driver(RigolDNA6000, "DNA6082")
    await dna.connect()
    mk = await dna.set_marker(1, frequency=50e6, trace=2)
    assert ":CALCulate1:MEASure2:MARKer1 ON" in i2.writes and ":CALCulate1:MEASure2:MARKer1:X 50000000" in i2.writes
    assert mk["frequency"] == 50e6 and mk["secondary"] == 0.0
    mk = await dna.marker_search(1, "MAX", trace=2)
    assert ":CALCulate1:MEASure2:MARKer1:FUNCtion:EXECute MAXimum" in i2.writes
    assert mk["frequency"] == 10e6
    with pytest.raises(ValueError):
        await dna.set_marker(17)


# --------------------------------------------------------------------------- #
# Calibration
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_rsan_calibration_flow():
    vna, inst = make_driver(RigolRSAN, "RSA5065N")
    await vna.connect()
    start = await vna.calibrate_start("SOL")
    assert start["parameter"] == "S11" and start["standards"] == ["OPEN", "SHORT", "LOAD"]
    for std in ("open", "short", "load"):
        await vna.calibrate_acquire(std)
    assert ":CALibration:S11:OPEN" in inst.writes and ":CALibration:S11:SHORt" in inst.writes
    assert ":CALibration:S11:LOAD" in inst.writes
    with pytest.raises(ValueError):
        await vna.calibrate_acquire("THRU")  # wrong calibration type
    assert await vna.calibrate_save() is True
    assert ":CALibration:S11:SAVE" in inst.writes
    await vna.calibrate_start("THRU")
    await vna.calibrate_acquire("THRU")
    assert ":CALibration:S21:THROugh" in inst.writes
    assert await vna.calibrate_abort() is True and ":CALibration:S21:ABORt" in inst.writes
    assert await vna.get_correction() is None
    assert await vna.set_correction(False) is False and ":CALibration:CLEAr" in inst.writes
    with pytest.raises(ValueError):
        await vna.set_correction(True)


@pytest.mark.asyncio
async def test_dna_calibration_flow():
    dna, inst = make_driver(RigolDNA6000, "DNA6082")
    await dna.connect()
    start = await dna.calibrate_start("BASIC", s_param="S11")
    assert start["method"] == "BAS" and ":SENSe1:CORRection:COLLect:METHod BASic" in inst.writes
    await dna.calibrate_acquire("OPEN")
    await dna.calibrate_acquire("short")
    await dna.calibrate_acquire("LOAD")
    assert ":SENSe1:CORRection:COLLect:ACQuire SHORt" in inst.writes
    assert await dna.get_correction() is False
    assert await dna.calibrate_save() is True
    assert ":SENSe1:CORRection:COLLect:SAVE" in inst.writes
    assert await dna.get_correction() is True
    assert await dna.set_correction(False) is False
    assert ":SENSe1:CORRection:STATe OFF" in inst.writes
    with pytest.raises(ValueError):
        await dna.calibrate_acquire("ISOLATION")
    assert await dna.set_rf_output(False) is False and ":OUTPut:STATe OFF" in inst.writes
    assert await dna.set_trigger_source("BUS") == "MAN"
    await dna.manual_trigger()
    assert ":INITiate1:IMMediate" in inst.writes


# --------------------------------------------------------------------------- #
# Acquisition hook / dispatch / state
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("cls,model", [(RigolRSAN, "RSA5065N"), (RigolDNA6000, "DNA6082")])
async def test_get_measurement_channel_semantics(cls, model):
    vna, inst = make_driver(cls, model)
    await vna.connect()
    s11 = await vna.get_measurement("S11:MIN")
    assert s11["parameter"] == "S11" and s11["value"] == pytest.approx(-20.0, abs=1e-6) and s11["unit"] == "dB"
    s21max = await vna.get_measurement("S21:MAX")
    assert s21max["parameter"] == "S21" and s21max["value"] == pytest.approx(0.0, abs=0.01)
    assert s21max["frequency"] == pytest.approx(10e6)
    at = await vna.get_measurement("S21:AT:100e6")
    assert at["value"] == pytest.approx(-3.01, abs=0.1) and at["frequency"] == 100e6
    fmin = await vna.get_measurement("S21:MIN_FREQ")
    assert fmin["value"] == 1e9 and fmin["unit"] == "Hz"
    default = await vna.get_measurement("TRACE1:MIN")
    assert not math.isnan(default["value"])
    await vna.set_marker(1, frequency=200e6, trace=(1 if cls is RigolRSAN else 2))
    mk = await vna.get_measurement("MARKER1")
    assert mk["frequency"] == 200e6 and mk["marker"] == 1
    with pytest.raises(ValueError):
        await vna.get_measurement("TRACE1:MEDIAN")
    with pytest.raises(ValueError):
        await vna.get_measurement("S21:AT")


@pytest.mark.asyncio
@pytest.mark.parametrize("cls,model", [(RigolRSAN, "RSA5065N"), (RigolDNA6000, "DNA6264-R")])
async def test_execute_command_dispatch_state_and_errors(cls, model):
    vna, inst = make_driver(cls, model)
    await vna.connect()
    readings = await vna.execute_command("get_readings", {})
    assert isinstance(readings, NetworkAnalyzerData) and readings.trace == 1
    sweep = await vna.execute_command("set_sweep", {"start": 1e6, "stop": 200e6, "points": 101})
    assert sweep["points"] == 101
    meas = await vna.execute_command("get_measurements", {"channel": 1})
    assert meas["points"] == 101 and meas["unit"] == "dB"
    state = await vna.execute_command("get_state", {})
    assert state["sweep"]["points"] == 101 and 1 in state["traces"]
    assert (await vna.execute_command("get_error", {}))["code"] == 0
    with pytest.raises(ValueError):
        await vna.execute_command("make_coffee", {})
    if cls is RigolDNA6000:
        assert await vna.execute_command("set_rf_output", {"enabled": True}) is True
        assert "correction" in state
    else:
        with pytest.raises(ValueError):
            await vna.execute_command("set_rf_output", {"enabled": True})
    await vna.execute_command("reset", {})
    assert "*RST" in inst.writes
    if cls is RigolRSAN:
        assert inst.mode == "VNA"  # reset re-selects the VNA mode
