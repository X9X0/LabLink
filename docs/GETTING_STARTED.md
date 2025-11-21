# LabLink - Getting Started Guide

## Overview

LabLink is a modular client-server application for remote control and data acquisition from laboratory equipment including Rigol oscilloscopes and BK Precision power supplies and electronic loads.

## Architecture

- **Server**: Python FastAPI application running on Raspberry Pi, connected to lab equipment
- **Client**: Desktop GUI application for remote control and monitoring
- **Communication**: REST API + WebSocket for real-time data streaming

## Prerequisites

### Server (Raspberry Pi)

- Raspberry Pi 4 or 5
- Raspberry Pi OS Lite (64-bit recommended)
- Python 3.11 or higher
- USB/Serial/Ethernet connections to lab equipment

### Client (Development Machine)

- Windows 10/11 or Linux
- Python 3.11 or higher
- Network connection to Raspberry Pi

## Installation

### Server Setup

1. **Prepare Raspberry Pi**
   ```bash
   # Update system
   sudo apt update && sudo apt upgrade -y

   # Install Python and dependencies
   sudo apt install python3-pip python3-venv libusb-1.0-0
   ```

2. **Clone/Copy LabLink to Raspberry Pi**
   ```bash
   cd ~
   # Copy LabLink directory to Pi (via scp, git, or USB)
   ```

3. **Set up Python virtual environment**
   ```bash
   cd ~/LabLink/server
   python3 -m venv venv
   source venv/bin/activate
   ```

4. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Configure USB permissions (for VISA devices)**
   ```bash
   # Add user to dialout and plugdev groups
   sudo usermod -a -G dialout $USER
   sudo usermod -a -G plugdev $USER

   # Create udev rule for USB instruments
   sudo nano /etc/udev/rules.d/99-lablink.rules
   ```

   Add this line:
   ```
   SUBSYSTEM=="usb", MODE="0666", GROUP="plugdev"
   ```

   Then:
   ```bash
   sudo udevadm control --reload-rules
   sudo udevadm trigger
   ```

6. **Configure server (optional)**
   ```bash
   cp .env.example .env
   nano .env  # Edit configuration as needed
   ```

7. **Run the server**
   ```bash
   python main.py
   ```

### Client Setup (Coming Soon)

The GUI client is under development. For now, you can test the server with the included test client:

```bash
cd ~/LabLink
python test_client.py
```

## Testing the Server

1. **Start the server**
   ```bash
   cd ~/LabLink/server
   source venv/bin/activate
   python main.py
   ```

2. **Test with curl or browser**
   ```bash
   # Health check
   curl http://localhost:8000/health

   # Discover devices
   curl -X POST http://localhost:8000/api/equipment/discover
   ```

3. **View API documentation**

   Open browser to: `http://<raspberry-pi-ip>:8000/docs`

   This provides interactive API documentation powered by FastAPI.

## Supported Equipment

### Currently Implemented

- **Rigol MSO2072A** - Mixed Signal Oscilloscope
- **Rigol DS1104** - Digital Oscilloscope
- **Rigol DL3021A** - DC Electronic Load
- **BK Precision 9206B** - Multi-Range DC Power Supply
- **BK Precision 9205B** - Multi-Range DC Power Supply
- **BK Precision 9130B** - Triple Output DC Power Supply
- **BK Precision 1902B** - DC Electronic Load
- **BK Precision 1685B** - DC Power Supply

### Adding More Equipment

New equipment can be added by:
1. Creating a new driver class in `server/equipment/`
2. Inheriting from `BaseEquipment`
3. Implementing required methods
4. Registering in `equipment_manager.py`

## API Usage Examples

### Discover Available Devices

```bash
curl -X POST http://localhost:8000/api/equipment/discover
```

### Connect to a Device

```bash
curl -X POST http://localhost:8000/api/equipment/connect \
  -H "Content-Type: application/json" \
  -d '{
    "resource_string": "USB0::0x1AB1::0x04CE::DS2A123456789::INSTR",
    "equipment_type": "oscilloscope",
    "model": "MSO2072A"
  }'
```

### List Connected Devices

```bash
curl http://localhost:8000/api/equipment/list
```

### Execute a Command

```bash
curl -X POST http://localhost:8000/api/equipment/{equipment_id}/command \
  -H "Content-Type: application/json" \
  -d '{
    "command_id": "cmd_001",
    "equipment_id": "scope_abc123",
    "action": "get_measurements",
    "parameters": {"channel": 1}
  }'
```

## WebSocket Streaming

Connect to `ws://localhost:8000/ws` for real-time data streaming.

Example messages:

**Start Streaming:**
```json
{
  "type": "start_stream",
  "equipment_id": "scope_abc123",
  "stream_type": "measurements",
  "interval_ms": 100
}
```

**Stop Streaming:**
```json
{
  "type": "stop_stream",
  "equipment_id": "scope_abc123",
  "stream_type": "measurements"
}
```

## Troubleshooting

### USB Device Not Detected

1. Check USB connections
2. Verify udev rules are set up correctly
3. Check dmesg for USB device recognition:
   ```bash
   dmesg | grep -i usb
   ```

### VISA Resource Not Found

1. Test with PyVISA directly:
   ```python
   import pyvisa
   rm = pyvisa.ResourceManager('@py')
   print(rm.list_resources())
   ```

2. Check device manufacturer's VISA driver installation

### Server Won't Start

1. Check port availability:
   ```bash
   sudo lsof -i :8000
   ```

2. Check Python dependencies:
   ```bash
   pip list
   ```

3. Check logs for error messages

## Next Steps

1. Connect your lab equipment to the Raspberry Pi
2. Start the server and test device discovery
3. Connect to devices and test basic commands
4. Explore the API documentation at `/docs`
5. Wait for GUI client development (or contribute!)

## Contributing

This project is in active development. Feature requests and contributions are welcome!

## License

TBD
