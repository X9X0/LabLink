# Configuration Persistence Guide

Complete guide to configuration management and persistence in LabLink using QSettings.

## Overview

LabLink uses Qt's QSettings system for persistent configuration storage. Settings are automatically saved between sessions and synced across the application.

**Features:**
- Persistent storage of all user preferences
- Recent servers list
- Equipment favorites
- Acquisition defaults
- Visualization preferences
- Import/Export settings
- Cross-platform storage (Windows Registry, macOS plist, Linux INI)

## Quick Start

### Basic Usage

```python
from client.utils.settings import get_settings

# Get global settings instance
settings = get_settings()

# Save connection settings
settings.set_last_host("192.168.1.100")
settings.set_last_api_port(8080)

# Load connection settings
host = settings.get_last_host()
port = settings.get_last_api_port()
```

### Settings Dialog

```python
from PyQt6.QtWidgets import QApplication
from client.ui.settings_dialog import SettingsDialog
from client.utils.settings import get_settings

app = QApplication([])
settings = get_settings()

# Open settings dialog
dialog = SettingsDialog(settings)
if dialog.exec():
    print("Settings saved!")

app.exec()
```

## SettingsManager API

### Connection Settings

```python
from client.utils.settings import SettingsManager

settings = SettingsManager()

# Server connection
settings.set_last_host("localhost")
host = settings.get_last_host(default="localhost")

settings.set_last_api_port(8000)
api_port = settings.get_last_api_port(default=8000)

settings.set_last_ws_port(8001)
ws_port = settings.get_last_ws_port(default=8001)

# Auto-connect on startup
settings.set_auto_connect(True)
auto_connect = settings.get_auto_connect(default=False)
```

### Recent Servers

```python
# Add to recent servers list
settings.add_recent_server(
    host="192.168.1.100",
    api_port=8000,
    ws_port=8001,
    name="Lab Server"
)

# Get recent servers (up to 10)
recent = settings.get_recent_servers(max_count=10)
for server in recent:
    print(f"{server['name']}: {server['host']}:{server['api_port']}")

# Output:
# Lab Server: 192.168.1.100:8000
# Local Server: localhost:8000
```

### Equipment Settings

```python
# Last selected equipment
settings.set_last_equipment("scope_12345678")
equipment_id = settings.get_last_equipment()

# Favorites
settings.add_favorite_equipment("ps_11111111")
settings.add_favorite_equipment("load_22222222")

favorites = settings.get_favorite_equipment()
# Returns: ["ps_11111111", "load_22222222"]

settings.remove_favorite_equipment("ps_11111111")
```

### Acquisition Settings

```python
# Default sample rate
settings.set_default_sample_rate(1000.0)
rate = settings.get_default_sample_rate(default=1000.0)

# Buffer size
settings.set_default_buffer_size(10000)
size = settings.get_default_buffer_size(default=10000)

# Auto-export
settings.set_auto_export(True)
auto_export = settings.get_auto_export(default=False)

# Export directory
settings.set_export_directory("/home/user/data")
directory = settings.get_export_directory(default="")
```

### Visualization Settings

```python
# Plot buffer size
settings.set_plot_buffer_size(1000)
buffer_size = settings.get_plot_buffer_size(default=1000)

# Plot update rate (milliseconds)
settings.set_plot_update_rate(50)
update_rate = settings.get_plot_update_rate(default=50)

# Theme
settings.set_theme("dark")
theme = settings.get_theme(default="light")
# Options: "light", "dark", "system"
```

### Window Geometry

```python
from PyQt6.QtWidgets import QMainWindow

class MyWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = get_settings()

        # Restore window geometry
        geometry = self.settings.get_window_geometry()
        if geometry:
            self.restoreGeometry(geometry)

        # Restore window state (toolbars, docks, etc.)
        state = self.settings.get_window_state()
        if state:
            self.restoreState(state)

    def closeEvent(self, event):
        # Save window geometry
        self.settings.set_window_geometry(self.saveGeometry())
        self.settings.set_window_state(self.saveState())
        event.accept()
```

### Generic Settings

```python
# Save any key-value pair
settings.set_value("custom/my_setting", 42)
settings.set_value("custom/another", "Hello")

# Load with type casting
value = settings.get_value("custom/my_setting", default=0, value_type=int)
text = settings.get_value("custom/another", default="", value_type=str)
```

### Advanced Operations

```python
# Get all settings keys
all_keys = settings.get_all_keys()
print(f"Total keys: {len(all_keys)}")

# Sync to disk (usually automatic)
settings.sync()

# Get settings file location
filepath = settings.get_settings_file()
print(f"Settings stored at: {filepath}")

# Clear all settings
settings.clear_all()  # Use with caution!
```

## Import/Export

### Export Settings

```python
# Export to JSON file
settings.export_settings("/path/to/backup.json")
```

Example exported file:
```json
{
  "connection/host": "192.168.1.100",
  "connection/api_port": 8000,
  "connection/ws_port": 8001,
  "acquisition/sample_rate": 1000.0,
  "acquisition/buffer_size": 10000,
  "visualization/theme": "dark"
}
```

### Import Settings

```python
# Import from JSON file
settings.import_settings("/path/to/backup.json")

# Settings are immediately available
host = settings.get_last_host()  # Returns imported value
```

## Settings Dialog

### Opening the Dialog

```python
from client.ui.settings_dialog import SettingsDialog

# Create and show dialog
dialog = SettingsDialog(settings, parent=main_window)

# Modal (blocks until closed)
if dialog.exec():
    print("User clicked Save")
else:
    print("User clicked Cancel")

# Non-modal (doesn't block)
dialog.show()
```

### Dialog Features

The settings dialog provides four tabs:

**1. Connection Tab:**
- Default server host
- API port
- WebSocket port
- Auto-connect on startup
- Recent servers management

**2. Acquisition Tab:**
- Default sample rate
- Buffer size
- Auto-export settings
- Export directory selection

**3. Visualization Tab:**
- Plot buffer size
- Update rate
- Theme selection (Light, Dark, System)

**4. Advanced Tab:**
- Settings file location
- Key count
- Sync to disk
- Clear all settings

### Dialog Actions

- **Save** - Save changes and close
- **Cancel** - Discard changes
- **Reset to Defaults** - Clear all settings
- **Import...** - Import from JSON file
- **Export...** - Export to JSON file

## Complete Example

```python
"""Complete settings integration example."""

from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget
from client.utils.settings import get_settings
from client.ui.settings_dialog import SettingsDialog
from client.api.client import LabLinkClient
import asyncio


class MainWindow(QMainWindow):
    """Main application window with settings integration."""

    def __init__(self):
        super().__init__()

        # Get settings
        self.settings = get_settings()

        # Restore window geometry
        geometry = self.settings.get_window_geometry()
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.setGeometry(100, 100, 800, 600)

        # Setup UI
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Settings button
        settings_btn = QPushButton("Settings...")
        settings_btn.clicked.connect(self.open_settings)
        layout.addWidget(settings_btn)

        # Connect button
        connect_btn = QPushButton("Connect to Server")
        connect_btn.clicked.connect(self.connect_to_server)
        layout.addWidget(connect_btn)

        # Auto-connect if enabled
        if self.settings.get_auto_connect():
            asyncio.create_task(self.auto_connect())

    def open_settings(self):
        """Open settings dialog."""
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            # Settings were saved
            print("Settings updated")

            # Apply new settings
            self.apply_settings()

    def apply_settings(self):
        """Apply current settings to application."""
        # Update theme
        theme = self.settings.get_theme()
        if theme == "dark":
            # Apply dark theme
            pass
        elif theme == "light":
            # Apply light theme
            pass

    async def auto_connect(self):
        """Auto-connect to last server."""
        host = self.settings.get_last_host()
        api_port = self.settings.get_last_api_port()
        ws_port = self.settings.get_last_ws_port()

        print(f"Auto-connecting to {host}:{api_port}...")
        await self.connect_to_server()

    async def connect_to_server(self):
        """Connect to server using saved settings."""
        # Get connection settings
        host = self.settings.get_last_host()
        api_port = self.settings.get_last_api_port()
        ws_port = self.settings.get_last_ws_port()

        # Create client
        client = LabLinkClient(host=host, api_port=api_port, ws_port=ws_port)

        # Connect
        if client.connect():
            print("Connected!")

            # Add to recent servers
            self.settings.add_recent_server(
                host=host,
                api_port=api_port,
                ws_port=ws_port,
                name="Last Connection"
            )

    def closeEvent(self, event):
        """Save settings on close."""
        # Save window geometry
        self.settings.set_window_geometry(self.saveGeometry())
        self.settings.set_window_state(self.saveState())

        # Sync to disk
        self.settings.sync()

        event.accept()


if __name__ == "__main__":
    app = QApplication([])

    window = MainWindow()
    window.show()

    app.exec()
```

## Settings Storage Locations

### Windows
```
HKEY_CURRENT_USER\Software\LabLink\LabLinkClient
```

### macOS
```
~/Library/Preferences/com.LabLink.LabLinkClient.plist
```

### Linux
```
~/.config/LabLink/LabLinkClient.conf
```

## Best Practices

### 1. Use Defaults

Always provide default values:

```python
# Good
host = settings.get_last_host(default="localhost")

# Avoid
host = settings.get_last_host()  # Returns None if not set
```

### 2. Sync After Batch Changes

```python
# Batch multiple changes
settings.set_last_host("192.168.1.100")
settings.set_last_api_port(8080)
settings.set_last_ws_port(8081)

# Sync once
settings.sync()
```

### 3. Validate Settings

```python
# Validate before use
port = settings.get_last_api_port()
if port < 1 or port > 65535:
    port = 8000  # Use default
    settings.set_last_api_port(port)
```

### 4. Handle Missing Settings

```python
# Gracefully handle missing settings
export_dir = settings.get_export_directory()
if not export_dir or not os.path.exists(export_dir):
    export_dir = os.path.expanduser("~/Documents")
    settings.set_export_directory(export_dir)
```

### 5. Save on Application Exit

```python
def closeEvent(self, event):
    """Always save on exit."""
    self.settings.set_window_geometry(self.saveGeometry())
    self.settings.sync()
    event.accept()
```

## Troubleshooting

### Settings Not Persisting

```python
# Explicitly sync to disk
settings.sync()

# Check file location
print(f"Settings file: {settings.get_settings_file()}")

# Verify write permissions
import os
filepath = settings.get_settings_file()
if os.path.exists(filepath):
    print(f"File exists: {os.access(filepath, os.W_OK)}")
```

### Settings File Corrupted

```python
# Clear and start fresh
settings.clear_all()

# Or restore from backup
settings.import_settings("/path/to/backup.json")
```

### Finding Settings

```python
# List all keys
for key in settings.get_all_keys():
    value = settings.settings.value(key)
    print(f"{key} = {value}")
```

## API Reference

### SettingsManager Methods

**Connection:**
- `get_last_host(default)` - Get last server host
- `set_last_host(host)` - Set last server host
- `get_last_api_port(default)` - Get API port
- `set_last_api_port(port)` - Set API port
- `get_last_ws_port(default)` - Get WebSocket port
- `set_last_ws_port(port)` - Set WebSocket port
- `get_auto_connect(default)` - Get auto-connect setting
- `set_auto_connect(enabled)` - Set auto-connect
- `get_recent_servers(max_count)` - Get recent servers list
- `add_recent_server(host, api_port, ws_port, name)` - Add recent server

**Window:**
- `get_window_geometry()` - Get window geometry
- `set_window_geometry(geometry)` - Set window geometry
- `get_window_state()` - Get window state
- `set_window_state(state)` - Set window state

**Equipment:**
- `get_last_equipment()` - Get last equipment ID
- `set_last_equipment(equipment_id)` - Set last equipment
- `get_favorite_equipment()` - Get favorites list
- `add_favorite_equipment(equipment_id)` - Add favorite
- `remove_favorite_equipment(equipment_id)` - Remove favorite

**Acquisition:**
- `get_default_sample_rate(default)` - Get sample rate
- `set_default_sample_rate(rate)` - Set sample rate
- `get_default_buffer_size(default)` - Get buffer size
- `set_default_buffer_size(size)` - Set buffer size
- `get_auto_export(default)` - Get auto-export
- `set_auto_export(enabled)` - Set auto-export
- `get_export_directory(default)` - Get export directory
- `set_export_directory(directory)` - Set export directory

**Visualization:**
- `get_plot_buffer_size(default)` - Get plot buffer
- `set_plot_buffer_size(size)` - Set plot buffer
- `get_plot_update_rate(default)` - Get update rate
- `set_plot_update_rate(rate_ms)` - Set update rate
- `get_theme(default)` - Get theme
- `set_theme(theme)` - Set theme

**General:**
- `get_value(key, default, value_type)` - Get generic value
- `set_value(key, value)` - Set generic value
- `clear_all()` - Clear all settings
- `get_all_keys()` - Get all keys
- `sync()` - Sync to disk
- `get_settings_file()` - Get file path
- `export_settings(filepath)` - Export to JSON
- `import_settings(filepath)` - Import from JSON

---

*Last updated: 2024-11-08*
