"""The three displays, once, for whichever instrument wants them.

Digital, analog and graph were built into the power supply panel. The
load needed the same three, and the supply wanted a watts channel it
did not have, so the views moved out and the channel set became data.

These tests are about the part that is easy to get wrong when something
becomes reusable: that it is genuinely parameterised rather than a
two-channel widget with a third bolted on, and that the behaviours the
supply had -- extremes tracked across all channels, a range that only
grows, markers cleared when tracking stops -- survived the move.
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

    from client.ui.instruments.measurement_views import (VOLTS_AMPS_WATTS,
                                                         Channel,
                                                         MeasurementViews)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def views(qapp):
    made = MeasurementViews(VOLTS_AMPS_WATTS)
    yield made
    made.deleteLater()
    qapp.processEvents()


class TestItIsActuallyParameterised:
    def test_a_widget_per_channel_in_each_view(self, views):
        for channel in VOLTS_AMPS_WATTS:
            assert channel.key in views.displays
            assert channel.key in views.gauges
            assert channel.key in views.series

    def test_two_channels_work_too(self, qapp):
        """The supply's original pair must not have become a special case."""
        pair = MeasurementViews(VOLTS_AMPS_WATTS[:2])
        try:
            assert len(pair.gauges) == 2
            pair.set_readings({"voltage": 12.0, "current": 1.0})
            assert "12.000" in pair.displays["voltage"].text()
        finally:
            pair.deleteLater()
            qapp.processEvents()

    def test_one_channel_works(self, qapp):
        single = MeasurementViews([Channel("temp", "Temperature", "C", 1, 150)])
        try:
            single.set_readings({"temp": 42.0})
            assert "42.0 C" in single.displays["temp"].text()
        finally:
            single.deleteLater()
            qapp.processEvents()

    def test_no_channels_is_refused(self, qapp):
        with pytest.raises(ValueError):
            MeasurementViews([])


class TestReadings:
    def test_each_display_shows_its_own_value_and_unit(self, views):
        views.set_readings({"voltage": 12.0, "current": 1.5, "power": 18.0})
        assert views.displays["voltage"].text() == "12.000 V"
        assert views.displays["current"].text() == "1.500 A"
        assert views.displays["power"].text() == "18.00 W"

    def test_the_gauges_follow(self, views):
        views.set_readings({"voltage": 12.0, "current": 1.5, "power": 18.0})
        assert views.gauges["voltage"].current_value == pytest.approx(12.0)
        assert views.gauges["power"].current_value == pytest.approx(18.0)

    def test_a_missing_channel_blanks_rather_than_showing_zero(self, views):
        """Nothing reported is not the same as a reading of nought."""
        views.set_readings({"voltage": 12.0})
        assert views.displays["power"].text() == "-- W"

    def test_history_feeds_the_graph(self, views):
        for volts in (1.0, 2.0, 3.0):
            views.set_readings({"voltage": volts, "current": 0.1, "power": 0.3})
        assert views.series["voltage"].count() == 3


class TestMinMaxAcrossEveryChannel:
    def test_extremes_are_tracked_for_all_three(self, views):
        views.minmax_button.setChecked(True)
        views.set_readings({"voltage": 5.0, "current": 1.0, "power": 5.0})
        views.set_readings({"voltage": 2.0, "current": 3.0, "power": 6.0})

        assert views.gauges["voltage"].min_marker == pytest.approx(2.0)
        assert views.gauges["voltage"].max_marker == pytest.approx(5.0)
        assert views.gauges["current"].max_marker == pytest.approx(3.0)
        assert views.gauges["power"].max_marker == pytest.approx(6.0)

    def test_nothing_is_tracked_while_it_is_off(self, views):
        views.set_readings({"voltage": 5.0, "current": 1.0, "power": 5.0})
        assert views.gauges["voltage"].max_marker is None

    def test_switching_off_clears_the_faces(self, views):
        views.minmax_button.setChecked(True)
        views.set_readings({"voltage": 5.0, "current": 1.0, "power": 5.0})
        assert views.gauges["voltage"].max_marker is not None

        views.minmax_button.setChecked(False)
        assert views.gauges["voltage"].max_marker is None

    def test_reset_forgets_and_starts_again(self, views):
        views.minmax_button.setChecked(True)
        views.set_readings({"voltage": 9.0, "current": 1.0, "power": 9.0})
        views.reset_extremes()
        assert views.gauges["voltage"].max_marker is None

        views.set_readings({"voltage": 3.0, "current": 1.0, "power": 3.0})
        assert views.gauges["voltage"].max_marker == pytest.approx(3.0)

    def test_the_label_names_every_channel(self, views):
        views.minmax_button.setChecked(True)
        views.set_readings({"voltage": 5.0, "current": 1.0, "power": 5.0})
        text = views.minmax_label.text()
        for unit in ("V", "A", "W"):
            assert unit in text


class TestRanging:
    def test_autorange_scales_the_gauge_down_to_the_reading(self, views):
        views.set_maximum("current", 16.0)
        views.autorange_button.setChecked(True)
        views.set_readings({"voltage": 1.0, "current": 0.3, "power": 0.3})

        assert views.gauges["current"].max_value < 16.0, (
            "a 0.3 A reading is using a sixteenth of a 16 A dial")

    def test_the_range_only_grows(self, views):
        """A scale that shrank made the needle and the trace jump about."""
        views.autorange_button.setChecked(True)
        views.set_readings({"voltage": 1.0, "current": 8.0, "power": 8.0})
        wide = views.gauges["current"].max_value

        views.set_readings({"voltage": 1.0, "current": 0.2, "power": 0.2})

        assert views.gauges["current"].max_value == pytest.approx(wide)

    def test_switching_autorange_off_restores_the_instrument_scale(self, views):
        views.set_maximum("current", 16.0)
        views.autorange_button.setChecked(True)
        views.set_readings({"voltage": 1.0, "current": 0.3, "power": 0.3})
        views.autorange_button.setChecked(False)

        assert views.gauges["current"].max_value == pytest.approx(16.0)

    def test_set_maximum_takes_effect_immediately(self, views):
        views.set_maximum("voltage", 30.0)
        assert views.gauges["voltage"].max_value == pytest.approx(30.0)

    def test_set_decimals_changes_the_readout(self, views):
        views.set_decimals("current", 1)
        views.set_readings({"voltage": 1.0, "current": 2.25, "power": 2.25})
        assert views.displays["current"].text() == "2.2 A" or \
               views.displays["current"].text() == "2.3 A"


class TestModeSwitching:
    def test_digital_to_begin_with(self, views):
        assert views.current_mode() == "digital"

    def test_each_radio_selects_its_view(self, views):
        views.analog_radio.setChecked(True)
        assert views.current_mode() == "analog"
        views.graph_radio.setChecked(True)
        assert views.current_mode() == "graph"
        views.digital_radio.setChecked(True)
        assert views.current_mode() == "digital"


class TestTheSupplyUsesThemToo:
    """The supply had its own copy of all this; now it shares the load's."""

    @pytest.fixture
    def supply(self, qapp):
        from client.ui.instruments import PowerSupplyPanel

        made = PowerSupplyPanel()
        yield made
        made.deleteLater()
        qapp.processEvents()

    def test_it_has_the_watts_channel(self, supply):
        """Asked for from the bench: the operator was doing V x I in
        their head while watching two of the three numbers."""
        assert "power" in supply.views.displays
        assert "power" in supply.views.gauges

    def test_power_is_the_product_of_the_other_two(self, supply):
        """None of these supplies report power, so it is derived -- and
        derived from the readings as they arrived, so it agrees with the
        numbers printed beside it."""
        supply.views.set_readings({"voltage": 12.0, "current": 1.5,
                                   "power": 12.0 * 1.5})
        assert supply.power_display.text() == "18.00 W"

    def test_the_old_names_still_reach_the_readouts(self, supply):
        """The panel is what the rest of the client holds; none of it
        should have to know a gauge moved."""
        supply.views.set_readings({"voltage": 5.0, "current": 0.5,
                                   "power": 2.5})
        assert "5.00" in supply.voltage_display.text()
        assert supply.voltage_gauge.current_value == pytest.approx(5.0)
        assert supply.minmax_button.isCheckable()
        assert supply.autorange_button.isCheckable()

    def test_configure_ranges_all_three_channels(self, supply):
        supply.configure({"max_voltage": 30.0, "max_current": 3.0,
                          "voltage_decimals": 2, "current_decimals": 3})

        assert supply.voltage_gauge.max_value == pytest.approx(30.0)
        assert supply.current_gauge.max_value == pytest.approx(3.0)
        assert supply.power_gauge.max_value == pytest.approx(90.0), (
            "the watts dial should span what this supply can actually "
            "deliver, not a default")

    def test_decimals_reach_the_readout(self, supply):
        """A supply that sends hundredths must not be shown thousandths."""
        supply.configure({"max_voltage": 30.0, "max_current": 3.0,
                          "voltage_decimals": 2, "current_decimals": 2})
        supply.views.set_readings({"voltage": 5.0, "current": 0.5,
                                   "power": 2.5})
        assert supply.current_display.text() == "0.50 A"
