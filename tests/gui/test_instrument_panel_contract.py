"""The contract that stops a panel from polling what an instrument cannot answer.

Both polling storms that shipped (the 404 storm in 2.1.4, the 501 storm in
2.2.1) came from one panel polling every instrument as if it were a power
supply. The Control tab now hosts one panel per instrument type, each
declaring what it polls and how fast, stopping itself on a permanent refusal
and never on a transient fault. These tests are the regression guard for
that contract, and for the registry rule that an unknown instrument gets the
generic panel and never the supply dials.
"""

import asyncio
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication

    from client.models.equipment import ConnectionStatus, Equipment, EquipmentType
    from client.ui.control_panel import ControlPanel
    from client.ui.instruments import (GenericInstrumentPanel, InstrumentPanel,
                                       PowerSupplyPanel, panel_class_for,
                                       registered_panels)
    from client.ui.instruments.base import POLL_KINDS, POLL_READINGS

    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(not GUI_AVAILABLE, reason="PyQt6 is required")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _no_timer_outlives_its_test(qapp):
    """Every panel a test starts is stopped and deleted afterwards.

    A running QTimer on a widget that outlives its test, with the
    QApplication later torn down by another module, is a segfault waiting
    for the next Qt call -- which is what happened the first time this file
    ran ahead of tests/unit/test_settings.py.
    """
    created = []
    original_init = InstrumentPanel.__init__

    def tracking_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        created.append(self)

    InstrumentPanel.__init__ = tracking_init
    try:
        yield
    finally:
        InstrumentPanel.__init__ = original_init
        for panel in created:
            try:
                panel.stop()
                panel.deleteLater()
            except RuntimeError:
                pass
        qapp.processEvents()


def _http_error(status_code):
    class _Response:
        def __init__(self, code):
            self.status_code = code

    error = Exception(f"{status_code} from server")
    error.response = _Response(status_code)
    return error


def _equipment(equipment_type=EquipmentType.POWER_SUPPLY, status=ConnectionStatus.CONNECTED):
    return Equipment(
        equipment_id="eq_1", name="Unit", equipment_type=equipment_type,
        manufacturer="Rigol", model="X", resource_name="USB::x",
        connection_status=status,
    )


def _tick(panel):
    """Run one poll tick without a qasync loop (asyncSlot keeps __wrapped__)."""
    method = type(panel)._poll
    coroutine = getattr(method, "__wrapped__", method)
    asyncio.run(coroutine(panel))


class RecordingPanel(InstrumentPanel):
    """A panel that polls exactly what a test tells it to."""

    POLLS = POLL_READINGS
    DEFAULT_INTERVAL_MS = 250
    SETTINGS_TYPE = "test_recording"

    def __init__(self, parent=None):
        self.polls = 0
        self.failure = None
        self.unsupported_shown = 0
        self.not_connected_shown = 0
        super().__init__(parent)

    async def poll(self):
        self.polls += 1
        if self.failure is not None:
            raise self.failure

    def show_unsupported(self):
        self.unsupported_shown += 1

    def show_not_connected(self):
        self.not_connected_shown += 1


class TestTheRegistry:
    def test_every_equipment_type_gets_a_panel(self):
        for equipment_type in EquipmentType:
            assert issubclass(panel_class_for(equipment_type), InstrumentPanel)

    def test_a_supply_gets_the_supply_panel(self):
        assert panel_class_for(EquipmentType.POWER_SUPPLY) is PowerSupplyPanel
        assert panel_class_for("power_supply") is PowerSupplyPanel

    @pytest.mark.parametrize("equipment_type", [
        t for t in EquipmentType if t not in registered_panels()
    ])
    def test_an_unmapped_type_never_gets_the_supply_dials(self, equipment_type):
        """The bug this package replaces: a scope shown volts-and-amps dials."""
        cls = panel_class_for(equipment_type)
        assert cls is GenericInstrumentPanel
        assert not issubclass(cls, PowerSupplyPanel)

    def test_garbage_falls_back_to_the_generic_panel(self):
        assert panel_class_for("no_such_type") is GenericInstrumentPanel
        assert panel_class_for(None) is GenericInstrumentPanel

    def test_every_panel_declares_a_valid_poll_kind(self):
        for cls in set(registered_panels().values()) | {GenericInstrumentPanel}:
            assert cls.POLLS in POLL_KINDS, cls.__name__
            assert cls.DEFAULT_INTERVAL_MS > 0


class TestThePollingContract:
    @pytest.fixture
    def panel(self, qapp):
        panel = RecordingPanel()
        panel.set_instrument(_equipment(), client=object())
        panel.poll_timer.start(panel.interval_ms())
        return panel

    def test_a_404_stops_the_timer_and_reports_the_instrument_gone(self, panel):
        gone = []
        panel.equipment_gone.connect(gone.append)
        panel.failure = _http_error(404)

        _tick(panel)

        assert not panel.poll_timer.isActive(), "the 404 storm: it kept asking"
        assert gone == ["eq_1"]
        assert panel.equipment.connection_status is ConnectionStatus.DISCONNECTED
        assert panel.not_connected_shown == 1

    @pytest.mark.parametrize("status", [501, 405])
    def test_a_permanent_refusal_stops_the_timer(self, panel, status):
        """The 501 storm: a permanent 'this instrument cannot' was retried."""
        panel.failure = _http_error(status)
        _tick(panel)
        assert not panel.poll_timer.isActive()
        assert panel.unsupported_shown == 1
        # Refusal is not disappearance: the instrument is still connected.
        assert panel.equipment.connection_status is ConnectionStatus.CONNECTED

    @pytest.mark.parametrize("failure", [_http_error(500), _http_error(503), TimeoutError("read timed out")])
    def test_a_transient_fault_keeps_polling(self, panel, failure):
        """A sick server or a serial hiccup must not silence a supply."""
        panel.failure = failure
        _tick(panel)
        assert panel.poll_timer.isActive()
        assert panel.unsupported_shown == 0

    def test_a_disconnected_instrument_is_never_polled(self, qapp):
        panel = RecordingPanel()
        panel.set_instrument(_equipment(status=ConnectionStatus.DISCONNECTED), client=object())
        panel.start()
        for _ in range(80):
            qapp.processEvents()
            qapp.thread().msleep(10)
        assert not panel.is_polling()
        assert panel.not_connected_shown == 1
        assert panel.polls == 0

    def test_a_panel_that_polls_nothing_never_starts_a_timer(self, qapp):
        class Silent(InstrumentPanel):
            POLLS = None

        panel = Silent()
        panel.set_instrument(_equipment(), client=object())
        panel.start()
        for _ in range(80):
            qapp.processEvents()
            qapp.thread().msleep(10)
        assert not panel.is_polling()

    def test_binding_another_instrument_stops_polling_the_old_one(self, panel):
        assert panel.poll_timer.isActive()
        panel.set_instrument(_equipment(), client=object())
        assert not panel.poll_timer.isActive()

    def test_a_tick_in_flight_is_not_queued_behind_itself(self, panel, monkeypatch):
        """A slow server must not pile up requests."""
        panel._poll_started_at = 1e12  # a request "still out"
        _tick(panel)
        assert panel.polls == 0
        panel._poll_started_at = None
        _tick(panel)
        assert panel.polls == 1


class TestCadence:
    def test_each_panel_uses_its_own_default(self, qapp, monkeypatch):
        """A scope is not polled at the supply's 10 Hz, or vice versa."""
        from client.utils import settings as settings_module

        class Forgetful:
            def get_reading_rate_for(self, equipment_type, default):
                return default

            def set_reading_rate_for(self, *a):
                pass

        monkeypatch.setattr(settings_module, "SettingsManager", lambda: Forgetful())
        assert PowerSupplyPanel().interval_ms() == PowerSupplyPanel.DEFAULT_INTERVAL_MS
        assert GenericInstrumentPanel().interval_ms() == GenericInstrumentPanel.DEFAULT_INTERVAL_MS
        assert PowerSupplyPanel.DEFAULT_INTERVAL_MS != GenericInstrumentPanel.DEFAULT_INTERVAL_MS

    def test_an_override_is_remembered_per_type(self, qapp, monkeypatch):
        from client.utils import settings as settings_module

        store = {}

        class Memory:
            def get_reading_rate_for(self, equipment_type, default):
                return store.get(equipment_type, default)

            def set_reading_rate_for(self, equipment_type, rate):
                store[equipment_type] = rate

        monkeypatch.setattr(settings_module, "SettingsManager", lambda: Memory())

        supply = PowerSupplyPanel()
        supply._on_refresh_changed(2.0)
        assert store == {"power_supply": pytest.approx(2.0)}

        # A new supply panel comes back at 2 Hz; a generic panel is untouched.
        assert PowerSupplyPanel().interval_ms() == 500
        assert GenericInstrumentPanel().interval_ms() == GenericInstrumentPanel.DEFAULT_INTERVAL_MS

    def test_a_running_timer_follows_a_rate_change(self, qapp):
        panel = RecordingPanel()
        panel.set_instrument(_equipment(), client=object())
        panel.poll_timer.start(panel.interval_ms())
        panel.set_rate_hz(5.0, remember=False)
        assert panel.poll_timer.interval() == 200


class TestTheShell:
    class FakeClient:
        def __init__(self):
            self.commands = []

        def get_equipment_status(self, equipment_id):
            return {"capabilities": {"max_voltage": 30.0, "max_current": 5.0}}

        def send_command(self, equipment_id, command, parameters=None):
            self.commands.append(command)
            return {"success": True, "data": {"voltage": 1.0, "current": 0.5}}

        def get_lock_status(self, equipment_id):
            return {}

        def holds_lock(self, status):
            return False

        def acquire_lock(self, *a, **k):
            return {}

        def release_lock(self, equipment_id):
            return {}

    def _shell_with(self, qapp, *equipment):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QListWidgetItem

        shell = ControlPanel(client=self.FakeClient())
        shell._refresh_lock_status = lambda: None
        shell.equipment_list = list(equipment)
        for eq in equipment:
            item = QListWidgetItem(eq.name)
            item.setData(Qt.ItemDataRole.UserRole, eq.key)
            shell.equipment_list_widget.addItem(item)
        return shell

    def _select(self, shell, row):
        shell.equipment_list_widget.setCurrentRow(row)
        shell._on_equipment_selected()
        return shell.current_panel

    def test_a_scope_gets_no_supply_dials(self, qapp):
        scope = Equipment(
            equipment_id="scope_1", name="DS1054Z", equipment_type=EquipmentType.OSCILLOSCOPE,
            manufacturer="Rigol", model="DS1054Z", resource_name="USB::x",
            connection_status=ConnectionStatus.CONNECTED,
        )
        shell = self._shell_with(qapp, scope)
        panel = self._select(shell, 0)
        assert not isinstance(panel, PowerSupplyPanel)
        assert not hasattr(panel, "voltage_dial")
        shell._stop_data_acquisition()

    def test_switching_instruments_stops_the_hidden_panel(self, qapp):
        supply = _equipment()
        scope = Equipment(
            equipment_id="scope_1", name="DS1054Z", equipment_type=EquipmentType.OSCILLOSCOPE,
            manufacturer="Rigol", model="DS1054Z", resource_name="USB::x",
            connection_status=ConnectionStatus.CONNECTED,
        )
        shell = self._shell_with(qapp, supply, scope)
        supply_panel = self._select(shell, 0)
        supply_panel.poll_timer.start(100)   # as if the settle delay had passed

        scope_panel = self._select(shell, 1)

        assert scope_panel is not supply_panel
        assert not supply_panel.is_polling(), "a hidden panel kept polling"
        assert shell.panel_stack.currentWidget() is scope_panel
        shell._stop_data_acquisition()

    def test_deselecting_shows_the_empty_page_and_stops_everything(self, qapp):
        shell = self._shell_with(qapp, _equipment())
        panel = self._select(shell, 0)
        panel.poll_timer.start(100)

        shell.equipment_list_widget.clearSelection()
        shell._on_equipment_selected()

        assert shell.selected_equipment is None
        assert not panel.is_polling()
        assert shell.panel_stack.currentWidget() is shell.empty_page
        assert not shell.lock_timer.isActive()

    def test_a_panels_status_message_reaches_the_shell(self, qapp):
        shell = self._shell_with(qapp, _equipment())
        messages = []
        shell.status_message.connect(messages.append)
        panel = self._select(shell, 0)
        panel.status_message.emit("hello from the panel")
        assert messages == ["hello from the panel"]
        shell._stop_data_acquisition()
