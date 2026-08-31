"""Shared fixtures for instrument driver tests.

These tests exercise the SCPI drivers against a mocked pyvisa layer, so they
run without physical hardware attached. The mocks mirror what the drivers in
server/equipment/base.py actually touch:

- ResourceManager.list_resources()  (validity check before opening)
- ResourceManager.open_resource()   (returns the instrument)
- instrument.timeout                (set after opening)
- instrument.query() / write()      (SCPI traffic)
- instrument.session                (validity check)
- instrument.close()
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../server"))


@pytest.fixture
def mock_instrument():
    """A mock pyvisa instrument session.

    Defaults to a generic *IDN? response; individual tests override
    ``query.return_value`` or ``query.side_effect`` for their own device.
    """
    instrument = MagicMock()
    instrument.session = 1  # non-None marks the session as valid
    instrument.timeout = 10000
    instrument.query.return_value = "MOCK,DEVICE,SERIAL123,1.0.0"
    instrument.write.return_value = None
    instrument.read.return_value = ""
    instrument.close.return_value = None
    # The BK driver reads a byte at a time until it sees the "OK\r" terminator.
    # Without a real bytes value here that loop never terminates and the test
    # session hangs, so default to an immediate terminator.
    instrument.read_bytes.side_effect = lambda n=1: b"OK\r"
    return instrument


@pytest.fixture
def mock_resource_manager(mock_instrument):
    """A mock pyvisa ResourceManager that hands out ``mock_instrument``."""
    manager = MagicMock()
    manager.list_resources.return_value = (
        "USB0::0x1AB1::0x0588::DS1ZA123456789::INSTR",
    )
    manager.open_resource.return_value = mock_instrument
    manager.close.return_value = None
    return manager


@pytest.fixture
def mock_resource_manager_with_instrument(mock_resource_manager):
    """Alias used by the driver tests, which pass it to the driver constructor."""
    return mock_resource_manager
