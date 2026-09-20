"""A refresh asked for while one is in flight must not vanish.

Reported from the bench: the connected dots beside the equipment names do
not appear when equipment is connected, and the Control tab's list takes a
while to catch up.

Both panels guard their fan-out with a single in-flight slot, which is
right for a timer tick -- the answer it would fetch is the one already on
its way. It is wrong for a request that follows an event: connecting an
instrument changes the thing the in-flight fetch already asked about, so
its answer is stale by the time it lands. The handler did call refresh,
the guard refused it, and nothing retried; the dot then waited for the
five-second tick or a tab switch.

Separately, the shell's periodic refresh and its tab-change handler look
for a method called ``refresh``. The Control tab's is called
``refresh_equipment_list``, so it was the one panel they both skipped --
sitting on that tab, nothing refreshed the list at all.
"""

import asyncio
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication

    from client.ui.control_panel import ControlPanel
    from client.ui.equipment_panel import EquipmentPanel
    from client.utils.inflight import (REFRESH_ABANDONED_AFTER, claim_slot,
                                       note_missed, release_slot, take_missed)

    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(not GUI_AVAILABLE, reason="PyQt6 is required")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _Owner:
    pass


class TestTheRecordOfAMissedRequest:
    def test_nothing_is_missed_to_begin_with(self):
        assert take_missed(_Owner(), "_slot") is False

    def test_a_noted_miss_is_reported_once(self):
        owner = _Owner()
        note_missed(owner, "_slot")
        assert take_missed(owner, "_slot") is True
        assert take_missed(owner, "_slot") is False, "a miss was served twice"

    def test_several_misses_coalesce_into_one_pass(self):
        """Three collisions do not mean three extra fetches."""
        owner = _Owner()
        for _ in range(3):
            note_missed(owner, "_slot")
        assert take_missed(owner, "_slot") is True
        assert take_missed(owner, "_slot") is False

    def test_the_record_is_per_slot(self):
        owner = _Owner()
        note_missed(owner, "_readings")
        assert take_missed(owner, "_list") is False
        assert take_missed(owner, "_readings") is True

    def test_claiming_a_slot_is_unchanged(self):
        """The instrument panels guard readings with this; a missed reading
        really is better dropped than run late."""
        owner = _Owner()
        assert claim_slot(owner, "_slot", REFRESH_ABANDONED_AFTER) is True
        assert claim_slot(owner, "_slot", REFRESH_ABANDONED_AFTER) is False
        release_slot(owner, "_slot")
        assert claim_slot(owner, "_slot", REFRESH_ABANDONED_AFTER) is True


class _SlowClient:
    """Answers list_equipment slowly, so a second request collides."""

    def __init__(self, gate):
        self.gate = gate
        self.calls = 0

    def list_equipment(self):
        self.calls += 1
        return []


def _drive(panel, method_name):
    slot = getattr(type(panel), method_name)
    return getattr(slot, "__wrapped__", slot)(panel)


class TestTheEquipmentPanelRunsAMissedRefresh:
    def test_a_collision_is_served_when_the_first_returns(self, qapp):
        """The reported bug: connecting refreshed nothing when it collided."""
        panel = EquipmentPanel()
        client = _SlowClient(None)
        panel.client = client
        panel._connections = lambda: {"srv": client}

        async def scenario():
            first = asyncio.ensure_future(_drive(panel, "refresh"))
            await asyncio.sleep(0)          # let it take the slot
            # Connecting an instrument asks again while that is out.
            await _drive(panel, "refresh")  # refused, and recorded
            await first

        asyncio.run(scenario())
        panel.deleteLater()
        qapp.processEvents()

        assert client.calls >= 2, (
            "the second request was dropped -- this is why the connected dot "
            f"did not appear; the server was asked {client.calls} time(s)")

    def test_an_uncontended_refresh_asks_once(self, qapp):
        panel = EquipmentPanel()
        client = _SlowClient(None)
        panel.client = client
        panel._connections = lambda: {"srv": client}

        asyncio.run(_drive(panel, "refresh"))
        panel.deleteLater()
        qapp.processEvents()

        assert client.calls == 1, f"asked {client.calls} times for one refresh"


class TestTheControlPanelIsRefreshedLikeTheOthers:
    def test_it_answers_to_refresh(self, qapp):
        """The name the periodic timer and the tab-change handler look for."""
        panel = ControlPanel()
        try:
            assert hasattr(panel, "refresh"), (
                "the shell skips this tab entirely: sitting on it, nothing "
                "refreshes the list")
        finally:
            panel.deleteLater()
            qapp.processEvents()

    def test_refresh_is_the_list_refresh(self, qapp):
        panel = ControlPanel()
        try:
            assert ControlPanel.refresh is ControlPanel.refresh_equipment_list
        finally:
            panel.deleteLater()
            qapp.processEvents()

    def test_a_collision_is_served_when_the_first_returns(self, qapp):
        panel = ControlPanel()
        client = _SlowClient(None)
        panel.client = client
        panel._connections = lambda: {"srv": client}

        async def scenario():
            first = asyncio.ensure_future(_drive(panel, "refresh_equipment_list"))
            await asyncio.sleep(0)
            await _drive(panel, "refresh_equipment_list")
            await first

        asyncio.run(scenario())
        panel.deleteLater()
        qapp.processEvents()

        assert client.calls >= 2, (
            f"the second request was dropped; asked {client.calls} time(s)")
