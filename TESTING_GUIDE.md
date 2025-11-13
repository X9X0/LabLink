# LabLink Testing Guide

**Comprehensive guide to testing LabLink with and without hardware**

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Mock Equipment Testing](#mock-equipment-testing)
3. [Automated Test Suite](#automated-test-suite)
4. [GUI Integration Testing](#gui-integration-testing)
5. [CI/CD Integration](#cicd-integration)
6. [Running Tests](#running-tests)
7. [Test Coverage](#test-coverage)
8. [Best Practices](#best-practices)

---

## Overview

LabLink supports comprehensive testing at multiple levels:

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test component interactions with mock equipment
- **End-to-End Tests**: Test complete workflows
- **GUI Tests**: Test client application functionality
- **Performance Tests**: Measure and validate performance

**Key Feature**: All tests can run without physical hardware using **mock equipment**.

---

## Mock Equipment Testing

### Quick Start

```bash
# Run mock equipment test suite
pytest tests/test_mock_equipment.py -v

# Run with coverage
pytest tests/test_mock_equipment.py -v --cov=server/equipment --cov-report=html

# Run specific test
pytest tests/test_mock_equipment.py::test_oscilloscope_waveform_acquisition -v
```

### Test Categories

The mock equipment test suite (`tests/test_mock_equipment.py`) includes:

#### 1. Equipment Manager Tests
- Equipment manager initialization
- Complete mock lab setup
- Device registration

#### 2. Mock Oscilloscope Tests
- Connection and info retrieval
- Waveform acquisition (sine, square, triangle, noise)
- Automated measurements (Vpp, frequency, Vrms)
- Configuration via helper functions
- Multi-channel operation

#### 3. Mock Power Supply Tests
- Voltage and current control
- Output enable/disable
- CV/CC mode simulation
- Measurement readings

#### 4. Mock Electronic Load Tests
- Mode switching (CC, CV, CR, CP)
- Current/voltage/resistance/power control
- Input enable/disable
- Load simulation

#### 5. Multi-Device Tests
- Multiple oscilloscopes
- Concurrent operations
- Full lab workflows

#### 6. Performance Tests
- Acquisition speed benchmarks
- Concurrent operation performance

### Example Test

```python
@pytest.mark.asyncio
async def test_oscilloscope_waveform_acquisition(mock_oscilloscope):
    """Test waveform data acquisition."""
    equipment_id, equipment = mock_oscilloscope

    waveform = await equipment.get_waveform(channel=1)

    assert waveform is not None
    assert waveform.points > 0
    assert len(waveform.voltage_data) == waveform.points
```

---

## Automated Test Suite

### Test Structure

```
tests/
├── conftest.py                    # Shared fixtures
├── test_mock_equipment.py         # Mock equipment tests (40+ tests)
├── unit/                          # Unit tests
├── integration/                   # Integration tests
└── e2e/                           # End-to-end tests
```

### Pytest Fixtures

#### Equipment Manager Fixture
```python
@pytest.fixture
async def equipment_manager():
    """Fixture providing initialized equipment manager."""
    manager = EquipmentManager()
    await manager.initialize()
    yield manager
    await manager.shutdown()
```

#### Mock Lab Fixture
```python
@pytest.fixture
async def mock_lab(equipment_manager):
    """Fixture providing complete mock lab."""
    lab = await setup_demo_lab(equipment_manager)
    yield lab
```

#### Individual Equipment Fixtures
```python
@pytest.fixture
async def mock_oscilloscope(equipment_manager):
    """Fixture providing single mock oscilloscope."""
    equipment_id = await equipment_manager.connect_device(
        resource_string="MOCK::SCOPE::0",
        equipment_type=EquipmentType.OSCILLOSCOPE,
        model="MockScope-2000"
    )
    yield equipment_id, equipment_manager.equipment[equipment_id]
```

### Using Fixtures

```python
@pytest.mark.asyncio
async def test_with_mock_lab(mock_lab, equipment_manager):
    """Test using complete mock lab."""
    scope = equipment_manager.equipment[mock_lab['oscilloscope']]
    psu = equipment_manager.equipment[mock_lab['power_supply']]

    # Your test code here
    waveform = await scope.get_waveform(channel=1)
    assert waveform.points > 0
```

---

## GUI Integration Testing

### GUI Test Script

Test the GUI client with mock equipment:

```bash
# 1. Start server with mock equipment
export LABLINK_ENABLE_MOCK_EQUIPMENT=true
python -m server.main

# 2. In another terminal, run GUI test
python test_gui_with_mock.py
```

### What GUI Tests Cover

- ✅ Main window creation
- ✅ Server connection
- ✅ Mock equipment detection
- ✅ Equipment panel functionality
- ✅ WebSocket connection
- ✅ Real-time data updates

### GUI Test Output

```
INFO - Test 1: Creating main window...
INFO - ✅ Main window created
INFO - Test 2: Connecting to server...
INFO - ✅ Connected to server
INFO - Test 3: Checking for mock equipment...
INFO - Found 3 mock equipment devices
INFO -   - MockScope-2000: scope_abc123
INFO -   - MockPSU-3000: psu_def456
INFO -   - MockLoad-1000: load_ghi789
INFO - ✅ Found 3 mock equipment devices
INFO - Test 4: Testing equipment panel...
INFO - ✅ Equipment panel functional
INFO - Test 5: Testing WebSocket connection...
INFO - ✅ WebSocket connected
INFO - Results: 5 passed, 0 failed
INFO - 🎉 All tests passed!
```

---

## CI/CD Integration

### GitHub Actions Workflow

Automated testing workflow: `.github/workflows/test-with-mock-equipment.yml`

**Features:**
- ✅ Tests on multiple Python versions (3.10, 3.11)
- ✅ Parallel test execution
- ✅ Code coverage reporting
- ✅ Integration tests with running server
- ✅ Lint and format checks
- ✅ Test result summary

**Workflow Jobs:**

1. **test-server**: Run mock equipment test suite
2. **test-integration**: Start server and run integration tests
3. **test-demo-script**: Verify demo script works
4. **lint-and-format**: Code quality checks
5. **test-summary**: Aggregate results

### Triggering Workflows

```bash
# Automatic triggers:
git push origin main           # On push to main
git push origin develop        # On push to develop

# Manual trigger:
# Go to GitHub Actions → Select workflow → "Run workflow"
```

### Viewing Results

Navigate to: `https://github.com/your-repo/actions`

See test results, coverage reports, and logs for each job.

---

## Running Tests

### All Tests

```bash
# Run all mock equipment tests
pytest tests/test_mock_equipment.py -v

# Run all tests in tests directory
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=server --cov=client --cov-report=html
```

### Specific Test Categories

```bash
# Oscilloscope tests only
pytest tests/test_mock_equipment.py -k "oscilloscope" -v

# Power supply tests only
pytest tests/test_mock_equipment.py -k "power_supply" -v

# Performance tests only
pytest tests/test_mock_equipment.py -k "performance" -v
```

### Specific Tests

```bash
# Single test
pytest tests/test_mock_equipment.py::test_oscilloscope_connection -v

# Multiple specific tests
pytest tests/test_mock_equipment.py::test_oscilloscope_connection \
       tests/test_mock_equipment.py::test_power_supply_connection -v
```

### Test Options

```bash
# Verbose output
pytest tests/ -v

# Show print statements
pytest tests/ -s

# Stop on first failure
pytest tests/ -x

# Run last failed tests
pytest tests/ --lf

# Show slowest tests
pytest tests/ --durations=10

# Parallel execution (requires pytest-xdist)
pytest tests/ -n auto
```

---

## Test Coverage

### Generating Coverage Reports

```bash
# Generate HTML coverage report
pytest tests/test_mock_equipment.py --cov=server/equipment --cov-report=html

# Open report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

### Coverage Reports Include

- **Line coverage**: Which lines were executed
- **Branch coverage**: Which branches were taken
- **Function coverage**: Which functions were called
- **Missing lines**: Lines not covered by tests

### Coverage Goals

| Component | Target Coverage |
|-----------|----------------|
| Mock Equipment | 95%+ |
| Equipment Manager | 90%+ |
| API Endpoints | 85%+ |
| Client Code | 80%+ |

---

## Best Practices

### 1. Use Mock Equipment by Default

```python
# ✅ Good: Use mock equipment in tests
@pytest.mark.asyncio
async def test_waveform_acquisition(mock_oscilloscope):
    equipment_id, equipment = mock_oscilloscope
    waveform = await equipment.get_waveform(channel=1)
    assert waveform.points > 0

# ❌ Bad: Require real equipment
async def test_waveform_acquisition():
    # Requires physical oscilloscope - fails in CI/CD
    equipment = connect_to_real_oscilloscope()
    ...
```

### 2. Test at Multiple Levels

```python
# Unit test: Single component
async def test_waveform_generator():
    generator = WaveformGenerator()
    data = generator.generate_sine(1000, 1.0, 1000)
    assert len(data) == 1000

# Integration test: Multiple components
async def test_acquisition_system(mock_oscilloscope):
    # Tests oscilloscope + acquisition manager
    ...

# End-to-end test: Full workflow
async def test_complete_acquisition_workflow(mock_lab):
    # Tests entire system from connection to export
    ...
```

### 3. Use Fixtures for Setup/Teardown

```python
# ✅ Good: Fixture handles cleanup
@pytest.fixture
async def configured_oscilloscope(mock_oscilloscope):
    equipment_id, equipment = mock_oscilloscope
    equipment.set_waveform_type(1, "sine")
    equipment.set_signal_frequency(1, 1000.0)
    yield equipment
    # Cleanup happens automatically

# ❌ Bad: Manual cleanup in every test
async def test_something():
    equipment = await setup_equipment()
    try:
        # test code
        pass
    finally:
        await equipment.disconnect()
```

### 4. Test Error Conditions

```python
@pytest.mark.asyncio
async def test_invalid_channel():
    """Test error handling for invalid channel."""
    equipment_id, equipment = mock_oscilloscope

    with pytest.raises(ValueError):
        await equipment.get_waveform(channel=99)  # Invalid channel
```

### 5. Use Descriptive Test Names

```python
# ✅ Good: Clear what's being tested
async def test_oscilloscope_acquisition_returns_correct_number_of_points():
    ...

# ❌ Bad: Unclear purpose
async def test_oscilloscope_1():
    ...
```

### 6. Keep Tests Fast

```python
# ✅ Good: Fast test
async def test_connection(mock_oscilloscope):
    equipment_id, equipment = mock_oscilloscope
    assert equipment.connected  # Instant

# ⚠️  Avoid: Unnecessary delays
async def test_connection_slow(mock_oscilloscope):
    equipment_id, equipment = mock_oscilloscope
    await asyncio.sleep(5)  # Why?
    assert equipment.connected
```

### 7. Test Isolation

```python
# ✅ Good: Each test is independent
async def test_voltage_set(mock_power_supply):
    equipment_id, equipment = mock_power_supply
    await equipment.set_voltage(12.0)
    # Test doesn't depend on other tests

# ❌ Bad: Tests depend on order
async def test_step_1():
    global voltage
    voltage = 12.0

async def test_step_2():
    # Depends on test_step_1 running first
    assert voltage == 12.0
```

---

## Continuous Integration

### Pre-commit Checks

Add to `.git/hooks/pre-commit`:

```bash
#!/bin/bash
# Run tests before commit
pytest tests/test_mock_equipment.py -q
if [ $? -ne 0 ]; then
    echo "Tests failed. Commit aborted."
    exit 1
fi
```

### Pre-push Checks

Add to `.git/hooks/pre-push`:

```bash
#!/bin/bash
# Run full test suite before push
pytest tests/ -q --cov=server --cov=client
if [ $? -ne 0 ]; then
    echo "Tests failed. Push aborted."
    exit 1
fi
```

---

## Troubleshooting

### Tests Fail with "No module named..."

**Solution**:
```bash
# Ensure PYTHONPATH includes project root
export PYTHONPATH=/path/to/LabLink:$PYTHONPATH
pytest tests/
```

### Tests Timeout

**Solution**:
```bash
# Increase timeout (default: 60s)
pytest tests/ --timeout=120
```

### Mock Equipment Not Found

**Solution**:
```bash
# Ensure mock equipment is enabled
export LABLINK_ENABLE_MOCK_EQUIPMENT=true
python -m server.main
```

### GUI Tests Fail

**Solution**:
```bash
# Ensure server is running
python -m server.main &
sleep 5
python test_gui_with_mock.py
```

---

## Summary

**Testing Workflow:**

1. **Development**: Use mock equipment for rapid iteration
   ```bash
   pytest tests/test_mock_equipment.py -k "test_name" -v
   ```

2. **Before Commit**: Run relevant tests
   ```bash
   pytest tests/test_mock_equipment.py -q
   ```

3. **Before Push**: Run full suite
   ```bash
   pytest tests/ --cov=server --cov=client
   ```

4. **CI/CD**: Automated testing on every push
   - GitHub Actions runs all tests
   - Coverage reported automatically
   - Pull request checks pass/fail

**Key Commands:**

```bash
# Quick test
pytest tests/test_mock_equipment.py -v

# With coverage
pytest tests/test_mock_equipment.py --cov=server/equipment --cov-report=html

# GUI test
python test_gui_with_mock.py

# Demo script
python demo_mock_equipment.py
```

---

## Resources

- **Test Suite**: `tests/test_mock_equipment.py`
- **GUI Test**: `test_gui_with_mock.py`
- **CI/CD Workflow**: `.github/workflows/test-with-mock-equipment.yml`
- **Mock Equipment Guide**: `MOCK_EQUIPMENT_GUIDE.md`
- **pytest Documentation**: https://docs.pytest.org/

---

*For more information on mock equipment, see `MOCK_EQUIPMENT_GUIDE.md`*
