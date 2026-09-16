"""The VNA panel draws one S-parameter trace and speaks the VNA vocabulary."""

import asyncio
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication

    from client.models.equipment import ConnectionStatus, Equipment, EquipmentType
    from client.ui.instruments import VNAPanel, panel_class_for

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
    original = VNAPanel.__init__

    def tracking(self, *a, **k):
        original(self, *a, **k)
        made.append(self)

    VNAPanel.__init__ = tracking
    try:
        yield
    finally:
        VNAPanel.__init__ = original
        for p in made:
            p.stop()
            p.deleteLater()
        qapp.processEvents()


class FakeVNAClient:
    def __init__(self):
        self.commands = []

    def get_equipment_status(self, equipment_id):
        return {"capabilities": {"parameters": ["S11", "S21"], "formats": ["MLOG", "PHAS", "SWR", "SMIT"],
                                 "calibration_methods": ["RESP", "SOL"], "power_min_dbm": -40.0,
                                 "power_max_dbm": 10.0, "max_points": 10001}}

    def send_command(self, equipment_id, command, parameters=None):
        self.commands.append((command, parameters or {}))
        if command == "get_state":
            return {"success": True, "data": {"sweep": {"start_frequency": 10e6, "stop_frequency": 3e9, "points": 401},
                                              "parameter": "S21", "format": "MLOG", "correction": True}}
        if command == "get_trace":
            return {"success": True, "data": {"trace": 1, "parameter": "S21", "format": "MLOG", "unit": "dB",
                                              "start_frequency": 10e6, "stop_frequency": 3e9,
                                              "frequencies": [10e6, 1e9, 2e9, 3e9],
                                              "values": [-0.5, -3.0, -20.0, -45.0], "secondary_values": []}}
        if command == "set_marker":
            return {"success": True, "data": {"marker": 1, "frequency": 1e9, "value": -3.01}}
        return {"success": True, "data": None}


def _vna():
    return Equipment(equipment_id="vna_1", name="DNA6082", equipment_type=EquipmentType.VECTOR_NETWORK_ANALYZER,
                     manufacturer="Rigol", model="DNA6082", resource_name="TCPIP::x",
                     connection_status=ConnectionStatus.CONNECTED)


def _run(panel, method_name, *args):
    method = getattr(type(panel), method_name)
    coroutine = getattr(method, "__wrapped__", method)
    return asyncio.run(coroutine(panel, *args))


def test_vnas_get_this_panel():
    assert panel_class_for(EquipmentType.VECTOR_NETWORK_ANALYZER) is VNAPanel


def test_binding_reads_state_and_capabilities_without_commanding(qapp):
    client = FakeVNAClient()
    panel = VNAPanel()
    panel.set_instrument(_vna(), client)
    assert [panel.parameter_combo.itemData(i) for i in range(panel.parameter_combo.count())] == ["S11", "S21"]
    assert panel.parameter_combo.currentData() == "S21"
    assert panel.format_combo.currentData() == "MLOG"
    assert panel.start_spin.value() == pytest.approx(10.0) and panel.stop_spin.value() == pytest.approx(3000.0)
    assert panel.points_spin.value() == 401 and panel.points_spin.maximum() == 10001
    assert panel.correction_check.isChecked()
    assert panel.power_spin.minimum() == pytest.approx(-40.0)
    assert [c for c, _ in client.commands if c.startswith("set_")] == []


def test_poll_draws_the_trace_against_reported_frequencies(qapp):
    client = FakeVNAClient()
    panel = VNAPanel()
    panel.set_instrument(_vna(), client)
    _run(panel, "_poll")
    assert panel.series.count() == 4
    assert panel.axis_x.min() == pytest.approx(10e6) and panel.axis_x.max() == pytest.approx(3e9)
    assert panel.axis_y.min() < -45.0 < -0.5 < panel.axis_y.max()
    assert panel.chart.title() == "S21  Log magnitude (dB)"


def test_stimulus_parameter_format_marker_and_calibration_payloads(qapp):
    client = FakeVNAClient()
    panel = VNAPanel()
    panel.set_instrument(_vna(), client)
    sent = []
    panel._command = lambda name, params=None: sent.append((name, params))
    panel.start_spin.setValue(100.0); panel.stop_spin.setValue(1000.0); panel.points_spin.setValue(201)
    panel.power_spin.setValue(-5.0); panel.ifbw_combo.setCurrentIndex(panel.ifbw_combo.findData(10e3))
    panel._apply_stimulus()
    panel.parameter_combo.setCurrentIndex(0)                                  # S11
    panel.format_combo.setCurrentIndex(panel.format_combo.findData("SWR"))
    panel.marker_frequency_spin.setValue(500.0); panel._apply_marker()
    panel.cal_method_combo.setCurrentIndex(panel.cal_method_combo.findData("SOL")); panel.cal_start_button.click()
    panel.cal_standard_combo.setCurrentIndex(panel.cal_standard_combo.findData("SHORT")); panel.cal_acquire_button.click()
    panel.cal_save_button.click()
    panel.correction_check.setChecked(False)
    assert sent == [
        ("set_sweep", {"start": 100e6, "stop": 1000e6, "points": 201, "power": -5.0, "if_bandwidth": 10e3}),
        ("set_parameter", {"trace": 1, "s_param": "S11"}),
        ("set_format", {"trace": 1, "fmt": "SWR"}),
        ("set_marker", {"marker": 1, "frequency": 500e6, "trace": 1}),
        ("calibrate_start", {"method": "SOL"}),
        ("calibrate_acquire", {"standard": "SHORT"}),
        ("calibrate_save", {}),
        ("set_correction", {"enabled": False}),
    ]


def test_marker_result_is_shown(qapp):
    client = FakeVNAClient()
    panel = VNAPanel()
    panel.set_instrument(_vna(), client)
    _run(panel, "_send_command", "set_marker", {"marker": 1, "frequency": 1e9, "trace": 1})
    assert panel.marker_label.text() == "M1: 1 GHz  -3.010"
