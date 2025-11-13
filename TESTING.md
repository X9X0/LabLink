# LabLink Testing Guide

Complete guide for testing LabLink, including automated tests, mock equipment, and manual verification.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Running Tests](#running-tests)
3. [Mock Equipment Testing](#mock-equipment-testing)
4. [Test Organization](#test-organization)
5. [Writing Tests](#writing-tests)
6. [CI/CD Integration](#cicd-integration)
7. [Manual Testing](#manual-testing)
8. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Prerequisites

```bash
# Install test dependencies
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-timeout pytest-cov

# Verify installation
pytest --version
```

### Run All Tests

```bash
# Run complete test suite
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=client --cov=server --cov-report=html

# Run specific test categories
pytest tests/ -v -m unit          # Unit tests only
pytest tests/ -v -m integration   # Integration tests only
pytest tests/ -v -m "not slow"    # Skip slow tests
```

---

## Running Tests

### Test Structure

```
tests/
├── unit/              # Unit tests for individual components
├── integration/       # Integration tests for component interaction
├── gui/              # GUI-specific tests (require display)
├── hardware/         # Hardware driver tests (require equipment)
└── conftest.py       # Shared fixtures and configuration
```

### Common Test Commands

```bash
# Run specific test directory
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/gui/ -v

# Run specific test file
pytest tests/unit/test_mock_equipment.py -v

# Run specific test function
pytest tests/unit/test_mock_equipment.py::test_mock_oscilloscope_basic -v

# Run tests matching pattern
pytest tests/ -v -k "oscilloscope"
pytest tests/ -v -k "websocket"

# Stop at first failure
pytest tests/ -v -x

# Run last failed tests
pytest tests/ -v --lf

# Show test output (print statements)
pytest tests/ -v -s

# Parallel execution (requires pytest-xdist)
pytest tests/ -v -n auto
```

### Test Markers

Use markers to categorize and filter tests:

```python
@pytest.mark.unit
@pytest.mark.integration
@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.requires_hardware
@pytest.mark.requires_gui
@pytest.mark.asyncio
```

Run tests by marker:

```bash
pytest tests/ -v -m "unit and not slow"
pytest tests/ -v -m "requires_hardware"
pytest tests/ -v -m "not requires_gui"
```

---

## Mock Equipment Testing

### Overview

LabLink provides comprehensive mock equipment drivers for testing without physical hardware. Mock drivers simulate realistic behavior including:

- Configuration persistence
- State management
- Error conditions
- Measurement simulation
- Channel operations
- Safety limits

### Available Mock Equipment

#### 1. Mock Oscilloscope (Rigol DS1054Z)

```python
from server.equipment.mock.oscilloscope import MockRigolDS1054Z

# Create mock oscilloscope
scope = MockRigolDS1054Z("MOCK::SCOPE::001")

# Configure channels
scope.set_channel_enabled(1, True)
scope.set_channel_scale(1, 1.0)  # 1V/div
scope.set_timebase_scale(0.001)  # 1ms/div

# Acquire data
waveform = scope.get_waveform(1)
measurements = scope.measure_all(1)
```

#### 2. Mock Power Supply (Keysight E36312A)

```python
from server.equipment.mock.power_supply import MockKeysightE36312A

# Create mock power supply
psu = MockKeysightE36312A("MOCK::PSU::001")

# Configure channel
psu.set_voltage(1, 5.0)
psu.set_current_limit(1, 1.0)
psu.set_output_enabled(1, True)

# Read measurements
voltage = psu.measure_voltage(1)
current = psu.measure_current(1)
power = psu.measure_power(1)
```

#### 3. Mock Electronic Load (BK Precision 8500)

```python
from server.equipment.mock.electronic_load import MockBKPrecision8500

# Create mock load
load = MockBKPrecision8500("MOCK::LOAD::001")

# Set mode and value
load.set_mode("CC")  # Constant current
load.set_current(2.0)  # 2A
load.set_input_enabled(True)

# Read measurements
voltage = load.measure_voltage()
current = load.measure_current()
power = load.measure_power()
```

### Mock Equipment Features

#### Realistic Behavior

Mock equipment simulates real device behavior:

```python
# Timebase affects waveform resolution
scope.set_timebase_scale(0.001)  # 1ms/div → 1000 points
scope.set_timebase_scale(0.0001)  # 100μs/div → 10000 points

# Output voltage/current affects measurements
psu.set_voltage(1, 5.0)
psu.set_current_limit(1, 1.0)
psu.measure_voltage(1)  # Returns ~5.0V ±1%
psu.measure_current(1)  # Returns realistic current draw
```

#### Error Simulation

Test error handling with simulated errors:

```python
# Channel out of range
scope.set_channel_enabled(5, True)  # Raises ValueError

# Invalid parameter
psu.set_voltage(1, -10.0)  # Raises ValueError

# Safety limits
psu.set_voltage(1, 50.0)  # Raises ValueError (exceeds max)
```

#### State Persistence

Mock equipment maintains state across operations:

```python
# Configuration persists
scope.set_channel_scale(1, 2.0)
scope.set_trigger_level(1.5)
# State is maintained for subsequent operations

# Measurements reflect current state
psu.set_output_enabled(1, False)
psu.measure_current(1)  # Returns 0.0 (output disabled)
```

---

## Test Organization

### Pytest Configuration

Configuration is defined in `pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py *_test.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
timeout = 300
```

### Global Fixtures

Shared fixtures are defined in `tests/conftest.py`:

```python
import pytest
from pathlib import Path

@pytest.fixture(scope="session")
def project_root():
    """Get project root directory."""
    return Path(__file__).parent.parent

@pytest.fixture
def sample_equipment_info():
    """Sample equipment info for testing."""
    return {
        "id": "test_scope_001",
        "type": "oscilloscope",
        "model": "Rigol DS1054Z",
        # ... additional fields
    }
```

### Test Examples

#### Unit Test Example

```python
import pytest
from server.equipment.mock.oscilloscope import MockRigolDS1054Z

@pytest.mark.unit
def test_mock_oscilloscope_basic():
    """Test basic oscilloscope operations."""
    scope = MockRigolDS1054Z("MOCK::SCOPE::001")

    # Test channel configuration
    scope.set_channel_enabled(1, True)
    assert scope.get_channel_enabled(1) is True

    # Test timebase
    scope.set_timebase_scale(0.001)
    assert scope.get_timebase_scale() == 0.001

    # Test waveform acquisition
    waveform = scope.get_waveform(1)
    assert len(waveform) > 0
    assert all(isinstance(x, float) for x in waveform)
```

#### Integration Test Example

```python
import pytest
import asyncio
from client.websocket_client import WebSocketClient

@pytest.mark.integration
@pytest.mark.asyncio
async def test_websocket_streaming():
    """Test WebSocket data streaming."""
    client = WebSocketClient("ws://localhost:8000/ws")

    try:
        await client.connect()

        # Subscribe to equipment data
        await client.subscribe("oscilloscope", "test_scope_001")

        # Receive data
        data = await asyncio.wait_for(client.receive(), timeout=5.0)
        assert data is not None
        assert "waveform" in data

    finally:
        await client.disconnect()
```

#### GUI Test Example

```python
import pytest
from PyQt6.QtWidgets import QApplication
from client.panels.oscilloscope_panel import OscilloscopePanel

@pytest.mark.gui
@pytest.mark.requires_gui
def test_oscilloscope_panel(qtbot, sample_equipment_info):
    """Test oscilloscope panel with mock equipment."""
    panel = OscilloscopePanel(sample_equipment_info)
    qtbot.addWidget(panel)

    # Test UI elements exist
    assert panel.channel1_checkbox is not None
    assert panel.timebase_combo is not None

    # Test interaction
    qtbot.mouseClick(panel.channel1_checkbox, Qt.MouseButton.LeftButton)
    assert panel.channel1_checkbox.isChecked()
```

---

## Writing Tests

### Best Practices

1. **Use Descriptive Names**

```python
# Good
def test_oscilloscope_waveform_acquisition_returns_valid_data():
    pass

# Bad
def test_scope():
    pass
```

2. **Follow AAA Pattern** (Arrange, Act, Assert)

```python
def test_power_supply_voltage_setting():
    # Arrange
    psu = MockKeysightE36312A("MOCK::PSU::001")
    expected_voltage = 5.0

    # Act
    psu.set_voltage(1, expected_voltage)
    actual_voltage = psu.get_voltage(1)

    # Assert
    assert actual_voltage == expected_voltage
```

3. **Test One Thing at a Time**

```python
# Good - focused test
def test_channel_enable():
    scope = MockRigolDS1054Z("MOCK::SCOPE::001")
    scope.set_channel_enabled(1, True)
    assert scope.get_channel_enabled(1) is True

# Bad - testing too much
def test_everything():
    scope = MockRigolDS1054Z("MOCK::SCOPE::001")
    scope.set_channel_enabled(1, True)
    scope.set_timebase_scale(0.001)
    waveform = scope.get_waveform(1)
    # ... many more assertions
```

4. **Use Fixtures for Common Setup**

```python
@pytest.fixture
def configured_oscilloscope():
    """Oscilloscope with standard test configuration."""
    scope = MockRigolDS1054Z("MOCK::SCOPE::001")
    scope.set_channel_enabled(1, True)
    scope.set_channel_scale(1, 1.0)
    scope.set_timebase_scale(0.001)
    return scope

def test_with_fixture(configured_oscilloscope):
    """Test using pre-configured oscilloscope."""
    waveform = configured_oscilloscope.get_waveform(1)
    assert len(waveform) == 1000
```

5. **Test Error Conditions**

```python
def test_invalid_channel_raises_error():
    """Test that invalid channel number raises ValueError."""
    scope = MockRigolDS1054Z("MOCK::SCOPE::001")

    with pytest.raises(ValueError, match="Channel must be between 1 and 4"):
        scope.set_channel_enabled(5, True)
```

6. **Use Parametrize for Multiple Cases**

```python
@pytest.mark.parametrize("channel,scale", [
    (1, 0.5),
    (2, 1.0),
    (3, 2.0),
    (4, 5.0),
])
def test_channel_scales(channel, scale):
    """Test different channel scales."""
    scope = MockRigolDS1054Z("MOCK::SCOPE::001")
    scope.set_channel_scale(channel, scale)
    assert scope.get_channel_scale(channel) == scale
```

---

## CI/CD Integration

### GitHub Actions

LabLink uses GitHub Actions for continuous testing. The workflow is defined in `.github/workflows/test.yml`:

```yaml
name: Run Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-asyncio pytest-timeout pytest-cov

    - name: Run tests
      run: |
        pytest tests/ -v --tb=short \
          -m "not requires_hardware and not requires_gui" \
          --cov=client --cov=server \
          --cov-report=xml \
          --cov-report=term-missing

    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
```

### Test Coverage Goals

- **Overall**: ≥80% coverage
- **Core modules**: ≥90% coverage
- **Mock equipment**: 100% coverage
- **API endpoints**: ≥85% coverage

### Running CI Tests Locally

```bash
# Run the same tests as CI
pytest tests/ -v --tb=short \
  -m "not requires_hardware and not requires_gui" \
  --cov=client --cov=server \
  --cov-report=html \
  --cov-report=term-missing

# View coverage report
open htmlcov/index.html
```

---

## Manual Testing

### Server API Testing

#### 1. Start the Server

```bash
# Development mode
cd server
python main.py --dev

# Production mode
python main.py
```

#### 2. Test Endpoints with curl

**Health Check**:
```bash
curl http://localhost:8000/health
```

**List Equipment**:
```bash
curl http://localhost:8000/api/equipment
```

**Connect to Equipment**:
```bash
curl -X POST http://localhost:8000/api/equipment/connect \
  -H "Content-Type: application/json" \
  -d '{"equipment_id": "test_scope_001"}'
```

**Oscilloscope Control**:
```bash
# Configure channel
curl -X POST http://localhost:8000/api/equipment/oscilloscope/test_scope_001/channel/1/config \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "scale": 1.0,
    "offset": 0.0,
    "coupling": "DC"
  }'

# Get waveform
curl http://localhost:8000/api/equipment/oscilloscope/test_scope_001/waveform/1
```

**Power Supply Control**:
```bash
# Set voltage
curl -X POST http://localhost:8000/api/equipment/power_supply/test_psu_001/channel/1/voltage \
  -H "Content-Type: application/json" \
  -d '{"voltage": 5.0}'

# Enable output
curl -X POST http://localhost:8000/api/equipment/power_supply/test_psu_001/channel/1/output \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'

# Read measurements
curl http://localhost:8000/api/equipment/power_supply/test_psu_001/channel/1/measurements
```

**Electronic Load Control**:
```bash
# Set mode and current
curl -X POST http://localhost:8000/api/equipment/electronic_load/test_load_001/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "CC"}'

curl -X POST http://localhost:8000/api/equipment/electronic_load/test_load_001/current \
  -H "Content-Type: application/json" \
  -d '{"current": 2.0}'

# Enable input
curl -X POST http://localhost:8000/api/equipment/electronic_load/test_load_001/input \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

### WebSocket Testing

Using `websocat` (install: `cargo install websocat`):

```bash
# Connect to WebSocket
websocat ws://localhost:8000/ws

# Subscribe to equipment data
{"type": "subscribe", "equipment_type": "oscilloscope", "equipment_id": "test_scope_001"}

# Unsubscribe
{"type": "unsubscribe", "equipment_type": "oscilloscope", "equipment_id": "test_scope_001"}
```

### Client GUI Testing

```bash
# Start client
cd client
python main.py

# Or run with mock equipment
python main.py --mock
```

**Manual Test Checklist**:

- [ ] Equipment discovery shows available devices
- [ ] Connect to oscilloscope displays panel
- [ ] Channel enable/disable works
- [ ] Timebase changes update waveform
- [ ] Trigger level adjustment works
- [ ] Waveform display updates in real-time
- [ ] Power supply channel controls work
- [ ] Voltage/current settings apply correctly
- [ ] Output enable/disable works
- [ ] Electronic load mode switching works
- [ ] Load value settings apply correctly
- [ ] Measurements update correctly
- [ ] WebSocket connection indicator shows status
- [ ] Error messages display properly

---

## Troubleshooting

### Common Issues

#### 1. Tests Fail to Import Modules

**Error**:
```
ModuleNotFoundError: No module named 'server'
```

**Solution**:
```bash
# Verify Python path in tests/conftest.py
# Should include:
sys.path.insert(0, str(project_root / "client"))
sys.path.insert(0, str(project_root / "server"))
sys.path.insert(0, str(project_root / "shared"))
```

#### 2. Async Tests Timeout

**Error**:
```
asyncio.TimeoutError: Task took too long
```

**Solution**:
```python
# Increase timeout
@pytest.mark.asyncio
@pytest.mark.timeout(60)  # 60 second timeout
async def test_long_operation():
    pass
```

#### 3. GUI Tests Fail on Headless Systems

**Error**:
```
QXcbConnection: Could not connect to display
```

**Solution**:
```bash
# Use virtual display (Linux)
sudo apt-get install xvfb
xvfb-run pytest tests/gui/ -v

# Or skip GUI tests
pytest tests/ -v -m "not requires_gui"
```

#### 4. WebSocket Connection Refused

**Error**:
```
ConnectionRefusedError: [Errno 111] Connection refused
```

**Solution**:
```bash
# Ensure server is running
cd server
python main.py &

# Wait for server to start
sleep 2

# Run tests
pytest tests/integration/test_websocket_streaming.py -v
```

#### 5. Port Already in Use

**Error**:
```
OSError: [Errno 48] Address already in use
```

**Solution**:
```bash
# Find and kill process using port 8000
lsof -ti:8000 | xargs kill -9

# Or use different port
export LABLINK_PORT=8001
python server/main.py
```

### Debug Mode

Enable verbose logging for debugging:

```bash
# Server debug mode
python server/main.py --debug

# Pytest verbose output
pytest tests/ -v -s --log-cli-level=DEBUG
```

### Getting Help

1. **Check logs**: Server logs are in `server/logs/`
2. **Review test output**: Use `-v` and `--tb=long` for detailed tracebacks
3. **Enable debug logging**: Set `log_cli = true` in `pytest.ini`
4. **Run single test**: Isolate failing test with `-k pattern`
5. **Check CI logs**: Review GitHub Actions workflow logs

---

## Test Statistics

Current test coverage (as of v0.10.0):

- **Total tests**: 34+
- **Unit tests**: 28+ (mock equipment, utilities)
- **Integration tests**: 6+ (WebSocket, API)
- **GUI tests**: Available but require display
- **Hardware tests**: Available but require equipment
- **Coverage**: ~85% (client/server combined)

---

## Quick Reference

### Essential Commands

```bash
# Run all tests
pytest tests/ -v

# Run specific category
pytest tests/unit/ -v

# Run with coverage
pytest tests/ -v --cov=client --cov=server

# Run CI tests locally
pytest tests/ -v -m "not requires_hardware and not requires_gui"

# Debug failing test
pytest tests/unit/test_mock_equipment.py::test_specific_function -v -s

# Update snapshots (if using pytest-snapshot)
pytest tests/ --snapshot-update
```

### Test Markers

```bash
-m unit              # Unit tests only
-m integration       # Integration tests
-m "not slow"        # Exclude slow tests
-m "not requires_hardware"  # Skip hardware tests
-m "not requires_gui"       # Skip GUI tests
```

### Coverage Commands

```bash
# Generate HTML report
pytest tests/ --cov=client --cov=server --cov-report=html

# Show missing lines
pytest tests/ --cov=client --cov=server --cov-report=term-missing

# Set minimum coverage (fail if below threshold)
pytest tests/ --cov=client --cov=server --cov-fail-under=80
```

---

## Additional Resources

- **pytest documentation**: https://docs.pytest.org/
- **pytest-asyncio**: https://github.com/pytest-dev/pytest-asyncio
- **pytest-qt**: https://pytest-qt.readthedocs.io/
- **Coverage.py**: https://coverage.readthedocs.io/

For more information, see:
- `tests/README.md` - Test organization details
- `.github/workflows/test.yml` - CI/CD configuration
- `pytest.ini` - Pytest configuration
- `tests/conftest.py` - Global fixtures
