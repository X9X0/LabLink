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


def _with_loop(qapp, action, limit=2.0):
    """Perform `action` with a loop running, then let what it scheduled run.

    qasync.asyncSlot needs a running loop at the moment the signal
    fires, so the widget interaction has to happen inside one -- not
    before it. Selecting a mode fires a synchronous handler that
    schedules the send; without turning the loop afterwards the test
    would look for a command that has not been issued yet.
    """
    import time

    async def scenario():
        action()
        deadline = time.monotonic() + limit
        # Quiet twice running, not once. _send_mode awaits the mode and
        # then a read-back, and a single quiet check can land between
        # the two -- which ends the loop with the task still going and
        # leaves "Task was destroyed but it is pending" in the output.
        quiet = 0
        while time.monotonic() < deadline:
            qapp.processEvents()
            await asyncio.sleep(0.005)
            others = [t for t in asyncio.all_tasks()
                      if t is not asyncio.current_task() and not t.done()]
            quiet = quiet + 1 if not others else 0
            if quiet >= 2:
                return

    asyncio.run(scenario())
    qapp.processEvents()


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


def test_changing_the_mode_combo_switches_the_load(qapp):
    """Selecting a mode applies it, as pressing CV on the front panel does.

    It used to send nothing until Apply, because one setpoint box serves
    all four modes and a number meaning amps in CC would mean ohms in
    CR. The instrument does not have that problem -- the user guide
    lists separate parameters under each mode key -- so the panel reads
    the new mode's own level back instead of carrying the old one over.

    The operator reported the selector looking dead, and this was half
    of why. The other half was the driver sending :SOUR:FUNC CV, which
    the instrument ignores.
    """
    client = FakeLoadClient()
    panel = ElectronicLoadPanel()
    panel.set_instrument(_load(), client)
    client.commands.clear()

    _with_loop(qapp, lambda: panel.mode_combo.setCurrentIndex(
        panel.mode_combo.findData("CV")))

    assert ("set_mode", {"mode": "CV"}) in client.commands, (
        f"selecting a mode sent nothing: {client.commands}")


def test_changing_the_mode_does_not_command_a_setpoint(qapp):
    """Switching mode must not push the previous mode's number at it."""
    client = FakeLoadClient()
    panel = ElectronicLoadPanel()
    panel.set_instrument(_load(), client)
    panel.setpoint_spin.setValue(5.0)
    client.commands.clear()

    _with_loop(qapp, lambda: panel.mode_combo.setCurrentIndex(
        panel.mode_combo.findData("CR")))

    sent = [name for name, _ in client.commands]
    assert "set_resistance" not in sent and "set_current" not in sent, (
        f"a setpoint was applied by a mode change: {client.commands}")


def test_the_setpoint_box_reranges_at_once(qapp):
    """Synchronously, not on the next turn of the loop.

    Read inside the action, before anything has been awaited, because
    reading afterwards would pass whether the re-range were immediate
    or scheduled -- and the box is on screen while the operator is
    looking at it.
    """
    panel = ElectronicLoadPanel()
    panel.set_instrument(_load(), FakeLoadClient())
    seen = {}

    def select_constant_power():
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CP"))
        seen["maximum"] = panel.setpoint_spin.maximum()
        seen["label"] = panel.setpoint_label.text()

    _with_loop(qapp, select_constant_power)

    assert seen["maximum"] == pytest.approx(200.0)
    assert "(W)" in seen["label"]


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


CAPABILITIES = {
    "max_voltage": 150.0, "max_current": 40.0, "max_power": 200.0,
    "modes": ["CC", "CV", "CR", "CP"],
    "current_ranges": [4.0, 40.0],
    "voltage_ranges": [15.0, 150.0],
    "resistance_ranges": [15.0, 15000.0],
}


class TestTheRangeSelector:
    """The user guide lists "range" among the parameters under each mode
    key -- CC has current and range, CV voltage and range -- so it sits
    beside the setpoint rather than in a settings dialog.

    The driver has had set_current_range, set_voltage_range and
    set_resistance_range all along, and the capabilities have carried
    the values. Nothing asked for either.
    """

    def _panel(self, client=None):
        panel = ElectronicLoadPanel()
        panel.set_instrument(_load(), client or FakeLoadClient())
        panel.configure(CAPABILITIES)
        return panel

    def test_it_offers_the_loads_own_two_ranges(self, qapp):
        panel = self._panel()
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CC"))
        values = [panel.range_combo.itemData(i)
                  for i in range(panel.range_combo.count())]
        assert values == [4.0, 40.0]

    def test_the_ranges_follow_the_mode(self, qapp):
        panel = self._panel()
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CV"))
        values = [panel.range_combo.itemData(i)
                  for i in range(panel.range_combo.count())]
        assert values == [15.0, 150.0], "still showing the CC ranges"

    def test_constant_power_hides_it(self, qapp):
        """These loads have no power range: :SOUR:CURR:RANG, :VOLT:RANG
        and :RES:RANG exist and nothing for watts. A control that is
        present but does nothing is worse than one that is absent."""
        panel = self._panel()
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CP"))
        assert not panel.range_combo.isVisible() or \
               panel.range_combo.count() == 0

    def test_the_units_are_shown(self, qapp):
        panel = self._panel()
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CR"))
        labels = [panel.range_combo.itemText(i)
                  for i in range(panel.range_combo.count())]
        assert any("Ohm" in text for text in labels), labels

    def test_choosing_one_sends_it(self, qapp):
        client = FakeLoadClient()
        panel = self._panel(client)
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CC"))
        client.commands.clear()

        _with_loop(qapp, lambda: panel.range_combo.setCurrentIndex(1))

        sent = [c for c in client.commands if c[0] == "set_current_range"]
        assert sent, f"choosing a range sent nothing: {client.commands}"
        assert sent[0][1] == {"current_range": 40.0}

    def test_a_load_that_reports_no_ranges_hides_it(self, qapp):
        """Not every load in the registry is a DL3000."""
        panel = ElectronicLoadPanel()
        panel.set_instrument(_load(), FakeLoadClient())
        panel.configure({"max_voltage": 60.0, "max_current": 30.0,
                         "modes": ["CC", "CV"]})
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CC"))
        assert panel.range_combo.count() == 0
