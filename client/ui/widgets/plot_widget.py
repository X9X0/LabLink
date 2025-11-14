"""Reusable real-time plot widget using pyqtgraph."""

import logging
from typing import Optional, Dict, List
import numpy as np

try:
    import pyqtgraph as pg
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
    from PyQt6.QtCore import Qt, QTimer
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    pg = None
    # Define dummy classes for when PyQt6 is not available
    class QWidget:  # type: ignore
        """Dummy QWidget for when PyQt6 is not available."""
        def __init__(self, parent=None):
            pass
    QVBoxLayout = None  # type: ignore
    QHBoxLayout = None  # type: ignore
    QPushButton = None  # type: ignore
    QLabel = None  # type: ignore
    Qt = None  # type: ignore
    QTimer = None  # type: ignore

logger = logging.getLogger(__name__)


class RealTimePlotWidget(QWidget):
    """Real-time plotting widget with circular buffer."""

    def __init__(self, parent=None, buffer_size: int = 1000):
        """Initialize real-time plot widget.

        Args:
            parent: Parent widget
            buffer_size: Number of data points to display
        """
        super().__init__(parent)

        if not PYQTGRAPH_AVAILABLE:
            raise ImportError("pyqtgraph and PyQt6 are required for plotting")

        self.buffer_size = buffer_size

        # Data buffers (circular)
        self._time_buffer = np.zeros(buffer_size)
        self._data_buffers: Dict[str, np.ndarray] = {}
        self._buffer_index = 0
        self._buffer_full = False

        # Plot curves
        self._curves: Dict[str, pg.PlotDataItem] = {}
        self._colors = [
            (255, 0, 0),      # Red
            (0, 255, 0),      # Green
            (0, 0, 255),      # Blue
            (255, 255, 0),    # Yellow
            (255, 0, 255),    # Magenta
            (0, 255, 255),    # Cyan
        ]
        self._next_color_index = 0

        # Statistics
        self.points_plotted = 0
        self.update_count = 0

        self._setup_ui()

    def _setup_ui(self):
        """Set up user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Control bar
        control_layout = QHBoxLayout()

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear_data)
        control_layout.addWidget(self.clear_btn)

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setCheckable(True)
        self.pause_btn.clicked.connect(self._on_pause_clicked)
        control_layout.addWidget(self.pause_btn)

        self.stats_label = QLabel("Points: 0")
        control_layout.addWidget(self.stats_label)

        control_layout.addStretch()

        layout.addLayout(control_layout)

        # Create plot widget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('w')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('bottom', 'Time', units='s')

        layout.addWidget(self.plot_widget)

        # Update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_plot)
        self.update_timer.start(50)  # 20 Hz update rate

        self._paused = False

    def add_channel(self, name: str, color: Optional[tuple] = None, width: int = 2):
        """Add a data channel to the plot.

        Args:
            name: Channel name
            color: RGB color tuple (0-255), or None for auto
            width: Line width
        """
        if name in self._data_buffers:
            return

        # Create data buffer
        self._data_buffers[name] = np.zeros(self.buffer_size)

        # Choose color
        if color is None:
            color = self._colors[self._next_color_index % len(self._colors)]
            self._next_color_index += 1

        # Create curve
        pen = pg.mkPen(color=color, width=width)
        curve = self.plot_widget.plot(pen=pen, name=name)
        self._curves[name] = curve

        logger.info(f"Added channel: {name}")

    def remove_channel(self, name: str):
        """Remove a data channel.

        Args:
            name: Channel name
        """
        if name not in self._data_buffers:
            return

        # Remove curve
        if name in self._curves:
            self.plot_widget.removeItem(self._curves[name])
            del self._curves[name]

        # Remove buffer
        del self._data_buffers[name]

        logger.info(f"Removed channel: {name}")

    def add_data_point(self, timestamp: float, data: Dict[str, float]):
        """Add a data point to the plot.

        Args:
            timestamp: Time in seconds
            data: Dictionary of {channel_name: value}
        """
        if self._paused:
            return

        # Add to circular buffer
        self._time_buffer[self._buffer_index] = timestamp

        for channel, value in data.items():
            if channel not in self._data_buffers:
                self.add_channel(channel)

            self._data_buffers[channel][self._buffer_index] = value

        # Update buffer index
        self._buffer_index = (self._buffer_index + 1) % self.buffer_size

        if self._buffer_index == 0:
            self._buffer_full = True

        self.points_plotted += 1

    def _update_plot(self):
        """Update the plot display."""
        if self._paused:
            return

        # Get valid data range
        if self._buffer_full:
            # Use entire buffer, but reorder to be chronological
            time_data = np.roll(self._time_buffer, -self._buffer_index)
            start_idx = 0
            end_idx = self.buffer_size
        else:
            # Use only filled portion
            time_data = self._time_buffer[:self._buffer_index]
            start_idx = 0
            end_idx = self._buffer_index

        if end_idx - start_idx < 2:
            return

        # Update each curve
        for channel, buffer in self._data_buffers.items():
            if channel not in self._curves:
                continue

            if self._buffer_full:
                channel_data = np.roll(buffer, -self._buffer_index)
            else:
                channel_data = buffer[:self._buffer_index]

            self._curves[channel].setData(time_data, channel_data)

        self.update_count += 1

        # Update stats
        self.stats_label.setText(f"Points: {self.points_plotted} | Updates: {self.update_count}")

    def clear_data(self):
        """Clear all data from the plot."""
        self._time_buffer.fill(0)
        for buffer in self._data_buffers.values():
            buffer.fill(0)

        self._buffer_index = 0
        self._buffer_full = False
        self.points_plotted = 0
        self.update_count = 0

        self.stats_label.setText("Points: 0")

        logger.info("Plot data cleared")

    def _on_pause_clicked(self, checked: bool):
        """Handle pause button click."""
        self._paused = checked
        if checked:
            self.pause_btn.setText("Resume")
        else:
            self.pause_btn.setText("Pause")

    def set_labels(self, title: str = "", x_label: str = "Time", y_label: str = "Value",
                   x_units: str = "s", y_units: str = ""):
        """Set plot labels.

        Args:
            title: Plot title
            x_label: X-axis label
            y_label: Y-axis label
            x_units: X-axis units
            y_units: Y-axis units
        """
        if title:
            self.plot_widget.setTitle(title)
        self.plot_widget.setLabel('bottom', x_label, units=x_units)
        self.plot_widget.setLabel('left', y_label, units=y_units)

    def set_y_range(self, min_val: float, max_val: float):
        """Set Y-axis range.

        Args:
            min_val: Minimum value
            max_val: Maximum value
        """
        self.plot_widget.setYRange(min_val, max_val)

    def enable_auto_range(self, enable: bool = True):
        """Enable or disable auto-ranging.

        Args:
            enable: True to enable auto-ranging
        """
        self.plot_widget.enableAutoRange(enable=enable)

    def add_legend(self):
        """Add legend to the plot."""
        self.plot_widget.addLegend()

    def get_statistics(self) -> Dict[str, int]:
        """Get plotting statistics.

        Returns:
            Dictionary of statistics
        """
        return {
            "points_plotted": self.points_plotted,
            "update_count": self.update_count,
            "buffer_size": self.buffer_size,
            "channels": len(self._data_buffers),
            "buffer_usage": self._buffer_index if not self._buffer_full else self.buffer_size
        }
