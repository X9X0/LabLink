"""The legacy Rigol scope drivers answer the commands the scope panel sends.

RigolDS1104 drives the bench DS1054Z. Its get_waveform() returned metadata
only -- the samples were meant to travel over a binary WebSocket that the
Control tab does not use -- so a live trace needs get_waveform_data() with
the same JSON shape the modern driver returns, plus set_trigger / get_state /
get_measurement, which the class never had.
"""

import asyncio
import struct
from unittest.mock import MagicMock

import pytest

from server.equipment.rigol_scope import RigolDS1104, RigolMSO2072A


class ScriptedScope:
    """A DS1000Z answering the subset of SCPI the extras use."""

    def __init__(self):
        self.session = 1
        self.timeout = 10000
        self.writes = []
        self.queries = []
        self.samples = [128 + int(40 * ((i % 20) - 10) / 10) for i in range(1200)]

    def close(self):
        pass

    def write(self, cmd):
        self.writes.append(cmd)

    def query(self, cmd):
        self.queries.append(cmd)
        c = cmd.upper()
        if c == "*IDN?":
            return "RIGOL TECHNOLOGIES,DS1054Z,DS1ZA171409212,00.04.03"
        if c == ":WAV:PRE?":
            # format,type,points,count,xinc,xorig,xref,yinc,yorig,yref
            return "0,0,1200,1,1.000000e-06,-6.000000e-04,0,4.000000e-02,0,128"
        if c == ":TIM:MAIN:SCAL?":
            return "1.000000e-04"
        if c == ":TIM:MAIN:OFFS?":
            return "0.000000e+00"
        if c.startswith(":CHAN") and c.endswith(":SCAL?"):
            return "1.000000e+00"
        if c.startswith(":CHAN") and c.endswith(":OFFS?"):
            return "0.000000e+00"
        if c.startswith(":CHAN") and c.endswith(":DISP?"):
            return "1"
        if c.startswith(":CHAN") and c.endswith(":COUP?"):
            return "DC"
        if c.startswith(":CHAN") and c.endswith(":PROB?"):
            return "10"
        if c == ":TRIG:MODE?":
            return "EDGE"
        if c == ":TRIG:EDGE:SOUR?":
            return "CHAN1"
        if c == ":TRIG:EDGE:SLOP?":
            return "POS"
        if c == ":TRIG:SWE?":
            return "AUTO"
        if c == ":TRIG:STAT?":
            return "TD"
        if c == ":TRIG:EDGE:LEV?":
            return "1.500000e+00"
        if c.startswith(":MEAS:"):
            return {"VPP": "1.52", "VMAX": "0.76", "VMIN": "-0.76", "VAV": "0.0",
                    "VRMS": "0.54", "FREQ": "1000.0", "PER": "0.001"}[c.split(":")[2].rstrip("?")]
        raise AssertionError(f"unscripted query {cmd}")

    def query_binary_values(self, cmd, datatype="B"):
        self.queries.append(cmd)
        assert cmd == ":WAV:DATA?"
        return list(self.samples)


def make(cls=RigolDS1104):
    inst = ScriptedScope()
    rm = MagicMock()
    rm.open_resource = MagicMock(return_value=inst)
    return cls(rm, "USB0::0x1AB1::0x04CE::DS1ZA171409212::INSTR"), inst


@pytest.mark.unit
def test_waveform_data_has_the_modern_shape_and_real_samples():
    scope, inst = make()
    asyncio.run(scope.connect())
    data = asyncio.run(scope.execute_command("get_waveform_data", {"channel": 1}))

    assert set(data) >= {"time", "voltage", "x_increment", "x_origin", "sample_rate",
                         "voltage_scale", "num_samples", "channel", "source"}
    assert data["num_samples"] == 1200 and len(data["voltage"]) == 1200
    # (raw - yorigin - yref) * yinc: sample 128 is 0 V, 168 is +1.6 V
    assert data["voltage"][0] == pytest.approx((inst.samples[0] - 128) * 0.04)
    assert data["time"][0] == pytest.approx(-6e-4)
    assert data["time"][1] - data["time"][0] == pytest.approx(1e-6)
    assert data["sample_rate"] == pytest.approx(1e6)
    assert ":WAV:SOUR CHAN1" in inst.writes and ":WAV:FORM BYTE" in inst.writes


@pytest.mark.unit
def test_waveform_data_is_decimated_server_side():
    """600 points asked for, 1200 available: every second sample, times too."""
    scope, inst = make()
    asyncio.run(scope.connect())
    data = asyncio.run(scope.get_waveform_data(channel=1, points=600))
    assert data["num_samples"] == 600
    assert len(data["time"]) == 600
    assert data["x_increment"] == pytest.approx(2e-6)
    assert data["voltage"][1] == pytest.approx((inst.samples[2] - 128) * 0.04)


@pytest.mark.unit
def test_waveform_rejects_a_channel_the_model_lacks():
    scope, inst = make(RigolMSO2072A)  # 2 analog channels
    asyncio.run(scope.connect())
    with pytest.raises(ValueError):
        asyncio.run(scope.get_waveform_data(channel=3))


@pytest.mark.unit
def test_set_trigger_writes_only_what_it_is_given():
    scope, inst = make()
    asyncio.run(scope.connect())
    inst.writes.clear()
    result = asyncio.run(scope.execute_command(
        "set_trigger", {"source": "CH2", "level": 0.5, "slope": "falling", "sweep": "normal"}
    ))
    assert ":TRIG:EDGE:SOUR CHAN2" in inst.writes
    assert ":TRIG:EDGE:LEV 0.5" in inst.writes
    assert ":TRIG:EDGE:SLOP NEG" in inst.writes
    assert ":TRIG:SWE NORM" in inst.writes
    assert not any(w.startswith(":TRIG:MODE") for w in inst.writes)
    assert result["level"] == pytest.approx(1.5)   # read back from the scripted scope
    with pytest.raises(ValueError):
        asyncio.run(scope.set_trigger(slope="sideways"))


@pytest.mark.unit
def test_state_and_measurement_hooks():
    scope, inst = make()
    asyncio.run(scope.connect())
    state = asyncio.run(scope.execute_command("get_state", {}))
    assert set(state["channels"]) == {"1", "2", "3", "4"}
    assert state["channels"]["1"]["scale"] == pytest.approx(1.0)
    assert state["timebase"]["scale"] == pytest.approx(1e-4)
    assert state["trigger"]["source"] == "CHAN1"

    sample = asyncio.run(scope.execute_command("get_measurement", {"channel": "CH2:VPP"}))
    assert sample == {"value": pytest.approx(1.52), "channel": 2, "item": "vpp"}
    assert ":MEAS:SOUR CHAN2" in inst.writes
    readings = asyncio.run(scope.execute_command("get_readings", {"channel": 1}))
    assert readings["freq"] == pytest.approx(1000.0) and readings["channel"] == 1


@pytest.mark.unit
def test_unknown_commands_still_raise():
    scope, inst = make()
    asyncio.run(scope.connect())
    with pytest.raises(ValueError, match="Unknown command"):
        asyncio.run(scope.execute_command("fly", {}))
