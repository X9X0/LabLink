"""A panel whose polls keep failing slows down instead of asking every tick.

An instrument answers one caller at a time and the server does not cancel a
request whose client has given up. At the panel's 2 s cadence, a command that
costs a ten-second VISA timeout means the client adds backlog five times
faster than the server can drain it: on the bench the DS1054Z's queue reached
205 s and every request, including selecting the instrument in the list,
looked like a hang. Backing off is the client's half of that fix; the server's
half is BaseEquipment.MAX_QUEUED_EXCHANGES. See docs/HANDOFF_SCOPE_LAG.md.

The distinction being pinned here: backing off is not stopping. A transient
fault must keep polling -- slower -- so a panel recovers by itself when the
instrument starts answering again. Only a permanent refusal (404, 501) stops
the timer, which tests/gui/test_readings_stop_on_404.py covers.
"""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication

    from client.ui.instruments import InstrumentPanel, PowerSupplyPanel

    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not GUI_AVAILABLE, reason="PyQt6 is required for control panel tests"
)


class _Response:
    def __init__(self, status_code):
        self.status_code = status_code


def _http_error(status_code):
    error = Exception(f"{status_code} from server")
    error.response = _Response(status_code)
    return error


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp):
    made = PowerSupplyPanel()
    made.set_interval_ms(2000, remember=False)
    yield made
    made.stop()
    made.deleteLater()


class TestTheIntervalGrows:
    def test_each_consecutive_failure_doubles_it(self, panel):
        panel.poll_timer.start(panel.interval_ms())
        seen = []
        for _ in range(4):
            panel._handle_poll_error(TimeoutError("read timed out"))
            seen.append(panel.poll_timer.interval())
        assert seen == [4000, 8000, 16000, 30000]

    def test_it_stops_at_the_cap(self, panel):
        panel.poll_timer.start(panel.interval_ms())
        for _ in range(20):
            panel._handle_poll_error(TimeoutError("read timed out"))
        assert panel.poll_timer.interval() == panel.POLL_BACKOFF_CAP_MS

    def test_a_503_from_a_busy_instrument_backs_off(self, panel):
        """What the server now answers once an instrument's queue is full."""
        panel.poll_timer.start(panel.interval_ms())
        panel._handle_poll_error(_http_error(503))
        assert panel.poll_timer.interval() == 4000

    def test_the_timer_is_still_running(self, panel):
        """Backing off is not stopping: the panel must recover on its own."""
        panel.poll_timer.start(panel.interval_ms())
        for _ in range(5):
            panel._handle_poll_error(TimeoutError("read timed out"))
        assert panel.poll_timer.isActive()


class TestTheIntervalComesBack:
    def test_a_good_poll_restores_the_cadence(self, panel):
        panel.poll_timer.start(panel.interval_ms())
        for _ in range(3):
            panel._handle_poll_error(TimeoutError("read timed out"))
        assert panel.poll_timer.interval() > 2000

        panel._poll_succeeded()
        assert panel.poll_timer.interval() == 2000
        assert panel._poll_failures == 0

    def test_the_operators_cadence_outranks_a_back_off(self, panel):
        """Moving the refresh control is an instruction, not a suggestion."""
        panel.poll_timer.start(panel.interval_ms())
        for _ in range(3):
            panel._handle_poll_error(TimeoutError("read timed out"))
        panel.set_interval_ms(1000, remember=False)
        assert panel.poll_timer.interval() == 1000
        assert panel._poll_failures == 0

    def test_the_users_interval_is_never_overwritten(self, panel):
        """The back-off moves the timer, not the remembered setting."""
        panel.poll_timer.start(panel.interval_ms())
        for _ in range(3):
            panel._handle_poll_error(TimeoutError("read timed out"))
        assert panel.interval_ms() == 2000


class TestWhatDoesNotBackOff:
    def test_a_permanent_refusal_stops_instead(self, panel):
        """404 and 501 already stop the timer; they must not merely slow it."""
        panel.poll_timer.start(panel.interval_ms())
        panel._handle_poll_error(_http_error(501))
        assert not panel.poll_timer.isActive()
        assert panel._poll_failures == 0

    def test_a_panel_with_no_timer_running_does_not_crash(self, panel):
        """A failure can land after the panel was hidden and stopped."""
        panel.stop()
        panel._handle_poll_error(TimeoutError("read timed out"))
        assert not panel.poll_timer.isActive()


class TestTheCapIsDeclaredOnce:
    def test_every_panel_shares_the_cap(self, qapp):
        assert InstrumentPanel.POLL_BACKOFF_CAP_MS == 30_000
