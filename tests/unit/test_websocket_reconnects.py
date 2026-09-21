"""A dead WebSocket must reconnect, every time, not only the first.

The bench log showed the connection die at 22:05 and then this, every
thirty seconds for eight minutes, with no reconnect ever attempted:

    ERROR - Error sending message: keepalive ping timeout
    ERROR - Error in ping loop: keepalive ping timeout

Three faults, and they compound.

The ping loop logged its exception and went round again, so a ping that
could not be sent -- the clearest possible evidence the socket is gone --
left ``connected`` True and nothing watching.

The receive loop only reconnected from its ConnectionClosed branch. Any
other exception marked the connection down and stopped there, killing the
reader with nothing to replace it.

And the guard in connect() was ``not self._reconnect_task``, an attribute
nothing ever reset. After one reconnect it stayed truthy for the life of
the process and every later attempt was skipped -- "it updated the first
disconnect and reconnect cycle, but failed subsequently afterwards".
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from client.utils.websocket_manager import WebSocketManager


def manager():
    made = WebSocketManager.__new__(WebSocketManager)
    made.connected = True
    made.connecting = False
    made.errors = 0
    made._should_reconnect = True
    made._reconnect_task = None
    made._reconnect_delay = 0.01
    made._rejected_for_auth = False
    made.renew_token = None
    made._connection = None
    made._receive_task = None
    made._ping_task = None
    made._active_streams = {}
    made.reconnects = []

    async def fake_connect():
        made.reconnects.append(True)
        made.connected = True
        return True

    made.connect = fake_connect
    return made


class TestAFailedPingIsTreatedAsALostConnection:
    @pytest.mark.asyncio
    async def test_it_marks_the_connection_down(self):
        ws = manager()
        ws.send_ping = _raises("keepalive ping timeout")
        ws._reconnect_delay = 0.01

        await asyncio.wait_for(_ping_once(ws), timeout=2)

        assert ws.connected is False, (
            "connected stayed True, so nothing reconnected and the ping "
            "loop pinged a dead socket every 30s")

    @pytest.mark.asyncio
    async def test_it_starts_a_reconnect(self):
        ws = manager()
        ws.send_ping = _raises("keepalive ping timeout")
        await asyncio.wait_for(_ping_once(ws), timeout=2)
        await asyncio.sleep(0.1)
        assert ws.reconnects, "no reconnect was ever attempted"

    @pytest.mark.asyncio
    async def test_the_ping_loop_stops(self):
        """Not still looping against a socket known to be gone."""
        ws = manager()
        ws.send_ping = _raises("keepalive ping timeout")
        await asyncio.wait_for(_ping_once(ws), timeout=2)
        assert ws.connected is False


class TestReconnectionWorksMoreThanOnce:
    @pytest.mark.asyncio
    async def test_a_second_loss_reconnects_too(self):
        """The reported regression: first cycle fine, later ones not."""
        ws = manager()

        ws._note_connection_lost("first")
        await asyncio.sleep(0.1)
        first = len(ws.reconnects)
        assert first >= 1

        ws._note_connection_lost("second")
        await asyncio.sleep(0.1)

        assert len(ws.reconnects) > first, (
            "the second loss never reconnected; the guard was stuck on a "
            "task attribute nothing reset")

    @pytest.mark.asyncio
    async def test_the_task_handle_is_cleared_when_it_finishes(self):
        ws = manager()
        ws._note_connection_lost("gone")
        await asyncio.sleep(0.1)
        assert ws._reconnect_task is None

    @pytest.mark.asyncio
    async def test_only_one_reconnect_loop_runs_at_a_time(self):
        ws = manager()

        async def slow_connect():
            await asyncio.sleep(0.2)
            ws.reconnects.append(True)
            ws.connected = True
            return True

        ws.connect = slow_connect
        ws.connected = False
        ws._ensure_reconnecting()
        first = ws._reconnect_task
        ws._ensure_reconnecting()
        assert ws._reconnect_task is first, "two reconnect loops at once"
        await asyncio.sleep(0.4)


class TestDisconnectIsStillDeliberate:
    @pytest.mark.asyncio
    async def test_it_does_not_reconnect_after_a_requested_disconnect(self):
        ws = manager()
        ws._should_reconnect = False
        ws._note_connection_lost("we asked")
        await asyncio.sleep(0.1)
        assert ws.reconnects == []


def _raises(message):
    async def boom():
        raise RuntimeError(message)
    return boom


async def _ping_once(ws):
    """Run the ping loop with its sleep shortened to nothing."""
    real_sleep = asyncio.sleep

    async def no_wait(seconds, *a, **k):
        return await real_sleep(0)

    asyncio.sleep = no_wait
    try:
        await ws._ping_loop()
    finally:
        asyncio.sleep = real_sleep


class TestAStreamSurvivesBeingStartedOnADeadSocket:
    """A reconnect restored the connection and not the streams.

    On the bench the socket died at the moment a stream was being
    started:

        22:42:19  Could not start equipment stream: keepalive ping timeout
        22:42:19  WebSocket connection lost: ping failed
        22:42:24  WebSocket connected successfully

    and the readings stayed off. start_equipment_stream recorded the
    stream in _active_streams *after* sending, so a send that failed left
    nothing for _restart_streams to replay. That list should say what the
    operator asked for, not what happened to succeed.
    """

    @pytest.mark.asyncio
    async def test_a_failed_start_is_still_remembered(self):
        ws = manager()
        ws._send_message = _raises("keepalive ping timeout")

        with pytest.raises(Exception):
            await ws.start_equipment_stream("ps_1", "readings", 200)

        assert ws._active_streams, (
            "the stream was forgotten because the send failed, so the "
            "reconnect had nothing to restore")

    @pytest.mark.asyncio
    async def test_the_reconnect_replays_it(self):
        ws = manager()
        ws._send_message = _raises("keepalive ping timeout")
        with pytest.raises(Exception):
            await ws.start_equipment_stream("ps_1", "readings", 200)

        sent = []

        async def works(message):
            sent.append(message)

        ws._send_message = works
        await ws._restart_streams()

        assert any(m.get("equipment_id") == "ps_1" for m in sent), (
            f"restart sent {sent}")

    @pytest.mark.asyncio
    async def test_a_successful_start_is_recorded_once(self):
        ws = manager()
        sent = []

        async def works(message):
            sent.append(message)

        ws._send_message = works
        await ws.start_equipment_stream("ps_1", "readings", 200)

        assert len(ws._active_streams) == 1
        assert len(sent) == 1
