# Enhanced WebSocket Features User Guide

**Version:** 0.15.0
**Last Updated:** 2025-11-13
**Status:** Production-ready

---

## Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Configuration](#configuration)
4. [Stream Recording](#stream-recording)
5. [Message Compression](#message-compression)
6. [Priority Channels](#priority-channels)
7. [Backpressure Handling](#backpressure-handling)
8. [API Reference](#api-reference)
9. [Client Examples](#client-examples)
10. [Best Practices](#best-practices)
11. [Troubleshooting](#troubleshooting)

---

## Overview

The Enhanced WebSocket Features module provides advanced capabilities for real-time data streaming in LabLink, including:

- **Stream Recording**: Record WebSocket streams to files for replay and analysis
- **Message Compression**: Reduce bandwidth usage with gzip/zlib compression
- **Priority Channels**: Route messages based on priority levels
- **Backpressure Handling**: Prevent client overwhelming with flow control

These features are designed to improve performance, reliability, and scalability of WebSocket communications.

---

## Features

### Stream Recording

Record WebSocket streams to various file formats:

- **Formats**: JSON, JSONL (JSON Lines), CSV, Binary
- **Compression**: Optional gzip compression
- **Metadata**: Include timestamps and custom metadata
- **Size Limits**: Automatic rotation based on file size
- **Multiple Sessions**: Record multiple streams simultaneously

### Message Compression

Reduce network bandwidth with message compression:

- **GZIP**: Standard compression (better compression ratio)
- **ZLIB**: Fast compression (lower latency)
- **Per-Message**: Selectively compress messages
- **Transparent**: Automatic compression/decompression

### Priority Channels

Route messages based on priority:

- **4 Priority Levels**: Critical, High, Normal, Low
- **Fair Scheduling**: Higher priority messages sent first
- **Queue Management**: Separate queues per priority
- **Drop Policy**: Optionally drop low-priority when full

### Backpressure Handling

Prevent overwhelming clients with flow control:

- **Queue Management**: Per-connection message queues
- **Rate Limiting**: Token bucket rate limiter
- **Warning Thresholds**: Alerts when queue is filling
- **Drop Policies**: Configurable message dropping
- **Statistics**: Real-time monitoring of queue health

---

## Configuration

### Server Configuration

Add to `.env` file or settings:

```bash
# Stream Recording
LABLINK_WS_RECORDING_ENABLED=false
LABLINK_WS_RECORDING_FORMAT=jsonl
LABLINK_WS_RECORDING_DIR=./data/ws_recordings
LABLINK_WS_RECORDING_MAX_SIZE_MB=100
LABLINK_WS_RECORDING_TIMESTAMPS=true
LABLINK_WS_RECORDING_METADATA=true
LABLINK_WS_RECORDING_COMPRESS=true

# Backpressure & Flow Control
LABLINK_WS_BACKPRESSURE_ENABLED=true
LABLINK_WS_MESSAGE_QUEUE_SIZE=1000
LABLINK_WS_QUEUE_WARNING_THRESHOLD=750
LABLINK_WS_DROP_LOW_PRIORITY=true
LABLINK_WS_RATE_LIMIT_ENABLED=true
LABLINK_WS_MAX_MESSAGES_PER_SECOND=100
LABLINK_WS_BURST_SIZE=50
```

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `ws_recording_enabled` | `false` | Enable stream recording |
| `ws_recording_format` | `jsonl` | Recording format (json/jsonl/csv/binary) |
| `ws_recording_dir` | `./data/ws_recordings` | Output directory |
| `ws_recording_max_size_mb` | `100` | Maximum file size (MB) |
| `ws_recording_timestamps` | `true` | Include timestamps |
| `ws_recording_metadata` | `true` | Include metadata |
| `ws_recording_compress` | `true` | Compress output files |
| `ws_backpressure_enabled` | `true` | Enable backpressure handling |
| `ws_message_queue_size` | `1000` | Maximum queue size per connection |
| `ws_queue_warning_threshold` | `750` | Queue warning threshold (75%) |
| `ws_drop_low_priority` | `true` | Drop low-priority when full |
| `ws_rate_limit_enabled` | `true` | Enable rate limiting |
| `ws_max_messages_per_second` | `100` | Max messages/second per connection |
| `ws_burst_size` | `50` | Burst size for rate limiter |

---

## Stream Recording

### Starting a Recording

**REST API:**
```bash
curl -X POST http://localhost:8000/api/websocket/recording/start \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "experiment_001",
    "metadata": {
      "description": "Temperature monitoring test",
      "equipment": "oscilloscope_1",
      "operator": "john_doe"
    }
  }'
```

**Response:**
```json
{
  "session_id": "experiment_001",
  "filepath": "./data/ws_recordings/stream_experiment_001_20251113_143022.jsonl.gz",
  "started_at": "2025-11-13T14:30:22.123456"
}
```

**WebSocket Message:**
```json
{
  "type": "start_recording",
  "session_id": "experiment_001",
  "metadata": {
    "description": "Temperature monitoring test"
  }
}
```

### Stopping a Recording

**REST API:**
```bash
curl -X POST http://localhost:8000/api/websocket/recording/stop/experiment_001
```

**Response:**
```json
{
  "session_id": "experiment_001",
  "filepath": "./data/ws_recordings/stream_experiment_001_20251113_143022.jsonl.gz",
  "duration_seconds": 125.5,
  "message_count": 1255,
  "bytes_written": 524288,
  "messages_per_second": 10.0
}
```

**WebSocket Message:**
```json
{
  "type": "stop_recording",
  "session_id": "experiment_001"
}
```

### Recording Statistics

**REST API:**
```bash
curl http://localhost:8000/api/websocket/recording/stats/experiment_001
```

**Response:**
```json
{
  "session_id": "experiment_001",
  "filepath": "./data/ws_recordings/stream_experiment_001_20251113_143022.jsonl.gz",
  "duration_seconds": 62.3,
  "message_count": 623,
  "bytes_written": 262144,
  "messages_per_second": 10.0
}
```

### List Active Recordings

**REST API:**
```bash
curl http://localhost:8000/api/websocket/recording/active
```

**Response:**
```json
["experiment_001", "test_session_002"]
```

### Recording Formats

#### JSONL (Recommended)

One JSON object per line (easy to parse, streamable):

```jsonl
{"_timestamp": "2025-11-13T14:30:22.123Z", "type": "stream_data", "value": 1.23}
{"_timestamp": "2025-11-13T14:30:23.125Z", "type": "stream_data", "value": 1.25}
```

#### JSON

Single JSON array (requires loading entire file):

```json
[
  {"_timestamp": "2025-11-13T14:30:22.123Z", "type": "stream_data", "value": 1.23},
  {"_timestamp": "2025-11-13T14:30:23.125Z", "type": "stream_data", "value": 1.25}
]
```

#### CSV

CSV format with headers:

```csv
timestamp,message_type,data
"2025-11-13T14:30:22.123Z","stream_data","{\"value\": 1.23}"
"2025-11-13T14:30:23.125Z","stream_data","{\"value\": 1.25}"
```

---

## Message Compression

### Enabling Compression

**WebSocket Message:**
```json
{
  "type": "set_compression",
  "compression": "gzip"
}
```

Compression types: `none`, `gzip`, `zlib`

### Per-Message Compression

**Starting a Stream with Compression:**
```json
{
  "type": "start_stream",
  "equipment_id": "oscilloscope_1",
  "stream_type": "waveform",
  "interval_ms": 100,
  "compression": "gzip"
}
```

### Compression Performance

| Type | Ratio | CPU | Latency | Use Case |
|------|-------|-----|---------|----------|
| None | 1.0x | None | Lowest | Small messages, low bandwidth |
| ZLIB | 3-5x | Low | Low | Fast streaming, moderate compression |
| GZIP | 4-6x | Medium | Medium | Best compression, file storage |

**Typical Compression Ratios:**
- Text data: 4-6x
- JSON: 3-5x
- Binary waveforms: 2-3x
- Random data: ~1x (no compression)

---

## Priority Channels

### Priority Levels

| Level | Value | Use Case |
|-------|-------|----------|
| CRITICAL | 3 | Alarms, emergency stops, errors |
| HIGH | 2 | User commands, state changes |
| NORMAL | 1 | Regular data streaming (default) |
| LOW | 0 | Background updates, statistics |

### Setting Message Priority

**WebSocket Message:**
```json
{
  "type": "start_stream",
  "equipment_id": "oscilloscope_1",
  "stream_type": "waveform",
  "priority": "high"
}
```

### Testing Priority Channels

**REST API:**
```bash
# Send high-priority test message
curl -X POST http://localhost:8000/api/websocket/test/send \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "client_abc123",
    "message": {"type": "test", "data": "urgent"},
    "priority": "high",
    "compression": "none"
  }'
```

### Priority Queue Behavior

1. **CRITICAL** messages always sent first
2. **HIGH** messages sent before NORMAL/LOW
3. **NORMAL** messages sent in FIFO order
4. **LOW** messages sent last (may be dropped when queue is full)

---

## Backpressure Handling

### Queue Management

Each WebSocket connection has:
- **Per-Priority Queues**: Separate queues for each priority level
- **Queue Size Limit**: Configurable maximum (default: 1000 messages)
- **Warning Threshold**: Alert when 75% full (default)
- **Drop Policy**: Drop low-priority when full (configurable)

### Rate Limiting

Token bucket algorithm:
- **Max Rate**: Messages per second per connection (default: 100)
- **Burst Size**: Maximum burst (default: 50)
- **Refill Rate**: Tokens refilled at configured rate

### Monitoring Backpressure

**REST API:**
```bash
# Get backpressure stats for specific connection
curl http://localhost:8000/api/websocket/connections/client_abc123/backpressure
```

**Response:**
```json
{
  "messages_queued": 1234,
  "messages_sent": 1200,
  "messages_dropped": 5,
  "queue_overflows": 1,
  "rate_limit_hits": 15,
  "queue_size": 34,
  "queue_size_by_priority": {
    "critical": 0,
    "high": 2,
    "normal": 30,
    "low": 2
  }
}
```

### Backpressure Statistics

**WebSocket Message:**
```json
{
  "type": "get_stats"
}
```

**Response:**
```json
{
  "type": "stats",
  "connection": {
    "messages_queued": 1234,
    "messages_sent": 1200,
    "messages_dropped": 5,
    "queue_size": 34
  },
  "global": {
    "total_connections": 3,
    "total_messages_sent": 15234,
    "active_connections": 3,
    "active_recordings": 1,
    "average_compression_ratio": 4.2
  }
}
```

---

## API Reference

### REST API Endpoints

#### Recording Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/websocket/recording/start` | Start recording session |
| POST | `/api/websocket/recording/stop/{session_id}` | Stop recording session |
| GET | `/api/websocket/recording/stats/{session_id}` | Get recording statistics |
| GET | `/api/websocket/recording/active` | List active recordings |

#### Connection Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/websocket/connections` | List all connections |
| GET | `/api/websocket/connections/{client_id}` | Get connection info |
| GET | `/api/websocket/connections/{client_id}/backpressure` | Get backpressure stats |

#### Statistics Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/websocket/stats` | Get global statistics |
| POST | `/api/websocket/test/send` | Send test message |

### WebSocket Messages

#### Client to Server

```json
// Start stream with compression and priority
{
  "type": "start_stream",
  "equipment_id": "oscilloscope_1",
  "stream_type": "waveform",
  "interval_ms": 100,
  "priority": "high",
  "compression": "gzip"
}

// Stop stream
{
  "type": "stop_stream",
  "equipment_id": "oscilloscope_1",
  "stream_type": "waveform"
}

// Start recording
{
  "type": "start_recording",
  "session_id": "experiment_001",
  "metadata": {"description": "Test"}
}

// Stop recording
{
  "type": "stop_recording",
  "session_id": "experiment_001"
}

// Set compression preference
{
  "type": "set_compression",
  "compression": "gzip"
}

// Set priority preference
{
  "type": "set_priority",
  "priority": "high"
}

// Get statistics
{
  "type": "get_stats"
}

// Ping
{
  "type": "ping"
}
```

#### Server to Client

```json
// Capabilities announcement (sent on connect)
{
  "type": "capabilities",
  "features": {
    "compression": {
      "enabled": true,
      "types": ["none", "gzip", "zlib"]
    },
    "priorities": {
      "enabled": true,
      "levels": ["LOW", "NORMAL", "HIGH", "CRITICAL"]
    },
    "recording": {
      "enabled": false,
      "formats": ["json", "jsonl", "csv", "binary"]
    },
    "backpressure": {
      "enabled": true,
      "max_queue_size": 1000,
      "rate_limit": 100
    }
  }
}

// Stream data
{
  "type": "stream_data",
  "equipment_id": "oscilloscope_1",
  "stream_type": "waveform",
  "data": { ... },
  "timestamp": "2025-11-13T14:30:22.123Z"
}

// Pong response
{
  "type": "pong",
  "timestamp": "2025-11-13T14:30:22.123Z"
}

// Error
{
  "type": "error",
  "error": "Failed to start recording: session already exists"
}
```

---

## Client Examples

### Python Client with Enhanced Features

```python
import asyncio
import websockets
import json

async def enhanced_websocket_client():
    uri = "ws://localhost:8001/ws"

    async with websockets.connect(uri) as websocket:
        # Wait for capabilities announcement
        capabilities = await websocket.recv()
        print("Server capabilities:", capabilities)

        # Start recording
        await websocket.send(json.dumps({
            "type": "start_recording",
            "session_id": "test_session",
            "metadata": {"test": True}
        }))

        # Set compression
        await websocket.send(json.dumps({
            "type": "set_compression",
            "compression": "gzip"
        }))

        # Start high-priority compressed stream
        await websocket.send(json.dumps({
            "type": "start_stream",
            "equipment_id": "oscilloscope_1",
            "stream_type": "waveform",
            "interval_ms": 100,
            "priority": "high",
            "compression": "gzip"
        }))

        # Receive messages for 10 seconds
        try:
            async for message in asyncio.wait_for(
                websocket, timeout=10.0
            ):
                data = json.loads(message)
                print(f"Received: {data['type']}")
        except asyncio.TimeoutError:
            pass

        # Stop recording
        await websocket.send(json.dumps({
            "type": "stop_recording",
            "session_id": "test_session"
        }))

        # Get final statistics
        await websocket.send(json.dumps({
            "type": "get_stats"
        }))

        stats = await websocket.recv()
        print("Final stats:", stats)

asyncio.run(enhanced_websocket_client())
```

### JavaScript Client

```javascript
const ws = new WebSocket('ws://localhost:8001/ws');

ws.onopen = () => {
  console.log('Connected');

  // Start recording
  ws.send(JSON.stringify({
    type: 'start_recording',
    session_id: 'js_session',
    metadata: { browser: navigator.userAgent }
  }));

  // Start compressed stream
  ws.send(JSON.stringify({
    type: 'start_stream',
    equipment_id: 'oscilloscope_1',
    stream_type: 'waveform',
    interval_ms: 100,
    priority: 'high',
    compression: 'gzip'
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data.type);

  if (data.type === 'capabilities') {
    console.log('Server features:', data.features);
  }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('Disconnected');
};
```

---

## Best Practices

### Stream Recording

1. **Use JSONL format** for large recordings (streamable, line-based)
2. **Enable compression** to save disk space (4-6x reduction)
3. **Set appropriate file size limits** (100MB default recommended)
4. **Include metadata** for session identification
5. **Monitor disk space** when recording enabled
6. **Stop recordings** when done to finalize files

### Message Compression

1. **Use compression for large messages** (>1KB typically benefits)
2. **Choose GZIP for storage**, ZLIB for low-latency streaming
3. **Don't compress small messages** (< 100 bytes overhead)
4. **Test compression ratios** for your data types
5. **Monitor CPU usage** if compression causes issues

### Priority Channels

1. **Use CRITICAL for alarms** and emergency stops
2. **Use HIGH for user commands** requiring immediate response
3. **Use NORMAL for regular data** streaming (default)
4. **Use LOW for statistics** and background updates
5. **Don't overuse high priorities** (defeats the purpose)

### Backpressure Handling

1. **Monitor queue sizes** regularly
2. **Investigate warnings** (>75% queue full)
3. **Adjust rate limits** based on client capabilities
4. **Use appropriate priorities** for message importance
5. **Handle dropped messages** gracefully in clients
6. **Implement exponential backoff** for reconnections

---

## Troubleshooting

### Issue: Recording files not created

**Symptoms:**
- `start_recording` succeeds but no file appears
- Recording directory not created

**Solutions:**
1. Check `ws_recording_enabled=true` in settings
2. Verify `ws_recording_dir` permissions
3. Check disk space availability
4. Review server logs for errors

**Check:**
```bash
# Verify recording directory
ls -la ./data/ws_recordings/

# Check settings
curl http://localhost:8000/api/websocket/stats
```

### Issue: Messages being dropped

**Symptoms:**
- `messages_dropped` > 0 in statistics
- Data gaps in recordings
- Client not receiving all messages

**Solutions:**
1. Increase `ws_message_queue_size` (default: 1000)
2. Reduce streaming frequency (increase `interval_ms`)
3. Enable compression to reduce queue load
4. Use appropriate priorities (don't mark everything HIGH)
5. Increase `ws_max_messages_per_second` if rate limited

**Check:**
```bash
# Check backpressure stats
curl http://localhost:8000/api/websocket/connections/{client_id}/backpressure
```

### Issue: High CPU usage

**Symptoms:**
- Server CPU usage high
- Compression enabled
- Many concurrent connections

**Solutions:**
1. Use ZLIB instead of GZIP (faster, less compression)
2. Disable compression for small messages
3. Reduce streaming frequency
4. Limit concurrent connections (`ws_max_connections`)
5. Use binary formats instead of JSON

**Check:**
```bash
# Monitor CPU usage
top -p $(pgrep -f "python.*main.py")

# Check compression stats
curl http://localhost:8000/api/websocket/stats
```

### Issue: WebSocket disconnections

**Symptoms:**
- Frequent disconnections
- `queue_overflows` > 0
- Rate limit hits high

**Solutions:**
1. Adjust `ws_max_messages_per_second` (increase)
2. Increase `ws_burst_size` for bursty traffic
3. Enable `ws_drop_low_priority` to prevent overflows
4. Implement client-side reconnection logic
5. Use heartbeat/ping to detect connection issues

**Check:**
```bash
# Check connection stats
curl http://localhost:8000/api/websocket/connections

# Monitor disconnections in logs
tail -f ./logs/lablink.log | grep "disconnect"
```

### Issue: Large recording files

**Symptoms:**
- Recording files very large
- Disk space filling up
- File size limit reached quickly

**Solutions:**
1. Enable compression (`ws_recording_compress=true`)
2. Reduce `ws_recording_max_size_mb` for auto-rotation
3. Use JSONL or CSV instead of JSON format
4. Reduce streaming frequency
5. Filter unnecessary data before recording
6. Implement automatic cleanup of old recordings

**Check:**
```bash
# Check recording sizes
du -sh ./data/ws_recordings/*

# Monitor disk space
df -h ./data/
```

---

## Performance Tuning

### High-Throughput Streaming

For maximum throughput:

```bash
LABLINK_WS_MESSAGE_QUEUE_SIZE=5000
LABLINK_WS_MAX_MESSAGES_PER_SECOND=500
LABLINK_WS_BURST_SIZE=200
LABLINK_WS_RATE_LIMIT_ENABLED=false
```

### Low-Latency Streaming

For minimum latency:

```bash
LABLINK_WS_BACKPRESSURE_ENABLED=false
LABLINK_WS_COMPRESSION_ENABLED=false
LABLINK_WS_MESSAGE_QUEUE_SIZE=100
```

### Bandwidth-Constrained

For low bandwidth:

```bash
LABLINK_WS_COMPRESSION_ENABLED=true
LABLINK_WS_MAX_MESSAGES_PER_SECOND=50
LABLINK_WS_DROP_LOW_PRIORITY=true
```

---

## Summary

Enhanced WebSocket Features provide:

✅ **Stream Recording** - Capture streams for analysis and replay
✅ **Compression** - Reduce bandwidth by 3-6x
✅ **Priority Channels** - Route critical messages first
✅ **Backpressure** - Prevent overwhelming clients

For questions or issues, consult the troubleshooting section or check server logs.

**Repository:** https://github.com/X9X0/LabLink
**Documentation:** See `server/` directory for additional guides
