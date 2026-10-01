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
from client.ui.instruments.timer_dialog import TimerDialog
from client.ui.instruments.measurement_views import (Channel,
                                                     MeasurementViews)
from client.ui.instruments.widgets import (AnalogGauge, ChartWithReadouts,
                                           FittedReadout, nice_range)
from client.ui.theme import dialog_palette, get_theme_setting

logger = logging.getLogger(__name__)


def _spell_short(seconds: float) -> str:
    """Seconds for a button face, so it does not resize as it counts."""
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return "%ds" % round(seconds)
    minutes, rest = divmod(int(round(seconds)), 60)
    if minutes < 60:
        return "%d:%02d" % (minutes, rest)
    hours, minutes = divmod(minutes, 60)
    return "%d:%02d:%02d" % (hours, minutes, rest)


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
        #: What the supply says its output coupling is, not what was
        #: last asked for.
        self._coupling = None
        #: Where the rate control lives when this is a single-channel
        #: panel, so the columns can borrow it and give it back.
        self._rate_home = None
        self._timer_buttons = {}
        self._timer_edit_buttons = {}
        #: Open timer editors, by channel. Held so a second click
        #: raises the one already up rather than stacking another.
        self._timer_dialogs = {}
        #: Per channel: how long the five groups add up to, as last
        #: read or sent, and how much of it has been counted off. The
        #: instrument reports neither -- see _advance_timers.
        self._timer_total = {}
        self._timer_elapsed = {}
        self._timer_last_tick = {}

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

        # Controls band: a column of controls per channel, plus room
        # for whatever belongs to the supply rather than to a channel.
        self.channel_area = QWidget()
        self._channel_layout = QHBoxLayout(self.channel_area)
        self._channel_layout.setContentsMargins(0, 0, 0, 0)
        self.channel_area.setVisible(False)
        layout.addWidget(self.channel_area)

        # One selector and one rate for the instrument. Three of either
        # would be three things to keep in step, and the rate is a
        # property of the poll, which is per instrument.
        self.shared_bar = QWidget()
        shared = QHBoxLayout(self.shared_bar)
        shared.setContentsMargins(0, 0, 0, 0)
        self.display_mode_group = QGroupBox("Display Mode")
        modes = QHBoxLayout(self.display_mode_group)
        self.shared_mode_buttons = QButtonGroup(self)
        for index, name in enumerate(("Digital", "Analog", "Graph")):
            radio = QRadioButton(name)
            radio.setChecked(index == 0)
            self.shared_mode_buttons.addButton(radio, index)
            modes.addWidget(radio)
        self.shared_mode_buttons.idToggled.connect(self._on_shared_mode)
        shared.addWidget(self.display_mode_group)

        # Independent / Series / Parallel, and which one the supply is
        # actually in. These are not display options: in series and
        # parallel the two channels are linked internally into one
        # controlled by CH1, and the load is wired differently for
        # each, so the indicator has to show the instrument's own
        # answer rather than the last button pressed.
        self.coupling_group = QGroupBox("Output Mode")
        coupling = QHBoxLayout(self.coupling_group)
        self.coupling_buttons = {}
        for name, label, tip in (
            ("independent", "Independent",
             "CH1 and CH2 controlled separately."),
            ("series", "Series",
             "CH1 and CH2 linked internally into one channel controlled\n"
             "by CH1, rated 0-60 V / 0-3.2 A. Wire the load across CH2's\n"
             "positive and CH1's negative terminal."),
            ("parallel", "Parallel",
             "CH1 and CH2 linked internally into one channel controlled\n"
             "by CH1, rated 0-32 V / 0-6.4 A. Wire the load to CH1's\n"
             "terminals. CH2 only works in CC mode."),
        ):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setToolTip(
                tip + "\n\nBoth outputs are switched off before the mode "
                      "changes, because it changes what your circuit is "
                      "connected to.")
            button.clicked.connect(
                lambda _checked, n=name: self._coupling_requested(n))
            coupling.addWidget(button)
            self.coupling_buttons[name] = button
        self.coupling_indicator = QLabel("Mode: --")
        self.coupling_indicator.setToolTip(
            "What the supply reports, not what was last asked for.")
        coupling.addWidget(self.coupling_indicator)
        shared.addWidget(self.coupling_group)

        shared.addStretch()

        # Min/Max, Reset and Auto Range belong to the readout as a
        # whole rather than to one column, so there is one of each and
        # it drives every column.
        self.shared_minmax_button = QPushButton("Min/Max")
        self.shared_minmax_button.setCheckable(True)
        self.shared_minmax_button.setToolTip(
            "Track the lowest and highest reading on every channel.")
        self.shared_minmax_button.toggled.connect(self._on_shared_minmax)
        shared.addWidget(self.shared_minmax_button)

        self.shared_minmax_reset = QPushButton("Reset")
        self.shared_minmax_reset.setToolTip("Forget the extremes so far.")
        self.shared_minmax_reset.setEnabled(False)
        self.shared_minmax_reset.clicked.connect(self._on_shared_minmax_reset)
        shared.addWidget(self.shared_minmax_reset)

        self.shared_autorange_button = QPushButton("Auto Range")
        self.shared_autorange_button.setCheckable(True)
        self.shared_autorange_button.setToolTip(
            "Fit each column's scale to what it is reading.")
        self.shared_autorange_button.toggled.connect(
            self._on_shared_autorange)
        shared.addWidget(self.shared_autorange_button)

        self.shared_bar.setVisible(False)
        layout.addWidget(self.shared_bar)

        # Readings band: a column per readable channel.
        self.readout_area = QWidget()
        self._readout_layout = QHBoxLayout(self.readout_area)
        self._readout_layout.setContentsMargins(0, 0, 0, 0)
        self.readout_area.setVisible(False)
        layout.addWidget(self.readout_area, 1)
        self._channel_views = {}

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
        self._timer_buttons = {}
        self._timer_edit_buttons = {}
        for views in self._channel_views.values():
            views.setParent(None)
            views.deleteLater()
        self._channel_views = {}
        self._clear_channel_boxes()

        single = count <= 1
        self.channel_bar.setVisible(not single)
        self.channel_area.setVisible(not single)
        # The single-channel body and the columns are alternatives, not
        # layers: leaving both up would draw the same instrument twice.
        self._single_channel_widgets_visible(single)
        if single:
            return

        self.shared_bar.setVisible(True)
        self.readout_area.setVisible(True)
        self._adopt_rate_control()

        self._hidden_channels = set(self._remembered_hidden())
        for number in range(1, count + 1):
            strip = ChannelStrip(number,
                                 programmable=number in programmable,
                                 note=unreadable.get(number, ""))
            strip.setpoint_committed.connect(self._strip_setpoint_requested)
            strip.output_toggled.connect(self._strip_output_requested)
            self._channel_layout.addWidget(strip, 1)
            self._strips[number] = strip
            if number in programmable:
                self._add_timer_button(strip, number)
            if number in programmable:
                self._channel_views[number] = self._build_channel_views(
                    number, capabilities)
            self._add_channel_box(number)
        self._range_strips(capabilities)
        self._apply_channel_visibility()

    def _add_timer_button(self, strip, number: int):
        """A channel's timer, on its own column.

        The guide: five timing groups per channel, each a voltage, a
        current and how long to hold them, run one after another. It
        only works in independent mode, and switching the output off
        pauses the countdown rather than ending it.
        """
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        button = QPushButton("Timer off")
        button.setCheckable(True)
        button.setToolTip(
            "Run CH%d through its five timing groups." % number)
        button.clicked.connect(
            lambda wanted, n=number: self._timer_requested(n, bool(wanted)))
        row.addWidget(button, 1)

        edit = QPushButton("Set...")
        edit.setToolTip(
            "Enter the five groups for CH%d: a voltage, a current and how "
            "long to hold them, run one after another." % number)
        edit.clicked.connect(lambda _c=False, n=number: self._open_timer(n))
        row.addWidget(edit)

        strip.layout().addLayout(row)
        self._timer_buttons[number] = button
        self._timer_edit_buttons[number] = edit

    def _open_timer(self, channel: int):
        """Put up the editor for one channel's five groups.

        Read from the instrument first. It holds these itself -- they
        survive a disconnection and can be set from the front panel --
        so offering an empty grid and sending it would quietly discard
        a setup somebody had already made.
        """
        existing = self._timer_dialogs.get(channel)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return

        # The timer's shape is the instrument's, not this editor's: the
        # SPD keeps whole seconds, and a supply with a finer timer
        # should be offered at its own resolution.
        dialog = TimerDialog(
            channel,
            max_voltage=self.capabilities.get("max_voltage",
                                              self.instrument_max_voltage),
            max_current=self.capabilities.get("max_current",
                                              self.instrument_max_current),
            parent=self,
            groups=self.capabilities.get("timer_groups") or (1, 2, 3, 4, 5),
            seconds_decimals=self.capabilities.get(
                "timer_seconds_decimals", 0),
            min_seconds=self.capabilities.get("min_timer_seconds", 1.0),
            max_seconds=self.capabilities.get("max_timer_seconds", 10000.0))
        dialog.accepted.connect(
            lambda n=channel: self._timer_steps_requested("send", n))
        dialog.reread_button.clicked.connect(
            lambda _c=False, n=channel: self._timer_steps_requested("read", n))
        self._timer_dialogs[channel] = dialog
        dialog.show()
        self._timer_steps_requested("read", channel)

    def _timer_steps_requested(self, what: str, channel: int):
        """Read or send, if there is anything to talk to.

        The editor opens whether or not a client is attached -- an
        operator can look at the grid -- so these two have to be as
        guarded as every other slot that reaches the server.
        """
        if not self._ready_to_send():
            return
        if what in ("read", "read_total"):
            self._read_timer_steps(channel)
        else:
            self._send_timer_steps(channel)

    @qasync.asyncSlot(int)
    async def _read_timer_steps(self, channel: int):
        """Fill the editor from the supply."""
        # Called with no editor open too, to total the groups for a
        # run that started elsewhere.
        dialog = self._timer_dialogs.get(channel)
        if not (self.client and self.equipment):
            return
        steps = []
        for group in (1, 2, 3, 4, 5):
            try:
                step = await call_blocking(
                    self.client.send_command, self.equipment.equipment_id,
                    "get_timer_step", {"channel": channel, "group": group})
            except Exception as e:
                logger.warning("Could not read CH%d timer group %d: %s"
                               % (channel, group, e))
                continue
            steps.append((step or {}).get("data") or step or {})
        self._remember_timer_total(channel, steps)
        if dialog is not None and dialog.isVisible():
            dialog.load(steps)

    @qasync.asyncSlot(int)
    async def _send_timer_steps(self, channel: int):
        """Write all five groups, then say so.

        Every group goes, including the ones left at zero: a group the
        operator cleared has to reach the instrument, or the sequence
        keeps running an old step they think they removed.
        """
        dialog = self._timer_dialogs.get(channel)
        if dialog is None or not (self.client and self.equipment):
            return
        for step in dialog.steps():
            try:
                await call_blocking(
                    self.client.send_command, self.equipment.equipment_id,
                    "set_timer_step",
                    {"channel": channel, "group": step["group"],
                     "voltage": step["voltage"], "current": step["current"],
                     "seconds": step["seconds"]})
            except Exception as e:
                logger.error("Sending CH%d timer group %d failed: %s"
                             % (channel, step["group"], e))
                self.status_message.emit(
                    "CH%d timer group %d was refused: %s"
                    % (channel, step["group"], e))
                return
        self._remember_timer_total(channel, dialog.steps())
        self.status_message.emit(
            "CH%d timer set. Press Timer to run it." % channel)

    def _timer_requested(self, channel: int, wanted: bool):
        if not self._ready_to_send():
            self._show_timer(channel, not wanted)
            return
        self._send_timer(channel, wanted)

    @qasync.asyncSlot(int, bool)
    async def _send_timer(self, channel: int, wanted: bool):
        try:
            await call_blocking(self.client.send_command,
                                self.equipment.equipment_id,
                                "set_timer_enabled",
                                {"enabled": wanted, "channel": channel})
        except Exception as e:
            logger.error("Switching CH%d's timer failed: %s" % (channel, e))
            self.status_message.emit(
                "Switching CH%d's timer failed: %s" % (channel, e))
            self._show_timer(channel, not wanted)
            return
        # The next poll confirms it; this is so the button moves on the
        # click rather than up to a poll interval later.
        self._note_timer_state(channel, wanted, True)
        self._show_timer(channel, wanted)

    def _show_timer(self, channel: int, running: bool):
        button = self._timer_buttons.get(channel)
        if button is None:
            return
        button.blockSignals(True)
        button.setChecked(bool(running))
        button.setText(self._timer_label(channel, running))
        button.blockSignals(False)

    def _timer_label(self, channel: int, running: bool) -> str:
        """What the button says.

        Elapsed against the total when both are known, because "Timer
        running" on its own tells an operator nothing they cannot see
        from the readings. The figure is this panel's count, not the
        supply's, so it is shown against the total rather than as a
        time remaining -- there is a difference between "about this far
        through" and a countdown the instrument would stand behind.
        """
        if not running:
            return "Timer off"
        total = self._timer_total.get(channel)
        if not total:
            return "Timer running"
        elapsed = min(self._timer_elapsed.get(channel, 0.0), total)
        return "Timer %s / %s" % (_spell_short(elapsed), _spell_short(total))

    def _note_timer_state(self, channel: int, running: bool,
                          output_on: bool) -> None:
        """Keep the estimate in step with the run.

        Starting resets the count. Stopping forgets it. While it runs
        the clock only advances when the output is on, because the
        guide is explicit that switching the output off pauses the
        countdown rather than ending it.
        """
        import time

        was = bool(self._timer_last_tick.get(channel) is not None)
        if not running:
            self._timer_elapsed.pop(channel, None)
            self._timer_last_tick.pop(channel, None)
            return
        now = time.monotonic()
        if not was:
            self._timer_elapsed[channel] = 0.0
            self._timer_last_tick[channel] = now
            # A run that started somewhere other than this panel still
            # wants a total to count against.
            if not self._timer_total.get(channel):
                self._timer_steps_requested("read_total", channel)
            return
        previous = self._timer_last_tick.get(channel) or now
        self._timer_last_tick[channel] = now
        if output_on:
            self._timer_elapsed[channel] = (
                self._timer_elapsed.get(channel, 0.0) + (now - previous))

    def _remember_timer_total(self, channel: int, steps) -> None:
        """Total the five groups, so there is something to count
        against."""
        total = 0.0
        for step in steps or []:
            seconds = (step or {}).get("seconds")
            if seconds:
                total += float(seconds)
        self._timer_total[channel] = total

    def _build_channel_views(self, number: int,
                             capabilities: Dict[str, Any]):
        """One channel's readings: digital, analog and graph.

        Vertical, and without its own selector or tools -- the panel
        keeps one of each above and drives every column from it.
        """
        max_voltage = capabilities.get("max_voltage",
                                       self.instrument_max_voltage)
        max_current = capabilities.get("max_current",
                                       self.instrument_max_current)
        views = MeasurementViews(
            (
                Channel("voltage", "CH%d Voltage" % number, "V",
                        capabilities.get("voltage_decimals", 3),
                        max_voltage, 1.0, "#4a9eff"),
                Channel("current", "CH%d Current" % number, "A",
                        capabilities.get("current_decimals", 3),
                        max_current, 0.1, "#ff9d4a"),
                Channel("power", "CH%d Power" % number, "W", 2,
                        max_voltage * max_current, 1.0, "#7ed957"),
            ),
            vertical=True, with_selector=False, with_tools=False,
        )
        views.set_mode(self.shared_mode_buttons.checkedId())
        self._readout_layout.addWidget(views, 1)
        return views

    def _adopt_rate_control(self):
        """Move the one rate control into the shared band.

        There is exactly one, and it is built inside the single-channel
        controls group -- which the columns hide. Re-parenting it keeps
        one widget and one set of handlers rather than a second rate
        that could disagree with the first.

        Where it came from is remembered, because it has to go back.
        """
        rate = getattr(self, "_rate_group", None)
        if rate is None or rate.parent() is self.shared_bar:
            return
        if self._rate_home is None:
            self._rate_home = rate.parentWidget()
        self.shared_bar.layout().addWidget(rate)
        rate.setVisible(True)

    def _return_rate_control(self):
        """Put it back with the single-channel controls.

        Without this it stayed in the shared band, which a
        single-channel instrument hides -- so selecting the Siglent and
        then a B&K supply left the B&K with no refresh rate at all. The
        same panel object serves both, so anything the columns borrow
        has to be given back.
        """
        rate = getattr(self, "_rate_group", None)
        home = self._rate_home
        if rate is None or home is None or rate.parentWidget() is home:
            return
        layout = home.layout()
        if layout is None:
            return
        layout.addWidget(rate)
        rate.setVisible(True)

    def _on_shared_mode(self, index: int, checked: bool):
        if not checked:
            return
        for views in self._channel_views.values():
            views.set_mode(index)

    def _on_shared_minmax(self, tracking: bool):
        """One button, every column.

        The views each keep their own extremes -- they are per channel
        -- but whether to track them is a decision about the readout,
        so it is made once.
        """
        for views in self._channel_views.values():
            views.set_minmax_tracking(tracking)
        self.shared_minmax_reset.setEnabled(tracking)

    def _on_shared_minmax_reset(self):
        for views in self._channel_views.values():
            views.reset_extremes()

    def _on_shared_autorange(self, on: bool):
        for views in self._channel_views.values():
            views.set_autorange(on)

    def _coupling_requested(self, mode: str):
        """Ask for independent, series or parallel.

        The buttons are put back where the supply says it is, not where
        the click left them: the driver switches both outputs off on
        the way, and if any of that is refused the panel must not be
        showing a mode the instrument is not in.
        """
        self._show_coupling(self._coupling)
        if not self._ready_to_send():
            return
        self._send_coupling(mode)

    @qasync.asyncSlot(str)
    async def _send_coupling(self, mode: str):
        try:
            await call_blocking(self.client.send_command,
                                self.equipment.equipment_id, "set_tracking",
                                {"mode": mode})
        except Exception as e:
            logger.error("Setting %s mode failed: %s" % (mode, e))
            self.status_message.emit("Setting %s mode failed: %s" % (mode, e))
            return
        self.status_message.emit(
            "%s mode selected -- both outputs were switched off, and the "
            "load may need rewiring" % mode.capitalize()
            if mode != "independent" else "Independent mode selected")

    def _show_coupling(self, mode):
        """Put the buttons and the indicator where the supply is."""
        self._coupling = mode
        for name, button in self.coupling_buttons.items():
            button.blockSignals(True)
            button.setChecked(name == mode)
            button.blockSignals(False)
        self.coupling_indicator.setText(
            "Mode: %s" % (mode.capitalize() if mode else "--"))
        # In series and parallel the pair is one channel driven by CH1,
        # so CH2's own controls would be commanding something that is
        # not listening.
        linked = mode in ("series", "parallel")
        second = self._strips.get(2)
        if second is not None:
            second.set_controls_enabled(not linked)
            second.setToolTip(
                "CH1 and CH2 are linked in %s mode; CH1 controls both."
                % mode if linked else "")
        for number, timer in self._timer_buttons.items():
            timer.setEnabled(not linked)
            timer.setToolTip(
                "The timer only runs in independent mode."
                if linked else
                "Run CH%d through its five timing groups." % number)
        for number, edit in self._timer_edit_buttons.items():
            # Setting groups up is refused in series and parallel too,
            # so there is nothing to be gained by opening the editor.
            edit.setEnabled(not linked)
            edit.setToolTip(
                "The timer only runs in independent mode."
                if linked else
                "Enter the five groups for CH%d." % number)

    def _single_channel_widgets_visible(self, visible: bool):
        for widget in (getattr(self, "_controls_group", None), self.views):
            if widget is not None:
                widget.setVisible(visible)
        if not visible:
            return
        # Coming back to a single-channel instrument: put the bands the
        # columns borrowed back out of the way, and give back the one
        # widget they borrowed out of them.
        self._return_rate_control()
        for widget in (self.shared_bar, self.readout_area):
            widget.setVisible(False)

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
            views = self._channel_views.get(number)
            if views is not None:
                views.setVisible(shown)
                self._readout_layout.setStretch(
                    self._readout_layout.indexOf(views), 1 if shown else 0)

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
            return
        # Show what was commanded. The poll corrects this for a channel
        # the supply reports, and for one it does not -- the fixed rail
        # has no bit in the status word -- this is the only thing that
        # will ever move the button. Without it CH3's switch stayed
        # reading "Output off" however many times it was pressed.
        strip = self._strips.get(channel)
        if strip is not None:
            strip.show_output(wanted)

    def _apply_all_readings(self, data: Dict[str, Any]):
        """One reply, every channel."""
        if data:
            coupling = data.get("coupling")
            if coupling != self._coupling:
                self._show_coupling(coupling)
        for entry in (data or {}).get("channels") or []:
            strip = self._strips.get(entry.get("channel"))
            if strip is None:
                continue
            # Not while somebody is typing into them; see
            # _apply_readings. Asked per column, because focus in one
            # channel says nothing about the other two.
            if not strip.is_being_edited():
                strip.show_setpoints(entry.get("voltage_set"),
                                     entry.get("current_set"))
            strip.show_output(bool(entry.get("output_enabled")))
            strip.show_mode(bool(entry.get("in_cv_mode")),
                            bool(entry.get("in_cc_mode")))
            number = entry.get("channel")
            if number in self._timer_buttons and "timer_running" in entry:
                running = bool(entry.get("timer_running"))
                self._note_timer_state(
                    number, running, bool(entry.get("output_enabled")))
                self._show_timer(number, running)
            views = self._channel_views.get(entry.get("channel"))
            if views is not None:
                voltage = entry.get("voltage_actual") or 0.0
                current = entry.get("current_actual") or 0.0
                # Power as the supply reports it when it does, and
                # otherwise the product of the two readings beside it,
                # so the third figure agrees with the first two.
                power = entry.get("power_actual")
                views.set_readings({
                    "voltage": voltage,
                    "current": current,
                    "power": voltage * current if power is None else power,
                })

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
