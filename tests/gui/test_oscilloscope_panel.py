"""The oscilloscope panel drives a scope as a scope.

Selecting a DS1054Z on the Control tab used to show voltage and current dials
and poll for supply readings. This panel sends the scope drivers' own
commands, polls automatic measurements on its cadence and the waveform on a
slower one, and never asks for anything a scope cannot answer.
"""

import asyncio
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication

    from client.models.equipment import ConnectionStatus, Equipment, EquipmentType
    from client.ui.instruments import OscilloscopePanel, panel_class_for
    from client.ui.instruments.oscilloscope import si_format

    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(not GUI_AVAILABLE, reason="PyQt6 is required")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _stop_panels(qapp):
    made = []
    original = OscilloscopePanel.__init__

    def tracking(self, *a, **k):
        original(self, *a, **k)
        made.append(self)

    OscilloscopePanel.__init__ = tracking
    try:
        yield
    finally:
        OscilloscopePanel.__init__ = original
        for p in made:
            p.stop()
            p.deleteLater()
        qapp.processEvents()


class FakeScopeClient:
    """Answers like a DS1054Z through the command endpoint."""

    def __init__(self, num_channels=4, waveform=True):
        self.commands = []
        self.num_channels = num_channels
        self.waveform = waveform

    def get_equipment_status(self, equipment_id):
        return {"capabilities": {"num_channels": self.num_channels, "bandwidth": "50MHz"}}

    def send_command(self, equipment_id, command, parameters=None):
        self.commands.append((command, parameters or {}))
        if command == "get_state":
            return {"success": True, "data": {
                "channels": {"1": {"enabled": True, "scale": 0.5, "offset": 0.1, "coupling": "AC"},
                             "2": {"enabled": False, "scale": 2.0, "offset": 0.0, "coupling": "DC"}},
                "timebase": {"scale": 2e-3, "offset": 0.0},
                "trigger": {"source": "CHAN2", "level": 0.25, "slope": "NEG", "sweep": "NORM", "status": "TD"},
            }}
        if command == "get_measurements":
            return {"success": True, "data": {"vpp": 1.52, "vmax": 0.76, "vmin": -0.76,
                                              "vavg": 0.0, "vrms": 0.54, "freq": 1000.0, "period": 1e-3}}
        if command == "get_waveform_data":
            if not self.waveform:
                return {"success": False, "error": "Unknown command: get_waveform_data"}
            ch = parameters["channel"]
            n = 8
            return {"success": True, "data": {
                "channel": ch, "voltage_scale": 0.5 * ch, "x_origin": -1e-3, "x_increment": 2.5e-4,
                "time": [-1e-3 + i * 2.5e-4 for i in range(n)],
                "voltage": [0.1 * ch * ((i % 2) * 2 - 1) for i in range(n)],
            }}
        return {"success": True, "data": None}


def _scope(status=ConnectionStatus.CONNECTED):
    return Equipment(
        equipment_id="scope_1", name="DS1054Z", equipment_type=EquipmentType.OSCILLOSCOPE,
        manufacturer="Rigol", model="DS1054Z", resource_name="USB::x", connection_status=status,
    )


def _run(panel, method_name, *args):
    method = getattr(type(panel), method_name)
    coroutine = getattr(method, "__wrapped__", method)
    return asyncio.run(coroutine(panel, *args))


def _sent(client, name):
    return [p for c, p in client.commands if c == name]


class TestRegistration:
    def test_scopes_get_this_panel(self):
        assert panel_class_for(EquipmentType.OSCILLOSCOPE) is OscilloscopePanel

    def test_it_polls_measurements_not_readings(self):
        assert OscilloscopePanel.POLLS == "measurements"
        assert OscilloscopePanel.DEFAULT_INTERVAL_MS >= 200, "a :MEAS:ITEM? per item is not free"


class TestConfiguration:
    def test_channel_rows_follow_the_instrument(self, qapp):
        panel = OscilloscopePanel()
        panel.set_instrument(_scope(), FakeScopeClient(num_channels=2))
        visible = [row["enable"].isVisibleTo(panel) for row in panel.channel_rows]
        assert visible[:2] == [True, True] and not any(visible[2:])
        assert [panel.trigger_source.itemText(i) for i in range(panel.trigger_source.count())] == \
            ["CH1", "CH2", "EXT", "AC Line"]

    def test_the_scopes_own_settings_land_on_the_controls_without_commanding(self, qapp):
        client = FakeScopeClient()
        panel = OscilloscopePanel()
        panel.set_instrument(_scope(), client)

        row1 = panel.channel_rows[0]
        assert row1["scale"].currentData() == pytest.approx(0.5)
        assert row1["offset"].value() == pytest.approx(0.1)
        assert row1["coupling"].currentText() == "AC"
        assert not panel.channel_rows[1]["enable"].isChecked()
        assert panel.timebase_scale.currentData() == pytest.approx(2e-3)
        assert panel.trigger_source.currentData() == "CHAN2"
        assert panel.trigger_level.value() == pytest.approx(0.25)
        assert panel.trigger_slope.currentData() == "NEG"
        assert panel.trigger_sweep.currentData() == "NORMAL"
        # Reading state back must not have written anything.
        assert [c for c, _ in client.commands if c.startswith("set_")] == []


class TestCommands:
    @pytest.fixture
    def bound(self, qapp):
        client = FakeScopeClient()
        panel = OscilloscopePanel()
        panel.set_instrument(_scope(), client)
        client.commands.clear()
        return panel, client

    def test_apply_channel_sends_set_channel_with_the_row_values(self, bound):
        panel, client = bound
        row = panel.channel_rows[2]
        row["enable"].setChecked(True)
        row["scale"].setCurrentIndex(row["scale"].findData(0.2))
        row["offset"].setValue(-0.5)
        row["coupling"].setCurrentText("GND")
        _run(panel, "_send_command", "set_channel", {
            "channel": 3, "enabled": True, "scale": 0.2, "offset": -0.5, "coupling": "GND"})
        assert _sent(client, "set_channel") == [
            {"channel": 3, "enabled": True, "scale": 0.2, "offset": -0.5, "coupling": "GND"}]

    def test_the_apply_button_builds_the_same_payload(self, bound, monkeypatch):
        panel, client = bound
        captured = []
        monkeypatch.setattr(panel, "_command", lambda name, params=None: captured.append((name, params)))
        panel.channel_rows[0]["offset"].setValue(0.75)
        panel._apply_channel(1)
        assert captured == [("set_channel", {
            "channel": 1, "enabled": True, "scale": pytest.approx(0.5),
            "offset": 0.75, "coupling": "AC"})]

    def test_timebase_and_trigger_payloads(self, bound, monkeypatch):
        panel, client = bound
        captured = []
        monkeypatch.setattr(panel, "_command", lambda name, params=None: captured.append((name, params)))
        panel.timebase_scale.setCurrentIndex(panel.timebase_scale.findData(1e-6))
        panel.timebase_offset.setValue(0.002)
        panel._apply_timebase()
        panel.trigger_source.setCurrentIndex(panel.trigger_source.findData("EXT"))
        panel.trigger_level.setValue(1.2)
        panel.trigger_slope.setCurrentIndex(panel.trigger_slope.findData("RFAL"))
        panel.trigger_sweep.setCurrentIndex(panel.trigger_sweep.findData("SINGLE"))
        panel._apply_trigger()
        assert captured == [
            ("set_timebase", {"scale": 1e-6, "offset": 0.002}),
            ("set_trigger", {"source": "EXT", "level": 1.2, "slope": "RFAL", "sweep": "SINGLE"}),
        ]

    def test_run_stop_single_force_auto_use_the_driver_names(self, bound):
        panel, client = bound
        for name in ("trigger_run", "trigger_stop", "trigger_single", "force_trigger", "autoscale"):
            _run(panel, "_send_command", name, {})
        assert [c for c, _ in client.commands] == [
            "trigger_run", "trigger_stop", "trigger_single", "force_trigger", "autoscale"]
        assert panel.trigger_status.text() == "FORCED" or panel.trigger_status.text() in ("RUN", "STOP", "SINGLE", "FORCED")

    def test_lock_gating_reaches_every_control(self, bound):
        panel, _ = bound
        panel.set_controls_enabled(False)
        assert not panel.run_button.isEnabled()
        assert not panel.channel_rows[0]["apply"].isEnabled()
        assert not panel.trigger_apply.isEnabled()
        panel.set_controls_enabled(True)
        assert panel.run_button.isEnabled()


class TestPolling:
    def test_measurements_fill_the_table_for_the_chosen_channel(self, qapp):
        client = FakeScopeClient()
        panel = OscilloscopePanel()
        panel.set_instrument(_scope(), client)
        panel.measure_channel.setCurrentIndex(1)
        client.commands.clear()

        _run(panel, "_poll")

        assert _sent(client, "get_measurements") == [{"channel": 2}]
        values = {panel.measurement_table.item(i, 0).text(): panel.measurement_table.item(i, 1).text()
                  for i in range(panel.measurement_table.rowCount())}
        assert values["Vpp"] == "1.52 V"
        assert values["Frequency"] == "1 kHz"
        assert values["Rise time"] == "--"

    def test_the_trace_fetches_only_enabled_channels_decimated(self, qapp):
        client = FakeScopeClient()
        panel = OscilloscopePanel()
        panel.set_instrument(_scope(), client)
        panel.channel_rows[1]["enable"].setChecked(True)   # CH1 on from state, CH2 now too
        client.commands.clear()

        _run(panel, "_poll_trace")

        fetched = _sent(client, "get_waveform_data")
        assert [p["channel"] for p in fetched] == [1, 2]
        assert all(p["points"] == OscilloscopePanel.TRACE_POINTS for p in fetched)
        assert panel.series[0].count() == 8 and panel.series[1].count() == 8
        assert panel.series[2].count() == 0
        # Axes from the returned data: time span, and ±4 div of the largest scale (CH2 = 1.0 V/div)
        assert panel.axis_x.min() == pytest.approx(-1e-3)
        assert panel.axis_y.max() == pytest.approx(4.0)

    def test_a_driver_without_waveforms_is_asked_once(self, qapp):
        client = FakeScopeClient(waveform=False)
        panel = OscilloscopePanel()
        panel.set_instrument(_scope(), client)
        panel.trace_timer.start(1000)

        _run(panel, "_poll_trace")

        assert not panel.trace_timer.isActive()
        assert "waveform" in panel.trace_note.text().lower()
        assert panel._trace_unsupported

    def test_stop_halts_both_cadences(self, qapp):
        panel = OscilloscopePanel()
        panel.set_instrument(_scope(), FakeScopeClient())
        panel.poll_timer.start(500)
        panel.trace_timer.start(1000)
        assert panel.is_polling()
        panel.stop()
        assert not panel.poll_timer.isActive() and not panel.trace_timer.isActive()
        assert not panel.is_polling()

    def test_the_trace_rate_control_changes_the_trace_timer(self, qapp):
        panel = OscilloscopePanel()
        panel.set_instrument(_scope(), FakeScopeClient())
        panel.trace_timer.start(panel.trace_interval_ms())
        panel.trace_rate_spinbox.setValue(2.0)
        assert panel.trace_timer.interval() == 500


class TestFormatting:
    @pytest.mark.parametrize("value,unit,text", [
        (1.52, "V", "1.52 V"), (0.0047, "V", "4.7 mV"), (1000.0, "Hz", "1 kHz"),
        (2.5e-6, "s", "2.5 µs"), (float("nan"), "V", "--"), (None, "V", "--"), (45.0, "%", "45.0 %"),
    ])
    def test_si_format(self, value, unit, text):
        assert si_format(value, unit) == text
