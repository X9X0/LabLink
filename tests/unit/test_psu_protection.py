"""Tests for OVP/OCP support on power supplies (#117).

Covers the three things that make protection different from a setpoint: it is
a control command and so must be gated by the equipment lock, not every driver
implements it, and a protection query a model does not answer must read as
unknown rather than as a limit of zero.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from server.api.equipment import CONTROL_COMMANDS, requires_control
from server.equipment.bk_power_supply import BK1685B
from server.equipment.bk_scpi import BKSCPIPowerSupply


@pytest.fixture
def supply():
    """A 9140 with its transport replaced by a recorder."""
    ps = BKSCPIPowerSupply(MagicMock(), "TCPIP::192.0.2.10::INSTR", model="9140")
    ps.cached_info = None
    ps.writes = []
    ps.replies = {
        "VOLT:PROT?": "12.500", "VOLT:PROT:STAT?": "1", "VOLT:PROT:TRIP?": "0",
        "CURR:PROT?": "2.000", "CURR:PROT:STAT?": "1", "CURR:PROT:TRIP?": "0",
        "CURR:PROT:DEL?": "0.50",
    }

    async def _write(command):
        ps.writes.append(command)

    async def _query(command):
        if command not in ps.replies:
            # What a model that does not implement the header actually does.
            raise RuntimeError(f"undefined header: {command}")
        return ps.replies[command]

    async def _after_write():
        return None

    ps._write, ps._query, ps._after_write = _write, _query, _after_write
    return ps


class TestProtectionCommands:
    """The command strings must match B&K's published SCPI."""

    @pytest.mark.asyncio
    async def test_set_ovp_writes_level_then_arms(self, supply):
        await supply.set_ovp(12.5, channel=1, enabled=True)
        assert "VOLT:PROT 12.5" in supply.writes
        assert "VOLT:PROT:STAT ON" in supply.writes
        # Order matters: arming before the level is set would briefly guard at
        # whatever the previous limit was.
        assert supply.writes.index("VOLT:PROT 12.5") < supply.writes.index(
            "VOLT:PROT:STAT ON"
        )

    @pytest.mark.asyncio
    async def test_set_ocp_sends_the_delay_only_when_given(self, supply):
        await supply.set_ocp(2.0, delay=0.5)
        assert "CURR:PROT:DEL 0.5" in supply.writes

        supply.writes.clear()
        await supply.set_ocp(2.0)
        assert not any("DEL" in w for w in supply.writes), (
            "a model without the delay header must not be sent one"
        )

    @pytest.mark.asyncio
    async def test_disarming_writes_off(self, supply):
        await supply.set_ovp(12.5, enabled=False)
        assert "VOLT:PROT:STAT OFF" in supply.writes

    @pytest.mark.asyncio
    async def test_clear_protection_uses_the_output_subsystem(self, supply):
        await supply.clear_protection()
        assert "OUTP:PROT:CLE" in supply.writes


class TestProtectionReadback:
    """A partial answer is the normal case, not an error."""

    @pytest.mark.asyncio
    async def test_reads_every_field(self, supply):
        state = await supply.get_protection()
        assert state["ovp_level"] == 12.5
        assert state["ovp_enabled"] is True
        assert state["ovp_tripped"] is False
        assert state["ocp_level"] == 2.0
        assert state["ocp_delay"] == 0.5

    @pytest.mark.asyncio
    async def test_a_missing_query_reads_unknown_not_zero(self, supply):
        """The :TRIPped? headers are absent on some models.

        Reporting the trip state as False there would claim the supply is fine
        on evidence nobody collected; reporting the level as 0.0 would show an
        armed guard at zero volts. Both must come back as None.
        """
        del supply.replies["CURR:PROT:TRIP?"]
        del supply.replies["VOLT:PROT?"]

        state = await supply.get_protection()

        assert state["ocp_tripped"] is None
        assert state["ovp_level"] is None
        # The rest of the read survives the gap.
        assert state["ocp_level"] == 2.0
        assert state["ovp_enabled"] is True

    @pytest.mark.asyncio
    async def test_a_trip_is_reported(self, supply):
        supply.replies["CURR:PROT:TRIP?"] = "1"
        state = await supply.get_protection()
        assert state["ocp_tripped"] is True

    @pytest.mark.asyncio
    async def test_selects_the_channel_first(self, supply):
        await supply.get_protection(channel=2)
        assert supply.writes[0] == "INST:NSEL 2"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("action,params,expect_written", [
        ("set_ovp", {"voltage": 1.0}, "VOLT:PROT 1"),
        ("set_ocp", {"current": 1.0}, "CURR:PROT 1"),
        ("clear_protection", {}, "OUTP:PROT:CLE"),
    ])
    async def test_protection_is_reachable_through_execute_command(
        self, supply, action, params, expect_written
    ):
        """The panel reaches the driver through execute_command, not directly.

        A method the dispatch table does not list is unreachable from the API,
        so each one is called the way the panel calls it and checked for the
        command it should have put on the wire.
        """
        await supply.execute_command(action, params)
        assert expect_written in supply.writes

    @pytest.mark.asyncio
    async def test_get_protection_is_reachable_and_returns_state(self, supply):
        state = await supply.execute_command("get_protection", {})
        assert state["ovp_level"] == 12.5

    @pytest.mark.asyncio
    async def test_an_unlisted_action_is_still_rejected(self, supply):
        with pytest.raises(ValueError, match="Unknown command"):
            await supply.execute_command("definitely_not_a_command", {})


class TestLockGating:
    """Protection is control, and must not slip past the equipment lock."""

    @pytest.mark.parametrize("action", ["set_ovp", "set_ocp",
                                        "clear_protection"])
    def test_protection_changes_require_exclusive_control(self, action):
        """Raising an OVP ceiling under another operator's session removes the
        guard on their experiment; clearing a trip re-arms an output that
        latched off for a reason."""
        assert action in CONTROL_COMMANDS
        assert requires_control(action) is True

    def test_reading_protection_stays_open(self):
        """Observers must still be able to see the state of the supply."""
        assert requires_control("get_protection") is False


class TestCapabilityHonesty:
    """A panel decides what to offer from the capability flag."""

    def test_scpi_supplies_advertise_protection(self):
        ps = BKSCPIPowerSupply(MagicMock(), "TCPIP::x::INSTR", model="9140")
        assert ps._capabilities()["supports_protection"] is True

    def test_fixed_width_supplies_do_not(self):
        """The legacy protocol has no OVP/OCP commands at all.

        Advertising them would put controls on screen that look like an armed
        guard and do nothing — worse on a supply than having no controls.
        """
        ps = BK1685B(MagicMock(), "ASRL/dev/ttyUSB0::INSTR")
        assert not hasattr(ps, "set_ovp")
        with pytest.raises(ValueError, match="Unknown command"):
            asyncio.run(ps.execute_command("set_ovp", {"voltage": 5.0}))
