"""CC mode has two parameters beyond its level, and we had neither.

The user guide lists them under the CC key: "You can set parameters for
the mode, such as current, range, slew rate, and starting voltage." The
driver had the current and the range. Slew rate and Von were absent --
grep for "slew" in the driver returned nothing at all.

The command to be careful about is the slew rate.
``:CURRent:SLEW[:BOTH]`` is the CC-mode rate and sets rising and
falling together. ``:SLEW:POSitive`` and ``:SLEW:NEGative`` look like
the obvious pair and are documented as the rising and falling rates in
*transient* operation -- a different mode with its own levels. Reaching
for those would have written something real and not this, which is the
kind of mistake that reports success and does nothing.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.equipment.base import SetpointRefused
from server.equipment.rigol_electronic_load import (DL3000_MODELS,
                                                    RigolDL3021A)


def driver(error_reply='0,"No error"'):
    made = RigolDL3021A.__new__(RigolDL3021A)
    made.resource_string = "USB0::6833::3601::DL3B268M00049::0::INSTR"
    made.model = "DL3021A"
    made._apply_spec(DL3000_MODELS["DL3021A"])
    made.written = []
    made.queried = []

    async def record(command):
        made.written.append(command)

    async def query(command):
        made.queried.append(command)
        if "ERR" in command.upper():
            return error_reply
        return "0.5"
    made._write = record
    made._query = query
    return made


def commands(load):
    """The writes that are not bookkeeping.

    Every checked write clears the error queue first, so *CLS sits in
    front of the command being tested. Filtering it here keeps the
    assertions about the command rather than about the housekeeping --
    and TestTheQueueIsClearedBeforeTheWrite still checks the clear
    itself, against the unfiltered list.
    """
    return [c for c in load.written if c != "*CLS"]


class TestTheSlewRate:
    @pytest.mark.asyncio
    async def test_it_sets_the_cc_rate_not_the_transient_one(self):
        load = driver()
        await load.set_slew_rate(0.5)

        sent = commands(load)[0]
        assert "SLEW" in sent
        assert "POS" not in sent.upper() and "NEG" not in sent.upper(), (
            f"{sent} is the transient-mode rate, not the CC one")

    @pytest.mark.asyncio
    async def test_the_value_goes_out(self):
        load = driver()
        await load.set_slew_rate(0.25)
        assert "0.25" in commands(load)[0]

    @pytest.mark.asyncio
    async def test_zero_is_refused(self):
        load = driver()
        with pytest.raises(SetpointRefused):
            await load.set_slew_rate(0)
        assert load.written == []

    @pytest.mark.asyncio
    async def test_a_negative_rate_is_refused(self):
        load = driver()
        with pytest.raises(SetpointRefused):
            await load.set_slew_rate(-1.0)

    @pytest.mark.asyncio
    async def test_no_ceiling_is_invented(self):
        """The per-model maximum is not in the data the driver holds.
        Guessing one is how a supply got three different wrong floors;
        the instrument knows, and the error queue now reports it."""
        load = driver()
        await load.set_slew_rate(10_000.0)      # absurd, and not ours to judge
        assert commands(load), "the driver refused on a limit it invented"

    @pytest.mark.asyncio
    async def test_it_is_read_back_from_the_cc_command(self):
        load = driver()
        assert await load.get_slew_rate() == pytest.approx(0.5)
        assert any("SLEW" in q for q in load.queried)


class TestTheStartingVoltage:
    @pytest.mark.asyncio
    async def test_it_sets_von(self):
        load = driver()
        await load.set_von(5.0)
        assert ":SOUR:CURR:VON" in commands(load)[0]
        assert "5.0" in commands(load)[0]

    @pytest.mark.asyncio
    async def test_above_the_models_voltage_is_refused(self):
        """This one the driver does know: it is a voltage, and the
        model table has the load's rating."""
        load = driver()
        with pytest.raises(SetpointRefused):
            await load.set_von(500.0)

    @pytest.mark.asyncio
    async def test_negative_is_refused(self):
        load = driver()
        with pytest.raises(SetpointRefused):
            await load.set_von(-1.0)

    @pytest.mark.asyncio
    async def test_zero_is_allowed(self):
        """Von of 0 means sink whatever is there, which is a real setting."""
        load = driver()
        await load.set_von(0.0)
        assert load.written


class TestTheyAreReachableAndAdvertised:
    @pytest.mark.asyncio
    async def test_the_api_can_dispatch_them(self):
        load = driver()
        await load.execute_command("set_slew_rate", {"slew_rate": 0.5})
        await load.execute_command("set_von", {"von": 2.0})
        assert len(commands(load)) == 2

    def test_the_capabilities_say_so(self):
        """Or a panel has no way to know whether to offer the controls."""
        load = driver()
        caps = load._capabilities()
        assert caps.get("supports_slew_rate") is True
        assert caps.get("supports_von") is True

    @pytest.mark.asyncio
    async def test_a_rejection_still_surfaces(self):
        """These go out through the checked write like every other
        control command."""
        from server.equipment.base import CommandRejected

        load = driver(error_reply='-222,"Data out of range"')
        with pytest.raises(CommandRejected):
            await load.set_slew_rate(0.5)
