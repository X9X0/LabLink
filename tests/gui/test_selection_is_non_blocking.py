"""Selecting an instrument must never wait on the server from the GUI thread.

On the bench, switching the Control tab from a supply to a DS1000Z froze the
window for twenty seconds: the panel read the scope's capabilities and its
full state synchronously (some thirty SCPI queries queued behind the
pollers), and the shell released and acquired locks the same way. These
tests bind a panel and select in the shell under a *running* event loop,
with a client whose every call blocks, and require control back at once.
"""

import asyncio
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from client.models.equipment import ConnectionStatus, Equipment, EquipmentType  # noqa: E402
from client.ui.instruments.base import InstrumentPanel, run_now_or_soon  # noqa: E402
from client.ui.instruments.oscilloscope import OscilloscopePanel  # noqa: E402
from client.ui.instruments.power_supply import PowerSupplyPanel  # noqa: E402

BLOCK_S = 0.3

#: When the stopwatch backstop should fire.
#:
#: This has been tuned twice by chasing the fake's sleep, and both times
#: it flaked. BLOCK_S / 2 was 0.15 s and a clean run on a loaded machine
#: took 0.172 s. Raising it to BLOCK_S, 0.3 s, bought about a tenth of a
#: second of headroom and flaked again in a combined run.
#:
#: The mistake was deriving the bar from the fake rather than from what
#: it is for. The exact evidence is ``called_on_gui_thread``, which names
#: every blocking call that landed on the GUI thread and does not care
#: how fast the machine is; that assertion catches the bug this file is
#: about. The stopwatch only guards the residue -- a stall on the GUI
#: thread that never calls the client at all, such as a long synchronous
#: computation or a modal.
#:
#: So it is sized to what an operator would notice rather than to half a
#: simulated sleep. A stall worth failing over is not 0.3 s; it is the
#: kind that makes the window feel dead. Anything under a second here is
#: measuring the CI box's load, not the code.
BLOCKED_IF_OVER_S = 1.0


def _assert_did_not_block(client, elapsed, what):
    """The GUI thread ran nothing slow.

    Two assertions, and the first is the real one. ``called_on_gui_thread``
    names every blocking call that happened on the GUI thread, which is the
    property exactly and does not depend on how fast the machine is. The
    stopwatch stays as a backstop for blocking that never reaches the client
    -- a long synchronous computation, say -- with a threshold derived from
    what the failure costs rather than from an arbitrary fraction of it.
    """
    assert client.called_on_gui_thread == [], (
        f"{what} made {client.called_on_gui_thread} on the GUI thread")
    assert elapsed < BLOCKED_IF_OVER_S, (
        f"{what} held the GUI thread for {elapsed:.2f}s without calling the "
        f"client, so something else on that path blocks. Note this is the "
        f"backstop, not the main assertion -- if it fires alone, look for "
        f"a synchronous stall that is not a client call")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def cleanup(qapp):
    panels = []
    yield panels
    for panel in panels:
        panel.stop()
        panel.deleteLater()
    qapp.processEvents()


class SlowClient:
    """Every call sleeps like a server whose instrument is busy."""

    def __init__(self):
        self.calls = []
        self.gui_thread = threading.get_ident()
        self.called_on_gui_thread = []

    def _block(self, name, *args):
        self.calls.append((name, args))
        if threading.get_ident() == self.gui_thread:
            self.called_on_gui_thread.append(name)
        time.sleep(BLOCK_S)

    def get_equipment_status(self, equipment_id):
        self._block("get_equipment_status", equipment_id)
        return {"capabilities": {"max_voltage": 30.0, "max_current": 5.0, "num_channels": 4}}

    def send_command(self, equipment_id, command, parameters=None):
        self._block(command, equipment_id)
        if command == "get_setpoints":
            return {"success": True, "data": {"voltage": 12.0, "current": 1.0}}
        if command == "get_state":
            return {"success": True, "data": {"channels": {"1": {"enabled": True, "scale": 2.0, "offset": 0.0}},
                                              "timebase": {"scale": 1e-3, "offset": 0.0},
                                              "trigger": {"source": "CHAN1", "level": 0.5, "sweep": "AUTO"}}}
        return {"success": True, "data": {}}

    def get_readings(self, equipment_id):
        self._block("get_readings", equipment_id)
        return {"voltage": 12.0, "current": 0.5}

    def get_lock_status(self, equipment_id):
        self._block("get_lock_status", equipment_id)
        return {"locked": False}

    def holds_lock(self, status):
        return bool(status.get("locked"))

    def acquire_lock(self, equipment_id, lock_mode="exclusive", timeout_seconds=300):
        self._block("acquire_lock", equipment_id)
        return {"success": True}

    def release_lock(self, equipment_id, force=False):
        self._block("release_lock", equipment_id)
        return {"success": True}


def _equipment(kind=EquipmentType.OSCILLOSCOPE, equipment_id="scope_1"):
    return Equipment(
        equipment_id=equipment_id, name="Bench", equipment_type=kind,
        manufacturer="Rigol", model="DS1054Z", resource_name="USB::x",
        connection_status=ConnectionStatus.CONNECTED,
    )


async def _drain(seconds):
    await asyncio.sleep(seconds)


class TestRunNowOrSoon:
    def test_with_no_loop_it_runs_to_completion(self):
        seen = []

        async def work():
            seen.append(1)

        assert run_now_or_soon(work()) is None
        assert seen == [1]

    def test_with_a_running_loop_it_schedules_and_returns(self):
        seen = []

        async def work():
            await asyncio.sleep(0.01)
            seen.append(1)

        async def main():
            task = run_now_or_soon(work())
            assert isinstance(task, asyncio.Task)
            assert seen == []            # not run yet: the caller was not blocked
            await task
            assert seen == [1]

        asyncio.run(main())


@pytest.mark.parametrize("panel_cls,kind", [
    (OscilloscopePanel, EquipmentType.OSCILLOSCOPE),
    (PowerSupplyPanel, EquipmentType.POWER_SUPPLY),
])
def test_binding_returns_before_the_server_answers(qapp, cleanup, panel_cls, kind):
    client = SlowClient()
    panel = panel_cls()
    cleanup.append(panel)

    async def main():
        started = time.monotonic()
        panel.set_instrument(_equipment(kind), client)
        elapsed = time.monotonic() - started
        _assert_did_not_block(client, elapsed, "set_instrument")
        assert client.calls == []            # nothing has been asked yet
        await _drain(BLOCK_S * 4)
        # ...and then everything was, off the GUI thread.
        names = [name for name, _ in client.calls]
        assert names[0] == "get_equipment_status"
        assert client.called_on_gui_thread == []
        assert panel.capabilities.get("num_channels") == 4 or panel.capabilities.get("max_voltage") == 30.0

    asyncio.run(main())


def test_settings_land_on_the_controls_once_read(qapp, cleanup):
    client = SlowClient()
    panel = PowerSupplyPanel()
    cleanup.append(panel)

    async def main():
        panel.set_instrument(_equipment(EquipmentType.POWER_SUPPLY, "ps_1"), client)
        await _drain(BLOCK_S * 4)
        assert panel.voltage_spinbox.value() == pytest.approx(12.0)
        assert panel.current_spinbox.value() == pytest.approx(1.0)
        # Reading the setpoints back never commands the instrument.
        assert not any(name.startswith("set_") for name, _ in client.calls)

    asyncio.run(main())


def test_a_reply_for_a_superseded_selection_is_dropped(qapp, cleanup):
    """Switch again while the first read-back is in flight: the first answer must not land."""
    client = SlowClient()
    panel = PowerSupplyPanel()
    cleanup.append(panel)
    first = _equipment(EquipmentType.POWER_SUPPLY, "ps_1")
    second = _equipment(EquipmentType.POWER_SUPPLY, "ps_2")

    async def main():
        panel.set_instrument(first, client)
        await _drain(BLOCK_S / 4)
        panel.set_instrument(second, client)
        await _drain(BLOCK_S * 6)
        assert panel.equipment is second
        ids = [args[0] for name, args in client.calls if name == "get_setpoints"]
        # The second instrument's setpoints were read; the first's may have
        # been asked for before the switch but its capabilities were dropped.
        assert "ps_2" in ids

    asyncio.run(main())


def test_the_shell_selects_without_waiting_on_locks(qapp, cleanup):
    from client.ui.control_panel import ControlPanel

    shell = ControlPanel()
    client = SlowClient()
    scope = _equipment()
    supply = _equipment(EquipmentType.POWER_SUPPLY, "ps_1")
    shell.client = client
    shell.equipment_list = [supply, scope]
    shell._client_for = lambda equipment: client  # one server in this test
    shell._selected_client = lambda: client
    shell.equipment_list_widget.clear()
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QListWidgetItem
    for eq in (supply, scope):
        item = QListWidgetItem(eq.name)
        item.setData(Qt.ItemDataRole.UserRole, eq.key)
        shell.equipment_list_widget.addItem(item)

    async def main():
        started = time.monotonic()
        # The shell selects on itemClicked; drive the slot as a click would.
        shell.equipment_list_widget.setCurrentRow(0)
        shell._on_equipment_selected()
        shell.equipment_list_widget.setCurrentRow(1)
        shell._on_equipment_selected()
        elapsed = time.monotonic() - started
        _assert_did_not_block(client, elapsed, "selecting in the shell")
        await _drain(BLOCK_S * 8)
        names = [name for name, _ in client.calls]
        assert "acquire_lock" in names
        assert "release_lock" in names          # the supply's lock was given back
        assert client.called_on_gui_thread == []
        assert shell.selected_equipment is scope

    try:
        asyncio.run(main())
    finally:
        shell._stop_data_acquisition()
        for panel in shell._panels.values():
            cleanup.append(panel)
        shell.deleteLater()


class TestFrontPanelKeysFitTheirLegends:
    """The first version fixed every key at 52x26 and RUN/STOP read \"RUI TO\"."""

    @pytest.mark.parametrize("legend", ["CLEAR", "AUTO", "RUN\nSTOP", "SINGLE", "Measure",
                                        "Acquire", "Storage", "Cursor", "Display", "Utility", "FORCE"])
    def test_key_is_at_least_as_wide_as_its_text(self, qapp, legend):
        from client.ui.instruments.scope_front_panel import PanelKey

        key = PanelKey(legend)
        widest = max(key.fontMetrics().horizontalAdvance(line) for line in legend.split("\n"))
        assert key.minimumWidth() >= widest + 8
        assert key.height() >= key.fontMetrics().height() * len(legend.split("\n"))
        key.deleteLater()

    def test_the_control_area_never_shrinks_below_its_keys(self, qapp):
        from client.ui.instruments.scope_front_panel import FrontPanelView

        view = FrontPanelView(4)
        view.resize(1280, 720)
        view.show()
        qapp.processEvents()
        for key in (view.clear_key, view.auto_key, view.run_stop_key, view.single_key,
                    view.mode_key, view.force_key, *view.channel_keys.values()):
            assert key.width() >= key.minimumWidth()
        # The screen takes the greater part of the width.
        assert view.screen.width() > view.width() * 0.45
        view.deleteLater()
