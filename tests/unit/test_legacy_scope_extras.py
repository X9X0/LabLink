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

from server.equipment.rigol_scope import (RigolDS1102D, RigolDS1104,
                                          RigolMSO2072A)


MEASURED = {"VPP": "1.52", "VMAX": "0.76", "VMIN": "-0.76", "VAVG": "0.0",
            "VRMS": "0.54", "FREQ": "1000.0", "PER": "0.001"}


class ScriptedScope:
    """A DS1000Z answering the subset of SCPI the extras use."""

    #: The measured ceiling on one reply from the bench DS1054Z: a 492-byte
    #: reply arrives, a 512-byte one never does. Counts the whole reply, header
    #: included. None for a scope whose USB is not broken.
    packet_ceiling = 492

    def __init__(self):
        self.session = 1
        self.timeout = 10000
        self.writes = []
        self.queries = []
        self.samples = [128 + int(40 * ((i % 20) - 10) / 10) for i in range(1200)]
        self.start = 1
        self.stop = 1200

    def close(self):
        pass

    def write(self, cmd):
        self.writes.append(cmd)
        c = cmd.upper()
        if c.startswith(":WAV:STAR "):
            self.start = int(cmd.split()[1])
        elif c.startswith(":WAV:STOP "):
            self.stop = int(cmd.split()[1])

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
        if c.startswith(":MEAS:ITEM?"):
            item, source = [p.strip() for p in c[len(":MEAS:ITEM?"):].split(",")]
            assert source.startswith("CHAN"), f"no source in {cmd}"
            return MEASURED[item]
        if c == ":MEAS:VAV?":
            # Not a DS1000Z command. The bench DS1054Z never answered it; each
            # send burned the full 10 s VISA timeout.
            raise TimeoutError("VI_ERROR_TMO")
        if c.startswith(":MEAS:"):
            # The undocumented per-item forms. :MEAS:VPP? and :MEAS:FREQ? do
            # answer on a DS1054Z, so the fake answers them too -- but the
            # driver is expected to use :MEAS:ITEM? and the tests assert it.
            return MEASURED[c.split(":")[2].rstrip("?")]
        raise AssertionError(f"unscripted query {cmd}")

    def query_binary_values(self, cmd, datatype="B"):
        self.queries.append(cmd)
        assert cmd == ":WAV:DATA?"
        block = self.samples[self.start - 1:self.stop]
        # 11-byte IEEE header plus the payload plus the terminator. Past the
        # ceiling the real scope sends nothing at all and the read waits out
        # the whole VISA timeout.
        if self.packet_ceiling is not None and len(block) + 12 > self.packet_ceiling:
            raise TimeoutError("VI_ERROR_TMO")
        return list(block)


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
def test_the_trace_is_read_in_windows_small_enough_to_arrive():
    """The 1200-sample screen comes back as three windowed reads.

    The bench DS1054Z declares wMaxPacketSize 64 on both bulk endpoints where
    USB 2.0 high speed requires 512. Measured over pyvisa-py/libusb, a
    492-byte reply arrives and a 512-byte one never does, so the 1212-byte
    single-shot screen read could not work and the panel had no trace.
    ScriptedScope enforces that same ceiling, so a driver that goes back to
    one big read fails here rather than on the bench.
    """
    scope, inst = make()
    asyncio.run(scope.connect())
    inst.writes.clear()
    inst.queries.clear()
    data = asyncio.run(scope.execute_command("get_waveform_data", {"channel": 1}))

    assert data["num_samples"] == 1200
    assert data["voltage"][0] == pytest.approx((inst.samples[0] - 128) * 0.04)
    # Stitched in order, and nothing lost or repeated at the seams.
    assert [pytest.approx(v) for v in data["voltage"]] == [
        pytest.approx((s - 128) * 0.04) for s in inst.samples]
    windows = [w for w in inst.writes if w.startswith((":WAV:STAR", ":WAV:STOP"))]
    assert windows == [":WAV:STAR 1", ":WAV:STOP 1200",       # full screen, for the preamble
                       ":WAV:STAR 1", ":WAV:STOP 400",
                       ":WAV:STAR 401", ":WAV:STOP 800",
                       ":WAV:STAR 801", ":WAV:STOP 1200"]
    assert inst.queries.count(":WAV:DATA?") == 3


@pytest.mark.unit
def test_a_short_block_stops_the_read_instead_of_running_off_the_end():
    """A window that comes back short ends the trace at what arrived."""
    scope, inst = make()
    asyncio.run(scope.connect())
    original = inst.query_binary_values

    def truncating(cmd, datatype="B"):
        block = original(cmd, datatype)
        return block[:100] if inst.start == 401 else block

    inst.query_binary_values = truncating
    data = asyncio.run(scope.execute_command("get_waveform_data", {"channel": 1}))
    assert data["num_samples"] == 500          # 400 whole + 100 short, then stop
    assert inst.queries.count(":WAV:DATA?") == 2


@pytest.mark.unit
def test_the_other_legacy_families_still_read_the_trace_in_one_go():
    """Windowing is opt-in per family.

    Only the DS1000Z has been measured on the bench. The DS1000D/E command
    tree is older and may not window at all, so those drivers must keep the
    single read they have always used.
    """
    assert RigolMSO2072A.trace_block_points is None
    assert RigolDS1102D.trace_block_points is None

    inst = ScriptedScope()
    inst.packet_ceiling = None          # a scope whose bulk endpoints are sane
    rm = MagicMock()
    rm.open_resource = MagicMock(return_value=inst)
    scope = RigolMSO2072A(rm, "USB0::0x1AB1::0x04B3::MSO2072A::INSTR")
    asyncio.run(scope.connect())
    inst.writes.clear()
    inst.queries.clear()
    data = asyncio.run(scope.get_waveform_data(channel=1))
    assert data["num_samples"] == 1200
    assert inst.queries.count(":WAV:DATA?") == 1
    assert not any(w.startswith((":WAV:STAR", ":WAV:STOP")) for w in inst.writes)


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
    # The source travels in the query, so there is no :MEAS:SOUR write at all.
    assert ":MEAS:ITEM? VPP,CHAN2" in inst.queries
    assert not any(w.startswith(":MEAS:SOUR") for w in inst.writes)
    readings = asyncio.run(scope.execute_command("get_readings", {"channel": 1}))
    # A cheap snapshot: /readings is polled twice a second by the Equipment
    # tab's stream, and answering it with :MEAS queries held the I/O lock and
    # queued front-panel commands for tens of seconds on the bench.
    assert readings == {"channel": 1, "trigger_status": "TD", "timebase_scale": pytest.approx(1e-4),
                        "channel_scale": pytest.approx(1.0)}
    assert not any(q.startswith(":MEAS") for q in inst.queries[-3:])


@pytest.mark.unit
def test_measurements_use_the_documented_item_form():
    """Every item goes out as :MEAS:ITEM? <item>,CHAN<n>.

    The driver used to send :MEAS:VPP?, :MEAS:VAV? and friends. Those are not
    in the DS1000Z programming guide; on the bench DS1054Z :MEAS:VAV? was
    never answered and cost a full 10 s VISA timeout on every measurement
    poll, which is what built the instrument's ~200 s command queue.
    """
    scope, inst = make()
    asyncio.run(scope.connect())
    inst.queries.clear()
    data = asyncio.run(scope.execute_command("get_measurements", {"channel": 3}))
    assert data == {"vpp": pytest.approx(1.52), "vmax": pytest.approx(0.76),
                    "vmin": pytest.approx(-0.76), "vavg": pytest.approx(0.0),
                    "vrms": pytest.approx(0.54), "freq": pytest.approx(1000.0),
                    "period": pytest.approx(0.001)}
    assert [q for q in inst.queries if q.startswith(":MEAS:")] == [
        ":MEAS:ITEM? VPP,CHAN3", ":MEAS:ITEM? VMAX,CHAN3", ":MEAS:ITEM? VMIN,CHAN3",
        ":MEAS:ITEM? VAVG,CHAN3", ":MEAS:ITEM? VRMS,CHAN3", ":MEAS:ITEM? FREQ,CHAN3",
        ":MEAS:ITEM? PER,CHAN3",
    ]


@pytest.mark.unit
def test_one_unanswered_item_does_not_lose_the_others():
    """A query that times out costs its own item, not the rest of the set."""
    scope, inst = make()
    asyncio.run(scope.connect())
    original = inst.query

    def query(cmd):
        if cmd == ":MEAS:ITEM? VPP,CHAN1":
            inst.queries.append(cmd)
            raise TimeoutError("VI_ERROR_TMO")
        return original(cmd)

    inst.query = query
    data = asyncio.run(scope.execute_command(
        "get_measurements", {"channel": 1, "items": ["vpp", "vrms", "freq"]}))
    assert data == {"vrms": pytest.approx(0.54), "freq": pytest.approx(1000.0)}


@pytest.mark.unit
def test_measurements_can_be_limited_to_the_items_asked_for():
    """Two items asked for: two :MEAS queries, not seven."""
    scope, inst = make()
    asyncio.run(scope.connect())
    inst.queries.clear()
    data = asyncio.run(scope.execute_command("get_measurements", {"channel": 1, "items": ["vpp", "freq"]}))
    assert set(data) == {"vpp", "freq"}
    meas = [q for q in inst.queries if q.startswith(":MEAS:")]
    assert meas == [":MEAS:ITEM? VPP,CHAN1", ":MEAS:ITEM? FREQ,CHAN1"]


@pytest.mark.unit
def test_clear_key_maps_to_cle():
    scope, inst = make()
    asyncio.run(scope.connect())
    asyncio.run(scope.execute_command("clear", {}))
    assert ":CLE" in inst.writes


@pytest.mark.unit
def test_unknown_commands_still_raise():
    scope, inst = make()
    asyncio.run(scope.connect())
    with pytest.raises(ValueError, match="Unknown command"):
        asyncio.run(scope.execute_command("fly", {}))


@pytest.mark.unit
def test_get_state_asks_one_question_of_a_dark_channel():
    """The panel reads this on every selection; a channel that is off costs :DISP? only."""
    scope, inst = make()
    asyncio.run(scope.connect())
    original = inst.query

    def query(cmd):
        if cmd.upper().startswith(":CHAN") and cmd.upper().endswith(":DISP?"):
            inst.queries.append(cmd)
            return "1" if cmd.upper().startswith(":CHAN1") else "0"
        return original(cmd)

    inst.query = query
    inst.queries.clear()
    state = asyncio.run(scope.execute_command("get_state", {}))
    assert state["channels"]["1"]["scale"] == pytest.approx(1.0)
    assert state["channels"]["2"] == {"channel": 2, "enabled": False}
    for ch in ("2", "3", "4"):
        assert not any(q.upper().startswith(f":CHAN{ch}:") and not q.upper().endswith(":DISP?")
                       for q in inst.queries)
