"""Test script for mock equipment drivers."""

import asyncio
import sys
import os

# Add paths to system path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "server", "equipment", "mock"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "shared"))

# Import mock equipment directly
from mock_oscilloscope import MockOscilloscope
from mock_power_supply import MockPowerSupply
from mock_electronic_load import MockElectronicLoad


async def test_mock_oscilloscope():
    """Test mock oscilloscope."""
    print("\n" + "="*60)
    print("Testing Mock Oscilloscope")
    print("="*60)

    scope = MockOscilloscope()

    # Connect
    await scope.connect()
    print(f"✓ Connected: {scope.connected}")

    # Get info
    info = await scope.get_info()
    print(f"✓ Equipment ID: {info.id}")
    print(f"  Manufacturer: {info.manufacturer}")
    print(f"  Model: {info.model}")
    print(f"  Serial: {info.serial_number}")

    # Get status
    status = await scope.get_status()
    print(f"✓ Status: Connected={status.connected}")
    print(f"  Capabilities: {status.capabilities}")

    # Configure channel
    await scope.set_channel(channel=1, enabled=True, scale=1.0, offset=0.0)
    print(f"✓ Configured Channel 1")

    # Set timebase
    await scope.set_timebase(scale=1e-3, offset=0.0)
    print(f"✓ Set timebase to 1ms/div")

    # Get waveform metadata
    waveform = await scope.get_waveform(channel=1)
    print(f"✓ Waveform metadata:")
    print(f"  Sample rate: {waveform.sample_rate/1e9:.1f} GSa/s")
    print(f"  Num samples: {waveform.num_samples}")
    print(f"  Data ID: {waveform.data_id}")

    # Get raw waveform data
    raw_data = await scope.get_waveform_raw(channel=1)
    print(f"✓ Raw waveform data: {len(raw_data)} bytes")

    # Get measurements
    measurements = await scope.get_measurements(channel=1)
    print(f"✓ Measurements:")
    for key, value in measurements.items():
        print(f"  {key}: {value:.6f}")

    # Disconnect
    await scope.disconnect()
    print(f"✓ Disconnected")


async def test_mock_power_supply():
    """Test mock power supply."""
    print("\n" + "="*60)
    print("Testing Mock Power Supply")
    print("="*60)

    psu = MockPowerSupply()

    # Connect
    await psu.connect()
    print(f"✓ Connected: {psu.connected}")

    # Get info
    info = await psu.get_info()
    print(f"✓ Equipment ID: {info.id}")
    print(f"  Manufacturer: {info.manufacturer}")
    print(f"  Model: {info.model}")
    print(f"  Serial: {info.serial_number}")

    # Get status
    status = await psu.get_status()
    print(f"✓ Status: Connected={status.connected}")
    print(f"  Capabilities: {status.capabilities}")

    # Test Channel 1
    print("\n--- Testing Channel 1 ---")

    # Set voltage and current
    await psu.set_voltage(voltage=12.0, channel=1)
    await psu.set_current(current=2.0, channel=1)
    print(f"✓ Set voltage=12V, current=2A")

    # Get setpoints
    setpoints = await psu.get_setpoints(channel=1)
    print(f"✓ Setpoints: V={setpoints['voltage']}V, I={setpoints['current']}A")

    # Enable output
    await psu.set_output(enabled=True, channel=1)
    print(f"✓ Output enabled")

    # Get readings (CV mode with 10 ohm load)
    psu.set_load_resistance(channel=1, resistance=10.0)
    readings = await psu.get_readings(channel=1)
    print(f"✓ Readings (10Ω load):")
    print(f"  Voltage: {readings.voltage_actual:.3f}V (set: {readings.voltage_set}V)")
    print(f"  Current: {readings.current_actual:.3f}A (set: {readings.current_set}A)")
    print(f"  Mode: CV={readings.in_cv_mode}, CC={readings.in_cc_mode}")

    # Test CC mode with 1 ohm load (high current demand)
    psu.set_load_resistance(channel=1, resistance=1.0)
    readings = await psu.get_readings(channel=1)
    print(f"✓ Readings (1Ω load - should hit current limit):")
    print(f"  Voltage: {readings.voltage_actual:.3f}V")
    print(f"  Current: {readings.current_actual:.3f}A")
    print(f"  Mode: CV={readings.in_cv_mode}, CC={readings.in_cc_mode}")

    # Disable output
    await psu.set_output(enabled=False, channel=1)
    print(f"✓ Output disabled")

    # Disconnect
    await psu.disconnect()
    print(f"✓ Disconnected")


async def test_mock_electronic_load():
    """Test mock electronic load."""
    print("\n" + "="*60)
    print("Testing Mock Electronic Load")
    print("="*60)

    load = MockElectronicLoad()

    # Connect
    await load.connect()
    print(f"✓ Connected: {load.connected}")

    # Get info
    info = await load.get_info()
    print(f"✓ Equipment ID: {info.id}")
    print(f"  Manufacturer: {info.manufacturer}")
    print(f"  Model: {info.model}")
    print(f"  Serial: {info.serial_number}")

    # Get status
    status = await load.get_status()
    print(f"✓ Status: Connected={status.connected}")
    print(f"  Capabilities: {status.capabilities}")

    # Simulate 12V power supply connected
    load.simulate_power_supply(voltage=12.0, resistance=0.1)
    print(f"✓ Simulated 12V power supply connected")

    # Test CC mode
    print("\n--- Testing CC Mode (2A) ---")
    await load.set_mode("CC")
    await load.set_current(2.0)
    await load.set_input(enabled=True)

    readings = await load.get_readings()
    print(f"✓ Readings:")
    print(f"  Mode: {readings.mode}")
    print(f"  Setpoint: {readings.setpoint}A")
    print(f"  Voltage: {readings.voltage:.3f}V")
    print(f"  Current: {readings.current:.3f}A")
    print(f"  Power: {readings.power:.3f}W")

    # Test CR mode
    print("\n--- Testing CR Mode (6Ω) ---")
    await load.set_mode("CR")
    await load.set_resistance(6.0)

    readings = await load.get_readings()
    print(f"✓ Readings:")
    print(f"  Mode: {readings.mode}")
    print(f"  Setpoint: {readings.setpoint}Ω")
    print(f"  Voltage: {readings.voltage:.3f}V")
    print(f"  Current: {readings.current:.3f}A")
    print(f"  Power: {readings.power:.3f}W")

    # Test CP mode
    print("\n--- Testing CP Mode (20W) ---")
    await load.set_mode("CP")
    await load.set_power(20.0)

    readings = await load.get_readings()
    print(f"✓ Readings:")
    print(f"  Mode: {readings.mode}")
    print(f"  Setpoint: {readings.setpoint}W")
    print(f"  Voltage: {readings.voltage:.3f}V")
    print(f"  Current: {readings.current:.3f}A")
    print(f"  Power: {readings.power:.3f}W")

    # Disable input
    await load.set_input(enabled=False)
    print(f"✓ Input disabled")

    # Disconnect
    await load.disconnect()
    print(f"✓ Disconnected")


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Mock Equipment Driver Tests")
    print("="*60)

    try:
        await test_mock_oscilloscope()
        await test_mock_power_supply()
        await test_mock_electronic_load()

        print("\n" + "="*60)
        print("✓ All tests passed!")
        print("="*60 + "\n")

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
