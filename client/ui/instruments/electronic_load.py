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

import asyncio
import logging
from typing import Any, Dict

import qasync
from PyQt6.QtWidgets import (QComboBox, QDoubleSpinBox, QGridLayout, QGroupBox,
                             QHBoxLayout, QLabel, QMessageBox, QPushButton,
                             QSizePolicy, QVBoxLayout, QWidget)

from client.api.client import call_blocking
from client.ui.instruments.base import POLL_READINGS, InstrumentPanel
from client.ui.instruments.measurement_views import (Channel,
                                                     MeasurementViews)
from client.utils.modals import ask

logger = logging.getLogger(__name__)

MODES = {
    "CC": ("Constant current", "A", "set_current", "current"),
    "CV": ("Constant voltage", "V", "set_voltage", "voltage"),
    "CR": ("Constant resistance", "Ohm", "set_resistance", "resistance"),
    "CP": ("Constant power", "W", "set_power", "power"),
}

#: Which capability lists the ranges for a mode, and the command that
#: selects one. The user guide puts "range" among the parameters under
#: each mode key -- CC has current and range, CV voltage and range --
#: so it belongs beside the setpoint rather than in a settings dialog.
#:
#: CP has no range of its own on these loads: the SCPI tree has
#: :SOUR:CURR:RANG, :VOLT:RANG and :RES:RANG and nothing for power, so
#: the selector is hidden in constant power rather than offered and
#: then refused.
MODE_RANGES = {
    "CC": ("current_ranges", "set_current_range", "A"),
    "CV": ("voltage_ranges", "set_voltage_range", "V"),
    "CR": ("resistance_ranges", "set_resistance_range", "Ohm"),
}


#: Transient operation modes, and the timing each one actually uses.
#:
#: The guide splits these: :AWIDth and :BWIDth apply to continuous and
#: pulsed, while :FREQuency and :ADUTy are continuous only, and they
#: describe the same thing twice -- period is A plus B, duty is A over
#: the period. Offering both at once lets the operator set two
#: contradictory timings and wonder which won, so each mode shows the
#: one it is usually thought about in: a repetitive stream by frequency
#: and duty, a single pulse by how long each level lasts. Toggle needs
#: neither; it alternates on triggers rather than on a clock.
TRANSIENT_MODES = {
    "CON": ("Continuous", "frequency"),
    "PUL": ("Pulsed", "widths"),
    "TOG": ("Toggled", "none"),
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
        #: Ranges the load reports per mode, from its capabilities.
        self._available_ranges = {}
        #: Whether this load has CC slew rate and starting voltage. Not
        #: every load in the registry is a DL3000.
        self._supports_cc_extras = False
        #: ...and whether it has a transient generator.
        self._supports_transient = False
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

        self.range_label = QLabel("Range:")
        grid.addWidget(self.range_label, 2, 0)
        self.range_combo = QComboBox()
        self.range_combo.setToolTip(
            "Low range resolves finer; high range reaches further.\n"
            "The load keeps one per mode, as the front panel does."
        )
        self.range_combo.currentIndexChanged.connect(self._on_range_changed)
        grid.addWidget(self.range_combo, 2, 1)

        # CC carries two more parameters, both listed under the CC key
        # in the user guide and both meaningless in the other modes, so
        # they appear and disappear with it rather than sitting greyed
        # out in CV.
        self.cc_extras = QWidget()
        extras = QHBoxLayout(self.cc_extras)
        extras.setContentsMargins(0, 0, 0, 0)

        extras.addWidget(QLabel("Slew (A/us):"))
        self.slew_spin = QDoubleSpinBox()
        self.slew_spin.setDecimals(3)
        self.slew_spin.setSingleStep(0.01)
        # No ceiling of our own: the per-model maximum is not something
        # the panel knows, and the load rejects what it cannot do --
        # audibly now that control commands read the error queue.
        self.slew_spin.setRange(0.001, 100.0)
        self.slew_spin.setValue(0.5)
        self.slew_spin.setToolTip(
            "How fast the sink current may change, rising and falling\n"
            "alike. CC mode only."
        )
        extras.addWidget(self.slew_spin)

        extras.addWidget(QLabel("Von (V):"))
        self.von_spin = QDoubleSpinBox()
        self.von_spin.setDecimals(2)
        self.von_spin.setSingleStep(0.1)
        self.von_spin.setRange(0.0, self.max_voltage)
        self.von_spin.setToolTip(
            "Starting voltage. The load begins sinking once the input\n"
            "rises above this and stops when it falls back below, which\n"
            "is what keeps it off while a source is still coming up."
        )
        extras.addWidget(self.von_spin)

        self.cc_apply_button = QPushButton("Apply CC options")
        self.cc_apply_button.clicked.connect(self._apply_cc_options)
        extras.addWidget(self.cc_apply_button)
        extras.addStretch()
        grid.addWidget(self.cc_extras, 3, 0, 1, 4)

        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self._apply_setpoint)
        grid.addWidget(self.apply_button, 0, 2, 3, 1)

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
        grid.addWidget(self.input_button, 0, 3, 3, 1)
        layout.addWidget(controls)

        # Transient operation -- the Con, Pul and Tog keys. Inside CC
        # because that is where the instrument puts it: the levels are
        # currents and the guide calls it "transient operation mode in
        # CC mode".
        #
        # The group's own checkbox is the generator's on/off, which is
        # what :SOUR:TRAN:STAT does and what the TRAN key does.
        # Not a checkable group. :SOUR:TRAN:STAT reads back False after
        # a trigger, and the guide describes it as "the same effect as
        # pressing the TRAN key" -- it arms the generator, which then
        # sinks Level B and waits. A checkbox says "this is on until I
        # untick it", which is not what the instrument does, and on the
        # bench it sat unticking itself.
        self.transient_group = QGroupBox("Transient (dynamic) operation")
        tgrid = QGridLayout(self.transient_group)

        tgrid.addWidget(QLabel("Mode:"), 0, 0)
        self.transient_mode_combo = QComboBox()
        for key, (label, _timing) in TRANSIENT_MODES.items():
            self.transient_mode_combo.addItem(label, key)
        self.transient_mode_combo.currentIndexChanged.connect(
            self._on_transient_mode_changed)
        tgrid.addWidget(self.transient_mode_combo, 0, 1)

        tgrid.addWidget(QLabel("Level A (A):"), 0, 2)
        self.level_a_spin = QDoubleSpinBox()
        self.level_a_spin.setDecimals(3)
        self.level_a_spin.setRange(0.0, self.max_current)
        self.level_a_spin.setToolTip("The high value it sinks at")
        tgrid.addWidget(self.level_a_spin, 0, 3)

        tgrid.addWidget(QLabel("Level B (A):"), 0, 4)
        self.level_b_spin = QDoubleSpinBox()
        self.level_b_spin.setDecimals(3)
        self.level_b_spin.setRange(0.0, self.max_current)
        self.level_b_spin.setToolTip("The low value it drops back to")
        tgrid.addWidget(self.level_b_spin, 0, 5)

        # Frequency and duty, for continuous.
        self.frequency_label = QLabel("Frequency (kHz):")
        tgrid.addWidget(self.frequency_label, 1, 0)
        self.frequency_spin = QDoubleSpinBox()
        self.frequency_spin.setDecimals(3)
        self.frequency_spin.setRange(0.001, 30.0)
        self.frequency_spin.setValue(1.0)
        self.frequency_spin.setToolTip(
            "Kilohertz, which is the unit the load takes.\n"
            "The ceiling is per model: 15 kHz, or 30 on an A model."
        )
        tgrid.addWidget(self.frequency_spin, 1, 1)

        self.duty_label = QLabel("Duty (%):")
        tgrid.addWidget(self.duty_label, 1, 2)
        self.duty_spin = QDoubleSpinBox()
        self.duty_spin.setDecimals(0)
        self.duty_spin.setRange(1, 100)
        self.duty_spin.setValue(50)
        self.duty_spin.setToolTip("Share of each period spent at Level A")
        tgrid.addWidget(self.duty_spin, 1, 3)

        # A and B widths, for pulsed.
        self.a_width_label = QLabel("A width (ms):")
        tgrid.addWidget(self.a_width_label, 2, 0)
        self.a_width_spin = QDoubleSpinBox()
        self.a_width_spin.setDecimals(3)
        self.a_width_spin.setRange(0.001, 10000.0)
        self.a_width_spin.setValue(1.0)
        tgrid.addWidget(self.a_width_spin, 2, 1)

        self.b_width_label = QLabel("B width (ms):")
        tgrid.addWidget(self.b_width_label, 2, 2)
        self.b_width_spin = QDoubleSpinBox()
        self.b_width_spin.setDecimals(3)
        self.b_width_spin.setRange(0.001, 10000.0)
        self.b_width_spin.setValue(1.0)
        tgrid.addWidget(self.b_width_spin, 2, 3)

        tgrid.addWidget(QLabel("Rise (A/us):"), 1, 4)
        self.rise_spin = QDoubleSpinBox()
        self.rise_spin.setDecimals(3)
        self.rise_spin.setRange(0.001, 100.0)
        self.rise_spin.setValue(0.5)
        tgrid.addWidget(self.rise_spin, 1, 5)

        tgrid.addWidget(QLabel("Fall (A/us):"), 2, 4)
        self.fall_spin = QDoubleSpinBox()
        self.fall_spin.setDecimals(3)
        self.fall_spin.setRange(0.001, 100.0)
        self.fall_spin.setValue(0.5)
        tgrid.addWidget(self.fall_spin, 2, 5)

        self.transient_apply_button = QPushButton("Apply transient")
        self.transient_apply_button.clicked.connect(self._apply_transient)
        tgrid.addWidget(self.transient_apply_button, 3, 0, 1, 2)

        self.arm_button = QPushButton("Arm")
        self.arm_button.setToolTip(
            "Arm the transient generator. The load then sinks Level B\n"
            "and waits for a trigger, which is what the front-panel TRAN\n"
            "key does."
        )
        self.arm_button.clicked.connect(self._arm_transient)
        tgrid.addWidget(self.arm_button, 3, 4)

        self.trigger_button = QPushButton("Trigger")
        self.trigger_button.setToolTip(
            "Fire one trigger. The load's default trigger source is the\n"
            "front-panel TRAN key, so this selects the bus source first --\n"
            "otherwise the command is accepted and does nothing."
        )
        self.trigger_button.clicked.connect(self._fire_trigger)
        tgrid.addWidget(self.trigger_button, 3, 2, 1, 2)

        layout.addWidget(self.transient_group)

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
        self._available_ranges = {
            mode: [float(v) for v in (capabilities.get(key) or [])]
            for mode, (key, _cmd, _unit) in MODE_RANGES.items()
        }
        self._supports_cc_extras = bool(
            capabilities.get("supports_slew_rate")
            and capabilities.get("supports_von")
        )
        self.von_spin.setRange(0.0, self.max_voltage)
        self._supports_transient = bool(
            capabilities.get("supports_transient"))
        for spin in (self.level_a_spin, self.level_b_spin):
            spin.setRange(0.0, self.max_current)
        self._range_setpoint()
        self._show_ranges_for_mode()
        self._show_cc_extras()
        self._show_transient()

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

    def _show_ranges_for_mode(self):
        """Offer the ranges the current mode actually has.

        Hidden in CP rather than shown empty: these loads have no power
        range, and a control that is present but does nothing is worse
        than one that is not there.
        """
        mode = self.mode_combo.currentData() or "CC"
        spec = MODE_RANGES.get(mode)
        available = self._available_ranges.get(mode) or [] if spec else []

        showing = bool(spec and len(available) >= 2)
        self.range_label.setVisible(showing)
        self.range_combo.setVisible(showing)
        if not showing:
            return

        unit = spec[2]
        self.range_combo.blockSignals(True)
        self.range_combo.clear()
        low, high = available[0], available[-1]
        for value, name in ((low, "Low"), (high, "High")):
            self.range_combo.addItem(f"{name}  ({value:g} {unit})", value)
        self.range_combo.blockSignals(False)

    async def _ask(self, put_it_up):
        """Run a modal that has an answer, without blocking the loop.

        See client/utils/modals.py -- opening one inline from a
        coroutine lets the nested Qt loop step other asyncio tasks
        while this one is still current.
        """
        return await ask(put_it_up)

    def _show_transient(self):
        """Transient lives inside CC, and only on a load that has it."""
        mode = self.mode_combo.currentData() or "CC"
        self.transient_group.setVisible(
            mode == "CC" and self._supports_transient)
        self._show_transient_timing()

    def _show_transient_timing(self):
        """Show the timing the chosen transient mode actually uses.

        Continuous is thought about as a frequency and a duty cycle,
        pulsed as how long each level lasts, and toggle needs neither
        because it alternates on triggers. The load will accept widths
        in continuous too -- they describe the same thing -- so showing
        both would let two contradictory timings be set with no way to
        tell which won.
        """
        which = TRANSIENT_MODES.get(
            self.transient_mode_combo.currentData() or "CON",
            ("", "none"))[1]
        for widget in (self.frequency_label, self.frequency_spin,
                       self.duty_label, self.duty_spin):
            widget.setVisible(which == "frequency")
        for widget in (self.a_width_label, self.a_width_spin,
                       self.b_width_label, self.b_width_spin):
            widget.setVisible(which == "widths")

    def _on_transient_mode_changed(self, _index: int):
        self._show_transient_timing()

    def _arm_transient(self):
        """Arm the generator: it sinks Level B and waits for a trigger."""
        if not (self.client and self.equipment):
            return
        self._send_arm()

    @qasync.asyncSlot()
    async def _send_arm(self):
        try:
            await self.send("set_transient_enabled", {"enabled": True})
            self.status_message.emit(
                "Transient armed -- the load is at Level B, waiting for a "
                "trigger")
        except Exception as e:
            logger.error(f"Arming transient operation failed: {e}")
            self.status_message.emit(
                f"Arming transient operation failed: {e}")

    def _apply_transient(self):
        """Send the whole configuration on a button, like the setpoint.

        Every intermediate value of a spinbox being typed into is a real
        command on a load, and these ones change what it sinks.
        """
        if not (self.client and self.equipment):
            return
        self._send_transient()

    @qasync.asyncSlot()
    async def _send_transient(self):
        mode = self.transient_mode_combo.currentData() or "CON"
        timing = TRANSIENT_MODES[mode][1]
        try:
            await self.send("set_transient_mode", {"mode": mode})
            await self.send("set_transient_levels", {
                "level_a": float(self.level_a_spin.value()),
                "level_b": float(self.level_b_spin.value()),
            })
            if timing == "frequency":
                await self.send("set_transient_frequency", {
                    "frequency_khz": float(self.frequency_spin.value())})
                await self.send("set_transient_duty", {
                    "duty_percent": float(self.duty_spin.value())})
            elif timing == "widths":
                await self.send("set_transient_widths", {
                    "a_width_ms": float(self.a_width_spin.value()),
                    "b_width_ms": float(self.b_width_spin.value()),
                })
            await self.send("set_transient_slew", {
                "rising": float(self.rise_spin.value()),
                "falling": float(self.fall_spin.value()),
            })
            self.status_message.emit(
                f"Transient set: {TRANSIENT_MODES[mode][0]}, "
                f"{self.level_a_spin.value():g} / "
                f"{self.level_b_spin.value():g} A")
        except Exception as e:
            logger.error(f"Setting transient operation failed: {e}")
            self.status_message.emit(f"Setting transient operation failed: {e}")

    @qasync.asyncSlot()
    async def _fire_trigger(self):
        """One trigger. The driver selects the bus source first."""
        try:
            await self.send("trigger", {})
            self.status_message.emit("Triggered")
        except Exception as e:
            logger.error(f"Triggering failed: {e}")
            self.status_message.emit(f"Triggering failed: {e}")

    def _show_cc_extras(self):
        """Slew rate and Von belong to CC and to nothing else."""
        mode = self.mode_combo.currentData() or "CC"
        self.cc_extras.setVisible(mode == "CC" and self._supports_cc_extras)

    def _apply_cc_options(self):
        """Send both, on a button rather than on every spinbox tick.

        The same reason the setpoint is on Apply: a spinbox that
        commands while it is being typed into sends every intermediate
        value, and on a load those are real.
        """
        if not (self.client and self.equipment):
            return
        self._send_cc_options(float(self.slew_spin.value()),
                              float(self.von_spin.value()))

    @qasync.asyncSlot(float, float)
    async def _send_cc_options(self, slew_rate: float, von: float):
        try:
            await self.send("set_slew_rate", {"slew_rate": slew_rate})
            await self.send("set_von", {"von": von})
            self.status_message.emit(
                f"CC options applied: {slew_rate:g} A/us, Von {von:g} V")
        except Exception as e:
            logger.error(f"Setting the CC options failed: {e}")
            self.status_message.emit(f"Setting the CC options failed: {e}")

    def _on_range_changed(self, _index: int):
        """Select the range on the load, as choosing it on the front
        panel would."""
        if not (self.client and self.equipment):
            return
        mode = self.mode_combo.currentData() or "CC"
        spec = MODE_RANGES.get(mode)
        value = self.range_combo.currentData()
        if spec is None or value is None:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return              # see _on_mode_changed
        self._send_range(spec[1], float(value))

    @qasync.asyncSlot(str, float)
    async def _send_range(self, command: str, value: float):
        """Switch the range, offering to drop the input if it is live.

        The user guide is blunt about this: "Before switching the
        current range, please disable the channel input to avoid
        causing damage to the instrument or the DUT." The driver
        refuses outright while the load is sinking, so this is the
        panel making that refusal actionable rather than a dead end --
        and the operator gets to say whether their test can take the
        interruption, because dropping a load mid-test changes what the
        device under test sees.
        """
        try:
            await self.send(command, {command.split("_")[1] + "_range": value})
            return
        except Exception as e:
            if "input" not in str(e).lower():
                logger.error(f"Setting the load range failed: {e}")
                self.status_message.emit(
                    f"Setting the load range failed: {e}")
                return

        turn_it_off = await self._ask(lambda: QMessageBox.question(
            self,
            "Disable the load input?",
            "Changing range needs the load input off.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes)

        if not turn_it_off:
            # Put the selector back where the load actually is, rather
            # than leaving it showing a range that was never applied.
            self._show_ranges_for_mode()
            self.status_message.emit("Range unchanged -- the input is on")
            return

        try:
            await self.send("set_input", {"enabled": False})
            self.commanded("input", False)
            self.input_button.setChecked(False)
            self.input_button.setText(_INPUT_LABEL[False])
            await self.send(command, {command.split("_")[1] + "_range": value})
            # Left off on purpose. Re-enabling into a freshly changed
            # range is the operator's decision to make deliberately.
            self.status_message.emit(
                "Range changed. The load input is off -- switch it back on "
                "when you are ready.")
        except Exception as e:
            logger.error(f"Setting the load range failed: {e}")
            self.status_message.emit(f"Setting the load range failed: {e}")

    def _on_mode_changed(self, _index: int):
        """Re-range the setpoint box now; apply the mode just after.

        Synchronous on purpose. An asyncSlot only schedules, so the box
        would still be showing the previous mode's range and unit until
        the loop next turned -- and this runs on every selection, where
        that shows.
        """
        self._range_setpoint()
        self._show_ranges_for_mode()
        self._show_cc_extras()
        self._show_transient()

        # Only schedule the send when there is a loop to run it. The
        # combo also changes while the panel is being built and while a
        # reading adopts the load's own mode, and qasync.asyncSlot with
        # no running loop creates a task that never starts -- which
        # surfaces later as "Task was destroyed but it is pending" from
        # somewhere unrelated. There is nothing to send to at those
        # moments anyway.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        self._send_mode()

    @qasync.asyncSlot()
    async def _send_mode(self):
        """Switch the load into the chosen mode there and then.

        The instrument works this way: CC, CV, CR and CP are four keys
        on the front panel, and pressing one enters that mode. It also
        keeps a separate level for each -- the user guide lists current
        and slew rate under CC, voltage and range under CV, and so on --
        which is what makes switching safe to do on its own. Nothing is
        re-applied to the output; the mode simply becomes the one whose
        stored level is already in force.

        This used to send nothing until Apply, because the panel has one
        setpoint box for all four modes and a number meaning amps in CC
        would have meant ohms in CR. Reading the new mode's own level
        back from the instrument removes that: the box shows what this
        mode is actually set to, not what the last one was.
        """
        if not (self.client and self.equipment):
            return                      # still being built, or unbound

        mode = self.mode_combo.currentData() or "CC"
        try:
            await self.send("set_mode", {"mode": mode})
            # Read back rather than assume: if the instrument did not
            # take the mode, this shows what it is really in.
            await self.refresh_settings()
        except Exception as e:
            logger.error(f"Switching the load mode failed: {e}")
            self.status_message.emit(f"Switching the load mode failed: {e}")

    def _apply_setpoint(self):
        mode = self.mode_combo.currentData() or "CC"
        _label, _unit, command, field = MODES[mode]
        self._send_setpoint(mode, command, field, float(self.setpoint_spin.value()))

    @qasync.asyncSlot(str, str, str, float)
    async def _send_setpoint(self, mode: str, command: str, field: str, value: float):
        """The setpoint for the mode the load is already in.

        set_mode goes first even so. Selecting a mode applies it, so
        this is normally a no-op -- but Apply is also the button an
        operator reaches for when the panel and the instrument look out
        of step, and sending both makes it mean what they expect.
        """
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
