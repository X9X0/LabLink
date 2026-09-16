"""The spectrum-analyzer panel: frequency, bandwidth, amplitude, markers, trace.

The trace *is* the reading, so it is what the panel polls (``get_trace``,
one trace per tick, drawn against the start/stop it came with). Around it
are the analyzer's own groups -- Frequency, Bandwidth, Amplitude, Sweep,
Trace, Marker, and the tracking generator where the model has one -- each
sending the driver command that group is named for.

Commands (DSA and RSA families share them): ``set_frequency``,
``set_start_stop``, ``set_rbw``, ``set_vbw``, ``set_reference_level``,
``set_attenuation``, ``set_preamp``, ``set_detector``, ``set_trace_mode``,
``set_sweep``, ``set_continuous``, ``single_sweep``, ``peak_search``,
``next_peak``, ``marker_to_center``, ``set_marker``, ``set_tracking_generator``,
``set_mode``, ``get_trace``.
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

BANDWIDTHS = [1, 3, 10, 30, 100, 300, 1e3, 3e3, 10e3, 30e3, 100e3, 300e3, 1e6, 3e6, 10e6]


def format_frequency(hz: Optional[float]) -> str:
    if hz is None or (isinstance(hz, float) and math.isnan(hz)):
        return "--"
    for factor, unit in ((1e9, "GHz"), (1e6, "MHz"), (1e3, "kHz"), (1.0, "Hz")):
        if abs(hz) >= factor or factor == 1.0:
            return f"{hz / factor:.6g} {unit}"
    return f"{hz:g} Hz"


class SpectrumAnalyzerPanel(InstrumentPanel):
    """Drive a spectrum analyzer and watch its trace."""

    POLLS = POLL_MEASUREMENTS
    DEFAULT_INTERVAL_MS = 1000
    SETTINGS_TYPE = "spectrum_analyzer"

    def __init__(self, parent=None):
        self.frequency_min = 0.0
        self.frequency_max = 1.5e9
        self.has_tracking_generator = False
        self.supports_mode_select = False
        self.detectors: List[str] = ["POS", "NEG", "SAMP", "NORM", "RMS", "AVER"]
        self.trace_modes: List[str] = ["WRITE", "MAXHOLD", "MINHOLD", "VIEW", "BLANK", "AVERAGE"]
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
        right.addWidget(self._create_frequency_controls())
        right.addWidget(self._create_bandwidth_controls())
        right.addWidget(self._create_amplitude_controls())
        right.addWidget(self._create_sweep_controls())
        right.addWidget(self._create_tg_controls())
        right.addWidget(self._create_rate_control("How often to fetch the trace"))
        right.addStretch()
        outer.addLayout(right, 2)

    def _create_trace(self) -> QWidget:
        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.chart = QChart()
        self.chart.setTitle("Spectrum")
        self.chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        self.chart.setTheme(QChart.ChartTheme.ChartThemeDark if get_theme_setting() == "dark"
                            else QChart.ChartTheme.ChartThemeLight)
        self.axis_x = QValueAxis()
        self.axis_x.setTitleText("Frequency (Hz)")
        self.axis_x.setLabelFormat("%.4g")
        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
        self.axis_y = QValueAxis()
        self.axis_y.setTitleText("Amplitude (dBm)")
        self.axis_y.setRange(-100.0, 0.0)
        self.chart.addAxis(self.axis_y, Qt.AlignmentFlag.AlignLeft)
        self.series = QLineSeries()
        self.series.setName("Trace 1")
        self.series.setPen(QPen(QColor("#F8FC00"), 1.2))
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
        self.peak_label = QLabel("Peak: --")
        layout.addWidget(self.peak_label)
        return widget

    def _create_frequency_controls(self) -> QGroupBox:
        group = QGroupBox("Frequency")
        grid = QGridLayout(group)
        grid.addWidget(QLabel("Center (MHz):"), 0, 0)
        self.center_spin = QDoubleSpinBox()
        self.center_spin.setRange(0.0, 1e6)
        self.center_spin.setDecimals(6)
        self.center_spin.setValue(100.0)
        grid.addWidget(self.center_spin, 0, 1)
        grid.addWidget(QLabel("Span (MHz):"), 1, 0)
        self.span_spin = QDoubleSpinBox()
        self.span_spin.setRange(0.0, 1e6)
        self.span_spin.setDecimals(6)
        self.span_spin.setValue(10.0)
        grid.addWidget(self.span_spin, 1, 1)
        self.frequency_apply = QPushButton("Set center/span")
        self.frequency_apply.clicked.connect(self._apply_center_span)
        grid.addWidget(self.frequency_apply, 0, 2, 2, 1)
        grid.addWidget(QLabel("Start (MHz):"), 2, 0)
        self.start_spin = QDoubleSpinBox()
        self.start_spin.setRange(0.0, 1e6)
        self.start_spin.setDecimals(6)
        self.start_spin.setValue(95.0)
        grid.addWidget(self.start_spin, 2, 1)
        grid.addWidget(QLabel("Stop (MHz):"), 3, 0)
        self.stop_spin = QDoubleSpinBox()
        self.stop_spin.setRange(0.0, 1e6)
        self.stop_spin.setDecimals(6)
        self.stop_spin.setValue(105.0)
        grid.addWidget(self.stop_spin, 3, 1)
        self.start_stop_apply = QPushButton("Set start/stop")
        self.start_stop_apply.clicked.connect(self._apply_start_stop)
        grid.addWidget(self.start_stop_apply, 2, 2, 2, 1)
        self.full_span_button = QPushButton("Full span")
        self.full_span_button.clicked.connect(lambda: self._command("set_full_span", {}))
        grid.addWidget(self.full_span_button, 4, 2)
        return group

    def _create_bandwidth_controls(self) -> QGroupBox:
        group = QGroupBox("Bandwidth")
        grid = QGridLayout(group)
        grid.addWidget(QLabel("RBW:"), 0, 0)
        self.rbw_combo = QComboBox()
        self.rbw_combo.addItem("Auto", "AUTO")
        for bw in BANDWIDTHS:
            self.rbw_combo.addItem(format_frequency(bw), float(bw))
        self.rbw_combo.currentIndexChanged.connect(lambda _i: self._apply_bandwidth("set_rbw", "rbw", self.rbw_combo))
        grid.addWidget(self.rbw_combo, 0, 1)
        grid.addWidget(QLabel("VBW:"), 1, 0)
        self.vbw_combo = QComboBox()
        self.vbw_combo.addItem("Auto", "AUTO")
        for bw in BANDWIDTHS:
            self.vbw_combo.addItem(format_frequency(bw), float(bw))
        self.vbw_combo.currentIndexChanged.connect(lambda _i: self._apply_bandwidth("set_vbw", "vbw", self.vbw_combo))
        grid.addWidget(self.vbw_combo, 1, 1)
        grid.addWidget(QLabel("Detector:"), 2, 0)
        self.detector_combo = QComboBox()
        self._fill_detectors()
        self.detector_combo.currentIndexChanged.connect(
            lambda _i: self._command("set_detector", {"detector": self.detector_combo.currentData(), "trace": 1}))
        grid.addWidget(self.detector_combo, 2, 1)
        return group

    def _create_amplitude_controls(self) -> QGroupBox:
        group = QGroupBox("Amplitude")
        grid = QGridLayout(group)
        grid.addWidget(QLabel("Ref level (dBm):"), 0, 0)
        self.ref_level_spin = QDoubleSpinBox()
        self.ref_level_spin.setRange(-150.0, 50.0)
        self.ref_level_spin.setDecimals(1)
        self.ref_level_spin.setValue(0.0)
        grid.addWidget(self.ref_level_spin, 0, 1)
        self.ref_level_apply = QPushButton("Set")
        self.ref_level_apply.clicked.connect(
            lambda: self._command("set_reference_level", {"level": float(self.ref_level_spin.value())}))
        grid.addWidget(self.ref_level_apply, 0, 2)
        grid.addWidget(QLabel("Attenuation (dB):"), 1, 0)
        self.attenuation_spin = QSpinBox()
        self.attenuation_spin.setRange(0, 70)
        self.attenuation_spin.setValue(10)
        grid.addWidget(self.attenuation_spin, 1, 1)
        self.attenuation_auto = QCheckBox("Auto")
        self.attenuation_auto.setChecked(True)
        grid.addWidget(self.attenuation_auto, 1, 2)
        self.attenuation_apply = QPushButton("Set")
        self.attenuation_apply.clicked.connect(self._apply_attenuation)
        grid.addWidget(self.attenuation_apply, 1, 3)
        self.preamp_check = QCheckBox("Preamp")
        self.preamp_check.toggled.connect(lambda on: self._command("set_preamp", {"enabled": bool(on)}))
        grid.addWidget(self.preamp_check, 2, 0, 1, 2)
        return group

    def _create_sweep_controls(self) -> QGroupBox:
        group = QGroupBox("Sweep / Trace")
        grid = QGridLayout(group)
        self.continuous_button = QPushButton("Continuous")
        self.continuous_button.clicked.connect(lambda: self._command("set_continuous", {"enabled": True}))
        grid.addWidget(self.continuous_button, 0, 0)
        self.single_button = QPushButton("Single")
        self.single_button.clicked.connect(lambda: self._command("single_sweep", {}))
        grid.addWidget(self.single_button, 0, 1)
        grid.addWidget(QLabel("Trace mode:"), 1, 0)
        self.trace_mode_combo = QComboBox()
        self._fill_trace_modes()
        self.trace_mode_combo.currentIndexChanged.connect(
            lambda _i: self._command("set_trace_mode", {"trace": 1, "mode": self.trace_mode_combo.currentData()}))
        grid.addWidget(self.trace_mode_combo, 1, 1)
        grid.addWidget(QLabel("Mode:"), 2, 0)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Swept (GPSA)", "GPSA")
        self.mode_combo.addItem("Real-time (RTSA)", "RTSA")
        self.mode_combo.currentIndexChanged.connect(
            lambda _i: self._command("set_mode", {"mode": self.mode_combo.currentData()}))
        grid.addWidget(self.mode_combo, 2, 1)
        return group

    def _create_marker_controls(self) -> QGroupBox:
        group = QGroupBox("Marker 1")
        row = QHBoxLayout(group)
        self.peak_button = QPushButton("Peak search")
        self.peak_button.clicked.connect(lambda: self._marker_command("peak_search", {"marker": 1}))
        row.addWidget(self.peak_button)
        self.next_peak_button = QPushButton("Next peak")
        self.next_peak_button.clicked.connect(lambda: self._marker_command("next_peak", {"marker": 1, "direction": "NEXT"}))
        row.addWidget(self.next_peak_button)
        self.marker_to_center_button = QPushButton("Marker → center")
        self.marker_to_center_button.clicked.connect(lambda: self._command("marker_to_center", {"marker": 1}))
        row.addWidget(self.marker_to_center_button)
        row.addWidget(QLabel("at (MHz):"))
        self.marker_frequency_spin = QDoubleSpinBox()
        self.marker_frequency_spin.setRange(0.0, 1e6)
        self.marker_frequency_spin.setDecimals(6)
        row.addWidget(self.marker_frequency_spin)
        self.marker_set_button = QPushButton("Set")
        self.marker_set_button.clicked.connect(
            lambda: self._marker_command("set_marker", {"marker": 1, "frequency": float(self.marker_frequency_spin.value()) * 1e6}))
        row.addWidget(self.marker_set_button)
        self.marker_label = QLabel("M1: --")
        row.addWidget(self.marker_label, 1)
        return group

    def _create_tg_controls(self) -> QGroupBox:
        self.tg_group = QGroupBox("Tracking generator")
        row = QHBoxLayout(self.tg_group)
        self.tg_enable = QCheckBox("On")
        row.addWidget(self.tg_enable)
        row.addWidget(QLabel("Level (dBm):"))
        self.tg_level = QDoubleSpinBox()
        self.tg_level.setRange(-40.0, 0.0)
        self.tg_level.setDecimals(1)
        self.tg_level.setValue(-20.0)
        row.addWidget(self.tg_level)
        self.tg_apply = QPushButton("Apply")
        self.tg_apply.clicked.connect(
            lambda: self._command("set_tracking_generator", {"enabled": self.tg_enable.isChecked(), "level": float(self.tg_level.value())}))
        row.addWidget(self.tg_apply)
        self.tg_group.setVisible(False)
        return self.tg_group

    def _fill_detectors(self):
        self.detector_combo.blockSignals(True)
        self.detector_combo.clear()
        for d in self.detectors:
            self.detector_combo.addItem(str(d).title(), str(d).upper())
        self.detector_combo.blockSignals(False)

    def _fill_trace_modes(self):
        self.trace_mode_combo.blockSignals(True)
        self.trace_mode_combo.clear()
        for m in self.trace_modes:
            self.trace_mode_combo.addItem(str(m).title(), str(m).upper())
        self.trace_mode_combo.blockSignals(False)

    # ------------------------------------------------------------------ #
    # Contract
    # ------------------------------------------------------------------ #

    def configure(self, capabilities: Dict[str, Any]):
        self.frequency_min = float(capabilities.get("frequency_min") or 0.0)
        self.frequency_max = float(capabilities.get("frequency_max") or self.frequency_max)
        self.has_tracking_generator = bool(capabilities.get("has_tracking_generator"))
        self.supports_mode_select = bool(capabilities.get("supports_rtsa") or capabilities.get("supports_mode_select"))
        if capabilities.get("detectors"):
            self.detectors = [str(d).upper() for d in capabilities["detectors"]]
            self._fill_detectors()
        if capabilities.get("trace_modes"):
            self.trace_modes = [str(m).upper() for m in capabilities["trace_modes"]]
            self._fill_trace_modes()
        self.tg_group.setVisible(self.has_tracking_generator)
        self.mode_combo.setEnabled(self.supports_mode_select)
        self.preamp_check.setEnabled(bool(capabilities.get("has_preamp", True)))
        self.series.clear()
        self._last_trace = None
    async def refresh_settings(self):
        if not (self.client and self.equipment):
            return
        state = await self.send("get_state", {}, priority=False)
        if not isinstance(state, dict):
            return
        widgets = (self.center_spin, self.span_spin, self.start_spin, self.stop_spin, self.rbw_combo,
                   self.vbw_combo, self.ref_level_spin, self.attenuation_spin, self.attenuation_auto,
                   self.detector_combo, self.mode_combo, self.tg_enable, self.tg_level, self.preamp_check)
        for w in widgets:
            w.blockSignals(True)
        try:
            freq = state.get("frequency") or {}
            if freq.get("center") is not None:
                self.center_spin.setValue(float(freq["center"]) / 1e6)
            if freq.get("span") is not None:
                self.span_spin.setValue(float(freq["span"]) / 1e6)
            if freq.get("start") is not None:
                self.start_spin.setValue(float(freq["start"]) / 1e6)
            if freq.get("stop") is not None:
                self.stop_spin.setValue(float(freq["stop"]) / 1e6)
            bw = state.get("bandwidth") or {}
            for key, combo in (("rbw", self.rbw_combo), ("vbw", self.vbw_combo)):
                if bw.get(f"{key}_auto"):
                    combo.setCurrentIndex(0)
                elif bw.get(key) is not None:
                    idx = combo.findData(float(bw[key]))
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
            amp = state.get("amplitude") or {}
            if amp.get("reference_level") is not None:
                self.ref_level_spin.setValue(float(amp["reference_level"]))
            if amp.get("attenuation") is not None:
                self.attenuation_spin.setValue(int(float(amp["attenuation"])))
            if amp.get("attenuation_auto") is not None:
                self.attenuation_auto.setChecked(bool(amp["attenuation_auto"]))
            if amp.get("preamp") is not None:
                self.preamp_check.setChecked(bool(amp["preamp"]))
            det = state.get("detector")
            if isinstance(det, str):
                idx = self.detector_combo.findData(det.upper()[:4]) if self.detector_combo.findData(det.upper()) < 0 else self.detector_combo.findData(det.upper())
                if idx >= 0:
                    self.detector_combo.setCurrentIndex(idx)
            mode = state.get("mode")
            if isinstance(mode, str):
                idx = self.mode_combo.findData("RTSA" if "RT" in mode.upper() else "GPSA")
                if idx >= 0:
                    self.mode_combo.setCurrentIndex(idx)
            tg = state.get("tracking_generator") or {}
            if tg.get("enabled") is not None:
                self.tg_enable.setChecked(bool(tg["enabled"]))
            if tg.get("level") is not None:
                self.tg_level.setValue(float(tg["level"]))
        finally:
            for w in widgets:
                w.blockSignals(False)

    def set_controls_enabled(self, enabled: bool):
        for w in (self.center_spin, self.span_spin, self.frequency_apply, self.start_spin, self.stop_spin,
                  self.start_stop_apply, self.full_span_button, self.rbw_combo, self.vbw_combo,
                  self.detector_combo, self.ref_level_spin, self.ref_level_apply, self.attenuation_spin,
                  self.attenuation_auto, self.attenuation_apply, self.preamp_check, self.continuous_button,
                  self.single_button, self.trace_mode_combo, self.peak_button, self.next_peak_button,
                  self.marker_to_center_button, self.marker_frequency_spin, self.marker_set_button,
                  self.tg_enable, self.tg_level, self.tg_apply):
            w.setEnabled(enabled)
        self.mode_combo.setEnabled(enabled and self.supports_mode_select)

    def show_not_connected(self):
        self.series.clear()
        self.peak_label.setText("Peak: --")
        self.status_message.emit("Not connected. Connect it on the Equipment tab to read it.")

    def show_unsupported(self):
        self.series.clear()
        name = getattr(self.equipment, "name", "This instrument")
        self.status_message.emit(f"{name} does not provide trace data.")

    def clear_instrument(self):
        self.series.clear()
        self.peak_label.setText("Peak: --")
        self.marker_label.setText("M1: --")

    # ------------------------------------------------------------------ #
    # Polling
    # ------------------------------------------------------------------ #

    async def poll(self):
        trace = await self.send("get_trace", {"trace": 1})
        if isinstance(trace, dict):
            self._show_trace(trace)

    def _show_trace(self, trace: Dict[str, Any]):
        self._last_trace = trace
        values = trace.get("values") or []
        start = trace.get("start_frequency")
        stop = trace.get("stop_frequency")
        n = len(values)
        if n and start is not None and stop is not None:
            start, stop = float(start), float(stop)
            step = (stop - start) / (n - 1) if n > 1 else 0.0
            points = [QPointF(start + i * step, float(v)) for i, v in enumerate(values)
                      if v is not None and not (isinstance(v, float) and math.isnan(v))]
            self.series.replace(points)
            if stop > start:
                self.axis_x.setRange(start, stop)
            unit = trace.get("unit") or "dBm"
            self.axis_y.setTitleText(f"Amplitude ({unit})")
            ref = trace.get("reference_level")
            top = float(ref) if ref is not None else max(p.y() for p in points) + 10.0 if points else 0.0
            self.axis_y.setRange(top - 100.0, top)
            self.chart.setTitle(f"Spectrum  {format_frequency(start)} – {format_frequency(stop)}"
                                + (f"  RBW {format_frequency(float(trace['rbw']))}" if trace.get("rbw") else ""))
        pf, pa = trace.get("peak_frequency"), trace.get("peak_amplitude")
        if pf is not None and pa is not None:
            self.peak_label.setText(f"Peak: {format_frequency(float(pf))}  {float(pa):.2f} {trace.get('unit') or 'dBm'}")
        markers = trace.get("markers") or {}
        m1 = markers.get("1") or markers.get(1) or markers.get("M1")
        if isinstance(m1, dict) and m1.get("frequency") is not None:
            self.marker_label.setText(f"M1: {format_frequency(float(m1['frequency']))}  {float(m1.get('amplitude', float('nan'))):.2f}")

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

    def _marker_command(self, name: str, parameters: Dict[str, Any]):
        self._send_marker_command(name, parameters)

    @qasync.asyncSlot(str, dict)
    async def _send_marker_command(self, name: str, parameters: dict):
        try:
            result = await self.send(name, parameters)
            if isinstance(result, dict) and result.get("frequency") is not None:
                amp = result.get("amplitude")
                self.marker_label.setText(
                    f"M1: {format_frequency(float(result['frequency']))}"
                    + (f"  {float(amp):.2f}" if amp is not None else ""))
        except Exception as e:
            logger.error(f"{name} failed: {e}")
            self.status_message.emit(f"{name.replace('_', ' ')} failed: {e}")

    def _apply_center_span(self):
        self._command("set_frequency", {"center": float(self.center_spin.value()) * 1e6,
                                        "span": float(self.span_spin.value()) * 1e6})

    def _apply_start_stop(self):
        self._command("set_start_stop", {"start": float(self.start_spin.value()) * 1e6,
                                         "stop": float(self.stop_spin.value()) * 1e6})

    def _apply_bandwidth(self, command: str, field: str, combo: QComboBox):
        choice = combo.currentData()
        if choice == "AUTO":
            self._command(command, {field: "AUTO", "auto": True})
        elif choice is not None:
            self._command(command, {field: float(choice), "auto": False})

    def _apply_attenuation(self):
        if self.attenuation_auto.isChecked():
            self._command("set_attenuation", {"auto": True})
        else:
            self._command("set_attenuation", {"db": float(self.attenuation_spin.value()), "auto": False})
