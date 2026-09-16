"""An instrument can be removed from the register, not just disconnected.

The register only ever grew. Connecting remembered an instrument and nothing
removed it, so a bench accumulated an entry for every resource string it had
ever seen. The DS1054Z that moved from USB to LAN appeared twice -- the id is
derived from the resource string, so the two links are two ids -- and the
stale USB entry could not be cleared from the UI or the API.

``EquipmentInventory.forget`` existed the whole time, with the docstring
"Drop an instrument, for when it is deliberately removed", and was called by
nothing.
"""

import asyncio

import pytest

from server.equipment.inventory import EquipmentInventory


def _manager(entries, open_ids=()):
    """The real EquipmentManager.forget_device, on a stand-in instance.

    Constructed with __new__ because the real __init__ opens resource
    managers and starts discovery; forget_device touches only these three
    attributes, so this exercises the real code without a bench.
    """
    from server.equipment.manager import EquipmentManager

    manager = EquipmentManager.__new__(EquipmentManager)
    manager.inventory = _FakeInventory(entries)
    manager.equipment = {i: object() for i in open_ids}
    manager._lock = asyncio.Lock()
    return manager


@pytest.mark.unit
def test_the_real_manager_refuses_to_forget_a_connected_instrument():
    """Removing an open instrument would strand the session."""
    manager = _manager({"scope_1": {"id": "scope_1"}}, open_ids=["scope_1"])

    with pytest.raises(ValueError, match="connected"):
        asyncio.run(manager.forget_device("scope_1"))
    assert "scope_1" in manager.inventory, "the entry must survive a refusal"


@pytest.mark.unit
def test_a_disconnected_instrument_is_forgotten():
    manager = _manager({"scope_usb": {"id": "scope_usb"},
                        "scope_lan": {"id": "scope_lan"}})

    assert asyncio.run(manager.forget_device("scope_usb")) is True
    assert "scope_usb" not in manager.inventory
    # Only the one asked for.
    assert "scope_lan" in manager.inventory


@pytest.mark.unit
def test_forgetting_something_unknown_says_so_rather_than_pretending():
    manager = _manager({})

    assert asyncio.run(manager.forget_device("nope")) is False


class _FakeInventory:
    """The slice of EquipmentInventory that forget_device touches."""

    def __init__(self, entries):
        self._entries = dict(entries)
        self.saved = 0

    def __contains__(self, equipment_id):
        return equipment_id in self._entries

    def forget(self, equipment_id):
        if self._entries.pop(equipment_id, None) is not None:
            self.saved += 1


@pytest.mark.unit
def test_inventory_forget_removes_and_persists(tmp_path):
    """The layer underneath, which had no caller until now."""
    store = tmp_path / "equipment_inventory.json"
    inventory = EquipmentInventory(path=store)
    inventory.remember(_Info("scope_usb", "USB0::6833::1230::DS1ZA1::0::INSTR"))
    inventory.remember(_Info("scope_lan", "TCPIP0::192.168.91.37::inst0::INSTR"))
    assert len(inventory) == 2

    inventory.forget("scope_usb")
    assert "scope_usb" not in inventory
    assert "scope_lan" in inventory

    # It has to survive a restart, or the entry is back on the next launch --
    # which is the whole point of the inventory being on disk.
    again = EquipmentInventory(path=store)
    assert "scope_usb" not in again
    assert "scope_lan" in again


@pytest.mark.unit
def test_forgetting_an_unknown_id_writes_nothing(tmp_path):
    store = tmp_path / "equipment_inventory.json"
    inventory = EquipmentInventory(path=store)
    inventory.remember(_Info("scope_lan", "TCPIP0::192.168.91.37::inst0::INSTR"))
    before = store.read_text(encoding="utf-8")
    inventory.forget("never_seen")
    assert store.read_text(encoding="utf-8") == before
    assert "scope_lan" in inventory


class _Info:
    """The attributes EquipmentInventory.remember reads off an EquipmentInfo."""

    def __init__(self, equipment_id, resource_string):
        self.id = equipment_id
        self.type = "oscilloscope"
        self.manufacturer = "RIGOL TECHNOLOGIES"
        self.model = "DS1054Z"
        self.serial_number = "DS1ZA171409212"
        self.connection_type = "usb" if resource_string.startswith("USB") else "lan"
        self.resource_string = resource_string
        self.nickname = None
