"""Oscilloscope-specific control panel."""

import asyncio
import logging
from typing import Optional

try:
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                                 QFormLayout, QGridLayout, QGroupBox,
                                 QHBoxLayout, QLabel, QPushButton, QTabWidget,
                                 QVBoxLayout, QWidget)

    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from client.api.client import LabLinkClient
from client.ui.widgets.waveform_display import WaveformDisplay

logger = logging.getLogger(__name__)


class OscilloscopePanel(QWidget):
    """Control panel for oscilloscope equipment."""

    def __init__(self, parent=None):
        """Initialize oscilloscope panel."""
        if not PYQT_AVAILABLE:
            raise ImportError("PyQt6 is required")

        super().__init__(parent)

        self.client: Optional[LabLinkClient] = None
        self.equipment_id: Optional[str] = None
        self.streaming = False

        self._setup_ui()

    def _setup_ui(self):
        """Set up user interface."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("<h2>Oscilloscope Control</h2>")
        layout.addWidget(header)

        # Equipment info
        self.info_label = QLabel("<i>No equipment connected</i>")
        layout.addWidget(self.info_label)

        # Tabs for controls and display
        tabs = QTabWidget()

        # Display tab
        display_tab = QWidget()
        display_layout = QVBoxLayout(display_tab)

        self.waveform_display = WaveformDisplay(num_channels=4)
        display_layout.addWidget(self.waveform_display)

        tabs.addTab(display_tab, "Display")

        # Control tab
        control_tab = self._create_control_tab()
        tabs.addTab(control_tab, "Controls")

        # Measurements tab
        measurements_tab = self._create_measurements_tab()
        tabs.addTab(measurements_tab, "Measurements")

        layout.addWidget(tabs)

        # Stream control buttons
        stream_layout = QHBoxLayout()

        self.start_stream_btn = QPushButton("Start Streaming")
        self.start_stream_btn.clicked.connect(self._on_start_stream)
        self.start_stream_btn.setEnabled(False)
        stream_layout.addWidget(self.start_stream_btn)

        self.stop_stream_btn = QPushButton("Stop Streaming")
        self.stop_stream_btn.clicked.connect(self._on_stop_stream)
        self.stop_stream_btn.setEnabled(False)
        stream_layout.addWidget(self.stop_stream_btn)

        stream_layout.addStretch()

        self.status_label = QLabel("Status: Not streaming")
        stream_layout.addWidget(self.status_label)

        layout.addLayout(stream_layout)

    def _create_control_tab(self) -> QWidget:
        """Create controls tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Timebase group
        timebase_group = QGroupBox("Timebase")
        timebase_layout = QFormLayout()

        self.timebase_combo = QComboBox()
        self.timebase_combo.addItems(
            [
                "1 ns/div",
                "2 ns/div",
                "5 ns/div",
                "10 ns/div",
                "20 ns/div",
                "50 ns/div",
                "100 ns/div",
                "200 ns/div",
                "500 ns/div",
                "1 µs/div",
                "2 µs/div",
                "5 µs/div",
                "10 µs/div",
                "20 µs/div",
                "50 µs/div",
                "100 µs/div",
                "200 µs/div",
                "500 µs/div",
                "1 ms/div",
                "2 ms/div",
                "5 ms/div",
                "10 ms/div",
                "20 ms/div",
                "50 ms/div",
                "100 ms/div",
                "200 ms/div",
                "500 ms/div",
                "1 s/div",
                "2 s/div",
                "5 s/div",
            ]
        )
        self.timebase_combo.setCurrentText("1 ms/div")
        timebase_layout.addRow("Scale:", self.timebase_combo)

        self.timebase_offset_spin = QDoubleSpinBox()
        self.timebase_offset_spin.setRange(-100, 100)
        self.timebase_offset_spin.setSuffix(" s")
        timebase_layout.addRow("Offset:", self.timebase_offset_spin)

        apply_timebase_btn = QPushButton("Apply Timebase")
        apply_timebase_btn.clicked.connect(self._on_apply_timebase)
        timebase_layout.addRow("", apply_timebase_btn)

        timebase_group.setLayout(timebase_layout)
        layout.addWidget(timebase_group)

        # Channel controls
        channels_group = QGroupBox("Channels")
        channels_layout = QGridLayout()

        self.channel_controls = {}

        for i in range(1, 5):
            # Channel label
            ch_label = QLabel(f"<b>CH{i}</b>")
            channels_layout.addWidget(ch_label, i - 1, 0)

            # Enable checkbox
            enable_cb = QCheckBox("Enable")
            enable_cb.setChecked(i <= 2)
            channels_layout.addWidget(enable_cb, i - 1, 1)

            # Scale combo
            scale_combo = QComboBox()
            scale_combo.addItems(
                [
                    "1 mV/div",
                    "2 mV/div",
                    "5 mV/div",
                    "10 mV/div",
                    "20 mV/div",
                    "50 mV/div",
                    "100 mV/div",
                    "200 mV/div",
                    "500 mV/div",
                    "1 V/div",
                    "2 V/div",
                    "5 V/div",
                    "10 V/div",
                ]
            )
            scale_combo.setCurrentText("1 V/div")
            channels_layout.addWidget(scale_combo, i - 1, 2)

            # Coupling combo
            coupling_combo = QComboBox()
            coupling_combo.addItems(["DC", "AC", "GND"])
            channels_layout.addWidget(coupling_combo, i - 1, 3)

            # Apply button
            apply_btn = QPushButton("Apply")
            apply_btn.clicked.connect(lambda checked, ch=i: self._on_apply_channel(ch))
            channels_layout.addWidget(apply_btn, i - 1, 4)

            self.channel_controls[i] = {
                "enable": enable_cb,
                "scale": scale_combo,
                "coupling": coupling_combo,
            }

        channels_group.setLayout(channels_layout)
        layout.addWidget(channels_group)

        # Trigger controls
        trigger_group = QGroupBox("Trigger")
        trigger_layout = QFormLayout()

        self.trigger_mode_combo = QComboBox()
        self.trigger_mode_combo.addItems(["Auto", "Normal", "Single"])
        trigger_layout.addRow("Mode:", self.trigger_mode_combo)

        self.trigger_source_combo = QComboBox()
        self.trigger_source_combo.addItems(["CH1", "CH2", "CH3", "CH4", "EXT"])
        trigger_layout.addRow("Source:", self.trigger_source_combo)

        self.trigger_level_spin = QDoubleSpinBox()
        self.trigger_level_spin.setRange(-10, 10)
        self.trigger_level_spin.setSuffix(" V")
        trigger_layout.addRow("Level:", self.trigger_level_spin)

        trigger_buttons = QHBoxLayout()

        run_btn = QPushButton("Run")
        run_btn.clicked.connect(self._on_trigger_run)
        trigger_buttons.addWidget(run_btn)

        single_btn = QPushButton("Single")
        single_btn.clicked.connect(self._on_trigger_single)
        trigger_buttons.addWidget(single_btn)

        stop_btn = QPushButton("Stop")
        stop_btn.clicked.connect(self._on_trigger_stop)
        trigger_buttons.addWidget(stop_btn)

        trigger_layout.addRow("", trigger_buttons)

        trigger_group.setLayout(trigger_layout)
        layout.addWidget(trigger_group)

        # Quick actions
        actions_group = QGroupBox("Quick Actions")
        actions_layout = QHBoxLayout()

        autoscale_btn = QPushButton("Autoscale")
        autoscale_btn.clicked.connect(self._on_autoscale)
        actions_layout.addWidget(autoscale_btn)

        default_btn = QPushButton("Default Setup")
        default_btn.clicked.connect(self._on_default_setup)
        actions_layout.addWidget(default_btn)

        actions_group.setLayout(actions_layout)
        layout.addWidget(actions_group)

        layout.addStretch()

        return widget

    def _create_measurements_tab(self) -> QWidget:
        """Create measurements tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        info_label = QLabel("<h3>Automated Measurements</h3>")
        layout.addWidget(info_label)

        # Measurement controls
        meas_control_layout = QHBoxLayout()

        self.meas_channel_combo = QComboBox()
        self.meas_channel_combo.addItems(["CH1", "CH2", "CH3", "CH4"])
        meas_control_layout.addWidget(QLabel("Channel:"))
        meas_control_layout.addWidget(self.meas_channel_combo)

        get_meas_btn = QPushButton("Get Measurements")
        get_meas_btn.clicked.connect(self._on_get_measurements)
        meas_control_layout.addWidget(get_meas_btn)

        meas_control_layout.addStretch()

        layout.addLayout(meas_control_layout)

        # Measurements display
        self.measurements_group = QGroupBox("Results")
        measurements_layout = QGridLayout()

        self.meas_labels = {}
        meas_names = [
            ("Vpp", "Peak-to-peak"),
            ("Vmax", "Maximum"),
            ("Vmin", "Minimum"),
            ("Vavg", "Average"),
            ("Vrms", "RMS"),
            ("Freq", "Frequency"),
            ("Period", "Period"),
        ]

        for i, (key, label) in enumerate(meas_names):
            measurements_layout.addWidget(QLabel(f"<b>{label}:</b>"), i, 0)
            value_label = QLabel("---")
            value_label.setStyleSheet("font-size: 14pt;")
            measurements_layout.addWidget(value_label, i, 1)
            self.meas_labels[key.lower()] = value_label

        self.measurements_group.setLayout(measurements_layout)
        layout.addWidget(self.measurements_group)

        layout.addStretch()

        return widget

    def set_client(self, client: LabLinkClient):
        """Set API client."""
        self.client = client

    def set_equipment(self, equipment_id: str, info: dict):
        """Set connected equipment.

        Args:
            equipment_id: Equipment ID
            info: Equipment info dictionary
        """
        self.equipment_id = equipment_id

        # Update info label
        model = info.get("model", "Unknown")
        manufacturer = info.get("manufacturer", "Unknown")
        self.info_label.setText(
            f"<b>Connected:</b> {manufacturer} {model} ({equipment_id})"
        )

        # Enable streaming button
        self.start_stream_btn.setEnabled(True)

        logger.info(f"Equipment set: {equipment_id}")

    def _on_start_stream(self):
        """Start waveform streaming."""
        if not self.client or not self.equipment_id:
            return

        # Register handler
        self.client.register_stream_data_handler(self._on_waveform_data)

        # Start streaming
        asyncio.create_task(self._start_streaming())

    async def _start_streaming(self):
        """Start streaming (async)."""
        try:
            await self.client.start_equipment_stream(
                equipment_id=self.equipment_id, stream_type="waveform", interval_ms=100
            )

            self.streaming = True
            self.start_stream_btn.setEnabled(False)
            self.stop_stream_btn.setEnabled(True)
            self.status_label.setText("Status: Streaming")

            logger.info("Started waveform streaming")

        except Exception as e:
            logger.error(f"Failed to start streaming: {e}")
            self.status_label.setText(f"Status: Error - {e}")

    def _on_stop_stream(self):
        """Stop waveform streaming."""
        asyncio.create_task(self._stop_streaming())

    async def _stop_streaming(self):
        """Stop streaming (async)."""
        try:
            await self.client.stop_equipment_stream(
                equipment_id=self.equipment_id, stream_type="waveform"
            )

            self.streaming = False
            self.start_stream_btn.setEnabled(True)
            self.stop_stream_btn.setEnabled(False)
            self.status_label.setText("Status: Not streaming")

            logger.info("Stopped waveform streaming")

        except Exception as e:
            logger.error(f"Failed to stop streaming: {e}")

    def _on_waveform_data(self, message: dict):
        """Handle incoming waveform data."""
        if message.get("equipment_id") != self.equipment_id:
            return

        if message.get("stream_type") != "waveform":
            return

        # Update display
        self.waveform_display.update_waveform_from_message(message)

    def _on_apply_timebase(self):
        """Apply timebase settings."""
        if not self.client or not self.equipment_id:
            return

        # Parse timebase value
        timebase_text = self.timebase_combo.currentText()
        # Extract numeric value and unit
        # For now, just log
        logger.info(f"Apply timebase: {timebase_text}")

        # Would send command to equipment
        # asyncio.create_task(self.client.send_command(...))

    def _on_apply_channel(self, channel: int):
        """Apply channel settings."""
        if not self.client or not self.equipment_id:
            return

        controls = self.channel_controls[channel]
        enabled = controls["enable"].isChecked()
        scale_text = controls["scale"].currentText()
        coupling = controls["coupling"].currentText()

        logger.info(
            f"Apply CH{channel}: enabled={enabled}, scale={scale_text}, coupling={coupling}"
        )

        # Would send command to equipment

    def _on_trigger_run(self):
        """Set trigger to run mode."""
        logger.info("Trigger: Run")
        # Would send command

    def _on_trigger_single(self):
        """Set trigger to single mode."""
        logger.info("Trigger: Single")
        # Would send command

    def _on_trigger_stop(self):
        """Set trigger to stop mode."""
        logger.info("Trigger: Stop")
        # Would send command

    def _on_autoscale(self):
        """Run autoscale."""
        logger.info("Autoscale")
        # Would send command

    def _on_default_setup(self):
        """Apply default setup."""
        logger.info("Default setup")
        # Would send command

    def _on_get_measurements(self):
        """Get measurements for selected channel."""
        if not self.client or not self.equipment_id:
            return

        channel = self.meas_channel_combo.currentIndex() + 1
        asyncio.create_task(self._fetch_measurements(channel))

    async def _fetch_measurements(self, channel: int):
        """Fetch measurements (async)."""
        try:
            # Get measurements from waveform display
            measurements = self.waveform_display.get_measurements(channel)

            if measurements:
                self.meas_labels["vpp"].setText(f"{measurements['vpp']:.3f} V")
                self.meas_labels["vmax"].setText(f"{measurements.get('vmax', 0):.3f} V")
                self.meas_labels["vmin"].setText(f"{measurements.get('vmin', 0):.3f} V")
                self.meas_labels["vavg"].setText(f"{measurements.get('vavg', 0):.3f} V")
                self.meas_labels["vrms"].setText(f"{measurements['vrms']:.3f} V")

                freq = measurements["freq"]
                if freq > 1e6:
                    self.meas_labels["freq"].setText(f"{freq/1e6:.3f} MHz")
                elif freq > 1e3:
                    self.meas_labels["freq"].setText(f"{freq/1e3:.3f} kHz")
                else:
                    self.meas_labels["freq"].setText(f"{freq:.3f} Hz")

                period = 1 / freq if freq > 0 else 0
                if period > 1:
                    self.meas_labels["period"].setText(f"{period:.3f} s")
                elif period > 1e-3:
                    self.meas_labels["period"].setText(f"{period*1e3:.3f} ms")
                elif period > 1e-6:
                    self.meas_labels["period"].setText(f"{period*1e6:.3f} µs")
                else:
                    self.meas_labels["period"].setText(f"{period*1e9:.3f} ns")

        except Exception as e:
            logger.error(f"Failed to get measurements: {e}")
