"""The oscilloscope panel: channels, timebase, trigger, measurements, live trace.

Laid out the way the front panel is -- vertical controls per channel on one
side, horizontal and trigger on the other, run/stop/single where the thumb
falls -- because that is the arrangement every operator already knows.

Two cadences, both owned by the panel: automatic measurements on the base
class's poll timer (default 2 Hz; a ``:MEAS:ITEM?`` round trip per item is
not free), and the waveform on its own slower timer (default 1 Hz), fetched
decimated (``points``) so a live trace does not move 1200 floats per channel
per second into a chart 400 pixels wide.

Every command is one the drivers already expose through ``execute_command``:
``set_channel``, ``set_timebase``, ``set_trigger``, ``trigger_run`` /
``trigger_stop`` / ``trigger_single`` / ``force_trigger`` / ``autoscale``,
``get_measurements``, ``get_waveform_data``, ``get_state``. The legacy
DS1000Z / MSO2000A / DS1000D drivers gained the ones they lacked in
``rigol_scope.LegacyScopeExtras``.
"""

import logging
import math
from typing import Any, Dict, List, Optional

import qasync
from PyQt6.QtCharts import QChart, QLineSeries, QValueAxis
from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QGridLayout,
                             QGroupBox, QHBoxLayout, QLabel, QPushButton,
                             QSizePolicy, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from client.ui.instruments.base import POLL_MEASUREMENTS, InstrumentPanel
from client.ui.instruments.widgets import ChartWithReadouts  # noqa: F401  (shared look)
from client.ui.theme import dialog_palette, get_theme_setting

logger = logging.getLogger(__name__)

#: Rigol's channel colours, which every operator of one has already learned.
CHANNEL_COLOURS = ["#F8FC00", "#00FCF8", "#F800F8", "#0080FF", "#FF8000", "#00FF00", "#FF4040", "#C0C0C0"]

#: 1-2-5 vertical scales from 1 mV/div to 10 V/div.
VOLTS_PER_DIV = [v * m for m in (1e-3, 1e-2, 1e-1, 1.0) for v in (1, 2, 5)] + [10.0]

#: 1-2-5 horizontal scales from 1 ns/div to 50 s/div.
SECONDS_PER_DIV = [v * m for m in (1e-9, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 1e-1, 1.0) for v in (1, 2, 5)] + [10.0, 20.0, 50.0]

MEASUREMENT_ROWS = [
    ("vpp", "Vpp", "V"), ("vmax", "Vmax", "V"), ("vmin", "Vmin", "V"),
    ("vavg", "Vavg", "V"), ("vrms", "Vrms", "V"), ("freq", "Frequency", "Hz"),
    ("period", "Period", "s"), ("rise_time", "Rise time", "s"),
    ("fall_time", "Fall time", "s"), ("duty", "Duty cycle", "%"),
]


def si_format(value: Optional[float], unit: str) -> str:
    """4.700 mV rather than 0.0047 V: the way the instrument prints it."""
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "--"
    if unit == "%":
        return f"{value:.1f} %"
    magnitude = abs(value)
    for factor, prefix in ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n")):
        if magnitude >= factor or factor == 1e-9:
            return f"{value / factor:.4g} {prefix}{unit}"
    return f"{value:.4g} {unit}"


class OscilloscopePanel(InstrumentPanel):
    """Drive an oscilloscope and watch its trace."""

    POLLS = POLL_MEASUREMENTS
    #: Automatic measurements: each item is a query round trip.
    DEFAULT_INTERVAL_MS = 500
    SETTINGS_TYPE = "oscilloscope"

    #: The live trace has its own, slower cadence.
    TRACE_INTERVAL_MS = 1000
    #: Points per channel per fetch; decimated by the server.
    TRACE_POINTS = 600
    MAX_CHANNELS = 8

    def __init__(self, parent=None):
        self.num_channels = 4
        self.channel_rows: List[Dict[str, Any]] = []
        self.series: List[QLineSeries] = []
        self._trace_started_at = None
        self._trace_unsupported = False
        self._last_trace: Dict[int, Dict[str, Any]] = {}
        super().__init__(parent)
        self.trace_timer = QTimer(self)
        self.trace_timer.timeout.connect(self._poll_trace)
        self._trace_interval_ms = self.TRACE_INTERVAL_MS

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Left: the trace and the measurements under it.
        left = QVBoxLayout()
        left.addWidget(self._create_trace(), 3)
        left.addWidget(self._create_measurements(), 1)
        outer.addLayout(left, 3)

        # Right: the controls, in front-panel order.
        right = QVBoxLayout()
        right.addWidget(self._create_run_controls())
        right.addWidget(self._create_channel_controls())
        right.addWidget(self._create_horizontal_controls())
        right.addWidget(self._create_trigger_controls())
        rates = QHBoxLayout()
        rates.addWidget(self._create_rate_control("How often to re-read the automatic measurements"))
        rates.addWidget(self._create_trace_rate_control())
        right.addLayout(rates)
        right.addStretch()
        outer.addLayout(right, 2)

    def _create_trace(self) -> QWidget:
        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.chart = QChart()
        self.chart.setTitle("Live trace")
        self.chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        self.chart.setTheme(
            QChart.ChartTheme.ChartThemeDark if get_theme_setting() == "dark"
            else QChart.ChartTheme.ChartThemeLight
        )
        self.axis_x = QValueAxis()
        self.axis_x.setTitleText("Time (s)")
        self.axis_x.setLabelFormat("%.3g")
        self.axis_x.setRange(-0.005, 0.005)
        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
        self.axis_y = QValueAxis()
        self.axis_y.setTitleText("Volts")
        self.axis_y.setLabelFormat("%.3g")
        self.axis_y.setRange(-4.0, 4.0)
        self.chart.addAxis(self.axis_y, Qt.AlignmentFlag.AlignLeft)

        for n in range(self.MAX_CHANNELS):
            series = QLineSeries()
            series.setName(f"CH{n + 1}")
            series.setPen(QPen(QColor(CHANNEL_COLOURS[n % len(CHANNEL_COLOURS)]), 1.5))
            series.setUseOpenGL(False)
            self.chart.addSeries(series)
            series.attachAxis(self.axis_x)
            series.attachAxis(self.axis_y)
            series.setVisible(n < self.num_channels)
            self.series.append(series)

        _c = dialog_palette()
        self.chart.setTitleBrush(QColor(_c["text"]))
        if self.chart.legend():
            self.chart.legend().setLabelColor(QColor(_c["text"]))
        for axis in (self.axis_x, self.axis_y):
            axis.setLabelsColor(QColor(_c["text"]))
            axis.setTitleBrush(QColor(_c["text"]))

        self.chart_view = ChartWithReadouts(self.chart)
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        # The supply-style readouts do not apply; hide them.
        self.chart_view.voltage_readout.hide()
        self.chart_view.current_readout.hide()
        layout.addWidget(self.chart_view)

        self.trace_note = QLabel("")
        layout.addWidget(self.trace_note)
        return widget

    def _create_measurements(self) -> QGroupBox:
        group = QGroupBox("Measurements")
        layout = QVBoxLayout(group)
        row = QHBoxLayout()
        row.addWidget(QLabel("Source:"))
        self.measure_channel = QComboBox()
        for n in range(1, self.num_channels + 1):
            self.measure_channel.addItem(f"CH{n}", n)
        self.measure_channel.currentIndexChanged.connect(self._on_measure_channel_changed)
        row.addWidget(self.measure_channel)
        row.addStretch()
        layout.addLayout(row)

        self.measurement_table = QTableWidget(len(MEASUREMENT_ROWS), 2)
        self.measurement_table.setHorizontalHeaderLabels(["Item", "Value"])
        self.measurement_table.horizontalHeader().setStretchLastSection(True)
        self.measurement_table.verticalHeader().setVisible(False)
        self.measurement_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for i, (_key, label, _unit) in enumerate(MEASUREMENT_ROWS):
            self.measurement_table.setItem(i, 0, QTableWidgetItem(label))
            self.measurement_table.setItem(i, 1, QTableWidgetItem("--"))
        layout.addWidget(self.measurement_table)
        return group

    def _create_run_controls(self) -> QGroupBox:
        group = QGroupBox("Acquisition")
        layout = QHBoxLayout(group)
        self.run_button = QPushButton("Run")
        self.stop_button = QPushButton("Stop")
        self.single_button = QPushButton("Single")
        self.force_button = QPushButton("Force")
        self.autoscale_button = QPushButton("Auto")
        self.run_button.clicked.connect(lambda: self._command("trigger_run"))
        self.stop_button.clicked.connect(lambda: self._command("trigger_stop"))
        self.single_button.clicked.connect(lambda: self._command("trigger_single"))
        self.force_button.clicked.connect(lambda: self._command("force_trigger"))
        self.autoscale_button.clicked.connect(lambda: self._command("autoscale"))
        for b in (self.run_button, self.stop_button, self.single_button,
                  self.force_button, self.autoscale_button):
            layout.addWidget(b)
        self.trigger_status = QLabel("")
        layout.addWidget(self.trigger_status)
        return group

    def _create_channel_controls(self) -> QGroupBox:
        group = QGroupBox("Vertical")
        grid = QGridLayout(group)
        for col, header in enumerate(("", "Scale (V/div)", "Offset (V)", "Coupling", "")):
            grid.addWidget(QLabel(header), 0, col)
        for n in range(self.MAX_CHANNELS):
            colour = CHANNEL_COLOURS[n % len(CHANNEL_COLOURS)]
            enable = QCheckBox(f"CH{n + 1}")
            enable.setChecked(n == 0)
            enable.setStyleSheet(f"QCheckBox {{ color: {colour}; font-weight: bold; }}")
            scale = QComboBox()
            for v in VOLTS_PER_DIV:
                scale.addItem(si_format(v, "V/div"), v)
            scale.setCurrentIndex(VOLTS_PER_DIV.index(1.0))
            offset = QDoubleSpinBox()
            offset.setRange(-100.0, 100.0)
            offset.setDecimals(3)
            offset.setSingleStep(0.1)
            coupling = QComboBox()
            coupling.addItems(["DC", "AC", "GND"])
            apply_btn = QPushButton("Apply")
            apply_btn.clicked.connect(lambda _=False, ch=n + 1: self._apply_channel(ch))
            row = n + 1
            for col, w in enumerate((enable, scale, offset, coupling, apply_btn)):
                grid.addWidget(w, row, col)
            self.channel_rows.append({
                "enable": enable, "scale": scale, "offset": offset,
                "coupling": coupling, "apply": apply_btn,
            })
            enable.toggled.connect(lambda checked, ch=n + 1: self._on_channel_enabled(ch, checked))
        self._show_channel_rows()
        return group

    def _create_horizontal_controls(self) -> QGroupBox:
        group = QGroupBox("Horizontal")
        layout = QGridLayout(group)
        layout.addWidget(QLabel("Scale (s/div):"), 0, 0)
        self.timebase_scale = QComboBox()
        for v in SECONDS_PER_DIV:
            self.timebase_scale.addItem(si_format(v, "s/div"), v)
        self.timebase_scale.setCurrentIndex(SECONDS_PER_DIV.index(1e-3))
        layout.addWidget(self.timebase_scale, 0, 1)
        layout.addWidget(QLabel("Offset (s):"), 1, 0)
        self.timebase_offset = QDoubleSpinBox()
        self.timebase_offset.setRange(-1000.0, 1000.0)
        self.timebase_offset.setDecimals(6)
        self.timebase_offset.setSingleStep(0.001)
        layout.addWidget(self.timebase_offset, 1, 1)
        self.timebase_apply = QPushButton("Apply")
        self.timebase_apply.clicked.connect(self._apply_timebase)
        layout.addWidget(self.timebase_apply, 0, 2, 2, 1)
        return group

    def _create_trigger_controls(self) -> QGroupBox:
        group = QGroupBox("Trigger (edge)")
        layout = QGridLayout(group)
        layout.addWidget(QLabel("Source:"), 0, 0)
        self.trigger_source = QComboBox()
        layout.addWidget(self.trigger_source, 0, 1)
        layout.addWidget(QLabel("Level (V):"), 1, 0)
        self.trigger_level = QDoubleSpinBox()
        self.trigger_level.setRange(-100.0, 100.0)
        self.trigger_level.setDecimals(3)
        self.trigger_level.setSingleStep(0.1)
        layout.addWidget(self.trigger_level, 1, 1)
        layout.addWidget(QLabel("Slope:"), 2, 0)
        self.trigger_slope = QComboBox()
        self.trigger_slope.addItem("Rising", "POS")
        self.trigger_slope.addItem("Falling", "NEG")
        self.trigger_slope.addItem("Either", "RFAL")
        layout.addWidget(self.trigger_slope, 2, 1)
        layout.addWidget(QLabel("Sweep:"), 3, 0)
        self.trigger_sweep = QComboBox()
        self.trigger_sweep.addItem("Auto", "AUTO")
        self.trigger_sweep.addItem("Normal", "NORMAL")
        self.trigger_sweep.addItem("Single", "SINGLE")
        layout.addWidget(self.trigger_sweep, 3, 1)
        self.trigger_apply = QPushButton("Apply")
        self.trigger_apply.clicked.connect(self._apply_trigger)
        layout.addWidget(self.trigger_apply, 0, 2, 4, 1)
        self._fill_trigger_sources()
        return group

    def _create_trace_rate_control(self) -> QGroupBox:
        group = QGroupBox("Trace Rate")
        layout = QHBoxLayout(group)
        layout.addWidget(QLabel("Update Rate (Hz):"))
        self.trace_rate_spinbox = QDoubleSpinBox()
        self.trace_rate_spinbox.setRange(0.1, 5.0)
        self.trace_rate_spinbox.setDecimals(1)
        self.trace_rate_spinbox.setSingleStep(0.1)
        self.trace_rate_spinbox.setValue(1000.0 / self.TRACE_INTERVAL_MS)
        self.trace_rate_spinbox.setToolTip("How often to fetch the waveform for the live trace")
        self.trace_rate_spinbox.valueChanged.connect(self._on_trace_rate_changed)
        layout.addWidget(self.trace_rate_spinbox)
        return group

    def _show_channel_rows(self):
        for n, row in enumerate(self.channel_rows):
            visible = n < self.num_channels
            for w in row.values():
                w.setVisible(visible)
        for n, series in enumerate(self.series):
            series.setVisible(n < self.num_channels and self.channel_rows[n]["enable"].isChecked())

    def _fill_trigger_sources(self):
        current = self.trigger_source.currentData()
        self.trigger_source.blockSignals(True)
        self.trigger_source.clear()
        for n in range(1, self.num_channels + 1):
            self.trigger_source.addItem(f"CH{n}", f"CHAN{n}")
        self.trigger_source.addItem("EXT", "EXT")
        self.trigger_source.addItem("AC Line", "ACL")
        idx = self.trigger_source.findData(current)
        self.trigger_source.setCurrentIndex(idx if idx >= 0 else 0)
        self.trigger_source.blockSignals(False)

    # ------------------------------------------------------------------ #
    # Contract
    # ------------------------------------------------------------------ #

    def configure(self, capabilities: Dict[str, Any]):
        n = capabilities.get("num_channels") or capabilities.get("analog_channels") or 4
        try:
            n = int(n)
        except (TypeError, ValueError):
            n = 4
        self.num_channels = max(1, min(self.MAX_CHANNELS, n))
        self._show_channel_rows()
        self.measure_channel.blockSignals(True)
        self.measure_channel.clear()
        for ch in range(1, self.num_channels + 1):
            self.measure_channel.addItem(f"CH{ch}", ch)
        self.measure_channel.blockSignals(False)
        self._fill_trigger_sources()
        self._trace_unsupported = False
        self.trace_note.setText("")
        self._clear_trace()
        self._clear_measurements()
        bandwidth = capabilities.get("bandwidth") or capabilities.get("bandwidth_mhz")
        if bandwidth:
            self.chart.setTitle(f"Live trace — {bandwidth}{' MHz' if isinstance(bandwidth, (int, float)) else ''}")
        else:
            self.chart.setTitle("Live trace")
        self._show_current_settings()

    def _show_current_settings(self):
        """Read the scope's own settings onto the controls without commanding it.

        Best effort and synchronous like the supply's setpoint read-back: the
        controls are blocked while they are set, so nothing is sent.
        """
        if not (self.client and self.equipment):
            return
        try:
            result = self.client.send_command(self.equipment.equipment_id, "get_state", {})
            if not result.get("success"):
                return
            state = result.get("data") or {}
        except Exception as e:
            logger.debug(f"Could not read scope state: {e}")
            return

        widgets = [w for row in self.channel_rows for w in row.values()] + [
            self.timebase_scale, self.timebase_offset, self.trigger_source,
            self.trigger_level, self.trigger_slope, self.trigger_sweep,
        ]
        for w in widgets:
            w.blockSignals(True)
        try:
            for ch_key, ch in (state.get("channels") or {}).items():
                try:
                    idx = int(ch_key) - 1
                except ValueError:
                    continue
                if idx < 0 or idx >= len(self.channel_rows) or not isinstance(ch, dict):
                    continue
                row = self.channel_rows[idx]
                if ch.get("enabled") is not None:
                    row["enable"].setChecked(bool(ch["enabled"]))
                if ch.get("scale") is not None:
                    self._select_nearest(row["scale"], float(ch["scale"]))
                if ch.get("offset") is not None:
                    row["offset"].setValue(float(ch["offset"]))
                if ch.get("coupling"):
                    i = row["coupling"].findText(str(ch["coupling"]).upper()[:3])
                    if i >= 0:
                        row["coupling"].setCurrentIndex(i)
            tb = state.get("timebase") or {}
            if tb.get("scale") is not None:
                self._select_nearest(self.timebase_scale, float(tb["scale"]))
            if tb.get("offset") is not None:
                self.timebase_offset.setValue(float(tb["offset"]))
            tr = state.get("trigger") or {}
            if tr.get("source"):
                i = self.trigger_source.findData(str(tr["source"]).upper()[:5].replace("CHANN", "CHAN"))
                if i >= 0:
                    self.trigger_source.setCurrentIndex(i)
            if tr.get("level") is not None:
                self.trigger_level.setValue(float(tr["level"]))
            if tr.get("slope"):
                i = self.trigger_slope.findData(str(tr["slope"]).upper()[:4])
                if i >= 0:
                    self.trigger_slope.setCurrentIndex(i)
            if tr.get("sweep"):
                sweep = str(tr["sweep"]).upper()
                sweep = {"NORM": "NORMAL", "SING": "SINGLE"}.get(sweep[:4], sweep)
                i = self.trigger_sweep.findData(sweep)
                if i >= 0:
                    self.trigger_sweep.setCurrentIndex(i)
            if tr.get("status"):
                self.trigger_status.setText(str(tr["status"]))
        finally:
            for w in widgets:
                w.blockSignals(False)
        self._show_channel_rows()

    @staticmethod
    def _select_nearest(combo: QComboBox, value: float):
        best, best_err = 0, float("inf")
        for i in range(combo.count()):
            data = combo.itemData(i)
            if data is None:
                continue
            err = abs(math.log10(max(float(data), 1e-15)) - math.log10(max(value, 1e-15)))
            if err < best_err:
                best, best_err = i, err
        combo.setCurrentIndex(best)

    def set_controls_enabled(self, enabled: bool):
        for row in self.channel_rows:
            for w in row.values():
                w.setEnabled(enabled)
        for w in (self.run_button, self.stop_button, self.single_button, self.force_button,
                  self.autoscale_button, self.timebase_scale, self.timebase_offset,
                  self.timebase_apply, self.trigger_source, self.trigger_level,
                  self.trigger_slope, self.trigger_sweep, self.trigger_apply):
            w.setEnabled(enabled)

    def show_not_connected(self):
        self._clear_measurements()
        self.trace_note.setText("Not connected. Connect it on the Equipment tab to read it.")
        self.status_message.emit("Not connected. Connect it on the Equipment tab to read it.")

    def show_unsupported(self):
        self._clear_measurements()
        name = getattr(self.equipment, "name", "This instrument")
        self.status_message.emit(f"{name} does not report automatic measurements.")

    def clear_instrument(self):
        self._clear_measurements()
        self._clear_trace()
        self.trigger_status.setText("")

    def _clear_measurements(self):
        for i in range(self.measurement_table.rowCount()):
            item = self.measurement_table.item(i, 1)
            if item is not None:
                item.setText("--")

    def _clear_trace(self):
        for series in self.series:
            series.clear()
        self._last_trace.clear()

    # ------------------------------------------------------------------ #
    # Polling: measurements on the base timer, the trace on its own
    # ------------------------------------------------------------------ #

    async def poll(self):
        channel = self.measure_channel.currentData() or 1
        data = await self.send("get_measurements", {"channel": int(channel)})
        self._show_measurements(data or {})

    def _show_measurements(self, data: Dict[str, Any]):
        for i, (key, _label, unit) in enumerate(MEASUREMENT_ROWS):
            value = data.get(key)
            try:
                value = float(value) if value is not None else None
            except (TypeError, ValueError):
                value = None
            self.measurement_table.item(i, 1).setText(si_format(value, unit))

    def _start_now(self):
        super()._start_now()
        if self.poll_timer.isActive() and not self._trace_unsupported:
            self.trace_timer.start(self.trace_interval_ms())

    def stop(self):
        super().stop()
        self.trace_timer.stop()

    def is_polling(self) -> bool:
        return super().is_polling() or self.trace_timer.isActive()

    def trace_interval_ms(self) -> int:
        return max(int(self._trace_interval_ms), 50)

    def _on_trace_rate_changed(self, value: float):
        self._trace_interval_ms = int(round(1000.0 / max(float(value), 0.1)))
        if self.trace_timer.isActive():
            self.trace_timer.setInterval(self.trace_interval_ms())

    def enabled_channels(self) -> List[int]:
        return [n + 1 for n in range(self.num_channels) if self.channel_rows[n]["enable"].isChecked()]

    @qasync.asyncSlot()
    async def _poll_trace(self):
        """Fetch one decimated waveform per enabled channel and redraw."""
        if self.equipment is None or self.client is None or not self.is_connected():
            self.trace_timer.stop()
            return
        from client.utils.inflight import (READINGS_ABANDONED_AFTER, claim_slot,
                                           release_slot)

        if not claim_slot(self, "_trace_started_at", READINGS_ABANDONED_AFTER):
            return
        try:
            for channel in self.enabled_channels():
                trace = await self.send(
                    "get_waveform_data", {"channel": channel, "points": self.TRACE_POINTS}
                )
                if isinstance(trace, dict) and trace.get("voltage") is not None:
                    self._last_trace[channel] = trace
            self._redraw_trace()
        except RuntimeError as e:
            if "unknown command" in str(e).lower():
                # This driver has no waveform read-back. Ask once, not forever.
                self.trace_timer.stop()
                self._trace_unsupported = True
                self.trace_note.setText("This driver does not provide waveform data.")
            else:
                logger.error(f"Waveform fetch failed: {e}")
        except Exception as e:
            if self._equipment_is_gone(e) or self._readings_unsupported(e):
                self.trace_timer.stop()
                if self._readings_unsupported(e):
                    self._trace_unsupported = True
                    self.trace_note.setText("This instrument does not provide waveform data.")
            else:
                logger.error(f"Waveform fetch failed: {e}")
        finally:
            release_slot(self, "_trace_started_at")

    def _redraw_trace(self):
        """Put every fetched channel on the chart, axes from the returned preamble."""
        t_min, t_max = math.inf, -math.inf
        v_min, v_max = math.inf, -math.inf
        for n, series in enumerate(self.series):
            trace = self._last_trace.get(n + 1)
            if trace is None or n >= self.num_channels or not self.channel_rows[n]["enable"].isChecked():
                series.clear()
                series.setVisible(False)
                continue
            times = trace.get("time") or []
            volts = trace.get("voltage") or []
            if not times or not volts:
                x0 = float(trace.get("x_origin") or 0.0)
                dx = float(trace.get("x_increment") or 1e-6)
                times = [x0 + i * dx for i in range(len(volts))]
            points = [QPointF(float(t), float(v)) for t, v in zip(times, volts)
                      if v is not None and not math.isnan(float(v))]
            series.replace(points)
            series.setVisible(True)
            if points:
                t_min = min(t_min, points[0].x())
                t_max = max(t_max, points[-1].x())
                v_min = min(v_min, min(p.y() for p in points))
                v_max = max(v_max, max(p.y() for p in points))
        if math.isfinite(t_min) and t_max > t_min:
            self.axis_x.setRange(t_min, t_max)
        if math.isfinite(v_min):
            # Prefer the screen the scope itself shows: ±4 divisions of the
            # largest enabled scale, so the trace sits where it does on the
            # instrument; fall back to the data when a scale is unknown.
            scales = []
            for ch in self.enabled_channels():
                trace = self._last_trace.get(ch)
                if trace and trace.get("voltage_scale"):
                    scales.append(float(trace["voltage_scale"]))
            if scales:
                span = 4.0 * max(scales)
                self.axis_y.setRange(-span, span)
            else:
                pad = max((v_max - v_min) * 0.1, 1e-3)
                self.axis_y.setRange(v_min - pad, v_max + pad)

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #

    def _command(self, name: str, parameters: Optional[Dict[str, Any]] = None):
        self._send_command(name, parameters or {})

    @qasync.asyncSlot(str, dict)
    async def _send_command(self, name: str, parameters: dict):
        try:
            result = await self.send(name, parameters)
            if name in ("trigger_run", "trigger_stop", "trigger_single", "force_trigger"):
                self.trigger_status.setText(
                    {"trigger_run": "RUN", "trigger_stop": "STOP", "trigger_single": "SINGLE",
                     "force_trigger": "FORCED"}[name]
                )
            return result
        except Exception as e:
            logger.error(f"{name} failed: {e}")
            self.status_message.emit(f"{name.replace('_', ' ')} failed: {e}")

    def _apply_channel(self, channel: int):
        row = self.channel_rows[channel - 1]
        self._command("set_channel", {
            "channel": channel,
            "enabled": row["enable"].isChecked(),
            "scale": float(row["scale"].currentData()),
            "offset": float(row["offset"].value()),
            "coupling": row["coupling"].currentText(),
        })

    def _on_channel_enabled(self, channel: int, checked: bool):
        self.series[channel - 1].setVisible(checked)
        if not checked:
            self._last_trace.pop(channel, None)
            self.series[channel - 1].clear()

    def _apply_timebase(self):
        self._command("set_timebase", {
            "scale": float(self.timebase_scale.currentData()),
            "offset": float(self.timebase_offset.value()),
        })

    def _apply_trigger(self):
        self._command("set_trigger", {
            "source": self.trigger_source.currentData(),
            "level": float(self.trigger_level.value()),
            "slope": self.trigger_slope.currentData(),
            "sweep": self.trigger_sweep.currentData(),
        })

    def _on_measure_channel_changed(self, _index: int):
        self._clear_measurements()
