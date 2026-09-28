"""Min/max belongs to the instrument, not to the readout widget.

One panel serves every instrument of its type, and configure() resets
the readout on each switch -- deliberately, because a held scale from
a 25 A supply is wrong for a 5 A one. That threw the extremes away
with it, so looking at the load and coming back lost however long you
had been watching.

They are kept per equipment id now, restored when that instrument
comes back, and dropped only by Reset.
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
    from client.ui.instruments.base import InstrumentPanel
    from client.ui.instruments.electronic_load import ElectronicLoadPanel
    from client.ui.instruments.power_supply import PowerSupplyPanel

SINGLE = {"channels": 1, "max_voltage": 60.0, "max_current": 25.0}
_ALIVE = []


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _clean(qapp):
    InstrumentPanel._extremes_by_equipment.clear()
    yield
    InstrumentPanel._extremes_by_equipment.clear()
    while _ALIVE:
        _ALIVE.pop().hide()
    qapp.processEvents()


class _Equipment:
    def __init__(self, equipment_id):
        self.equipment_id = equipment_id
        self.equipment_type = "power_supply"


def supply(qapp):
    made = PowerSupplyPanel()
    made.configure(SINGLE)
    made.resize(1200, 800)
    made.show()
    _ALIVE.append(made)
    qapp.processEvents()
    return made


def watch(panel, voltage, current):
    panel.views.set_minmax_tracking(True)
    panel.views.set_readings(
        {"voltage": voltage, "current": current, "power": voltage * current})


class TestItSurvivesASwitch:
    def test_what_was_seen_comes_back(self, qapp):
        made = supply(qapp)
        made.equipment = _Equipment("ps_A")
        watch(made, 5.0, 1.0)
        watch(made, 9.0, 0.2)
        seen = made.views.extremes()

        made.remember_extremes()
        made.equipment = _Equipment("ps_B")
        made.views.reset_extremes()          # what configure() does
        watch(made, 1.0, 3.0)

        made.remember_extremes()
        made.equipment = _Equipment("ps_A")
        made.views.reset_extremes()
        made.restore_extremes()

        assert made.views.extremes() == seen

    def test_the_other_instrument_keeps_its_own(self, qapp):
        made = supply(qapp)
        made.equipment = _Equipment("ps_A")
        watch(made, 9.0, 0.2)
        made.remember_extremes()

        made.equipment = _Equipment("ps_B")
        made.views.reset_extremes()
        watch(made, 1.0, 3.0)
        made.remember_extremes()

        store = InstrumentPanel._extremes_by_equipment
        assert store["ps_A/"]["voltage"] == [9.0, 9.0]
        assert store["ps_B/"]["voltage"] == [1.0, 1.0]

    def test_an_instrument_never_watched_restores_nothing(self, qapp):
        made = supply(qapp)
        made.equipment = _Equipment("ps_new")
        made.restore_extremes()
        assert made.views.extremes()["voltage"] == [None, None]

    def test_with_no_instrument_bound_nothing_is_kept(self, qapp):
        """An empty id is not a key; every unbound panel would share
        it."""
        made = supply(qapp)
        made.equipment = None
        watch(made, 4.0, 1.0)
        made.remember_extremes()
        assert InstrumentPanel._extremes_by_equipment == {}


class TestOnlyResetClearsIt:
    def test_reset_drops_the_kept_copy(self, qapp):
        made = supply(qapp)
        made.equipment = _Equipment("ps_A")
        watch(made, 9.0, 0.2)
        made.remember_extremes()
        made._hear_about_resets()

        made.views.reset_extremes()

        assert "ps_A/" not in InstrumentPanel._extremes_by_equipment

    def test_after_reset_the_old_figures_do_not_come_back(self, qapp):
        """The whole point of clearing."""
        made = supply(qapp)
        made.equipment = _Equipment("ps_A")
        watch(made, 9.0, 0.2)
        made.remember_extremes()
        made._hear_about_resets()
        made.views.reset_extremes()

        made.restore_extremes()

        assert made.views.extremes()["voltage"] == [None, None]

    def test_listening_is_wired_once_however_often_it_binds(self, qapp):
        made = supply(qapp)
        made.equipment = _Equipment("ps_A")
        for _ in range(5):
            made._hear_about_resets()
        watch(made, 9.0, 0.2)
        made.remember_extremes()
        made.views.reset_extremes()
        assert "ps_A/" not in InstrumentPanel._extremes_by_equipment


class TestItAppliesToEveryPanel:
    def test_the_load_keeps_its_own_too(self, qapp):
        made = ElectronicLoadPanel()
        made.configure({"max_current": 40.0, "max_voltage": 150.0})
        _ALIVE.append(made)
        made.equipment = _Equipment("load_A")
        made.views.set_minmax_tracking(True)
        made.views.set_readings(
            {"voltage": 12.0, "current": 2.0, "power": 24.0})

        made.remember_extremes()
        made.views.reset_extremes()
        made.restore_extremes()

        assert made.views.extremes()["voltage"] == [12.0, 12.0]

    def test_each_column_of_a_multi_channel_supply_keeps_its_own(self, qapp):
        made = PowerSupplyPanel()
        made.configure({"channels": 3, "programmable_channels": [1, 2],
                        "max_voltage": 32.0, "max_current": 3.2,
                        "has_fixed_rail": True})
        made.resize(1600, 900)
        made.show()
        _ALIVE.append(made)
        qapp.processEvents()
        made.equipment = _Equipment("ps_siglent")

        for number, views in made._channel_views.items():
            views.set_minmax_tracking(True)
            views.set_readings({"voltage": float(number), "current": 0.1,
                                "power": 0.1})
        made.remember_extremes()
        for views in made._channel_views.values():
            views.reset_extremes()
        made.restore_extremes()

        for number, views in made._channel_views.items():
            assert views.extremes()["voltage"] == [float(number),
                                                   float(number)], number

    def test_a_panel_with_no_readout_is_not_a_problem(self, qapp):
        """Not every panel has one, and the memory simply does not
        apply to those."""
        made = supply(qapp)
        made.equipment = _Equipment("ps_A")
        made.views = None
        made.remember_extremes()
        made.restore_extremes()
        made.forget_extremes()
