"""Connect All and Disconnect All, driven rather than inspected.

A server restart drops every instrument and reconnects none of them.
After tonight's update the bench came back with one of four connected
and the rest needing a click each:

    ps_36509eb5   9205B     connected
    ps_56fdd3df   1902B     DISCONNECTED
    scope_cee816af DS1054Z  DISCONNECTED
    load_b8929b78 DL3021A   DISCONNECTED

The interesting behaviour is not "it calls connect" but what it does
with the awkward cases: an instrument that is already connected must be
left alone, one that fails must not stop the others, and disconnecting
must ask once rather than once per instrument.
"""

import asyncio
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# Only the dependency is guarded. The project imports are deliberately
# outside the try: wrapping them in it means a typo in a module path is
# reported as "PyQt6 is required" and the whole file skips green. That
# happened while writing this one -- ConnectionStatus lives in
# client.models.equipment, not shared.models.equipment, and all fourteen
# tests skipped rather than failing.
try:
    import PyQt6.QtWidgets  # noqa: F401

    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(not GUI_AVAILABLE, reason="PyQt6 is required")

if GUI_AVAILABLE:
    from PyQt6.QtWidgets import QApplication, QMessageBox

    from client.models.equipment import ConnectionStatus
    from client.ui.equipment_panel import EquipmentPanel
    from shared.models.equipment import EquipmentType

PANEL = "client.ui.equipment_panel"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class Gear:
    """Enough of an Equipment row for the bulk handlers."""

    def __init__(self, eid, connected, name=None):
        self.equipment_id = eid
        self.name = name or eid
        self.resource_name = f"ASRL/dev/{eid}::INSTR"
        self.equipment_type = EquipmentType.POWER_SUPPLY
        self.model = "1902B"
        self.server_name = "bench"
        self.connection_status = (ConnectionStatus.CONNECTED if connected
                                  else ConnectionStatus.DISCONNECTED)
        self.key = eid


class Server:
    """Records connects and disconnects; can refuse a named instrument."""

    def __init__(self, refuse=(), raise_for=()):
        self.connected = []
        self.disconnected = []
        self.refuse = set(refuse)
        self.raise_for = set(raise_for)

    def connect_equipment(self, resource, kind, model):
        eid = resource.split("/")[-1].split("::")[0]
        if eid in self.raise_for:
            raise OSError(f"{eid} will not open")
        self.connected.append(eid)
        if eid in self.refuse:
            return {"status": "error", "error": "port busy"}
        return {"status": "connected"}

    def disconnect_equipment(self, equipment_id, on_disconnect):
        self.disconnected.append((equipment_id, on_disconnect))
        return {"status": "disconnected"}

    def get_readings(self, equipment_id):
        return {"output_enabled": True}


class Dialogs:
    def __init__(self, answer=None):
        self.shown = []
        self.answer = answer

    def install(self, monkeypatch):
        for kind in ("information", "critical", "warning"):
            def record(_p, title, text, k=kind):
                self.shown.append((k, title, text))
            monkeypatch.setattr(f"{PANEL}.QMessageBox.{kind}", record)

    def text(self):
        return "\n".join(t for _, _, t in self.shown)


async def drive(coro, qapp, limit=8.0):
    loop = asyncio.get_event_loop()
    task = asyncio.ensure_future(coro)
    deadline = loop.time() + limit
    while not task.done() and loop.time() < deadline:
        qapp.processEvents()
        await asyncio.sleep(0.005)
    qapp.processEvents()
    if not task.done():
        task.cancel()
        raise AssertionError("the handler never finished")
    return await task


@pytest.fixture
def panel(qapp):
    made = EquipmentPanel()
    yield made
    made.deleteLater()
    qapp.processEvents()


def _wire(panel, server, gear):
    panel.client = server
    panel.equipment_list = list(gear)
    panel._client_for = lambda equipment: server
    panel._connections = lambda: {"bench": server}
    panel.refresh = lambda: None          # the fan-out is not under test


class TestConnectAll:
    @pytest.mark.asyncio
    async def test_it_connects_only_the_disconnected_ones(self, panel, qapp,
                                                          monkeypatch):
        """Reconnecting a working instrument drops what it was doing."""
        Dialogs().install(monkeypatch)
        server = Server()
        _wire(panel, server, [Gear("a", connected=True),
                              Gear("b", connected=False),
                              Gear("c", connected=False)])

        await drive(panel.connect_all(), qapp)

        assert server.connected == ["b", "c"], (
            f"it reconnected something already up: {server.connected}")

    @pytest.mark.asyncio
    async def test_one_failure_does_not_stop_the_rest(self, panel, qapp,
                                                      monkeypatch):
        """The whole point of a bulk button."""
        Dialogs().install(monkeypatch)
        server = Server(raise_for={"b"})
        _wire(panel, server, [Gear("a", connected=False),
                              Gear("b", connected=False),
                              Gear("c", connected=False)])

        await drive(panel.connect_all(), qapp)

        assert "c" in server.connected, (
            "one instrument that would not open stopped the others")

    @pytest.mark.asyncio
    async def test_it_names_what_failed(self, panel, qapp, monkeypatch):
        dialogs = Dialogs()
        dialogs.install(monkeypatch)
        server = Server(raise_for={"b"})
        _wire(panel, server, [Gear("a", connected=False),
                              Gear("b", connected=False, name="DS1054Z")])

        await drive(panel.connect_all(), qapp)

        assert "DS1054Z" in dialogs.text(), (
            f"the operator is not told which one failed: {dialogs.shown}")

    @pytest.mark.asyncio
    async def test_a_refusal_counts_as_a_failure(self, panel, qapp,
                                                 monkeypatch):
        """A reply that is not 'connected' is not a success."""
        dialogs = Dialogs()
        dialogs.install(monkeypatch)
        server = Server(refuse={"a"})
        _wire(panel, server, [Gear("a", connected=False)])

        await drive(panel.connect_all(), qapp)

        assert "port busy" in dialogs.text()

    @pytest.mark.asyncio
    async def test_the_rows_are_marked_connected(self, panel, qapp,
                                                 monkeypatch):
        Dialogs().install(monkeypatch)
        server = Server()
        gear = [Gear("a", connected=False)]
        _wire(panel, server, gear)

        await drive(panel.connect_all(), qapp)

        assert gear[0].connection_status == ConnectionStatus.CONNECTED

    @pytest.mark.asyncio
    async def test_nothing_to_do_says_so(self, panel, qapp, monkeypatch):
        dialogs = Dialogs()
        dialogs.install(monkeypatch)
        server = Server()
        _wire(panel, server, [Gear("a", connected=True)])

        await drive(panel.connect_all(), qapp)

        assert server.connected == []
        assert dialogs.shown, "it did nothing and said nothing"


class TestDisconnectAll:
    @staticmethod
    def _answer(panel, choice):
        """Stand in for the one-and-only prompt."""
        async def ask(_put_it_up):
            return choice
        panel._ask = ask

    @pytest.mark.asyncio
    async def test_it_asks_once_not_once_per_instrument(self, panel, qapp,
                                                        monkeypatch):
        """Ten dialogs would be worse than the ten clicks they replace."""
        Dialogs().install(monkeypatch)
        asked = []

        async def ask(_put_it_up):
            asked.append(1)
            return "off"
        panel._ask = ask

        server = Server()
        _wire(panel, server, [Gear(x, connected=True) for x in "abcd"])

        await drive(panel.disconnect_all(), qapp)

        assert len(asked) == 1, f"asked {len(asked)} times"
        assert len(server.disconnected) == 4

    @pytest.mark.asyncio
    async def test_cancelling_disconnects_nothing(self, panel, qapp,
                                                  monkeypatch):
        Dialogs().install(monkeypatch)
        self._answer(panel, None)
        server = Server()
        _wire(panel, server, [Gear(x, connected=True) for x in "ab"])

        await drive(panel.disconnect_all(), qapp)

        assert server.disconnected == [], "cancelled and it went ahead"

    @pytest.mark.asyncio
    async def test_the_output_choice_reaches_every_instrument(self, panel,
                                                              qapp,
                                                              monkeypatch):
        """One policy, applied to all of them."""
        Dialogs().install(monkeypatch)
        self._answer(panel, "hold")
        server = Server()
        _wire(panel, server, [Gear(x, connected=True) for x in "abc"])

        await drive(panel.disconnect_all(), qapp)

        assert [state for _, state in server.disconnected] == ["hold"] * 3

    @pytest.mark.asyncio
    async def test_it_leaves_disconnected_ones_alone(self, panel, qapp,
                                                     monkeypatch):
        Dialogs().install(monkeypatch)
        self._answer(panel, "off")
        server = Server()
        _wire(panel, server, [Gear("a", connected=True),
                              Gear("b", connected=False)])

        await drive(panel.disconnect_all(), qapp)

        assert [eid for eid, _ in server.disconnected] == ["a"]

    @pytest.mark.asyncio
    async def test_nothing_connected_says_so(self, panel, qapp, monkeypatch):
        dialogs = Dialogs()
        dialogs.install(monkeypatch)
        self._answer(panel, "off")
        server = Server()
        _wire(panel, server, [Gear("a", connected=False)])

        await drive(panel.disconnect_all(), qapp)

        assert server.disconnected == []
        assert dialogs.shown


class TestTheyBehaveLikeTheRestOfTheClient:
    """Everything converted tonight has to keep these properties."""

    def test_both_are_coroutines(self):
        import inspect

        for name in ("connect_all", "disconnect_all"):
            slot = getattr(EquipmentPanel, name)
            assert inspect.iscoroutinefunction(
                getattr(slot, "__wrapped__", slot)), (
                f"{name} runs on the GUI thread")

    def test_neither_calls_the_client_synchronously(self):
        import inspect
        import re

        for name in ("connect_all", "disconnect_all"):
            slot = getattr(EquipmentPanel, name)
            source = inspect.getsource(getattr(slot, "__wrapped__", slot))
            bare = re.findall(r"(?<!await )(?<!await call_blocking\()"
                              r"client\.\w+\(", source)
            assert not bare, f"{name} blocks the loop on {bare}"

    @pytest.mark.asyncio
    async def test_the_buttons_come_back_after_a_failure(self, panel, qapp,
                                                         monkeypatch):
        """A raise mid-run must not leave them greyed out for ever."""
        Dialogs().install(monkeypatch)
        server = Server(raise_for={"a"})
        _wire(panel, server, [Gear("a", connected=False)])

        await drive(panel.connect_all(), qapp)

        assert panel.connect_all_btn.isEnabled()
        assert panel.disconnect_all_btn.isEnabled()
        assert panel.connect_all_btn.text() == "Connect All"
