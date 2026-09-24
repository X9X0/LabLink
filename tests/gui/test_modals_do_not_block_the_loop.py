"""A modal must not be opened while its coroutine is the current task.

This is the refresh stall, finally. Five mechanisms were proposed for it
over an evening and the first four were wrong; the log said this one
outright, once the error text was read untruncated:

    RuntimeError: Cannot enter into task
      <Task pending coro=<EquipmentPanel.refresh()
        wait_for=<_GatheringFuture finished result=[{...}]>>
      while another task
        <Task pending coro=<EquipmentPanel.connect_equipment()
          running at equipment_panel.py:924>> is being executed

Line 924 was ``QMessageBox.information(... "Equipment connected
successfully")``. A modal runs a nested Qt event loop; qasync pumps
asyncio from it; and asyncio refuses to enter a second task while one is
current. So ``refresh`` -- whose fan-out had *finished*, with the
equipment list sitting in the future -- could never be resumed. Its
in-flight slot stayed held until the 45s backstop and every refresh in
between was refused. Two stalls ran to 310s and 177s: a dialog left open
that long.

Not "asyncio.run leaving the thread without a loop", not "a hung
request", not "a task destroyed", not "a coalescing loop that never
ends". One loop, one task, one modal.

Two shapes are correct here, and the panel now uses both:

* nothing to answer -> show it from a timer and carry on (_say_later)
* something to answer -> show it from a timer and await the answer
  (_ask), so the coroutine is suspended, not current, while it is up

Asserted against the source. Driving a real modal in a test means
either blocking for ever or stubbing the thing under test.
"""

import ast
import inspect
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication      # noqa: F401


    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(not GUI_AVAILABLE, reason="PyQt6 is required")

if GUI_AVAILABLE:
    from client.ui import equipment_panel as panel_module
    from client.ui.equipment_panel import EquipmentPanel
    from client.utils import modals

OPENS_A_MODAL = ("QMessageBox.information(", "QMessageBox.warning(",
                 "QMessageBox.critical(", "QMessageBox.question(",
                 "box.exec()", ".exec()")


def modals_opened_inline():
    """Every modal opened directly in a coroutine's own body.

    A modal inside a nested ``def`` is fine: that runs later, from a
    timer, when the coroutine is no longer the current task.
    """
    source = inspect.getsource(panel_module)
    lines = source.splitlines()
    offenders = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        nested = [(f.lineno, f.end_lineno or f.lineno)
                  for f in ast.walk(node) if isinstance(f, ast.FunctionDef)]
        for n in range(node.lineno, (node.end_lineno or node.lineno) + 1):
            text = lines[n - 1]
            if not any(m in text for m in OPENS_A_MODAL):
                continue
            if "_say_later" in text or "_ask(" in text or "lambda" in text:
                continue
            if any(a <= n <= b for a, b in nested):
                continue
            offenders.append(f"{node.name}:{n} {text.strip()[:60]}")
    return offenders


class TestNoCoroutineOpensAModalInline:
    def test_none_are_left(self):
        """The whole fault, in one assertion."""
        offenders = modals_opened_inline()
        assert offenders == [], (
            "these open a modal while their own task is current, which "
            "strands any task the nested loop then tries to step:\n  "
            + "\n  ".join(offenders))


class TestTheTwoSafeShapes:
    """Both live in client/utils/modals.py now.

    They were EquipmentPanel methods when this was written, and were
    lifted out unchanged so the panels converted afterwards could use
    them rather than rediscover the problem. The panel keeps thin
    wrappers, so the assertions follow the implementation rather than
    the name.
    """

    def test_say_later_defers_to_a_timer(self):
        body = inspect.getsource(modals.say_later)
        assert "QTimer.singleShot(0" in body, (
            "it still opens the dialog inline")

    def test_ask_awaits_the_answer(self):
        """The coroutine must be suspended while the dialog is up."""
        body = inspect.getsource(modals.ask)
        assert "QTimer.singleShot(0" in body
        assert "await answer" in body, (
            "without awaiting a future it is still the current task")
        assert "create_future" in body

    def test_ask_reports_a_dialog_that_cannot_open(self):
        """Or the caller waits for ever on a future nobody completes."""
        body = inspect.getsource(modals.ask)
        assert "set_exception" in body

    def test_ask_is_a_coroutine(self):
        assert inspect.iscoroutinefunction(modals.ask)
        assert inspect.iscoroutinefunction(EquipmentPanel._ask), (
            "the panel wrapper must stay awaitable for its call sites")

    def test_the_panel_wrappers_delegate_rather_than_reimplement(self):
        """Two copies would drift, and only one would get the next fix."""
        for name in ("_say_later", "_ask"):
            body = inspect.getsource(getattr(EquipmentPanel, name))
            assert "QTimer" not in body, (
                f"{name} grew its own copy of the timer dance")


class TestTheHandlersStillTellTheOperatorThings:
    """Deferring must not mean dropping."""

    @pytest.mark.parametrize("handler", ["connect_equipment",
                                         "disconnect_equipment",
                                         "remove_equipment"])
    def test_each_still_reports_success_or_failure(self, handler):
        body = inspect.getsource(getattr(EquipmentPanel, handler))
        assert "_say_later" in body or "_ask(" in body, (
            f"{handler} no longer tells the operator anything")

    def test_remove_still_asks_before_removing(self):
        body = inspect.getsource(EquipmentPanel.remove_equipment)
        assert "_ask(" in body and "StandardButton.Yes" in body, (
            "the confirmation was lost in the conversion")

    def test_disconnect_still_offers_the_output_choice(self):
        body = inspect.getsource(EquipmentPanel._choose_disconnect_state)
        assert "_ask(" in body
        for choice in ("Turn output off", "Leave it running"):
            assert choice in body, f"{choice!r} went missing"
