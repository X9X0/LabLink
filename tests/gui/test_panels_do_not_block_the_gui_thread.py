"""A panel's refresh must not run HTTP on the GUI thread.

LabLinkClient is synchronous -- ``requests`` under the hood -- so any
call made straight from a slot freezes the entire window for the round
trip, and for the full 10s read timeout when the server does not
answer. That is not a hypothetical latency: it is how the reported
"connecting takes about fifteen seconds" turned out to be spent, and
why ``call_blocking`` exists.

Four panels were still doing it after the diagnostics one was fixed --
alarm, scheduler, system and test_sequence. The system panel was the
worst of them, because it is the tab you are watching *during a server
update*, which is exactly when the server stops answering and every
request costs the full timeout. The window froze in the one moment the
operator most wanted to see progress.

The test is written against the source rather than by timing a real
freeze, because a timing test here would need a real Qt loop, a real
server and a real stall to be honest, and would pass on a fast machine
for the wrong reason. What can be checked exactly is the shape: the
refresh is a coroutine, and the client call inside it is awaited
through call_blocking rather than made directly.
"""

import inspect
import os
import re
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

#: panel module -> the class whose refresh is driven by the shell's timer.
TIMER_DRIVEN = {
    "client.ui.alarm_panel": "AlarmPanel",
    "client.ui.scheduler_panel": "SchedulerPanel",
    "client.ui.system_panel": "SystemPanel",
    "client.ui.diagnostics_panel": "DiagnosticsPanel",
    "client.ui.equipment_panel": "EquipmentPanel",
}

#: A bare synchronous client call: `self.client.foo(` with no await.
BARE_CALL = re.compile(r"(?<!await )(?<!await call_blocking\()self\.client\.\w+\(")


def _panel(module_name, class_name):
    import importlib

    return getattr(importlib.import_module(module_name), class_name)


def _refresh_of(panel):
    slot = getattr(panel, "refresh", None)
    assert slot is not None, f"{panel.__name__} has no refresh"
    return getattr(slot, "__wrapped__", slot)


@pytest.mark.parametrize("module,cls", sorted(TIMER_DRIVEN.items()))
class TestTheTimerDrivenRefreshIsAsynchronous:
    def test_refresh_is_a_coroutine(self, module, cls):
        underlying = _refresh_of(_panel(module, cls))
        assert inspect.iscoroutinefunction(underlying), (
            f"{cls}.refresh runs on the GUI thread; a slow or unreachable "
            f"server freezes the whole window for the read timeout")

    def test_refresh_makes_no_bare_client_call(self, module, cls):
        source = inspect.getsource(_refresh_of(_panel(module, cls)))
        bare = BARE_CALL.findall(source)
        assert not bare, (
            f"{cls}.refresh calls the synchronous client directly ({bare}); "
            f"it must go through call_blocking or the await buys nothing")


class TestTheWorstOffenderInParticular:
    """The system panel, during a server update, is the case that hurt."""

    def test_the_status_poll_is_also_off_the_thread(self):
        """refresh() calls it, and so do six other places."""
        from client.ui.system_panel import SystemPanel

        slot = SystemPanel._update_status_display
        underlying = getattr(slot, "__wrapped__", slot)
        assert inspect.iscoroutinefunction(underlying), (
            "_update_status_display blocks; refresh awaiting around it "
            "achieves nothing while this still runs inline")

    def test_it_is_guarded_against_pile_up(self):
        """A 5s timer against a server that takes longer than 5s."""
        from client.ui.system_panel import SystemPanel

        slot = SystemPanel.refresh
        source = inspect.getsource(getattr(slot, "__wrapped__", slot))
        assert "claim_slot" in source, (
            "without the guard, a restarting server queues one refresh "
            "per tick and they all land at once when it comes back")


class TestTheSequencePanelFetchesOffTheThread:
    """Its slots were already async and still blocked inside.

    A decorator that says asyncSlot does not make the body
    asynchronous: `result = self.client.list_test_templates()` inside a
    coroutine blocks the loop exactly as it would anywhere else. This is
    the failure that looks fixed in a diff and is not.
    """

    @pytest.mark.parametrize("name", [
        "_load_templates", "_create_from_template", "_save_sequence",
    ])
    def test_no_bare_client_call(self, name):
        from client.ui.test_sequence_panel import TestSequencePanel

        slot = getattr(TestSequencePanel, name)
        source = inspect.getsource(getattr(slot, "__wrapped__", slot))
        bare = BARE_CALL.findall(source)
        assert not bare, f"{name} blocks the loop on {bare}"


class TestNoCoroutineOpensAModalInline:
    """The re-entrancy bug, asserted structurally rather than by memory.

    A modal opened inside a coroutine lets the nested Qt loop step other
    asyncio tasks while this one is still current, and asyncio refuses:
    "Cannot enter into task X while another task Y is being executed".
    It cost four wrong theories to find the first time.

    Converting a handler to async is exactly what creates the hazard, so
    the check has to be automatic. Two of these were missed by hand
    during the very change that added the rest -- a multi-line edit that
    silently failed to apply, leaving the function async with its
    dialogs still inline, which is the worst of both.
    """

    @staticmethod
    def _offenders(module_name):
        import ast
        import importlib

        source = open(
            importlib.import_module(module_name).__file__, encoding="utf-8"
        ).read()
        tree = ast.parse(source)

        # A call is safe if it sits inside a lambda (handed to _ask) or is
        # an argument to _say_later.
        safe = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Lambda):
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Call):
                        safe.add(inner.lineno)
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("_say_later", "say_later")):
                for arg in node.args:
                    safe.add(getattr(arg, "lineno", -1))

        found = []
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.AsyncFunctionDef):
                continue
            for node in ast.walk(fn):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "QMessageBox"
                        and node.func.attr in ("question", "information",
                                               "critical", "warning")
                        and node.lineno not in safe):
                    found.append(f"{fn.name}() line {node.lineno}: "
                                 f"QMessageBox.{node.func.attr}")
        return found

    @pytest.mark.parametrize("module", sorted(TIMER_DRIVEN) + [
        "client.ui.test_sequence_panel",
    ])
    def test_every_modal_is_deferred(self, module):
        offenders = self._offenders(module)
        assert not offenders, (
            "a coroutine opens a modal inline; the nested Qt loop will try "
            "to step other asyncio tasks while it is still current:\n  "
            + "\n  ".join(offenders))
