"""Raspberry Pi Network Discovery Dialog for LabLink."""

import asyncio
import logging
import time
from typing import Optional

try:
    from PyQt6.QtCore import Qt, QThread, pyqtSignal
    from PyQt6.QtGui import QColor
    from PyQt6.QtWidgets import (
        QDialog,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
    )

    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

from client.utils.pi_discovery import PiDiscovery

logger = logging.getLogger(__name__)


class ScanWorker(QThread):
    """Worker thread for Raspberry Pi network scanning."""

    finished = pyqtSignal(list, float)  # Emits (discovered_pis, scan_time)
    error = pyqtSignal(str)  # Emits error message
    progress = pyqtSignal(int, int)  # Emits (current, total)

    def __init__(self, network: Optional[str] = None, timeout: float = 2.0, batch_size: int = 20):
        super().__init__()
        self.network = network
        self.timeout = timeout
        self.batch_size = batch_size
        self.discovery = PiDiscovery()

    def _on_progress(self, current: int, total: int):
        """Progress callback from discovery."""
        self.progress.emit(current, total)

    def run(self):
        """Execute the network scan in background thread."""
        try:
            # Run async discovery in this thread
            start_time = time.time()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            discovered_pis = loop.run_until_complete(
                self.discovery.discover_network(
                    network=self.network,
                    timeout=self.timeout,
                    batch_size=self.batch_size,
                    progress_callback=self._on_progress
                )
            )
            loop.close()
            scan_time = time.time() - start_time

            self.finished.emit(discovered_pis, scan_time)
        except Exception as e:
            logger.error(f"Scan error: {e}")
            self.error.emit(str(e))


class PiDiscoveryDialog(QDialog):
    """Dialog for discovering Raspberry Pi devices on the network."""

    def __init__(self, parent=None):
        """Initialize Pi Discovery Dialog.

        Args:
            parent: Parent widget
        """
        if not PYQT_AVAILABLE:
            raise ImportError("PyQt6 is required for PiDiscoveryDialog")

        super().__init__(parent)

        self.scan_worker = None
        self.discovered_pis = []

        self.setWindowTitle("Raspberry Pi Network Discovery")
        self.resize(900, 600)

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

        # Scan parameters
        params_layout = QHBoxLayout()

        # Timeout input
        params_layout.addWidget(QLabel("Timeout (seconds):"))
        self.timeout_input = QLineEdit()
        self.timeout_input.setText("3.0")
        self.timeout_input.setMaximumWidth(80)
        self.timeout_input.setToolTip("Timeout for each host check (1-10 seconds)")
        params_layout.addWidget(self.timeout_input)

        params_layout.addSpacing(20)

        # Batch size input
        params_layout.addWidget(QLabel("Batch Size:"))
        self.batch_size_input = QLineEdit()
        self.batch_size_input.setText("10")
        self.batch_size_input.setMaximumWidth(80)
        self.batch_size_input.setToolTip("Number of hosts to scan concurrently (1-50)")
        params_layout.addWidget(self.batch_size_input)

        params_layout.addStretch()
        scan_layout.addLayout(params_layout)

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

        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Scanning: %v / %m hosts (%p%)")
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

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

        # Get timeout from input
        try:
            timeout = float(self.timeout_input.text())
            if timeout < 1.0 or timeout > 10.0:
                QMessageBox.warning(
                    self,
                    "Invalid Timeout",
                    "Timeout must be between 1 and 10 seconds."
                )
                return
        except ValueError:
            QMessageBox.warning(
                self,
                "Invalid Timeout",
                "Timeout must be a valid number."
            )
            return

        # Get batch size from input
        try:
            batch_size = int(self.batch_size_input.text())
            if batch_size < 1 or batch_size > 50:
                QMessageBox.warning(
                    self,
                    "Invalid Batch Size",
                    "Batch size must be between 1 and 50."
                )
                return
        except ValueError:
            QMessageBox.warning(
                self,
                "Invalid Batch Size",
                "Batch size must be a valid integer."
            )
            return

        # Update UI
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Scanning...")
        self.scan_status.setText("Scanning network... this may take a minute")
        self.scan_status.setStyleSheet("color: #2196F3;")
        self.results_table.setRowCount(0)

        # Show and reset progress bar
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.show()

        # Start scan in background
        self.scan_worker = ScanWorker(network=network, timeout=timeout, batch_size=batch_size)
        self.scan_worker.finished.connect(self._on_scan_complete)
        self.scan_worker.error.connect(self._on_scan_error)
        self.scan_worker.progress.connect(self._on_scan_progress)
        self.scan_worker.start()

    def _on_scan_progress(self, current: int, total: int):
        """Handle scan progress update.

        Args:
            current: Current number of hosts scanned
            total: Total number of hosts to scan
        """
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def _on_scan_complete(self, discovered_pis: list, scan_time: float):
        """Handle scan completion.

        Args:
            discovered_pis: List of DiscoveredPi objects
            scan_time: Time taken for scan in seconds
        """
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("Scan Network")
        self.progress_bar.hide()

        # Update status
        pis_found = len(discovered_pis)
        lablink_count = sum(1 for pi in discovered_pis if pi.is_lablink)

        status_msg = f"Found {pis_found} Raspberry Pi(s) ({lablink_count} LabLink) in {scan_time:.1f}s"
        self.scan_status.setText(status_msg)
        self.scan_status.setStyleSheet("color: #4CAF50;")

        # Update table
        self.discovered_pis = discovered_pis
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
        self.progress_bar.hide()
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
            ip_item = QTableWidgetItem(pi.ip_address)
            ip_item.setData(Qt.ItemDataRole.UserRole, pi)

            # Color code based on LabLink status
            if pi.is_lablink:
                ip_item.setForeground(QColor("#4CAF50"))
                ip_item.setData(Qt.ItemDataRole.FontRole, "bold")
            else:
                ip_item.setForeground(QColor("#FF9800"))

            self.results_table.setItem(i, 0, ip_item)

            # Hostname
            hostname = pi.hostname or "Unknown"
            hostname_item = QTableWidgetItem(hostname)
            if pi.is_lablink:
                hostname_item.setForeground(QColor("#4CAF50"))
            else:
                hostname_item.setForeground(QColor("#FF9800"))
            self.results_table.setItem(i, 1, hostname_item)

            # MAC Address
            mac = pi.mac_address or "Unknown"
            self.results_table.setItem(i, 2, QTableWidgetItem(mac))

            # Type
            if pi.is_lablink:
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
            version = pi.lablink_version or "-"
            self.results_table.setItem(i, 4, QTableWidgetItem(version))

            # Response Time
            if pi.response_time_ms is not None:
                time_str = f"{pi.response_time_ms:.1f} ms"
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
            if pi_data and pi_data.is_lablink:
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

        if pi_data and pi_data.is_lablink:
            self._on_connect_to_pi()
        else:
            # Show info about regular Pi
            ip = pi_data.ip_address
            hostname = pi_data.hostname or "Unknown"
            mac = pi_data.mac_address or "Unknown"

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

        if not pi_data or not pi_data.is_lablink:
            QMessageBox.warning(
                self,
                "Not a LabLink Server",
                "The selected device is not running LabLink.\n\n"
                "Please select a LabLink server to connect.",
            )
            return

        # Get connection details
        ip = pi_data.ip_address
        name = pi_data.lablink_name or "LabLink"
        version = pi_data.lablink_version or "unknown"

        # Confirm connection
        reply = QMessageBox.question(
            self,
            "Connect to LabLink Server",
            f"Connect to {name} at {ip}?\n\nVersion: {version}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Close dialog and pass connection info to parent
            QMessageBox.information(
                self,
                "Connection Requested",
                f"Please use the File menu to connect to {name} at {ip}:8000.\n\n"
                f"Host: {ip}\n"
                f"API Port: 8000\n"
                f"WS Port: 8001",
            )
            self.accept()
