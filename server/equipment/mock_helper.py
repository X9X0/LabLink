"""Helper utilities for working with mock equipment."""

import logging
import asyncio
from typing import List, Dict, Optional
from shared.models.equipment import EquipmentType

logger = logging.getLogger(__name__)


class MockEquipmentHelper:
    """Helper class for easily setting up and managing mock equipment."""

    # Default mock equipment configurations
    DEFAULT_MOCK_EQUIPMENT = [
        {
            "resource_string": "MOCK::SCOPE::0",
            "type": EquipmentType.OSCILLOSCOPE,
            "model": "MockScope-2000",
            "name": "Mock Oscilloscope 1"
        },
        {
            "resource_string": "MOCK::PSU::0",
            "type": EquipmentType.POWER_SUPPLY,
            "model": "MockPSU-3000",
            "name": "Mock Power Supply 1"
        },
        {
            "resource_string": "MOCK::LOAD::0",
            "type": EquipmentType.ELECTRONIC_LOAD,
            "model": "MockLoad-1000",
            "name": "Mock Electronic Load 1"
        },
    ]

    @staticmethod
    async def register_default_mock_equipment(equipment_manager) -> List[str]:
        """
        Register default set of mock equipment with the equipment manager.

        Args:
            equipment_manager: EquipmentManager instance

        Returns:
            List of registered equipment IDs

        Example:
            from equipment.manager import EquipmentManager
            from equipment.mock_helper import MockEquipmentHelper

            manager = EquipmentManager()
            await manager.initialize()
            equipment_ids = await MockEquipmentHelper.register_default_mock_equipment(manager)
            print(f"Registered {len(equipment_ids)} mock devices")
        """
        equipment_ids = []

        for config in MockEquipmentHelper.DEFAULT_MOCK_EQUIPMENT:
            try:
                equipment_id = await equipment_manager.connect_device(
                    resource_string=config["resource_string"],
                    equipment_type=config["type"],
                    model=config["model"]
                )
                equipment_ids.append(equipment_id)
                logger.info(f"Registered mock equipment: {config['name']} (ID: {equipment_id})")
            except Exception as e:
                logger.error(f"Failed to register {config['name']}: {e}")

        return equipment_ids

    @staticmethod
    async def register_mock_equipment(
        equipment_manager,
        equipment_type: EquipmentType,
        count: int = 1,
        base_resource_string: Optional[str] = None
    ) -> List[str]:
        """
        Register one or more mock equipment of a specific type.

        Args:
            equipment_manager: EquipmentManager instance
            equipment_type: Type of equipment to register
            count: Number of devices to register (default: 1)
            base_resource_string: Optional custom resource string prefix

        Returns:
            List of registered equipment IDs

        Example:
            # Register 3 mock oscilloscopes
            ids = await MockEquipmentHelper.register_mock_equipment(
                manager,
                EquipmentType.OSCILLOSCOPE,
                count=3
            )
        """
        equipment_ids = []

        # Determine model and resource string based on type
        type_configs = {
            EquipmentType.OSCILLOSCOPE: {
                "model": "MockScope-2000",
                "resource_prefix": base_resource_string or "MOCK::SCOPE::"
            },
            EquipmentType.POWER_SUPPLY: {
                "model": "MockPSU-3000",
                "resource_prefix": base_resource_string or "MOCK::PSU::"
            },
            EquipmentType.ELECTRONIC_LOAD: {
                "model": "MockLoad-1000",
                "resource_prefix": base_resource_string or "MOCK::LOAD::"
            },
        }

        if equipment_type not in type_configs:
            raise ValueError(f"Unsupported equipment type: {equipment_type}")

        config = type_configs[equipment_type]

        for i in range(count):
            resource_string = f"{config['resource_prefix']}{i}"

            try:
                equipment_id = await equipment_manager.connect_device(
                    resource_string=resource_string,
                    equipment_type=equipment_type,
                    model=config["model"]
                )
                equipment_ids.append(equipment_id)
                logger.info(f"Registered mock {equipment_type.value} #{i+1} (ID: {equipment_id})")
            except Exception as e:
                logger.error(f"Failed to register mock {equipment_type.value} #{i+1}: {e}")

        return equipment_ids

    @staticmethod
    def list_mock_resource_strings() -> List[str]:
        """
        Get list of common mock equipment resource strings.

        Returns:
            List of mock resource strings that can be used for connection
        """
        return [
            "MOCK::SCOPE::0",
            "MOCK::SCOPE::1",
            "MOCK::SCOPE::2",
            "MOCK::PSU::0",
            "MOCK::PSU::1",
            "MOCK::PSU::2",
            "MOCK::LOAD::0",
            "MOCK::LOAD::1",
            "MOCK::LOAD::2",
        ]

    @staticmethod
    async def configure_mock_oscilloscope(equipment_manager, equipment_id: str, config: Dict) -> None:
        """
        Configure a mock oscilloscope with custom waveform parameters.

        Args:
            equipment_manager: EquipmentManager instance
            equipment_id: ID of the mock oscilloscope
            config: Configuration dictionary with parameters:
                - channel: Channel number (1-4)
                - waveform_type: "sine", "square", "triangle", or "noise"
                - frequency: Frequency in Hz
                - amplitude: Amplitude in V

        Example:
            await MockEquipmentHelper.configure_mock_oscilloscope(
                manager,
                "scope_abc123",
                {
                    "channel": 1,
                    "waveform_type": "sine",
                    "frequency": 1000.0,
                    "amplitude": 5.0
                }
            )
        """
        equipment = equipment_manager.equipment.get(equipment_id)

        if not equipment:
            raise ValueError(f"Equipment {equipment_id} not found")

        if not hasattr(equipment, 'set_waveform_type'):
            raise ValueError(f"Equipment {equipment_id} is not a mock oscilloscope")

        # Apply configuration
        channel = config.get("channel", 1)

        if "waveform_type" in config:
            equipment.set_waveform_type(channel, config["waveform_type"])

        if "frequency" in config:
            equipment.set_signal_frequency(channel, config["frequency"])

        if "amplitude" in config:
            equipment.set_signal_amplitude(channel, config["amplitude"])

        logger.info(f"Configured mock oscilloscope {equipment_id}: {config}")


# Convenience functions for common use cases

async def setup_demo_lab(equipment_manager) -> Dict[str, str]:
    """
    Set up a complete demo lab with all mock equipment types.

    Returns:
        Dictionary mapping equipment types to IDs

    Example:
        from equipment.manager import EquipmentManager
        from equipment.mock_helper import setup_demo_lab

        manager = EquipmentManager()
        await manager.initialize()
        lab = await setup_demo_lab(manager)

        print(f"Oscilloscope ID: {lab['oscilloscope']}")
        print(f"Power Supply ID: {lab['power_supply']}")
        print(f"Electronic Load ID: {lab['electronic_load']}")
    """
    helper = MockEquipmentHelper()

    equipment_ids = await helper.register_default_mock_equipment(equipment_manager)

    # Return mapping for easy access
    equipment_map = {}
    for equipment_id in equipment_ids:
        equipment = equipment_manager.equipment.get(equipment_id)
        if equipment:
            info = await equipment.get_info()
            if info.type == EquipmentType.OSCILLOSCOPE:
                equipment_map['oscilloscope'] = equipment_id
            elif info.type == EquipmentType.POWER_SUPPLY:
                equipment_map['power_supply'] = equipment_id
            elif info.type == EquipmentType.ELECTRONIC_LOAD:
                equipment_map['electronic_load'] = equipment_id

    return equipment_map


async def setup_multi_scope_lab(equipment_manager, num_scopes: int = 3) -> List[str]:
    """
    Set up a lab with multiple mock oscilloscopes.

    Args:
        equipment_manager: EquipmentManager instance
        num_scopes: Number of oscilloscopes to create

    Returns:
        List of oscilloscope equipment IDs

    Example:
        scope_ids = await setup_multi_scope_lab(manager, num_scopes=3)
        for scope_id in scope_ids:
            print(f"Scope: {scope_id}")
    """
    helper = MockEquipmentHelper()
    return await helper.register_mock_equipment(
        equipment_manager,
        EquipmentType.OSCILLOSCOPE,
        count=num_scopes
    )
