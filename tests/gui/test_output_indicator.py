"""The Output indicator does not flash off on one odd reading.

Reported from the bench: scrolling a dial makes "Output: ON" flash briefly
to "Output: OFF" while the supply stays on.

Scrolling interleaves a setpoint write per notch with this panel's 10 Hz
poll, and the supply's answer to the output query can come back out of step.
The driver reads anything it does not recognise as "off" -- so one crossed
reply reported a live supply as off, and the panel believed it at once.

Being wrong in that direction is the dangerous one: it invites someone to
touch an output that is still live. So the indicator now waits for
consecutive readings to agree, and a reading that carries no output state
says nothing rather than "off".
"""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication

    from client.ui.instruments.power_supply import PowerSupplyPanel

    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(not GUI_AVAILABLE, reason="PyQt6 is required")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp):
    made = PowerSupplyPanel()
    yield made
    made.stop()
    made.deleteLater()
    qapp.processEvents()


def show_on(panel):
    """Get the indicator to a settled ON, as a live supply would."""
    for _ in range(panel.OUTPUT_STATE_CONFIRMATIONS):
        panel._show_output_state(True)
    assert panel.output_button.isChecked()
    return panel.output_button.text()


class TestOneOddReadingIsNotBelieved:
    def test_a_single_off_does_not_flip_a_live_supply(self, panel):
        was = show_on(panel)
        panel._show_output_state(False)
        assert panel.output_button.text() == was, (
            "one crossed reply flashed the indicator off -- the reported bug")
        assert panel.output_button.isChecked()

    def test_the_streak_resets_when_readings_agree_again(self, panel):
        show_on(panel)
        panel._show_output_state(False)     # one odd reading
        panel._show_output_state(True)      # back to normal
        panel._show_output_state(False)     # another, much later
        assert panel.output_button.isChecked(), (
            "two odd readings with a good one between them are not a change")

    def test_a_reading_with_no_output_state_says_nothing(self, panel):
        show_on(panel)
        panel._show_output_state(None)
        panel._show_output_state(None)
        assert panel.output_button.isChecked(), (
            "a missing field is not the same as off")


class TestARealChangeStillShows:
    def test_consecutive_offs_turn_the_indicator_off(self, panel):
        show_on(panel)
        for _ in range(panel.OUTPUT_STATE_CONFIRMATIONS):
            panel._show_output_state(False)
        assert panel.output_button.isChecked() is False
        assert panel.output_button.text() == "Output: OFF"

    def test_it_comes_back_on(self, panel):
        for _ in range(panel.OUTPUT_STATE_CONFIRMATIONS):
            panel._show_output_state(False)
        for _ in range(panel.OUTPUT_STATE_CONFIRMATIONS):
            panel._show_output_state(True)
        assert panel.output_button.isChecked() is True
        assert panel.output_button.text() == "Output: ON"

    def test_showing_the_state_never_commands_the_supply(self, panel):
        """blockSignals, or the indicator would switch the output itself."""
        sent = []
        panel.output_button.clicked.connect(lambda checked: sent.append(checked))
        for _ in range(panel.OUTPUT_STATE_CONFIRMATIONS * 2):
            panel._show_output_state(False)
            panel._show_output_state(True)
        assert sent == [], f"displaying a reading emitted {sent}"


class TestTheDriverSaysWhenAReplyMakesNoSense:
    """Reporting an unparsed reply as "off" is a confident lie, and silent."""

    def test_recognised_replies_are_read(self):
        from server.equipment.bk_power_supply import _output_is_on

        for answer in ("1", "ON", "on", " ON\n", "TRUE"):
            assert _output_is_on(answer, "res", "OUTP?") is True, answer
        for answer in ("0", "OFF", "off", " 0\r\n", "FALSE"):
            assert _output_is_on(answer, "res", "OUTP?") is False, answer

    def test_an_unrecognised_reply_is_logged(self, caplog):
        import logging

        from server.equipment.bk_power_supply import _output_is_on

        with caplog.at_level(logging.WARNING,
                             logger="server.equipment.bk_power_supply"):
            # What a crossed reply looks like: the answer to CURR?
            assert _output_is_on("1.200", "res", "OUTP?") is False
        assert any("neither on nor off" in r.message for r in caplog.records), (
            "an unparsed reply was reported as off with nothing in the log")
