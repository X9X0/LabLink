"""The function-generator panel applies a channel's settings the way the front panel does."""

import asyncio
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication


    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(not GUI_AVAILABLE, reason="PyQt6 is required")

if GUI_AVAILABLE:
    from client.models.equipment import ConnectionStatus, Equipment, EquipmentType
    from client.ui.instruments import FunctionGeneratorPanel, panel_class_for


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _stop_panels(qapp):
    made = []
    original = FunctionGeneratorPanel.__init__

    def tracking(self, *a, **k):
        original(self, *a, **k)
        made.append(self)

    FunctionGeneratorPanel.__init__ = tracking
    try:
        yield
    finally:
        FunctionGeneratorPanel.__init__ = original
        for p in made:
            p.stop()
            p.deleteLater()
        qapp.processEvents()


class FakeDGClient:
    def __init__(self, counter=True):
        self.commands = []
        self.counter = counter
        self.settings = {1: {"channel": 1, "waveform": "SQU", "frequency": 2500.0, "amplitude": 2.0,
                             "amplitude_unit": "VPP", "offset": 0.5, "phase": 90.0, "duty_cycle": 25.0,
                             "output_enabled": True, "load_impedance": "INF", "sweep_enabled": False,
                             "burst_enabled": True, "modulation": None},
                         2: {"channel": 2, "waveform": "SIN", "frequency": 1000.0, "amplitude": 1.0,
                             "amplitude_unit": "VRMS", "offset": 0.0, "phase": 0.0, "output_enabled": False,
                             "load_impedance": "50"}}

    def get_equipment_status(self, equipment_id):
        return {"capabilities": {"channels": 2, "waveforms": ["SIN", "SQU", "RAMP", "PULS", "NOIS", "DC", "ARB"],
                                 "max_frequency": {"SIN": 60e6, "SQU": 25e6, "RAMP": 1e6, "PULS": 25e6},
                                 "max_amplitude_vpp_highz": 20.0}}

    def send_command(self, equipment_id, command, parameters=None):
        p = parameters or {}
        self.commands.append((command, p))
        if command == "get_readings":
            return {"success": True, "data": dict(self.settings[p.get("channel", 1)])}
        if command == "get_counter":
            if not self.counter:
                return {"success": False, "error": "Unknown command: get_counter"}
            return {"success": True, "data": {"enabled": True, "frequency": 2499.8, "period": 4e-4}}
        if command == "apply":
            return {"success": True, "data": dict(self.settings[p["channel"]], **{k: v for k, v in p.items() if k != "channel"})}
        return {"success": True, "data": None}


def _gen():
    return Equipment(
        equipment_id="fgen_1", name="DG1062Z", equipment_type=EquipmentType.FUNCTION_GENERATOR,
        manufacturer="Rigol", model="DG1062Z", resource_name="USB::x",
        connection_status=ConnectionStatus.CONNECTED,
    )


def _run(panel, method_name, *args):
    method = getattr(type(panel), method_name)
    coroutine = getattr(method, "__wrapped__", method)
    return asyncio.run(coroutine(panel, *args))


def test_generators_get_this_panel():
    assert panel_class_for(EquipmentType.FUNCTION_GENERATOR) is FunctionGeneratorPanel


def test_binding_reads_channel_one_onto_the_controls_without_commanding(qapp):
    client = FakeDGClient()
    panel = FunctionGeneratorPanel()
    panel.set_instrument(_gen(), client)

    assert panel.channel_combo.count() == 2
    assert panel.waveform_combo.currentData() == "SQU"
    assert panel.frequency_spin.value() == pytest.approx(2500.0)
    assert panel.frequency_spin.maximum() == pytest.approx(25e6), "square wave ceiling"
    assert panel.amplitude_spin.value() == pytest.approx(2.0)
    assert panel.amplitude_unit.currentText() == "VPP"
    assert panel.duty_spin.value() == pytest.approx(25.0) and panel.duty_spin.isEnabled()
    assert panel.load_combo.currentText() == "High Z"
    assert panel.output_button.isChecked()
    assert panel.burst_enable.isChecked() and not panel.sweep_enable.isChecked()
    assert "Square" in panel.summary_display.text() and "2.5 kHz" in panel.summary_display.text()
    assert [c for c, _ in client.commands if c.startswith("set_") or c == "apply"] == []


def test_switching_channel_reads_that_channel(qapp):
    client = FakeDGClient()
    panel = FunctionGeneratorPanel()
    panel.set_instrument(_gen(), client)
    panel.channel_combo.setCurrentIndex(1)
    assert panel.waveform_combo.currentData() == "SIN"
    assert panel.amplitude_unit.currentText() == "VRMS"
    assert panel.load_combo.currentText() == "50 Ω"
    assert not panel.duty_spin.isEnabled()


def test_apply_sends_unit_then_apply_then_duty_for_square(qapp):
    client = FakeDGClient()
    panel = FunctionGeneratorPanel()
    panel.set_instrument(_gen(), client)
    client.commands.clear()
    panel.frequency_spin.setValue(5000.0)
    panel.duty_spin.setValue(40.0)

    _run(panel, "_apply_all", panel.apply_payload(), panel.amplitude_unit.currentText(), 40.0)

    assert [c for c, _ in client.commands] == ["set_amplitude_unit", "apply", "set_duty_cycle"]
    assert client.commands[1][1] == {"channel": 1, "waveform": "SQU", "frequency": 5000.0,
                                     "amplitude": 2.0, "offset": 0.5, "phase": 90.0}
    assert client.commands[2][1] == {"duty_cycle": 40.0, "channel": 1}


def test_dc_and_noise_payloads_omit_what_they_have_no_use_for(qapp):
    panel = FunctionGeneratorPanel()
    panel.set_instrument(_gen(), FakeDGClient())
    panel.waveform_combo.setCurrentIndex(panel.waveform_combo.findData("DC"))
    assert set(panel.apply_payload()) == {"channel", "waveform", "offset"}
    panel.waveform_combo.setCurrentIndex(panel.waveform_combo.findData("NOIS"))
    assert set(panel.apply_payload()) == {"channel", "waveform", "amplitude", "offset"}


def test_output_load_sweep_burst_modulation_payloads(qapp):
    client = FakeDGClient()
    panel = FunctionGeneratorPanel()
    panel.set_instrument(_gen(), client)
    sent = []
    panel._command = lambda name, params=None: sent.append((name, params))

    panel.output_button.click()                       # was ON -> OFF
    panel.load_combo.setCurrentIndex(0)               # 50 Ω
    panel.sweep_enable.setChecked(True)
    panel.sweep_start.setValue(10.0); panel.sweep_stop.setValue(1000.0); panel.sweep_time.setValue(2.0)
    panel._apply_sweep()
    panel.burst_cycles.setValue(5); panel.burst_period.setValue(0.02)
    panel._apply_burst()
    panel.mod_enable.setChecked(True)
    panel.mod_type.setCurrentIndex(panel.mod_type.findData("FM"))
    panel.mod_param.setValue(1500.0); panel.mod_frequency.setValue(50.0)
    panel._apply_modulation()

    assert sent == [
        ("set_output", {"enabled": False, "channel": 1}),
        ("set_load", {"impedance": 50, "channel": 1}),
        ("set_sweep", {"enabled": True, "start": 10.0, "stop": 1000.0, "time": 2.0, "spacing": "LINEAR", "channel": 1}),
        ("set_burst", {"enabled": True, "mode": "TRIG", "cycles": 5, "period": 0.02, "channel": 1}),
        ("set_modulation", {"enabled": True, "modulation_type": "FM", "frequency": 50.0, "source": "INT",
                            "channel": 1, "deviation": 1500.0}),
    ]
    assert "Deviation (Hz)" in panel.mod_param_label.text()


def test_poll_reads_settings_and_the_counter(qapp):
    client = FakeDGClient()
    panel = FunctionGeneratorPanel()
    panel.set_instrument(_gen(), client)
    client.commands.clear()
    _run(panel, "_poll")
    assert [c for c, _ in client.commands] == ["get_readings", "get_counter"]
    assert panel.counter_display.text() == "Counter: 2.4998 kHz"


def test_a_model_without_a_counter_is_asked_once(qapp):
    client = FakeDGClient(counter=False)
    panel = FunctionGeneratorPanel()
    panel.set_instrument(_gen(), client)
    client.commands.clear()
    _run(panel, "_poll")
    _run(panel, "_poll")
    assert [c for c, _ in client.commands].count("get_counter") == 1
    assert panel.poll_timer is not None  # still a live panel; only the counter was dropped


class TestTheOutputButtonAgainstStaleReadings:
    """The panel polls while it commands, and the two are not ordered.

    A reading taken before the click arrives after it, carrying the state
    from before. The panel used to ignore readings for two seconds after a
    click, which also hid a command that never landed and stopped a change
    made at the front panel reaching the display. It now holds the click
    only until the generator is seen to agree with it.

    Reporting a live output as off is the dangerous direction to be wrong
    in, so a reading that carries no output state says nothing at all.
    """

    def panel(self, qapp):
        made = FunctionGeneratorPanel()
        made.set_instrument(_gen(), FakeDGClient())
        made._command = lambda name, params=None: None
        return made

    def test_a_stale_reading_does_not_undo_a_click(self, qapp):
        panel = self.panel(qapp)
        panel.output_button.click()                      # ON -> OFF
        assert panel.output_button.isChecked() is False
        panel._apply_settings({"output_enabled": True})  # taken before the click
        assert panel.output_button.isChecked() is False, (
            "a reading older than the click put the output back on in the display")

    def test_the_generator_gets_the_last_word_once_it_agrees(self, qapp):
        panel = self.panel(qapp)
        panel.output_button.click()                       # ON -> OFF
        panel._apply_settings({"output_enabled": False})  # it agrees
        panel._apply_settings({"output_enabled": True})   # switched at the front panel
        assert panel.output_button.isChecked() is True, (
            "agreement must hand authority back, rather than a timer expiring")

    def test_a_reading_with_no_output_state_says_nothing(self, qapp):
        panel = self.panel(qapp)
        assert panel.output_button.isChecked() is True
        panel._apply_settings({"waveform": "SQU", "frequency": 2500.0})
        assert panel.output_button.isChecked() is True, (
            "a missing field was read as off, showing Output OFF on a live channel")

    def test_a_command_the_generator_never_took_stops_being_believed(self, qapp):
        panel = self.panel(qapp)
        panel.output_button.click()                      # ON -> OFF
        pending = panel._pending["output"]
        panel._pending["output"] = pending._replace(
            at=pending.at - panel.PENDING_TIMEOUT_SEC - 1)
        panel._apply_settings({"output_enabled": True})
        assert panel.output_button.isChecked() is True, (
            "the display would have gone on claiming the output was off")

    def test_a_click_on_one_channel_does_not_speak_for_another(self, qapp):
        """Channel 1 is on and channel 2 is off in the fake.

        Switching channel re-reads, and that reading is about the channel
        now selected -- so a command to the one being left must not
        suppress it.
        """
        panel = self.panel(qapp)
        panel.output_button.click()                      # channel 1: ON -> OFF
        panel.channel_combo.setCurrentIndex(1)           # channel 2, which is off
        assert panel._pending.get("output") is None
        panel._apply_settings({"output_enabled": True})
        assert panel.output_button.isChecked() is True
