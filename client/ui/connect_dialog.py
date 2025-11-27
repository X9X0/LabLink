"""Dialog for connecting to discovered equipment."""

import asyncio
import logging
from typing import List

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QComboBox,
    QPushButton,
    QMessageBox,
    QDialogButtonBox,
)

from client.api.client import LabLinkClient

logger = logging.getLogger(__name__)


class ConnectDeviceDialog(QDialog):
    """Dialog for selecting and connecting to discovered devices."""

    def __init__(self, resources: List[str], client: LabLinkClient, parent=None):
        """Initialize connect device dialog.

        Args:
            resources: List of discovered VISA resource strings
            client: LabLink API client
            parent: Parent widget
        """
        super().__init__(parent)
        self.resources = resources
        self.client = client
        self.connected = False

        self.setWindowTitle("Connect to Equipment")
        self.setModal(True)
        self.resize(600, 400)

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("<h3>Discovered Equipment</h3>")
        layout.addWidget(header)

        info = QLabel(
            f"Found {len(self.resources)} device(s). Select one to connect:"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # Resource list
        self.resource_list = QListWidget()
        self.resource_list.addItems(self.resources)
        if self.resources:
            self.resource_list.setCurrentRow(0)
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
        # Default to power_supply since we know it's a BK Precision PSU
        self.type_combo.setCurrentText("power_supply")
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
        self.model_combo.setCurrentText("BK Precision 9206B")  # Default for BK PSU
        model_layout.addWidget(self.model_combo)
        layout.addLayout(model_layout)

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

    def _connect_device(self):
        """Connect to the selected device."""
        # Get selected resource
        current_item = self.resource_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a device to connect.")
            return

        resource_string = current_item.text()
        equipment_type = self.type_combo.currentText()
        model = self.model_combo.currentText()

        # Disable connect button during connection
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("Connecting...")

        # Start async connection (non-blocking)
        asyncio.create_task(self._connect_device_async(resource_string, equipment_type, model))

    async def _connect_device_async(self, resource_string: str, equipment_type: str, model: str):
        """Perform device connection asynchronously (non-blocking).

        Args:
            resource_string: VISA resource string
            equipment_type: Equipment type
            model: Equipment model
        """
        try:
            # Call API to connect (async)
            logger.info(f"Connecting to {resource_string} as {equipment_type} ({model})")

            result = await self.client.connect_device_async(
                resource_string, equipment_type, model
            )

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
                # Re-enable button on failure
                self.connect_btn.setEnabled(True)
                self.connect_btn.setText("Connect")

        except Exception as e:
            logger.error(f"Error connecting to device: {e}")
            QMessageBox.critical(
                self, "Error", f"Failed to connect to device:\n\n{str(e)}"
            )
            # Re-enable button on error
            self.connect_btn.setEnabled(True)
            self.connect_btn.setText("Connect")
