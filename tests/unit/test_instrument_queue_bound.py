"""An instrument's command queue is bounded; it does not grow without limit.

An instrument answers one caller at a time, so a command it never answers
turns every later request into a queue entry. A client that gives up after ten
seconds does not cancel what it asked for, so the server keeps draining the
backlog and the next request waits behind all of it. On the bench a single
unanswered ``:MEAS:VAV?`` every two seconds grew the DS1054Z's queue to 205 s
and made every request -- including ``/status`` while merely selecting the
instrument in the list -- look like a hang. See docs/HANDOFF_SCOPE_LAG.md.
"""

import asyncio
import logging
from unittest.mock import MagicMock

import pytest

from server.equipment.base import BaseEquipment, InstrumentBusy


class _Instrument(BaseEquipment):
    async def get_info(self):  # pragma: no cover
        return None

    async def get_status(self):  # pragma: no cover
        return None

    async def execute_command(self, command, parameters):  # pragma: no cover
        return None


def _connected(limit=4):
    equipment = _Instrument(MagicMock(), "USB0::0x1AB1::0x04CE::DS1ZA1::INSTR")
    equipment.instrument = MagicMock()
    equipment.instrument.session = 1
    equipment.connected = True
    equipment.MAX_QUEUED_EXCHANGES = limit
    return equipment


async def _hold(equipment, release: asyncio.Event):
    """Occupy the instrument's I/O lock until `release` is set."""
    holding = asyncio.Event()

    async def holder():
        async with equipment._io_lock:
            holding.set()
            await release.wait()

    task = asyncio.create_task(holder())
    await holding.wait()
    return task


@pytest.mark.unit
def test_requests_past_the_limit_are_refused_instead_of_queued(caplog):
    """The queue stops growing at the limit, and the refusal names the count."""
    equipment = _connected(limit=4)
    equipment.instrument.query = lambda cmd: "1"

    async def main():
        release = asyncio.Event()
        holder = await _hold(equipment, release)

        # Four callers queue up behind it, which is the whole allowance.
        queued = [asyncio.create_task(equipment._query(f"Q{i}?")) for i in range(4)]
        for _ in range(4):
            await asyncio.sleep(0)
        assert equipment._io_lock.waiting == 4

        # The fifth is told now rather than in three minutes.
        with pytest.raises(InstrumentBusy):
            await equipment._query(":TRIG:STAT?")

        release.set()
        await holder
        await asyncio.gather(*queued)

    with caplog.at_level(logging.WARNING, logger="server.equipment.base"):
        asyncio.run(main())
    assert any("refusing ':TRIG:STAT?'" in r.message and "4 requests" in r.message
               for r in caplog.records)


@pytest.mark.unit
def test_the_queue_reopens_once_it_drains():
    """A refusal is a statement about right now, not a latch."""
    equipment = _connected(limit=2)
    equipment.instrument.query = lambda cmd: "ok"

    async def main():
        release = asyncio.Event()
        holder = await _hold(equipment, release)
        queued = [asyncio.create_task(equipment._query(f"Q{i}?")) for i in range(2)]
        for _ in range(3):
            await asyncio.sleep(0)
        with pytest.raises(InstrumentBusy):
            await equipment._query("REFUSED?")
        release.set()
        await holder
        await asyncio.gather(*queued)
        # Drained: the next caller is served normally.
        assert await equipment._query("*IDN?") == "ok"

    asyncio.run(main())


@pytest.mark.unit
def test_a_nested_exchange_is_never_refused():
    """Reconnection runs _query inside _query and must not be turned away.

    _query -> _ensure_connected -> connect -> _query all run in the one task
    that already holds the I/O lock. Refusing the inner call would break the
    reconnect path exactly when the instrument is in trouble.
    """
    equipment = _connected(limit=0)          # refuse everything that can be refused
    equipment.instrument.query = lambda cmd: "RIGOL,DS1054Z,1,00.04.03"

    async def main():
        async with equipment._io_lock:
            # Holding the lock, in this task: this is the nested case.
            assert await equipment._query("*IDN?") == "RIGOL,DS1054Z,1,00.04.03"

    asyncio.run(main())


@pytest.mark.unit
def test_an_idle_instrument_refuses_nothing():
    """With no queue there is nothing to protect against."""
    equipment = _connected(limit=1)
    equipment.instrument.query = lambda cmd: "1"

    async def main():
        for _ in range(5):
            assert await equipment._query(":TRIG:STAT?") == "1"

    asyncio.run(main())


@pytest.mark.unit
def test_the_binary_read_is_bounded_too():
    """The trace fetch is the most expensive thing on the queue."""
    equipment = _connected(limit=1)
    equipment.instrument.query_binary_values = lambda cmd, datatype="B": [1, 2, 3]
    equipment.instrument.query = lambda cmd: "1"

    async def main():
        release = asyncio.Event()
        holder = await _hold(equipment, release)
        queued = asyncio.create_task(equipment._query("Q?"))
        for _ in range(2):
            await asyncio.sleep(0)
        with pytest.raises(InstrumentBusy):
            await equipment._query_binary(":WAV:DATA?")
        release.set()
        await holder
        await queued

    asyncio.run(main())
