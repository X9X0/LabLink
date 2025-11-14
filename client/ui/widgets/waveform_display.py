"""Oscilloscope-style waveform display widget."""

import logging
from typing import Optional, Dict, List
import numpy as np

try:
    import pyqtgraph as pg
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
        QLabel, QGroupBox, QGridLayout, QCheckBox
    )
    from PyQt6.QtCore import Qt
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    pg = None
    # Define dummy classes for when PyQt6 is not available
    class QWidget:  # type: ignore
        """Dummy QWidget for when PyQt6 is not available."""
        def __init__(self, parent=None, num_channels: int = 4):
            pass
    QVBoxLayout = None  # type: ignore
    QHBoxLayout = None  # type: ignore
    QPushButton = None  # type: ignore
    QLabel = None  # type: ignore
    QGroupBox = None  # type: ignore
    QGridLayout = None  # type: ignore
    QCheckBox = None  # type: ignore
    Qt = None  # type: ignore

logger = logging.getLogger(__name__)


class WaveformDisplay(QWidget):
    """Oscilloscope-style waveform display with measurements."""

    def __init__(self, parent=None, num_channels: int = 4):
        """Initialize waveform display.

        Args:
            parent: Parent widget
            num_channels: Number of channels to support
        """
        super().__init__(parent)

        if not PYQTGRAPH_AVAILABLE:
            raise ImportError("pyqtgraph and PyQt6 are required")

        self.num_channels = num_channels

        # Channel data
        self._channel_data: Dict[int, np.ndarray] = {}
        self._channel_enabled: Dict[int, bool] = {i: True for i in range(1, num_channels + 1)}
        self._channel_curves: Dict[int, pg.PlotDataItem] = {}

        # Channel colors (oscilloscope style)
        self._channel_colors = {
            1: (255, 255, 0),    # Yellow
            2: (0, 255, 255),    # Cyan
            3: (255, 0, 255),    # Magenta
            4: (0, 255, 0),      # Green
        }

        # Waveform parameters
        self.sample_rate = 1e9  # Hz
        self.time_scale = 1e-3  # s/div
        self.voltage_scales = {i: 1.0 for i in range(1, num_channels + 1)}  # V/div

        # Measurements
        self._measurements: Dict[int, Dict[str, float]] = {}

        # Statistics
        self.waveforms_displayed = 0

        self._setup_ui()

    def _setup_ui(self):
        """Set up user interface."""
        layout = QVBoxLayout(self)

        # Top controls
        control_layout = QHBoxLayout()

        self.run_btn = QPushButton("Run")
        self.run_btn.setCheckable(True)
        self.run_btn.setChecked(True)
        control_layout.addWidget(self.run_btn)

        self.single_btn = QPushButton("Single")
        control_layout.addWidget(self.single_btn)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear_waveforms)
        control_layout.addWidget(self.clear_btn)

        control_layout.addStretch()

        # Time/div display
        self.timescale_label = QLabel(f"Time: {self.time_scale*1e3:.1f}ms/div")
        control_layout.addWidget(self.timescale_label)

        layout.addLayout(control_layout)

        # Main waveform display
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('k')  # Black background (scope style)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.5)
        self.plot_widget.setLabel('bottom', 'Time', units='s')
        self.plot_widget.setLabel('left', 'Voltage', units='V')

        # Style the grid to look like an oscilloscope
        self.plot_widget.getPlotItem().getAxis('bottom').setPen(pg.mkPen(color=(0, 255, 0), width=1))
        self.plot_widget.getPlotItem().getAxis('left').setPen(pg.mkPen(color=(0, 255, 0), width=1))

        layout.addWidget(self.plot_widget, stretch=3)

        # Channel controls and measurements
        bottom_layout = QHBoxLayout()

        # Channel enable checkboxes
        channels_group = QGroupBox("Channels")
        channels_layout = QHBoxLayout()

        self.channel_checkboxes = {}
        for i in range(1, self.num_channels + 1):
            cb = QCheckBox(f"CH{i}")
            cb.setChecked(True)
            cb.stateChanged.connect(lambda state, ch=i: self._on_channel_toggled(ch, state))
            channels_layout.addWidget(cb)
            self.channel_checkboxes[i] = cb

        channels_group.setLayout(channels_layout)
        bottom_layout.addWidget(channels_group)

        # Measurements display
        measurements_group = QGroupBox("Measurements")
        measurements_layout = QGridLayout()

        self.measurement_labels: Dict[int, Dict[str, QLabel]] = {}

        row = 0
        for i in range(1, min(self.num_channels + 1, 3)):  # Show first 2-3 channels
            # Channel label
            ch_label = QLabel(f"<b>CH{i}</b>")
            ch_label.setStyleSheet(f"color: rgb{self._channel_colors.get(i, (255, 255, 255))};")
            measurements_layout.addWidget(ch_label, row, 0)

            # Frequency
            freq_label = QLabel("---")
            measurements_layout.addWidget(QLabel("Freq:"), row, 1)
            measurements_layout.addWidget(freq_label, row, 2)

            # Vpp
            vpp_label = QLabel("---")
            measurements_layout.addWidget(QLabel("Vpp:"), row, 3)
            measurements_layout.addWidget(vpp_label, row, 4)

            # Vrms
            vrms_label = QLabel("---")
            measurements_layout.addWidget(QLabel("Vrms:"), row, 5)
            measurements_layout.addWidget(vrms_label, row, 6)

            self.measurement_labels[i] = {
                "freq": freq_label,
                "vpp": vpp_label,
                "vrms": vrms_label
            }

            row += 1

        measurements_group.setLayout(measurements_layout)
        bottom_layout.addWidget(measurements_group, stretch=1)

        layout.addLayout(bottom_layout)

        # Initialize curves
        for i in range(1, self.num_channels + 1):
            color = self._channel_colors.get(i, (255, 255, 255))
            pen = pg.mkPen(color=color, width=2)
            curve = self.plot_widget.plot(pen=pen, name=f"CH{i}")
            self._channel_curves[i] = curve

    def update_waveform(self, channel: int, waveform_data: np.ndarray,
                       sample_rate: Optional[float] = None):
        """Update waveform for a channel.

        Args:
            channel: Channel number (1-indexed)
            waveform_data: Waveform data array
            sample_rate: Sample rate in Hz (optional)
        """
        if not self.run_btn.isChecked():
            return

        if channel < 1 or channel > self.num_channels:
            logger.warning(f"Invalid channel: {channel}")
            return

        if not self._channel_enabled.get(channel, False):
            return

        # Store data
        self._channel_data[channel] = waveform_data

        if sample_rate:
            self.sample_rate = sample_rate

        # Create time array
        num_samples = len(waveform_data)
        time_array = np.arange(num_samples) / self.sample_rate

        # Update curve
        if channel in self._channel_curves:
            self._channel_curves[channel].setData(time_array, waveform_data)

        self.waveforms_displayed += 1

        # Calculate and update measurements
        self._update_measurements(channel, waveform_data)

    def update_waveform_from_message(self, message: Dict):
        """Update waveform from WebSocket message.

        Args:
            message: Message dictionary with waveform data
        """
        data = message.get('data', {})
        channel = data.get('channel', 1)

        # For now, generate synthetic waveform based on metadata
        # In real implementation, you'd receive raw binary data separately
        num_samples = data.get('num_samples', 1000)
        sample_rate = data.get('sample_rate', 1e9)

        # Generate synthetic waveform (replace with actual data reception)
        t = np.linspace(0, num_samples / sample_rate, num_samples)
        waveform = np.sin(2 * np.pi * 1000 * t) * 2  # 1 kHz sine wave

        self.update_waveform(channel, waveform, sample_rate)

    def _update_measurements(self, channel: int, waveform: np.ndarray):
        """Calculate and update measurements for a channel.

        Args:
            channel: Channel number
            waveform: Waveform data
        """
        if len(waveform) < 2:
            return

        # Calculate measurements
        vpp = np.max(waveform) - np.min(waveform)
        vrms = np.sqrt(np.mean(waveform**2))

        # Estimate frequency (zero-crossing method)
        try:
            zero_crossings = np.where(np.diff(np.sign(waveform)))[0]
            if len(zero_crossings) >= 2:
                # Period = average time between zero crossings * 2
                period = (zero_crossings[-1] - zero_crossings[0]) / len(zero_crossings) * 2 / self.sample_rate
                freq = 1 / period if period > 0 else 0
            else:
                freq = 0
        except:
            freq = 0

        # Store measurements
        self._measurements[channel] = {
            "freq": freq,
            "vpp": vpp,
            "vrms": vrms
        }

        # Update display
        if channel in self.measurement_labels:
            labels = self.measurement_labels[channel]

            if freq > 1e6:
                labels["freq"].setText(f"{freq/1e6:.2f} MHz")
            elif freq > 1e3:
                labels["freq"].setText(f"{freq/1e3:.2f} kHz")
            else:
                labels["freq"].setText(f"{freq:.2f} Hz")

            labels["vpp"].setText(f"{vpp:.3f} V")
            labels["vrms"].setText(f"{vrms:.3f} V")

    def _on_channel_toggled(self, channel: int, state: int):
        """Handle channel enable/disable.

        Args:
            channel: Channel number
            state: Checkbox state
        """
        enabled = (state == Qt.CheckState.Checked.value)
        self._channel_enabled[channel] = enabled

        # Show/hide curve
        if channel in self._channel_curves:
            self._channel_curves[channel].setVisible(enabled)

        logger.info(f"Channel {channel} {'enabled' if enabled else 'disabled'}")

    def clear_waveforms(self):
        """Clear all waveforms."""
        for curve in self._channel_curves.values():
            curve.setData([], [])

        self._channel_data.clear()
        self._measurements.clear()

        # Clear measurement displays
        for channel_labels in self.measurement_labels.values():
            for label in channel_labels.values():
                label.setText("---")

        logger.info("Waveforms cleared")

    def set_time_scale(self, time_scale: float):
        """Set time scale (seconds per division).

        Args:
            time_scale: Time per division in seconds
        """
        self.time_scale = time_scale
        self.timescale_label.setText(f"Time: {time_scale*1e3:.1f}ms/div")

    def set_voltage_scale(self, channel: int, voltage_scale: float):
        """Set voltage scale for a channel.

        Args:
            channel: Channel number
            voltage_scale: Volts per division
        """
        self.voltage_scales[channel] = voltage_scale

    def get_measurements(self, channel: int) -> Optional[Dict[str, float]]:
        """Get measurements for a channel.

        Args:
            channel: Channel number

        Returns:
            Dictionary of measurements or None
        """
        return self._measurements.get(channel)

    def get_statistics(self) -> Dict:
        """Get display statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "waveforms_displayed": self.waveforms_displayed,
            "channels_enabled": sum(1 for enabled in self._channel_enabled.values() if enabled),
            "sample_rate": self.sample_rate,
            "time_scale": self.time_scale
        }
