# Mock Equipment Drivers

Mock equipment drivers enable testing and development of LabLink without physical hardware. They simulate realistic behavior of oscilloscopes, power supplies, and electronic loads.

## Overview

The mock drivers are located in `server/equipment/mock/` and include:

- **MockOscilloscope** - Simulates oscilloscope with realistic waveform generation
- **MockPowerSupply** - Simulates programmable power supply with CV/CC modes
- **MockElectronicLoad** - Simulates electronic load with CC/CV/CR/CP modes

## Features

### MockOscilloscope
- 4-channel oscilloscope simulation
- Realistic waveform generation (sine, square, triangle, noise)
- Configurable frequency, amplitude, and waveform type per channel
- Automated measurements (Vpp, Vrms, Vavg, frequency, etc.)
- Trigger modes (AUTO, NORM, SINGLE)
- 1 GSa/s sample rate, 1000 points memory depth

### MockPowerSupply
- 3-channel power supply simulation
- Realistic CV/CC mode switching based on load
- Configurable load resistance per channel
- Voltage and current limits per channel
- Measurement noise simulation
- Channel specifications:
  - CH1/CH2: 30V, 3A
  - CH3: 5V, 3A

### MockElectronicLoad
- Multiple operating modes: CC, CV, CR, CP
- Realistic load behavior based on source voltage
- Configurable source simulation
- Power limiting (300W max)
- Voltage/current/power measurements with noise

## Installation

The mock drivers are already integrated into LabLink. No additional hardware or VISA drivers required.

### Dependencies

```bash
pip install numpy pydantic
```

## Usage

### Via Equipment Manager

The equipment manager automatically recognizes mock equipment when you use `MOCK::` resource strings:

```python
from server.equipment.manager import equipment_manager
from shared.models.equipment import EquipmentType

# Initialize equipment manager
await equipment_manager.initialize()

# Connect mock oscilloscope
scope_id = await equipment_manager.connect_device(
    resource_string="MOCK::SCOPE::0",
    equipment_type=EquipmentType.OSCILLOSCOPE,
    model="MockScope"
)

# Connect mock power supply
psu_id = await equipment_manager.connect_device(
    resource_string="MOCK::PSU::0",
    equipment_type=EquipmentType.POWER_SUPPLY,
    model="MockPSU"
)

# Connect mock electronic load
load_id = await equipment_manager.connect_device(
    resource_string="MOCK::LOAD::0",
    equipment_type=EquipmentType.ELECTRONIC_LOAD,
    model="MockLoad"
)
```

### Direct Usage

You can also use mock equipment directly:

```python
from server.equipment.mock import MockOscilloscope, MockPowerSupply, MockElectronicLoad

# Create and connect oscilloscope
scope = MockOscilloscope()
await scope.connect()

# Configure channel
await scope.set_channel(channel=1, enabled=True, scale=1.0, offset=0.0)

# Get waveform
waveform = await scope.get_waveform(channel=1)
raw_data = await scope.get_waveform_raw(channel=1)

# Get measurements
measurements = await scope.get_measurements(channel=1)
print(f"Frequency: {measurements['freq']} Hz")
print(f"Vpp: {measurements['vpp']} V")
```

## Configuring Mock Behavior

### Oscilloscope Waveform Configuration

```python
# Set waveform type for channel 1
scope.set_waveform_type(channel=1, waveform_type="sine")  # sine, square, triangle, noise

# Set frequency
scope.set_signal_frequency(channel=1, frequency=1000.0)  # Hz

# Set amplitude
scope.set_signal_amplitude(channel=1, amplitude=2.0)  # V
```

### Power Supply Load Simulation

```python
# Simulate 10 ohm load on channel 1
psu.set_load_resistance(channel=1, resistance=10.0)

# Simulate short circuit
psu.simulate_short_circuit(channel=1)

# Simulate open circuit
psu.simulate_open_circuit(channel=1)

# Set voltage and current
await psu.set_voltage(voltage=12.0, channel=1)
await psu.set_current(current=2.0, channel=1)
await psu.set_output(enabled=True, channel=1)

# Get readings
readings = await psu.get_readings(channel=1)
print(f"Mode: CV={readings.in_cv_mode}, CC={readings.in_cc_mode}")
print(f"Voltage: {readings.voltage_actual}V")
print(f"Current: {readings.current_actual}A")
```

### Electronic Load Source Simulation

```python
# Simulate 12V power supply connected to load
load.simulate_power_supply(voltage=12.0, resistance=0.1)

# Or set manually
load.set_source_voltage(15.0)
load.set_source_resistance(0.05)

# Set to CC mode
await load.set_mode("CC")
await load.set_current(2.0)
await load.set_input(enabled=True)

# Get readings
readings = await load.get_readings()
print(f"Mode: {readings.mode}")
print(f"Voltage: {readings.voltage}V")
print(f"Current: {readings.current}A")
print(f"Power: {readings.power}W")
```

## Example: End-to-End Demo

```python
import asyncio
from server.equipment.mock import MockOscilloscope, MockPowerSupply, MockElectronicLoad

async def demo():
    # Create mock equipment
    scope = MockOscilloscope()
    psu = MockPowerSupply()
    load = MockElectronicLoad()

    # Connect all devices
    await scope.connect()
    await psu.connect()
    await load.connect()

    # Configure oscilloscope
    scope.set_waveform_type(channel=1, waveform_type="sine")
    scope.set_signal_frequency(channel=1, frequency=1000.0)
    scope.set_signal_amplitude(channel=1, amplitude=5.0)

    # Get oscilloscope measurements
    measurements = await scope.get_measurements(channel=1)
    print(f"Oscilloscope - Freq: {measurements['freq']}Hz, Vpp: {measurements['vpp']:.2f}V")

    # Configure power supply
    await psu.set_voltage(voltage=12.0, channel=1)
    await psu.set_current(current=2.0, channel=1)
    await psu.set_output(enabled=True, channel=1)

    # Get power supply readings
    psu_readings = await psu.get_readings(channel=1)
    print(f"PSU - Voltage: {psu_readings.voltage_actual:.2f}V, Current: {psu_readings.current_actual:.2f}A")

    # Configure electronic load
    load.simulate_power_supply(voltage=12.0)
    await load.set_mode("CC")
    await load.set_current(1.5)
    await load.set_input(enabled=True)

    # Get load readings
    load_readings = await load.get_readings()
    print(f"Load - Voltage: {load_readings.voltage:.2f}V, Power: {load_readings.power:.2f}W")

    # Cleanup
    await scope.disconnect()
    await psu.disconnect()
    await load.disconnect()

if __name__ == "__main__":
    asyncio.run(demo())
```

## API Reference

### MockOscilloscope

#### Connection
- `async connect()` - Connect to mock oscilloscope
- `async disconnect()` - Disconnect from mock oscilloscope
- `async get_info()` - Get equipment information
- `async get_status()` - Get equipment status

#### Channel Control
- `async set_channel(channel, enabled, scale, offset, coupling)` - Configure channel
- `async set_timebase(scale, offset)` - Set timebase settings
- `set_waveform_type(channel, waveform_type)` - Set waveform type
- `set_signal_frequency(channel, frequency)` - Set signal frequency
- `set_signal_amplitude(channel, amplitude)` - Set signal amplitude

#### Data Acquisition
- `async get_waveform(channel)` - Get waveform metadata
- `async get_waveform_raw(channel)` - Get raw waveform data
- `async get_measurements(channel)` - Get automated measurements

#### Trigger Control
- `async trigger_single()` - Single trigger
- `async trigger_run()` - Continuous triggering
- `async trigger_stop()` - Stop triggering
- `async autoscale()` - Run autoscale

### MockPowerSupply

#### Connection
- `async connect()` - Connect to mock power supply
- `async disconnect()` - Disconnect
- `async get_info()` - Get equipment information
- `async get_status()` - Get equipment status

#### Output Control
- `async set_voltage(voltage, channel)` - Set output voltage
- `async set_current(current, channel)` - Set current limit
- `async set_output(enabled, channel)` - Enable/disable output
- `async get_readings(channel)` - Get voltage/current readings
- `async get_setpoints(channel)` - Get voltage/current setpoints

#### Mock Configuration
- `set_load_resistance(channel, resistance)` - Set simulated load
- `simulate_short_circuit(channel)` - Simulate short circuit
- `simulate_open_circuit(channel)` - Simulate open circuit

### MockElectronicLoad

#### Connection
- `async connect()` - Connect to mock load
- `async disconnect()` - Disconnect
- `async get_info()` - Get equipment information
- `async get_status()` - Get equipment status

#### Load Control
- `async set_mode(mode)` - Set operating mode (CC, CV, CR, CP)
- `async set_current(current)` - Set current (CC mode)
- `async set_voltage(voltage)` - Set voltage (CV mode)
- `async set_resistance(resistance)` - Set resistance (CR mode)
- `async set_power(power)` - Set power (CP mode)
- `async set_input(enabled)` - Enable/disable load
- `async get_readings()` - Get voltage/current/power readings

#### Mock Configuration
- `set_source_voltage(voltage)` - Set simulated source voltage
- `set_source_resistance(resistance)` - Set simulated source resistance
- `simulate_power_supply(voltage, resistance)` - Simulate power supply connection

## Testing

Run the test script to verify mock equipment functionality:

```bash
python3 test_mock_equipment.py
```

## Use Cases

### Development
- Develop and test client UI without hardware
- Test WebSocket streaming with realistic data
- Develop data visualization features
- Test equipment control logic

### Testing
- Unit tests for equipment commands
- Integration tests for acquisition pipeline
- End-to-end system tests
- Performance testing with realistic loads

### Demonstration
- Demo LabLink features to users
- Training sessions
- Screenshots and documentation
- Trade shows and presentations

## Limitations

- Mock equipment doesn't simulate all edge cases
- Timing may not match real hardware exactly
- Some advanced features may not be implemented
- No simulation of hardware failures or communication errors

## Future Enhancements

- [ ] More waveform types (sawtooth, pulse, arbitrary)
- [ ] Multi-channel correlation for power supply
- [ ] Realistic measurement delays
- [ ] Configurable error injection
- [ ] State persistence
- [ ] Hardware fault simulation
- [ ] Web-based equipment simulator UI

## Contributing

To add new mock equipment:

1. Create new file in `server/equipment/mock/`
2. Implement the same interface as real equipment
3. Add to `server/equipment/mock/__init__.py`
4. Update `manager.py` to recognize the mock model
5. Add documentation and examples
6. Write tests

---

*Last updated: 2024-11-08*
