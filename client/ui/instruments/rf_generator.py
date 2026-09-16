"""The RF signal-generator panel: carrier, level, RF on/off, modulation, sweep.

An RF source has two numbers that matter -- frequency and level -- and a
switch. They get the big readouts and the direct controls. Modulation and
the step sweep are groups with their own Apply. The poll reads the settings
back so a change made at the front panel shows up here.

Commands (Rigol DSG800 / DSG3000 / DSG5000 share them): ``set_frequency``,
``set_level``, ``set_output``, ``set_alc``, ``set_modulation``, ``set_sweep``,
``get_readings``.
"""

import logging
import math
from typing import Any, Dict, List, Optional

import qasync
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QGridLayout,
                             QGroupBox, QHBoxLayout, QLabel, QPushButton,
                             QSpinBox, QVBoxLayout, QWidget)

from client.ui.instruments.base import POLL_STATE, InstrumentPanel
from client.ui.instruments.widgets import FittedReadout

logger = logging.getLogger(__name__)

FREQUENCY_UNITS = [("GHz", 1e9), ("MHz", 1e6), ("kHz", 1e3), ("Hz", 1.0)]
MODULATION_PARAMS = {
    "AM": ("Depth (%):", "depth"),
    "FM": ("Deviation (Hz):", "deviation"),
    "PM": ("Deviation (rad):", "deviation"),
    "PULSE": ("Width (s):", "width"),
    "IQ": ("", None),
}


def format_frequency(hz: Optional[float]) -> str:
    if hz is None or (isinstance(hz, float) and math.isnan(hz)):
        return "--"
    for unit, factor in FREQUENCY_UNITS:
        if abs(hz) >= factor or factor == 1.0:
            return f"{hz / factor:.9g} {unit}"
    return f"{hz:g} Hz"


class RFGeneratorPanel(InstrumentPanel):
    """Drive an RF signal generator."""

    POLLS = POLL_STATE
    DEFAULT_INTERVAL_MS = 1000
    SETTINGS_TYPE = "rf_signal_generator"

    def __init__(self, parent=None):
        self.frequency_min = 9e3
        self.frequency_max = 3.6e9
        self.level_min = -130.0
        self.level_max = 20.0
        self.modulation_types: List[str] = ["AM", "FM", "PM"]
        self._last_output_command_time = 0.0
        super().__init__(parent)

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        left = QVBoxLayout()
        face = QWidget()
        face.setObjectName("rfPanel")
        face.setStyleSheet("QWidget#rfPanel { background-color: black; border-radius: 6px; }")
        face_layout = QVBoxLayout(face)
        face_layout.setContentsMargins(12, 12, 12, 12)
        self.frequency_display = FittedReadout("--")
        face_layout.addWidget(self.frequency_display, 2)
        self.level_display = FittedReadout("--")
        self.level_display.MAX_POINT_SIZE = 72
        face_layout.addWidget(self.level_display, 1)
        self.annunciator = QLabel("")
        self.annunciator.setStyleSheet("QLabel { color: #39FF14; background: transparent; }")
        face_layout.addWidget(self.annunciator)
        left.addWidget(face, 1)
        left.addWidget(self._create_carrier_controls())
        outer.addLayout(left, 3)

        right = QVBoxLayout()
        right.addWidget(self._create_modulation_controls())
        right.addWidget(self._create_sweep_controls())
        right.addWidget(self._create_rate_control("How often to read the generator's settings back"))
        right.addStretch()
        outer.addLayout(right, 2)

    def _create_carrier_controls(self) -> QGroupBox:
        group = QGroupBox("Carrier")
        grid = QGridLayout(group)
        grid.addWidget(QLabel("Frequency:"), 0, 0)
        self.frequency_spin = QDoubleSpinBox()
        self.frequency_spin.setRange(0.0, 1e12)
        self.frequency_spin.setDecimals(6)
        self.frequency_spin.setValue(100.0)
        grid.addWidget(self.frequency_spin, 0, 1)
        self.frequency_unit = QComboBox()
        for unit, factor in FREQUENCY_UNITS:
            self.frequency_unit.addItem(unit, factor)
        self.frequency_unit.setCurrentIndex(1)  # MHz
        grid.addWidget(self.frequency_unit, 0, 2)
        self.frequency_apply = QPushButton("Set")
        self.frequency_apply.clicked.connect(self._apply_frequency)
        grid.addWidget(self.frequency_apply, 0, 3)

        grid.addWidget(QLabel("Level (dBm):"), 1, 0)
        self.level_spin = QDoubleSpinBox()
        self.level_spin.setRange(self.level_min, self.level_max)
        self.level_spin.setDecimals(2)
        self.level_spin.setSingleStep(1.0)
        self.level_spin.setValue(-30.0)
        grid.addWidget(self.level_spin, 1, 1)
        self.level_apply = QPushButton("Set")
        self.level_apply.clicked.connect(self._apply_level)
        grid.addWidget(self.level_apply, 1, 3)

        self.output_button = QPushButton("RF: OFF")
        self.output_button.setCheckable(True)
        self.output_button.setStyleSheet("QPushButton:checked { background-color: #b00020; color: white; }")
        self.output_button.clicked.connect(self._on_output_toggled)
        grid.addWidget(self.output_button, 2, 0, 1, 2)
        self.alc_check = QCheckBox("ALC")
        self.alc_check.setToolTip("Automatic level control")
        self.alc_check.toggled.connect(lambda on: self._command("set_alc", {"enabled": bool(on)}))
        grid.addWidget(self.alc_check, 2, 2, 1, 2)
        return group

    def _create_modulation_controls(self) -> QGroupBox:
        group = QGroupBox("Modulation")
        grid = QGridLayout(group)
        self.mod_enable = QCheckBox("Enabled")
        grid.addWidget(self.mod_enable, 0, 0, 1, 2)
        grid.addWidget(QLabel("Type:"), 1, 0)
        self.mod_type = QComboBox()
        self._fill_modulation_types()
        self.mod_type.currentIndexChanged.connect(self._on_mod_type_changed)
        grid.addWidget(self.mod_type, 1, 1)
        self.mod_param_label = QLabel("Depth (%):")
        grid.addWidget(self.mod_param_label, 2, 0)
        self.mod_param = QDoubleSpinBox()
        self.mod_param.setRange(0.0, 1e9)
        self.mod_param.setDecimals(4)
        self.mod_param.setValue(30.0)
        grid.addWidget(self.mod_param, 2, 1)
        grid.addWidget(QLabel("Mod. freq (Hz):"), 3, 0)
        self.mod_frequency = QDoubleSpinBox()
        self.mod_frequency.setRange(0.001, 1e7)
        self.mod_frequency.setDecimals(3)
        self.mod_frequency.setValue(1000.0)
        grid.addWidget(self.mod_frequency, 3, 1)
        grid.addWidget(QLabel("Source:"), 4, 0)
        self.mod_source = QComboBox()
        self.mod_source.addItem("Internal", "INT")
        self.mod_source.addItem("External", "EXT")
        grid.addWidget(self.mod_source, 4, 1)
        self.mod_apply = QPushButton("Apply modulation")
        self.mod_apply.clicked.connect(self._apply_modulation)
        grid.addWidget(self.mod_apply, 5, 0, 1, 2)
        self._on_mod_type_changed(0)
        return group

    def _create_sweep_controls(self) -> QGroupBox:
        group = QGroupBox("Step sweep (frequency)")
        grid = QGridLayout(group)
        grid.addWidget(QLabel("Start (MHz):"), 0, 0)
        self.sweep_start = QDoubleSpinBox()
        self.sweep_start.setRange(0.0, 1e6)
        self.sweep_start.setDecimals(6)
        self.sweep_start.setValue(100.0)
        grid.addWidget(self.sweep_start, 0, 1)
        grid.addWidget(QLabel("Stop (MHz):"), 1, 0)
        self.sweep_stop = QDoubleSpinBox()
        self.sweep_stop.setRange(0.0, 1e6)
        self.sweep_stop.setDecimals(6)
        self.sweep_stop.setValue(200.0)
        grid.addWidget(self.sweep_stop, 1, 1)
        grid.addWidget(QLabel("Points:"), 2, 0)
        self.sweep_points = QSpinBox()
        self.sweep_points.setRange(2, 65535)
        self.sweep_points.setValue(11)
        grid.addWidget(self.sweep_points, 2, 1)
        grid.addWidget(QLabel("Dwell (s):"), 3, 0)
        self.sweep_dwell = QDoubleSpinBox()
        self.sweep_dwell.setRange(0.0001, 100.0)
        self.sweep_dwell.setDecimals(4)
        self.sweep_dwell.setValue(0.01)
        grid.addWidget(self.sweep_dwell, 3, 1)
        self.sweep_continuous = QCheckBox("Continuous")
        grid.addWidget(self.sweep_continuous, 4, 0, 1, 2)
        self.sweep_apply = QPushButton("Apply sweep")
        self.sweep_apply.clicked.connect(self._apply_sweep)
        grid.addWidget(self.sweep_apply, 5, 0, 1, 2)
        return group

    def _fill_modulation_types(self):
        current = self.mod_type.currentData() if self.mod_type.count() else None
        self.mod_type.blockSignals(True)
        self.mod_type.clear()
        for t in self.modulation_types:
            self.mod_type.addItem(t, t)
        idx = self.mod_type.findData(current)
        self.mod_type.setCurrentIndex(idx if idx >= 0 else 0)
        self.mod_type.blockSignals(False)
        if hasattr(self, "mod_param_label"):   # built after the combo on first fill
            self._on_mod_type_changed(0)

    # ------------------------------------------------------------------ #
    # Contract
    # ------------------------------------------------------------------ #

    def configure(self, capabilities: Dict[str, Any]):
        self.frequency_min = float(capabilities.get("frequency_min") or self.frequency_min)
        self.frequency_max = float(capabilities.get("frequency_max") or self.frequency_max)
        self.level_min = float(capabilities.get("level_min_dbm") or self.level_min)
        self.level_max = float(capabilities.get("level_max_dbm") or self.level_max)
        self.level_spin.setRange(self.level_min, self.level_max)
        mods = capabilities.get("modulation_types")
        if mods:
            self.modulation_types = [str(m).upper() for m in mods]
            self._fill_modulation_types()
        self._show_current_settings()

    def _show_current_settings(self):
        if not (self.client and self.equipment):
            return
        try:
            result = self.client.send_command(self.equipment.equipment_id, "get_readings", {"channel": 1})
            if not result.get("success"):
                return
            data = result.get("data") or {}
        except Exception as e:
            logger.debug(f"Could not read RF generator settings: {e}")
            return
        self._apply_settings(data, adopt=True)

    def _apply_settings(self, data: Dict[str, Any], adopt: bool = False):
        import time

        freq = data.get("frequency")
        level = data.get("level")
        unit = data.get("level_unit") or "dBm"
        self.frequency_display.setText(format_frequency(float(freq)) if freq is not None else "--")
        self.level_display.setText(f"{float(level):.2f} {unit}" if level is not None else "--")
        flags = []
        if data.get("output_enabled"):
            flags.append("RF ON")
        if data.get("modulation_enabled"):
            flags.append(f"MOD {data.get('modulation_type') or ''}".strip())
        if data.get("alc_enabled"):
            flags.append("ALC")
        self.annunciator.setText("   ".join(flags))

        if time.monotonic() - self._last_output_command_time > 2.0:
            enabled = bool(data.get("output_enabled", False))
            self.output_button.blockSignals(True)
            self.output_button.setChecked(enabled)
            self.output_button.setText("RF: ON" if enabled else "RF: OFF")
            self.output_button.blockSignals(False)

        if adopt:
            widgets = (self.frequency_spin, self.frequency_unit, self.level_spin, self.alc_check,
                       self.mod_enable, self.mod_type)
            for w in widgets:
                w.blockSignals(True)
            try:
                if freq is not None:
                    freq = float(freq)
                    for i, (_unit, factor) in enumerate(FREQUENCY_UNITS):
                        if freq >= factor or factor == 1.0:
                            self.frequency_unit.setCurrentIndex(i)
                            self.frequency_spin.setValue(freq / factor)
                            break
                if level is not None:
                    self.level_spin.setValue(float(level))
                if data.get("alc_enabled") is not None:
                    self.alc_check.setChecked(bool(data["alc_enabled"]))
                self.mod_enable.setChecked(bool(data.get("modulation_enabled")))
                if data.get("modulation_type"):
                    idx = self.mod_type.findData(str(data["modulation_type"]).upper())
                    if idx >= 0:
                        self.mod_type.setCurrentIndex(idx)
                        self._on_mod_type_changed(idx)
            finally:
                for w in widgets:
                    w.blockSignals(False)

    def set_controls_enabled(self, enabled: bool):
        for w in (self.frequency_spin, self.frequency_unit, self.frequency_apply, self.level_spin,
                  self.level_apply, self.output_button, self.alc_check, self.mod_apply, self.sweep_apply):
            w.setEnabled(enabled)

    def show_not_connected(self):
        self.frequency_display.setText("--")
        self.level_display.setText("--")
        self.status_message.emit("Not connected. Connect it on the Equipment tab to read it.")

    def show_unsupported(self):
        self.frequency_display.setText("--")
        name = getattr(self.equipment, "name", "This instrument")
        self.status_message.emit(f"{name} does not report RF generator settings.")

    def clear_instrument(self):
        self.frequency_display.setText("--")
        self.level_display.setText("--")
        self.annunciator.setText("")

    # ------------------------------------------------------------------ #
    # Polling
    # ------------------------------------------------------------------ #

    async def poll(self):
        data = await self.send("get_readings", {"channel": 1})
        self._apply_settings(data or {})

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

    def frequency_hz(self) -> float:
        return float(self.frequency_spin.value()) * float(self.frequency_unit.currentData() or 1.0)

    def _apply_frequency(self):
        hz = self.frequency_hz()
        if not (self.frequency_min <= hz <= self.frequency_max):
            self.status_message.emit(
                f"Frequency must be between {format_frequency(self.frequency_min)} and "
                f"{format_frequency(self.frequency_max)}"
            )
            return
        self._command("set_frequency", {"frequency": hz})

    def _apply_level(self):
        self._command("set_level", {"level": float(self.level_spin.value()), "unit": "dBm"})

    def _on_output_toggled(self, checked: bool):
        import time

        self._last_output_command_time = time.monotonic()
        self.output_button.setText("RF: ON" if checked else "RF: OFF")
        self._command("set_output", {"enabled": bool(checked)})

    def _on_mod_type_changed(self, _index: int):
        mod_type = self.mod_type.currentData() or "AM"
        label, param = MODULATION_PARAMS.get(mod_type, ("Deviation:", "deviation"))
        self.mod_param_label.setText(label)
        self.mod_param.setEnabled(param is not None)
        # A pulse width is microseconds; a depth is whole percent.
        self.mod_param.setDecimals({"AM": 2, "FM": 3, "PM": 4, "PULSE": 9}.get(mod_type, 4))
        self.mod_frequency.setEnabled(mod_type in ("AM", "FM", "PM"))

    def _apply_modulation(self):
        mod_type = self.mod_type.currentData() or "AM"
        payload: Dict[str, Any] = {"type": mod_type, "enabled": self.mod_enable.isChecked(),
                                   "source": self.mod_source.currentData()}
        _label, param = MODULATION_PARAMS.get(mod_type, ("", "deviation"))
        if param:
            payload[param] = float(self.mod_param.value())
        if mod_type in ("AM", "FM", "PM"):
            payload["frequency"] = float(self.mod_frequency.value())
        self._command("set_modulation", payload)

    def _apply_sweep(self):
        self._command("set_sweep", {
            "mode": "FREQ",
            "start_frequency": float(self.sweep_start.value()) * 1e6,
            "stop_frequency": float(self.sweep_stop.value()) * 1e6,
            "points": int(self.sweep_points.value()),
            "dwell": float(self.sweep_dwell.value()),
            "continuous": self.sweep_continuous.isChecked(),
        })
