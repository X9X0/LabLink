# LabLink

![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)
![Coverage](https://img.shields.io/badge/coverage-26%25-yellow.svg)
![Security](https://img.shields.io/badge/security-hardened-brightgreen.svg)

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
- [x] **Data analysis pipeline** (comprehensive signal processing and quality control)
  - [x] Signal filtering (Butterworth, Chebyshev, Bessel, Elliptic, FIR filters)
  - [x] Filter types: lowpass, highpass, bandpass, bandstop/notch
  - [x] Specialized filters: Moving Average, Savitzky-Golay, Median
  - [x] Data resampling and interpolation (linear, cubic, spline, Fourier methods)
  - [x] Anti-aliasing for downsampling, missing data interpolation
  - [x] Curve fitting (8 fit types: linear, polynomial, exponential, logarithmic, power, sinusoidal, Gaussian, custom)
  - [x] Comprehensive fit statistics (R², RMSE, residuals)
  - [x] Statistical Process Control (6 chart types: X-bar/R, X-bar/S, Individuals, P, C, U)
  - [x] Western Electric rules detection for out-of-control points
  - [x] Process capability analysis (Cp, Cpk, Pp, Ppk, Cpm indices)
  - [x] Automated report generation (HTML, Markdown, JSON, PDF formats)
  - [x] Batch processing engine (parallel/sequential file processing)
  - [x] 30+ analysis API endpoints
- [x] **Database integration** (centralized SQLite storage for historical data)
  - [x] Command history logging (all SCPI commands with timestamps, execution time, status)
  - [x] Measurement archival (all measurements with metadata and session tracking)
  - [x] Equipment usage statistics (session duration, command/measurement counts, errors)
  - [x] Data acquisition session tracking (complete session lifecycle and statistics)
  - [x] Historical data query API (filtering, pagination, aggregation, trend analysis)
  - [x] Automatic cleanup of old records (configurable retention period)
  - [x] Database health monitoring and statistics
  - [x] 15+ database API endpoints
- [x] **Enhanced calibration management** (comprehensive calibration workflows and tracking)
  - [x] Calibration procedures (step-by-step workflows with validation)
  - [x] Procedure execution tracking (real-time progress, step completion, results)
  - [x] Digital calibration certificates (ISO/IEC 17025, traceability, digital signatures)
  - [x] Calibration corrections (linear, polynomial, lookup table, custom functions)
  - [x] Automatic correction application to measurements
  - [x] Reference standards management (calibration tracking, usage recording)
  - [x] Standards due date monitoring and alerts
  - [x] 20+ enhanced calibration API endpoints
- [x] **Automated test sequences** (comprehensive test automation and validation)
  - [x] Test sequence creation and management (9 step types)
  - [x] Automated execution with real-time progress tracking
  - [x] Parameter sweeping for characterization (linear/log scales)
  - [x] Pass/fail validation (6 operators, tolerance support)
  - [x] Test result archival and trending
  - [x] Template library for common tests (voltage accuracy, frequency response)
  - [x] Multi-equipment coordination
  - [x] 15+ test automation API endpoints

- [x] **Backup & restore system** (production-grade data protection and disaster recovery)
  - [x] Automatic scheduled backups (configurable interval)
  - [x] Multiple backup types (full, config, profiles, data, database, incremental)
  - [x] Compression support (gzip, zip, tar.gz)
  - [x] SHA-256 checksum verification
  - [x] Selective restore (granular control over what to restore)
  - [x] Pre-restore safety backups
  - [x] Retention policy (automatic cleanup of old backups)
  - [x] Backup statistics and monitoring
  - [x] 10+ backup management API endpoints

- [x] **Equipment discovery system** (automatic device discovery and smart connection management)
  - [x] mDNS/Bonjour discovery (automatic network device discovery)
  - [x] VISA resource scanning (TCPIP, USB, GPIB, Serial)
  - [x] Automatic device identification (*IDN? query)
  - [x] Connection history tracking with statistics
  - [x] Smart connection recommendations based on success rates
  - [x] Device aliases and friendly names
  - [x] Last-known-good configuration tracking
  - [x] Auto-discovery with configurable intervals
  - [x] Device caching for fast access
  - [x] 15+ discovery API endpoints

- [x] **Advanced security system** (enterprise-grade security for multi-user environments)
  - [x] JWT authentication (secure token-based authentication with access/refresh tokens)
  - [x] Role-based access control (RBAC with granular permissions)
  - [x] User management (complete lifecycle with password policies)
  - [x] API key management (programmatic access with scoped permissions)
  - [x] IP whitelisting/blacklisting (network-level access control)
  - [x] Security audit logging (comprehensive audit trail for compliance)
  - [x] Session management (track and manage active user sessions)
  - [x] Account lockout protection (brute-force attack prevention)
  - [x] Password policies (complexity requirements, expiration, change enforcement)
  - [x] Three default roles (admin, operator, viewer) with custom role support
  - [x] 30+ security configuration settings
  - [x] 25+ security API endpoints
  - [x] Compliance support (NIST CSF, ISO 27001, FDA 21 CFR Part 11, GDPR)

- [x] **Desktop GUI client** (PyQt6-based cross-platform application)
  - [x] Equipment control and monitoring
  - [x] Data acquisition interface
  - [x] Alarm monitoring and acknowledgment
  - [x] Scheduler management interface
  - [x] Diagnostics and health monitoring dashboard
  - [x] Server connection management

- [x] **MVP Web Dashboard** (responsive browser-based interface)
  - [x] JWT-based authentication with login page
  - [x] Real-time equipment status display with auto-refresh
  - [x] Quick equipment control (connect/disconnect/send commands)
  - [x] SCPI command interface with history
  - [x] Dark mode with system detection
  - [x] Responsive design (mobile/tablet/desktop)
  - [x] 11 new files (~2,000+ lines)

- [x] **OAuth2 authentication** (social login integration)
  - [x] Google OAuth2 provider
  - [x] GitHub OAuth2 provider
  - [x] Microsoft OAuth2 provider
  - [x] Automatic user provisioning
  - [x] Account linking for existing users
  - [x] OAuth2 configuration management
  - [x] 8 OAuth2 API endpoints

- [x] **Enhanced Web Dashboard** (real-time monitoring and visualization)
  - [x] WebSocket real-time updates with exponential backoff reconnection
  - [x] Chart.js live data visualization (4 real-time charts with 50-point rolling buffer)
  - [x] Equipment profile management UI (CRUD operations, JSON validation)
  - [x] Alarm notifications panel with severity levels
  - [x] User settings page (profile editing, password change, MFA setup)
  - [x] Dark mode support for all new components
  - [x] 6 new files and significant updates (~1,200+ lines)

- [x] **Multi-Factor Authentication (MFA/2FA)** (enhanced security)
  - [x] TOTP-based two-factor authentication (RFC 6238 compliant)
  - [x] QR code generation for authenticator apps
  - [x] 10 one-time backup codes (bcrypt-hashed)
  - [x] MFA setup wizard in user settings
  - [x] Enhanced login flow with MFA verification
  - [x] 5 MFA API endpoints
  - [x] Complete frontend integration

- [x] **Real-time data visualization** (pyqtgraph integration)
  - [x] Real-time plotting widget with circular buffer
  - [x] Multi-channel support with auto-coloring
  - [x] Pause/resume and clear controls
  - [x] Statistics display (points plotted, update rate)
  - [x] Auto-ranging and manual range control
  - [x] Integrated into acquisition panel and equipment panels

- [x] **SSH deployment wizard** (automated server deployment)
  - [x] Multi-step wizard interface
  - [x] SSH connection testing
  - [x] Password and SSH key authentication
  - [x] Automatic file transfer via SCP
  - [x] Remote dependency installation
  - [x] Systemd service setup for auto-start
  - [x] Progress tracking and logging
  - [x] Integrated into Tools menu

- [x] **Multi-server connection management**
  - [x] Server configuration storage (JSON)
  - [x] Add/remove/update server profiles
  - [x] Server selector widget in main toolbar
  - [x] Connection status indicators
  - [x] Quick server switching
  - [x] Remember last connected server
  - [x] Per-server connection history

### In Development

- [ ] Advanced waveform analysis tools
- [ ] Automated test sequence builder
- [ ] Remote firmware update capability

## Supported Equipment

- Rigol MSO2072A Oscilloscope
- Rigol DS1104 Oscilloscope
- Rigol DS1102D Oscilloscope (100 MHz, 1 GSa/s, 2 channels)
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
- [Data Analysis Pipeline](server/ANALYSIS_USER_GUIDE.md) - Signal processing, curve fitting, SPC, and reporting
- [Development Roadmap](server/ROADMAP.md) - Planned features and enhancements

## Project Status

**Current Version**: v1.0.0 (Production Ready) 🎉

**Release Date**: November 14, 2025

**Development Phases Complete**:
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

**Phase 4 Complete**: Web Dashboard & Authentication
- ✅ MVP Web Dashboard with responsive design
- ✅ OAuth2 authentication with 3 providers (Google, GitHub, Microsoft)
- ✅ Enhanced Web Dashboard with real-time features
- ✅ Multi-Factor Authentication (TOTP-based 2FA)
- ✅ WebSocket real-time updates
- ✅ Chart.js live data visualization
- ✅ Equipment profile management UI
- ✅ 3,200+ lines of web interface code

**Phase 5 Complete**: One-Click Deployment & Raspberry Pi Imaging
- ✅ **Real-time data visualization** (pyqtgraph integration)
  - ✅ Real-time plotting widget with circular buffer
  - ✅ Multi-channel support with auto-coloring
  - ✅ Zoom, pan, and measurement tools

- ✅ **SSH deployment wizard** (automated server deployment)
  - ✅ Multi-step wizard interface
  - ✅ Automatic file transfer via SCP
  - ✅ Remote dependency installation
  - ✅ Systemd service configuration
  - ✅ Real-time deployment progress

- ✅ **Multi-server connection management**
  - ✅ Save and manage multiple server profiles
  - ✅ Quick server switching from toolbar
  - ✅ Connection history tracking
  - ✅ Persistent JSON configuration

- ✅ **One-click installation scripts**
  - ✅ install-server.sh (Linux/macOS/Raspberry Pi)
  - ✅ install-client.sh (Linux/macOS)
  - ✅ install-client.ps1 (Windows PowerShell)
  - ✅ Automatic Docker and dependency installation
  - ✅ JWT secret generation
  - ✅ Desktop shortcut creation

- ✅ **Raspberry Pi image builder & SD card writer**
  - ✅ GUI wizard for building custom Pi images
  - ✅ Pre-configured images with LabLink pre-installed
  - ✅ Wi-Fi and SSH configuration
  - ✅ Auto-expanding filesystem
  - ✅ First-boot automation script
  - ✅ Cross-platform SD card writer (Linux/macOS/Windows)
  - ✅ Image verification after writing
  - ✅ build-pi-image.sh automation script
  - ✅ Zero command-line knowledge required

- ✅ **Docker Compose stack** (production-ready deployment)
  - ✅ Profile-based service activation (default, caching, postgres, monitoring, full)
  - ✅ Health checks and auto-restart
  - ✅ Volume persistence
  - ✅ Resource limits
  - ✅ nginx reverse proxy
  - ✅ Optional Redis, PostgreSQL, Grafana, Prometheus

- ✅ **Mobile Architecture Validation** (v1.0.0 mobile-readiness assessment)
  - ✅ Complete API validation for mobile compatibility
  - ✅ REST API assessment (200+ endpoints, platform-agnostic)
  - ✅ JWT authentication validation (works perfectly on mobile)
  - ✅ OAuth2 flow validation (minor redirect URI support needed)
  - ✅ WebSocket reconnection strategy for mobile
  - ✅ Response size analysis (all within mobile limits)
  - ✅ React Native SDK design
  - ✅ Advanced visualization spike results
  - ✅ **Conclusion:** API is 100% mobile-ready, no breaking changes needed
  - ✅ Documentation: `docs/MOBILE_API_REQUIREMENTS.md` (500+ lines)
  - ✅ Summary: `MOBILE_ARCHITECTURE_VALIDATION.md` (295 lines)

**v1.0.0 Production Release:**
- ✅ **Phase 1-3**: Core features, UI, deployment automation
- ✅ **Phase 2**: Test Coverage Sprint (137 passing tests, 26% overall, 70%+ critical paths)
- ✅ **Phase 3**: Production Hardening (security fixes, performance benchmarks, profiling)
- ✅ **Phase 4**: v1.0.0 Release (CHANGELOG, documentation, release notes)

**Security & Quality:**
- ✅ All critical vulnerabilities fixed (FastAPI, Starlette upgraded)
- ✅ Security scans BLOCKING in CI/CD
- ✅ Type hints on critical functions (PEP 484)
- ✅ Performance benchmarked (10 benchmarks established)
- ✅ Comprehensive documentation (2,500+ lines)

**Next Versions:**
- **v1.1.0**: Mobile app (React Native for iOS/Android) - API 100% ready
- **v1.2.0**: Advanced visualization (3D waveforms, FFT waterfalls, SPC charts)
- **v1.3.0+**: Enterprise features (See ROADMAP.md)

## Contributing

This project is in active development. Contributions, feature requests, and bug reports are welcome!

## License

TBD
