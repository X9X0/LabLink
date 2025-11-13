# LabLink

A modular client-server application for remote control and data acquisition from laboratory equipment (Rigol and BK Precision scopes, power supplies, and loads).

## Overview

LabLink enables remote control of lab equipment through a Raspberry Pi server, providing an intuitive graphical client for equipment management, data acquisition, and visualization.

## Architecture

- **Server**: Python-based server running on Raspberry Pi, connected to lab equipment via USB/Serial/Ethernet
- **Client**: Cross-platform desktop GUI for equipment control, monitoring, and data visualization
- **Communication**: WebSocket for real-time data streaming, REST API for control commands

## Features

### Implemented ✓

- [x] Modular driver architecture for equipment
- [x] REST API for equipment control and management
- [x] WebSocket support for real-time data streaming
- [x] Device discovery via VISA
- [x] Multi-device connection management
- [x] Configurable data buffering and formats
- [x] Complete equipment drivers for Rigol and BK Precision devices
- [x] Comprehensive configuration management (65+ settings)
- [x] Error handling with auto-reconnect and health monitoring
- [x] Equipment profile system (save/load configurations)
- [x] Safety limits and interlocks (voltage/current/power limits, emergency stop)
- [x] Equipment lock/session management (multi-user access control, exclusive/observer modes)
- [x] Equipment state management (capture/restore/compare states, versioning)
- [x] **Data acquisition & logging system** (continuous/triggered modes, 26 API endpoints)
  - [x] Multiple acquisition modes (continuous, single-shot, triggered)
  - [x] Advanced statistics (FFT, trend detection, data quality assessment)
  - [x] Multi-instrument synchronization
  - [x] Real-time WebSocket streaming
  - [x] Multiple export formats (CSV, NumPy, JSON, HDF5)
- [x] **Advanced logging system** (structured logging, rotation, metrics)
  - [x] Structured JSON logging with multiple formatters
  - [x] Automatic log rotation and compression
  - [x] Performance metrics logging
  - [x] Audit trail and access logs
  - [x] Equipment event logging
- [x] **Alarm & notification system** (threshold monitoring, multi-channel alerts)
  - [x] 8 alarm types (threshold, deviation, rate-of-change, equipment error, etc.)
  - [x] 4 severity levels (info, warning, error, critical)
  - [x] Multi-channel notifications (email, SMS, WebSocket)
  - [x] Automatic alarm monitoring and lifecycle management
  - [x] Alarm history and statistics
  - [x] 16 alarm management API endpoints
- [x] **Scheduled operations** (automated tasks with APScheduler)
  - [x] 6 schedule types (acquisition, state capture, measurement, command, test, script)
  - [x] 6 trigger types (cron, interval, date, daily, weekly, monthly)
  - [x] Job execution history and statistics
  - [x] Job pause/resume/manual trigger
  - [x] Maximum execution limits and date ranges
  - [x] 14 scheduler API endpoints
- [x] **Equipment diagnostics** (health monitoring and performance benchmarking)
  - [x] Comprehensive health checks (connection, communication, performance, functionality)
  - [x] Equipment health scoring (0-100) with status levels
  - [x] Performance benchmarking and command latency measurement
  - [x] Communication statistics (success rate, response times, error tracking)
  - [x] System-wide diagnostics and resource monitoring
  - [x] Diagnostic report generation
  - [x] 11 diagnostics API endpoints
- [x] **Waveform capture & analysis** (professional oscilloscope functionality)
  - [x] High-speed waveform acquisition with averaging and decimation
  - [x] 30+ enhanced automatic measurements (voltage, time, signal quality, statistical)
  - [x] Cursor measurements (horizontal/vertical with delta calculations)
  - [x] 15 math operations (add, subtract, FFT, integrate, differentiate, etc.)
  - [x] Persistence mode (infinite, envelope, variable decay)
  - [x] Histogram analysis (voltage/time distributions with statistics)
  - [x] XY mode (channel vs channel plots)
  - [x] Continuous acquisition (up to 100 Hz)
  - [x] 25+ waveform API endpoints

- [x] **Desktop GUI client** (PyQt6-based cross-platform application)
  - [x] Equipment control and monitoring
  - [x] Data acquisition interface
  - [x] Alarm monitoring and acknowledgment
  - [x] Scheduler management interface
  - [x] Diagnostics and health monitoring dashboard
  - [x] Server connection management

### In Development

- [ ] Real-time data visualization (pyqtgraph integration)
- [ ] Automatic Raspberry Pi network discovery (mDNS/Bonjour)
- [ ] SSH-based server deployment wizard
- [ ] WebSocket streaming integration
- [ ] Multi-server connection management

## Supported Equipment

- Rigol MSO2072A Oscilloscope
- Rigol DS1104 Oscilloscope
- Rigol DL3021A DC Electronic Load
- BK Precision 9206B Multi-Range DC Power Supply
- BK Precision 9205B Multi-Range DC Power Supply
- BK Precision 9130 DC Power Supply
- BK Precision 1902B DC Electronic Load
- BK Precision 1685B DC Power Supply

## Technology Stack

- **Language**: Python 3.11+
- **Server**: FastAPI, PyVISA
- **Client**: PyQt6, pyqtgraph
- **Communication**: WebSockets, REST API
- **Data Formats**: CSV, HDF5, NumPy binary

## Quick Start

### Server Setup

1. Install dependencies:
   ```bash
   cd server
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Run the server:
   ```bash
   python main.py
   ```

3. Access API documentation:
   - Open browser to `http://localhost:8000/docs`

### GUI Client Setup

1. Install dependencies:
   ```bash
   cd client
   pip install -r requirements.txt
   ```

2. Run the GUI client:
   ```bash
   python main.py
   ```

3. Connect to server:
   - Click "Connect to Server..." or press Ctrl+N
   - Use "Localhost" quick connect for local server
   - Or enter custom hostname/IP and ports

For detailed setup instructions, see [Getting Started Guide](docs/GETTING_STARTED.md) and [Client README](client/README.md).

## Documentation

- [Getting Started Guide](docs/GETTING_STARTED.md) - Installation and setup
- [API Reference](docs/API_REFERENCE.md) - Complete API documentation with examples
- [Data Acquisition System](server/ACQUISITION_SYSTEM.md) - Comprehensive guide to data acquisition features
- [Advanced Logging System](server/LOGGING_SYSTEM.md) - Logging configuration and best practices
- [Alarm & Notification System](server/ALARM_SYSTEM.md) - Alarm configuration and notification setup
- [Scheduled Operations](server/SCHEDULER_SYSTEM.md) - Job scheduling and automation
- [Equipment Diagnostics](server/DIAGNOSTICS_SYSTEM.md) - Health monitoring and performance diagnostics
- [Waveform Capture & Analysis](server/WAVEFORM_USER_GUIDE.md) - Advanced oscilloscope functionality
- [Development Roadmap](server/ROADMAP.md) - Planned features and enhancements

## Project Status

**Current Version**: v0.16.0

**Phase 1 Complete**: Core server functionality & multi-user support
- ✅ REST API operational (90+ endpoints)
- ✅ WebSocket streaming functional
- ✅ All equipment drivers working
- ✅ Configuration management system
- ✅ Error handling & recovery
- ✅ Equipment profiles
- ✅ Safety limits & interlocks
- ✅ Equipment lock/session management
- ✅ Equipment state management

**Phase 2 Complete**: Data acquisition & advanced features
- ✅ Continuous, single-shot, and triggered acquisition modes
- ✅ Advanced statistics (FFT, trend detection, data quality)
- ✅ Multi-instrument synchronization
- ✅ Real-time WebSocket streaming
- ✅ Multiple export formats (CSV, NumPy, JSON, HDF5)
- ✅ 26 acquisition API endpoints

**Phase 2.5 Complete**: Operations & monitoring (Logging, Alarms, Scheduling, Diagnostics)
- ✅ Advanced logging system (JSON, rotation, audit trails, performance metrics)
- ✅ Alarm & notification system (8 types, multi-channel, 16 endpoints)
- ✅ Scheduled operations (6 schedule types, 6 triggers, 14 endpoints)
- ✅ Equipment diagnostics (health checks, benchmarking, 11 endpoints)
- ✅ Comprehensive documentation for all systems

**Phase 3 Complete**: GUI Client (PyQt6 desktop application)
- ✅ Full-featured desktop GUI with tabbed interface
- ✅ Equipment control panel with SCPI command interface
- ✅ Data acquisition interface with configuration
- ✅ Alarm monitoring with color-coded severity
- ✅ Scheduler management interface
- ✅ Diagnostics dashboard with health scoring
- ✅ Server connection management
- ✅ 40+ API client methods
- ✅ 2,200+ lines of GUI code

**Next Phase**: Advanced visualization & multi-server support

## Contributing

This project is in active development. Contributions, feature requests, and bug reports are welcome!

## License

TBD
