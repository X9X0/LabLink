"""Raspberry Pi Network Discovery Panel for LabLink."""

import logging
from typing import Optional

try:
    from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
    from PyQt6.QtGui import QColor
    from PyQt6.QtWidgets import (
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

logger = logging.getLogger(__name__)


class ScanWorker(QThread):
    """Worker thread for Raspberry Pi network scanning."""

    finished = pyqtSignal(dict)  # Emits scan results
    error = pyqtSignal(str)  # Emits error message

    def __init__(self, client, network: Optional[str] = None, timeout: float = 2.0):
        super().__init__()
        self.client = client
        self.network = network
        self.timeout = timeout

    def run(self):
        """Execute the network scan in background thread."""
        try:
            result = self.client.scan_raspberry_pis(
                network=self.network, timeout=self.timeout
            )
            self.finished.emit(result)
        except Exception as e:
            logger.error(f"Scan error: {e}")
            self.error.emit(str(e))


class PiDiscoveryPanel(QWidget):
    """Panel for discovering Raspberry Pi devices on the network."""

    def __init__(self, client, parent=None):
        """Initialize Pi Discovery Panel.

        Args:
            client: LabLink API client
            parent: Parent widget
        """
        if not PYQT_AVAILABLE:
            raise ImportError("PyQt6 is required for PiDiscoveryPanel")

        super().__init__(parent)

        self.client = client
        self.scan_worker = None
        self.discovered_pis = []

        self._setup_ui()

    def _setup_ui(self):
        """Set up user interface."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("<h2>Raspberry Pi Network Discovery</h2>")
        layout.addWidget(header)

        # Scan controls group
        scan_group = QGroupBox("Scan Network")
        scan_layout = QVBoxLayout()

        # Network input
        network_layout = QHBoxLayout()
        network_layout.addWidget(QLabel("Network (CIDR):"))
        self.network_input = QLineEdit()
        self.network_input.setPlaceholderText("e.g., 192.168.1.0/24 (leave empty for auto-detect)")
        network_layout.addWidget(self.network_input)
        scan_layout.addLayout(network_layout)

        # Scan button and status
        scan_btn_layout = QHBoxLayout()
        self.scan_btn = QPushButton("Scan Network")
        self.scan_btn.clicked.connect(self._on_scan)
        self.scan_btn.setStyleSheet(
            "background-color: #2196F3; color: white; font-weight: bold; padding: 8px;"
        )
        scan_btn_layout.addWidget(self.scan_btn)

        self.scan_status = QLabel("Ready to scan")
        self.scan_status.setStyleSheet("color: #666;")
        scan_btn_layout.addWidget(self.scan_status)
        scan_btn_layout.addStretch()

        scan_layout.addLayout(scan_btn_layout)
        scan_group.setLayout(scan_layout)
        layout.addWidget(scan_group)

        # Results table
        results_group = QGroupBox("Discovered Raspberry Pis")
        results_layout = QVBoxLayout()

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(6)
        self.results_table.setHorizontalHeaderLabels(
            ["IP Address", "Hostname", "MAC Address", "Type", "Version", "Response Time"]
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.results_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.results_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.results_table.itemDoubleClicked.connect(self._on_pi_double_clicked)
        results_layout.addWidget(self.results_table)

        # Action buttons
        action_layout = QHBoxLayout()

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._on_scan)
        action_layout.addWidget(self.refresh_btn)

        action_layout.addStretch()

        self.connect_btn = QPushButton("Connect to LabLink")
        self.connect_btn.clicked.connect(self._on_connect_to_pi)
        self.connect_btn.setEnabled(False)
        self.connect_btn.setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;"
        )
        action_layout.addWidget(self.connect_btn)

        results_layout.addLayout(action_layout)
        results_group.setLayout(results_layout)
        layout.addWidget(results_group)

        # Legend
        legend_layout = QHBoxLayout()
        legend_layout.addWidget(QLabel("Legend:"))

        lablink_label = QLabel("■ LabLink Server")
        lablink_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        legend_layout.addWidget(lablink_label)

        pi_label = QLabel("■ Regular Raspberry Pi")
        pi_label.setStyleSheet("color: #FF9800;")
        legend_layout.addWidget(pi_label)

        legend_layout.addStretch()
        layout.addLayout(legend_layout)

        # Enable row selection handler
        self.results_table.itemSelectionChanged.connect(self._on_selection_changed)

    def _on_scan(self):
        """Start network scan for Raspberry Pis."""
        if self.scan_worker and self.scan_worker.isRunning():
            QMessageBox.warning(
                self, "Scan In Progress", "A scan is already in progress. Please wait."
            )
            return

        # Get network from input
        network = self.network_input.text().strip() or None

        # Update UI
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Scanning...")
        self.scan_status.setText("Scanning network... this may take a minute")
        self.scan_status.setStyleSheet("color: #2196F3;")
        self.results_table.setRowCount(0)

        # Start scan in background
        self.scan_worker = ScanWorker(self.client, network=network, timeout=2.0)
        self.scan_worker.finished.connect(self._on_scan_complete)
        self.scan_worker.error.connect(self._on_scan_error)
        self.scan_worker.start()

    def _on_scan_complete(self, result: dict):
        """Handle scan completion.

        Args:
            result: Scan results dictionary
        """
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("Scan Network")

        if not result.get("success"):
            self._on_scan_error("Scan failed")
            return

        # Update status
        pis_found = result.get("pis_found", 0)
        lablink_count = result.get("lablink_servers", 0)
        scan_time = result.get("scan_time_sec", 0)

        status_msg = f"Found {pis_found} Raspberry Pi(s) ({lablink_count} LabLink) in {scan_time}s"
        self.scan_status.setText(status_msg)
        self.scan_status.setStyleSheet("color: #4CAF50;")

        # Update table
        self.discovered_pis = result.get("discovered_pis", [])
        self._update_table()

        # Show message if no Pis found
        if pis_found == 0:
            QMessageBox.information(
                self,
                "No Devices Found",
                "No Raspberry Pi devices were found on the network.\n\n"
                "Make sure the devices are powered on and connected to the network.",
            )

    def _on_scan_error(self, error_msg: str):
        """Handle scan error.

        Args:
            error_msg: Error message
        """
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("Scan Network")
        self.scan_status.setText(f"Scan failed: {error_msg}")
        self.scan_status.setStyleSheet("color: #f44336;")

        QMessageBox.critical(
            self, "Scan Error", f"Failed to scan network:\n\n{error_msg}"
        )

    def _update_table(self):
        """Update the results table with discovered Pis."""
        self.results_table.setRowCount(len(self.discovered_pis))

        for i, pi in enumerate(self.discovered_pis):
            # IP Address
            ip_item = QTableWidgetItem(pi.get("ip_address", ""))
            ip_item.setData(Qt.ItemDataRole.UserRole, pi)

            # Color code based on LabLink status
            if pi.get("is_lablink"):
                ip_item.setForeground(QColor("#4CAF50"))
                ip_item.setData(Qt.ItemDataRole.FontRole, "bold")
            else:
                ip_item.setForeground(QColor("#FF9800"))

            self.results_table.setItem(i, 0, ip_item)

            # Hostname
            hostname = pi.get("hostname", "Unknown")
            hostname_item = QTableWidgetItem(hostname)
            if pi.get("is_lablink"):
                hostname_item.setForeground(QColor("#4CAF50"))
            else:
                hostname_item.setForeground(QColor("#FF9800"))
            self.results_table.setItem(i, 1, hostname_item)

            # MAC Address
            mac = pi.get("mac_address", "Unknown")
            self.results_table.setItem(i, 2, QTableWidgetItem(mac))

            # Type
            if pi.get("is_lablink"):
                type_str = "LabLink Server"
                type_item = QTableWidgetItem(type_str)
                type_item.setForeground(QColor("#4CAF50"))
                type_item.setData(Qt.ItemDataRole.FontRole, "bold")
            else:
                type_str = "Raspberry Pi OS"
                type_item = QTableWidgetItem(type_str)
                type_item.setForeground(QColor("#FF9800"))
            self.results_table.setItem(i, 3, type_item)

            # Version (for LabLink servers)
            version = pi.get("lablink_version", "-")
            self.results_table.setItem(i, 4, QTableWidgetItem(version))

            # Response Time
            response_time = pi.get("response_time_ms")
            if response_time is not None:
                time_str = f"{response_time:.1f} ms"
            else:
                time_str = "-"
            self.results_table.setItem(i, 5, QTableWidgetItem(time_str))

    def _on_selection_changed(self):
        """Handle table selection change."""
        selected = self.results_table.selectedItems()

        if selected and len(selected) > 0:
            row = selected[0].row()
            pi_data = self.results_table.item(row, 0).data(Qt.ItemDataRole.UserRole)

            # Enable connect button only for LabLink servers
            if pi_data and pi_data.get("is_lablink"):
                self.connect_btn.setEnabled(True)
            else:
                self.connect_btn.setEnabled(False)
        else:
            self.connect_btn.setEnabled(False)

    def _on_pi_double_clicked(self, item):
        """Handle double-click on Pi entry.

        Args:
            item: Table widget item
        """
        row = item.row()
        pi_data = self.results_table.item(row, 0).data(Qt.ItemDataRole.UserRole)

        if pi_data and pi_data.get("is_lablink"):
            self._on_connect_to_pi()
        else:
            # Show info about regular Pi
            ip = pi_data.get("ip_address", "Unknown")
            hostname = pi_data.get("hostname", "Unknown")
            mac = pi_data.get("mac_address", "Unknown")

            QMessageBox.information(
                self,
                "Raspberry Pi Information",
                f"This is a regular Raspberry Pi (not running LabLink).\n\n"
                f"IP Address: {ip}\n"
                f"Hostname: {hostname}\n"
                f"MAC Address: {mac}\n\n"
                f"To use this Pi with LabLink, you need to provision it with LabLink software.",
            )

    def _on_connect_to_pi(self):
        """Connect to selected LabLink server."""
        selected = self.results_table.selectedItems()

        if not selected:
            return

        row = selected[0].row()
        pi_data = self.results_table.item(row, 0).data(Qt.ItemDataRole.UserRole)

        if not pi_data or not pi_data.get("is_lablink"):
            QMessageBox.warning(
                self,
                "Not a LabLink Server",
                "The selected device is not running LabLink.\n\n"
                "Please select a LabLink server to connect.",
            )
            return

        # Get connection details
        ip = pi_data.get("ip_address")
        name = pi_data.get("lablink_name", "LabLink")
        version = pi_data.get("lablink_version", "unknown")

        # Confirm connection
        reply = QMessageBox.question(
            self,
            "Connect to LabLink Server",
            f"Connect to {name} at {ip}?\n\nVersion: {version}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Update client connection
                self.client.host = ip
                self.client.api_base_url = f"http://{ip}:8000/api"

                # Test connection
                if self.client.connect():
                    QMessageBox.information(
                        self,
                        "Connected",
                        f"Successfully connected to {name} at {ip}",
                    )
                else:
                    QMessageBox.critical(
                        self,
                        "Connection Failed",
                        f"Failed to connect to {name} at {ip}.\n\n"
                        "Please check the server is running and accessible.",
                    )
            except Exception as e:
                logger.error(f"Connection error: {e}")
                QMessageBox.critical(
                    self, "Connection Error", f"Error connecting to server:\n\n{str(e)}"
                )

    def set_client(self, client):
        """Set API client.

        Args:
            client: LabLink API client
        """
        self.client = client
        self.refresh()

    def refresh(self):
        """Refresh the panel (called when switching tabs)."""
        if not self.client:
            return

        # Auto-load cached results on first view
        if self.results_table.rowCount() == 0:
            try:
                status = self.client.get_pi_discovery_status()
                if status.get("success"):
                    cached_pis = status.get("discovered_pis", [])
                    if len(cached_pis) > 0:
                        self.discovered_pis = cached_pis
                        self._update_table()
                        self.scan_status.setText(
                            f"Showing {len(cached_pis)} cached result(s)"
                        )
                        self.scan_status.setStyleSheet("color: #666;")
            except Exception as e:
                logger.debug(f"Failed to load cached results: {e}")
