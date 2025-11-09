# LabLink Quick Reference

Quick reference guide for common tasks and keyboard shortcuts.

## Quick Start

### 1. Connect to Server

```bash
# Start client
cd client
python main.py
```

**Option A: Auto Discovery**
1. Click "Discover Servers"
2. Select server from list
3. Click "Connect"

**Option B: Manual**
1. Enter host: `192.168.1.100`
2. Enter ports: API `8000`, WS `8001`
3. Click "Connect"

### 2. Control Equipment

1. Select equipment from list
2. Click "Control" button
3. Use equipment-specific panel
4. Click "Start Monitoring" for live data

### 3. Export Data

1. Click "Export Data" button
2. Choose format (CSV, JSON, HDF5)
3. Select save location
4. Click "Save"

## Keyboard Shortcuts

### General
| Shortcut | Action |
|----------|--------|
| `Ctrl+Q` | Quit application |
| `Ctrl+,` | Open settings |
| `F1` | Help |
| `F5` | Refresh |

### Connection
| Shortcut | Action |
|----------|--------|
| `Ctrl+D` | Discover servers |
| `Ctrl+N` | New connection |
| `Ctrl+Shift+C` | Connect/Disconnect |

### Equipment
| Shortcut | Action |
|----------|--------|
| `Ctrl+E` | Equipment panel |
| `Ctrl+O` | Open control panel |
| `Ctrl+M` | Start/Stop monitoring |

### Charts
| Shortcut | Action |
|----------|--------|
| `Space` | Pause/Resume |
| `Ctrl+0` | Auto-scale |
| `Ctrl++` | Zoom in |
| `Ctrl+-` | Zoom out |
| `Ctrl+R` | Reset zoom |
| `C` | Clear chart |

## Common Tasks

### Connect to Server

**Auto Discovery:**
```python
from client.ui.discovery_dialog import show_discovery_dialog

server = show_discovery_dialog(timeout=10.0)
if server:
    # Connect to server
    client.connect_to(server['address'], server['port'])
```

**Manual:**
```python
from client.api.client import LabLinkClient

client = LabLinkClient(host="192.168.1.100", api_port=8000, ws_port=8001)
if client.connect():
    print("Connected!")
```

### Control Power Supply

```python
# Set voltage and current
psu.voltage_spin.setValue(12.0)
psu.current_spin.setValue(2.0)

# Enable output
psu.output_checkbox.setChecked(True)

# Apply settings
psu._on_apply_settings()

# Start monitoring
psu._on_start_monitoring()
```

### Capture Oscilloscope Waveform

```python
# Configure channel
scope.set_channel_enabled(1, True)
scope.set_channel_scale(1, 1.0)  # 1 V/div

# Get waveform
waveform = await scope.get_waveform(1)

# Start streaming
await scope._start_streaming()
```

### Export Data

```python
# Export acquisition data
data = acquisition.get_data()

# Save as CSV
with open('data.csv', 'w') as f:
    writer = csv.writer(f)
    writer.writerow(['Time', 'Channel1', 'Channel2'])
    writer.writerows(data)

# Save as JSON
with open('data.json', 'w') as f:
    json.dump(data, f, indent=2)
```

## Equipment Control Quick Reference

### Oscilloscope

**Setup:**
1. Select channel
2. Set timebase (1 ms/div)
3. Set scale (1 V/div)
4. Configure trigger
5. Click "Run"

**Measure:**
1. Click "Measurements" tab
2. Select channel
3. Click "Get Measurements"
4. View Vpp, Vrms, frequency

**Stream:**
1. Click "Display" tab
2. Click "Start Streaming"
3. View real-time waveforms
4. Click "Stop Streaming" when done

### Power Supply

**Setup:**
1. Select channel (1-3)
2. Set voltage (0-30V)
3. Set current limit (0-5A)
4. Click "Apply Settings"

**Enable Output:**
1. Check "Output Enabled"
2. Click "Apply Settings"

**Monitor:**
1. Click "Monitor" tab
2. Click "Start Monitoring"
3. View V/I/P in real-time
4. Watch for CV/CC mode

### Electronic Load

**Setup:**
1. Select mode (CC/CV/CR/CP)
2. Set appropriate value:
   - CC: Current (A)
   - CV: Voltage (V)
   - CR: Resistance (Ω)
   - CP: Power (W)
3. Click "Apply Settings"

**Enable Input:**
1. Check "Input Enabled"
2. Click "Apply Settings"

**Monitor:**
1. Click "Monitor" tab
2. Click "Start Monitoring"
3. View real-time data
4. Monitor mode indicator

## Settings Quick Reference

### Connection Settings

```python
from client.utils.settings import get_settings

settings = get_settings()

# Save connection
settings.set_last_host("192.168.1.100")
settings.set_last_api_port(8000)
settings.set_last_ws_port(8001)

# Enable auto-connect
settings.set_auto_connect(True)

# Add to recent servers
settings.add_recent_server(
    host="192.168.1.100",
    api_port=8000,
    ws_port=8001,
    name="Lab Server"
)
```

### Visualization Settings

```python
# Set update rate
settings.set_plot_update_rate(50)  # 50ms = 20 Hz

# Set buffer size
settings.set_plot_buffer_size(1000)  # 1000 points

# Set theme
settings.set_theme("dark")  # "light", "dark", "system"
```

### Acquisition Settings

```python
# Set defaults
settings.set_default_sample_rate(1000.0)  # 1 kHz
settings.set_default_buffer_size(10000)

# Enable auto-export
settings.set_auto_export(True)
settings.set_export_directory("/home/user/data")
```

## WebSocket Streaming Quick Reference

### Start Stream

```python
await client.start_equipment_stream(
    equipment_id="scope_001",
    stream_type="waveform",
    interval_ms=100  # 10 Hz
)
```

### Handle Data

```python
def on_data(message):
    if message['type'] == 'stream_data':
        data = message['data']
        # Process data...

client.register_stream_data_handler(on_data)
```

### Stop Stream

```python
await client.stop_equipment_stream(
    equipment_id="scope_001",
    stream_type="waveform"
)
```

## mDNS Discovery Quick Reference

### Server Side

```python
from server.utils.mdns import LabLinkMDNSService

# Start broadcasting
mdns = LabLinkMDNSService(port=8000, ws_port=8001)
mdns.start()

# Update properties
mdns.update_properties({'status': 'running'})

# Stop
mdns.stop()
```

### Client Side

```python
from client.utils.mdns_discovery import discover_servers

# Discover servers
servers = discover_servers(timeout=5.0)

for server in servers:
    print(f"{server.name}: {server.address}:{server.port}")
```

## Troubleshooting Quick Reference

### Connection Issues

**Problem:** Can't connect to server

**Quick Fix:**
```bash
# Test server
curl http://server-ip:8000/health

# Ping server
ping server-ip

# Check ports
netstat -an | grep 8000
```

### Equipment Not Found

**Quick Fix:**
1. Click "Refresh" button
2. Click "Discover" button
3. Check USB/GPIB connections
4. Verify equipment is powered on

### Slow Visualization

**Quick Fix:**
1. Open Settings (`Ctrl+,`)
2. Reduce update rate to 100ms
3. Reduce buffer size to 500
4. Close other applications

### Data Export Fails

**Quick Fix:**
1. Check disk space: `df -h`
2. Verify directory permissions
3. Try different export location
4. Check logs for errors

## Command Line Reference

### Server

```bash
# Start server
cd server
python main.py

# Start with custom port
python main.py --port 8080

# Enable debug logging
python main.py --log-level DEBUG
```

### Client

```bash
# Start client
cd client
python main.py

# Start with specific server
python main.py --host 192.168.1.100 --port 8000
```

### Testing

```bash
# Run all tests
python run_tests.py

# Run unit tests only
python run_tests.py --unit

# Run with coverage
python run_tests.py --coverage --html

# Run specific test
python run_tests.py --file tests/unit/test_settings.py
```

## API Quick Reference

### REST API

```bash
# Server info
GET http://server:8000/

# Health check
GET http://server:8000/health

# List equipment
GET http://server:8000/api/equipment

# Get equipment info
GET http://server:8000/api/equipment/{id}

# Connect to equipment
POST http://server:8000/api/equipment/{id}/connect

# Send command
POST http://server:8000/api/equipment/{id}/command
Content-Type: application/json
{
  "command": "set_voltage",
  "parameters": {"voltage": 12.0}
}
```

### Python Client API

```python
from client.api.client import LabLinkClient

client = LabLinkClient(host="localhost", api_port=8000, ws_port=8001)

# Connect
client.connect()

# Get server info
info = client.get_server_info()

# List equipment
equipment = client.list_equipment()

# Connect to equipment
client.connect_equipment("scope_001")

# Send command
await client.send_command(
    equipment_id="scope_001",
    command="set_channel_scale",
    parameters={"channel": 1, "scale": 1.0}
)

# Start stream
await client.start_equipment_stream(
    equipment_id="scope_001",
    stream_type="waveform",
    interval_ms=100
)
```

## File Locations

### Configuration

- **Linux:** `~/.config/LabLink/LabLinkClient.conf`
- **Windows:** `HKEY_CURRENT_USER\Software\LabLink\LabLinkClient`
- **macOS:** `~/Library/Preferences/com.LabLink.LabLinkClient.plist`

### Logs

- **Server:** `server/lablink_server.log`
- **Client:** `client/lablink_client.log`

### Data Export

- **Default:** `~/Documents/LabLink/`
- **Custom:** Set in Settings → Acquisition → Export Directory

## Network Ports

- **8000** - HTTP REST API
- **8001** - WebSocket streaming
- **5353** - mDNS/Zeroconf (UDP)

## Environment Variables

```bash
# Set display for GUI (WSL/Linux)
export DISPLAY=:0

# Enable debug logging
export LABLINK_DEBUG=1

# Set custom config path
export LABLINK_CONFIG_PATH=/path/to/config
```

## Status Indicators

### Connection Status

- 🔴 **Disconnected** - Not connected to server
- 🟡 **Connecting...** - Connection in progress
- 🟢 **Connected** - Successfully connected
- 🔴 **Error** - Connection error

### Equipment Status

- ✓ **Connected** - Equipment ready
- ⏸ **Disconnected** - Not connected
- ⚠ **Error** - Equipment error
- 🔄 **Busy** - Operation in progress

### Streaming Status

- ▶ **Streaming** - Data streaming active
- ⏸ **Paused** - Stream paused
- ⏹ **Stopped** - Stream stopped
- ⚠ **Error** - Stream error

## Data Formats

### CSV

```csv
Time,Channel1,Channel2,Channel3
0.000,1.234,2.345,3.456
0.001,1.235,2.346,3.457
0.002,1.236,2.347,3.458
```

### JSON

```json
{
  "timestamp": 1699999999.123,
  "equipment_id": "scope_001",
  "channels": [1, 2, 3],
  "data": {
    "time": [0.0, 0.001, 0.002],
    "channel1": [1.234, 1.235, 1.236],
    "channel2": [2.345, 2.346, 2.347]
  }
}
```

## Resources

- **Documentation:** `docs/`
- **Examples:** `examples/` (if available)
- **Tests:** `tests/`
- **GitHub:** https://github.com/yourusername/LabLink
- **Issues:** https://github.com/yourusername/LabLink/issues

---

**Version:** 1.0.0
**Last Updated:** 2024-11-08
**Print-Friendly:** Yes
**Pages:** 5-6 when printed
