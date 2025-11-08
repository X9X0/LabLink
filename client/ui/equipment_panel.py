"""Equipment control panel for LabLink GUI."""

import logging
from typing import Optional, List
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QGroupBox, QLabel,
    QPushButton, QMessageBox, QGridLayout, QLineEdit,
    QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal

from api.client import LabLinkClient
from models.equipment import Equipment, ConnectionStatus

logger = logging.getLogger(__name__)


class EquipmentPanel(QWidget):
    """Panel for equipment control and monitoring."""

    equipment_selected = pyqtSignal(str)  # equipment_id

    def __init__(self, parent=None):
        """Initialize equipment panel."""
        super().__init__(parent)

        self.client: Optional[LabLinkClient] = None
        self.equipment_list: List[Equipment] = []
        self.selected_equipment: Optional[Equipment] = None

        self._setup_ui()

    def _setup_ui(self):
        """Set up user interface."""
        layout = QHBoxLayout(self)

        # Splitter for list and details
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side: Equipment list
        list_widget = self._create_equipment_list()
        splitter.addWidget(list_widget)

        # Right side: Equipment details and control
        details_widget = self._create_details_panel()
        splitter.addWidget(details_widget)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter)

    def _create_equipment_list(self) -> QWidget:
        """Create equipment list widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Header
        header = QLabel("<h3>Equipment</h3>")
        layout.addWidget(header)

        # List
        self.equipment_list_widget = QListWidget()
        self.equipment_list_widget.itemSelectionChanged.connect(self._on_equipment_selected)
        layout.addWidget(self.equipment_list_widget)

        # Buttons
        button_layout = QHBoxLayout()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        button_layout.addWidget(refresh_btn)

        discover_btn = QPushButton("Discover")
        discover_btn.clicked.connect(self.discover_equipment)
        button_layout.addWidget(discover_btn)

        layout.addLayout(button_layout)

        return widget

    def _create_details_panel(self) -> QWidget:
        """Create equipment details panel."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Equipment info group
        info_group = QGroupBox("Equipment Information")
        info_layout = QGridLayout()

        self.name_label = QLabel("No equipment selected")
        self.name_label.setStyleSheet("font-weight: bold; font-size: 14pt;")
        info_layout.addWidget(QLabel("Name:"), 0, 0)
        info_layout.addWidget(self.name_label, 0, 1)

        self.type_label = QLabel("-")
        info_layout.addWidget(QLabel("Type:"), 1, 0)
        info_layout.addWidget(self.type_label, 1, 1)

        self.manufacturer_label = QLabel("-")
        info_layout.addWidget(QLabel("Manufacturer:"), 2, 0)
        info_layout.addWidget(self.manufacturer_label, 2, 1)

        self.model_label = QLabel("-")
        info_layout.addWidget(QLabel("Model:"), 3, 0)
        info_layout.addWidget(self.model_label, 3, 1)

        self.resource_label = QLabel("-")
        info_layout.addWidget(QLabel("Resource:"), 4, 0)
        info_layout.addWidget(self.resource_label, 4, 1)

        self.status_label = QLabel("-")
        info_layout.addWidget(QLabel("Status:"), 5, 0)
        info_layout.addWidget(self.status_label, 5, 1)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # Connection control
        connection_group = QGroupBox("Connection Control")
        connection_layout = QHBoxLayout()

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.connect_equipment)
        self.connect_btn.setEnabled(False)
        connection_layout.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self.disconnect_equipment)
        self.disconnect_btn.setEnabled(False)
        connection_layout.addWidget(self.disconnect_btn)

        connection_group.setLayout(connection_layout)
        layout.addWidget(connection_group)

        # Readings group
        readings_group = QGroupBox("Current Readings")
        readings_layout = QVBoxLayout()

        self.readings_display = QTextEdit()
        self.readings_display.setReadOnly(True)
        self.readings_display.setMaximumHeight(150)
        readings_layout.addWidget(self.readings_display)

        refresh_readings_btn = QPushButton("Refresh Readings")
        refresh_readings_btn.clicked.connect(self.refresh_readings)
        readings_layout.addWidget(refresh_readings_btn)

        readings_group.setLayout(readings_layout)
        layout.addWidget(readings_group)

        # Commands group
        commands_group = QGroupBox("Send Command")
        commands_layout = QVBoxLayout()

        command_input_layout = QHBoxLayout()
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("Enter SCPI command...")
        command_input_layout.addWidget(self.command_input)

        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self.send_command)
        command_input_layout.addWidget(send_btn)

        commands_layout.addLayout(command_input_layout)

        self.command_output = QTextEdit()
        self.command_output.setReadOnly(True)
        self.command_output.setMaximumHeight(100)
        commands_layout.addWidget(self.command_output)

        commands_group.setLayout(commands_layout)
        layout.addWidget(commands_group)

        layout.addStretch()

        return widget

    def set_client(self, client: LabLinkClient):
        """Set API client.

        Args:
            client: LabLink API client
        """
        self.client = client

    def refresh(self):
        """Refresh equipment list."""
        if not self.client:
            return

        try:
            equipment_data = self.client.list_equipment()
            self.equipment_list.clear()

            for eq_data in equipment_data:
                equipment = Equipment.from_api_dict(eq_data)
                self.equipment_list.append(equipment)

            self._update_equipment_list_widget()

        except Exception as e:
            logger.error(f"Error refreshing equipment list: {e}")
            QMessageBox.warning(self, "Error", f"Failed to refresh equipment list: {str(e)}")

    def _update_equipment_list_widget(self):
        """Update equipment list widget."""
        self.equipment_list_widget.clear()

        for equipment in self.equipment_list:
            status_icon = "●" if equipment.connection_status == ConnectionStatus.CONNECTED else "○"
            item_text = f"{status_icon} {equipment.name} ({equipment.model})"

            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, equipment.equipment_id)

            self.equipment_list_widget.addItem(item)

    def _on_equipment_selected(self):
        """Handle equipment selection."""
        selected_items = self.equipment_list_widget.selectedItems()
        if not selected_items:
            return

        equipment_id = selected_items[0].data(Qt.ItemDataRole.UserRole)

        # Find equipment in list
        for equipment in self.equipment_list:
            if equipment.equipment_id == equipment_id:
                self.selected_equipment = equipment
                self._update_details_panel()
                self.equipment_selected.emit(equipment_id)
                break

    def _update_details_panel(self):
        """Update details panel with selected equipment."""
        if not self.selected_equipment:
            return

        eq = self.selected_equipment

        self.name_label.setText(eq.name)
        self.type_label.setText(eq.equipment_type.value)
        self.manufacturer_label.setText(eq.manufacturer)
        self.model_label.setText(eq.model)
        self.resource_label.setText(eq.resource_name)

        # Update status with color
        status_text = eq.connection_status.value.upper()
        if eq.connection_status == ConnectionStatus.CONNECTED:
            self.status_label.setText(f"<span style='color: green;'>{status_text}</span>")
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
        else:
            self.status_label.setText(f"<span style='color: red;'>{status_text}</span>")
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)

        # Update readings if available
        if eq.current_readings:
            self.readings_display.setPlainText(self._format_readings(eq.current_readings))

    def _format_readings(self, readings: dict) -> str:
        """Format readings for display."""
        lines = []
        for key, value in readings.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)

    def discover_equipment(self):
        """Discover available equipment."""
        if not self.client:
            QMessageBox.warning(self, "Not Connected", "Please connect to a server first")
            return

        try:
            # Call discover endpoint
            response = self.client._session.post(f"{self.client.api_base_url}/equipment/discover")
            response.raise_for_status()

            data = response.json()
            discovered_count = data.get("discovered_count", 0)

            QMessageBox.information(
                self, "Discovery Complete",
                f"Discovered {discovered_count} device(s)"
            )

            self.refresh()

        except Exception as e:
            logger.error(f"Error discovering equipment: {e}")
            QMessageBox.warning(self, "Error", f"Discovery failed: {str(e)}")

    def connect_equipment(self):
        """Connect to selected equipment."""
        if not self.selected_equipment or not self.client:
            return

        try:
            result = self.client.connect_equipment(self.selected_equipment.equipment_id)

            if result.get("success"):
                QMessageBox.information(self, "Success", "Equipment connected successfully")
                self.refresh()
                self._on_equipment_selected()  # Refresh details
            else:
                QMessageBox.warning(self, "Failed", result.get("message", "Connection failed"))

        except Exception as e:
            logger.error(f"Error connecting equipment: {e}")
            QMessageBox.critical(self, "Error", f"Connection failed: {str(e)}")

    def disconnect_equipment(self):
        """Disconnect from selected equipment."""
        if not self.selected_equipment or not self.client:
            return

        try:
            result = self.client.disconnect_equipment(self.selected_equipment.equipment_id)

            if result.get("success"):
                QMessageBox.information(self, "Success", "Equipment disconnected successfully")
                self.refresh()
                self._on_equipment_selected()  # Refresh details
            else:
                QMessageBox.warning(self, "Failed", result.get("message", "Disconnection failed"))

        except Exception as e:
            logger.error(f"Error disconnecting equipment: {e}")
            QMessageBox.critical(self, "Error", f"Disconnection failed: {str(e)}")

    def refresh_readings(self):
        """Refresh current readings from equipment."""
        if not self.selected_equipment or not self.client:
            return

        try:
            result = self.client.get_readings(self.selected_equipment.equipment_id)

            if result.get("success"):
                readings = result.get("readings", {})
                self.selected_equipment.current_readings = readings
                self.readings_display.setPlainText(self._format_readings(readings))
            else:
                QMessageBox.warning(self, "Failed", "Could not retrieve readings")

        except Exception as e:
            logger.error(f"Error getting readings: {e}")
            QMessageBox.warning(self, "Error", f"Failed to get readings: {str(e)}")

    def send_command(self):
        """Send custom command to equipment."""
        if not self.selected_equipment or not self.client:
            return

        command = self.command_input.text().strip()
        if not command:
            return

        try:
            result = self.client.send_command(
                self.selected_equipment.equipment_id,
                command,
                {}
            )

            if result.get("success"):
                output = result.get("result", "Command executed")
                self.command_output.append(f"> {command}\n{output}\n")
                self.command_input.clear()
            else:
                error = result.get("error", "Command failed")
                self.command_output.append(f"> {command}\nERROR: {error}\n")

        except Exception as e:
            logger.error(f"Error sending command: {e}")
            self.command_output.append(f"> {command}\nERROR: {str(e)}\n")
