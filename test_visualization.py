"""Test real-time visualization widgets."""

import sys
import os
import time
import numpy as np

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "client"))

try:
    from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QLabel
    from PyQt6.QtCore import QTimer
    import pyqtgraph as pg

    from ui.widgets import RealTimePlotWidget, WaveformDisplay, PowerChartWidget
    from utils.data_buffer import CircularBuffer, SlidingWindowBuffer

    PYQT_AVAILABLE = True
except ImportError as e:
    print(f"Error: {e}")
    print("\nRequired packages:")
    print("  pip install PyQt6 pyqtgraph numpy")
    PYQT_AVAILABLE = False
    sys.exit(1)


class VisualizationDemo(QMainWindow):
    """Demo application for visualization widgets."""

    def __init__(self):
        """Initialize demo."""
        super().__init__()

        self.setWindowTitle("LabLink Visualization Demo")
        self.setGeometry(100, 100, 1200, 800)

        # Create tab widget
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Add demo tabs
        self._add_realtime_plot_demo()
        self._add_waveform_demo()
        self._add_power_chart_demo()
        self._add_buffer_demo()

        # Start data generation
        self.data_timer = QTimer()
        self.data_timer.timeout.connect(self._generate_data)
        self.data_timer.start(100)  # 10 Hz

        self.start_time = time.time()
        self.data_count = 0

    def _add_realtime_plot_demo(self):
        """Add real-time plot demo tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Create plot widget
        self.plot_widget = RealTimePlotWidget(buffer_size=500)
        self.plot_widget.set_labels(
            title="Real-Time Multi-Channel Plot",
            x_label="Time",
            y_label="Value",
            x_units="s"
        )

        # Add channels
        self.plot_widget.add_channel("Sine Wave", color=(255, 0, 0))
        self.plot_widget.add_channel("Cosine Wave", color=(0, 255, 0))
        self.plot_widget.add_channel("Noise", color=(0, 0, 255))

        self.plot_widget.add_legend()

        layout.addWidget(self.plot_widget)

        self.tabs.addTab(widget, "Real-Time Plot")

    def _add_waveform_demo(self):
        """Add waveform display demo tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Create waveform display
        self.waveform_display = WaveformDisplay(num_channels=4)
        layout.addWidget(self.waveform_display)

        self.tabs.addTab(widget, "Oscilloscope")

    def _add_power_chart_demo(self):
        """Add power chart demo tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Create power supply chart
        psu_label = QLabel("<h3>Power Supply</h3>")
        layout.addWidget(psu_label)

        self.psu_chart = PowerChartWidget(
            equipment_type="power_supply",
            buffer_size=500
        )
        layout.addWidget(self.psu_chart)

        # Create electronic load chart
        load_label = QLabel("<h3>Electronic Load</h3>")
        layout.addWidget(load_label)

        self.load_chart = PowerChartWidget(
            equipment_type="electronic_load",
            buffer_size=500
        )
        layout.addWidget(self.load_chart)

        self.tabs.addTab(widget, "Power/Load Charts")

    def _add_buffer_demo(self):
        """Add buffer demo tab."""
        from PyQt6.QtWidgets import QTextEdit, QLabel

        widget = QWidget()
        layout = QVBoxLayout(widget)

        info_label = QLabel("<h3>Data Buffer Demo</h3>")
        layout.addWidget(info_label)

        self.buffer_text = QTextEdit()
        self.buffer_text.setReadOnly(True)
        layout.addWidget(self.buffer_text)

        # Create test buffers
        self.circular_buffer = CircularBuffer(size=100, num_channels=2)
        self.sliding_buffer = SlidingWindowBuffer(window_size=5.0, sample_rate=10.0)

        self.tabs.addTab(widget, "Data Buffers")

    def _generate_data(self):
        """Generate synthetic data for demos."""
        t = time.time() - self.start_time
        self.data_count += 1

        # Update real-time plot
        sine_val = np.sin(2 * np.pi * 0.5 * t)
        cos_val = np.cos(2 * np.pi * 0.5 * t)
        noise_val = np.random.randn() * 0.5

        self.plot_widget.add_data_point(t, {
            "Sine Wave": sine_val,
            "Cosine Wave": cos_val,
            "Noise": noise_val
        })

        # Update waveform display (every 5 updates)
        if self.data_count % 5 == 0:
            for channel in range(1, 5):
                # Generate synthetic waveform
                num_samples = 1000
                sample_rate = 1e9
                time_array = np.linspace(0, num_samples / sample_rate, num_samples)

                if channel == 1:
                    # Sine wave
                    freq = 1e6 * (1 + 0.1 * np.sin(t))
                    waveform = 2 * np.sin(2 * np.pi * freq * time_array)
                elif channel == 2:
                    # Square wave
                    freq = 500e3
                    waveform = 3 * np.sign(np.sin(2 * np.pi * freq * time_array))
                elif channel == 3:
                    # Triangle wave
                    freq = 250e3
                    waveform = 1.5 * (2 * np.abs(2 * (freq * time_array - np.floor(freq * time_array + 0.5))) - 1)
                else:
                    # Noise
                    waveform = np.random.randn(num_samples) * 0.5

                self.waveform_display.update_waveform(channel, waveform, sample_rate)

        # Update power supply chart
        voltage = 12.0 + 0.5 * np.sin(2 * np.pi * 0.1 * t)
        current = 2.0 + 0.3 * np.sin(2 * np.pi * 0.15 * t)

        psu_message = {
            'data': {
                'voltage_actual': voltage,
                'current_actual': current,
                'output_enabled': True,
                'in_cv_mode': current < 2.2,
                'in_cc_mode': current >= 2.2
            }
        }
        self.psu_chart.update_from_message(psu_message)

        # Update electronic load chart
        load_voltage = 12.0 + np.random.randn() * 0.1
        load_current = 1.5 + 0.2 * np.sin(2 * np.pi * 0.2 * t)

        load_message = {
            'data': {
                'voltage': load_voltage,
                'current': load_current,
                'mode': 'CC',
                'load_enabled': True
            }
        }
        self.load_chart.update_from_message(load_message)

        # Update buffer demo
        if self.data_count % 10 == 0:
            self._update_buffer_demo(t)

    def _update_buffer_demo(self, t: float):
        """Update buffer demo display."""
        # Add to buffers
        self.circular_buffer.append(t, [np.sin(t), np.cos(t)])
        self.sliding_buffer.append(t, np.sin(t))

        # Display buffer info
        info_text = "=== Circular Buffer ===\n"
        info_text += f"Size: {self.circular_buffer.size}\n"
        info_text += f"Count: {self.circular_buffer.get_count()}\n"
        info_text += f"Total: {self.circular_buffer.get_total_count()}\n"
        info_text += f"Full: {self.circular_buffer.is_full()}\n\n"

        # Get latest data
        time_data, data_array = self.circular_buffer.get_latest(5)
        info_text += "Latest 5 samples:\n"
        for i in range(len(time_data)):
            info_text += f"  t={time_data[i]:.2f}: [{data_array[0][i]:.3f}, {data_array[1][i]:.3f}]\n"

        info_text += "\n=== Sliding Window Buffer ===\n"
        info_text += f"Window: {self.sliding_buffer.window_size}s\n"
        info_text += f"Count: {self.sliding_buffer.get_count()}\n"
        info_text += f"Total: {self.sliding_buffer.get_total_count()}\n\n"

        # Get latest
        time_data, data_array = self.sliding_buffer.get_latest(5)
        info_text += "Latest 5 samples:\n"
        for i in range(len(time_data)):
            info_text += f"  t={time_data[i]:.2f}: {data_array[i]:.3f}\n"

        # Statistics
        info_text += "\n=== Statistics ===\n"
        plot_stats = self.plot_widget.get_statistics()
        info_text += f"Plot updates: {plot_stats['update_count']}\n"
        info_text += f"Plot points: {plot_stats['points_plotted']}\n"

        waveform_stats = self.waveform_display.get_statistics()
        info_text += f"Waveforms displayed: {waveform_stats['waveforms_displayed']}\n"

        psu_stats = self.psu_chart.get_statistics()
        info_text += f"PSU updates: {psu_stats['updates_received']}\n"

        load_stats = self.load_chart.get_statistics()
        info_text += f"Load updates: {load_stats['updates_received']}\n"

        self.buffer_text.setText(info_text)


def main():
    """Run the demo."""
    if not PYQT_AVAILABLE:
        return

    app = QApplication(sys.argv)

    # Set application style
    app.setStyle('Fusion')

    demo = VisualizationDemo()
    demo.show()

    print("\n" + "="*60)
    print("LabLink Visualization Demo")
    print("="*60)
    print("\nFeatures demonstrated:")
    print("  1. Real-Time Plot - Multi-channel time-series plotting")
    print("  2. Oscilloscope - Waveform display with measurements")
    print("  3. Power/Load Charts - Voltage, current, power monitoring")
    print("  4. Data Buffers - Circular and sliding window buffers")
    print("\nAll widgets update in real-time with synthetic data.")
    print("Try the controls: Pause, Clear, channel toggles, etc.")
    print("\n" + "="*60 + "\n")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
