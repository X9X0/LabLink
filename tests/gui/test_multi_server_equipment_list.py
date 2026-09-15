"""One list, every bench.

The Equipment and Control tabs listed whatever the single active connection
returned, so the other Pi's instruments were invisible until you switched the
dropdown. They now fan out over every connected server.

Three properties matter, and all three are easy to get wrong:

- instruments from both servers appear together, each remembering where it
  came from, so a command goes to the bench the operator clicked on;
- the server is named only once there is more than one, because on a
  single-Pi bench the suffix is noise on every row;
- one unreachable server costs its own rows and nothing else. Fanning out
  turns a single failure into a failure on every refresh, so this must
  degrade quietly rather than empty the list or raise a dialog.
"""

import asyncio
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication

    from client.ui import control_panel as control_panel_module
    from client.ui import equipment_panel as equipment_panel_module
    from client.ui.control_panel import ControlPanel
    from client.ui.equipment_panel import EquipmentPanel

    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not GUI_AVAILABLE, reason="PyQt6 is required for panel tests"
)


class FakeClient:
    """A server that lists instruments, or refuses to."""

    def __init__(self, *equipment, unreachable=False):
        self.equipment = list(equipment)
        self.unreachable = unreachable
        self.commands = []

    def list_equipment(self):
        if self.unreachable:
            raise ConnectionError("server did not answer")
        return self.equipment

    def send_command(self, equipment_id, command, params):
        self.commands.append((equipment_id, command, params))
        return {"success": True, "data": {}}


def supply(equipment_id, model="1685B"):
    return {
        "id": equipment_id,
        "model": model,
        "type": "power_supply",
        "manufacturer": "B&K Precision",
        "connected": True,
    }


class FakeRegistry:
    def __init__(self, clients):
        self._clients = clients

    def connected_clients(self):
        return dict(self._clients)

    def get_client(self, name):
        return self._clients.get(name)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def registry(monkeypatch):
    """Point both panels at a registry we control."""
    def use(clients):
        fake = FakeRegistry(clients)
        for module in (equipment_panel_module, control_panel_module):
            monkeypatch.setattr(module, "get_server_manager", lambda: fake)
        return fake
    return use


def _run(panel, method_name, *args):
    """Drive a qasync asyncSlot without a running qasync loop.

    The slots under test are decorated, so calling them only schedules a task
    on a loop the test does not run. asyncSlot keeps the original coroutine on
    __wrapped__, and `call_blocking` is `asyncio.to_thread`, which is happy
    under a plain `asyncio.run`.
    """
    method = getattr(type(panel), method_name)
    coroutine = getattr(method, "__wrapped__", method)
    asyncio.run(coroutine(panel, *args))


def _drain(qapp):
    for _ in range(6):
        qapp.processEvents()


def _rows(widget):
    return [widget.item(i).text() for i in range(widget.count())]


class TestTheEquipmentTabSpansServers:
    def test_both_servers_appear_in_one_list(self, qapp, registry):
        registry({
            "Lab Server": FakeClient(supply("ps_1", "1685B")),
            "Bench 2": FakeClient(supply("ps_2", "9205B")),
        })
        panel = EquipmentPanel()

        _run(panel, "refresh")
        _drain(qapp)

        assert len(panel.equipment_list) == 2
        assert {eq.server_name for eq in panel.equipment_list} == {
            "Lab Server", "Bench 2",
        }

    def test_the_server_is_named_when_there_are_two(self, qapp, registry):
        registry({
            "Lab Server": FakeClient(supply("ps_1", "1685B")),
            "Bench 2": FakeClient(supply("ps_2", "9205B")),
        })
        panel = EquipmentPanel()

        _run(panel, "refresh")
        _drain(qapp)

        rows = _rows(panel.equipment_list_widget)
        assert any("Lab Server" in row for row in rows)
        assert any("Bench 2" in row for row in rows)

    def test_a_single_server_is_not_labelled(self, qapp, registry):
        """The suffix would be on every row and tell the operator nothing."""
        registry({"Lab Server": FakeClient(supply("ps_1", "1685B"))})
        panel = EquipmentPanel()

        _run(panel, "refresh")
        _drain(qapp)

        assert all("Lab Server" not in row for row in _rows(panel.equipment_list_widget))

    def test_the_same_id_on_two_servers_produces_two_rows(self, qapp, registry):
        """Ids are unique per server; matching on one alone loses a row."""
        registry({
            "Lab Server": FakeClient(supply("ps_36509eb5")),
            "Bench 2": FakeClient(supply("ps_36509eb5")),
        })
        panel = EquipmentPanel()

        _run(panel, "refresh")
        _drain(qapp)

        assert panel.equipment_list_widget.count() == 2
        keys = {eq.key for eq in panel.equipment_list}
        assert len(keys) == 2


class TestOneServerGoingAwayIsSurvivable:
    def test_the_reachable_server_still_lists(self, qapp, registry):
        registry({
            "Lab Server": FakeClient(unreachable=True),
            "Bench 2": FakeClient(supply("ps_2", "9205B")),
        })
        panel = EquipmentPanel()

        _run(panel, "refresh")
        _drain(qapp)

        assert [eq.server_name for eq in panel.equipment_list] == ["Bench 2"]

    def test_no_dialog_is_raised(self, qapp, registry, monkeypatch):
        """This runs on a timer; a modal would interrupt the bench repeatedly."""
        raised = []
        monkeypatch.setattr(
            equipment_panel_module.QMessageBox, "warning",
            lambda *a, **k: raised.append(a),
        )
        registry({"Lab Server": FakeClient(unreachable=True)})
        panel = EquipmentPanel()

        _run(panel, "refresh")
        _drain(qapp)

        assert raised == []

    def test_the_missing_server_is_still_reported_somewhere(self, qapp, registry):
        registry({
            "Lab Server": FakeClient(unreachable=True),
            "Bench 2": FakeClient(supply("ps_2")),
        })
        panel = EquipmentPanel()

        _run(panel, "refresh")
        _drain(qapp)

        assert "Lab Server" in panel.equipment_list_widget.toolTip()


class TestTheControlTabDrivesTheRightBench:
    def _panel_with_two_servers(self, qapp, registry):
        lab = FakeClient(supply("ps_36509eb5", "1685B"))
        bench = FakeClient(supply("ps_36509eb5", "9205B"))
        registry({"Lab Server": lab, "Bench 2": bench})

        panel = ControlPanel(client=lab)
        panel._refresh_lock_status = lambda: None
        _run(panel, "refresh_equipment_list")
        _drain(qapp)
        return panel, lab, bench

    def test_both_supplies_are_listed(self, qapp, registry):
        panel, _, _ = self._panel_with_two_servers(qapp, registry)

        assert panel.equipment_list_widget.count() == 2

    def test_a_setpoint_goes_to_the_selected_instruments_server(self, qapp, registry):
        """The point of the whole change: not the dropdown's server."""
        panel, lab, bench = self._panel_with_two_servers(qapp, registry)

        on_bench = next(
            eq for eq in panel.equipment_list if eq.server_name == "Bench 2"
        )
        panel.selected_equipment = on_bench
        _run(panel, "_send_voltage_command", 12.0)
        _drain(qapp)

        assert [c[1] for c in bench.commands] == ["set_voltage"]
        assert lab.commands == [], "the command went to the wrong bench"

    def test_the_active_client_is_used_when_nothing_names_a_server(
        self, qapp, registry
    ):
        """Single-server behaviour has to survive unchanged."""
        lab = FakeClient(supply("ps_1"))
        registry({})
        panel = ControlPanel(client=lab)
        panel._refresh_lock_status = lambda: None
        _run(panel, "refresh_equipment_list")
        _drain(qapp)

        panel.selected_equipment = panel.equipment_list[0]
        _run(panel, "_send_voltage_command", 5.0)
        _drain(qapp)

        assert [c[1] for c in lab.commands] == ["set_voltage"]
