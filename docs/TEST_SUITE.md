# LabLink Test Suite Guide

Comprehensive guide to testing LabLink using the automated test suite.

## Overview

The LabLink test suite provides comprehensive testing coverage across all components:

- **Unit Tests** - Test individual components in isolation
- **Integration Tests** - Test component interaction
- **End-to-End Tests** - Test complete workflows
- **Mock Equipment Tests** - Test with simulated hardware

**Test Framework:** pytest with async support

**Coverage:** Client, server, and shared components

## Quick Start

### Install Test Dependencies

```bash
# Install pytest and related packages
pip install pytest pytest-asyncio pytest-cov pytest-timeout

# Optional: For parallel test execution
pip install pytest-xdist
```

### Run All Tests

```bash
# Simple run
python run_tests.py

# With coverage report
python run_tests.py --coverage

# With HTML coverage report
python run_tests.py --coverage --html
# Open htmlcov/index.html to view report
```

### Run Specific Test Categories

```bash
# Unit tests only
python run_tests.py --unit

# Integration tests only
python run_tests.py --integration

# End-to-end tests only
python run_tests.py --e2e

# Fast tests only (skip slow tests)
python run_tests.py --fast
```

## Test Organization

### Directory Structure

```
tests/
├── __init__.py                 # Test suite root
├── conftest.py                 # Global fixtures and configuration
│
├── unit/                       # Unit tests
│   ├── __init__.py
│   ├── test_data_buffer.py     # Data buffer tests
│   ├── test_settings.py        # Settings manager tests
│   └── test_websocket_manager.py  # WebSocket tests
│
├── integration/                # Integration tests
│   ├── __init__.py
│   └── test_client_server.py   # Client-server integration
│
├── e2e/                        # End-to-end tests
│   ├── __init__.py
│   └── test_full_workflow.py   # Complete workflow tests
│
└── fixtures/                   # Shared test fixtures
    └── sample_data.json
```

### Test Markers

Tests are categorized using markers:

- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.e2e` - End-to-end tests
- `@pytest.mark.slow` - Tests that take >5 seconds
- `@pytest.mark.requires_hardware` - Tests needing physical equipment
- `@pytest.mark.requires_gui` - Tests needing GUI/display
- `@pytest.mark.asyncio` - Async tests (auto-detected)

## Unit Tests

### Data Buffer Tests

**File:** `tests/unit/test_data_buffer.py`

Tests for circular and sliding window buffers:

```bash
# Run buffer tests
python run_tests.py --file tests/unit/test_data_buffer.py

# Run specific test
python run_tests.py --pattern "test_circular_overwrite"
```

**Coverage:**
- Buffer initialization
- Data append operations
- Circular buffer overwrite behavior
- Sliding window expiration
- Channel data retrieval
- Clear operations

### Settings Tests

**File:** `tests/unit/test_settings.py`

Tests for configuration persistence:

```bash
# Run settings tests
python run_tests.py --file tests/unit/test_settings.py
```

**Coverage:**
- Connection settings (host, port, auto-connect)
- Recent servers list
- Equipment favorites
- Acquisition defaults
- Visualization preferences
- Import/Export functionality
- Window geometry persistence

**Note:** Requires PyQt6. Tests are automatically skipped if not available.

### WebSocket Manager Tests

**File:** `tests/unit/test_websocket_manager.py`

Tests for WebSocket communication:

```bash
# Run WebSocket tests
python run_tests.py --file tests/unit/test_websocket_manager.py
```

**Coverage:**
- Connection/disconnection
- Message sending/receiving
- Stream management
- Message routing
- Handler registration
- Statistics tracking

## Integration Tests

### Client-Server Integration

**File:** `tests/integration/test_client_server.py`

Tests client-server communication:

```bash
# Run integration tests (requires running server)
python run_tests.py --integration
```

**Coverage:**
- Server health check
- Equipment list retrieval
- Equipment discovery
- Client connection
- API endpoint calls

**Prerequisites:** Server must be running on localhost:8000

### Mock Equipment Integration

Tests integration with mock equipment drivers:

```bash
# Run mock equipment tests
python run_tests.py --pattern "mock"
```

**Coverage:**
- Mock oscilloscope operations
- Mock power supply control
- Mock electronic load modes
- Data streaming
- Mode switching behavior

## End-to-End Tests

### Full Workflow Tests

**File:** `tests/e2e/test_full_workflow.py`

Tests complete system workflows:

```bash
# Run e2e tests
python run_tests.py --e2e
```

**Coverage:**
- Equipment discovery workflow
- Data acquisition workflow
- Power supply control workflow
- Oscilloscope capture workflow
- Mock equipment workflows

**Note:** Most e2e tests require either real hardware or a running server with mock equipment.

## Running Tests

### Basic Usage

```bash
# Run all tests
pytest

# Run with test runner
python run_tests.py

# Run specific directory
pytest tests/unit/

# Run specific file
pytest tests/unit/test_settings.py

# Run specific test
pytest tests/unit/test_settings.py::TestSettingsManager::test_connection_settings

# Run tests matching pattern
pytest -k "buffer"
```

### Advanced Usage

```bash
# Verbose output
python run_tests.py --verbose

# Parallel execution (4 workers)
python run_tests.py --parallel 4

# Stop on first failure
pytest -x

# Show local variables on failure
pytest -l

# Only show failed tests
pytest --tb=short --quiet

# Run last failed tests
pytest --lf

# Run failed tests first, then others
pytest --ff
```

### Coverage Reports

```bash
# Terminal coverage report
python run_tests.py --coverage

# HTML coverage report
python run_tests.py --coverage --html
open htmlcov/index.html

# XML coverage report (for CI/CD)
pytest --cov=client --cov=server --cov-report=xml

# Coverage for specific module
pytest --cov=client.utils.settings tests/unit/test_settings.py
```

## Writing Tests

### Unit Test Template

```python
"""Unit tests for MyComponent."""

import pytest
from my_module import MyComponent


@pytest.mark.unit
class TestMyComponent:
    """Test MyComponent class."""

    @pytest.fixture
    def component(self):
        """Create component instance for testing."""
        return MyComponent()

    def test_initialization(self, component):
        """Test component initializes correctly."""
        assert component.value == 0
        assert component.status == "ready"

    def test_operation(self, component):
        """Test component operation."""
        result = component.do_something()
        assert result is True

    def test_error_handling(self, component):
        """Test component handles errors."""
        with pytest.raises(ValueError):
            component.invalid_operation()
```

### Async Test Template

```python
"""Async unit tests."""

import pytest
import asyncio


@pytest.mark.unit
@pytest.mark.asyncio
class TestAsyncComponent:
    """Test async component."""

    @pytest.fixture
    async def component(self):
        """Create and initialize async component."""
        component = AsyncComponent()
        await component.initialize()
        yield component
        await component.cleanup()

    @pytest.mark.asyncio
    async def test_async_operation(self, component):
        """Test async operation."""
        result = await component.async_method()
        assert result is not None
```

### Integration Test Template

```python
"""Integration tests."""

import pytest


@pytest.mark.integration
@pytest.mark.slow
class TestComponentIntegration:
    """Test component integration."""

    def test_components_work_together(self):
        """Test multiple components interact correctly."""
        component_a = ComponentA()
        component_b = ComponentB()

        # Setup interaction
        component_a.register_listener(component_b)

        # Trigger action
        component_a.do_something()

        # Verify result
        assert component_b.received_event is True
```

### Using Fixtures

**Global Fixtures** (in `tests/conftest.py`):

```python
@pytest.fixture
def sample_equipment_info():
    """Sample equipment info for testing."""
    return {
        "id": "test_001",
        "type": "oscilloscope",
        "model": "Test Scope",
        # ...
    }


# Use in tests:
def test_with_fixture(sample_equipment_info):
    """Test using global fixture."""
    assert sample_equipment_info["id"] == "test_001"
```

**Local Fixtures** (in test file):

```python
class TestMyComponent:
    @pytest.fixture
    def component(self):
        """Create component for this test class."""
        component = MyComponent()
        yield component
        component.cleanup()  # Runs after test
```

### Mocking

```python
from unittest.mock import Mock, AsyncMock, patch


def test_with_mock():
    """Test with mocked dependency."""
    mock_dependency = Mock()
    mock_dependency.method.return_value = "mocked result"

    component = MyComponent(dependency=mock_dependency)
    result = component.use_dependency()

    assert result == "mocked result"
    mock_dependency.method.assert_called_once()


@pytest.mark.asyncio
async def test_with_async_mock():
    """Test with async mock."""
    mock_client = AsyncMock()
    mock_client.fetch_data.return_value = {"data": "test"}

    component = MyComponent(client=mock_client)
    result = await component.get_data()

    assert result == {"data": "test"}
```

### Parametrized Tests

```python
@pytest.mark.parametrize("input,expected", [
    (1, 2),
    (2, 4),
    (3, 6),
    (4, 8),
])
def test_doubling(input, expected):
    """Test doubling function with multiple inputs."""
    assert double(input) == expected
```

## Continuous Integration

### GitHub Actions Example

Create `.github/workflows/test.yml`:

```yaml
name: Tests

on: [push, pull_request]

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
        pip install -r server/requirements.txt
        pip install -r client/requirements.txt
        pip install pytest pytest-asyncio pytest-cov

    - name: Run tests
      run: |
        python run_tests.py --coverage --unit --integration

    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

### Pre-commit Hook

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash

# Run fast tests before commit
python run_tests.py --fast

if [ $? -ne 0 ]; then
    echo "Tests failed! Commit aborted."
    exit 1
fi
```

Make executable:
```bash
chmod +x .git/hooks/pre-commit
```

## Troubleshooting

### Tests Not Found

**Issue:** pytest can't find tests

**Solution:**
```bash
# Ensure you're in project root
cd /home/x9x0/LabLink

# Check pytest can find tests
pytest --collect-only

# Add paths explicitly
PYTHONPATH=. pytest
```

### Import Errors

**Issue:** Module import errors during tests

**Solution:**
```bash
# Install in development mode
pip install -e .

# Or add to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)/client:$(pwd)/server"
```

### PyQt6 Tests Fail

**Issue:** GUI tests fail with display errors

**Solution:**
```bash
# Tests will auto-skip if PyQt6 unavailable
pip install PyQt6

# For headless environments, use Xvfb
sudo apt install xvfb
xvfb-run pytest tests/unit/test_settings.py
```

### Async Tests Timeout

**Issue:** Async tests hang or timeout

**Solution:**
```python
# Add timeout marker
@pytest.mark.timeout(10)
async def test_slow_async():
    await slow_operation()

# Or in pytest.ini
[pytest]
timeout = 300  # 5 minutes
```

### Server Tests Skip

**Issue:** Integration tests all skip

**Cause:** Server not running

**Solution:**
```bash
# Start server in background
cd server
python main.py &
SERVER_PID=$!

# Run tests
cd ..
python run_tests.py --integration

# Stop server
kill $SERVER_PID
```

## Best Practices

### 1. Test Naming

```python
# Good
def test_buffer_overwrites_oldest_data():
    """Test that circular buffer overwrites oldest data."""

# Avoid
def test_buffer_1():
    """Test buffer."""
```

### 2. One Assertion per Test (when possible)

```python
# Good
def test_initialization_sets_default_values():
    component = MyComponent()
    assert component.value == 0

def test_initialization_sets_ready_status():
    component = MyComponent()
    assert component.status == "ready"

# Acceptable for related assertions
def test_initialization():
    component = MyComponent()
    assert component.value == 0
    assert component.status == "ready"
    assert component.connected is False
```

### 3. Use Fixtures for Setup

```python
# Good
@pytest.fixture
def buffer():
    return CircularBuffer(size=10, num_channels=2)

def test_append(buffer):
    buffer.append(1.0, np.array([1.0, 2.0]))
    assert buffer.count == 1

# Avoid repeating setup in each test
```

### 4. Clean Up Resources

```python
@pytest.fixture
def connection():
    """Create connection."""
    conn = connect()
    yield conn
    conn.close()  # Cleanup
```

### 5. Mark Slow Tests

```python
@pytest.mark.slow
def test_expensive_operation():
    """Test that takes >5 seconds."""
    # Allow skipping with --fast flag
```

### 6. Skip Appropriately

```python
@pytest.mark.requires_hardware
def test_real_equipment():
    """Test with real hardware."""
    # Automatically skipped unless running with hardware

@pytest.mark.skipif(not PYQT_AVAILABLE, reason="PyQt6 not installed")
def test_gui_component():
    """Test GUI component."""
```

## Test Coverage Goals

### Minimum Coverage Targets

- **Overall:** 80%
- **Critical paths:** 95%
- **Business logic:** 90%
- **UI code:** 60%

### Checking Coverage

```bash
# Generate coverage report
python run_tests.py --coverage

# View specific module coverage
pytest --cov=client.utils.settings --cov-report=term-missing

# Generate detailed HTML report
python run_tests.py --coverage --html
open htmlcov/index.html
```

## Performance Testing

### Benchmark Tests

```python
import time

def test_buffer_performance():
    """Test buffer performance."""
    buffer = CircularBuffer(size=10000, num_channels=4)

    start = time.time()
    for i in range(10000):
        buffer.append(float(i), np.random.rand(4))
    elapsed = time.time() - start

    # Should complete in < 1 second
    assert elapsed < 1.0
```

### Load Testing

```python
@pytest.mark.slow
def test_high_throughput():
    """Test system handles high data throughput."""
    # Test with high message rate
    # Verify no data loss
    # Check memory usage
```

---

*Last updated: 2024-11-08*
