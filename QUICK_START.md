# LabLink Quick Start Guide

Get up and running with LabLink in minutes!

---

## Prerequisites

- **Python 3.8+** (Python 3.10+ recommended)
- **pip** package manager
- **Git** (for cloning the repository)

**Optional:**
- NI-VISA for hardware equipment control
- Virtual environment tool (venv, virtualenv, conda)

---

## Installation

### Method 1: Automated Setup (Recommended)

The easiest way to get started is using the automated setup script:

```bash
# Clone the repository (if not already done)
git clone <repository-url>
cd LabLink

# Run automated setup
python3 setup.py --auto

# Or interactive setup
python3 setup.py
```

The setup script will:
- ✅ Check Python version
- ✅ Check system dependencies
- ✅ Install all required Python packages
- ✅ Create configuration files
- ✅ Verify installation

**Setup Options:**

```bash
python3 setup.py              # Full interactive setup
python3 setup.py --auto       # Auto-install everything
python3 setup.py --server     # Server dependencies only
python3 setup.py --client     # Client dependencies only
python3 setup.py --check      # Check only (no install)
python3 setup.py --venv       # Setup virtual environment
```

### Method 2: Manual Setup

If you prefer manual installation:

**1. Create virtual environment (recommended):**

```bash
python3 -m venv venv

# Activate virtual environment
# Linux/macOS:
source venv/bin/activate

# Windows:
venv\Scripts\activate
```

**2. Install server dependencies:**

```bash
cd server
pip install -r requirements.txt
cd ..
```

**3. Install client dependencies:**

```bash
cd client
pip install -r requirements.txt
cd ..
```

**4. Install test dependencies (optional):**

```bash
pip install -r requirements-test.txt
```

**5. Create configuration file:**

```bash
cd server
cp .env.example .env
# Edit .env with your settings
cd ..
```

---

## Configuration

### Server Configuration

Edit `server/.env` to configure the server:

```bash
# Server Settings
HOST=0.0.0.0          # Listen on all interfaces
PORT=8000             # REST API port
WS_PORT=8001          # WebSocket port

# Logging
LOG_LEVEL=INFO        # DEBUG, INFO, WARNING, ERROR
LOG_FILE=lablink.log

# VISA Settings (for equipment)
VISA_LIBRARY=@py      # Use pyvisa-py (pure Python)
VISA_TIMEOUT=5000     # Timeout in milliseconds

# Safety Settings
ENABLE_SAFETY_LIMITS=true
MAX_VOLTAGE=50.0      # Maximum voltage limit
MAX_CURRENT=10.0      # Maximum current limit
MAX_POWER=500.0       # Maximum power limit

# Data Storage
DATA_DIR=./data
EXPORT_DIR=./exports
```

**Note:** The setup script creates a default `.env` file if one doesn't exist.

---

## Running LabLink

### Start the Server

```bash
cd server
python3 main.py
```

You should see:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Server will be available at:**
- REST API: http://localhost:8000
- API Documentation: http://localhost:8000/docs
- WebSocket: ws://localhost:8001

### Run the Demo Application

In a new terminal:

```bash
python3 demo_acquisition_full.py
```

This launches the comprehensive demo with:
- Data Acquisition Panel
- Multi-Instrument Synchronization Panel
- Real-time statistics
- Data export functionality

---

## Quick Usage Examples

### 1. Simple Acquisition (Python Script)

```python
from client.api.client import LabLinkClient
from client.models import AcquisitionConfig, AcquisitionMode

# Connect to server
client = LabLinkClient(host="localhost", api_port=8000)
client.connect()

# List available equipment
equipment = client.list_equipment()
print(f"Found {len(equipment)} equipment")

# Create acquisition configuration
config = AcquisitionConfig(
    equipment_id="PSU_001",
    mode=AcquisitionMode.CONTINUOUS,
    sample_rate=1000.0,
    channels=["voltage", "current"],
    buffer_size=10000
)

# Create and start acquisition
result = client.create_acquisition_session("PSU_001", config.to_dict())
acquisition_id = result["acquisition_id"]

client.start_acquisition(acquisition_id)
print(f"Acquisition started: {acquisition_id}")

# Get statistics
stats = client.get_acquisition_rolling_stats(acquisition_id)
print(f"Statistics: {stats}")

# Stop acquisition
client.stop_acquisition(acquisition_id)
```

### 2. Using the GUI Demo

1. **Start the server** (see above)
2. **Run demo:** `python3 demo_acquisition_full.py`
3. **In Data Acquisition tab:**
   - Select equipment from dropdown
   - Configure acquisition (mode, sample rate, channels)
   - Click "Create Session"
   - Click "Start" to begin
   - View statistics in the Statistics tab
   - Load data in the Data tab
   - Export using "Export..." button

### 3. Multi-Instrument Synchronization

1. **In Multi-Instrument Sync tab:**
   - Select multiple equipment (Ctrl+Click)
   - Enter a group ID (e.g., "test_sync")
   - Click "Create Group"
2. **Create acquisitions** for each equipment first (in Data Acquisition tab)
3. **Add acquisitions to group:**
   - Select sync group from list
   - Choose acquisition from dropdown
   - Click "Add to Group"
4. **Start synchronized acquisition:**
   - Click "Start Group"

---

## Testing the Installation

### 1. Run Setup Check

```bash
python3 setup.py --check
```

This verifies all dependencies without installing.

### 2. Run Unit Tests

```bash
# Run all tests
python3 run_tests.py

# Run specific test category
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/
```

### 3. Test Server API

```bash
# Start server
cd server
python3 main.py

# In another terminal, test with curl
curl http://localhost:8000/health
curl http://localhost:8000/api/equipment
```

### 4. Test Mock Equipment

```bash
cd server
python3 test_mock_equipment.py
```

---

## Troubleshooting

### Common Issues

**1. "Python version not supported"**
```bash
# Check Python version
python3 --version

# Upgrade if needed (Ubuntu/Debian)
sudo apt update
sudo apt install python3.10

# Or use pyenv for version management
```

**2. "Module not found" errors**
```bash
# Reinstall dependencies
pip install -r server/requirements.txt
pip install -r client/requirements.txt

# Or use setup script
python3 setup.py --auto
```

**3. "Connection refused" when starting client**
```bash
# Make sure server is running
cd server
python3 main.py

# Check if port 8000 is in use
lsof -i :8000  # Linux/macOS
netstat -ano | findstr :8000  # Windows
```

**4. "Permission denied" for VISA/USB devices**
```bash
# Linux: Add user to dialout group
sudo usermod -a -G dialout $USER
# Log out and back in for changes to take effect
```

**5. PyQt6 import errors**
```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt install python3-pyqt6

# Or reinstall PyQt6
pip uninstall PyQt6
pip install PyQt6
```

**6. "No module named 'venv'"**
```bash
# Install venv module (Ubuntu/Debian)
sudo apt install python3-venv

# Or use virtualenv instead
pip install virtualenv
virtualenv venv
```

### Getting Help

- **Documentation:** See `docs/` directory
- **User Guide:** `docs/USER_GUIDE.md`
- **API Reference:** http://localhost:8000/docs (when server running)
- **Issues:** Create an issue on GitHub
- **Logs:** Check `server/lablink.log` for errors

---

## Directory Structure

```
LabLink/
├── setup.py                  # Automated setup script ⭐
├── demo_acquisition_full.py  # Comprehensive demo ⭐
├── server/
│   ├── main.py              # Server entry point
│   ├── requirements.txt     # Server dependencies
│   ├── .env                 # Configuration (create from .env.example)
│   └── ...
├── client/
│   ├── requirements.txt     # Client dependencies
│   ├── api/                 # API client
│   ├── ui/                  # PyQt6 UI components
│   ├── models/              # Data models
│   └── utils/               # Utilities
├── tests/
│   ├── unit/                # Unit tests
│   ├── integration/         # Integration tests
│   └── e2e/                 # End-to-end tests
├── docs/                    # Documentation
│   ├── USER_GUIDE.md        # User guide
│   ├── QUICK_REFERENCE.md   # Quick reference
│   └── ...
└── requirements-test.txt    # Test dependencies
```

---

## Next Steps

Once you have LabLink running:

1. **Explore the Demo:**
   - Try different acquisition modes
   - Test statistics analysis
   - Export data in different formats
   - Create sync groups

2. **Read the Documentation:**
   - `docs/USER_GUIDE.md` - Complete user guide
   - `docs/QUICK_REFERENCE.md` - Quick command reference
   - `client/ACQUISITION_CLIENT.md` - Client integration details
   - `server/ACQUISITION_SYSTEM.md` - Server API reference

3. **Connect Your Equipment:**
   - Install NI-VISA if using real hardware
   - Configure equipment in server settings
   - Test with mock equipment first

4. **Customize:**
   - Add equipment drivers (see `server/equipment/`)
   - Create custom UI panels
   - Write automation scripts
   - Integrate with your workflow

---

## Deployment Checklist

Before deploying LabLink:

- [ ] Run `python3 setup.py --check` to verify dependencies
- [ ] Review and configure `server/.env` settings
- [ ] Test with mock equipment first
- [ ] Configure safety limits appropriately
- [ ] Set up logging directory with write permissions
- [ ] Configure firewall rules if accessing remotely
- [ ] Test client-server connection
- [ ] Review security settings (authentication, permissions)
- [ ] Set up backup procedures for data exports
- [ ] Document your equipment configurations

---

## Performance Tips

- Use virtual environment to isolate dependencies
- Configure appropriate buffer sizes (larger = more memory)
- Use appropriate sample rates (higher = more CPU/memory)
- Export large datasets to HDF5 instead of CSV
- Enable auto-export for long-term acquisitions
- Monitor server logs for performance issues
- Use mDNS for automatic server discovery
- Configure acquisition timeout values appropriately

---

## Security Notes

**For production deployment:**

1. Change default ports if needed
2. Configure firewall rules
3. Use strong authentication (add JWT/OAuth if needed)
4. Restrict CORS origins
5. Enable HTTPS for web access
6. Review equipment permissions
7. Audit equipment access logs
8. Use virtual environment
9. Keep dependencies updated
10. Follow security best practices

---

## Additional Resources

- **Main Roadmap:** `ROADMAP.md`
- **Server Roadmap:** `server/ROADMAP.md`
- **Completion Summary:** `COMPLETION_SUMMARY.md`
- **Test Guide:** `docs/TEST_SUITE.md`
- **Mock Equipment Guide:** `docs/MOCK_EQUIPMENT.md`
- **WebSocket Guide:** `docs/WEBSOCKET_STREAMING.md`

---

## Support

For issues, questions, or contributions:

- Check existing documentation
- Search issues on GitHub
- Create a new issue with details
- Include logs and error messages
- Specify Python version and OS

---

**Last Updated:** 2025-11-08
**Version:** 0.6.0
**Status:** Production Ready

**Happy data acquisition! 🔬📊**
