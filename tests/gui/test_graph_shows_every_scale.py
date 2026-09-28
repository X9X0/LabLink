"""A trace whose scale is not shown is a shape, not a measurement.

The graph gave furniture to only the first two channels -- the
reasoning being that three sets of numbers down the sides of a narrow
chart cannot be read -- which left the watts trace on the chart with
nothing to read it against. Supplies and loads both show volts, amps
and watts, so both were affected.
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
    from client.ui.instruments.electronic_load import ElectronicLoadPanel
    from client.ui.instruments.measurement_views import (VOLTS_AMPS_WATTS,
                                                         MeasurementViews)
    from client.ui.instruments.power_supply import PowerSupplyPanel

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


class TestEveryChannelHasAVisibleScale:
    def test_the_views_show_all_three(self, qapp):
        views = MeasurementViews(VOLTS_AMPS_WATTS)
        _ALIVE.append(views)
        assert sorted(views.axes) == ["current", "power", "voltage"]
        for key, axis in views.axes.items():
            assert axis.isVisible(), "%s has a trace and no scale" % key

    def test_the_watts_axis_is_labelled(self, qapp):
        """An axis with no title is a column of numbers."""
        views = MeasurementViews(VOLTS_AMPS_WATTS)
        _ALIVE.append(views)
        assert "W" in views.axes["power"].titleText()

    def test_a_supply_shows_all_three(self, qapp):
        made = PowerSupplyPanel()
        made.configure({"channels": 1, "max_voltage": 60.0,
                        "max_current": 25.0})
        made.resize(1600, 900)
        made.show()
        _ALIVE.append(made)
        qapp.processEvents()
        assert all(a.isVisible() for a in made.views.axes.values())

    def test_a_load_shows_all_three(self, qapp):
        made = ElectronicLoadPanel()
        made.configure({"max_current": 40.0, "max_voltage": 150.0})
        made.resize(1600, 900)
        made.show()
        _ALIVE.append(made)
        qapp.processEvents()
        assert all(a.isVisible() for a in made.views.axes.values()), {
            k: a.isVisible() for k, a in made.views.axes.items()}

    def test_a_multi_channel_column_shows_all_three(self, qapp):
        made = PowerSupplyPanel()
        made.configure({"channels": 3, "programmable_channels": [1, 2],
                        "max_voltage": 32.0, "max_current": 3.2,
                        "has_fixed_rail": True})
        made.resize(1900, 950)
        made.show()
        _ALIVE.append(made)
        qapp.processEvents()
        for number, views in made._channel_views.items():
            for key, axis in views.axes.items():
                assert axis.isVisible(), "CH%d %s" % (number, key)

    def test_a_two_channel_view_is_unaffected(self, qapp):
        """Not every readout has three. Nothing here should change for
        one that has two."""
        views = MeasurementViews(VOLTS_AMPS_WATTS[:2])
        _ALIVE.append(views)
        assert all(a.isVisible() for a in views.axes.values())
