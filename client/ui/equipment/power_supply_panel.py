"""Power supply-specific control panel."""

import logging
from typing import Optional
import asyncio

try:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
        QPushButton, QDoubleSpinBox, QCheckBox, QFormLayout,
        QTabWidget, QSlider, QSpinBox
    )
    from PyQt6.QtCore import Qt, QTimer
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from api.client import LabLinkClient
from ui.widgets.power_chart_widget import PowerChartWidget

logger = logging.getLogger(__name__)


class PowerSupplyPanel(QWidget):
    """Control panel for power supply equipment."""

    def __init__(self, parent=None):
        """Initialize power supply panel."""
        if not PYQT_AVAILABLE:
            raise ImportError("PyQt6 is required")

        super().__init__(parent)

        self.client: Optional[LabLinkClient] = None
        self.equipment_id: Optional[str] = None
        self.streaming = False
        self.num_channels = 1

        self._setup_ui()

    def _setup_ui(self):
        """Set up user interface."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("<h2>Power Supply Control</h2>")
        layout.addWidget(header)

        # Equipment info
        self.info_label = QLabel("<i>No equipment connected</i>")
        layout.addWidget(self.info_label)

        # Tabs
        tabs = QTabWidget()

        # Control tab
        control_tab = self._create_control_tab()
        tabs.addTab(control_tab, "Control")

        # Monitor tab
        monitor_tab = self._create_monitor_tab()
        tabs.addTab(monitor_tab, "Monitor")

        layout.addWidget(tabs)

        # Status bar
        status_layout = QHBoxLayout()

        self.status_label = QLabel("Status: Not connected")
        status_layout.addWidget(self.status_label)

        status_layout.addStretch()

        self.mode_label = QLabel("Mode: ---")
        self.mode_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        status_layout.addWidget(self.mode_label)

        layout.addLayout(status_layout)

    def _create_control_tab(self) -> QWidget:
        """Create control tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Channel selection (for multi-channel PSU)
        channel_layout = QHBoxLayout()
        channel_layout.addWidget(QLabel("Channel:"))

        self.channel_selector = QSpinBox()
        self.channel_selector.setRange(1, 3)
        self.channel_selector.setValue(1)
        self.channel_selector.valueChanged.connect(self._on_channel_changed)
        channel_layout.addWidget(self.channel_selector)

        channel_layout.addStretch()
        layout.addLayout(channel_layout)

        # Voltage control
        voltage_group = QGroupBox("Voltage Control")
        voltage_layout = QVBoxLayout()

        # Voltage setpoint
        v_setpoint_layout = QHBoxLayout()

        v_setpoint_layout.addWidget(QLabel("Setpoint:"))

        self.voltage_spin = QDoubleSpinBox()
        self.voltage_spin.setRange(0, 60)
        self.voltage_spin.setDecimals(3)
        self.voltage_spin.setSuffix(" V")
        self.voltage_spin.setSingleStep(0.1)
        self.voltage_spin.valueChanged.connect(self._on_voltage_changed)
        v_setpoint_layout.addWidget(self.voltage_spin)

        v_setpoint_layout.addStretch()
        voltage_layout.addLayout(v_setpoint_layout)

        # Voltage slider
        self.voltage_slider = QSlider(Qt.Orientation.Horizontal)
        self.voltage_slider.setRange(0, 60000)  # mV
        self.voltage_slider.valueChanged.connect(self._on_voltage_slider_changed)
        voltage_layout.addWidget(self.voltage_slider)

        # Voltage readback
        v_readback_layout = QHBoxLayout()
        v_readback_layout.addWidget(QLabel("Actual:"))

        self.voltage_actual_label = QLabel("0.000 V")
        self.voltage_actual_label.setStyleSheet("font-size: 16pt; font-weight: bold; color: #FF0000;")
        v_readback_layout.addWidget(self.voltage_actual_label)

        v_readback_layout.addStretch()
        voltage_layout.addLayout(v_readback_layout)

        voltage_group.setLayout(voltage_layout)
        layout.addWidget(voltage_group)

        # Current control
        current_group = QGroupBox("Current Control")
        current_layout = QVBoxLayout()

        # Current limit
        i_setpoint_layout = QHBoxLayout()

        i_setpoint_layout.addWidget(QLabel("Limit:"))

        self.current_spin = QDoubleSpinBox()
        self.current_spin.setRange(0, 10)
        self.current_spin.setDecimals(3)
        self.current_spin.setSuffix(" A")
        self.current_spin.setSingleStep(0.01)
        self.current_spin.valueChanged.connect(self._on_current_changed)
        i_setpoint_layout.addWidget(self.current_spin)

        i_setpoint_layout.addStretch()
        current_layout.addLayout(i_setpoint_layout)

        # Current slider
        self.current_slider = QSlider(Qt.Orientation.Horizontal)
        self.current_slider.setRange(0, 10000)  # mA
        self.current_slider.valueChanged.connect(self._on_current_slider_changed)
        current_layout.addWidget(self.current_slider)

        # Current readback
        i_readback_layout = QHBoxLayout()
        i_readback_layout.addWidget(QLabel("Actual:"))

        self.current_actual_label = QLabel("0.000 A")
        self.current_actual_label.setStyleSheet("font-size: 16pt; font-weight: bold; color: #00FF00;")
        i_readback_layout.addWidget(self.current_actual_label)

        i_readback_layout.addStretch()
        current_layout.addLayout(i_readback_layout)

        current_group.setLayout(current_layout)
        layout.addWidget(current_group)

        # Power display
        power_layout = QHBoxLayout()
        power_layout.addWidget(QLabel("<b>Power:</b>"))

        self.power_label = QLabel("0.000 W")
        self.power_label.setStyleSheet("font-size: 16pt; font-weight: bold; color: #0000FF;")
        power_layout.addWidget(self.power_label)

        power_layout.addStretch()
        layout.addLayout(power_layout)

        # Output control
        output_layout = QHBoxLayout()

        self.output_checkbox = QCheckBox("Output Enabled")
        self.output_checkbox.setStyleSheet("font-size: 14pt;")
        self.output_checkbox.stateChanged.connect(self._on_output_changed)
        output_layout.addWidget(self.output_checkbox)

        output_layout.addStretch()
        layout.addLayout(output_layout)

        # Quick actions
        actions_layout = QHBoxLayout()

        self.apply_btn = QPushButton("Apply Settings")
        self.apply_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        self.apply_btn.clicked.connect(self._on_apply_settings)
        self.apply_btn.setEnabled(False)
        actions_layout.addWidget(self.apply_btn)

        zero_btn = QPushButton("Set to Zero")
        zero_btn.clicked.connect(self._on_set_zero)
        actions_layout.addWidget(zero_btn)

        layout.addLayout(actions_layout)

        layout.addStretch()

        return widget

    def _create_monitor_tab(self) -> QWidget:
        """Create monitoring tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Chart
        self.chart = PowerChartWidget(equipment_type="power_supply", buffer_size=500)
        layout.addWidget(self.chart)

        # Stream control
        stream_layout = QHBoxLayout()

        self.start_monitor_btn = QPushButton("Start Monitoring")
        self.start_monitor_btn.clicked.connect(self._on_start_monitoring)
        self.start_monitor_btn.setEnabled(False)
        stream_layout.addWidget(self.start_monitor_btn)

        self.stop_monitor_btn = QPushButton("Stop Monitoring")
        self.stop_monitor_btn.clicked.connect(self._on_stop_monitoring)
        self.stop_monitor_btn.setEnabled(False)
        stream_layout.addWidget(self.stop_monitor_btn)

        stream_layout.addStretch()

        layout.addLayout(stream_layout)

        return widget

    def set_client(self, client: LabLinkClient):
        """Set API client."""
        self.client = client

    def set_equipment(self, equipment_id: str, info: dict):
        """Set connected equipment."""
        self.equipment_id = equipment_id

        # Update info
        model = info.get('model', 'Unknown')
        manufacturer = info.get('manufacturer', 'Unknown')
        self.info_label.setText(f"<b>Connected:</b> {manufacturer} {model} ({equipment_id})")

        # Get capabilities
        capabilities = info.get('capabilities', {})
        num_channels = capabilities.get('num_channels', 1)
        max_voltage = capabilities.get('max_voltage', 60)
        max_current = capabilities.get('max_current', 10)

        self.num_channels = num_channels
        self.channel_selector.setMaximum(num_channels)

        # Update ranges
        self.voltage_spin.setMaximum(max_voltage)
        self.voltage_slider.setMaximum(int(max_voltage * 1000))

        self.current_spin.setMaximum(max_current)
        self.current_slider.setMaximum(int(max_current * 1000))

        # Enable controls
        self.apply_btn.setEnabled(True)
        self.start_monitor_btn.setEnabled(True)

        self.status_label.setText("Status: Connected")

        logger.info(f"Equipment set: {equipment_id}, channels={num_channels}")

    def _on_channel_changed(self, channel: int):
        """Handle channel selection change."""
        logger.info(f"Channel changed: {channel}")
        # Would fetch current settings for this channel

    def _on_voltage_changed(self, value: float):
        """Handle voltage spinbox change."""
        self.voltage_slider.blockSignals(True)
        self.voltage_slider.setValue(int(value * 1000))
        self.voltage_slider.blockSignals(False)

    def _on_voltage_slider_changed(self, value: int):
        """Handle voltage slider change."""
        voltage = value / 1000.0
        self.voltage_spin.blockSignals(True)
        self.voltage_spin.setValue(voltage)
        self.voltage_spin.blockSignals(False)

    def _on_current_changed(self, value: float):
        """Handle current spinbox change."""
        self.current_slider.blockSignals(True)
        self.current_slider.setValue(int(value * 1000))
        self.current_slider.blockSignals(False)

    def _on_current_slider_changed(self, value: int):
        """Handle current slider change."""
        current = value / 1000.0
        self.current_spin.blockSignals(True)
        self.current_spin.setValue(current)
        self.current_spin.blockSignals(False)

    def _on_output_changed(self, state: int):
        """Handle output checkbox change."""
        enabled = (state == Qt.CheckState.Checked.value)
        logger.info(f"Output changed: {enabled}")

    def _on_apply_settings(self):
        """Apply voltage/current settings."""
        if not self.client or not self.equipment_id:
            return

        voltage = self.voltage_spin.value()
        current = self.current_spin.value()
        channel = self.channel_selector.value()
        output_enabled = self.output_checkbox.isChecked()

        logger.info(f"Applying: V={voltage}V, I={current}A, CH={channel}, OUT={output_enabled}")

        asyncio.create_task(self._apply_settings_async(voltage, current, channel, output_enabled))

    async def _apply_settings_async(self, voltage: float, current: float, channel: int, output_enabled: bool):
        """Apply settings asynchronously."""
        try:
            # Set voltage
            await self.client.send_command(
                equipment_id=self.equipment_id,
                command="set_voltage",
                parameters={"voltage": voltage, "channel": channel}
            )

            # Set current
            await self.client.send_command(
                equipment_id=self.equipment_id,
                command="set_current",
                parameters={"current": current, "channel": channel}
            )

            # Set output
            await self.client.send_command(
                equipment_id=self.equipment_id,
                command="set_output",
                parameters={"enabled": output_enabled, "channel": channel}
            )

            self.status_label.setText("Status: Settings applied")
            logger.info("Settings applied successfully")

        except Exception as e:
            self.status_label.setText(f"Status: Error - {e}")
            logger.error(f"Failed to apply settings: {e}")

    def _on_set_zero(self):
        """Set voltage and current to zero."""
        self.voltage_spin.setValue(0.0)
        self.current_spin.setValue(0.0)
        self.output_checkbox.setChecked(False)

    def _on_start_monitoring(self):
        """Start real-time monitoring."""
        if not self.client or not self.equipment_id:
            return

        # Register handler
        self.client.register_stream_data_handler(self._on_readings_data)

        # Start streaming
        asyncio.create_task(self._start_streaming())

    async def _start_streaming(self):
        """Start streaming (async)."""
        try:
            await self.client.start_equipment_stream(
                equipment_id=self.equipment_id,
                stream_type="readings",
                interval_ms=200
            )

            self.streaming = True
            self.start_monitor_btn.setEnabled(False)
            self.stop_monitor_btn.setEnabled(True)

            logger.info("Started monitoring")

        except Exception as e:
            logger.error(f"Failed to start monitoring: {e}")

    def _on_stop_monitoring(self):
        """Stop real-time monitoring."""
        asyncio.create_task(self._stop_streaming())

    async def _stop_streaming(self):
        """Stop streaming (async)."""
        try:
            await self.client.stop_equipment_stream(
                equipment_id=self.equipment_id,
                stream_type="readings"
            )

            self.streaming = False
            self.start_monitor_btn.setEnabled(True)
            self.stop_monitor_btn.setEnabled(False)

            logger.info("Stopped monitoring")

        except Exception as e:
            logger.error(f"Failed to stop monitoring: {e}")

    def _on_readings_data(self, message: dict):
        """Handle incoming readings data."""
        if message.get('equipment_id') != self.equipment_id:
            return

        if message.get('stream_type') != 'readings':
            return

        data = message.get('data', {})

        # Update displays
        voltage = data.get('voltage_actual', 0.0)
        current = data.get('current_actual', 0.0)
        power = voltage * current

        self.voltage_actual_label.setText(f"{voltage:.3f} V")
        self.current_actual_label.setText(f"{current:.3f} A")
        self.power_label.setText(f"{power:.3f} W")

        # Update mode
        in_cv = data.get('in_cv_mode', False)
        in_cc = data.get('in_cc_mode', False)

        if in_cv:
            self.mode_label.setText("Mode: CV (Constant Voltage)")
            self.mode_label.setStyleSheet("font-weight: bold; font-size: 12pt; color: #FF0000;")
        elif in_cc:
            self.mode_label.setText("Mode: CC (Constant Current)")
            self.mode_label.setStyleSheet("font-weight: bold; font-size: 12pt; color: #00FF00;")
        else:
            self.mode_label.setText("Mode: ---")

        # Update chart
        self.chart.update_from_message(message)
