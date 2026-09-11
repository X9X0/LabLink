"""Panel-level tests for the OVP/OCP controls (#117).

These drive the real PowerSupplyPanel under Qt's offscreen platform, so they
run without a display and without hardware. What they check is the part that
cannot be checked server-side: what an operator is shown, and whether a
control that cannot work is left switchable.
"""

import os
import sys

import pytest

# Offscreen must be chosen before the first QApplication, or Qt binds to
# whatever platform the environment happens to offer and the run depends on
# whether a display was attached.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    # pyqtgraph belongs in the guard as much as PyQt6 does. The panel embeds a
    # PowerChartWidget, which raises ImportError from its constructor rather
    # than at import time, so importing the panel successfully does not mean a
    # panel can be built. Checking it here turns that into a clean skip
    # instead of an error at fixture setup.
    import pyqtgraph  # noqa: F401
    from PyQt6.QtWidgets import QApplication

    from client.ui.equipment.power_supply_panel import PowerSupplyPanel

    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not GUI_AVAILABLE, reason="PyQt6 and pyqtgraph are required for panel tests"
)


@pytest.fixture(scope="module")
def qapp():
    """One QApplication for the module; Qt allows only a single instance."""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def panel(qapp):
    return PowerSupplyPanel()


def connect(panel, *, model="9140", protection=True, max_v=30.0, max_i=3.0,
            channels=1):
    panel.set_equipment(
        "ps_test",
        {
            "model": model,
            "manufacturer": "B&K Precision",
            "capabilities": {
                "num_channels": channels,
                "max_voltage": max_v,
                "max_current": max_i,
                "supports_protection": protection,
            },
        },
    )
    return panel


class TestProtectionAvailability:
    """Controls that cannot act must not look like controls that can."""

    def test_disabled_until_something_is_connected(self, panel):
        assert not panel.ovp_spin.isEnabled()
        assert not panel.clear_protection_btn.isEnabled()

    def test_enabled_for_a_supply_that_supports_it(self, panel):
        connect(panel, model="9140", protection=True)
        assert panel.ovp_spin.isEnabled()
        assert panel.ocp_spin.isEnabled()
        assert panel.clear_protection_btn.isEnabled()
        assert panel.protection_note.isHidden()

    def test_disabled_with_an_explanation_for_a_legacy_supply(self, panel):
        """A 1685B has no OVP/OCP commands at all.

        Leaving the rollers live would show an operator a guard they could
        set, arm, and rely on, which would never have been sent anywhere.
        """
        connect(panel, model="1685B", protection=False)

        assert not panel.ovp_spin.isEnabled()
        assert not panel.ocp_enable.isEnabled()
        assert not panel.clear_protection_btn.isEnabled()
        assert not panel.protection_note.isHidden()
        assert "1685B" in panel.protection_note.text()
        assert "front panel" in panel.protection_note.text()

    def test_missing_capability_is_treated_as_unsupported(self, panel):
        """An older server will not send the flag at all.

        The safe reading of silence is "no protection", not "protection".
        """
        panel.set_equipment(
            "ps_old",
            {"model": "9140", "manufacturer": "B&K",
             "capabilities": {"num_channels": 1}},
        )
        assert not panel.ovp_spin.isEnabled()


class TestProtectionRanges:
    """A trip ceiling is set above the working point, not below it."""

    def test_rollers_span_the_supplys_full_range(self, panel):
        connect(panel, max_v=60.0, max_i=25.0)
        assert panel.ovp_spin.maximum() == 60.0
        assert panel.ocp_spin.maximum() == 25.0
        assert panel.ovp_slider.maximum() == 60000
        assert panel.ocp_slider.maximum() == 25000

    def test_roller_and_slider_track_each_other(self, panel):
        connect(panel)
        panel.ovp_spin.setValue(12.5)
        assert panel.ovp_slider.value() == 12500

        panel.ocp_slider.setValue(1500)
        assert panel.ocp_spin.value() == pytest.approx(1.5)


class TestIndicators:
    """Three states, because "unknown" is not "fine"."""

    def test_tripped_is_unmistakable(self, panel):
        connect(panel)
        panel._show_protection({"ovp_tripped": True, "ovp_enabled": True})

        assert panel.ovp_indicator.text() == "TRIPPED"
        assert "TRIPPED" in panel.protection_status_label.text()
        assert "latched off" in panel.protection_status_label.text()

    def test_armed_and_off_are_distinguished(self, panel):
        connect(panel)
        panel._show_protection({"ovp_tripped": False, "ovp_enabled": True,
                                "ocp_tripped": False, "ocp_enabled": False})
        assert panel.ovp_indicator.text() == "armed"
        assert panel.ocp_indicator.text() == "off"

    def test_an_unanswered_trip_query_is_not_reported_as_ok(self, panel):
        """Some models do not implement :PROT:TRIPped?.

        Showing "armed" there would assert the guard is live on evidence
        nobody collected.
        """
        connect(panel)
        panel._show_protection({"ovp_tripped": None, "ovp_enabled": True})
        assert panel.ovp_indicator.text() == "—"

    def test_a_partial_readback_leaves_other_fields_alone(self, panel):
        """A level that came back as None must not render as 0 V.

        An armed guard at zero is the most misleading thing this panel could
        show, so a missing level leaves the previous value in place.
        """
        connect(panel)
        panel.ovp_spin.setValue(12.5)

        panel._show_protection({"ovp_level": None, "ovp_enabled": True})

        assert panel.ovp_spin.value() == pytest.approx(12.5)

    def test_readback_populates_the_controls(self, panel):
        connect(panel)
        panel._show_protection({
            "ovp_level": 15.0, "ovp_enabled": True, "ovp_tripped": False,
            "ocp_level": 2.5, "ocp_enabled": False, "ocp_tripped": False,
            "ocp_delay": 0.25,
        })

        assert panel.ovp_spin.value() == pytest.approx(15.0)
        assert panel.ovp_enable.isChecked()
        assert panel.ocp_spin.value() == pytest.approx(2.5)
        assert not panel.ocp_enable.isChecked()
        assert panel.ocp_delay_spin.value() == pytest.approx(0.25)
        assert panel.protection_status_label.text() == "Protection: no trip"


class TestEventLoopSafety:
    """set_equipment is called from ordinary synchronous code."""

    def test_connecting_without_a_running_loop_does_not_raise(self, panel):
        """The background readback must not take out the connection itself.

        Every test in this file relies on this: they call set_equipment with
        no loop running, and an unguarded create_task raises RuntimeError.
        """
        connect(panel, protection=True)
        assert panel.ovp_spin.isEnabled()

    def test_spawn_reports_whether_it_scheduled(self, panel):
        async def noop():
            return None

        assert panel._spawn(noop()) is False
