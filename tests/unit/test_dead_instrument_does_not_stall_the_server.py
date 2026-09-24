"""One unreachable instrument must not take the whole server down.

Reported from the lab bench: "what happened on the lab server, it just
stopped streaming?" The API was not slow, it was gone -- two requests,
10s and 21s, both returned nothing -- and the container had gone
``unhealthy`` while still ``Up 24 hours``.

A scope had been powered off. Every poll of it tried a VXI-11 connect
that took 2.1s to fail::

    RPCError: can't connect to server
    Failed to connect to TCPIP0::192.168.91.37::inst0::INSTR
    Invalid instrument session detected, reconnecting...

84 attempts in three minutes, one every 2.1 seconds, which is the loop
occupied essentially all of the time. In those same three minutes the
log held 252 lines and every one of them was about that scope: the two
supplies on the same server were never polled at all. They had not
failed, they were starved.

The cause was one synchronous line in an async method::

    self.instrument = self._open_resource()

PyVISA is blocking, and every other exchange in this class already goes
through ``run_in_executor`` -- ``_write``, ``_query``, ``_query_binary``.
The open, the slowest call of the lot, was the one that did not.

Two things are asserted here, because fixing either alone leaves the
bench exposed: the open does not block the event loop, and a failing
instrument is not retried every two seconds forever.
"""

import asyncio
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.equipment import base as base_module
from server.equipment.base import RECONNECT_BACKOFF_SEC, BaseEquipment


class DeadInstrument(BaseEquipment):
    """An instrument whose open blocks and then fails, as a dead one does.

    ``open_cost`` is the wall-clock the blocking call burns. The real one
    was 2.1s; a fraction of that is enough to show the loop stalling and
    keeps the suite quick.
    """

    def __init__(self, open_cost=0.25, fail=True):
        super().__init__(None, "TCPIP0::192.168.91.37::inst0::INSTR")
        self.open_cost = open_cost
        self.fail = fail
        self.opens = 0

    def _refresh_resource_manager(self):
        pass                                    # not what is under test

    def _open_resource(self):
        self.opens += 1
        time.sleep(self.open_cost)              # PyVISA is synchronous
        if self.fail:
            raise OSError("can't connect to server")
        return _LiveSession()

    async def get_info(self):
        return None

    async def get_status(self):
        return None

    async def execute_command(self, command, parameters):
        return None


class _LiveSession:
    """Enough of a PyVISA resource to look valid."""

    session = 1
    timeout = 0

    def close(self):
        self.session = None


async def heartbeat(stop, ticks, interval=0.01):
    """A stand-in for everything else the server owes its users.

    The API, the WebSocket stream and every other instrument's poll are
    all just coroutines wanting a turn. If one blocking call holds the
    loop, none of them get one -- so counting turns measures the outage
    directly.
    """
    while not stop.is_set():
        ticks.append(asyncio.get_event_loop().time())
        await asyncio.sleep(interval)


class TestTheOpenDoesNotBlockTheEventLoop:
    """The headline: the server keeps serving while an open hangs."""

    @pytest.mark.asyncio
    async def test_other_work_still_runs_during_a_failing_connect(self):
        dead = DeadInstrument(open_cost=0.25)
        stop = asyncio.Event()
        ticks = []
        beating = asyncio.ensure_future(heartbeat(stop, ticks))
        await asyncio.sleep(0.02)                  # let it get going
        before = len(ticks)

        with pytest.raises(OSError):
            await dead.connect()

        stop.set()
        await beating
        during = len(ticks) - before

        # 0.25s of blocking open against a 10ms heartbeat: about 25 turns
        # if the loop is free, 0 or 1 if it is not.
        assert during >= 10, (
            f"the loop got {during} turns while one instrument's open was "
            f"in progress -- a blocked open is not one instrument's "
            f"problem, it is every request the server owes anyone")

    @pytest.mark.asyncio
    async def test_a_successful_open_is_off_the_loop_too(self):
        """Not only the failing path: a slow open stalls just as hard."""
        slow = DeadInstrument(open_cost=0.2, fail=False)
        slow._query = _answers("RIGOL,DS1054Z")
        stop = asyncio.Event()
        ticks = []
        beating = asyncio.ensure_future(heartbeat(stop, ticks))
        await asyncio.sleep(0.02)
        before = len(ticks)

        await slow.connect()

        stop.set()
        await beating
        assert len(ticks) - before >= 8, "a successful open blocked the loop"

    @pytest.mark.asyncio
    async def test_the_open_still_happens(self):
        """Offloading it must not quietly skip it."""
        dead = DeadInstrument(open_cost=0.01)
        with pytest.raises(OSError):
            await dead.connect()
        assert dead.opens == 1


class TestAFailingInstrumentIsLeftAlone:
    """2.1s per attempt is affordable once a minute and not every 2s."""

    @pytest.mark.asyncio
    async def test_a_second_attempt_is_refused_at_once(self):
        dead = DeadInstrument(open_cost=0.05)
        with pytest.raises(OSError):
            await dead.connect()
        assert dead.opens == 1

        started = time.monotonic()
        with pytest.raises(ConnectionError):
            await dead._ensure_connected()
        took = time.monotonic() - started

        assert dead.opens == 1, (
            "asked the dead instrument again inside the backoff window; "
            "this is the 84-attempts-in-three-minutes loop")
        assert took < 0.02, (
            f"refusing took {took:.3f}s -- the point of backing off is that "
            f"the poller gets its answer immediately and the loop stays free")

    @pytest.mark.asyncio
    async def test_the_wait_grows_with_repeated_failure(self):
        dead = DeadInstrument(open_cost=0.01)
        waits = []
        loop = asyncio.get_event_loop()
        for _ in range(4):
            dead._retry_after = 0.0             # pretend the wait elapsed
            with pytest.raises(OSError):
                await dead._ensure_connected()
            waits.append(round(dead._retry_after - loop.time(), 1))

        assert waits == sorted(waits), f"backoff did not grow: {waits}"
        assert waits[-1] > waits[0], f"backoff never grew at all: {waits}"

    @pytest.mark.asyncio
    async def test_the_wait_is_capped(self):
        """It has to keep trying; an instrument does come back."""
        dead = DeadInstrument(open_cost=0.0)
        loop = asyncio.get_event_loop()
        for _ in range(len(RECONNECT_BACKOFF_SEC) + 5):
            dead._retry_after = 0.0
            with pytest.raises(OSError):
                await dead._ensure_connected()

        assert dead._retry_after - loop.time() <= max(RECONNECT_BACKOFF_SEC) + 0.1

    @pytest.mark.asyncio
    async def test_it_tries_again_once_the_wait_has_passed(self):
        dead = DeadInstrument(open_cost=0.01)
        with pytest.raises(OSError):
            await dead.connect()
        dead._retry_after = 0.0                 # the wait elapsed

        with pytest.raises(OSError):
            await dead._ensure_connected()
        assert dead.opens == 2, "backed off and never came back"


class TestComingBack:
    @pytest.mark.asyncio
    async def test_an_instrument_that_returns_is_reconnected(self):
        """What happened on the bench: the scope was plugged back in."""
        supply = DeadInstrument(open_cost=0.01)
        with pytest.raises(OSError):
            await supply.connect()

        supply.fail = False                     # plugged back in
        supply._query = _answers("RIGOL,DS1054Z")
        supply._retry_after = 0.0
        await supply._ensure_connected()

        assert supply.connected is True
        assert supply._failed_connects == 0, "still counting a healed outage"
        assert supply._retry_after == 0.0

    @pytest.mark.asyncio
    async def test_an_operator_pressing_connect_never_waits_out_a_backoff(self):
        """The automatic path backs off. A person asking does not."""
        dead = DeadInstrument(open_cost=0.01)
        with pytest.raises(OSError):
            await dead.connect()
        assert dead._retry_after > 0, "no backoff was set to test against"

        dead.fail = False
        dead._query = _answers("RIGOL,DS1054Z")
        await dead.connect()                    # no wait, no refusal

        assert dead.connected is True
        assert dead.opens == 2

    @pytest.mark.asyncio
    async def test_disconnecting_clears_the_backoff(self):
        dead = DeadInstrument(open_cost=0.01)
        with pytest.raises(OSError):
            await dead.connect()

        await dead.disconnect()

        assert dead._retry_after == 0.0
        assert dead._failed_connects == 0


class TestTheOtherInstrumentsKeepBeingServed:
    """The part that made this a server outage rather than a dead scope."""

    @pytest.mark.asyncio
    async def test_a_healthy_instrument_is_not_starved_by_a_dead_one(self):
        """Counted across the outage, not after it.

        Polling once either side of the dead instrument's open proves
        nothing -- the poll simply runs before or after the block and
        looks fine. What the bench saw was three minutes in which the
        two healthy supplies were polled zero times, so the measurement
        has to be how many polls land *while* the open is in flight.
        """
        dead = DeadInstrument(open_cost=0.25)
        healthy = DeadInstrument(open_cost=0.0, fail=False)
        healthy._query = _answers("B&K,1685B")

        stop = asyncio.Event()
        polls = []

        async def poll_the_healthy_one():
            while not stop.is_set():
                await healthy.connect()
                polls.append(healthy.connected)
                await asyncio.sleep(0.01)

        polling = asyncio.ensure_future(poll_the_healthy_one())
        await asyncio.sleep(0.02)                  # let it get going
        before = len(polls)

        with pytest.raises(OSError):
            await dead.connect()

        stop.set()
        await polling
        during = len(polls) - before

        assert during >= 8, (
            f"the supply on the same server was polled {during} times "
            f"while the scope's open was in flight; on the bench it was 0 "
            f"for three minutes and the operator saw the server stop")
        assert all(polls), "a healthy instrument failed to connect"


def _answers(idn):
    async def query(command):
        return idn
    return query
