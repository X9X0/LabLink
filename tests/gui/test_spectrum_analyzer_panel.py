"""The spectrum-analyzer panel draws the trace it polls and speaks the SA vocabulary."""

import asyncio
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication

    from client.models.equipment import ConnectionStatus, Equipment, EquipmentType
    from client.ui.instruments import SpectrumAnalyzerPanel, panel_class_for

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
    original = SpectrumAnalyzerPanel.__init__

    def tracking(self, *a, **k):
        original(self, *a, **k)
        made.append(self)

    SpectrumAnalyzerPanel.__init__ = tracking
    try:
        yield
    finally:
        SpectrumAnalyzerPanel.__init__ = original
        for p in made:
            p.stop()
            p.deleteLater()
        qapp.processEvents()


class FakeSAClient:
    def __init__(self, tg=True):
        self.commands = []
        self.tg = tg

    def get_equipment_status(self, equipment_id):
        return {"capabilities": {"frequency_min": 9e3, "frequency_max": 1.5e9, "has_tracking_generator": self.tg,
                                 "supports_rtsa": False, "detectors": ["POS", "NEG", "SAMP", "RMS"],
                                 "trace_modes": ["WRITE", "MAXHOLD", "MINHOLD", "VIEW", "BLANK"], "has_preamp": True}}

    def send_command(self, equipment_id, command, parameters=None):
        self.commands.append((command, parameters or {}))
        if command == "get_state":
            return {"success": True, "data": {
                "frequency": {"center": 100e6, "span": 10e6, "start": 95e6, "stop": 105e6},
                "bandwidth": {"rbw": 100e3, "rbw_auto": False, "vbw": 100e3, "vbw_auto": True},
                "amplitude": {"reference_level": -10.0, "attenuation": 20.0, "attenuation_auto": False, "preamp": False},
                "detector": "POS", "mode": "GPSA", "tracking_generator": {"enabled": True, "level": -15.0}}}
        if command == "get_trace":
            return {"success": True, "data": {"trace": 1, "start_frequency": 95e6, "stop_frequency": 105e6,
                                              "reference_level": -10.0, "unit": "dBm", "rbw": 100e3,
                                              "values": [-90.0, -85.0, -40.0, -85.0, -90.0],
                                              "peak_frequency": 100e6, "peak_amplitude": -40.0,
                                              "markers": {"1": {"frequency": 100e6, "amplitude": -40.0}}}}
        if command in ("peak_search", "next_peak", "set_marker"):
            return {"success": True, "data": {"marker": 1, "frequency": 100.5e6, "amplitude": -41.2}}
        return {"success": True, "data": None}


def _sa():
    return Equipment(equipment_id="sa_1", name="DSA815-TG", equipment_type=EquipmentType.SPECTRUM_ANALYZER,
                     manufacturer="Rigol", model="DSA815-TG", resource_name="USB::x",
                     connection_status=ConnectionStatus.CONNECTED)


def _run(panel, method_name, *args):
    method = getattr(type(panel), method_name)
    coroutine = getattr(method, "__wrapped__", method)
    return asyncio.run(coroutine(panel, *args))


def test_analyzers_get_this_panel():
    assert panel_class_for(EquipmentType.SPECTRUM_ANALYZER) is SpectrumAnalyzerPanel


def test_binding_reads_state_onto_the_controls_without_commanding(qapp):
    client = FakeSAClient()
    panel = SpectrumAnalyzerPanel()
    panel.set_instrument(_sa(), client)
    assert panel.center_spin.value() == pytest.approx(100.0)
    assert panel.span_spin.value() == pytest.approx(10.0)
    assert panel.rbw_combo.currentData() == pytest.approx(100e3)
    assert panel.vbw_combo.currentData() == "AUTO"
    assert panel.ref_level_spin.value() == pytest.approx(-10.0)
    assert panel.attenuation_spin.value() == 20 and not panel.attenuation_auto.isChecked()
    assert panel.tg_group.isVisibleTo(panel) and panel.tg_enable.isChecked()
    assert panel.tg_level.value() == pytest.approx(-15.0)
    assert not panel.mode_combo.isEnabled(), "no RTSA on a DSA815"
    assert [c for c, _ in client.commands if c.startswith("set_")] == []


def test_tracking_generator_group_hides_when_not_fitted(qapp):
    panel = SpectrumAnalyzerPanel()
    panel.set_instrument(_sa(), FakeSAClient(tg=False))
    assert not panel.tg_group.isVisibleTo(panel)


def test_poll_draws_the_trace_against_its_own_span(qapp):
    client = FakeSAClient()
    panel = SpectrumAnalyzerPanel()
    panel.set_instrument(_sa(), client)
    client.commands.clear()
    _run(panel, "_poll")
    assert client.commands == [("get_trace", {"trace": 1})]
    assert panel.series.count() == 5
    assert panel.axis_x.min() == pytest.approx(95e6) and panel.axis_x.max() == pytest.approx(105e6)
    assert panel.axis_y.max() == pytest.approx(-10.0) and panel.axis_y.min() == pytest.approx(-110.0)
    assert "100 MHz" in panel.peak_label.text() and "-40.00 dBm" in panel.peak_label.text()
    assert "M1: 100 MHz" in panel.marker_label.text()


def test_control_payloads(qapp):
    panel = SpectrumAnalyzerPanel()
    panel.set_instrument(_sa(), FakeSAClient())
    sent = []
    panel._command = lambda name, params=None: sent.append((name, params))
    panel.center_spin.setValue(433.92); panel.span_spin.setValue(2.0); panel._apply_center_span()
    panel.start_spin.setValue(400.0); panel.stop_spin.setValue(500.0); panel._apply_start_stop()
    panel.rbw_combo.setCurrentIndex(0)
    panel.rbw_combo.setCurrentIndex(panel.rbw_combo.findData(10e3))
    panel.ref_level_spin.setValue(5.0); panel.ref_level_apply.click()
    panel.attenuation_auto.setChecked(True); panel._apply_attenuation()
    panel.attenuation_auto.setChecked(False); panel.attenuation_spin.setValue(30); panel._apply_attenuation()
    panel.detector_combo.setCurrentIndex(panel.detector_combo.findData("RMS"))
    panel.trace_mode_combo.setCurrentIndex(panel.trace_mode_combo.findData("MAXHOLD"))
    panel.tg_enable.setChecked(False); panel.tg_level.setValue(-20.0); panel.tg_apply.click()
    assert sent == [
        ("set_frequency", {"center": pytest.approx(433.92e6), "span": 2e6}),
        ("set_start_stop", {"start": 400e6, "stop": 500e6}),
        ("set_rbw", {"rbw": "AUTO", "auto": True}),
        ("set_rbw", {"rbw": 10e3, "auto": False}),
        ("set_reference_level", {"level": 5.0}),
        ("set_attenuation", {"auto": True}),
        ("set_attenuation", {"db": 30.0, "auto": False}),
        ("set_detector", {"detector": "RMS", "trace": 1}),
        ("set_trace_mode", {"trace": 1, "mode": "MAXHOLD"}),
        ("set_tracking_generator", {"enabled": False, "level": -20.0}),
    ]


def test_peak_search_updates_the_marker_readout(qapp):
    client = FakeSAClient()
    panel = SpectrumAnalyzerPanel()
    panel.set_instrument(_sa(), client)
    _run(panel, "_send_marker_command", "peak_search", {"marker": 1})
    assert ("peak_search", {"marker": 1}) in client.commands
    assert panel.marker_label.text() == "M1: 100.5 MHz  -41.20"


def test_lock_gating_covers_the_marker_and_tg_buttons(qapp):
    panel = SpectrumAnalyzerPanel()
    panel.set_instrument(_sa(), FakeSAClient())
    panel.set_controls_enabled(False)
    assert not panel.peak_button.isEnabled() and not panel.tg_apply.isEnabled() and not panel.frequency_apply.isEnabled()
