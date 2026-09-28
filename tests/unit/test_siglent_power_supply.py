"""The Siglent SPD supplies.

Verified against an SPD3303X-E on the bench at 192.168.91.191,
firmware 1.01.01.03.12R1 V6.2.

The command set is conventional SCPI, which is exactly what makes it
dangerous: it looks close enough to every other supply in this tree
that the differences read as typos. They are not.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.equipment.base import CommandRejected, SetpointRefused
from server.equipment.siglent_power_supply import (SiglentSPD1000X,
                                                   SiglentSPD3303X,
                                                   spd_driver_for)


def supply(cls=SiglentSPD3303X, answers=None):
    made = cls.__new__(cls)
    made.resource_string = "USB0::62700::5168::SPD3XJGCA01014::0::INSTR"
    made.model = cls.model
    made.num_channels = cls.num_channels
    made.programmable_channels = cls.programmable_channels
    made.has_fixed_rail = cls.has_fixed_rail
    made.max_voltage = cls.max_voltage
    made.max_current = cls.max_current
    made.cached_info = None
    made.connected = True
    made.serial_number = None
    made.firmware_version = None
    made._io_lock = asyncio.Lock()
    made.written = []
    answers = answers or {}

    async def record(command):
        made.written.append(command)

    async def query(command):
        for key, value in answers.items():
            if key in command:
                return value
        if "ERRor" in command or "ERR" in command:
            return '0 No Error'
        if "STATus" in command:
            return "0x4"
        return "0.00"

    made._write = record
    made._query = query
    return made


def sent(psu):
    return list(psu.written)


class TestTheAbbreviationTrap:
    """MEASure:POWEr abbreviates to POWE, not POW.

    The uppercase run in the published spelling is the legal short
    form, and Siglent spells it POWEr. MEAS:POW? -- which is what every
    other supply in this tree uses, and what anyone would write from
    memory -- is an undefined header on this instrument.

    On the bench:

        MEASure:POWEr? CH1  -> '0.00'
        MEASure:POWE?  CH1  -> '0.00'
        MEAS:POW?      CH1  -> no reply at all, then
        SYSTem:ERRor?       -> '-113,Undefined header,MEAS:POW?'

    The failure is a stall rather than an error: the supply does not
    answer, so the caller waits out a full timeout and the link needs
    clearing. That is why every keyword here is spelled out in full.
    """

    @pytest.mark.asyncio
    async def test_power_is_never_asked_for_as_pow(self):
        psu = supply()
        asked = []

        async def watch(command):
            asked.append(command)
            return "0.00"

        psu._query = watch
        await psu.measure(1)

        assert any("POWEr" in c for c in asked), asked
        for command in asked:
            assert ":POW?" not in command.replace("POWEr", ""), (
                "sent the undefined header that stalls this supply: %r"
                % command)

    @pytest.mark.asyncio
    async def test_the_measure_keywords_are_spelled_in_full(self):
        psu = supply()
        asked = []

        async def watch(command):
            asked.append(command)
            return "0.00"

        psu._query = watch
        await psu.measure(1)

        assert "MEASure:VOLTage? CH1" in asked, asked
        assert "MEASure:CURRent? CH1" in asked, asked
        assert "MEASure:POWEr? CH1" in asked, asked


class TestTheChannelIsPartOfTheCommand:
    """Three shapes for the same idea: CH1:VOLTage to set,
    MEASure:VOLTage? CH1 to measure, OUTPut CH1,ON to switch. The third
    takes a comma."""

    @pytest.mark.asyncio
    async def test_setting_uses_the_channel_prefix(self):
        psu = supply()
        await psu.set_voltage(5.0, channel=1)
        assert any(c.startswith("CH1:VOLTage ") for c in sent(psu)), sent(psu)

    @pytest.mark.asyncio
    async def test_the_second_channel_is_addressed_as_ch2(self):
        psu = supply()
        await psu.set_current(0.5, channel=2)
        assert any(c.startswith("CH2:CURRent ") for c in sent(psu)), sent(psu)

    @pytest.mark.asyncio
    async def test_output_takes_a_comma_not_a_space(self):
        psu = supply()
        await psu.set_output(True, channel=1)
        assert "OUTPut CH1,ON" in sent(psu), sent(psu)

    @pytest.mark.asyncio
    async def test_output_off_says_off(self):
        psu = supply()
        await psu.set_output(False, channel=2)
        assert "OUTPut CH2,OFF" in sent(psu), sent(psu)

    @pytest.mark.parametrize("given", [1, "1", "CH1", "ch1"])
    @pytest.mark.asyncio
    async def test_a_channel_may_be_named_either_way(self, given):
        psu = supply()
        await psu.set_voltage(1.0, channel=given)
        assert any("CH1:VOLTage" in c for c in sent(psu)), sent(psu)


class TestTheFixedRail:
    """CH3 is a 2.5/3.3/5 V rail chosen by a front-panel switch. Remote
    control can switch it on and off and nothing else."""

    @pytest.mark.asyncio
    async def test_it_can_be_switched(self):
        psu = supply()
        await psu.set_output(True, channel=3)
        assert "OUTPut CH3,ON" in sent(psu), sent(psu)

    @pytest.mark.asyncio
    async def test_it_refuses_a_voltage_and_says_why(self):
        psu = supply()
        with pytest.raises(SetpointRefused) as caught:
            await psu.set_voltage(3.3, channel=3)
        assert "front panel" in str(caught.value).lower()
        assert not sent(psu), "it sent something before refusing"

    @pytest.mark.asyncio
    async def test_it_refuses_a_current(self):
        psu = supply()
        with pytest.raises(SetpointRefused):
            await psu.set_current(1.0, channel=3)

    @pytest.mark.asyncio
    async def test_it_cannot_be_measured(self):
        psu = supply()
        with pytest.raises(SetpointRefused):
            await psu.measure(3)

    @pytest.mark.asyncio
    async def test_asking_whether_it_is_on_says_it_cannot_tell(self):
        """The status word has bits for CH1 and CH2 only. Returning
        False would be a guess presented as a fact."""
        psu = supply()
        with pytest.raises(CommandRejected):
            await psu.get_output(3)

    @pytest.mark.asyncio
    async def test_a_single_channel_supply_has_no_third_rail(self):
        psu = supply(SiglentSPD1000X)
        with pytest.raises(SetpointRefused):
            await psu.set_output(True, channel=3)


class TestTheStatusWord:
    """SYSTem:STATus? answers in hex and has to be read as bits."""

    @pytest.mark.asyncio
    async def test_the_bench_reading_decodes(self):
        """0x4 is what the bench unit answered with both outputs off:
        bit 2 set, which is the independent-mode field."""
        psu = supply(answers={"STATus": "0x4"})
        status = await psu.get_system_status()
        assert status["coupling"] == "independent"
        assert not status["ch1_on"] and not status["ch2_on"]
        assert not status["ch1_cc"] and not status["ch2_cc"]

    @pytest.mark.asyncio
    async def test_output_and_mode_bits(self):
        # bit 0 CH1 CC, bit 4 CH1 on, bit 5 CH2 on, bit 2 independent
        psu = supply(answers={"STATus": hex(0b0000110101)})
        status = await psu.get_system_status()
        assert status["ch1_cc"] and status["ch1_on"] and status["ch2_on"]

    @pytest.mark.asyncio
    async def test_an_unknown_coupling_is_reported_not_guessed(self):
        """The quick start documents 01 for independent and 10 for
        parallel, and gives no encoding for series. An undocumented
        value is left as None rather than invented."""
        psu = supply(answers={"STATus": hex(0b1100)})
        status = await psu.get_system_status()
        assert status["coupling"] is None
        assert status["coupling_bits"] == 0b11

    @pytest.mark.asyncio
    async def test_a_reply_that_is_not_hex_is_refused(self):
        psu = supply(answers={"STATus": "banana"})
        with pytest.raises(ValueError):
            await psu.get_system_status()


class TestTheErrorQueue:
    """SYSTem:ERRor? answers in two different shapes."""

    @pytest.mark.asyncio
    async def test_a_clean_queue_is_space_separated(self):
        psu = supply(answers={"ERRor": "0 No Error"})
        fault = await psu.get_error()
        assert fault["code"] == 0

    @pytest.mark.asyncio
    async def test_a_fault_is_comma_separated(self):
        psu = supply(answers={"ERRor": "-113,Undefined header,MEAS:POW?"})
        fault = await psu.get_error()
        assert fault["code"] == -113
        assert "Undefined header" in fault["message"]

    @pytest.mark.asyncio
    async def test_a_rejected_setting_raises(self):
        psu = supply(answers={"ERRor": "-113,Undefined header,CH1:VOLT"})
        with pytest.raises(CommandRejected):
            await psu.set_voltage(5.0, channel=1)

    @pytest.mark.asyncio
    async def test_no_cls_is_ever_sent(self):
        """*CLS is not in this instrument's published command list, and
        the documented cost of an undefined header here is a stalled
        link. The queue is drained by reading instead."""
        psu = supply()
        await psu.set_voltage(5.0, channel=1)
        assert not any("*CLS" in c for c in sent(psu)), sent(psu)


class TestSetpointLimits:
    @pytest.mark.asyncio
    async def test_over_the_voltage_rating_is_refused_before_it_is_sent(self):
        psu = supply()
        with pytest.raises(SetpointRefused):
            await psu.set_voltage(40.0, channel=1)
        assert not sent(psu)

    @pytest.mark.asyncio
    async def test_over_the_current_rating_is_refused(self):
        psu = supply()
        with pytest.raises(SetpointRefused):
            await psu.set_current(5.0, channel=1)
        assert not sent(psu)

    @pytest.mark.asyncio
    async def test_negative_is_refused(self):
        psu = supply()
        with pytest.raises(SetpointRefused):
            await psu.set_voltage(-1.0, channel=1)


class TestReadings:
    @pytest.mark.asyncio
    async def test_a_reading_carries_measurement_setpoint_and_state(self):
        psu = supply(answers={
            "MEASure:VOLTage": "4.97", "MEASure:CURRent": "1.20",
            "MEASure:POWEr": "5.96",
            "CH1:VOLTage?": "5.00", "CH1:CURRent?": "2.00",
            "STATus": hex(0b0010100),   # bit 2 independent, bit 4 CH1 on
        })
        data = await psu.get_readings(1)
        assert data.voltage_actual == pytest.approx(4.97)
        assert data.current_actual == pytest.approx(1.20)
        assert data.voltage_set == pytest.approx(5.00)
        assert data.output_enabled is True
        assert data.in_cv_mode is True and data.in_cc_mode is False

    @pytest.mark.asyncio
    async def test_cc_is_reported_when_the_bit_is_set(self):
        psu = supply(answers={"STATus": hex(0b0010101)})   # bit 0 + bit 4
        data = await psu.get_readings(1)
        assert data.in_cc_mode is True and data.in_cv_mode is False

    @pytest.mark.asyncio
    async def test_neither_mode_is_claimed_while_the_output_is_off(self):
        """A supply with its output off is not regulating anything."""
        psu = supply(answers={"STATus": "0x4"})
        data = await psu.get_readings(1)
        assert data.in_cv_mode is False and data.in_cc_mode is False


class TestTheApiCanReachIt:
    @pytest.mark.parametrize("action,args", [
        ("set_voltage", {"voltage": 1.0}),
        ("set_current", {"current": 0.1}),
        ("set_output", {"enabled": False}),
        ("set_tracking", {"mode": "independent"}),
    ])
    @pytest.mark.asyncio
    async def test_the_setters_are_dispatched(self, action, args):
        psu = supply()
        await psu.execute_command(action, args)
        assert sent(psu), f"{action} reached the instrument as nothing"

    @pytest.mark.parametrize("action", ["get_setpoints", "measure",
                                        "get_system_status", "get_error"])
    @pytest.mark.asyncio
    async def test_the_getters_are_dispatched(self, action):
        psu = supply()
        await psu.execute_command(action, {})

    @pytest.mark.asyncio
    async def test_an_unknown_action_is_refused(self):
        psu = supply()
        with pytest.raises(ValueError):
            await psu.execute_command("set_ovp", {"voltage": 1.0})


class TestTracking:
    @pytest.mark.parametrize("given,expected", [
        ("independent", 0), ("series", 1), ("parallel", 2),
        (0, 0), (1, 1), (2, 2),
    ])
    @pytest.mark.asyncio
    async def test_each_mode_sends_its_number(self, given, expected):
        psu = supply()
        await psu.set_tracking(given)
        assert "OUTPut:TRACK %d" % expected in sent(psu), sent(psu)

    @pytest.mark.asyncio
    async def test_an_unknown_mode_is_refused(self):
        psu = supply()
        with pytest.raises(SetpointRefused):
            await psu.set_tracking("sideways")
        assert not sent(psu)


class TestConnectIdentifiesTheSupply:
    """BaseEquipment.connect returns nothing and raises on failure.

    This first shipped as `connected = await super().connect()` with an
    early return when it was falsy -- which is always, because it
    returns None. Identification would have been skipped on every
    connection and the driver would have kept its class defaults, so a
    SPD1168X would have reported itself as a three-channel 32 V supply.
    """

    @pytest.mark.asyncio
    async def test_it_adopts_what_the_supply_reports(self, monkeypatch):
        from server.equipment import base as base_module

        async def no_op(self):
            return None

        monkeypatch.setattr(base_module.BaseEquipment, "connect", no_op)

        psu = supply()
        psu.serial_number = psu.firmware_version = None

        async def idn(command):
            return ("Siglent Technologies,SPD3303X-E,"
                    "SPD3XJGCA01014\x00\x00,1.01.01.03.12R1 V6.2")

        psu._query = idn
        await SiglentSPD3303X.connect(psu)

        assert psu.model == "SPD3303X-E"
        assert psu.serial_number == "SPD3XJGCA01014"
        assert psu.firmware_version == "1.01.01.03.12R1 V6.2"

    @pytest.mark.asyncio
    async def test_an_unreadable_idn_does_not_lose_the_connection(
            self, monkeypatch):
        """A supply that is open and talking should not be thrown away
        because its *IDN? was slow."""
        from server.equipment import base as base_module

        async def no_op(self):
            return None

        monkeypatch.setattr(base_module.BaseEquipment, "connect", no_op)

        psu = supply()
        psu.serial_number = psu.firmware_version = None

        async def broken(command):
            raise RuntimeError("timed out")

        psu._query = broken
        await SiglentSPD3303X.connect(psu)      # must not raise
        assert psu.model == "SPD3303X"          # left at the default


class TestDriverSelection:
    @pytest.mark.parametrize("model,cls", [
        ("SPD3303X", SiglentSPD3303X),
        ("SPD3303X-E", SiglentSPD3303X),
        ("SPD1168X", SiglentSPD1000X),
        ("SPD1305X", SiglentSPD1000X),
    ])
    def test_each_family_gets_its_driver(self, model, cls):
        assert spd_driver_for(model) is cls

    @pytest.mark.parametrize("model", ["SDS1104X-E", "SDM3065X", "DL3021A",
                                       "9205B", None])
    def test_everything_else_gets_none(self, model):
        assert spd_driver_for(model) is None


class TestItDescribesItselfToTheServer:
    """get_info and get_status build models the API validates.

    This shipped wrong and the bench found it. get_info was written
    with field names that do not exist on EquipmentInfo -- name,
    equipment_type, connection_string -- so connecting the supply got
    as far as opening it and then failed with

        500 Server Error: 3 validation errors for EquipmentInfo
        type / connection_type / resource_string: Field required

    Every test above drove the wire protocol and not one called
    get_info, which is how a driver that talks to the instrument
    correctly could still be impossible to connect.
    """

    @pytest.mark.asyncio
    async def test_get_info_validates(self):
        psu = supply()
        psu.serial_number = "SPD3XJGCA01014"
        psu.firmware_version = "1.01.01.03.12R1 V6.2"
        info = await psu.get_info()
        assert info.type.value == "power_supply"
        assert info.resource_string == psu.resource_string
        assert info.connection_type.value == "usb"
        assert info.manufacturer == "Siglent Technologies"

    @pytest.mark.asyncio
    async def test_the_id_is_stable_for_one_resource(self):
        first, second = supply(), supply()
        assert (await first.get_info()).id == (await second.get_info()).id

    @pytest.mark.asyncio
    async def test_a_nul_padded_resource_still_yields_an_id(self):
        """The supply pads its descriptors, and the padding reaches the
        resource string."""
        psu = supply()
        psu.resource_string = (
            "USB0::62700::5168::SPD3XJGCA01014\x00\x00\x00\x00::0::INSTR")
        psu.serial_number = psu.firmware_version = None
        info = await psu.get_info()
        assert info.id.startswith("ps_")

    @pytest.mark.asyncio
    async def test_get_status_validates_and_reports_capabilities(self):
        psu = supply()
        psu.serial_number = psu.firmware_version = None
        psu.connected = True
        psu.cached_info = await psu.get_info()
        status = await psu.get_status()
        assert status.id == psu.cached_info.id
        assert status.connected is True
        assert status.capabilities["channels"] == 3
        assert status.capabilities["programmable_channels"] == [1, 2]


class TestReadingEveryChannelAtOnce:
    """Three channels at 10 Hz cannot be three round trips.

    Measured on the bench: get_readings for one channel is ~83 ms and
    a bare status query ~73 ms, so the hop dominates. Three sequential
    calls miss a 100 ms poll by more than double.
    """

    def _supply(self):
        return supply(answers={
            "MEASure:VOLTage": "4.97", "MEASure:CURRent": "1.20",
            "MEASure:POWEr": "5.96",
            "CH1:VOLTage?": "5.00", "CH1:CURRent?": "2.00",
            "CH2:VOLTage?": "3.30", "CH2:CURRent?": "0.50",
            "STATus": hex(0b0110100),   # independent, CH1 on, CH2 on
        })

    @pytest.mark.asyncio
    async def test_it_returns_every_programmable_channel(self):
        data = await self._supply().get_all_readings()
        assert [c["channel"] for c in data["channels"]] == [1, 2]

    @pytest.mark.asyncio
    async def test_the_status_word_is_read_once_for_all_of_them(self):
        """The saving. Reading it per channel would be three status
        queries for one number that covers all of them."""
        psu = self._supply()
        asked = []
        inner = psu._query

        async def counting(command):
            asked.append(command)
            return await inner(command)

        psu._query = counting
        await psu.get_all_readings()

        assert sum(1 for c in asked if "STATus" in c) == 1, asked

    @pytest.mark.asyncio
    async def test_each_channel_carries_its_own_setpoints(self):
        data = await self._supply().get_all_readings()
        first, second = data["channels"]
        assert first["voltage_set"] == pytest.approx(5.00)
        assert second["voltage_set"] == pytest.approx(3.30)

    @pytest.mark.asyncio
    async def test_the_fixed_rail_is_reported_as_unreadable(self):
        """CH3 answers none of the measurement queries, and does not
        refuse them -- it never replies, so each attempt costs a full
        timeout. Naming it here is what stops a caller trying."""
        data = await self._supply().get_all_readings()
        assert [c["channel"] for c in data["unreadable"]] == [3]
        assert "front panel" in data["unreadable"][0]["why"]

    @pytest.mark.asyncio
    async def test_the_fixed_rail_is_never_measured(self):
        psu = self._supply()
        asked = []
        inner = psu._query

        async def counting(command):
            asked.append(command)
            return await inner(command)

        psu._query = counting
        await psu.get_all_readings()

        assert not any("CH3" in c for c in asked), (
            "asked the fixed rail for something: %s" % asked)

    @pytest.mark.asyncio
    async def test_a_single_channel_supply_has_nothing_unreadable(self):
        psu = supply(SiglentSPD1000X, answers={"STATus": "0x4"})
        data = await psu.get_all_readings()
        assert [c["channel"] for c in data["channels"]] == [1]
        assert data["unreadable"] == []

    @pytest.mark.asyncio
    async def test_coupling_comes_along(self):
        data = await self._supply().get_all_readings()
        assert data["coupling"] == "independent"

    @pytest.mark.asyncio
    async def test_it_is_dispatched(self):
        psu = self._supply()
        data = await psu.execute_command("get_all_readings", {})
        assert data["channels"]
