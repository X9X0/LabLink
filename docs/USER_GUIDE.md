## LabLink User Guide

Complete guide for using the LabLink laboratory equipment control system.

## Table of Contents

1. [Introduction](#introduction)
2. [Installation](#installation)
3. [Getting Started](#getting-started)
4. [Connecting to a Server](#connecting-to-a-server)
5. [Working with Equipment](#working-with-equipment)
6. [Data Acquisition](#data-acquisition)
7. [Real-Time Monitoring](#real-time-monitoring)
8. [Equipment Control Panels](#equipment-control-panels)
9. [Settings and Configuration](#settings-and-configuration)
10. [Troubleshooting](#troubleshooting)

## Introduction

**LabLink** is a comprehensive laboratory equipment control system that provides:

- **Centralized Control** - Control multiple instruments from one interface
- **Real-Time Monitoring** - Live data visualization and streaming
- **Data Acquisition** - Capture and export measurement data
- **Equipment Discovery** - Automatic detection of available instruments
- **Remote Access** - Client-server architecture for remote operation

**Architecture:**
- **Server** - Communicates with equipment, manages data
- **Client** - User interface for control and monitoring
- **Communication** - HTTP REST API + WebSocket streaming

## Installation

### Prerequisites

- **Python 3.11 or higher**
- **Operating System:** Windows, macOS, or Linux
- **Network:** Local network access to server

### Client Installation

```bash
# Clone repository
git clone https://github.com/yourusername/LabLink.git
cd LabLink

# Install client dependencies
cd client
pip install -r requirements.txt

# Optional: Install for server discovery
pip install zeroconf
```

### Server Installation

If you're setting up the server:

```bash
# Install server dependencies
cd server
pip install -r requirements.txt

# Run server
python main.py
```

### Verify Installation

```bash
# Test client can run
cd client
python main.py --help

# Should show usage information
```

## Getting Started

### Starting the Client

```bash
cd client
python main.py
```

The LabLink client window will open showing the connection dialog.

### First Connection

**Option 1: Automatic Discovery (Recommended)**

1. Click "**Discover Servers**" button
2. Wait 5-10 seconds for servers to appear
3. Select your server from the list
4. Click "**Connect**"

**Option 2: Manual Connection**

1. Enter server details:
   - **Host:** IP address or hostname (e.g., `192.168.1.100` or `labserver.local`)
   - **API Port:** Usually `8000`
   - **WebSocket Port:** Usually `8001`
2. Click "**Connect**"

**Option 3: Recent Servers**

- Previously connected servers appear in the recent servers list
- Click a server to select it
- Click "**Connect**"

### Connection Status

Connection status is shown in the status bar:

- **🔴 Disconnected** - Not connected to server
- **🟢 Connected: server:port** - Successfully connected
- **🟡 Connecting...** - Connection in progress
- **🔴 Connection Error** - Failed to connect

## Connecting to a Server

### Connection Dialog

The connection dialog provides multiple ways to connect:

```
┌─────────────────────────────────────────┐
│  Connect to LabLink Server              │
├─────────────────────────────────────────┤
│  Host: [192.168.1.100        ]          │
│  API Port: [8000]  WS Port: [8001]      │
│                                         │
│  Recent Servers:                        │
│  ○ Lab Server (192.168.1.100:8000)     │
│  ○ Local Server (localhost:8000)       │
│                                         │
│  [ Discover Servers ]                  │
│                                         │
│  [×] Auto-connect on startup           │
│                                         │
│         [Connect]  [Cancel]            │
└─────────────────────────────────────────┘
```

### Server Discovery

Click "**Discover Servers**" to automatically find LabLink servers on your network:

1. **Discovery dialog opens**
2. **Servers appear** in table as they're found
3. **Select a server** from the list
4. **Click Connect** or double-click server

Discovery shows:
- Server name
- IP address
- API port
- WebSocket port
- Server version

### Auto-Connect

Enable "**Auto-connect on startup**" to automatically connect to the last server when launching the client.

### Connection Troubleshooting

**Can't find server:**
- Verify server is running: `curl http://server-ip:8000/health`
- Check firewall settings
- Ensure client and server on same network
- Try manual connection with IP address

**Connection refused:**
- Server may not be running
- Wrong port number
- Firewall blocking connection

**Connection timeout:**
- Server unreachable
- Network issues
- Wrong IP address

## Working with Equipment

### Equipment Panel

After connecting, the Equipment panel shows all available equipment.

```
┌─────────────────────────────────────────────────┐
│  Equipment                                      │
├─────────────────────────────────────────────────┤
│  [ Refresh ]  [ Discover ]  [ Filters ▼ ]      │
│                                                 │
│  Name          │ Type         │ Status         │
│  ──────────────┼──────────────┼────────────────│
│  Scope 1       │ Oscilloscope │ Connected ✓    │
│  Power Supply  │ PSU          │ Connected ✓    │
│  Load Bank     │ E-Load       │ Disconnected   │
│  ──────────────┴──────────────┴────────────────│
│                                                 │
│  Equipment Details:                            │
│  Model: Rigol DS1054Z                          │
│  Manufacturer: Rigol                           │
│  Serial: DS1ZA123456789                        │
│  Capabilities: 4 channels, 50 MHz, 1 GSa/s    │
└─────────────────────────────────────────────────┘
```

### Equipment Actions

**Refresh** - Update equipment list
**Discover** - Scan for new equipment
**Connect** - Connect to selected equipment
**Disconnect** - Disconnect from equipment
**Control** - Open control panel for equipment

### Equipment Types

LabLink supports various equipment types:

- **Oscilloscopes** - Waveform capture and analysis
- **Power Supplies** - Voltage/current sources
- **Electronic Loads** - Programmable loads
- **Function Generators** - Signal generation
- **Multimeters** - Measurement instruments
- **And more...**

### Equipment Discovery

Click "**Discover**" to scan for new equipment:

1. Server queries all configured interfaces (USB, GPIB, Ethernet)
2. Detected equipment appears in list
3. Equipment automatically connects if configured
4. Status updates show connection progress

## Data Acquisition

### Acquisition Panel

The Acquisition panel manages data collection from equipment.

### Starting an Acquisition

1. **Select Equipment** from dropdown
2. **Configure Settings:**
   - Sample rate (Hz)
   - Duration (seconds) or continuous
   - Channels to record
3. **Click "Start Acquisition"**

### Acquisition Modes

**Single Shot:**
- Capture one dataset
- Specified duration
- Automatically stops

**Continuous:**
- Runs until manually stopped
- Circular buffer (keeps last N samples)
- Real-time display updates

**Triggered:**
- Waits for trigger condition
- Captures when triggered
- Can re-arm for multiple captures

### Acquisition Controls

- **Start** - Begin acquisition
- **Stop** - Stop acquisition
- **Pause** - Pause without stopping
- **Resume** - Continue paused acquisition
- **Clear** - Clear buffer and reset

### Data Export

After acquisition:

1. Click "**Export Data**"
2. Choose format:
   - CSV - Comma-separated values
   - JSON - Structured data format
   - HDF5 - High-performance binary format
   - MATLAB - .mat file format
3. Select location
4. Click "**Save**"

### Auto-Export

Enable auto-export in Settings to automatically save data after each acquisition.

## Real-Time Monitoring

### Live Data Display

LabLink provides real-time visualization of equipment data:

### Starting Monitoring

1. **Select Equipment**
2. **Choose Monitoring Type:**
   - Waveform (oscilloscope)
   - Readings (power supply, load)
   - Parameters (any equipment)
3. **Click "Start Monitoring"**

### Chart Controls

**Pause/Resume** - Freeze/unfreeze display
**Clear** - Clear chart data
**Auto-Scale** - Automatically adjust axes
**Zoom** - Mouse wheel or drag to zoom
**Pan** - Right-click drag to pan

### Chart Features

- **Multi-channel** - Display multiple signals
- **Color-coded** - Each channel different color
- **Legend** - Show/hide channel names
- **Cursor** - Measure values at points
- **Statistics** - Min/max/average display

### Update Rate

Adjust update rate in Settings:
- **Fast (20 Hz)** - Smooth but higher CPU usage
- **Medium (10 Hz)** - Balanced
- **Slow (5 Hz)** - Lower CPU usage

## Equipment Control Panels

Equipment-specific control panels provide tailored interfaces for different instruments.

### Oscilloscope Panel

**Display Tab:**
- 4-channel waveform display
- Real-time waveform streaming
- Auto-scaling and cursors
- Pause/resume/clear controls

**Controls Tab:**
- Timebase configuration
- Channel settings (scale, coupling, offset)
- Trigger controls (mode, source, level)
- Autoscale and default setup

**Measurements Tab:**
- Automated measurements (Vpp, Vrms, frequency)
- Per-channel statistics
- Export measurements

**Usage:**
1. Select oscilloscope from equipment list
2. Click "**Control**" to open panel
3. Configure channels and timebase
4. Click "**Start Streaming**" for live display
5. Use measurements tab for analysis

### Power Supply Panel

**Control Tab:**
- Channel selection (1-3)
- Voltage control (spinbox + slider)
- Current limit (spinbox + slider)
- Output enable/disable
- Apply settings button
- Set to zero button

**Monitor Tab:**
- Real-time V/I/P chart
- CV/CC mode indication
- Historical data

**Usage:**
1. Select power supply
2. Open control panel
3. Select channel
4. Set voltage and current
5. Enable output
6. Monitor in real-time

### Electronic Load Panel

**Control Tab:**
- Mode selection (CC/CV/CR/CP)
- Setpoint control (changes with mode)
- Input enable/disable
- Real-time readings display
- Mode indicator

**Monitor Tab:**
- Real-time V/I/P chart
- Mode-specific data

**Usage:**
1. Select electronic load
2. Open control panel
3. Choose mode (CC, CV, CR, or CP)
4. Set appropriate value
5. Enable input
6. Monitor performance

## Settings and Configuration

### Opening Settings

Click **Settings** menu → **Preferences** or press `Ctrl+,`

### Settings Tabs

**Connection:**
- Default server host
- API port
- WebSocket port
- Auto-connect on startup
- Recent servers management

**Acquisition:**
- Default sample rate
- Buffer size
- Auto-export enabled
- Export directory
- Export format

**Visualization:**
- Plot buffer size
- Update rate (Hz)
- Theme (Light/Dark/System)
- Chart style

**Advanced:**
- Settings file location
- Import/Export settings
- Reset to defaults
- Clear all settings

### Importing/Exporting Settings

**Export Settings:**
1. Open Settings
2. Click "**Export...**"
3. Choose location
4. Save as JSON file

**Import Settings:**
1. Open Settings
2. Click "**Import...**"
3. Select JSON file
4. Settings applied immediately

**Use Case:** Share configuration between computers or backup settings.

### Resetting Settings

1. Open Settings
2. Go to Advanced tab
3. Click "**Reset to Defaults**"
4. Confirm reset

**Warning:** This clears all saved settings including recent servers and favorites.

## Troubleshooting

### Connection Issues

**Problem:** Can't connect to server

**Solutions:**
1. Verify server is running:
   ```bash
   curl http://server-ip:8000/health
   ```
2. Check network connectivity:
   ```bash
   ping server-ip
   ```
3. Verify ports:
   - API port (usually 8000)
   - WebSocket port (usually 8001)
4. Check firewall settings
5. Try manual connection with IP address

### Equipment Not Found

**Problem:** Equipment doesn't appear in list

**Solutions:**
1. Click "**Refresh**" to update list
2. Click "**Discover**" to scan for equipment
3. Check equipment is powered on
4. Verify USB/GPIB/network connections
5. Check server logs for detection errors

### Visualization Performance

**Problem:** Charts are slow or laggy

**Solutions:**
1. Reduce update rate in Settings
2. Decrease plot buffer size
3. Close other applications
4. Reduce number of active channels
5. Use hardware acceleration if available

### Data Export Fails

**Problem:** Can't export data

**Solutions:**
1. Check write permissions for directory
2. Ensure enough disk space
3. Verify export format is supported
4. Try different export location
5. Check logs for error details

### GUI Issues

**Problem:** Interface doesn't display correctly

**Solutions:**
1. Update PyQt6: `pip install --upgrade PyQt6`
2. Try different theme (Light/Dark)
3. Adjust display scaling in OS
4. Check graphics drivers
5. Restart application

### Settings Not Saving

**Problem:** Settings don't persist between sessions

**Solutions:**
1. Check settings file location (in Settings → Advanced)
2. Verify write permissions
3. Click "Sync to Disk" in Advanced settings
4. Check disk space
5. Try exporting/importing settings

## Keyboard Shortcuts

### General
- `Ctrl+Q` - Quit application
- `Ctrl+,` - Open settings
- `F1` - Help
- `F5` - Refresh

### Connection
- `Ctrl+D` - Discover servers
- `Ctrl+N` - New connection
- `Ctrl+Shift+C` - Connect/Disconnect

### Charts
- `Space` - Pause/Resume
- `Ctrl+0` - Auto-scale
- `Ctrl++` - Zoom in
- `Ctrl+-` - Zoom out
- `Ctrl+R` - Reset zoom
- `C` - Clear chart

### Equipment
- `Ctrl+E` - Equipment panel
- `Ctrl+O` - Open control panel
- `Ctrl+M` - Start/Stop monitoring

## Tips and Best Practices

### 1. Use Server Discovery

Enable mDNS discovery for easy server connection without manual IP entry.

### 2. Save Frequently Used Settings

Use Settings export to backup your configuration before making changes.

### 3. Enable Auto-Connect

For dedicated setups, enable auto-connect to save time on startup.

### 4. Monitor Performance

Watch CPU usage and adjust visualization settings if performance issues occur.

### 5. Regular Equipment Discovery

Run discovery periodically to detect newly connected equipment.

### 6. Use Appropriate Buffer Sizes

Larger buffers use more memory but provide more history. Adjust based on needs.

### 7. Export Data Regularly

Enable auto-export or regularly export important data to prevent loss.

### 8. Keep Software Updated

Update LabLink and dependencies regularly for bug fixes and new features.

## Getting Help

### Documentation

- **User Guide** - This document
- **API Reference** - docs/API_REFERENCE.md
- **Equipment Panels** - docs/EQUIPMENT_PANELS.md
- **WebSocket Streaming** - docs/WEBSOCKET_STREAMING.md
- **Settings** - docs/SETTINGS.md
- **mDNS Discovery** - docs/MDNS_DISCOVERY.md
- **Testing** - docs/TEST_SUITE.md

### Support Channels

- **GitHub Issues** - Report bugs and feature requests
- **Documentation** - Check docs/ directory
- **Server Logs** - Check server/lablink_server.log
- **Client Logs** - Check client/lablink_client.log

### Reporting Issues

When reporting issues, include:

1. **Steps to reproduce**
2. **Expected behavior**
3. **Actual behavior**
4. **System information** (OS, Python version)
5. **Log files** (if applicable)
6. **Screenshots** (for UI issues)

### Example Issue Report

```
Title: Connection to server fails with timeout

Description:
When attempting to connect to server at 192.168.1.100:8000,
connection times out after 30 seconds.

Steps to Reproduce:
1. Open LabLink client
2. Enter host: 192.168.1.100, port: 8000
3. Click Connect
4. Wait 30 seconds
5. Connection fails with timeout error

Expected: Connection succeeds
Actual: Timeout error

System Info:
- OS: Windows 11
- Python: 3.11.4
- LabLink version: 1.0.0
- Network: Same subnet as server

Logs:
[Attach client log showing timeout error]
```

## Appendix

### Supported Equipment

LabLink supports equipment through:

- **Native Drivers** - Built-in support for common instruments
- **SCPI Protocol** - Generic support for SCPI-compatible equipment
- **Custom Drivers** - Extensible driver system

**Currently Supported:**
- Rigol oscilloscopes (DS1000Z, DS1000Z-E series)
- Rigol electronic loads (DL3000 series)
- BK Precision power supplies
- Keysight equipment (various models)
- Generic SCPI instruments

### File Formats

**CSV (Comma-Separated Values):**
- Human-readable
- Excel compatible
- Good for simple data

**JSON (JavaScript Object Notation):**
- Structured data
- Includes metadata
- Easy to parse

**HDF5 (Hierarchical Data Format):**
- High performance
- Large datasets
- Binary format
- MATLAB/Python compatible

**MATLAB (.mat):**
- Native MATLAB format
- Direct import to MATLAB
- Includes variable names

### Network Ports

- **8000** - HTTP API (default)
- **8001** - WebSocket streaming (default)
- **5353** - mDNS/Zeroconf (UDP)

Ensure these ports are open in firewall for proper operation.

### System Requirements

**Minimum:**
- CPU: Dual-core 2 GHz
- RAM: 4 GB
- Storage: 500 MB
- Display: 1024x768
- Network: 100 Mbps

**Recommended:**
- CPU: Quad-core 3 GHz
- RAM: 8 GB
- Storage: 2 GB SSD
- Display: 1920x1080
- Network: 1 Gbps

---

**Version:** 1.0.0
**Last Updated:** 2024-11-08
**Copyright:** © 2024 LabLink Project
