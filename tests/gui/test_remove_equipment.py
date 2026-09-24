"""The Remove button actually removes, against the real Equipment model.

It shipped broken. The handler read ``eq.resource_string`` to name the
instrument in its confirmation, and the client's Equipment dataclass calls
that field ``resource_name`` -- so pressing Remove raised AttributeError
inside a qasync async slot, which logs and swallows it. Nothing happened, no
dialog, no error: the button looked dead.

The server side was tested and worked; what was missing was any test that
drove the *handler*. The fake used elsewhere carried a ``resource_string``
attribute the real model does not have, so a fake-based test would have
passed just as happily. These build a real ``Equipment``, which is the only
reason they catch it.
"""

import asyncio
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication, QMessageBox


    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(not GUI_AVAILABLE, reason="PyQt6 is required")

if GUI_AVAILABLE:
    from client.models.equipment import (ConnectionStatus, Equipment,
                                         EquipmentType)
    from client.ui.equipment_panel import EquipmentPanel


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def loop():
    """A loop to run what the handler schedules, putting the old one back.

    Leaving the event loop set to None broke tests that ran later and called
    asyncio.get_event_loop(): this file passed, and
    test_selection_is_non_blocking failed in a full run while passing alone.
    """
    try:
        previous = asyncio.get_event_loop_policy().get_event_loop()
    except Exception:
        previous = None
    made = asyncio.new_event_loop()
    asyncio.set_event_loop(made)
    yield made
    made.close()
    asyncio.set_event_loop(previous)


def pump(loop, times=8):
    """Let Qt deliver its events and asyncio run what they scheduled.

    Both, alternately. The confirmation is shown from a QTimer now and
    awaited, so the handler only advances once Qt has fired that timer:
    stepping asyncio on its own waits for ever.

    That indirection is not incidental. A modal opened inline runs a
    nested Qt loop while its own coroutine is still the current asyncio
    task, and anything the nested loop then tries to step dies with
    "Cannot enter into task" -- which is what stranded the equipment
    refresh for 45s at a time on the bench.
    """
    for _ in range(times):
        QApplication.processEvents()
        loop.run_until_complete(asyncio.sleep(0))


class _Client:
    def __init__(self, fail=None):
        self.removed = []
        self._fail = fail

    def remove_equipment(self, equipment_id):
        if self._fail:
            raise self._fail
        self.removed.append(equipment_id)
        return {"equipment_id": equipment_id, "status": "removed"}


def _equipment(equipment_id="scope_a62f42e9"):
    """A real Equipment, not a stand-in: the bug was a field name."""
    return Equipment(
        equipment_id=equipment_id,
        name="DS1054Z",
        equipment_type=EquipmentType.OSCILLOSCOPE,
        manufacturer="RIGOL TECHNOLOGIES",
        model="DS1054Z",
        resource_name="USB0::6833::1230::DS1ZA171409212::0::INSTR",
        connection_status=ConnectionStatus.DISCONNECTED,
    )


@pytest.fixture
def panel(qapp, loop, monkeypatch):
    made = EquipmentPanel()
    # Say yes to the confirmation without showing it.
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(made, "refresh", lambda *a, **k: None)
    yield made
    # deleteLater alone leaves the panel, and the websocket handlers it
    # registered, alive into the next test: processEvents is what actually
    # reaps it. Without this, an EquipmentPanel left behind here made
    # test_selection_is_non_blocking fail in a full run while passing alone.
    made.client = None
    made.selected_equipment = None
    made.deleteLater()
    qapp.processEvents()


class TestTheButtonActuallyRemoves:
    def test_pressing_remove_calls_the_server(self, panel, loop):
        client = _Client()
        panel.client = client
        panel.selected_equipment = _equipment()

        panel.remove_equipment()
        pump(loop)

        assert client.removed == ["scope_a62f42e9"], (
            "the handler never reached the server -- this is exactly how it "
            "shipped broken, raising inside an async slot that swallows it")

    def test_the_selection_is_cleared_afterwards(self, panel, loop):
        panel.client = _Client()
        panel.selected_equipment = _equipment()
        panel.remove_equipment()
        pump(loop)
        assert panel.selected_equipment is None

    def test_a_refusal_from_the_server_leaves_the_selection_alone(self, panel, loop):
        """409 is the server declining to strand a live session."""
        error = RuntimeError("409 Client Error: Conflict")
        panel.client = _Client(fail=error)
        panel.selected_equipment = _equipment()
        panel.remove_equipment()
        pump(loop)
        assert panel.selected_equipment is not None

    def test_nothing_selected_is_a_no_op(self, panel, loop):
        client = _Client()
        panel.client = client
        panel.selected_equipment = None
        panel.remove_equipment()
        pump(loop)
        assert client.removed == []


class TestTheHandlerMatchesTheModel:
    def test_every_field_the_handler_reads_exists(self):
        """The bug in one line: the handler read a field that is not there.

        Asserted against the dataclass rather than a fake, because the fake
        had the wrong field and would have agreed with the bug.
        """
        eq = _equipment()
        for field in ("equipment_id", "manufacturer", "model", "resource_name"):
            assert hasattr(eq, field), field
        assert not hasattr(eq, "resource_string"), (
            "if this ever exists, the handler and the model have drifted again")
