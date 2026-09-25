"""Selecting CV on an electronic load has to put it in CV.

Reported from the bench: "on the load control panel, I also notice that
it seems like it's not switching between CC, CV, CP and CR." Tested
against the DL3021A, and it was not::

    asked    set_mode reply    mode read back
    CV       ok                CC
    CR       ok                CC
    CP       ok                CC
    CC       ok                CC

``:SOURce:FUNCtion`` is asymmetric on these loads. The query answers
with the short form -- CC/CV/CR/CP -- but the setting takes the long
keyword: CURRent/VOLTage/RESistance/POWer. The driver sent the short
form straight back, which the instrument will not accept.

Nothing looked wrong from here because a SCPI syntax fault goes to the
instrument's error queue, not into the reply. The write "succeeded",
the API returned success, and the load stayed where it was. Only asking
it what mode it was in showed anything.

``_MODE_TO_FUNCTION`` was already in the module, directly above the
function that needed it, with a comment explaining that the setting
keyword is the long form. It had no callers.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.equipment.base import CommandRejected
from server.equipment.rigol_electronic_load import (DL3000_MODELS,
                                                    _FUNCTION_TO_MODE,
                                                    _MODE_TO_FUNCTION, _MODES,
                                                    RigolDL3021A)


def driver():
    made = RigolDL3021A.__new__(RigolDL3021A)
    made.resource_string = "USB0::6833::3601::DL3B268M00049::0::INSTR"
    made.model = "DL3021A"
    # The ratings the setters range against; __init__ normally applies
    # these from the model table.
    made._apply_spec(DL3000_MODELS["DL3021A"])
    made.written = []

    async def record(command):
        made.written.append(command)
    made._write = record
    return made


class TestTheModeActuallyChanges:
    @pytest.mark.parametrize("mode,keyword", [
        ("CC", "CURR"), ("CV", "VOLT"), ("CR", "RES"), ("CP", "POW"),
    ])
    @pytest.mark.asyncio
    async def test_it_sends_the_long_keyword(self, mode, keyword):
        load = driver()
        await load.set_mode(mode)

        assert len(load.written) == 1
        sent = load.written[0]
        assert sent.startswith(":SOUR:FUNC "), sent
        argument = sent.split(" ", 1)[1].upper()
        assert argument.startswith(keyword), (
            f"sent {sent!r}; the instrument wants the long keyword and "
            f"silently ignores the short one")

    @pytest.mark.asyncio
    async def test_it_does_not_send_the_short_form(self):
        """The exact regression: :SOUR:FUNC CV does nothing at all."""
        load = driver()
        await load.set_mode("CV")

        assert load.written[0] != ":SOUR:FUNC CV", (
            "this is the command that reported success and left the load "
            "in CC")

    @pytest.mark.asyncio
    async def test_lowercase_is_accepted(self):
        load = driver()
        await load.set_mode("cv")
        assert "VOLT" in load.written[0].upper()

    @pytest.mark.asyncio
    async def test_an_unknown_mode_is_refused(self):
        load = driver()
        with pytest.raises(ValueError):
            await load.set_mode("CX")
        assert load.written == [], "a bad mode still reached the instrument"


class TestTheTwoMapsAgree:
    """The read path maps one way; the write path must map the other."""

    def test_every_mode_has_a_keyword(self):
        missing = [m for m in _MODES if m not in _MODE_TO_FUNCTION]
        assert not missing, f"no setting keyword for {missing}"

    def test_every_keyword_maps_back(self):
        """Round trip: what we set must be recognised when read."""
        for mode in _MODES:
            keyword = _MODE_TO_FUNCTION[mode].upper()
            # The instrument may answer with the short form or any
            # truncation of the long one; the read map must cover both.
            assert _FUNCTION_TO_MODE.get(mode) == mode, (
                f"reading back {mode!r} does not map to itself")
            assert any(_FUNCTION_TO_MODE.get(k) == mode
                       for k in (keyword, keyword[:4])), (
                f"setting {mode} sends {keyword}, which the read map does "
                f"not recognise -- so the panel would show the wrong mode")

    def test_the_map_is_used(self):
        """It existed, commented, with no callers, for however long."""
        import inspect

        source = inspect.getsource(RigolDL3021A.set_mode)
        assert "_MODE_TO_FUNCTION" in source, (
            "set_mode is formatting the mode itself again")


class TestTheLoadIsAskedWhetherItAgreed:
    """A SCPI fault goes to the error queue, not into the reply.

    That is the whole reason the mode bug was invisible: the write
    returned, the API returned success, and :SOUR:FUNC? kept answering
    CC. Asking the queue after a control command turns that class of
    bug from silent into an error where it happens.
    """

    @staticmethod
    def _driver(error_reply):
        load = driver()
        load.queried = []

        async def query(command):
            load.queried.append(command)
            return error_reply
        load._query = query
        return load

    @pytest.mark.asyncio
    async def test_a_clean_queue_passes(self):
        load = self._driver('0,"No error"')
        await load.set_mode("CV")
        assert load.written, "the command never went out"

    @pytest.mark.asyncio
    async def test_a_fault_is_raised_rather_than_swallowed(self):
        load = self._driver('-113,"Undefined header"')
        with pytest.raises(CommandRejected) as rejected:
            await load.set_mode("CV")

        said = str(rejected.value)
        assert "Undefined header" in said, (
            f"the instrument's own words are the useful part: {said}")

    @pytest.mark.asyncio
    async def test_the_command_is_named(self, ):
        """So the log says which one, not just that something failed."""
        load = self._driver('-113,"Undefined header"')
        with pytest.raises(CommandRejected) as rejected:
            await load.set_current(2.0)
        assert "CURR" in str(rejected.value)

    @pytest.mark.asyncio
    async def test_the_queue_is_checked_after_the_write(self):
        load = self._driver('0,"No error"')
        await load.set_mode("CV")
        assert any("ERR" in q.upper() for q in load.queried), (
            "nothing asked the load whether it objected")

    @pytest.mark.asyncio
    async def test_not_being_able_to_ask_is_not_a_failure(self):
        """A load that will not answer :SYST:ERR? has not thereby
        refused the command, and must not be reported as having done."""
        load = driver()

        async def broken(command):
            raise OSError("no reply")
        load._query = broken

        await load.set_mode("CV")       # must not raise
        assert load.written == [":SOUR:FUNC VOLTage"]

    @pytest.mark.asyncio
    async def test_readings_are_not_slowed_by_it(self):
        """Only control commands pay the extra round trip. A poll at
        5 Hz doubling its traffic is how the serial supplies were
        driven into timing out earlier."""
        import inspect

        source = inspect.getsource(RigolDL3021A.get_readings)
        assert "_command(" not in source, (
            "the readings path is making checked writes")
