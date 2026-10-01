"""Entering a SPD channel's five timing groups.

The guide: five timing setups per channel, each a voltage, a current
and how long to hold them, run one after another, 10000 s at most per
group. The instrument holds them itself -- they survive a
disconnection and can be set from the front panel -- so the editor
reads what is there before offering to change it.
"""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication, QDoubleSpinBox
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(not GUI_AVAILABLE, reason="PyQt6 is required")

if GUI_AVAILABLE:
    from client.ui.instruments.timer_dialog import (GROUPS, MAX_SECONDS,
                                                    TimerDialog, _spell)

_ALIVE = []


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _close(qapp):
    yield
    while _ALIVE:
        _ALIVE.pop().hide()
    qapp.processEvents()


def dialog(channel=1, max_voltage=32.0, max_current=3.2):
    made = TimerDialog(channel, max_voltage, max_current)
    _ALIVE.append(made)
    return made


class TestTheGrid:
    def test_there_are_five_groups(self, qapp):
        """Fixed by the instrument: five, always."""
        assert dialog().table.rowCount() == len(GROUPS) == 5

    def test_each_holds_volts_amps_and_seconds(self, qapp):
        made = dialog()
        assert made.table.columnCount() == 3
        labels = [made.table.horizontalHeaderItem(c).text()
                  for c in range(3)]
        assert "Voltage" in labels[0] and "Current" in labels[1]
        assert "Time" in labels[2]

    def test_the_rows_are_tall_enough_for_their_contents(self, qapp):
        """A hard-coded height clipped the digits on a Windows theme
        once already, in the list editor. Asked of a real spin box."""
        made = dialog()
        probe = QDoubleSpinBox().sizeHint().height()
        for row in range(made.table.rowCount()):
            assert made.table.rowHeight(row) >= probe, row

    def test_the_boxes_are_ranged_from_the_supply(self, qapp):
        made = dialog(max_voltage=16.0, max_current=8.0)
        assert made.table.cellWidget(0, 0).maximum() == pytest.approx(16.0)
        assert made.table.cellWidget(0, 1).maximum() == pytest.approx(8.0)

    def test_the_time_stops_at_the_documented_limit(self, qapp):
        assert dialog().table.cellWidget(0, 2).maximum() == pytest.approx(
            MAX_SECONDS)


class TestReadingWhatTheSupplyHolds:
    def test_groups_land_in_their_own_rows(self, qapp):
        made = dialog()
        made.load([{"group": 1, "voltage": 3.0, "current": 0.5, "seconds": 2},
                   {"group": 3, "voltage": 5.0, "current": 1.0, "seconds": 9}])
        steps = {s["group"]: s for s in made.steps()}
        assert steps[1]["voltage"] == pytest.approx(3.0)
        assert steps[3]["voltage"] == pytest.approx(5.0)
        assert steps[2]["voltage"] == pytest.approx(0.0)

    def test_an_unreportable_group_is_left_at_zero(self, qapp):
        """Not guessed at. A group the supply could not answer for is
        not a group holding some particular value."""
        made = dialog()
        made.load([{"group": 1, "voltage": None, "current": None,
                    "seconds": None}])
        assert made.steps()[0]["voltage"] == pytest.approx(0.0)

    def test_nothing_at_all_is_survivable(self, qapp):
        made = dialog()
        made.load([])
        made.load(None)
        assert len(made.steps()) == 5

    def test_reading_does_not_look_like_editing(self, qapp):
        """The boxes are wired to recompute the total; filling them
        from the instrument must not be mistaken for the operator
        changing something."""
        made = dialog()
        made.load([{"group": 1, "voltage": 3.0, "current": 0.5,
                    "seconds": 2}])
        assert "2" in made.total_label.text()


class TestTheTotal:
    def test_it_adds_the_groups_up(self, qapp):
        made = dialog()
        made.load([{"group": g, "voltage": 1.0, "current": 0.1,
                    "seconds": 10} for g in GROUPS])
        assert "50s" in made.total_label.text()

    def test_it_counts_only_groups_that_hold(self, qapp):
        made = dialog()
        made.load([{"group": 1, "voltage": 1.0, "current": 0.1,
                    "seconds": 5}])
        assert "1 group" in made.total_label.text()

    def test_an_empty_sequence_says_so(self, qapp):
        """Five groups all at zero seconds would finish at once, which
        is worth saying rather than showing "0s"."""
        made = dialog()
        made.load([])
        assert "at once" in made.total_label.text()

    @pytest.mark.parametrize("seconds,expected", [
        (0.5, "0.5s"), (45, "45s"), (90, "1m 30s"),
        (3700, "1h 01m 40s"), (10000, "2h 46m 40s"),
    ])
    def test_long_times_are_spelled_readably(self, seconds, expected):
        """10000 s is the limit, and "10000 s" tells an operator less
        than "2h 46m 40s"."""
        assert _spell(seconds) == expected


class TestSendingIt:
    def test_every_group_is_reported_including_the_empty_ones(self, qapp):
        """A group the operator cleared has to reach the instrument, or
        the sequence keeps running a step they think they removed."""
        made = dialog()
        made.load([{"group": 1, "voltage": 3.0, "current": 0.5,
                    "seconds": 2}])
        assert [s["group"] for s in made.steps()] == [1, 2, 3, 4, 5]

    def test_the_send_button_says_what_it_does(self, qapp):
        assert "supply" in dialog().send_button.text().lower()

    def test_it_does_not_block_the_event_loop(self, qapp):
        """Modeless, like the list editor: the operator wants to watch
        the readings while setting this up."""
        assert not dialog().isModal()


class TestWholeSeconds:
    """The supply keeps the time as an integer and truncates it.

    The guide gives only the maximum -- "the longest time of each group
    is 10000s" -- and says nothing about a minimum or a resolution. The
    bench does: asked for 0.9 s it stores 0, for 1.6 s it stores 1, for
    2.5 s it stores 2. So a second is the resolution, and a box
    offering tenths promises something the hardware does not have.
    """

    def test_the_time_box_takes_no_decimals(self, qapp):
        assert dialog().table.cellWidget(0, 2).decimals() == 0

    def test_volts_and_amps_still_do(self, qapp):
        """Only the time is integral. 0.5 A is a real setpoint."""
        made = dialog()
        assert made.table.cellWidget(0, 0).decimals() > 0
        assert made.table.cellWidget(0, 1).decimals() > 0

    def test_the_minimum_that_holds_is_one_second(self, qapp):
        from client.ui.instruments.timer_dialog import MIN_SECONDS

        assert MIN_SECONDS == 1.0

    def test_a_group_under_a_second_is_not_counted_as_running(self, qapp):
        """It holds for no time, so it is not one of the groups that
        will run -- saying "1 group" for it would be wrong."""
        made = dialog()
        made.load([{"group": 1, "voltage": 1.0, "current": 0.1,
                    "seconds": 0}])
        assert "at once" in made.total_label.text()

    def test_the_dialog_says_what_the_time_does(self, qapp):
        """Somebody typing 0.5 should be told why it will not hold."""
        from PyQt6.QtWidgets import QLabel

        made = dialog()
        said = " ".join(label.text() for label in made.findChildren(QLabel))
        assert "whole seconds" in said.lower()


class TestTheResolutionBelongsToTheInstrument:
    """Whole seconds is the SPD3303X-E's limit, not this editor's.

    B&K's timing profiles are finer, and when those are implemented
    the editor has to offer what they support rather than what this
    one supply happens to keep.
    """

    def _fine(self):
        """A timer with millisecond resolution and eight groups."""
        made = TimerDialog(1, 60.0, 25.0, groups=(1, 2, 3, 4, 5, 6, 7, 8),
                           seconds_decimals=3, min_seconds=0.001,
                           max_seconds=3600.0)
        _ALIVE.append(made)
        return made

    def test_a_finer_timer_gets_a_finer_box(self, qapp):
        assert self._fine().table.cellWidget(0, 2).decimals() == 3

    def test_its_step_matches_its_resolution(self, qapp):
        assert self._fine().table.cellWidget(0, 2).singleStep() == pytest.approx(
            0.001)

    def test_a_finer_timer_keeps_a_millisecond(self, qapp):
        made = self._fine()
        made.load([{"group": 1, "voltage": 5.0, "current": 1.0,
                    "seconds": 0.005}])
        assert made.steps()[0]["seconds"] == pytest.approx(0.005)

    def test_the_number_of_groups_is_the_instruments(self, qapp):
        """Five is the SPD's count, not a property of timers."""
        made = self._fine()
        assert made.table.rowCount() == 8
        assert [s["group"] for s in made.steps()] == [1, 2, 3, 4, 5, 6, 7, 8]

    def test_the_whole_seconds_note_is_only_for_instruments_that_truncate(
            self, qapp):
        """Telling somebody their times are whole seconds when they are
        not would be worse than saying nothing."""
        assert self._fine()._time_note() == ""
        assert "whole seconds" in dialog()._time_note()

    def test_the_blurb_counts_the_real_groups(self, qapp):
        from PyQt6.QtWidgets import QLabel

        said = " ".join(label.text()
                        for label in self._fine().findChildren(QLabel))
        assert "8 groups" in said

    def test_a_finer_minimum_is_what_counts_as_holding(self, qapp):
        made = self._fine()
        made.load([{"group": 1, "voltage": 5.0, "current": 1.0,
                    "seconds": 0.002}])
        assert "1 group" in made.total_label.text(), made.total_label.text()
