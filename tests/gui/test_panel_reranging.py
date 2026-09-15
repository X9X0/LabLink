"""Switching instruments must not command the one being switched to.

Both power-supply panels re-range their controls from the newly selected
instrument's capabilities. `setMaximum()` clamps a value that no longer fits
and Qt emits `valueChanged` for that clamp, so on ControlPanel -- where those
signals are wired straight to `_send_*_command` -- selecting a smaller supply
after a larger one sent the carried-over setpoint to the new instrument as a
command. Picking the 5 A 1685B after the 25 A 9205B commanded the 1685B to
5.0 A, its full scale, from a number the operator never typed.

PowerSupplyPanel sends only on Apply, so it never commanded anything by
itself, but it showed the same clamped leftover as though it were the new
supply's setpoint, ready for Apply to send.

These drive the real panels under Qt's offscreen platform, so they need
neither a display nor hardware.
"""

import os
import sys

import pytest

# Offscreen must be chosen before the first QApplication, or Qt binds to
# whatever platform the environment happens to offer.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    import pyqtgraph  # noqa: F401
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QListWidgetItem

    from client.models.equipment import (
        ConnectionStatus,
        Equipment,
        EquipmentType,
    )
    from client.ui.control_panel import ControlPanel
    from client.ui.equipment.power_supply_panel import PowerSupplyPanel

    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not GUI_AVAILABLE, reason="PyQt6 and pyqtgraph are required for panel tests"
)


#: The two supplies from the bench that first showed this. The 9205B's 25 A
#: ceiling is what makes a carried-over setpoint too large for the 1685B.
SUPPLIES = {
    "ps_9205b": {"max_voltage": 60.0, "max_current": 25.0},
    "ps_1685b": {"max_voltage": 60.0, "max_current": 5.0},
}

#: What each supply reports when asked for its own setpoints. Deliberately
#: unlike both the other supply's setpoint and either ceiling, so a panel that
#: shows one of those is caught rather than passing by coincidence.
SETPOINTS = {
    "ps_9205b": {"voltage": 12.0, "current": 8.0},
    "ps_1685b": {"voltage": 3.3, "current": 1.2},
}


class FakeClient:
    """Records every command, and answers get_setpoints from SETPOINTS."""

    def __init__(self):
        self.commands = []

    # -- command plumbing --------------------------------------------------

    def send_command(self, equipment_id, command, parameters=None):
        self.commands.append((equipment_id, command, parameters))
        if command == "get_setpoints":
            return {"success": True, "data": SETPOINTS[equipment_id]}
        return {"success": True, "data": None}

    def get_equipment_status(self, equipment_id):
        caps = dict(SUPPLIES[equipment_id])
        caps["num_channels"] = 1
        caps["supports_protection"] = False
        return {"capabilities": caps}

    # -- locks: nothing is held, so selection takes control cleanly --------

    def get_lock_status(self, equipment_id):
        return {}

    def holds_lock(self, status):
        return False

    def acquire_lock(self, equipment_id, lock_mode="exclusive"):
        return {}

    def release_lock(self, equipment_id):
        return {}

    # -- convenience -------------------------------------------------------

    def writes(self):
        """Just the commands that change the instrument."""
        return [c for c in self.commands if c[1] != "get_setpoints"]


@pytest.fixture(scope="module")
def qapp():
    """One QApplication for the module; Qt allows only a single instance."""
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# ControlPanel
# ---------------------------------------------------------------------------


def _equipment(equipment_id, model):
    return Equipment(
        equipment_id=equipment_id,
        name=model,
        equipment_type=EquipmentType.POWER_SUPPLY,
        manufacturer="B&K Precision",
        model=model,
        resource_name=f"ASRL::{equipment_id}",
        connection_status=ConnectionStatus.CONNECTED,
    )


@pytest.fixture
def control_panel(qapp):
    """A ControlPanel wired to a FakeClient, with both supplies listed.

    The supply controls now live on the power-supply panel the shell hosts;
    its `_send_*_command` are replaced with plain recorders: they are
    asyncSlots that would need a running qasync loop, and what the tests care
    about is only whether re-ranging reached them at all.
    """
    client = FakeClient()
    panel = ControlPanel(client=client)

    supply = panel.panel_for(_equipment("ps_9205b", "9205B"))
    panel.sent = []
    supply._send_voltage_command = lambda v: panel.sent.append(("voltage", v))
    supply._send_current_command = lambda v: panel.sent.append(("current", v))

    # Neither is part of what is under test, and both would otherwise want a
    # timer or an event loop.
    panel._refresh_lock_status = lambda: None
    supply.start = lambda: None

    panel.equipment_list = [
        _equipment("ps_9205b", "9205B"),
        _equipment("ps_1685b", "1685B"),
    ]
    for equipment in panel.equipment_list:
        item = QListWidgetItem(equipment.name)
        # Matches what refresh_equipment_list writes: the composite key,
        # so the same id on two servers stays distinguishable.
        item.setData(Qt.ItemDataRole.UserRole, equipment.key)
        panel.equipment_list_widget.addItem(item)

    panel.client = client
    return panel


def _select(panel, row):
    panel.equipment_list_widget.setCurrentRow(row)
    panel._on_equipment_selected()
    return panel.current_panel


class TestControlPanelSwitching:
    def test_switching_to_a_smaller_supply_commands_nothing(self, control_panel):
        """The regression: re-ranging must never reach _send_*_command.

        Selecting the 1685B used to clamp the 9205B's carried-over setpoint to
        5.0 and send it as set_current -- the 1685B's full scale.
        """
        supply = _select(control_panel, 0)
        supply.current_spinbox.setValue(8.0)   # a real operator edit
        control_panel.sent.clear()

        _select(control_panel, 1)                     # 25 A -> 5 A

        assert control_panel.sent == []

    def test_the_operator_edit_itself_still_commands(self, control_panel):
        """The guard must not have muted the controls for real edits."""
        supply = _select(control_panel, 0)
        control_panel.sent.clear()

        supply.current_spinbox.setValue(7.5)

        assert ("current", 7.5) in control_panel.sent

    def test_the_new_supply_s_own_setpoint_is_shown(self, control_panel):
        """Not the ceiling, and not the previous instrument's number."""
        supply = _select(control_panel, 0)
        supply.current_spinbox.setValue(8.0)

        supply = _select(control_panel, 1)

        assert supply.current_spinbox.value() == pytest.approx(1.2)
        assert supply.voltage_spinbox.value() == pytest.approx(3.3)

    def test_the_ceiling_still_follows_the_supply(self, control_panel):
        """Blocking the signals must not have skipped the re-ranging."""
        supply = _select(control_panel, 0)
        assert supply.current_spinbox.maximum() == pytest.approx(25.0)

        supply = _select(control_panel, 1)
        assert supply.current_spinbox.maximum() == pytest.approx(5.0)

    def test_both_supplies_share_one_panel(self, control_panel):
        """One instance per panel class, so switching keeps the graph history
        and does not leak a widget per selection."""
        first = _select(control_panel, 0)
        second = _select(control_panel, 1)
        assert first is second

    def test_a_supply_that_cannot_report_setpoints_still_commands_nothing(
        self, control_panel
    ):
        """An older server may not answer get_setpoints.

        The panel then has nothing better to show, but it must still not turn
        the clamp into a command.
        """
        def refuse(equipment_id, command, parameters=None):
            if command == "get_setpoints":
                return {"success": False, "error": "unsupported"}
            return {"success": True, "data": None}

        supply = _select(control_panel, 0)
        supply.current_spinbox.setValue(8.0)
        control_panel.client.send_command = refuse
        control_panel.sent.clear()

        _select(control_panel, 1)

        assert control_panel.sent == []


# ---------------------------------------------------------------------------
# PowerSupplyPanel
# ---------------------------------------------------------------------------


@pytest.fixture
def psu_panel(qapp):
    client = FakeClient()
    panel = PowerSupplyPanel()
    panel.set_client(client)
    # set_equipment ends by refreshing protection on the event loop, which is
    # not what these tests are about.
    panel._spawn = lambda coro: coro.close()
    return panel


def _connect(panel, equipment_id, model):
    caps = dict(SUPPLIES[equipment_id])
    caps["num_channels"] = 1
    caps["supports_protection"] = False
    panel.set_equipment(
        equipment_id,
        {"model": model, "manufacturer": "B&K Precision", "capabilities": caps},
    )


class TestPowerSupplyPanelSwitching:
    def test_switching_shows_the_new_supply_s_setpoint(self, psu_panel):
        """Not the previous supply's value clamped to this one's ceiling."""
        _connect(psu_panel, "ps_9205b", "9205B")
        psu_panel.current_spin.setValue(8.0)

        _connect(psu_panel, "ps_1685b", "1685B")

        assert psu_panel.current_spin.value() != pytest.approx(5.0)   # the clamp
        assert psu_panel.current_spin.value() == pytest.approx(1.2)
        assert psu_panel.voltage_spin.value() == pytest.approx(3.3)

    def test_switching_sends_no_command(self, psu_panel):
        """This panel sends on Apply; re-ranging must add nothing of its own."""
        _connect(psu_panel, "ps_9205b", "9205B")
        psu_panel.current_spin.setValue(8.0)
        psu_panel.client.commands.clear()

        _connect(psu_panel, "ps_1685b", "1685B")

        assert psu_panel.client.writes() == []

    def test_the_slider_still_tracks_the_spinbox(self, psu_panel):
        """The mirroring must survive being blocked during the re-range."""
        _connect(psu_panel, "ps_1685b", "1685B")

        psu_panel.current_spin.setValue(2.5)

        assert psu_panel.current_slider.value() == 2500

    def test_the_ceiling_still_follows_the_supply(self, psu_panel):
        _connect(psu_panel, "ps_9205b", "9205B")
        assert psu_panel.current_spin.maximum() == pytest.approx(25.0)

        _connect(psu_panel, "ps_1685b", "1685B")
        assert psu_panel.current_spin.maximum() == pytest.approx(5.0)
