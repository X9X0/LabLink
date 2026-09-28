"""The power-supply panel: setpoints, output, and three ways to watch it.

This is the Control tab's original body, moved out of the shell unchanged in
behaviour: voltage and current dials with spinboxes, the output button, the
CV/CC indicators, the digital / analog / graph displays, min/max tracking and
auto-ranging. It is the first panel to follow the InstrumentPanel contract,
so the shell no longer has to know what a supply is.
"""

import asyncio
import logging
from collections import deque
from typing import Any, Dict

from PyQt6.QtCharts import QChart, QLineSeries, QValueAxis
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QDial, QDoubleSpinBox,
                             QGroupBox, QHBoxLayout, QLabel, QPushButton,
                             QRadioButton, QSizePolicy, QVBoxLayout, QWidget)

import qasync
from client.api.client import call_blocking
from client.ui.instruments.base import POLL_READINGS, InstrumentPanel
from client.ui.instruments.channel_strip import ChannelStrip
from client.ui.instruments.measurement_views import (Channel,
                                                     MeasurementViews)
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

        # Min/max tracking, auto-ranging and the readings history all
        # live in MeasurementViews now, along with the displays they
        # serve; see client/ui/instruments/measurement_views.py.

        #: The last readings as they arrived, before any clamping.
        self._last_readings = (0.0, 0.0)



        #: Consecutive readings that disagree with the indicator.
        self._output_state_streak = 0

        #: Multi-channel supplies get a column per channel instead of
        #: the single-channel body. One panel class still serves both:
        #: panels are chosen by equipment type, so the Siglent and the
        #: B&K arrive here together, and a supply with one channel must
        #: look exactly as it always has.
        self._strips = {}
        self._channel_count = 1
        self._unreadable_channels = ()
        self._hidden_channels = set()

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


    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #

    # The readouts, gauges, chart and the Min/Max and Auto Range buttons
    # moved into MeasurementViews when the three displays became shared
    # with the electronic load. These keep the panel's own names pointing
    # at them: the panel is what the rest of the client and the tests
    # hold, and none of them should have to know where a gauge lives.
    @property
    def voltage_display(self):
        return self.views.displays["voltage"]

    @property
    def current_display(self):
        return self.views.displays["current"]

    @property
    def power_display(self):
        return self.views.displays["power"]

    @property
    def voltage_gauge(self):
        return self.views.gauges["voltage"]

    @property
    def current_gauge(self):
        return self.views.gauges["current"]

    @property
    def power_gauge(self):
        return self.views.gauges["power"]

    @property
    def digital_display(self):
        return self.views.digital_view

    @property
    def analog_display(self):
        return self.views.analog_view

    @property
    def graph_display(self):
        return self.views.graph_view

    @property
    def digital_divider(self):
        """The rule between volts and amps on the digital face."""
        return self.views.dividers[0]

    @property
    def minmax_button(self):
        return self.views.minmax_button

    @property
    def minmax_label(self):
        return self.views.minmax_label

    @property
    def minmax_reset_button(self):
        return self.views.minmax_reset_button

    @property
    def autorange_button(self):
        return self.views.autorange_button

    @property
    def digital_radio(self):
        return self.views.digital_radio

    @property
    def analog_radio(self):
        return self.views.analog_radio

    @property
    def graph_radio(self):
        return self.views.graph_radio

    @property
    def chart_view(self):
        return self.views.chart_view

    @property
    def voltage_series(self):
        return self.views.series["voltage"]

    @property
    def current_series(self):
        return self.views.series["current"]

    @property
    def axis_y_voltage(self):
        return self.views.axes["voltage"]

    @property
    def axis_y_current(self):
        return self.views.axes["current"]

    @property
    def axis_x(self):
        return self.views.axis_x

    # Decimals stay the panel's, because the panel is what learns them
    # from the instrument's capabilities, but they have to reach the
    # readouts that now live in the views. Written as properties so
    # assigning one still takes effect -- and so it works before
    # _build_ui has made the views, which is when __init__ sets them.
    @property
    def voltage_decimals(self):
        return self._voltage_decimals

    @voltage_decimals.setter
    def voltage_decimals(self, places):
        self._voltage_decimals = int(places)
        # __dict__, not getattr: __init__ sets the decimals before
        # super().__init__() has run, and asking a QWidget subclass for
        # a missing attribute before that raises "super-class __init__()
        # was never called" rather than returning the default.
        views = self.__dict__.get("views")
        if views is not None:
            views.set_decimals("voltage", int(places))

    @property
    def current_decimals(self):
        return self._current_decimals

    @current_decimals.setter
    def current_decimals(self, places):
        self._current_decimals = int(places)
        views = self.__dict__.get("views")
        if views is not None:
            views.set_decimals("current", int(places))

    # Full scale, like the decimals above: the panel learns it from the
    # instrument's capabilities, and the gauges and axes that need it
    # are in the views.
    @property
    def instrument_max_voltage(self):
        return self._instrument_max_voltage

    @instrument_max_voltage.setter
    def instrument_max_voltage(self, maximum):
        self._instrument_max_voltage = float(maximum)
        views = self.__dict__.get("views")
        if views is not None:
            views.set_maximum("voltage", float(maximum))
            views.set_maximum("power",
                              float(maximum) * self._instrument_max_current)

    @property
    def instrument_max_current(self):
        return self._instrument_max_current

    @instrument_max_current.setter
    def instrument_max_current(self, maximum):
        self._instrument_max_current = float(maximum)
        views = self.__dict__.get("views")
        if views is not None:
            views.set_maximum("current", float(maximum))
            views.set_maximum("power",
                              self._instrument_max_voltage * float(maximum))

    # Min/Max and auto-range moved into the views with the displays they
    # serve. These are the panel's old names for them, kept because they
    # read as things a panel does and because the behaviour they stand
    # for was found on the bench and is worth keeping addressable.
    def _track_extremes(self, voltage: float, current: float):
        self.views.set_readings({"voltage": voltage, "current": current,
                                 "power": voltage * current})

    def _reset_extremes(self):
        self.views.reset_extremes()

    def _apply_auto_range(self):
        # From the panel's own record of the last reading, which is what
        # a caller setting _last_readings and then re-ranging means.
        voltage, current = self._last_readings
        self.views.apply_auto_range({"voltage": voltage, "current": current,
                                     "power": voltage * current})

    def _on_display_mode_changed(self, mode: str):
        """Switch which of the three displays is showing."""
        {"digital": self.views.digital_radio,
         "analog": self.views.analog_radio,
         "graph": self.views.graph_radio}[mode].setChecked(True)

    def _mark_extremes_on_gauges(self):
        self.views._mark_gauges()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self._create_control_section())

        # Digital, analog and graph, with Min/Max and auto-range, all
        # from the widget the electronic load uses. Watts is the third
        # channel: the supply does not measure power, so it is the
        # product of the two it does -- see _apply_readings.
        self.views = MeasurementViews((
            Channel("voltage", "Voltage", "V", self.voltage_decimals,
                    self.instrument_max_voltage, 1.0, "#4a9eff"),
            Channel("current", "Current", "A", self.current_decimals,
                    self.instrument_max_current, 0.1, "#ff9d4a"),
            Channel("power", "Power", "W", 2,
                    self.instrument_max_voltage * self.instrument_max_current,
                    1.0, "#7ed957"),
        ))
        layout.addWidget(self.views, 1)

        # The multi-channel body, empty until an instrument says it has
        # more than one channel. Built here rather than on demand so the
        # panel keeps one layout for its whole life: swapping the
        # top-level layout while a poll is in flight is how a panel ends
        # up drawing into widgets that have gone.
        self.channel_bar = QWidget()
        bar = QHBoxLayout(self.channel_bar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.addWidget(QLabel("Channels:"))
        self._channel_boxes_layout = bar
        self._channel_boxes = {}
        bar.addStretch()
        self.channel_bar.setVisible(False)
        layout.addWidget(self.channel_bar)

        self.channel_area = QWidget()
        self._channel_layout = QHBoxLayout(self.channel_area)
        self._channel_layout.setContentsMargins(0, 0, 0, 0)
        self.channel_area.setVisible(False)
        layout.addWidget(self.channel_area, 1)

    # ------------------------------------------------------------------ #
    # Multi-channel supplies
    # ------------------------------------------------------------------ #

    def _configure_channels(self, capabilities: Dict[str, Any]):
        """Grow a column per channel, or leave the single-channel body.

        One channel is the overwhelming case and its panel is mature,
        so it is left exactly as it was rather than reimplemented as a
        column of itself.
        """
        count = int(capabilities.get("channels", 1) or 1)
        programmable = [int(c) for c in
                        (capabilities.get("programmable_channels")
                         or range(1, count + 1))]
        unreadable = {}
        if capabilities.get("has_fixed_rail") and count >= 3:
            unreadable[3] = (
                "Fixed 2.5 / 3.3 / 5 V rail, selected by the switch on the "
                "front panel. The supply does not report its voltage or its "
                "draw over the remote interface, so there is nothing to show "
                "here but the switch.")

        if count == self._channel_count and self._strips:
            self._range_strips(capabilities)
            return
        self._channel_count = count
        self._unreadable_channels = tuple(sorted(unreadable))

        for strip in self._strips.values():
            strip.setParent(None)
            strip.deleteLater()
        self._strips = {}
        self._clear_channel_boxes()

        single = count <= 1
        self.channel_bar.setVisible(not single)
        self.channel_area.setVisible(not single)
        # The single-channel body and the columns are alternatives, not
        # layers: leaving both up would draw the same instrument twice.
        self._single_channel_widgets_visible(single)
        if single:
            return

        self._hidden_channels = set(self._remembered_hidden())
        for number in range(1, count + 1):
            strip = ChannelStrip(number,
                                 programmable=number in programmable,
                                 note=unreadable.get(number, ""))
            strip.setpoint_committed.connect(self._strip_setpoint_requested)
            strip.output_toggled.connect(self._strip_output_requested)
            self._channel_layout.addWidget(strip, 1)
            self._strips[number] = strip
            self._add_channel_box(number)
        self._range_strips(capabilities)
        self._apply_channel_visibility()

    def _single_channel_widgets_visible(self, visible: bool):
        for widget in (getattr(self, "_controls_group", None), self.views):
            if widget is not None:
                widget.setVisible(visible)

    def _range_strips(self, capabilities: Dict[str, Any]):
        for strip in self._strips.values():
            strip.set_ranges(
                capabilities.get("max_voltage", self.instrument_max_voltage),
                capabilities.get("max_current", self.instrument_max_current),
                capabilities.get("voltage_decimals", 3),
                capabilities.get("current_decimals", 3),
            )

    def _clear_channel_boxes(self):
        self._channel_boxes = {}
        layout = self._channel_boxes_layout
        for index in reversed(range(layout.count())):
            widget = layout.itemAt(index).widget()
            if isinstance(widget, QCheckBox):
                layout.takeAt(index)
                widget.setParent(None)
                widget.deleteLater()

    def _add_channel_box(self, number: int):
        box = QCheckBox("CH%d" % number)
        box.setChecked(number not in self._hidden_channels)
        box.setToolTip(
            "Show CH%d. Hiding a channel gives its width to the others, so "
            "the readings left on screen get bigger." % number)
        box.toggled.connect(
            lambda shown, n=number: self._on_channel_toggled(n, shown))
        # Before the stretch, so the boxes stay left-aligned.
        self._channel_boxes_layout.insertWidget(
            self._channel_boxes_layout.count() - 1, box)
        self._channel_boxes[number] = box

    def _on_channel_toggled(self, number: int, shown: bool):
        if shown:
            self._hidden_channels.discard(number)
        else:
            self._hidden_channels.add(number)
        self._apply_channel_visibility()
        self._remember_hidden()

    def _apply_channel_visibility(self):
        """Hidden columns give their width back.

        Hiding a widget is not enough on its own: its stretch has to go
        too, or the layout keeps the space and the remaining readings
        stay the size they were beside a gap.
        """
        for number, strip in self._strips.items():
            shown = number not in self._hidden_channels
            strip.setVisible(shown)
            self._channel_layout.setStretch(
                self._channel_layout.indexOf(strip), 1 if shown else 0)

    def _remembered_hidden(self):
        """What was hidden on this instrument last time.

        Nothing, for a panel with no instrument bound. An empty id is
        not a key: every unbound panel would share it, so hiding a
        channel on one supply before it had been identified would hide
        that channel on the next supply to arrive.
        """
        if not self.equipment_id:
            return []
        try:
            from client.utils.settings import SettingsManager

            return SettingsManager().get_hidden_channels(self.equipment_id)
        except Exception as e:
            logger.debug("Could not read hidden channels: %s" % e)
            return []

    def _remember_hidden(self):
        if not self.equipment_id:
            return
        try:
            from client.utils.settings import SettingsManager

            SettingsManager().set_hidden_channels(
                self.equipment_id, self._hidden_channels)
        except Exception as e:
            logger.debug("Could not remember hidden channels: %s" % e)

    def _ready_to_send(self) -> bool:
        """Whether there is anything to send to, and a loop to send on.

        An asyncSlot invoked with no running event loop does not raise
        -- it aborts the interpreter. A strip's signals can arrive
        outside the loop: Qt fires editingFinished when a box loses
        focus, and that happens during teardown and in tests as
        readily as under a running client.
        """
        if not (self.client and self.equipment):
            return False
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return False
        return True

    def _strip_setpoint_requested(self, channel: int, what: str, value: float):
        if self._ready_to_send():
            self._on_strip_setpoint(channel, what, value)

    def _strip_output_requested(self, channel: int, wanted: bool):
        if self._ready_to_send():
            self._on_strip_output(channel, wanted)
        else:
            strip = self._strips.get(channel)
            if strip is not None:
                strip.show_output(not wanted)

    @qasync.asyncSlot(int, str, float)
    async def _on_strip_setpoint(self, channel: int, what: str, value: float):
        action = "set_voltage" if what == "voltage" else "set_current"
        try:
            await call_blocking(self.client.send_command,
                                self.equipment.equipment_id, action,
                                {what: value, "channel": channel})
        except Exception as e:
            logger.error("Setting CH%d %s failed: %s" % (channel, what, e))
            self.status_message.emit(
                "Setting CH%d %s failed: %s" % (channel, what, e))

    @qasync.asyncSlot(int, bool)
    async def _on_strip_output(self, channel: int, wanted: bool):
        try:
            await call_blocking(self.client.send_command,
                                self.equipment.equipment_id, "set_output",
                                {"enabled": wanted, "channel": channel})
        except Exception as e:
            logger.error("Switching CH%d failed: %s" % (channel, e))
            self.status_message.emit("Switching CH%d failed: %s" % (channel, e))
            # Back where the supply still is, rather than showing an
            # output that was never switched.
            strip = self._strips.get(channel)
            if strip is not None:
                strip.show_output(not wanted)

    def _apply_all_readings(self, data: Dict[str, Any]):
        """One reply, every channel."""
        for entry in (data or {}).get("channels") or []:
            strip = self._strips.get(entry.get("channel"))
            if strip is None:
                continue
            strip.show_readings(entry.get("voltage_actual"),
                                entry.get("current_actual"),
                                entry.get("power_actual"))
            # Not while somebody is typing into them; see
            # _apply_readings. Asked per column, because focus in one
            # channel says nothing about the other two.
            if not strip.is_being_edited():
                strip.show_setpoints(entry.get("voltage_set"),
                                     entry.get("current_set"))
            strip.show_output(bool(entry.get("output_enabled")))
            strip.show_mode(bool(entry.get("in_cv_mode")),
                            bool(entry.get("in_cc_mode")))

    def _create_control_section(self) -> QGroupBox:
        group = QGroupBox("Controls")
        # Held so the multi-channel body can hide it; the two are
        # alternatives, not layers.
        self._controls_group = group
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
        self.voltage_decimals = capabilities.get("voltage_decimals", 2)
        self.current_decimals = capabilities.get("current_decimals", 3)
        # Another instrument, another scale: holding the last one would
        # range a 5 A supply to a 25 A dial. reset_extremes drops the
        # held auto-range tops along with the tracked extremes.
        self.views.reset_extremes()
        self.views.set_decimals("voltage", self.voltage_decimals)
        self.views.set_decimals("current", self.current_decimals)
        self.views.set_maximum("voltage", max_voltage)
        self.views.set_maximum("current", max_current)
        self.views.set_maximum("power", max_voltage * max_current)

        ranged = (self.voltage_dial, self.voltage_spinbox,
                  self.current_dial, self.current_spinbox)
        for widget in ranged:
            widget.blockSignals(True)
        try:
            self.voltage_dial.setRange(int(min_voltage * 10),
                                       int(max_voltage * 10))
            self.voltage_spinbox.setRange(min_voltage, max_voltage)
            self.current_dial.setRange(int(min_current * 10),
                                       int(max_current * 10))
            self.current_spinbox.setRange(min_current, max_current)
        finally:
            for widget in ranged:
                widget.blockSignals(False)

        logger.info(
            f"Configured controls for {self.describe()}: "
            f"voltage {min_voltage}-{max_voltage}V, "
            f"current {min_current}-{max_current}A"
        )

        # The channel count only arrives with the capabilities, so
        # the columns cannot be built in _build_ui.
        self._configure_channels(capabilities)

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
        self.views.blank()

    def clear_instrument(self):
        self._blank_readouts()

    # ------------------------------------------------------------------ #
    # Readings
    # ------------------------------------------------------------------ #

    async def poll(self):
        """One call updates everything; several serial commands in
        flight at once is what overloads a supply's port.

        A multi-channel supply reads every channel in one request.
        Measured against the SPD3303X-E, a per-channel get_readings
        is ~83 ms and almost all of that is the hop rather than the
        instrument, so three of them come to ~250 ms against a
        100 ms poll -- the panel would fall behind its own clock.
        """
        if self._strips:
            data = await call_blocking(
                self.client.send_command, self.equipment.equipment_id,
                "get_all_readings", {})
            self._apply_all_readings((data or {}).get("data") or data)
            return
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

        # Watts is computed, not measured: none of these supplies report
        # power, and the operator was doing volts times amps in their
        # head. Derived from the two readings as they arrived, so it
        # agrees with the numbers beside it rather than with a rounded
        # version of them.
        self._last_readings = (voltage_actual, current_actual)
        self.views.set_readings({
            "voltage": voltage_actual,
            "current": current_actual,
            "power": voltage_actual * current_actual,
        })

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
