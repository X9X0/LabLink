# Equipment Control Panels Guide

Complete guide to using and developing equipment-specific control panels in LabLink.

## Overview

LabLink provides specialized control panels for different types of laboratory equipment. Each panel is tailored to the specific capabilities and controls of that equipment type, providing an intuitive interface for operation and monitoring.

**Available Panels:**
- **OscilloscopePanel** - Waveform capture and analysis
- **PowerSupplyPanel** - Voltage and current control
- **ElectronicLoadPanel** - Multi-mode load testing (CC/CV/CR/CP)

**Features:**
- Real-time data visualization
- Equipment-specific controls
- Asynchronous command execution
- WebSocket streaming integration
- Persistent settings
- Auto-scaling and measurements

## Quick Start

### Running the Demo

```bash
# Install dependencies
pip install PyQt6 pyqtgraph numpy

# Run equipment panels demo
python test_equipment_panels.py
```

The demo provides:
- All three equipment panels in tabs
- Simulated data generation for testing
- Connection to real LabLink server support
- Interactive controls and real-time updates

### Basic Integration

```python
from PyQt6.QtWidgets import QApplication, QMainWindow
from client.ui.equipment import OscilloscopePanel
from client.api.client import LabLinkClient

app = QApplication([])

# Create client
client = LabLinkClient(host="localhost", api_port=8000, ws_port=8001)

# Create panel
panel = OscilloscopePanel()
panel.set_client(client)

# Set equipment
equipment_info = {
    'model': 'Rigol DS1054Z',
    'manufacturer': 'Rigol',
    'capabilities': {
        'num_channels': 4,
        'max_sample_rate': 1e9,
        'max_bandwidth': 50e6
    }
}
panel.set_equipment('scope_12345678', equipment_info)

# Show panel
panel.show()

app.exec()
```

## Oscilloscope Panel

### Features

**Display Tab:**
- 4-channel waveform display
- Real-time waveform streaming
- Auto-scaling and grid
- Color-coded channels
- Pause/resume/clear controls

**Controls Tab:**
- Timebase configuration (1 ns/div to 5 s/div)
- Channel settings (scale, coupling, offset)
- Trigger controls (mode, source, level)
- Quick actions (autoscale, default setup)

**Measurements Tab:**
- Automated waveform measurements
- Vpp, Vmax, Vmin, Vavg, Vrms
- Frequency and period
- Per-channel measurements

### Usage Example

```python
from client.ui.equipment import OscilloscopePanel
import asyncio

# Create panel
scope = OscilloscopePanel()
scope.set_client(client)

# Configure equipment
scope.set_equipment('scope_001', {
    'model': 'Keysight DSOX1204G',
    'manufacturer': 'Keysight',
    'capabilities': {
        'num_channels': 4,
        'max_sample_rate': 2e9,
        'max_bandwidth': 200e6,
        'memory_depth': 1000000
    }
})

# Start waveform streaming
# User clicks "Start Streaming" button or programmatically:
await client.start_equipment_stream(
    equipment_id='scope_001',
    stream_type='waveform',
    interval_ms=100
)

# Waveforms automatically update via WebSocket
```

### Waveform Data Format

The panel expects waveform data in this format:

```python
{
    'type': 'stream_data',
    'equipment_id': 'scope_001',
    'stream_type': 'waveform',
    'timestamp': 1234567890.123,
    'data': {
        'channels': [1, 2, 3, 4],  # Active channels
        'waveforms': [
            [0.1, 0.2, 0.3, ...],  # CH1 data (list of floats)
            [0.4, 0.5, 0.6, ...],  # CH2 data
            # ... etc
        ],
        'time_scale': 0.001,  # seconds per division
        'voltage_scales': [1.0, 1.0, 2.0, 1.0]  # V/div for each channel
    }
}
```

### Configuration Commands

```python
# Set timebase
await client.send_command(
    equipment_id='scope_001',
    command='set_timebase',
    parameters={'scale': 0.001, 'offset': 0.0}  # 1 ms/div
)

# Configure channel
await client.send_command(
    equipment_id='scope_001',
    command='set_channel',
    parameters={
        'channel': 1,
        'enabled': True,
        'scale': 1.0,  # V/div
        'coupling': 'DC',
        'offset': 0.0
    }
)

# Set trigger
await client.send_command(
    equipment_id='scope_001',
    command='set_trigger',
    parameters={
        'mode': 'normal',
        'source': 'CH1',
        'level': 0.5,
        'slope': 'rising'
    }
)
```

## Power Supply Panel

### Features

**Control Tab:**
- Multi-channel support (up to 3 channels)
- Voltage control (spinbox + slider)
- Current limit control (spinbox + slider)
- Real-time voltage/current/power display
- Output enable/disable
- Quick actions (apply settings, set to zero)

**Monitor Tab:**
- Real-time voltage, current, power plotting
- CV/CC mode indication
- Historical data tracking
- Configurable buffer size

### Usage Example

```python
from client.ui.equipment import PowerSupplyPanel

# Create panel
psu = PowerSupplyPanel()
psu.set_client(client)

# Configure equipment
psu.set_equipment('psu_001', {
    'model': 'Keysight E36312A',
    'manufacturer': 'Keysight',
    'capabilities': {
        'num_channels': 3,
        'max_voltage': 30.0,
        'max_current': 5.0,
        'max_power': 150.0
    }
})

# Controls automatically adjust to equipment limits
# User can set voltage/current via UI or programmatically:
psu.voltage_spin.setValue(12.0)
psu.current_spin.setValue(2.0)
psu.output_checkbox.setChecked(True)

# Apply settings
psu._on_apply_settings()  # Sends commands to equipment
```

### Readings Data Format

```python
{
    'type': 'stream_data',
    'equipment_id': 'psu_001',
    'stream_type': 'readings',
    'timestamp': 1234567890.123,
    'data': {
        'channel': 1,
        'voltage_actual': 12.003,  # Measured voltage
        'current_actual': 1.998,   # Measured current
        'voltage_set': 12.0,       # Setpoint
        'current_set': 2.0,        # Limit
        'in_cv_mode': True,        # Constant voltage mode
        'in_cc_mode': False,       # Constant current mode
        'output_enabled': True
    }
}
```

### Control Commands

```python
# Set voltage
await client.send_command(
    equipment_id='psu_001',
    command='set_voltage',
    parameters={'voltage': 12.0, 'channel': 1}
)

# Set current limit
await client.send_command(
    equipment_id='psu_001',
    command='set_current',
    parameters={'current': 2.0, 'channel': 1}
)

# Enable output
await client.send_command(
    equipment_id='psu_001',
    command='set_output',
    parameters={'enabled': True, 'channel': 1}
)
```

### Multi-Channel Support

```python
# Channel selector (1-3)
channel = psu.channel_selector.value()

# Settings are per-channel
psu.voltage_spin.setValue(12.0)  # CH1: 12V
psu.channel_selector.setValue(2)
psu.voltage_spin.setValue(5.0)   # CH2: 5V
psu.channel_selector.setValue(3)
psu.voltage_spin.setValue(3.3)   # CH3: 3.3V
```

## Electronic Load Panel

### Features

**Control Tab:**
- Mode selection: CC, CV, CR, CP
- Dynamic setpoint controls (change based on mode)
- Real-time voltage/current/power display
- Mode indicator with color coding
- Input enable/disable
- Quick actions (apply settings, set to zero)

**Monitor Tab:**
- Real-time voltage, current, power plotting
- Mode-specific data display
- Historical data tracking

### Usage Example

```python
from client.ui.equipment import ElectronicLoadPanel

# Create panel
load = ElectronicLoadPanel()
load.set_client(client)

# Configure equipment
load.set_equipment('load_001', {
    'model': 'BK Precision 8500',
    'manufacturer': 'BK Precision',
    'capabilities': {
        'max_voltage': 120.0,
        'max_current': 30.0,
        'max_power': 350.0,
        'max_resistance': 10000.0,
        'modes': ['CC', 'CV', 'CR', 'CP']
    }
})

# Set mode and parameters
load.mode_combo.setCurrentText('CC')  # Constant current
load.current_spin.setValue(5.0)       # 5A load
load.input_checkbox.setChecked(True)

# Apply settings
load._on_apply_settings()
```

### Operating Modes

**CC (Constant Current):**
- Load draws constant current regardless of voltage
- Setpoint: Current (A)
- Display: Voltage, current, power
- Color: Green

**CV (Constant Voltage):**
- Load maintains constant voltage
- Setpoint: Voltage (V)
- Display: Voltage, current, power
- Color: Red

**CR (Constant Resistance):**
- Load simulates fixed resistance
- Setpoint: Resistance (Ω)
- Display: Voltage, current, resistance, power
- Color: Orange

**CP (Constant Power):**
- Load draws constant power
- Setpoint: Power (W)
- Display: Voltage, current, power
- Color: Blue

### Readings Data Format

```python
{
    'type': 'stream_data',
    'equipment_id': 'load_001',
    'stream_type': 'readings',
    'timestamp': 1234567890.123,
    'data': {
        'voltage': 12.05,      # Measured voltage
        'current': 4.98,       # Measured current
        'power': 60.01,        # Calculated power
        'resistance': 2.42,    # Calculated/set resistance (CR mode)
        'mode': 'CC',          # Current operating mode
        'setpoint': 5.0,       # Current setpoint value
        'input_enabled': True
    }
}
```

### Control Commands

```python
# Set mode and parameters
await client.send_command(
    equipment_id='load_001',
    command='set_mode',
    parameters={'mode': 'CC'}
)

await client.send_command(
    equipment_id='load_001',
    command='set_current',
    parameters={'current': 5.0}
)

# Enable input
await client.send_command(
    equipment_id='load_001',
    command='set_input',
    parameters={'enabled': True}
)

# For other modes:
# CV mode
await client.send_command(
    equipment_id='load_001',
    command='set_voltage',
    parameters={'voltage': 12.0}
)

# CR mode
await client.send_command(
    equipment_id='load_001',
    command='set_resistance',
    parameters={'resistance': 10.0}
)

# CP mode
await client.send_command(
    equipment_id='load_001',
    command='set_power',
    parameters={'power': 100.0}
)
```

## Creating Custom Equipment Panels

### Panel Structure

All equipment panels should follow this structure:

```python
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from typing import Optional
import asyncio

class CustomEquipmentPanel(QWidget):
    """Control panel for custom equipment."""

    def __init__(self, parent=None):
        """Initialize panel."""
        super().__init__(parent)

        self.client: Optional[LabLinkClient] = None
        self.equipment_id: Optional[str] = None
        self.streaming = False

        self._setup_ui()

    def _setup_ui(self):
        """Set up user interface."""
        layout = QVBoxLayout(self)

        # Add your controls here
        # - Equipment info label
        # - Control widgets
        # - Display widgets
        # - Status indicators

    def set_client(self, client: LabLinkClient):
        """Set API client."""
        self.client = client

    def set_equipment(self, equipment_id: str, info: dict):
        """Set connected equipment."""
        self.equipment_id = equipment_id

        # Update UI based on equipment capabilities
        capabilities = info.get('capabilities', {})
        # Configure controls, ranges, etc.

    def _on_start_monitoring(self):
        """Start real-time monitoring."""
        if not self.client or not self.equipment_id:
            return

        # Register data handler
        self.client.register_stream_data_handler(self._on_data)

        # Start streaming
        asyncio.create_task(self._start_streaming())

    async def _start_streaming(self):
        """Start streaming (async)."""
        await self.client.start_equipment_stream(
            equipment_id=self.equipment_id,
            stream_type='readings',
            interval_ms=100
        )

    def _on_data(self, message: dict):
        """Handle incoming data."""
        if message.get('equipment_id') != self.equipment_id:
            return

        data = message.get('data', {})
        # Update displays with data
```

### Best Practices

**1. Async Command Execution**

Always send commands asynchronously to avoid blocking the UI:

```python
def _on_apply_settings(self):
    """Apply settings button clicked."""
    asyncio.create_task(self._apply_settings_async())

async def _apply_settings_async(self):
    """Apply settings asynchronously."""
    try:
        await self.client.send_command(
            equipment_id=self.equipment_id,
            command='set_parameter',
            parameters={'value': self.spin.value()}
        )
        self.status_label.setText("Settings applied")
    except Exception as e:
        self.status_label.setText(f"Error: {e}")
```

**2. Filter Incoming Messages**

Always filter messages by equipment_id and stream_type:

```python
def _on_data(self, message: dict):
    """Handle data."""
    # Check equipment ID
    if message.get('equipment_id') != self.equipment_id:
        return

    # Check stream type
    if message.get('stream_type') != 'readings':
        return

    # Process data
    data = message.get('data', {})
```

**3. Handle Capabilities**

Adapt UI to equipment capabilities:

```python
def set_equipment(self, equipment_id: str, info: dict):
    """Set equipment."""
    self.equipment_id = equipment_id

    capabilities = info.get('capabilities', {})

    # Set ranges based on capabilities
    max_voltage = capabilities.get('max_voltage', 100.0)
    self.voltage_spin.setMaximum(max_voltage)

    # Enable/disable features
    has_feature = capabilities.get('has_advanced_mode', False)
    self.advanced_btn.setEnabled(has_feature)
```

**4. Provide Visual Feedback**

Update status labels and indicators:

```python
# Mode indicators with colors
if mode == 'CC':
    self.mode_label.setText("Mode: CC")
    self.mode_label.setStyleSheet("color: #00FF00;")
elif mode == 'CV':
    self.mode_label.setText("Mode: CV")
    self.mode_label.setStyleSheet("color: #FF0000;")
```

**5. Use Widgets Effectively**

Combine spinboxes with sliders for better UX:

```python
# Spinbox for precise entry
self.voltage_spin = QDoubleSpinBox()
self.voltage_spin.setRange(0, 30)
self.voltage_spin.setDecimals(3)
self.voltage_spin.valueChanged.connect(self._on_voltage_changed)

# Slider for quick adjustment
self.voltage_slider = QSlider(Qt.Orientation.Horizontal)
self.voltage_slider.setRange(0, 30000)  # millivolts
self.voltage_slider.valueChanged.connect(self._on_slider_changed)

# Keep them synchronized
def _on_voltage_changed(self, value: float):
    self.voltage_slider.blockSignals(True)
    self.voltage_slider.setValue(int(value * 1000))
    self.voltage_slider.blockSignals(False)

def _on_slider_changed(self, value: int):
    voltage = value / 1000.0
    self.voltage_spin.blockSignals(True)
    self.voltage_spin.setValue(voltage)
    self.voltage_spin.blockSignals(False)
```

## Integration with Main Application

### Adding Panels to Main Window

```python
from client.ui.equipment import (
    OscilloscopePanel,
    PowerSupplyPanel,
    ElectronicLoadPanel
)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.client = LabLinkClient(...)

        # Create panel container
        self.equipment_stack = QStackedWidget()

        # Create panels
        self.scope_panel = OscilloscopePanel()
        self.psu_panel = PowerSupplyPanel()
        self.load_panel = ElectronicLoadPanel()

        # Set client for all panels
        for panel in [self.scope_panel, self.psu_panel, self.load_panel]:
            panel.set_client(self.client)

        # Add to stack
        self.equipment_stack.addWidget(self.scope_panel)
        self.equipment_stack.addWidget(self.psu_panel)
        self.equipment_stack.addWidget(self.load_panel)

    def on_equipment_selected(self, equipment_id: str, equipment_info: dict):
        """Handle equipment selection."""
        equipment_type = equipment_info.get('type')

        # Select appropriate panel
        if equipment_type == 'oscilloscope':
            self.scope_panel.set_equipment(equipment_id, equipment_info)
            self.equipment_stack.setCurrentWidget(self.scope_panel)
        elif equipment_type == 'power_supply':
            self.psu_panel.set_equipment(equipment_id, equipment_info)
            self.equipment_stack.setCurrentWidget(self.psu_panel)
        elif equipment_type == 'electronic_load':
            self.load_panel.set_equipment(equipment_id, equipment_info)
            self.equipment_stack.setCurrentWidget(self.load_panel)
```

### Dynamic Panel Loading

For extensibility, load panels dynamically:

```python
# Panel registry
EQUIPMENT_PANELS = {
    'oscilloscope': OscilloscopePanel,
    'power_supply': PowerSupplyPanel,
    'electronic_load': ElectronicLoadPanel,
}

def get_panel_for_equipment(equipment_type: str) -> QWidget:
    """Get appropriate panel for equipment type."""
    panel_class = EQUIPMENT_PANELS.get(equipment_type)
    if panel_class:
        return panel_class()
    else:
        # Return generic panel
        return GenericEquipmentPanel()
```

## Testing Equipment Panels

### Unit Testing

```python
import pytest
from PyQt6.QtWidgets import QApplication
from client.ui.equipment import PowerSupplyPanel
from unittest.mock import Mock, AsyncMock

@pytest.fixture
def app():
    return QApplication([])

@pytest.fixture
def panel(app):
    return PowerSupplyPanel()

def test_panel_initialization(panel):
    """Test panel initializes correctly."""
    assert panel.client is None
    assert panel.equipment_id is None
    assert not panel.streaming

def test_set_equipment(panel):
    """Test setting equipment."""
    info = {
        'model': 'Test PSU',
        'manufacturer': 'Test',
        'capabilities': {
            'max_voltage': 30.0,
            'max_current': 5.0
        }
    }

    panel.set_equipment('test_001', info)

    assert panel.equipment_id == 'test_001'
    assert panel.voltage_spin.maximum() == 30.0
    assert panel.current_spin.maximum() == 5.0

@pytest.mark.asyncio
async def test_apply_settings(panel):
    """Test applying settings."""
    # Mock client
    panel.client = Mock()
    panel.client.send_command = AsyncMock()
    panel.equipment_id = 'test_001'

    # Set values
    panel.voltage_spin.setValue(12.0)
    panel.current_spin.setValue(2.0)

    # Apply
    await panel._apply_settings_async(12.0, 2.0, 1, True)

    # Verify commands sent
    assert panel.client.send_command.call_count == 3
```

### Integration Testing

Use the demo application to test with simulated data:

```bash
python test_equipment_panels.py
```

1. Click "Start Demo Data"
2. Switch between equipment types
3. Verify controls work correctly
4. Check real-time updates
5. Test all modes and features

## Troubleshooting

### Panel Not Updating

**Issue:** Panel displays not updating with streaming data

**Solutions:**
```python
# 1. Verify handler registration
self.client.register_stream_data_handler(self._on_data)

# 2. Check equipment_id filter
if message.get('equipment_id') != self.equipment_id:
    return  # Make sure this matches

# 3. Verify streaming started
await self.client.start_equipment_stream(
    equipment_id=self.equipment_id,
    stream_type='readings',
    interval_ms=100
)
```

### Commands Not Executing

**Issue:** Commands sent but equipment doesn't respond

**Solutions:**
```python
# 1. Check client is set
if not self.client:
    print("Client not set!")
    return

# 2. Verify equipment_id
if not self.equipment_id:
    print("Equipment not set!")
    return

# 3. Add error handling
try:
    await self.client.send_command(...)
except Exception as e:
    print(f"Command failed: {e}")
```

### UI Freezing

**Issue:** UI becomes unresponsive during operations

**Solutions:**
```python
# 1. Always use async for commands
# Bad:
def _on_apply(self):
    self.client.send_command(...)  # Blocks UI!

# Good:
def _on_apply(self):
    asyncio.create_task(self._apply_async())

async def _apply_async(self):
    await self.client.send_command(...)

# 2. Use QTimer for updates
self.update_timer = QTimer()
self.update_timer.timeout.connect(self._update_display)
self.update_timer.start(50)  # 50ms updates
```

## API Reference

### OscilloscopePanel

**Methods:**
- `set_client(client)` - Set LabLinkClient instance
- `set_equipment(equipment_id, info)` - Configure for equipment
- `_on_start_stream()` - Start waveform streaming
- `_on_stop_stream()` - Stop streaming
- `_on_waveform_data(message)` - Handle waveform data
- `_on_get_measurements()` - Get automated measurements

**Properties:**
- `client` - LabLinkClient instance
- `equipment_id` - Connected equipment ID
- `streaming` - Streaming status (bool)
- `waveform_display` - WaveformDisplay widget
- `channel_controls` - Dict of channel control widgets

### PowerSupplyPanel

**Methods:**
- `set_client(client)` - Set LabLinkClient instance
- `set_equipment(equipment_id, info)` - Configure for equipment
- `_on_apply_settings()` - Apply voltage/current settings
- `_on_start_monitoring()` - Start readings stream
- `_on_stop_monitoring()` - Stop stream
- `_on_readings_data(message)` - Handle readings data

**Properties:**
- `client` - LabLinkClient instance
- `equipment_id` - Connected equipment ID
- `num_channels` - Number of channels
- `voltage_spin` - Voltage spinbox
- `current_spin` - Current spinbox
- `output_checkbox` - Output enable checkbox
- `chart` - PowerChartWidget

### ElectronicLoadPanel

**Methods:**
- `set_client(client)` - Set LabLinkClient instance
- `set_equipment(equipment_id, info)` - Configure for equipment
- `_on_apply_settings()` - Apply mode and setpoint
- `_on_mode_changed(index)` - Handle mode change
- `_on_start_monitoring()` - Start readings stream
- `_on_stop_monitoring()` - Stop stream
- `_on_readings_data(message)` - Handle readings data

**Properties:**
- `client` - LabLinkClient instance
- `equipment_id` - Connected equipment ID
- `mode_combo` - Mode selection combobox
- `current_spin`, `voltage_spin`, `resistance_spin`, `power_spin` - Setpoint controls
- `input_checkbox` - Input enable checkbox
- `chart` - PowerChartWidget

---

*Last updated: 2024-11-08*
