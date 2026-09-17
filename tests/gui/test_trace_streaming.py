"""The scope panel takes pushed trace frames, and falls back when it cannot.

Asking for each frame over HTTP costs a round trip the instrument does not
need and leaves the client waiting through every stall the scope takes --
~150 ms on about one exchange in ten on the bench DS1054Z. The server can
hold a cadence against the instrument and push frames; the panel draws what
arrives.

What matters most here is the falling back. A stream carries one channel, an
older server does not know the "trace" type, and a client without a websocket
manager cannot stream at all. Each of those has to leave a working panel
rather than a blank one, which is exactly the kind of failure that looks like
"the trace stopped" and costs a day.
"""

import asyncio
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication

    from client.models.equipment import ConnectionStatus
    from client.ui.instruments import OscilloscopePanel

    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(not GUI_AVAILABLE, reason="PyQt6 is required")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _Equipment:
    equipment_id = "scope_cee816af"
    name = "DS1054Z"
    manufacturer = "RIGOL"
    model = "DS1054Z"
    resource_string = "TCPIP0::192.168.91.37::inst0::INSTR"
    connection_status = ConnectionStatus.CONNECTED


class _Client:
    """A client that can stream, recording what it was asked to do."""

    def __init__(self, ws=True):
        self.ws_manager = object() if ws else None
        self.started = []
        self.stopped = []
        self.handlers = []

    def register_stream_data_handler(self, handler):
        self.handlers.append(handler)

    def unregister_stream_data_handler(self, handler):
        if handler in self.handlers:
            self.handlers.remove(handler)

    async def start_equipment_stream(self, equipment_id, stream_type,
                                     interval_ms, parameters=None):
        self.started.append((equipment_id, stream_type, interval_ms,
                             dict(parameters or {})))

    async def stop_equipment_stream(self, equipment_id, stream_type):
        self.stopped.append((equipment_id, stream_type))


@pytest.fixture
def loop():
    """A real event loop, because the panel schedules its stream calls.

    The panel uses asyncio.ensure_future, as the rest of the client does; in
    the running app qasync provides the loop. Without one the coroutine is
    created and never runs, so a test would see no stream and no error --
    which is the same thing the operator would see.
    """
    made = asyncio.new_event_loop()
    asyncio.set_event_loop(made)
    yield made
    made.close()
    asyncio.set_event_loop(None)


def pump(loop, times=3):
    """Run whatever the panel just scheduled."""
    for _ in range(times):
        loop.run_until_complete(asyncio.sleep(0))


@pytest.fixture
def panel(qapp, loop):
    made = OscilloscopePanel()
    made.num_channels = 4
    yield made
    made.stop()
    made.deleteLater()


def _bind(panel, client, channels=(1,)):
    panel.equipment = _Equipment()
    panel.client = client
    for n in range(4):
        panel.channel_rows[n]["enable"].blockSignals(True)
        panel.channel_rows[n]["enable"].setChecked((n + 1) in channels)
        panel.channel_rows[n]["enable"].blockSignals(False)


class TestItStreamsWhenItCan:
    def test_one_channel_streams_and_the_timer_stays_off(self, panel, loop):
        client = _Client()
        _bind(panel, client, channels=(1,))
        assert panel._start_trace_stream() is True
        assert panel._trace_streaming
        pump(loop)

        equipment_id, stream_type, interval, parameters = client.started[0]
        assert equipment_id == "scope_cee816af"
        assert stream_type == "trace"
        assert parameters["channel"] == 1
        assert parameters["points"] == panel.TRACE_POINTS

    def test_the_stream_names_the_channel_actually_shown(self, panel, loop):
        client = _Client()
        _bind(panel, client, channels=(3,))
        assert panel._start_trace_stream() is True
        pump(loop)
        assert client.started[0][3]["channel"] == 3

    def test_a_pushed_frame_is_drawn(self, panel):
        client = _Client()
        _bind(panel, client, channels=(1,))
        panel._start_trace_stream()
        panel._on_stream_frame({
            "type": "stream_data",
            "equipment_id": "scope_cee816af",
            "stream_type": "trace",
            "data": {"channel": 1, "voltage": [0.0, 0.5, 1.0],
                     "time": [0.0, 1e-6, 2e-6], "num_samples": 3},
        })
        assert panel._last_trace[1]["num_samples"] == 3


class TestItFallsBackRatherThanGoingBlank:
    def test_several_channels_poll_instead(self, panel):
        """A stream carries one source, and switching source costs ~100 ms."""
        client = _Client()
        _bind(panel, client, channels=(1, 2, 3))
        assert panel._start_trace_stream() is False
        assert not panel._trace_streaming
        assert client.started == []

    def test_a_client_without_a_websocket_polls(self, panel):
        client = _Client(ws=False)
        _bind(panel, client, channels=(1,))
        assert panel._start_trace_stream() is False
        assert not panel._trace_streaming

    def test_a_server_that_refuses_the_stream_falls_back(self, panel):
        """An older server does not know the "trace" type."""
        client = _Client()

        async def refuse(*_a, **_k):
            raise RuntimeError("unknown stream type: trace")

        client.start_equipment_stream = refuse
        _bind(panel, client, channels=(1,))
        # The failure surfaces when the coroutine runs, so the panel must not
        # be left believing it is streaming.
        panel._start_trace_stream()
        panel._stop_trace_stream()
        assert not panel._trace_streaming


class TestFramesForOtherInstruments:
    def test_a_frame_for_another_instrument_is_ignored(self, panel):
        client = _Client()
        _bind(panel, client, channels=(1,))
        panel._start_trace_stream()
        panel._on_stream_frame({
            "equipment_id": "ps_36509eb5", "stream_type": "trace",
            "data": {"channel": 1, "voltage": [9.9], "time": [0.0]},
        })
        assert 1 not in panel._last_trace

    def test_a_readings_frame_is_ignored(self, panel):
        """The equipment tab streams readings for the same instrument."""
        client = _Client()
        _bind(panel, client, channels=(1,))
        panel._start_trace_stream()
        panel._on_stream_frame({
            "equipment_id": "scope_cee816af", "stream_type": "readings",
            "data": {"channel": 1, "trigger_status": "TD"},
        })
        assert 1 not in panel._last_trace

    def test_a_malformed_frame_does_not_raise(self, panel):
        client = _Client()
        _bind(panel, client, channels=(1,))
        panel._start_trace_stream()
        for rubbish in (None, "text", {}, {"stream_type": "trace"},
                        {"equipment_id": "scope_cee816af",
                         "stream_type": "trace", "data": None}):
            panel._on_stream_frame(rubbish)
        assert 1 not in panel._last_trace


class TestStoppingReleasesTheStream:
    def test_stop_unsubscribes(self, panel):
        client = _Client()
        _bind(panel, client, channels=(1,))
        panel._start_trace_stream()
        assert client.handlers, "the handler was never registered"
        panel._stop_trace_stream()
        assert not panel._trace_streaming
        assert client.handlers == [], "the handler outlived the stream"
