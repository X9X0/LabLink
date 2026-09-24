"""The multimeter panel: one big number and the knobs that decide what it is."""

import asyncio
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication


    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(not GUI_AVAILABLE, reason="PyQt6 is required")

if GUI_AVAILABLE:
    from client.models.equipment import ConnectionStatus, Equipment, EquipmentType
    from client.ui.instruments import MultimeterPanel, panel_class_for
    from client.ui.instruments.multimeter import format_reading


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _stop_panels(qapp):
    made = []
    original = MultimeterPanel.__init__

    def tracking(self, *a, **k):
        original(self, *a, **k)
        made.append(self)

    MultimeterPanel.__init__ = tracking
    try:
        yield
    finally:
        MultimeterPanel.__init__ = original
        for p in made:
            p.stop()
            p.deleteLater()
        qapp.processEvents()


class FakeDMMClient:
    """Answers like a DM3068 through /readings and the command endpoint."""

    def __init__(self):
        self.commands = []
        self.readings = {"function": "DCV", "value": 4.999871, "unit": "V", "overload": False,
                         "range_index": 2, "range_full_scale": 20.0, "auto_range": False,
                         "rate": "SLOW", "secondary_function": None}

    def get_equipment_status(self, equipment_id):
        return {"capabilities": {
            "digits": 6.5, "functions": ["DCV", "ACV", "DCI", "ACI", "RES", "FRES", "FREQ", "PER", "CAP", "CONT", "DIODE"],
            "ranges": {"DCV": [0.2, 2.0, 20.0, 200.0, 1000.0], "RES": [200.0, 2e3, 20e3]},
            "rates": ["FAST", "MEDIUM", "SLOW"], "secondary_functions": ["FREQ"], "function": "DCV",
        }}

    def get_readings(self, equipment_id):
        return dict(self.readings)

    def send_command(self, equipment_id, command, parameters=None):
        self.commands.append((command, parameters or {}))
        if command == "get_statistics":
            return {"success": True, "data": {"min": 4.99, "max": 5.01, "average": 5.0, "count": 252}}
        if command == "set_secondary_function":
            return {"success": False, "error": "Unknown command: set_secondary_function"}
        return {"success": True, "data": None}


def _dmm():
    return Equipment(
        equipment_id="dmm_1", name="DM3068", equipment_type=EquipmentType.MULTIMETER,
        manufacturer="Rigol", model="DM3068", resource_name="USB::x",
        connection_status=ConnectionStatus.CONNECTED,
    )


def _run(panel, method_name, *args):
    method = getattr(type(panel), method_name)
    coroutine = getattr(method, "__wrapped__", method)
    return asyncio.run(coroutine(panel, *args))


def test_multimeters_get_this_panel():
    assert panel_class_for(EquipmentType.MULTIMETER) is MultimeterPanel


def test_binding_fills_the_controls_from_capabilities_and_the_present_reading(qapp):
    client = FakeDMMClient()
    panel = MultimeterPanel()
    panel.set_instrument(_dmm(), client)

    assert panel.function_combo.currentData() == "DCV"
    ranges = [panel.range_combo.itemData(i) for i in range(panel.range_combo.count())]
    assert ranges == ["AUTO", 0.2, 2.0, 20.0, 200.0, 1000.0]
    assert panel.range_combo.currentData() == 20.0      # the meter's present range
    assert panel.rate_combo.currentData() == "SLOW"
    assert panel.primary_display.text() == "4.9999 V"
    assert "DCV" in panel.annunciator.text() and "RANGE 20 V" in panel.annunciator.text()
    assert client.commands == [], "binding must not command the meter"


def test_choosing_a_function_commands_it_and_reranges(qapp):
    client = FakeDMMClient()
    panel = MultimeterPanel()
    panel.set_instrument(_dmm(), client)
    sent = []
    panel._command = lambda name, params=None: sent.append((name, params))

    panel.function_combo.setCurrentIndex(panel.function_combo.findData("RES"))

    assert sent == [("set_function", {"function": "RES"})]
    assert [panel.range_combo.itemData(i) for i in range(panel.range_combo.count())] == ["AUTO", 200.0, 2e3, 20e3]


def test_range_rate_math_and_null_payloads(qapp):
    client = FakeDMMClient()
    panel = MultimeterPanel()
    panel.set_instrument(_dmm(), client)
    sent = []
    panel._command = lambda name, params=None: sent.append((name, params))

    panel.range_combo.setCurrentIndex(0)                                   # Auto
    panel.range_combo.setCurrentIndex(panel.range_combo.findData(200.0))
    panel.rate_combo.setCurrentIndex(panel.rate_combo.findData("FAST"))
    panel.math_combo.setCurrentIndex(panel.math_combo.findData("MAX"))
    panel.null_button.click()

    assert sent == [
        ("set_auto_range", {"enabled": True, "function": "DCV"}),
        ("set_range", {"range": 200.0, "function": "DCV"}),
        ("set_rate", {"rate": "FAST", "function": "DCV"}),
        ("set_math_function", {"math_function": "MAX"}),
        ("set_rel_offset", {"offset": "CURR", "enabled": True}),
    ]


def test_overload_reads_ovld_and_secondary_is_shown(qapp):
    client = FakeDMMClient()
    panel = MultimeterPanel()
    panel.set_instrument(_dmm(), client)
    client.readings.update({"function": "RES", "value": None, "unit": "Ohm", "overload": True,
                            "secondary_function": "FREQ", "secondary_value": 1000.5, "secondary_unit": "Hz"})
    _run(panel, "_poll")
    assert panel.primary_display.text() == "OVLD"
    assert panel.secondary_display.text() == "FREQ: 1.0005 kHz"
    assert panel.function_combo.currentData() == "RES", "the panel follows a front-panel function change"


def test_statistics_are_fetched_only_while_a_statistic_is_selected(qapp):
    client = FakeDMMClient()
    panel = MultimeterPanel()
    panel.set_instrument(_dmm(), client)
    client.commands.clear()

    _run(panel, "_poll")
    assert [c for c, _ in client.commands] == []

    panel.math_combo.blockSignals(True)
    panel.math_combo.setCurrentIndex(panel.math_combo.findData("AVERAGE"))
    panel.math_combo.blockSignals(False)
    _run(panel, "_poll")
    assert [c for c, _ in client.commands] == ["get_statistics"]
    assert "avg 5 V" in panel.statistics_label.text() and "n=252" in panel.statistics_label.text()


def test_an_unsupported_command_is_reported_not_retried(qapp):
    client = FakeDMMClient()
    panel = MultimeterPanel()
    panel.set_instrument(_dmm(), client)
    messages = []
    panel.status_message.connect(messages.append)
    _run(panel, "_send_command", "set_secondary_function", {"function": "FREQ"})
    assert messages and "Unknown command" in messages[0]


@pytest.mark.parametrize("value,unit,overload,text", [
    (4.999871, "V", False, "4.9999 V"), (0.0047, "A", False, "4.7 mA"), (4700.0, "Ohm", False, "4.7 kOhm"),
    (None, "V", True, "OVLD"), (None, "V", False, "--"), (23.456, "°C", False, "23.456 °C"),
])
def test_format_reading(value, unit, overload, text):
    assert format_reading(value, unit, overload) == text
