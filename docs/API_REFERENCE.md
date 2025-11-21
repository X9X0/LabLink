## LabLink API Reference

## Base URL

```
http://<server-ip>:8000
```

## REST API Endpoints

### System Endpoints

#### GET /
Health check endpoint.

**Response:**
```json
{
  "name": "LabLink Server",
  "version": "0.1.0",
  "status": "running"
}
```

#### GET /health
Detailed health status with connected device count.

**Response:**
```json
{
  "status": "healthy",
  "connected_devices": 2
}
```

### Equipment Management

#### POST /api/equipment/discover
Discover available VISA devices on the system.

**Response:**
```json
{
  "resources": [
    "USB0::0x1AB1::0x04CE::DS2A123456789::INSTR",
    "ASRL/dev/ttyUSB0::INSTR"
  ]
}
```

#### POST /api/equipment/connect
Connect to a device.

**Request Body:**
```json
{
  "resource_string": "USB0::0x1AB1::0x04CE::DS2A123456789::INSTR",
  "equipment_type": "oscilloscope",
  "model": "MSO2072A"
}
```

**Response:**
```json
{
  "equipment_id": "scope_abc12345",
  "status": "connected"
}
```

#### POST /api/equipment/disconnect/{equipment_id}
Disconnect a device.

**Response:**
```json
{
  "equipment_id": "scope_abc12345",
  "status": "disconnected"
}
```

#### GET /api/equipment/list
List all connected devices.

**Response:**
```json
[
  {
    "id": "scope_abc12345",
    "type": "oscilloscope",
    "manufacturer": "Rigol",
    "model": "MSO2072A",
    "serial_number": "DS2A123456789",
    "connection_type": "usb",
    "resource_string": "USB0::0x1AB1::0x04CE::DS2A123456789::INSTR",
    "nickname": null
  }
]
```

#### GET /api/equipment/{equipment_id}/status
Get status of a specific device.

**Response:**
```json
{
  "id": "scope_abc12345",
  "connected": true,
  "error": null,
  "firmware_version": "00.01.02.00.00",
  "capabilities": {
    "num_channels": 2,
    "bandwidth": "70MHz",
    "sample_rate": "2GSa/s"
  }
}
```

#### POST /api/equipment/{equipment_id}/command
Execute a command on a device.

**Request Body:**
```json
{
  "command_id": "cmd_001",
  "equipment_id": "scope_abc12345",
  "action": "get_measurements",
  "parameters": {
    "channel": 1
  },
  "timestamp": "2025-01-01T12:00:00"
}
```

**Response:**
```json
{
  "command_id": "cmd_001",
  "success": true,
  "data": {
    "vpp": 3.2,
    "vmax": 1.6,
    "vmin": -1.6,
    "freq": 1000.0
  },
  "error": null,
  "timestamp": "2025-01-01T12:00:00.123"
}
```

### Data Acquisition

#### POST /api/data/stream/configure
Configure data streaming for a device.

**Request Body:**
```json
{
  "equipment_id": "scope_abc12345",
  "stream_type": "measurements",
  "interval_ms": 100,
  "enabled": true,
  "buffer_size": 1000
}
```

#### GET /api/data/{equipment_id}/snapshot
Get a single snapshot of data.

**Query Parameters:**
- `data_type`: Type of data to retrieve (readings, waveform, measurements)

**Response:** Varies by equipment type and data_type.

## Equipment-Specific Commands

### Oscilloscope (Rigol MSO2072A)

#### get_waveform
Get waveform data from a channel.

**Parameters:**
- `channel` (int): Channel number (1-2)

**Returns:** WaveformData object

#### get_measurements
Get automated measurements.

**Parameters:**
- `channel` (int): Channel number (1-2)

**Returns:**
```json
{
  "vpp": 3.2,
  "vmax": 1.6,
  "vmin": -1.6,
  "vavg": 0.0,
  "vrms": 1.13,
  "freq": 1000.0,
  "period": 0.001
}
```

#### set_timebase
Set timebase settings.

**Parameters:**
- `scale` (float): Time per division (seconds)
- `offset` (float): Time offset (seconds)

#### set_channel
Configure channel settings.

**Parameters:**
- `channel` (int): Channel number
- `enabled` (bool): Enable/disable channel
- `scale` (float): Volts per division
- `offset` (float): Voltage offset
- `coupling` (str): Coupling mode (DC, AC, GND)

#### trigger_single
Set trigger to single mode.

#### trigger_run
Start continuous triggering.

#### trigger_stop
Stop triggering.

#### autoscale
Run autoscale.

### Power Supply (BK 9206B, 9130B)

#### set_voltage
Set output voltage.

**Parameters:**
- `voltage` (float): Voltage in volts
- `channel` (int): Channel number (default: 1)

#### set_current
Set current limit.

**Parameters:**
- `current` (float): Current in amps
- `channel` (int): Channel number (default: 1)

#### set_output
Enable or disable output.

**Parameters:**
- `enabled` (bool): Enable/disable output
- `channel` (int): Channel number (default: 1)

#### get_readings
Get current readings.

**Parameters:**
- `channel` (int): Channel number (default: 1)

**Returns:**
```json
{
  "equipment_id": "ps_xyz789",
  "channel": 1,
  "voltage_set": 12.0,
  "current_set": 1.0,
  "voltage_actual": 12.01,
  "current_actual": 0.523,
  "output_enabled": true,
  "in_cv_mode": true,
  "in_cc_mode": false,
  "timestamp": "2025-01-01T12:00:00"
}
```

### Electronic Load (BK 1902B)

#### set_mode
Set operating mode.

**Parameters:**
- `mode` (str): Mode (CC, CV, CR, CP)

#### set_current
Set current in CC mode.

**Parameters:**
- `current` (float): Current in amps

#### set_voltage
Set voltage in CV mode.

**Parameters:**
- `voltage` (float): Voltage in volts

#### set_resistance
Set resistance in CR mode.

**Parameters:**
- `resistance` (float): Resistance in ohms

#### set_power
Set power in CP mode.

**Parameters:**
- `power` (float): Power in watts

#### set_input
Enable or disable load.

**Parameters:**
- `enabled` (bool): Enable/disable load

#### get_readings
Get current readings.

**Returns:**
```json
{
  "equipment_id": "load_def456",
  "mode": "CC",
  "setpoint": 2.0,
  "voltage": 12.1,
  "current": 2.0,
  "power": 24.2,
  "load_enabled": true,
  "timestamp": "2025-01-01T12:00:00"
}
```

## WebSocket API

### Connection

```
ws://<server-ip>:8000/ws
```

### Message Types

#### Start Streaming

**Send:**
```json
{
  "type": "start_stream",
  "equipment_id": "scope_abc12345",
  "stream_type": "measurements",
  "interval_ms": 100
}
```

**Receive (confirmation):**
```json
{
  "type": "stream_started",
  "equipment_id": "scope_abc12345",
  "stream_type": "measurements"
}
```

**Receive (data):**
```json
{
  "type": "stream_data",
  "equipment_id": "scope_abc12345",
  "stream_type": "measurements",
  "data": {
    "vpp": 3.2,
    "freq": 1000.0,
    ...
  }
}
```

#### Stop Streaming

**Send:**
```json
{
  "type": "stop_stream",
  "equipment_id": "scope_abc12345",
  "stream_type": "measurements"
}
```

**Receive:**
```json
{
  "type": "stream_stopped",
  "equipment_id": "scope_abc12345",
  "stream_type": "measurements"
}
```

#### Ping/Pong

**Send:**
```json
{
  "type": "ping"
}
```

**Receive:**
```json
{
  "type": "pong"
}
```

## Error Responses

All error responses follow this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

Common HTTP status codes:
- `200`: Success
- `400`: Bad request (invalid parameters)
- `404`: Resource not found
- `500`: Internal server error

## Data Models

### Equipment Types
- `oscilloscope`
- `power_supply`
- `electronic_load`
- `multimeter`
- `function_generator`

### Connection Types
- `usb`
- `serial`
- `ethernet`
- `gpib`

### Stream Types
- `readings`: General readings from the device
- `waveform`: Oscilloscope waveform data
- `measurements`: Automated measurements
