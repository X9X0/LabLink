"""The power-supply panel: setpoints, output, and three ways to watch it.

This is the Control tab's original body, moved out of the shell unchanged in
behaviour: voltage and current dials with spinboxes, the output button, the
CV/CC indicators, the digital / analog / graph displays, min/max tracking and
auto-ranging. It is the first panel to follow the InstrumentPanel contract,
so the shell no longer has to know what a supply is.
"""

import logging
from collections import deque
from typing import Any, Dict

from PyQt6.QtCharts import QChart, QLineSeries, QValueAxis
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (QButtonGroup, QDial, QDoubleSpinBox, QGroupBox,
                             QHBoxLayout, QLabel, QPushButton, QRadioButton,
                             QSizePolicy, QVBoxLayout, QWidget)

import qasync
from client.api.client import call_blocking
from client.ui.instruments.base import POLL_READINGS, InstrumentPanel
from client.ui.instruments.widgets import (AnalogGauge, ChartWithReadouts,
                                           FittedReadout, nice_range)
from client.ui.theme import dialog_palette, get_theme_setting

logger = logging.getLogger(__name__)


class PowerSupplyPanel(InstrumentPanel):
    """Drive a DC power supply and watch what it does."""

    POLLS = POLL_READINGS
    #: 10 Hz. A supply's readings are cheap serial queries, and watching a
    #: current limit engage wants better than once a second.
    DEFAULT_INTERVAL_MS = 100
    SETTINGS_TYPE = "power_supply"

    def __init__(self, parent=None):
        # How many places the instrument's readings actually resolve to. A
        # supply that sends hundredths printed as 0.300 A claims a digit it
        # never sent. The server reports this per model; these are the
        # fallbacks for one too old to say.
        self.instrument_max_voltage = 60.0
        self.instrument_max_current = 5.0
        self.voltage_decimals = 2
        self.current_decimals = 3

        # Min/max tracking, reset by the button rather than by a reading.
        self._extremes = {"v_min": None, "v_max": None, "i_min": None, "i_max": None}
        # The top of scale auto-range has settled on. It only ever grows: a
        # scale that shrank when the reading fell made the needle and the
        # graph jump about.
        self._auto_range_top = {"v": None, "i": None}
        #: The last readings as they arrived, before any clamping.
        self._last_readings = (0.0, 0.0)

        self.voltage_data = deque(maxlen=100)
        self.current_data = deque(maxlen=100)
        self.time_data = deque(maxlen=100)

        #: Consecutive readings that disagree with the indicator.
        self._output_state_streak = 0

        super().__init__(parent)

    # ------------------------------------------------------------------ #
    # Compatibility names: the shell used these before the extraction and the
    # GUI tests still speak them.
    # ------------------------------------------------------------------ #

    @property
    def readings_timer(self):
        return self.poll_timer

    @property
    def selected_equipment(self):
        return self.equipment

    @selected_equipment.setter
    def selected_equipment(self, equipment):
        self.equipment = equipment

    def _readings_interval_ms(self) -> int:
        """The selected rate as a timer interval, never zero."""
        if self.refresh_spinbox is not None:
            rate = max(self.refresh_spinbox.value(), 0.1)
            return int(1000 / rate)
        return self.interval_ms()

    def _start_data_acquisition(self):
        self.start()

    def _stop_data_acquisition(self):
        self.stop()

    def _selected_is_connected(self) -> bool:
        return self.is_connected()

    def _show_not_connected(self):
        self.show_not_connected()

    def _show_no_readings_for_this_instrument(self):
        self.show_unsupported()

    def _mark_selection_disconnected(self):
        self.mark_disconnected()

    def _set_controls_enabled(self, enabled: bool):
        self.set_controls_enabled(enabled)

    @staticmethod
    def _nice_range(seen: float, instrument_max: float, floor: float) -> float:
        return nice_range(seen, instrument_max, floor)

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self._create_control_section())
        layout.addWidget(self._create_display_mode_section())

        self.display_stack = QWidget()
        self.display_layout = QVBoxLayout(self.display_stack)

        self.digital_display = self._create_digital_display()
        self.analog_display = self._create_analog_display()
        self.graph_display = self._create_graph_display()
        self.display_layout.addWidget(self.digital_display)
        self.display_layout.addWidget(self.analog_display)
        self.display_layout.addWidget(self.graph_display)
        self.analog_display.hide()
        self.graph_display.hide()

        # One row of tools under the stack: only one display is visible at a
        # time, so these serve digital, analog and graph alike.
        self.display_layout.addWidget(self._create_display_tools())
        layout.addWidget(self.display_stack, 1)

    def _create_control_section(self) -> QGroupBox:
        group = QGroupBox("Controls")
        layout = QVBoxLayout(group)

        controls_layout = QHBoxLayout()

        voltage_group = QGroupBox("Voltage Control")
        voltage_layout = QVBoxLayout(voltage_group)
        self.voltage_dial = QDial()
        self.voltage_dial.setMinimum(0)
        self.voltage_dial.setMaximum(600)  # 60.0V * 10
        self.voltage_dial.setValue(0)
        self.voltage_dial.setNotchesVisible(True)
        self.voltage_dial.setWrapping(False)
        self.voltage_dial.valueChanged.connect(self._on_voltage_dial_changed)
        self.voltage_dial.installEventFilter(self)
        voltage_layout.addWidget(self.voltage_dial)
        voltage_input = QHBoxLayout()
        voltage_input.addWidget(QLabel("Voltage (V):"))
        self.voltage_spinbox = QDoubleSpinBox()
        self.voltage_spinbox.setRange(0.0, 60.0)
        self.voltage_spinbox.setDecimals(2)
        self.voltage_spinbox.setSingleStep(0.1)
        self.voltage_spinbox.valueChanged.connect(self._on_voltage_spinbox_changed)
        voltage_input.addWidget(self.voltage_spinbox)
        voltage_layout.addLayout(voltage_input)
        controls_layout.addWidget(voltage_group)

        current_group = QGroupBox("Current Control")
        current_layout = QVBoxLayout(current_group)
        self.current_dial = QDial()
        self.current_dial.setMinimum(0)
        self.current_dial.setMaximum(160)  # 16.0A * 10
        self.current_dial.setValue(0)
        self.current_dial.setNotchesVisible(True)
        self.current_dial.setWrapping(False)
        self.current_dial.valueChanged.connect(self._on_current_dial_changed)
        self.current_dial.installEventFilter(self)
        current_layout.addWidget(self.current_dial)
        current_input = QHBoxLayout()
        current_input.addWidget(QLabel("Current (A):"))
        self.current_spinbox = QDoubleSpinBox()
        self.current_spinbox.setRange(0.0, 16.0)
        self.current_spinbox.setDecimals(2)
        self.current_spinbox.setSingleStep(0.1)
        self.current_spinbox.valueChanged.connect(self._on_current_spinbox_changed)
        current_input.addWidget(self.current_spinbox)
        current_layout.addLayout(current_input)
        controls_layout.addWidget(current_group)

        layout.addLayout(controls_layout)

        bottom = QHBoxLayout()

        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout(output_group)
        self.output_button = QPushButton("Output: OFF")
        self.output_button.setCheckable(True)
        self.output_button.setStyleSheet(
            "QPushButton:checked { background-color: green; color: white; }"
        )
        self.output_button.clicked.connect(self._on_output_toggled)
        output_layout.addWidget(self.output_button)
        bottom.addWidget(output_group)

        mode_group = QGroupBox("Operating Mode")
        mode_layout = QVBoxLayout(mode_group)
        self.cv_indicator = QLabel("CV: OFF")
        self.cv_indicator.setStyleSheet(self._indicator_style("gray"))
        mode_layout.addWidget(self.cv_indicator)
        self.cc_indicator = QLabel("CC: OFF")
        self.cc_indicator.setStyleSheet(self._indicator_style("gray"))
        mode_layout.addWidget(self.cc_indicator)
        bottom.addWidget(mode_group)

        bottom.addWidget(self._create_rate_control(
            "How often to query voltage and current readings from the equipment"
        ))

        layout.addLayout(bottom)
        return group

    @staticmethod
    def _indicator_style(colour: str) -> str:
        return f"QLabel {{ background-color: {colour}; color: white; padding: 5px; }}"

    def _create_display_mode_section(self) -> QGroupBox:
        group = QGroupBox("Display Mode")
        layout = QHBoxLayout(group)
        self.display_mode_group = QButtonGroup()
        self.digital_radio = QRadioButton("Digital")
        self.digital_radio.setChecked(True)
        self.digital_radio.toggled.connect(lambda: self._on_display_mode_changed("digital"))
        self.analog_radio = QRadioButton("Analog")
        self.analog_radio.toggled.connect(lambda: self._on_display_mode_changed("analog"))
        self.graph_radio = QRadioButton("Graph")
        self.graph_radio.toggled.connect(lambda: self._on_display_mode_changed("graph"))
        for radio in (self.digital_radio, self.analog_radio, self.graph_radio):
            self.display_mode_group.addButton(radio)
            layout.addWidget(radio)
        return group

    def _create_display_tools(self) -> QWidget:
        """Min/max tracking and auto-ranging, shared by all three displays."""
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 4, 0, 0)

        self.minmax_button = QPushButton("Min/Max")
        self.minmax_button.setCheckable(True)
        self.minmax_button.setToolTip(
            "Track the highest and lowest readings seen.\n"
            "Useful for catching a transient that the live number misses."
        )
        self.minmax_button.toggled.connect(self._on_minmax_toggled)
        row.addWidget(self.minmax_button)

        self.minmax_label = QLabel("")
        self.minmax_label.setToolTip("Lowest and highest reading since tracking began")
        row.addWidget(self.minmax_label, 1)

        self.minmax_reset_button = QPushButton("Reset")
        self.minmax_reset_button.setToolTip("Start tracking again from the next reading")
        self.minmax_reset_button.clicked.connect(self._reset_extremes)
        self.minmax_reset_button.setEnabled(False)
        row.addWidget(self.minmax_reset_button)

        self.autorange_button = QPushButton("Auto Range")
        self.autorange_button.setCheckable(True)
        self.autorange_button.setToolTip(
            "Scale the gauges and the graph to the readings actually seen.\n"
            "A 5 A supply sitting at 0.3 A uses a sixteenth of the dial "
            "otherwise, and small changes are invisible."
        )
        self.autorange_button.toggled.connect(self._on_autorange_toggled)
        row.addWidget(self.autorange_button)
        return widget

    def _create_digital_display(self) -> QWidget:
        """One black face with the two readings side by side."""
        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 0, 0, 0)

        panel = QWidget()
        panel.setObjectName("digitalPanel")
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        panel.setStyleSheet(
            "QWidget#digitalPanel { background-color: black; border-radius: 6px; }"
            # Inset from the top and bottom so the rule reads as a separator
            # between the two readings rather than a border cutting the panel
            # into halves.
            "QWidget#digitalDivider { background-color: #3f4a3f; margin: 16px 0; }"
        )
        readings = QHBoxLayout(panel)
        readings.setContentsMargins(12, 12, 12, 12)
        readings.setSpacing(12)

        self.voltage_display = FittedReadout("0.000 V")
        readings.addWidget(self.voltage_display, 1)

        # A plain widget rather than a QFrame VLine: a frame draws itself from
        # the palette, which the dark sheet supplies, and the result is all
        # but invisible on black.
        self.digital_divider = QWidget()
        self.digital_divider.setObjectName("digitalDivider")
        self.digital_divider.setFixedWidth(8)
        self.digital_divider.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        readings.addWidget(self.digital_divider)

        self.current_display = FittedReadout("0.000 A")
        readings.addWidget(self.current_display, 1)

        outer.addWidget(panel)
        return widget

    def _create_analog_display(self) -> QWidget:
        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.voltage_gauge = AnalogGauge("Voltage", 0, 60, "V")
        layout.addWidget(self.voltage_gauge, 1)
        self.current_gauge = AnalogGauge("Current", 0, 16, "A")
        layout.addWidget(self.current_gauge, 1)
        return widget

    def _create_graph_display(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.chart = QChart()
        self.chart.setTitle("Voltage and Current vs Time")
        self.chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        self.chart.setTheme(
            QChart.ChartTheme.ChartThemeDark if get_theme_setting() == "dark"
            else QChart.ChartTheme.ChartThemeLight
        )

        self.voltage_series = QLineSeries()
        self.voltage_series.setName("Voltage (V)")
        self.chart.addSeries(self.voltage_series)
        self.current_series = QLineSeries()
        self.current_series.setName("Current (A)")
        self.chart.addSeries(self.current_series)

        self.axis_x = QValueAxis()
        self.axis_x.setTitleText("Time (s)")
        self.axis_x.setRange(0, 100)
        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
        self.axis_y_voltage = QValueAxis()
        self.axis_y_voltage.setTitleText("Voltage (V)")
        self.axis_y_voltage.setRange(0, 60)
        self.chart.addAxis(self.axis_y_voltage, Qt.AlignmentFlag.AlignLeft)
        self.axis_y_current = QValueAxis()
        self.axis_y_current.setTitleText("Current (A)")
        self.axis_y_current.setRange(0, 16)
        self.chart.addAxis(self.axis_y_current, Qt.AlignmentFlag.AlignRight)

        # The theme leaves the title and the axis labels at their default
        # colour, which is near-black and unreadable on the dark card.
        _c = dialog_palette()
        self.chart.setTitleBrush(QColor(_c["text"]))
        if self.chart.legend():
            self.chart.legend().setLabelColor(QColor(_c["text"]))
        for axis in (self.axis_x, self.axis_y_voltage, self.axis_y_current):
            axis.setLabelsColor(QColor(_c["text"]))
            axis.setTitleBrush(QColor(_c["text"]))

        self.voltage_series.attachAxis(self.axis_x)
        self.voltage_series.attachAxis(self.axis_y_voltage)
        self.current_series.attachAxis(self.axis_x)
        self.current_series.attachAxis(self.axis_y_current)

        self.chart_view = ChartWithReadouts(self.chart)
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        layout.addWidget(self.chart_view)

        buttons = QHBoxLayout()
        buttons.addStretch()
        clear_button = QPushButton("Clear Graph")
        clear_button.setMaximumWidth(120)
        clear_button.clicked.connect(self._clear_graph)
        buttons.addWidget(clear_button)
        layout.addLayout(buttons)
        return widget

    # ------------------------------------------------------------------ #
    # Contract
    # ------------------------------------------------------------------ #

    def configure(self, capabilities: Dict[str, Any]):
        """Range the controls from the supply's capabilities.

        Re-ranged without commanding the instrument. ``setMaximum()`` clamps a
        value that no longer fits and Qt emits ``valueChanged`` for the clamp;
        those signals are wired to the send methods, so lowering a ceiling on
        a device switch used to command the instrument that had just been
        selected -- picking the 5 A 1685B after the 25 A 9205B clamped the
        carried-over setpoint to 5.0 and sent it as set_current. Block the
        widgets across the whole re-range, then show what the instrument
        itself reports.
        """
        max_voltage = capabilities.get("max_voltage", 60.0)
        max_current = capabilities.get("max_current", 5.0)
        # And the floor, which is not zero on every supply. Both B&K
        # supplies on the bench stop at 0.1 V, and the 1685B's current at
        # 0.01 A. Asking for less is not refused by the instrument -- it
        # is ignored, with no reply, so the server waits out a full read
        # timeout and the panel then reports honestly that the supply is
        # not where it was asked to be. Ranging the controls to the floor
        # means the question never gets asked.
        min_voltage = capabilities.get("min_voltage", 0.0) or 0.0
        min_current = capabilities.get("min_current", 0.0) or 0.0
        self.instrument_max_voltage = max_voltage
        self.instrument_max_current = max_current
        # Another instrument, another scale: holding the last one would
        # range a 5 A supply to a 25 A dial.
        self._auto_range_top = {"v": None, "i": None}
        self.voltage_decimals = capabilities.get("voltage_decimals", 2)
        self.current_decimals = capabilities.get("current_decimals", 3)

        ranged = (self.voltage_dial, self.voltage_spinbox,
                  self.current_dial, self.current_spinbox)
        for widget in ranged:
            widget.blockSignals(True)
        try:
            self.voltage_dial.setRange(int(min_voltage * 10),
                                       int(max_voltage * 10))
            self.voltage_spinbox.setRange(min_voltage, max_voltage)
            self.voltage_gauge.max_value = max_voltage
            self.current_dial.setRange(int(min_current * 10),
                                       int(max_current * 10))
            self.current_spinbox.setRange(min_current, max_current)
            self.current_gauge.max_value = max_current
            if not self.autorange_button.isChecked():
                self.axis_y_voltage.setRange(0, max_voltage)
                self.axis_y_current.setRange(0, max_current)
        finally:
            for widget in ranged:
                widget.blockSignals(False)

        logger.info(
            f"Configured controls for {self.describe()}: "
            f"voltage {min_voltage}-{max_voltage}V, "
            f"current {min_current}-{max_current}A"
        )

    async def refresh_settings(self):
        """Show the instrument's own setpoints on the controls.

        Without it the panel keeps whatever the previously selected instrument
        was set to, clamped into the new one's range, which reads like a
        measurement from the new instrument but is not one. The widgets are
        blocked while set, so re-ranging never commands the instrument.
        """
        if not (self.client and self.equipment):
            return
        try:
            setpoints = await self.send("get_setpoints", {"channel": 1}, priority=False)
        except Exception as e:
            logger.warning(
                f"Could not read setpoints from {self.equipment_id}; the panel may "
                f"show a stale setpoint until it is next changed: {e}"
            )
            return
        setpoints = setpoints or {}
        if self.editing_in_progress():
            return          # never overwrite a value being entered
        self._show_reported_setpoints(setpoints.get("voltage"),
                                      setpoints.get("current"))

    def _show_reported_setpoints(self, voltage, current) -> None:
        """Put the instrument's own setpoints on the controls, where they win.

        A control this panel has just commanded keeps the commanded value
        until the instrument is seen to agree with it -- see
        :meth:`~client.ui.instruments.base.InstrumentPanel.may_show`. The two
        are reconciled separately, so setting the voltage does not freeze the
        current field as well.
        """
        if voltage is not None and self.may_show("voltage", voltage):
            self._show_setpoint(self.voltage_dial, self.voltage_spinbox, voltage)
        if current is not None and self.may_show("current", current):
            self._show_setpoint(self.current_dial, self.current_spinbox, current)

    @staticmethod
    def _show_setpoint(dial, spinbox, value: float) -> None:
        """Move the knob and the field together, commanding nothing.

        blockSignals is what stops the display writing back to the
        instrument; without it, showing a reading would send it.
        """
        for widget in (dial, spinbox):
            widget.blockSignals(True)
        try:
            dial.setValue(int(value * 10))
            spinbox.setValue(value)
        finally:
            for widget in (dial, spinbox):
                widget.blockSignals(False)

    def _show_setpoints(self, equipment_id=None):
        """Pre-extraction name; the read-back is asynchronous now."""
        self._schedule_refresh_settings()

    def set_controls_enabled(self, enabled: bool):
        for name in ("voltage_dial", "voltage_spinbox", "current_dial",
                     "current_spinbox", "output_button"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setEnabled(enabled)

    def show_not_connected(self):
        """Say why there are no readings, rather than showing stale ones."""
        self._blank_readouts()
        self.status_message.emit("Not connected. Connect it on the Equipment tab to read it.")

    def show_unsupported(self):
        self._blank_readouts()
        name = getattr(self.equipment, "name", "This instrument")
        self.status_message.emit(
            f"{name} does not report voltage and current. "
            "This panel drives power supplies."
        )

    def _blank_readouts(self):
        self.voltage_display.setText("--")
        self.current_display.setText("--")
        self.voltage_gauge.set_value(0)
        self.current_gauge.set_value(0)

    def clear_instrument(self):
        self._blank_readouts()
        self._clear_graph()

    # ------------------------------------------------------------------ #
    # Readings
    # ------------------------------------------------------------------ #

    async def poll(self):
        """One get_readings() call updates everything; several serial
        commands in flight at once is what overloads a supply's port."""
        readings = await call_blocking(self.client.get_readings, self.equipment.equipment_id)
        self._apply_readings(readings)

    @qasync.asyncSlot()
    async def _update_readings(self):
        """The pre-extraction name for one poll tick."""
        await self._poll()

    def _apply_readings(self, readings: Dict[str, Any]):
        voltage_actual = readings.get("voltage_actual", 0.0)
        current_actual = readings.get("current_actual", 0.0)

        # Show the setpoints on the knobs -- but not while the operator is
        # typing into them.
        #
        # This panel polls ten times a second. Writing the instrument's
        # current setpoint into the field someone is part-way through typing
        # replaces what they have entered: aiming for 12.5 V, they type "1",
        # the next reading overwrites it, and what is finally committed is
        # whatever survived the race. blockSignals stops the send, not the
        # overwrite.
        #
        # A reading older than a command this panel sent is handled a layer
        # down, by reconciling against what was commanded.
        if not self.editing_in_progress():
            self._show_reported_setpoints(readings.get("voltage_set"),
                                          readings.get("current_set"))

        self.voltage_display.setText(f"{voltage_actual:.{self.voltage_decimals}f} V")
        self.voltage_gauge.set_value(voltage_actual)
        self.current_display.setText(f"{current_actual:.{self.current_decimals}f} A")
        self.current_gauge.set_value(current_actual)

        self._last_readings = (voltage_actual, current_actual)
        self._track_extremes(voltage_actual, current_actual)
        self._apply_auto_range()
        self.chart_view.set_readings(
            voltage_actual, current_actual, self.voltage_decimals, self.current_decimals
        )

        self.voltage_data.append(voltage_actual)
        self.current_data.append(current_actual)
        self.time_data.append(len(self.time_data))

        # Unless the operator has just clicked the button and the supply has
        # not caught up: until it agrees, the click is what is true.
        output_enabled = readings.get("output_enabled")
        if self.may_show("output", output_enabled):
            self._show_output_state(output_enabled)

        if readings.get("in_cv_mode"):
            self.cv_indicator.setText("CV: ON")
            self.cv_indicator.setStyleSheet(self._indicator_style("green"))
            self.cc_indicator.setText("CC: OFF")
            self.cc_indicator.setStyleSheet(self._indicator_style("gray"))
        elif readings.get("in_cc_mode"):
            self.cc_indicator.setText("CC: ON")
            self.cc_indicator.setStyleSheet(self._indicator_style("orange"))
            self.cv_indicator.setText("CV: OFF")
            self.cv_indicator.setStyleSheet(self._indicator_style("gray"))

        self._update_graph()

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #

    def _on_voltage_dial_changed(self, value):
        voltage = value / 10.0
        self.voltage_spinbox.blockSignals(True)
        self.voltage_spinbox.setValue(voltage)
        self.voltage_spinbox.blockSignals(False)
        self._command_voltage(voltage)

    def _on_voltage_spinbox_changed(self, value):
        self.voltage_dial.blockSignals(True)
        self.voltage_dial.setValue(int(value * 10))
        self.voltage_dial.blockSignals(False)
        self._command_voltage(value)

    def _on_current_dial_changed(self, value):
        current = value / 10.0
        self.current_spinbox.blockSignals(True)
        self.current_spinbox.setValue(current)
        self.current_spinbox.blockSignals(False)
        self._command_current(current)

    def _on_current_spinbox_changed(self, value):
        self.current_dial.blockSignals(True)
        self.current_dial.setValue(int(value * 10))
        self.current_dial.blockSignals(False)
        self._command_current(value)

    # Intent is recorded here, synchronously, rather than inside the send
    # coroutines below. An @asyncSlot only schedules: by the time its body
    # runs, the poll may already have applied a reading taken before the
    # operator moved the control, which is the stale value we are guarding
    # against in the first place.

    def _command_voltage(self, voltage: float) -> None:
        self.commanded("voltage", voltage)
        self.write_latest("voltage", voltage, self._send_voltage_command)

    def _command_current(self, current: float) -> None:
        self.commanded("current", current)
        self.write_latest("current", current, self._send_current_command)

    #: Readings that must agree before the output indicator changes. One
    #: contrary reading is not enough to say a live supply has gone off.
    OUTPUT_STATE_CONFIRMATIONS = 2

    def _show_output_state(self, reported) -> None:
        """Move the indicator only once consecutive readings agree.

        A single reading used to flip it. Scrolling a dial interleaves a
        setpoint write per notch with this panel's 10 Hz poll, and the
        supply's answer to the output query can come back out of step; the
        driver reads anything it does not recognise as "off". The operator
        then sees Output flash OFF on a supply that is still on, which is
        the more dangerous direction to be wrong in -- it invites touching
        something live.

        A reading with no output state at all says nothing, so nothing
        changes; it does not mean off.
        """
        if reported is None:
            return
        reported = bool(reported)
        if reported == self.output_button.isChecked():
            self._output_state_streak = 0
            return
        self._output_state_streak += 1
        if self._output_state_streak < self.OUTPUT_STATE_CONFIRMATIONS:
            return
        self._output_state_streak = 0
        self.output_button.blockSignals(True)
        self.output_button.setChecked(reported)
        self.output_button.setText("Output: ON" if reported else "Output: OFF")
        self.output_button.blockSignals(False)

    def _on_output_toggled(self, checked):
        self.output_button.setText("Output: ON" if checked else "Output: OFF")
        self.commanded("output", bool(checked))
        self._output_state_streak = 0
        self._send_output_command(bool(checked))

    @qasync.asyncSlot(float)
    async def _send_voltage_command(self, voltage: float):
        if not (self.equipment and self.client):
            return
        try:
            await call_blocking(
                self.client.send_command, self.equipment.equipment_id,
                "set_voltage", {"voltage": voltage, "channel": 1},
            )
        except Exception as e:
            logger.error(f"Error sending voltage command: {e}")
            self._say_a_setpoint_was_refused("voltage", voltage, e)

    @qasync.asyncSlot(float)
    async def _send_current_command(self, current: float):
        if not (self.equipment and self.client):
            return
        try:
            await call_blocking(
                self.client.send_command, self.equipment.equipment_id,
                "set_current", {"current": current, "channel": 1},
            )
        except Exception as e:
            logger.error(f"Error sending current command: {e}")
            self._say_a_setpoint_was_refused("current", current, e)

    def _say_a_setpoint_was_refused(self, what: str, value: float, error) -> None:
        """Tell the operator, not just the log.

        A refused setpoint used to be a line in a file nobody was reading,
        and the only sign on screen was the field quietly correcting itself
        a few seconds later. On a live bench the operator needs to know the
        supply did not take what they asked for.
        """
        self.status_message.emit(
            f"The supply did not accept {what} {value:g}: {error}"
        )

    @qasync.asyncSlot(bool)
    async def _send_output_command(self, enabled: bool):
        if not (self.equipment and self.client):
            return
        try:
            await call_blocking(
                self.client.send_command, self.equipment.equipment_id,
                "set_output", {"enabled": enabled, "channel": 1},
            )
            logger.info(f"Set output to {'ON' if enabled else 'OFF'}")
        except Exception as e:
            logger.error(f"Error sending output command: {e}")

    # ------------------------------------------------------------------ #
    # Display modes, min/max, auto-range, graph
    # ------------------------------------------------------------------ #

    def _on_display_mode_changed(self, mode):
        self.digital_display.setVisible(mode == "digital")
        self.analog_display.setVisible(mode == "analog")
        self.graph_display.setVisible(mode == "graph")

    def _reset_extremes(self):
        """Forget what has been seen and start again."""
        self._extremes = {"v_min": None, "v_max": None, "i_min": None, "i_max": None}
        # The held scale is a record of what has been seen too; otherwise
        # Reset would leave the dial stuck wide open.
        self._auto_range_top = {"v": None, "i": None}
        self._update_minmax_label()

    def _on_minmax_toggled(self, enabled: bool):
        self.minmax_reset_button.setEnabled(enabled)
        if enabled:
            self._reset_extremes()
        else:
            self.minmax_label.setText("")

    def _on_autorange_toggled(self, enabled: bool):
        if not enabled:
            # Back to what the instrument can actually do.
            self.voltage_gauge.max_value = self.instrument_max_voltage
            self.current_gauge.max_value = self.instrument_max_current
            self.axis_y_voltage.setRange(0, self.instrument_max_voltage)
            self.axis_y_current.setRange(0, self.instrument_max_current)
            self.voltage_gauge.update()
            self.current_gauge.update()
        else:
            self._auto_range_top = {"v": None, "i": None}
            self._apply_auto_range()

    def _track_extremes(self, voltage: float, current: float):
        if not self.minmax_button.isChecked():
            return
        for key, value in (("v", voltage), ("i", current)):
            low, high = self._extremes[f"{key}_min"], self._extremes[f"{key}_max"]
            self._extremes[f"{key}_min"] = value if low is None else min(low, value)
            self._extremes[f"{key}_max"] = value if high is None else max(high, value)
        self._update_minmax_label()

    def _update_minmax_label(self):
        """Show the extremes to the resolution the instrument reports."""
        v_min = self._extremes["v_min"]
        if v_min is None:
            self.minmax_label.setText("waiting for a reading...")
            return
        vd, cd = self.voltage_decimals, self.current_decimals
        self.minmax_label.setText(
            f"V  {v_min:.{vd}f} / {self._extremes['v_max']:.{vd}f}       "
            f"A  {self._extremes['i_min']:.{cd}f} / {self._extremes['i_max']:.{cd}f}"
        )

    def _apply_auto_range(self):
        """Scale the gauges and graph to the readings actually seen.

        Uses the readings, not the gauges: set_value clamps to the current top
        of scale, so reading them back off the needle meant a 2.4 A reading on
        a 0.15 A scale came back as 0.15 and the range crept up one step per
        reading instead of jumping to fit.
        """
        if not self.autorange_button.isChecked():
            return
        seen_v = self._extremes["v_max"]
        seen_i = self._extremes["i_max"]
        if seen_v is None:
            seen_v = self._last_readings[0]
        if seen_i is None:
            seen_i = self._last_readings[1]

        v_range = self._latched("v", nice_range(seen_v, self.instrument_max_voltage, floor=1.0))
        i_range = self._latched("i", nice_range(seen_i, self.instrument_max_current, floor=0.1))
        self.voltage_gauge.max_value = v_range
        self.current_gauge.max_value = i_range
        self.axis_y_voltage.setRange(0, v_range)
        self.axis_y_current.setRange(0, i_range)
        self.voltage_gauge.update()
        self.current_gauge.update()

    def _latched(self, key: str, candidate: float) -> float:
        """The largest scale asked for so far, never a smaller one."""
        previous = self._auto_range_top.get(key)
        top = candidate if previous is None else max(previous, candidate)
        self._auto_range_top[key] = top
        return top

    def _update_graph(self):
        self.voltage_series.clear()
        self.current_series.clear()
        for i, v in enumerate(self.voltage_data):
            self.voltage_series.append(i, v)
        for i, c in enumerate(self.current_data):
            self.current_series.append(i, c)
        if self.time_data:
            self.axis_x.setRange(max(0, len(self.time_data) - 100), len(self.time_data))

    def _clear_graph(self):
        self.voltage_data.clear()
        self.current_data.clear()
        self.time_data.clear()
        self.voltage_series.clear()
        self.current_series.clear()
        self.axis_x.setRange(0, 100)

    #: What one notch of the wheel over a dial changes the setpoint by, in
    #: volts or amps. Plain scrolling is the adjustment wanted most often;
    #: Ctrl is the coarse one; Shift is finer than the dial itself can go.
    WHEEL_STEP = 0.10
    WHEEL_STEP_COARSE = 1.00        # Ctrl
    WHEEL_STEP_FINE = 0.01          # Shift

    def eventFilter(self, watched, event):
        """Take the wheel over a dial, because QDial's own handling is wrong
        for this panel.

        QAbstractSlider moves by singleStep times the platform's
        scroll-lines setting -- three here -- so one notch moved three dial
        units, and a dial unit is 0.1 V: 0.30 a notch. It also treats Ctrl
        and Shift alike, both using pageStep, which is where the 1.0 came
        from and why Shift could not be finer.

        The panel had a wheelEvent meaning to do this, but it never ran: the
        dial accepts the event, so it never reaches the parent.

        The step is applied to the spin box, not the dial. The spin box
        carries two decimals, so Shift reaches 0.01; the dial's integer
        units stop at 0.1, and it follows along rounded.
        """
        if event.type() == QEvent.Type.Wheel and watched in (
                self.voltage_dial, self.current_dial):
            box = (self.voltage_spinbox if watched is self.voltage_dial
                   else self.current_spinbox)
            modifiers = event.modifiers()
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                step = self.WHEEL_STEP_COARSE
            elif modifiers & Qt.KeyboardModifier.ShiftModifier:
                step = self.WHEEL_STEP_FINE
            else:
                step = self.WHEEL_STEP
            if event.angleDelta().y() < 0:
                step = -step
            box.setValue(round(box.value() + step, box.decimals()))
            return True
        return super().eventFilter(watched, event)
