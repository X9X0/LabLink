"""List, battery discharge, OCP and OPP -- the :FUNCtion:MODE family.

These four share one selector. The guide puts it as "what controls the
input regulation mode": :SOURce:FUNCtion picks the regulation law (CC,
CV, CR, CP) and :FUNCtion:MODE picks what is allowed to move the
setpoint -- the fixed level, a list, the battery discharge, or one of
the two protection tests.

Two spellings in here are traps rather than choices, and both are
tested because getting either wrong is a "Parameter error" from the
instrument and nothing else:

  * :FUNCtion:MODE takes {FIXed|LIST|WAVe|BATTery|OCP|OPP} but its
    query "returns FIX, LIST, WAV, BATT, OCP, or OPP". Feeding a
    query's answer back to the setter sends WAV where WAVe was meant.
    This is the same asymmetry that made :SOUR:FUNC CV silently fail.

  * Rigol spells the battery subsystem BATTary and the matching
    function mode BATTery. Both abbreviate to BATT, so the short form
    is correct either way -- which is the only reason the spelling did
    not have to be discovered on the bench.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.equipment.base import SetpointRefused
from server.equipment.rigol_electronic_load import (DL3000_MODELS,
                                                    RigolDL3021A)


def driver(input_on=False, answers=None):
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
        if "INP" in command.upper() and "SHOR" not in command.upper():
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


class TestChoosingWhatDrivesTheInput:
    @pytest.mark.parametrize("asked,sent", [
        ("LIST", "LIST"),
        ("OCP", "OCP"),
        ("OPP", "OPP"),
        ("FIX", "FIX"),
        ("BATT", "BATT"),
    ])
    @pytest.mark.asyncio
    async def test_it_selects_the_mode(self, asked, sent):
        load = driver()
        await load.set_function_mode(asked)
        assert f":SOUR:FUNC:MODE {sent}" in commands(load)

    @pytest.mark.parametrize("spelling", ["FIXed", "fixed", "Fixed"])
    @pytest.mark.asyncio
    async def test_the_guides_long_spellings_are_accepted(self, spelling):
        """Somebody reading the manual will type what it prints."""
        load = driver()
        await load.set_function_mode(spelling)
        assert ":SOUR:FUNC:MODE FIX" in commands(load)

    @pytest.mark.parametrize("spelling", ["BATTery", "BATTary", "battery"])
    @pytest.mark.asyncio
    async def test_both_of_rigols_battery_spellings_work(self, spelling):
        """The guide spells it BATTery here and BATTary in the
        subsystem. A caller should not have to know which."""
        load = driver()
        await load.set_function_mode(spelling)
        assert ":SOUR:FUNC:MODE BATT" in commands(load)

    @pytest.mark.asyncio
    async def test_an_unknown_mode_is_refused_before_it_is_sent(self):
        load = driver()
        with pytest.raises(SetpointRefused) as refused:
            await load.set_function_mode("TURBO")
        assert "TURBO" in str(refused.value)
        assert not commands(load), "it sent something anyway"

    @pytest.mark.asyncio
    async def test_the_query_short_forms_read_back(self):
        """The query answers in short forms, which is what it has to
        return so the answer can be handed straight back to the setter."""
        for raw, expected in (("FIX", "FIX"), ("WAV", "WAV"),
                              ("BATT", "BATT"), ("LIST", "LIST"),
                              ("OCP", "OCP"), ("OPP", "OPP")):
            load = driver(answers={":SOUR:FUNC:MODE?": raw})
            assert await load.get_function_mode() == expected

    @pytest.mark.asyncio
    async def test_a_reading_round_trips(self):
        """Whatever the query returns, the setter must accept."""
        for raw in ("FIX", "WAV", "BATT", "LIST", "OCP", "OPP"):
            load = driver(answers={":SOUR:FUNC:MODE?": raw})
            await load.set_function_mode(await load.get_function_mode())
            assert any("FUNC:MODE" in c for c in commands(load))

    @pytest.mark.asyncio
    async def test_a_nonsense_answer_is_not_guessed_at(self):
        load = driver(answers={":SOUR:FUNC:MODE?": "SOMETHING"})
        with pytest.raises(ValueError):
            await load.get_function_mode()


class TestTheBatterySubsystemUsesTheShortForm:
    """BATTary/BATTery both abbreviate to BATT, so every battery
    command is sent short on purpose."""

    @pytest.mark.parametrize("name", [
        "battery_level", "battery_range", "battery_von",
        "battery_stop_volts", "battery_stop_ah", "battery_stop_time",
    ])
    @pytest.mark.asyncio
    async def test_no_battery_command_gambles_on_the_spelling(self, name):
        load = driver()
        await load.set_function_parameter(name, 1.0)
        sent = commands(load)[-1]
        assert ":SOUR:BATT" in sent, sent
        assert "BATTERY" not in sent.upper().replace(":SOUR:BATT", "")
        assert "BATTARY" not in sent.upper()


class TestTheFunctionParameters:
    @pytest.mark.parametrize("name,scpi", [
        ("ocp_start", ":SOUR:OCP:ISET"),
        ("ocp_step", ":SOUR:OCP:IST"),
        ("ocp_trip_volts", ":SOUR:OCP:VOCP"),
        ("opp_start", ":SOUR:OPP:PSET"),
        ("opp_trip_volts", ":SOUR:OPP:VOPP"),
        ("battery_stop_volts", ":SOUR:BATT:VST"),
        ("list_count", ":SOUR:LIST:COUN"),
    ])
    @pytest.mark.asyncio
    async def test_each_goes_to_its_own_command(self, name, scpi):
        load = driver()
        await load.set_function_parameter(name, 2.0)
        assert f"{scpi} 2.0" in commands(load)

    @pytest.mark.asyncio
    async def test_a_reading_comes_back_as_a_number(self):
        load = driver(answers={":SOUR:OCP:ISET?": "1.234"})
        assert await load.get_function_parameter("ocp_start") == pytest.approx(1.234)

    @pytest.mark.asyncio
    async def test_an_unknown_parameter_is_refused(self):
        load = driver()
        with pytest.raises(SetpointRefused):
            await load.set_function_parameter("ocp_enthusiasm", 1.0)
        assert not commands(load)

    @pytest.mark.parametrize("name,too_big", [
        ("ocp_max", 41.0),          # DL3021A is a 40 A load
        ("opp_max", 201.0),         # ...and 200 W
        ("ocp_trip_volts", 151.0),  # ...and 150 V
    ])
    @pytest.mark.asyncio
    async def test_over_the_loads_rating_is_refused(self, name, too_big):
        load = driver()
        with pytest.raises(SetpointRefused):
            await load.set_function_parameter(name, too_big)
        assert not commands(load), "it sent a value the load cannot do"

    @pytest.mark.asyncio
    async def test_negative_is_refused(self):
        load = driver()
        with pytest.raises(SetpointRefused):
            await load.set_function_parameter("ocp_start", -1.0)

    @pytest.mark.asyncio
    async def test_a_parameter_with_no_rating_is_left_to_the_load(self):
        """The guide gives no ceiling for the timers, so inventing one
        here would refuse settings the instrument accepts."""
        load = driver()
        await load.set_function_parameter("ocp_timeout", 9999.0)
        assert ":SOUR:OCP:TOCP 9999.0" in commands(load)


class TestRangesStillRefuseWhileSinking:
    """Switching range moves the shunt whichever mode asked for it, so
    the user guide's CAUTION covers the battery and OCP ranges exactly
    as it covers :SOUR:CURR:RANG.
    """

    @pytest.mark.parametrize("name", ["battery_range", "ocp_range",
                                      "list_range"])
    @pytest.mark.asyncio
    async def test_it_refuses_with_the_input_on(self, name):
        load = driver(input_on=True)
        with pytest.raises(SetpointRefused) as refused:
            await load.set_function_parameter(name, 4.0)
        assert "input" in str(refused.value).lower()
        assert not any("RANG" in c for c in commands(load))

    @pytest.mark.asyncio
    async def test_a_non_range_parameter_is_not_blocked(self):
        """Only the ranges carry the hazard. Refusing everything while
        sinking would make the test modes unconfigurable in exactly the
        state you want to configure them from."""
        load = driver(input_on=True)
        await load.set_function_parameter("ocp_start", 1.0)
        assert ":SOUR:OCP:ISET 1.0" in commands(load)


class TestTheBatteryCutoffs:
    @pytest.mark.asyncio
    async def test_each_switch_is_its_own_command(self):
        load = driver()
        await load.set_battery_cutoffs(volts=True, capacity=False, time=True)
        sent = commands(load)
        assert ":SOUR:BATT:VENabstop 1" in sent
        assert ":SOUR:BATT:CENabstop 0" in sent
        assert ":SOUR:BATT:TENabstop 1" in sent

    @pytest.mark.asyncio
    async def test_leaving_one_out_leaves_it_alone(self):
        """None means "do not touch". Turning a cut-off off because the
        caller did not mention it would arm a discharge with one less
        thing to stop it."""
        load = driver()
        await load.set_battery_cutoffs(volts=True)
        sent = commands(load)
        assert any("VENabstop" in c for c in sent)
        assert not any("CENabstop" in c for c in sent)
        assert not any("TENabstop" in c for c in sent)

    @pytest.mark.asyncio
    async def test_they_read_back(self):
        load = driver(answers={"VENabstop?": "1", "CENabstop?": "0",
                               "TENabstop?": "1"})
        armed = await load.get_battery_cutoffs()
        assert armed == {"volts": True, "capacity": False, "time": True}

    @pytest.mark.asyncio
    async def test_an_unreadable_switch_is_none_not_false(self):
        """Reporting an unknown cut-off as disarmed is the dangerous
        direction to be wrong in."""
        load = driver()

        async def broken(command):
            if "abstop" in command:
                raise OSError("no reply")
            return '0,"No error"'
        load._query = broken

        armed = await load.get_battery_cutoffs()
        assert armed["volts"] is None


class TestTheBatteryResults:
    @pytest.mark.asyncio
    async def test_it_reads_capacity_energy_and_time(self):
        load = driver(answers={":MEAS:CAP?": "2.5", ":MEAS:WATT?": "11.25",
                               ":MEAS:DISC?": "3600"})
        results = await load.get_battery_results()
        assert results["capacity_ah"] == pytest.approx(2.5)
        assert results["watt_hours"] == pytest.approx(11.25)
        assert results["discharge_seconds"] == pytest.approx(3600)

    @pytest.mark.asyncio
    async def test_an_unreadable_result_is_none(self):
        load = driver()

        async def broken(command):
            if ":MEAS:" in command:
                raise OSError("no reply")
            return '0,"No error"'
        load._query = broken

        assert (await load.get_battery_results())["capacity_ah"] is None


class TestTheList:
    @pytest.mark.asyncio
    async def test_a_step_sets_level_width_and_slew(self):
        load = driver()
        await load.set_list_step(3, level=1.5, width=0.2, slew=0.5)
        sent = commands(load)
        assert ":SOUR:LIST:LEV 3,1.5" in sent
        assert ":SOUR:LIST:WID 3,0.2" in sent
        assert ":SOUR:LIST:SLEW 3,0.5" in sent

    @pytest.mark.asyncio
    async def test_only_what_was_asked_for_is_sent(self):
        load = driver()
        await load.set_list_step(1, level=1.0)
        sent = commands(load)
        assert any("LEV" in c for c in sent)
        assert not any("WID" in c for c in sent)

    @pytest.mark.asyncio
    async def test_steps_are_numbered_from_one(self):
        """As the front panel numbers them. Step 0 would silently
        address a step that is not the one the operator is looking at."""
        load = driver()
        with pytest.raises(SetpointRefused):
            await load.set_list_step(0, level=1.0)

    @pytest.mark.asyncio
    async def test_a_step_reads_back(self):
        load = driver(answers={":SOUR:LIST:LEV?": "1.5",
                               ":SOUR:LIST:WID?": "0.2",
                               ":SOUR:LIST:SLEW?": "0.5"})
        step = await load.get_list_step(2)
        assert step["level"] == pytest.approx(1.5)
        assert step["width"] == pytest.approx(0.2)

    @pytest.mark.asyncio
    async def test_the_list_has_its_own_regulation_mode(self):
        load = driver()
        await load.set_list_mode("CV")
        assert ":SOUR:LIST:MODE CV" in commands(load)

    @pytest.mark.asyncio
    async def test_an_unknown_list_mode_is_refused(self):
        load = driver()
        with pytest.raises(SetpointRefused):
            await load.set_list_mode("CX")
        assert not commands(load)

    @pytest.mark.asyncio
    async def test_the_end_state_is_last_or_off(self):
        load = driver()
        await load.set_list_end_state(True)
        assert ":SOUR:LIST:END LAST" in commands(load)

        load = driver()
        await load.set_list_end_state(False)
        assert ":SOUR:LIST:END OFF" in commands(load)

    @pytest.mark.asyncio
    async def test_the_end_state_reads_back(self):
        load = driver(answers={":SOUR:LIST:END?": "LAST"})
        assert await load.get_list_end_state() is True
        load = driver(answers={":SOUR:LIST:END?": "OFF"})
        assert await load.get_list_end_state() is False


class TestTheApiCanReachAllOfIt:
    @pytest.mark.parametrize("action,args", [
        ("set_function_mode", {"function_mode": "OCP"}),
        ("set_function_parameter", {"name": "ocp_start", "value": 1.0}),
        ("set_battery_cutoffs", {"volts": True}),
        ("set_list_step", {"step": 1, "level": 1.0}),
        ("set_list_mode", {"mode": "CC"}),
        ("set_list_end_state", {"hold_last": True}),
    ])
    @pytest.mark.asyncio
    async def test_the_setters_are_dispatched(self, action, args):
        load = driver()
        await load.execute_command(action, args)
        assert commands(load), f"{action} reached the instrument as nothing"

    @pytest.mark.parametrize("action", [
        "get_function_mode", "get_battery_cutoffs", "get_battery_results",
        "get_list_mode", "get_list_end_state",
    ])
    @pytest.mark.asyncio
    async def test_the_getters_are_dispatched(self, action):
        load = driver(answers={":SOUR:FUNC:MODE?": "FIX",
                               ":SOUR:LIST:MODE?": "CC",
                               ":SOUR:LIST:END?": "OFF"})
        await load.execute_command(action, {})


class TestTheProtectionStatus:
    """OCP and OPP are setters all the way down -- the command tree has
    no query for the current a DUT tripped at, and no pass/fail. The
    questionable status register's overcurrent and overpower flags are
    the only result a caller can read back.
    """

    @pytest.mark.asyncio
    async def test_it_decodes_the_overcurrent_flag(self):
        load = driver(answers={":STAT:QUES:COND?": "2"})
        status = await load.get_protection_status()
        assert status["over_current"] is True
        assert status["over_power"] is False

    @pytest.mark.asyncio
    async def test_it_decodes_several_at_once(self):
        load = driver(answers={":STAT:QUES:COND?": "10"})   # 2 | 8
        status = await load.get_protection_status()
        assert status["over_current"] is True
        assert status["over_power"] is True

    @pytest.mark.asyncio
    async def test_a_clear_register_is_all_false(self):
        load = driver(answers={":STAT:QUES:COND?": "0"})
        status = await load.get_protection_status()
        assert not any(v for k, v in status.items() if k != "raw")

    @pytest.mark.asyncio
    async def test_the_raw_value_comes_back_too(self):
        """The guide's bit table is only legible for the low bits, so a
        caller that knows better than we do gets the number."""
        load = driver(answers={":STAT:QUES:COND?": "8192"})
        assert (await load.get_protection_status())["raw"] == 8192

    @pytest.mark.asyncio
    async def test_the_api_can_ask(self):
        load = driver(answers={":STAT:QUES:COND?": "0"})
        assert "raw" in await load.execute_command("get_protection_status", {})


class TestWhatTheBenchFound:
    """Three things the mocks could not have found, all from the probe
    against DL3B268M00049 on 2026-09-25.
    """

    @pytest.mark.asyncio
    async def test_a_mode_that_does_not_take_is_not_reported_as_success(self):
        """The load accepted LIST and BATT, then from BATT took OCP,
        OPP and FIX in turn without a murmur -- clean error queue every
        time -- and stayed in BATT throughout.

        An unchecked write here is a mode switch that reports success
        and does nothing, which is how the trigger bug and the
        short-form :SOUR:FUNC bug both looked.
        """
        load = driver(answers={":SOUR:FUNC:MODE?": "BATT"})
        with pytest.raises(Exception) as rejected:
            await load.set_function_mode("FIX")

        said = str(rejected.value).lower()
        assert "batt" in said, said
        assert "set_mode" in said, "it does not say how to get out"

    @pytest.mark.asyncio
    async def test_a_mode_that_does_take_is_quiet(self):
        load = driver(answers={":SOUR:FUNC:MODE?": "LIST"})
        await load.set_function_mode("LIST")

    @pytest.mark.asyncio
    async def test_an_unreadable_confirmation_is_not_a_failure(self):
        """A load that will not answer the read-back has still very
        likely done as it was told; refusing here would turn a flaky
        query into a failed mode switch."""
        load = driver()

        async def no_readback(command):
            if "FUNC:MODE?" in command:
                raise OSError("no reply")
            return '0,"No error"'
        load._query = no_readback

        await load.set_function_mode("LIST")

    @pytest.mark.asyncio
    async def test_none_means_a_function_mode_owns_the_setpoint(self):
        """In battery discharge :SOUR:FUNC? answers NONE. That is not a
        fault and not an unexpected reply -- it is the load saying the
        FUNCtion command is not in charge. Raising on it made get_mode
        fail for the whole time a battery test ran, and took
        get_readings down with it."""
        load = driver(answers={":SOUR:FUNC?": "NONE"})
        assert await load.get_mode() is None

    @pytest.mark.asyncio
    async def test_a_real_mode_still_comes_back(self):
        load = driver(answers={":SOUR:FUNC?": "CC"})
        assert await load.get_mode() == "CC"

    @pytest.mark.asyncio
    async def test_genuine_nonsense_still_raises(self):
        load = driver(answers={":SOUR:FUNC?": "BANANA"})
        with pytest.raises(ValueError):
            await load.get_mode()
