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

### In Development

- [ ] Desktop GUI client (PyQt6)
- [ ] Automatic Raspberry Pi network discovery
- [ ] SSH-based server deployment wizard
- [ ] Real-time data visualization
- [ ] Data logging and export functionality
- [ ] Multi-server management interface

## Supported Equipment

- Rigol MSO2072A Oscilloscope
- BK Precision 9206B Multi-Range DC Power Supply
- BK Precision 9130 DC Power Supply
- BK Precision 1902B DC Electronic Load

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

4. Test the server:
   ```bash
   python ../test_client.py
   ```

For detailed setup instructions, see [Getting Started Guide](docs/GETTING_STARTED.md).

## Documentation

- [Getting Started Guide](docs/GETTING_STARTED.md) - Installation and setup
- [API Reference](docs/API_REFERENCE.md) - Complete API documentation with examples

## Project Status

**Phase 1 Complete**: Core server functionality implemented
- REST API operational
- WebSocket streaming functional
- All equipment drivers working

**Next Phase**: GUI client development

## Contributing

This project is in active development. Contributions, feature requests, and bug reports are welcome!

## License

TBD
