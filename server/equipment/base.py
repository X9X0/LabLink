"""Base class for all equipment."""

import logging
from abc import ABC, abstractmethod
from typing import Optional, Any
import asyncio
from pyvisa import ResourceManager
from pyvisa.resources import MessageBasedResource

from shared.models.equipment import EquipmentInfo, EquipmentStatus, EquipmentType, ConnectionType

logger = logging.getLogger(__name__)


class BaseEquipment(ABC):
    """Base class for all lab equipment."""

    def __init__(self, resource_manager: ResourceManager, resource_string: str):
        """Initialize equipment."""
        self.resource_manager = resource_manager
        self.resource_string = resource_string
        self.instrument: Optional[MessageBasedResource] = None
        self.connected = False
        self.cached_info: Optional[EquipmentInfo] = None
        self._lock = asyncio.Lock()

    async def connect(self):
        """Connect to the equipment."""
        async with self._lock:
            try:
                # Open the resource
                self.instrument = self.resource_manager.open_resource(self.resource_string)

                # Set timeout (10 seconds)
                self.instrument.timeout = 10000

                # Verify connection with IDN query
                idn = await self._query("*IDN?")
                logger.info(f"Connected to device: {idn}")

                self.connected = True

                # Cache equipment info
                self.cached_info = await self.get_info()

            except Exception as e:
                logger.error(f"Failed to connect to {self.resource_string}: {e}")
                self.connected = False
                raise

    async def disconnect(self):
        """Disconnect from the equipment."""
        async with self._lock:
            if self.instrument:
                try:
                    self.instrument.close()
                    logger.info(f"Disconnected from {self.resource_string}")
                except Exception as e:
                    logger.error(f"Error disconnecting: {e}")
                finally:
                    self.instrument = None
                    self.connected = False

    async def _write(self, command: str):
        """Write a command to the instrument."""
        if not self.instrument or not self.connected:
            raise RuntimeError("Equipment not connected")

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.instrument.write, command)
        except Exception as e:
            logger.error(f"Error writing command '{command}': {e}")
            raise

    async def _query(self, command: str) -> str:
        """Query the instrument and return response."""
        if not self.instrument or not self.connected:
            raise RuntimeError("Equipment not connected")

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, self.instrument.query, command)
            return response.strip()
        except Exception as e:
            logger.error(f"Error querying '{command}': {e}")
            raise

    async def _query_binary(self, command: str) -> bytes:
        """Query the instrument and return binary response."""
        if not self.instrument or not self.connected:
            raise RuntimeError("Equipment not connected")

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, self.instrument.query_binary_values, command, datatype='B')
            return bytes(response)
        except Exception as e:
            logger.error(f"Error querying binary '{command}': {e}")
            raise

    @abstractmethod
    async def get_info(self) -> EquipmentInfo:
        """Get equipment information."""
        pass

    @abstractmethod
    async def get_status(self) -> EquipmentStatus:
        """Get current equipment status."""
        pass

    @abstractmethod
    async def execute_command(self, command: str, parameters: dict) -> Any:
        """Execute a command on the equipment."""
        pass

    def _determine_connection_type(self) -> ConnectionType:
        """Determine connection type from resource string."""
        resource_upper = self.resource_string.upper()
        if "USB" in resource_upper:
            return ConnectionType.USB
        elif "ASRL" in resource_upper or "COM" in resource_upper:
            return ConnectionType.SERIAL
        elif "TCPIP" in resource_upper:
            return ConnectionType.ETHERNET
        elif "GPIB" in resource_upper:
            return ConnectionType.GPIB
        return ConnectionType.USB  # Default
