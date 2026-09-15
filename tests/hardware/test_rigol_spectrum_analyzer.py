"""Tests for the Rigol DSA / RSA spectrum analyzer drivers.

These run against a scripted fake VISA instrument that answers the SCPI
documented in the DSA800 / DSA1000 / RSA3000 / RSA5000 / RSA800 / RSA6000
programming guides, so no hardware is needed.
"""

import re
import struct
import sys
from unittest.mock import MagicMock

import pytest

sys.path.append("..")

from equipment.rigol_spectrum_analyzer import (  # noqa: E402
    MODEL_TABLE, RigolDSA800, RigolDSA1000, RigolRSA800, RigolRSA3000,
    RigolRSA5000, RigolRSA6000, compute_frequencies,
    lookup_model, parse_ascii_trace, parse_binary_trace, parse_number)
from shared.models.data import SpectrumData  # noqa: E402
from shared.models.equipment import ConnectionType, EquipmentType  # noqa: E402

POINTS = 601
# Short forms the instruments answer to :SENSe:DETector? (DSA1000 guide: "NEG, NORM, POS, RMS, SAMP, VAV or QPEAK")
DETECTOR_SHORT = {"POSITIVE": "POS", "NEGATIVE": "NEG", "NORMAL": "NORM", "SAMPLE": "SAMP",
                  "RMS": "RMS", "VAVERAGE": "VAV", "QPEAK": "QPEAK"}
NOISE = -90.0
PEAK_INDEX = 300
PEAK_DBM = -20.0


class ScriptedSA:
    """Minimal Rigol spectrum analyzer SCPI simulator.

    ``family`` selects the answer style: DSA (header on ASCII trace data,
    MARKer<n> peak-search mode, :TRACe<n>:MODE) or RSA (bare ASCII list,
    :INSTrument:SELect, EXTernal TG tree, per-trace detector on RSA800/6000).
    """

    def __init__(self, model="DSA815", family="DSA"):
        self.model = model
        self.family = family
        self.session = 1
        self.timeout = 10000
        self.writes = []
        self.queries = []
        self.read_termination = None
        self.write_termination = None
        spec = lookup_model(model, "DSA815")
        self.fmax = spec.freq_max
        self.center = self.fmax / 2
        self.span = self.fmax
        self.rbw = 1e6
        self.vbw = 1e6
        self.rbw_auto = "1"
        self.vbw_auto = "1"
        self.rlevel = 0.0
        self.atten = 10
        self.atten_auto = "1"
        self.preamp = "0"
        self.unit = "DBM"
        self.points = POINTS
        self.sweep_time = 0.0375
        self.sweep_time_auto = "1"
        self.continuous = "1"
        self.detector = "POS"
        self.detectors = {n: "POS" for n in range(1, 7)}
        self.trace_mode = {n: "WRIT" for n in range(1, 7)}
        self.trace_display = {n: "1" for n in range(1, 7)}
        self.trace_update = {n: "1" for n in range(1, 7)}
        self.avg_count = 100
        self.fmt = "ASC"
        self.border = "NORM"
        self.markers = {n: {"state": "0", "x": self.center, "mode": "POS", "trace": 1} for n in range(1, 9)}
        self.peak_mode = "MAX"
        self.tg_on = "0"
        self.tg_level = -20.0
        self.mode = "SA"
        self.status_condition = 0
        self.chpower_configured = False
        self.obw_configured = False
        self.errors = []

    # -- helpers -----------------------------------------------------------
    @property
    def start(self):
        return self.center - self.span / 2

    @property
    def stop(self):
        return self.center + self.span / 2

    def trace_values(self):
        vals = [NOISE] * self.points
        if self.points > PEAK_INDEX:
            vals[PEAK_INDEX] = PEAK_DBM
            vals[PEAK_INDEX - 5] = -40.0  # secondary peak for NEXT
        return vals

    def peak_freqs(self):
        freqs = compute_frequencies(self.start, self.stop, self.points)
        return freqs[PEAK_INDEX], freqs[PEAK_INDEX - 5]

    def amplitude_at(self, x):
        freqs = compute_frequencies(self.start, self.stop, self.points)
        idx = min(range(len(freqs)), key=lambda i: abs(freqs[i] - x))
        return self.trace_values()[idx]

    def close(self):
        pass

    # -- writes --------------------------------------------------------------
    def write(self, cmd):
        self.writes.append(cmd)
        c = cmd.strip()
        u = c.upper()
        head, _, arg = u.partition(" ")
        arg = arg.strip()

        def flt():
            return float(arg)

        if head in ("*RST", "*CLS"):
            return
        if head == ":SENSE:FREQUENCY:CENTER":
            self.center = flt()
        elif head == ":SENSE:FREQUENCY:SPAN":
            self.span = flt()
        elif head == ":SENSE:FREQUENCY:SPAN:FULL":
            self.center, self.span = self.fmax / 2, self.fmax
        elif head == ":SENSE:FREQUENCY:SPAN:ZERO":
            assert self.family == "RSA", "SPAN:ZERO is RSA only"
            self.span = 0.0
        elif head == ":SENSE:FREQUENCY:START":
            start, stop = flt(), self.stop
            self.center, self.span = (start + stop) / 2, stop - start
        elif head == ":SENSE:FREQUENCY:STOP":
            start, stop = self.start, flt()
            self.center, self.span = (start + stop) / 2, stop - start
        elif head == ":SENSE:BANDWIDTH:RESOLUTION":
            self.rbw = flt()
        elif head == ":SENSE:BANDWIDTH:RESOLUTION:AUTO":
            self.rbw_auto = "1" if arg in ("ON", "1") else "0"
        elif head == ":SENSE:BANDWIDTH:VIDEO":
            self.vbw = flt()
        elif head == ":SENSE:BANDWIDTH:VIDEO:AUTO":
            self.vbw_auto = "1" if arg in ("ON", "1") else "0"
        elif head == ":DISPLAY:WINDOW:TRACE:Y:SCALE:RLEVEL":
            self.rlevel = flt()
        elif head == ":SENSE:POWER:RF:ATTENUATION":
            self.atten = int(flt())
        elif head == ":SENSE:POWER:RF:ATTENUATION:AUTO":
            self.atten_auto = "1" if arg in ("ON", "1") else "0"
        elif head == ":SENSE:POWER:RF:GAIN:STATE":
            self.preamp = "1" if arg in ("ON", "1") else "0"
        elif head == ":UNIT:POWER":
            self.unit = arg
        elif head == ":SENSE:SWEEP:POINTS":
            assert self.model not in ("DSA705", "DSA710"), "DSA700 has no SWEep:POINts"
            self.points = int(arg)
        elif head == ":SENSE:SWEEP:TIME":
            self.sweep_time = flt()
        elif head == ":SENSE:SWEEP:TIME:AUTO":
            self.sweep_time_auto = "1" if arg in ("ON", "1") else "0"
        elif head == ":INITIATE:CONTINUOUS":
            self.continuous = "1" if arg in ("ON", "1") else "0"
        elif head == ":INITIATE:IMMEDIATE":
            self.status_condition = 0
        elif head == ":SENSE:DETECTOR:FUNCTION":
            assert self.family != "RSA800", "RSA800/6000 detector is per trace"
            self.detector = DETECTOR_SHORT[arg]
        elif re.fullmatch(r":SENSE:DETECTOR:TRACE\d", head):
            self.detectors[int(head[-1])] = DETECTOR_SHORT[arg]
        elif re.fullmatch(r":TRACE\d:(MODE|TYPE)", head):
            n = int(head[6])
            if head.endswith("TYPE"):
                assert self.family in ("RSA", "RSA800"), "TRACe:TYPE is RSA only"
            else:
                assert self.family != "RSA800", "RSA800/6000 only have TRACe<n>:TYPE"
            if self.family in ("RSA", "RSA800"):
                assert arg in ("WRITE", "AVERAGE", "MAXHOLD", "MINHOLD"), f"bad RSA trace type {arg}"
            self.trace_mode[n] = {"WRITE": "WRIT", "MAXHOLD": "MAXH", "MINHOLD": "MINH", "VIEW": "VIEW",
                                  "BLANK": "BLAN", "VIDEOAVG": "VID", "POWERAVG": "POW", "AVERAGE": "AVER"}[arg]
        elif re.fullmatch(r":TRACE\d:DISPLAY:STATE", head):
            self.trace_display[int(head[6])] = "1" if arg in ("ON", "1") else "0"
        elif re.fullmatch(r":TRACE\d:UPDATE:STATE", head):
            self.trace_update[int(head[6])] = "1" if arg in ("ON", "1") else "0"
        elif head in (":TRACE:AVERAGE:COUNT", ":SENSE:AVERAGE:COUNT"):
            if head.startswith(":SENSE"):
                assert self.family in ("RSA", "RSA800"), "SENSe:AVERage is RSA only"
            self.avg_count = int(arg)
        elif head in (":TRACE:AVERAGE:RESET", ":SENSE:AVERAGE:CLEAR"):
            pass
        elif head == ":FORMAT:TRACE:DATA":
            if self.family == "RSA800":
                raise AssertionError("RSA800/6000 have no :FORMat command")
            self.fmt = {"ASCII": "ASC", "REAL,32": "REAL,32", "REAL,64": "REAL,64", "INTEGER,32": "INT,32"}[arg]
        elif head == ":FORMAT:BORDER":
            self.border = arg[:4]
        elif re.fullmatch(r":CALCULATE:MARKER\d:STATE", head):
            self.markers[int(head[17])]["state"] = "1" if arg in ("ON", "1") else "0"
        elif re.fullmatch(r":CALCULATE:MARKER\d:X", head):
            self.markers[int(head[17])]["x"] = flt()
        elif re.fullmatch(r":CALCULATE:MARKER\d:MODE", head):
            self.markers[int(head[17])]["mode"] = arg[:4] if arg != "OFF" else "OFF"
        elif re.fullmatch(r":CALCULATE:MARKER\d:TRACE", head):
            self.markers[int(head[17])]["trace"] = int(arg)
        elif re.fullmatch(r":CALCULATE:MARKER\d:MAXIMUM:MAX", head):
            self.markers[int(head[17])]["x"] = self.peak_freqs()[0]
        elif re.fullmatch(r":CALCULATE:MARKER\d:MAXIMUM:NEXT", head):
            self.markers[int(head[17])]["x"] = self.peak_freqs()[1]
        elif re.fullmatch(r":CALCULATE:MARKER\d:SET:CENTER", head):
            self.center = self.markers[int(head[17])]["x"]
        elif re.fullmatch(r":CALCULATE:MARKER\d:PEAK:SEARCH:MODE", head):
            assert self.family == "DSA", "MARKer<n>:PEAK:SEARch:MODE is DSA only"
            self.peak_mode = arg[:3]
        elif head == ":CALCULATE:MARKER:PEAK:SEARCH:MODE":
            assert self.family != "DSA", "DSA needs MARKer<n>:PEAK:SEARch:MODE"
            self.peak_mode = arg[:3]
        elif head == ":CALCULATE:MARKER:AOFF":
            for m in self.markers.values():
                m["state"] = "0"
        elif head == ":OUTPUT:STATE":
            assert self.family == "DSA"
            self.tg_on = "1" if arg in ("ON", "1") else "0"
        elif head == ":OUTPUT:EXTERNAL:STATE":
            assert self.family != "DSA"
            self.tg_on = "1" if arg in ("ON", "1") else "0"
        elif head == ":SOURCE:POWER:LEVEL:IMMEDIATE:AMPLITUDE":
            assert self.family == "DSA"
            self.tg_level = flt()
        elif head == ":SOURCE:EXTERNAL:POWER:LEVEL:IMMEDIATE:AMPLITUDE":
            assert self.family != "DSA"
            self.tg_level = flt()
        elif head == ":INSTRUMENT:SELECT":
            assert self.family != "DSA", "DSA has no INSTrument:SELect"
            self.mode = arg
        elif head == ":CONFIGURE:CHPOWER":
            assert self.family == "DSA", "only DSA has :CONFigure:CHPower"
            self.chpower_configured = True
        elif head == ":CONFIGURE:OBWIDTH":
            self.obw_configured = True
        elif head.startswith(":SENSE:CHPOWER:") or head.startswith(":SENSE:OBWIDTH:"):
            pass
        elif head == ":INPUT:IMPEDANCE":
            assert self.family == "DSA" and self.model.startswith("DSA10")
            self.impedance = int(arg)
        else:
            raise AssertionError(f"Unscripted write: {cmd}")

    # -- queries -------------------------------------------------------------
    def query(self, cmd):
        self.queries.append(cmd)
        c = cmd.strip().upper()
        if c == "*IDN?":
            return f"Rigol Technologies,{self.model},DSA8A134400008,00.01.16.00.03"
        if c == "*OPC?":
            return "1"
        if c == ":SYSTEM:ERROR?":
            return self.errors.pop(0) if self.errors else '0,"No error"'
        if c == ":SENSE:FREQUENCY:CENTER?":
            return f"{self.center:.0f}"
        if c == ":SENSE:FREQUENCY:SPAN?":
            return f"{self.span:.0f}"
        if c == ":SENSE:FREQUENCY:START?":
            return f"{self.start:.0f}"
        if c == ":SENSE:FREQUENCY:STOP?":
            return f"{self.stop:.0f}"
        if c == ":SENSE:BANDWIDTH:RESOLUTION?":
            return f"{self.rbw:.0f}" if self.family == "DSA" else f"{self.rbw:.9e}"
        if c == ":SENSE:BANDWIDTH:RESOLUTION:AUTO?":
            return self.rbw_auto
        if c == ":SENSE:BANDWIDTH:VIDEO?":
            return f"{self.vbw:.0f}"
        if c == ":SENSE:BANDWIDTH:VIDEO:AUTO?":
            return self.vbw_auto
        if c == ":DISPLAY:WINDOW:TRACE:Y:SCALE:RLEVEL?":
            return f"{self.rlevel:.6E}"
        if c == ":SENSE:POWER:RF:ATTENUATION?":
            return str(self.atten)
        if c == ":SENSE:POWER:RF:ATTENUATION:AUTO?":
            return self.atten_auto
        if c == ":SENSE:POWER:RF:GAIN:STATE?":
            return self.preamp
        if c == ":UNIT:POWER?":
            return self.unit
        if c == ":SENSE:SWEEP:POINTS?":
            assert self.model not in ("DSA705", "DSA710"), "DSA700 has no SWEep:POINts"
            return str(self.points)
        if c == ":SENSE:SWEEP:TIME?":
            return f"{self.sweep_time:.6E}"
        if c == ":SENSE:SWEEP:TIME:AUTO?":
            return self.sweep_time_auto
        if c == ":INITIATE:CONTINUOUS?":
            return self.continuous
        if c == ":STATUS:OPERATION:CONDITION?":
            assert self.family != "RSA800", "RSA800/6000 have no :STATus:OPERation"
            return str(self.status_condition)
        if c == ":SENSE:DETECTOR:FUNCTION?":
            assert self.family != "RSA800"
            return self.detector
        m = re.fullmatch(r":SENSE:DETECTOR:TRACE(\d)\?", c)
        if m:
            return self.detectors[int(m.group(1))]
        m = re.fullmatch(r":TRACE(\d):(MODE|TYPE)\?", c)
        if m:
            return self.trace_mode[int(m.group(1))]
        m = re.fullmatch(r":TRACE(\d):DISPLAY:STATE\?", c)
        if m:
            return self.trace_display[int(m.group(1))]
        m = re.fullmatch(r":TRACE(\d):UPDATE:STATE\?", c)
        if m:
            return self.trace_update[int(m.group(1))]
        if c in (":TRACE:AVERAGE:COUNT?", ":SENSE:AVERAGE:COUNT?"):
            return str(self.avg_count)
        if c == ":FORMAT:TRACE:DATA?":
            return self.fmt
        if c == ":FORMAT:BORDER?":
            return self.border
        m = re.fullmatch(r":TRACE:DATA\? TRACE(\d)", c)
        if m:
            assert self.fmt == "ASC", "ASCII query while binary format selected"
            body = ", ".join(f"{v:.6e}" for v in self.trace_values())
            if self.family == "DSA":
                # DSA800 guide 2-188: ASCII reply carries a #9 definite-length header.
                return f"#9{len(body) + 1:09d} " + body
            return body
        m = re.fullmatch(r":CALCULATE:MARKER(\d):STATE\?", c)
        if m:
            return self.markers[int(m.group(1))]["state"]
        m = re.fullmatch(r":CALCULATE:MARKER(\d):X\?", c)
        if m:
            return f"{self.markers[int(m.group(1))]['x']:.0f}"
        m = re.fullmatch(r":CALCULATE:MARKER(\d):Y\?", c)
        if m:
            return f"{self.amplitude_at(self.markers[int(m.group(1))]['x']):.6E}"
        m = re.fullmatch(r":CALCULATE:MARKER(\d):MODE\?", c)
        if m:
            return self.markers[int(m.group(1))]["mode"]
        if re.fullmatch(r":CALCULATE:MARKER\d?:?PEAK:SEARCH:MODE\?", c):
            return self.peak_mode
        if c in (":OUTPUT:STATE?", ":OUTPUT:EXTERNAL:STATE?"):
            return self.tg_on
        if c in (":SOURCE:POWER:LEVEL:IMMEDIATE:AMPLITUDE?", ":SOURCE:EXTERNAL:POWER:LEVEL:IMMEDIATE:AMPLITUDE?"):
            return f"{self.tg_level:.6E}"
        if c == ":INSTRUMENT:SELECT?":
            return self.mode
        if c == ":READ:CHPOWER?":
            assert self.chpower_configured, ":READ:CHPower? before :CONFigure:CHPower"
            return "-1.599480E+01,-7.900511E+01"
        if c == ":FETCH:CHPOWER1?":
            assert self.mode == "GPSA_CHPOWER", "FETCh:CHPower needs GPSA_CHPower mode"
            return "-1.599480E+01"
        if c == ":FETCH:CHPOWER:DENSITY1?":
            return "-7.900511E+01"
        if c in (":READ:OBWIDTH?", ":FETCH:OBWIDTH?"):
            return "2.000000E+06,1.500000E+03"
        if c == ":INPUT:IMPEDANCE?":
            return str(getattr(self, "impedance", 50))
        raise AssertionError(f"Unscripted query: {cmd}")

    def query_binary_values(self, cmd, datatype="B"):
        c = cmd.strip().upper()
        if c == ":MMEMORY:STORE:SCREEN:DATA?":
            return list(b"BM" + bytes(64))
        m = re.fullmatch(r":TRACE:DATA\? TRACE(\d)", c)
        assert m, f"Unscripted binary query: {cmd}"
        assert self.fmt == "REAL,32", "binary query while ASCII selected"
        order = "<" if self.border == "SWAP" else ">"
        return list(struct.pack(f"{order}{self.points}f", *self.trace_values()))


FAMILY_OF = {RigolDSA800: "DSA", RigolDSA1000: "DSA", RigolRSA3000: "RSA", RigolRSA5000: "RSA",
             RigolRSA800: "RSA800", RigolRSA6000: "RSA800"}


def make_driver(cls, model, resource="USB0::0x1AB1::0x0960::DSA8A134400008::INSTR"):
    inst = ScriptedSA(model, FAMILY_OF[cls])
    rm = MagicMock()
    rm.open_resource = MagicMock(return_value=inst)
    return cls(rm, resource), inst


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #


def test_parse_ascii_trace_with_and_without_header():
    body = "-1.390530e+01, -7.108871e+01, -7.089631e+01"
    assert parse_ascii_trace(body) == pytest.approx([-13.9053, -71.08871, -70.89631])
    assert parse_ascii_trace(f"#9{len(body) + 1:09d} {body}") == pytest.approx([-13.9053, -71.08871, -70.89631])
    assert parse_ascii_trace("#0" + body) == pytest.approx([-13.9053, -71.08871, -70.89631])
    assert parse_ascii_trace("") == []


def test_parse_binary_trace_block_and_payload():
    values = [-13.9053, -71.08871, -70.89631]
    payload_le = struct.pack("<3f", *values)
    payload_be = struct.pack(">3f", *values)
    assert parse_binary_trace(payload_le, "REAL,32", True) == pytest.approx(values, rel=1e-6)
    assert parse_binary_trace(payload_be, "REAL,32", False) == pytest.approx(values, rel=1e-6)
    block = b"#9" + f"{len(payload_le):09d}".encode() + payload_le
    assert parse_binary_trace(block, "REAL,32", True) == pytest.approx(values, rel=1e-6)
    assert parse_binary_trace(struct.pack("<2d", 1.5, -2.5), "REAL,64", True) == [1.5, -2.5]


def test_compute_frequencies_and_parse_number():
    freqs = compute_frequencies(0.0, 1.5e9, 601)
    assert len(freqs) == 601 and freqs[0] == 0.0 and freqs[-1] == pytest.approx(1.5e9)
    assert freqs[300] == pytest.approx(750e6)
    assert compute_frequencies(1e6, 1e6, 1) == [1e6]
    assert parse_number("-1.000000E+01") == -10.0
    assert parse_number("9.9E37") is None
    assert parse_number("") is None


def test_model_table_lookup():
    assert lookup_model("DSA815-TG", "DSA815").tracking_generator is True
    assert lookup_model("dsa815", "DSA815").tracking_generator is False
    assert lookup_model("RSA6140-TG", "RSA6140").tracking_generator is True  # derived row
    assert lookup_model("UNKNOWN", "RSA5065").model == "RSA5065"
    assert MODEL_TABLE["DSA705"].points_settable is False and MODEL_TABLE["DSA705"].max_points == 601
    assert MODEL_TABLE["RSA6265"].freq_max == 26.5e9 and MODEL_TABLE["RSA6265"].rtsa is True
    assert MODEL_TABLE["DSA1030A"].rbw_min == 10.0 and MODEL_TABLE["DSA1030"].rbw_min == 100.0


# --------------------------------------------------------------------------- #
# Identification
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "cls,model,fmax,tg,rtsa",
    [
        (RigolDSA800, "DSA815", 1.5e9, False, False),
        (RigolDSA800, "DSA832-TG", 3.2e9, True, False),
        (RigolDSA800, "DSA875", 7.5e9, False, False),
        (RigolDSA800, "DSA832E", 3.2e9, False, False),
        (RigolDSA800, "DSA710", 1e9, False, False),
        (RigolDSA1000, "DSA1030A", 3e9, False, False),
        (RigolDSA1000, "DSA1030-TG", 3e9, True, False),
        (RigolRSA3000, "RSA3030E", 3e9, False, True),
        (RigolRSA3000, "RSA3045-TG", 4.5e9, True, True),
        (RigolRSA5000, "RSA5065", 6.5e9, False, True),
        (RigolRSA5000, "RSA5032-TG", 3.2e9, True, True),
        (RigolRSA800, "RSA814", 14e9, True, True),
        (RigolRSA6000, "RSA6085", 8.5e9, False, True),
        (RigolRSA6000, "RSA6265", 26.5e9, False, True),
    ],
)
async def test_identification(cls, model, fmax, tg, rtsa):
    sa, inst = make_driver(cls, model)
    await sa.connect()
    assert sa.connected is True
    info = await sa.get_info()
    assert info.type == EquipmentType.SPECTRUM_ANALYZER
    assert info.id.startswith("sa_")
    assert info.manufacturer == "Rigol Technologies"
    assert info.model == model
    assert info.serial_number == "DSA8A134400008"
    assert info.connection_type == ConnectionType.USB
    status = await sa.get_status()
    caps = status.capabilities
    assert status.connected is True
    assert status.firmware_version == "00.01.16.00.03"
    assert caps["frequency_max"] == fmax
    assert caps["has_tracking_generator"] is tg
    assert caps["supports_rtsa"] is rtsa
    assert caps["supports_acquisition"] is True
    assert caps["family"] == cls.FAMILY


async def test_connect_selects_ascii_format_and_reads_mode():
    sa, inst = make_driver(RigolRSA5000, "RSA5065")
    await sa.connect()
    assert ":FORMat:TRACe:DATA ASCii" in inst.writes
    assert (await sa.get_status()).capabilities["mode"] == "SA"
    dsa, dinst = make_driver(RigolDSA800, "DSA815")
    await dsa.connect()
    assert not any(q.upper().startswith(":INSTRUMENT") for q in dinst.queries)


# --------------------------------------------------------------------------- #
# Frequency / bandwidth / amplitude
# --------------------------------------------------------------------------- #


async def test_frequency_setters():
    sa, inst = make_driver(RigolDSA800, "DSA815")
    await sa.connect()
    f = await sa.set_frequency(center=100e6, span=10e6)
    assert ":SENSe:FREQuency:CENTer 100000000" in inst.writes
    assert ":SENSe:FREQuency:SPAN 10000000" in inst.writes
    assert f == {"center": 100e6, "span": 10e6, "start": 95e6, "stop": 105e6}
    f = await sa.set_start_stop(1e6, 501e6)
    assert f["center"] == 251e6 and f["span"] == 500e6
    await sa.set_zero_span()
    assert inst.writes[-1] == ":SENSe:FREQuency:SPAN 0"  # DSA has no SPAN:ZERO
    await sa.set_full_span()
    assert inst.span == 1.5e9
    with pytest.raises(ValueError):
        await sa.set_frequency(center=2e9)  # above 1.5 GHz
    with pytest.raises(ValueError):
        await sa.set_start_stop(10e6, 1e6)


async def test_zero_span_uses_rsa_keyword():
    sa, inst = make_driver(RigolRSA3000, "RSA3030")
    await sa.connect()
    await sa.set_frequency(span=0)
    assert inst.writes[-1] == ":SENSe:FREQuency:SPAN:ZERO"


async def test_bandwidth_setters_and_limits():
    sa, inst = make_driver(RigolDSA800, "DSA815")
    await sa.connect()
    bw = await sa.set_rbw(1000)
    assert ":SENSe:BANDwidth:RESolution:AUTO OFF" in inst.writes
    assert ":SENSe:BANDwidth:RESolution 1000" in inst.writes
    assert bw["rbw"] == 1000.0 and bw["rbw_auto"] is False
    bw = await sa.set_vbw(300)
    assert bw["vbw"] == 300.0 and bw["vbw_auto"] is False
    bw = await sa.set_rbw("AUTO")
    assert bw["rbw_auto"] is True
    with pytest.raises(ValueError):
        await sa.set_rbw(1)  # DSA815 min RBW is 10 Hz
    rsa, _ = make_driver(RigolRSA5000, "RSA5065")
    await rsa.connect()
    assert (await rsa.set_rbw(1))["rbw"] == 1.0  # RSA5000 goes to 1 Hz
    dsa1030, _ = make_driver(RigolDSA1000, "DSA1030")
    await dsa1030.connect()
    with pytest.raises(ValueError):
        await dsa1030.set_rbw(10)  # DSA1030 (non-A) min RBW is 100 Hz


async def test_amplitude_setters():
    sa, inst = make_driver(RigolDSA800, "DSA815")
    await sa.connect()
    amp = await sa.set_reference_level(-10)
    assert ":DISPlay:WINdow:TRACe:Y:SCALe:RLEVel -10" in inst.writes
    assert amp["reference_level"] == -10.0
    amp = await sa.set_attenuation(20)
    assert ":SENSe:POWer:RF:ATTenuation:AUTO OFF" in inst.writes
    assert amp["attenuation"] == 20.0 and amp["attenuation_auto"] is False
    amp = await sa.set_attenuation(auto=True)
    assert amp["attenuation_auto"] is True
    with pytest.raises(ValueError):
        await sa.set_attenuation(40)  # DSA800 max is 30 dB
    with pytest.raises(ValueError):
        await sa.set_reference_level(25)  # DSA800 max is +20 dBm
    assert await sa.set_unit("dBuV") == "dBuV"
    assert ":UNIT:POWer DBUV" in inst.writes
    with pytest.raises(ValueError):
        await sa.set_preamp(True)  # DSA815 has no preamp in the table
    sa832, i832 = make_driver(RigolDSA800, "DSA832")
    await sa832.connect()
    assert await sa832.set_preamp(True) is True
    assert ":SENSe:POWer:RF:GAIN:STATe ON" in i832.writes
    rsa, _ = make_driver(RigolRSA800, "RSA814")
    await rsa.connect()
    assert (await rsa.set_attenuation(50))["attenuation"] == 50.0
    assert (await rsa.set_reference_level(30))["reference_level"] == 30.0


# --------------------------------------------------------------------------- #
# Sweep / detector / trace mode / averaging
# --------------------------------------------------------------------------- #


async def test_sweep_settings_and_single_sweep():
    sa, inst = make_driver(RigolDSA800, "DSA815")
    await sa.connect()
    sw = await sa.set_sweep(points=1001, time=0.5, continuous=False)
    assert ":SENSe:SWEep:POINts 1001" in inst.writes
    assert ":SENSe:SWEep:TIME 0.5" in inst.writes
    assert sw == {"points": 1001, "time": 0.5, "time_auto": False, "continuous": False}
    await sa.set_sweep(time="AUTO")
    assert ":SENSe:SWEep:TIME:AUTO ON" in inst.writes
    with pytest.raises(ValueError):
        await sa.set_sweep(points=5000)
    assert await sa.single_sweep() is True
    assert ":INITiate:CONTinuous OFF" in inst.writes and ":INITiate:IMMediate" in inst.writes
    assert "*OPC?" in inst.queries and ":STATus:OPERation:CONDition?" in inst.queries


async def test_single_sweep_without_status_register_on_rsa800():
    sa, inst = make_driver(RigolRSA800, "RSA814")
    await sa.connect()
    assert await sa.single_sweep() is True
    assert ":STATus:OPERation:CONDition?" not in inst.queries


async def test_dsa700_fixed_points():
    sa, inst = make_driver(RigolDSA800, "DSA705")
    await sa.connect()
    with pytest.raises(ValueError):
        await sa.set_sweep(points=1001)
    assert (await sa.get_sweep())["points"] == 601
    assert not any("POINTS" in q.upper() for q in inst.queries)


async def test_detector_family_forms():
    dsa, dinst = make_driver(RigolDSA800, "DSA815")
    await dsa.connect()
    assert await dsa.set_detector("rms") == "RMS"
    assert ":SENSe:DETector:FUNCtion RMS" in dinst.writes
    assert await dsa.set_detector("sample") == "SAMPLE"
    with pytest.raises(ValueError):
        await dsa.set_detector("magic")
    rsa, rinst = make_driver(RigolRSA6000, "RSA6140")
    await rsa.connect()
    assert await rsa.set_detector("POSITIVE", trace=2) == "POSITIVE"
    assert ":SENSe:DETector:TRACe2 POSitive" in rinst.writes


async def test_trace_modes_dsa_and_rsa():
    dsa, dinst = make_driver(RigolDSA800, "DSA815")
    await dsa.connect()
    assert await dsa.set_trace_mode(1, "maxhold") == "MAXHOLD"
    assert ":TRACe1:MODE MAXHold" in dinst.writes
    assert await dsa.set_trace_mode(2, "VIEW") == "VIEW"
    assert await dsa.set_trace_mode(1, "AVERAGE") == "VIDEOAVG"  # DSA spelling
    with pytest.raises(ValueError):
        await dsa.set_trace_mode(4, "WRITE")  # DSA has traces 1..3
    rsa, rinst = make_driver(RigolRSA800, "RSA814")
    await rsa.connect()
    assert await rsa.set_trace_mode(1, "AVERAGE") == "AVERAGE"
    assert ":TRACe1:TYPE AVERage" in rinst.writes
    assert await rsa.set_trace_mode(1, "VIEW") == "VIEW"
    assert ":TRACe1:UPDate:STATe OFF" in rinst.writes
    assert await rsa.set_trace_mode(1, "BLANK") == "BLANK"
    assert ":TRACe1:DISPlay:STATe OFF" in rinst.writes
    assert await rsa.set_trace_mode(6, "WRITE") == "WRITE"


async def test_average_uses_family_command():
    dsa, dinst = make_driver(RigolDSA800, "DSA815")
    await dsa.connect()
    avg = await dsa.set_average(50)
    assert ":TRACe:AVERage:COUNt 50" in dinst.writes and avg["count"] == 50
    rsa, rinst = make_driver(RigolRSA5000, "RSA5065")
    await rsa.connect()
    avg = await rsa.set_average(20, trace=2)
    assert ":SENSe:AVERage:COUNt 20" in rinst.writes and avg["count"] == 20
    assert ":TRACe2:MODE AVERage" in rinst.writes


# --------------------------------------------------------------------------- #
# Trace data
# --------------------------------------------------------------------------- #


async def test_get_trace_ascii_with_header_and_peak():
    sa, inst = make_driver(RigolDSA800, "DSA815")
    await sa.connect()
    data = await sa.get_trace(1)
    assert isinstance(data, SpectrumData)
    assert data.num_points == POINTS and len(data.values) == POINTS
    assert data.start_frequency == 0.0 and data.stop_frequency == 1.5e9
    assert data.center_frequency == 750e6 and data.span == 1.5e9
    assert data.peak_amplitude == pytest.approx(PEAK_DBM)
    assert data.peak_frequency == pytest.approx(750e6)
    assert data.rbw == 1e6 and data.vbw == 1e6
    assert data.reference_level == 0.0 and data.attenuation == 10.0
    assert data.unit == "dBm" and data.detector == "POSITIVE"
    assert ":TRACe:DATA? TRACE1" in inst.queries


async def test_get_trace_ascii_bare_list_on_rsa():
    sa, inst = make_driver(RigolRSA5000, "RSA5065")
    await sa.connect()
    await sa.set_frequency(center=1e9, span=100e6)
    data = await sa.get_trace(2)
    assert data.trace == 2 and data.num_points == POINTS
    assert data.peak_frequency == pytest.approx(1e9)
    assert data.values[0] == pytest.approx(NOISE)


async def test_get_trace_real32_block():
    sa, inst = make_driver(RigolDSA800, "DSA875")
    await sa.connect()
    assert await sa.set_data_format("REAL,32") == "REAL,32"
    assert ":FORMat:TRACe:DATA REAL,32" in inst.writes
    assert ":FORMat:BORDer SWAPped" in inst.writes  # NORMal is MSB first on DSA800
    data = await sa.get_trace(1)
    assert data.num_points == POINTS
    assert data.peak_amplitude == pytest.approx(PEAK_DBM, rel=1e-6)
    assert data.values[10] == pytest.approx(NOISE, rel=1e-6)
    with pytest.raises(ValueError):
        await sa.set_data_format("REAL,64")  # DSA800 has REAL,32 only
    rsa800, _ = make_driver(RigolRSA800, "RSA814")
    await rsa800.connect()
    with pytest.raises(ValueError):
        await rsa800.set_data_format("REAL,32")  # ASCII only on RSA800/6000


async def test_get_trace_with_sweep_and_unit():
    sa, inst = make_driver(RigolDSA800, "DSA815")
    await sa.connect()
    await sa.set_unit("W")
    data = await sa.get_trace(1, sweep=True)
    assert ":INITiate:IMMediate" in inst.writes
    assert data.unit == "W"
    readings = await sa.get_readings()
    assert readings.trace == 1


# --------------------------------------------------------------------------- #
# Markers
# --------------------------------------------------------------------------- #


async def test_markers_peak_search_and_readout():
    sa, inst = make_driver(RigolDSA800, "DSA815")
    await sa.connect()
    m = await sa.peak_search(1)
    assert ":CALCulate:MARKer1:STATe ON" in inst.writes
    assert ":CALCulate:MARKer1:MAXimum:MAX" in inst.writes
    assert m["enabled"] is True
    assert m["frequency"] == pytest.approx(750e6)
    assert m["amplitude"] == pytest.approx(PEAK_DBM)
    m = await sa.next_peak(1)
    assert ":CALCulate:MARKer1:MAXimum:NEXT" in inst.writes
    assert m["amplitude"] == pytest.approx(-40.0)
    m = await sa.set_marker(2, frequency=200e6, mode="DELTA")
    assert ":CALCulate:MARKer2:X 200000000" in inst.writes
    assert ":CALCulate:MARKer2:MODE DELTa" in inst.writes
    assert m["frequency"] == 200e6 and m["mode"] == "DELT"
    f = await sa.marker_to_center(1)  # marker 1 sits on the NEXT peak now
    assert ":CALCulate:MARKer1:SET:CENTer" in inst.writes
    assert f["center"] == pytest.approx(737.5e6)
    n_before = inst.writes.count(":CALCulate:MARKer1:MAXimum:MAX")
    f = await sa.marker_to_center(1, peak=True)  # peak search first, then -> CF
    assert inst.writes.count(":CALCulate:MARKer1:MAXimum:MAX") == n_before + 1
    assert f["center"] == pytest.approx(inst.peak_freqs()[0])
    assert await sa.set_peak_search_mode("PARAMETER") == "PAR"
    assert ":CALCulate:MARKer1:PEAK:SEARch:MODE PARameter" in inst.writes
    await sa.marker_off(2)
    assert (await sa.get_marker(2))["enabled"] is False
    await sa.all_markers_off()
    assert ":CALCulate:MARKer:AOFF" in inst.writes
    with pytest.raises(ValueError):
        await sa.get_marker(5)  # DSA has 4 markers
    with pytest.raises(ValueError):
        await sa.set_marker(1, mode="FIXED")  # RSA-only marker type


async def test_marker_differences_on_rsa():
    sa, inst = make_driver(RigolRSA3000, "RSA3045")
    await sa.connect()
    assert await sa.set_peak_search_mode("MAX") == "MAX"
    assert ":CALCulate:MARKer:PEAK:SEARch:MODE MAXimum" in inst.writes
    m = await sa.set_marker(8, frequency=1e9, mode="FIXED")
    assert m["marker"] == 8 and ":CALCulate:MARKer8:MODE FIXed" in inst.writes


# --------------------------------------------------------------------------- #
# Tracking generator / mode / measurements
# --------------------------------------------------------------------------- #


async def test_tracking_generator_guard_and_control():
    plain, _ = make_driver(RigolDSA800, "DSA815")
    await plain.connect()
    with pytest.raises(ValueError):
        await plain.set_tracking_generator(True, level=-10)
    with pytest.raises(ValueError):
        await plain.get_tracking_generator()
    assert await plain.set_output(False) is None  # disconnect hook is a no-op without TG

    tg, inst = make_driver(RigolDSA800, "DSA815-TG")
    await tg.connect()
    state = await tg.set_tracking_generator(True, level=-10)
    assert ":SOURce:POWer:LEVel:IMMediate:AMPLitude -10" in inst.writes
    assert ":OUTPut:STATe ON" in inst.writes
    assert state == {"enabled": True, "level": -10.0, "unit": "dBm"}
    with pytest.raises(ValueError):
        await tg.set_tracking_generator(True, level=5)
    assert (await tg.set_output(False))["enabled"] is False

    # Override when *IDN? omits the -TG suffix
    plain.set_tracking_generator_fitted(True)
    assert (await plain.get_status()).capabilities["has_tracking_generator"] is True

    rsa, rinst = make_driver(RigolRSA5000, "RSA5065-TG")
    await rsa.connect()
    await rsa.set_tracking_generator(True, level=-5)
    assert ":OUTPut:EXTernal:STATe ON" in rinst.writes
    assert ":SOURce:EXTernal:POWer:LEVel:IMMediate:AMPLitude -5" in rinst.writes

    dsa1030, dinst = make_driver(RigolDSA1000, "DSA1030-TG")
    await dsa1030.connect()
    with pytest.raises(ValueError):
        await dsa1030.set_tracking_generator(True, level=-30)  # DSA1030-TG: -20..0 dBm


async def test_mode_select_on_rsa_only():
    dsa, _ = make_driver(RigolDSA800, "DSA815")
    await dsa.connect()
    assert await dsa.get_mode() == "GPSA"
    with pytest.raises(ValueError):
        await dsa.set_mode("RTSA")

    rsa, inst = make_driver(RigolRSA5000, "RSA5065")
    await rsa.connect()
    assert await rsa.set_mode("RTSA") == "RTSA"
    assert ":INSTrument:SELect RTSA" in inst.writes
    assert await rsa.set_mode("GPSA") == "SA"
    assert ":INSTrument:SELect SA" in inst.writes
    with pytest.raises(ValueError):
        await rsa.set_mode("VSA")  # RSA5000 guide lists SA|RTSA only

    rsa3e, _ = make_driver(RigolRSA3000, "RSA3030E")
    await rsa3e.connect()
    assert await rsa3e.set_mode("EMI") == "EMI"

    rsa8, i8 = make_driver(RigolRSA800, "RSA814")
    await rsa8.connect()
    assert await rsa8.set_mode("GPSA_CHPOWER") == "GPSA_CHPOWER"
    assert ":INSTrument:SELect GPSA_CHPower" in i8.writes


async def test_channel_power_paths():
    dsa, dinst = make_driver(RigolDSA800, "DSA815")
    await dsa.connect()
    chp = await dsa.measure_channel_power(bandwidth=1e6)
    assert ":CONFigure:CHPower" in dinst.writes
    assert ":SENSe:CHPower:BANDwidth:INTegration 1000000" in dinst.writes
    assert chp["power"] == pytest.approx(-15.9948) and chp["density"] == pytest.approx(-79.00511)
    assert chp["method"] == "instrument"

    rsa8, _ = make_driver(RigolRSA800, "RSA814")
    await rsa8.connect()
    chp = await rsa8.measure_channel_power()
    assert chp["power"] == pytest.approx(-15.9948) and chp["method"] == "instrument"

    rsa5, _ = make_driver(RigolRSA5000, "RSA5065")
    await rsa5.connect()
    await rsa5.set_frequency(center=1e9, span=10e6)
    chp = await rsa5.measure_channel_power(bandwidth=1e6)
    assert chp["method"] == "trace_integration"
    # -20 dBm tone in a 1 MHz RBW, bin width 16.7 kHz -> the peak bin dominates
    assert -45 < chp["power"] < -30

    obw = await dsa.measure_obw(percent=99)
    assert obw["obw"] == 2e6 and obw["transmit_frequency_error"] == 1500.0


async def test_screenshot_support():
    rsa8, _ = make_driver(RigolRSA800, "RSA814")
    await rsa8.connect()
    img = await rsa8.get_screenshot()
    assert img[:2] == b"BM"
    dsa, _ = make_driver(RigolDSA800, "DSA815")
    await dsa.connect()
    with pytest.raises(ValueError):
        await dsa.get_screenshot()


async def test_dsa1000_input_impedance():
    sa, inst = make_driver(RigolDSA1000, "DSA1030A")
    await sa.connect()
    assert await sa.execute_command("set_input_impedance", {"ohms": 75}) == 75
    assert ":INPut:IMPedance 75" in inst.writes
    with pytest.raises(ValueError):
        await sa.set_input_impedance(600)
    assert (await sa.set_attenuation(50))["attenuation"] == 50.0  # DSA1000 goes to 50 dB


# --------------------------------------------------------------------------- #
# Acquisition / dispatch / state
# --------------------------------------------------------------------------- #


async def test_get_measurement_channels():
    sa, inst = make_driver(RigolDSA800, "DSA815")
    await sa.connect()
    peak = await sa.get_measurement("PEAK")
    assert peak["value"] == pytest.approx(PEAK_DBM) and peak["unit"] == "dBm"
    assert peak["frequency"] == pytest.approx(750e6)
    default = await sa.get_measurement()
    assert default["channel"] == "PEAK"
    pf = await sa.get_measurement("PEAK_FREQ")
    assert pf["value"] == pytest.approx(750e6) and pf["unit"] == "Hz"
    await sa.peak_search(1)
    m1 = await sa.get_measurement("MARKER1")
    assert m1["value"] == pytest.approx(PEAK_DBM)
    m1f = await sa.get_measurement("MARKER1_FREQ")
    assert m1f["value"] == pytest.approx(750e6)
    chp = await sa.get_measurement("CHPOWER")
    assert chp["value"] == pytest.approx(-15.9948)
    assert (await sa.get_measurement("TRACE1:MAX"))["value"] == pytest.approx(PEAK_DBM)
    assert (await sa.get_measurement("TRACE1:MIN"))["value"] == pytest.approx(NOISE)
    mean = (await sa.get_measurement("TRACE1:MEAN"))["value"]
    assert NOISE < mean < PEAK_DBM
    with pytest.raises(ValueError):
        await sa.get_measurement("MARKER9")
    with pytest.raises(ValueError):
        await sa.get_measurement("VOLTAGE")
    stream = await sa.get_measurements(1)
    assert stream["peak"] == pytest.approx(PEAK_DBM) and stream["num_points"] == POINTS


async def test_execute_command_dispatch_and_state():
    sa, inst = make_driver(RigolDSA800, "DSA832-TG")
    await sa.connect()
    readings = await sa.execute_command("get_readings", {})
    assert isinstance(readings, SpectrumData)
    f = await sa.execute_command("set_frequency", {"center": 433.92e6, "span": 2e6})
    assert f["center"] == 433.92e6
    m = await sa.execute_command("peak_search", {"marker": 2})
    assert m["marker"] == 2
    state = await sa.execute_command("get_state", {})
    assert state["frequency"]["center"] == 433.92e6
    assert state["bandwidth"]["rbw"] == 1e6
    assert state["amplitude"]["reference_level"] == 0.0
    assert state["sweep"]["points"] == POINTS
    assert state["detector"] == "POSITIVE" and state["trace1_mode"] == "WRITE"
    assert state["tracking_generator"] == {"enabled": False, "level": -20.0, "unit": "dBm"}
    assert state["data_format"] == "ASCII"
    err = await sa.execute_command("get_error", {})
    assert err["code"] == 0 and err["message"] == "No error"
    with pytest.raises(ValueError):
        await sa.execute_command("fly_to_the_moon", {})


async def test_rsa_state_includes_mode():
    sa, _ = make_driver(RigolRSA6000, "RSA6265")
    await sa.connect()
    state = await sa.get_state()
    assert state["mode"] == "SA"
    assert "tracking_generator" not in state  # RSA6265 (non-TG) row
