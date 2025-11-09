"""Server discovery dialog using mDNS."""

import logging
from typing import Optional

try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
        QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
        QMessageBox, QProgressBar
    )
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

logger = logging.getLogger(__name__)


class DiscoveryDialog(QDialog):
    """Dialog for discovering LabLink servers on the network."""

    # Signal emitted when server is selected
    server_selected = pyqtSignal(dict)  # server_dict

    def __init__(self, parent=None, timeout: float = 10.0):
        """
        Initialize discovery dialog.

        Args:
            parent: Parent widget
            timeout: Discovery timeout in seconds
        """
        if not PYQT_AVAILABLE:
            raise ImportError("PyQt6 is required")

        super().__init__(parent)

        self.timeout = timeout
        self.discovery = None
        self.selected_server = None

        self._setup_ui()
        self._check_zeroconf()

    def _setup_ui(self):
        """Set up user interface."""
        self.setWindowTitle("Discover LabLink Servers")
        self.setModal(True)
        self.resize(700, 400)

        layout = QVBoxLayout(self)

        # Header
        header = QLabel("<h2>Discover LabLink Servers</h2>")
        layout.addWidget(header)

        info = QLabel(
            "Searching for LabLink servers on the local network using mDNS/Zeroconf..."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Initializing discovery...")
        layout.addWidget(self.status_label)

        # Servers table
        self.servers_table = QTableWidget()
        self.servers_table.setColumnCount(5)
        self.servers_table.setHorizontalHeaderLabels([
            "Server Name", "IP Address", "API Port", "WS Port", "Version"
        ])
        self.servers_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.servers_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.servers_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.servers_table.itemDoubleClicked.connect(self._on_server_double_clicked)
        layout.addWidget(self.servers_table)

        # Buttons
        button_layout = QHBoxLayout()

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._on_refresh)
        button_layout.addWidget(self.refresh_btn)

        button_layout.addStretch()

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._on_connect)
        self.connect_btn.setEnabled(False)
        self.connect_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;")
        button_layout.addWidget(self.connect_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        # Timer for updating discovery status
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_table)
        self.update_timer.start(500)  # Update every 500ms

        # Timer for stopping discovery after timeout
        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_timeout)

    def _check_zeroconf(self):
        """Check if zeroconf is available."""
        try:
            from client.utils.mdns_discovery import LabLinkDiscovery, ZEROCONF_AVAILABLE

            if not ZEROCONF_AVAILABLE:
                self._show_error(
                    "Zeroconf not available",
                    "mDNS/Zeroconf discovery requires the 'zeroconf' package.\n\n"
                    "Install with: pip install zeroconf"
                )
                return

            # Start discovery
            self.discovery = LabLinkDiscovery()
            self.discovery.register_callback(self._on_server_discovered)
            self.discovery.start()

            self.status_label.setText(f"Discovering servers... (timeout: {self.timeout}s)")
            self.timeout_timer.start(int(self.timeout * 1000))

        except Exception as e:
            self._show_error("Discovery Error", f"Failed to start discovery: {e}")

    def _on_server_discovered(self, event_type: str, server):
        """Handle server discovered callback."""
        logger.info(f"Server {event_type}: {server}")
        # Table will be updated by timer

    def _update_table(self):
        """Update servers table."""
        if not self.discovery:
            return

        servers = self.discovery.get_servers()

        # Update table
        self.servers_table.setRowCount(len(servers))

        for i, server in enumerate(servers):
            # Server name
            name_item = QTableWidgetItem(server.name)
            name_item.setData(Qt.ItemDataRole.UserRole, server)
            self.servers_table.setItem(i, 0, name_item)

            # IP address
            self.servers_table.setItem(i, 1, QTableWidgetItem(server.address))

            # API port
            self.servers_table.setItem(i, 2, QTableWidgetItem(str(server.port)))

            # WS port
            self.servers_table.setItem(i, 3, QTableWidgetItem(str(server.ws_port)))

            # Version
            version = server.properties.get('version', 'Unknown')
            self.servers_table.setItem(i, 4, QTableWidgetItem(version))

        # Update status
        if len(servers) == 0:
            self.status_label.setText("No servers found yet...")
            self.connect_btn.setEnabled(False)
        else:
            self.status_label.setText(f"Found {len(servers)} server(s)")
            # Enable connect if row selected
            selected = self.servers_table.selectedItems()
            self.connect_btn.setEnabled(len(selected) > 0)

    def _on_timeout(self):
        """Handle discovery timeout."""
        if self.discovery:
            servers = self.discovery.get_servers()

            if len(servers) == 0:
                self.status_label.setText("Discovery complete. No servers found.")
                QMessageBox.information(
                    self,
                    "No Servers Found",
                    "No LabLink servers were found on the network.\n\n"
                    "Make sure the server is running and mDNS is enabled."
                )
            else:
                self.status_label.setText(f"Discovery complete. Found {len(servers)} server(s).")

        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)

    def _on_refresh(self):
        """Refresh discovery."""
        if self.discovery:
            self.discovery.clear()

        self.servers_table.setRowCount(0)
        self.status_label.setText("Refreshing...")
        self.progress_bar.setRange(0, 0)

        # Restart discovery
        if self.discovery:
            self.discovery.stop()

        self._check_zeroconf()

    def _on_server_double_clicked(self, item):
        """Handle server double-clicked."""
        self._on_connect()

    def _on_connect(self):
        """Handle connect button clicked."""
        selected = self.servers_table.selectedItems()

        if not selected:
            return

        # Get server from first item in row
        row = selected[0].row()
        name_item = self.servers_table.item(row, 0)
        server = name_item.data(Qt.ItemDataRole.UserRole)

        if server:
            self.selected_server = server.to_dict()
            self.server_selected.emit(self.selected_server)
            self.accept()

    def _show_error(self, title: str, message: str):
        """Show error message."""
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Error: {title}")

        QMessageBox.critical(self, title, message)

    def get_selected_server(self) -> Optional[dict]:
        """
        Get selected server.

        Returns:
            Server dictionary if selected, None otherwise
        """
        return self.selected_server

    def closeEvent(self, event):
        """Handle dialog close."""
        # Stop discovery
        if self.discovery:
            self.discovery.stop()

        # Stop timers
        self.update_timer.stop()
        self.timeout_timer.stop()

        event.accept()


def show_discovery_dialog(parent=None, timeout: float = 10.0) -> Optional[dict]:
    """
    Show discovery dialog and return selected server.

    Args:
        parent: Parent widget
        timeout: Discovery timeout in seconds

    Returns:
        Server dictionary if selected, None if cancelled
    """
    dialog = DiscoveryDialog(parent, timeout)

    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.get_selected_server()

    return None
