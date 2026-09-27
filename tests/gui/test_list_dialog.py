"""The list sequence editor.

A list is a profile the instrument runs on its own clock: each step has
a level, a dwell and a slew rate, and dwell goes down to 50
microseconds. That lower bound is the whole reason the feature exists
-- a test sequence step is a host-side sleep and an HTTP round trip, so
anything under about a tenth of a second can only be done here.

In a dialog because a list is configuration rather than monitoring: it
is built, sent, armed, and then the operator watches the ordinary
readouts. A step table on the panel would have cost the readouts the
height that two rounds of layout work had just given them back.
"""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    import PyQt6.QtWidgets  # noqa: F401

    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(not GUI_AVAILABLE, reason="PyQt6 is required")

if GUI_AVAILABLE:
    from PyQt6.QtWidgets import QApplication

    from client.ui.instruments.list_dialog import (MAX_CYCLES, MAX_STEPS,
                                                   MAX_WIDTH, MIN_STEPS,
                                                   MIN_WIDTH, ListDialog)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(qapp):
    made = ListDialog(max_current=40.0)
    yield made
    made.deleteLater()
    qapp.processEvents()


class TestItStartsUsable:
    def test_it_opens_with_the_fewest_steps_a_list_can_have(self, dialog):
        """Two, and the load's rule rather than ours: ":SOURce:LIST:STEP
        ... Its range is from 2 to 512". A one-step list is not a list."""
        assert dialog.table.rowCount() == MIN_STEPS

    def test_the_columns_say_what_the_numbers_are(self, dialog):
        headers = [dialog.table.horizontalHeaderItem(i).text()
                   for i in range(dialog.table.columnCount())]
        assert "Level (A)" in headers[0]
        assert "Dwell" in headers[1]

    def test_the_units_follow_the_mode(self, dialog):
        """A list in CR steps through ohms, and a column headed amps
        would be a lie."""
        dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData("CR"))
        headers = [dialog.table.horizontalHeaderItem(i).text()
                   for i in range(dialog.table.columnCount())]
        assert "Ohm" in headers[0], headers


class TestTheStepTable:
    def test_a_step_can_be_added(self, dialog):
        before = dialog.table.rowCount()
        dialog.add_button.click()
        assert dialog.table.rowCount() == before + 1

    def test_it_will_not_go_below_two(self, dialog):
        for _ in range(5):
            dialog.remove_button.click()
        assert dialog.table.rowCount() == MIN_STEPS

    def test_remove_is_disabled_at_the_floor(self, dialog):
        assert not dialog.remove_button.isEnabled(), (
            "a button that does nothing is worse than one that is greyed")

    def test_it_will_not_pass_the_instruments_ceiling(self, dialog):
        dialog._set_step_count(MAX_STEPS)
        dialog.add_button.click()
        assert dialog.table.rowCount() == MAX_STEPS
        assert not dialog.add_button.isEnabled()

    def test_the_dwell_reaches_fifty_microseconds(self, dialog):
        """The reason a list exists rather than a test sequence."""
        dwell = dialog.table.cellWidget(0, 1)
        assert dwell.minimum() == pytest.approx(MIN_WIDTH)
        assert dwell.maximum() == pytest.approx(MAX_WIDTH)
        dwell.setValue(MIN_WIDTH)
        assert dwell.value() == pytest.approx(MIN_WIDTH), (
            "the spin box cannot express the shortest step the load takes")

    def test_a_level_cannot_exceed_the_load(self, dialog):
        level = dialog.table.cellWidget(0, 0)
        level.setValue(999.0)
        assert level.value() <= 40.0


class TestWhatItHandsBack:
    def test_the_steps_are_numbered_from_one(self, dialog):
        """As the panel counts them; the driver converts to the
        instrument's zero base."""
        steps = dialog.steps()
        assert [s["step"] for s in steps] == list(
            range(1, len(steps) + 1))

    def test_every_row_becomes_a_step(self, dialog):
        dialog._set_step_count(5)
        dialog.table.cellWidget(2, 0).setValue(1.25)
        dialog.table.cellWidget(2, 1).setValue(0.002)

        steps = dialog.steps()
        assert len(steps) == 5
        assert steps[2]["step"] == 3
        assert steps[2]["level"] == pytest.approx(1.25)
        assert steps[2]["width"] == pytest.approx(0.002)

    def test_the_settings_carry_the_shape(self, dialog):
        dialog._set_step_count(4)
        dialog.cycles_spin.setValue(7)
        dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData("CV"))

        settings = dialog.settings()
        assert settings == {"mode": "CV", "cycles": 7, "step_count": 4,
                            "hold_last": True}

    def test_cycles_reach_the_instruments_maximum(self, dialog):
        dialog.cycles_spin.setValue(MAX_CYCLES)
        assert dialog.settings()["cycles"] == MAX_CYCLES

    def test_zero_cycles_is_allowed(self, dialog):
        """The guide's range starts at zero, which repeats until
        something stops it."""
        dialog.cycles_spin.setValue(0)
        assert dialog.settings()["cycles"] == 0


class TestShowingWhatTheLoadHolds:
    def test_it_fills_from_a_readback(self, dialog):
        dialog.load(
            {"mode": "CR", "cycles": 3, "hold_last": False},
            [{"level": 10.0, "width": 0.5, "slew": 0.2},
             {"level": 20.0, "width": 1.5, "slew": 0.3},
             {"level": 30.0, "width": 2.5, "slew": 0.4}],
        )
        assert dialog.table.rowCount() == 3
        assert dialog.mode_combo.currentData() == "CR"
        assert dialog.cycles_spin.value() == 3
        assert dialog.settings()["hold_last"] is False
        assert dialog.table.cellWidget(1, 0).value() == pytest.approx(20.0)

    def test_a_short_readback_still_leaves_a_usable_list(self, dialog):
        """The load cannot hold fewer than two steps, so neither can
        the editor showing them."""
        dialog.load({"mode": "CC", "cycles": 1}, [{"level": 1.0}])
        assert dialog.table.rowCount() >= MIN_STEPS

    def test_a_missing_field_leaves_its_cell_alone(self, dialog):
        """get_list_step returns None for anything it could not read."""
        before = dialog.table.cellWidget(0, 2).value()
        dialog.load({"mode": "CC", "cycles": 1},
                    [{"level": 1.0, "width": None, "slew": None},
                     {"level": 2.0, "width": None, "slew": None}])
        assert dialog.table.cellWidget(0, 2).value() == pytest.approx(before)


class TestTheRowsFitTheirContents:
    """A row shorter than the widget in it clips the digits, and gives
    no other sign of trouble.

    The height was a measured constant -- 24px, taken against this
    machine's spin box -- and on a Windows theme the same control is
    taller. The values were there and cut in half.
    """

    def test_a_row_is_taller_than_the_spin_box_in_it(self, dialog):
        spin = dialog.table.cellWidget(0, 0)
        assert dialog.table.rowHeight(0) > spin.sizeHint().height(), (
            f"row {dialog.table.rowHeight(0)}px against a spin box "
            f"{spin.sizeHint().height()}px -- the digits are clipped")

    def test_it_asks_the_widget_rather_than_assuming(self, dialog):
        """The number differs by theme and by display scaling, so it
        cannot be a constant."""
        from PyQt6.QtWidgets import QDoubleSpinBox

        probe = QDoubleSpinBox()
        assert dialog._row_height() >= probe.sizeHint().height() + 4

    def test_added_rows_get_it_too(self, dialog):
        """setDefaultSectionSize covers the rows the table makes; a row
        added later needs it applying."""
        dialog.add_button.click()
        last = dialog.table.rowCount() - 1
        spin = dialog.table.cellWidget(last, 0)
        assert dialog.table.rowHeight(last) > spin.sizeHint().height()

    def test_every_row_is_the_same_height(self, dialog):
        dialog._set_step_count(5)
        heights = {dialog.table.rowHeight(r)
                   for r in range(dialog.table.rowCount())}
        assert len(heights) == 1, heights


class TestTheColumnsUseTheWidth:
    """Fixed columns left most of the table empty to the right of Slew,
    which reads as though something is missing."""

    def test_they_fill_the_table(self, dialog, qapp):
        dialog.resize(900, 500)
        dialog.show()
        qapp.processEvents()
        used = sum(dialog.table.columnWidth(c) for c in range(3))
        assert used > dialog.table.geometry().width() * 0.9, (
            f"{used}px of columns in a {dialog.table.geometry().width()}px "
            f"table")

    def test_they_share_it_evenly(self, dialog, qapp):
        dialog.resize(900, 500)
        dialog.show()
        qapp.processEvents()
        widths = [dialog.table.columnWidth(c) for c in range(3)]
        assert max(widths) - min(widths) <= 2, widths
