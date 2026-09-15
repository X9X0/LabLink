"""
Tests that blocking API calls are offloaded off the event loop.

LabLinkClient is synchronous (requests-based). Calling it directly from a Qt
slot or a qasync coroutine freezes the GUI for the whole round-trip, which is
what made live equipment monitoring stutter. call_blocking() moves that work
to a worker thread.
"""

import asyncio
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from client.api.client import call_blocking


class TestCallBlocking:
    @pytest.mark.asyncio
    async def test_returns_the_functions_result(self):
        result = await call_blocking(lambda: {"voltage": 5.0})

        assert result == {"voltage": 5.0}

    @pytest.mark.asyncio
    async def test_passes_args_and_kwargs(self):
        def fake_send_command(equipment_id, command, params=None):
            return (equipment_id, command, params)

        result = await call_blocking(
            fake_send_command, "eq-1", "set_voltage", params={"voltage": 5.0}
        )

        assert result == ("eq-1", "set_voltage", {"voltage": 5.0})

    @pytest.mark.asyncio
    async def test_runs_off_the_event_loop_thread(self):
        """The whole point: the blocking call must not run on the UI thread."""
        calling_thread = threading.current_thread().ident

        worker_thread = await call_blocking(
            lambda: threading.current_thread().ident
        )

        assert worker_thread != calling_thread

    @pytest.mark.asyncio
    async def test_event_loop_stays_responsive_during_a_slow_call(self):
        """A slow server must not stall other work on the loop.

        Without offloading, the 0.3s sleep would block the loop and the ticker
        below could not advance while it ran.
        """
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        ticker_task = asyncio.create_task(ticker())
        try:
            await call_blocking(time.sleep, 0.3)
        finally:
            ticker_task.cancel()

        assert ticks > 5, (
            f"event loop was blocked during the call (only {ticks} ticks)"
        )

    @pytest.mark.asyncio
    async def test_exceptions_propagate_to_the_caller(self):
        """Panels rely on try/except around these calls to show errors."""

        def failing_call():
            raise ConnectionError("server unreachable")

        with pytest.raises(ConnectionError, match="server unreachable"):
            await call_blocking(failing_call)

    @pytest.mark.asyncio
    async def test_concurrent_calls_do_not_serialise_on_the_loop(self):
        started = asyncio.get_running_loop().time()

        await asyncio.gather(
            call_blocking(time.sleep, 0.2),
            call_blocking(time.sleep, 0.2),
            call_blocking(time.sleep, 0.2),
        )

        elapsed = asyncio.get_running_loop().time() - started
        assert elapsed < 0.5, f"calls ran serially ({elapsed:.2f}s)"


class TestPanelsUseOffloading:
    """Guards against a blocking call being reintroduced on a hot path.

    These paths are timer-driven (1-2 Hz), so a synchronous client call here
    freezes the GUI on every tick.
    """

    HOT_PATHS = [
        ("client/ui/control_panel.py", "_update_readings"),
        ("client/ui/control_panel.py", "refresh_equipment_list"),
        ("client/ui/acquisition_panel.py", "refresh_sessions"),
        ("client/ui/sync_panel.py", "refresh_groups"),
        ("client/ui/test_sequence_panel.py", "_poll_execution_status"),
        ("client/ui/equipment_panel.py", "refresh"),
        ("client/ui/equipment_panel.py", "refresh_readings"),
    ]

    @pytest.mark.parametrize("rel_path,func_name", HOT_PATHS)
    def test_hot_path_is_async(self, rel_path, func_name):
        import ast

        root = os.path.join(os.path.dirname(__file__), "../..")
        with open(os.path.join(root, rel_path), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())

        matches = [
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == func_name
        ]
        assert matches, f"{func_name} not found in {rel_path}"

        for node in matches:
            assert isinstance(node, ast.AsyncFunctionDef), (
                f"{rel_path}::{func_name} is synchronous; a blocking client "
                "call here freezes the Qt event loop on every timer tick"
            )

    @pytest.mark.parametrize("rel_path,func_name", HOT_PATHS)
    def test_hot_path_does_not_call_client_synchronously(self, rel_path, func_name):
        """No bare ``self.client.foo()`` on a hot path.

        Offloaded calls pass the method as a reference
        (``call_blocking(self.client.foo, ...)``), so they are an Attribute
        node rather than a Call and are not flagged. Natively-async client
        methods invoked as ``await self.client.foo()`` are allowed.
        """
        import ast

        root = os.path.join(os.path.dirname(__file__), "../..")
        # Explicit UTF-8: bare open() decodes with the locale's codec, which
        # is cp1252 on Windows, and these UI modules are not pure ASCII.
        with open(os.path.join(root, rel_path), encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source)

        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                child.parent = parent

        target = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == func_name
        )

        offenders = []
        for sub in ast.walk(target):
            if not (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)):
                continue
            owner = sub.func.value
            is_client_call = (
                isinstance(owner, ast.Attribute)
                and owner.attr == "client"
                and isinstance(owner.value, ast.Name)
                and owner.value.id == "self"
            )
            if is_client_call and not isinstance(
                getattr(sub, "parent", None), ast.Await
            ):
                offenders.append(f"line {sub.lineno}: self.client.{sub.func.attr}()")

        assert not offenders, (
            f"{rel_path}::{func_name} calls the synchronous client directly "
            f"({'; '.join(offenders)}). Wrap it in call_blocking() - this path "
            "is timer-driven and will freeze the GUI."
        )
