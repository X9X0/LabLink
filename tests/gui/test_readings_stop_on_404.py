"""A stale equipment id must stop the readings timer, not be retried at 10 Hz.

The server generates a fresh equipment id each time it opens an instrument, so
a server restart -- which every update performs -- invalidates the id the
client is holding. The client kept polling it because the readings loop logged
every exception and carried on, which at 10 Hz is a 404 storm. That storm is
not merely noise: it saturates the loop and starves the connect task, so the
reconnect that would have fixed it appears to hang.

The distinction being pinned here is narrow. A 404 means the id is gone and
retrying cannot help. A timeout or a dropped socket is transient and must keep
polling, or a supply would stop reading over one slow serial reply.
"""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication


    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not GUI_AVAILABLE, reason="PyQt6 is required for control panel tests"
)

if GUI_AVAILABLE:
    from client.models.equipment import ConnectionStatus
    from client.ui.instruments import InstrumentPanel, PowerSupplyPanel


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


class TestWhatCountsAsGone:
    def test_a_404_is_gone(self, qapp):
        assert InstrumentPanel._equipment_is_gone(_http_error(404))

    @pytest.mark.parametrize("status", [500, 502, 503])
    def test_a_server_fault_is_not_gone(self, qapp, status):
        """The server is unwell, not missing the instrument -- keep reading."""
        assert not InstrumentPanel._equipment_is_gone(_http_error(status))

    def test_a_bare_exception_is_not_gone(self, qapp):
        """Timeouts and dropped sockets carry no response at all."""
        assert not InstrumentPanel._equipment_is_gone(TimeoutError("read timed out"))


class TestTheCachedStatusIsCorrected:
    def test_the_selection_stops_claiming_to_be_connected(self, qapp):
        """Otherwise the next tick starts the timer straight back up.

        ``_selected_is_connected`` reads the status the list was populated
        with, which after a server restart still says CONNECTED.
        """
        panel = PowerSupplyPanel()

        class _Equipment:
            equipment_id = "ps_36509eb5"
            connection_status = ConnectionStatus.CONNECTED

        panel.selected_equipment = _Equipment()
        assert panel._selected_is_connected()

        panel._mark_selection_disconnected()

        assert panel.selected_equipment.connection_status is ConnectionStatus.DISCONNECTED
        assert not panel._selected_is_connected()

    def test_no_selection_does_not_raise(self, qapp):
        panel = PowerSupplyPanel()
        panel.selected_equipment = None
        panel._mark_selection_disconnected()  # would raise if it assumed one


class TestAPermanentRefusalAlsoStops:
    """A scope has no volts and amps, and asking again will not change that.

    The Control tab drives power supplies. Selecting an oscilloscope made it
    poll `/readings` anyway, and the server answered 501 Not Implemented five
    times a second, forever. That is the same storm a stale id produced -- it
    saturates the loop and starves the connect task, so the *other* bench
    instruments then fail to connect, which is how it was noticed.

    The original fix stopped only on 404 and treated everything else as
    transient, on the reasoning that a 5xx means the server is unwell and a
    supply should read through it. That reasoning holds for 500 and 503 and
    not for 501, which is a permanent statement about this instrument.
    """

    @pytest.mark.parametrize("status", [501, 405])
    def test_a_permanent_refusal_is_recognised(self, qapp, status):
        assert InstrumentPanel._readings_unsupported(_http_error(status))

    @pytest.mark.parametrize("status", [500, 502, 503])
    def test_a_real_server_fault_is_not(self, qapp, status):
        """A supply must keep reading through a sick server."""
        assert not InstrumentPanel._readings_unsupported(_http_error(status))

    def test_a_missing_instrument_is_not_a_refusal(self, qapp):
        """404 has its own handling: gone, rather than incapable."""
        assert not InstrumentPanel._readings_unsupported(_http_error(404))
        assert InstrumentPanel._equipment_is_gone(_http_error(404))

    def test_a_refusal_is_not_treated_as_the_instrument_vanishing(self, qapp):
        """The scope is connected and fine -- it just has no setpoints.

        Marking it disconnected would be a lie, and would make the Equipment
        tab show a connected instrument as gone.
        """
        assert not InstrumentPanel._equipment_is_gone(_http_error(501))

    def test_the_readouts_are_blanked_rather_than_left_stale(self, qapp):
        panel = PowerSupplyPanel()
        panel.voltage_display.setText("12.00 V")
        panel.current_display.setText("1.500 A")

        panel._show_no_readings_for_this_instrument()

        assert panel.voltage_display.text() == "--"
        assert panel.current_display.text() == "--"
