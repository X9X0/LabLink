"""What an instrument is left doing when LabLink lets go of it (issue #198).

The output going off on disconnect was read as an accident of serial wiring --
DTR dropping when the port closes. It is not. `EquipmentManager` commands it,
in `disconnect_device`, because `safe_state_on_disconnect` defaults to True.
The Pi's own logs say so:

    Putting ps_56fdd3df into safe state before disconnect
    Disabled output for ps_56fdd3df
    Disconnected from ASRL/dev/ttyUSB0::INSTR

The original diagnosis inspected `AsyncEquipment.disconnect()` in base.py,
found only `instrument.close()`, and concluded from its absence -- while the
decision was one layer above.

So it is deliberate, and therefore something the operator can be given a say
in. These cover that: the default is unchanged, "hold" sends nothing, and
server shutdown behaves the same way an explicit disconnect does.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server.equipment.manager import EquipmentManager  # noqa: E402


def supply(**kwargs):
    """A power supply double: has set_output, records what it was told."""
    instrument = MagicMock()
    instrument.set_output = AsyncMock()
    instrument.disconnect = AsyncMock()
    for key, value in kwargs.items():
        setattr(instrument, key, value)
    return instrument


def load():
    """An electronic load: set_input rather than set_output."""
    instrument = MagicMock(spec=["set_input", "disconnect"])
    instrument.set_input = AsyncMock()
    instrument.disconnect = AsyncMock()
    return instrument


@pytest.fixture
def manager():
    m = EquipmentManager()
    m.equipment = {}
    return m


@pytest.fixture
def safe_state(monkeypatch):
    """Set the server default; returns a setter."""
    def _set(enabled: bool):
        from server.config import settings as settings_module
        monkeypatch.setattr(
            settings_module.settings, "safe_state_on_disconnect", enabled
        )
    return _set


class TestTheDefaultIsUnchanged:
    """Whatever else this adds, it must not quietly alter today's behaviour."""

    @pytest.mark.asyncio
    async def test_a_supply_output_is_disabled(self, manager, safe_state):
        safe_state(True)
        ps = supply()
        manager.equipment["ps1"] = ps

        with patch("server.diagnostics.diagnostics_manager"):
            await manager.disconnect_device("ps1")

        ps.set_output.assert_awaited_once_with(False)
        ps.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_load_input_is_disabled(self, manager, safe_state):
        safe_state(True)
        el = load()
        manager.equipment["load1"] = el

        with patch("server.diagnostics.diagnostics_manager"):
            await manager.disconnect_device("load1")

        el.set_input.assert_awaited_once_with(False)

    def test_the_setting_still_names_the_default(self, safe_state):
        manager = EquipmentManager()

        safe_state(True)
        assert manager.default_disconnect_policy() == "off"

        safe_state(False)
        assert manager.default_disconnect_policy() == "hold"


class TestHoldSendsNothing:
    @pytest.mark.asyncio
    async def test_the_output_is_left_alone(self, manager, safe_state):
        safe_state(True)          # server default is off; the caller overrides
        ps = supply()
        manager.equipment["ps1"] = ps

        with patch("server.diagnostics.diagnostics_manager"):
            await manager.disconnect_device("ps1", policy="hold")

        ps.set_output.assert_not_awaited()
        ps.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_it_still_disconnects(self, manager, safe_state):
        """Holding the output is not a reason to keep the port open."""
        safe_state(True)
        ps = supply()
        manager.equipment["ps1"] = ps

        with patch("server.diagnostics.diagnostics_manager"):
            await manager.disconnect_device("ps1", policy="hold")

        assert "ps1" not in manager.equipment


class TestAnUnknownPolicyIsRefused:
    @pytest.mark.asyncio
    async def test_it_raises_rather_than_falling_back(self, manager, safe_state):
        """Falling back to the default would turn off an output someone asked
        to keep running."""
        safe_state(True)
        ps = supply()
        manager.equipment["ps1"] = ps

        with pytest.raises(ValueError, match="Unknown disconnect policy"):
            await manager.disconnect_device("ps1", policy="leave_it_alone_please")

        ps.set_output.assert_not_awaited()
        ps.disconnect.assert_not_awaited()
        assert "ps1" in manager.equipment


class TestShutdownAgreesWithDisconnect:
    """The gap this found: stopping the server used to skip the safe state."""

    @pytest.mark.asyncio
    async def test_shutdown_applies_the_policy(self, manager, safe_state):
        safe_state(True)
        ps = supply()
        manager.equipment["ps1"] = ps

        await manager.shutdown()

        ps.set_output.assert_awaited_once_with(False)
        ps.disconnect.assert_awaited_once()
        assert manager.equipment == {}

    @pytest.mark.asyncio
    async def test_shutdown_holds_when_configured_to(self, manager, safe_state):
        safe_state(False)
        ps = supply()
        manager.equipment["ps1"] = ps

        await manager.shutdown()

        ps.set_output.assert_not_awaited()
        ps.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_failing_instrument_does_not_block_shutdown(
        self, manager, safe_state
    ):
        """A shutdown must still shut down."""
        safe_state(True)
        ps = supply()
        ps.set_output.side_effect = RuntimeError("instrument stopped answering")
        manager.equipment["ps1"] = ps

        await manager.shutdown()

        ps.disconnect.assert_awaited_once()
        assert manager.equipment == {}


class TestBaseDisconnectStillSendsNothing:
    """The premise of the whole correction."""

    def test_it_only_closes_the_transport(self):
        source = (
            Path(__file__).resolve().parents[2] / "server" / "equipment" / "base.py"
        ).read_text(encoding="utf-8")
        body = source.split("async def disconnect", 1)[1].split("\n    async def ", 1)[0]

        assert "instrument.close()" in body
        assert "set_output" not in body
        assert "set_input" not in body


class TestTheEndpointReportsFaultsHonestly:
    """Found by driving the API rather than the manager.

    The endpoint wraps its body in `except Exception -> 500`, which caught the
    `HTTPException(400)` raised for an unknown policy and re-raised it as
    `500 {"detail": "400: Unknown disconnect policy ..."}` -- the right message
    inside the wrong status, which a caller cannot tell from a crash.
    """

    def test_http_exceptions_are_not_rewrapped_as_500(self):
        source = (
            Path(__file__).resolve().parents[2] / "server" / "api" / "equipment.py"
        ).read_text(encoding="utf-8")
        body = source.split("async def disconnect_device", 1)[1].split(
            "\n@router.", 1
        )[0]

        assert "except HTTPException:" in body, (
            "a 400 raised inside the try block is re-raised as a 500 without this"
        )
        # rindex, not index: there is an inner `except Exception` around the
        # lock release earlier in the body. The one that matters is the last,
        # which is the catch-all this must precede.
        assert body.index("except HTTPException:") < body.rindex("except Exception")
