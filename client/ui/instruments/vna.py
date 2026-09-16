"""The vector-network-analyzer panel: stimulus, S-parameter, format, trace.

One trace at a time, drawn against the stimulus frequencies the instrument
reports. The Stimulus group sends one ``set_sweep`` (start, stop, points,
power, IF bandwidth); Parameter and Format command immediately; the marker
and calibration groups have their own buttons. Formats with two values per
point (real/imaginary, Smith) draw the primary value and say so.

Commands (RSA-N and DNA6000 drivers share them): ``set_sweep``,
``set_parameter``, ``set_format``, ``set_marker``, ``get_marker``,
``calibrate_start`` / ``calibrate_acquire`` / ``calibrate_save`` /
``calibrate_abort``, ``set_correction``, ``get_trace``, ``get_state``.
"""

import logging
import math
from typing import Any, Dict, List, Optional

import qasync
from PyQt6.QtCharts import QChart, QLineSeries, QValueAxis
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QGridLayout,
                             QGroupBox, QHBoxLayout, QLabel, QPushButton,
                             QSizePolicy, QSpinBox, QVBoxLayout, QWidget)

from client.ui.instruments.base import POLL_MEASUREMENTS, InstrumentPanel
from client.ui.instruments.widgets import ChartWithReadouts
from client.ui.theme import dialog_palette, get_theme_setting

logger = logging.getLogger(__name__)

FORMAT_LABELS = {"MLOG": "Log magnitude (dB)", "MLIN": "Linear magnitude", "PHAS": "Phase (°)",
                 "SWR": "SWR", "SMIT": "Smith", "REAL": "Real", "IMAG": "Imaginary",
                 "GDEL": "Group delay (s)", "UPH": "Unwrapped phase", "PPH": "Positive phase"}
CAL_STANDARDS = ["OPEN", "SHORT", "LOAD", "THRU"]


def format_frequency(hz: Optional[float]) -> str:
    if hz is None or (isinstance(hz, float) and math.isnan(hz)):
        return "--"
    for factor, unit in ((1e9, "GHz"), (1e6, "MHz"), (1e3, "kHz"), (1.0, "Hz")):
        if abs(hz) >= factor or factor == 1.0:
            return f"{hz / factor:.6g} {unit}"
    return f"{hz:g} Hz"


class VNAPanel(InstrumentPanel):
    """Drive a vector network analyzer and watch one trace."""

    POLLS = POLL_MEASUREMENTS
    DEFAULT_INTERVAL_MS = 1000
    SETTINGS_TYPE = "vector_network_analyzer"

    def __init__(self, parent=None):
        self.parameters: List[str] = ["S11", "S21", "S12", "S22"]
        self.formats: List[str] = ["MLOG", "PHAS", "SWR", "MLIN", "REAL", "IMAG", "GDEL"]
        self.calibration_methods: List[str] = ["SOL", "SOLT", "RESPONSE"]
        self.power_min, self.power_max = -40.0, 10.0
        self._last_trace: Optional[Dict[str, Any]] = None
        super().__init__(parent)

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        left = QVBoxLayout()
        left.addWidget(self._create_trace(), 1)
        left.addWidget(self._create_marker_controls())
        outer.addLayout(left, 3)
        right = QVBoxLayout()
        right.addWidget(self._create_stimulus_controls())
        right.addWidget(self._create_measurement_controls())
        right.addWidget(self._create_calibration_controls())
        right.addWidget(self._create_rate_control("How often to fetch the trace"))
        right.addStretch()
        outer.addLayout(right, 2)

    def _create_trace(self) -> QWidget:
        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.chart = QChart()
        self.chart.setTitle("S21  Log magnitude")
        self.chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        self.chart.setTheme(QChart.ChartTheme.ChartThemeDark if get_theme_setting() == "dark"
                            else QChart.ChartTheme.ChartThemeLight)
        self.axis_x = QValueAxis()
        self.axis_x.setTitleText("Frequency (Hz)")
        self.axis_x.setLabelFormat("%.4g")
        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
        self.axis_y = QValueAxis()
        self.axis_y.setTitleText("dB")
        self.axis_y.setRange(-80.0, 10.0)
        self.chart.addAxis(self.axis_y, Qt.AlignmentFlag.AlignLeft)
        self.series = QLineSeries()
        self.series.setName("Trace 1")
        self.series.setPen(QPen(QColor("#00FCF8"), 1.4))
        self.chart.addSeries(self.series)
        self.series.attachAxis(self.axis_x)
        self.series.attachAxis(self.axis_y)
        _c = dialog_palette()
        self.chart.setTitleBrush(QColor(_c["text"]))
        if self.chart.legend():
            self.chart.legend().setLabelColor(QColor(_c["text"]))
        for axis in (self.axis_x, self.axis_y):
            axis.setLabelsColor(QColor(_c["text"]))
            axis.setTitleBrush(QColor(_c["text"]))
        self.chart_view = ChartWithReadouts(self.chart)
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.chart_view.voltage_readout.hide()
        self.chart_view.current_readout.hide()
        layout.addWidget(self.chart_view)
        self.trace_note = QLabel("")
        layout.addWidget(self.trace_note)
        return widget

    def _create_stimulus_controls(self) -> QGroupBox:
        group = QGroupBox("Stimulus")
        grid = QGridLayout(group)
        grid.addWidget(QLabel("Start (MHz):"), 0, 0)
        self.start_spin = QDoubleSpinBox()
        self.start_spin.setRange(0.0, 1e6)
        self.start_spin.setDecimals(6)
        self.start_spin.setValue(1.0)
        grid.addWidget(self.start_spin, 0, 1)
        grid.addWidget(QLabel("Stop (MHz):"), 1, 0)
        self.stop_spin = QDoubleSpinBox()
        self.stop_spin.setRange(0.0, 1e6)
        self.stop_spin.setDecimals(6)
        self.stop_spin.setValue(1000.0)
        grid.addWidget(self.stop_spin, 1, 1)
        grid.addWidget(QLabel("Points:"), 2, 0)
        self.points_spin = QSpinBox()
        self.points_spin.setRange(2, 100001)
        self.points_spin.setValue(201)
        grid.addWidget(self.points_spin, 2, 1)
        grid.addWidget(QLabel("Power (dBm):"), 3, 0)
        self.power_spin = QDoubleSpinBox()
        self.power_spin.setRange(self.power_min, self.power_max)
        self.power_spin.setDecimals(1)
        self.power_spin.setValue(0.0)
        grid.addWidget(self.power_spin, 3, 1)
        grid.addWidget(QLabel("IF BW (Hz):"), 4, 0)
        self.ifbw_combo = QComboBox()
        for bw in (10, 30, 100, 300, 1e3, 3e3, 10e3, 30e3, 100e3):
            self.ifbw_combo.addItem(format_frequency(bw), float(bw))
        self.ifbw_combo.setCurrentIndex(4)
        grid.addWidget(self.ifbw_combo, 4, 1)
        self.stimulus_apply = QPushButton("Apply stimulus")
        self.stimulus_apply.clicked.connect(self._apply_stimulus)
        grid.addWidget(self.stimulus_apply, 5, 0, 1, 2)
        return group

    def _create_measurement_controls(self) -> QGroupBox:
        group = QGroupBox("Measurement (trace 1)")
        grid = QGridLayout(group)
        grid.addWidget(QLabel("Parameter:"), 0, 0)
        self.parameter_combo = QComboBox()
        self._fill_parameters()
        self.parameter_combo.currentIndexChanged.connect(
            lambda _i: self._command("set_parameter", {"trace": 1, "s_param": self.parameter_combo.currentData()}))
        grid.addWidget(self.parameter_combo, 0, 1)
        grid.addWidget(QLabel("Format:"), 1, 0)
        self.format_combo = QComboBox()
        self._fill_formats()
        self.format_combo.currentIndexChanged.connect(
            lambda _i: self._command("set_format", {"trace": 1, "fmt": self.format_combo.currentData()}))
        grid.addWidget(self.format_combo, 1, 1)
        self.continuous_button = QPushButton("Continuous")
        self.continuous_button.clicked.connect(lambda: self._command("set_continuous", {"enabled": True}))
        grid.addWidget(self.continuous_button, 2, 0)
        self.single_button = QPushButton("Single")
        self.single_button.clicked.connect(lambda: self._command("sweep_single", {}))
        grid.addWidget(self.single_button, 2, 1)
        return group

    def _create_marker_controls(self) -> QGroupBox:
        group = QGroupBox("Marker 1")
        row = QHBoxLayout(group)
        row.addWidget(QLabel("Frequency (MHz):"))
        self.marker_frequency_spin = QDoubleSpinBox()
        self.marker_frequency_spin.setRange(0.0, 1e6)
        self.marker_frequency_spin.setDecimals(6)
        self.marker_frequency_spin.setValue(100.0)
        row.addWidget(self.marker_frequency_spin)
        self.marker_set_button = QPushButton("Set")
        self.marker_set_button.clicked.connect(self._apply_marker)
        row.addWidget(self.marker_set_button)
        self.marker_label = QLabel("M1: --")
        row.addWidget(self.marker_label, 1)
        return group

    def _create_calibration_controls(self) -> QGroupBox:
        group = QGroupBox("Calibration")
        grid = QGridLayout(group)
        grid.addWidget(QLabel("Method:"), 0, 0)
        self.cal_method_combo = QComboBox()
        self._fill_cal_methods()
        grid.addWidget(self.cal_method_combo, 0, 1)
        self.cal_start_button = QPushButton("Start")
        self.cal_start_button.clicked.connect(
            lambda: self._command("calibrate_start", {"method": self.cal_method_combo.currentData()}))
        grid.addWidget(self.cal_start_button, 0, 2)
        grid.addWidget(QLabel("Standard:"), 1, 0)
        self.cal_standard_combo = QComboBox()
        for s in CAL_STANDARDS:
            self.cal_standard_combo.addItem(s.title(), s)
        grid.addWidget(self.cal_standard_combo, 1, 1)
        self.cal_acquire_button = QPushButton("Acquire")
        self.cal_acquire_button.clicked.connect(
            lambda: self._command("calibrate_acquire", {"standard": self.cal_standard_combo.currentData()}))
        grid.addWidget(self.cal_acquire_button, 1, 2)
        self.cal_save_button = QPushButton("Save")
        self.cal_save_button.clicked.connect(lambda: self._command("calibrate_save", {}))
        grid.addWidget(self.cal_save_button, 2, 1)
        self.cal_abort_button = QPushButton("Abort")
        self.cal_abort_button.clicked.connect(lambda: self._command("calibrate_abort", {}))
        grid.addWidget(self.cal_abort_button, 2, 2)
        self.correction_check = QCheckBox("Correction on")
        self.correction_check.toggled.connect(lambda on: self._command("set_correction", {"enabled": bool(on)}))
        grid.addWidget(self.correction_check, 2, 0)
        return group

    def _fill_parameters(self):
        self.parameter_combo.blockSignals(True)
        self.parameter_combo.clear()
        for p in self.parameters:
            self.parameter_combo.addItem(p, p)
        self.parameter_combo.blockSignals(False)

    def _fill_formats(self):
        self.format_combo.blockSignals(True)
        self.format_combo.clear()
        for f in self.formats:
            key = str(f).upper()[:4]
            self.format_combo.addItem(FORMAT_LABELS.get(key, f), str(f).upper())
        self.format_combo.blockSignals(False)

    def _fill_cal_methods(self):
        self.cal_method_combo.blockSignals(True)
        self.cal_method_combo.clear()
        for m in self.calibration_methods:
            self.cal_method_combo.addItem(str(m), str(m))
        self.cal_method_combo.blockSignals(False)

    # ------------------------------------------------------------------ #
    # Contract
    # ------------------------------------------------------------------ #

    def configure(self, capabilities: Dict[str, Any]):
        if capabilities.get("parameters"):
            self.parameters = [str(p).upper() for p in capabilities["parameters"]]
            self._fill_parameters()
        if capabilities.get("formats"):
            self.formats = [str(f).upper() for f in capabilities["formats"]]
            self._fill_formats()
        if capabilities.get("calibration_methods"):
            self.calibration_methods = [str(m) for m in capabilities["calibration_methods"]]
            self._fill_cal_methods()
        if capabilities.get("power_min_dbm") is not None and capabilities.get("power_max_dbm") is not None:
            self.power_min = float(capabilities["power_min_dbm"])
            self.power_max = float(capabilities["power_max_dbm"])
            self.power_spin.setRange(self.power_min, self.power_max)
        if capabilities.get("max_points"):
            self.points_spin.setMaximum(int(capabilities["max_points"]))
        self.series.clear()
    async def refresh_settings(self):
        if not (self.client and self.equipment):
            return
        state = await self.send("get_state", {}, priority=False)
        if not isinstance(state, dict):
            return
        widgets = (self.start_spin, self.stop_spin, self.points_spin, self.parameter_combo,
                   self.format_combo, self.correction_check)
        for w in widgets:
            w.blockSignals(True)
        try:
            sweep = state.get("sweep") or {}
            if sweep.get("start_frequency") is not None:
                self.start_spin.setValue(float(sweep["start_frequency"]) / 1e6)
            if sweep.get("stop_frequency") is not None:
                self.stop_spin.setValue(float(sweep["stop_frequency"]) / 1e6)
            if sweep.get("points"):
                self.points_spin.setValue(int(sweep["points"]))
            if state.get("parameter"):
                idx = self.parameter_combo.findData(str(state["parameter"]).upper())
                if idx >= 0:
                    self.parameter_combo.setCurrentIndex(idx)
            if state.get("format"):
                fmt = str(state["format"]).upper()
                idx = self.format_combo.findData(fmt)
                if idx < 0:
                    idx = next((i for i in range(self.format_combo.count())
                                if str(self.format_combo.itemData(i)).startswith(fmt[:4])), -1)
                if idx >= 0:
                    self.format_combo.setCurrentIndex(idx)
            if state.get("correction") is not None:
                self.correction_check.setChecked(bool(state["correction"]))
        finally:
            for w in widgets:
                w.blockSignals(False)

    def set_controls_enabled(self, enabled: bool):
        for w in (self.start_spin, self.stop_spin, self.points_spin, self.power_spin, self.ifbw_combo,
                  self.stimulus_apply, self.parameter_combo, self.format_combo, self.continuous_button,
                  self.single_button, self.marker_frequency_spin, self.marker_set_button,
                  self.cal_method_combo, self.cal_start_button, self.cal_standard_combo,
                  self.cal_acquire_button, self.cal_save_button, self.cal_abort_button, self.correction_check):
            w.setEnabled(enabled)

    def show_not_connected(self):
        self.series.clear()
        self.status_message.emit("Not connected. Connect it on the Equipment tab to read it.")

    def show_unsupported(self):
        self.series.clear()
        name = getattr(self.equipment, "name", "This instrument")
        self.status_message.emit(f"{name} does not provide trace data.")

    def clear_instrument(self):
        self.series.clear()
        self.marker_label.setText("M1: --")
        self.trace_note.setText("")

    # ------------------------------------------------------------------ #
    # Polling
    # ------------------------------------------------------------------ #

    async def poll(self):
        trace = await self.send("get_trace", {"trace": 1})
        if isinstance(trace, dict):
            self._show_trace(trace)

    def _show_trace(self, trace: Dict[str, Any]):
        self._last_trace = trace
        freqs = trace.get("frequencies") or []
        values = trace.get("values") or []
        if not freqs and values and trace.get("start_frequency") is not None and trace.get("stop_frequency") is not None:
            n = len(values)
            start, stop = float(trace["start_frequency"]), float(trace["stop_frequency"])
            step = (stop - start) / (n - 1) if n > 1 else 0.0
            freqs = [start + i * step for i in range(n)]
        points = [QPointF(float(f), float(v)) for f, v in zip(freqs, values)
                  if v is not None and not (isinstance(v, float) and math.isnan(v))]
        self.series.replace(points)
        if points:
            self.axis_x.setRange(points[0].x(), points[-1].x())
            lo = min(p.y() for p in points)
            hi = max(p.y() for p in points)
            pad = max((hi - lo) * 0.1, 1e-3)
            self.axis_y.setRange(lo - pad, hi + pad)
        fmt = str(trace.get("format") or "").upper()
        unit = trace.get("unit") or ""
        self.axis_y.setTitleText(unit or FORMAT_LABELS.get(fmt[:4], fmt))
        self.chart.setTitle(f"{trace.get('parameter') or ''}  {FORMAT_LABELS.get(fmt[:4], fmt)}".strip())
        if trace.get("secondary_values"):
            self.trace_note.setText("Two values per point in this format; the primary is drawn.")
        else:
            self.trace_note.setText("")

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #

    def _command(self, name: str, parameters: Optional[Dict[str, Any]] = None):
        self._send_command(name, parameters or {})

    @qasync.asyncSlot(str, dict)
    async def _send_command(self, name: str, parameters: dict):
        try:
            result = await self.send(name, parameters)
            if name in ("set_marker", "get_marker") and isinstance(result, dict):
                self._show_marker(result)
            return result
        except Exception as e:
            logger.error(f"{name} failed: {e}")
            self.status_message.emit(f"{name.replace('_', ' ')} failed: {e}")

    def _show_marker(self, marker: Dict[str, Any]):
        freq = marker.get("frequency")
        value = marker.get("value", marker.get("y"))
        if freq is None:
            return
        text = f"M1: {format_frequency(float(freq))}"
        if value is not None:
            try:
                text += f"  {float(value):.3f}"
            except (TypeError, ValueError):
                text += f"  {value}"
        self.marker_label.setText(text)

    def _apply_stimulus(self):
        self._command("set_sweep", {
            "start": float(self.start_spin.value()) * 1e6,
            "stop": float(self.stop_spin.value()) * 1e6,
            "points": int(self.points_spin.value()),
            "power": float(self.power_spin.value()),
            "if_bandwidth": float(self.ifbw_combo.currentData()),
        })

    def _apply_marker(self):
        self._command("set_marker", {"marker": 1, "frequency": float(self.marker_frequency_spin.value()) * 1e6, "trace": 1})
