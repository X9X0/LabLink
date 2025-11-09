# LabLink Test Suite

Comprehensive automated testing for the LabLink laboratory equipment control system.

## Quick Start

### 1. Install Test Dependencies

```bash
pip install -r requirements-test.txt
```

### 2. Run Tests

```bash
# Run all tests
python run_tests.py

# Run specific test category
python run_tests.py --unit           # Unit tests only
python run_tests.py --integration    # Integration tests only
python run_tests.py --e2e            # End-to-end tests only

# Run with coverage
python run_tests.py --coverage --html
```

### 3. View Results

```bash
# Terminal output shows pass/fail
# HTML coverage report: htmlcov/index.html
```

## Test Categories

### Unit Tests (`tests/unit/`)

Test individual components in isolation:

- **test_data_buffer.py** - Circular and sliding window buffers
- **test_settings.py** - Configuration persistence (QSettings)
- **test_websocket_manager.py** - WebSocket communication

Run: `python run_tests.py --unit`

### Integration Tests (`tests/integration/`)

Test component interaction:

- **test_client_server.py** - Client-server communication
- **test_mock_equipment.py** - Mock equipment integration

Run: `python run_tests.py --integration`

*Note: Requires server running on localhost:8000*

### End-to-End Tests (`tests/e2e/`)

Test complete workflows:

- **test_full_workflow.py** - Complete system workflows

Run: `python run_tests.py --e2e`

## Test Structure

```
tests/
├── conftest.py              # Global fixtures and configuration
├── unit/                    # Unit tests
├── integration/             # Integration tests
├── e2e/                     # End-to-end tests
└── fixtures/                # Shared test data
```

## Test Markers

- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.e2e` - End-to-end tests
- `@pytest.mark.slow` - Tests taking >5 seconds
- `@pytest.mark.requires_hardware` - Needs physical equipment
- `@pytest.mark.requires_gui` - Needs display/GUI
- `@pytest.mark.asyncio` - Async tests (auto-applied)

## Common Commands

```bash
# Run fast tests only
python run_tests.py --fast

# Run specific test file
python run_tests.py --file tests/unit/test_settings.py

# Run tests matching pattern
python run_tests.py --pattern "buffer"

# Verbose output
python run_tests.py --verbose

# Parallel execution (4 workers)
python run_tests.py --parallel 4

# Coverage report
python run_tests.py --coverage --html
```

## Writing Tests

### Basic Test

```python
import pytest

@pytest.mark.unit
def test_something():
    """Test description."""
    result = do_something()
    assert result == expected
```

### Async Test

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_operation():
    """Test async operation."""
    result = await async_function()
    assert result is not None
```

### Using Fixtures

```python
@pytest.fixture
def my_fixture():
    """Create test fixture."""
    obj = MyObject()
    yield obj
    obj.cleanup()

def test_with_fixture(my_fixture):
    """Test using fixture."""
    my_fixture.do_something()
    assert my_fixture.status == "done"
```

## Coverage Goals

- **Overall:** 80%
- **Critical paths:** 95%
- **Business logic:** 90%
- **UI code:** 60%

## Continuous Integration

The test suite integrates with CI/CD:

```yaml
# .github/workflows/test.yml
- name: Run tests
  run: python run_tests.py --coverage --unit --integration
```

## Documentation

Full testing guide: [docs/TEST_SUITE.md](../docs/TEST_SUITE.md)

## Support

For testing issues:
- Check test logs for error details
- Ensure all dependencies installed
- Verify server is running (for integration tests)
- Use `--verbose` flag for detailed output

---

**Test Framework:** pytest
**Coverage Tool:** pytest-cov
**Python Version:** 3.11+
