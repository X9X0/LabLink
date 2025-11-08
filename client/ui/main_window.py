"""Main window for LabLink GUI client."""

import logging
from typing import Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QMenuBar, QMenu, QStatusBar, QMessageBox,
    QDockWidget, QLabel, QPushButton
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction

from api.client import LabLinkClient
from ui.connection_dialog import ConnectionDialog
from ui.equipment_panel import EquipmentPanel
from ui.acquisition_panel import AcquisitionPanel
from ui.alarm_panel import AlarmPanel
from ui.scheduler_panel import SchedulerPanel
from ui.diagnostics_panel import DiagnosticsPanel

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window."""

    # Signals
    connection_changed = pyqtSignal(bool)  # True if connected, False if disconnected

    def __init__(self):
        """Initialize main window."""
        super().__init__()

        self.client: Optional[LabLinkClient] = None
        self.connection_dialog: Optional[ConnectionDialog] = None

        self._setup_ui()
        self._setup_menus()
        self._setup_status_bar()
        self._setup_timers()

        self.setWindowTitle("LabLink - Laboratory Equipment Control")
        self.resize(1400, 900)

    def _setup_ui(self):
        """Set up user interface."""
        # Central widget with tab layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Tab widget for main panels
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Equipment control panel
        self.equipment_panel = EquipmentPanel()
        self.tab_widget.addTab(self.equipment_panel, "Equipment")

        # Data acquisition panel
        self.acquisition_panel = AcquisitionPanel()
        self.tab_widget.addTab(self.acquisition_panel, "Data Acquisition")

        # Alarm monitoring panel
        self.alarm_panel = AlarmPanel()
        self.tab_widget.addTab(self.alarm_panel, "Alarms")

        # Scheduler panel
        self.scheduler_panel = SchedulerPanel()
        self.tab_widget.addTab(self.scheduler_panel, "Scheduler")

        # Diagnostics panel
        self.diagnostics_panel = DiagnosticsPanel()
        self.tab_widget.addTab(self.diagnostics_panel, "Diagnostics")

        # Connect signals
        self.connection_changed.connect(self._on_connection_changed)

    def _setup_menus(self):
        """Set up menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        connect_action = QAction("&Connect to Server...", self)
        connect_action.setShortcut("Ctrl+N")
        connect_action.triggered.connect(self.show_connection_dialog)
        file_menu.addAction(connect_action)

        disconnect_action = QAction("&Disconnect", self)
        disconnect_action.triggered.connect(self.disconnect_from_server)
        file_menu.addAction(disconnect_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        refresh_action = QAction("&Refresh", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.refresh_all)
        view_menu.addAction(refresh_action)

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")

        diagnostics_action = QAction("Run &Diagnostics", self)
        diagnostics_action.triggered.connect(self.run_diagnostics)
        tools_menu.addAction(diagnostics_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def _setup_status_bar(self):
        """Set up status bar."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Connection status label
        self.connection_label = QLabel("Not Connected")
        self.status_bar.addPermanentWidget(self.connection_label)

        # Server info label
        self.server_info_label = QLabel("")
        self.status_bar.addPermanentWidget(self.server_info_label)

    def _setup_timers(self):
        """Set up periodic update timers."""
        # Periodic refresh timer (every 5 seconds when connected)
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.periodic_refresh)
        self.refresh_timer.setInterval(5000)  # 5 seconds

    # ==================== Connection Management ====================

    def show_connection_dialog(self):
        """Show connection dialog."""
        if self.connection_dialog is None:
            self.connection_dialog = ConnectionDialog(self)

        if self.connection_dialog.exec():
            host = self.connection_dialog.get_host()
            api_port = self.connection_dialog.get_api_port()
            ws_port = self.connection_dialog.get_ws_port()

            self.connect_to_server(host, api_port, ws_port)

    def connect_to_server(self, host: str, api_port: int, ws_port: int):
        """Connect to LabLink server.

        Args:
            host: Server hostname or IP
            api_port: REST API port
            ws_port: WebSocket port
        """
        try:
            self.client = LabLinkClient(host, api_port, ws_port)

            if self.client.connect():
                # Get server info
                server_info = self.client.get_server_info()

                self.status_bar.showMessage(
                    f"Connected to {server_info.get('name', 'LabLink')} "
                    f"v{server_info.get('version', 'unknown')}", 3000
                )

                self.connection_label.setText(f"Connected: {host}:{api_port}")
                self.server_info_label.setText(
                    f"{server_info.get('name', 'LabLink')} v{server_info.get('version', '')}"
                )

                # Set client for all panels
                self.equipment_panel.set_client(self.client)
                self.acquisition_panel.set_client(self.client)
                self.alarm_panel.set_client(self.client)
                self.scheduler_panel.set_client(self.client)
                self.diagnostics_panel.set_client(self.client)

                # Emit signal
                self.connection_changed.emit(True)

                # Start periodic refresh
                self.refresh_timer.start()

                # Initial data load
                self.refresh_all()

            else:
                QMessageBox.warning(
                    self, "Connection Failed",
                    f"Could not connect to server at {host}:{api_port}"
                )

        except Exception as e:
            logger.error(f"Connection error: {e}")
            QMessageBox.critical(
                self, "Connection Error",
                f"Error connecting to server: {str(e)}"
            )

    def disconnect_from_server(self):
        """Disconnect from server."""
        if self.client:
            self.client.disconnect()
            self.client = None

        self.connection_label.setText("Not Connected")
        self.server_info_label.setText("")
        self.status_bar.showMessage("Disconnected", 3000)

        # Stop periodic refresh
        self.refresh_timer.stop()

        # Emit signal
        self.connection_changed.emit(False)

    def _on_connection_changed(self, connected: bool):
        """Handle connection state change.

        Args:
            connected: True if connected, False if disconnected
        """
        # Update UI state based on connection
        logger.info(f"Connection state changed: {'connected' if connected else 'disconnected'}")

    # ==================== Data Refresh ====================

    def refresh_all(self):
        """Refresh all panels."""
        if not self.client or not self.client.connected:
            return

        try:
            # Refresh each panel
            self.equipment_panel.refresh()
            self.acquisition_panel.refresh()
            self.alarm_panel.refresh()
            self.scheduler_panel.refresh()
            self.diagnostics_panel.refresh()

        except Exception as e:
            logger.error(f"Error refreshing data: {e}")

    def periodic_refresh(self):
        """Periodic refresh of data."""
        # Only refresh the currently visible tab
        current_widget = self.tab_widget.currentWidget()

        try:
            if hasattr(current_widget, 'refresh'):
                current_widget.refresh()
        except Exception as e:
            logger.error(f"Error in periodic refresh: {e}")

    # ==================== Actions ====================

    def run_diagnostics(self):
        """Run diagnostics on all equipment."""
        if not self.client or not self.client.connected:
            QMessageBox.warning(self, "Not Connected", "Please connect to a server first")
            return

        # Switch to diagnostics tab
        self.tab_widget.setCurrentWidget(self.diagnostics_panel)

        # Trigger diagnostics
        self.diagnostics_panel.run_full_diagnostics()

    def show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About LabLink",
            "<h2>LabLink v0.10.0</h2>"
            "<p>Laboratory Equipment Control and Data Acquisition System</p>"
            "<p>A modular client-server application for remote control and data "
            "acquisition from laboratory equipment.</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>Equipment control and monitoring</li>"
            "<li>Real-time data acquisition and visualization</li>"
            "<li>Alarm and notification system</li>"
            "<li>Job scheduling and automation</li>"
            "<li>Equipment diagnostics and health monitoring</li>"
            "</ul>"
            "<p>© 2024 LabLink Project</p>"
        )

    def closeEvent(self, event):
        """Handle window close event."""
        if self.client and self.client.connected:
            reply = QMessageBox.question(
                self, "Confirm Exit",
                "Are you sure you want to exit? Active connections will be closed.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.disconnect_from_server()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
