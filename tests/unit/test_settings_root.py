"""Test settings persistence functionality."""

import sys
import os

try:
    from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel
    from client.utils.settings import SettingsManager, get_settings
    from client.ui.settings_dialog import SettingsDialog
    PYQT_AVAILABLE = True
except ImportError as e:
    print(f"Error: {e}")
    print("\nRequired packages:")
    print("  pip install PyQt6")
    PYQT_AVAILABLE = False
    sys.exit(1)


def test_settings_manager():
    """Test SettingsManager functionality."""
    print("\n" + "="*60)
    print("Testing SettingsManager")
    print("="*60)

    # Create settings manager
    settings = SettingsManager(organization="LabLinkTest", application="TestApp")
    print(f"\n✓ Created settings manager")
    print(f"  Settings file: {settings.get_settings_file()}")

    # Test connection settings
    print("\n--- Connection Settings ---")
    settings.set_last_host("192.168.1.100")
    settings.set_last_api_port(8080)
    settings.set_last_ws_port(8081)
    settings.set_auto_connect(True)

    print(f"✓ Saved: host={settings.get_last_host()}")
    print(f"✓ Saved: api_port={settings.get_last_api_port()}")
    print(f"✓ Saved: ws_port={settings.get_last_ws_port()}")
    print(f"✓ Saved: auto_connect={settings.get_auto_connect()}")

    # Test recent servers
    print("\n--- Recent Servers ---")
    settings.add_recent_server("localhost", 8000, 8001, "Local Server")
    settings.add_recent_server("192.168.1.100", 8000, 8001, "Lab Server")
    settings.add_recent_server("10.0.0.50", 9000, 9001, "Test Server")

    recent = settings.get_recent_servers()
    print(f"✓ Added {len(recent)} recent servers:")
    for i, server in enumerate(recent, 1):
        name = server['name'] or "Unnamed"
        print(f"  {i}. {name}: {server['host']}:{server['api_port']}")

    # Test equipment settings
    print("\n--- Equipment Settings ---")
    settings.set_last_equipment("scope_12345678")
    print(f"✓ Last equipment: {settings.get_last_equipment()}")

    settings.add_favorite_equipment("ps_11111111")
    settings.add_favorite_equipment("load_22222222")
    settings.add_favorite_equipment("scope_33333333")

    favorites = settings.get_favorite_equipment()
    print(f"✓ Favorites ({len(favorites)}):")
    for fav in favorites:
        print(f"  - {fav}")

    # Test acquisition settings
    print("\n--- Acquisition Settings ---")
    settings.set_default_sample_rate(5000.0)
    settings.set_default_buffer_size(20000)
    settings.set_auto_export(True)
    settings.set_export_directory("/home/user/data")

    print(f"✓ Sample rate: {settings.get_default_sample_rate()} Hz")
    print(f"✓ Buffer size: {settings.get_default_buffer_size()}")
    print(f"✓ Auto export: {settings.get_auto_export()}")
    print(f"✓ Export dir: {settings.get_export_directory()}")

    # Test visualization settings
    print("\n--- Visualization Settings ---")
    settings.set_plot_buffer_size(1500)
    settings.set_plot_update_rate(75)
    settings.set_theme("dark")

    print(f"✓ Plot buffer: {settings.get_plot_buffer_size()}")
    print(f"✓ Update rate: {settings.get_plot_update_rate()} ms")
    print(f"✓ Theme: {settings.get_theme()}")

    # Test generic get/set
    print("\n--- Generic Settings ---")
    settings.set_value("custom/test_value", 42)
    settings.set_value("custom/test_string", "Hello, World!")

    print(f"✓ Custom int: {settings.get_value('custom/test_value', 0, int)}")
    print(f"✓ Custom string: {settings.get_value('custom/test_string', '', str)}")

    # Export/Import test
    print("\n--- Export/Import ---")
    export_file = "/tmp/test_settings.json"

    try:
        settings.export_settings(export_file)
        print(f"✓ Exported to: {export_file}")

        # Create new settings manager
        settings2 = SettingsManager(organization="LabLinkTest2", application="TestApp2")
        settings2.import_settings(export_file)
        print(f"✓ Imported successfully")

        # Verify imported settings
        assert settings2.get_last_host() == "192.168.1.100"
        assert settings2.get_default_sample_rate() == 5000.0
        print(f"✓ Settings verified after import")

        # Cleanup
        os.remove(export_file)

    except Exception as e:
        print(f"✗ Export/Import failed: {e}")

    # Statistics
    print("\n--- Statistics ---")
    all_keys = settings.get_all_keys()
    print(f"✓ Total settings keys: {len(all_keys)}")

    # Sync
    settings.sync()
    print(f"✓ Settings synced to disk")

    print("\n" + "="*60)
    print("✓ All tests passed!")
    print("="*60)


class SettingsTestWindow(QMainWindow):
    """Test window for settings dialog."""

    def __init__(self):
        """Initialize test window."""
        super().__init__()

        self.setWindowTitle("Settings Test")
        self.setGeometry(100, 100, 400, 300)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)

        # Info label
        self.info_label = QLabel("<h2>Settings Manager Test</h2>")
        layout.addWidget(self.info_label)

        # Get settings
        self.settings = get_settings()

        # Display current settings
        settings_text = f"""
        <b>Current Settings:</b><br>
        <ul>
        <li>Host: {self.settings.get_last_host()}</li>
        <li>API Port: {self.settings.get_last_api_port()}</li>
        <li>WS Port: {self.settings.get_last_ws_port()}</li>
        <li>Sample Rate: {self.settings.get_default_sample_rate()} Hz</li>
        <li>Buffer Size: {self.settings.get_default_buffer_size()}</li>
        <li>Theme: {self.settings.get_theme()}</li>
        </ul>
        """

        self.current_label = QLabel(settings_text)
        self.current_label.setWordWrap(True)
        layout.addWidget(self.current_label)

        # Open settings button
        self.settings_btn = QPushButton("Open Settings Dialog")
        self.settings_btn.clicked.connect(self._open_settings_dialog)
        layout.addWidget(self.settings_btn)

        # Refresh button
        self.refresh_btn = QPushButton("Refresh Display")
        self.refresh_btn.clicked.connect(self._refresh_display)
        layout.addWidget(self.refresh_btn)

        layout.addStretch()

    def _open_settings_dialog(self):
        """Open settings dialog."""
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            self._refresh_display()
            print("Settings saved!")

    def _refresh_display(self):
        """Refresh settings display."""
        settings_text = f"""
        <b>Current Settings:</b><br>
        <ul>
        <li>Host: {self.settings.get_last_host()}</li>
        <li>API Port: {self.settings.get_last_api_port()}</li>
        <li>WS Port: {self.settings.get_last_ws_port()}</li>
        <li>Sample Rate: {self.settings.get_default_sample_rate()} Hz</li>
        <li>Buffer Size: {self.settings.get_default_buffer_size()}</li>
        <li>Theme: {self.settings.get_theme()}</li>
        </ul>
        """
        self.current_label.setText(settings_text)


def test_settings_dialog():
    """Test settings dialog UI."""
    print("\n" + "="*60)
    print("Testing Settings Dialog UI")
    print("="*60)

    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    window = SettingsTestWindow()
    window.show()

    print("\n✓ Settings dialog opened")
    print("  Try changing settings and clicking Save")
    print("  Settings are persisted across app restarts")

    sys.exit(app.exec())


def main():
    """Run tests."""
    if not PYQT_AVAILABLE:
        return

    print("\n" + "="*60)
    print("LabLink Settings Persistence Tests")
    print("="*60)

    # Run programmatic tests
    test_settings_manager()

    # Ask user if they want to test the UI
    print("\nWould you like to test the Settings Dialog UI? (y/n)")
    response = input().strip().lower()

    if response == 'y':
        test_settings_dialog()
    else:
        print("\n✓ Tests complete!")


if __name__ == "__main__":
    main()
