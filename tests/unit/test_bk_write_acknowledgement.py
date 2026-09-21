"""A write's acknowledgement must not be mistaken for the next read's answer.

Watched on the bench: a few times a minute, a readings poll failed with

    ERROR  Error getting device readings: Invalid GETD response:

-- note the empty value after the colon -- and every single one of them
followed a write:

    00:27:50  Slew rate limit applied ... requested 0.6, limited to 2.09
    00:27:50  ERROR  Error getting device readings: Invalid GETD response:

Every command in this protocol is answered, writes included. ``VOLT120``
is replied to with ``OK\\r`` exactly as ``GETD`` is replied to with
``DATA\\rOK\\r``. Nothing was reading the acknowledgement to a write, so it
sat in the input buffer, and the next read -- which stops at the first
``OK\\r`` it sees -- took it for the answer and returned an empty string.

``_bk_query`` flushes the input buffer before writing, which is why this
was intermittent rather than constant: at 9600 baud the stale ``OK\\r`` is
often still on the wire when the flush runs, and lands just in time to be
mistaken for the reply.

The fake here is a line, not a mock: bytes queued by writes, drained by
reads. That is the only reason it can reproduce a desync at all -- a mock
returning canned answers per call has no buffer to leave anything in.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.equipment.bk_power_supply import BK1902B, dialect_for


class FakeLine:
    """A B&K on the other end of a serial line, answering every command."""

    timeout = 1000  # ms, as PyVISA reports it

    def __init__(self, setpoints="150300", readings="15000300" + "0"):
        #: Bytes that have arrived and sit in the host's input buffer.
        self.buffer = bytearray()
        #: Bytes still travelling down the wire. At 9600 baud an "OK\r" is
        #: about three milliseconds long, and a flush issued in that window
        #: cannot clear what has not got here yet. Modelling this is the
        #: whole point: with everything landing instantly, the flush in
        #: _bk_query always wins and the desync never reproduces.
        self.in_flight = bytearray()
        self.written = []
        self._setpoints = setpoints
        self._readings = readings

    # -- the instrument side --------------------------------------------
    def write(self, command):
        self.written.append(command)
        if command.startswith("GETD"):
            self.in_flight += f"{self._readings}\rOK\r".encode()
        elif command.startswith("GETS"):
            self.in_flight += f"{self._setpoints}\rOK\r".encode()
        elif command.startswith("GOUT"):
            self.in_flight += b"0\rOK\r"
        else:
            # A set command. It is acknowledged too -- this is the whole point.
            self.in_flight += b"OK\r"

    def read_bytes(self, count):
        if not self.buffer:                 # whatever was on the wire lands
            self.buffer += self.in_flight
            self.in_flight.clear()
        if not self.buffer:
            raise TimeoutError("nothing on the line")
        taken, self.buffer = bytes(self.buffer[:count]), self.buffer[count:]
        return taken

    def flush(self, _mask):
        """VI_READ_BUF: discards what has arrived, not what is still coming."""
        self.buffer.clear()

    def on_the_line(self) -> bytes:
        """Everything not yet consumed, arrived or otherwise."""
        return bytes(self.buffer) + bytes(self.in_flight)

    def close(self):
        pass


@pytest.fixture
def supply():
    made = BK1902B.__new__(BK1902B)          # no resource manager, no VISA
    made.resource_string = "ASRL/dev/ttyUSB0::INSTR"
    made.instrument = FakeLine()
    made.connected = True
    made.safety_validator = None
    made.cached_info = None
    made.dialect = dialect_for("1902B")
    made._current_voltage = 0.0
    made._current_current = 0.0
    made._is_connecting = False
    made._lock = asyncio.Lock()
    from server.equipment.base import _ReentrantAsyncLock
    from server.equipment.slew_ramp import SlewRamps
    made._io_lock = _ReentrantAsyncLock()
    made._slew_ramps = SlewRamps("fake")
    made._ensure_connected = _noop
    return made


async def _noop(*a, **k):
    return None


class TestAWriteTakesItsAcknowledgement:
    @pytest.mark.asyncio
    async def test_the_line_is_empty_after_a_write(self, supply):
        """If it is not, the next read finds someone else's OK first."""
        await supply._write("VOLT120")
        assert supply.instrument.on_the_line() == b"", (
            f"left {supply.instrument.on_the_line()!r} on the line for the "
            f"next read to trip over")

    @pytest.mark.asyncio
    async def test_a_read_after_a_write_gets_the_real_answer(self, supply):
        """The bench failure, reproduced: this returned '' before the fix."""
        await supply._write("VOLT120")
        answer = await supply._bk_query("GETD")
        assert answer == "150003000", f"got {answer!r}"

    @pytest.mark.asyncio
    async def test_readings_survive_a_write_immediately_before(self, supply):
        """End to end: the poll that was failing on the bench."""
        await supply._write("VOLT120")
        readings = await supply.get_readings()
        assert readings.voltage_actual == pytest.approx(15.0)
        assert readings.current_actual == pytest.approx(3.0)

    @pytest.mark.asyncio
    async def test_several_writes_in_a_row_leave_nothing_behind(self, supply):
        """A ramp writes repeatedly; each one must clean up after itself."""
        for value in range(5):
            await supply._write(f"VOLT{value:03d}")
        assert supply.instrument.on_the_line() == b""
        assert await supply._bk_query("GETS") == "150300"

    @pytest.mark.asyncio
    async def test_the_command_still_reaches_the_instrument(self, supply):
        """Consuming the reply must not stop the write happening."""
        await supply._write("VOLT120")
        assert supply.instrument.written == ["VOLT120"]

    @pytest.mark.asyncio
    async def test_a_missing_acknowledgement_does_not_raise(self, supply, caplog):
        """The write went out. A silent supply is a log line, not an
        exception thrown at a caller who has already moved the instrument."""
        import logging

        class Silent(FakeLine):
            def write(self, command):
                self.written.append(command)   # answers nothing

        supply.instrument = Silent()
        with caplog.at_level(logging.WARNING,
                             logger="server.equipment.bk_power_supply"):
            await supply._write("VOLT120")
        assert any("no acknowledgement" in r.message for r in caplog.records)


class TestQueriesAreUnaffected:
    @pytest.mark.asyncio
    async def test_a_query_still_reads_its_own_data_and_ok(self, supply):
        assert await supply._bk_query("GETS") == "150300"

    @pytest.mark.asyncio
    async def test_two_queries_in_a_row_stay_in_step(self, supply):
        assert await supply._bk_query("GETS") == "150300"
        assert await supply._bk_query("GETD") == "150003000"


class TestOnlyTheFixedWidthModelsDoThis:
    def test_the_scpi_models_do_not_inherit_the_override(self):
        """SCPI does not acknowledge writes; reading one would hang."""
        from server.equipment.base import BaseEquipment
        from server.equipment.bk_power_supply import (BK1685B, BK1902B,
                                                      BK9205B)

        assert BK1902B._write is not BaseEquipment._write
        assert BK1685B._write is not BaseEquipment._write
        assert BK9205B._write is BaseEquipment._write, (
            "a SCPI supply would wait a full timeout for an OK that never comes")
