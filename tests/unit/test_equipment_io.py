"""Tests for per-instrument I/O serialisation and USB stall recovery.

Seen live on a 9205B: a client polling readings while the health monitor sent
*IDN? put two USBTMC transfers on the wire at once. The device stalled its
bulk pipe, and every exchange after that -- including the operator's attempt
to turn the output off -- failed with "[Errno 32] Pipe error" until the
device was reset.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from server.equipment.base import BaseEquipment


class _Instrument(BaseEquipment):
    """The smallest concrete BaseEquipment."""

    async def get_info(self):  # pragma: no cover - not exercised
        return None

    async def get_status(self):  # pragma: no cover - not exercised
        return None

    async def execute_command(self, command, parameters):  # pragma: no cover
        return None


def _connected(resource="USB0::11975::37376::800886011797210043::0::INSTR"):
    equipment = _Instrument(MagicMock(), resource)
    equipment.instrument = MagicMock()
    equipment.instrument.session = 1
    equipment.connected = True
    equipment.USB_RESET_SETTLE_SEC = 0
    return equipment


class TestExchangesAreSerialised:

    @pytest.mark.asyncio
    async def test_queries_from_different_tasks_do_not_interleave(self):
        equipment = _connected()
        in_flight = 0
        overlapped = False

        def slow_query(command):
            nonlocal in_flight, overlapped
            in_flight += 1
            if in_flight > 1:
                overlapped = True
            time.sleep(0.02)
            in_flight -= 1
            return command

        equipment.instrument.query = slow_query

        replies = await asyncio.gather(
            *(equipment._query(f"Q{i}?") for i in range(5))
        )

        assert not overlapped, "two exchanges were on the wire at once"
        assert sorted(replies) == [f"Q{i}?" for i in range(5)]

    @pytest.mark.asyncio
    async def test_a_write_waits_for_a_query_in_progress(self):
        equipment = _connected()
        order = []

        def query(command):
            order.append("query start")
            time.sleep(0.02)
            order.append("query end")
            return "1"

        def write(command):
            order.append("write")

        equipment.instrument.query = query
        equipment.instrument.write = write

        await asyncio.gather(equipment._query("MEAS:VOLT?"), equipment._write("OUTP OFF"))

        assert order == ["query start", "query end", "write"]

    @pytest.mark.asyncio
    async def test_the_lock_is_reentrant_along_the_reconnect_path(self):
        """_query -> _ensure_connected -> connect -> _query, all in one task."""
        equipment = _connected()
        equipment.instrument = None  # an invalid session forces a reconnect

        async def connect():
            equipment.instrument = MagicMock()
            equipment.instrument.session = 2
            equipment.instrument.query = lambda command: f"reply to {command}"
            await equipment._query("*IDN?")  # nested under the outer lock
            equipment.connected = True

        equipment.connect = connect

        reply = await asyncio.wait_for(equipment._query("MEAS:VOLT?"), timeout=2)
        assert reply == "reply to MEAS:VOLT?"


class TestUSBStallRecovery:

    def _stall(self, equipment):
        """Make the current session fail with EPIPE and expose its pyusb device."""
        stalled = equipment.instrument
        usb_dev = MagicMock()
        stalled.visalib.sessions = {
            stalled.session: MagicMock(interface=MagicMock(usb_dev=usb_dev))
        }
        stalled.query = MagicMock(side_effect=OSError(32, "Pipe error"))
        stalled.write = MagicMock(side_effect=OSError(32, "Pipe error"))
        return stalled, usb_dev

    def _reconnect_to(self, equipment, fresh):
        async def connect():
            equipment.instrument = fresh
            equipment.connected = True

        equipment.connect = connect

    @pytest.mark.asyncio
    async def test_a_pipe_error_resets_the_device_and_retries_once(self):
        equipment = _connected()
        stalled, usb_dev = self._stall(equipment)
        fresh = MagicMock()
        fresh.session = 2
        fresh.query = MagicMock(return_value="12.000")
        self._reconnect_to(equipment, fresh)

        assert await equipment._query("MEAS:VOLT?") == "12.000"

        usb_dev.reset.assert_called_once()
        stalled.close.assert_called_once()
        fresh.query.assert_called_once_with("MEAS:VOLT?")

    @pytest.mark.asyncio
    async def test_the_operators_command_goes_through_after_the_reset(self):
        """The case that mattered: OUTP OFF failing on a stalled supply."""
        equipment = _connected()
        _, usb_dev = self._stall(equipment)
        fresh = MagicMock()
        fresh.session = 2
        self._reconnect_to(equipment, fresh)

        await equipment._write("OUTP OFF")

        usb_dev.reset.assert_called_once()
        fresh.write.assert_called_once_with("OUTP OFF")

    @pytest.mark.asyncio
    async def test_a_second_pipe_error_is_raised_not_looped_on(self):
        equipment = _connected()
        _, usb_dev = self._stall(equipment)
        fresh = MagicMock()
        fresh.session = 2
        fresh.query = MagicMock(side_effect=OSError(32, "Pipe error"))
        self._reconnect_to(equipment, fresh)

        with pytest.raises(OSError):
            await equipment._query("MEAS:VOLT?")
        usb_dev.reset.assert_called_once()

    @pytest.mark.asyncio
    async def test_a_serial_instrument_is_not_reset(self):
        equipment = _connected("ASRL/dev/ttyUSB0::INSTR")
        equipment.instrument.query = MagicMock(side_effect=OSError(32, "Pipe error"))
        equipment.connect = AsyncMock(side_effect=AssertionError("reconnected"))

        with pytest.raises(OSError):
            await equipment._query("GETD")
        assert equipment.instrument is not None

    @pytest.mark.asyncio
    async def test_other_errors_are_not_mistaken_for_a_stall(self):
        equipment = _connected()
        equipment.instrument.query = MagicMock(side_effect=TimeoutError("VI_ERROR_TMO"))
        equipment.connect = AsyncMock(side_effect=AssertionError("reconnected"))

        with pytest.raises(TimeoutError):
            await equipment._query("*IDN?")
        assert equipment.instrument is not None


class TestHealthProbe:

    @pytest.mark.asyncio
    async def test_scpi_instruments_are_probed_with_idn(self):
        equipment = _connected()
        equipment.instrument.query = MagicMock(return_value="B&K Precision,9205B,1,1.17")
        assert await equipment.health_probe() == "B&K Precision,9205B,1,1.17"
        equipment.instrument.query.assert_called_once_with("*IDN?")

    @pytest.mark.asyncio
    async def test_fixed_width_supplies_are_probed_with_gmax_and_never_idn(self):
        """*IDN? to a 1685B is a guaranteed timeout, and the health monitor
        sent one every 30 seconds while the operator was using the port."""
        from server.equipment.bk_power_supply import BK1685B

        supply = BK1685B(MagicMock(), "ASRL/dev/ttyUSB0::INSTR")
        supply._bk_query = AsyncMock(return_value="605680")
        supply._query = AsyncMock(
            side_effect=AssertionError("*IDN? sent to a fixed-width supply")
        )

        assert await supply.health_probe() == "605680"
        status = await supply.get_status()

        assert status.firmware_version is None
        supply._query.assert_not_called()

    @pytest.mark.asyncio
    async def test_the_public_query_is_the_locked_one(self):
        equipment = _connected()
        equipment.instrument.query = MagicMock(return_value="0")
        assert await equipment.query("*OPC?") == "0"
        equipment.instrument.query.assert_called_once_with("*OPC?")
