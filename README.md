# LabLink

A modular client-server application for remote control and data acquisition from laboratory equipment (Rigol and BK Precision scopes, power supplies, and loads).

## Overview

LabLink enables remote control of lab equipment through a Raspberry Pi server, providing an intuitive graphical client for equipment management, data acquisition, and visualization.

## Architecture

- **Server**: Python-based server running on Raspberry Pi, connected to lab equipment via USB/Serial/Ethernet
- **Client**: Cross-platform desktop GUI for equipment control, monitoring, and data visualization
- **Communication**: WebSocket for real-time data streaming, REST API for control commands

## Features (Planned)

- [ ] Automatic Raspberry Pi discovery on local network
- [ ] Easy SSH-based server deployment to Raspberry Pi
- [ ] Support for multiple equipment types (scopes, power supplies, loads)
- [ ] Real-time data streaming and visualization
- [ ] Configurable data logging and buffering
- [ ] Multi-server management from single client
- [ ] Modular driver architecture for easy equipment addition

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

## Project Status

In initial development phase.

## License

TBD
