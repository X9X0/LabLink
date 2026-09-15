"""The bench survives a restart.

The equipment list lived only in memory, so every container restart emptied it
-- and an upgrade restarts containers. The operator was then asked to
rediscover instruments they had already identified.

That is worse than tedious for this hardware. A 1685B does not answer *IDN?,
so discovery infers it from a USB serial bridge; two bridges look alike, and
picking the wrong one means commanding a supply believing it is another one.

Identity is remembered. Connections are not: nothing here opens a port, which
is what makes it safe to load at boot on a shared bench.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.equipment.inventory import SCHEMA, EquipmentInventory  # noqa: E402
from shared.models.equipment import (  # noqa: E402
    ConnectionType,
    EquipmentInfo,
    EquipmentType,
)


def an_instrument(equipment_id="ps_1685b", model="1685B"):
    return EquipmentInfo(
        id=equipment_id,
        type=EquipmentType.POWER_SUPPLY,
        manufacturer="B&K Precision",
        model=model,
        serial_number=None,
        connection_type=ConnectionType.SERIAL,
        resource_string="ASRL/dev/ttyUSB0::INSTR",
        nickname=None,
    )


@pytest.fixture
def inventory(tmp_path):
    return EquipmentInventory(tmp_path / "inventory.json")


class TestItSurvivesARestart:
    def test_an_instrument_is_remembered(self, inventory, tmp_path):
        inventory.remember(an_instrument())

        reopened = EquipmentInventory(tmp_path / "inventory.json")
        assert len(reopened) == 1
        assert reopened.entries()[0]["model"] == "1685B"

    def test_the_resource_string_is_kept(self, inventory, tmp_path):
        """Which port it was on is the part rediscovery would have to guess."""
        inventory.remember(an_instrument())

        entry = EquipmentInventory(tmp_path / "inventory.json").entries()[0]
        assert entry["resource_string"] == "ASRL/dev/ttyUSB0::INSTR"

    def test_re_remembering_the_same_thing_rewrites_nothing(self, inventory):
        inventory.remember(an_instrument())
        before = inventory.path.stat().st_mtime_ns

        inventory.remember(an_instrument())

        assert inventory.path.stat().st_mtime_ns == before

    def test_a_changed_instrument_is_updated(self, inventory):
        inventory.remember(an_instrument())
        inventory.remember(an_instrument(model="1687B"))

        assert len(inventory) == 1
        assert inventory.entries()[0]["model"] == "1687B"

    def test_forgetting_removes_it(self, inventory, tmp_path):
        inventory.remember(an_instrument())
        inventory.forget("ps_1685b")

        assert len(EquipmentInventory(tmp_path / "inventory.json")) == 0

    def test_the_file_is_plain_readable_json(self, inventory):
        """Someone debugging a bench should be able to read it."""
        inventory.remember(an_instrument())

        data = json.loads(inventory.path.read_text(encoding="utf-8"))
        assert data["schema"] == SCHEMA
        assert data["equipment"][0]["manufacturer"] == "B&K Precision"

    def test_enums_are_stored_as_values(self, inventory):
        """So the file does not depend on the python that wrote it."""
        inventory.remember(an_instrument())

        entry = inventory.entries()[0]
        assert isinstance(entry["type"], str)
        assert isinstance(entry["connection_type"], str)


class TestItNeverStopsTheServerStarting:
    def test_a_missing_file_is_an_empty_bench(self, tmp_path):
        assert len(EquipmentInventory(tmp_path / "nothing.json")) == 0

    def test_a_corrupt_file_is_ignored(self, tmp_path):
        path = tmp_path / "inventory.json"
        path.write_text("{ not json", encoding="utf-8")

        assert len(EquipmentInventory(path)) == 0

    def test_an_unknown_schema_is_ignored(self, tmp_path):
        """Half-reading a future format would be worse than starting empty."""
        path = tmp_path / "inventory.json"
        path.write_text(
            json.dumps({"schema": SCHEMA + 99, "equipment": [{"id": "x"}]}),
            encoding="utf-8",
        )

        assert len(EquipmentInventory(path)) == 0

    def test_an_unwritable_location_does_not_raise(self, tmp_path):
        """Failing to remember must not take down a working server."""
        blocked = tmp_path / "a-file"
        blocked.write_text("not a directory", encoding="utf-8")

        inventory = EquipmentInventory(blocked / "inventory.json")
        inventory.remember(an_instrument())  # must not raise

    def test_an_entry_with_no_id_is_skipped(self, inventory):
        class Nameless:
            id = None

        inventory.remember(Nameless())
        assert len(inventory) == 0


class TestTheListShowsRememberedInstruments:
    def _manager(self, tmp_path):
        from server.equipment.manager import EquipmentManager

        manager = EquipmentManager()
        manager.inventory = EquipmentInventory(tmp_path / "inventory.json")
        return manager

    def test_remembered_instruments_are_listed_as_disconnected(self, tmp_path):
        manager = self._manager(tmp_path)
        manager.inventory.remember(an_instrument())

        devices = asyncio.run(manager.get_connected_devices())

        assert len(devices) == 1
        assert devices[0].id == "ps_1685b"
        assert devices[0].connected is False

    def test_listing_opens_no_port(self, tmp_path):
        """Appearing in the list must not touch the hardware -- that is what
        makes it safe to load at boot on a shared bench."""
        manager = self._manager(tmp_path)
        manager.inventory.remember(an_instrument())

        asyncio.run(manager.get_connected_devices())

        assert manager.equipment == {}, "something was opened just by listing"

    def test_an_open_instrument_is_not_listed_twice(self, tmp_path):
        """It is in memory and remembered; it should appear once, as connected."""
        manager = self._manager(tmp_path)
        info = an_instrument()
        manager.inventory.remember(info)

        class Open:
            cached_info = info

        manager.equipment["ps_1685b"] = Open()

        devices = asyncio.run(manager.get_connected_devices())

        assert len(devices) == 1
        assert devices[0].connected is True
