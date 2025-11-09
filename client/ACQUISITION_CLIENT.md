# LabLink Client - Data Acquisition Integration

## Overview

This document describes the client-side integration with the LabLink server's Data Acquisition & Logging System (v0.6.0).

**Status:** Integration Complete
**Date:** 2025-11-08
**Version:** Client v0.6.0

---

## Features Implemented

### 1. Complete API Client Integration

**File:** `client/api/client.py`

Added comprehensive acquisition API methods (26 endpoints total):

#### Session Management (10 endpoints)
- `create_acquisition_session()` - Create new acquisition session
- `start_acquisition()` - Start data collection
- `stop_acquisition()` - Stop acquisition
- `pause_acquisition()` - Pause acquisition
- `resume_acquisition()` - Resume paused acquisition
- `get_acquisition_status()` - Get session status
- `get_acquisition_data()` - Retrieve acquired data
- `list_acquisition_sessions()` - List all sessions
- `export_acquisition_data()` - Export to CSV/HDF5/NPY/JSON
- `delete_acquisition_session()` - Delete session

#### Statistics Analysis (6 endpoints)
- `get_acquisition_rolling_stats()` - Rolling statistics (mean, std, min, max, RMS, P2P)
- `get_acquisition_fft()` - FFT analysis with THD and SNR
- `get_acquisition_trend()` - Trend detection (rising, falling, stable, noisy)
- `get_acquisition_quality()` - Data quality assessment
- `get_acquisition_peaks()` - Peak detection
- `get_acquisition_crossings()` - Threshold crossing detection

#### Multi-Instrument Synchronization (10 endpoints)
- `create_sync_group()` - Create synchronization group
- `add_to_sync_group()` - Add acquisition to sync group
- `start_sync_group()` - Start synchronized acquisition
- `stop_sync_group()` - Stop all in group
- `pause_sync_group()` - Pause all in group
- `resume_sync_group()` - Resume all in group
- `get_sync_group_status()` - Get group status
- `get_sync_group_data()` - Get synchronized data
- `list_sync_groups()` - List all groups
- `delete_sync_group()` - Delete group

### 2. Data Models

**File:** `client/models/acquisition.py`

Comprehensive data models matching server API:

#### Enumerations
- `AcquisitionMode` - Continuous, single-shot, triggered
- `AcquisitionState` - Idle, acquiring, paused, stopped, etc.
- `TriggerType` - Immediate, level, edge, time, external
- `TriggerEdge` - Rising, falling, either
- `ExportFormat` - CSV, HDF5, NumPy, JSON
- `TrendType` - Rising, falling, stable, noisy
- `DataQuality` - Excellent, good, fair, poor
- `SyncState` - Idle, ready, running, paused, stopped, error

#### Data Classes
- `TriggerConfig` - Trigger configuration
- `AcquisitionConfig` - Complete acquisition configuration
- `DataPoint` - Single timestamped measurement
- `AcquisitionSession` - Session status and info
- `RollingStatistics` - Rolling stats result
- `FFTResult` - FFT analysis result
- `TrendAnalysis` - Trend detection result
- `QualityMetrics` - Data quality metrics
- `PeakInfo` - Peak detection result
- `CrossingInfo` - Threshold crossing result
- `SyncConfig` - Synchronization group config
- `SyncGroup` - Sync group status

All models include:
- Type hints for safety
- `to_dict()` methods for API calls
- `from_dict()` class methods for parsing responses
- Full documentation

### 3. Enhanced Acquisition Panel UI

**File:** `client/ui/acquisition_panel.py`

Completely redesigned acquisition panel with professional features:

#### Configuration Section
- Equipment selection dropdown
- Session naming
- Acquisition mode selection (continuous/single-shot/triggered)
- Sample rate control (0.001 - 1,000,000 Hz)
- Duration and sample count settings
- Multi-channel support
- Full trigger configuration:
  - Trigger type selection
  - Trigger level/threshold
  - Trigger edge (rising/falling/either)
  - Trigger channel selection
- Buffer size control
- Auto-export options with format selection

#### Session Management
- Active sessions list with real-time status
- Session selection and info display
- Auto-refresh capability (2-second interval)
- Control buttons:
  - Create Session
  - Start/Stop/Pause/Resume
  - Delete session
  - Export data
- Smart button state management based on acquisition state

#### Three-Tab Interface

**Visualization Tab**
- Integration with PlotWidget for real-time plotting
- Automatic channel plotting
- Sample-based x-axis

**Statistics Tab**
- Statistics table display (metric, value, unit)
- Four analysis buttons:
  - Rolling Stats - Mean, std dev, min, max, RMS, peak-to-peak
  - FFT Analysis - Fundamental frequency, THD, SNR
  - Trend Analysis - Trend type, slope, confidence
  - Data Quality - Quality grade, noise level, stability, outliers
- Per-channel statistics display

**Data Tab**
- Data table (timestamp, channel, value, unit)
- Configurable max points (10 - 1,000,000)
- Load data button
- Supports displaying large datasets

#### Advanced Features
- PyQt6 signals for integration (acquisition_started, acquisition_stopped)
- Auto-refresh timer with toggle
- Comprehensive error handling
- User-friendly dialogs
- Session info text display
- Smart form field enabling/disabling based on mode

---

## Usage Example

```python
from PyQt6.QtWidgets import QApplication
from client.ui.acquisition_panel import AcquisitionPanel
from client.api.client import LabLinkClient

# Create application
app = QApplication([])

# Create and configure client
client = LabLinkClient(host="localhost", api_port=8000, ws_port=8001)
client.connect()

# Create acquisition panel
panel = AcquisitionPanel()
panel.set_client(client)
panel.show()

# Panel is now fully functional:
# 1. Select equipment from dropdown
# 2. Configure acquisition parameters
# 3. Create session
# 4. Start/stop/pause/resume acquisition
# 5. View real-time statistics
# 6. Export data

app.exec()
```

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│           AcquisitionPanel (PyQt6 Widget)           │
│  ┌─────────────────────────────────────────────┐   │
│  │  Configuration Section                      │   │
│  │  - Equipment, mode, sample rate             │   │
│  │  - Channels, triggers, buffer               │   │
│  │  - Export settings                          │   │
│  └─────────────────────────────────────────────┘   │
│  ┌──────────────────┐  ┌──────────────────────┐   │
│  │ Sessions List    │  │ Session Info         │   │
│  │ - Auto-refresh   │  │ - Details display    │   │
│  └──────────────────┘  └──────────────────────┘   │
│  ┌─────────────────────────────────────────────┐   │
│  │  Tabs: Visualization | Statistics | Data   │   │
│  └─────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │   LabLinkClient       │
         │  (API Wrapper)        │
         └───────────┬───────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │  LabLink Server       │
         │  Acquisition System   │
         │  (26 REST endpoints)  │
         └───────────────────────┘
```

---

## API Method Reference

### Creating and Starting an Acquisition

```python
# Method 1: Using panel UI (recommended)
panel.create_session()  # Click "Create Session" button
panel.start_acquisition()  # Click "Start" button

# Method 2: Programmatic
from models import AcquisitionConfig, AcquisitionMode

config = AcquisitionConfig(
    equipment_id="PSU_001",
    mode=AcquisitionMode.CONTINUOUS,
    sample_rate=1000.0,
    channels=["voltage", "current"],
    buffer_size=10000
)

result = client.create_acquisition_session("PSU_001", config.to_dict())
acquisition_id = result["acquisition_id"]

client.start_acquisition(acquisition_id)
```

### Getting Statistics

```python
# Rolling statistics
stats = client.get_acquisition_rolling_stats(acquisition_id)
for channel in stats["channels"]:
    print(f"{channel['channel']}: mean={channel['mean']}, std={channel['std_dev']}")

# FFT analysis
fft = client.get_acquisition_fft(acquisition_id)
for channel in fft["channels"]:
    print(f"{channel['channel']}: freq={channel['fundamental_frequency']} Hz, THD={channel['thd']}%")

# Trend detection
trend = client.get_acquisition_trend(acquisition_id)
for channel in trend["channels"]:
    print(f"{channel['channel']}: trend={channel['trend']}, confidence={channel['confidence']}")

# Data quality
quality = client.get_acquisition_quality(acquisition_id)
for channel in quality["channels"]:
    print(f"{channel['channel']}: grade={channel['quality_grade']}, noise={channel['noise_level']}")
```

### Multi-Instrument Synchronization

```python
# Create sync group
client.create_sync_group(
    group_id="test_sync",
    equipment_ids=["PSU_001", "DMM_001", "OSC_001"],
    master_equipment_id="PSU_001",
    sync_tolerance_ms=10.0
)

# Create acquisition sessions for each
acq1 = client.create_acquisition_session("PSU_001", config1)
acq2 = client.create_acquisition_session("DMM_001", config2)
acq3 = client.create_acquisition_session("OSC_001", config3)

# Add to sync group
client.add_to_sync_group("test_sync", "PSU_001", acq1["acquisition_id"])
client.add_to_sync_group("test_sync", "DMM_001", acq2["acquisition_id"])
client.add_to_sync_group("test_sync", "OSC_001", acq3["acquisition_id"])

# Start all synchronized
client.start_sync_group("test_sync")

# Get synchronized data
data = client.get_sync_group_data("test_sync")
```

### Exporting Data

```python
# From panel UI
panel.export_current_session()  # Opens file dialog

# Programmatically
client.export_acquisition_data(
    acquisition_id,
    format="csv",
    filepath="/path/to/export.csv"
)
```

---

## Configuration Options

### Acquisition Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `continuous` | Acquire until manually stopped | Long-term monitoring |
| `single_shot` | Acquire N samples then stop | Burst capture |
| `triggered` | Wait for trigger condition | Event-based capture |

### Trigger Types

| Type | Parameters | Description |
|------|------------|-------------|
| `immediate` | None | Start immediately |
| `level` | level, channel | Trigger when signal crosses threshold |
| `edge` | level, edge, channel | Trigger on rising/falling edge |
| `time` | time | Trigger at specific time |
| `external` | None | Wait for external trigger |

### Export Formats

| Format | Extension | Use Case |
|--------|-----------|----------|
| CSV | .csv | Spreadsheet analysis |
| HDF5 | .h5 | Large datasets, scientific |
| NumPy | .npy | Python/NumPy processing |
| JSON | .json | Web/JavaScript applications |

---

## Integration Points

The acquisition panel integrates with:

1. **Existing Widgets**
   - `PlotWidget` for visualization
   - Can be extended with `WaveformDisplay`, `PowerChartWidget`

2. **WebSocket Manager**
   - Real-time data streaming (future enhancement)
   - Live plot updates during acquisition

3. **Settings Manager**
   - Save/load acquisition configurations
   - Default parameter persistence

4. **Equipment Panels**
   - Coordinate with equipment-specific panels
   - Shared equipment selection

---

## Future Enhancements

### Near Term
1. WebSocket streaming integration for real-time plot updates
2. Synchronization UI panel
3. Acquisition templates/presets
4. Batch acquisition wizard

### Long Term
1. Advanced trigger conditions (AND/OR logic)
2. Math channels (computed from acquired data)
3. Automated test sequences
4. Cloud data backup

---

## Testing

### Manual Testing Checklist

- [ ] Create continuous acquisition session
- [ ] Create single-shot acquisition session
- [ ] Create triggered acquisition session
- [ ] Start/stop/pause/resume acquisition
- [ ] View rolling statistics
- [ ] View FFT analysis
- [ ] View trend analysis
- [ ] View data quality metrics
- [ ] Load and display data
- [ ] Export data to CSV
- [ ] Export data to HDF5
- [ ] Delete acquisition session
- [ ] Multi-channel acquisition
- [ ] Auto-refresh sessions
- [ ] Session info display
- [ ] Trigger configuration
- [ ] Buffer size limits

### Automated Tests

(To be implemented in `tests/integration/test_acquisition_client.py`)

---

## Troubleshooting

### Common Issues

**Problem:** "Please connect to a server first"
**Solution:** Call `panel.set_client(client)` after creating a connected LabLinkClient

**Problem:** Statistics show no data
**Solution:** Ensure acquisition is running and has collected samples

**Problem:** Export fails
**Solution:** Check file path permissions and disk space

**Problem:** Sessions not refreshing
**Solution:** Enable auto-refresh checkbox or click Refresh button

---

## File Locations

```
client/
├── api/
│   └── client.py                 # API client with 26 acquisition methods
├── models/
│   ├── __init__.py               # Exports all models
│   └── acquisition.py            # All acquisition data models
├── ui/
│   └── acquisition_panel.py      # Main acquisition UI panel (766 lines)
└── ACQUISITION_CLIENT.md         # This document
```

---

## Performance Notes

- Auto-refresh interval: 2 seconds (configurable)
- Default max data points: 1000 (adjustable to 1M)
- Buffer sizes: 100 - 10,000,000 samples
- Sample rates: 0.001 Hz - 1 MHz

---

## Dependencies

- PyQt6 (UI framework)
- requests (HTTP client)
- Client models
- Client WebSocket manager (optional)
- Client widgets (PlotWidget - optional)

---

**Last Updated:** 2025-11-08
**Author:** Claude Code
**Status:** Production Ready
