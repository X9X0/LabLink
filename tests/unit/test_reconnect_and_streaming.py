"""Three faults that between them stopped a working bench reconnecting.

All three were found after a server update, with the scope and both supplies
still physically fine and the server still holding them open.

**Connecting something already connected.** `connect_device` always built a
new driver and opened the resource, so pressing Connect on an instrument the
server already had open asked libusb to claim an interface the server itself
was holding. It answered "[Errno 16] Resource busy" and the API returned 500 —
a refusal that sounds like broken hardware and is actually the server
colliding with itself.

**A stream the instrument cannot serve.** The streaming loop logged every
exception and slept, so a scope asked for "get_readings" produced
"Unknown command" twice a second forever. Each pass sends the identical
command: what fails once fails every time.

**A datetime in a broadcast.** `send_json` uses a plain json.dumps, which
cannot encode the timestamp every readings payload carries. That raised
inside the per-connection loop, so a serialisation bug was read as the client
hanging up and the websocket was dropped.
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server.equipment.manager import EquipmentManager  # noqa: E402
from server.websocket_server import StreamManager  # noqa: E402


class FakeEquipment:
    def __init__(self, resource_string, connected=True):
        self.resource_string = resource_string
        self.connected = connected


@pytest.fixture
def manager():
    return EquipmentManager()


class TestConnectingWhatIsAlreadyConnected:
    def test_an_open_instrument_is_returned_rather_than_reopened(self, manager):
        """The regression: this is what raised "Resource busy"."""
        resource = "USB0::11975::37376::800886011797210043::0::INSTR"
        manager.equipment["ps_36509eb5"] = FakeEquipment(resource)

        assert manager._already_open(resource) == "ps_36509eb5"

    def test_a_different_instrument_is_not_confused_for_it(self, manager):
        manager.equipment["ps_1"] = FakeEquipment("ASRL/dev/ttyUSB0::INSTR")

        assert manager._already_open("USB0::1::2::3::0::INSTR") is None

    def test_nothing_open_means_a_fresh_connection(self, manager):
        assert manager._already_open("ASRL/dev/ttyUSB0::INSTR") is None

    def test_an_entry_that_died_is_dropped_so_it_can_reopen(self, manager):
        """Unplugged, or the link failed: the caller does want a real open."""
        resource = "ASRL/dev/ttyUSB0::INSTR"
        manager.equipment["ps_stale"] = FakeEquipment(resource, connected=False)

        assert manager._already_open(resource) is None
        assert "ps_stale" not in manager.equipment, "the dead entry was kept"


class TestABroadcastSurvivesATimestamp:
    def test_a_datetime_payload_is_encoded_rather_than_dropping_the_client(self):
        sent = []

        class FakeConnection:
            """Serialises like Starlette's send_json, so the bug can occur.

            A fake that merely records the payload would accept a datetime
            happily and pass against the unfixed code, proving nothing.
            """

            async def send_json(self, payload):
                json.dumps(payload)  # raises on a datetime, as the real one does
                sent.append(payload)

        websockets = StreamManager()
        connection = FakeConnection()
        websockets.active_connections.add(connection)

        asyncio.run(websockets.broadcast({
            "type": "stream_data",
            "equipment_id": "ps_56fdd3df",
            "data": {"voltage": 5.9, "timestamp": datetime(2026, 9, 15, 21, 0)},
        }))

        assert sent, "nothing was sent at all"
        assert connection in websockets.active_connections, (
            "the client was dropped over an encoding problem"
        )
        assert sent[0]["data"]["voltage"] == 5.9
        assert isinstance(sent[0]["data"]["timestamp"], str)

    def test_a_connection_that_really_fails_is_still_dropped(self):
        """The guard must not have made every send look successful."""
        class DeadConnection:
            async def send_json(self, payload):
                raise ConnectionError("client hung up")

        websockets = StreamManager()
        connection = DeadConnection()
        websockets.active_connections.add(connection)

        asyncio.run(websockets.broadcast({"type": "ping"}))

        assert connection not in websockets.active_connections
