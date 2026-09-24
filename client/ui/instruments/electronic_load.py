"""The electronic-load panel: mode, setpoint, input on/off, and what it sinks.

A load is a supply turned around: one setpoint whose meaning depends on the
mode (amps in CC, volts in CV, ohms in CR, watts in CP), an input switch in
place of an output switch, and the same three live numbers. The setpoint is
sent on Apply, not on every spinbox tick, so re-ranging on a device switch
can never command the instrument.

Commands (Rigol DL3000 and B&K SCPI loads alike): ``set_mode``,
``set_current`` / ``set_voltage`` / ``set_resistance`` / ``set_power``,
``set_input``; readings come from ``GET /equipment/{id}/readings``
(``ElectronicLoadData``).
"""

import logging
from typing import Any, Dict

import qasync
from PyQt6.QtWidgets import (QComboBox, QDoubleSpinBox, QGridLayout, QGroupBox,
                             QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                             QVBoxLayout, QWidget)

from client.api.client import call_blocking
from client.ui.instruments.base import POLL_READINGS, InstrumentPanel
from client.ui.instruments.measurement_views import (Channel,
                                                     MeasurementViews)

logger = logging.getLogger(__name__)

MODES = {
    "CC": ("Constant current", "A", "set_current", "current"),
    "CV": ("Constant voltage", "V", "set_voltage", "voltage"),
    "CR": ("Constant resistance", "Ohm", "set_resistance", "resistance"),
    "CP": ("Constant power", "W", "set_power", "power"),
}


#: What the input button says in each state. "Enabled"/"disabled"
#: describes the load, where "Input: ON" described a terminal -- and on
#: a bench beside a supply's Output button, the operator reading it
#: wants to know whether this thing is sinking, not which end the
#: current comes in.
_INPUT_LABEL = {True: "Load enabled", False: "Load disabled"}


class ElectronicLoadPanel(InstrumentPanel):
    """Drive a DC electronic load and watch what it draws."""

    POLLS = POLL_READINGS
    DEFAULT_INTERVAL_MS = 200
    SETTINGS_TYPE = "electronic_load"

    def __init__(self, parent=None):
        self.max_voltage = 150.0
        self.max_current = 40.0
        self.max_power = 200.0
        self.max_resistance = 15000.0
        super().__init__(parent)

    # The readouts moved into MeasurementViews when the three display
    # modes became shared with the supply. These keep the panel's own
    # names pointing at them, so call sites and tests that ask the panel
    # for a reading still get one.
    @property
    def voltage_display(self):
        return self.views.displays["voltage"]

    @property
    def current_display(self):
        return self.views.displays["current"]

    @property
    def power_display(self):
        return self.views.displays["power"]

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        controls = QGroupBox("Load")
        grid = QGridLayout(controls)
        grid.addWidget(QLabel("Mode:"), 0, 0)
        self.mode_combo = QComboBox()
        for key, (label, _unit, _cmd, _field) in MODES.items():
            self.mode_combo.addItem(f"{key} — {label}", key)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        grid.addWidget(self.mode_combo, 0, 1)

        self.setpoint_label = QLabel("Current (A):")
        grid.addWidget(self.setpoint_label, 1, 0)
        self.setpoint_spin = QDoubleSpinBox()
        self.setpoint_spin.setDecimals(3)
        self.setpoint_spin.setSingleStep(0.1)
        self.setpoint_spin.setRange(0.0, self.max_current)
        grid.addWidget(self.setpoint_spin, 1, 1)

        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self._apply_setpoint)
        grid.addWidget(self.apply_button, 0, 2, 2, 1)

        # "Input" is the instrument's own word for the terminals, and on
        # a panel next to a supply's "Output" it reads as the same kind of
        # thing seen from the other end -- which tells an operator nothing
        # about whether the load is currently sinking. Say what it is.
        self.input_button = QPushButton("Load disabled")
        self.input_button.setCheckable(True)
        self.input_button.setStyleSheet(
            "QPushButton:checked { background-color: #b06000; color: white; }"
        )
        self.input_button.clicked.connect(self._on_input_toggled)
        grid.addWidget(self.input_button, 0, 3, 2, 1)
        layout.addWidget(controls)

        # The same digital / analog / graph views the supply has, over
        # volts, amps and watts. A load's three quantities are exactly
        # what MeasurementViews takes, so this is the whole of it.
        self.views = MeasurementViews((
            Channel("voltage", "Voltage", "V", 3, self.max_voltage, 1.0,
                    "#4a9eff"),
            Channel("current", "Current", "A", 3, self.max_current, 0.1,
                    "#ff9d4a"),
            Channel("power", "Power", "W", 2, self.max_power, 1.0,
                    "#7ed957"),
        ))
        layout.addWidget(self.views, 1)

        status = QHBoxLayout()
        self.mode_indicator = QLabel("Mode: --")
        self.setpoint_indicator = QLabel("Setpoint: --")
        status.addWidget(self.mode_indicator)
        status.addWidget(self.setpoint_indicator)
        status.addStretch()
        status.addWidget(self._create_rate_control("How often to read voltage, current and power"))
        layout.addLayout(status)

    # ------------------------------------------------------------------ #
    # Contract
    # ------------------------------------------------------------------ #

    def configure(self, capabilities: Dict[str, Any]):
        self.max_voltage = float(capabilities.get("max_voltage") or self.max_voltage)
        self.max_current = float(capabilities.get("max_current") or self.max_current)
        self.max_power = float(capabilities.get("max_power") or self.max_power)
        modes = capabilities.get("modes")
        if modes:
            self.mode_combo.blockSignals(True)
            self.mode_combo.clear()
            for key in modes:
                key = str(key).upper()
                if key in MODES:
                    self.mode_combo.addItem(f"{key} — {MODES[key][0]}", key)
            self.mode_combo.blockSignals(False)
        self._range_setpoint()
    async def refresh_settings(self):
        """Put the load's own mode/setpoint/input on the controls, silently."""
        if not (self.client and self.equipment):
            return
        readings = await call_blocking(self.client.get_readings, self.equipment.equipment_id)
        self._apply_readings(readings or {}, adopt_setpoint=True)

    def _range_setpoint(self):
        mode = self.mode_combo.currentData() or "CC"
        _label, unit, _cmd, _field = MODES[mode]
        maximum = {"CC": self.max_current, "CV": self.max_voltage,
                   "CR": self.max_resistance, "CP": self.max_power}[mode]
        self.setpoint_spin.blockSignals(True)
        self.setpoint_spin.setRange(0.0, maximum)
        self.setpoint_spin.setDecimals(1 if mode == "CR" else 3)
        self.setpoint_spin.blockSignals(False)
        self.setpoint_label.setText(f"{_label.split()[1].capitalize()} ({unit}):")

    def set_controls_enabled(self, enabled: bool):
        for w in (self.mode_combo, self.setpoint_spin, self.apply_button, self.input_button):
            w.setEnabled(enabled)

    def show_not_connected(self):
        self._blank()
        self.status_message.emit("Not connected. Connect it on the Equipment tab to read it.")

    def show_unsupported(self):
        self._blank()
        name = getattr(self.equipment, "name", "This instrument")
        self.status_message.emit(f"{name} does not report load readings.")

    def clear_instrument(self):
        self._blank()

    def _blank(self):
        self.views.blank()
        self.mode_indicator.setText("Mode: --")
        self.setpoint_indicator.setText("Setpoint: --")

    # ------------------------------------------------------------------ #
    # Readings
    # ------------------------------------------------------------------ #

    async def poll(self):
        readings = await call_blocking(self.client.get_readings, self.equipment.equipment_id)
        self._apply_readings(readings or {})

    def _apply_readings(self, readings: Dict[str, Any], adopt_setpoint: bool = False):
        import time

        voltage = readings.get("voltage")
        current = readings.get("current")
        power = readings.get("power")
        self.views.set_readings({"voltage": voltage, "current": current,
                                 "power": power})

        mode = str(readings.get("mode") or "").upper()
        if mode in MODES:
            self.mode_indicator.setText(f"Mode: {mode}")
            if adopt_setpoint:
                idx = self.mode_combo.findData(mode)
                if idx >= 0:
                    self.mode_combo.blockSignals(True)
                    self.mode_combo.setCurrentIndex(idx)
                    self.mode_combo.blockSignals(False)
                    self._range_setpoint()
        setpoint = readings.get("setpoint")
        if setpoint is not None and mode in MODES:
            self.setpoint_indicator.setText(f"Setpoint: {float(setpoint):g} {MODES[mode][1]}")
            if adopt_setpoint:
                self.setpoint_spin.blockSignals(True)
                self.setpoint_spin.setValue(float(setpoint))
                self.setpoint_spin.blockSignals(False)

        # Unless the operator has just clicked the button and the load has
        # not caught up: until it agrees, the click is what is true. A
        # reading with no input state in it says nothing, rather than
        # "off" -- reporting a load that is still sinking as off is the
        # dangerous direction to be wrong in.
        reported = readings.get("load_enabled")
        if reported is not None and self.may_show("input", reported):
            enabled = bool(reported)
            self.input_button.blockSignals(True)
            self.input_button.setChecked(enabled)
            self.input_button.setText(_INPUT_LABEL[enabled])
            self.input_button.blockSignals(False)

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #

    def _on_mode_changed(self, _index: int):
        self._range_setpoint()

    def _apply_setpoint(self):
        mode = self.mode_combo.currentData() or "CC"
        _label, _unit, command, field = MODES[mode]
        self._send_setpoint(mode, command, field, float(self.setpoint_spin.value()))

    @qasync.asyncSlot(str, str, str, float)
    async def _send_setpoint(self, mode: str, command: str, field: str, value: float):
        """Mode first, then the setpoint that mode gives meaning to."""
        try:
            await self.send("set_mode", {"mode": mode})
            await self.send(command, {field: value})
            self.setpoint_indicator.setText(f"Setpoint: {value:g} {MODES[mode][1]}")
            self.mode_indicator.setText(f"Mode: {mode}")
        except Exception as e:
            logger.error(f"Setting the load failed: {e}")
            self.status_message.emit(f"Setting the load failed: {e}")

    def _on_input_toggled(self, checked: bool):
        # Recorded here, not in the slot below: an @asyncSlot only
        # schedules, and by the time its body runs a reading taken before
        # the click can already have been applied.
        self.commanded("input", bool(checked))
        self.input_button.setText(_INPUT_LABEL[checked])
        self._send_input(bool(checked))

    @qasync.asyncSlot(bool)
    async def _send_input(self, enabled: bool):
        try:
            await self.send("set_input", {"enabled": enabled})
        except Exception as e:
            logger.error(f"Switching the load input failed: {e}")
            self.status_message.emit(f"Switching the load input failed: {e}")
