# LabLink Data Acquisition & Logging System

## Overview

The LabLink Data Acquisition & Logging System provides a comprehensive solution for capturing, analyzing, and exporting data from laboratory equipment. It supports continuous data streaming, triggered acquisition, real-time statistics, and multi-instrument synchronization.

**Version:** 0.6.0
**Status:** Production Ready

---

## Table of Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Acquisition Modes](#acquisition-modes)
4. [API Reference](#api-reference)
5. [Advanced Statistics](#advanced-statistics)
6. [Multi-Instrument Synchronization](#multi-instrument-synchronization)
7. [WebSocket Streaming](#websocket-streaming)
8. [Data Export Formats](#data-export-formats)
9. [Usage Examples](#usage-examples)
10. [Configuration](#configuration)

---

## Features

### Core Capabilities
- **Multiple Acquisition Modes**: Continuous, single-shot, and triggered data capture
- **Circular Buffer**: Efficient in-memory data storage with automatic overflow handling
- **Real-time Statistics**: FFT, trend detection, data quality assessment, peak detection
- **Multi-Instrument Sync**: Coordinate data acquisition across multiple devices
- **WebSocket Streaming**: Real-time data streaming to connected clients
- **Multiple Export Formats**: CSV, NumPy, JSON, HDF5

### Trigger Types
- **Immediate**: Start acquisition immediately
- **Level**: Trigger when signal crosses a threshold
- **Edge**: Trigger on rising/falling edge
- **Time**: Trigger at a specific time
- **External**: Wait for external trigger signal

### Advanced Features
- Rolling statistics (mean, std, min, max, RMS, peak-to-peak)
- FFT frequency analysis with THD and SNR
- Trend detection (rising, falling, stable, noisy)
- Data quality metrics (noise level, stability, outliers)
- Peak detection with configurable parameters
- Threshold crossing detection

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Applications                       │
└────────────┬────────────────────────────┬───────────────────┘
             │                            │
    ┌────────▼────────┐          ┌────────▼────────┐
    │   REST API      │          │   WebSocket     │
    │  (26 endpoints) │          │   Streaming     │
    └────────┬────────┘          └────────┬────────┘
             │                            │
    ┌────────▼────────────────────────────▼────────┐
    │         Acquisition Manager                  │
    │  - Session Management                        │
    │  - Trigger Detection                         │
    │  - Data Collection                           │
    └────────┬────────────────────────────┬────────┘
             │                            │
    ┌────────▼────────┐          ┌────────▼────────┐
    │  Circular       │          │  Statistics     │
    │  Buffer         │          │  Engine         │
    └────────┬────────┘          └────────┬────────┘
             │                            │
    ┌────────▼────────────────────────────▼────────┐
    │         Equipment Drivers                    │
    └──────────────────────────────────────────────┘
```

### Components

**Acquisition Manager** (`acquisition/manager.py`)
- Creates and manages acquisition sessions
- Handles background data collection loops
- Implements trigger detection logic
- Manages data export

**Circular Buffer** (`acquisition/models.py`)
- Fixed-size ring buffer for efficient data storage
- Automatic overflow handling
- Thread-safe operations
- O(1) read/write performance

**Statistics Engine** (`acquisition/statistics.py`)
- Real-time statistical analysis
- FFT frequency domain analysis
- Trend detection algorithms
- Data quality assessment

**Synchronization Manager** (`acquisition/synchronization.py`)
- Multi-instrument coordination
- Timestamp alignment
- Synchronized start/stop/pause/resume

---

## Acquisition Modes

### Continuous Mode
Continuously acquire data until manually stopped.

```python
config = AcquisitionConfig(
    equipment_id="PSU_001",
    mode=AcquisitionMode.CONTINUOUS,
    sample_rate=10.0,  # Hz
    channels=["voltage", "current"],
    buffer_size=10000
)
```

### Single-Shot Mode
Acquire a fixed number of samples and then stop.

```python
config = AcquisitionConfig(
    equipment_id="OSC_001",
    mode=AcquisitionMode.SINGLE_SHOT,
    sample_rate=1000.0,
    channels=["CH1", "CH2"],
    duration_seconds=1.0  # Acquire for 1 second
)
```

### Triggered Mode
Wait for a trigger condition before starting acquisition.

```python
trigger_config = TriggerConfig(
    trigger_type=TriggerType.LEVEL,
    channel="voltage",
    threshold=5.0,
    edge=TriggerEdge.RISING,
    pre_trigger_samples=100
)

config = AcquisitionConfig(
    equipment_id="DMM_001",
    mode=AcquisitionMode.TRIGGERED,
    sample_rate=100.0,
    channels=["voltage"],
    trigger_config=trigger_config
)
```

---

## API Reference

### Basic Acquisition Endpoints

#### Create Session
```http
POST /api/acquisition/session/create
Content-Type: application/json

{
  "equipment_id": "PSU_001",
  "mode": "continuous",
  "sample_rate": 10.0,
  "channels": ["voltage", "current"],
  "buffer_size": 10000
}

Response: {
  "success": true,
  "acquisition_id": "acq_abc123",
  "message": "Acquisition session created"
}
```

#### Start Acquisition
```http
POST /api/acquisition/session/{acquisition_id}/start

Response: {
  "success": true,
  "message": "Acquisition started",
  "state": "acquiring"
}
```

#### Stop Acquisition
```http
POST /api/acquisition/session/{acquisition_id}/stop

Response: {
  "success": true,
  "message": "Acquisition stopped",
  "stats": {
    "total_samples": 5420,
    "duration_seconds": 542.0
  }
}
```

#### Get Acquisition Data
```http
GET /api/acquisition/session/{acquisition_id}/data?num_samples=100

Response: {
  "success": true,
  "acquisition_id": "acq_abc123",
  "data": {
    "timestamps": ["2025-01-08T10:30:00Z", ...],
    "channels": {
      "voltage": [5.01, 5.02, ...],
      "current": [0.51, 0.52, ...]
    }
  },
  "stats": {
    "total_samples": 5420,
    "sample_rate": 10.0
  }
}
```

#### Export Data
```http
POST /api/acquisition/export
Content-Type: application/json

{
  "acquisition_id": "acq_abc123",
  "format": "csv",
  "filename": "experiment_data.csv"
}

Response: {
  "success": true,
  "filepath": "./data/acquisitions/experiment_data.csv",
  "format": "csv",
  "size_bytes": 245678
}
```

---

## Advanced Statistics

### Rolling Statistics
Get statistical metrics over a data window.

```http
GET /api/acquisition/session/{acquisition_id}/stats/rolling?channel=voltage&num_samples=1000

Response: {
  "success": true,
  "stats": {
    "mean": 5.003,
    "std": 0.012,
    "min": 4.98,
    "max": 5.03,
    "median": 5.002,
    "rms": 5.004,
    "peak_to_peak": 0.05,
    "num_samples": 1000
  }
}
```

### FFT Analysis
Perform frequency domain analysis.

```http
GET /api/acquisition/session/{acquisition_id}/stats/fft?channel=CH1&window=hann

Response: {
  "success": true,
  "fft": {
    "frequencies": [0, 0.1, 0.2, ...],
    "magnitudes": [0.001, 0.002, ...],
    "phases": [0, 0.5, ...],
    "dominant_frequency": 60.0,
    "fundamental_amplitude": 0.85,
    "thd_percent": 2.3,
    "snr_db": 45.2
  }
}
```

### Trend Detection
Detect trends in time-series data.

```http
GET /api/acquisition/session/{acquisition_id}/stats/trend?channel=temperature

Response: {
  "success": true,
  "trend": {
    "type": "rising",
    "slope": 0.05,
    "r_squared": 0.98,
    "confidence": 0.98
  }
}
```

### Data Quality Assessment
```http
GET /api/acquisition/session/{acquisition_id}/stats/quality?channel=voltage

Response: {
  "success": true,
  "quality": {
    "noise_level": 0.024,
    "stability_score": 0.95,
    "outlier_count": 3,
    "missing_count": 0,
    "valid_percentage": 100.0
  }
}
```

### Peak Detection
```http
GET /api/acquisition/session/{acquisition_id}/stats/peaks?channel=CH1&prominence=0.5

Response: {
  "success": true,
  "peaks": {
    "indices": [120, 450, 780],
    "values": [3.2, 3.5, 3.1],
    "count": 3
  }
}
```

### Threshold Crossings
```http
GET /api/acquisition/session/{acquisition_id}/stats/crossings?channel=voltage&threshold=5.0&direction=rising

Response: {
  "success": true,
  "crossings": {
    "rising": [245, 890, 1340],
    "falling": [],
    "total": 3
  }
}
```

---

## Multi-Instrument Synchronization

Coordinate data acquisition across multiple instruments with synchronized timing.

### Create Sync Group
```http
POST /api/acquisition/sync/group/create
Content-Type: application/json

{
  "group_id": "sync_experiment_1",
  "equipment_ids": ["PSU_001", "DMM_001", "OSC_001"],
  "master_equipment_id": "OSC_001",
  "wait_for_all": true,
  "auto_align_timestamps": true
}

Response: {
  "success": true,
  "message": "Sync group created",
  "status": {
    "group_id": "sync_experiment_1",
    "state": "idle",
    "equipment_count": 3,
    "master": "OSC_001"
  }
}
```

### Add Acquisitions to Sync Group
```http
POST /api/acquisition/sync/group/{group_id}/add
Content-Type: application/json

{
  "equipment_id": "PSU_001",
  "acquisition_id": "acq_psu_001"
}

Response: {
  "success": true,
  "status": {
    "ready_count": 1,
    "total_count": 3,
    "state": "preparing"
  }
}
```

### Start Synchronized Acquisition
```http
POST /api/acquisition/sync/group/{group_id}/start

Response: {
  "success": true,
  "message": "Sync group started",
  "status": {
    "group_id": "sync_experiment_1",
    "state": "running",
    "start_time": "2025-01-08T10:30:00Z",
    "acquisition_ids": {
      "PSU_001": "acq_psu_001",
      "DMM_001": "acq_dmm_001",
      "OSC_001": "acq_osc_001"
    }
  }
}
```

### Get Synchronized Data
```http
GET /api/acquisition/sync/group/{group_id}/data?num_samples=100

Response: {
  "success": true,
  "group_id": "sync_experiment_1",
  "data": {
    "PSU_001": {
      "data": [[5.01, 0.51], [5.02, 0.52], ...],
      "timestamps": [0.0, 0.1, 0.2, ...]  // Aligned to start_time
    },
    "DMM_001": {
      "data": [[12.34], [12.35], ...],
      "timestamps": [0.0, 0.1, 0.2, ...]
    }
  }
}
```

---

## WebSocket Streaming

Real-time data streaming via WebSocket for live visualization.

### Connect to WebSocket
```javascript
const ws = new WebSocket('ws://localhost:8001/ws');

ws.onopen = () => {
  console.log('Connected to LabLink WebSocket');
};
```

### Start Acquisition Stream
```javascript
ws.send(JSON.stringify({
  type: 'start_acquisition_stream',
  acquisition_id: 'acq_abc123',
  interval_ms: 100,  // Update every 100ms
  num_samples: 50     // Send last 50 samples
}));
```

### Receive Streamed Data
```javascript
ws.onmessage = (event) => {
  const message = JSON.parse(event.data);

  if (message.type === 'acquisition_stream') {
    console.log('State:', message.state);
    console.log('Stats:', message.stats);
    console.log('Data:', message.data);

    // Update your charts/displays
    updateChart(message.data.timestamps, message.data.values);
  }
};
```

### Stop Streaming
```javascript
ws.send(JSON.stringify({
  type: 'stop_acquisition_stream',
  acquisition_id: 'acq_abc123'
}));
```

---

## Data Export Formats

### CSV Format
```csv
timestamp,voltage,current
2025-01-08T10:30:00.000Z,5.01,0.51
2025-01-08T10:30:00.100Z,5.02,0.52
...
```

### NumPy Format (.npz)
```python
import numpy as np

data = np.load('experiment_data.npz')
print(data['timestamps'])  # Array of timestamps
print(data['voltage'])     # Channel data
print(data['current'])     # Channel data
```

### JSON Format
```json
{
  "acquisition_id": "acq_abc123",
  "equipment_id": "PSU_001",
  "start_time": "2025-01-08T10:30:00Z",
  "config": {
    "mode": "continuous",
    "sample_rate": 10.0,
    "channels": ["voltage", "current"]
  },
  "data": {
    "timestamps": [1704710400.0, 1704710400.1, ...],
    "voltage": [5.01, 5.02, ...],
    "current": [0.51, 0.52, ...]
  }
}
```

### HDF5 Format
```python
import h5py

with h5py.File('experiment_data.h5', 'r') as f:
    timestamps = f['data/timestamps'][:]
    voltage = f['data/voltage'][:]
    config = dict(f['config'].attrs)
```

---

## Usage Examples

### Example 1: Simple Continuous Acquisition
```python
import requests

# Create acquisition session
response = requests.post('http://localhost:8000/api/acquisition/session/create', json={
    'equipment_id': 'PSU_001',
    'mode': 'continuous',
    'sample_rate': 10.0,
    'channels': ['voltage', 'current'],
    'buffer_size': 10000
})
acq_id = response.json()['acquisition_id']

# Start acquisition
requests.post(f'http://localhost:8000/api/acquisition/session/{acq_id}/start')

# Wait for some data...
time.sleep(10)

# Get data
data = requests.get(f'http://localhost:8000/api/acquisition/session/{acq_id}/data?num_samples=100')
print(data.json())

# Stop acquisition
requests.post(f'http://localhost:8000/api/acquisition/session/{acq_id}/stop')

# Export to CSV
requests.post('http://localhost:8000/api/acquisition/export', json={
    'acquisition_id': acq_id,
    'format': 'csv',
    'filename': 'power_supply_data.csv'
})
```

### Example 2: Triggered Acquisition with Statistics
```python
# Create triggered acquisition
response = requests.post('http://localhost:8000/api/acquisition/session/create', json={
    'equipment_id': 'OSC_001',
    'mode': 'triggered',
    'sample_rate': 1000.0,
    'channels': ['CH1'],
    'trigger_config': {
        'trigger_type': 'level',
        'channel': 'CH1',
        'threshold': 2.5,
        'edge': 'rising',
        'pre_trigger_samples': 100
    }
})
acq_id = response.json()['acquisition_id']

# Start (will wait for trigger)
requests.post(f'http://localhost:8000/api/acquisition/session/{acq_id}/start')

# After trigger occurs and data is captured...

# Get FFT analysis
fft = requests.get(f'http://localhost:8000/api/acquisition/session/{acq_id}/stats/fft?channel=CH1')
print('Dominant frequency:', fft.json()['fft']['dominant_frequency'])

# Detect peaks
peaks = requests.get(f'http://localhost:8000/api/acquisition/session/{acq_id}/stats/peaks?channel=CH1&prominence=0.5')
print('Peaks found:', peaks.json()['peaks']['count'])
```

### Example 3: Multi-Instrument Synchronized Acquisition
```python
# Create sync group
requests.post('http://localhost:8000/api/acquisition/sync/group/create', json={
    'group_id': 'power_measurement',
    'equipment_ids': ['PSU_001', 'DMM_001', 'OSC_001'],
    'wait_for_all': True
})

# Create individual acquisition sessions
psu_resp = requests.post('http://localhost:8000/api/acquisition/session/create', json={
    'equipment_id': 'PSU_001',
    'mode': 'continuous',
    'sample_rate': 10.0,
    'channels': ['voltage', 'current']
})
psu_acq = psu_resp.json()['acquisition_id']

# Add to sync group
requests.post('http://localhost:8000/api/acquisition/sync/group/power_measurement/add', json={
    'equipment_id': 'PSU_001',
    'acquisition_id': psu_acq
})

# (Repeat for other devices...)

# Start synchronized acquisition
requests.post('http://localhost:8000/api/acquisition/sync/group/power_measurement/start')

# Get synchronized data
sync_data = requests.get('http://localhost:8000/api/acquisition/sync/group/power_measurement/data?num_samples=100')
print(sync_data.json())
```

---

## Configuration

Configuration options in `.env` file:

```bash
# Data Acquisition
LABLINK_ENABLE_ACQUISITION=true
LABLINK_ACQUISITION_EXPORT_DIR=./data/acquisitions
LABLINK_DEFAULT_SAMPLE_RATE=1.0
LABLINK_DEFAULT_BUFFER_SIZE=10000
LABLINK_MAX_ACQUISITION_DURATION=3600
LABLINK_AUTO_EXPORT_ON_STOP=false
```

---

## Performance Characteristics

- **Maximum Sample Rate**: Limited by equipment driver (~10 kHz for most devices)
- **Buffer Size**: Configurable (default: 10,000 samples per channel)
- **Memory Usage**: ~80 bytes per sample per channel (with timestamps)
- **Latency**: < 1ms for buffer operations, ~10ms for statistics
- **Concurrent Sessions**: Limited only by system resources
- **WebSocket Throughput**: ~1000 updates/second

---

## Error Handling

The acquisition system includes comprehensive error handling:

- **Equipment Disconnection**: Acquisition automatically stops, data preserved in buffer
- **Buffer Overflow**: Tracked with `overruns` counter, oldest data overwritten
- **Trigger Timeout**: Configurable timeout for triggered acquisitions
- **Invalid Configuration**: Validation at session creation time
- **Export Failures**: Detailed error messages, data remains in buffer

---

## Best Practices

1. **Buffer Sizing**: Set buffer size to at least `sample_rate * expected_duration`
2. **Sample Rate**: Match to equipment capabilities and measurement needs
3. **Trigger Configuration**: Add pre-trigger samples to capture signal leading edge
4. **Statistics Window**: Use appropriate num_samples for statistics (100-1000 recommended)
5. **Export Regularly**: For long acquisitions, export periodically to free memory
6. **Sync Groups**: Use master device with most precise timing
7. **WebSocket Updates**: Limit update rate to 10-100 Hz for smooth visualization

---

## Troubleshooting

**Q: Acquisition won't start**
- Verify equipment is connected and not in emergency stop
- Check equipment locks (may be locked by another user)
- Ensure sample rate is within equipment capabilities

**Q: Missing data or gaps**
- Check buffer `overruns` counter - may need larger buffer
- Verify network connectivity for remote equipment
- Check equipment health status

**Q: Trigger not firing**
- Verify trigger threshold and channel are correct
- Check signal is actually crossing threshold
- Enable immediate trigger type for testing

**Q: Poor statistics results**
- Ensure sufficient sample count (100+ for statistics)
- Check data quality metrics first
- Verify sample rate is appropriate for signal

---

## Version History

**v0.6.0** (2025-01-08)
- Initial release of Data Acquisition & Logging System
- 3 acquisition modes (continuous, single-shot, triggered)
- 5 trigger types
- 26 REST API endpoints
- WebSocket streaming support
- Advanced statistics (FFT, trend, quality, peaks, crossings)
- Multi-instrument synchronization
- 4 export formats (CSV, NumPy, JSON, HDF5)

---

## Future Enhancements

Planned features for future releases:
- Digital triggering and pattern detection
- Automatic calibration and baseline correction
- Advanced signal processing (filtering, deconvolution)
- Cloud storage integration
- Scheduled/automated acquisitions
- Advanced data compression
- Remote procedure calls for custom analysis

---

## Support

For questions, issues, or feature requests:
- Documentation: See README.md and ROADMAP.md
- Issue Tracker: GitHub Issues
- Examples: See `/examples` directory

---

**End of Documentation**
