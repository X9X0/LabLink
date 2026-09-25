"""Changing range with the input live can damage things.

The user guide says so under Set Range, in a CAUTION box: "Before
switching the current range, please disable the channel input to avoid
causing damage to the instrument or the DUT." Switching range moves the
shunt the load regulates against, and doing that with current flowing
is what the caution is about.

The panel shipped a Range selector that sent the change immediately,
whatever the input was doing. This refuses it in the driver instead of
warning about it in one panel, so it holds for anything that drives the
instrument.

It refuses rather than turning the input off on the caller's behalf.
Disabling a load part-way through a test changes what the device under
test sees, and that is the operator's decision, not a side effect of
asking for a different range.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.equipment.base import SetpointRefused
from server.equipment.rigol_electronic_load import (DL3000_MODELS,
                                                    RigolDL3021A)


def driver(input_on=False, input_raises=False, answers=None):
    made = RigolDL3021A.__new__(RigolDL3021A)
    made.resource_string = "USB0::6833::3601::DL3B268M00049::0::INSTR"
    made.model = "DL3021A"
    made._apply_spec(DL3000_MODELS["DL3021A"])
    made.written = []
    answers = answers or {}

    async def record(command):
        made.written.append(command)

    async def query(command):
        if "ERR" in command.upper():
            return '0,"No error"'
        if "INP" in command.upper():
            if input_raises:
                raise OSError("no reply")
            return "1" if input_on else "0"
        for key, value in answers.items():
            if key in command:
                return value
        return "0.5"

    made._write = record
    made._query = query
    return made


def commands(load):
    return [c for c in load.written if c != "*CLS"]


class TestARangeChangeWhileSinkingIsRefused:
    @pytest.mark.parametrize("setter,argument", [
        ("set_current_range", {"current_range": 40.0}),
        ("set_voltage_range", {"voltage_range": 150.0}),
        ("set_resistance_range", {"resistance_range": 15000.0}),
    ])
    @pytest.mark.asyncio
    async def test_it_refuses_with_the_input_on(self, setter, argument):
        load = driver(input_on=True)
        with pytest.raises(SetpointRefused) as refused:
            await getattr(load, setter)(*argument.values())

        assert "input" in str(refused.value).lower()
        assert not any("RANG" in c for c in commands(load)), (
            "the range change reached the instrument anyway")

    @pytest.mark.parametrize("setter,argument", [
        ("set_current_range", 40.0),
        ("set_voltage_range", 150.0),
        ("set_resistance_range", 15000.0),
    ])
    @pytest.mark.asyncio
    async def test_it_goes_through_with_the_input_off(self, setter, argument):
        load = driver(input_on=False)
        await getattr(load, setter)(argument)
        assert any("RANG" in c for c in commands(load))

    @pytest.mark.asyncio
    async def test_not_knowing_counts_as_unsafe(self):
        """A load that will not say whether it is sinking cannot be
        promised safe to re-range."""
        load = driver(input_raises=True)
        with pytest.raises(SetpointRefused):
            await load.set_current_range(40.0)
        assert not any("RANG" in c for c in commands(load))

    @pytest.mark.asyncio
    async def test_it_does_not_disable_the_input_itself(self):
        """Dropping a load mid-test changes what the DUT sees. That is
        the operator's call, not a side effect of a range request."""
        load = driver(input_on=True)
        with pytest.raises(SetpointRefused):
            await load.set_current_range(40.0)

        assert not any("INP" in c for c in commands(load)), (
            f"it turned the input off on its own: {commands(load)}")

    @pytest.mark.asyncio
    async def test_the_message_says_what_to_do(self):
        load = driver(input_on=True)
        with pytest.raises(SetpointRefused) as refused:
            await load.set_current_range(40.0)
        said = str(refused.value).lower()
        assert "disable" in said and "current range" in said


class TestTheSlewLimitsComeFromTheLoad:
    """They move with the current range, so they cannot be a constant.

    In the 4 A range on the bench the CC rate took 0.24 A/us and refused
    0.5. A per-model number written into the driver would have been
    wrong the moment anybody switched range -- and :CURRent:SLEW? takes
    MINimum and MAXimum, so there is no need to guess.
    """

    @pytest.mark.asyncio
    async def test_it_asks_for_min_and_max(self):
        load = driver(answers={"SLEW? MAX": "2.5", "SLEW? MIN": "0.001"})
        limits = await load.get_slew_limits()

        assert limits["cc_max"] == pytest.approx(2.5)
        assert limits["cc_min"] == pytest.approx(0.001)

    @pytest.mark.asyncio
    async def test_the_transient_rates_are_separate(self):
        """CC and transient have their own slew commands and their own
        limits."""
        load = driver(answers={"SLEW:POS? MAX": "1.5", "SLEW? MAX": "2.5"})
        limits = await load.get_slew_limits()

        assert limits["transient_max"] == pytest.approx(1.5)
        assert limits["cc_max"] == pytest.approx(2.5)

    @pytest.mark.asyncio
    async def test_an_unreadable_limit_is_none_not_a_guess(self):
        load = driver()

        async def broken(command):
            if "SLEW" in command:
                raise OSError("no reply")
            return '0,"No error"'
        load._query = broken

        limits = await load.get_slew_limits()
        assert limits["cc_max"] is None

    @pytest.mark.asyncio
    async def test_the_api_can_ask(self):
        load = driver(answers={"SLEW? MAX": "2.5"})
        limits = await load.execute_command("get_slew_limits", {})
        assert limits["cc_max"] == pytest.approx(2.5)
