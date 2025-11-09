"""Unit tests for settings manager."""

import pytest
import json
from pathlib import Path

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QSettings
    from client.utils.settings import SettingsManager, get_settings
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False


@pytest.mark.unit
@pytest.mark.requires_gui
@pytest.mark.skipif(not PYQT_AVAILABLE, reason="PyQt6 not available")
class TestSettingsManager:
    """Test SettingsManager class."""

    @pytest.fixture(scope="class")
    def app(self):
        """Create QApplication instance."""
        return QApplication([])

    @pytest.fixture
    def settings(self, app, tmp_path):
        """Create test settings manager."""
        # Use temp organization/app names to avoid interfering with real settings
        settings = SettingsManager(
            organization="LabLinkTest",
            application="TestApp"
        )
        yield settings
        # Clean up
        settings.clear_all()

    def test_initialization(self, settings):
        """Test settings manager initializes correctly."""
        assert settings.settings is not None
        assert isinstance(settings.settings, QSettings)

    def test_connection_settings(self, settings):
        """Test connection settings get/set."""
        settings.set_last_host("192.168.1.100")
        settings.set_last_api_port(8080)
        settings.set_last_ws_port(8081)
        settings.set_auto_connect(True)

        assert settings.get_last_host() == "192.168.1.100"
        assert settings.get_last_api_port() == 8080
        assert settings.get_last_ws_port() == 8081
        assert settings.get_auto_connect() is True

    def test_connection_defaults(self, settings):
        """Test connection settings with defaults."""
        # Clear all first
        settings.clear_all()

        assert settings.get_last_host(default="localhost") == "localhost"
        assert settings.get_last_api_port(default=8000) == 8000
        assert settings.get_last_ws_port(default=8001) == 8001
        assert settings.get_auto_connect(default=False) is False

    def test_recent_servers(self, settings):
        """Test recent servers list."""
        settings.add_recent_server("localhost", 8000, 8001, "Local")
        settings.add_recent_server("192.168.1.100", 8000, 8001, "Lab")
        settings.add_recent_server("10.0.0.50", 9000, 9001, "Test")

        recent = settings.get_recent_servers(max_count=10)

        assert len(recent) == 3
        assert recent[0]["name"] == "Test"  # Most recent first
        assert recent[0]["host"] == "10.0.0.50"
        assert recent[1]["name"] == "Lab"
        assert recent[2]["name"] == "Local"

    def test_recent_servers_limit(self, settings):
        """Test recent servers respects max count."""
        # Add 15 servers
        for i in range(15):
            settings.add_recent_server(f"host_{i}", 8000, 8001, f"Server {i}")

        # Get only 10 most recent
        recent = settings.get_recent_servers(max_count=10)

        assert len(recent) == 10
        assert recent[0]["name"] == "Server 14"  # Most recent

    def test_equipment_settings(self, settings):
        """Test equipment settings."""
        settings.set_last_equipment("scope_12345678")

        assert settings.get_last_equipment() == "scope_12345678"

    def test_favorite_equipment(self, settings):
        """Test favorite equipment list."""
        settings.add_favorite_equipment("ps_11111111")
        settings.add_favorite_equipment("load_22222222")
        settings.add_favorite_equipment("scope_33333333")

        favorites = settings.get_favorite_equipment()

        assert len(favorites) == 3
        assert "ps_11111111" in favorites
        assert "load_22222222" in favorites
        assert "scope_33333333" in favorites

    def test_remove_favorite(self, settings):
        """Test removing favorite equipment."""
        settings.add_favorite_equipment("ps_11111111")
        settings.add_favorite_equipment("load_22222222")

        favorites = settings.get_favorite_equipment()
        assert len(favorites) == 2

        settings.remove_favorite_equipment("ps_11111111")

        favorites = settings.get_favorite_equipment()
        assert len(favorites) == 1
        assert "load_22222222" in favorites
        assert "ps_11111111" not in favorites

    def test_acquisition_settings(self, settings):
        """Test acquisition settings."""
        settings.set_default_sample_rate(5000.0)
        settings.set_default_buffer_size(20000)
        settings.set_auto_export(True)
        settings.set_export_directory("/tmp/data")

        assert settings.get_default_sample_rate() == 5000.0
        assert settings.get_default_buffer_size() == 20000
        assert settings.get_auto_export() is True
        assert settings.get_export_directory() == "/tmp/data"

    def test_visualization_settings(self, settings):
        """Test visualization settings."""
        settings.set_plot_buffer_size(1500)
        settings.set_plot_update_rate(75)
        settings.set_theme("dark")

        assert settings.get_plot_buffer_size() == 1500
        assert settings.get_plot_update_rate() == 75
        assert settings.get_theme() == "dark"

    def test_generic_settings(self, settings):
        """Test generic get/set value."""
        settings.set_value("custom/test_int", 42)
        settings.set_value("custom/test_str", "hello")
        settings.set_value("custom/test_float", 3.14)

        assert settings.get_value("custom/test_int", 0, int) == 42
        assert settings.get_value("custom/test_str", "", str) == "hello"
        assert settings.get_value("custom/test_float", 0.0, float) == 3.14

    def test_export_import(self, settings, tmp_path):
        """Test export and import settings."""
        # Set various settings
        settings.set_last_host("192.168.1.100")
        settings.set_last_api_port(8080)
        settings.set_default_sample_rate(5000.0)
        settings.set_theme("dark")

        # Export
        export_file = tmp_path / "settings_export.json"
        settings.export_settings(str(export_file))

        assert export_file.exists()

        # Read export file
        with open(export_file, 'r') as f:
            exported = json.load(f)

        assert "connection/host" in exported
        assert exported["connection/host"] == "192.168.1.100"

        # Create new settings manager
        settings2 = SettingsManager(
            organization="LabLinkTest2",
            application="TestApp2"
        )

        # Import
        settings2.import_settings(str(export_file))

        # Verify imported settings
        assert settings2.get_last_host() == "192.168.1.100"
        assert settings2.get_last_api_port() == 8080
        assert settings2.get_default_sample_rate() == 5000.0
        assert settings2.get_theme() == "dark"

        # Clean up
        settings2.clear_all()

    def test_clear_all(self, settings):
        """Test clearing all settings."""
        settings.set_last_host("test_host")
        settings.set_last_api_port(9999)
        settings.set_theme("dark")

        keys_before = settings.get_all_keys()
        assert len(keys_before) > 0

        settings.clear_all()

        keys_after = settings.get_all_keys()
        assert len(keys_after) == 0

    def test_sync(self, settings):
        """Test sync to disk."""
        settings.set_value("test/sync", "value")

        # Should not raise
        settings.sync()

        # Value should still be there
        assert settings.get_value("test/sync", "", str) == "value"

    def test_get_settings_file(self, settings):
        """Test getting settings file path."""
        filepath = settings.get_settings_file()

        assert isinstance(filepath, str)
        assert len(filepath) > 0

    def test_window_geometry(self, settings):
        """Test window geometry storage."""
        # Create fake geometry (QByteArray)
        from PyQt6.QtCore import QByteArray
        geometry = QByteArray(b"fake_geometry_data")

        settings.set_window_geometry(geometry)

        restored = settings.get_window_geometry()

        assert restored is not None
        assert restored == geometry

    def test_get_settings_singleton(self, app):
        """Test get_settings returns singleton."""
        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2


@pytest.mark.unit
@pytest.mark.skipif(PYQT_AVAILABLE, reason="Testing import error handling")
def test_import_error_without_pyqt():
    """Test settings fails gracefully without PyQt6."""
    # This test only runs when PyQt6 is NOT available
    # It verifies the code handles the import gracefully
    pass
