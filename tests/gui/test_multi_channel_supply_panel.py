"""A supply with more than one channel gets a column each.

Panels are chosen by equipment type, so one PowerSupplyPanel serves
the three-channel Siglent and the single-channel B&K supplies beside
it. The columns are therefore an alternative body, not a replacement:
a supply with one channel has to look exactly as it always has, and
most of the tests here are about that as much as about the columns.
"""

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
    from client.ui.instruments.channel_strip import ChannelStrip
    from client.ui.instruments.power_supply import PowerSupplyPanel


#: What the SPD3303X-E reports.
SIGLENT = {
    "channels": 3,
    "programmable_channels": [1, 2],
    "max_voltage": 32.0,
    "max_current": 3.2,
    "has_fixed_rail": True,
}

#: What a B&K 9205B reports.
SINGLE = {"channels": 1, "max_voltage": 60.0, "max_current": 25.0}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


#: Panels are kept alive for the length of a test. A shown QWidget
#: collected while Qt still holds pointers into it takes the
#: interpreter down with an access violation rather than a failure,
#: which is a miserable thing to debug.
_ALIVE = []


@pytest.fixture(autouse=True)
def _close_panels(qapp):
    yield
    while _ALIVE:
        made = _ALIVE.pop()
        made.hide()
        made.setParent(None)
    qapp.processEvents()


def panel(qapp, capabilities, width=1400):
    made = PowerSupplyPanel()
    made.configure(capabilities)
    made.resize(width, 700)
    made.show()
    qapp.processEvents()
    # Showing the panel parks focus in the first spin box, and a
    # focused setpoint box means "being typed into" -- which would
    # hold that channel's setpoints back. Nobody is typing in a test.
    focused = QApplication.focusWidget()
    if focused is not None:
        focused.clearFocus()
    qapp.processEvents()
    _ALIVE.append(made)
    return made


class TestOneChannelIsUnchanged:
    """The case that must not regress. Four of the five instruments on
    the bench are single-channel."""

    def test_no_columns_are_built(self, qapp):
        assert panel(qapp, SINGLE)._strips == {}

    def test_the_original_body_is_the_one_on_screen(self, qapp):
        made = panel(qapp, SINGLE)
        assert made._controls_group.isVisible()
        assert made.views.isVisible()

    def test_the_channel_furniture_stays_out_of_the_way(self, qapp):
        made = panel(qapp, SINGLE)
        assert not made.channel_bar.isVisible()
        assert not made.channel_area.isVisible()

    def test_a_server_that_reports_nothing_still_gets_a_panel(self, qapp):
        """An older server sends no capabilities at all."""
        made = panel(qapp, {})
        assert made._controls_group.isVisible()
        assert made._strips == {}

    def test_the_original_controls_are_still_ranged(self, qapp):
        made = panel(qapp, SINGLE)
        assert made.voltage_spinbox.maximum() == pytest.approx(60.0)


class TestThreeChannelsGetThreeColumns:
    def test_one_strip_per_channel(self, qapp):
        assert sorted(panel(qapp, SIGLENT)._strips) == [1, 2, 3]

    def test_they_sit_side_by_side(self, qapp):
        made = panel(qapp, SIGLENT)
        first, second, third = (made._strips[n].geometry() for n in (1, 2, 3))
        assert first.right() <= second.left(), "CH1 and CH2 overlap"
        assert second.right() <= third.left(), "CH2 and CH3 overlap"
        assert abs(first.y() - second.y()) < 8, "they are not on one row"

    def test_the_single_channel_body_steps_aside(self, qapp):
        """Both bodies up at once would draw the same instrument
        twice, and poll it twice."""
        made = panel(qapp, SIGLENT)
        assert not made._controls_group.isVisible()
        assert not made.views.isVisible()

    def test_the_columns_are_ranged_from_the_capabilities(self, qapp):
        made = panel(qapp, SIGLENT)
        assert made._strips[1].voltage_spinbox.maximum() == pytest.approx(32.0)
        assert made._strips[2].current_spinbox.maximum() == pytest.approx(3.2)

    def test_the_dials_are_ranged_with_the_boxes(self, qapp):
        """A dial left at another instrument's scale puts the needle
        somewhere the number is not."""
        made = panel(qapp, SIGLENT)
        assert made._strips[1].voltage_dial.maximum() == 320   # 32.0 V
        assert made._strips[1].current_dial.maximum() == 32    # 3.2 A

    def test_each_channel_has_its_own_switch_and_indicators(self, qapp):
        made = panel(qapp, SIGLENT)
        for number in (1, 2):
            strip = made._strips[number]
            assert strip.output_button is not None
            assert strip.cv_indicator is not None
            assert strip.cc_indicator is not None
        # And they are not the same widgets shared between columns.
        assert (made._strips[1].output_button
                is not made._strips[2].output_button)


class TestTheFixedRail:
    """CH3 answers no measurement query, and does not refuse them -- it
    never replies, so asking costs a full read timeout."""

    def test_it_is_not_programmable(self, qapp):
        made = panel(qapp, SIGLENT)
        assert made._strips[3].programmable is False
        assert made._strips[1].programmable is True

    def test_it_offers_no_setpoints(self, qapp):
        strip = panel(qapp, SIGLENT)._strips[3]
        assert strip.voltage_spinbox is None
        assert strip.current_spinbox is None

    def test_it_gets_no_readout_column(self, qapp):
        """Nothing to put in one. CH1 and CH2 get a column each."""
        made = panel(qapp, SIGLENT)
        assert sorted(made._channel_views) == [1, 2]

    def test_it_still_has_its_switch(self, qapp):
        """The one thing remote control can do with it."""
        assert panel(qapp, SIGLENT)._strips[3].output_button is not None

    def test_it_says_why_there_are_no_numbers(self, qapp):
        """Three dashes with no explanation reads as a fault."""
        from PyQt6.QtWidgets import QLabel

        strip = panel(qapp, SIGLENT)._strips[3]
        said = " ".join(label.text() for label in strip.findChildren(QLabel))
        assert "front panel" in said.lower()

    def test_a_supply_with_no_fixed_rail_has_none_of_this(self, qapp):
        two = dict(SIGLENT, channels=2, has_fixed_rail=False,
                   programmable_channels=[1, 2])
        made = panel(qapp, two)
        assert sorted(made._strips) == [1, 2]
        assert all(s.programmable for s in made._strips.values())


class TestHidingAChannel:
    def test_there_is_a_box_per_channel(self, qapp):
        assert sorted(panel(qapp, SIGLENT)._channel_boxes) == [1, 2, 3]

    def test_unchecking_hides_the_column(self, qapp):
        made = panel(qapp, SIGLENT)
        made._channel_boxes[3].setChecked(False)
        qapp.processEvents()
        assert not made._strips[3].isVisible()

    def test_the_others_take_the_width(self, qapp):
        """The point of hiding one: the readings left on screen get
        bigger, rather than a gap appearing where the column was."""
        made = panel(qapp, SIGLENT)
        before = made._strips[1].width()

        made._channel_boxes[3].setChecked(False)
        qapp.processEvents()

        assert made._strips[1].width() > before, (
            "hiding a channel left the others the size they were: %d -> %d"
            % (before, made._strips[1].width()))

    def test_showing_it_again_gives_the_width_back(self, qapp):
        made = panel(qapp, SIGLENT)
        wide = made._strips[1].width()
        made._channel_boxes[3].setChecked(False)
        qapp.processEvents()
        made._channel_boxes[3].setChecked(True)
        qapp.processEvents()
        assert made._strips[1].width() == pytest.approx(wide, abs=4)

    def test_hiding_every_channel_is_survivable(self, qapp):
        made = panel(qapp, SIGLENT)
        for number in (1, 2, 3):
            made._channel_boxes[number].setChecked(False)
        qapp.processEvents()
        assert not any(s.isVisible() for s in made._strips.values())


class TestApplyingAReading:
    def _made(self, qapp):
        return panel(qapp, SIGLENT)

    REPLY = {
        "channels": [
            {"channel": 1, "voltage_set": 5.0, "current_set": 2.0,
             "voltage_actual": 4.97, "current_actual": 1.20,
             "power_actual": 5.96, "output_enabled": True,
             "in_cv_mode": True, "in_cc_mode": False},
            {"channel": 2, "voltage_set": 3.3, "current_set": 0.5,
             "voltage_actual": 3.30, "current_actual": 0.50,
             "power_actual": 1.65, "output_enabled": True,
             "in_cv_mode": False, "in_cc_mode": True},
        ],
        "unreadable": [{"channel": 3, "why": "fixed rail", "switchable": True}],
        "coupling": "independent",
    }

    def _digits(self, made, channel):
        return [d.text() for d
                in made._channel_views[channel].displays.values()]

    def test_each_column_shows_its_own_reading(self, qapp):
        made = self._made(qapp)
        made._apply_all_readings(self.REPLY)
        assert "4.970 V" in self._digits(made, 1)
        assert "3.300 V" in self._digits(made, 2)

    def test_watts_reach_the_third_readout(self, qapp):
        """The figure the operator was working out in their head."""
        made = self._made(qapp)
        made._apply_all_readings(self.REPLY)
        assert "5.96 W" in self._digits(made, 1)

    def test_the_setpoints_land_on_the_right_column(self, qapp):
        made = self._made(qapp)
        made._apply_all_readings(self.REPLY)
        assert made._strips[1].voltage_spinbox.value() == pytest.approx(5.0)
        assert made._strips[2].voltage_spinbox.value() == pytest.approx(3.3)

    def test_cv_and_cc_are_per_channel(self, qapp):
        made = self._made(qapp)
        made._apply_all_readings(self.REPLY)
        assert "bold" in made._strips[1].cv_indicator.styleSheet()
        assert "bold" in made._strips[2].cc_indicator.styleSheet()

    def test_the_output_buttons_follow(self, qapp):
        made = self._made(qapp)
        made._apply_all_readings(self.REPLY)
        assert made._strips[1].output_button.isChecked()

    def test_a_reply_missing_a_channel_is_not_a_crash(self, qapp):
        """The fixed rail is absent from `channels` by design."""
        made = self._made(qapp)
        made._apply_all_readings({"channels": [self.REPLY["channels"][0]]})
        assert 3 not in made._channel_views

    def test_an_empty_reply_is_survivable(self, qapp):
        made = self._made(qapp)
        made._apply_all_readings({})
        made._apply_all_readings(None)

    def test_typing_in_one_channel_does_not_freeze_the_others(self, qapp):
        """The panel-wide check was too coarse once there are columns.

        A polled reading overwrites the setpoint boxes, so it has to
        stand off while somebody is typing -- but focus in CH1 says
        nothing about CH2, and holding CH2's setpoints back because
        CH1 has the cursor would leave it showing a stale number.
        """
        made = self._made(qapp)
        made._strips[1].voltage_spinbox.setFocus()
        qapp.processEvents()

        made._apply_all_readings(self.REPLY)

        assert made._strips[1].voltage_spinbox.value() != pytest.approx(5.0), (
            "overwrote the value being typed into CH1")
        assert made._strips[2].voltage_spinbox.value() == pytest.approx(3.3), (
            "froze CH2 because CH1 had the cursor")

    def test_a_channel_being_typed_into_still_shows_its_readings(self, qapp):
        """Only the setpoint boxes stand off. The measured value is
        not something the operator is editing."""
        made = self._made(qapp)
        made._strips[1].voltage_spinbox.setFocus()
        qapp.processEvents()

        made._apply_all_readings(self.REPLY)

        assert "4.970 V" in [
            d.text() for d in made._channel_views[1].displays.values()]


class TestAStripCommandsNothingItself:
    """A strip reports what was asked for; the panel owns the server."""

    def test_committing_a_setpoint_names_its_channel(self, qapp):
        strip = ChannelStrip(2)
        _ALIVE.append(strip)
        seen = []
        strip.setpoint_committed.connect(
            lambda *args: seen.append(args))
        strip.voltage_spinbox.setValue(4.0)
        strip.voltage_spinbox.editingFinished.emit()
        assert seen == [(2, "voltage", 4.0)]

    def test_the_output_button_names_its_channel(self, qapp):
        strip = ChannelStrip(3, programmable=False, note="fixed")
        _ALIVE.append(strip)
        seen = []
        strip.output_toggled.connect(lambda *args: seen.append(args))
        strip.output_button.click()
        assert seen == [(3, True)]

    def test_showing_a_setpoint_does_not_command_one(self, qapp):
        """These boxes are wired to send. Putting the instrument's own
        value on them must not send it straight back."""
        strip = ChannelStrip(1)
        _ALIVE.append(strip)
        seen = []
        strip.setpoint_committed.connect(lambda *args: seen.append(args))
        strip.show_setpoints(voltage=7.5, current=1.0)
        assert seen == []

    def test_ranging_does_not_command_anything(self, qapp):
        """setMaximum clamps a value that no longer fits and Qt emits
        the change; the single-channel panel learned that the hard
        way, commanding the instrument it had just switched to."""
        strip = ChannelStrip(1)
        _ALIVE.append(strip)
        strip.set_ranges(32.0, 3.2)
        strip.show_setpoints(voltage=30.0)
        seen = []
        strip.setpoint_committed.connect(lambda *args: seen.append(args))
        strip.set_ranges(5.0, 1.0)
        assert seen == []


class TestLosingFocusIsNotACommand:
    """editingFinished fires whenever a box loses focus, not only when
    something was typed.

    Found by a crash rather than a failure: clearing focus fired the
    signal, which reached an asyncSlot with no running event loop, and
    an asyncSlot invoked outside a loop aborts the interpreter instead
    of raising. Two faults in one, and the quieter of the two is the
    worse: re-sending a setpoint the operator had just changed on the
    front panel.
    """

    def test_tabbing_past_an_untouched_field_sends_nothing(self, qapp):
        strip = ChannelStrip(1)
        _ALIVE.append(strip)
        strip.set_ranges(32.0, 3.2)
        strip.show_setpoints(voltage=5.0, current=1.0)

        seen = []
        strip.setpoint_committed.connect(lambda *args: seen.append(args))
        strip.voltage_spinbox.setFocus()
        strip.voltage_spinbox.clearFocus()
        qapp.processEvents()

        assert seen == [], "commanded a setpoint nobody changed"

    def test_a_value_that_did_change_is_still_sent(self, qapp):
        strip = ChannelStrip(1)
        _ALIVE.append(strip)
        strip.set_ranges(32.0, 3.2)
        strip.show_setpoints(voltage=5.0)

        seen = []
        strip.setpoint_committed.connect(lambda *args: seen.append(args))
        strip.voltage_spinbox.setValue(7.5)
        strip.voltage_spinbox.editingFinished.emit()

        assert seen == [(1, "voltage", 7.5)]

    def test_the_same_value_twice_is_sent_once(self, qapp):
        strip = ChannelStrip(1)
        _ALIVE.append(strip)
        strip.set_ranges(32.0, 3.2)
        seen = []
        strip.setpoint_committed.connect(lambda *args: seen.append(args))

        strip.voltage_spinbox.setValue(3.0)
        strip.voltage_spinbox.editingFinished.emit()
        strip.voltage_spinbox.editingFinished.emit()

        assert len(seen) == 1, seen

    def test_a_strip_signal_outside_the_event_loop_is_dropped(self, qapp):
        """There is no loop running in a test, and there is none
        during teardown either."""
        made = panel(qapp, SIGLENT)
        made._strips[1].voltage_spinbox.setValue(9.0)
        made._strips[1].voltage_spinbox.editingFinished.emit()
        qapp.processEvents()   # must not abort

    def test_an_output_click_outside_the_loop_puts_the_button_back(self, qapp):
        """A button that stayed pressed would claim an output that was
        never switched."""
        made = panel(qapp, SIGLENT)
        made._strips[1].output_button.click()
        qapp.processEvents()
        assert not made._strips[1].output_button.isChecked()


class TestOneSelectorAndOneRate:
    """Shared, not repeated.

    Three display-mode selectors would be three things to keep in
    step, and the refresh rate is a property of the poll, which is per
    instrument rather than per channel.
    """

    def test_there_is_one_display_mode_selector(self, qapp):
        made = panel(qapp, SIGLENT)
        assert made.shared_bar.isVisible()
        assert made.shared_mode_buttons.buttons()

    def test_the_columns_have_no_selector_of_their_own(self, qapp):
        made = panel(qapp, SIGLENT)
        for views in made._channel_views.values():
            assert views.mode_group is None

    @pytest.mark.parametrize("index,expected", [
        (0, "digital"), (1, "analog"), (2, "graph")])
    def test_it_drives_every_column(self, qapp, index, expected):
        made = panel(qapp, SIGLENT)
        made.shared_mode_buttons.button(index).setChecked(True)
        qapp.processEvents()
        for views in made._channel_views.values():
            assert views.current_mode() == expected

    def test_the_readings_are_stacked_in_a_column(self, qapp):
        """Three quantities read well in a row for one channel. Three
        channels of three do not, so each column stacks its own."""
        made = panel(qapp, SIGLENT)
        assert all(v.vertical for v in made._channel_views.values())

    def test_there_is_one_refresh_rate_for_the_supply(self, qapp):
        made = panel(qapp, SIGLENT)
        assert made._rate_group.parent() is made.shared_bar
        assert made._rate_group.isVisible()

    def test_the_rate_control_is_not_duplicated(self, qapp):
        """It is the panel's own, moved rather than rebuilt: a second
        one could disagree with the first about the poll."""
        from PyQt6.QtWidgets import QGroupBox

        made = panel(qapp, SIGLENT)
        rates = [g for g in made.findChildren(QGroupBox)
                 if g.title() == "Refresh Rate"]
        assert len(rates) == 1, rates


class TestComingBackToOneChannel:
    """The Control tab switches instruments in place, so the same panel
    object serves the Siglent and then the B&K beside it."""

    def test_the_shared_bands_stand_down(self, qapp):
        made = panel(qapp, SIGLENT)
        assert made.shared_bar.isVisible()

        made.configure(SINGLE)
        qapp.processEvents()

        assert not made.shared_bar.isVisible()
        assert not made.readout_area.isVisible()
        assert not made.channel_area.isVisible()

    def test_the_original_body_comes_back(self, qapp):
        made = panel(qapp, SIGLENT)
        made.configure(SINGLE)
        qapp.processEvents()
        assert made._controls_group.isVisible()
        assert made.views.isVisible()

    def test_the_columns_are_let_go_of(self, qapp):
        made = panel(qapp, SIGLENT)
        made.configure(SINGLE)
        qapp.processEvents()
        assert made._strips == {}
        assert made._channel_views == {}

    def test_and_back_again(self, qapp):
        made = panel(qapp, SIGLENT)
        made.configure(SINGLE)
        qapp.processEvents()
        made.configure(SIGLENT)
        qapp.processEvents()
        assert sorted(made._strips) == [1, 2, 3]
        assert sorted(made._channel_views) == [1, 2]
        assert made._rate_group.isVisible()


class TestTheSharedReadoutTools:
    """Min/Max, Reset and Auto Range belong to the readout as a whole,
    so there is one of each rather than one per column."""

    def test_they_are_on_the_shared_bar(self, qapp):
        made = panel(qapp, SIGLENT)
        assert made.shared_minmax_button is not None
        assert made.shared_minmax_reset is not None
        assert made.shared_autorange_button is not None

    def test_minmax_drives_every_column(self, qapp):
        made = panel(qapp, SIGLENT)
        made.shared_minmax_button.setChecked(True)
        qapp.processEvents()
        assert all(v._minmax_tracking for v in made._channel_views.values())

    def test_reset_only_matters_while_tracking(self, qapp):
        made = panel(qapp, SIGLENT)
        assert not made.shared_minmax_reset.isEnabled()
        made.shared_minmax_button.setChecked(True)
        qapp.processEvents()
        assert made.shared_minmax_reset.isEnabled()

    def test_auto_range_drives_every_column(self, qapp):
        made = panel(qapp, SIGLENT)
        made.shared_autorange_button.setChecked(True)
        qapp.processEvents()
        assert all(v._autorange for v in made._channel_views.values())

    def test_a_column_has_no_tools_of_its_own(self, qapp):
        made = panel(qapp, SIGLENT)
        for views in made._channel_views.values():
            assert views.minmax_button is None
            assert views.autorange_button is None


class TestSeriesAndParallel:
    """Not display options. In either mode CH1 and CH2 are linked
    internally into one channel controlled by CH1, and the load is
    wired differently for each."""

    def test_there_is_a_button_for_each_mode(self, qapp):
        made = panel(qapp, SIGLENT)
        assert sorted(made.coupling_buttons) == [
            "independent", "parallel", "series"]

    def test_the_indicator_follows_the_supply(self, qapp):
        """Not the last button pressed. The driver switches the outputs
        off on the way and any of it can be refused."""
        made = panel(qapp, SIGLENT)
        made._apply_all_readings({"coupling": "parallel", "channels": []})
        assert "Parallel" in made.coupling_indicator.text()
        assert made.coupling_buttons["parallel"].isChecked()

    def test_a_click_alone_does_not_move_the_indicator(self, qapp):
        """With nothing to send to, the panel must not claim a mode
        the instrument is not in."""
        made = panel(qapp, SIGLENT)
        made.coupling_buttons["series"].click()
        qapp.processEvents()
        assert not made.coupling_buttons["series"].isChecked()
        assert "--" in made.coupling_indicator.text()

    @pytest.mark.parametrize("mode", ["series", "parallel"])
    def test_ch2_is_locked_out_when_the_pair_is_linked(self, qapp, mode):
        """CH1 controls both, so CH2's own controls would be
        commanding something that is not listening."""
        made = panel(qapp, SIGLENT)
        made._apply_all_readings({"coupling": mode, "channels": []})
        assert not made._strips[2].voltage_spinbox.isEnabled()
        assert not made._strips[2].output_button.isEnabled()

    def test_ch1_is_left_alone(self, qapp):
        made = panel(qapp, SIGLENT)
        made._apply_all_readings({"coupling": "series", "channels": []})
        assert made._strips[1].voltage_spinbox.isEnabled()

    def test_independent_gives_ch2_back(self, qapp):
        made = panel(qapp, SIGLENT)
        made._apply_all_readings({"coupling": "parallel", "channels": []})
        made._apply_all_readings({"coupling": "independent", "channels": []})
        assert made._strips[2].voltage_spinbox.isEnabled()


class TestTheTimer:
    """Five timing groups per channel, run one after another. The
    guide: "The timer function is invalid when the series mode or
    parallel mode is turn on."
    """

    def test_each_programmable_channel_has_a_timer(self, qapp):
        made = panel(qapp, SIGLENT)
        assert sorted(made._timer_buttons) == [1, 2]

    def test_the_fixed_rail_has_none(self, qapp):
        assert 3 not in panel(qapp, SIGLENT)._timer_buttons

    @pytest.mark.parametrize("mode", ["series", "parallel"])
    def test_it_is_unavailable_when_the_pair_is_linked(self, qapp, mode):
        made = panel(qapp, SIGLENT)
        made._apply_all_readings({"coupling": mode, "channels": []})
        assert not made._timer_buttons[1].isEnabled()
        assert "independent" in made._timer_buttons[1].toolTip()

    def test_independent_makes_it_available_again(self, qapp):
        made = panel(qapp, SIGLENT)
        made._apply_all_readings({"coupling": "series", "channels": []})
        made._apply_all_readings({"coupling": "independent", "channels": []})
        assert made._timer_buttons[1].isEnabled()

    def test_a_click_that_cannot_be_sent_puts_the_button_back(self, qapp):
        made = panel(qapp, SIGLENT)
        made._timer_buttons[1].click()
        qapp.processEvents()
        assert not made._timer_buttons[1].isChecked()
        assert "off" in made._timer_buttons[1].text().lower()
