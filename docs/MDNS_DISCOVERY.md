# mDNS/Zeroconf Server Discovery Guide

Complete guide to automatic server discovery in LabLink using mDNS/Zeroconf.

## Overview

LabLink supports automatic server discovery using mDNS (Multicast DNS) / Zeroconf technology. This allows:

- **Servers** to automatically advertise themselves on the local network
- **Clients** to discover available servers without manual configuration
- **Zero configuration** networking - no need to remember IP addresses

**Service Type:** `_lablink._tcp.local.`

**Technology:** Based on Apple Bonjour / Avahi / Zeroconf protocol

**Requirements:** `zeroconf` Python package

## Quick Start

### Installation

```bash
# Install zeroconf package
pip install zeroconf
```

### Server - Enable mDNS

```python
from server.utils.mdns import LabLinkMDNSService

# Create mDNS service
mdns = LabLinkMDNSService(
    port=8000,              # HTTP API port
    ws_port=8001,           # WebSocket port
    server_name="MyLabServer",
    server_version="1.0.0"
)

# Start broadcasting
mdns.start()

# Server is now discoverable on the network

# Stop broadcasting when shutting down
mdns.stop()
```

### Client - Discover Servers

```python
from client.utils.mdns_discovery import discover_servers

# Discover servers (blocks for timeout period)
servers = discover_servers(timeout=5.0)

for server in servers:
    print(f"Found: {server.name} at {server.address}:{server.port}")

# Connect to first server
if servers:
    server = servers[0]
    client = LabLinkClient(
        host=server.address,
        api_port=server.port,
        ws_port=server.ws_port
    )
    client.connect()
```

### Client - Discovery Dialog (GUI)

```python
from client.ui.discovery_dialog import show_discovery_dialog

# Show discovery dialog
server = show_discovery_dialog(parent=main_window, timeout=10.0)

if server:
    print(f"User selected: {server['name']}")
    print(f"  Connect to: {server['url']}")
    # Connect to server...
```

## Server-Side mDNS

### LabLinkMDNSService Class

**Module:** `server.utils.mdns`

**Class:** `LabLinkMDNSService`

Broadcasts server availability on the local network.

#### Initialization

```python
from server.utils.mdns import LabLinkMDNSService

service = LabLinkMDNSService(
    port=8000,                      # HTTP API port
    ws_port=8001,                   # WebSocket port
    server_name="MyServer",         # Server name (defaults to hostname)
    server_version="1.0.0"          # Server version
)
```

#### Starting/Stopping

```python
# Start broadcasting
success = service.start()

if success:
    print("mDNS service started")
else:
    print("Failed to start mDNS")

# Stop broadcasting
service.stop()
```

#### Context Manager

```python
# Using context manager (auto cleanup)
with LabLinkMDNSService(port=8000, ws_port=8001) as service:
    # Service automatically starts
    print("Service running")
    # Service automatically stops when exiting
```

#### Updating Properties

```python
# Update service properties dynamically
service.update_properties({
    'status': 'running',
    'equipment_count': '5',
    'load': 'low'
})

# Changes are broadcast to network
```

#### Getting Service Info

```python
info = service.get_service_info()

print(f"Running: {info['running']}")
print(f"Name: {info['server_name']}")
print(f"Port: {info['port']}")
print(f"WS Port: {info['ws_port']}")
print(f"Version: {info['version']}")
```

### Integration with Server

**File:** `server/main.py`

```python
from fastapi import FastAPI
from server.utils.mdns import LabLinkMDNSService
import uvicorn

app = FastAPI()

# Create mDNS service
mdns_service = None

@app.on_event("startup")
async def startup():
    global mdns_service

    # Start mDNS broadcasting
    mdns_service = LabLinkMDNSService(
        port=8000,
        ws_port=8001,
        server_name="LabLink Server",
        server_version="1.0.0"
    )

    if mdns_service.start():
        print("✓ mDNS service started")
    else:
        print("✗ Failed to start mDNS service")

@app.on_event("shutdown")
async def shutdown():
    global mdns_service

    if mdns_service:
        mdns_service.stop()
        print("✓ mDNS service stopped")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Broadcast Information

The service broadcasts:

- **Server name** - Hostname or custom name
- **IP address** - Local network IP
- **API port** - HTTP API port
- **WebSocket port** - WebSocket port
- **Version** - Server version
- **Custom properties** - Any additional metadata

Example broadcast:

```
Service: MyServer._lablink._tcp.local.
Address: 192.168.1.100
Port: 8000
Properties:
  - version: 1.0.0
  - api_port: 8000
  - ws_port: 8001
  - hostname: MyServer
```

## Client-Side Discovery

### LabLinkDiscovery Class

**Module:** `client.utils.mdns_discovery`

**Class:** `LabLinkDiscovery`

Discovers LabLink servers on the network.

#### Basic Usage

```python
from client.utils.mdns_discovery import LabLinkDiscovery

discovery = LabLinkDiscovery()

# Start discovery
discovery.start()

# Wait for servers to be discovered
import time
time.sleep(5)

# Get discovered servers
servers = discovery.get_servers()

for server in servers:
    print(f"Name: {server.name}")
    print(f"Address: {server.address}:{server.port}")

# Stop discovery
discovery.stop()
```

#### Using Callbacks

```python
discovery = LabLinkDiscovery()

# Register callback for discovery events
def on_server_event(event_type, server):
    if event_type == 'added':
        print(f"Server found: {server.name}")
    elif event_type == 'removed':
        print(f"Server lost: {server.name}")
    elif event_type == 'updated':
        print(f"Server updated: {server.name}")

discovery.register_callback(on_server_event)

# Start discovery
discovery.start()

# Events will trigger callbacks in real-time

# Later...
discovery.stop()
```

#### Context Manager

```python
# Automatic cleanup
with LabLinkDiscovery() as discovery:
    discovery.start()
    time.sleep(5)
    servers = discovery.get_servers()
    # Automatically stopped when exiting
```

#### Convenience Function

```python
from client.utils.mdns_discovery import discover_servers

# Simple one-liner discovery
servers = discover_servers(timeout=5.0)

# Returns list of LabLinkServer objects
for server in servers:
    print(server.name)
```

### LabLinkServer Object

Represents a discovered server.

```python
server = servers[0]

# Properties
server.name           # Server name
server.address        # IP address
server.port           # HTTP API port
server.ws_port        # WebSocket port
server.properties     # Dict of additional properties
server.discovered_at  # Timestamp when discovered

# Methods
server_dict = server.to_dict()

# Dictionary contains:
{
    'name': 'MyServer',
    'address': '192.168.1.100',
    'port': 8000,
    'ws_port': 8001,
    'url': 'http://192.168.1.100:8000',
    'ws_url': 'ws://192.168.1.100:8001/ws',
    'properties': {'version': '1.0.0'},
    'discovered_at': 1699999999.123
}
```

### Finding Servers

```python
discovery = LabLinkDiscovery()
discovery.start()

# Find by name
server = discovery.find_server_by_name("MyServer")

# Find by IP address
server = discovery.find_server_by_address("192.168.1.100")

# Get all servers
all_servers = discovery.get_servers()

# Get as dictionaries
servers_dict = discovery.get_servers_dict()

# Clear discovered servers
discovery.clear()
```

## Discovery Dialog (GUI)

### DiscoveryDialog Class

**Module:** `client.ui.discovery_dialog`

**Class:** `DiscoveryDialog`

Qt dialog for discovering and selecting servers.

#### Using the Dialog

```python
from PyQt6.QtWidgets import QApplication, QMainWindow
from client.ui.discovery_dialog import DiscoveryDialog

class MainWindow(QMainWindow):
    def open_discovery(self):
        # Create dialog
        dialog = DiscoveryDialog(parent=self, timeout=10.0)

        # Connect signal
        dialog.server_selected.connect(self.on_server_selected)

        # Show dialog
        if dialog.exec():
            server = dialog.get_selected_server()
            # Connect to server...

    def on_server_selected(self, server_dict):
        print(f"Selected: {server_dict['name']}")
        # Connect to server...
```

#### Convenience Function

```python
from client.ui.discovery_dialog import show_discovery_dialog

# Simple one-liner
server = show_discovery_dialog(parent=main_window, timeout=10.0)

if server:
    # User selected a server
    client = LabLinkClient(
        host=server['address'],
        api_port=server['port'],
        ws_port=server['ws_port']
    )
    client.connect()
else:
    # User cancelled
    print("Discovery cancelled")
```

### Dialog Features

- **Automatic discovery** - Finds servers on network
- **Real-time updates** - Shows servers as they're discovered
- **Table view** - Displays server name, IP, ports, version
- **Refresh button** - Restart discovery
- **Connect button** - Select server and close
- **Double-click** - Quick connect to server
- **Timeout** - Automatically stops after timeout
- **Progress indicator** - Shows discovery in progress

### Dialog Screenshot Flow

```
┌─────────────────────────────────────────────────────────┐
│  Discover LabLink Servers                           [×] │
├─────────────────────────────────────────────────────────┤
│  Searching for LabLink servers on the local network... │
│                                                         │
│  [████████████████████████] Discovering...             │
│                                                         │
│  Status: Found 2 server(s)                            │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Name       │ IP Address    │ API Port │ WS Port │  │
│  ├──────────────────────────────────────────────────┤  │
│  │ LabServer  │ 192.168.1.100 │ 8000     │ 8001    │  │
│  │ TestServer │ 192.168.1.101 │ 8000     │ 8001    │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│  [Refresh]                           [Connect] [Cancel]│
└─────────────────────────────────────────────────────────┘
```

## Complete Examples

### Server Example

```python
"""LabLink server with mDNS discovery."""

from fastapi import FastAPI
from server.utils.mdns import LabLinkMDNSService
import uvicorn
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Global mDNS service
mdns_service = None

@app.on_event("startup")
async def startup():
    """Start mDNS broadcasting on server startup."""
    global mdns_service

    logger.info("Starting mDNS service...")

    try:
        mdns_service = LabLinkMDNSService(
            port=8000,
            ws_port=8001,
            server_name="LabLink Production Server",
            server_version="1.0.0"
        )

        if mdns_service.start():
            logger.info("✓ mDNS service started successfully")

            # Update with additional properties
            mdns_service.update_properties({
                'status': 'running',
                'max_connections': '100'
            })
        else:
            logger.error("✗ Failed to start mDNS service")

    except ImportError:
        logger.warning("zeroconf not installed - mDNS discovery disabled")
    except Exception as e:
        logger.error(f"mDNS service error: {e}")

@app.on_event("shutdown")
async def shutdown():
    """Stop mDNS broadcasting on server shutdown."""
    global mdns_service

    if mdns_service:
        logger.info("Stopping mDNS service...")
        mdns_service.stop()
        logger.info("✓ mDNS service stopped")

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "LabLink Server",
        "version": "1.0.0",
        "mdns_enabled": mdns_service is not None and mdns_service.running
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Client Example

```python
"""LabLink client with automatic server discovery."""

from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget
from client.utils.mdns_discovery import LabLinkDiscovery
from client.ui.discovery_dialog import show_discovery_dialog
from client.api.client import LabLinkClient

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("LabLink Client")
        self.client = None

        # Setup UI
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)

        # Discovery button
        discover_btn = QPushButton("Discover Servers")
        discover_btn.clicked.connect(self.on_discover)
        layout.addWidget(discover_btn)

        # Manual connect button
        manual_btn = QPushButton("Manual Connect")
        manual_btn.clicked.connect(self.on_manual_connect)
        layout.addWidget(manual_btn)

    def on_discover(self):
        """Open discovery dialog."""
        server = show_discovery_dialog(parent=self, timeout=10.0)

        if server:
            self.connect_to_server(server)

    def on_manual_connect(self):
        """Manual connection (fallback)."""
        # Show manual connection dialog
        pass

    def connect_to_server(self, server):
        """Connect to discovered server."""
        print(f"Connecting to: {server['name']} at {server['address']}")

        self.client = LabLinkClient(
            host=server['address'],
            api_port=server['port'],
            ws_port=server['ws_port']
        )

        if self.client.connect():
            print("✓ Connected successfully")
        else:
            print("✗ Connection failed")

if __name__ == "__main__":
    app = QApplication([])

    window = MainWindow()
    window.show()

    app.exec()
```

### Background Discovery Example

```python
"""Continuous background server discovery."""

from client.utils.mdns_discovery import LabLinkDiscovery
import time

class BackgroundDiscovery:
    def __init__(self):
        self.discovery = LabLinkDiscovery()
        self.servers = {}

    def start(self):
        """Start continuous discovery."""
        # Register callback
        self.discovery.register_callback(self.on_server_event)

        # Start discovery
        self.discovery.start()

        print("Background discovery started")

    def on_server_event(self, event_type, server):
        """Handle server discovery events."""
        if event_type == 'added':
            self.servers[server.name] = server
            print(f"+ Server appeared: {server.name}")

            # Auto-connect to first server
            if len(self.servers) == 1:
                self.auto_connect(server)

        elif event_type == 'removed':
            if server.name in self.servers:
                del self.servers[server.name]
                print(f"- Server disappeared: {server.name}")

        elif event_type == 'updated':
            print(f"~ Server updated: {server.name}")

    def auto_connect(self, server):
        """Automatically connect to server."""
        print(f"Auto-connecting to: {server.name}")
        # Connect logic here...

    def stop(self):
        """Stop discovery."""
        self.discovery.stop()
        print("Background discovery stopped")

# Usage
discovery = BackgroundDiscovery()
discovery.start()

try:
    # Keep running
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    discovery.stop()
```

## Troubleshooting

### No Servers Found

**Problem:** Discovery finds no servers

**Solutions:**

1. **Check zeroconf is installed:**
   ```bash
   pip install zeroconf
   ```

2. **Verify server is running:**
   ```bash
   curl http://localhost:8000/health
   ```

3. **Check server has mDNS enabled:**
   - Server should start LabLinkMDNSService on startup
   - Check server logs for "mDNS service started"

4. **Network firewall:**
   - mDNS uses UDP port 5353
   - Check firewall allows multicast UDP
   - May not work across network segments/VLANs

5. **Same network:**
   - Client and server must be on same local network
   - mDNS doesn't work across internet/VPNs

### Service Won't Start

**Problem:** `service.start()` returns False

**Solutions:**

1. **Port already in use:**
   ```bash
   # Check if port is available
   lsof -i :8000
   ```

2. **Permission issues:**
   - On some systems, may need elevated privileges
   - Try running with sudo (not recommended for production)

3. **Hostname resolution:**
   - Ensure hostname is valid
   - Check `/etc/hosts` configuration

4. **Multiple network interfaces:**
   - Service binds to first available interface
   - May need to specify interface explicitly

### Discovery Slow

**Problem:** Takes long time to discover servers

**Solutions:**

1. **Increase timeout:**
   ```python
   servers = discover_servers(timeout=10.0)  # Try longer timeout
   ```

2. **Network congestion:**
   - mDNS uses multicast
   - Can be slow on busy networks

3. **DNS issues:**
   - Check local DNS resolver
   - May interfere with .local domain

### Docker / Container Issues

**Problem:** mDNS doesn't work in containers

**Solutions:**

1. **Use host network:**
   ```bash
   docker run --network=host myapp
   ```

2. **Enable multicast:**
   ```yaml
   # docker-compose.yml
   services:
     lablink:
       network_mode: host
   ```

3. **Alternative:** Use static configuration instead of mDNS in containers

## Best Practices

### 1. Graceful Degradation

Always provide fallback if mDNS fails:

```python
try:
    # Try mDNS discovery
    servers = discover_servers(timeout=5.0)

    if servers:
        server = servers[0]
    else:
        raise Exception("No servers found")

except Exception as e:
    # Fall back to manual configuration
    server = {
        'address': 'localhost',
        'port': 8000,
        'ws_port': 8001
    }
```

### 2. Error Handling

Handle import errors gracefully:

```python
try:
    from server.utils.mdns import LabLinkMDNSService
    mdns_enabled = True
except ImportError:
    mdns_enabled = False
    logger.warning("mDNS disabled - zeroconf not installed")

if mdns_enabled:
    service = LabLinkMDNSService(...)
    service.start()
```

### 3. Resource Cleanup

Always stop services on shutdown:

```python
# Using context manager (recommended)
with LabLinkMDNSService(port=8000, ws_port=8001) as service:
    # Service auto-stops on exit
    run_server()

# Or manual cleanup
service = LabLinkMDNSService(port=8000, ws_port=8001)
try:
    service.start()
    run_server()
finally:
    service.stop()
```

### 4. Production Deployment

For production:

- Enable mDNS for development/local networks
- Use static configuration for cloud/production
- Provide both options in configuration

```python
# Configuration
if config.get('mdns_enabled'):
    mdns = LabLinkMDNSService(...)
    mdns.start()
```

## API Reference

### Server - LabLinkMDNSService

**Methods:**
- `__init__(port, ws_port, server_name, server_version)` - Initialize service
- `start() -> bool` - Start broadcasting
- `stop()` - Stop broadcasting
- `update_properties(properties: dict)` - Update broadcast properties
- `get_service_info() -> dict` - Get service information

**Properties:**
- `running: bool` - Service running status
- `port: int` - HTTP API port
- `ws_port: int` - WebSocket port
- `server_name: str` - Server name
- `server_version: str` - Server version

### Client - LabLinkDiscovery

**Methods:**
- `__init__()` - Initialize discovery
- `start(timeout=None)` - Start discovering
- `stop()` - Stop discovering
- `get_servers() -> List[LabLinkServer]` - Get discovered servers
- `get_servers_dict() -> List[dict]` - Get servers as dictionaries
- `find_server_by_name(name) -> LabLinkServer` - Find by name
- `find_server_by_address(address) -> LabLinkServer` - Find by address
- `register_callback(callback)` - Register event callback
- `unregister_callback(callback)` - Unregister callback
- `clear()` - Clear discovered servers

**Properties:**
- `running: bool` - Discovery running status
- `servers: dict` - Dictionary of discovered servers

### Client - LabLinkServer

**Properties:**
- `name: str` - Server name
- `address: str` - IP address
- `port: int` - HTTP API port
- `ws_port: int` - WebSocket port
- `properties: dict` - Additional properties
- `discovered_at: float` - Discovery timestamp

**Methods:**
- `to_dict() -> dict` - Convert to dictionary

---

*Last updated: 2024-11-08*
