# Mock Equipment Guide

**LabLink Mock Equipment System**

Test your LabLink applications without physical hardware using realistic mock equipment drivers.

---

## 🎯 Overview

LabLink includes a complete mock equipment system that simulates real laboratory instruments without requiring any physical hardware. This is perfect for:

- **Development**: Build and test features without equipment access
- **Testing**: Create comprehensive test suites with CI/CD
- **Demos**: Demonstrate LabLink capabilities anywhere
- **Training**: Learn LabLink without risking expensive equipment
- **Debugging**: Reproduce issues in controlled environment

### Available Mock Equipment

| Equipment | Model | Features |
|-----------|-------|----------|
| **Oscilloscope** | MockScope-2000 | 4 channels, realistic waveform generation (sine, square, triangle, noise), configurable frequency/amplitude |
| **Power Supply** | MockPSU-3000 | Voltage/current control, CV/CC mode simulation, output enable/disable, realistic settling |
| **Electronic Load** | MockLoad-1000 | CC/CV/CR/CP modes, input enable/disable, realistic load simulation |

---

## 🚀 Quick Start

### Method 1: Auto-Register on Server Startup (Easiest)

Set environment variable before starting server:

```bash
# Enable mock equipment
export LABLINK_ENABLE_MOCK_EQUIPMENT=true

# Start server
python -m server.main
```

The server will automatically register:
- 1x Mock Oscilloscope
- 1x Mock Power Supply
- 1x Mock Electronic Load

**Check the logs:**
```
INFO - Mock equipment enabled - registering mock devices...
INFO - Registered 3 mock equipment devices
INFO -   - MockScope-2000 (oscilloscope): scope_abc123
INFO -   - MockPSU-3000 (power_supply): psu_def456
INFO -   - MockLoad-1000 (electronic_load): load_ghi789
```

### Method 2: Manual Registration via API

```python
import requests

# Connect to mock oscilloscope
response = requests.post("http://localhost:8000/api/equipment/connect", json={
    "resource_string": "MOCK::SCOPE::0",
    "equipment_type": "oscilloscope",
    "model": "MockScope-2000"
})

equipment_id = response.json()["equipment_id"]
print(f"Connected to mock oscilloscope: {equipment_id}")
```

### Method 3: Using Helper Functions

```python
from equipment.manager import EquipmentManager
from equipment.mock_helper import setup_demo_lab

# Initialize manager
manager = EquipmentManager()
await manager.initialize()

# One-line lab setup
lab = await setup_demo_lab(manager)

print(f"Oscilloscope: {lab['oscilloscope']}")
print(f"Power Supply: {lab['power_supply']}")
print(f"Electronic Load: {lab['electronic_load']}")
```

---

## 📋 Mock Equipment Resource Strings

Mock equipment uses special resource strings with the `MOCK::` prefix:

| Resource String | Equipment Type |
|----------------|----------------|
| `MOCK::SCOPE::0` | Oscilloscope #0 |
| `MOCK::SCOPE::1` | Oscilloscope #1 |
| `MOCK::PSU::0` | Power Supply #0 |
| `MOCK::PSU::1` | Power Supply #1 |
| `MOCK::LOAD::0` | Electronic Load #0 |
| `MOCK::LOAD::1` | Electronic Load #1 |

You can create multiple instances by changing the number.

---

## 🔧 Configuration

### Environment Variables

```bash
# Enable mock equipment auto-registration
LABLINK_ENABLE_MOCK_EQUIPMENT=true

# Specify which types to register (comma-separated)
LABLINK_MOCK_EQUIPMENT_TYPES="oscilloscope,power_supply,electronic_load"
```

### Server Settings

In `server/config/settings.py` or via environment:

```python
enable_mock_equipment = True  # Auto-register on startup
mock_equipment_types = "oscilloscope,power_supply,electronic_load"
```

---

## 📖 Usage Examples

### Example 1: Mock Oscilloscope Waveforms

```python
from equipment.manager import EquipmentManager
from equipment.mock_helper import MockEquipmentHelper
from shared.models.equipment import EquipmentType

# Setup
manager = EquipmentManager()
await manager.initialize()

# Connect
equipment_id = await manager.connect_device(
    resource_string="MOCK::SCOPE::0",
    equipment_type=EquipmentType.OSCILLOSCOPE,
    model="MockScope-2000"
)

equipment = manager.equipment[equipment_id]

# Configure for 1kHz sine wave
await MockEquipmentHelper.configure_mock_oscilloscope(
    manager,
    equipment_id,
    {
        "channel": 1,
        "waveform_type": "sine",  # sine, square, triangle, noise
        "frequency": 1000.0,      # Hz
        "amplitude": 5.0          # V
    }
)

# Acquire waveform
waveform = await equipment.get_waveform(channel=1)
print(f"Acquired {waveform.points} points")
print(f"Voltage range: {min(waveform.voltage_data):.3f} to {max(waveform.voltage_data):.3f} V")

# Get measurements
measurements = await equipment.get_measurements(channel=1)
print(f"Vpp: {measurements['vpp']:.3f} V")
print(f"Frequency: {measurements['frequency']:.1f} Hz")
```

**Output:**
```
Acquired 1000 points
Voltage range: -5.000 to 5.000 V
Vpp: 10.000 V
Frequency: 1000.0 Hz
```

### Example 2: Mock Power Supply Control

```python
# Connect to mock power supply
equipment_id = await manager.connect_device(
    resource_string="MOCK::PSU::0",
    equipment_type=EquipmentType.POWER_SUPPLY,
    model="MockPSU-3000"
)

equipment = manager.equipment[equipment_id]

# Set voltage and current limit
await equipment.set_voltage(12.0)  # 12V
await equipment.set_current(2.0)   # 2A limit

# Enable output
await equipment.enable_output()

# Read measurements
readings = await equipment.measure_all()
print(f"Voltage: {readings['voltage']:.3f} V")
print(f"Current: {readings['current']:.3f} A")
print(f"Power: {readings['power']:.3f} W")
print(f"Mode: {readings['mode']}")  # CV or CC
```

**Output:**
```
Voltage: 12.000 V
Current: 1.950 A
Power: 23.400 W
Mode: CV
```

### Example 3: Mock Electronic Load

```python
# Connect to mock load
equipment_id = await manager.connect_device(
    resource_string="MOCK::LOAD::0",
    equipment_type=EquipmentType.ELECTRONIC_LOAD,
    model="MockLoad-1000"
)

equipment = manager.equipment[equipment_id]

# Set constant current mode
await equipment.set_mode("CC")     # CC, CV, CR, CP
await equipment.set_current(3.0)   # 3A

# Enable input
await equipment.enable_input()

# Read measurements
readings = await equipment.measure_all()
print(f"Current: {readings['current']:.3f} A")
print(f"Voltage: {readings['voltage']:.3f} V")
print(f"Power: {readings['power']:.3f} W")
print(f"Mode: {readings['mode']}")
```

**Output:**
```
Current: 3.000 A
Voltage: 24.050 V
Power: 72.150 W
Mode: CC
```

### Example 4: Multiple Mock Devices

```python
from equipment.mock_helper import MockEquipmentHelper

# Register 3 oscilloscopes at once
scope_ids = await MockEquipmentHelper.register_mock_equipment(
    manager,
    EquipmentType.OSCILLOSCOPE,
    count=3
)

# Configure each with different waveforms
waveforms = ["sine", "square", "triangle"]
for scope_id, waveform in zip(scope_ids, waveforms):
    await MockEquipmentHelper.configure_mock_oscilloscope(
        manager,
        scope_id,
        {
            "channel": 1,
            "waveform_type": waveform,
            "frequency": 1000.0,
            "amplitude": 3.0
        }
    )

# Acquire from all simultaneously
tasks = [manager.equipment[sid].get_waveform(channel=1) for sid in scope_ids]
waveforms_data = await asyncio.gather(*tasks)

for i, waveform in enumerate(waveforms_data):
    print(f"Scope {i+1}: {waveform.points} points")
```

**Output:**
```
Scope 1: 1000 points
Scope 2: 1000 points
Scope 3: 1000 points
```

---

## 🎮 Interactive Demo Script

Run the interactive demo:

```bash
python demo_mock_equipment.py
```

**Demo Menu:**
```
Available demos:
  1. Basic Connection
  2. Helper Functions
  3. Oscilloscope Waveforms
  4. Power Supply
  5. Electronic Load
  6. Multiple Devices
  7. Run all demos
  0. Exit

Select demo (0-7):
```

Each demo shows practical usage of mock equipment with detailed output.

---

## 🧪 Testing with Mock Equipment

### Unit Tests

```python
import pytest
from equipment.manager import EquipmentManager
from equipment.mock_helper import setup_demo_lab

@pytest.fixture
async def mock_lab():
    """Fixture providing mock equipment."""
    manager = EquipmentManager()
    await manager.initialize()
    lab = await setup_demo_lab(manager)
    yield lab
    await manager.shutdown()

async def test_oscilloscope_acquisition(mock_lab):
    """Test waveform acquisition."""
    scope_id = mock_lab['oscilloscope']
    equipment = manager.equipment[scope_id]

    waveform = await equipment.get_waveform(channel=1)

    assert waveform.points > 0
    assert len(waveform.voltage_data) == waveform.points
    assert len(waveform.time_data) == waveform.points
```

### Integration Tests

```python
async def test_data_acquisition_with_mock():
    """Test data acquisition system with mock oscilloscope."""
    from acquisition import acquisition_manager

    # Connect mock oscilloscope
    equipment_id = await manager.connect_device(
        "MOCK::SCOPE::0",
        EquipmentType.OSCILLOSCOPE,
        "MockScope-2000"
    )

    # Start acquisition
    acq_id = await acquisition_manager.start_acquisition(
        equipment_id=equipment_id,
        channels=[1],
        mode="continuous",
        sample_rate=1000,
        duration=5.0
    )

    # Wait for acquisition
    await asyncio.sleep(5.5)

    # Stop and get data
    await acquisition_manager.stop_acquisition(acq_id)
    data = acquisition_manager.get_acquisition_data(acq_id)

    assert len(data) > 0
    assert "channel_1" in data
```

---

## 🎯 CI/CD Integration

### GitHub Actions Example

```yaml
name: Test with Mock Equipment

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-test.txt

      - name: Run tests with mock equipment
        env:
          LABLINK_ENABLE_MOCK_EQUIPMENT: 'true'
        run: |
          pytest tests/ -v --cov=server --cov=client
```

---

## 🔧 Advanced Configuration

### Custom Waveform Parameters

```python
# Access mock oscilloscope directly for fine control
mock_scope = manager.equipment[equipment_id]

# Set waveform parameters
mock_scope.set_waveform_type(1, "sine")
mock_scope.set_signal_frequency(1, 2500.0)  # 2.5 kHz
mock_scope.set_signal_amplitude(1, 3.3)      # 3.3V
mock_scope.noise_level = 0.01                # Low noise

# Set timebase
await mock_scope.set_timebase(scale=1e-3, offset=0.0)  # 1ms/div

# Set channel parameters
await mock_scope.set_channel(
    channel=1,
    enabled=True,
    scale=1.0,    # 1V/div
    offset=0.0,   # 0V
    coupling="DC"
)
```

### Custom Mock Behaviors

Mock equipment can be configured to simulate various behaviors:

```python
# Power supply with CV/CC mode transitions
psu = manager.equipment[psu_id]
await psu.set_voltage(12.0)
await psu.set_current(1.0)  # Low current limit

# Simulated load will cause CC mode
psu.simulated_load_current = 1.5  # Exceeds limit
await psu.enable_output()

readings = await psu.measure_all()
# mode will be "CC" because load exceeds current limit
```

---

## 📊 Mock Equipment Characteristics

### Oscilloscope

- **Channels**: 4
- **Bandwidth**: 200 MHz (simulated)
- **Sample Rate**: 1 GSa/s (configurable)
- **Memory Depth**: 1000 points (configurable)
- **Waveform Types**: Sine, Square, Triangle, Noise
- **Noise Level**: Configurable (default 20mV)
- **Frequency Range**: 1 Hz - 100 MHz
- **Amplitude Range**: 0 - 10V

### Power Supply

- **Channels**: 1-3 (depending on model)
- **Voltage Range**: 0 - 30V
- **Current Range**: 0 - 3A
- **Modes**: Constant Voltage (CV), Constant Current (CC)
- **Settling Time**: ~100ms (simulated)
- **Accuracy**: ±0.1% (simulated)
- **Output Enable/Disable**: Yes

### Electronic Load

- **Modes**: CC, CV, CR, CP
- **Current Range**: 0 - 30A
- **Voltage Range**: 0 - 150V
- **Power Range**: 0 - 200W
- **Resistance Range**: 0.1 - 10kΩ
- **Input Enable/Disable**: Yes
- **Thermal Simulation**: Optional

---

## 🐛 Troubleshooting

### Mock Equipment Not Registered

**Problem**: Server starts but no mock equipment appears

**Solution**:
```bash
# Check environment variable is set
echo $LABLINK_ENABLE_MOCK_EQUIPMENT

# Should output: true

# Check server logs for mock equipment registration
tail -f logs/server.log | grep -i mock
```

### Connection Errors

**Problem**: Can't connect to mock equipment

**Solution**:
- Verify resource string starts with `MOCK::`
- Check equipment type matches resource string
- Ensure equipment manager is initialized

```python
# Correct:
await manager.connect_device("MOCK::SCOPE::0", EquipmentType.OSCILLOSCOPE, "MockScope-2000")

# Incorrect:
await manager.connect_device("MOCK::SCOPE", EquipmentType.OSCILLOSCOPE, "MockScope-2000")  # Missing number
```

### Import Errors

**Problem**: `ImportError: cannot import name 'MockEquipmentHelper'`

**Solution**:
```bash
# Ensure you're in the correct directory
cd /path/to/LabLink

# Run with proper Python path
PYTHONPATH=. python demo_mock_equipment.py
```

---

## 📚 API Reference

### MockEquipmentHelper

```python
class MockEquipmentHelper:
    @staticmethod
    async def register_default_mock_equipment(equipment_manager) -> List[str]

    @staticmethod
    async def register_mock_equipment(
        equipment_manager,
        equipment_type: EquipmentType,
        count: int = 1,
        base_resource_string: Optional[str] = None
    ) -> List[str]

    @staticmethod
    async def configure_mock_oscilloscope(
        equipment_manager,
        equipment_id: str,
        config: Dict
    ) -> None

    @staticmethod
    def list_mock_resource_strings() -> List[str]
```

### Convenience Functions

```python
async def setup_demo_lab(equipment_manager) -> Dict[str, str]

async def setup_multi_scope_lab(
    equipment_manager,
    num_scopes: int = 3
) -> List[str]
```

---

## 💡 Best Practices

1. **Use Environment Variables**: Enable mock equipment via `LABLINK_ENABLE_MOCK_EQUIPMENT=true` for easy on/off
2. **CI/CD Integration**: Always use mock equipment in automated tests
3. **Realistic Tests**: Configure mock equipment to match your real equipment's behavior
4. **Clean Shutdown**: Always call `await manager.shutdown()` to clean up resources
5. **Multiple Instances**: Use numbered resource strings (`MOCK::SCOPE::0`, `MOCK::SCOPE::1`) for multiple devices
6. **Helper Functions**: Use `MockEquipmentHelper` for common patterns instead of manual setup

---

## 🎓 Next Steps

- **Try the demo script**: `python demo_mock_equipment.py`
- **Write tests**: Use mock equipment in your test suite
- **Explore the code**: Check `server/equipment/mock/` for implementation details
- **Contribute**: Add new mock equipment types or enhance existing ones

---

## 📝 Summary

Mock equipment enables:
- ✅ Development without hardware
- ✅ Comprehensive testing
- ✅ CI/CD automation
- ✅ Demos anywhere
- ✅ Risk-free experimentation

**Quick Commands:**
```bash
# Enable mock equipment
export LABLINK_ENABLE_MOCK_EQUIPMENT=true

# Run server
python -m server.main

# Run demo
python demo_mock_equipment.py

# Run tests
pytest tests/ -v
```

---

*For more information, see:*
- `server/equipment/mock/` - Mock equipment implementation
- `server/equipment/mock_helper.py` - Helper utilities
- `demo_mock_equipment.py` - Interactive demo script
- API documentation: `http://localhost:8000/docs`
