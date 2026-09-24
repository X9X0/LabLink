"""The load panel drives a load as a load: mode, one setpoint, input switch."""

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
    from client.ui.instruments import ElectronicLoadPanel, panel_class_for


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _stop_panels(qapp):
    made = []
    original = ElectronicLoadPanel.__init__

    def tracking(self, *a, **k):
        original(self, *a, **k)
        made.append(self)

    ElectronicLoadPanel.__init__ = tracking
    try:
        yield
    finally:
        ElectronicLoadPanel.__init__ = original
        for p in made:
            p.stop()
            p.deleteLater()
        qapp.processEvents()


class FakeLoadClient:
    def __init__(self):
        self.commands = []
        self.readings = {"mode": "CR", "setpoint": 47.0, "voltage": 12.01, "current": 0.255,
                         "power": 3.06, "load_enabled": True}

    def get_equipment_status(self, equipment_id):
        return {"capabilities": {"max_voltage": 150.0, "max_current": 40.0, "max_power": 200.0,
                                 "modes": ["CC", "CV", "CR", "CP"]}}

    def get_readings(self, equipment_id):
        return dict(self.readings)

    def send_command(self, equipment_id, command, parameters=None):
        self.commands.append((command, parameters or {}))
        return {"success": True, "data": None}


def _load():
    return Equipment(
        equipment_id="load_1", name="DL3021A", equipment_type=EquipmentType.ELECTRONIC_LOAD,
        manufacturer="Rigol", model="DL3021A", resource_name="USB::x",
        connection_status=ConnectionStatus.CONNECTED,
    )


def _run(panel, method_name, *args):
    method = getattr(type(panel), method_name)
    coroutine = getattr(method, "__wrapped__", method)
    return asyncio.run(coroutine(panel, *args))


def test_loads_get_this_panel():
    assert panel_class_for(EquipmentType.ELECTRONIC_LOAD) is ElectronicLoadPanel


def test_binding_adopts_the_loads_own_state_without_commanding(qapp):
    client = FakeLoadClient()
    panel = ElectronicLoadPanel()
    panel.set_instrument(_load(), client)

    assert panel.mode_combo.currentData() == "CR"
    assert panel.setpoint_spin.value() == pytest.approx(47.0)
    # "Load enabled"/"Load disabled" rather than "Input: ON/OFF":
    # the old wording named a terminal, which beside a supply's
    # Output button does not say whether this thing is sinking.
    assert panel.input_button.isChecked()
    assert panel.input_button.text() == "Load enabled"
    assert panel.voltage_display.text() == "12.010 V"
    assert panel.power_display.text() == "3.06 W"
    assert client.commands == []


def test_the_setpoint_ceiling_and_unit_follow_the_mode(qapp):
    panel = ElectronicLoadPanel()
    panel.set_instrument(_load(), FakeLoadClient())
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CC"))
    assert panel.setpoint_spin.maximum() == pytest.approx(40.0)
    assert "(A)" in panel.setpoint_label.text()
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CP"))
    assert panel.setpoint_spin.maximum() == pytest.approx(200.0)
    assert "(W)" in panel.setpoint_label.text()


def test_apply_sends_mode_then_the_matching_setpoint(qapp):
    client = FakeLoadClient()
    panel = ElectronicLoadPanel()
    panel.set_instrument(_load(), client)
    _run(panel, "_send_setpoint", "CP", "set_power", "power", 12.5)
    assert client.commands == [("set_mode", {"mode": "CP"}), ("set_power", {"power": 12.5})]
    assert panel.setpoint_indicator.text() == "Setpoint: 12.5 W"


def test_changing_the_mode_combo_alone_commands_nothing(qapp):
    """Only Apply sends. The re-range on a mode change must stay silent."""
    client = FakeLoadClient()
    panel = ElectronicLoadPanel()
    panel.set_instrument(_load(), client)
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CV"))
    panel.setpoint_spin.setValue(5.0)
    assert client.commands == []


def test_input_button_sends_set_input(qapp):
    client = FakeLoadClient()
    panel = ElectronicLoadPanel()
    panel.set_instrument(_load(), client)
    _run(panel, "_send_input", False)
    assert client.commands == [("set_input", {"enabled": False})]


def test_poll_updates_readouts_but_not_the_setpoint_being_edited(qapp):
    client = FakeLoadClient()
    panel = ElectronicLoadPanel()
    panel.set_instrument(_load(), client)
    panel.setpoint_spin.setValue(99.0)
    client.readings.update({"voltage": 11.5, "current": 1.0, "power": 11.5, "setpoint": 1.0, "mode": "CC"})

    _run(panel, "_poll")

    assert panel.current_display.text() == "1.000 A"
    assert panel.setpoint_indicator.text() == "Setpoint: 1 A"
    assert panel.setpoint_spin.value() == pytest.approx(99.0), "a poll overwrote an edit in progress"


def test_lock_gating(qapp):
    panel = ElectronicLoadPanel()
    panel.set_controls_enabled(False)
    assert not panel.apply_button.isEnabled() and not panel.input_button.isEnabled()
    panel.set_controls_enabled(True)
    assert panel.apply_button.isEnabled()


class TestTheInputButtonAgainstStaleReadings:
    """The panel polls five times a second while it commands, unordered.

    A reading taken before the click arrives after it, carrying the state
    from before. The panel used to ignore readings for two seconds after a
    click -- and recorded that moment inside the async slot, which only
    runs after the click has been handled, so a reading applied in between
    slipped through the window entirely. It now records the click where the
    click happens, and holds it only until the load is seen to agree.

    Reporting a load that is still sinking current as off is the dangerous
    direction to be wrong in, so a reading with no input state in it says
    nothing at all.
    """

    def panel(self, qapp):
        made = ElectronicLoadPanel()
        made.set_instrument(_load(), FakeLoadClient())
        made._send_input = lambda enabled: None
        return made

    def test_a_stale_reading_does_not_undo_a_click(self, qapp):
        panel = self.panel(qapp)
        panel.input_button.click()                          # ON -> OFF
        assert panel.input_button.isChecked() is False
        panel._apply_readings({"load_enabled": True})       # taken before the click
        assert panel.input_button.isChecked() is False, (
            "a reading older than the click put the input back on in the display")

    def test_the_load_gets_the_last_word_once_it_agrees(self, qapp):
        panel = self.panel(qapp)
        panel.input_button.click()                          # ON -> OFF
        panel._apply_readings({"load_enabled": False})      # it agrees
        panel._apply_readings({"load_enabled": True})       # switched at the front panel
        assert panel.input_button.isChecked() is True, (
            "agreement must hand authority back, rather than a timer expiring")

    def test_a_reading_with_no_input_state_says_nothing(self, qapp):
        panel = self.panel(qapp)
        assert panel.input_button.isChecked() is True
        panel._apply_readings({"voltage": 12.01, "current": 0.255})
        assert panel.input_button.isChecked() is True, (
            "a missing field was read as off, on a load that is still sinking")

    def test_a_command_the_load_never_took_stops_being_believed(self, qapp):
        panel = self.panel(qapp)
        panel.input_button.click()                          # ON -> OFF
        pending = panel._pending["input"]
        panel._pending["input"] = pending._replace(
            at=pending.at - panel.PENDING_TIMEOUT_SEC - 1)
        panel._apply_readings({"load_enabled": True})
        assert panel.input_button.isChecked() is True, (
            "the display would have gone on claiming the input was off")
