"""Equipment control panel with advanced controls and visualization."""

import asyncio
import logging
from collections import deque
from datetime import datetime
from typing import Dict, Optional

from models.equipment import ConnectionStatus, Equipment
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup, QDial, QDoubleSpinBox, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QRadioButton, QSplitter,
    QVBoxLayout, QWidget
)
from PyQt6.QtGui import QFont, QPalette, QColor
from PyQt6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis

from client.api.client import LabLinkClient

logger = logging.getLogger(__name__)


class AnalogGauge(QWidget):
    """Custom analog gauge widget for voltage/current display."""

    def __init__(self, title="", min_value=0, max_value=100, unit="", parent=None):
        """Initialize analog gauge.

        Args:
            title: Gauge title
            min_value: Minimum value
            max_value: Maximum value
            unit: Unit of measurement
            parent: Parent widget
        """
        super().__init__(parent)
        self.title = title
        self.min_value = min_value
        self.max_value = max_value
        self.unit = unit
        self.current_value = 0.0

        self.setMinimumSize(200, 200)

    def set_value(self, value: float):
        """Set the current value and update display."""
        self.current_value = max(self.min_value, min(self.max_value, value))
        self.update()

    def paintEvent(self, event):
        """Paint the gauge."""
        from PyQt6.QtGui import QPainter, QPen, QBrush, QConicalGradient
        from PyQt6.QtCore import QPointF, QRectF
        import math

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Get dimensions
        width = self.width()
        height = self.height()
        size = min(width, height) - 20
        center_x = width / 2
        center_y = height / 2

        # Draw gauge background
        painter.setPen(QPen(Qt.GlobalColor.gray, 2))
        painter.setBrush(QBrush(Qt.GlobalColor.lightGray))
        painter.drawEllipse(QPointF(center_x, center_y), size / 2, size / 2)

        # Draw tick marks
        painter.setPen(QPen(Qt.GlobalColor.black, 2))
        for i in range(11):
            angle = 225 - (i * 27)  # 270 degrees range
            rad = math.radians(angle)
            x1 = center_x + (size / 2 - 15) * math.cos(rad)
            y1 = center_y - (size / 2 - 15) * math.sin(rad)
            x2 = center_x + (size / 2 - 5) * math.cos(rad)
            y2 = center_y - (size / 2 - 5) * math.sin(rad)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        # Draw value labels
        painter.setFont(QFont("Arial", 8))
        for i in range(11):
            value = self.min_value + (self.max_value - self.min_value) * i / 10
            angle = 225 - (i * 27)
            rad = math.radians(angle)
            x = center_x + (size / 2 - 30) * math.cos(rad)
            y = center_y - (size / 2 - 30) * math.sin(rad)
            painter.drawText(int(x - 15), int(y + 5), 30, 20, Qt.AlignmentFlag.AlignCenter, f"{value:.1f}")

        # Draw needle
        value_ratio = (self.current_value - self.min_value) / (self.max_value - self.min_value)
        needle_angle = 225 - (value_ratio * 270)
        rad = math.radians(needle_angle)
        needle_length = size / 2 - 40

        painter.setPen(QPen(Qt.GlobalColor.red, 3))
        x_end = center_x + needle_length * math.cos(rad)
        y_end = center_y - needle_length * math.sin(rad)
        painter.drawLine(int(center_x), int(center_y), int(x_end), int(y_end))

        # Draw center dot
        painter.setBrush(QBrush(Qt.GlobalColor.red))
        painter.drawEllipse(QPointF(center_x, center_y), 5, 5)

        # Draw title
        painter.setPen(QPen(Qt.GlobalColor.black))
        painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        painter.drawText(0, int(center_y + size / 2 - 40), width, 30, Qt.AlignmentFlag.AlignCenter, self.title)

        # Draw current value
        painter.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        value_text = f"{self.current_value:.2f} {self.unit}"
        painter.drawText(0, int(center_y + size / 2 - 10), width, 30, Qt.AlignmentFlag.AlignCenter, value_text)


class ControlPanel(QWidget):
    """Advanced equipment control panel with visualization."""

    equipment_selected = pyqtSignal(str)

    def __init__(self, client: Optional[LabLinkClient] = None, parent=None):
        """Initialize control panel.

        Args:
            client: LabLink API client
            parent: Parent widget
        """
        super().__init__(parent)
        self.client = client
        self.selected_equipment: Optional[Equipment] = None
        self.equipment_list: List[Equipment] = []

        # Data storage for graphs
        self.voltage_data = deque(maxlen=100)
        self.current_data = deque(maxlen=100)
        self.time_data = deque(maxlen=100)

        # Timers
        self.voltage_timer = QTimer()
        self.current_timer = QTimer()
        self.voltage_timer.timeout.connect(self._update_voltage)
        self.current_timer.timeout.connect(self._update_current)

        self._setup_ui()

    def _setup_ui(self):
        """Set up the user interface."""
        main_layout = QHBoxLayout(self)

        # Create splitter for resizable panels
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel - Equipment list
        left_panel = self._create_equipment_list_panel()
        splitter.addWidget(left_panel)

        # Right panel - Controls and displays
        right_panel = self._create_control_panel()
        splitter.addWidget(right_panel)

        # Set initial sizes (20% left, 80% right)
        splitter.setSizes([200, 800])

        main_layout.addWidget(splitter)

    def _create_equipment_list_panel(self) -> QWidget:
        """Create the equipment list panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Title
        title = QLabel("<h3>Connected Equipment</h3>")
        layout.addWidget(title)

        # Equipment list
        self.equipment_list_widget = QListWidget()
        self.equipment_list_widget.itemClicked.connect(self._on_equipment_selected)
        layout.addWidget(self.equipment_list_widget)

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_equipment_list)
        layout.addWidget(refresh_btn)

        return panel

    def _create_control_panel(self) -> QWidget:
        """Create the main control panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Equipment info
        self.equipment_info_label = QLabel("No equipment selected")
        self.equipment_info_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(self.equipment_info_label)

        # Control section
        control_group = self._create_control_section()
        layout.addWidget(control_group)

        # Display mode selection
        display_mode_group = self._create_display_mode_section()
        layout.addWidget(display_mode_group)

        # Display area
        self.display_stack = QWidget()
        self.display_layout = QVBoxLayout(self.display_stack)

        # Create display modes
        self.digital_display = self._create_digital_display()
        self.analog_display = self._create_analog_display()
        self.graph_display = self._create_graph_display()

        # Add to stack (only one visible at a time)
        self.display_layout.addWidget(self.digital_display)
        self.display_layout.addWidget(self.analog_display)
        self.display_layout.addWidget(self.graph_display)

        # Initially show digital
        self.analog_display.hide()
        self.graph_display.hide()

        layout.addWidget(self.display_stack)

        return panel

    def _create_control_section(self) -> QGroupBox:
        """Create the control section with knobs and inputs."""
        group = QGroupBox("Controls")
        layout = QVBoxLayout(group)

        # Top row: Voltage and Current controls
        controls_layout = QHBoxLayout()

        # Voltage control
        voltage_group = QGroupBox("Voltage Control")
        voltage_layout = QVBoxLayout(voltage_group)

        # Voltage knob
        self.voltage_dial = QDial()
        self.voltage_dial.setMinimum(0)
        self.voltage_dial.setMaximum(600)  # 60.0V * 10
        self.voltage_dial.setValue(0)
        self.voltage_dial.setNotchesVisible(True)
        self.voltage_dial.valueChanged.connect(self._on_voltage_dial_changed)
        self.voltage_dial.setWrapping(False)
        voltage_layout.addWidget(self.voltage_dial)

        # Voltage numeric input
        voltage_input_layout = QHBoxLayout()
        voltage_input_layout.addWidget(QLabel("Voltage (V):"))
        self.voltage_spinbox = QDoubleSpinBox()
        self.voltage_spinbox.setMinimum(0.0)
        self.voltage_spinbox.setMaximum(60.0)
        self.voltage_spinbox.setValue(0.0)
        self.voltage_spinbox.setDecimals(2)
        self.voltage_spinbox.setSingleStep(0.1)
        self.voltage_spinbox.valueChanged.connect(self._on_voltage_spinbox_changed)
        voltage_input_layout.addWidget(self.voltage_spinbox)
        voltage_layout.addLayout(voltage_input_layout)

        controls_layout.addWidget(voltage_group)

        # Current control
        current_group = QGroupBox("Current Control")
        current_layout = QVBoxLayout(current_group)

        # Current knob
        self.current_dial = QDial()
        self.current_dial.setMinimum(0)
        self.current_dial.setMaximum(160)  # 16.0A * 10
        self.current_dial.setValue(0)
        self.current_dial.setNotchesVisible(True)
        self.current_dial.valueChanged.connect(self._on_current_dial_changed)
        self.current_dial.setWrapping(False)
        current_layout.addWidget(self.current_dial)

        # Current numeric input
        current_input_layout = QHBoxLayout()
        current_input_layout.addWidget(QLabel("Current (A):"))
        self.current_spinbox = QDoubleSpinBox()
        self.current_spinbox.setMinimum(0.0)
        self.current_spinbox.setMaximum(16.0)
        self.current_spinbox.setValue(0.0)
        self.current_spinbox.setDecimals(2)
        self.current_spinbox.setSingleStep(0.1)
        self.current_spinbox.valueChanged.connect(self._on_current_spinbox_changed)
        current_input_layout.addWidget(self.current_spinbox)
        current_layout.addLayout(current_input_layout)

        controls_layout.addWidget(current_group)

        layout.addLayout(controls_layout)

        # Bottom row: Output control and mode indicators
        bottom_layout = QHBoxLayout()

        # Output control
        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout(output_group)

        self.output_button = QPushButton("Output: OFF")
        self.output_button.setCheckable(True)
        self.output_button.setStyleSheet("QPushButton:checked { background-color: green; color: white; }")
        self.output_button.clicked.connect(self._on_output_toggled)
        output_layout.addWidget(self.output_button)

        bottom_layout.addWidget(output_group)

        # Mode indicators
        mode_group = QGroupBox("Operating Mode")
        mode_layout = QVBoxLayout(mode_group)

        self.cv_indicator = QLabel("CV: OFF")
        self.cv_indicator.setStyleSheet("QLabel { background-color: gray; color: white; padding: 5px; }")
        mode_layout.addWidget(self.cv_indicator)

        self.cc_indicator = QLabel("CC: OFF")
        self.cc_indicator.setStyleSheet("QLabel { background-color: gray; color: white; padding: 5px; }")
        mode_layout.addWidget(self.cc_indicator)

        bottom_layout.addWidget(mode_group)

        # Refresh rate controls
        refresh_group = QGroupBox("Refresh Rates")
        refresh_layout = QVBoxLayout(refresh_group)

        # Voltage refresh rate
        v_refresh_layout = QHBoxLayout()
        v_refresh_layout.addWidget(QLabel("Voltage (Hz):"))
        self.voltage_refresh_spinbox = QDoubleSpinBox()
        self.voltage_refresh_spinbox.setMinimum(0.1)
        self.voltage_refresh_spinbox.setMaximum(10.0)
        self.voltage_refresh_spinbox.setValue(1.0)
        self.voltage_refresh_spinbox.setDecimals(1)
        self.voltage_refresh_spinbox.setSingleStep(0.1)
        self.voltage_refresh_spinbox.valueChanged.connect(self._on_voltage_refresh_changed)
        v_refresh_layout.addWidget(self.voltage_refresh_spinbox)
        refresh_layout.addLayout(v_refresh_layout)

        # Current refresh rate
        i_refresh_layout = QHBoxLayout()
        i_refresh_layout.addWidget(QLabel("Current (Hz):"))
        self.current_refresh_spinbox = QDoubleSpinBox()
        self.current_refresh_spinbox.setMinimum(0.1)
        self.current_refresh_spinbox.setMaximum(10.0)
        self.current_refresh_spinbox.setValue(1.0)
        self.current_refresh_spinbox.setDecimals(1)
        self.current_refresh_spinbox.setSingleStep(0.1)
        self.current_refresh_spinbox.valueChanged.connect(self._on_current_refresh_changed)
        i_refresh_layout.addWidget(self.current_refresh_spinbox)
        refresh_layout.addLayout(i_refresh_layout)

        bottom_layout.addWidget(refresh_group)

        layout.addLayout(bottom_layout)

        return group

    def _create_display_mode_section(self) -> QGroupBox:
        """Create display mode selection."""
        group = QGroupBox("Display Mode")
        layout = QHBoxLayout(group)

        self.display_mode_group = QButtonGroup()

        self.digital_radio = QRadioButton("Digital")
        self.digital_radio.setChecked(True)
        self.digital_radio.toggled.connect(lambda: self._on_display_mode_changed("digital"))
        self.display_mode_group.addButton(self.digital_radio)
        layout.addWidget(self.digital_radio)

        self.analog_radio = QRadioButton("Analog")
        self.analog_radio.toggled.connect(lambda: self._on_display_mode_changed("analog"))
        self.display_mode_group.addButton(self.analog_radio)
        layout.addWidget(self.analog_radio)

        self.graph_radio = QRadioButton("Graph")
        self.graph_radio.toggled.connect(lambda: self._on_display_mode_changed("graph"))
        self.display_mode_group.addButton(self.graph_radio)
        layout.addWidget(self.graph_radio)

        return group

    def _create_digital_display(self) -> QWidget:
        """Create digital display mode."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Large digital readouts
        self.voltage_display = QLabel("0.00 V")
        self.voltage_display.setFont(QFont("Arial", 48, QFont.Weight.Bold))
        self.voltage_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.voltage_display.setStyleSheet("QLabel { background-color: black; color: lime; padding: 20px; }")
        layout.addWidget(self.voltage_display)

        self.current_display = QLabel("0.000 A")
        self.current_display.setFont(QFont("Arial", 48, QFont.Weight.Bold))
        self.current_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_display.setStyleSheet("QLabel { background-color: black; color: lime; padding: 20px; }")
        layout.addWidget(self.current_display)

        return widget

    def _create_analog_display(self) -> QWidget:
        """Create analog gauge display mode."""
        widget = QWidget()
        layout = QHBoxLayout(widget)

        self.voltage_gauge = AnalogGauge("Voltage", 0, 60, "V")
        layout.addWidget(self.voltage_gauge)

        self.current_gauge = AnalogGauge("Current", 0, 16, "A")
        layout.addWidget(self.current_gauge)

        return widget

    def _create_graph_display(self) -> QWidget:
        """Create graph display mode."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Create chart
        self.chart = QChart()
        self.chart.setTitle("Voltage and Current vs Time")
        self.chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)

        # Create series
        self.voltage_series = QLineSeries()
        self.voltage_series.setName("Voltage (V)")
        self.chart.addSeries(self.voltage_series)

        self.current_series = QLineSeries()
        self.current_series.setName("Current (A)")
        self.chart.addSeries(self.current_series)

        # Create axes
        self.axis_x = QValueAxis()
        self.axis_x.setTitleText("Time (s)")
        self.axis_x.setRange(0, 100)
        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)

        self.axis_y_voltage = QValueAxis()
        self.axis_y_voltage.setTitleText("Voltage (V)")
        self.axis_y_voltage.setRange(0, 60)
        self.chart.addAxis(self.axis_y_voltage, Qt.AlignmentFlag.AlignLeft)

        self.axis_y_current = QValueAxis()
        self.axis_y_current.setTitleText("Current (A)")
        self.axis_y_current.setRange(0, 16)
        self.chart.addAxis(self.axis_y_current, Qt.AlignmentFlag.AlignRight)

        # Attach series to axes
        self.voltage_series.attachAxis(self.axis_x)
        self.voltage_series.attachAxis(self.axis_y_voltage)
        self.current_series.attachAxis(self.axis_x)
        self.current_series.attachAxis(self.axis_y_current)

        # Create chart view
        chart_view = QChartView(self.chart)
        chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        layout.addWidget(chart_view)

        return widget

    def _on_equipment_selected(self):
        """Handle equipment selection."""
        selected_items = self.equipment_list_widget.selectedItems()
        if not selected_items:
            return

        equipment_id = selected_items[0].data(Qt.ItemDataRole.UserRole)

        # Find equipment in list
        for equipment in self.equipment_list:
            if equipment.equipment_id == equipment_id:
                self.selected_equipment = equipment
                self.equipment_info_label.setText(
                    f"{equipment.name} - {equipment.manufacturer} {equipment.model}"
                )
                self.equipment_selected.emit(equipment_id)
                # Start reading data
                self._start_data_acquisition()
                break

    def _on_voltage_dial_changed(self, value):
        """Handle voltage dial change."""
        voltage = value / 10.0
        self.voltage_spinbox.blockSignals(True)
        self.voltage_spinbox.setValue(voltage)
        self.voltage_spinbox.blockSignals(False)
        self._send_voltage_command(voltage)

    def _on_voltage_spinbox_changed(self, value):
        """Handle voltage spinbox change."""
        self.voltage_dial.blockSignals(True)
        self.voltage_dial.setValue(int(value * 10))
        self.voltage_dial.blockSignals(False)
        self._send_voltage_command(value)

    def _on_current_dial_changed(self, value):
        """Handle current dial change."""
        current = value / 10.0
        self.current_spinbox.blockSignals(True)
        self.current_spinbox.setValue(current)
        self.current_spinbox.blockSignals(False)
        self._send_current_command(current)

    def _on_current_spinbox_changed(self, value):
        """Handle current spinbox change."""
        self.current_dial.blockSignals(True)
        self.current_dial.setValue(int(value * 10))
        self.current_dial.blockSignals(False)
        self._send_current_command(value)

    def _on_output_toggled(self, checked):
        """Handle output button toggle."""
        if checked:
            self.output_button.setText("Output: ON")
            self._send_output_command(True)
        else:
            self.output_button.setText("Output: OFF")
            self._send_output_command(False)

    def _on_voltage_refresh_changed(self, value):
        """Handle voltage refresh rate change."""
        interval = int(1000 / value)  # Convert Hz to ms
        self.voltage_timer.setInterval(interval)

    def _on_current_refresh_changed(self, value):
        """Handle current refresh rate change."""
        interval = int(1000 / value)  # Convert Hz to ms
        self.current_timer.setInterval(interval)

    def _on_display_mode_changed(self, mode):
        """Handle display mode change."""
        if mode == "digital":
            self.digital_display.show()
            self.analog_display.hide()
            self.graph_display.hide()
        elif mode == "analog":
            self.digital_display.hide()
            self.analog_display.show()
            self.graph_display.hide()
        elif mode == "graph":
            self.digital_display.hide()
            self.analog_display.hide()
            self.graph_display.show()

    def _send_voltage_command(self, voltage: float):
        """Send voltage command to equipment."""
        if not self.selected_equipment or not self.client:
            return

        try:
            self.client.send_command(
                self.selected_equipment.equipment_id,
                "set_voltage",
                {"voltage": voltage, "channel": 1}
            )
        except Exception as e:
            logger.error(f"Error sending voltage command: {e}")

    def _send_current_command(self, current: float):
        """Send current command to equipment."""
        if not self.selected_equipment or not self.client:
            return

        try:
            self.client.send_command(
                self.selected_equipment.equipment_id,
                "set_current",
                {"current": current, "channel": 1}
            )
        except Exception as e:
            logger.error(f"Error sending current command: {e}")

    def _send_output_command(self, enabled: bool):
        """Send output enable/disable command."""
        if not self.selected_equipment or not self.client:
            return

        try:
            self.client.send_command(
                self.selected_equipment.equipment_id,
                "set_output",
                {"enabled": enabled, "channel": 1}
            )
        except Exception as e:
            logger.error(f"Error sending output command: {e}")

    def _start_data_acquisition(self):
        """Start acquiring data from selected equipment."""
        if not self.selected_equipment:
            return

        # Start timers
        self.voltage_timer.start(1000)  # 1 Hz default
        self.current_timer.start(1000)  # 1 Hz default

    def _stop_data_acquisition(self):
        """Stop acquiring data."""
        self.voltage_timer.stop()
        self.current_timer.stop()

    def _update_voltage(self):
        """Update voltage reading."""
        if not self.selected_equipment or not self.client:
            return

        try:
            readings = self.client.get_readings(self.selected_equipment.equipment_id)
            voltage = readings.get("voltage_actual", 0.0)

            # Update displays
            self.voltage_display.setText(f"{voltage:.2f} V")
            self.voltage_gauge.set_value(voltage)

            # Update graph
            timestamp = len(self.voltage_data)
            self.voltage_data.append(voltage)
            self.time_data.append(timestamp)

            # Update mode indicators
            if readings.get("in_cv_mode"):
                self.cv_indicator.setText("CV: ON")
                self.cv_indicator.setStyleSheet("QLabel { background-color: green; color: white; padding: 5px; }")
                self.cc_indicator.setText("CC: OFF")
                self.cc_indicator.setStyleSheet("QLabel { background-color: gray; color: white; padding: 5px; }")
            elif readings.get("in_cc_mode"):
                self.cc_indicator.setText("CC: ON")
                self.cc_indicator.setStyleSheet("QLabel { background-color: orange; color: white; padding: 5px; }")
                self.cv_indicator.setText("CV: OFF")
                self.cv_indicator.setStyleSheet("QLabel { background-color: gray; color: white; padding: 5px; }")

        except Exception as e:
            logger.error(f"Error updating voltage: {e}")

    def _update_current(self):
        """Update current reading."""
        if not self.selected_equipment or not self.client:
            return

        try:
            readings = self.client.get_readings(self.selected_equipment.equipment_id)
            current = readings.get("current_actual", 0.0)

            # Update displays
            self.current_display.setText(f"{current:.3f} A")
            self.current_gauge.set_value(current)

            # Update graph
            timestamp = len(self.current_data)
            self.current_data.append(current)

            # Update graph series
            self._update_graph()

        except Exception as e:
            logger.error(f"Error updating current: {e}")

    def _update_graph(self):
        """Update the graph with current data."""
        self.voltage_series.clear()
        self.current_series.clear()

        for i, v in enumerate(self.voltage_data):
            self.voltage_series.append(i, v)

        for i, c in enumerate(self.current_data):
            self.current_series.append(i, c)

        # Update x-axis range
        if self.time_data:
            self.axis_x.setRange(max(0, len(self.time_data) - 100), len(self.time_data))

    def refresh_equipment_list(self):
        """Refresh the equipment list from server."""
        if not self.client:
            return

        try:
            equipment_list = self.client.list_equipment()
            self.equipment_list = [Equipment(**eq) for eq in equipment_list]

            # Update list widget
            self.equipment_list_widget.clear()
            for equipment in self.equipment_list:
                if equipment.connection_status == ConnectionStatus.CONNECTED:
                    item = QListWidgetItem(
                        f"{equipment.name} ({equipment.equipment_type.value})"
                    )
                    item.setData(Qt.ItemDataRole.UserRole, equipment.equipment_id)
                    self.equipment_list_widget.addItem(item)

        except Exception as e:
            logger.error(f"Error refreshing equipment list: {e}")

    def set_client(self, client: LabLinkClient):
        """Set the API client."""
        self.client = client
        self.refresh_equipment_list()

    def wheelEvent(self, event):
        """Handle mouse wheel events over dials."""
        # This allows scrolling over dials to change values
        widget = self.childAt(event.position().toPoint())
        if isinstance(widget, QDial):
            delta = event.angleDelta().y()
            current_value = widget.value()
            step = 1 if delta > 0 else -1
            widget.setValue(current_value + step)
            event.accept()
        else:
            event.ignore()
