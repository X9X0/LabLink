"""After connecting an instrument, the panel has to say it is connected.

Reported from the bench, while reconnecting everything after a server
update: "I still see 'disconnected' after successfully reconnecting."

Two faults compounding, and either alone is enough to cause it.

The connect handler called ``self.refresh()`` and then redrew the details
pane on the next line. ``refresh`` is an ``@asyncSlot``, so calling it
only schedules the fetch -- the pane was redrawn from the equipment list
as it stood *before* the connect, which of course still said the
instrument was disconnected.

And the list rebuild cleared the widget without putting the selection
back. The details pane is only ever filled by the selection handler, so
once the refresh finally landed it dropped the selection and the pane was
never redrawn at all. It went on saying "DISCONNECTED" until the row was
clicked again.

A server update makes this unmissable, because everything needs
reconnecting at once.
"""

import asyncio
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication, QMessageBox

    from client.models.equipment import (ConnectionStatus, Equipment,
                                         EquipmentType)
    from client.ui.equipment_panel import EquipmentPanel

    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(not GUI_AVAILABLE, reason="PyQt6 is required")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _Client:
    """A server whose instrument really does change state on connect."""

    def __init__(self):
        self.connected = False

    def list_equipment(self):
        return [{
            "id": "ps_56fdd3df",
            "type": "power_supply",
            "manufacturer": "B&K Precision",
            "model": "1902B",
            "resource_string": "ASRL/dev/ttyUSB0::INSTR",
            "connected": self.connected,
        }]

    def connect_equipment(self, resource, equipment_type, model):
        self.connected = True
        return {"status": "connected", "equipment_id": "ps_56fdd3df"}


def _disconnected():
    return Equipment(
        equipment_id="ps_56fdd3df",
        name="1902B",
        equipment_type=EquipmentType.POWER_SUPPLY,
        manufacturer="B&K Precision",
        model="1902B",
        resource_name="ASRL/dev/ttyUSB0::INSTR",
        connection_status=ConnectionStatus.DISCONNECTED,
    )


@pytest.fixture
def panel(qapp, monkeypatch):
    made = EquipmentPanel()
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(made, "_start_equipment_stream",
                        lambda *a, **k: asyncio.sleep(0))
    yield made
    made.client = None
    made.selected_equipment = None
    made.deleteLater()
    qapp.processEvents()


def run(coro):
    return asyncio.run(coro)


def drive(panel, name, *args):
    """Run an asyncSlot's coroutine to completion."""
    slot = getattr(type(panel), name)
    return run(getattr(slot, "__wrapped__", slot)(panel, *args))


def status(panel):
    return panel.status_label.text()


class TestTheStatusFollowsTheInstrument:
    def test_after_connecting_it_does_not_still_say_disconnected(self, panel):
        """The bench report, in one assertion."""
        client = _Client()
        panel.client = client
        panel._connections = lambda: {"srv": client}
        drive(panel, "refresh")
        panel.equipment_list_widget.setCurrentRow(0)
        panel._on_equipment_selected()
        assert "DISCONNECTED" in status(panel), "not disconnected to begin with"

        drive(panel, "connect_equipment")

        assert "DISCONNECTED" not in status(panel), (
            f"still reporting {status(panel)!r} about an instrument that "
            f"connected successfully")
        assert "CONNECTED" in status(panel)

    def test_the_row_shows_the_filled_dot(self, panel):
        client = _Client()
        panel.client = client
        panel._connections = lambda: {"srv": client}
        drive(panel, "refresh")
        panel.equipment_list_widget.setCurrentRow(0)
        panel._on_equipment_selected()

        drive(panel, "connect_equipment")

        assert panel.equipment_list_widget.item(0).text().startswith("●"), (
            f"row reads {panel.equipment_list_widget.item(0).text()!r}")

    def test_the_buttons_follow_too(self, panel):
        """Disconnect must become available, Connect must not stay so."""
        client = _Client()
        panel.client = client
        panel._connections = lambda: {"srv": client}
        drive(panel, "refresh")
        panel.equipment_list_widget.setCurrentRow(0)
        panel._on_equipment_selected()

        drive(panel, "connect_equipment")

        assert panel.disconnect_btn.isEnabled() is True
        assert panel.connect_btn.isEnabled() is False


class TestARefreshKeepsTheOperatorsPlace:
    def test_the_selection_survives(self, panel):
        client = _Client()
        panel.client = client
        panel._connections = lambda: {"srv": client}
        drive(panel, "refresh")
        panel.equipment_list_widget.setCurrentRow(0)
        panel._on_equipment_selected()
        assert panel.selected_equipment is not None

        drive(panel, "refresh")

        assert panel.equipment_list_widget.currentRow() == 0, (
            "the rebuild dropped the selection, and with it the details pane")
        assert panel.selected_equipment is not None

    def test_the_selection_points_at_the_fresh_object(self, panel):
        """A refresh builds new Equipment objects; holding the old one is
        how the pane came to report stale state."""
        client = _Client()
        panel.client = client
        panel._connections = lambda: {"srv": client}
        drive(panel, "refresh")
        panel.equipment_list_widget.setCurrentRow(0)
        panel._on_equipment_selected()

        client.connected = True          # changed on the server
        drive(panel, "refresh")

        assert (panel.selected_equipment.connection_status
                == ConnectionStatus.CONNECTED), (
            "still holding the Equipment from before the refresh")
        assert "CONNECTED" in status(panel)

    def test_nothing_selected_stays_nothing_selected(self, panel):
        client = _Client()
        panel.client = client
        panel._connections = lambda: {"srv": client}
        drive(panel, "refresh")
        assert panel.equipment_list_widget.currentRow() in (-1, 0)
        assert panel.selected_equipment is None

    def test_an_instrument_that_vanishes_does_not_crash_the_rebuild(self, panel):
        client = _Client()
        panel.client = client
        panel._connections = lambda: {"srv": client}
        drive(panel, "refresh")
        panel.equipment_list_widget.setCurrentRow(0)
        panel._on_equipment_selected()

        client.list_equipment = lambda: []
        drive(panel, "refresh")          # must not raise

        assert panel.equipment_list_widget.count() == 0
