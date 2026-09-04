#!/usr/bin/env python3
"""
Demo script showing how to use mock equipment in LabLink.

This script demonstrates:
1. Setting up mock equipment without physical hardware
2. Connecting to mock devices
3. Reading data from mock equipment
4. Configuring mock equipment parameters
5. Streaming data from mock equipment

Run with: python demo_mock_equipment.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Import from server and shared packages
from server.equipment.manager import EquipmentManager
from server.equipment.mock_helper import MockEquipmentHelper, setup_demo_lab
from shared.models.equipment import EquipmentType

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def demo_basic_connection():
    """Demo 1: Basic connection to mock equipment."""
    print("\n" + "="*60)
    print("Demo 1: Basic Connection to Mock Equipment")
    print("="*60 + "\n")

    # Initialize equipment manager
    manager = EquipmentManager()
    await manager.initialize()

    # Connect to a mock oscilloscope
    print("Connecting to mock oscilloscope...")
    equipment_id = await manager.connect_device(
        resource_string="MOCK::SCOPE::0",
        equipment_type=EquipmentType.OSCILLOSCOPE,
        model="MockScope-2000"
    )
    print(f"✅ Connected! Equipment ID: {equipment_id}\n")

    # Get equipment info
    equipment = manager.equipment[equipment_id]
    info = await equipment.get_info()
    print(f"Equipment Info:")
    print(f"  Type: {info.type.value}")
    print(f"  Manufacturer: {info.manufacturer}")
    print(f"  Model: {info.model}")
    print(f"  Serial: {info.serial_number}")
    print()

    # Get equipment status
    status = await equipment.get_status()
    print(f"Equipment Status:")
    print(f"  Connected: {status.connected}")
    print(f"  Error: {status.error}")
    print(f"  Capabilities: {status.capabilities}")
    print()

    # Cleanup
    await manager.shutdown()
    print("✅ Demo 1 complete!\n")


async def demo_helper_functions():
    """Demo 2: Using helper functions for easy setup."""
    print("\n" + "="*60)
    print("Demo 2: Using Helper Functions")
    print("="*60 + "\n")

    # Initialize equipment manager
    manager = EquipmentManager()
    await manager.initialize()

    # Set up a complete demo lab with one click
    print("Setting up complete demo lab...")
    lab = await setup_demo_lab(manager)
    print(f"✅ Lab setup complete!\n")

    print(f"Available Equipment:")
    print(f"  Oscilloscope: {lab['oscilloscope']}")
    print(f"  Power Supply: {lab['power_supply']}")
    print(f"  Electronic Load: {lab['electronic_load']}")
    print()

    # Cleanup
    await manager.shutdown()
    print("✅ Demo 2 complete!\n")


async def demo_oscilloscope_waveforms():
    """Demo 3: Reading waveforms from mock oscilloscope."""
    print("\n" + "="*60)
    print("Demo 3: Reading Waveforms from Mock Oscilloscope")
    print("="*60 + "\n")

    # Initialize and connect
    manager = EquipmentManager()
    await manager.initialize()

    equipment_id = await manager.connect_device(
        resource_string="MOCK::SCOPE::0",
        equipment_type=EquipmentType.OSCILLOSCOPE,
        model="MockScope-2000"
    )

    equipment = manager.equipment[equipment_id]

    # Configure waveform parameters
    print("Configuring oscilloscope for 1kHz sine wave...")
    await MockEquipmentHelper.configure_mock_oscilloscope(
        manager,
        equipment_id,
        {
            "channel": 1,
            "waveform_type": "sine",
            "frequency": 1000.0,
            "amplitude": 5.0
        }
    )

    # Acquire waveform
    print("Acquiring waveform data...")
    waveform = await equipment.get_waveform(channel=1)
    print(f"\nWaveform Data:")
    print(f"  Channel: {waveform.channel}")
    print(f"  Points: {waveform.points}")
    print(f"  Voltage Range: [{min(waveform.voltage_data):.3f}, {max(waveform.voltage_data):.3f}] V")
    print(f"  Time Range: [{min(waveform.time_data):.6f}, {max(waveform.time_data):.6f}] s")
    print(f"  Sample Rate: {waveform.sample_rate/1e9:.1f} GSa/s")
    print()

    # Get measurements
    print("Getting automated measurements...")
    measurements = await equipment.get_measurements(channel=1)
    print(f"Measurements:")
    for key, value in measurements.items():
        print(f"  {key}: {value:.3f}")
    print()

    # Try different waveform types
    print("Testing different waveform types...")
    waveform_types = ["sine", "square", "triangle", "noise"]

    for waveform_type in waveform_types:
        # Configure
        equipment.set_waveform_type(1, waveform_type)

        # Acquire
        waveform = await equipment.get_waveform(channel=1)

        # Show summary
        print(f"  {waveform_type.capitalize()}: "
              f"{waveform.points} points, "
              f"Vpp = {max(waveform.voltage_data) - min(waveform.voltage_data):.3f} V")

    print()

    # Cleanup
    await manager.shutdown()
    print("✅ Demo 3 complete!\n")


async def demo_power_supply():
    """Demo 4: Controlling mock power supply."""
    print("\n" + "="*60)
    print("Demo 4: Controlling Mock Power Supply")
    print("="*60 + "\n")

    # Initialize and connect
    manager = EquipmentManager()
    await manager.initialize()

    equipment_id = await manager.connect_device(
        resource_string="MOCK::PSU::0",
        equipment_type=EquipmentType.POWER_SUPPLY,
        model="MockPSU-3000"
    )

    equipment = manager.equipment[equipment_id]

    # Get initial readings
    print("Initial State:")
    readings = await equipment.measure_all()
    print(f"  Voltage: {readings['voltage']:.3f} V")
    print(f"  Current: {readings['current']:.3f} A")
    print(f"  Power: {readings['power']:.3f} W")
    print(f"  Mode: {readings['mode']}")
    print()

    # Set voltage
    print("Setting voltage to 12.0 V...")
    await equipment.set_voltage(12.0)
    await asyncio.sleep(0.1)  # Allow settling

    readings = await equipment.measure_all()
    print(f"  Voltage: {readings['voltage']:.3f} V")
    print()

    # Set current limit
    print("Setting current limit to 2.0 A...")
    await equipment.set_current(2.0)
    await asyncio.sleep(0.1)

    readings = await equipment.measure_all()
    print(f"  Current Limit: {readings['current']:.3f} A")
    print()

    # Enable output
    print("Enabling output...")
    await equipment.enable_output()
    await asyncio.sleep(0.1)

    readings = await equipment.measure_all()
    print(f"  Output: ENABLED")
    print(f"  Voltage: {readings['voltage']:.3f} V")
    print(f"  Current: {readings['current']:.3f} A")
    print(f"  Power: {readings['power']:.3f} W")
    print(f"  Mode: {readings['mode']}")
    print()

    # Disable output
    print("Disabling output...")
    await equipment.disable_output()
    print("  Output: DISABLED")
    print()

    # Cleanup
    await manager.shutdown()
    print("✅ Demo 4 complete!\n")


async def demo_electronic_load():
    """Demo 5: Controlling mock electronic load."""
    print("\n" + "="*60)
    print("Demo 5: Controlling Mock Electronic Load")
    print("="*60 + "\n")

    # Initialize and connect
    manager = EquipmentManager()
    await manager.initialize()

    equipment_id = await manager.connect_device(
        resource_string="MOCK::LOAD::0",
        equipment_type=EquipmentType.ELECTRONIC_LOAD,
        model="MockLoad-1000"
    )

    equipment = manager.equipment[equipment_id]

    # Set constant current mode
    print("Setting Constant Current (CC) mode: 2.0 A")
    await equipment.set_mode("CC")
    await equipment.set_current(2.0)
    await asyncio.sleep(0.1)

    readings = await equipment.measure_all()
    print(f"  Mode: {readings['mode']}")
    print(f"  Current: {readings['current']:.3f} A")
    print(f"  Voltage: {readings['voltage']:.3f} V")
    print(f"  Power: {readings['power']:.3f} W")
    print()

    # Enable input
    print("Enabling input...")
    await equipment.enable_input()
    await asyncio.sleep(0.1)

    readings = await equipment.measure_all()
    print(f"  Input: ENABLED")
    print(f"  Current: {readings['current']:.3f} A")
    print(f"  Voltage: {readings['voltage']:.3f} V")
    print(f"  Power: {readings['power']:.3f} W")
    print()

    # Try different modes
    modes = [("CC", 3.0), ("CV", 5.0), ("CR", 10.0), ("CP", 50.0)]

    print("Testing different load modes:")
    for mode, setpoint in modes:
        await equipment.set_mode(mode)

        if mode == "CC":
            await equipment.set_current(setpoint)
        elif mode == "CV":
            await equipment.set_voltage(setpoint)
        elif mode == "CR":
            await equipment.set_resistance(setpoint)
        elif mode == "CP":
            await equipment.set_power(setpoint)

        await asyncio.sleep(0.05)
        readings = await equipment.measure_all()
        print(f"  {mode} Mode: {readings['voltage']:.2f}V, {readings['current']:.2f}A, {readings['power']:.2f}W")

    print()

    # Disable input
    print("Disabling input...")
    await equipment.disable_input()
    print("  Input: DISABLED")
    print()

    # Cleanup
    await manager.shutdown()
    print("✅ Demo 5 complete!\n")


async def demo_multiple_devices():
    """Demo 6: Working with multiple mock devices simultaneously."""
    print("\n" + "="*60)
    print("Demo 6: Multiple Mock Devices")
    print("="*60 + "\n")

    # Initialize
    manager = EquipmentManager()
    await manager.initialize()

    # Register multiple oscilloscopes
    print("Registering 3 mock oscilloscopes...")
    scope_ids = await MockEquipmentHelper.register_mock_equipment(
        manager,
        EquipmentType.OSCILLOSCOPE,
        count=3
    )
    print(f"✅ Registered {len(scope_ids)} oscilloscopes\n")

    # Configure each with different waveforms
    waveforms = ["sine", "square", "triangle"]
    print("Configuring each with different waveforms:")

    for i, (scope_id, waveform) in enumerate(zip(scope_ids, waveforms)):
        await MockEquipmentHelper.configure_mock_oscilloscope(
            manager,
            scope_id,
            {
                "channel": 1,
                "waveform_type": waveform,
                "frequency": 1000.0 * (i + 1),
                "amplitude": 2.0
            }
        )
        print(f"  Scope {i+1}: {waveform} @ {1000.0 * (i + 1):.0f} Hz")

    print()

    # Acquire from all simultaneously
    print("Acquiring from all oscilloscopes simultaneously...")
    tasks = []
    for scope_id in scope_ids:
        equipment = manager.equipment[scope_id]
        tasks.append(equipment.get_waveform(channel=1))

    waveforms_data = await asyncio.gather(*tasks)

    for i, waveform in enumerate(waveforms_data):
        print(f"  Scope {i+1}: {waveform.points} points, "
              f"Vpp = {max(waveform.voltage_data) - min(waveform.voltage_data):.3f} V")

    print()

    # Cleanup
    await manager.shutdown()
    print("✅ Demo 6 complete!\n")


async def main():
    """Run all demos."""
    print("\n" + "="*60)
    print("LabLink Mock Equipment Demo")
    print("="*60)
    print("\nThis demo shows how to use mock equipment for testing")
    print("without physical hardware.\n")

    demos = [
        ("Basic Connection", demo_basic_connection),
        ("Helper Functions", demo_helper_functions),
        ("Oscilloscope Waveforms", demo_oscilloscope_waveforms),
        ("Power Supply", demo_power_supply),
        ("Electronic Load", demo_electronic_load),
        ("Multiple Devices", demo_multiple_devices),
    ]

    print("Available demos:")
    for i, (name, _) in enumerate(demos, 1):
        print(f"  {i}. {name}")
    print(f"  {len(demos) + 1}. Run all demos")
    print("  0. Exit")
    print()

    try:
        choice = input("Select demo (0-{}): ".format(len(demos) + 1))
        choice = int(choice)

        if choice == 0:
            print("Exiting...")
            return
        elif choice == len(demos) + 1:
            # Run all demos
            for name, demo_func in demos:
                try:
                    await demo_func()
                except Exception as e:
                    logger.error(f"Error in {name} demo: {e}")
                    import traceback
                    traceback.print_exc()
        elif 1 <= choice <= len(demos):
            # Run selected demo
            name, demo_func = demos[choice - 1]
            await demo_func()
        else:
            print("Invalid choice!")
    except ValueError:
        print("Invalid input!")
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*60)
    print("Demo Complete!")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
