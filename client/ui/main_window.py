"""Main window for LabLink GUI client."""

import asyncio
import logging
from typing import Optional

import qasync
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (QDockWidget, QHBoxLayout, QLabel, QMainWindow,
                             QMenu, QMenuBar, QMessageBox, QPushButton,
                             QStatusBar, QTabWidget, QVBoxLayout, QWidget)

from client.api.client import LabLinkClient
from client.ui.acquisition_panel import AcquisitionPanel
from client.ui.alarm_panel import AlarmPanel
from client.ui.connection_dialog import ConnectionDialog
from client.ui.control_panel import ControlPanel
from client.ui.diagnostics_panel import DiagnosticsPanel
from client.ui.equipment_panel import EquipmentPanel
from client.ui.login_dialog import LoginDialog
from client.ui.pi_discovery_panel import PiDiscoveryDialog
from client.ui.system_panel import SystemPanel
from client.ui.pi_image_builder import PiImageBuilderWizard
from client.ui.scheduler_panel import SchedulerPanel
from client.ui.sd_card_writer import SDCardWriter
from client.ui.server_selector import ServerSelector
from client.ui.ssh_deploy_wizard import SSHDeployWizard
from client.ui.sync_panel import SyncPanel
from client.ui.test_sequence_panel import TestSequencePanel
from client.utils.server_manager import get_server_manager
from client.utils.token_storage import get_token_storage

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
        self.login_dialog: Optional[LoginDialog] = None
        self.ws_connected = False
        self.token_storage = get_token_storage()
        self.server_manager = get_server_manager()

        # Apply visual styling - window border and background
        self.setStyleSheet("""
            QMainWindow {
                border: 6px solid #0d1419;
                background-color: #ecf0f1;
            }
        """)

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

        # Set central widget background
        central_widget.setStyleSheet("QWidget { background-color: #ecf0f1; }")

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Server selector toolbar
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(5, 5, 5, 5)

        self.server_selector = ServerSelector()
        self.server_selector.connect_requested.connect(
            self._on_server_connect_requested
        )
        self.server_selector.server_changed.connect(self._on_server_changed)
        toolbar_layout.addWidget(self.server_selector)

        toolbar_layout.addStretch()

        layout.addLayout(toolbar_layout)

        # Tab widget for main panels
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Equipment control panel
        self.equipment_panel = EquipmentPanel()
        self.tab_widget.addTab(self.equipment_panel, "Equipment")

        # Control panel for equipment control and visualization
        self.control_panel = ControlPanel()
        self.tab_widget.addTab(self.control_panel, "Control")

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

        # Synchronization panel
        self.sync_panel = SyncPanel()
        self.tab_widget.addTab(self.sync_panel, "Synchronization")

        # Test Sequence panel
        self.test_sequence_panel = TestSequencePanel()
        self.tab_widget.addTab(self.test_sequence_panel, "Test Sequences")

        # System Management panel
        self.system_panel = SystemPanel()
        self.tab_widget.addTab(self.system_panel, "System")

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

        logout_action = QAction("&Logout", self)
        logout_action.triggered.connect(self.logout)
        file_menu.addAction(logout_action)

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

        discover_pi_action = QAction("Discover Raspberry &Pis...", self)
        discover_pi_action.triggered.connect(self.show_pi_discovery)
        tools_menu.addAction(discover_pi_action)

        tools_menu.addSeparator()

        deploy_action = QAction("Deploy Server via &SSH...", self)
        deploy_action.triggered.connect(self.show_deploy_wizard)
        tools_menu.addAction(deploy_action)

        build_image_action = QAction("&Build Raspberry Pi Image...", self)
        build_image_action.triggered.connect(self.show_pi_image_builder)
        tools_menu.addAction(build_image_action)

        write_sd_action = QAction("Write &Raspberry Pi Image to SD Card...", self)
        write_sd_action.triggered.connect(self.show_sd_card_writer)
        tools_menu.addAction(write_sd_action)

        tools_menu.addSeparator()

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

        # Git branch indicator (debug mode only)
        branch_info = self._get_git_branch()
        if branch_info and not branch_info.startswith("main"):
            self.branch_label = QLabel(f"📍 {branch_info}")
            self.branch_label.setStyleSheet("color: #27ae60; font-weight: bold;")
            self.status_bar.addWidget(self.branch_label)

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

    def _get_git_branch(self) -> Optional[str]:
        """Get current git branch name and commit hash for debug indicator.

        Returns:
            Branch name with commit hash or None if not in a git repo
        """
        try:
            import subprocess
            from pathlib import Path

            # Get the client directory (where this file is)
            client_dir = Path(__file__).parent.parent.parent

            # Get branch name
            branch_result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=client_dir,
                capture_output=True,
                text=True,
                timeout=1
            )

            if branch_result.returncode == 0:
                branch_name = branch_result.stdout.strip()

                # Get short commit hash
                hash_result = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=client_dir,
                    capture_output=True,
                    text=True,
                    timeout=1
                )

                if hash_result.returncode == 0:
                    commit_hash = hash_result.stdout.strip()
                    return f"{branch_name} ({commit_hash})"

                return branch_name
        except Exception:
            pass

        return None

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

    def show_pi_discovery(self):
        """Show Pi Discovery dialog."""
        dialog = PiDiscoveryDialog(self)
        dialog.exec()

    def show_deploy_wizard(self):
        """Show SSH deployment wizard."""
        try:
            wizard = SSHDeployWizard(self)
            wizard.exec()
        except ImportError as e:
            QMessageBox.warning(
                self,
                "Missing Dependencies",
                f"SSH deployment requires additional packages:\n{e}\n\n"
                "Please install: pip install paramiko scp",
            )

    def show_pi_image_builder(self):
        """Show Raspberry Pi image builder wizard."""
        wizard = PiImageBuilderWizard(self)
        wizard.exec()

    def show_sd_card_writer(self):
        """Show SD card writer tool."""
        writer = SDCardWriter(self)
        writer.exec()

    def _on_server_connect_requested(self, server_name: str):
        """Handle server connect request from server selector.

        Args:
            server_name: Name of server to connect to
        """
        server = self.server_manager.get_server(server_name)
        if not server:
            return

        if server.connected:
            # Disconnect
            self.disconnect_from_server()
            self.server_manager.mark_disconnected(server_name)
            self.server_selector.refresh()
        else:
            # Connect
            self.connect_to_server(server.host, server.api_port, server.ws_port)

            if self.client and self.client.connected:
                # Mark as connected
                username = (
                    self.client.username if hasattr(self.client, "username") else None
                )
                self.server_manager.mark_connected(server_name, self.client, username)
                self.server_manager.set_active_server(server_name)
                self.server_selector.refresh()

    def _on_server_changed(self, server_name: str):
        """Handle server selection change.

        Args:
            server_name: Name of selected server
        """
        server = self.server_manager.get_server(server_name)
        if server and server.connected:
            # Update status bar
            self.connection_label.setText(
                f"Connected to: {server.name} ({server.host})"
            )

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
                    f"v{server_info.get('version', 'unknown')}",
                    3000,
                )

                self.connection_label.setText(f"Connected: {host}:{api_port}")
                self.server_info_label.setText(
                    f"{server_info.get('name', 'LabLink')} v{server_info.get('version', '')}"
                )

                # Check if server has security enabled
                security_enabled = server_info.get('security_enabled', True)

                if not security_enabled:
                    # Server has no authentication - skip login
                    logger.info("Server authentication disabled, connecting without login")
                    self.client.authenticated = True
                    self.client.user_data = {"username": "anonymous", "roles": []}
                    self._complete_connection()
                    return

                # Try to restore session from stored tokens
                if self.token_storage.has_tokens():
                    access_token, refresh_token = self.token_storage.load_tokens()
                    self.client.access_token = access_token
                    self.client.refresh_token = refresh_token
                    self.client._update_auth_header()

                    # Try to refresh token to verify it's still valid
                    if self.client.refresh_access_token():
                        self.client.authenticated = True
                        user_data = self.token_storage.load_user_data()
                        self.client.user_data = user_data
                        logger.info("Session restored from stored tokens")
                        self._complete_connection()
                        return
                    else:
                        # Token refresh failed, clear and require login
                        logger.info("Stored tokens invalid, requiring login")
                        self.token_storage.clear_all()

                # Show login dialog
                if self.login_dialog is None:
                    self.login_dialog = LoginDialog(self.client, self)
                else:
                    # Update client reference in case we're reconnecting with a new client instance
                    self.login_dialog.api_client = self.client

                if self.login_dialog.exec():
                    # Login successful
                    user_data = self.login_dialog.get_user_data()

                    # Save tokens if login successful
                    if self.client.access_token and self.client.refresh_token:
                        self.token_storage.save_tokens(
                            self.client.access_token, self.client.refresh_token
                        )
                        self.token_storage.save_user_data(user_data)

                    self._complete_connection()
                else:
                    # Login cancelled, disconnect
                    self.status_bar.showMessage("Login cancelled", 3000)
                    self.connection_label.setText("Not Connected")
                    self.client = None

            else:
                QMessageBox.warning(
                    self,
                    "Connection Failed",
                    f"Could not connect to server at {host}:{api_port}",
                )

        except Exception as e:
            logger.error(f"Connection error: {e}")
            QMessageBox.critical(
                self, "Connection Error", f"Error connecting to server: {str(e)}"
            )

    def _complete_connection(self):
        """Complete connection setup after authentication."""
        if not self.client:
            logger.error("Cannot complete connection: no client")
            return

        # Only check authentication if we have it set
        # (security might be disabled on server)
        if not self.client.authenticated:
            logger.error("Cannot complete connection: not authenticated")
            return

        # Set client for all panels
        self.equipment_panel.set_client(self.client)
        self.control_panel.set_client(self.client)
        self.acquisition_panel.set_client(self.client)
        self.alarm_panel.set_client(self.client)
        self.scheduler_panel.set_client(self.client)
        self.diagnostics_panel.set_client(self.client)
        self.sync_panel.set_client(self.client)
        self.test_sequence_panel.set_client(self.client)
        self.system_panel.set_client(self.client)

        # Emit signal
        self.connection_changed.emit(True)

        # Start periodic refresh
        self.refresh_timer.start()

        # Initial data load
        self.refresh_all()

        # Attempt WebSocket connection (optional, non-blocking)
        # Schedule async task using asyncio's event loop (qasync provides it)
        try:
            loop = asyncio.get_event_loop()
            asyncio.ensure_future(self._connect_websocket(), loop=loop)
        except Exception as e:
            logger.error(f"Connection error: {e}")

        # Update UI with user info
        if self.client.user_data:
            username = self.client.user_data.get("username", "User")
            self.status_bar.showMessage(f"Logged in as {username}", 5000)

    @qasync.asyncSlot()
    async def _connect_websocket(self):
        """Connect WebSocket in background (async).

        This method is called after REST API connection succeeds.
        WebSocket connection is optional - REST API will continue to work if it fails.
        """
        if not self.client or not self.client.ws_manager:
            logger.warning(
                "Cannot connect WebSocket: client or ws_manager not available"
            )
            return

        try:
            logger.info("Attempting WebSocket connection...")
            success = await self.client.connect_websocket()

            if success:
                self.ws_connected = True
                self.status_bar.showMessage(
                    "WebSocket connected - real-time updates enabled", 3000
                )
                logger.info("WebSocket connected successfully")
            else:
                self.ws_connected = False
                logger.warning("WebSocket connection failed - using polling fallback")
                self.status_bar.showMessage(
                    "WebSocket unavailable - using polling mode", 3000
                )

        except Exception as e:
            self.ws_connected = False
            logger.error(f"WebSocket connection error: {e}")
            # Don't show error to user - WebSocket is optional

    def disconnect_from_server(self):
        """Disconnect from server."""
        if self.client:
            # Schedule async disconnect properly
            asyncio.create_task(self.client.disconnect())
            self.client = None

        # Reset connection states
        self.ws_connected = False
        self.connection_label.setText("Not Connected")
        self.server_info_label.setText("")
        self.status_bar.showMessage("Disconnected", 3000)

        # Stop periodic refresh
        self.refresh_timer.stop()

        # Emit signal
        self.connection_changed.emit(False)

    def logout(self):
        """Logout and clear authentication."""
        if self.client and self.client.is_authenticated():
            # Call logout API
            self.client.logout()

            # Clear stored tokens
            self.token_storage.clear_all()

            self.status_bar.showMessage("Logged out successfully", 3000)

            # Show login dialog again to re-authenticate
            if self.client and self.client.connected:
                # Still connected to server, just need to re-authenticate
                self.login_dialog = LoginDialog(self.client, self)

                if self.login_dialog.exec():
                    # Login successful
                    user_data = self.login_dialog.get_user_data()

                    # Save tokens
                    if self.client.access_token and self.client.refresh_token:
                        self.token_storage.save_tokens(
                            self.client.access_token, self.client.refresh_token
                        )
                        self.token_storage.save_user_data(user_data)

                    self.status_bar.showMessage(
                        f"Re-authenticated as {user_data.get('username', 'User')}", 3000
                    )
                else:
                    # Login cancelled, disconnect fully
                    self.disconnect_from_server()
        else:
            self.status_bar.showMessage("Not logged in", 3000)

    def _on_connection_changed(self, connected: bool):
        """Handle connection state change.

        Args:
            connected: True if connected, False if disconnected
        """
        # Update UI state based on connection
        logger.info(
            f"Connection state changed: {'connected' if connected else 'disconnected'}"
        )

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
            self.sync_panel.refresh()

        except Exception as e:
            logger.error(f"Error refreshing data: {e}")

    def periodic_refresh(self):
        """Periodic refresh of data."""
        # Only refresh the currently visible tab
        current_widget = self.tab_widget.currentWidget()

        try:
            if hasattr(current_widget, "refresh"):
                current_widget.refresh()
        except Exception as e:
            logger.error(f"Error in periodic refresh: {e}")

    # ==================== Actions ====================

    def run_diagnostics(self):
        """Run diagnostics on all equipment."""
        if not self.client or not self.client.connected:
            QMessageBox.warning(
                self, "Not Connected", "Please connect to a server first"
            )
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
            "<p>© 2024 LabLink Project</p>",
        )

    def closeEvent(self, event):
        """Handle window close event."""
        if self.client and self.client.connected:
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "Are you sure you want to exit? Active connections will be closed.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.disconnect_from_server()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
