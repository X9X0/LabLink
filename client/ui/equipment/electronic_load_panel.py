"""Electronic load-specific control panel."""

import logging
from typing import Optional
import asyncio

try:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
        QPushButton, QDoubleSpinBox, QCheckBox, QFormLayout,
        QTabWidget, QComboBox, QSlider
    )
    from PyQt6.QtCore import Qt
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from api.client import LabLinkClient
from ui.widgets.power_chart_widget import PowerChartWidget

logger = logging.getLogger(__name__)


class ElectronicLoadPanel(QWidget):
    """Control panel for electronic load equipment."""

    def __init__(self, parent=None):
        """Initialize electronic load panel."""
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
        header = QLabel("<h2>Electronic Load Control</h2>")
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

        # Mode selection
        mode_group = QGroupBox("Operating Mode")
        mode_layout = QVBoxLayout()

        mode_select_layout = QHBoxLayout()
        mode_select_layout.addWidget(QLabel("Mode:"))

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "CC - Constant Current",
            "CV - Constant Voltage",
            "CR - Constant Resistance",
            "CP - Constant Power"
        ])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_select_layout.addWidget(self.mode_combo)

        mode_select_layout.addStretch()
        mode_layout.addLayout(mode_select_layout)

        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # Setpoint controls (stacked based on mode)
        setpoint_group = QGroupBox("Setpoint")
        setpoint_layout = QVBoxLayout()

        # Current setpoint (CC mode)
        self.current_widget = QWidget()
        current_layout = QVBoxLayout(self.current_widget)

        current_spin_layout = QHBoxLayout()
        current_spin_layout.addWidget(QLabel("Current:"))

        self.current_spin = QDoubleSpinBox()
        self.current_spin.setRange(0, 30)
        self.current_spin.setDecimals(3)
        self.current_spin.setSuffix(" A")
        self.current_spin.setSingleStep(0.01)
        current_spin_layout.addWidget(self.current_spin)

        current_spin_layout.addStretch()
        current_layout.addLayout(current_spin_layout)

        self.current_slider = QSlider(Qt.Orientation.Horizontal)
        self.current_slider.setRange(0, 30000)  # mA
        self.current_slider.valueChanged.connect(lambda v: self.current_spin.setValue(v/1000.0))
        current_layout.addWidget(self.current_slider)
        self.current_spin.valueChanged.connect(lambda v: self.current_slider.setValue(int(v*1000)))

        setpoint_layout.addWidget(self.current_widget)

        # Voltage setpoint (CV mode)
        self.voltage_widget = QWidget()
        voltage_layout = QVBoxLayout(self.voltage_widget)

        voltage_spin_layout = QHBoxLayout()
        voltage_spin_layout.addWidget(QLabel("Voltage:"))

        self.voltage_spin = QDoubleSpinBox()
        self.voltage_spin.setRange(0, 120)
        self.voltage_spin.setDecimals(3)
        self.voltage_spin.setSuffix(" V")
        self.voltage_spin.setSingleStep(0.1)
        voltage_spin_layout.addWidget(self.voltage_spin)

        voltage_spin_layout.addStretch()
        voltage_layout.addLayout(voltage_spin_layout)

        self.voltage_slider = QSlider(Qt.Orientation.Horizontal)
        self.voltage_slider.setRange(0, 120000)  # mV
        self.voltage_slider.valueChanged.connect(lambda v: self.voltage_spin.setValue(v/1000.0))
        voltage_layout.addWidget(self.voltage_slider)
        self.voltage_spin.valueChanged.connect(lambda v: self.voltage_slider.setValue(int(v*1000)))

        self.voltage_widget.hide()
        setpoint_layout.addWidget(self.voltage_widget)

        # Resistance setpoint (CR mode)
        self.resistance_widget = QWidget()
        resistance_layout = QVBoxLayout(self.resistance_widget)

        resistance_spin_layout = QHBoxLayout()
        resistance_spin_layout.addWidget(QLabel("Resistance:"))

        self.resistance_spin = QDoubleSpinBox()
        self.resistance_spin.setRange(0.1, 10000)
        self.resistance_spin.setDecimals(2)
        self.resistance_spin.setSuffix(" Ω")
        self.resistance_spin.setSingleStep(1.0)
        resistance_spin_layout.addWidget(self.resistance_spin)

        resistance_spin_layout.addStretch()
        resistance_layout.addLayout(resistance_spin_layout)

        self.resistance_widget.hide()
        setpoint_layout.addWidget(self.resistance_widget)

        # Power setpoint (CP mode)
        self.power_widget = QWidget()
        power_layout = QVBoxLayout(self.power_widget)

        power_spin_layout = QHBoxLayout()
        power_spin_layout.addWidget(QLabel("Power:"))

        self.power_spin = QDoubleSpinBox()
        self.power_spin.setRange(0, 300)
        self.power_spin.setDecimals(2)
        self.power_spin.setSuffix(" W")
        self.power_spin.setSingleStep(1.0)
        power_spin_layout.addWidget(self.power_spin)

        power_spin_layout.addStretch()
        power_layout.addLayout(power_spin_layout)

        self.power_slider = QSlider(Qt.Orientation.Horizontal)
        self.power_slider.setRange(0, 300000)  # mW
        self.power_slider.valueChanged.connect(lambda v: self.power_spin.setValue(v/1000.0))
        power_layout.addWidget(self.power_slider)
        self.power_spin.valueChanged.connect(lambda v: self.power_slider.setValue(int(v*1000)))

        self.power_widget.hide()
        setpoint_layout.addWidget(self.power_widget)

        setpoint_group.setLayout(setpoint_layout)
        layout.addWidget(setpoint_group)

        # Measurements
        measurements_group = QGroupBox("Measurements")
        measurements_layout = QGridLayout()

        measurements_layout.addWidget(QLabel("<b>Voltage:</b>"), 0, 0)
        self.voltage_actual_label = QLabel("0.000 V")
        self.voltage_actual_label.setStyleSheet("font-size: 16pt; font-weight: bold; color: #FF0000;")
        measurements_layout.addWidget(self.voltage_actual_label, 0, 1)

        measurements_layout.addWidget(QLabel("<b>Current:</b>"), 1, 0)
        self.current_actual_label = QLabel("0.000 A")
        self.current_actual_label.setStyleSheet("font-size: 16pt; font-weight: bold; color: #00FF00;")
        measurements_layout.addWidget(self.current_actual_label, 1, 1)

        measurements_layout.addWidget(QLabel("<b>Power:</b>"), 2, 0)
        self.power_actual_label = QLabel("0.000 W")
        self.power_actual_label.setStyleSheet("font-size: 16pt; font-weight: bold; color: #0000FF;")
        measurements_layout.addWidget(self.power_actual_label, 2, 1)

        measurements_group.setLayout(measurements_layout)
        layout.addWidget(measurements_group)

        # Input control
        input_layout = QHBoxLayout()

        self.input_checkbox = QCheckBox("Input Enabled")
        self.input_checkbox.setStyleSheet("font-size: 14pt;")
        self.input_checkbox.stateChanged.connect(self._on_input_changed)
        input_layout.addWidget(self.input_checkbox)

        input_layout.addStretch()
        layout.addLayout(input_layout)

        # Actions
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
        self.chart = PowerChartWidget(equipment_type="electronic_load", buffer_size=500)
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

        # Enable controls
        self.apply_btn.setEnabled(True)
        self.start_monitor_btn.setEnabled(True)

        self.status_label.setText("Status: Connected")

        logger.info(f"Equipment set: {equipment_id}")

    def _on_mode_changed(self, index: int):
        """Handle mode selection change."""
        # Hide all setpoint widgets
        self.current_widget.hide()
        self.voltage_widget.hide()
        self.resistance_widget.hide()
        self.power_widget.hide()

        # Show selected widget
        if index == 0:  # CC
            self.current_widget.show()
        elif index == 1:  # CV
            self.voltage_widget.show()
        elif index == 2:  # CR
            self.resistance_widget.show()
        elif index == 3:  # CP
            self.power_widget.show()

        logger.info(f"Mode changed: {['CC', 'CV', 'CR', 'CP'][index]}")

    def _on_input_changed(self, state: int):
        """Handle input checkbox change."""
        enabled = (state == Qt.CheckState.Checked.value)
        logger.info(f"Input changed: {enabled}")

    def _on_apply_settings(self):
        """Apply load settings."""
        if not self.client or not self.equipment_id:
            return

        mode_idx = self.mode_combo.currentIndex()
        modes = ["CC", "CV", "CR", "CP"]
        mode = modes[mode_idx]

        # Get setpoint based on mode
        if mode == "CC":
            setpoint = self.current_spin.value()
        elif mode == "CV":
            setpoint = self.voltage_spin.value()
        elif mode == "CR":
            setpoint = self.resistance_spin.value()
        else:  # CP
            setpoint = self.power_spin.value()

        input_enabled = self.input_checkbox.isChecked()

        logger.info(f"Applying: mode={mode}, setpoint={setpoint}, input={input_enabled}")

        asyncio.create_task(self._apply_settings_async(mode, setpoint, input_enabled))

    async def _apply_settings_async(self, mode: str, setpoint: float, input_enabled: bool):
        """Apply settings asynchronously."""
        try:
            # Set mode
            await self.client.send_command(
                equipment_id=self.equipment_id,
                command="set_mode",
                parameters={"mode": mode}
            )

            # Set setpoint based on mode
            if mode == "CC":
                await self.client.send_command(
                    equipment_id=self.equipment_id,
                    command="set_current",
                    parameters={"current": setpoint}
                )
            elif mode == "CV":
                await self.client.send_command(
                    equipment_id=self.equipment_id,
                    command="set_voltage",
                    parameters={"voltage": setpoint}
                )
            elif mode == "CR":
                await self.client.send_command(
                    equipment_id=self.equipment_id,
                    command="set_resistance",
                    parameters={"resistance": setpoint}
                )
            else:  # CP
                await self.client.send_command(
                    equipment_id=self.equipment_id,
                    command="set_power",
                    parameters={"power": setpoint}
                )

            # Set input
            await self.client.send_command(
                equipment_id=self.equipment_id,
                command="set_input",
                parameters={"enabled": input_enabled}
            )

            self.status_label.setText("Status: Settings applied")
            logger.info("Settings applied successfully")

        except Exception as e:
            self.status_label.setText(f"Status: Error - {e}")
            logger.error(f"Failed to apply settings: {e}")

    def _on_set_zero(self):
        """Set all setpoints to zero."""
        self.current_spin.setValue(0.0)
        self.voltage_spin.setValue(0.0)
        self.resistance_spin.setValue(1.0)  # Min 0.1
        self.power_spin.setValue(0.0)
        self.input_checkbox.setChecked(False)

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
        voltage = data.get('voltage', 0.0)
        current = data.get('current', 0.0)
        power = data.get('power', 0.0)

        self.voltage_actual_label.setText(f"{voltage:.3f} V")
        self.current_actual_label.setText(f"{current:.3f} A")
        self.power_actual_label.setText(f"{power:.3f} W")

        # Update mode
        mode = data.get('mode', 'Unknown')
        self.mode_label.setText(f"Mode: {mode}")

        if mode == "CC":
            self.mode_label.setStyleSheet("font-weight: bold; font-size: 12pt; color: #00FF00;")
        elif mode == "CV":
            self.mode_label.setStyleSheet("font-weight: bold; font-size: 12pt; color: #FF0000;")
        elif mode == "CR":
            self.mode_label.setStyleSheet("font-weight: bold; font-size: 12pt; color: #FFA500;")
        elif mode == "CP":
            self.mode_label.setStyleSheet("font-weight: bold; font-size: 12pt; color: #0000FF;")

        # Update chart
        self.chart.update_from_message(message)
