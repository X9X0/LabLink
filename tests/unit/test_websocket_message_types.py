"""Registering for a message the server sends must actually work.

``MessageType`` listed twelve members. The server puts thirty-one
different strings in a message's ``"type"`` field. ``register_handler``
accepts only the types pre-seeded into ``_message_handlers`` and
otherwise logs a warning and returns -- so for two thirds of the
protocol, asking to be told about a message quietly did nothing.

``discovery_progress`` is how this surfaced: the server emits it, the
equipment panel wants it, and it worked only because that call site
happened to use ``register_message_handler``, which is documented as
"alias for register_handler" and is in fact the permissive one. Two
functions that differ in whether they silently discard your handler,
described as aliases, is the trap underneath the missing enum entry.

So there are three things to hold here: the enum matches what the
server sends, the handler table is derived from the enum rather than
hand-listed beside it, and registration is never a silent no-op.
"""

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from client.utils.websocket_manager import MessageType, WebSocketManager

REPO = Path(__file__).resolve().parents[2]

#: Types the server emits that are not addressed to a client handler --
#: request-scoped replies and test scaffolding.
NOT_BROADCAST = {"test"}


def types_the_server_sends():
    """Every literal the server puts in a message's "type" field."""
    found = set()
    for path in (REPO / "server").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        found |= set(re.findall(r'"type":\s*"([a-z_]+)"', text))
    return found - NOT_BROADCAST


class TestTheEnumMatchesTheProtocol:
    def test_every_type_the_server_sends_is_named(self):
        known = {member.value for member in MessageType}
        missing = sorted(types_the_server_sends() - known)
        assert not missing, (
            "the server sends these and MessageType does not name them, "
            "so register_handler treats them as unknown and a handler "
            f"for one never fires: {missing}")

    def test_discovery_progress_in_particular(self):
        """The one that surfaced it."""
        assert MessageType.DISCOVERY_PROGRESS.value == "discovery_progress"


class TestTheHandlerTableIsDerivedNotCopied:
    def test_every_member_has_a_slot(self):
        manager = WebSocketManager("localhost", 8000)
        missing = [m.value for m in MessageType
                   if m.value not in manager._message_handlers]
        assert not missing, (
            f"the table drifted from the enum again: {missing}")

    def test_it_is_not_a_hand_written_list(self):
        """A literal dict here is what drifted last time."""
        import inspect

        source = inspect.getsource(WebSocketManager.__init__)
        assert "for member in MessageType" in source, (
            "the handler table is hand-listed, so the next message type "
            "added to the enum will be missing from it")


class TestRegisteringIsNeverASilentNoOp:
    def test_a_known_type_registers(self):
        manager = WebSocketManager("localhost", 8000)
        called = []
        manager.register_handler(MessageType.DISCOVERY_PROGRESS,
                                 called.append)
        assert called is not None
        assert len(manager._message_handlers["discovery_progress"]) == 1

    def test_an_unrecognised_type_is_still_registered(self, caplog):
        """Warn, because it is probably a typo. Do not discard it."""
        manager = WebSocketManager("localhost", 8000)
        manager.register_handler("something_new", lambda m: None)

        assert len(manager._message_handlers["something_new"]) == 1, (
            "the handler was dropped; that is the original bug, which "
            "cost one warning at startup and silence thereafter")

    def test_the_two_entry_points_agree(self):
        """They are documented as aliases, so they must behave alike."""
        by_enum = WebSocketManager("localhost", 8000)
        by_string = WebSocketManager("localhost", 8000)

        by_enum.register_handler("job_started", lambda m: None)
        by_string.register_message_handler("job_started", lambda m: None)

        assert (len(by_enum._message_handlers["job_started"])
                == len(by_string._message_handlers["job_started"]) == 1)


class TestDispatchFindsTheHandler:
    @pytest.mark.asyncio
    async def test_a_registered_handler_receives_its_message(self):
        """End to end through the dispatch path, not just the table."""
        manager = WebSocketManager("localhost", 8000)
        seen = []
        manager.register_handler(MessageType.DISCOVERY_PROGRESS, seen.append)

        await manager._handle_message(
            {"type": "discovery_progress", "data": {"percent": 40}})

        assert seen and seen[0]["data"]["percent"] == 40, (
            "the message arrived and nothing was called")
