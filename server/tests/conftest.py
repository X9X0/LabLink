"""Pytest configuration and fixtures for equipment driver tests."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from pyvisa import ResourceManager


@pytest.fixture
def mock_resource_manager():
    """Create a mock VISA resource manager."""
    mock_rm = MagicMock(spec=ResourceManager)
    return mock_rm


@pytest.fixture
def mock_instrument():
    """Create a mock VISA instrument."""
    mock_inst = MagicMock()
    mock_inst.timeout = 10000
    mock_inst.query = MagicMock(return_value="RIGOL TECHNOLOGIES,DS1104Z,DS1ZA123456789,00.04.04.SP3")
    mock_inst.write = MagicMock()
    mock_inst.close = MagicMock()
    mock_inst.query_binary_values = MagicMock(return_value=[0] * 1000)
    return mock_inst


@pytest.fixture
def mock_resource_manager_with_instrument(mock_resource_manager, mock_instrument):
    """Create a mock resource manager that returns a mock instrument."""
    mock_resource_manager.open_resource = MagicMock(return_value=mock_instrument)
    return mock_resource_manager
