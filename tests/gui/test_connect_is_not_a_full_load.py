"""Connecting to a server must not block on tabs nobody is looking at.

Reported from the bench: connecting takes about fifteen seconds. The client
log says where it goes, to the millisecond::

    18:18:28,223  Connection state changed: connected
    18:18:38,239  diagnostics_panel ERROR  Read timed out
    18:18:38,242  Server '10.10.0.51' marked as connected

The connect itself costs about 140ms. What follows it cost ten seconds: the
initial load refreshed every panel, six of the seven do blocking HTTP on the
GUI thread, and the diagnostics one asks the server to run a connection
check, a communication check, a performance benchmark and a functionality
check against every instrument, serially. Measured against the two serial
supplies on the test bench: 20.5s cold, 9-20ms warm, because the server
caches it for thirty seconds.

So the window froze until the client's ten-second read timeout gave up, and
the table it was filling stayed empty. The cost bought nothing at all.

Two things are asserted here, because fixing only one re-breaks the other:
the initial load leaves off-screen tabs alone, and a tab brought to the
front loads at once rather than waiting for the five-second timer.
"""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication, QTabWidget, QWidget

    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(not GUI_AVAILABLE, reason="PyQt6 is required")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _Panel(QWidget):
    """Stands in for a panel, recording every refresh it is asked for."""

    def __init__(self, name, log):
        super().__init__()
        self._name = name
        self._log = log

    def refresh(self):
        self._log.append(self._name)


class _Window:
    """The two methods under test, over a real QTabWidget.

    Bound from MainWindow rather than copied, so this exercises the shipped
    code: constructing a MainWindow would open sockets and read settings.
    """

    def __init__(self, qapp, log):
        from client.ui.main_window import MainWindow

        self.tab_widget = QTabWidget()
        self.equipment_panel = _Panel("equipment", log)
        self.diagnostics_panel = _Panel("diagnostics", log)
        self.control_panel = _Panel("control", log)
        self.tab_widget.addTab(self.equipment_panel, "Equipment")
        self.tab_widget.addTab(self.control_panel, "Control")
        self.tab_widget.addTab(self.diagnostics_panel, "Diagnostics")

        self.client = type("C", (), {"connected": True})()
        self.refresh_all = MainWindow.refresh_all.__get__(self)
        self._on_tab_changed = MainWindow._on_tab_changed.__get__(self)
        self.periodic_refresh = MainWindow.periodic_refresh.__get__(self)


@pytest.fixture
def window(qapp):
    log = []
    made = _Window(qapp, log)
    yield made, log
    made.tab_widget.deleteLater()
    qapp.processEvents()


class TestTheInitialLoad:
    def test_it_does_not_refresh_an_off_screen_diagnostics_tab(self, window):
        """The ten seconds, in one assertion."""
        win, log = window
        win.tab_widget.setCurrentIndex(0)      # Equipment is on screen
        log.clear()

        win.refresh_all()

        assert "diagnostics" not in log, (
            "connect refreshed a tab nobody was looking at -- on the bench "
            f"that was a 10s freeze for an empty table; refreshed: {log}")

    def test_it_still_loads_the_equipment_list(self, window):
        """Both the Control tab and the equipment panel read from it."""
        win, log = window
        win.tab_widget.setCurrentIndex(2)      # something else on screen
        log.clear()
        win.refresh_all()
        assert "equipment" in log

    def test_it_loads_the_tab_that_is_on_screen(self, window):
        win, log = window
        win.tab_widget.setCurrentIndex(2)      # Diagnostics on screen
        log.clear()
        win.refresh_all()
        assert log.count("diagnostics") == 1, (
            "the tab the operator is looking at must be loaded, once")

    def test_the_visible_equipment_tab_is_not_refreshed_twice(self, window):
        win, log = window
        win.tab_widget.setCurrentIndex(0)
        log.clear()
        win.refresh_all()
        assert log.count("equipment") == 1, f"refreshed twice: {log}"

    def test_nothing_happens_while_disconnected(self, window):
        win, log = window
        win.client = None
        log.clear()
        win.refresh_all()
        assert log == []


class TestBringingATabToTheFront:
    def test_the_new_tab_is_refreshed_at_once(self, window):
        """Or it sits stale for up to five seconds, which is what the
        initial load used to paper over."""
        win, log = window
        win.tab_widget.setCurrentIndex(0)
        log.clear()

        win.tab_widget.setCurrentIndex(2)
        win._on_tab_changed(2)

        assert "diagnostics" in log

    def test_it_does_nothing_while_disconnected(self, window):
        win, log = window
        win.client = None
        log.clear()
        win._on_tab_changed(2)
        assert log == []

    def test_a_panel_that_raises_does_not_take_the_window_with_it(self, window):
        win, log = window

        def boom():
            raise RuntimeError("server went away mid-switch")

        win.diagnostics_panel.refresh = boom
        win.tab_widget.setCurrentIndex(2)
        win._on_tab_changed(2)      # must not raise


class TestTheDiagnosticsPanelDoesNotBlockTheGuiThread:
    """It is the one panel whose request can take twenty seconds."""

    def test_refresh_is_asynchronous(self):
        import inspect

        from client.ui.diagnostics_panel import DiagnosticsPanel

        slot = DiagnosticsPanel.refresh
        underlying = getattr(slot, "__wrapped__", slot)
        assert inspect.iscoroutinefunction(underlying), (
            "refresh runs on the GUI thread; a 20s health check freezes the "
            "whole window, which is exactly what was reported")

    def test_it_fetches_through_call_blocking(self):
        """Not self.client.get_all_equipment_health() directly."""
        import inspect

        from client.ui.diagnostics_panel import DiagnosticsPanel

        slot = DiagnosticsPanel.refresh
        source = inspect.getsource(getattr(slot, "__wrapped__", slot))
        assert "call_blocking" in source, source
        assert "await" in source

    def test_slow_ticks_do_not_pile_up(self):
        """A 5s timer drives a request that can take 20s."""
        import inspect

        from client.ui.diagnostics_panel import DiagnosticsPanel

        slot = DiagnosticsPanel.refresh
        source = inspect.getsource(getattr(slot, "__wrapped__", slot))
        assert "claim_slot" in source, (
            "without the guard a slow server queues a refresh per tick")


class TestTheStatusBarSaysWhichServerVersion:
    """Read once at connect, it went stale when the server changed.

    Not a rare case: updating the server is something this client does
    itself, from the System tab, and the client stays up while the
    container restarts. On the bench the bar read "LabLink Server v2.1.3"
    against a server answering 2.4.1 on both /api and /api/system/version.
    """

    def window(self, qapp):
        from PyQt6.QtWidgets import QLabel

        from client.ui.main_window import MainWindow

        win = type("W", (), {})()
        win.server_info_label = QLabel("")
        win._show_server_identity = MainWindow._show_server_identity.__get__(win)
        return win

    def test_the_name_and_version_are_shown(self, qapp):
        win = self.window(qapp)
        win._show_server_identity({"name": "LabLink Server", "version": "2.4.1"})
        assert win.server_info_label.text() == "LabLink Server v2.4.1"

    def test_a_later_reading_replaces_an_earlier_one(self, qapp):
        """The bug, in one assertion: the label must follow the server."""
        win = self.window(qapp)
        win._show_server_identity({"name": "LabLink Server", "version": "2.1.3"})
        win._show_server_identity({"name": "LabLink Server", "version": "2.4.1"})
        assert win.server_info_label.text() == "LabLink Server v2.4.1"

    def test_a_server_that_gives_no_version_is_still_named(self, qapp):
        win = self.window(qapp)
        win._show_server_identity({"name": "LabLink Server"})
        assert win.server_info_label.text() == "LabLink Server"

    def test_an_empty_answer_does_not_show_the_word_none(self, qapp):
        win = self.window(qapp)
        win._show_server_identity(None)
        assert "None" not in win.server_info_label.text()

    def test_the_version_is_re_read_off_the_gui_thread(self):
        """A status label is not worth freezing the window for."""
        import inspect

        from client.ui.main_window import MainWindow

        slot = MainWindow._refresh_server_identity
        underlying = getattr(slot, "__wrapped__", slot)
        assert inspect.iscoroutinefunction(underlying)
        assert "call_blocking" in inspect.getsource(underlying)

    def test_the_periodic_tick_re_reads_it(self):
        import inspect

        from client.ui.main_window import MainWindow

        source = inspect.getsource(MainWindow.periodic_refresh)
        assert "_refresh_server_identity" in source, (
            "nothing re-reads the version, so it stays as it was at connect")
