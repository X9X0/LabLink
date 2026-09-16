"""A slow exchange is named in the log, with how long it waited and how long it took.

The bench log is the only place a twenty-second lag can be traced to the
command that caused it.
"""

import asyncio
import logging
import time
from unittest.mock import MagicMock

import pytest

from server.equipment.base import BaseEquipment


class _Instrument(BaseEquipment):
    async def get_info(self):  # pragma: no cover
        return None

    async def get_status(self):  # pragma: no cover
        return None

    async def execute_command(self, command, parameters):  # pragma: no cover
        return None


def _connected():
    equipment = _Instrument(MagicMock(), "USB0::0x1AB1::0x04CE::DS1ZA1::INSTR")
    equipment.instrument = MagicMock()
    equipment.instrument.session = 1
    equipment.connected = True
    equipment.SLOW_IO_WARN_SEC = 0.05
    return equipment


@pytest.mark.unit
def test_a_slow_command_is_named(caplog):
    equipment = _connected()
    equipment.instrument.query = lambda cmd: (time.sleep(0.08), "1")[1]
    with caplog.at_level(logging.WARNING, logger="server.equipment.base"):
        asyncio.run(equipment._query(":MEAS:ITEM? VPP,CHAN1"))
    assert any(":MEAS:ITEM? VPP,CHAN1" in r.message and "took" in r.message for r in caplog.records)


@pytest.mark.unit
def test_waiting_for_the_lock_is_reported_separately(caplog):
    equipment = _connected()
    equipment.instrument.query = lambda cmd: (time.sleep(0.08), "1")[1] if cmd == "SLOW?" else "2"

    async def main():
        await asyncio.gather(equipment._query("SLOW?"), equipment._query("FAST?"))

    with caplog.at_level(logging.WARNING, logger="server.equipment.base"):
        asyncio.run(main())
    waited = [r.message for r in caplog.records if "waited" in r.message]
    assert waited and "FAST?" in waited[0]


@pytest.mark.unit
def test_a_quick_command_says_nothing(caplog):
    equipment = _connected()
    equipment.instrument.query = lambda cmd: "1"
    with caplog.at_level(logging.WARNING, logger="server.equipment.base"):
        asyncio.run(equipment._query("*OPC?"))
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
