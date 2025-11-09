# WebSocket Streaming Guide

Complete guide to real-time data streaming in LabLink using WebSockets.

## Overview

LabLink uses WebSockets for real-time bidirectional communication between the client and server. This enables:

- **Live equipment data streaming** - Readings, waveforms, measurements
- **Acquisition data streaming** - Continuous data acquisition with real-time updates
- **Event notifications** - Alarms, status changes, errors
- **Automatic reconnection** - Maintains connection through network issues

## Architecture

```
Client (WebSocketManager)  <--WebSocket-->  Server (StreamManager)
        |                                            |
        |-- Equipment Streams                       |-- Equipment Manager
        |-- Acquisition Streams                     |-- Acquisition Manager
        |-- Message Routing                         |-- Data Broadcasting
        |-- Reconnection Logic                      |-- Stream Management
```

## Quick Start

### Basic Setup

```python
from client.api.client import LabLinkClient
from client.utils.websocket_manager import StreamType

# Create client
client = LabLinkClient(host="localhost", api_port=8000, ws_port=8001)

# Connect WebSocket
await client.connect_websocket()

# Register data handler
def handle_data(message):
    equipment_id = message['equipment_id']
    data = message['data']
    print(f"Data from {equipment_id}: {data}")

client.register_stream_data_handler(handle_data)

# Start streaming
await client.start_equipment_stream(
    equipment_id="scope_12345678",
    stream_type="readings",
    interval_ms=100  # 100ms = 10 Hz
)
```

## WebSocketManager

### Features

- **Automatic reconnection** - Resumes streams after connection loss
- **Message routing** - Type-safe message handling with callbacks
- **Stream management** - Track and control multiple streams
- **Statistics tracking** - Monitor connection health
- **Async/sync callbacks** - Supports both async and sync handlers

### Connection Management

```python
from client.utils.websocket_manager import WebSocketManager

# Create manager
ws_manager = WebSocketManager(host="localhost", port=8001)

# Connect
connected = await ws_manager.connect()

# Check status
if ws_manager.connected:
    print("WebSocket connected!")

# Disconnect
await ws_manager.disconnect()
```

### Reconnection Behavior

The WebSocket manager automatically reconnects when the connection is lost:

```python
# Reconnection is enabled by default
ws_manager._should_reconnect = True
ws_manager._reconnect_delay = 5.0  # seconds

# Automatic behavior:
# 1. Connection lost
# 2. Wait 5 seconds
# 3. Attempt to reconnect
# 4. Repeat until successful
# 5. Automatically restart all active streams
```

## Streaming Equipment Data

### Stream Types

Three types of equipment data streams:

1. **readings** - Current measurements (voltage, current, power)
2. **waveform** - Oscilloscope waveform data
3. **measurements** - Automated measurements (Vpp, frequency, etc.)

### Starting Streams

```python
# Stream readings from power supply
await client.start_equipment_stream(
    equipment_id="ps_12345678",
    stream_type="readings",
    interval_ms=200  # 5 Hz update rate
)

# Stream waveform from oscilloscope
await client.start_equipment_stream(
    equipment_id="scope_12345678",
    stream_type="waveform",
    interval_ms=100  # 10 Hz
)

# Stream measurements
await client.start_equipment_stream(
    equipment_id="scope_12345678",
    stream_type="measurements",
    interval_ms=500  # 2 Hz
)
```

### Stopping Streams

```python
# Stop specific stream
await client.stop_equipment_stream(
    equipment_id="ps_12345678",
    stream_type="readings"
)

# Or stop all streams by disconnecting
await client.ws_manager.disconnect()
```

### Handling Stream Data

```python
# Register handler
@client.register_stream_data_handler
def handle_stream_data(message):
    equipment_id = message['equipment_id']
    stream_type = message['stream_type']
    data = message['data']

    if stream_type == 'readings':
        voltage = data.get('voltage_actual', 0)
        current = data.get('current_actual', 0)
        print(f"PSU: {voltage:.3f}V, {current:.3f}A")

    elif stream_type == 'waveform':
        num_samples = data.get('num_samples', 0)
        sample_rate = data.get('sample_rate', 0)
        print(f"Waveform: {num_samples} samples @ {sample_rate/1e9:.1f} GSa/s")

    elif stream_type == 'measurements':
        freq = data.get('freq', 0)
        vpp = data.get('vpp', 0)
        print(f"Measurements: {freq} Hz, {vpp:.2f} Vpp")

# Async handler also supported
@client.register_stream_data_handler
async def async_handler(message):
    # Process data asynchronously
    await process_data(message)
```

## Streaming Acquisition Data

### Starting Acquisition Streams

```python
# Create acquisition session (via REST API)
response = client.create_acquisition(
    equipment_id="scope_12345678",
    config={
        "mode": "continuous",
        "sample_rate": 1000.0,  # Hz
        "channels": ["CH1", "CH2"]
    }
)
acquisition_id = response['acquisition_id']

# Start the acquisition
client.start_acquisition(acquisition_id)

# Start streaming the data
await client.start_acquisition_stream(
    acquisition_id=acquisition_id,
    interval_ms=100,  # 10 Hz updates
    num_samples=100   # Samples per update
)
```

### Handling Acquisition Data

```python
@client.register_acquisition_data_handler
def handle_acquisition(message):
    acquisition_id = message['acquisition_id']
    state = message['state']
    stats = message['stats']
    data = message['data']

    if data:
        timestamps = data['timestamps']
        values = data['values']  # Dict: {channel: [values]}
        count = data['count']

        print(f"Acquisition {acquisition_id}: {count} samples")

        # Process channel data
        for channel, channel_data in values.items():
            print(f"  {channel}: {len(channel_data)} points")
```

## Message Types

### Client → Server Messages

```python
# Start equipment stream
{
    "type": "start_stream",
    "equipment_id": "ps_12345678",
    "stream_type": "readings",
    "interval_ms": 100
}

# Stop equipment stream
{
    "type": "stop_stream",
    "equipment_id": "ps_12345678",
    "stream_type": "readings"
}

# Start acquisition stream
{
    "type": "start_acquisition_stream",
    "acquisition_id": "acq_12345678",
    "interval_ms": 100,
    "num_samples": 100
}

# Stop acquisition stream
{
    "type": "stop_acquisition_stream",
    "acquisition_id": "acq_12345678"
}

# Ping (keepalive)
{
    "type": "ping"
}
```

### Server → Client Messages

```python
# Equipment stream data
{
    "type": "stream_data",
    "equipment_id": "ps_12345678",
    "stream_type": "readings",
    "data": {
        "voltage_actual": 12.003,
        "current_actual": 1.502,
        "output_enabled": true,
        "in_cv_mode": true
    }
}

# Acquisition stream data
{
    "type": "acquisition_stream",
    "acquisition_id": "acq_12345678",
    "state": "running",
    "stats": {
        "samples_captured": 1000,
        "duration": 10.5
    },
    "data": {
        "timestamps": ["2024-11-08T12:00:00", ...],
        "values": {
            "CH1": [1.0, 1.1, 1.2, ...],
            "CH2": [2.0, 2.1, 2.2, ...]
        },
        "count": 100
    }
}

# Stream started confirmation
{
    "type": "stream_started",
    "equipment_id": "ps_12345678",
    "stream_type": "readings"
}

# Stream stopped confirmation
{
    "type": "stream_stopped",
    "equipment_id": "ps_12345678",
    "stream_type": "readings"
}

# Pong response
{
    "type": "pong"
}
```

## Advanced Usage

### Multiple Simultaneous Streams

```python
# Stream from multiple devices
await client.start_equipment_stream("scope_1", "waveform", 100)
await client.start_equipment_stream("psu_1", "readings", 200)
await client.start_equipment_stream("psu_2", "readings", 200)
await client.start_equipment_stream("load_1", "readings", 200)

# Check active streams
active = client.ws_manager.get_active_streams()
print(f"Active streams: {len(active)}")
# Output: Active streams: 4

# Get statistics
stats = client.get_websocket_statistics()
print(f"Messages received: {stats['messages_received']}")
print(f"Active streams: {stats['active_streams']}")
```

### Custom Message Handlers

```python
from client.utils.websocket_manager import MessageType

# Register handler for specific message type
ws_manager.register_handler(
    MessageType.STREAM_STARTED,
    lambda msg: print(f"Stream started: {msg}")
)

# Register generic handler for all messages
ws_manager.register_generic_handler(
    lambda msg: print(f"Message: {msg['type']}")
)

# Unregister handlers
ws_manager.unregister_handler(MessageType.STREAM_STARTED, handler)
```

### Error Handling

```python
try:
    await client.start_equipment_stream(equipment_id, "readings")
except RuntimeError as e:
    print(f"WebSocket not connected: {e}")
except Exception as e:
    print(f"Failed to start stream: {e}")

# Monitor errors
stats = client.get_websocket_statistics()
if stats['errors'] > 0:
    print(f"Warning: {stats['errors']} errors occurred")
```

### Connection Lifecycle

```python
# Complete lifecycle management
async def streaming_session():
    client = LabLinkClient()

    try:
        # Connect
        await client.connect_websocket()

        # Register handlers
        client.register_stream_data_handler(handle_data)

        # Start streams
        await client.start_equipment_stream("device_1", "readings")

        # Run for duration
        await asyncio.sleep(60)

    except Exception as e:
        print(f"Error: {e}")

    finally:
        # Always cleanup
        await client.disconnect()
```

## Performance Considerations

### Update Intervals

Choose appropriate intervals based on data rate and network capacity:

```python
# High-frequency waveform data
await client.start_equipment_stream(
    equipment_id="scope",
    stream_type="waveform",
    interval_ms=50  # 20 Hz - high frequency
)

# Low-frequency readings
await client.start_equipment_stream(
    equipment_id="psu",
    stream_type="readings",
    interval_ms=500  # 2 Hz - low frequency
)
```

### Network Bandwidth

Estimate bandwidth usage:

```python
# Waveform: ~1KB per message @ 20 Hz = ~20 KB/s
# Readings: ~100 bytes per message @ 10 Hz = ~1 KB/s
# Measurements: ~200 bytes per message @ 2 Hz = ~0.4 KB/s

# Total for typical setup: ~20-30 KB/s
```

### Message Processing

Process messages efficiently:

```python
# BAD: Blocking handler
def slow_handler(message):
    time.sleep(1)  # Blocks event loop!
    process(message)

# GOOD: Async handler
async def fast_handler(message):
    await asyncio.to_thread(process, message)

# BEST: Queue for background processing
from asyncio import Queue

message_queue = Queue()

async def handler(message):
    await message_queue.put(message)

async def processor():
    while True:
        message = await message_queue.get()
        process(message)
```

## Troubleshooting

### Connection Issues

```python
# Check connection status
if not client.ws_manager.connected:
    print("Not connected to WebSocket")

    # Manual reconnect
    success = await client.connect_websocket()
    if not success:
        print("Reconnection failed")

# Check network
stats = client.get_websocket_statistics()
print(f"Errors: {stats['errors']}")
```

### Missing Data

```python
# Verify stream is active
active_streams = client.ws_manager.get_active_streams()
expected_stream = "ps_12345678_readings"

if expected_stream not in active_streams:
    print("Stream not active, restarting...")
    await client.start_equipment_stream("ps_12345678", "readings")
```

### High Latency

```python
# Reduce update frequency
await client.start_equipment_stream(
    equipment_id="device",
    stream_type="readings",
    interval_ms=1000  # Lower frequency = less latency
)

# Monitor message rate
last_count = 0
while True:
    await asyncio.sleep(1)
    stats = client.get_websocket_statistics()
    rate = stats['messages_received'] - last_count
    last_count = stats['messages_received']
    print(f"Message rate: {rate} msg/s")
```

## Examples

See `test_websocket_streaming.py` for complete examples including:

- Basic equipment streaming
- Multiple simultaneous streams
- Acquisition data streaming
- Automatic reconnection
- Error handling

## API Reference

### WebSocketManager

#### Connection
- `async connect() -> bool` - Connect to WebSocket server
- `async disconnect()` - Disconnect from server

#### Equipment Streaming
- `async start_equipment_stream(equipment_id, stream_type, interval_ms)` - Start stream
- `async stop_equipment_stream(equipment_id, stream_type)` - Stop stream

#### Acquisition Streaming
- `async start_acquisition_stream(acquisition_id, interval_ms, num_samples)` - Start acquisition stream
- `async stop_acquisition_stream(acquisition_id)` - Stop acquisition stream

#### Handlers
- `register_handler(message_type, handler)` - Register typed handler
- `register_generic_handler(handler)` - Register for all messages
- `on_stream_data(handler)` - Decorator for stream data
- `on_acquisition_data(handler)` - Decorator for acquisition data

#### Status
- `get_statistics() -> Dict` - Get connection statistics
- `get_active_streams() -> List[str]` - List active streams

### LabLinkClient

#### WebSocket Methods
- `async connect_websocket() -> bool` - Connect WebSocket
- `async start_equipment_stream(...)` - Start equipment stream
- `async stop_equipment_stream(...)` - Stop equipment stream
- `async start_acquisition_stream(...)` - Start acquisition stream
- `async stop_acquisition_stream(...)` - Stop acquisition stream
- `register_stream_data_handler(handler)` - Register data handler
- `register_acquisition_data_handler(handler)` - Register acquisition handler
- `get_websocket_statistics() -> Dict` - Get statistics

---

*Last updated: 2024-11-08*
