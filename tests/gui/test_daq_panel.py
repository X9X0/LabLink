"""The DAQ panel configures channels, sets the scan list and tabulates the last scan."""

import asyncio
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication

    from client.models.equipment import ConnectionStatus, Equipment, EquipmentType
    from client.ui.instruments import DAQPanel, panel_class_for

    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(not GUI_AVAILABLE, reason="PyQt6 is required")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _stop_panels(qapp):
    made = []
    original = DAQPanel.__init__

    def tracking(self, *a, **k):
        original(self, *a, **k)
        made.append(self)

    DAQPanel.__init__ = tracking
    try:
        yield
    finally:
        DAQPanel.__init__ = original
        for p in made:
            p.stop()
            p.deleteLater()
        qapp.processEvents()


SCAN = {"readings": {"101": 1.2345, "102": 0.00456, "203": 22.7}, "units": {"101": "V", "102": "V", "203": "C"},
        "functions": {"101": "DCV", "102": "DCV", "203": "TEMP"}, "scan_list": ["101", "102", "203"],
        "installed_modules": {"1": {"model": "MC3120", "description": "20-ch multiplexer"},
                              "2": {"model": "MC3120", "description": "20-ch multiplexer"},
                              "3": {"model": "MC3416", "description": "16-ch actuator"}}}


class FakeDAQClient:
    def __init__(self):
        self.commands = []

    def get_equipment_status(self, equipment_id):
        return {"capabilities": {"functions": ["DCV", "ACV", "RES", "FRES", "TEMP"],
                                 "ranges": {"DCV": [0.2, 2.0, 20.0, 200.0, 300.0], "RES": [100.0, 1e3, 10e3]},
                                 "temperature_sensors": ["TC", "RTD", "THER"], "thermocouple_types": ["J", "K", "T"],
                                 "trigger_sources": ["IMM", "BUS", "EXT", "TIMER"],
                                 "modules": SCAN["installed_modules"], "scan_list": ["101", "102"]}}

    def get_readings(self, equipment_id):
        return dict(SCAN)

    def send_command(self, equipment_id, command, parameters=None):
        self.commands.append((command, parameters or {}))
        if command == "scan":
            return {"success": True, "data": dict(SCAN)}
        if command == "set_scan_list":
            return {"success": True, "data": ["101", "102", "103", "104", "201"]}
        return {"success": True, "data": None}


def _daq():
    return Equipment(equipment_id="daq_1", name="M300", equipment_type=EquipmentType.DATA_ACQUISITION,
                     manufacturer="Rigol", model="M300", resource_name="TCPIP::x",
                     connection_status=ConnectionStatus.CONNECTED)


def _run(panel, method_name, *args):
    method = getattr(type(panel), method_name)
    coroutine = getattr(method, "__wrapped__", method)
    return asyncio.run(coroutine(panel, *args))


def _table(t):
    return [[t.item(r, c).text() for c in range(t.columnCount())] for r in range(t.rowCount())]


def test_daqs_get_this_panel():
    assert panel_class_for(EquipmentType.DATA_ACQUISITION) is DAQPanel


def test_binding_shows_modules_and_scan_list_without_commanding(qapp):
    client = FakeDAQClient()
    panel = DAQPanel()
    panel.set_instrument(_daq(), client)
    assert _table(panel.modules_table)[0] == ["1", "MC3120", "20-ch multiplexer"]
    assert panel.scan_list_edit.text() == "101, 102"
    assert [panel.function_combo.itemData(i) for i in range(panel.function_combo.count())] == ["DCV", "ACV", "RES", "FRES", "TEMP"]
    assert [panel.range_combo.itemData(i) for i in range(panel.range_combo.count())] == [None, 0.2, 2.0, 20.0, 200.0, 300.0]
    assert client.commands == []


def test_poll_tabulates_the_last_scan(qapp):
    panel = DAQPanel()
    panel.set_instrument(_daq(), FakeDAQClient())
    _run(panel, "_poll")
    rows = _table(panel.readings_table)
    assert rows == [["101", "1.2345 V", "V", "DCV"], ["102", "4.56 mV", "V", "DCV"], ["203", "22.700 C", "C", "TEMP"]]
    assert "Scan list: 101, 102, 203" in panel.scan_note.text()


def test_configure_scan_trigger_and_switch_payloads(qapp):
    panel = DAQPanel()
    panel.set_instrument(_daq(), FakeDAQClient())
    sent = []
    panel._command = lambda name, params=None: sent.append((name, params))

    panel.channel_edit.setText("101, 102:104")
    panel.function_combo.setCurrentIndex(panel.function_combo.findData("DCV"))
    panel.range_combo.setCurrentIndex(panel.range_combo.findData(20.0))
    panel._apply_configure()

    panel.channel_edit.setText("203")
    panel.function_combo.setCurrentIndex(panel.function_combo.findData("TEMP"))
    assert not panel.range_combo.isEnabled() and panel.sensor_combo.isEnabled()
    panel.sensor_combo.setCurrentIndex(panel.sensor_combo.findData("TC"))
    panel.sensor_type_combo.setCurrentIndex(panel.sensor_type_combo.findData("K"))
    panel._apply_configure()

    panel.scan_list_edit.setText("101:104; 201")
    panel._apply_scan_list()
    panel.trigger_source_combo.setCurrentIndex(panel.trigger_source_combo.findData("TIMER"))
    panel.trigger_count_spin.setValue(10); panel.trigger_interval_spin.setValue(2.5)
    panel._apply_trigger()
    panel.switch_edit.setText("301, 302"); panel.close_button.click(); panel.open_button.click()

    assert sent == [
        ("configure_channel", {"channel": ["101", "102:104"], "function": "DCV", "range": 20.0}),
        ("configure_channel", {"channel": ["203"], "function": "TEMP", "sensor": "TC", "sensor_type": "K"}),
        ("set_scan_list", {"channels": ["101:104", "201"]}),
        ("set_trigger", {"source": "TIMER", "count": 10, "interval": 2.5}),
        ("close_channel", {"channels": "301, 302"}),
        ("open_channel", {"channels": "301, 302"}),
    ]


def test_scan_now_fills_the_table_and_set_scan_list_echoes_the_instrument(qapp):
    client = FakeDAQClient()
    panel = DAQPanel()
    panel.set_instrument(_daq(), client)
    _run(panel, "_send_command", "scan", {"wait": True})
    assert panel.readings_table.rowCount() == 3
    _run(panel, "_send_command", "set_scan_list", {"channels": ["101:104", "201"]})
    assert panel.scan_list_edit.text() == "101, 102, 103, 104, 201"
