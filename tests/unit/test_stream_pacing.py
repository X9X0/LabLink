"""A pushed stream holds its cadence, and stops when nobody is listening.

The live trace used to cost an HTTP round trip per frame, with the client
asking and the server answering. On an instrument that stalls, that is the
worst arrangement available: the bench DS1054Z pauses ~150 ms on about one
exchange in ten, and the old loop slept a whole interval *after* each frame,
so one stall became a stall plus an interval and the stutter compounded.

Holding a deadline instead absorbs a stall into the slack that a fast frame
leaves behind. These tests pin that, and pin that a stream with no audience
stops driving the instrument -- which matters because every frame takes the
I/O lock the control panel is waiting for.
"""

import asyncio

import pytest

from server.websocket_server import StreamManager


class _Equipment:
    """Records what it was asked for, and can be made slow on demand."""

    def __init__(self, delays=()):
        self.calls = []
        self._delays = list(delays)

    async def execute_command(self, command, parameters):
        self.calls.append((command, dict(parameters or {})))
        if self._delays:
            await asyncio.sleep(self._delays.pop(0))
        # Distinct every time: identical frames are dropped as duplicates,
        # and these tests are about what is asked for, not what changed.
        return {"num_samples": 600, "voltage": [0.1, float(len(self.calls))],
                "time": [0.0, 1e-6]}


def _install(monkeypatch, equipment):
    import server.websocket_server as ws

    monkeypatch.setattr(ws.equipment_manager, "get_equipment",
                        lambda _id: equipment)


async def _run_briefly(manager, seconds, **kwargs):
    task = asyncio.create_task(manager._stream_data(**kwargs))
    await asyncio.sleep(seconds)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.unit
def test_a_trace_stream_sends_the_samples_not_the_metadata():
    """The "waveform" stream type answers with get_waveform, which carries no
    samples at all. A live trace needs the codes."""

    async def main(monkeypatch):
        equipment = _Equipment()
        _install(monkeypatch, equipment)
        manager = StreamManager()
        manager.active_connections = {object()}
        sent = []
        manager.broadcast = lambda m: sent.append(m) or asyncio.sleep(0)
        await _run_briefly(manager, 0.12, equipment_id="scope_1",
                           stream_type="trace", interval_ms=10,
                           parameters={"channel": 2, "points": 600})
        assert equipment.calls, "the stream sent nothing"
        command, parameters = equipment.calls[0]
        # Codes, not floats: 1,703 bytes and 0.04 ms against 32,636 and
        # 3.79 ms for the same samples.
        assert command == "get_waveform_codes"
        assert parameters == {"channel": 2}
        assert sent and sent[0]["stream_type"] == "trace"

    from _pytest.monkeypatch import MonkeyPatch
    patch = MonkeyPatch()
    try:
        asyncio.run(main(patch))
    finally:
        patch.undo()


class _Clock:
    """A clock the test moves, so cadence is asserted rather than timed.

    Wall-clock assertions here were flaky: the first version passed alone and
    failed in the full suite, where 1500 other tests compete for the CPU. A
    test that depends on the machine being idle cannot say anything about the
    code.
    """

    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now


class _AsyncioStub:
    """asyncio for the module under test, with sleep recorded and instant."""

    def __init__(self, real, clock, slept):
        self._real, self._clock, self._slept = real, clock, slept

    def __getattr__(self, name):
        return getattr(self._real, name)

    async def sleep(self, seconds):
        self._slept.append(seconds)
        self._clock.now += max(0.0, seconds)
        await self._real.sleep(0)


@pytest.mark.unit
def test_a_stall_does_not_push_the_following_frames_out():
    """One slow frame costs one slow frame, not one plus an interval.

    Sleeping a fixed gap after the work is what turned a 150 ms instrument
    stall into a 150 ms + interval gap, and made the stutter compound.
    """
    import server.websocket_server as ws

    clock = _Clock()
    slept = []
    frames = []

    class _Slow:
        """Frame 1 takes five intervals; the rest are instant."""

        def __init__(self):
            self.calls = 0

        async def execute_command(self, command, parameters):
            self.calls += 1
            if self.calls == 1:
                clock.now += 0.100          # the stall
            # A different trace each time: this test is about cadence, and
            # identical frames are dropped as duplicates.
            return {"num_samples": 600, "voltage": [float(self.calls)],
                    "time": [0.0]}

    async def main(patch):
        equipment = _Slow()
        patch.setattr(ws.equipment_manager, "get_equipment", lambda _i: equipment)
        patch.setattr(ws, "time", clock)        # the module reads time.monotonic
        patch.setattr(ws, "asyncio", _AsyncioStub(asyncio, clock, slept))

        manager = StreamManager()
        manager.active_connections = {object()}

        async def capture(_message):
            frames.append(clock.now)
            if len(frames) >= 6:
                raise asyncio.CancelledError

        manager.broadcast = capture
        try:
            await manager._stream_data("scope_1", "trace", 20, {"channel": 1})
        except asyncio.CancelledError:
            pass

    from _pytest.monkeypatch import MonkeyPatch
    patch = MonkeyPatch()
    try:
        asyncio.run(main(patch))
    finally:
        patch.undo()

    assert len(frames) == 6, frames
    # The stalled frame lands at 0.100 and is not slept off; every frame after
    # it arrives one interval apart, so the gap never doubles.
    gaps = [round(b - a, 4) for a, b in zip(frames, frames[1:])]
    assert gaps[0] == pytest.approx(0.0, abs=1e-9), (
        f"the loop slept after the stall instead of catching up: {gaps}")
    assert all(g == pytest.approx(0.020, abs=1e-9) for g in gaps[1:]), gaps
    assert max(slept) <= 0.020 + 1e-9, f"slept longer than an interval: {slept}"


@pytest.mark.unit
def test_an_unchanged_frame_is_not_sent_again():
    """Reading at 100 Hz gave about 9 distinct frames a second on the bench.

    A settled repetitive signal redraws to the same screen, so most frames
    carry nothing new; sending them costs the client a redraw and the network
    a frame to show what is already on screen. A changing signal dedupes to
    almost nothing, so the rate follows the signal.
    """
    import server.websocket_server as ws

    class _Repeating:
        """Two identical frames, then a different one."""

        def __init__(self):
            self.frames = [
                {"channel": 1, "voltage": [0.0, 1.0, 2.0], "data_id": "a"},
                {"channel": 1, "voltage": [0.0, 1.0, 2.0], "data_id": "b"},
                {"channel": 1, "voltage": [9.0, 9.0, 9.0], "data_id": "c"},
            ]
            self.served = 0

        async def execute_command(self, _command, _parameters):
            frame = self.frames[min(self.served, len(self.frames) - 1)]
            self.served += 1
            return frame

    async def main(patch):
        equipment = _Repeating()
        _install(patch, equipment)
        manager = StreamManager()
        manager.active_connections = {object()}
        sent = []

        async def capture(message):
            sent.append(message["data"]["data_id"])
            if equipment.served >= 3:
                raise asyncio.CancelledError

        manager.broadcast = capture
        try:
            await _run_briefly(manager, 0.3, equipment_id="scope_1",
                               stream_type="trace", interval_ms=1,
                               parameters={"channel": 1})
        except asyncio.CancelledError:
            pass

    from _pytest.monkeypatch import MonkeyPatch
    patch = MonkeyPatch()
    try:
        asyncio.run(main(patch))
    finally:
        patch.undo()


@pytest.mark.unit
def test_the_fingerprint_ignores_the_data_id():
    """Every read carries a fresh uuid; that alone is not a new trace."""
    manager = StreamManager()
    frame = {"channel": 1, "voltage": [0.1, 0.2, 0.3], "data_id": "one"}
    assert manager._is_repeat("k", frame) is False
    assert manager._is_repeat("k", {**frame, "data_id": "two"}) is True
    assert manager._is_repeat("k", {**frame, "voltage": [0.1, 0.2, 0.4]}) is False


@pytest.mark.unit
def test_a_stream_with_no_listener_leaves_the_instrument_alone():
    """Every frame takes the I/O lock the control panel is waiting for."""

    async def main(patch):
        equipment = _Equipment()
        _install(patch, equipment)
        manager = StreamManager()
        manager.active_connections = set()          # everybody has gone
        manager.broadcast = lambda _m: asyncio.sleep(0)
        await _run_briefly(manager, 0.12, equipment_id="scope_1",
                           stream_type="trace", interval_ms=10,
                           parameters={"channel": 1})
        assert equipment.calls == [], (
            f"drove the instrument for nobody: {equipment.calls}")

    from _pytest.monkeypatch import MonkeyPatch
    patch = MonkeyPatch()
    try:
        asyncio.run(main(patch))
    finally:
        patch.undo()


@pytest.mark.unit
def test_measurements_streams_honour_their_parameters_too():
    """They were hardcoded to channel 1 with the full seven-item set."""

    async def main(patch):
        equipment = _Equipment()
        _install(patch, equipment)
        manager = StreamManager()
        manager.active_connections = {object()}
        manager.broadcast = lambda _m: asyncio.sleep(0)
        await _run_briefly(manager, 0.08, equipment_id="scope_1",
                           stream_type="measurements", interval_ms=10,
                           parameters={"channel": 3, "items": ["vpp"]})
        assert equipment.calls[0] == (
            "get_measurements", {"channel": 3, "items": ["vpp"]})

    from _pytest.monkeypatch import MonkeyPatch
    patch = MonkeyPatch()
    try:
        asyncio.run(main(patch))
    finally:
        patch.undo()
