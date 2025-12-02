"""Dialog for connecting to discovered equipment."""

import logging
from typing import List, Dict, Any

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QComboBox,
    QPushButton,
    QMessageBox,
    QDialogButtonBox,
)
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtCore import Qt

from client.api.client import LabLinkClient

logger = logging.getLogger(__name__)


class ConnectDeviceDialog(QDialog):
    """Dialog for selecting and connecting to discovered devices."""

    def __init__(self, devices: List[Dict[str, Any]], client: LabLinkClient, parent=None):
        """Initialize connect device dialog.

        Args:
            devices: List of discovered device info dicts
            client: LabLink API client
            parent: Parent widget
        """
        super().__init__(parent)
        self.devices = devices  # List of device dicts with full info
        self.client = client
        self.connected = False

        self.setWindowTitle("Connect to Equipment")
        self.setModal(True)
        self.resize(700, 450)

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("<h3>Discovered Equipment</h3>")
        layout.addWidget(header)

        info = QLabel(
            f"Found {len(self.devices)} device(s). Devices with confirmed identification are highlighted."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # Resource list with device info
        self.resource_list = QListWidget()
        for device in self.devices:
            # Create display text with device info
            resource_name = device.get("resource_name", "Unknown")
            manufacturer = device.get("manufacturer", "")
            model = device.get("model", "")
            device_type = device.get("device_type", "unknown")
            confidence = device.get("confidence_score", 0.0)

            if manufacturer and model:
                display_text = f"{resource_name}  —  {manufacturer} {model} ({device_type})"
            else:
                display_text = f"{resource_name}  —  {device_type}"

            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, device)  # Store full device info

            # Highlight devices with high confidence (proper identification)
            if confidence >= 0.8 and manufacturer and model:
                item.setBackground(QBrush(QColor(230, 255, 230)))  # Light green
                item.setToolTip("Device properly identified via *IDN? query")
            elif confidence >= 0.6:
                item.setBackground(QBrush(QColor(255, 255, 230)))  # Light yellow
                item.setToolTip("Device partially identified via USB hardware database")

            self.resource_list.addItem(item)

        if self.devices:
            self.resource_list.setCurrentRow(0)

        # Connect selection change to auto-populate dropdowns
        self.resource_list.currentItemChanged.connect(self._on_device_selected)

        layout.addWidget(self.resource_list)

        # Equipment type selection
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Equipment Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems([
            "power_supply",
            "oscilloscope",
            "electronic_load",
            "multimeter",
            "function_generator",
            "spectrum_analyzer",
            "unknown",
        ])
        type_layout.addWidget(self.type_combo)
        layout.addLayout(type_layout)

        # Model selection
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)  # Allow custom model names
        self.model_combo.addItems([
            "BK Precision 1685B",
            "BK Precision 9130B",
            "BK Precision 9205B",
            "BK Precision 9206B",
            "BK Precision 1902B",
            "Rigol DS1054Z",
            "Rigol MSO2072A",
            "Rigol DS1102D",
            "Rigol DL3021A",
            "Generic",
        ])
        model_layout.addWidget(self.model_combo)
        layout.addLayout(model_layout)

        # Auto-populate dropdowns with first device
        if self.devices:
            self._on_device_selected(self.resource_list.item(0), None)

        # Buttons
        button_layout = QHBoxLayout()

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._connect_device)
        self.connect_btn.setDefault(True)
        button_layout.addWidget(self.connect_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    def _on_device_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        """Handle device selection - auto-populate equipment type and model."""
        if not current:
            return

        # Get device info from item data
        device = current.data(Qt.ItemDataRole.UserRole)
        if not device:
            return

        # Auto-select equipment type
        device_type = device.get("device_type", "unknown")
        index = self.type_combo.findText(device_type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)

        # Auto-select model
        manufacturer = device.get("manufacturer", "")
        model = device.get("model", "")

        if manufacturer and model:
            # Try to find exact match first
            full_model = f"{manufacturer} {model}"
            index = self.model_combo.findText(full_model)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
            else:
                # Set as custom text
                self.model_combo.setCurrentText(full_model)
        elif model:
            # Just model name
            self.model_combo.setCurrentText(model)

    def _connect_device(self):
        """Connect to the selected device."""
        # Get selected resource
        current_item = self.resource_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a device to connect.")
            return

        # Get device info
        device = current_item.data(Qt.ItemDataRole.UserRole)
        resource_string = device.get("resource_name", "")
        equipment_type = self.type_combo.currentText()
        model = self.model_combo.currentText()

        try:
            # Call API to connect (synchronous - connection is fast, no need for async)
            logger.info(f"Connecting to {resource_string} as {equipment_type} ({model})")

            response = self.client._session.post(
                f"{self.client.api_base_url}/equipment/connect",
                json={
                    "resource_string": resource_string,
                    "equipment_type": equipment_type,
                    "model": model,
                },
            )
            response.raise_for_status()

            result = response.json()

            if result.get("equipment_id"):
                self.connected = True
                QMessageBox.information(
                    self,
                    "Success",
                    f"Connected to {model} successfully!\n\nEquipment ID: {result['equipment_id']}",
                )
                self.accept()
            else:
                QMessageBox.warning(
                    self,
                    "Failed",
                    f"Connection failed: {result.get('message', 'Unknown error')}",
                )

        except Exception as e:
            logger.error(f"Error connecting to device: {e}")
            QMessageBox.critical(
                self, "Error", f"Failed to connect to device:\n\n{str(e)}"
            )
