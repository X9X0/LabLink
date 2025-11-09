

# Real-Time Visualization Guide

Complete guide to real-time data visualization in LabLink using pyqtgraph.

## Overview

LabLink provides high-performance real-time visualization widgets for displaying equipment data:

- **RealTimePlotWidget** - Multi-channel time-series plotting with circular buffer
- **WaveformDisplay** - Oscilloscope-style waveform display with measurements
- **PowerChartWidget** - Power supply and electronic load monitoring
- **Data Buffers** - Efficient circular and sliding window buffers

## Features

- **High Performance** - 60 FPS updates with 1000+ points
- **Circular Buffering** - Efficient memory usage for continuous data
- **Multiple Channels** - Plot multiple signals simultaneously
- **Interactive Controls** - Pause, clear, zoom, pan
- **Auto-scaling** - Automatic Y-axis ranging
- **Measurements** - Real-time waveform analysis
- **Statistics** - Track performance and data flow

## Installation

```bash
pip install PyQt6 pyqtgraph numpy
```

## Quick Start

### Basic Real-Time Plot

```python
from PyQt6.QtWidgets import QApplication
from client.ui.widgets import RealTimePlotWidget
import time

app = QApplication([])

# Create plot widget
plot = RealTimePlotWidget(buffer_size=1000)
plot.set_labels(title="Sensor Data", y_label="Temperature", y_units="°C")

# Add channels
plot.add_channel("Sensor 1", color=(255, 0, 0))
plot.add_channel("Sensor 2", color=(0, 255, 0))

# Add legend
plot.add_legend()

# Show widget
plot.show()

# Add data (in your update loop)
t = time.time()
plot.add_data_point(t, {
    "Sensor 1": 25.5,
    "Sensor 2": 26.2
})

app.exec()
```

## RealTimePlotWidget

### Creating a Plot

```python
from client.ui.widgets import RealTimePlotWidget

# Create widget
plot = RealTimePlotWidget(
    buffer_size=1000,  # Number of points to display
    parent=None
)

# Configure labels
plot.set_labels(
    title="Real-Time Data",
    x_label="Time",
    y_label="Value",
    x_units="s",
    y_units="V"
)
```

### Adding Channels

```python
# Add channel with auto color
plot.add_channel("Channel 1")

# Add channel with specific color
plot.add_channel("Channel 2", color=(255, 0, 0), width=2)

# Add multiple channels
for i in range(4):
    plot.add_channel(f"CH{i+1}")
```

### Updating Data

```python
import time

start_time = time.time()

# In your update loop
while True:
    t = time.time() - start_time

    # Add data point
    plot.add_data_point(t, {
        "Channel 1": value1,
        "Channel 2": value2,
        "Channel 3": value3
    })

    time.sleep(0.01)  # 100 Hz
```

### WebSocket Integration

```python
from client.api.client import LabLinkClient

client = LabLinkClient()
await client.connect_websocket()

# Register handler
def handle_data(message):
    equipment_id = message['equipment_id']
    data = message['data']
    timestamp = time.time()

    # Extract values
    plot_data = {
        "Voltage": data.get('voltage_actual', 0),
        "Current": data.get('current_actual', 0)
    }

    plot.add_data_point(timestamp, plot_data)

client.register_stream_data_handler(handle_data)

# Start streaming
await client.start_equipment_stream(
    equipment_id="ps_12345678",
    stream_type="readings",
    interval_ms=100
)
```

### Controls

```python
# Clear data
plot.clear_data()

# Pause/resume (via UI button)
# Set Y-axis range
plot.set_y_range(0, 10)

# Enable auto-range
plot.enable_auto_range(True)

# Get statistics
stats = plot.get_statistics()
print(f"Points: {stats['points_plotted']}")
print(f"Updates: {stats['update_count']}")
```

## WaveformDisplay

### Creating Oscilloscope Display

```python
from client.ui.widgets import WaveformDisplay

# Create display
scope = WaveformDisplay(
    num_channels=4,
    parent=None
)

# Show widget
scope.show()
```

### Updating Waveforms

```python
import numpy as np

# Generate waveform
num_samples = 1000
sample_rate = 1e9  # 1 GSa/s
t = np.linspace(0, num_samples/sample_rate, num_samples)
waveform = 2 * np.sin(2 * np.pi * 1e6 * t)  # 1 MHz sine

# Update channel 1
scope.update_waveform(
    channel=1,
    waveform_data=waveform,
    sample_rate=sample_rate
)
```

### WebSocket Integration

```python
# Register handler
def handle_waveform(message):
    scope.update_waveform_from_message(message)

client.register_stream_data_handler(handle_waveform)

# Start waveform streaming
await client.start_equipment_stream(
    equipment_id="scope_12345678",
    stream_type="waveform",
    interval_ms=100
)
```

### Measurements

```python
# Get measurements for channel
measurements = scope.get_measurements(channel=1)

if measurements:
    print(f"Frequency: {measurements['freq']} Hz")
    print(f"Vpp: {measurements['vpp']} V")
    print(f"Vrms: {measurements['vrms']} V")
```

### Channel Control

```python
# Channels are controlled via UI checkboxes
# Access programmatically:
scope._channel_enabled[1] = False  # Disable channel 1
scope._channel_curves[1].setVisible(False)  # Hide curve
```

## PowerChartWidget

### Creating Power Chart

```python
from client.ui.widgets import PowerChartWidget

# Power supply chart
psu_chart = PowerChartWidget(
    equipment_type="power_supply",
    buffer_size=500
)

# Electronic load chart
load_chart = PowerChartWidget(
    equipment_type="electronic_load",
    buffer_size=500
)
```

### WebSocket Integration

```python
# Register handler
def handle_psu_data(message):
    if message['equipment_id'] == psu_id:
        psu_chart.update_from_message(message)

client.register_stream_data_handler(handle_psu_data)

# Start streaming
await client.start_equipment_stream(
    equipment_id=psu_id,
    stream_type="readings",
    interval_ms=200
)
```

### Getting Current Values

```python
# Get current readings
values = psu_chart.get_current_values()

print(f"Voltage: {values['voltage']} V")
print(f"Current: {values['current']} A")
print(f"Power: {values['power']} W")
print(f"Mode: {values['mode']}")
```

## Data Buffers

### Circular Buffer

```python
from client.utils.data_buffer import CircularBuffer

# Create buffer
buffer = CircularBuffer(
    size=1000,        # Buffer size
    num_channels=3    # Number of channels
)

# Add data
timestamp = time.time()
values = [voltage, current, power]
buffer.append(timestamp, values)

# Get data for channel
time_data, channel_data = buffer.get_data(channel=0)

# Get all channels
time_data, all_data = buffer.get_all_data()
# all_data shape: (num_channels, num_samples)

# Get latest N samples
time_data, latest_data = buffer.get_latest(n=100)

# Check status
print(f"Count: {buffer.get_count()}")
print(f"Full: {buffer.is_full()}")
print(f"Total: {buffer.get_total_count()}")

# Clear
buffer.clear()
```

### Sliding Window Buffer

```python
from client.utils.data_buffer import SlidingWindowBuffer

# Create buffer
buffer = SlidingWindowBuffer(
    window_size=10.0,   # 10 second window
    sample_rate=100.0   # Expected rate
)

# Add data
buffer.append(timestamp, value)

# Get data in window
time_data, data = buffer.get_data()

# Get latest N
time_data, data = buffer.get_latest(n=50)

# Clear
buffer.clear()
```

## Complete Example: Live Power Monitor

```python
import asyncio
import time
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout
from client.api.client import LabLinkClient
from client.ui.widgets import PowerChartWidget

class PowerMonitor(QWidget):
    """Live power supply monitor."""

    def __init__(self):
        super().__init__()

        # Setup UI
        layout = QVBoxLayout(self)

        self.chart = PowerChartWidget(equipment_type="power_supply")
        layout.addWidget(self.chart)

        # Setup client
        self.client = LabLinkClient()
        self.client.register_stream_data_handler(self.on_data)

    def on_data(self, message):
        """Handle incoming data."""
        self.chart.update_from_message(message)

    async def start_monitoring(self, equipment_id: str):
        """Start monitoring equipment."""
        await self.client.connect_websocket()
        await self.client.start_equipment_stream(
            equipment_id=equipment_id,
            stream_type="readings",
            interval_ms=100
        )

    async def stop_monitoring(self):
        """Stop monitoring."""
        await self.client.ws_manager.disconnect()

# Run
app = QApplication([])
monitor = PowerMonitor()
monitor.show()

# Start monitoring
asyncio.run(monitor.start_monitoring("ps_12345678"))

app.exec()
```

## Performance Tips

### Update Rates

```python
# Choose appropriate update rates
# Too fast: High CPU usage, dropped frames
# Too slow: Choppy visualization

# Recommended rates:
# - Waveforms: 50-100ms (10-20 Hz)
# - Measurements: 100-200ms (5-10 Hz)
# - Slow data: 200-1000ms (1-5 Hz)
```

### Buffer Sizes

```python
# Choose appropriate buffer sizes
# Too small: Limited history
# Too large: High memory usage

# Recommended sizes:
# - Fast data (>10 Hz): 500-1000 points
# - Medium data (1-10 Hz): 1000-2000 points
# - Slow data (<1 Hz): 2000-5000 points

# Memory usage: ~8 bytes per point per channel
# 1000 points × 3 channels = ~24 KB
```

### Optimization

```python
# Reduce plot update rate
plot.update_timer.setInterval(100)  # Update every 100ms

# Disable anti-aliasing for better performance
pg.setConfigOptions(antialias=False)

# Use downsampling for large datasets
pg.setConfigOptions(
    useNumba=True,      # Use Numba for speedup
    enableExperimental=True
)
```

## Styling

### Plot Colors

```python
# Use custom color schemes
colors = [
    (255, 100, 100),  # Light red
    (100, 255, 100),  # Light green
    (100, 100, 255),  # Light blue
]

for i, name in enumerate(channel_names):
    plot.add_channel(name, color=colors[i])
```

### Background

```python
# Change background
plot.plot_widget.setBackground('w')  # White
plot.plot_widget.setBackground('k')  # Black
plot.plot_widget.setBackground((30, 30, 30))  # Dark gray
```

### Grid

```python
# Configure grid
plot.plot_widget.showGrid(x=True, y=True, alpha=0.3)

# Hide grid
plot.plot_widget.showGrid(x=False, y=False)
```

## Troubleshooting

### Performance Issues

```python
# Check update rate
stats = plot.get_statistics()
rate = stats['update_count'] / (time.time() - start_time)
print(f"Update rate: {rate:.1f} Hz")

# Reduce buffer size
plot = RealTimePlotWidget(buffer_size=500)  # Smaller buffer

# Increase update interval
plot.update_timer.setInterval(100)  # Slower updates
```

### Memory Issues

```python
# Monitor memory usage
stats = plot.get_statistics()
memory = stats['buffer_usage'] * stats['channels'] * 8  # bytes
print(f"Memory usage: {memory/1024:.1f} KB")

# Clear old data periodically
if stats['points_plotted'] > 10000:
    plot.clear_data()
```

### Display Issues

```python
# Enable auto-range if data not visible
plot.enable_auto_range(True)

# Manually set range
plot.set_y_range(-10, 10)

# Check if channels are added
print(f"Channels: {list(plot._data_buffers.keys())}")
```

## API Reference

### RealTimePlotWidget

- `__init__(buffer_size, parent)` - Create widget
- `add_channel(name, color, width)` - Add data channel
- `remove_channel(name)` - Remove channel
- `add_data_point(timestamp, data)` - Add data point
- `clear_data()` - Clear all data
- `set_labels(title, x_label, y_label, x_units, y_units)` - Set labels
- `set_y_range(min_val, max_val)` - Set Y range
- `enable_auto_range(enable)` - Enable auto-ranging
- `add_legend()` - Add legend
- `get_statistics()` - Get statistics

### WaveformDisplay

- `__init__(num_channels, parent)` - Create display
- `update_waveform(channel, waveform_data, sample_rate)` - Update waveform
- `update_waveform_from_message(message)` - Update from WebSocket message
- `clear_waveforms()` - Clear all waveforms
- `set_time_scale(time_scale)` - Set time scale
- `set_voltage_scale(channel, voltage_scale)` - Set voltage scale
- `get_measurements(channel)` - Get measurements
- `get_statistics()` - Get statistics

### PowerChartWidget

- `__init__(equipment_type, buffer_size, parent)` - Create chart
- `update_from_message(message)` - Update from WebSocket message
- `clear_data()` - Clear data
- `get_current_values()` - Get current readings
- `get_statistics()` - Get statistics

### CircularBuffer

- `__init__(size, num_channels)` - Create buffer
- `append(timestamp, values)` - Add data point
- `get_data(channel)` - Get channel data
- `get_all_data()` - Get all channels
- `get_latest(n)` - Get latest N samples
- `clear()` - Clear buffer
- `get_count()` - Get sample count
- `is_full()` - Check if full

---

*Last updated: 2024-11-08*
