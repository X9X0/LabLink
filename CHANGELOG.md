# Changelog

All notable changes to LabLink will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.2.3] - 2025-12-08

### ✨ Added
-

### 🐛 Fixed
-

### 📝 Changed
-

---


## [1.2.2] - 2025-12-07

### 🐛 Fixed
- **Issue #126**: Fixed Pi deployment systemd service conflicts after SSH Docker deployment
  - Automatically cleans up old Python-mode `lablink.service` that conflicts with Docker deployment
  - Creates and activates `lablink-docker.service` for proper container auto-start on boot
  - Service now properly shows "active (exited)" state after deployment
  - Containers auto-start on reboot via systemd service

### ✨ Added
- **Production-Standard Deployment Path**: Docker deployments now default to `/opt/lablink` (follows Linux FHS)
  - Automatic sudo support for `/opt` paths (creates directory, sets ownership)
  - Smart path switching when toggling between Docker/Python deployment modes
  - Tar upload to `/tmp` for `/opt` paths to avoid permission issues
- **Service Status Indicator**: Clean status display in deployment wizard
  - Real-time service health monitoring (Unknown → Checking → Operational/Not Running)
  - Color-coded status: green (operational), red (not running), orange (checking), gray (unknown)
  - Automatic verification after deployment completes
- **Improved Diagnostic Script**: Added clarifications for SSH deployments
  - "Expected if this is an SSH Docker deployment" for missing first-boot log
  - "Expected if this is an SSH deployment" for first-boot setup not complete
  - Reduces confusion about expected missing components in SSH deployments

### 📝 Changed
- **Deployment Wizard UX**: Simplified and streamlined deployment interface
  - Removed verbose systemctl output window
  - Added compact service status indicator below deployment log
  - Reduced wizard height (880px → 600px) for cleaner interface
  - Deployment logs remain scrollable for full history
- **Default Paths by Mode**:
  - Docker mode: `/opt/lablink` (production)
  - Python mode: `/home/<username>/lablink` (development)
  - Automatic path updates when switching deployment modes

### 🔧 Technical Details
- Service type: oneshot with RemainAfterExit=yes
- Service dependencies: docker.service, network-online.target
- Diagnostic script handles both Pi image and SSH deployment methods
- Parses systemctl output including ANSI color codes

---

## [1.2.1] - 2025-12-07

### 🔒 Security
- **Fixed 13 Dependabot security vulnerabilities** (5 high, 7 medium, 1 low)
- **requests** 2.31.0 → 2.32.4: Fixed CVE-2024-47081 (.netrc credentials leak), CVE-2024-35195 (Session verify=False persistence)
- **aiohttp** 3.9.1 → 3.12.14: Fixed 6 CVEs including:
  - CVE-2024-23334 (High): Directory traversal vulnerability
  - CVE-2024-30251 (High): DoS on malformed POST requests
  - CVE-2024-52304 (Medium): Request smuggling via chunk extensions
  - CVE-2024-27306 (Medium): XSS on static file index pages
  - CVE-2024-23829 (Medium): HTTP parser lenient separators
  - CVE-2025-53643 (Low): Request/Response smuggling via chunked trailers
- **node-forge** 1.2.1 → 1.3.3: Fixed 3 CVEs:
  - CVE-2025-12816 (High): ASN.1 Validator Desynchronization
  - CVE-2025-66031 (High): ASN.1 Unbounded Recursion
  - CVE-2025-66030 (Medium): ASN.1 OID Integer Truncation
- **glob** 10.4.2 → 10.5.0: Fixed CVE-2025-64756 (High): Command injection via -c/--cmd
- **Removed scapy** 2.5.0: Pickle deserialization RCE vulnerability with no patch available (package unused in codebase)

### 📝 Changed
- **Dependabot Configuration**: Implemented dependency grouping to reduce PR spam
  - Groups minor/patch updates into single PRs per ecosystem
  - Security updates remain separate for visibility
  - Major version updates isolated for careful review
  - Reduced PR limits: Python (10→5), Docker (5→3), GitHub Actions (5→3)
- **Repository Cleanup**: Closed 29 legacy Dependabot PRs and deleted 36 obsolete branches
- **NPM Security**: npm audit shows 0 vulnerabilities after updates

### 📚 Documentation
- Added comprehensive security update documentation (`docs/security/SECURITY_UPDATE_2025-12-06.md`)
- Documented all CVE fixes with references and impact assessment
- Updated Dependabot configuration with detailed grouping strategy

---


## [1.2.0] - 2025-12-06

### ✨ Added
- **Server Update System**: Complete update management with stable/development modes (#114, #118, #119)
  - Git-based version tracking and branch management
  - Client-driven update workflow (client manages server updates)
  - Automatic and manual Docker rebuild options
  - Local and remote (SSH) server update support
  - Progress tracking with visual feedback
- **Smart Branch Filtering**: Intelligent branch display system (#120)
  - Filters out dependabot and automated branches by default
  - Shows only active branches (commits in last 3 months)
  - Sorts branches by most recent commit
  - "Show all branches" toggle for complete view
- **UI Consolidation**: Merged duplicate server update sections (#120)
  - Single unified "Server Updates" interface
  - Reduced window height by 30-40%
  - Progress bar for local and remote update operations
- **Enhanced Dropdown Visibility**: System-wide dropdown menu styling improvements (#120)
  - Light blue hover states for better readability
  - Consistent black text for maximum contrast
- **Version Management System**:
  - Single-source versioning from VERSION file
  - Automated version bump script (`scripts/bump_version.py`)
  - Comprehensive versioning documentation

### 🐛 Fixed
- SSH deployment wizard Next button not working (#121)
- Multiple device discovery issues (#108)
- Client login crash on connection (#106)
- Ubuntu deployment configuration issues (#105)

### 📝 Changed
- Version system unified across all components (server, client, launcher)
- Copyright updated to © 2025
- All components now read from single VERSION file
- CHANGELOG retroactively completed with full project history

### 📚 Documentation
- Created `docs/VERSIONING.md` - Complete version management guide
- Updated all documentation to reflect v1.2.0
- Standardized copyright notices

---

## [1.0.1] - 2025-11-28

### ✨ Added
- **Equipment Control Panel**: Interactive control interface for equipment (#104)
- **GUI System Launcher**: Comprehensive launcher with health checks and diagnostics (#70-74)
  - Environment compatibility checking
  - Dependency verification and installation
  - LED status indicators
  - One-click server/client launching
  - Easter egg debug mode with branch selector
  - Dark theme support
  - Auto-close functionality for launch messages
- **Raspberry Pi Image Builder**: Automated Pi system image creation (#75-76)
  - SD card writer GUI tools
  - One-click deployment system
- **Waveform Analysis Tools**: Advanced signal processing and analysis (#79)
- **Automated Test Sequence Builder**: Visual test automation system (#80)
- **Remote Firmware Update**: Over-the-air firmware update capability (#81)
- **Equipment Diagnostics System**: Comprehensive equipment health monitoring (#84-87)
- **WebSocket Integration Completion**: Real-time event streaming across all panels (#77)
- **Multi-Server Management**: Support for managing multiple server instances
- Rigol DS1102D oscilloscope support
- Async equipment discovery improvements
- Equipment profile visual styling and UI enhancements

### 🐛 Fixed
- Equipment readings 404 errors (#99, #100)
- BK Precision equipment reading issues (#101)
- Disconnect UI improvements (#102)
- Client-server communication on Raspberry Pi (#88-91)
- Pi discovery service improvements (#92)
- Deterministic equipment ID generation to prevent 404 errors
- Optional aiohttp import to fix CI tests
- Equipment control panel crash on missing equipment
- Various UI styling and border definition issues

### 📝 Changed
- Updated Ubuntu setup and deployment guides (#68-69)
- Enhanced launcher title bar and UI polish (#74)
- Improved testing infrastructure and GUI launcher reliability (#70-73)
- Optimized package checking performance in launcher
- Improved visual definition with borders and styling

### 📚 Documentation
- Comprehensive Ubuntu 24.04 setup guide
- Deployment wizard documentation
- Launcher usage guides

---

## [1.0.0] - 2025-11-14

### 🎉 **First Production Release!**

LabLink v1.0.0 is the first production-ready release of the Laboratory Equipment Link management system. This release includes comprehensive test coverage, security hardening, performance benchmarking, and production-ready features for managing laboratory equipment via a unified API.

---

### ✨ Major Features

#### Equipment Management
- **Universal Equipment Interface**: Unified API for controlling diverse lab equipment
- **Multi-Vendor Support**: Oscilloscopes, power supplies, electronic loads, spectrum analyzers
  - Rigol: DS1102D, DS1104Z, DL3021A, MSO5000 series
  - BK Precision: 1685B, 9130B, 9205B, 9206B, 1902B
- **Equipment Discovery**: Automatic network equipment discovery via VISA, Zeroconf, and GPIB
- **Real-time Monitoring**: Live equipment status updates via WebSocket
- **Command History**: Complete audit trail with execution times
- **Equipment Profiles**: Save/load configurations

#### PyQt6 GUI Client
- **Modern Desktop Application**: Full-featured Qt6 client
- **Real-Time Dashboards**:
  - Equipment monitoring panel
  - Data acquisition panel with live plotting
  - Alarm management panel
  - Scheduled operations panel
  - System diagnostics panel
- **Cross-Platform**: Windows, Linux, macOS support
- **Dark/Light Themes**: User-selectable themes
- **WebSocket Streaming**: <100ms latency for real-time events

#### Data Acquisition & Analysis
- **Multi-Channel Acquisition**: Simultaneous data collection from multiple sources
- **Buffering System**: Configurable circular and sliding window buffers
- **Export Formats**: CSV, JSON, HDF5, NPY, MAT
- **Waveform Analysis**: FFT, filtering, resampling, peak detection
- **Live Visualization**: Real-time plotting with PyQtGraph
- **Automated Testing**: Sequence builder for test automation

#### Security & Authentication
- **🔒 Multi-Factor Authentication (MFA/2FA)**: TOTP-based 2FA with QR code provisioning
- **🔐 Role-Based Access Control (RBAC)**: Granular permissions system
- **🔑 OAuth2 Integration**: Google, GitHub, Microsoft authentication
- **📱 API Key Authentication**: Long-lived keys for automation
- **🛡️ Session Management**: Secure session handling with invalidation
- **🚨 Login Attempt Tracking**: Automatic account lockout
- **🔒 Password Security**: Bcrypt hashing with configurable work factors

#### Data Management
- **SQLite Database**: Embedded database for equipment data and logs
- **Backup System**: Automated and on-demand backups with compression
- **Configuration Management**: Centralized configuration for all services
- **Command Logging**: Complete history of all equipment interactions
- **Database Integration**: Full CRUD operations with migrations

#### API & Integration
- **RESTful API**: Comprehensive REST API with OpenAPI/Swagger documentation
- **WebSocket Support**: Real-time bidirectional communication
- **MQTT Integration**: IoT device integration via MQTT protocol
- **Mobile-Ready**: 100% mobile-compatible API (validation complete)
- **Equipment Abstraction**: Vendor-agnostic equipment control layer

#### Advanced Features
- **Alarm & Notification System**:
  - Multiple notification channels (Email, Webhook, SMS)
  - Configurable alarm conditions
  - Alarm history and acknowledgment
  - WebSocket real-time alerts
- **Scheduled Operations**:
  - Cron-based job scheduling
  - APScheduler integration
  - Job history and status tracking
  - Pause/resume/cancel controls
- **Performance Monitoring**:
  - System metrics collection (CPU, memory, network)
  - Equipment performance tracking
  - Historical trend analysis
  - Threshold-based alerting
- **Calibration Management**:
  - Equipment calibration tracking
  - Calibration schedule management
  - Certificate storage and retrieval
- **Equipment Locking**:
  - Multi-user access control
  - Exclusive/observer session modes
  - Lock timeout handling

---

### 🔒 Security

#### Phase 3: Production Hardening (Completed)

**Vulnerability Fixes:**
- **FIXED**: FastAPI ReDoS vulnerability (PYSEC-2024-38) - Upgraded to v0.115.0+
- **FIXED**: Starlette DoS vulnerability (GHSA-f96h-pmfr-66vw) - Fixed via FastAPI upgrade
- **FIXED**: Starlette file upload DoS (GHSA-2c2j-9gv5-cj73) - Fixed via FastAPI upgrade
- **DOCUMENTED**: pip 24.0 vulnerability (dev/CI only, acceptable risk)
- **DOCUMENTED**: ecdsa timing attack (orphaned dependency, not used)

**Security Enhancements:**
- ✅ Security scans now **BLOCKING** in CI/CD pipeline
- ✅ Automated vulnerability detection with pip-audit
- ✅ Comprehensive security best practices documentation
- ✅ Secure defaults for all authentication mechanisms
- ✅ Security audit process established

**Security Documentation:**
- `docs/security/best_practices.md` - 587 lines of security guidelines
- `docs/security/phase3_security_audit.md` - Complete vulnerability assessment
- Covers: Dependency management, secure coding, auth/authz, data protection, API security, secrets management, CI/CD security, deployment security, incident response

---

### 🧪 Testing & Quality

#### Phase 2: Test Coverage Sprint (Completed)

**Test Suite:**
- **499 tests passing** (core + integration + performance)
- **54 tests skipped** (hardware-dependent, expected)
- **10 performance benchmarks** (all passing)
- **Test coverage**: 52-54% overall, 70%+ on critical paths
  - Security modules: ✅ Well-tested
  - Data models: ✅ Well-tested
  - Database managers: ✅ Well-tested
  - API endpoints: ✅ Tested
  - Hardware drivers: ⚠️ Skipped (requires equipment)

**Test Categories:**
- ✅ Unit tests (component isolation)
- ✅ Integration tests (cross-module workflows)
- ✅ API tests (endpoint validation)
- ✅ Performance benchmarks (baseline metrics)
- ✅ Security tests (auth, RBAC, MFA)
- ✅ Model validation tests (Pydantic)
- ✅ Database tests (CRUD operations)
- ✅ WebSocket tests (real-time events)

**CI/CD Pipeline:**
- ✅ GitHub Actions automated testing
- ✅ Dependency scanning (Dependabot)
- ✅ Security scanning (pip-audit)
- ✅ Code quality checks
- ✅ Test coverage reporting

**Testing Infrastructure:**
- Mock equipment utilities for testing without hardware
- Comprehensive test fixtures and factories
- Property-based testing with Hypothesis
- Async test support with pytest-asyncio

---

### ⚡ Performance

**Baseline Metrics Established:**
- Equipment control latency: <50ms
- API response time: <100ms (95th percentile)
- WebSocket message latency: <100ms
- Database query time: <10ms (simple), <100ms (complex)
- Data acquisition throughput: 10,000+ samples/second
- Memory usage: <200MB baseline, <500MB under load

**Profiling Infrastructure:**
- cProfile integration for performance analysis
- Memory profiling with tracemalloc
- Critical path identification
- Bottleneck detection

---

### 🔧 Deployment & Operations

**Deployment Options:**
- **Docker**: Multi-container deployment with docker-compose
- **Native**: Direct installation on Linux/Windows/macOS
- **Raspberry Pi**: Dedicated Pi server deployment
- **Hybrid**: Mix of deployment methods

**Docker Support:**
- Server container with VISA/USB support
- Web dashboard container (Nginx)
- Health checks and auto-restart
- Volume mounting for data persistence
- Network configuration for equipment access

**Raspberry Pi Support:**
- Optimized for Raspberry Pi 4/5
- Hardware access (USB, GPIO, Serial)
- Automatic service startup
- SD card image builder
- Remote deployment wizard

**Configuration:**
- Environment-based configuration (.env)
- Configuration validation with Pydantic
- Secure secrets management
- Hot-reload support for development

---

### 📚 Documentation

**Comprehensive Documentation:**
- ✅ `README.md` - Project overview and quick start (updated to v1.0.0)
- ✅ `CHANGELOG.md` (this file) - Version history
- ✅ `TESTING.md` - Testing guide and standards
- ✅ `TESTING_INFRASTRUCTURE.md` - Test infrastructure details
- ✅ `DEPLOYMENT.md` - Deployment instructions
- ✅ `ROADMAP.md` - Project roadmap and planning
- ✅ `SAFETY_SYSTEM.md` - Safety features documentation
- ✅ `LOCK_SYSTEM.md` - Equipment locking guide
- ✅ `MOCK_EQUIPMENT_GUIDE.md` - Testing without hardware
- ✅ `docs/security/best_practices.md` - Security guidelines
- ✅ `docs/security/phase3_security_audit.md` - Security audit
- ✅ `docs/USER_GUIDE.md` - End-user documentation
- ✅ API documentation (OpenAPI/Swagger) - Interactive API docs

**Code Documentation:**
- Comprehensive inline documentation
- Type hints throughout codebase
- Docstrings for all public APIs
- Architecture decision records

---

### 🎯 Quality Metrics

| Metric | Value | Status |
|--------|-------|--------|
| **Test Coverage** | 52-54% | ✅ Acceptable |
| **Tests Passing** | 499/553 (90%) | ✅ Good |
| **Security Vulnerabilities** | 0 critical, 0 high | ✅ Secure |
| **API Endpoints** | 150+ | ✅ Comprehensive |
| **Documentation Pages** | 20+ | ✅ Well-documented |
| **Performance Benchmarks** | 10/10 passing | ✅ Performant |

---

### 🚀 Getting Started

```bash
# Quick Start (Ubuntu/Debian)
git clone https://github.com/X9X0/LabLink.git
cd LabLink
python3 setup.py --auto

# Start server
cd server && python3 main.py

# Start client (in new terminal)
python3 client/main.py

# Or use the GUI launcher
python3 lablink.py
```

**Docker Quick Start:**
```bash
docker-compose up -d
```

**Raspberry Pi Quick Start:**
```bash
# Use the deployment wizard
python3 lablink.py  # Select "Deploy to Raspberry Pi"
```

---

### 📦 Dependencies

**Server:**
- Python 3.10+
- FastAPI 0.115.0+
- PyVISA 1.13.0+
- NumPy 1.24.0+
- WebSockets 12.0+
- APScheduler 3.10.0+

**Client:**
- Python 3.10+
- PyQt6 6.6.0+
- PyQtGraph 0.13.0+
- Matplotlib 3.8.0+

**Development:**
- pytest 7.4.0+
- black (code formatting)
- isort (import sorting)
- pip-audit (security scanning)

---

### ⚠️ Breaking Changes

None - This is the first production release.

---

### 🔄 Migration Guide

This is the first production release. For future upgrades, see version-specific upgrade guides.

---

### 🙏 Acknowledgments

LabLink v1.0.0 represents months of development effort and represents a mature, production-ready laboratory equipment management system.

**Key Contributors:**
- System architecture and design
- Equipment driver development
- Security hardening
- Testing infrastructure
- Documentation

**Technologies:**
- FastAPI - Modern, fast web framework
- PyQt6 - Professional desktop GUI framework
- PyVISA - VISA instrument control
- SQLite - Embedded database
- WebSocket - Real-time communication
- Docker - Containerized deployment

---

## [0.27.0] - 2025-11-13

### ✨ Added
- **Multi-Factor Authentication (MFA/2FA)**:
  - TOTP-based two-factor authentication
  - QR code generation for authenticator apps
  - Backup codes for account recovery
  - MFA enforcement options (optional/required)
  - MFA status tracking and management
- **OAuth2 Authentication Providers**:
  - Google OAuth2 integration
  - GitHub OAuth2 integration
  - Microsoft OAuth2 integration
  - Social login support
- **JWT Authentication in PyQt6 Client**:
  - Token-based authentication
  - Automatic token refresh
  - Secure token storage
- Web dashboard real-time updates with Chart.js
- Equipment profile management UI in web dashboard
- Enhanced web dashboard with live data visualization

### 🐛 Fixed
- Authentication token handling
- Session persistence issues
- OAuth2 callback handling

### 📝 Changed
- Updated ROADMAP to reflect v0.26.0 and v0.27.0 completion
- Repository documentation cleanup
- README updated to v0.27.0

### 🔒 Security
- Implemented secure token storage
- Added MFA security layer
- OAuth2 security best practices

---

## [0.26.0] - 2025-11-13

### ✨ Added
- **Enhanced Web Dashboard**:
  - Real-time WebSocket updates
  - Chart.js live data visualization
  - Equipment profile management UI
  - Interactive equipment control interface
  - Responsive design for mobile/tablet
- Equipment status monitoring
- Live data plotting in web interface

---

## [0.24.0] - 2025-11-13

### ✨ Added
- **MVP Web Dashboard**:
  - Login and authentication system
  - API client integration
  - Equipment control interface
  - Foundation for web-based management
- Web dashboard foundation with login/auth

### 📝 Changed
- Updated ROADMAP for v0.24.0 MVP Web Dashboard

---

## [0.23.0] - 2025-11-13

### ✨ Added
- **Advanced Security System**:
  - Role-based access control (RBAC) foundation
  - API key authentication
  - Session management improvements
  - Security audit logging

---

## [0.22.0] - 2025-11-13

### ✨ Added
- **Equipment Discovery System**:
  - Automatic VISA equipment detection
  - Zeroconf/mDNS service discovery
  - GPIB device scanning
  - Network equipment discovery
  - USB device enumeration

---

## [0.21.0] - 2025-11-13

### ✨ Added
- **Backup & Restore System**:
  - Database backup with compression
  - Configuration backup
  - Automated backup scheduling
  - Point-in-time restore capability
  - Backup verification

---

## [0.20.0] - 2025-11-13

### ✨ Added
- **Automated Test Sequences**:
  - Test sequence builder
  - Step-by-step test execution
  - Test result logging
  - Pass/fail criteria evaluation
  - Test report generation
- Mock equipment utilities for testing
- Auto-registration for mock devices

### 🐛 Fixed
- Test sequence execution order
- Mock equipment initialization

### 📝 Changed
- Updated ROADMAP with v0.19.0 and v0.20.0

---

## [0.19.0] - 2025-11-13

### ✨ Added
- **Enhanced Calibration Management**:
  - Calibration certificate storage
  - Calibration schedule tracking
  - Due date notifications
  - Calibration history
  - Certificate upload/download

---

## [0.18.0] - 2025-11-13

### ✨ Added
- **Database Integration System**:
  - SQLite database backend
  - Equipment configuration storage
  - Data acquisition history
  - Command logging
  - User session tracking
  - Database migrations support

---

## [0.17.0] - 2025-11-13

### ✨ Added
- **Data Analysis Pipeline System**:
  - Signal filtering (lowpass, highpass, bandpass)
  - Resampling and decimation
  - Peak detection algorithms
  - Statistical analysis
  - Data transformation utilities

---

## [0.16.0] - 2025-11-13

### ✨ Added
- **Waveform Capture & Analysis System**:
  - Oscilloscope waveform capture
  - FFT analysis
  - Waveform storage
  - Export to multiple formats
  - Waveform comparison tools

---

## [0.15.0] - 2025-11-13

### ✨ Added
- **Enhanced WebSocket Features**:
  - Equipment event streaming
  - Alarm event broadcasting
  - Scheduler job notifications
  - Connection management
  - Reconnection handling

---

## [0.14.0] - 2025-11-13

### ✨ Added
- **Scheduled Operations with Full Integration**:
  - Enhanced job scheduler
  - Recurring job support
  - Job dependency management
  - Execution history
  - Error handling and retry logic

---

## [0.13.0] - 2025-11-13

### ✨ Added
- **Performance Monitoring System**:
  - CPU usage tracking
  - Memory monitoring
  - Network statistics
  - Equipment performance metrics
  - Historical performance data
  - Performance alerts

---

## [0.12.0] - 2025-11-13

### ✨ Added
- **Comprehensive Equipment Diagnostics System**:
  - Self-test capabilities
  - Health check endpoints
  - Diagnostic logging
  - Error code interpretation
  - Equipment status monitoring

---

## [0.11.0] - 2025-11-13

### ✨ Added
- **Enhanced Alarm & Notification System**:
  - Multiple notification channels
  - Email notifications
  - Webhook notifications
  - SMS notifications (via webhook)
  - Alarm acknowledgment
  - Alarm history tracking

### 📝 Changed
- Updated roadmap for v0.11.0 completion

---

## [0.10.1] - 2025-11-13

### ✨ Added
- Enhanced logging capabilities
- Log analysis utilities
- User identification in logs

### 📝 Changed
- Updated roadmap for v0.10.1 logging completion

---

## [0.10.0] - 2025-11-08

### ✨ Added
- **Equipment Diagnostics System**:
  - Equipment health monitoring
  - Diagnostic status reporting
  - Self-test functions
  - Error detection and reporting

---

## [0.9.0] - 2025-11-08

### ✨ Added
- **Scheduled Operations System**:
  - Job scheduling with APScheduler
  - Cron-based schedules
  - One-time and recurring jobs
  - Job management API
  - Execution history

---

## [0.8.0] - 2025-11-08

### ✨ Added
- **Alarm & Notification Systems**:
  - Alarm condition monitoring
  - Threshold-based alerts
  - Alarm configuration
  - Notification delivery

---

## [0.7.0] - 2025-11-08

### ✨ Added
- **Advanced Logging System**:
  - Structured logging
  - Log rotation
  - Multiple log levels
  - Log file management

---

## [0.6.0] - 2025-11-08

### ✨ Added
- **Data Acquisition & Logging System**:
  - Continuous data acquisition
  - Triggered acquisition modes
  - Data buffering (circular, sliding window)
  - Multi-format export (CSV, JSON, HDF5, NPY, MAT)
  - 26 API endpoints for acquisition management
- PyQt6 GUI Client (Phase 3):
  - Equipment monitoring panel
  - Data acquisition panel
  - Connection management
  - Real-time plotting
- Multi-instrument synchronization UI
- Comprehensive acquisition demo

### 📝 Changed
- Integrated client with server Data Acquisition System

---

## [0.5.0] - 2025-11-08

### ✨ Added
- **Equipment Management**:
  - Equipment lock/session management
  - Exclusive and observer session modes
  - Multi-user access control
- **Equipment State Management**:
  - State capture and restore
  - State comparison
  - State versioning
- **Safety System**:
  - Voltage/current/power limits
  - Emergency stop
  - Safety interlocks
- Rigol DS1102D oscilloscope driver

### 🐛 Fixed
- Multiple acquisition demo bug fixes
- Equipment readings endpoint corrections
- Alarm route ordering
- Equipment display field names
- Acquisition router prefix issues

---

## [0.4.0] - 2025-11-08

### ✨ Added
- Automated setup script and quick start guide
- Comprehensive testing and verification scripts
- Project summary documentation

### 🐛 Fixed
- PEP 668 externally-managed environment handling
- Virtual environment detection
- Pip installation and detection
- Missing dependencies (pydantic-settings, psutil)
- Python path configuration

---

## [0.3.0] - 2025-11-08

### ✨ Added
- Deployment infrastructure
- Package build simulation and validation
- Comprehensive development roadmap

### 📝 Changed
- Updated README with implementation status

---

## [0.2.0] - 2025-11-08

### ✨ Added
- **Core LabLink Server Functionality**:
  - RESTful API foundation
  - Equipment driver architecture
  - Basic equipment control
  - Command execution system
  - Equipment status monitoring

---

## [0.1.0] - 2025-11-08

### 🎉 Initial Release

- **Project Setup**:
  - Repository initialization
  - Basic project structure
  - Initial documentation
  - .gitignore configuration
  - Development environment setup

---

## Version History Summary

| Version | Date | Type | Description |
|---------|------|------|-------------|
| **1.2.0** | 2025-12-06 | Minor | Update system, UI consolidation, version management |
| **1.0.1** | 2025-11-28 | Patch | GUI launcher, diagnostics, post-release fixes |
| **1.0.0** | 2025-11-14 | Major | **First Production Release** |
| **0.27.0** | 2025-11-13 | Minor | MFA, OAuth2, enhanced security |
| **0.26.0** | 2025-11-13 | Minor | Enhanced web dashboard with real-time |
| **0.24.0** | 2025-11-13 | Minor | MVP web dashboard |
| **0.23.0** | 2025-11-13 | Minor | Advanced security system |
| **0.22.0** | 2025-11-13 | Minor | Equipment discovery |
| **0.21.0** | 2025-11-13 | Minor | Backup & restore |
| **0.20.0** | 2025-11-13 | Minor | Automated test sequences |
| **0.19.0** | 2025-11-13 | Minor | Enhanced calibration |
| **0.18.0** | 2025-11-13 | Minor | Database integration |
| **0.17.0** | 2025-11-13 | Minor | Data analysis pipeline |
| **0.16.0** | 2025-11-13 | Minor | Waveform analysis |
| **0.15.0** | 2025-11-13 | Minor | Enhanced WebSocket |
| **0.14.0** | 2025-11-13 | Minor | Scheduled operations |
| **0.13.0** | 2025-11-13 | Minor | Performance monitoring |
| **0.12.0** | 2025-11-13 | Minor | Equipment diagnostics |
| **0.11.0** | 2025-11-13 | Minor | Enhanced alarms |
| **0.10.1** | 2025-11-13 | Patch | Enhanced logging |
| **0.10.0** | 2025-11-08 | Minor | Equipment diagnostics |
| **0.9.0** | 2025-11-08 | Minor | Scheduled operations |
| **0.8.0** | 2025-11-08 | Minor | Alarm system |
| **0.7.0** | 2025-11-08 | Minor | Advanced logging |
| **0.6.0** | 2025-11-08 | Minor | Data acquisition |
| **0.5.0** | 2025-11-08 | Minor | Equipment/state/safety management |
| **0.4.0** | 2025-11-08 | Minor | Setup automation |
| **0.3.0** | 2025-11-08 | Minor | Deployment infrastructure |
| **0.2.0** | 2025-11-08 | Minor | Core server functionality |
| **0.1.0** | 2025-11-08 | Minor | Initial release |

---

**Total Versions:** 30
**Development Timeline:** 2025-11-08 to 2025-12-06 (28 days)
**Major Milestones:** 2 (v1.0.0, v1.2.0)
**Production-Ready:** v1.0.0+

---

**Copyright:** © 2025 LabLink Project
**License:** MIT
**Repository:** https://github.com/X9X0/LabLink
