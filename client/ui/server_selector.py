"""Server selector widget for multi-server management."""

import logging
from typing import Optional

try:
    from PyQt6.QtCore import Qt, pyqtSignal
    from PyQt6.QtGui import QAction
    from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                                 QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                                 QMenu, QMessageBox, QPushButton, QSpinBox,
                                 QVBoxLayout, QWidget)

    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

from client.utils.server_manager import ServerConnection, get_server_manager

logger = logging.getLogger(__name__)


class AddServerDialog(QDialog):
    """Dialog for adding a new server."""

    def __init__(self, parent=None):
        """Initialize add server dialog."""
        super().__init__(parent)

        self.setWindowTitle("Add Server")
        self.setMinimumWidth(400)

        layout = QFormLayout(self)

        # Server name
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("My Lab Server")
        layout.addRow("Server Name:", self.name_edit)

        # Host
        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("192.168.1.100 or lablink.local")
        layout.addRow("Hostname/IP:", self.host_edit)

        # API port
        self.api_port_spin = QSpinBox()
        self.api_port_spin.setRange(1, 65535)
        self.api_port_spin.setValue(8000)
        layout.addRow("API Port:", self.api_port_spin)

        # WebSocket port
        self.ws_port_spin = QSpinBox()
        self.ws_port_spin.setRange(1, 65535)
        self.ws_port_spin.setValue(8001)
        layout.addRow("WebSocket Port:", self.ws_port_spin)

        # Description
        self.description_edit = QLineEdit()
        self.description_edit.setPlaceholderText("Optional description")
        layout.addRow("Description:", self.description_edit)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_server_config(self):
        """Get server configuration.

        Returns:
            Dictionary with server configuration
        """
        return {
            "name": self.name_edit.text().strip(),
            "host": self.host_edit.text().strip(),
            "api_port": self.api_port_spin.value(),
            "ws_port": self.ws_port_spin.value(),
            "description": self.description_edit.text().strip(),
        }

    def accept(self):
        """Validate and accept dialog."""
        config = self.get_server_config()

        if not config["name"]:
            QMessageBox.warning(self, "Invalid Input", "Please enter a server name")
            return

        if not config["host"]:
            QMessageBox.warning(
                self, "Invalid Input", "Please enter a hostname or IP address"
            )
            return

        super().accept()


class ServerSelector(QWidget):
    """Widget for selecting and managing servers."""

    # Signals
    server_changed = pyqtSignal(str)  # Server name
    connect_requested = pyqtSignal(str)  # Server name

    def __init__(self, parent=None):
        """Initialize server selector."""
        if not PYQT_AVAILABLE:
            raise ImportError("PyQt6 is required")

        super().__init__(parent)

        self.server_manager = get_server_manager()

        self._setup_ui()
        self._refresh_server_list()

    def _setup_ui(self):
        """Set up user interface."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Server label
        label = QLabel("Server:")
        layout.addWidget(label)

        # Server combo box
        self.server_combo = QComboBox()
        self.server_combo.setMinimumWidth(200)
        self.server_combo.currentTextChanged.connect(self._on_server_changed)
        layout.addWidget(self.server_combo)

        # Connect button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._on_connect_clicked)
        layout.addWidget(self.connect_btn)

        # More options button (dropdown menu)
        more_btn = QPushButton("⋮")
        more_btn.setFixedWidth(30)
        more_btn.setToolTip("Server management options")
        more_btn.clicked.connect(self._show_menu)
        self.more_btn = more_btn
        layout.addWidget(more_btn)

        # Create context menu
        self.menu = QMenu(self)

        add_action = QAction("Add Server...", self)
        add_action.triggered.connect(self._on_add_server)
        self.menu.addAction(add_action)

        remove_action = QAction("Remove Server", self)
        remove_action.triggered.connect(self._on_remove_server)
        self.remove_action = remove_action
        self.menu.addAction(remove_action)

        self.menu.addSeparator()

        refresh_action = QAction("Refresh List", self)
        refresh_action.triggered.connect(self._refresh_server_list)
        self.menu.addAction(refresh_action)

    def _refresh_server_list(self):
        """Refresh the server list."""
        current_text = self.server_combo.currentText()

        self.server_combo.clear()

        servers = self.server_manager.list_servers()

        if not servers:
            self.server_combo.addItem("(No servers configured)")
            self.connect_btn.setEnabled(False)
            self.remove_action.setEnabled(False)
            return

        for server in servers:
            status = "● " if server.connected else "○ "
            self.server_combo.addItem(f"{status}{server.name}")
            self.server_combo.setItemData(
                self.server_combo.count() - 1, server.name, Qt.ItemDataRole.UserRole
            )

        # Restore selection if possible
        if current_text:
            index = self.server_combo.findText(current_text)
            if index >= 0:
                self.server_combo.setCurrentIndex(index)
        else:
            # Select active server if set
            active = self.server_manager.get_active_server()
            if active:
                for i in range(self.server_combo.count()):
                    name = self.server_combo.itemData(i, Qt.ItemDataRole.UserRole)
                    if name == active.name:
                        self.server_combo.setCurrentIndex(i)
                        break

        self.connect_btn.setEnabled(True)
        self.remove_action.setEnabled(True)

    def _on_server_changed(self, text: str):
        """Handle server selection change."""
        if not text or text == "(No servers configured)":
            return

        # Get actual server name from item data
        index = self.server_combo.currentIndex()
        server_name = self.server_combo.itemData(index, Qt.ItemDataRole.UserRole)

        if server_name:
            server = self.server_manager.get_server(server_name)

            if server:
                # Update button text based on connection status
                self.connect_btn.setText(
                    "Disconnect" if server.connected else "Connect"
                )
                self.server_changed.emit(server_name)

    def _on_connect_clicked(self):
        """Handle connect button click."""
        index = self.server_combo.currentIndex()
        if index < 0:
            return

        server_name = self.server_combo.itemData(index, Qt.ItemDataRole.UserRole)
        if server_name:
            self.connect_requested.emit(server_name)

    def _show_menu(self):
        """Show context menu."""
        # Position menu below button
        pos = self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft())
        self.menu.exec(pos)

    def _on_add_server(self):
        """Handle add server action."""
        dialog = AddServerDialog(self)

        if dialog.exec():
            config = dialog.get_server_config()

            try:
                # Check if server already exists
                existing = self.server_manager.find_server_by_host(
                    config["host"], config["api_port"]
                )

                if existing:
                    QMessageBox.warning(
                        self,
                        "Server Exists",
                        f"A server with this host and port already exists: {existing.name}",
                    )
                    return

                # Add server
                metadata = {}
                if config["description"]:
                    metadata["description"] = config["description"]

                self.server_manager.add_server(
                    config["name"],
                    config["host"],
                    config["api_port"],
                    config["ws_port"],
                    metadata,
                )

                self._refresh_server_list()

                # Select the newly added server
                for i in range(self.server_combo.count()):
                    name = self.server_combo.itemData(i, Qt.ItemDataRole.UserRole)
                    if name == config["name"]:
                        self.server_combo.setCurrentIndex(i)
                        break

                QMessageBox.information(
                    self,
                    "Server Added",
                    f"Server '{config['name']}' has been added successfully.",
                )

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to add server: {e}")

    def _on_remove_server(self):
        """Handle remove server action."""
        index = self.server_combo.currentIndex()
        if index < 0:
            return

        server_name = self.server_combo.itemData(index, Qt.ItemDataRole.UserRole)
        if not server_name:
            return

        server = self.server_manager.get_server(server_name)
        if not server:
            return

        # Confirm removal
        reply = QMessageBox.question(
            self,
            "Remove Server",
            f"Are you sure you want to remove server '{server_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            if server.connected:
                QMessageBox.warning(
                    self,
                    "Server Connected",
                    "Please disconnect from the server before removing it.",
                )
                return

            self.server_manager.remove_server(server_name)
            self._refresh_server_list()

            QMessageBox.information(
                self, "Server Removed", f"Server '{server_name}' has been removed."
            )

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to remove server: {e}")

    def get_selected_server(self) -> Optional[ServerConnection]:
        """Get the currently selected server.

        Returns:
            ServerConnection or None
        """
        index = self.server_combo.currentIndex()
        if index < 0:
            return None

        server_name = self.server_combo.itemData(index, Qt.ItemDataRole.UserRole)
        if server_name:
            return self.server_manager.get_server(server_name)

        return None

    def select_server(self, server_name: str):
        """Select a server by name.

        Args:
            server_name: Server name to select
        """
        for i in range(self.server_combo.count()):
            name = self.server_combo.itemData(i, Qt.ItemDataRole.UserRole)
            if name == server_name:
                self.server_combo.setCurrentIndex(i)
                break

    def refresh(self):
        """Refresh the server list."""
        self._refresh_server_list()
