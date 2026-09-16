"""The RF generator panel: carrier, level, RF on/off, modulation, sweep."""

import asyncio
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication

    from client.models.equipment import ConnectionStatus, Equipment, EquipmentType
    from client.ui.instruments import RFGeneratorPanel, panel_class_for
    from client.ui.instruments.rf_generator import format_frequency

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
    original = RFGeneratorPanel.__init__

    def tracking(self, *a, **k):
        original(self, *a, **k)
        made.append(self)

    RFGeneratorPanel.__init__ = tracking
    try:
        yield
    finally:
        RFGeneratorPanel.__init__ = original
        for p in made:
            p.stop()
            p.deleteLater()
        qapp.processEvents()


class FakeDSGClient:
    def __init__(self):
        self.commands = []
        self.state = {"frequency": 433.92e6, "level": -10.0, "level_unit": "dBm", "output_enabled": True,
                      "modulation_enabled": True, "modulation_type": "FM", "alc_enabled": True}

    def get_equipment_status(self, equipment_id):
        return {"capabilities": {"frequency_min": 9e3, "frequency_max": 3.6e9, "level_min_dbm": -130.0,
                                 "level_max_dbm": 20.0, "modulation_types": ["AM", "FM", "PM", "PULSE"]}}

    def send_command(self, equipment_id, command, parameters=None):
        self.commands.append((command, parameters or {}))
        if command == "get_readings":
            return {"success": True, "data": dict(self.state)}
        return {"success": True, "data": None}


def _rf():
    return Equipment(
        equipment_id="rfgen_1", name="DSG836", equipment_type=EquipmentType.RF_SIGNAL_GENERATOR,
        manufacturer="Rigol", model="DSG836", resource_name="USB::x", connection_status=ConnectionStatus.CONNECTED,
    )


def test_rf_generators_get_this_panel():
    assert panel_class_for(EquipmentType.RF_SIGNAL_GENERATOR) is RFGeneratorPanel


def test_binding_shows_the_carrier_in_a_sensible_unit_without_commanding(qapp):
    client = FakeDSGClient()
    panel = RFGeneratorPanel()
    panel.set_instrument(_rf(), client)
    assert panel.frequency_unit.currentText() == "MHz"
    assert panel.frequency_spin.value() == pytest.approx(433.92)
    assert panel.level_spin.value() == pytest.approx(-10.0)
    assert panel.output_button.isChecked() and panel.output_button.text() == "RF: ON"
    assert panel.alc_check.isChecked() and panel.mod_enable.isChecked()
    assert panel.mod_type.currentData() == "FM"
    assert panel.frequency_display.text() == "433.92 MHz"
    assert "RF ON" in panel.annunciator.text() and "MOD FM" in panel.annunciator.text()
    assert [c for c, _ in client.commands if c.startswith("set_")] == []


def test_frequency_and_level_payloads(qapp):
    client = FakeDSGClient()
    panel = RFGeneratorPanel()
    panel.set_instrument(_rf(), client)
    sent = []
    panel._command = lambda name, params=None: sent.append((name, params))
    panel.frequency_spin.setValue(2.4)
    panel.frequency_unit.setCurrentText("GHz")
    panel._apply_frequency()
    panel.level_spin.setValue(-3.5)
    panel._apply_level()
    assert sent == [("set_frequency", {"frequency": pytest.approx(2.4e9)}),
                    ("set_level", {"level": -3.5, "unit": "dBm"})]


def test_an_out_of_range_frequency_is_refused_before_it_is_sent(qapp):
    panel = RFGeneratorPanel()
    panel.set_instrument(_rf(), FakeDSGClient())
    sent, messages = [], []
    panel._command = lambda name, params=None: sent.append(name)
    panel.status_message.connect(messages.append)
    panel.frequency_spin.setValue(9.0)
    panel.frequency_unit.setCurrentText("GHz")
    panel._apply_frequency()
    assert sent == [] and messages and "between" in messages[0]


def test_modulation_sweep_output_and_alc_payloads(qapp):
    panel = RFGeneratorPanel()
    panel.set_instrument(_rf(), FakeDSGClient())
    sent = []
    panel._command = lambda name, params=None: sent.append((name, params))
    panel.mod_type.setCurrentIndex(panel.mod_type.findData("AM"))
    panel.mod_param.setValue(50.0); panel.mod_frequency.setValue(1000.0)
    panel._apply_modulation()
    panel.mod_type.setCurrentIndex(panel.mod_type.findData("PULSE"))
    panel.mod_param.setValue(1e-6)
    panel._apply_modulation()
    panel.sweep_start.setValue(100.0); panel.sweep_stop.setValue(200.0); panel.sweep_points.setValue(21)
    panel._apply_sweep()
    panel.output_button.click()      # ON -> OFF
    panel.alc_check.setChecked(False)
    assert sent == [
        ("set_modulation", {"type": "AM", "enabled": True, "source": "INT", "depth": 50.0, "frequency": 1000.0}),
        ("set_modulation", {"type": "PULSE", "enabled": True, "source": "INT", "width": 1e-6}),
        ("set_sweep", {"mode": "FREQ", "start_frequency": 100e6, "stop_frequency": 200e6, "points": 21,
                       "dwell": 0.01, "continuous": False}),
        ("set_output", {"enabled": False}),
        ("set_alc", {"enabled": False}),
    ]


@pytest.mark.parametrize("hz,text", [(433.92e6, "433.92 MHz"), (2.4e9, "2.4 GHz"), (9e3, "9 kHz"), (50.0, "50 Hz"), (None, "--")])
def test_format_frequency(hz, text):
    assert format_frequency(hz) == text
