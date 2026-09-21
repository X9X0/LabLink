"""Nothing that schedules coroutines may run before the event loop does.

Every client start logged five to twenty of these:

    RuntimeError: Cannot enter into task <Task pending name='Task-19'
      coro=<EquipmentPanel.refresh() ...>>
    Task was destroyed but it is pending!

They come in batches, and the batch includes WebSocketManager's own
receive loop and keepalive -- the socket reader dying with nothing
watching, which is a fault and not noise.

The cause is the order in main(). The connection dialog was shown
*before* loop.run_forever(), so connecting from it ran the whole bind
chain with no loop running. run_now_or_soon then had to run those
coroutines itself, on a throwaway loop, and asyncio.run() leaves the
thread's current loop unset on the way out -- after which every
@asyncSlot is handed a fresh loop nobody will ever pump, and its task
sits pending until it is collected.

Showing the dialog from a zero-delay timer fires it on the loop's first
pass instead. It still appears immediately; it appears with an event
loop underneath it.

Read as source rather than executed: running main() would open a
window, a dialog and sockets. What matters is the order of two
statements, and the order is in the text.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

MAIN = os.path.join(os.path.dirname(__file__), "../..", "client", "main.py")


@pytest.fixture(scope="module")
def source():
    with open(MAIN, encoding="utf-8") as handle:
        return handle.read()


def line_of(source, pattern):
    match = re.search(pattern, source, re.MULTILINE)
    assert match, f"no {pattern!r} in client/main.py"
    return source[:match.start()].count("\n") + 1


class TestTheDialogWaitsForTheLoop:
    def test_it_is_not_called_before_run_forever(self, source):
        """The bug, in one assertion."""
        assert not re.search(r"^\s*window\.show_connection_dialog\(\)\s*$",
                             source, re.MULTILINE), (
            "the dialog is called directly, so connecting from it runs the "
            "bind chain with no event loop running")

    def test_it_is_scheduled_onto_the_loop(self, source):
        assert re.search(r"QTimer\.singleShot\(\s*0\s*,\s*"
                         r"window\.show_connection_dialog\s*\)", source), (
            "nothing schedules the dialog")

    def test_it_is_scheduled_before_the_loop_starts(self, source):
        """Queued first, so it runs on the loop's first pass."""
        scheduled = line_of(source, r"QTimer\.singleShot\(\s*0\s*,\s*"
                                    r"window\.show_connection_dialog")
        running = line_of(source, r"loop\.run_forever\(\)")
        assert scheduled < running

    def test_qtimer_is_imported(self, source):
        assert re.search(r"from PyQt6\.QtCore import .*\bQTimer\b", source), (
            "QTimer is used but not imported, so startup raises NameError")

    def test_the_loop_is_still_the_qasync_one(self, source):
        """Changing the order must not change which loop runs."""
        assert "qasync.QEventLoop(app)" in source
        assert re.search(r"asyncio\.set_event_loop\(loop\)", source)


class TestRunNowOrSoonPrefersTheRunningLoop:
    """The other half: even reached, it must not strand the thread."""

    def test_a_running_loop_is_used_directly(self):
        import inspect

        from client.ui.instruments.base import run_now_or_soon

        body = inspect.getsource(run_now_or_soon)
        assert "get_running_loop" in body
        assert "create_task" in body

    def test_the_fallback_restores_the_thread_loop(self):
        import inspect

        from client.ui.instruments.base import run_now_or_soon

        body = inspect.getsource(run_now_or_soon)
        assert "set_event_loop(previous)" in body, (
            "asyncio.run() leaves the thread with no current loop, and every "
            "asyncSlot after that goes to a loop nobody runs")
