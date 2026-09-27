"""The converted handlers still call the server with the right arguments.

Nineteen handlers across the sync and acquisition panels were rewritten
mechanically -- wrapped in call_blocking by a script that walks
parentheses -- to get them off the GUI thread.

test_panels_do_not_block_the_gui_thread proves the *shape* of that
change: the handler is a coroutine, the call goes through
call_blocking, no modal opens inline. It proves nothing about
behaviour. A transform that moved an argument, dropped a keyword or
reordered a pair would satisfy every one of those checks and still
send the wrong thing to the instrument.

Nothing drove these handlers before today, so that risk was entirely
uncovered. These tests drive each one against a recording client and
assert what actually reached it.
"""

import asyncio
import os
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

if GUI_AVAILABLE:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QListWidgetItem

    from client.ui.acquisition_panel import AcquisitionPanel
    from client.ui.sync_panel import SyncPanel


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class Dialogs:
    """Stand in for every dialog these panels raise.

    Without this the deferred QMessageBox actually opens: say_later
    schedules it with QTimer.singleShot(0, ...), processEvents fires
    the timer, and the modal waits for a click that never comes. The
    first run of this file hung on exactly that, which is a fair
    demonstration that the deferral really does put a real modal up --
    but it makes the test useless.
    """

    def __init__(self):
        self.shown = []

    def install(self, monkeypatch, module):
        for kind in ("information", "critical", "warning"):
            def record(_parent, title, text, k=kind):
                self.shown.append((k, title, text))
            monkeypatch.setattr(f"{module}.QMessageBox.{kind}", record)


class Recorder:
    """Answers every client call and remembers how it was called."""

    def __init__(self, answer=None):
        self.calls = []
        self.answer = answer if answer is not None else {"success": True}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self.answer

        return record

    def named(self, name):
        return [c for c in self.calls if c[0] == name]


async def drive(coro, qapp, limit=5.0):
    """Run a handler to completion while pumping Qt events."""
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


def underlying(panel, name):
    """The coroutine behind an asyncSlot, callable directly."""
    slot = getattr(type(panel), name)
    return getattr(slot, "__wrapped__", slot)


# --------------------------------------------------------------------- #
# Sync panel
# --------------------------------------------------------------------- #


@pytest.fixture
def sync_panel(qapp, monkeypatch):
    Dialogs().install(monkeypatch, "client.ui.sync_panel")
    made = SyncPanel()
    made.client = Recorder()
    yield made
    made.deleteLater()
    qapp.processEvents()


class TestTheSyncGroupButtons:
    @pytest.mark.parametrize("handler,api", [
        ("start_sync_group", "start_sync_group"),
        ("stop_sync_group", "stop_sync_group"),
        ("pause_sync_group", "pause_sync_group"),
        ("resume_sync_group", "resume_sync_group"),
    ])
    @pytest.mark.asyncio
    async def test_it_passes_the_selected_group(self, sync_panel, qapp,
                                                handler, api):
        sync_panel.current_group_id = "bench-1"

        await drive(underlying(sync_panel, handler)(sync_panel), qapp)

        made = sync_panel.client.named(api)
        assert made, f"{handler} called nothing; client saw {sync_panel.client.calls}"
        _name, args, kwargs = made[0]
        assert "bench-1" in args or "bench-1" in kwargs.values(), (
            f"{handler} sent {args} {kwargs}")

    @pytest.mark.parametrize("handler", [
        "start_sync_group", "stop_sync_group", "pause_sync_group",
        "resume_sync_group", "delete_sync_group",
    ])
    @pytest.mark.asyncio
    async def test_nothing_is_sent_without_a_group(self, sync_panel, qapp,
                                                   handler):
        """The guard runs before the call, and must still do so now that
        the handler is a coroutine."""
        sync_panel.current_group_id = None

        await drive(underlying(sync_panel, handler)(sync_panel), qapp)

        assert sync_panel.client.calls == [], (
            f"{handler} talked to the server with no group selected")

    @pytest.mark.asyncio
    async def test_create_sends_every_field_it_collected(self, sync_panel,
                                                         qapp):
        """The handler with the most arguments, and so the most to lose
        in a mechanical rewrite."""
        sync_panel.group_id_edit.setText("  bench-1  ")
        item = QListWidgetItem("PSU")
        item.setData(Qt.ItemDataRole.UserRole, "ps_1")
        sync_panel.equipment_list.addItem(item)
        item.setSelected(True)
        sync_panel.tolerance_spin.setValue(12.5)
        sync_panel.wait_for_all_check.setChecked(True)
        sync_panel.auto_align_check.setChecked(False)

        await drive(underlying(sync_panel, "create_sync_group")(sync_panel),
                    qapp)

        made = sync_panel.client.named("create_sync_group")
        assert made, f"nothing was created; saw {sync_panel.client.calls}"
        _name, _args, kwargs = made[0]
        assert kwargs["group_id"] == "bench-1", "the id was not stripped"
        assert kwargs["equipment_ids"] == ["ps_1"]
        assert kwargs["sync_tolerance_ms"] == pytest.approx(12.5)
        assert kwargs["wait_for_all"] is True
        assert kwargs["auto_align_timestamps"] is False

    @pytest.mark.asyncio
    async def test_delete_asks_first_and_obeys_no(self, sync_panel, qapp,
                                                  monkeypatch):
        sync_panel.current_group_id = "bench-1"

        async def say_no(_put_it_up):
            return 0                     # anything that is not Yes
        monkeypatch.setattr(sync_panel, "_ask", say_no)

        await drive(underlying(sync_panel, "delete_sync_group")(sync_panel),
                    qapp)

        assert sync_panel.client.named("delete_sync_group") == [], (
            "it deleted the group after the operator declined")

    @pytest.mark.asyncio
    async def test_delete_goes_ahead_on_yes(self, sync_panel, qapp,
                                            monkeypatch):
        from PyQt6.QtWidgets import QMessageBox

        sync_panel.current_group_id = "bench-1"

        async def say_yes(_put_it_up):
            return QMessageBox.StandardButton.Yes
        monkeypatch.setattr(sync_panel, "_ask", say_yes)

        await drive(underlying(sync_panel, "delete_sync_group")(sync_panel),
                    qapp)

        made = sync_panel.client.named("delete_sync_group")
        assert made and "bench-1" in made[0][1], made


# --------------------------------------------------------------------- #
# Acquisition panel
# --------------------------------------------------------------------- #


@pytest.fixture
def acq_panel(qapp, monkeypatch):
    Dialogs().install(monkeypatch, "client.ui.acquisition_panel")
    made = AcquisitionPanel()
    made.client = Recorder()
    yield made
    made.deleteLater()
    qapp.processEvents()


class TestTheAcquisitionButtons:
    @pytest.mark.parametrize("handler,api", [
        ("start_acquisition", "start_acquisition"),
        ("pause_acquisition", "pause_acquisition"),
        ("resume_acquisition", "resume_acquisition"),
    ])
    @pytest.mark.asyncio
    async def test_it_passes_the_current_session(self, acq_panel, qapp,
                                                 handler, api):
        acq_panel.current_acquisition_id = "acq-7"

        await drive(underlying(acq_panel, handler)(acq_panel), qapp)

        made = acq_panel.client.named(api)
        assert made, f"{handler} called nothing; saw {acq_panel.client.calls}"
        assert "acq-7" in made[0][1], made[0]

    @pytest.mark.parametrize("handler", [
        "start_acquisition", "pause_acquisition", "resume_acquisition",
        "export_current_session", "load_acquisition_data",
        "show_rolling_stats", "show_fft_analysis", "show_trend_analysis",
        "show_quality_metrics",
    ])
    @pytest.mark.asyncio
    async def test_nothing_is_sent_without_a_session(self, acq_panel, qapp,
                                                     handler):
        acq_panel.current_acquisition_id = None

        await drive(underlying(acq_panel, handler)(acq_panel), qapp)

        assert acq_panel.client.calls == [], (
            f"{handler} talked to the server with no session selected")

    @pytest.mark.asyncio
    async def test_loading_data_passes_the_point_limit(self, acq_panel, qapp):
        """A keyword argument, which is the kind a paren walker can
        drop without anything else noticing."""
        acq_panel.current_acquisition_id = "acq-7"
        acq_panel.max_points_spin.setValue(250)
        acq_panel.client = Recorder(answer={"channels": [], "data": {}})

        await drive(underlying(acq_panel, "load_acquisition_data")(acq_panel),
                    qapp)

        made = acq_panel.client.named("get_acquisition_data")
        assert made, f"saw {acq_panel.client.calls}"
        _name, args, kwargs = made[0]
        assert "acq-7" in args
        assert kwargs.get("max_points") == 250, (
            f"the point limit did not survive the rewrite: {kwargs}")

    @pytest.mark.asyncio
    async def test_export_does_nothing_when_the_chooser_is_cancelled(
            self, acq_panel, qapp, monkeypatch):
        """Cancelling returns an empty filename, and the old code read
        that correctly. The rewrite must not have lost the check."""
        acq_panel.current_acquisition_id = "acq-7"

        async def cancelled(_put_it_up):
            return ("", "")
        monkeypatch.setattr(acq_panel, "_ask", cancelled)

        await drive(
            underlying(acq_panel, "export_current_session")(acq_panel), qapp)

        assert acq_panel.client.named("export_acquisition_data") == [], (
            "it exported after the file chooser was cancelled")

    @pytest.mark.asyncio
    async def test_export_picks_the_format_from_the_extension(
            self, acq_panel, qapp, monkeypatch):
        acq_panel.current_acquisition_id = "acq-7"

        async def chose_hdf5(_put_it_up):
            return ("/tmp/run.h5", "")
        monkeypatch.setattr(acq_panel, "_ask", chose_hdf5)

        await drive(
            underlying(acq_panel, "export_current_session")(acq_panel), qapp)

        made = acq_panel.client.named("export_acquisition_data")
        assert made, f"saw {acq_panel.client.calls}"
        _name, args, kwargs = made[0]
        assert "acq-7" in args
        assert kwargs.get("format") == "hdf5", kwargs
        assert kwargs.get("filepath") == "/tmp/run.h5", kwargs

    @pytest.mark.asyncio
    async def test_an_analysis_view_asks_for_channels_then_the_analysis(
            self, acq_panel, qapp):
        """These make two calls, and the order matters: the channel list
        comes from the first and feeds the second."""
        acq_panel.current_acquisition_id = "acq-7"
        acq_panel.client = Recorder(answer={"channels": ["CH1"], "stats": {}})

        await drive(underlying(acq_panel, "show_rolling_stats")(acq_panel),
                    qapp)

        names = [c[0] for c in acq_panel.client.calls]
        assert names[0] == "get_acquisition_data", names
        assert "get_acquisition_rolling_stats" in names, names
        stats = acq_panel.client.named("get_acquisition_rolling_stats")[0]
        assert stats[2].get("channel") == "CH1", stats
