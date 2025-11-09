"""Settings manager for LabLink client using QSettings."""

import logging
from typing import Any, Dict, List, Optional
from pathlib import Path

try:
    from PyQt6.QtCore import QSettings
    QSETTINGS_AVAILABLE = True
except ImportError:
    QSETTINGS_AVAILABLE = False

logger = logging.getLogger(__name__)


class SettingsManager:
    """Manages application settings using QSettings."""

    def __init__(self, organization: str = "LabLink", application: str = "LabLinkClient"):
        """Initialize settings manager.

        Args:
            organization: Organization name for settings
            application: Application name for settings
        """
        if not QSETTINGS_AVAILABLE:
            raise ImportError("PyQt6 is required for settings management")

        self.settings = QSettings(organization, application)
        logger.info(f"Settings file: {self.settings.fileName()}")

    # ==================== Connection Settings ====================

    def get_last_host(self, default: str = "localhost") -> str:
        """Get last used server host.

        Args:
            default: Default host if not set

        Returns:
            Server host
        """
        return self.settings.value("connection/host", default, type=str)

    def set_last_host(self, host: str):
        """Set last used server host.

        Args:
            host: Server host
        """
        self.settings.setValue("connection/host", host)
        logger.debug(f"Saved host: {host}")

    def get_last_api_port(self, default: int = 8000) -> int:
        """Get last used API port.

        Args:
            default: Default port if not set

        Returns:
            API port
        """
        return self.settings.value("connection/api_port", default, type=int)

    def set_last_api_port(self, port: int):
        """Set last used API port.

        Args:
            port: API port
        """
        self.settings.setValue("connection/api_port", port)

    def get_last_ws_port(self, default: int = 8001) -> int:
        """Get last used WebSocket port.

        Args:
            default: Default port if not set

        Returns:
            WebSocket port
        """
        return self.settings.value("connection/ws_port", default, type=int)

    def set_last_ws_port(self, port: int):
        """Set last used WebSocket port.

        Args:
            port: WebSocket port
        """
        self.settings.setValue("connection/ws_port", port)

    def get_recent_servers(self, max_count: int = 10) -> List[Dict[str, Any]]:
        """Get list of recent server connections.

        Args:
            max_count: Maximum number of recent servers

        Returns:
            List of server dictionaries
        """
        size = self.settings.beginReadArray("connection/recent_servers")
        servers = []

        for i in range(min(size, max_count)):
            self.settings.setArrayIndex(i)
            server = {
                "host": self.settings.value("host", "localhost", type=str),
                "api_port": self.settings.value("api_port", 8000, type=int),
                "ws_port": self.settings.value("ws_port", 8001, type=int),
                "name": self.settings.value("name", "", type=str)
            }
            servers.append(server)

        self.settings.endArray()
        return servers

    def add_recent_server(self, host: str, api_port: int, ws_port: int, name: str = ""):
        """Add server to recent connections list.

        Args:
            host: Server host
            api_port: API port
            ws_port: WebSocket port
            name: Optional friendly name
        """
        # Get existing servers
        servers = self.get_recent_servers()

        # Create new server entry
        new_server = {
            "host": host,
            "api_port": api_port,
            "ws_port": ws_port,
            "name": name
        }

        # Remove if already exists
        servers = [s for s in servers if not (
            s["host"] == host and
            s["api_port"] == api_port and
            s["ws_port"] == ws_port
        )]

        # Add to front
        servers.insert(0, new_server)

        # Keep only last 10
        servers = servers[:10]

        # Save
        self.settings.beginWriteArray("connection/recent_servers", len(servers))
        for i, server in enumerate(servers):
            self.settings.setArrayIndex(i)
            self.settings.setValue("host", server["host"])
            self.settings.setValue("api_port", server["api_port"])
            self.settings.setValue("ws_port", server["ws_port"])
            self.settings.setValue("name", server["name"])
        self.settings.endArray()

        logger.debug(f"Added recent server: {host}:{api_port}")

    def get_auto_connect(self, default: bool = False) -> bool:
        """Get auto-connect on startup setting.

        Args:
            default: Default value

        Returns:
            Auto-connect enabled
        """
        return self.settings.value("connection/auto_connect", default, type=bool)

    def set_auto_connect(self, enabled: bool):
        """Set auto-connect on startup.

        Args:
            enabled: Auto-connect enabled
        """
        self.settings.setValue("connection/auto_connect", enabled)

    # ==================== Window Settings ====================

    def get_window_geometry(self) -> Optional[bytes]:
        """Get saved window geometry.

        Returns:
            Window geometry bytes or None
        """
        return self.settings.value("window/geometry", None)

    def set_window_geometry(self, geometry: bytes):
        """Save window geometry.

        Args:
            geometry: Window geometry bytes
        """
        self.settings.setValue("window/geometry", geometry)

    def get_window_state(self) -> Optional[bytes]:
        """Get saved window state.

        Returns:
            Window state bytes or None
        """
        return self.settings.value("window/state", None)

    def set_window_state(self, state: bytes):
        """Save window state.

        Args:
            state: Window state bytes
        """
        self.settings.setValue("window/state", state)

    # ==================== Equipment Settings ====================

    def get_last_equipment(self) -> Optional[str]:
        """Get last selected equipment ID.

        Returns:
            Equipment ID or None
        """
        return self.settings.value("equipment/last_selected", None, type=str)

    def set_last_equipment(self, equipment_id: str):
        """Set last selected equipment.

        Args:
            equipment_id: Equipment ID
        """
        self.settings.setValue("equipment/last_selected", equipment_id)

    def get_favorite_equipment(self) -> List[str]:
        """Get list of favorite equipment IDs.

        Returns:
            List of equipment IDs
        """
        favorites = self.settings.value("equipment/favorites", [], type=list)
        return [str(item) for item in favorites]

    def add_favorite_equipment(self, equipment_id: str):
        """Add equipment to favorites.

        Args:
            equipment_id: Equipment ID
        """
        favorites = self.get_favorite_equipment()
        if equipment_id not in favorites:
            favorites.append(equipment_id)
            self.settings.setValue("equipment/favorites", favorites)
            logger.debug(f"Added favorite: {equipment_id}")

    def remove_favorite_equipment(self, equipment_id: str):
        """Remove equipment from favorites.

        Args:
            equipment_id: Equipment ID
        """
        favorites = self.get_favorite_equipment()
        if equipment_id in favorites:
            favorites.remove(equipment_id)
            self.settings.setValue("equipment/favorites", favorites)
            logger.debug(f"Removed favorite: {equipment_id}")

    # ==================== Acquisition Settings ====================

    def get_default_sample_rate(self, default: float = 1000.0) -> float:
        """Get default sample rate.

        Args:
            default: Default value

        Returns:
            Sample rate in Hz
        """
        return self.settings.value("acquisition/sample_rate", default, type=float)

    def set_default_sample_rate(self, rate: float):
        """Set default sample rate.

        Args:
            rate: Sample rate in Hz
        """
        self.settings.setValue("acquisition/sample_rate", rate)

    def get_default_buffer_size(self, default: int = 10000) -> int:
        """Get default buffer size.

        Args:
            default: Default value

        Returns:
            Buffer size
        """
        return self.settings.value("acquisition/buffer_size", default, type=int)

    def set_default_buffer_size(self, size: int):
        """Set default buffer size.

        Args:
            size: Buffer size
        """
        self.settings.setValue("acquisition/buffer_size", size)

    def get_auto_export(self, default: bool = False) -> bool:
        """Get auto-export setting.

        Args:
            default: Default value

        Returns:
            Auto-export enabled
        """
        return self.settings.value("acquisition/auto_export", default, type=bool)

    def set_auto_export(self, enabled: bool):
        """Set auto-export.

        Args:
            enabled: Auto-export enabled
        """
        self.settings.setValue("acquisition/auto_export", enabled)

    def get_export_directory(self, default: str = "") -> str:
        """Get default export directory.

        Args:
            default: Default directory

        Returns:
            Export directory path
        """
        return self.settings.value("acquisition/export_dir", default, type=str)

    def set_export_directory(self, directory: str):
        """Set default export directory.

        Args:
            directory: Directory path
        """
        self.settings.setValue("acquisition/export_dir", directory)

    # ==================== Visualization Settings ====================

    def get_plot_buffer_size(self, default: int = 1000) -> int:
        """Get plot buffer size.

        Args:
            default: Default value

        Returns:
            Buffer size
        """
        return self.settings.value("visualization/buffer_size", default, type=int)

    def set_plot_buffer_size(self, size: int):
        """Set plot buffer size.

        Args:
            size: Buffer size
        """
        self.settings.setValue("visualization/buffer_size", size)

    def get_plot_update_rate(self, default: int = 50) -> int:
        """Get plot update rate in milliseconds.

        Args:
            default: Default value

        Returns:
            Update rate in ms
        """
        return self.settings.value("visualization/update_rate", default, type=int)

    def set_plot_update_rate(self, rate_ms: int):
        """Set plot update rate.

        Args:
            rate_ms: Update rate in milliseconds
        """
        self.settings.setValue("visualization/update_rate", rate_ms)

    def get_theme(self, default: str = "light") -> str:
        """Get UI theme.

        Args:
            default: Default theme

        Returns:
            Theme name
        """
        return self.settings.value("visualization/theme", default, type=str)

    def set_theme(self, theme: str):
        """Set UI theme.

        Args:
            theme: Theme name (light, dark)
        """
        self.settings.setValue("visualization/theme", theme)

    # ==================== General Methods ====================

    def get_value(self, key: str, default: Any = None, value_type: type = str) -> Any:
        """Get a generic setting value.

        Args:
            key: Settings key
            default: Default value
            value_type: Type to cast to

        Returns:
            Setting value
        """
        return self.settings.value(key, default, type=value_type)

    def set_value(self, key: str, value: Any):
        """Set a generic setting value.

        Args:
            key: Settings key
            value: Value to set
        """
        self.settings.setValue(key, value)
        logger.debug(f"Set {key} = {value}")

    def clear_all(self):
        """Clear all settings."""
        self.settings.clear()
        logger.warning("All settings cleared")

    def get_all_keys(self) -> List[str]:
        """Get all settings keys.

        Returns:
            List of keys
        """
        return self.settings.allKeys()

    def sync(self):
        """Synchronize settings to disk."""
        self.settings.sync()

    def get_settings_file(self) -> str:
        """Get path to settings file.

        Returns:
            Settings file path
        """
        return self.settings.fileName()

    def export_settings(self, filepath: str):
        """Export settings to file.

        Args:
            filepath: Export file path
        """
        # Get all settings
        all_settings = {}
        for key in self.settings.allKeys():
            all_settings[key] = self.settings.value(key)

        # Write to file
        import json
        with open(filepath, 'w') as f:
            json.dump(all_settings, f, indent=2, default=str)

        logger.info(f"Settings exported to {filepath}")

    def import_settings(self, filepath: str):
        """Import settings from file.

        Args:
            filepath: Import file path
        """
        import json
        with open(filepath, 'r') as f:
            all_settings = json.load(f)

        # Set all settings
        for key, value in all_settings.items():
            self.settings.setValue(key, value)

        self.settings.sync()
        logger.info(f"Settings imported from {filepath}")


# Global settings manager instance
_settings_manager: Optional[SettingsManager] = None


def get_settings() -> SettingsManager:
    """Get global settings manager instance.

    Returns:
        Settings manager
    """
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = SettingsManager()
    return _settings_manager
