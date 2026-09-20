"""A half-typed setpoint must never reach the instrument.

Reported from the bench: typing a voltage into the supply's field, the field
kept changing under the operator and partial entries were accepted.

Two faults, and the first is the dangerous one.

A QDoubleSpinBox emits ``valueChanged`` on every keystroke by default, and
the panel sends each one. Typing 12.5 commanded the supply to 1 V, then
12 V, then 12.5 V. On a live bench that is not cosmetic: the instrument
really was driven to those values on the way past.

And the supply panel polls ten times a second, writing the instrument's
setpoint into the very field being typed into. blockSignals stopped those
writes from sending, not from replacing what the operator had entered.
"""

import asyncio
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
    from PyQt6.QtGui import QWheelEvent
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QAbstractSpinBox, QApplication

    from client.models.equipment import (ConnectionStatus, Equipment,
                                         EquipmentType)
    from client.ui.instruments.power_supply import PowerSupplyPanel

    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(not GUI_AVAILABLE, reason="PyQt6 is required")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _Client:
    """Records every command, so a partial send is visible."""

    def __init__(self):
        self.commands = []
        self.ws_manager = None

    def get_equipment_status(self, equipment_id):
        return {"capabilities": {"max_voltage": 30.0, "max_current": 5.0,
                                 "num_channels": 1}}

    def send_command(self, equipment_id, command, parameters=None):
        self.commands.append((command, dict(parameters or {})))
        return {"success": True, "data": {}}

    def get_readings(self, equipment_id):
        return {}


def _equipment():
    return Equipment(
        equipment_id="ps_36509eb5",
        name="9205B",
        equipment_type=EquipmentType.POWER_SUPPLY,
        manufacturer="B&K Precision",
        model="9205B",
        resource_name="USB0::11975::37376::800886011797210043::0::INSTR",
        connection_status=ConnectionStatus.CONNECTED,
    )


@pytest.fixture
def loop():
    """The send slots are @qasync.asyncSlot, so they need a loop to run on.

    Without one the coroutine is created and dropped: no command, no error.
    The previous loop is put back, because leaving it unset breaks tests
    that run later and call asyncio.get_event_loop().
    """
    try:
        previous = asyncio.get_event_loop_policy().get_event_loop()
    except Exception:
        previous = None
    made = asyncio.new_event_loop()
    asyncio.set_event_loop(made)
    yield made
    made.close()
    asyncio.set_event_loop(previous)


def settle(qapp, loop, times=4):
    """Let Qt deliver its signals and asyncio run what they scheduled."""
    for _ in range(times):
        qapp.processEvents()
        loop.run_until_complete(asyncio.sleep(0))


@pytest.fixture
def panel(qapp, loop):
    made = PowerSupplyPanel()
    made.equipment = _equipment()
    made.client = _Client()
    # Bind applies the protection; do it without the async capability read.
    made.commit_typed_values_on_enter_only()
    yield made
    made.stop()
    made.deleteLater()
    qapp.processEvents()


def voltage_sends(client):
    return [p.get("voltage") for name, p in client.commands if name == "set_voltage"]


class TestTypingDoesNotCommandTheInstrument:
    def test_a_spin_box_reports_once_the_edit_is_finished(self, panel):
        """Not per keystroke, which is Qt's default and sent 1, 12, 12.5."""
        for box in panel.findChildren(QAbstractSpinBox):
            assert box.keyboardTracking() is False, (
                f"{box.objectName() or box} still reports on every keystroke")

    def test_typing_a_voltage_sends_only_the_finished_value(self, panel, qapp, loop):
        panel.voltage_spinbox.setFocus()
        panel.voltage_spinbox.clear()
        QTest.keyClicks(panel.voltage_spinbox, "12.5")
        settle(qapp, loop)

        assert voltage_sends(panel.client) == [], (
            f"sent while still typing: {voltage_sends(panel.client)} -- this is "
            f"the bug, the supply was commanded to each partial value")

        QTest.keyClick(panel.voltage_spinbox, Qt.Key.Key_Return)
        settle(qapp, loop)
        assert voltage_sends(panel.client) == [pytest.approx(12.5)]

    def test_the_arrows_still_command_immediately(self, panel, qapp, loop):
        """Stepping is a finished value; it must not wait for Enter."""
        panel.voltage_spinbox.setValue(1.0)
        settle(qapp, loop)
        panel.client.commands.clear()
        panel.voltage_spinbox.stepUp()
        settle(qapp, loop)
        assert voltage_sends(panel.client), "stepping sent nothing"


class TestPollingDoesNotOverwriteWhatIsBeingTyped:
    def test_a_reading_leaves_a_field_being_typed_into_alone(self, panel, qapp,
                                                             monkeypatch):
        """Asserted against the guard, not against platform focus.

        Offscreen Qt will not always hand a widget keyboard focus, and a test
        that skips on the machine where it matters protects nothing.
        """
        panel.voltage_spinbox.clear()
        QTest.keyClicks(panel.voltage_spinbox, "12.5")
        before = panel.voltage_spinbox.text()
        monkeypatch.setattr(panel, "editing_in_progress", lambda: True)

        panel._apply_readings({"voltage_set": 3.0, "current_set": 0.5,
                               "voltage_actual": 3.0, "current_actual": 0.1})
        qapp.processEvents()

        assert panel.voltage_spinbox.text() == before, (
            "a poll overwrote the value being typed")

    def test_focus_in_the_panel_counts_as_editing(self, panel, qapp):
        """The guard's own input: whether the operator is in this panel."""
        panel.voltage_spinbox.clearFocus()
        qapp.processEvents()
        assert panel.editing_in_progress() is False
        panel.voltage_spinbox.setFocus()
        qapp.processEvents()
        if QApplication.focusWidget() is None:
            pytest.skip("this platform grants no keyboard focus offscreen")
        assert panel.editing_in_progress() is True

    def test_a_reading_updates_the_field_when_nobody_is_typing(self, panel, qapp):
        panel.voltage_spinbox.clearFocus()
        qapp.processEvents()
        panel._apply_readings({"voltage_set": 7.0, "current_set": 0.5,
                               "voltage_actual": 7.0, "current_actual": 0.1})
        qapp.processEvents()
        assert panel.voltage_spinbox.value() == pytest.approx(7.0), (
            "the setpoint must still track the instrument when idle")

    def test_showing_a_reading_never_commands_the_instrument(self, panel, qapp):
        panel.voltage_spinbox.clearFocus()
        panel.client.commands.clear()
        panel._apply_readings({"voltage_set": 9.0, "current_set": 1.0,
                               "voltage_actual": 9.0, "current_actual": 0.2})
        qapp.processEvents()
        assert panel.client.commands == [], (
            f"displaying a reading sent {panel.client.commands}")


def scroll(panel, dial, notches=1, modifier=Qt.KeyboardModifier.NoModifier):
    """One wheel notch over a dial, delivered the way Qt delivers it.

    Sent to the dial rather than handed to eventFilter directly, so the
    filter has to actually be installed. Calling the filter by hand would
    pass even if nothing had hooked it up -- and the handler this replaced
    was exactly that: correct-looking code that never ran.
    """
    centre = QPointF(dial.rect().center())
    event = QWheelEvent(
        centre, centre, QPoint(0, 0), QPoint(0, 120 * notches),
        Qt.MouseButton.NoButton, modifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(dial, event)


class TestScrollingADial:
    """The step sizes an operator asked for, after Qt's were wrong.

    QAbstractSlider moves by singleStep times the platform's scroll-lines
    setting -- three here -- and a dial unit is 0.1 V, so a notch moved
    0.30. It also treats Ctrl and Shift alike, both using pageStep, so Shift
    could not be finer than Ctrl.
    """

    def test_a_plain_notch_moves_a_tenth(self, panel, qapp, loop):
        panel.voltage_spinbox.setValue(1.00)
        settle(qapp, loop)
        scroll(panel, panel.voltage_dial)
        assert panel.voltage_spinbox.value() == pytest.approx(1.10)

    def test_ctrl_moves_a_whole_unit(self, panel, qapp, loop):
        panel.voltage_spinbox.setValue(1.00)
        settle(qapp, loop)
        scroll(panel, panel.voltage_dial,
               modifier=Qt.KeyboardModifier.ControlModifier)
        assert panel.voltage_spinbox.value() == pytest.approx(2.00)

    def test_shift_moves_a_hundredth(self, panel, qapp, loop):
        panel.voltage_spinbox.setValue(1.00)
        settle(qapp, loop)
        scroll(panel, panel.voltage_dial,
               modifier=Qt.KeyboardModifier.ShiftModifier)
        assert panel.voltage_spinbox.value() == pytest.approx(1.01)

    def test_scrolling_down_goes_down(self, panel, qapp, loop):
        panel.voltage_spinbox.setValue(1.00)
        settle(qapp, loop)
        scroll(panel, panel.voltage_dial, notches=-1)
        assert panel.voltage_spinbox.value() == pytest.approx(0.90)

    def test_the_current_dial_uses_the_same_steps(self, panel, qapp, loop):
        panel.current_spinbox.setValue(1.00)
        settle(qapp, loop)
        scroll(panel, panel.current_dial)
        assert panel.current_spinbox.value() == pytest.approx(1.10)
        scroll(panel, panel.current_dial,
               modifier=Qt.KeyboardModifier.ShiftModifier)
        assert panel.current_spinbox.value() == pytest.approx(1.11)

    def test_a_scrolled_value_is_sent_once(self, panel, qapp, loop):
        """Scrolling is a finished value, so it commands straight away."""
        panel.voltage_spinbox.setValue(1.00)
        settle(qapp, loop)
        panel.client.commands.clear()
        scroll(panel, panel.voltage_dial)
        settle(qapp, loop)
        assert voltage_sends(panel.client) == [pytest.approx(1.10)]


class TestAStaleReadingCannotMoveTheSetpoint:
    """Scrolling across a wide range left the field and the supply disagreeing.

    Sending is asynchronous and the panel keeps polling, so a reading
    already in flight carries the setpoint from before the command and
    arrives after it. On the bench the supply reached 32.49 V while a stale
    reading put 22.19 back in the field -- and the next click then sent
    22.19, dropping the supply ten volts to match the display. It looked
    like the display correcting itself; it was the instrument moving.
    """

    def test_a_reading_after_a_command_does_not_move_the_field(self, panel,
                                                               qapp, loop):
        panel.voltage_spinbox.setValue(22.19)
        settle(qapp, loop)
        # Scrolled up to 32.49, each notch commanding as it went.
        panel.voltage_spinbox.setValue(32.49)
        settle(qapp, loop)

        # A reading issued before that command, arriving after it.
        panel._apply_readings({"voltage_set": 22.19, "current_set": 10.0,
                               "voltage_actual": 22.19, "current_actual": 0.01,
                               "output_enabled": True})
        qapp.processEvents()

        assert panel.voltage_spinbox.value() == pytest.approx(32.49), (
            "a stale reading moved the field back; the next click would have "
            "sent it and dropped the supply")

    def test_the_field_tracks_the_instrument_again_once_things_settle(
            self, panel, qapp, loop, monkeypatch):
        panel.voltage_spinbox.setValue(12.0)
        settle(qapp, loop)
        # As if the last command were long ago: a knob turned on the
        # instrument itself must still reach the panel.
        monkeypatch.setattr(panel, "_setpoint_in_flight", lambda: False)
        panel._apply_readings({"voltage_set": 5.0, "current_set": 1.0,
                               "voltage_actual": 5.0, "current_actual": 0.0,
                               "output_enabled": True})
        qapp.processEvents()
        assert panel.voltage_spinbox.value() == pytest.approx(5.0)

    def test_the_window_opens_on_sending_not_on_the_reply(self, panel, qapp, loop):
        """The stale reading is already in flight when the command is sent."""
        assert panel._setpoint_in_flight() is False
        panel.voltage_spinbox.setValue(3.0)
        settle(qapp, loop)
        assert panel._setpoint_in_flight() is True
