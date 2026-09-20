"""The function-generator panel: waveform, frequency, amplitude, and the extras.

Per channel: shape, frequency, amplitude (in the channel's unit), offset,
phase and duty, applied together with one ``apply`` -- the way the front
panel's Apply key works -- plus the output switch and load setting. Sweep,
burst and modulation each have their own group and their own Apply. The
poll reads the channel's settings back (``get_readings``) so a change made at
the front panel shows up here, and reads the frequency counter where the
model has one.

Commands (Rigol DG classic and Pro platforms share them): ``apply``,
``set_duty_cycle``, ``set_output``, ``set_load``, ``set_sweep``, ``set_burst``,
``set_modulation``, ``sync_phase``, ``get_readings``, ``get_counter``.
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

DEFAULT_WAVEFORMS = ["SIN", "SQU", "RAMP", "PULS", "NOIS", "DC", "ARB"]
WAVEFORM_LABELS = {"SIN": "Sine", "SQU": "Square", "RAMP": "Ramp", "PULS": "Pulse",
                   "NOIS": "Noise", "DC": "DC", "ARB": "Arbitrary", "USER": "Arbitrary",
                   "HARM": "Harmonic", "TRI": "Triangle"}


def format_frequency(hz: Optional[float]) -> str:
    if hz is None or (isinstance(hz, float) and math.isnan(hz)):
        return "--"
    for factor, prefix in ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m")):
        if abs(hz) >= factor or factor == 1e-3:
            return f"{hz / factor:.6g} {prefix}Hz"
    return f"{hz:.6g} Hz"


class FunctionGeneratorPanel(InstrumentPanel):
    """Drive an arbitrary/function generator."""

    POLLS = POLL_STATE
    DEFAULT_INTERVAL_MS = 1000
    SETTINGS_TYPE = "function_generator"
    MAX_CHANNELS = 4

    def __init__(self, parent=None):
        self.num_channels = 2
        self.waveforms: List[str] = list(DEFAULT_WAVEFORMS)
        self.max_frequency: Dict[str, float] = {}
        self.max_amplitude_vpp = 20.0
        self._has_counter: Optional[bool] = None
        super().__init__(parent)

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        left = QVBoxLayout()
        face = QWidget()
        face.setObjectName("fgenPanel")
        face.setStyleSheet("QWidget#fgenPanel { background-color: black; border-radius: 6px; }")
        face_layout = QVBoxLayout(face)
        face_layout.setContentsMargins(12, 12, 12, 12)
        self.summary_display = FittedReadout("--")
        self.summary_display.MAX_POINT_SIZE = 64
        face_layout.addWidget(self.summary_display, 2)
        self.detail_display = FittedReadout("")
        self.detail_display.MAX_POINT_SIZE = 28
        face_layout.addWidget(self.detail_display, 1)
        self.counter_display = FittedReadout("")
        self.counter_display.MAX_POINT_SIZE = 28
        face_layout.addWidget(self.counter_display, 1)
        left.addWidget(face, 1)
        left.addWidget(self._create_basic_controls())
        outer.addLayout(left, 3)

        right = QVBoxLayout()
        right.addWidget(self._create_sweep_controls())
        right.addWidget(self._create_burst_controls())
        right.addWidget(self._create_modulation_controls())
        right.addWidget(self._create_rate_control("How often to read the generator's settings back"))
        right.addStretch()
        outer.addLayout(right, 2)

    def _create_basic_controls(self) -> QGroupBox:
        group = QGroupBox("Output")
        grid = QGridLayout(group)

        grid.addWidget(QLabel("Channel:"), 0, 0)
        self.channel_combo = QComboBox()
        self._fill_channels()
        self.channel_combo.currentIndexChanged.connect(self._on_channel_changed)
        grid.addWidget(self.channel_combo, 0, 1)

        self.output_button = QPushButton("Output: OFF")
        self.output_button.setCheckable(True)
        self.output_button.setStyleSheet("QPushButton:checked { background-color: green; color: white; }")
        self.output_button.clicked.connect(self._on_output_toggled)
        grid.addWidget(self.output_button, 0, 2)

        grid.addWidget(QLabel("Load:"), 0, 3)
        self.load_combo = QComboBox()
        self.load_combo.addItem("50 Ω", 50)
        self.load_combo.addItem("High Z", "INF")
        self.load_combo.currentIndexChanged.connect(self._on_load_chosen)
        grid.addWidget(self.load_combo, 0, 4)

        grid.addWidget(QLabel("Waveform:"), 1, 0)
        self.waveform_combo = QComboBox()
        self._fill_waveforms()
        self.waveform_combo.currentIndexChanged.connect(self._on_waveform_changed)
        grid.addWidget(self.waveform_combo, 1, 1)

        grid.addWidget(QLabel("Frequency (Hz):"), 1, 2)
        self.frequency_spin = QDoubleSpinBox()
        self.frequency_spin.setRange(1e-6, 1e9)
        self.frequency_spin.setDecimals(3)
        self.frequency_spin.setValue(1000.0)
        grid.addWidget(self.frequency_spin, 1, 3, 1, 2)

        grid.addWidget(QLabel("Amplitude:"), 2, 0)
        self.amplitude_spin = QDoubleSpinBox()
        self.amplitude_spin.setRange(0.0, 20.0)
        self.amplitude_spin.setDecimals(4)
        self.amplitude_spin.setValue(1.0)
        grid.addWidget(self.amplitude_spin, 2, 1)
        self.amplitude_unit = QComboBox()
        self.amplitude_unit.addItems(["VPP", "VRMS", "DBM"])
        grid.addWidget(self.amplitude_unit, 2, 2)

        grid.addWidget(QLabel("Offset (V):"), 2, 3)
        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(-10.0, 10.0)
        self.offset_spin.setDecimals(4)
        grid.addWidget(self.offset_spin, 2, 4)

        grid.addWidget(QLabel("Phase (°):"), 3, 0)
        self.phase_spin = QDoubleSpinBox()
        self.phase_spin.setRange(0.0, 360.0)
        self.phase_spin.setDecimals(2)
        grid.addWidget(self.phase_spin, 3, 1)

        grid.addWidget(QLabel("Duty (%):"), 3, 2)
        self.duty_spin = QDoubleSpinBox()
        self.duty_spin.setRange(0.01, 99.99)
        self.duty_spin.setDecimals(2)
        self.duty_spin.setValue(50.0)
        grid.addWidget(self.duty_spin, 3, 3)

        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self._apply)
        grid.addWidget(self.apply_button, 3, 4)

        self.sync_button = QPushButton("Align phases")
        self.sync_button.clicked.connect(lambda: self._command("sync_phase", {"channel": self.channel()}))
        grid.addWidget(self.sync_button, 4, 4)
        return group

    def _create_sweep_controls(self) -> QGroupBox:
        group = QGroupBox("Sweep")
        grid = QGridLayout(group)
        self.sweep_enable = QCheckBox("Enabled")
        grid.addWidget(self.sweep_enable, 0, 0, 1, 2)
        grid.addWidget(QLabel("Start (Hz):"), 1, 0)
        self.sweep_start = QDoubleSpinBox()
        self.sweep_start.setRange(1e-6, 1e9)
        self.sweep_start.setDecimals(3)
        self.sweep_start.setValue(100.0)
        grid.addWidget(self.sweep_start, 1, 1)
        grid.addWidget(QLabel("Stop (Hz):"), 2, 0)
        self.sweep_stop = QDoubleSpinBox()
        self.sweep_stop.setRange(1e-6, 1e9)
        self.sweep_stop.setDecimals(3)
        self.sweep_stop.setValue(10000.0)
        grid.addWidget(self.sweep_stop, 2, 1)
        grid.addWidget(QLabel("Time (s):"), 3, 0)
        self.sweep_time = QDoubleSpinBox()
        self.sweep_time.setRange(0.001, 500.0)
        self.sweep_time.setDecimals(3)
        self.sweep_time.setValue(1.0)
        grid.addWidget(self.sweep_time, 3, 1)
        grid.addWidget(QLabel("Spacing:"), 4, 0)
        self.sweep_spacing = QComboBox()
        self.sweep_spacing.addItem("Linear", "LINEAR")
        self.sweep_spacing.addItem("Logarithmic", "LOG")
        grid.addWidget(self.sweep_spacing, 4, 1)
        self.sweep_apply = QPushButton("Apply sweep")
        self.sweep_apply.clicked.connect(self._apply_sweep)
        grid.addWidget(self.sweep_apply, 5, 0, 1, 2)
        return group

    def _create_burst_controls(self) -> QGroupBox:
        group = QGroupBox("Burst")
        grid = QGridLayout(group)
        self.burst_enable = QCheckBox("Enabled")
        grid.addWidget(self.burst_enable, 0, 0, 1, 2)
        grid.addWidget(QLabel("Mode:"), 1, 0)
        self.burst_mode = QComboBox()
        self.burst_mode.addItem("N cycles", "TRIG")
        self.burst_mode.addItem("Gated", "GAT")
        self.burst_mode.addItem("Infinite", "INF")
        grid.addWidget(self.burst_mode, 1, 1)
        grid.addWidget(QLabel("Cycles:"), 2, 0)
        self.burst_cycles = QSpinBox()
        self.burst_cycles.setRange(1, 1000000)
        self.burst_cycles.setValue(1)
        grid.addWidget(self.burst_cycles, 2, 1)
        grid.addWidget(QLabel("Period (s):"), 3, 0)
        self.burst_period = QDoubleSpinBox()
        self.burst_period.setRange(1e-6, 500.0)
        self.burst_period.setDecimals(6)
        self.burst_period.setValue(0.01)
        grid.addWidget(self.burst_period, 3, 1)
        self.burst_apply = QPushButton("Apply burst")
        self.burst_apply.clicked.connect(self._apply_burst)
        grid.addWidget(self.burst_apply, 4, 0, 1, 2)
        return group

    def _create_modulation_controls(self) -> QGroupBox:
        group = QGroupBox("Modulation")
        grid = QGridLayout(group)
        self.mod_enable = QCheckBox("Enabled")
        grid.addWidget(self.mod_enable, 0, 0, 1, 2)
        grid.addWidget(QLabel("Type:"), 1, 0)
        self.mod_type = QComboBox()
        for t in ("AM", "FM", "PM", "PWM", "FSK", "ASK", "PSK"):
            self.mod_type.addItem(t, t)
        self.mod_type.currentIndexChanged.connect(self._on_mod_type_changed)
        grid.addWidget(self.mod_type, 1, 1)
        self.mod_param_label = QLabel("Depth (%):")
        grid.addWidget(self.mod_param_label, 2, 0)
        self.mod_param = QDoubleSpinBox()
        self.mod_param.setRange(0.0, 1e9)
        self.mod_param.setDecimals(3)
        self.mod_param.setValue(100.0)
        grid.addWidget(self.mod_param, 2, 1)
        grid.addWidget(QLabel("Mod. freq (Hz):"), 3, 0)
        self.mod_frequency = QDoubleSpinBox()
        self.mod_frequency.setRange(0.001, 1e6)
        self.mod_frequency.setDecimals(3)
        self.mod_frequency.setValue(100.0)
        grid.addWidget(self.mod_frequency, 3, 1)
        grid.addWidget(QLabel("Source:"), 4, 0)
        self.mod_source = QComboBox()
        self.mod_source.addItem("Internal", "INT")
        self.mod_source.addItem("External", "EXT")
        grid.addWidget(self.mod_source, 4, 1)
        self.mod_apply = QPushButton("Apply modulation")
        self.mod_apply.clicked.connect(self._apply_modulation)
        grid.addWidget(self.mod_apply, 5, 0, 1, 2)
        return group

    def _fill_channels(self):
        current = self.channel_combo.currentData() if self.channel_combo.count() else 1
        self.channel_combo.blockSignals(True)
        self.channel_combo.clear()
        for n in range(1, self.num_channels + 1):
            self.channel_combo.addItem(f"CH{n}", n)
        idx = self.channel_combo.findData(current)
        self.channel_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.channel_combo.blockSignals(False)

    def _fill_waveforms(self):
        current = self.waveform_combo.currentData() if self.waveform_combo.count() else "SIN"
        self.waveform_combo.blockSignals(True)
        self.waveform_combo.clear()
        for wf in self.waveforms:
            self.waveform_combo.addItem(WAVEFORM_LABELS.get(wf, wf), wf)
        idx = self.waveform_combo.findData(current)
        self.waveform_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.waveform_combo.blockSignals(False)

    def channel(self) -> int:
        return int(self.channel_combo.currentData() or 1)

    # ------------------------------------------------------------------ #
    # Contract
    # ------------------------------------------------------------------ #

    def configure(self, capabilities: Dict[str, Any]):
        try:
            self.num_channels = max(1, min(self.MAX_CHANNELS, int(capabilities.get("channels") or 2)))
        except (TypeError, ValueError):
            self.num_channels = 2
        waveforms = capabilities.get("waveforms")
        if waveforms:
            self.waveforms = [str(w).upper() for w in waveforms]
        mf = capabilities.get("max_frequency")
        self.max_frequency = {str(k).upper(): float(v) for k, v in mf.items()} if isinstance(mf, dict) else {}
        vpp = capabilities.get("max_amplitude_vpp_highz") or capabilities.get("max_amplitude_vpp_50ohm")
        if vpp:
            self.max_amplitude_vpp = float(vpp)
            self.amplitude_spin.setMaximum(self.max_amplitude_vpp)
        self._has_counter = capabilities.get("has_counter")
        self._fill_channels()
        self._fill_waveforms()
        self._range_frequency()
        self.counter_display.setText("")
    def _range_frequency(self):
        wf = self.waveform_combo.currentData() or "SIN"
        top = self.max_frequency.get(wf) or self.max_frequency.get("SIN") or 1e9
        self.frequency_spin.setMaximum(float(top))
        self.duty_spin.setEnabled(wf in ("SQU", "PULS"))

    async def refresh_settings(self):
        """Read the selected channel's settings onto the controls, silently."""
        if not (self.client and self.equipment):
            return
        data = await self.send("get_readings", {"channel": self.channel()}, priority=False)
        if isinstance(data, dict):
            self._apply_settings(data, adopt=True)

    def _show_channel_settings(self):
        """Channel switch: read that channel back, off the GUI thread."""
        self._schedule_refresh_settings()

    def _apply_settings(self, data: Dict[str, Any], adopt: bool = False):
        wf = str(data.get("waveform") or "").upper()
        freq = data.get("frequency")
        amp = data.get("amplitude")
        unit = str(data.get("amplitude_unit") or "VPP").upper()
        summary = f"{WAVEFORM_LABELS.get(wf, wf)}  {format_frequency(freq)}" if wf else "--"
        self.summary_display.setText(summary)
        details = []
        if amp is not None:
            details.append(f"{amp:g} {unit.replace('VPP', 'Vpp').replace('VRMS', 'Vrms').replace('DBM', 'dBm')}")
        if data.get("offset") is not None:
            details.append(f"offset {data['offset']:g} V")
        if data.get("phase") is not None:
            details.append(f"phase {data['phase']:g}°")
        if data.get("load_impedance"):
            details.append(f"load {data['load_impedance']}")
        for flag, key in (("SWEEP", "sweep_enabled"), ("BURST", "burst_enabled")):
            if data.get(key):
                details.append(flag)
        if data.get("modulation"):
            details.append(str(data["modulation"]))
        self.detail_display.setText("   ".join(details))

        # Unless the operator has just clicked the button and the generator
        # has not caught up: until it agrees, the click is what is true. A
        # reading with no output state in it says nothing, rather than
        # "off" -- reporting a live output as off is the dangerous
        # direction to be wrong in.
        reported = data.get("output_enabled")
        if reported is not None and self.may_show("output", reported):
            enabled = bool(reported)
            self.output_button.blockSignals(True)
            self.output_button.setChecked(enabled)
            self.output_button.setText("Output: ON" if enabled else "Output: OFF")
            self.output_button.blockSignals(False)

        if adopt:
            widgets = (self.waveform_combo, self.frequency_spin, self.amplitude_spin, self.amplitude_unit,
                       self.offset_spin, self.phase_spin, self.duty_spin, self.load_combo)
            for w in widgets:
                w.blockSignals(True)
            try:
                if wf:
                    idx = self.waveform_combo.findData(wf)
                    if idx >= 0:
                        self.waveform_combo.setCurrentIndex(idx)
                    self._range_frequency()
                if freq is not None:
                    self.frequency_spin.setValue(float(freq))
                if amp is not None:
                    self.amplitude_spin.setValue(float(amp))
                idx = self.amplitude_unit.findText(unit)
                if idx >= 0:
                    self.amplitude_unit.setCurrentIndex(idx)
                if data.get("offset") is not None:
                    self.offset_spin.setValue(float(data["offset"]))
                if data.get("phase") is not None:
                    self.phase_spin.setValue(float(data["phase"]))
                if data.get("duty_cycle") is not None:
                    self.duty_spin.setValue(float(data["duty_cycle"]))
                load = str(data.get("load_impedance") or "")
                if load:
                    idx = self.load_combo.findText("High Z") if "INF" in load.upper() or "HIGH" in load.upper() else self.load_combo.findText("50 Ω")
                    if idx >= 0:
                        self.load_combo.setCurrentIndex(idx)
                self.sweep_enable.setChecked(bool(data.get("sweep_enabled")))
                self.burst_enable.setChecked(bool(data.get("burst_enabled")))
                self.mod_enable.setChecked(bool(data.get("modulation")))
            finally:
                for w in widgets:
                    w.blockSignals(False)

    def set_controls_enabled(self, enabled: bool):
        for w in (self.channel_combo, self.output_button, self.load_combo, self.waveform_combo,
                  self.frequency_spin, self.amplitude_spin, self.amplitude_unit, self.offset_spin,
                  self.phase_spin, self.duty_spin, self.apply_button, self.sync_button,
                  self.sweep_apply, self.burst_apply, self.mod_apply):
            w.setEnabled(enabled)

    def show_not_connected(self):
        self.summary_display.setText("--")
        self.detail_display.setText("")
        self.status_message.emit("Not connected. Connect it on the Equipment tab to read it.")

    def show_unsupported(self):
        self.summary_display.setText("--")
        name = getattr(self.equipment, "name", "This instrument")
        self.status_message.emit(f"{name} does not report generator settings.")

    def clear_instrument(self):
        self.summary_display.setText("--")
        self.detail_display.setText("")
        self.counter_display.setText("")

    # ------------------------------------------------------------------ #
    # Polling
    # ------------------------------------------------------------------ #

    async def poll(self):
        data = await self.send("get_readings", {"channel": self.channel()})
        self._apply_settings(data or {})
        if self._has_counter is False:
            return
        try:
            counter = await self.send("get_counter", {})
        except RuntimeError as e:
            # No counter on this model: asked once, not every second.
            self._has_counter = False
            logger.debug(f"No frequency counter: {e}")
            return
        if isinstance(counter, dict):
            self._has_counter = True
            freq = counter.get("frequency")
            if counter.get("enabled") is False or freq is None or (isinstance(freq, float) and math.isnan(freq)):
                self.counter_display.setText("Counter off")
            else:
                self.counter_display.setText(f"Counter: {format_frequency(float(freq))}")

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #

    def _command(self, name: str, parameters: Optional[Dict[str, Any]] = None):
        self._send_command(name, parameters or {})

    @qasync.asyncSlot(str, dict)
    async def _send_command(self, name: str, parameters: dict):
        try:
            result = await self.send(name, parameters)
            if name == "apply" and isinstance(result, dict):
                self._apply_settings(result)
            return result
        except Exception as e:
            logger.error(f"{name} failed: {e}")
            self.status_message.emit(f"{name.replace('_', ' ')} failed: {e}")

    def apply_payload(self) -> Dict[str, Any]:
        wf = self.waveform_combo.currentData() or "SIN"
        payload: Dict[str, Any] = {"channel": self.channel(), "waveform": wf}
        if wf not in ("DC", "NOIS"):
            payload["frequency"] = float(self.frequency_spin.value())
        if wf != "DC":
            payload["amplitude"] = float(self.amplitude_spin.value())
        payload["offset"] = float(self.offset_spin.value())
        if wf not in ("DC", "NOIS"):
            payload["phase"] = float(self.phase_spin.value())
        return payload

    def _apply(self):
        self._apply_all(self.apply_payload(), self.amplitude_unit.currentText(),
                        float(self.duty_spin.value()) if self.duty_spin.isEnabled() else None)

    @qasync.asyncSlot(dict, str, object)
    async def _apply_all(self, payload: dict, unit: str, duty: Optional[float]):
        """Unit first (the amplitude is read in the channel's unit), then apply, then duty."""
        try:
            await self.send("set_amplitude_unit", {"unit": unit, "channel": payload["channel"]})
        except Exception as e:
            logger.debug(f"set_amplitude_unit not accepted: {e}")
        try:
            result = await self.send("apply", payload)
            if isinstance(result, dict):
                self._apply_settings(result)
            if duty is not None:
                await self.send("set_duty_cycle", {"duty_cycle": duty, "channel": payload["channel"]})
        except Exception as e:
            logger.error(f"apply failed: {e}")
            self.status_message.emit(f"Apply failed: {e}")

    def _apply_sweep(self):
        self._command("set_sweep", {
            "enabled": self.sweep_enable.isChecked(), "start": float(self.sweep_start.value()),
            "stop": float(self.sweep_stop.value()), "time": float(self.sweep_time.value()),
            "spacing": self.sweep_spacing.currentData(), "channel": self.channel(),
        })

    def _apply_burst(self):
        self._command("set_burst", {
            "enabled": self.burst_enable.isChecked(), "mode": self.burst_mode.currentData(),
            "cycles": int(self.burst_cycles.value()), "period": float(self.burst_period.value()),
            "channel": self.channel(),
        })

    def _apply_modulation(self):
        mod_type = self.mod_type.currentData()
        payload: Dict[str, Any] = {
            "enabled": self.mod_enable.isChecked(), "modulation_type": mod_type,
            "frequency": float(self.mod_frequency.value()), "source": self.mod_source.currentData(),
            "channel": self.channel(),
        }
        if mod_type == "AM":
            payload["depth"] = float(self.mod_param.value())
        else:
            payload["deviation"] = float(self.mod_param.value())
        self._command("set_modulation", payload)

    def _on_mod_type_changed(self, _index: int):
        mod_type = self.mod_type.currentData()
        self.mod_param_label.setText({"AM": "Depth (%):", "FM": "Deviation (Hz):", "PM": "Deviation (°):",
                                      "PWM": "Duty deviation (%):"}.get(mod_type, "Deviation:"))

    def _on_waveform_changed(self, _index: int):
        self._range_frequency()

    def _on_channel_changed(self, _index: int):
        # The button now means a different channel's output, and a command
        # to the one being left says nothing about this one.
        self.forget_commanded("output")
        self._show_channel_settings()

    def _on_output_toggled(self, checked: bool):
        self.commanded("output", bool(checked))
        self.output_button.setText("Output: ON" if checked else "Output: OFF")
        self._command("set_output", {"enabled": bool(checked), "channel": self.channel()})

    def _on_load_chosen(self, _index: int):
        self._command("set_load", {"impedance": self.load_combo.currentData(), "channel": self.channel()})
