"""Run the converted handlers for real, rather than reading their source.

The other tests here check the *shape* of these handlers: that refresh
is a coroutine, that no QMessageBox call sits inline in an
AsyncFunctionDef. Shape checks earn their place -- they caught two
half-converted handlers that were async with their dialogs still
inline. But they cannot tell you the handler still works. A dialog
that is deferred and then never shown looks identical to a correct one
from the ast.

So these drive the real panels, with the client faked and QMessageBox
recorded instead of opened, and assert the three things that actually
matter on the bench:

  - the operator is still asked before anything destructive, and
    answering No stops it;
  - the dialog really does appear, rather than being swallowed by the
    deferral;
  - the loop keeps running while the request is outstanding.

Qt events are pumped by hand below because a QTimer.singleShot(0) --
which is how both _say_later and _ask escape the coroutine -- only
fires when someone processes events. qasync does that in the running
client; a bare asyncio loop does not, so `drive` stands in for it.
"""

import asyncio
import os
import sys
import time

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
    from client.ui.system_panel import SystemPanel

PANEL_MODULE = "client.ui.system_panel"

#: How long the fake server takes. The freeze test reads the
#: difference between this and FREEZE_SEC as its signal.
REQUEST_SEC = 0.6


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class Dialogs:
    """Records what would have been shown, and answers any prompt."""

    def __init__(self, answer=None):
        self.shown = []          # (kind, title, text)
        self.answer = answer

    def install(self, monkeypatch, module=PANEL_MODULE):
        for kind in ("information", "critical", "warning"):
            def record(_parent, title, text, k=kind):
                self.shown.append((k, title, text))
            monkeypatch.setattr(f"{module}.QMessageBox.{kind}", record)

        def answer_it(_parent, title, text, *rest):
            self.shown.append(("question", title, text))
            return self.answer
        monkeypatch.setattr(f"{module}.QMessageBox.question", answer_it)

    def asked(self):
        return [t for kind, t, _ in self.shown if kind == "question"]

    def told(self):
        return [t for kind, t, _ in self.shown if kind != "question"]


class Client:
    """A LabLinkClient stand-in: records calls, and can be slow."""

    host = "10.10.0.51"

    def __init__(self, delay=0.0):
        self.calls = []
        self.delay = delay

    def _record(self, name):
        self.calls.append(name)
        if self.delay:
            time.sleep(self.delay)      # blocking, exactly as the real one is
        return {"success": True, "message": name + " ok"}

    def get_server_version(self):
        self._record("get_server_version")
        return {"version": "2.4.1"}

    def get_update_status(self):
        self._record("get_update_status")
        return {"update_mode": "stable", "status": "idle"}

    def list_equipment(self):
        self._record("list_equipment")
        return []

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *a, **kw: self._record(name)


async def drive(coro, qapp, limit=8.0):
    """Run `coro` while pumping Qt events, which is what qasync does.

    Without processEvents the zero-delay timers that carry every
    deferred dialog never fire, and an _ask would wait for ever -- so
    a test that forgot this would hang rather than fail, which is its
    own kind of misleading.
    """
    loop = asyncio.get_event_loop()
    task = asyncio.ensure_future(coro)
    deadline = loop.time() + limit
    while not task.done() and loop.time() < deadline:
        qapp.processEvents()
        await asyncio.sleep(0.005)
    qapp.processEvents()
    if not task.done():
        task.cancel()
        raise AssertionError("the handler never finished")
    return await task


async def longest_freeze(qapp, start, limit=8.0):
    """Drive `start()` and report the longest gap the loop went untouched.

    `start` is a callable, not a coroutine, and that matters. These
    handlers are qasync.asyncSlot, so calling one returns a Task that is
    *already scheduled*; Python evaluates an argument before the call,
    so passing `panel.refresh()` directly starts the work before the
    heartbeat exists and the stall lands outside the measured window.
    That is not a hypothetical either -- it made this test pass against
    a deliberately blocking get_server_version.

    A total tick count is too loose to be trusted: a handler that makes
    two requests and blocks on only one still accumulates plenty of
    ticks during the other, and the test passes while the window is
    visibly frozen for a third of a second. That is not hypothetical --
    it is what this function replaced, after a deliberately blocking
    get_server_version failed to fail.

    The longest gap measures the thing the operator actually notices.
    """
    ticks = []
    stop = asyncio.Event()

    async def heartbeat():
        while not stop.is_set():
            ticks.append(time.monotonic())
            await asyncio.sleep(0.01)

    beating = asyncio.ensure_future(heartbeat())
    await asyncio.sleep(0.02)               # let it get going
    mark = len(ticks)
    opened = time.monotonic()
    try:
        await drive(start(), qapp, limit=limit)
    finally:
        closed = time.monotonic()
        stop.set()
        await beating

    # The window's own edges count as observations. Without them a total
    # freeze -- the heartbeat never running twice -- leaves no gaps to
    # measure, and "no data" came back as 0.0, i.e. as success. That is
    # the same absence-read-as-success this whole file exists to catch,
    # and it passed a deliberately blocking get_server_version twice
    # before anyone looked at the tick count.
    marks = [opened] + ticks[mark:] + [closed]
    return max(b - a for a, b in zip(marks, marks[1:]))


@pytest.fixture
def panel(qapp):
    made = SystemPanel()
    yield made
    made.deleteLater()
    qapp.processEvents()


class TestItStillAsksBeforeSomethingDestructive:
    """Answering No must stop it. The assertion that matters most."""

    @pytest.mark.asyncio
    async def test_declining_a_rollback_does_not_roll_back(
            self, panel, qapp, monkeypatch):
        dialogs = Dialogs(answer=QMessageBox.StandardButton.No)
        dialogs.install(monkeypatch)
        panel.client = Client()

        await drive(panel.rollback(), qapp)

        assert dialogs.asked(), "it rolled back without asking at all"
        assert "rollback_server" not in panel.client.calls, (
            "the operator declined and it rolled the server back anyway")

    @pytest.mark.asyncio
    async def test_accepting_a_rollback_rolls_back(
            self, panel, qapp, monkeypatch):
        """The deferral must not break the answer coming back."""
        dialogs = Dialogs(answer=QMessageBox.StandardButton.Yes)
        dialogs.install(monkeypatch)
        panel.client = Client()

        await drive(panel.rollback(), qapp)

        assert "rollback_server" in panel.client.calls, (
            "accepted, and nothing happened -- _ask lost the answer")

    @pytest.mark.asyncio
    async def test_declining_a_rebuild_does_not_rebuild(
            self, panel, qapp, monkeypatch):
        dialogs = Dialogs(answer=QMessageBox.StandardButton.No)
        dialogs.install(monkeypatch)
        panel.client = Client()

        await drive(panel.execute_rebuild(), qapp)

        assert dialogs.asked()
        assert "execute_rebuild" not in panel.client.calls


class TestTheDialogIsActuallyShown:
    """A deferred dialog that never arrives looks fine to the ast."""

    @pytest.mark.asyncio
    async def test_an_outcome_is_reported(self, panel, qapp, monkeypatch):
        dialogs = Dialogs(answer=QMessageBox.StandardButton.Yes)
        dialogs.install(monkeypatch)
        panel.client = Client()

        await drive(panel.execute_rebuild(), qapp)

        assert dialogs.told(), (
            "only the prompt appeared; the operator was left not knowing "
            f"whether it worked: {dialogs.shown}")

    @pytest.mark.asyncio
    async def test_a_handler_with_no_prompt_still_reports(
            self, panel, qapp, monkeypatch):
        dialogs = Dialogs()
        dialogs.install(monkeypatch)
        panel.client = Client()

        await drive(panel.configure_auto_rebuild(), qapp)

        assert "configure_auto_rebuild" in panel.client.calls
        assert dialogs.told(), "configured silently"


class TestTheLoopKeepsRunning:
    """The whole point of the conversion.

    Each request the fake client serves takes 0.3s. If it runs on the
    GUI thread the loop goes untouched for that whole time; off it, the
    longest gap is a scheduling hiccup. FREEZE_SEC sits between the two
    with room to spare either side, so neither a slow CI box nor a fast
    one changes the answer.
    """

    #: Longer than any scheduling hiccup, far shorter than the stall.
    #:
    #: The gap between the two is what makes this reliable, so the fake
    #: request is slow enough to leave one. At a 0.3s request and a
    #: 0.15s bar there was only 0.15s of daylight, and a full-suite run
    #: on a busy machine crossed it -- passing alone and failing in the
    #: crowd, which is the signature of a threshold set too close to the
    #: noise rather than of a real stall.
    FREEZE_SEC = 0.25

    @pytest.mark.asyncio
    async def test_a_slow_handler_does_not_freeze_the_window(
            self, panel, qapp, monkeypatch):
        dialogs = Dialogs(answer=QMessageBox.StandardButton.Yes)
        dialogs.install(monkeypatch)
        panel.client = Client(delay=REQUEST_SEC)      # a server taking its time

        frozen = await longest_freeze(qapp, panel.rollback)

        assert frozen < self.FREEZE_SEC, (
            f"the loop went {frozen:.2f}s untouched while a slow request "
            f"was out; that is the window locked for the round trip")

    @pytest.mark.asyncio
    async def test_refresh_does_not_freeze_either(self, panel, qapp):
        """refresh makes two requests, so a total-tick count misses a
        stall in one of them. This measures the stall itself."""
        panel.client = Client(delay=REQUEST_SEC)

        frozen = await longest_freeze(qapp, panel.refresh)

        assert frozen < self.FREEZE_SEC, (
            f"refresh locked the window for {frozen:.2f}s, and it runs on "
            f"a 5s timer -- so that is every five seconds for as long as "
            f"the server is slow")
