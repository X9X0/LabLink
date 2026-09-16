"""The multimeter panel: one big number, and the knobs that decide what it is.

Function, range (or auto), rate, an optional secondary display, and the math
operation, laid out around a readout large enough to be read from across the
bench -- which is what a DMM's front panel is.

Commands follow the LabLink DMM vocabulary the Rigol drivers share
(``rigol_multimeter``, ``rigol_multimeter_dm858``): ``set_function``,
``set_range`` / ``set_auto_range``, ``set_rate``, ``set_secondary_function``
/ ``clear_secondary_function``, ``set_math_function``, ``get_statistics``.
Readings come from ``GET /equipment/{id}/readings`` (``MultimeterData``).
A driver that lacks one of these answers "Unknown command", which the panel
reports once rather than treating as a fault.
"""

import logging
from typing import Any, Dict, List, Optional

import qasync
from PyQt6.QtWidgets import (QComboBox, QGridLayout, QGroupBox, QHBoxLayout,
                             QLabel, QPushButton, QSizePolicy, QVBoxLayout,
                             QWidget)

from client.api.client import call_blocking
from client.ui.instruments.base import POLL_READINGS, InstrumentPanel
from client.ui.instruments.widgets import FittedReadout

logger = logging.getLogger(__name__)

FUNCTIONS = [
    ("DCV", "DC Voltage", "V"), ("ACV", "AC Voltage", "V"),
    ("DCI", "DC Current", "A"), ("ACI", "AC Current", "A"),
    ("RES", "Resistance 2W", "Ohm"), ("FRES", "Resistance 4W", "Ohm"),
    ("FREQ", "Frequency", "Hz"), ("PER", "Period", "s"),
    ("CAP", "Capacitance", "F"), ("CONT", "Continuity", "Ohm"),
    ("DIODE", "Diode", "V"), ("TEMP", "Temperature", "°C"),
]
UNITS = {key: unit for key, _label, unit in FUNCTIONS}
MATH_FUNCTIONS = ["NONE", "REL", "DB", "DBM", "MIN", "MAX", "AVERAGE", "TOTAL", "PF"]
STATISTIC_MATH = {"MIN", "MAX", "AVERAGE", "TOTAL"}


def format_reading(value: Optional[float], unit: str, overload: bool = False) -> str:
    """The instrument's own presentation: SI prefix, overload spelled out."""
    if overload or value is None:
        return "OVLD" if overload else "--"
    magnitude = abs(value)
    if unit in ("°C", "%"):
        return f"{value:.3f} {unit}"
    for factor, prefix in ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p")):
        if magnitude >= factor or factor == 1e-12:
            return f"{value / factor:.5g} {prefix}{unit}"
    return f"{value:.5g} {unit}"


class MultimeterPanel(InstrumentPanel):
    """Drive a bench multimeter and read it from across the room."""

    POLLS = POLL_READINGS
    DEFAULT_INTERVAL_MS = 200
    SETTINGS_TYPE = "multimeter"

    def __init__(self, parent=None):
        self.functions: List[str] = [k for k, _l, _u in FUNCTIONS]
        self.ranges: Dict[str, List[float]] = {}
        self.rates: List[str] = ["FAST", "MEDIUM", "SLOW"]
        self.secondary_functions: List[str] = []
        self._current_function: Optional[str] = None
        super().__init__(parent)

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        face = QWidget()
        face.setObjectName("dmmPanel")
        face.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        face.setStyleSheet("QWidget#dmmPanel { background-color: black; border-radius: 6px; }")
        face_layout = QVBoxLayout(face)
        face_layout.setContentsMargins(12, 12, 12, 12)
        self.primary_display = FittedReadout("--")
        face_layout.addWidget(self.primary_display, 3)
        self.secondary_display = FittedReadout("")
        self.secondary_display.MAX_POINT_SIZE = 48
        face_layout.addWidget(self.secondary_display, 1)
        self.annunciator = QLabel("")
        self.annunciator.setStyleSheet("QLabel { color: #39FF14; background: transparent; }")
        face_layout.addWidget(self.annunciator)
        layout.addWidget(face, 1)

        controls = QGroupBox("Measurement")
        grid = QGridLayout(controls)
        grid.addWidget(QLabel("Function:"), 0, 0)
        self.function_combo = QComboBox()
        self._fill_functions()
        self.function_combo.currentIndexChanged.connect(self._on_function_chosen)
        grid.addWidget(self.function_combo, 0, 1)

        grid.addWidget(QLabel("Range:"), 0, 2)
        self.range_combo = QComboBox()
        self._fill_ranges()
        self.range_combo.currentIndexChanged.connect(self._on_range_chosen)
        grid.addWidget(self.range_combo, 0, 3)

        grid.addWidget(QLabel("Rate:"), 1, 0)
        self.rate_combo = QComboBox()
        self._fill_rates()
        self.rate_combo.currentIndexChanged.connect(self._on_rate_chosen)
        grid.addWidget(self.rate_combo, 1, 1)

        grid.addWidget(QLabel("Secondary:"), 1, 2)
        self.secondary_combo = QComboBox()
        self.secondary_combo.addItem("Off", None)
        self.secondary_combo.currentIndexChanged.connect(self._on_secondary_chosen)
        grid.addWidget(self.secondary_combo, 1, 3)

        grid.addWidget(QLabel("Math:"), 2, 0)
        self.math_combo = QComboBox()
        for m in MATH_FUNCTIONS:
            self.math_combo.addItem(m.title() if m not in ("DB", "DBM", "PF") else m, m)
        self.math_combo.currentIndexChanged.connect(self._on_math_chosen)
        grid.addWidget(self.math_combo, 2, 1)
        self.null_button = QPushButton("Null (REL)")
        self.null_button.setToolTip("Take the present reading as the zero reference")
        self.null_button.clicked.connect(lambda: self._command("set_rel_offset", {"offset": "CURR", "enabled": True}))
        grid.addWidget(self.null_button, 2, 2)
        self.statistics_label = QLabel("")
        grid.addWidget(self.statistics_label, 2, 3)
        layout.addWidget(controls)

        row = QHBoxLayout()
        row.addWidget(self._create_rate_control("How often to read the meter"))
        row.addStretch()
        layout.addLayout(row)

    def _fill_functions(self):
        self.function_combo.blockSignals(True)
        self.function_combo.clear()
        for key, label, _unit in FUNCTIONS:
            if key in self.functions:
                self.function_combo.addItem(f"{key}  {label}", key)
        for key in self.functions:
            if key not in UNITS:
                self.function_combo.addItem(key, key)
        self.function_combo.blockSignals(False)

    def _fill_ranges(self):
        function = self.function_combo.currentData() if self.function_combo.count() else None
        self.range_combo.blockSignals(True)
        self.range_combo.clear()
        self.range_combo.addItem("Auto", "AUTO")
        unit = UNITS.get(function or "", "")
        for value in self.ranges.get(function or "", []):
            self.range_combo.addItem(format_reading(float(value), unit), float(value))
        self.range_combo.blockSignals(False)

    def _fill_rates(self):
        self.rate_combo.blockSignals(True)
        self.rate_combo.clear()
        for r in self.rates:
            self.rate_combo.addItem(str(r).title(), str(r).upper())
        self.rate_combo.blockSignals(False)

    def _fill_secondary(self):
        self.secondary_combo.blockSignals(True)
        self.secondary_combo.clear()
        self.secondary_combo.addItem("Off", None)
        for key in self.secondary_functions:
            self.secondary_combo.addItem(str(key), str(key))
        self.secondary_combo.blockSignals(False)
        self.secondary_combo.setEnabled(bool(self.secondary_functions))

    # ------------------------------------------------------------------ #
    # Contract
    # ------------------------------------------------------------------ #

    def configure(self, capabilities: Dict[str, Any]):
        functions = capabilities.get("functions")
        if functions:
            self.functions = [str(f).upper() for f in functions]
        ranges = capabilities.get("ranges")
        if isinstance(ranges, dict):
            self.ranges = {str(k).upper(): [float(v) for v in vals] for k, vals in ranges.items()}
        rates = capabilities.get("rates")
        if rates:
            self.rates = [str(r).upper() for r in rates]
        self.secondary_functions = [str(f).upper() for f in (capabilities.get("secondary_functions") or [])]
        self._fill_functions()
        self._fill_rates()
        self._fill_secondary()
        current = capabilities.get("function")
        if current:
            self._select_function(str(current).upper())
        self._fill_ranges()
    def _select_function(self, function: str):
        idx = self.function_combo.findData(function)
        if idx >= 0:
            self.function_combo.blockSignals(True)
            self.function_combo.setCurrentIndex(idx)
            self.function_combo.blockSignals(False)
        self._current_function = function

    async def refresh_settings(self):
        """Put the meter's present function/range/rate on the controls without commanding it."""
        if not (self.client and self.equipment):
            return
        readings = await call_blocking(self.client.get_readings, self.equipment.equipment_id)
        self._apply_readings(readings or {}, adopt_settings=True)

    def set_controls_enabled(self, enabled: bool):
        for w in (self.function_combo, self.range_combo, self.rate_combo,
                  self.math_combo, self.null_button):
            w.setEnabled(enabled)
        self.secondary_combo.setEnabled(enabled and bool(self.secondary_functions))

    def show_not_connected(self):
        self._blank()
        self.status_message.emit("Not connected. Connect it on the Equipment tab to read it.")

    def show_unsupported(self):
        self._blank()
        name = getattr(self.equipment, "name", "This instrument")
        self.status_message.emit(f"{name} does not report multimeter readings.")

    def clear_instrument(self):
        self._blank()

    def _blank(self):
        self.primary_display.setText("--")
        self.secondary_display.setText("")
        self.annunciator.setText("")
        self.statistics_label.setText("")

    # ------------------------------------------------------------------ #
    # Readings
    # ------------------------------------------------------------------ #

    async def poll(self):
        readings = await call_blocking(self.client.get_readings, self.equipment.equipment_id)
        self._apply_readings(readings or {})
        math_function = self.math_combo.currentData()
        if math_function in STATISTIC_MATH:
            try:
                stats = await self.send("get_statistics", {})
                self._show_statistics(stats or {})
            except Exception as e:
                logger.debug(f"Statistics unavailable: {e}")

    def _apply_readings(self, readings: Dict[str, Any], adopt_settings: bool = False):
        function = str(readings.get("function") or self._current_function or "").upper()
        unit = readings.get("unit") or UNITS.get(function, "")
        value = readings.get("value")
        overload = bool(readings.get("overload", False))
        self.primary_display.setText(format_reading(
            float(value) if value is not None else None, unit, overload))

        secondary = readings.get("secondary_function")
        if secondary:
            self.secondary_display.setText(
                f"{secondary}: " + format_reading(
                    readings.get("secondary_value"), readings.get("secondary_unit") or UNITS.get(str(secondary).upper(), ""))
            )
        else:
            self.secondary_display.setText("")

        flags = []
        if function:
            flags.append(function)
        if readings.get("auto_range"):
            flags.append("AUTO")
        elif readings.get("range_full_scale") is not None:
            flags.append(f"RANGE {format_reading(float(readings['range_full_scale']), unit)}")
        if readings.get("rate"):
            flags.append(str(readings["rate"]).upper())
        self.annunciator.setText("   ".join(flags))

        if adopt_settings or (function and function != self._current_function):
            if function:
                self._select_function(function)
                self._fill_ranges()
            if readings.get("auto_range"):
                self.range_combo.blockSignals(True)
                self.range_combo.setCurrentIndex(0)
                self.range_combo.blockSignals(False)
            elif readings.get("range_full_scale") is not None:
                idx = self.range_combo.findData(float(readings["range_full_scale"]))
                if idx >= 0:
                    self.range_combo.blockSignals(True)
                    self.range_combo.setCurrentIndex(idx)
                    self.range_combo.blockSignals(False)
            if readings.get("rate"):
                idx = self.rate_combo.findData(str(readings["rate"]).upper())
                if idx >= 0:
                    self.rate_combo.blockSignals(True)
                    self.rate_combo.setCurrentIndex(idx)
                    self.rate_combo.blockSignals(False)

    def _show_statistics(self, stats: Dict[str, Any]):
        unit = UNITS.get(self._current_function or "", "")
        parts = []
        for key, label in (("min", "min"), ("max", "max"), ("average", "avg")):
            if stats.get(key) is not None:
                parts.append(f"{label} {format_reading(float(stats[key]), unit)}")
        if stats.get("count") is not None:
            parts.append(f"n={int(float(stats['count']))}")
        self.statistics_label.setText("  ".join(parts))

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #

    def _command(self, name: str, parameters: Optional[Dict[str, Any]] = None):
        self._send_command(name, parameters or {})

    @qasync.asyncSlot(str, dict)
    async def _send_command(self, name: str, parameters: dict):
        try:
            return await self.send(name, parameters)
        except Exception as e:
            logger.error(f"{name} failed: {e}")
            self.status_message.emit(f"{name.replace('_', ' ')} failed: {e}")

    def _on_function_chosen(self, _index: int):
        function = self.function_combo.currentData()
        if not function:
            return
        self._current_function = function
        self._fill_ranges()
        self.statistics_label.setText("")
        self._command("set_function", {"function": function})

    def _on_range_chosen(self, _index: int):
        function = self.function_combo.currentData()
        choice = self.range_combo.currentData()
        if choice == "AUTO":
            self._command("set_auto_range", {"enabled": True, "function": function})
        elif choice is not None:
            self._command("set_range", {"range": float(choice), "function": function})

    def _on_rate_chosen(self, _index: int):
        rate = self.rate_combo.currentData()
        if rate:
            self._command("set_rate", {"rate": rate, "function": self.function_combo.currentData()})

    def _on_secondary_chosen(self, _index: int):
        choice = self.secondary_combo.currentData()
        if choice is None:
            self._command("clear_secondary_function", {})
        else:
            self._command("set_secondary_function", {"function": choice})

    def _on_math_chosen(self, _index: int):
        math_function = self.math_combo.currentData()
        self.statistics_label.setText("")
        self._command("set_math_function", {"math_function": math_function})
