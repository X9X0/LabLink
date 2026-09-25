"""Transient operation: the Con, Pul and Tog keys, which we had none of.

Three keys sit on the DL3000's front panel beside CC/CV/CR/CP and the
driver did not speak to any of them. They share one shape -- two levels
the sink current alternates between, a timing, and a pair of slew rates
-- which is why they arrive together rather than one at a time.

Two traps here, both of the kind that report success and do nothing:

  * :SLEW:POSitive and :SLEW:NEGative are the *transient* rising and
    falling rates. CC mode's own slew rate is :SLEW[:BOTH] and sets
    both directions at once. Reaching for the obvious-looking pair
    writes something real and unrelated.

  * the default trigger source is MANUal, meaning the front-panel TRAN
    key. :TRIGger on a load still set to MANUal is not an error and
    has no effect, which would look exactly like a dead button.

Units are the guide's and not the obvious ones: widths in ms,
frequency in kHz, duty as an integer percent.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.equipment.base import SetpointRefused
from server.equipment.rigol_electronic_load import (DL3000_MODELS,
                                                    RigolDL3021A)


def driver(answers=None):
    made = RigolDL3021A.__new__(RigolDL3021A)
    made.resource_string = "USB0::6833::3601::DL3B268M00049::0::INSTR"
    made.model = "DL3021A"
    made._apply_spec(DL3000_MODELS["DL3021A"])
    made.written = []
    made.queried = []
    answers = answers or {}

    async def record(command):
        made.written.append(command)

    async def query(command):
        made.queried.append(command)
        if "ERR" in command.upper():
            return '0,"No error"'
        for key, value in answers.items():
            if key in command:
                return value
        return "1.0"

    made._write = record
    made._query = query
    return made


def sent(load, fragment):
    return [c for c in load.written if fragment in c]


class TestTurningItOn:
    @pytest.mark.asyncio
    async def test_enabling_uses_the_tran_state_command(self):
        """Levels and timings do nothing visible until this is on."""
        load = driver()
        await load.set_transient_enabled(True)
        assert sent(load, ":SOUR:TRAN:STAT ON")

    @pytest.mark.asyncio
    async def test_disabling(self):
        load = driver()
        await load.set_transient_enabled(False)
        assert sent(load, ":SOUR:TRAN:STAT OFF")

    @pytest.mark.asyncio
    async def test_reading_it_back(self):
        load = driver({":SOUR:TRAN:STAT?": "1"})
        assert await load.get_transient_enabled() is True


class TestTheThreeModes:
    @pytest.mark.parametrize("asked,keyword", [
        ("CON", "CONTinuous"), ("PUL", "PULSe"), ("TOG", "TOGGle"),
    ])
    @pytest.mark.asyncio
    async def test_each_sends_its_keyword(self, asked, keyword):
        load = driver()
        await load.set_transient_mode(asked)
        assert sent(load, ":SOUR:CURR:TRAN:MODE " + keyword)

    @pytest.mark.asyncio
    async def test_a_full_word_is_accepted(self):
        load = driver()
        await load.set_transient_mode("continuous")
        assert sent(load, "CONTinuous")

    @pytest.mark.asyncio
    async def test_nonsense_is_refused(self):
        load = driver()
        with pytest.raises(SetpointRefused):
            await load.set_transient_mode("SQUARE")
        assert load.written == []

    @pytest.mark.asyncio
    async def test_the_short_form_comes_back(self):
        load = driver({":SOUR:CURR:TRAN:MODE?": "TOGG"})
        assert await load.get_transient_mode() == "TOG"


class TestTheLevels:
    @pytest.mark.asyncio
    async def test_both_go_out(self):
        load = driver()
        await load.set_transient_levels(5.0, 1.0)
        assert sent(load, ":SOUR:CURR:TRAN:ALEV 5.0")
        assert sent(load, ":SOUR:CURR:TRAN:BLEV 1.0")

    @pytest.mark.asyncio
    async def test_above_the_models_current_is_refused(self):
        load = driver()
        with pytest.raises(SetpointRefused):
            await load.set_transient_levels(100.0, 1.0)

    @pytest.mark.asyncio
    async def test_neither_is_sent_if_either_is_bad(self):
        """Half-applied levels would run the load on one new value and
        one old one."""
        load = driver()
        with pytest.raises(SetpointRefused):
            await load.set_transient_levels(5.0, 999.0)
        assert load.written == []


class TestTheTimings:
    @pytest.mark.asyncio
    async def test_widths_are_milliseconds(self):
        load = driver()
        await load.set_transient_widths(2.0, 3.0)
        assert sent(load, ":SOUR:CURR:TRAN:AWID 2.0")
        assert sent(load, ":SOUR:CURR:TRAN:BWID 3.0")

    @pytest.mark.asyncio
    async def test_a_zero_width_is_refused(self):
        load = driver()
        with pytest.raises(SetpointRefused):
            await load.set_transient_widths(0.0, 1.0)

    @pytest.mark.asyncio
    async def test_frequency_is_kilohertz(self):
        """The guide's unit. Sending Hz would be off by a thousand and
        perfectly well accepted."""
        load = driver()
        await load.set_transient_frequency(5.0)
        assert sent(load, ":SOUR:CURR:TRAN:FREQ 5.0")

    @pytest.mark.asyncio
    async def test_the_models_frequency_ceiling_is_enforced(self):
        """30 kHz on an A model, and the spec table has it -- so unlike
        the CC slew rate, this one we can check ourselves."""
        load = driver()
        with pytest.raises(SetpointRefused) as refused:
            await load.set_transient_frequency(40.0)
        assert "30" in str(refused.value)

    @pytest.mark.asyncio
    async def test_duty_is_a_percentage(self):
        load = driver()
        await load.set_transient_duty(50)
        assert sent(load, ":SOUR:CURR:TRAN:ADUT 50")

    @pytest.mark.parametrize("bad", [0, 101, -5])
    @pytest.mark.asyncio
    async def test_duty_outside_one_to_a_hundred_is_refused(self, bad):
        load = driver()
        with pytest.raises(SetpointRefused):
            await load.set_transient_duty(bad)


class TestTheTransientSlewIsNotTheCCOne:
    """The trap. Two slew commands, one per mode, and the wrong one
    succeeds silently."""

    @pytest.mark.asyncio
    async def test_it_uses_positive_and_negative(self):
        load = driver()
        await load.set_transient_slew(0.5, 0.25)
        assert sent(load, ":SOUR:CURR:SLEW:POS 0.5")
        assert sent(load, ":SOUR:CURR:SLEW:NEG 0.25")

    @pytest.mark.asyncio
    async def test_it_does_not_write_the_cc_rate(self):
        load = driver()
        await load.set_transient_slew(0.5, 0.25)
        bare = [c for c in load.written
                if "SLEW" in c and "POS" not in c and "NEG" not in c]
        assert not bare, f"wrote the CC slew rate as well: {bare}"

    @pytest.mark.asyncio
    async def test_the_cc_rate_does_not_write_the_transient_ones(self):
        load = driver()
        await load.set_slew_rate(0.5)
        assert not sent(load, "POS") and not sent(load, "NEG")


class TestTriggering:
    @pytest.mark.asyncio
    async def test_it_selects_the_bus_source_when_it_is_not_already(self):
        """MANUal is the default and means the front-panel key, so
        :TRIGger alone is a no-op that looks like a dead button."""
        load = driver({":TRIG:SOUR?": "MANUAL"})
        await load.trigger()

        assert sent(load, ":TRIG:SOUR BUS"), (
            f"triggered without selecting the bus source: {load.written}")
        assert load.written.index(":TRIG:SOUR BUS") < \
               load.written.index(":TRIG"), "the order is the whole point"

    @pytest.mark.asyncio
    async def test_it_leaves_the_source_alone_when_already_bus(self):
        """Setting the source disarms the transient generator.

        Doing it unconditionally before every trigger armed and then
        disarmed in the same breath, so the generator could never run.
        On the bench that was a load parked at Level B for ever -- which
        the user guide says is the correct *waiting* state: "the load
        sinks the current of Level B, and then waits trigger to occur".
        It was waiting for a trigger that kept undoing its arm.
        """
        load = driver({":TRIG:SOUR?": "BUS"})
        await load.trigger()

        assert not sent(load, ":TRIG:SOUR"), (
            f"re-set the source and disarmed the generator: {load.written}")
        assert ":TRIG" in load.written

    @pytest.mark.asyncio
    async def test_an_unreadable_source_is_set_rather_than_assumed(self):
        """Not knowing is a reason to set it, not to skip it."""
        load = driver()

        async def broken(command):
            if "TRIG:SOUR?" in command:
                raise OSError("no reply")
            return '0,"No error"'
        load._query = broken

        await load.trigger()
        assert sent(load, ":TRIG:SOUR BUS")

    @pytest.mark.asyncio
    async def test_the_source_can_be_set_on_its_own(self):
        load = driver()
        await load.set_trigger_source("external")
        assert sent(load, ":TRIG:SOUR EXTernal")

    @pytest.mark.asyncio
    async def test_a_bad_source_is_refused(self):
        load = driver()
        with pytest.raises(SetpointRefused):
            await load.set_trigger_source("SOMETIMES")


class TestReadingItAllBack:
    @pytest.mark.asyncio
    async def test_every_field_comes_back(self):
        load = driver({
            ":SOUR:TRAN:STAT?": "1",
            ":SOUR:CURR:TRAN:MODE?": "CONT",
            ":SOUR:CURR:TRAN:ALEV?": "5.0",
            ":SOUR:CURR:TRAN:BLEV?": "1.0",
        })
        state = await load.get_transient()

        assert state["enabled"] is True
        assert state["mode"] == "CON"
        assert state["level_a"] == pytest.approx(5.0)
        assert state["level_b"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_one_unreadable_field_does_not_lose_the_others(self):
        load = driver()

        async def query(command):
            load.queried.append(command)
            if "ALEV" in command:
                raise OSError("no reply")
            if "ERR" in command.upper():
                return '0,"No error"'
            return "2.0"
        load._query = query

        state = await load.get_transient()
        assert state["level_a"] is None
        assert state["level_b"] == pytest.approx(2.0)


class TestItIsReachableAndAdvertised:
    @pytest.mark.asyncio
    async def test_the_api_dispatches_them(self):
        load = driver()
        await load.execute_command("set_transient_mode", {"mode": "PUL"})
        await load.execute_command("set_transient_levels",
                                   {"level_a": 3.0, "level_b": 0.5})
        await load.execute_command("trigger", {})
        assert sent(load, "PULSe") and sent(load, "ALEV") and sent(load, ":TRIG")

    def test_the_capabilities_say_so(self):
        load = driver()
        caps = load._capabilities()
        assert caps.get("supports_transient") is True
        assert set(caps.get("transient_modes") or []) == {"CON", "PUL", "TOG"}


class TestWhatTheLoadSaysIsInstalled:
    """*OPT? reports high slew rate, high frequency, high readback
    resolution, LAN and Digital I/O -- and nothing else.

    It is not a gate on List, the battery test or OCP/OPP. This module
    used to claim in its header that those were the factory options,
    which sent me looking for a way to ask whether they were present
    before writing any UI for them. They are standard on every model:
    :FUNCtion:MODE takes {FIXed|LIST|WAVe|BATTery|OCP|OPP} with no
    caveat.
    """

    @pytest.mark.asyncio
    async def test_installed_options_are_listed(self):
        load = driver({"*OPT?": "HSR,HFR,HRR,LAN,DIO"})
        options = await load.get_options()
        assert options["installed"] == ["HSR", "HFR", "HRR", "LAN", "DIO"]

    @pytest.mark.asyncio
    async def test_a_zero_means_not_fitted_and_is_dropped(self):
        """An absent option comes back as "0", not as a missing field."""
        load = driver({"*OPT?": "0,HFR,0,LAN,0"})
        options = await load.get_options()
        assert options["installed"] == ["HFR", "LAN"]

    @pytest.mark.asyncio
    async def test_the_raw_reply_is_kept(self):
        """The names are the instrument's own, so do not lose them."""
        load = driver({"*OPT?": "0,0,0,LAN,0"})
        options = await load.get_options()
        assert options["raw"] == "0,0,0,LAN,0"

    @pytest.mark.asyncio
    async def test_the_api_can_ask(self):
        load = driver({"*OPT?": "HSR,HFR,HRR,LAN,DIO"})
        answer = await load.execute_command("get_options", {})
        assert answer["installed"]
