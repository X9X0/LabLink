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

    def disconnect_equipment(self, equipment_id, on_disconnect=None):
        # Signature matched to the real client: the handler passes what to
        # do with the output as well, and a fake that took only the id made
        # the test fail for the wrong reason.
        self.connected = False
        return {"status": "disconnected", "equipment_id": equipment_id}

    def get_equipment_readings(self, equipment_id):
        return {}


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
    # Disconnecting asks what to do with the output first. That dialog has
    # nobody to answer it here and would wait for ever.
    async def _leave_it(equipment_id):
        return "leave"
    monkeypatch.setattr(made, "_choose_disconnect_state", _leave_it)
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


class TestTheRowIsHonestWithoutWaitingForAFanOut:
    """Second report, after the first fix: "they are successfully
    connecting but the connected dot and text still shows disconnected."

    The first attempt awaited a refresh -- a fan-out over every instrument
    on every connected server -- before redrawing. That is the
    authoritative answer but not a fast one, and on the bench it hung long
    enough for the in-flight guard to give up on it at 45 seconds. While
    it hung, the pane went on saying DISCONNECTED about an instrument that
    had just connected.

    The reply to the connect already says the instrument is connected.
    That is enough to redraw one row honestly.
    """

    def test_the_status_does_not_wait_for_the_list(self, panel):
        """A refresh that never answers must not hold the status hostage."""
        client = _Client()
        panel.client = client
        panel._connections = lambda: {"srv": client}
        drive(panel, "refresh")
        panel.equipment_list_widget.setCurrentRow(0)
        panel._on_equipment_selected()

        hung = asyncio.Event()

        def never_answers():
            raise AssertionError("the fan-out should not be awaited")

        # Any refresh after the connect must not be what redraws the row.
        panel.refresh = lambda: None
        drive(panel, "connect_equipment")

        assert "CONNECTED" in status(panel), (
            f"pane reads {status(panel)!r} -- it is waiting on the list "
            f"rather than believing the reply it already has")
        assert panel.equipment_list_widget.item(0).text().startswith("●")

    def test_a_server_that_never_answers_does_not_stall_the_refresh(self, panel):
        """Bounded, so the in-flight slot cannot be held indefinitely."""
        client = _Client()
        panel.client = client
        panel._connections = lambda: {"srv": client}
        panel.LIST_TIMEOUT_SEC = 0.05

        def hangs():
            import time as _t
            _t.sleep(5)
            return []

        client.list_equipment = hangs

        # Timed inside the loop. Timing asyncio.run() would also count the
        # executor waiting for the stuck worker thread on shutdown, which
        # the application never does -- what matters is that the coroutine
        # returns, because that is what releases the in-flight slot.
        import time as _t

        async def timed():
            slot = type(panel).refresh
            began = _t.monotonic()
            await getattr(slot, "__wrapped__", slot)(panel)
            return _t.monotonic() - began

        waited = asyncio.run(timed())

        assert waited < 2.0, (
            f"the refresh took {waited:.1f}s for a server that never "
            f"answered; the in-flight slot is held for all of it")

    def test_the_slow_server_is_named(self, panel, caplog):
        import logging as _logging

        client = _Client()
        panel.client = client
        panel._connections = lambda: {"Bench 2": client}
        panel.LIST_TIMEOUT_SEC = 0.05
        client.list_equipment = lambda: __import__("time").sleep(5)

        with caplog.at_level(_logging.WARNING,
                             logger="client.ui.equipment_panel"):
            drive(panel, "refresh")

        assert any("Bench 2" in r.message for r in caplog.records), (
            "nothing says which server ran out of time")


class TestDisconnectingIsAsImmediateAsConnecting:
    """Reported after the connect fix: "dot and text now update
    immediately to show connected, but not disconnected."

    Disconnecting dropped the selection, blanked every label, and left
    the row's dot filled until the next refresh landed -- and that
    refresh is the thing that stalls. Connecting and disconnecting should
    behave the same way: believe the reply, redraw, then refresh.
    """

    def _connected_panel(self, panel):
        client = _Client()
        panel.client = client
        panel._connections = lambda: {"srv": client}
        drive(panel, "refresh")
        panel.equipment_list_widget.setCurrentRow(0)
        panel._on_equipment_selected()
        drive(panel, "connect_equipment")
        assert "CONNECTED" in status(panel)
        return client

    def test_the_dot_empties_at_once(self, panel):
        self._connected_panel(panel)
        panel.refresh = lambda: None          # the fan-out must not be needed

        drive(panel, "disconnect_equipment")

        assert panel.equipment_list_widget.item(0).text().startswith("○"), (
            f"row still reads {panel.equipment_list_widget.item(0).text()!r}")

    def test_the_text_says_disconnected_at_once(self, panel):
        self._connected_panel(panel)
        panel.refresh = lambda: None

        drive(panel, "disconnect_equipment")

        assert "DISCONNECTED" in status(panel), f"pane reads {status(panel)!r}"

    def test_the_buttons_re_range(self, panel):
        """So the operator can connect it again without clicking away."""
        self._connected_panel(panel)
        panel.refresh = lambda: None

        drive(panel, "disconnect_equipment")

        assert panel.connect_btn.isEnabled() is True
        assert panel.disconnect_btn.isEnabled() is False

    def test_the_row_stays_selected(self, panel):
        self._connected_panel(panel)
        panel.refresh = lambda: None

        drive(panel, "disconnect_equipment")

        assert panel.selected_equipment is not None
        assert panel.equipment_list_widget.currentRow() == 0
