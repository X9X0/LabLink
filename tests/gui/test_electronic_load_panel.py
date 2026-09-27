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


#: Requests the panel makes to read the instrument, as opposed to
#: commands that change it. Binding asks for the ranges because
#: capabilities only say which ranges a load has, never which one it is
#: in -- so a test asserting the panel "commanded nothing" has to mean
#: it changed nothing, not that it stayed silent.
READS = {"get_ranges", "get_function_mode"}


def controls(client):
    """Just the commands that told the instrument to do something."""
    return [c for c in client.commands if c[0] not in READS]


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
    assert controls(client) == [], (
        f"binding changed the instrument: {controls(client)}")


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
    assert controls(client) == [("set_mode", {"mode": "CP"}),
                                ("set_power", {"power": 12.5})]
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
    assert controls(client) == [("set_input", {"enabled": False})]


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


CC_CAPABILITIES = dict(CAPABILITIES, supports_slew_rate=True, supports_von=True)


class TestTheCCOptions:
    """CC has two parameters beyond its level -- slew rate and starting
    voltage -- both listed under the CC key in the user guide, and both
    meaningless in CV, CR and CP.
    """

    def _panel(self, client=None, capabilities=None):
        panel = ElectronicLoadPanel()
        panel.set_instrument(_load(), client or FakeLoadClient())
        panel.configure(capabilities or CC_CAPABILITIES)
        return panel

    def test_they_show_in_cc(self, qapp):
        panel = self._panel()
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CC"))
        assert panel.cc_extras.isVisibleTo(panel)

    def test_they_hide_in_the_other_modes(self, qapp):
        """A slew rate in constant resistance is not a thing."""
        panel = self._panel()
        for mode in ("CV", "CR", "CP"):
            panel.mode_combo.setCurrentIndex(panel.mode_combo.findData(mode))
            assert not panel.cc_extras.isVisibleTo(panel), (
                f"the CC options are showing in {mode}")

    def test_a_load_without_them_never_shows_them(self, qapp):
        """Not every load in the registry is a DL3000."""
        panel = self._panel(capabilities=CAPABILITIES)
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CC"))
        assert not panel.cc_extras.isVisibleTo(panel)

    def test_applying_sends_both(self, qapp):
        client = FakeLoadClient()
        panel = self._panel(client)
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CC"))
        panel.slew_spin.setValue(0.25)
        panel.von_spin.setValue(3.0)
        client.commands.clear()

        _with_loop(qapp, panel._apply_cc_options)

        assert ("set_slew_rate", {"slew_rate": 0.25}) in client.commands
        assert ("set_von", {"von": 3.0}) in client.commands

    def test_nothing_is_sent_by_typing(self, qapp):
        """Every intermediate value of a spinbox being typed into is a
        real command on a load. That is why there is a button."""
        client = FakeLoadClient()
        panel = self._panel(client)
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CC"))
        client.commands.clear()

        panel.slew_spin.setValue(0.9)
        panel.von_spin.setValue(4.0)

        assert client.commands == [], (
            f"a spinbox commanded the load: {client.commands}")

    def test_von_is_ranged_to_the_load(self, qapp):
        panel = self._panel()
        assert panel.von_spin.maximum() == pytest.approx(150.0)

    def test_the_slew_box_invents_no_ceiling_of_its_own(self, qapp):
        """The per-model maximum is not something the panel knows. The
        load rejects what it cannot do, and says so now."""
        panel = self._panel()
        assert panel.slew_spin.maximum() >= 10.0
        assert panel.slew_spin.minimum() > 0


TRANSIENT_CAPABILITIES = dict(CC_CAPABILITIES, supports_transient=True,
                              transient_modes=["CON", "PUL", "TOG"])


class TestTheTransientSection:
    """Con, Pul and Tog. Inside CC, because that is where the
    instrument puts it: the levels are currents, and the guide calls it
    "transient operation mode in CC mode".
    """

    def _panel(self, client=None, capabilities=None):
        panel = ElectronicLoadPanel()
        panel.set_instrument(_load(), client or FakeLoadClient())
        panel.configure(capabilities or TRANSIENT_CAPABILITIES)
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CC"))
        return panel

    def test_it_shows_in_cc(self, qapp):
        panel = self._panel()
        assert panel.transient_group.isVisibleTo(panel)

    def test_it_hides_outside_cc(self, qapp):
        panel = self._panel()
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CV"))
        assert not panel.transient_group.isVisibleTo(panel)

    def test_a_load_without_it_never_shows_it(self, qapp):
        panel = self._panel(capabilities=CC_CAPABILITIES)
        assert not panel.transient_group.isVisibleTo(panel)

    def test_continuous_offers_frequency_and_duty(self, qapp):
        panel = self._panel()
        panel.transient_mode_combo.setCurrentIndex(
            panel.transient_mode_combo.findData("CON"))
        assert panel.frequency_spin.isVisibleTo(panel)
        assert panel.duty_spin.isVisibleTo(panel)
        assert not panel.a_width_spin.isVisibleTo(panel)

    def test_pulsed_offers_the_two_widths(self, qapp):
        panel = self._panel()
        panel.transient_mode_combo.setCurrentIndex(
            panel.transient_mode_combo.findData("PUL"))
        assert panel.a_width_spin.isVisibleTo(panel)
        assert panel.b_width_spin.isVisibleTo(panel)
        assert not panel.frequency_spin.isVisibleTo(panel)

    def test_toggle_offers_neither(self, qapp):
        """It alternates on triggers rather than on a clock."""
        panel = self._panel()
        panel.transient_mode_combo.setCurrentIndex(
            panel.transient_mode_combo.findData("TOG"))
        assert not panel.frequency_spin.isVisibleTo(panel)
        assert not panel.a_width_spin.isVisibleTo(panel)

    def test_the_two_timings_are_never_shown_together(self, qapp):
        """They describe the same thing -- period is A plus B, duty is A
        over the period -- so both visible means two contradictory
        settings and no way to tell which won."""
        panel = self._panel()
        for mode in ("CON", "PUL", "TOG"):
            panel.transient_mode_combo.setCurrentIndex(
                panel.transient_mode_combo.findData(mode))
            assert not (panel.frequency_spin.isVisibleTo(panel)
                        and panel.a_width_spin.isVisibleTo(panel)), mode

    def test_applying_continuous_sends_frequency_not_widths(self, qapp):
        client = FakeLoadClient()
        panel = self._panel(client)
        panel.transient_mode_combo.setCurrentIndex(
            panel.transient_mode_combo.findData("CON"))
        panel.level_a_spin.setValue(4.0)
        panel.level_b_spin.setValue(1.0)
        panel.frequency_spin.setValue(2.0)
        client.commands.clear()

        _with_loop(qapp, panel._apply_transient)

        names = [name for name, _ in client.commands]
        assert "set_transient_frequency" in names
        assert "set_transient_widths" not in names
        assert ("set_transient_levels",
                {"level_a": 4.0, "level_b": 1.0}) in client.commands

    def test_applying_pulsed_sends_widths_not_frequency(self, qapp):
        client = FakeLoadClient()
        panel = self._panel(client)
        panel.transient_mode_combo.setCurrentIndex(
            panel.transient_mode_combo.findData("PUL"))
        client.commands.clear()

        _with_loop(qapp, panel._apply_transient)

        names = [name for name, _ in client.commands]
        assert "set_transient_widths" in names
        assert "set_transient_frequency" not in names

    def test_the_slew_rates_go_with_it(self, qapp):
        client = FakeLoadClient()
        panel = self._panel(client)
        panel.rise_spin.setValue(0.25)
        panel.fall_spin.setValue(0.75)
        client.commands.clear()

        _with_loop(qapp, panel._apply_transient)

        assert ("set_transient_slew",
                {"rising": 0.25, "falling": 0.75}) in client.commands

    def test_nothing_is_sent_by_typing(self, qapp):
        client = FakeLoadClient()
        panel = self._panel(client)
        client.commands.clear()

        panel.level_a_spin.setValue(3.0)
        panel.frequency_spin.setValue(9.0)

        assert client.commands == [], (
            f"a spinbox commanded the load: {client.commands}")

    def test_arming_starts_the_generator_waiting(self, qapp):
        """A button, not a checkbox.

        :SOUR:TRAN:STAT reads back False after a trigger, and the guide
        calls it "the same effect as pressing the TRAN key": it arms
        the generator, which then sinks Level B and waits. A checkbox
        claims "on until I untick it", which is not what the instrument
        does -- on the bench it sat unticking itself.
        """
        client = FakeLoadClient()
        panel = self._panel(client)
        client.commands.clear()

        _with_loop(qapp, panel._arm_transient)

        assert ("set_transient_enabled", {"enabled": True}) in client.commands

    def test_the_group_is_not_checkable(self, qapp):
        panel = self._panel()
        assert not panel.transient_group.isCheckable(), (
            "a checkbox here promises a latch the instrument does not have")

    def test_the_trigger_button_fires_one(self, qapp):
        client = FakeLoadClient()
        panel = self._panel(client)
        client.commands.clear()

        _with_loop(qapp, panel._fire_trigger)

        assert ("trigger", {}) in client.commands

    def test_the_levels_are_ranged_to_the_load(self, qapp):
        panel = self._panel()
        assert panel.level_a_spin.maximum() == pytest.approx(40.0)
        assert panel.level_b_spin.maximum() == pytest.approx(40.0)


class TestTheRangePromptWhenTheInputIsLive:
    """The driver refuses a range change while the load is sinking, as
    the user guide's CAUTION requires. The panel's job is to make that
    refusal actionable rather than a dead end -- and to let the operator
    decide, because dropping a load mid-test changes what the device
    under test sees.
    """

    class Refusing(FakeLoadClient):
        """Refuses the range the way the driver does, until the input
        is switched off."""

        def __init__(self):
            super().__init__()
            self.input_live = True

        def send_command(self, equipment_id, command, parameters=None):
            parameters = parameters or {}
            if command == "set_input":
                self.input_live = bool(parameters.get("enabled"))
            if "range" in command and self.input_live:
                raise RuntimeError(
                    "Disable the load input before changing the current "
                    "range.")
            return super().send_command(equipment_id, command, parameters)

    def _panel(self, client):
        panel = ElectronicLoadPanel()
        panel.set_instrument(_load(), client)
        panel.configure(TRANSIENT_CAPABILITIES)
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CC"))
        return panel

    def test_declining_leaves_the_load_alone(self, qapp):
        client = self.Refusing()
        panel = self._panel(client)

        async def say_no(_put_it_up):
            return False
        panel._ask = say_no
        client.commands.clear()

        _with_loop(qapp, lambda: panel._send_range("set_current_range", 40.0))

        sent = [name for name, _ in client.commands]
        assert "set_input" not in sent, "it dropped the input anyway"
        assert client.input_live, "the load stopped sinking without consent"

    def test_accepting_turns_the_input_off_then_switches(self, qapp):
        client = self.Refusing()
        panel = self._panel(client)

        async def say_yes(_put_it_up):
            return True
        panel._ask = say_yes
        client.commands.clear()

        _with_loop(qapp, lambda: panel._send_range("set_current_range", 40.0))

        sent = [name for name, _ in client.commands]
        assert "set_input" in sent, "never disabled the input"
        assert sent.index("set_input") < len(sent) - 1
        assert "set_current_range" in sent[sent.index("set_input"):], (
            f"the range was not applied after the input went off: {sent}")

    def test_the_input_is_left_off_afterwards(self, qapp):
        """Re-enabling into a freshly changed range is a deliberate act,
        not something to do on the operator's behalf."""
        client = self.Refusing()
        panel = self._panel(client)

        async def say_yes(_put_it_up):
            return True
        panel._ask = say_yes

        _with_loop(qapp, lambda: panel._send_range("set_current_range", 40.0))

        assert not client.input_live
        assert not panel.input_button.isChecked()

    def test_an_unrelated_failure_is_not_turned_into_a_prompt(self, qapp):
        """Only the input refusal gets the offer; anything else is just
        an error."""
        client = FakeLoadClient()

        def boom(equipment_id, command, parameters=None):
            raise RuntimeError("the load is on fire")
        client.send_command = boom
        panel = self._panel(client)

        asked = []

        async def watch(_put_it_up):
            asked.append(1)
            return True
        panel._ask = watch

        _with_loop(qapp, lambda: panel._send_range("set_current_range", 40.0))

        assert not asked, "offered to drop the input over an unrelated error"

    def test_it_goes_straight_through_when_the_input_is_off(self, qapp):
        client = self.Refusing()
        client.input_live = False
        panel = self._panel(client)

        asked = []

        async def watch(_put_it_up):
            asked.append(1)
            return True
        panel._ask = watch
        client.commands.clear()

        _with_loop(qapp, lambda: panel._send_range("set_current_range", 40.0))

        assert not asked, "prompted even though nothing was sinking"
        assert ("set_current_range", {"current_range": 40.0}) in client.commands


class TestTheSelectorShowsTheRangeTheLoadIsIn:
    """Capabilities say which ranges a load has; only the load knows
    which one is selected, and get_readings does not carry it.

    The selector used to clear and repopulate itself and leave index 0
    showing, so a load sitting in its 40 A range displayed "Low (4 A)".
    On the bench that turned the safety prompt into a liar: picking
    "High" on a load already in High offered to drop a live input in
    order to send a command that would have changed nothing.
    """

    class Ranged(FakeLoadClient):
        """Answers get_ranges, and remembers what it was told to set."""

        def __init__(self, current_range=40.0):
            super().__init__()
            self.current_range = current_range

        def send_command(self, equipment_id, command, parameters=None):
            parameters = parameters or {}
            if command == "get_ranges":
                self.commands.append((command, parameters))
                return {"success": True, "data": {
                    "current_range": self.current_range,
                    "voltage_range": 150.0,
                    "resistance_range": 15000.0,
                }}
            if command == "set_current_range":
                self.current_range = float(parameters["current_range"])
            return super().send_command(equipment_id, command, parameters)

    def _panel(self, client):
        panel = ElectronicLoadPanel()
        panel.set_instrument(_load(), client)
        panel.configure(CAPABILITIES)
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CC"))
        return panel

    def test_it_asks_the_load_which_range_it_is_in(self, qapp):
        client = self.Ranged()
        self._panel(client)
        assert ("get_ranges", {}) in client.commands, (
            f"nothing ever asked: {client.commands}")

    def test_a_load_in_its_high_range_does_not_show_low(self, qapp):
        client = self.Ranged(current_range=40.0)
        panel = self._panel(client)
        assert panel.range_combo.currentData() == pytest.approx(40.0), (
            "the selector claimed a range the load was not in")

    def test_a_load_in_its_low_range_shows_low(self, qapp):
        client = self.Ranged(current_range=4.0)
        panel = self._panel(client)
        assert panel.range_combo.currentData() == pytest.approx(4.0)

    def test_choosing_the_range_it_is_already_in_sends_nothing(self, qapp):
        """The prompt must not cry wolf.

        This is the bench case: the load was in 40 A, the selector said
        4 A, and choosing 40 A produced a refusal and an offer to drop a
        live input -- all to tell the load to stay put.
        """
        client = self.Ranged(current_range=40.0)
        panel = self._panel(client)
        asked = []
        panel._ask = lambda put_it_up: asked.append(True)
        client.commands.clear()

        _with_loop(qapp, lambda: panel._send_range("set_current_range", 40.0))

        assert not asked, "it prompted to change to the range it was in"
        assert controls(client) == [], (
            f"it commanded the load anyway: {controls(client)}")

    def test_a_real_change_still_goes_through(self, qapp):
        client = self.Ranged(current_range=40.0)
        panel = self._panel(client)
        client.commands.clear()

        _with_loop(qapp, lambda: panel._send_range("set_current_range", 4.0))

        assert ("set_current_range", {"current_range": 4.0}) in client.commands

    def test_the_selector_remembers_what_it_applied(self, qapp):
        """Having changed range, choosing it again is a no-op too --
        without another round trip to find that out."""
        client = self.Ranged(current_range=40.0)
        panel = self._panel(client)
        _with_loop(qapp, lambda: panel._send_range("set_current_range", 4.0))
        client.commands.clear()

        _with_loop(qapp, lambda: panel._send_range("set_current_range", 4.0))

        assert controls(client) == [], (
            f"it re-sent a range it had just applied: {controls(client)}")

    def test_declining_snaps_back_to_where_the_load_really_is(self, qapp):
        """Answering No used to leave the selector on index 0, which on
        a load in its high range meant it went on lying."""
        client = TestTheRangePromptWhenTheInputIsLive.Refusing()
        client.current_range = 40.0

        def answer_ranges(equipment_id, command, parameters=None):
            if command == "get_ranges":
                return {"success": True,
                        "data": {"current_range": 40.0,
                                 "voltage_range": 150.0,
                                 "resistance_range": 15000.0}}
            return type(client).send_command(client, equipment_id, command,
                                             parameters)

        panel = ElectronicLoadPanel()
        panel.set_instrument(_load(), client)
        panel.configure(CAPABILITIES)
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CC"))
        panel._active_ranges = {"CC": 40.0}
        panel._show_ranges_for_mode()

        async def say_no(_put_it_up):
            return False
        panel._ask = say_no

        _with_loop(qapp, lambda: panel._send_range("set_current_range", 4.0))

        assert panel.range_combo.currentData() == pytest.approx(40.0), (
            "after declining, the selector showed a range the load was "
            "not in")


class TestTheSetpointKnob:
    """A knob on the load, built the way the supply's is.

    It commands as it turns, which is what a knob is for and what the
    supply's does; Apply stays for a value typed into the box. The
    wheel is taken over so Ctrl is coarse and Shift fine, because
    QAbstractSlider would otherwise move three dial units a notch and
    treat the two modifiers alike.

    The one thing that cannot be copied across is the scale. The
    supply's dial is a fixed x10 because volts are volts; here the
    setpoint is amps, volts, ohms or watts by turn, and 15 kOhm at x10
    would be 150,000 steps of something dragged with a mouse.
    """

    def _panel(self, client=None):
        panel = ElectronicLoadPanel()
        panel.set_instrument(_load(), client or FakeLoadClient())
        panel.configure(CAPABILITIES)
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CC"))
        return panel

    def test_the_knob_exists(self, qapp):
        panel = self._panel()
        assert panel.setpoint_dial is not None

    def test_its_span_is_the_modes_span(self, qapp):
        panel = self._panel()
        scale = panel._dial_scale()
        assert panel.setpoint_dial.maximum() == int(
            panel.setpoint_spin.maximum() * scale)

    @pytest.mark.parametrize("mode", ["CC", "CV", "CR", "CP"])
    def test_no_mode_gives_an_unusable_number_of_steps(self, qapp, mode):
        """A dial is dragged, not typed into."""
        panel = self._panel()
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData(mode))
        span = panel.setpoint_dial.maximum() - panel.setpoint_dial.minimum()
        assert 0 < span <= panel.MAX_DIAL_UNITS, (
            f"{mode}: {span} steps")

    def test_turning_it_moves_the_box(self, qapp):
        panel = self._panel()
        scale = panel._dial_scale()
        panel.setpoint_dial.setValue(int(2.5 * scale))
        assert panel.setpoint_spin.value() == pytest.approx(2.5, abs=1 / scale)

    def test_turning_it_commands_the_load(self, qapp):
        """The difference from Apply: a knob sends as it turns."""
        client = FakeLoadClient()
        panel = self._panel(client)
        client.commands.clear()

        _with_loop(qapp,
                   lambda: panel.setpoint_dial.setValue(
                       int(2.0 * panel._dial_scale())))

        sent = [c for c in client.commands if c[0] == "set_current"]
        assert sent, f"turning the knob sent nothing: {client.commands}"

    def test_showing_a_reading_commands_nothing(self, qapp):
        """The trap this kind of control falls into: the display writes
        back to the instrument."""
        client = FakeLoadClient()
        panel = self._panel(client)
        client.commands.clear()

        _with_loop(qapp, lambda: panel._show_setpoint(3.0))

        assert client.commands == [], (
            f"showing a reading commanded the load: {client.commands}")
        assert panel.setpoint_spin.value() == pytest.approx(3.0)

    def test_changing_mode_commands_no_setpoint(self, qapp):
        """Re-ranging the box for a new mode moves the knob with it, and
        a knob that commanded on every programmatic move would send a
        setpoint nobody asked for -- in the new mode's units."""
        client = FakeLoadClient()
        panel = self._panel(client)
        client.commands.clear()

        _with_loop(qapp, lambda: panel.mode_combo.setCurrentIndex(
            panel.mode_combo.findData("CV")))

        setpoints = [c for c in client.commands
                     if c[0] in ("set_current", "set_voltage",
                                 "set_resistance", "set_power")]
        assert setpoints == [], f"switching mode sent {setpoints}"

    def test_the_knob_follows_the_instrument(self, qapp):
        """A reading of 47 ohms in CR must move it, not just the box."""
        client = FakeLoadClient()
        panel = self._panel(client)
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CR"))

        _run(panel, "refresh_settings")

        scale = panel._dial_scale()
        assert panel.setpoint_dial.value() == pytest.approx(
            int(47.0 * scale), abs=1)


class TestTheLoadGroupLayout:
    """The knob, Apply and the input button must not sit on top of
    each other.

    They did. The knob was added at grid cell (0, 3) spanning three
    rows, which is exactly where the input button already was, so Qt
    drew one over the other and the panel shipped with a dial
    overlapping "Load disabled".

    Geometry rather than appearance: a test cannot say whether a layout
    looks right, but it can say whether two widgets occupy the same
    space, and that is the part that was wrong.
    """

    def _shown(self, qapp, width=1560):
        panel = ElectronicLoadPanel()
        panel.set_instrument(_load(), FakeLoadClient())
        panel.configure(CAPABILITIES)
        panel.resize(width, 400)
        panel.show()
        qapp.processEvents()
        return panel

    @staticmethod
    def _overlap(a, b):
        one, two = a.geometry(), b.geometry()
        return not (one.right() < two.left() or two.right() < one.left())

    def test_nothing_in_the_row_overlaps(self, qapp):
        panel = self._shown(qapp)
        pairs = (
            ("knob", panel.setpoint_dial, "Apply", panel.apply_button),
            ("knob", panel.setpoint_dial, "input", panel.input_button),
            ("Apply", panel.apply_button, "input", panel.input_button),
            ("setpoint", panel.setpoint_spin, "knob", panel.setpoint_dial),
        )
        for a_name, a, b_name, b in pairs:
            assert not self._overlap(a, b), (
                f"{a_name} at {a.geometry()} overlaps {b_name} at "
                f"{b.geometry()}")

    def test_they_read_left_to_right(self, qapp):
        """Fields, then the knob, then Apply, then the input button."""
        panel = self._shown(qapp)
        order = [name for _x, name in sorted((
            (panel.setpoint_spin.geometry().x(), "fields"),
            (panel.setpoint_dial.geometry().x(), "knob"),
            (panel.apply_button.geometry().x(), "apply"),
            (panel.input_button.geometry().x(), "input"),
        ))]
        assert order == ["fields", "knob", "apply", "input"], order

    def test_the_buttons_are_full_height(self, qapp):
        """They span the three rows, as the mock-up has them."""
        panel = self._shown(qapp)
        rows = panel.range_combo.geometry().bottom() - \
            panel.mode_combo.geometry().top()
        for name, button in (("Apply", panel.apply_button),
                             ("input", panel.input_button)):
            assert button.geometry().height() >= rows * 0.8, (
                f"{name} is {button.geometry().height()}px against "
                f"{rows}px of rows")

    def test_the_fields_do_not_sprawl(self, qapp):
        """A wide window should give the space to the buttons, not to a
        combo box a thousand pixels long."""
        panel = self._shown(qapp, width=1900)
        assert panel.mode_combo.geometry().width() <= 400, (
            panel.mode_combo.geometry().width())

    def test_it_still_holds_at_a_narrow_width(self, qapp):
        panel = self._shown(qapp, width=900)
        assert not self._overlap(panel.setpoint_dial, panel.apply_button)
        assert not self._overlap(panel.apply_button, panel.input_button)


#: A DL3021A as the driver actually reports it. supports_transient
#: matters here: without it the transient group is hidden and never
#: laid out, so a layout test sees an unpositioned 640x480 default and
#: cannot say anything about where it sits.
BATTERY_CAPABILITIES = dict(CAPABILITIES,
                            function_modes=["FIX", "LIST", "WAV", "BATT",
                                            "OCP", "OPP"],
                            supports_transient=True)


class TestTheBatteryGroup:
    """Battery discharge, the one function mode worth a panel.

    The driver has had the whole subsystem since e8fcc2b and nothing
    could reach it. List needs a step table and is its own piece of
    work. OCP and OPP are setters all the way down -- no query for the
    current a device under test tripped at, and no pass/fail -- and on
    this firmware asking for either selects battery discharge instead,
    which the driver refuses rather than pretends.
    """

    def _panel(self, client=None, capabilities=None):
        panel = ElectronicLoadPanel()
        panel.set_instrument(_load(), client or FakeLoadClient())
        panel.configure(capabilities or BATTERY_CAPABILITIES)
        return panel

    def test_it_is_there_when_the_load_has_the_mode(self, qapp):
        panel = self._panel()
        assert panel.battery_group.isVisibleTo(panel)

    def test_it_is_hidden_when_the_load_does_not(self, qapp):
        """Not every load in the registry is a DL3000."""
        panel = self._panel(capabilities=CAPABILITIES)   # no function_modes
        assert not panel.battery_group.isVisibleTo(panel)

    def test_entering_hands_over_the_setpoint(self, qapp):
        client = FakeLoadClient()
        panel = self._panel(client)
        client.commands.clear()

        _with_loop(qapp, lambda: panel.battery_enable.click())

        assert ("set_function_mode", {"function_mode": "BATT"}) in \
            client.commands, client.commands

    def test_leaving_asserts_the_regulation_mode(self, qapp):
        """Not the mirror of entering. The load accepts
        :SOUR:FUNC:MODE and ignores it when it will not leave the mode
        it is in, so fixed operation is reclaimed by set_mode."""
        client = FakeLoadClient()
        panel = self._panel(client)
        panel._show_function_mode("BATT")
        client.commands.clear()

        _with_loop(qapp, lambda: panel.battery_enable.click())

        sent = [c for c in client.commands]
        assert any(c[0] == "set_mode" for c in sent), sent
        assert not any(c[0] == "set_function_mode" and
                       c[1].get("function_mode") == "FIX" for c in sent), (
            "it tried to leave with a command the load ignores")

    def test_apply_sends_every_level_and_then_the_switches(self, qapp):
        """Order matters: arming a cut-off whose value has not been
        sent would run the discharge against whatever the load held."""
        client = FakeLoadClient()
        panel = self._panel(client)
        panel.battery_level_spin.setValue(0.5)
        panel.stop_volts_spin.setValue(3.0)
        panel.stop_volts_check.setChecked(True)
        client.commands.clear()

        _with_loop(qapp, lambda: panel.battery_apply_button.click())

        names = [c[0] for c in client.commands]
        assert "set_function_parameter" in names, client.commands
        assert "set_battery_cutoffs" in names, client.commands
        assert names.index("set_battery_cutoffs") > \
            names.index("set_function_parameter"), names

    def test_the_cutoff_switches_carry_the_checkboxes(self, qapp):
        client = FakeLoadClient()
        panel = self._panel(client)
        panel.stop_volts_check.setChecked(True)
        panel.stop_ah_check.setChecked(False)
        panel.stop_time_check.setChecked(True)
        client.commands.clear()

        _with_loop(qapp, lambda: panel.battery_apply_button.click())

        sent = [c for c in client.commands if c[0] == "set_battery_cutoffs"]
        assert sent, client.commands
        assert sent[0][1] == {"volts": True, "capacity": False, "time": True}

    def test_the_discharge_level_reaches_the_load(self, qapp):
        client = FakeLoadClient()
        panel = self._panel(client)
        panel.battery_level_spin.setValue(0.75)
        client.commands.clear()

        _with_loop(qapp, lambda: panel.battery_apply_button.click())

        levels = [c for c in client.commands
                  if c[0] == "set_function_parameter"
                  and c[1].get("name") == "battery_level"]
        assert levels and levels[0][1]["value"] == pytest.approx(0.75), levels


class TestTheBatteryResults:
    """Capacity, energy and elapsed time as the load reports them."""

    def _panel(self, qapp):
        panel = ElectronicLoadPanel()
        panel.set_instrument(_load(), FakeLoadClient())
        panel.configure(BATTERY_CAPABILITIES)
        return panel

    def test_it_shows_what_was_measured(self, qapp):
        panel = self._panel(qapp)
        panel._show_battery_results(
            {"capacity_ah": 2.5, "watt_hours": 11.25,
             "discharge_seconds": 3661})
        shown = panel.battery_results.text()
        assert "2.500 Ah" in shown, shown
        assert "11.250 Wh" in shown, shown
        assert "1:01:01" in shown, shown

    def test_an_unread_value_is_not_shown_as_zero(self, qapp):
        """None means the load did not say, which is not the same as
        nothing having been drawn."""
        panel = self._panel(qapp)
        panel._show_battery_results(
            {"capacity_ah": None, "watt_hours": None,
             "discharge_seconds": None})
        shown = panel.battery_results.text()
        assert "0.000" not in shown, shown
        assert shown.count("--") >= 3, shown

    def test_a_fresh_discharge_reads_zero(self, qapp):
        """The bench case: 0:0:0 from the load, parsed."""
        panel = self._panel(qapp)
        panel._show_battery_results(
            {"capacity_ah": 0.0, "watt_hours": 0.0, "discharge_seconds": 0.0})
        assert "0:00:00" in panel.battery_results.text()


class TestTheResultsAndModeStayLive:
    """A readout that never updates is worse than none: capacity would
    sit at whatever it read when the panel opened and look like a
    measurement."""

    class Battery(FakeLoadClient):
        """A load in battery mode with something to report."""

        def __init__(self, mode="BATT"):
            super().__init__()
            self.mode = mode

        def send_command(self, equipment_id, command, parameters=None):
            if command == "get_function_mode":
                self.commands.append((command, parameters or {}))
                return {"success": True, "data": self.mode}
            if command == "get_battery_results":
                self.commands.append((command, parameters or {}))
                return {"success": True,
                        "data": {"capacity_ah": 1.5, "watt_hours": 7.0,
                                 "discharge_seconds": 600}}
            return super().send_command(equipment_id, command, parameters)

    def _panel(self, client):
        panel = ElectronicLoadPanel()
        panel.set_instrument(_load(), client)
        panel.configure(BATTERY_CAPABILITIES)
        return panel

    def test_polling_updates_the_figures(self, qapp):
        client = self.Battery()
        panel = self._panel(client)
        panel._function_mode = "BATT"

        _run(panel, "poll")

        assert "1.500 Ah" in panel.battery_results.text(), \
            panel.battery_results.text()

    def test_it_does_not_ask_when_not_discharging(self, qapp):
        """Three extra queries a tick is worth it during a battery test
        and wasted the rest of the time."""
        client = self.Battery(mode="FIX")
        panel = self._panel(client)
        panel._function_mode = "FIX"
        client.commands.clear()

        _run(panel, "poll")

        assert not [c for c in client.commands
                    if c[0] == "get_battery_results"], client.commands

    def test_binding_adopts_the_loads_own_mode(self, qapp):
        """A load already discharging must not show "Enter battery
        mode", or pressing it sends the mode it is already in."""
        client = self.Battery(mode="BATT")
        panel = self._panel(client)

        _run(panel, "refresh_settings")

        assert panel.battery_enable.isChecked()
        assert "Leave" in panel.battery_enable.text(), \
            panel.battery_enable.text()

    def test_adopting_the_mode_commands_nothing(self, qapp):
        client = self.Battery(mode="BATT")
        panel = self._panel(client)
        client.commands.clear()

        _run(panel, "refresh_settings")

        wrote = [c for c in client.commands
                 if c[0] in ("set_function_mode", "set_mode")]
        assert wrote == [], f"showing the mode commanded the load: {wrote}"


class TestTheBatteryGroupIsCompact:
    """It shares the window with the readouts, so a row of height for
    nothing costs something visible.

    Discharge and Von are two rows against the cut-offs' three, which
    left the left column's third row empty and pushed the measured
    figures onto a fifth row of their own. The figures now sit in that
    gap and the row is gone.
    """

    def _shown(self, qapp):
        panel = ElectronicLoadPanel()
        panel.set_instrument(_load(), FakeLoadClient())
        panel.configure(BATTERY_CAPABILITIES)
        panel.resize(1960, 900)
        panel.show()
        qapp.processEvents()
        return panel

    def test_the_figures_share_a_row_with_a_cutoff(self, qapp):
        """Which is what proves the empty row is gone."""
        panel = self._shown(qapp)
        results = panel.battery_results.geometry()
        last_cutoff = panel.stop_time_spin.geometry()
        assert abs(results.y() - last_cutoff.y()) < 12, (
            f"figures at y={results.y()}, last cut-off at "
            f"y={last_cutoff.y()} -- they are on separate rows")

    def test_nothing_sits_below_the_figures(self, qapp):
        panel = self._shown(qapp)
        bottom = panel.battery_results.geometry().bottom()
        for name in ("battery_enable", "battery_apply_button",
                     "battery_level_spin", "battery_von_spin",
                     "stop_volts_spin", "stop_ah_spin", "stop_time_spin"):
            assert getattr(panel, name).geometry().top() <= bottom + 4, name

    def test_the_two_buttons_share_the_top_row(self, qapp):
        panel = self._shown(qapp)
        enter = panel.battery_enable.geometry()
        apply_ = panel.battery_apply_button.geometry()
        assert abs(enter.y() - apply_.y()) < 6, (enter, apply_)
        assert enter.right() < apply_.left(), "they overlap"

    def test_the_group_leaves_room_for_the_readouts(self, qapp):
        """The whole point of tightening it."""
        panel = self._shown(qapp)
        assert panel.battery_group.geometry().height() <= 150, (
            panel.battery_group.geometry().height())
        assert panel.views.geometry().height() > \
            panel.battery_group.geometry().height() * 2


class TestTransientAndBatterySitSideBySide:
    """Stacked, the two groups cost 292px of a window the readouts have
    to share. Side by side they cost 146px, and the three digits that
    are the point of the panel get the difference.
    """

    def _shown(self, qapp, width=1960, capabilities=None):
        panel = ElectronicLoadPanel()
        panel.set_instrument(_load(), FakeLoadClient())
        panel.configure(capabilities or BATTERY_CAPABILITIES)
        panel.resize(width, 900)
        panel.show()
        qapp.processEvents()
        return panel

    def test_they_share_a_row(self, qapp):
        panel = self._shown(qapp)
        transient = panel.transient_group.geometry()
        battery = panel.battery_group.geometry()
        assert abs(transient.y() - battery.y()) < 8, (transient, battery)
        assert transient.right() < battery.left(), "they overlap"

    def test_the_readouts_get_the_height(self, qapp):
        panel = self._shown(qapp)
        assert panel.views.geometry().height() > 500, (
            panel.views.geometry().height())

    def test_battery_takes_the_room_when_transient_hides(self, qapp):
        """Transient lives inside CC. In CV there is nobody to share
        with, and a half-width group beside empty space would be silly."""
        panel = self._shown(qapp)
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("CV"))
        qapp.processEvents()

        assert not panel.transient_group.isVisibleTo(panel)
        assert panel.battery_group.geometry().width() > 1500, (
            panel.battery_group.geometry().width())

    def test_transient_takes_the_room_on_a_load_with_no_battery(self, qapp):
        """Not every load in the registry is a DL3000.

        Transient is left supported here on purpose: a fixture with
        neither hides both groups, and a test that cannot see either
        one proves nothing about which takes the room.
        """
        no_battery = dict(CAPABILITIES, supports_transient=True)
        panel = self._shown(qapp, capabilities=no_battery)
        assert not panel.battery_group.isVisibleTo(panel)
        assert panel.transient_group.geometry().width() > 1500, (
            panel.transient_group.geometry().width())

    def test_the_fields_clamp_rather_than_compress(self, qapp):
        """Nothing here scrolls horizontally, so a narrow window must
        not squeeze the spin boxes into uselessness -- better that the
        groups hold their minimum and the panel overflows."""
        narrow = self._shown(qapp, width=1500)
        assert narrow.transient_group.geometry().width() >= 900, (
            narrow.transient_group.geometry().width())
        assert narrow.battery_group.geometry().width() >= 860, (
            narrow.battery_group.geometry().width())


class TestSendingAList:
    """The panel's half: shape before contents, and in an order the
    load can act on."""

    def _panel(self, client):
        panel = ElectronicLoadPanel()
        panel.set_instrument(_load(), client)
        panel.configure(BATTERY_CAPABILITIES)
        panel._open_list_dialog()
        return panel

    def test_the_button_is_there_in_every_mode(self, qapp):
        """A list runs in CC, CV, CR and CP. The CC extras row beside it
        hides in the other three; this must not."""
        panel = ElectronicLoadPanel()
        panel.set_instrument(_load(), FakeLoadClient())
        panel.configure(BATTERY_CAPABILITIES)
        for mode in ("CC", "CV", "CR", "CP"):
            panel.mode_combo.setCurrentIndex(panel.mode_combo.findData(mode))
            qapp.processEvents()
            assert panel.list_button.isVisibleTo(panel), mode

    def test_the_step_count_goes_before_the_steps(self, qapp):
        """A value written past the current length is one the
        instrument will not keep."""
        client = FakeLoadClient()
        panel = self._panel(client)
        panel._list_dialog._set_step_count(3)
        client.commands.clear()

        _with_loop(qapp, lambda: panel._send_list())

        names = [c[0] for c in client.commands]
        counts = [i for i, c in enumerate(client.commands)
                  if c[0] == "set_function_parameter"
                  and c[1].get("name") == "list_steps"]
        firsts = [i for i, c in enumerate(client.commands)
                  if c[0] == "set_list_step"]
        assert counts and firsts, names
        assert counts[0] < firsts[0], names

    def test_every_row_is_sent(self, qapp):
        client = FakeLoadClient()
        panel = self._panel(client)
        panel._list_dialog._set_step_count(4)
        client.commands.clear()

        _with_loop(qapp, lambda: panel._send_list())

        steps = [c for c in client.commands if c[0] == "set_list_step"]
        assert len(steps) == 4, steps
        assert [c[1]["step"] for c in steps] == [1, 2, 3, 4]

    def test_the_mode_and_cycles_reach_the_load(self, qapp):
        client = FakeLoadClient()
        panel = self._panel(client)
        dialog = panel._list_dialog
        dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData("CR"))
        dialog.cycles_spin.setValue(5)
        client.commands.clear()

        _with_loop(qapp, lambda: panel._send_list())

        assert ("set_list_mode", {"mode": "CR"}) in client.commands
        cycles = [c for c in client.commands
                  if c[0] == "set_function_parameter"
                  and c[1].get("name") == "list_count"]
        assert cycles and cycles[0][1]["value"] == pytest.approx(5.0)

    def test_the_end_state_is_sent_last(self, qapp):
        """It describes what happens after the run, so it has nothing
        to say until the run is defined."""
        client = FakeLoadClient()
        panel = self._panel(client)
        client.commands.clear()

        _with_loop(qapp, lambda: panel._send_list())

        names = [c[0] for c in client.commands]
        assert names[-1] == "set_list_end_state", names

    def test_opening_it_twice_reuses_the_one_dialog(self, qapp):
        """Otherwise each press leaves another window behind."""
        panel = self._panel(FakeLoadClient())
        first = panel._list_dialog
        panel._open_list_dialog()
        assert panel._list_dialog is first


class TestTheListButtonCostsNoHeight:
    """It shares the CC extras row rather than making one.

    The readouts have been given back every row that could be spared,
    twice, and a button that quietly took one back would undo that.
    """

    #: A DL3021A as the driver reports it. supports_slew_rate and
    #: supports_von matter: without them the extras row hides, row 3 is
    #: empty, and the button does make a row of its own -- which is what
    #: a fixture missing them appeared to show.
    FULL = dict(BATTERY_CAPABILITIES, supports_slew_rate=True,
                supports_von=True)

    def _height(self, qapp, capabilities):
        from PyQt6.QtWidgets import QGroupBox

        panel = ElectronicLoadPanel()
        panel.set_instrument(_load(), FakeLoadClient())
        panel.configure(capabilities)
        panel.resize(1960, 900)
        panel.show()
        qapp.processEvents()
        load_group = panel.findChildren(QGroupBox)[0]
        return panel, load_group.geometry().height()

    def test_it_shares_the_extras_row(self, qapp):
        panel, _height = self._height(qapp, self.FULL)
        extras = panel.cc_extras.geometry()
        button = panel.list_button.geometry()
        assert abs(extras.y() - button.y()) < 8, (extras, button)
        assert extras.right() <= button.left(), "they overlap"

    def test_the_readouts_keep_their_height(self, qapp):
        panel, _height = self._height(qapp, self.FULL)
        assert panel.views.geometry().height() > 500, (
            panel.views.geometry().height())


class TestRunningAList:
    """The editor could build a sequence and send it, and nothing could
    hand the setpoint to the list subsystem -- so the list never ran.

    Then this button selected :FUNCtion:MODE LIST and stopped there,
    because the guide has no :LIST:STARt and describes LIST as "the
    input regulation mode is determined by the activated list command".
    On the bench that only arms the list: the load sat with the RUN bit
    set, drawing a steady current, stepping nothing. A trigger is what
    runs it, so the button goes through the driver's start_list, which
    sets the source, arms and fires in that order.
    """

    def _panel(self, client=None):
        panel = ElectronicLoadPanel()
        panel.set_instrument(_load(), client or FakeLoadClient())
        panel.configure(BATTERY_CAPABILITIES)
        return panel

    def test_there_is_a_run_button(self, qapp):
        assert self._panel().list_run_button is not None

    def test_running_starts_the_list(self, qapp):
        client = FakeLoadClient()
        panel = self._panel(client)
        client.commands.clear()

        _with_loop(qapp, lambda: panel.list_run_button.click())

        assert any(c[0] == "start_list" for c in client.commands), \
            client.commands

    def test_running_does_not_merely_select_the_mode(self, qapp):
        """The bug this button shipped with.

        Selecting LIST and stopping there arms the load and runs
        nothing. Whatever else the panel sends, the run has to go
        through start_list, which is the only path that triggers.
        """
        client = FakeLoadClient()
        panel = self._panel(client)
        client.commands.clear()

        _with_loop(qapp, lambda: panel.list_run_button.click())

        sent = [c[0] for c in client.commands]
        assert "start_list" in sent, sent
        assert "set_function_mode" not in sent, (
            "arming the mode from the panel skips the trigger: %s" % sent)

    def test_stopping_stops_the_list(self, qapp):
        client = FakeLoadClient()
        panel = self._panel(client)
        panel._show_list_running(True)
        client.commands.clear()

        _with_loop(qapp, lambda: panel.list_run_button.click())

        assert any(c[0] == "stop_list" for c in client.commands), \
            client.commands

    def test_a_failed_start_leaves_the_button_where_the_load_is(self, qapp):
        """A refused start that left the button reading "Stop list"
        would invite the operator to stop a list that never began."""
        client = FakeLoadClient()

        def refuse(equipment_id, command, parameters=None):
            if command == "start_list":
                raise RuntimeError("locked by another session")
            return FakeLoadClient.send_command(
                client, equipment_id, command, parameters)

        panel = self._panel(client)
        client.send_command = refuse

        _with_loop(qapp, lambda: panel.list_run_button.click())

        assert not panel.list_run_button.isChecked()
        assert "Run" in panel.list_run_button.text()

    def test_the_button_says_which_way_it_goes(self, qapp):
        panel = self._panel()
        assert "Run" in panel.list_run_button.text()
        panel._show_list_running(True)
        assert "Stop" in panel.list_run_button.text()

    def test_it_follows_the_load_rather_than_the_last_click(self, qapp):
        """A load already running a list must not offer to start one."""
        panel = self._panel()
        panel._show_list_running(True)
        assert panel.list_run_button.isChecked()

    def test_the_mode_query_cannot_unpress_a_running_list(self, qapp):
        """The bench case, and the reason the button does not follow
        the mode.

        Run was pressed, the load set the RUN bit, and the button
        popped back out on the next refresh because :FUNC:MODE?
        answered WAV -- the waveform screen was up -- and WAV is not
        LIST. The list was running the whole time.
        """
        panel = self._panel()
        panel._show_list_running(True)

        panel._show_function_mode("WAV")

        assert panel.list_run_button.isChecked(), (
            "the mode query un-pressed a list that was running")

    def test_the_two_function_buttons_do_not_disagree(self, qapp):
        """One instrument, two buttons. Entering battery must un-press
        run, because the load cannot be doing both."""
        panel = self._panel()
        panel._show_list_running(True)
        assert panel.list_run_button.isChecked()

        panel._show_function_mode("BATT")
        assert not panel.list_run_button.isChecked()
        assert panel.battery_enable.isChecked()

    def test_the_run_bit_is_what_drives_it(self, qapp):
        """Straight from get_protection_status, which is the load's own
        word for whether a list is stepping."""
        client = FakeLoadClient()

        def with_status(equipment_id, command, parameters=None):
            if command == "get_protection_status":
                client.commands.append((command, parameters or {}))
                return {"success": True,
                        "data": {"raw": 16512, "list_running": True}}
            return FakeLoadClient.send_command(
                client, equipment_id, command, parameters)

        panel = self._panel(client)
        client.send_command = with_status

        _run(panel, "poll")

        assert panel.list_run_button.isChecked(), (
            "the RUN bit said it was running and the button did not")

    def test_showing_the_mode_commands_nothing(self, qapp):
        client = FakeLoadClient()
        panel = self._panel(client)
        client.commands.clear()

        panel._show_function_mode("LIST")
        qapp.processEvents()

        assert client.commands == [], client.commands

    def test_the_run_button_costs_no_height(self, qapp):
        """It shares the cell with Edit list, which shares the row with
        the CC extras."""
        from PyQt6.QtWidgets import QGroupBox

        full = dict(BATTERY_CAPABILITIES, supports_slew_rate=True,
                    supports_von=True)
        panel = ElectronicLoadPanel()
        panel.set_instrument(_load(), FakeLoadClient())
        panel.configure(full)
        panel.resize(1960, 900)
        panel.show()
        qapp.processEvents()

        assert abs(panel.list_run_button.geometry().y()
                   - panel.list_button.geometry().y()) < 6
        assert panel.views.geometry().height() > 500, (
            panel.views.geometry().height())
