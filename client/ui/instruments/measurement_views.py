"""Digital, analog and graph views over a set of measured channels.

Lifted out of the power supply panel so the electronic load can have
the same three displays rather than a second implementation of them.
The supply had voltage and current; the load wants voltage, current and
power, and the supply wants power too -- so the channel set is data
rather than structure.

What travels together, and is why this is one widget rather than three:

* the three views show the same readings, so they share the mode
  selector and switch as a unit;
* Min/Max tracking and the markers it puts on the gauge faces are
  meaningful in all three;
* auto-ranging rescales the gauges *and* the graph from the same held
  maxima, and a range that only grows is the reason the needle and the
  trace do not jump about.

Splitting those apart was what made the supply's copy long. Keeping
them together is what makes this reusable.

The graph shows every channel, each on its own correctly scaled axis,
but draws axis furniture only for the first two -- three sets of
numbers down the sides of a chart that narrow is unreadable, and the
values are already on the readout strip and in the legend.
"""

import logging
from collections import deque
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from PyQt6.QtCharts import QChart, QLineSeries, QValueAxis
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (QButtonGroup, QGroupBox, QHBoxLayout, QLabel,
                             QPushButton, QRadioButton, QSizePolicy,
                             QStackedWidget, QVBoxLayout, QWidget)

from client.ui.instruments.widgets import (AnalogGauge, ChartWithReadouts,
                                           FittedReadout, nice_range)
from client.ui.theme import dialog_palette, get_theme_setting

logger = logging.getLogger(__name__)

#: How many readings the graph keeps.
HISTORY = 100


@dataclass(frozen=True)
class Channel:
    """One measured quantity, as all three views need to know it."""

    key: str                    #: how readings are keyed, e.g. "voltage"
    label: str                  #: "Voltage"
    unit: str                   #: "V"
    decimals: int = 3
    maximum: float = 100.0      #: full scale the instrument can reach
    #: Smallest sensible auto-range top. Without a floor a channel
    #: resting at zero would range down to nothing and the first real
    #: reading would peg the needle.
    floor: float = 0.1
    colour: str = "#4a9eff"


#: The pair the supply has always shown, plus the power the operator
#: was working out in their head.
VOLTS_AMPS_WATTS = (
    Channel("voltage", "Voltage", "V", 3, 60.0, 1.0, "#4a9eff"),
    Channel("current", "Current", "A", 3, 16.0, 0.1, "#ff9d4a"),
    Channel("power", "Power", "W", 2, 200.0, 1.0, "#7ed957"),
)


class MeasurementViews(QWidget):
    """The Digital / Analog / Graph stack, its selector, and its tools."""

    def __init__(self, channels: Iterable[Channel], parent=None):
        super().__init__(parent)
        self.channels = tuple(channels)
        if not self.channels:
            raise ValueError("MeasurementViews needs at least one channel")

        self._extremes: Dict[str, list] = {
            c.key: [None, None] for c in self.channels
        }
        #: The top of scale auto-range has settled on, per channel. It
        #: only ever grows: a scale that shrank when the reading fell
        #: made the needle and the trace jump about.
        self._auto_top: Dict[str, Optional[float]] = {
            c.key: None for c in self.channels
        }
        #: Last readings as they arrived, before any clamping. Reading
        #: them back off a gauge does not work -- set_value clamps to
        #: the current top of scale, so a 2.4 A reading on a 0.15 A
        #: scale came back as 0.15 and the range crept up one step per
        #: reading instead of jumping to fit.
        self._last: Dict[str, float] = {c.key: 0.0 for c in self.channels}
        self._history: Dict[str, deque] = {
            c.key: deque(maxlen=HISTORY) for c in self.channels
        }
        #: Full scale per channel. Kept here rather than on Channel,
        #: which is frozen: a panel re-ranges these from the
        #: instrument's capabilities at connect time, and a frozen
        #: dataclass is the wrong place to keep something that changes.
        self._full_scale: Dict[str, float] = {
            c.key: c.maximum for c in self.channels
        }
        self._decimals: Dict[str, int] = {
            c.key: c.decimals for c in self.channels
        }

        self.displays: Dict[str, FittedReadout] = {}
        #: The rules between the digital readouts, in order.
        self.dividers: list = []
        self.gauges: Dict[str, AnalogGauge] = {}
        self.series: Dict[str, QLineSeries] = {}
        self.axes: Dict[str, QValueAxis] = {}

        self._build()

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self._build_mode_selector())

        self.stack = QStackedWidget()
        # Kept by name as well as by index: a caller that wants to grab
        # the digital face and look at the pixels should not have to
        # know which slot it is in.
        self.digital_view = self._build_digital()
        self.analog_view = self._build_analog()
        self.graph_view = self._build_graph()
        self.stack.addWidget(self.digital_view)
        self.stack.addWidget(self.analog_view)
        self.stack.addWidget(self.graph_view)
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding,
                                 QSizePolicy.Policy.Expanding)
        layout.addWidget(self.stack, 1)

        layout.addWidget(self._build_tools())

    def _build_mode_selector(self) -> QGroupBox:
        group = QGroupBox("Display Mode")
        row = QHBoxLayout(group)
        self.mode_group = QButtonGroup(self)
        self.digital_radio = QRadioButton("Digital")
        self.digital_radio.setChecked(True)
        self.analog_radio = QRadioButton("Analog")
        self.graph_radio = QRadioButton("Graph")
        for index, radio in enumerate((self.digital_radio, self.analog_radio,
                                       self.graph_radio)):
            self.mode_group.addButton(radio, index)
            row.addWidget(radio)
        self.mode_group.idToggled.connect(self._on_mode_changed)
        return group

    def _build_digital(self) -> QWidget:
        """One black face with the readings side by side."""
        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Policy.Expanding,
                             QSizePolicy.Policy.Expanding)
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 0, 0, 0)

        panel = QWidget()
        panel.setObjectName("digitalPanel")
        panel.setSizePolicy(QSizePolicy.Policy.Expanding,
                            QSizePolicy.Policy.Expanding)
        panel.setStyleSheet(
            "QWidget#digitalPanel { background-color: black; border-radius: 6px; }"
            # Inset top and bottom so a rule reads as a separator between
            # readings rather than a border cutting the panel into parts.
            "QWidget#digitalDivider { background-color: #3f4a3f; margin: 16px 0; }"
        )
        readings = QHBoxLayout(panel)
        readings.setContentsMargins(12, 12, 12, 12)
        readings.setSpacing(12)

        for index, channel in enumerate(self.channels):
            if index:
                # A plain widget rather than a QFrame VLine: a frame
                # draws itself from the palette, which the dark sheet
                # supplies, and is all but invisible on black.
                divider = QWidget()
                divider.setObjectName("digitalDivider")
                divider.setFixedWidth(8)
                divider.setSizePolicy(QSizePolicy.Policy.Fixed,
                                      QSizePolicy.Policy.Expanding)
                readings.addWidget(divider)
                self.dividers.append(divider)
            readout = FittedReadout(
                f"{0:.{channel.decimals}f} {channel.unit}")
            self.displays[channel.key] = readout
            readings.addWidget(readout, 1)

        outer.addWidget(panel)
        return widget

    def _build_analog(self) -> QWidget:
        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Policy.Expanding,
                             QSizePolicy.Policy.Expanding)
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        for channel in self.channels:
            gauge = AnalogGauge(channel.label, 0, channel.maximum, channel.unit)
            self.gauges[channel.key] = gauge
            row.addWidget(gauge, 1)
        return widget

    def _build_graph(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        colours = dialog_palette()
        self.chart = QChart()
        self.chart.setTitle(" and ".join(c.label for c in self.channels)
                            + " vs Time")
        self.chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        self.chart.setTheme(
            QChart.ChartTheme.ChartThemeDark
            if get_theme_setting() == "dark"
            else QChart.ChartTheme.ChartThemeLight
        )

        self.axis_x = QValueAxis()
        self.axis_x.setTitleText("Samples")
        self.axis_x.setRange(0, HISTORY)

        for index, channel in enumerate(self.channels):
            series = QLineSeries()
            series.setName(f"{channel.label} ({channel.unit})")
            series.setColor(QColor(channel.colour))
            self.chart.addSeries(series)
            self.series[channel.key] = series

            axis = QValueAxis()
            axis.setTitleText(f"{channel.label} ({channel.unit})")
            axis.setRange(0, channel.maximum)
            # Only the first two get furniture: three sets of numbers
            # down the sides of a chart this narrow cannot be read, and
            # the values are on the readout strip and in the legend
            # already. The axis still exists and still scales, so the
            # trace is correct either way.
            if index == 0:
                self.chart.addAxis(axis, Qt.AlignmentFlag.AlignLeft)
            elif index == 1:
                self.chart.addAxis(axis, Qt.AlignmentFlag.AlignRight)
            else:
                axis.setVisible(False)
                self.chart.addAxis(axis, Qt.AlignmentFlag.AlignRight)
            series.attachAxis(self.axis_x)
            series.attachAxis(axis)
            self.axes[channel.key] = axis

        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
        for series in self.series.values():
            series.attachAxis(self.axis_x)

        self.chart.setTitleBrush(QColor(colours["text"]))
        if self.chart.legend():
            self.chart.legend().setLabelColor(QColor(colours["text"]))

        self.chart_view = ChartWithReadouts(self.chart)
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        layout.addWidget(self.chart_view)
        return widget

    def _build_tools(self) -> QWidget:
        """Min/Max and auto-range, which apply to all three views."""
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
        self.minmax_label.setToolTip(
            "Lowest and highest reading since tracking began")
        row.addWidget(self.minmax_label, 1)

        self.minmax_reset_button = QPushButton("Reset")
        self.minmax_reset_button.setToolTip(
            "Start tracking again from the next reading")
        self.minmax_reset_button.clicked.connect(self.reset_extremes)
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

    # ------------------------------------------------------------------ #
    # Readings
    # ------------------------------------------------------------------ #

    def set_readings(self, readings: Dict[str, Optional[float]]):
        """Show a set of readings. Missing or None channels blank out."""
        for channel in self.channels:
            value = readings.get(channel.key)
            readout = self.displays[channel.key]
            if value is None:
                readout.setText(f"-- {channel.unit}")
                continue
            value = float(value)
            self._last[channel.key] = value
            readout.setText(
                f"{value:.{self._decimals[channel.key]}f} {channel.unit}")
            self.gauges[channel.key].set_value(value)
            self._history[channel.key].append(value)

        self._track_extremes()
        self._apply_auto_range()
        self._redraw_series()
        if len(self.channels) >= 2:
            first, second = self.channels[0], self.channels[1]
            self.chart_view.set_readings(
                self._last[first.key], self._last[second.key],
                self._decimals[first.key], self._decimals[second.key],
            )

    def blank(self):
        """No instrument, or nothing to say about it."""
        for channel in self.channels:
            self.displays[channel.key].setText(f"-- {channel.unit}")

    def _redraw_series(self):
        for channel in self.channels:
            self.series[channel.key].replace(
                [QPointF(i, v)
                 for i, v in enumerate(self._history[channel.key])]
            )

    # ------------------------------------------------------------------ #
    # Min/Max
    # ------------------------------------------------------------------ #

    def _track_extremes(self):
        if not self.minmax_button.isChecked():
            return
        for channel in self.channels:
            value = self._last[channel.key]
            low, high = self._extremes[channel.key]
            self._extremes[channel.key] = [
                value if low is None else min(low, value),
                value if high is None else max(high, value),
            ]
        self._update_minmax()

    def reset_extremes(self):
        """Forget what has been seen and start again."""
        self._extremes = {c.key: [None, None] for c in self.channels}
        # The held scale is a record of what has been seen too, so Reset
        # would otherwise leave the dial stuck wide open.
        self._auto_top = {c.key: None for c in self.channels}
        self._update_minmax()

    def _update_minmax(self):
        self._mark_gauges()
        first = self.channels[0]
        if self._extremes[first.key][0] is None:
            self.minmax_label.setText(
                "waiting for a reading..."
                if self.minmax_button.isChecked() else "")
            return
        parts = []
        for channel in self.channels:
            low, high = self._extremes[channel.key]
            places = self._decimals[channel.key]
            parts.append(f"{channel.unit}  {low:.{places}f} / "
                         f"{high:.{places}f}")
        self.minmax_label.setText("       ".join(parts))

    def _mark_gauges(self):
        """Put the extremes on the meter faces, or take them off.

        Cleared when tracking is off, so a stale pair cannot sit on the
        face looking current.
        """
        tracking = self.minmax_button.isChecked()
        for channel in self.channels:
            gauge = self.gauges[channel.key]
            if tracking:
                gauge.set_markers(*self._extremes[channel.key])
            else:
                gauge.set_markers(None, None)

    def _on_minmax_toggled(self, enabled: bool):
        self.minmax_reset_button.setEnabled(enabled)
        if enabled:
            self.reset_extremes()
        else:
            self.minmax_label.setText("")
            self._mark_gauges()

    # ------------------------------------------------------------------ #
    # Ranging
    # ------------------------------------------------------------------ #

    def set_maximum(self, key: str, maximum: float):
        """The instrument's own full scale for a channel."""
        if key not in self._full_scale:
            return
        self._full_scale[key] = float(maximum)
        if not self.autorange_button.isChecked():
            self.gauges[key].max_value = float(maximum)
            self.axes[key].setRange(0, float(maximum))
            self.gauges[key].update()

    def set_decimals(self, key: str, decimals: int):
        if key in self._decimals:
            self._decimals[key] = int(decimals)

    def apply_auto_range(self, readings: Optional[Dict[str, float]] = None):
        """Re-range, optionally from readings that did not come through
        set_readings -- which is how a caller says "the last reading was
        this" without redrawing everything around it."""
        if readings:
            for key, value in readings.items():
                if key in self._last:
                    self._last[key] = float(value)
        self._apply_auto_range()

    def _apply_auto_range(self):
        if not self.autorange_button.isChecked():
            return
        for channel in self.channels:
            top = nice_range(self._last[channel.key],
                             self._full_scale[channel.key], channel.floor)
            held = self._auto_top[channel.key]
            if held is not None and top < held:
                top = held          # only ever grows
            self._auto_top[channel.key] = top
            self.gauges[channel.key].max_value = top
            self.axes[channel.key].setRange(0, top)
            self.gauges[channel.key].update()

    def _on_autorange_toggled(self, enabled: bool):
        if enabled:
            self._auto_top = {c.key: None for c in self.channels}
            self._apply_auto_range()
            return
        # Back to what the instrument can actually do.
        for channel in self.channels:
            self.gauges[channel.key].max_value = self._full_scale[channel.key]
            self.axes[channel.key].setRange(0, self._full_scale[channel.key])
            self.gauges[channel.key].update()

    # ------------------------------------------------------------------ #
    # Mode
    # ------------------------------------------------------------------ #

    def _on_mode_changed(self, index: int, checked: bool):
        if checked:
            self.stack.setCurrentIndex(index)

    def current_mode(self) -> str:
        return ("digital", "analog", "graph")[self.stack.currentIndex()]
