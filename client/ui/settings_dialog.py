"""Settings dialog for LabLink client."""

import logging
from typing import Optional

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog,
                                 QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                                 QLineEdit, QMessageBox, QPushButton, QSpinBox,
                                 QTabWidget, QVBoxLayout, QWidget)

    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from client.utils.settings import SettingsManager

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """Settings configuration dialog."""

    def __init__(self, settings_manager: SettingsManager, parent=None):
        """Initialize settings dialog.

        Args:
            settings_manager: Settings manager instance
            parent: Parent widget
        """
        if not PYQT_AVAILABLE:
            raise ImportError("PyQt6 is required for settings dialog")

        super().__init__(parent)

        self.settings = settings_manager

        self.setWindowTitle("LabLink Settings")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        """Set up user interface."""
        layout = QVBoxLayout(self)

        # Tabs for different setting categories
        self.tabs = QTabWidget()

        self.tabs.addTab(self._create_connection_tab(), "Connection")
        self.tabs.addTab(self._create_acquisition_tab(), "Acquisition")
        self.tabs.addTab(self._create_visualization_tab(), "Visualization")
        self.tabs.addTab(self._create_advanced_tab(), "Advanced")

        layout.addWidget(self.tabs)

        # Buttons
        button_layout = QHBoxLayout()

        self.import_btn = QPushButton("Import...")
        self.import_btn.clicked.connect(self._on_import_clicked)
        button_layout.addWidget(self.import_btn)

        self.export_btn = QPushButton("Export...")
        self.export_btn.clicked.connect(self._on_export_clicked)
        button_layout.addWidget(self.export_btn)

        button_layout.addStretch()

        self.reset_btn = QPushButton("Reset to Defaults")
        self.reset_btn.clicked.connect(self._on_reset_clicked)
        button_layout.addWidget(self.reset_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self._on_save_clicked)
        self.save_btn.setDefault(True)
        button_layout.addWidget(self.save_btn)

        layout.addLayout(button_layout)

    def _create_connection_tab(self) -> QWidget:
        """Create connection settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Default server settings
        server_group = QGroupBox("Default Server")
        server_layout = QFormLayout()

        self.host_edit = QLineEdit()
        server_layout.addRow("Host:", self.host_edit)

        self.api_port_spin = QSpinBox()
        self.api_port_spin.setRange(1, 65535)
        server_layout.addRow("API Port:", self.api_port_spin)

        self.ws_port_spin = QSpinBox()
        self.ws_port_spin.setRange(1, 65535)
        server_layout.addRow("WebSocket Port:", self.ws_port_spin)

        self.auto_connect_check = QCheckBox("Auto-connect on startup")
        server_layout.addRow("", self.auto_connect_check)

        server_group.setLayout(server_layout)
        layout.addWidget(server_group)

        # Recent servers info
        recent_group = QGroupBox("Recent Servers")
        recent_layout = QVBoxLayout()

        recent_count = len(self.settings.get_recent_servers())
        recent_label = QLabel(f"{recent_count} recent server(s) saved")
        recent_layout.addWidget(recent_label)

        clear_recent_btn = QPushButton("Clear Recent Servers")
        clear_recent_btn.clicked.connect(self._on_clear_recent_clicked)
        recent_layout.addWidget(clear_recent_btn)

        recent_group.setLayout(recent_layout)
        layout.addWidget(recent_group)

        layout.addStretch()

        return widget

    def _create_acquisition_tab(self) -> QWidget:
        """Create acquisition settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Default acquisition settings
        acq_group = QGroupBox("Default Acquisition Settings")
        acq_layout = QFormLayout()

        self.sample_rate_spin = QSpinBox()
        self.sample_rate_spin.setRange(1, 1000000)
        self.sample_rate_spin.setSuffix(" Hz")
        acq_layout.addRow("Sample Rate:", self.sample_rate_spin)

        self.buffer_size_spin = QSpinBox()
        self.buffer_size_spin.setRange(100, 1000000)
        acq_layout.addRow("Buffer Size:", self.buffer_size_spin)

        self.auto_export_check = QCheckBox("Auto-export on completion")
        acq_layout.addRow("Export:", self.auto_export_check)

        acq_group.setLayout(acq_layout)
        layout.addWidget(acq_group)

        # Export settings
        export_group = QGroupBox("Export Settings")
        export_layout = QVBoxLayout()

        dir_layout = QHBoxLayout()
        self.export_dir_edit = QLineEdit()
        dir_layout.addWidget(self.export_dir_edit)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse_export_dir)
        dir_layout.addWidget(browse_btn)

        export_layout.addLayout(dir_layout)

        export_group.setLayout(export_layout)
        layout.addWidget(export_group)

        layout.addStretch()

        return widget

    def _create_visualization_tab(self) -> QWidget:
        """Create visualization settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Plot settings
        plot_group = QGroupBox("Plot Settings")
        plot_layout = QFormLayout()

        self.plot_buffer_spin = QSpinBox()
        self.plot_buffer_spin.setRange(100, 10000)
        plot_layout.addRow("Buffer Size:", self.plot_buffer_spin)

        self.plot_update_spin = QSpinBox()
        self.plot_update_spin.setRange(10, 1000)
        self.plot_update_spin.setSuffix(" ms")
        plot_layout.addRow("Update Rate:", self.plot_update_spin)

        plot_group.setLayout(plot_layout)
        layout.addWidget(plot_group)

        # Theme settings
        theme_group = QGroupBox("Appearance")
        theme_layout = QFormLayout()

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark", "System"])
        theme_layout.addRow("Theme:", self.theme_combo)

        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)

        layout.addStretch()

        return widget

    def _create_advanced_tab(self) -> QWidget:
        """Create advanced settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Settings file info
        info_group = QGroupBox("Settings Information")
        info_layout = QVBoxLayout()

        settings_file = self.settings.get_settings_file()
        file_label = QLabel(f"<b>Settings File:</b><br>{settings_file}")
        file_label.setWordWrap(True)
        info_layout.addWidget(file_label)

        key_count = len(self.settings.get_all_keys())
        count_label = QLabel(f"<b>Stored Keys:</b> {key_count}")
        info_layout.addWidget(count_label)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # Actions
        actions_group = QGroupBox("Actions")
        actions_layout = QVBoxLayout()

        sync_btn = QPushButton("Sync Settings to Disk")
        sync_btn.clicked.connect(self._on_sync_clicked)
        actions_layout.addWidget(sync_btn)

        clear_btn = QPushButton("Clear All Settings")
        clear_btn.clicked.connect(self._on_clear_all_clicked)
        actions_layout.addWidget(clear_btn)

        actions_group.setLayout(actions_layout)
        layout.addWidget(actions_group)

        layout.addStretch()

        return widget

    def _load_settings(self):
        """Load current settings into UI."""
        # Connection
        self.host_edit.setText(self.settings.get_last_host())
        self.api_port_spin.setValue(self.settings.get_last_api_port())
        self.ws_port_spin.setValue(self.settings.get_last_ws_port())
        self.auto_connect_check.setChecked(self.settings.get_auto_connect())

        # Acquisition
        self.sample_rate_spin.setValue(int(self.settings.get_default_sample_rate()))
        self.buffer_size_spin.setValue(self.settings.get_default_buffer_size())
        self.auto_export_check.setChecked(self.settings.get_auto_export())
        self.export_dir_edit.setText(self.settings.get_export_directory())

        # Visualization
        self.plot_buffer_spin.setValue(self.settings.get_plot_buffer_size())
        self.plot_update_spin.setValue(self.settings.get_plot_update_rate())

        theme = self.settings.get_theme()
        if theme == "light":
            self.theme_combo.setCurrentIndex(0)
        elif theme == "dark":
            self.theme_combo.setCurrentIndex(1)
        else:
            self.theme_combo.setCurrentIndex(2)

    def _save_settings(self):
        """Save UI values to settings."""
        # Connection
        self.settings.set_last_host(self.host_edit.text())
        self.settings.set_last_api_port(self.api_port_spin.value())
        self.settings.set_last_ws_port(self.ws_port_spin.value())
        self.settings.set_auto_connect(self.auto_connect_check.isChecked())

        # Acquisition
        self.settings.set_default_sample_rate(float(self.sample_rate_spin.value()))
        self.settings.set_default_buffer_size(self.buffer_size_spin.value())
        self.settings.set_auto_export(self.auto_export_check.isChecked())
        self.settings.set_export_directory(self.export_dir_edit.text())

        # Visualization
        self.settings.set_plot_buffer_size(self.plot_buffer_spin.value())
        self.settings.set_plot_update_rate(self.plot_update_spin.value())

        theme_idx = self.theme_combo.currentIndex()
        if theme_idx == 0:
            self.settings.set_theme("light")
        elif theme_idx == 1:
            self.settings.set_theme("dark")
        else:
            self.settings.set_theme("system")

        # Sync to disk
        self.settings.sync()

        logger.info("Settings saved")

    def _on_save_clicked(self):
        """Handle save button click."""
        self._save_settings()
        self.accept()

    def _on_reset_clicked(self):
        """Handle reset button click."""
        reply = QMessageBox.question(
            self,
            "Reset Settings",
            "Reset all settings to defaults?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.settings.clear_all()
            self._load_settings()
            QMessageBox.information(
                self, "Reset Complete", "Settings reset to defaults."
            )

    def _on_clear_recent_clicked(self):
        """Handle clear recent servers button."""
        self.settings.settings.beginWriteArray("connection/recent_servers", 0)
        self.settings.settings.endArray()
        QMessageBox.information(self, "Cleared", "Recent servers list cleared.")

    def _on_browse_export_dir(self):
        """Handle browse export directory button."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Export Directory", self.export_dir_edit.text()
        )

        if directory:
            self.export_dir_edit.setText(directory)

    def _on_import_clicked(self):
        """Handle import button click."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import Settings", "", "JSON Files (*.json);;All Files (*)"
        )

        if filepath:
            try:
                self.settings.import_settings(filepath)
                self._load_settings()
                QMessageBox.information(
                    self, "Success", "Settings imported successfully."
                )
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to import settings:\n{e}")

    def _on_export_clicked(self):
        """Handle export button click."""
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Export Settings",
            "lablink_settings.json",
            "JSON Files (*.json);;All Files (*)",
        )

        if filepath:
            try:
                self.settings.export_settings(filepath)
                QMessageBox.information(
                    self, "Success", f"Settings exported to:\n{filepath}"
                )
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export settings:\n{e}")

    def _on_sync_clicked(self):
        """Handle sync button click."""
        self.settings.sync()
        QMessageBox.information(self, "Synced", "Settings synchronized to disk.")

    def _on_clear_all_clicked(self):
        """Handle clear all button click."""
        reply = QMessageBox.warning(
            self,
            "Clear All Settings",
            "This will permanently delete ALL settings!\n\nAre you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.settings.clear_all()
            self._load_settings()
            QMessageBox.information(self, "Cleared", "All settings have been cleared.")
