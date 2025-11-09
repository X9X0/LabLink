"""Power supply and electronic load chart widget."""

import logging
from typing import Optional, Dict
import time

try:
    import pyqtgraph as pg
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
        QLabel, QGroupBox, QGridLayout
    )
    from PyQt6.QtCore import Qt, QTimer
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    pg = None

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from utils.data_buffer import CircularBuffer

logger = logging.getLogger(__name__)


class PowerChartWidget(QWidget):
    """Real-time chart for power supply or electronic load data."""

    def __init__(self, parent=None, equipment_type: str = "power_supply", buffer_size: int = 500):
        """Initialize power chart widget.

        Args:
            parent: Parent widget
            equipment_type: "power_supply" or "electronic_load"
            buffer_size: Number of data points to display
        """
        super().__init__(parent)

        if not PYQTGRAPH_AVAILABLE:
            raise ImportError("pyqtgraph and PyQt6 are required")

        self.equipment_type = equipment_type
        self.buffer_size = buffer_size

        # Data buffer (3 channels: voltage, current, power)
        self._buffer = CircularBuffer(size=buffer_size, num_channels=3)
        self._start_time = time.time()

        # Current values
        self._current_values = {
            "voltage": 0.0,
            "current": 0.0,
            "power": 0.0,
            "mode": "Unknown"
        }

        # Statistics
        self.updates_received = 0

        self._setup_ui()

        # Update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_plot)
        self.update_timer.start(100)  # 10 Hz

        self._paused = False

    def _setup_ui(self):
        """Set up user interface."""
        layout = QVBoxLayout(self)

        # Title
        if self.equipment_type == "power_supply":
            title = "<h3>Power Supply Monitor</h3>"
        else:
            title = "<h3>Electronic Load Monitor</h3>"

        title_label = QLabel(title)
        layout.addWidget(title_label)

        # Current readings display
        readings_group = QGroupBox("Current Readings")
        readings_layout = QGridLayout()

        self.voltage_label = QLabel("0.000 V")
        self.voltage_label.setStyleSheet("font-size: 18pt; font-weight: bold; color: #FF0000;")
        readings_layout.addWidget(QLabel("Voltage:"), 0, 0)
        readings_layout.addWidget(self.voltage_label, 0, 1)

        self.current_label = QLabel("0.000 A")
        self.current_label.setStyleSheet("font-size: 18pt; font-weight: bold; color: #00FF00;")
        readings_layout.addWidget(QLabel("Current:"), 1, 0)
        readings_layout.addWidget(self.current_label, 1, 1)

        self.power_label = QLabel("0.000 W")
        self.power_label.setStyleSheet("font-size: 18pt; font-weight: bold; color: #0000FF;")
        readings_layout.addWidget(QLabel("Power:"), 2, 0)
        readings_layout.addWidget(self.power_label, 2, 1)

        self.mode_label = QLabel("Mode: ---")
        readings_layout.addWidget(self.mode_label, 3, 0, 1, 2)

        readings_group.setLayout(readings_layout)
        layout.addWidget(readings_group)

        # Controls
        control_layout = QHBoxLayout()

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setCheckable(True)
        self.pause_btn.clicked.connect(self._on_pause_clicked)
        control_layout.addWidget(self.pause_btn)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear_data)
        control_layout.addWidget(self.clear_btn)

        control_layout.addStretch()

        self.stats_label = QLabel("Updates: 0")
        control_layout.addWidget(self.stats_label)

        layout.addLayout(control_layout)

        # Plot widget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('w')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('bottom', 'Time', units='s')
        self.plot_widget.addLegend()

        # Create curves
        self.voltage_curve = self.plot_widget.plot(
            pen=pg.mkPen(color=(255, 0, 0), width=2),
            name='Voltage (V)'
        )
        self.current_curve = self.plot_widget.plot(
            pen=pg.mkPen(color=(0, 255, 0), width=2),
            name='Current (A)'
        )
        self.power_curve = self.plot_widget.plot(
            pen=pg.mkPen(color=(0, 0, 255), width=2),
            name='Power (W)'
        )

        layout.addWidget(self.plot_widget, stretch=1)

    def update_from_message(self, message: Dict):
        """Update chart from WebSocket message.

        Args:
            message: Message dictionary with power/load data
        """
        if self._paused:
            return

        data = message.get('data', {})

        # Extract values based on equipment type
        if self.equipment_type == "power_supply":
            voltage = data.get('voltage_actual', 0.0)
            current = data.get('current_actual', 0.0)
            output_enabled = data.get('output_enabled', False)

            # Determine mode
            in_cv = data.get('in_cv_mode', False)
            in_cc = data.get('in_cc_mode', False)

            if not output_enabled:
                mode = "OFF"
            elif in_cv:
                mode = "CV"
            elif in_cc:
                mode = "CC"
            else:
                mode = "ON"

        else:  # electronic_load
            voltage = data.get('voltage', 0.0)
            current = data.get('current', 0.0)
            load_enabled = data.get('load_enabled', False)
            mode = data.get('mode', 'Unknown')

            if not load_enabled:
                mode = "OFF"

        power = voltage * current

        # Update current values
        self._current_values = {
            "voltage": voltage,
            "current": current,
            "power": power,
            "mode": mode
        }

        # Add to buffer
        timestamp = time.time() - self._start_time
        self._buffer.append(timestamp, [voltage, current, power])

        self.updates_received += 1

        # Update displays
        self.voltage_label.setText(f"{voltage:.3f} V")
        self.current_label.setText(f"{current:.3f} A")
        self.power_label.setText(f"{power:.3f} W")
        self.mode_label.setText(f"Mode: {mode}")
        self.stats_label.setText(f"Updates: {self.updates_received}")

    def _update_plot(self):
        """Update plot display."""
        if self._paused:
            return

        count = self._buffer.get_count()
        if count < 2:
            return

        # Get data
        time_data, voltage_data = self._buffer.get_data(channel=0)
        _, current_data = self._buffer.get_data(channel=1)
        _, power_data = self._buffer.get_data(channel=2)

        # Update curves
        self.voltage_curve.setData(time_data, voltage_data)
        self.current_curve.setData(time_data, current_data)
        self.power_curve.setData(time_data, power_data)

    def clear_data(self):
        """Clear all data."""
        self._buffer.clear()
        self._start_time = time.time()
        self.updates_received = 0

        self.voltage_label.setText("0.000 V")
        self.current_label.setText("0.000 A")
        self.power_label.setText("0.000 W")
        self.mode_label.setText("Mode: ---")
        self.stats_label.setText("Updates: 0")

        logger.info("Chart data cleared")

    def _on_pause_clicked(self, checked: bool):
        """Handle pause button click."""
        self._paused = checked
        if checked:
            self.pause_btn.setText("Resume")
        else:
            self.pause_btn.setText("Pause")

    def get_current_values(self) -> Dict[str, float]:
        """Get current readings.

        Returns:
            Dictionary of current values
        """
        return self._current_values.copy()

    def get_statistics(self) -> Dict:
        """Get chart statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "updates_received": self.updates_received,
            "buffer_size": self.buffer_size,
            "buffer_count": self._buffer.get_count(),
            "total_samples": self._buffer.get_total_count()
        }
