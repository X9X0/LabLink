"""The data-acquisition panel: modules, channel setup, scan list, readings.

A switch/DAQ mainframe is a set of slots, each holding a module of numbered
channels. The panel shows what is fitted, lets you configure a channel or a
range of channels (function, range, temperature sensor), sets the scan list
and the trigger, drives the switch modules, and reads the last scan into a
table -- one row per channel with its value, unit and function.

Commands (Rigol M300 driver): ``get_modules``, ``configure_channel``,
``set_scan_list``, ``scan``, ``read_channel``, ``close_channel``,
``open_channel``, ``set_trigger``, ``get_readings``, ``get_state``.
"""

import logging
from typing import Any, Dict, List, Optional

import qasync
from PyQt6.QtWidgets import (QComboBox, QDoubleSpinBox, QGridLayout, QGroupBox,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QSpinBox, QTableWidget, QTableWidgetItem,
                             QVBoxLayout)

from client.ui.instruments.base import POLL_READINGS, InstrumentPanel

logger = logging.getLogger(__name__)

FUNCTIONS = ["DCV", "ACV", "DCI", "ACI", "RES", "FRES", "FREQ", "PER", "TEMP"]
UNITS = {"DCV": "V", "ACV": "V", "DCI": "A", "ACI": "A", "RES": "Ohm", "FRES": "Ohm",
         "FREQ": "Hz", "PER": "s", "TEMP": "°C"}


def format_value(value: Any, unit: str) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "--"
    if v != v:  # NaN
        return "--"
    if unit in ("°C", "C", "F", "K"):
        return f"{v:.3f} {unit}"
    magnitude = abs(v)
    for factor, prefix in ((1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"), (1e-6, "µ")):
        if magnitude >= factor or factor == 1e-6:
            return f"{v / factor:.5g} {prefix}{unit}"
    return f"{v:.5g} {unit}"


class DAQPanel(InstrumentPanel):
    """Drive a data-acquisition / switch mainframe."""

    POLLS = POLL_READINGS
    DEFAULT_INTERVAL_MS = 2000
    SETTINGS_TYPE = "data_acquisition"

    def __init__(self, parent=None):
        self.functions: List[str] = list(FUNCTIONS)
        self.ranges: Dict[str, List[float]] = {}
        self.sensors: List[str] = ["TC", "RTD", "FRTD", "THER"]
        self.thermocouple_types: List[str] = ["J", "K", "T", "E", "N", "R", "S", "B"]
        self.trigger_sources: List[str] = ["IMM", "BUS", "EXT", "TIMER"]
        super().__init__(parent)

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        left = QVBoxLayout()
        readings = QGroupBox("Readings (last scan)")
        rl = QVBoxLayout(readings)
        self.readings_table = QTableWidget(0, 4)
        self.readings_table.setHorizontalHeaderLabels(["Channel", "Value", "Unit", "Function"])
        self.readings_table.horizontalHeader().setStretchLastSection(True)
        self.readings_table.verticalHeader().setVisible(False)
        self.readings_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        rl.addWidget(self.readings_table)
        row = QHBoxLayout()
        self.scan_button = QPushButton("Scan now")
        self.scan_button.clicked.connect(lambda: self._command("scan", {"wait": True}))
        row.addWidget(self.scan_button)
        self.scan_note = QLabel("")
        row.addWidget(self.scan_note, 1)
        rl.addLayout(row)
        left.addWidget(readings, 2)

        modules = QGroupBox("Modules")
        ml = QVBoxLayout(modules)
        self.modules_table = QTableWidget(0, 3)
        self.modules_table.setHorizontalHeaderLabels(["Slot", "Model", "Description"])
        self.modules_table.horizontalHeader().setStretchLastSection(True)
        self.modules_table.verticalHeader().setVisible(False)
        self.modules_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        ml.addWidget(self.modules_table)
        left.addWidget(modules, 1)
        outer.addLayout(left, 3)

        right = QVBoxLayout()
        right.addWidget(self._create_channel_controls())
        right.addWidget(self._create_scan_controls())
        right.addWidget(self._create_switch_controls())
        right.addWidget(self._create_rate_control("How often to read the last scan"))
        right.addStretch()
        outer.addLayout(right, 2)

    def _create_channel_controls(self) -> QGroupBox:
        group = QGroupBox("Configure channels")
        grid = QGridLayout(group)
        grid.addWidget(QLabel("Channels:"), 0, 0)
        self.channel_edit = QLineEdit("101")
        self.channel_edit.setPlaceholderText("101, 102:110")
        grid.addWidget(self.channel_edit, 0, 1, 1, 2)
        grid.addWidget(QLabel("Function:"), 1, 0)
        self.function_combo = QComboBox()
        self._fill_functions()
        self.function_combo.currentIndexChanged.connect(self._on_function_changed)
        grid.addWidget(self.function_combo, 1, 1)
        grid.addWidget(QLabel("Range:"), 1, 2)
        self.range_combo = QComboBox()
        self._fill_ranges()
        grid.addWidget(self.range_combo, 1, 3)
        grid.addWidget(QLabel("Sensor:"), 2, 0)
        self.sensor_combo = QComboBox()
        self._fill_sensors()
        grid.addWidget(self.sensor_combo, 2, 1)
        grid.addWidget(QLabel("Type:"), 2, 2)
        self.sensor_type_combo = QComboBox()
        self._fill_sensor_types()
        grid.addWidget(self.sensor_type_combo, 2, 3)
        self.configure_button = QPushButton("Configure")
        self.configure_button.clicked.connect(self._apply_configure)
        grid.addWidget(self.configure_button, 3, 0, 1, 4)
        self._on_function_changed(0)
        return group

    def _create_scan_controls(self) -> QGroupBox:
        group = QGroupBox("Scan list and trigger")
        grid = QGridLayout(group)
        grid.addWidget(QLabel("Scan list:"), 0, 0)
        self.scan_list_edit = QLineEdit("")
        self.scan_list_edit.setPlaceholderText("101:110, 201")
        grid.addWidget(self.scan_list_edit, 0, 1, 1, 2)
        self.scan_list_button = QPushButton("Set")
        self.scan_list_button.clicked.connect(self._apply_scan_list)
        grid.addWidget(self.scan_list_button, 0, 3)
        grid.addWidget(QLabel("Trigger:"), 1, 0)
        self.trigger_source_combo = QComboBox()
        self._fill_trigger_sources()
        grid.addWidget(self.trigger_source_combo, 1, 1)
        grid.addWidget(QLabel("Count:"), 1, 2)
        self.trigger_count_spin = QSpinBox()
        self.trigger_count_spin.setRange(1, 50000)
        self.trigger_count_spin.setValue(1)
        grid.addWidget(self.trigger_count_spin, 1, 3)
        grid.addWidget(QLabel("Interval (s):"), 2, 0)
        self.trigger_interval_spin = QDoubleSpinBox()
        self.trigger_interval_spin.setRange(0.0, 359999.0)
        self.trigger_interval_spin.setDecimals(3)
        self.trigger_interval_spin.setValue(1.0)
        grid.addWidget(self.trigger_interval_spin, 2, 1)
        self.trigger_button = QPushButton("Set trigger")
        self.trigger_button.clicked.connect(self._apply_trigger)
        grid.addWidget(self.trigger_button, 2, 2, 1, 2)
        return group

    def _create_switch_controls(self) -> QGroupBox:
        group = QGroupBox("Switch modules")
        row = QHBoxLayout(group)
        row.addWidget(QLabel("Channels:"))
        self.switch_edit = QLineEdit("301")
        row.addWidget(self.switch_edit, 1)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(lambda: self._command("close_channel", {"channels": self.switch_edit.text()}))
        row.addWidget(self.close_button)
        self.open_button = QPushButton("Open")
        self.open_button.clicked.connect(lambda: self._command("open_channel", {"channels": self.switch_edit.text()}))
        row.addWidget(self.open_button)
        return group

    def _fill_functions(self):
        self.function_combo.blockSignals(True)
        self.function_combo.clear()
        for f in self.functions:
            self.function_combo.addItem(f, f)
        self.function_combo.blockSignals(False)

    def _fill_ranges(self):
        function = self.function_combo.currentData() if self.function_combo.count() else None
        self.range_combo.blockSignals(True)
        self.range_combo.clear()
        self.range_combo.addItem("Auto", None)
        for r in self.ranges.get(function or "", []):
            self.range_combo.addItem(format_value(r, UNITS.get(function or "", "")), float(r))
        self.range_combo.blockSignals(False)

    def _fill_sensors(self):
        self.sensor_combo.blockSignals(True)
        self.sensor_combo.clear()
        for s in self.sensors:
            self.sensor_combo.addItem(str(s), str(s))
        self.sensor_combo.blockSignals(False)

    def _fill_sensor_types(self):
        self.sensor_type_combo.blockSignals(True)
        self.sensor_type_combo.clear()
        for t in self.thermocouple_types:
            self.sensor_type_combo.addItem(str(t), str(t))
        self.sensor_type_combo.blockSignals(False)

    def _fill_trigger_sources(self):
        self.trigger_source_combo.blockSignals(True)
        self.trigger_source_combo.clear()
        for s in self.trigger_sources:
            self.trigger_source_combo.addItem(str(s), str(s))
        self.trigger_source_combo.blockSignals(False)

    # ------------------------------------------------------------------ #
    # Contract
    # ------------------------------------------------------------------ #

    def configure(self, capabilities: Dict[str, Any]):
        if capabilities.get("functions"):
            self.functions = [str(f).upper() for f in capabilities["functions"]]
            self._fill_functions()
        if isinstance(capabilities.get("ranges"), dict):
            self.ranges = {str(k).upper(): [float(v) for v in vals] for k, vals in capabilities["ranges"].items()}
        if capabilities.get("temperature_sensors"):
            self.sensors = [str(s) for s in capabilities["temperature_sensors"]]
            self._fill_sensors()
        if capabilities.get("thermocouple_types"):
            self.thermocouple_types = [str(t) for t in capabilities["thermocouple_types"]]
            self._fill_sensor_types()
        if capabilities.get("trigger_sources"):
            self.trigger_sources = [str(s) for s in capabilities["trigger_sources"]]
            self._fill_trigger_sources()
        self._fill_ranges()
        self._show_modules(capabilities.get("modules") or {})
        scan_list = capabilities.get("scan_list")
        if scan_list:
            self.scan_list_edit.setText(", ".join(str(c) for c in scan_list))
        self.readings_table.setRowCount(0)
        self.scan_note.setText("")

    def _show_modules(self, modules: Any):
        rows = []
        if isinstance(modules, dict):
            for slot, info in sorted(modules.items(), key=lambda kv: str(kv[0])):
                if isinstance(info, dict):
                    rows.append((str(slot), str(info.get("model") or ""), str(info.get("description") or info.get("kind") or "")))
                else:
                    rows.append((str(slot), str(info), ""))
        self.modules_table.setRowCount(len(rows))
        for i, (slot, model, desc) in enumerate(rows):
            for col, text in enumerate((slot, model, desc)):
                self.modules_table.setItem(i, col, QTableWidgetItem(text))

    def set_controls_enabled(self, enabled: bool):
        for w in (self.channel_edit, self.function_combo, self.range_combo, self.sensor_combo,
                  self.sensor_type_combo, self.configure_button, self.scan_list_edit, self.scan_list_button,
                  self.trigger_source_combo, self.trigger_count_spin, self.trigger_interval_spin,
                  self.trigger_button, self.switch_edit, self.close_button, self.open_button, self.scan_button):
            w.setEnabled(enabled)

    def show_not_connected(self):
        self.readings_table.setRowCount(0)
        self.scan_note.setText("Not connected. Connect it on the Equipment tab to read it.")
        self.status_message.emit("Not connected. Connect it on the Equipment tab to read it.")

    def show_unsupported(self):
        self.readings_table.setRowCount(0)
        self.scan_note.setText("This instrument does not report scan readings.")

    def clear_instrument(self):
        self.readings_table.setRowCount(0)
        self.modules_table.setRowCount(0)
        self.scan_note.setText("")

    # ------------------------------------------------------------------ #
    # Polling
    # ------------------------------------------------------------------ #

    async def poll(self):
        from client.api.client import call_blocking

        data = await call_blocking(self.client.get_readings, self.equipment.equipment_id)
        self._show_readings(data or {})

    def _show_readings(self, data: Dict[str, Any]):
        readings = data.get("readings") or {}
        units = data.get("units") or {}
        functions = data.get("functions") or {}
        channels = sorted(readings.keys(), key=lambda c: (len(str(c)), str(c)))
        self.readings_table.setRowCount(len(channels))
        for i, ch in enumerate(channels):
            unit = units.get(ch) or UNITS.get(str(functions.get(ch, "")).upper(), "")
            cells = (str(ch), format_value(readings[ch], unit), unit, str(functions.get(ch, "")))
            for col, text in enumerate(cells):
                self.readings_table.setItem(i, col, QTableWidgetItem(text))
        if data.get("scan_list"):
            self.scan_note.setText(f"Scan list: {', '.join(str(c) for c in data['scan_list'])}")
        if data.get("installed_modules"):
            self._show_modules(data["installed_modules"])

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #

    def _command(self, name: str, parameters: Optional[Dict[str, Any]] = None):
        self._send_command(name, parameters or {})

    @qasync.asyncSlot(str, dict)
    async def _send_command(self, name: str, parameters: dict):
        try:
            result = await self.send(name, parameters)
            if name == "scan" and isinstance(result, dict):
                self._show_readings(result)
            elif name == "set_scan_list" and isinstance(result, list):
                self.scan_list_edit.setText(", ".join(str(c) for c in result))
            return result
        except Exception as e:
            logger.error(f"{name} failed: {e}")
            self.status_message.emit(f"{name.replace('_', ' ')} failed: {e}")

    @staticmethod
    def parse_channels(text: str) -> List[str]:
        """'101, 102:104' -> ['101', '102:104'] (the driver expands ranges)."""
        return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]

    def _on_function_changed(self, _index: int):
        self._fill_ranges()
        is_temp = (self.function_combo.currentData() or "") == "TEMP"
        self.sensor_combo.setEnabled(is_temp)
        self.sensor_type_combo.setEnabled(is_temp)
        self.range_combo.setEnabled(not is_temp)

    def _apply_configure(self):
        function = self.function_combo.currentData() or "DCV"
        payload: Dict[str, Any] = {"channel": self.parse_channels(self.channel_edit.text()), "function": function}
        if function == "TEMP":
            payload["sensor"] = self.sensor_combo.currentData()
            payload["sensor_type"] = self.sensor_type_combo.currentData()
        elif self.range_combo.currentData() is not None:
            payload["range"] = float(self.range_combo.currentData())
        self._command("configure_channel", payload)

    def _apply_scan_list(self):
        self._command("set_scan_list", {"channels": self.parse_channels(self.scan_list_edit.text())})

    def _apply_trigger(self):
        self._command("set_trigger", {
            "source": self.trigger_source_combo.currentData(),
            "count": int(self.trigger_count_spin.value()),
            "interval": float(self.trigger_interval_spin.value()),
        })
