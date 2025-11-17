"""Connection dialog for LabLink server."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QSpinBox, QVBoxLayout)


class ConnectionDialog(QDialog):
    """Dialog for connecting to LabLink server."""

    def __init__(self, parent=None):
        """Initialize connection dialog."""
        super().__init__(parent)

        self.setWindowTitle("Connect to LabLink Server")
        self.setModal(True)

        # Apply visual styling
        self.setStyleSheet("""
            QDialog {
                background-color: #ecf0f1;
            }
            QGroupBox {
                border: 2px solid #bdc3c7;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 15px;
                background-color: white;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 5px 10px;
                background-color: white;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                border: 2px solid #2471a3;
                border-radius: 6px;
                padding: 8px 15px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #2e86c1;
                border: 2px solid #1f618d;
            }
            QPushButton:pressed {
                background-color: #2471a3;
            }
        """)

        self._setup_ui()
        self._load_last_connection()

    def _setup_ui(self):
        """Set up user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Server configuration group
        server_group = QGroupBox("Server Configuration")
        server_layout = QFormLayout()

        # Hostname/IP
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("lablink-pi.local, localhost, or IP address")
        server_layout.addRow("Host:", self.host_input)

        # API Port
        self.api_port_input = QSpinBox()
        self.api_port_input.setRange(1, 65535)
        self.api_port_input.setValue(8000)
        server_layout.addRow("API Port:", self.api_port_input)

        # WebSocket Port
        self.ws_port_input = QSpinBox()
        self.ws_port_input.setRange(1, 65535)
        self.ws_port_input.setValue(8001)
        server_layout.addRow("WebSocket Port:", self.ws_port_input)

        server_group.setLayout(server_layout)
        layout.addWidget(server_group)

        # Quick connections
        quick_group = QGroupBox("Quick Connections")
        quick_layout = QHBoxLayout()

        localhost_btn = QPushButton("Localhost")
        localhost_btn.clicked.connect(
            lambda: self.set_connection("localhost", 8000, 8001)
        )
        quick_layout.addWidget(localhost_btn)

        pi_btn = QPushButton("Raspberry Pi")
        pi_btn.clicked.connect(
            lambda: self.set_connection("lablink-pi.local", 8000, 8001)
        )
        quick_layout.addWidget(pi_btn)

        quick_group.setLayout(quick_layout)
        layout.addWidget(quick_group)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_last_connection(self):
        """Load last used connection settings."""
        # TODO: Load from settings file
        self.host_input.setText("lablink-pi.local")

    def set_connection(self, host: str, api_port: int, ws_port: int):
        """Set connection parameters.

        Args:
            host: Server hostname
            api_port: API port
            ws_port: WebSocket port
        """
        self.host_input.setText(host)
        self.api_port_input.setValue(api_port)
        self.ws_port_input.setValue(ws_port)

    def get_host(self) -> str:
        """Get entered host.

        Returns:
            Host string
        """
        return self.host_input.text()

    def get_api_port(self) -> int:
        """Get entered API port.

        Returns:
            Port number
        """
        return self.api_port_input.value()

    def get_ws_port(self) -> int:
        """Get entered WebSocket port.

        Returns:
            Port number
        """
        return self.ws_port_input.value()
