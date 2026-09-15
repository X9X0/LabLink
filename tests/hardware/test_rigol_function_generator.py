"""Tests for the Rigol DG function / arbitrary waveform generator drivers.

These run against a scripted fake VISA instrument that answers the SCPI the
programming guides document (classic DG1000Z-style tree and the Pro tree), so
no hardware is needed.
"""

import struct
import sys
from unittest.mock import MagicMock

import pytest

sys.path.append("..")

from equipment.rigol_function_generator import (  # noqa: E402
    MODEL_SPECS, RigolDG800, RigolDG800Pro, RigolDG900, RigolDG1000Z,
    RigolDG2000, RigolDG4000, RigolDG5000, RigolDG5000Pro, RigolDG6000,
    lookup_model_spec, normalize_waveform, parse_apply_response, parse_load)
from shared.models.data import FunctionGeneratorData  # noqa: E402
from shared.models.equipment import ConnectionType, EquipmentType  # noqa: E402


# --------------------------------------------------------------------------- #
# Scripted instrument
# --------------------------------------------------------------------------- #


class ScriptedDG:
    """Minimal Rigol DG SCPI simulator covering the classic and Pro trees."""

    APPLY_NAMES_CLASSIC = {"SINUSOID": "SIN", "SQUARE": "SQU", "RAMP": "RAMP", "PULSE": "PULSE",
                           "NOISE": "NOISE", "DC": "DC", "USER": "USER", "HARMONIC": "HARM"}
    APPLY_NAMES_PRO = {"SINUSOID": "SIN", "SQUARE": "SQU", "RAMP": "RAMP", "PULSE": "PULS",
                       "NOISE": "NOIS", "DC": "DC", "ARBITRARY": "ARB", "HARMONIC": "HARM"}

    def __init__(self, model="DG1062Z", channels=2):
        self.model = model
        self.pro = "PRO" in model.upper().replace(" ", "") or model.startswith("DG6")
        self.session = 1  # makes BaseEquipment._is_instrument_valid() happy
        self.timeout = 10000
        self.read_termination = None
        self.write_termination = None
        self.writes = []
        self.raw_writes = []
        self.queries = []
        self.channels = {
            n: {
                "wave": "SIN", "freq": 1000.0, "amp": 5.0, "offs": 0.0, "phase": 0.0,
                "unit": "VPP", "out": False, "load": 50.0, "pol": "NORMAL",
                "squ_duty": 50.0, "puls_duty": 50.0, "puls_width": 5e-4, "puls_lead": 2e-8,
                "puls_trail": 2e-8, "symm": 50.0,
                "mod_state": False, "mod_type": "AM", "am_depth": 100.0, "fm_dev": 1000.0,
                "pm_dev": 90.0, "mod_freq": 100.0, "mod_src": "INT",
                "mod_states": {t: False for t in ("AM", "FM", "PM", "ASKEY", "FSKEY", "PSKEY", "PWM")},
                "swe_state": False, "swe_time": 1.0, "swe_spac": "LIN", "fstart": 100.0, "fstop": 1000.0,
                "burst_state": False, "burst_mode": "TRIG", "ncyc": 1.0, "bper": 0.01, "bphase": 0.0,
                "arb_mode": "FREQ", "arb_srate": 1e6,
            }
            for n in range(1, channels + 1)
        }
        self.counter_state = "OFF"
        self.beeper = True
        self.aligned = 0
        self.triggered = 0

    def close(self):
        pass

    # -- helpers -----------------------------------------------------------
    def _bool(self, arg):
        return arg.upper() in ("ON", "1")

    def _fmt_bool(self, value):
        if self.pro:
            return "1" if value else "0"
        return "ON" if value else "OFF"

    def _sci(self, value):
        return f"{value:.6E}"

    @staticmethod
    def _split(cmd):
        head, _, arg = cmd.strip().partition(" ")
        return head.upper(), arg.strip()

    def _channel_of(self, head):
        for prefix in (":SOURCE", ":OUTPUT", ":TRIGGER"):
            if head.startswith(prefix):
                digits = ""
                for ch in head[len(prefix):]:
                    if ch.isdigit():
                        digits += ch
                    else:
                        break
                n = int(digits or "1")
                if n not in self.channels:
                    raise AssertionError(f"Channel {n} does not exist on {self.model}: {head}")
                return n, head[len(prefix) + len(digits):]
        return None, head

    # -- write ---------------------------------------------------------------
    def write(self, cmd):
        self.writes.append(cmd)
        head, arg = self._split(cmd)
        if head in ("*RST", "*CLS"):
            return
        if head == ":SYSTEM:BEEPER:STATE":
            self.beeper = self._bool(arg)
            return
        if head == ":SYSTEM:BEEPER":
            return
        if head == ":COUNTER:STATE":
            self.counter_state = "RUN" if self._bool(arg) else "OFF"
            return
        if head == ":TRACE:DATA":
            assert arg.startswith("VOLATILE,"), arg
            self.arb_values = [float(v) for v in arg[len("VOLATILE,"):].split(",")]
            self.channels[1]["wave"] = "USER"
            return
        n, tail = self._channel_of(head)
        if n is None:
            raise AssertionError(f"Unscripted write: {cmd}")
        st = self.channels[n]
        if head.startswith(":OUTPUT"):
            if tail in ("", ":STATE"):
                st["out"] = self._bool(arg)
            elif tail in (":LOAD", ":IMPEDANCE"):
                st["load"] = float("inf") if arg.upper().startswith("INF") else float(arg)
            elif tail == ":POLARITY":
                st["pol"] = "INVERTED" if arg.upper().startswith("INV") else "NORMAL"
            else:
                raise AssertionError(f"Unscripted output write: {cmd}")
            return
        if head.startswith(":TRIGGER"):
            assert self.pro and tail == ":IMMEDIATE", cmd
            self.triggered += 1
            return
        # :SOURce<n> tree
        if tail.startswith(":APPLY:"):
            name = tail[len(":APPLY:"):]
            names = self.APPLY_NAMES_PRO if self.pro else self.APPLY_NAMES_CLASSIC
            assert name in names, f"Unknown apply keyword {name} on {self.model}"
            st["wave"] = names[name]
            parts = [p.strip() for p in arg.split(",")] if arg else []
            if name == "DC":
                if len(parts) > 2 and parts[2].upper() != "DEF":
                    st["offs"] = float(parts[2])
            elif name == "NOISE" and not self.pro:
                if parts and parts[0].upper() != "DEF":
                    st["amp"] = float(parts[0])
                if len(parts) > 1 and parts[1].upper() != "DEF":
                    st["offs"] = float(parts[1])
            else:
                keys = ["freq", "amp", "offs", "phase"]
                for key, value in zip(keys, parts):
                    if value.upper() != "DEF":
                        st[key] = float(value)
            st["mod_state"] = st["swe_state"] = st["burst_state"] = False
            return
        if tail == ":FUNCTION":
            names = self.APPLY_NAMES_PRO if self.pro else self.APPLY_NAMES_CLASSIC
            key = arg.upper()
            if self.pro and key == "ARB":
                st["wave"] = "ARB"
            else:
                assert key in names, f"Unknown function keyword {arg}"
                st["wave"] = names[key]
            return
        simple = {
            ":FREQUENCY": "freq", ":VOLTAGE": "amp", ":VOLTAGE:OFFSET": "offs", ":PHASE": "phase",
            ":FUNCTION:SQUARE:DCYCLE": "squ_duty", ":FUNCTION:RAMP:SYMMETRY": "symm",
            ":SWEEP:TIME": "swe_time", ":FREQUENCY:START": "fstart", ":FREQUENCY:STOP": "fstop",
            ":BURST:INTERNAL:PERIOD": "bper", ":BURST:PHASE": "bphase",
            ":FUNCTION:ARBITRARY:SRATE": "arb_srate",
        }
        pulse_root = ":FUNCTION:PULSE" if self.pro else ":PULSE"
        simple.update({
            f"{pulse_root}:DCYCLE": "puls_duty", f"{pulse_root}:WIDTH": "puls_width",
            f"{pulse_root}:TRANSITION:LEADING": "puls_lead", f"{pulse_root}:TRANSITION:TRAILING": "puls_trail",
        })
        if tail in simple:
            st[simple[tail]] = float(arg)
            return
        if tail == ":BURST:NCYCLES":
            st["ncyc"] = float("inf") if arg.upper().startswith("INF") else float(arg)
            return
        if tail == ":VOLTAGE:UNIT":
            assert arg.upper() in ("VPP", "VRMS", "DBM")
            st["unit"] = arg.upper()
            return
        if tail == ":SWEEP:STATE":
            st["swe_state"] = self._bool(arg)
            return
        if tail == ":SWEEP:SPACING":
            st["swe_spac"] = arg.upper()[:3]
            return
        if tail == ":BURST:STATE":
            st["burst_state"] = self._bool(arg)
            return
        if tail == ":BURST:MODE":
            key = arg.upper()
            if self.pro:
                assert key in ("TRIGGERED", "GATED"), f"Pro burst mode {arg}"
            else:
                assert key in ("TRIGGERED", "INFINITY", "GATED"), f"Burst mode {arg}"
            st["burst_mode"] = key[:3] if key != "TRIGGERED" else "TRIG"
            return
        if tail == ":BURST:TRIGGER":
            assert not self.pro, "Pro uses :TRIGger<n>"
            self.triggered += 1
            return
        if tail in (":PHASE:SYNCHRONIZE", ":PHASE:INITIATE"):
            if self.model.startswith(("DG4", "DG5")) and not self.pro:
                assert tail == ":PHASE:INITIATE", "DG4000/DG5000 only document :PHASe:INITiate"
            if self.pro:
                assert tail == ":PHASE:SYNCHRONIZE", "Pro only documents :PHASe:SYNChronize"
            self.aligned += 1
            return
        if tail == ":FUNCTION:ARBITRARY:MODE":
            st["arb_mode"] = arg.upper()
            return
        if tail == ":TRACE:DATA":
            assert not self.pro
            assert arg.startswith("VOLATILE,"), arg
            self.arb_values = [float(v) for v in arg[len("VOLATILE,"):].split(",")]
            self.arb_channel = n
            st["wave"] = "USER"
            return
        if tail == ":TRACE:DATA:DAC16":
            assert self.pro, "text DAC16 is Pro only; classic tree uses a binary block"
            kind, flag, data = arg.split(",", 2)
            assert kind.upper() == "VOLTAGE"
            assert flag.upper() in ("HEADER", "CONTINUE", "END")
            self.raw_writes.append((flag.upper(), [float(v) for v in data.split(",")]))
            return
        # Modulation (classic: :MOD:..., Pro: :AM:... per type)
        mod_tail = tail
        if not self.pro:
            assert mod_tail.startswith(":MOD"), f"Classic tree needs :MOD node: {cmd}"
            mod_tail = mod_tail[len(":MOD"):]
            if mod_tail == ":STATE":
                st["mod_state"] = self._bool(arg)
                return
            if mod_tail == ":TYPE":
                assert arg.upper() in ("AM", "FM", "PM", "ASK", "FSK", "PSK", "PWM")
                st["mod_type"] = arg.upper()
                return
        else:
            assert not tail.startswith(":MOD"), f"Pro tree has no :MOD node: {cmd}"
        parts = mod_tail.lstrip(":").split(":")
        mtype = parts[0]
        assert mtype in ("AM", "FM", "PM", "ASKEY", "FSKEY", "PSKEY", "PWM"), f"Unscripted write: {cmd}"
        rest = ":".join(parts[1:])
        if rest == "STATE":
            assert self.pro
            for k in st["mod_states"]:
                st["mod_states"][k] = False
            st["mod_states"][mtype] = self._bool(arg)
            return
        if rest == "DEPTH":
            st["am_depth"] = float(arg)
        elif rest == "DEVIATION" and mtype == "FM":
            st["fm_dev"] = float(arg)
        elif rest == "DEVIATION" and mtype == "PM":
            st["pm_dev"] = float(arg)
        elif rest == "DEVIATION:DCYCLE":
            st["pwm_dev"] = float(arg)
        elif rest in ("INTERNAL:FREQUENCY", "INTERNAL:RATE"):
            st["mod_freq"] = float(arg)
        elif rest == "SOURCE":
            st["mod_src"] = arg.upper()[:3]
        elif rest == "INTERNAL:FUNCTION":
            st["mod_shape"] = arg.upper()
        else:
            raise AssertionError(f"Unscripted modulation write: {cmd}")

    def write_raw(self, payload):
        """Binary DAC16 blocks: header ASCII, '#<d><len>', data, newline."""
        self.raw_writes.append(payload)
        head, _, rest = payload.partition(b",")
        head = head.decode()
        assert head.upper().endswith(":TRACE:DATA:DAC16 VOLATILE"), head
        flag, _, block = rest.partition(b",")
        assert flag in (b"CON", b"END"), flag
        assert block[:1] == b"#"
        ndigits = int(block[1:2])
        length = int(block[2:2 + ndigits])
        data = block[2 + ndigits:2 + ndigits + length]
        assert len(data) == length, (len(data), length)
        assert block[2 + ndigits + length:] == b"\n"
        codes = struct.unpack(f"<{length // 2}H", data)
        assert all(0 <= c <= 0x3FFF for c in codes)
        self.dac16_codes = getattr(self, "dac16_codes", []) + list(codes)
        if flag == b"END":
            self.channels[1]["wave"] = "USER"

    # -- query ---------------------------------------------------------------
    def query(self, cmd):
        self.queries.append(cmd)
        head, arg = self._split(cmd)
        if head == "*IDN?":
            if self.pro:
                return f"RIGOL TECHNOLOGIES,{self.model},DG8A000000001,00.01.02"
            return f"Rigol Technologies,{self.model},DG1ZA000000001,00.01.03"
        if head == "*TST?":
            return "0"
        if head == ":SYSTEM:ERROR?":
            return '0,"No error"'
        if head == ":SYSTEM:BEEPER:STATE?":
            return self._fmt_bool(self.beeper)
        if head == ":COUNTER:STATE?":
            if self.pro:
                return "1" if self.counter_state != "OFF" else "0"
            return self.counter_state
        if head == ":COUNTER:MEASURE?":
            if self.counter_state == "OFF":
                return ",".join(["0.000000000E+00"] * 5)
            return "2.000000000E+03,5.000000000E-04,4.760800000E+01,2.380415000E-04,2.619585000E-04"
        n, tail = self._channel_of(head)
        if n is None:
            raise AssertionError(f"Unscripted query: {cmd}")
        st = self.channels[n]
        if head.startswith(":OUTPUT"):
            if tail in ("?", ":STATE?"):
                return self._fmt_bool(st["out"])
            if tail in (":LOAD?", ":IMPEDANCE?"):
                if st["load"] == float("inf"):
                    return "INFINITY" if self.model.startswith(("DG4", "DG5")) and not self.pro else "9.900000E+37"
                return self._sci(st["load"])
            if tail == ":POLARITY?":
                return st["pol"]
            raise AssertionError(f"Unscripted output query: {cmd}")
        if tail == ":APPLY?":
            wave = st["wave"]
            if wave in ("DC",):
                return f'"DC,DEF,DEF,{self._sci(st["offs"])},DEF"'
            if wave in ("NOISE", "NOIS"):
                return f'"{wave},DEF,{self._sci(st["amp"])},{self._sci(st["offs"])},DEF"'
            return f'"{wave},{self._sci(st["freq"])},{self._sci(st["amp"])},{self._sci(st["offs"])},{self._sci(st["phase"])}"'
        if tail == ":FUNCTION?":
            return st["wave"]
        simple = {
            ":FREQUENCY?": "freq", ":VOLTAGE?": "amp", ":VOLTAGE:OFFSET?": "offs", ":PHASE?": "phase",
            ":FUNCTION:SQUARE:DCYCLE?": "squ_duty", ":FUNCTION:RAMP:SYMMETRY?": "symm",
            ":SWEEP:TIME?": "swe_time", ":FREQUENCY:START?": "fstart", ":FREQUENCY:STOP?": "fstop",
            ":BURST:INTERNAL:PERIOD?": "bper", ":BURST:PHASE?": "bphase", ":BURST:NCYCLES?": "ncyc",
            ":FUNCTION:ARBITRARY:SRATE?": "arb_srate",
        }
        pulse_root = ":FUNCTION:PULSE" if self.pro else ":PULSE"
        simple.update({
            f"{pulse_root}:DCYCLE?": "puls_duty", f"{pulse_root}:WIDTH?": "puls_width",
            f"{pulse_root}:TRANSITION:LEADING?": "puls_lead", f"{pulse_root}:TRANSITION:TRAILING?": "puls_trail",
        })
        if tail in simple:
            value = st[simple[tail]]
            return "9.900000E+37" if value == float("inf") else self._sci(value)
        if tail == ":VOLTAGE:UNIT?":
            return st["unit"]
        if tail == ":SWEEP:STATE?":
            return self._fmt_bool(st["swe_state"])
        if tail == ":SWEEP:SPACING?":
            return st["swe_spac"]
        if tail == ":BURST:STATE?":
            return self._fmt_bool(st["burst_state"])
        if tail == ":BURST:MODE?":
            return st["burst_mode"]
        mod_tail = tail
        if not self.pro:
            assert mod_tail.startswith(":MOD"), f"Unscripted query: {cmd}"
            mod_tail = mod_tail[len(":MOD"):]
            if mod_tail == ":STATE?":
                return self._fmt_bool(st["mod_state"])
            if mod_tail == ":TYPE?":
                return st["mod_type"]
        parts = mod_tail.lstrip(":").split(":")
        mtype = parts[0]
        rest = ":".join(parts[1:])
        if mtype in st["mod_states"]:
            if rest == "STATE?":
                assert self.pro
                return self._fmt_bool(st["mod_states"][mtype])
            if rest == "DEPTH?":
                return self._sci(st["am_depth"])
            if rest == "DEVIATION?":
                return self._sci(st["fm_dev"] if mtype == "FM" else st["pm_dev"])
            if rest == "DEVIATION:DCYCLE?":
                return self._sci(st.get("pwm_dev", 20.0))
            if rest == "INTERNAL:FREQUENCY?":
                return self._sci(st["mod_freq"])
        raise AssertionError(f"Unscripted query: {cmd}")


def make_driver(cls, model, resource="USB0::0x1AB1::0x0642::DG1ZA000000001::INSTR", channels=None):
    if channels is None:
        spec = lookup_model_spec(model)
        channels = spec.channels if spec else 2
    inst = ScriptedDG(model, channels)
    rm = MagicMock()
    rm.open_resource = MagicMock(return_value=inst)
    return cls(rm, resource), inst


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #


def test_normalize_waveform_aliases():
    assert normalize_waveform("sine") == "SIN"
    assert normalize_waveform("PULSE") == "PULS"
    assert normalize_waveform("user") == "ARB"
    assert normalize_waveform("NOISE") == "NOIS"
    assert normalize_waveform("Triangle") == "RAMP"
    with pytest.raises(ValueError):
        normalize_waveform("SAWTOOTH_OF_DOOM")


def test_parse_apply_response():
    r = parse_apply_response('"SQU,1.000000E+03,2.000000E+00,3.000000E+00,4.000000E+00"')
    assert r == {"waveform": "SQU", "frequency": 1000.0, "amplitude": 2.0, "offset": 3.0, "phase": 4.0}
    r = parse_apply_response('"NOISE,DEF,5.000000E+00,0.000000E+00,DEF"')
    assert r["waveform"] == "NOIS" and r["frequency"] is None and r["phase"] is None
    r = parse_apply_response('"SIN,+5.000000000000000E+03,+3.0000000000000E+00,-3.0000000000000E+00,+4.0000000000000E+00"')
    assert r["frequency"] == pytest.approx(5000.0) and r["offset"] == pytest.approx(-3.0)


def test_parse_load():
    assert parse_load("5.000000E+01") == "50"
    assert parse_load("9.900000E+37") == "INF"
    assert parse_load("INFINITY") == "INF"
    assert parse_load("+1.000000000000000E+02") == "100"


def test_model_table_covers_every_model():
    expected = {
        "DG811", "DG812", "DG821", "DG822", "DG831", "DG832", "DG952", "DG972", "DG992",
        "DG1022Z", "DG1032Z", "DG1062Z", "DG2052", "DG2072", "DG2102",
        "DG4062", "DG4102", "DG4162", "DG4202",
        "DG5071", "DG5072", "DG5101", "DG5102", "DG5251", "DG5252", "DG5351", "DG5352",
        "DG821PRO", "DG822PRO", "DG852PRO", "DG902PRO", "DG912PRO", "DG922PRO",
        "DG5252PRO", "DG5254PRO", "DG5258PRO", "DG5352PRO", "DG5354PRO", "DG5358PRO",
        "DG5502PRO", "DG5504PRO", "DG5508PRO", "DG6052", "DG6054", "DG6102", "DG6104",
    }
    assert expected <= set(MODEL_SPECS)
    assert lookup_model_spec("DG822 Pro").channels == 2
    assert lookup_model_spec("DG821 Pro").channels == 1
    assert lookup_model_spec("DG5258 Pro").channels == 8
    assert lookup_model_spec("DG5351").channels == 1
    assert lookup_model_spec("DG1062Z").max_frequency["SIN"] == 60e6
    assert lookup_model_spec("DG4202").max_frequency["SIN"] == 200e6
    assert MODEL_SPECS["DG1062Z"].max_amplitude(1e6, False) == 10.0
    assert MODEL_SPECS["DG1062Z"].max_amplitude(50e6, False) == 2.5
    assert MODEL_SPECS["DG1062Z"].max_amplitude(1e6, True) == 20.0


# --------------------------------------------------------------------------- #
# Identification
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cls,model,channels,max_sine,has_counter",
    [
        (RigolDG800, "DG832", 2, 35e6, True),
        (RigolDG800, "DG811", 1, 10e6, True),
        (RigolDG900, "DG992", 2, 100e6, True),
        (RigolDG1000Z, "DG1062Z", 2, 60e6, True),
        (RigolDG1000Z, "DG1022Z", 2, 25e6, True),
        (RigolDG2000, "DG2072", 2, 70e6, True),
        (RigolDG4000, "DG4162", 2, 160e6, True),
        (RigolDG5000, "DG5352", 2, 350e6, False),
        (RigolDG5000, "DG5071", 1, 70e6, False),
        (RigolDG800Pro, "DG822 Pro", 2, 25e6, True),
        (RigolDG800Pro, "DG912 Pro", 2, 150e6, True),
        (RigolDG5000Pro, "DG5504 Pro", 4, 500e6, False),
        (RigolDG6000, "DG6104", 4, 1e9, False),
    ],
)
async def test_identification(cls, model, channels, max_sine, has_counter):
    gen, inst = make_driver(cls, model)
    await gen.connect()
    assert gen.connected is True

    info = await gen.get_info()
    assert info.type == EquipmentType.FUNCTION_GENERATOR
    assert info.id.startswith("fgen_")
    assert info.manufacturer.upper() == "RIGOL TECHNOLOGIES"
    assert info.model == model
    assert info.connection_type == ConnectionType.USB

    status = await gen.get_status()
    assert status.connected is True
    caps = status.capabilities
    assert caps["channels"] == channels
    assert caps["max_frequency"]["SIN"] == max_sine
    assert caps["has_counter"] is has_counter
    assert caps["supports_acquisition"] is True
    assert set(caps["outputs"]) == set(range(1, channels + 1))
    assert gen.spec is MODEL_SPECS[model.upper().replace(" ", "")]


@pytest.mark.asyncio
async def test_unknown_model_falls_back_to_family_default():
    gen, inst = make_driver(RigolDG1000Z, "DG1099Z", channels=2)
    await gen.connect()
    assert gen.spec is MODEL_SPECS["DG1062Z"]


# --------------------------------------------------------------------------- #
# Apply / setters / readings
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_apply_and_readings():
    gen, inst = make_driver(RigolDG1000Z, "DG1062Z")
    await gen.connect()
    data = await gen.apply(channel=1, waveform="square", frequency=1e3, amplitude=2.0, offset=0.5, phase=10)
    assert ":SOURce1:APPLy:SQUare 1000,2,0.5,10" in inst.writes
    assert isinstance(data, FunctionGeneratorData)
    assert data.channel == 1
    assert data.waveform == "SQU"
    assert data.frequency == pytest.approx(1000.0)
    assert data.amplitude == pytest.approx(2.0)
    assert data.amplitude_unit == "VPP"
    assert data.offset == pytest.approx(0.5)
    assert data.phase == pytest.approx(10.0)
    assert data.output_enabled is False
    assert data.load_impedance == "50"
    assert data.duty_cycle == pytest.approx(50.0)
    assert data.modulation is None
    assert data.sweep_enabled is False and data.burst_enabled is False

    # Omitted parameters are sent as DEF; DC and noise use their own argument shapes.
    await gen.apply(channel=2, waveform="sin", frequency=5e6)
    assert ":SOURce2:APPLy:SINusoid 5000000,DEF,DEF,DEF" in inst.writes
    dc = await gen.apply(channel=2, waveform="DC", offset=1.5)
    assert ":SOURce2:APPLy:DC 1,1,1.5" in inst.writes
    assert dc.waveform == "DC" and dc.offset == pytest.approx(1.5) and dc.frequency is None
    noise = await gen.apply(channel=1, waveform="noise", amplitude=1.0, offset=0.0)
    assert ":SOURce1:APPLy:NOISe 1,0" in inst.writes
    assert noise.waveform == "NOIS" and noise.frequency is None
    arb = await gen.apply(channel=1, waveform="arb", frequency=1e3)
    assert ":SOURce1:APPLy:USER 1000,DEF,DEF,DEF" in inst.writes
    assert arb.waveform == "ARB"
    ramp = await gen.apply(channel=1, waveform="ramp", frequency=100)
    assert ramp.symmetry == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_individual_setters():
    gen, inst = make_driver(RigolDG1000Z, "DG1062Z")
    await gen.connect()
    assert await gen.set_waveform("PULSE", channel=2) == "PULS"
    assert ":SOURce2:FUNCtion PULSe" in inst.writes
    assert await gen.set_frequency(2.5e6, channel=2) == pytest.approx(2.5e6)
    assert ":SOURce2:FREQuency 2500000" in inst.writes
    assert await gen.set_amplitude(1.25, channel=2) == pytest.approx(1.25)
    assert ":SOURce2:VOLTage 1.25" in inst.writes
    assert await gen.set_amplitude(0.5, unit="vrms", channel=2) == pytest.approx(0.5)
    assert ":SOURce2:VOLTage:UNIT VRMS" in inst.writes
    assert await gen.get_amplitude_unit(2) == "VRMS"
    assert await gen.set_offset(-0.25, channel=2) == pytest.approx(-0.25)
    assert ":SOURce2:VOLTage:OFFSet -0.25" in inst.writes
    assert await gen.set_phase(90, channel=2) == pytest.approx(90.0)
    assert ":SOURce2:PHASe 90" in inst.writes
    # Pulse channel -> :PULSe:DCYCle; square channel -> :FUNCtion:SQUare:DCYCle
    assert await gen.set_duty_cycle(25, channel=2) == pytest.approx(25.0)
    assert ":SOURce2:PULSe:DCYCle 25" in inst.writes
    await gen.set_waveform("SQU", channel=1)
    assert await gen.set_duty_cycle(40, channel=1) == pytest.approx(40.0)
    assert ":SOURce1:FUNCtion:SQUare:DCYCle 40" in inst.writes
    with pytest.raises(ValueError):
        await gen.set_duty_cycle(40, channel=1, waveform="SIN")
    assert await gen.set_symmetry(75, channel=1) == pytest.approx(75.0)
    assert ":SOURce1:FUNCtion:RAMP:SYMMetry 75" in inst.writes
    pulse = await gen.set_pulse(width=1e-6, rise_time=2e-8, fall_time=3e-8, channel=2)
    assert ":SOURce2:PULSe:WIDTh 1e-06" in inst.writes
    assert ":SOURce2:PULSe:TRANsition:LEADing 2e-08" in inst.writes
    assert ":SOURce2:PULSe:TRANsition:TRAiling 3e-08" in inst.writes
    assert pulse["width"] == pytest.approx(1e-6) and pulse["fall_time"] == pytest.approx(3e-8)


@pytest.mark.asyncio
async def test_output_load_polarity():
    gen, inst = make_driver(RigolDG1000Z, "DG1062Z")
    await gen.connect()
    assert await gen.set_output(True, channel=2) is True
    assert ":OUTPut2 ON" in inst.writes
    assert await gen.set_output(False, channel=2) is False
    assert ":OUTPut2 OFF" in inst.writes
    assert await gen.set_load("HighZ", channel=1) == "INF"
    assert ":OUTPut1:LOAD INFinity" in inst.writes
    assert await gen.set_load(75, channel=1) == "75"
    assert ":OUTPut1:LOAD 75" in inst.writes
    with pytest.raises(ValueError):
        await gen.set_load(20000, channel=1)
    assert await gen.set_polarity("inverted", channel=1) == "INVERTED"
    assert ":OUTPut1:POLarity INVerted" in inst.writes
    # dBm is refused into HighZ
    await gen.set_load("INF", channel=2)
    with pytest.raises(ValueError):
        await gen.set_amplitude_unit("DBM", channel=2)


@pytest.mark.asyncio
async def test_channel_validation():
    gen, inst = make_driver(RigolDG800, "DG811")
    await gen.connect()
    assert await gen.set_frequency(1e3, channel="CH1") == pytest.approx(1e3)
    with pytest.raises(ValueError):
        await gen.set_frequency(1e3, channel=2)
    with pytest.raises(ValueError):
        await gen.set_output(True, channel="CH3")


# --------------------------------------------------------------------------- #
# Modulation / sweep / burst
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_modulation_classic_tree():
    gen, inst = make_driver(RigolDG1000Z, "DG1062Z")
    await gen.connect()
    mod = await gen.set_modulation(True, "AM", depth=50, frequency=200, source="internal", shape="sine")
    assert ":SOURce1:MOD:TYPe AM" in inst.writes
    assert ":SOURce1:MOD:AM:DEPTh 50" in inst.writes
    assert ":SOURce1:MOD:AM:INTernal:FREQuency 200" in inst.writes
    assert ":SOURce1:MOD:AM:SOURce INTernal" in inst.writes
    assert ":SOURce1:MOD:AM:INTernal:FUNCtion SINusoid" in inst.writes
    assert ":SOURce1:MOD:STATe ON" in inst.writes
    assert mod == {"enabled": True, "type": "AM", "depth": 50.0, "frequency": 200.0}

    mod = await gen.set_modulation(True, "FM", deviation=5e3, channel=2)
    assert ":SOURce2:MOD:FM:DEViation 5000" in inst.writes
    assert mod["type"] == "FM" and mod["deviation"] == pytest.approx(5000.0)
    readings = await gen.get_readings(2)
    assert readings.modulation == "FM"

    mod = await gen.set_modulation(False, "FM", channel=2)
    assert ":SOURce2:MOD:STATe OFF" in inst.writes
    assert mod["enabled"] is False
    with pytest.raises(ValueError):
        await gen.set_modulation(True, "AM", depth=150)
    with pytest.raises(ValueError):
        await gen.set_modulation(True, "QAM")
    with pytest.raises(ValueError):
        await gen.set_modulation(True, "FM", depth=50)


@pytest.mark.asyncio
async def test_sweep_and_burst_classic_tree():
    gen, inst = make_driver(RigolDG1000Z, "DG1062Z")
    await gen.connect()
    sweep = await gen.set_sweep(True, start=1e3, stop=1e5, time=2.5, spacing="log")
    assert ":SOURce1:FREQuency:STARt 1000" in inst.writes
    assert ":SOURce1:FREQuency:STOP 100000" in inst.writes
    assert ":SOURce1:SWEep:TIME 2.5" in inst.writes
    assert ":SOURce1:SWEep:SPACing LOGarithmic" in inst.writes
    assert ":SOURce1:SWEep:STATe ON" in inst.writes
    assert sweep["enabled"] is True and sweep["start"] == 1000.0 and sweep["spacing"] == "LOG"
    assert (await gen.get_readings(1)).sweep_enabled is True

    burst = await gen.set_burst(True, mode="ncycle", cycles=10, period=0.05, phase=45, channel=2)
    assert ":SOURce2:BURSt:MODE TRIGgered" in inst.writes
    assert ":SOURce2:BURSt:NCYCles 10" in inst.writes
    assert ":SOURce2:BURSt:INTernal:PERiod 0.05" in inst.writes
    assert ":SOURce2:BURSt:PHASe 45" in inst.writes
    assert ":SOURce2:BURSt:STATe ON" in inst.writes
    assert burst == {"enabled": True, "mode": "TRIG", "cycles": 10, "period": 0.05, "phase": 45.0}
    assert (await gen.get_readings(2)).burst_enabled is True
    await gen.set_burst(True, mode="infinity", channel=2)
    assert ":SOURce2:BURSt:MODE INFinity" in inst.writes
    await gen.trigger_burst(2)
    assert ":SOURce2:BURSt:TRIGger" in inst.writes
    assert inst.triggered == 1
    with pytest.raises(ValueError):
        await gen.set_burst(True, cycles=0)
    with pytest.raises(ValueError):
        await gen.set_sweep(True, spacing="SPIRAL")


# --------------------------------------------------------------------------- #
# Arbitrary upload
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_upload_arbitrary_float_dg1000z():
    gen, inst = make_driver(RigolDG1000Z, "DG1062Z")
    await gen.connect()
    points = [-1.0, -0.5, 0.0, 0.5, 1.0, 0.5, 0.0, -0.5]
    result = await gen.upload_arbitrary(points, channel=2)
    assert inst.writes[-1] == ":SOURce2:TRACe:DATA VOLATILE,-1,-0.5,0,0.5,1,0.5,0,-0.5"
    assert inst.arb_values == points and inst.arb_channel == 2
    assert result == {"channel": 2, "points": 8, "format": "FLOAT", "packets": 1, "name": "VOLATILE"}
    # Values are clipped to -1..1
    await gen.upload_arbitrary([2.0] * 4 + [-3.0] * 4, channel=1)
    assert inst.arb_values == [1.0] * 4 + [-1.0] * 4
    with pytest.raises(ValueError):
        await gen.upload_arbitrary([0.0] * 4)  # fewer than 8 points
    with pytest.raises(ValueError):
        await gen.upload_arbitrary([0.0] * 20000)  # more than one :DATA command allows
    with pytest.raises(ValueError):
        await gen.upload_arbitrary([0.0, float("nan")] * 4)
    # Sample-rate mode is a DG1000Z feature
    assert await gen.set_arb_sample_rate(1e6, channel=1) == pytest.approx(1e6)
    assert ":SOURce1:FUNCtion:ARBitrary:MODE SRATe" in inst.writes
    assert ":SOURce1:FUNCtion:ARBitrary:SRATe 1000000" in inst.writes


@pytest.mark.asyncio
async def test_upload_arbitrary_dac16_dg800():
    gen, inst = make_driver(RigolDG800, "DG832")
    await gen.connect()
    points = [-1.0, 0.0, 1.0, 0.0] * 2
    result = await gen.upload_arbitrary(points, channel=1)
    assert result["format"] == "DAC16" and result["packets"] == 1
    assert len(inst.raw_writes) == 1
    payload = inst.raw_writes[0]
    assert payload.startswith(b":SOURce1:TRACe:DATA:DAC16 VOLATILE,END,#216")
    assert inst.dac16_codes == [0, 0x2000, 0x3FFF, 0x2000] * 2
    # Fewer than 8 points are padded; more than 16 kpts are split into CON/END packets.
    inst.dac16_codes = []
    result = await gen.upload_arbitrary([0.5, -0.5], channel=2)
    assert len(inst.dac16_codes) == 8
    assert inst.raw_writes[-1].startswith(b":SOURce2:TRACe:DATA:DAC16 VOLATILE,END,")
    inst.dac16_codes = []
    result = await gen.upload_arbitrary([0.0] * 20000, channel=1)
    assert result["packets"] == 2
    assert inst.raw_writes[-2].startswith(b":SOURce1:TRACe:DATA:DAC16 VOLATILE,CON,#532768")
    assert inst.raw_writes[-1].startswith(b":SOURce1:TRACe:DATA:DAC16 VOLATILE,END,#47232")
    assert len(inst.dac16_codes) == 20000
    with pytest.raises(ValueError):
        await gen.set_arb_sample_rate(1e6)


@pytest.mark.asyncio
async def test_upload_arbitrary_dg4000_has_no_channel_node():
    gen, inst = make_driver(RigolDG4000, "DG4162")
    await gen.connect()
    await gen.upload_arbitrary([0.25, -0.25], channel=1)
    assert inst.writes[-1] == ":TRACe:DATA VOLATILE,0.25,-0.25"
    with pytest.raises(ValueError):
        await gen.upload_arbitrary([0.0] * 16385)  # 16 kpts memory


# --------------------------------------------------------------------------- #
# Limits validation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_frequency_limits_per_model_and_waveform():
    gen, inst = make_driver(RigolDG1000Z, "DG1022Z")
    await gen.connect()
    with pytest.raises(ValueError, match="25e\\+06|2.5e\\+07"):
        await gen.apply(waveform="SIN", frequency=30e6)
    with pytest.raises(ValueError):
        await gen.apply(waveform="RAMP", frequency=600e3)  # ramp stops at 500 kHz
    await gen.apply(waveform="RAMP", frequency=400e3)
    with pytest.raises(ValueError):
        await gen.set_frequency(0)  # below 1 uHz
    # set_frequency validates against the *current* waveform
    await gen.set_waveform("PULS")
    with pytest.raises(ValueError):
        await gen.set_frequency(20e6)  # pulse stops at 15 MHz on DG1022Z
    big, _ = make_driver(RigolDG1000Z, "DG1062Z")
    await big.connect()
    await big.apply(waveform="SIN", frequency=60e6)
    with pytest.raises(ValueError):
        await big.apply(waveform="SIN", frequency=61e6)


@pytest.mark.asyncio
async def test_amplitude_limits_follow_frequency_and_load():
    gen, inst = make_driver(RigolDG1000Z, "DG1062Z")
    await gen.connect()
    await gen.apply(waveform="SIN", frequency=1e6, amplitude=10.0)       # <=10 MHz: 10 Vpp
    with pytest.raises(ValueError):
        await gen.apply(waveform="SIN", frequency=1e6, amplitude=10.5)
    with pytest.raises(ValueError):
        await gen.apply(waveform="SIN", frequency=20e6, amplitude=6.0)   # <=30 MHz: 5 Vpp
    with pytest.raises(ValueError):
        await gen.apply(waveform="SIN", frequency=50e6, amplitude=3.0)   # <=60 MHz: 2.5 Vpp
    with pytest.raises(ValueError):
        await gen.set_amplitude(0.001)                                   # below 2 mVpp
    # HighZ doubles the limit
    await gen.set_load("INF")
    await gen.apply(waveform="SIN", frequency=1e6, amplitude=20.0)
    with pytest.raises(ValueError):
        await gen.apply(waveform="SIN", frequency=1e6, amplitude=21.0)
    with pytest.raises(ValueError):
        await gen.set_offset(11.0)
    # Vrms values are not range-checked against the Vpp table
    await gen.set_load(50)
    await gen.set_amplitude_unit("VRMS")
    await gen.set_amplitude(3.5)
    with pytest.raises(ValueError):
        await gen.set_phase(400)


@pytest.mark.asyncio
async def test_model_differences_dg4000_vs_dg1000z():
    dg4, i4 = make_driver(RigolDG4000, "DG4202")
    dg1, i1 = make_driver(RigolDG1000Z, "DG1062Z")
    await dg4.connect()
    await dg1.connect()
    # Align phase command differs
    await dg4.sync_phase()
    assert ":SOURce1:PHASe:INITiate" in i4.writes
    await dg1.sync_phase(2)
    assert ":SOURce2:PHASe:SYNChronize" in i1.writes
    # DG4000 :APPLy:PULSe has no <phase> argument
    await dg4.apply(waveform="PULSE", frequency=1e3, amplitude=1.0, offset=0.0, phase=0.0)
    assert ":SOURce1:APPLy:PULSe 1000,1,0" in i4.writes
    await dg1.apply(waveform="PULSE", frequency=1e3, amplitude=1.0, offset=0.0, phase=0.0)
    assert ":SOURce1:APPLy:PULSe 1000,1,0,0" in i1.writes
    # DG4000 amplitude tiers and frequency range
    await dg4.apply(waveform="SIN", frequency=150e6, amplitude=1.0)
    with pytest.raises(ValueError):
        await dg4.apply(waveform="SIN", frequency=150e6, amplitude=2.0)
    # DG4000/DG5000 answer INFINITY for HighZ
    assert await dg4.set_load("INF") == "INF"
    # DG5000 has no counter
    dg5, _ = make_driver(RigolDG5000, "DG5352")
    await dg5.connect()
    with pytest.raises(ValueError):
        await dg5.get_counter()


# --------------------------------------------------------------------------- #
# Pro platform
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pro_platform_commands():
    gen, inst = make_driver(RigolDG800Pro, "DG852 Pro")
    await gen.connect()
    data = await gen.apply(channel=1, waveform="arb", frequency=100, amplitude=1, offset=2, phase=3)
    assert ":SOURce1:APPLy:ARBitrary 100,1,2,3" in inst.writes
    assert data.waveform == "ARB" and data.frequency == pytest.approx(100.0)
    await gen.apply(channel=2, waveform="noise", amplitude=1.0, offset=0.0)
    assert ":SOURce2:APPLy:NOISe DEF,1,0" in inst.writes
    await gen.apply(channel=2, waveform="dc", offset=0.7)
    assert ":SOURce2:APPLy:DC DEF,DEF,0.7" in inst.writes
    assert await gen.set_waveform("ARB", channel=2) == "ARB"
    assert ":SOURce2:FUNCtion ARB" in inst.writes
    # Output query answers 0/1 on the Pro platform
    assert await gen.set_output(True, channel=1) is True
    assert await gen.set_output(False, channel=1) is False
    assert await gen.set_load("INF", channel=1) == "INF"
    # Pulse tree lives under :FUNCtion:PULSe
    await gen.set_pulse(width=2e-6, duty_cycle=30, channel=1)
    assert ":SOURce1:FUNCtion:PULSe:WIDTh 2e-06" in inst.writes
    assert ":SOURce1:FUNCtion:PULSe:DCYCle 30" in inst.writes
    # Modulation is per type, no :MOD node
    mod = await gen.set_modulation(True, "FM", deviation=1e3, frequency=50, channel=1)
    assert ":SOURce1:FM:DEViation 1000" in inst.writes
    assert ":SOURce1:FM:INTernal:FREQuency 50" in inst.writes
    assert ":SOURce1:FM:STATe ON" in inst.writes
    assert not any(":MOD" in w for w in inst.writes)
    assert mod["enabled"] is True and mod["type"] == "FM" and mod["deviation"] == pytest.approx(1000.0)
    assert (await gen.get_readings(1)).modulation == "FM"
    await gen.set_modulation(False, "FM", channel=1)
    assert ":SOURce1:FM:STATe OFF" in inst.writes
    assert (await gen.get_modulation(1))["enabled"] is False
    # Burst: no INFinity mode, manual trigger via :TRIGger<n>
    await gen.set_burst(True, mode="INF", channel=2)
    assert ":SOURce2:BURSt:MODE TRIGgered" in inst.writes
    assert ":SOURce2:BURSt:NCYCles INFinity" in inst.writes
    await gen.trigger_burst(2)
    assert ":TRIGger2:IMMediate" in inst.writes
    # Align phase
    await gen.sync_phase()
    assert ":SOURce1:PHASe:SYNChronize" in inst.writes
    # Counter uses the same query, state answers 0/1
    await gen.set_counter(True)
    counter = await gen.get_counter()
    assert counter["enabled"] is True and counter["frequency"] == pytest.approx(2000.0)
    # Sweep is shared with the classic tree
    sweep = await gen.set_sweep(True, start=10, stop=100, time=1, spacing="step", channel=1)
    assert ":SOURce1:SWEep:SPACing STEp" in inst.writes
    assert sweep["enabled"] is True


@pytest.mark.asyncio
async def test_pro_arbitrary_upload_is_chunked_text():
    gen, inst = make_driver(RigolDG800Pro, "DG852 Pro")
    await gen.connect()
    result = await gen.upload_arbitrary([0.1, -0.1, 0.2], channel=2)
    assert inst.writes[-1] == ":SOURce2:TRACe:DATA:DAC16 VOLTage,END,0.1,-0.1,0.2"
    assert result["packets"] == 1 and result["format"] == "PRO"
    result = await gen.upload_arbitrary([0.0] * 5000, channel=1)
    flags = [flag for flag, _ in inst.raw_writes[-3:]]
    assert flags == ["HEADER", "CONTINUE", "END"]
    assert result["packets"] == 3
    assert sum(len(v) for _, v in inst.raw_writes[-3:]) == 5000
    with pytest.raises(ValueError):
        await gen.upload_arbitrary([0.0] * 3_000_000)  # DG852 Pro: 2 Mpts
    with pytest.raises(ValueError):
        await gen.set_arb_sample_rate(1e6)


@pytest.mark.asyncio
async def test_pro_multichannel_models():
    gen, inst = make_driver(RigolDG5000Pro, "DG5508 Pro")
    await gen.connect()
    assert gen.spec.channels == 8
    await gen.set_output(True, channel=8)
    assert ":OUTPut8 ON" in inst.writes
    await gen.apply(channel=7, waveform="SIN", frequency=400e6, amplitude=1.0)
    assert ":SOURce7:APPLy:SINusoid 400000000,1,DEF,DEF" in inst.writes
    with pytest.raises(ValueError):
        await gen.apply(channel=7, waveform="SIN", frequency=400e6, amplitude=1.5)  # >350 MHz: 1 Vpp
    with pytest.raises(ValueError):
        await gen.apply(channel=9, waveform="SIN")
    with pytest.raises(ValueError):
        await gen.get_counter()
    dg6, _ = make_driver(RigolDG6000, "DG6102")
    await dg6.connect()
    assert dg6.spec.channels == 2 and dg6.spec.max_frequency["SIN"] == 1e9


# --------------------------------------------------------------------------- #
# Counter, acquisition hook, dispatch, safety
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_counter_and_acquisition_hook():
    gen, inst = make_driver(RigolDG1000Z, "DG1062Z")
    await gen.connect()
    counter = await gen.get_counter()
    assert counter["enabled"] is False
    assert counter["frequency"] != counter["frequency"]  # NaN while disabled
    assert await gen.set_counter(True) is True
    assert ":COUNter:STATe ON" in inst.writes
    counter = await gen.get_counter()
    assert counter["frequency"] == pytest.approx(2000.0)
    assert counter["period"] == pytest.approx(5e-4)
    assert counter["duty_cycle"] == pytest.approx(47.608)

    m = await gen.get_measurement("COUNTER")
    assert m["value"] == pytest.approx(2000.0) and m["unit"] == "Hz"
    m = await gen.get_measurement("COUNT:PERIOD")
    assert m["value"] == pytest.approx(5e-4) and m["unit"] == "s"
    await gen.apply(channel=1, waveform="SIN", frequency=12345.0, amplitude=3.3, offset=0.1, phase=5)
    m = await gen.get_measurement("CH1:FREQ")
    assert m["value"] == pytest.approx(12345.0) and m["unit"] == "Hz" and m["channel"] == 1
    m = await gen.get_measurement("CH1")
    assert m["value"] == pytest.approx(12345.0)
    m = await gen.get_measurement("CH1:AMPL")
    assert m["value"] == pytest.approx(3.3) and m["unit"] == "VPP"
    m = await gen.get_measurement("ch1:offs")
    assert m["value"] == pytest.approx(0.1)
    m = await gen.get_measurement("CH1:PHASE")
    assert m["value"] == pytest.approx(5.0)
    await gen.set_output(True, 1)
    m = await gen.get_measurement("CH1:OUTPUT")
    assert m["value"] == 1.0
    with pytest.raises(ValueError):
        await gen.get_measurement("CH1:BANANAS")
    with pytest.raises(ValueError):
        await gen.get_measurement("CH3:FREQ")
    streams = await gen.get_measurements(1)
    assert streams["frequency"] == pytest.approx(12345.0)
    assert streams["counter_frequency"] == pytest.approx(2000.0)


@pytest.mark.asyncio
async def test_execute_command_dispatch():
    gen, inst = make_driver(RigolDG1000Z, "DG1062Z")
    await gen.connect()
    data = await gen.execute_command(
        "apply", {"channel": 2, "waveform": "SIN", "frequency": 5000, "amplitude": 1.0}
    )
    assert isinstance(data, FunctionGeneratorData) and data.frequency == pytest.approx(5000.0)
    assert await gen.execute_command("set_output", {"enabled": True, "channel": 2}) is True
    assert await gen.execute_command("get_frequency", {"channel": 2}) == pytest.approx(5000.0)
    readings = await gen.execute_command("get_readings", {"channel": 2})
    assert readings.output_enabled is True
    m = await gen.execute_command("get_measurement", {"channel": "CH2:FREQ"})
    assert m["value"] == pytest.approx(5000.0)
    state = await gen.execute_command("get_state", {})
    assert state["channels"][2]["frequency"] == pytest.approx(5000.0)
    assert state["channels"][2]["output"] is True
    err = await gen.execute_command("get_error", {})
    assert err["code"] == 0 and err["message"] == "No error"
    assert await gen.execute_command("set_beeper", {"enabled": False}) is False
    await gen.execute_command("reset", {})
    assert "*RST" in inst.writes
    with pytest.raises(ValueError, match="Unknown command"):
        await gen.execute_command("make_coffee", {})
    # Every dispatch entry points at a coroutine method of the driver
    handlers = gen._handlers()
    for name in ("apply", "set_waveform", "set_frequency", "set_amplitude", "set_offset", "set_phase",
                 "set_duty_cycle", "set_output", "set_load", "set_modulation", "set_sweep", "set_burst",
                 "upload_arbitrary", "get_readings", "sync_phase", "get_counter", "get_measurement",
                 "get_state", "reset", "get_error"):
        assert name in handlers and callable(handlers[name])


@pytest.mark.asyncio
async def test_set_output_exists_for_disconnect_safety():
    """manager.disconnect_device() calls set_output(False) on generators."""
    for cls, model in ((RigolDG1000Z, "DG1062Z"), (RigolDG800, "DG812"), (RigolDG4000, "DG4062"),
                       (RigolDG5000, "DG5072"), (RigolDG800Pro, "DG822 Pro"), (RigolDG6000, "DG6054")):
        gen, inst = make_driver(cls, model)
        await gen.connect()
        assert hasattr(gen, "set_output") and not hasattr(gen, "set_input")
        await gen.set_output(True)
        assert await gen.set_output(False) is False
        assert inst.writes[-1] == ":OUTPut1 OFF"
        assert inst.channels[1]["out"] is False
