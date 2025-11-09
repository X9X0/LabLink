"""Pytest configuration and global fixtures."""

import pytest
import sys
import os
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "client"))
sys.path.insert(0, str(project_root / "server"))
sys.path.insert(0, str(project_root / "shared"))


# Pytest configuration
def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers", "unit: Unit tests for individual components"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests for component interaction"
    )
    config.addinivalue_line(
        "markers", "e2e: End-to-end tests for full system"
    )
    config.addinivalue_line(
        "markers", "slow: Tests that take significant time to run"
    )
    config.addinivalue_line(
        "markers", "requires_hardware: Tests that require physical equipment"
    )
    config.addinivalue_line(
        "markers", "requires_gui: Tests that require GUI/display"
    )


@pytest.fixture(scope="session")
def project_root():
    """Get project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def client_root(project_root):
    """Get client directory."""
    return project_root / "client"


@pytest.fixture(scope="session")
def server_root(project_root):
    """Get server directory."""
    return project_root / "server"


@pytest.fixture
def temp_dir(tmp_path):
    """Provide temporary directory for tests."""
    return tmp_path


@pytest.fixture
def sample_equipment_info():
    """Sample equipment info for testing."""
    return {
        "id": "test_scope_001",
        "type": "oscilloscope",
        "model": "Rigol DS1054Z",
        "manufacturer": "Rigol",
        "resource": "USB0::0x1AB1::0x04CE::DS1ZA123456789::INSTR",
        "capabilities": {
            "num_channels": 4,
            "max_sample_rate": 1e9,
            "max_bandwidth": 50e6,
            "memory_depth": 12000000,
        },
        "status": "connected",
    }


@pytest.fixture
def sample_psu_info():
    """Sample power supply info for testing."""
    return {
        "id": "test_psu_001",
        "type": "power_supply",
        "model": "Keysight E36312A",
        "manufacturer": "Keysight",
        "resource": "USB0::0x0957::0x0F07::MY12345678::INSTR",
        "capabilities": {
            "num_channels": 3,
            "max_voltage": 30.0,
            "max_current": 5.0,
            "max_power": 150.0,
        },
        "status": "connected",
    }


@pytest.fixture
def sample_load_info():
    """Sample electronic load info for testing."""
    return {
        "id": "test_load_001",
        "type": "electronic_load",
        "model": "BK Precision 8500",
        "manufacturer": "BK Precision",
        "resource": "USB0::0x1AB1::0x0E11::LOAD123456::INSTR",
        "capabilities": {
            "max_voltage": 120.0,
            "max_current": 30.0,
            "max_power": 350.0,
            "max_resistance": 10000.0,
            "modes": ["CC", "CV", "CR", "CP"],
        },
        "status": "connected",
    }
