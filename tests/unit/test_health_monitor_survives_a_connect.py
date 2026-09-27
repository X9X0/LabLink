"""Health monitoring must survive the bench changing under it.

Seen on the Pi, every time an instrument was connected:

    ERROR - server.equipment.error_handler - Error in health
    monitoring loop: dictionary changed size during iteration

_check_all_equipment walked equipment_manager.equipment directly and
awaited inside the loop, so connecting or disconnecting anything
mid-pass raised. The log line was the small part: the exception
escaped to _monitor_loop, which caught it and slept, so every
instrument after the mutation went unchecked until the next interval.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.equipment.error_handler import HealthMonitor


class FakeStatus:
    def __init__(self, connected=True):
        self.connected = connected


class FakeEquipment:
    """An instrument whose status query yields to the event loop.

    Yielding is the point: it is the await inside the loop that gives
    a connect the chance to land mid-pass.
    """

    def __init__(self, name, connected=True, on_status=None):
        self.name = name
        self.checked = 0
        self._connected = connected
        self._on_status = on_status
        self.reconnected = 0

    async def get_status(self):
        self.checked += 1
        await asyncio.sleep(0)
        if self._on_status:
            self._on_status()
        return FakeStatus(self._connected)

    async def connect(self):
        self.reconnected += 1


class FakeManager:
    def __init__(self, equipment=None):
        self.equipment = dict(equipment or {})


class TestAConnectDoesNotBreakThePass:
    @pytest.mark.asyncio
    async def test_adding_equipment_mid_pass_does_not_raise(self):
        manager = FakeManager()
        added = FakeEquipment("late")

        def connect_something():
            manager.equipment.setdefault("late", added)

        manager.equipment["first"] = FakeEquipment(
            "first", on_status=connect_something)
        manager.equipment["second"] = FakeEquipment("second")

        await HealthMonitor()._check_all_equipment(manager)   # must not raise

    @pytest.mark.asyncio
    async def test_the_rest_of_the_bench_is_still_checked(self):
        """The real cost of the bug. Everything after the mutation was
        skipped until the next interval."""
        manager = FakeManager()

        def connect_something():
            manager.equipment.setdefault("late", FakeEquipment("late"))

        first = FakeEquipment("first", on_status=connect_something)
        second = FakeEquipment("second")
        third = FakeEquipment("third")
        manager.equipment.update(
            {"first": first, "second": second, "third": third})

        await HealthMonitor()._check_all_equipment(manager)

        assert second.checked == 1, "the instrument after the connect was skipped"
        assert third.checked == 1, "the rest of the pass was abandoned"

    @pytest.mark.asyncio
    async def test_removing_equipment_mid_pass_does_not_raise(self):
        manager = FakeManager()

        def disconnect_something():
            manager.equipment.pop("second", None)

        manager.equipment["first"] = FakeEquipment(
            "first", on_status=disconnect_something)
        manager.equipment["second"] = FakeEquipment("second")
        manager.equipment["third"] = FakeEquipment("third")

        await HealthMonitor()._check_all_equipment(manager)

        assert manager.equipment["third"].checked == 1


class TestSomethingLetGoOfIsLeftAlone:
    """The hazard a snapshot introduces, and why the membership checks
    are there."""

    @pytest.mark.asyncio
    async def test_equipment_removed_before_its_turn_is_not_checked(self):
        manager = FakeManager()
        doomed = FakeEquipment("doomed")

        def disconnect_doomed():
            manager.equipment.pop("doomed", None)

        manager.equipment["first"] = FakeEquipment(
            "first", on_status=disconnect_doomed)
        manager.equipment["doomed"] = doomed

        await HealthMonitor()._check_all_equipment(manager)

        assert doomed.checked == 0

    @pytest.mark.asyncio
    async def test_equipment_removed_while_its_status_was_in_flight_is_not_reconnected(
            self):
        """Reconnecting an instrument the operator has just
        disconnected is worse than skipping it."""
        manager = FakeManager()
        going = FakeEquipment("going", connected=False)

        def remove_itself():
            manager.equipment.pop("going", None)

        going._on_status = remove_itself
        manager.equipment["going"] = going

        await HealthMonitor()._check_all_equipment(manager)

        assert going.reconnected == 0

    @pytest.mark.asyncio
    async def test_a_reused_id_is_not_mistaken_for_the_old_object(self):
        """Presence is not enough -- the id can name a different
        instrument by the time we look again."""
        manager = FakeManager()
        replacement = FakeEquipment("replacement", connected=False)
        original = FakeEquipment("original", connected=False)

        def swap():
            manager.equipment["slot"] = replacement

        original._on_status = swap
        manager.equipment["slot"] = original

        await HealthMonitor()._check_all_equipment(manager)

        assert original.reconnected == 0
        assert replacement.reconnected == 0


class TestOrdinaryCheckingStillWorks:
    @pytest.mark.asyncio
    async def test_a_healthy_instrument_is_recorded(self):
        manager = FakeManager({"one": FakeEquipment("one")})
        monitor = HealthMonitor()

        await monitor._check_all_equipment(manager)

        assert "one" in monitor.equipment_health

    @pytest.mark.asyncio
    async def test_a_disconnected_instrument_is_reconnected(self):
        gone = FakeEquipment("gone", connected=False)
        manager = FakeManager({"gone": gone})

        await HealthMonitor()._check_all_equipment(manager)

        assert gone.reconnected == 1

    @pytest.mark.asyncio
    async def test_one_failing_status_does_not_stop_the_others(self):
        class Broken(FakeEquipment):
            async def get_status(self):
                raise RuntimeError("no reply")

        healthy = FakeEquipment("healthy")
        manager = FakeManager({"broken": Broken("broken"), "healthy": healthy})

        await HealthMonitor()._check_all_equipment(manager)

        assert healthy.checked == 1
