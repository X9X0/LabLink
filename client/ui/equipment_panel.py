"""Equipment control panel for LabLink GUI."""

import asyncio
import logging
from typing import Dict, List, Optional, Set

from models.equipment import ConnectionStatus, Equipment
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox,
                             QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                             QLineEdit, QListWidget, QListWidgetItem,
                             QMessageBox, QPushButton, QSplitter, QTextEdit,
                             QVBoxLayout, QWidget)

from client.api.client import LabLinkClient

logger = logging.getLogger(__name__)


class DiscoverySettingsDialog(QDialog):
    """Dialog for configuring discovery settings."""

    def __init__(self, client, parent=None):
        """Initialize discovery settings dialog."""
        super().__init__(parent)
        self.client = client
        self.setWindowTitle("Discovery Settings")
        self.setModal(True)
        self.resize(400, 300)

        layout = QVBoxLayout(self)

        # Header
        header = QLabel("<h3>Equipment Discovery Settings</h3>")
        layout.addWidget(header)

        info = QLabel("Enable the types of equipment you want to discover:")
        info.setWordWrap(True)
        layout.addWidget(info)

        # Settings group
        settings_group = QGroupBox("Scan Types")
        settings_layout = QVBoxLayout()

        self.tcpip_checkbox = QCheckBox("TCPIP/Network devices")
        settings_layout.addWidget(self.tcpip_checkbox)

        self.usb_checkbox = QCheckBox("USB devices")
        settings_layout.addWidget(self.usb_checkbox)

        self.serial_checkbox = QCheckBox("Serial devices (COM/ttyUSB)")
        settings_layout.addWidget(self.serial_checkbox)

        self.gpib_checkbox = QCheckBox("GPIB devices")
        settings_layout.addWidget(self.gpib_checkbox)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Load current settings
        self._load_settings()

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_settings(self):
        """Load current discovery settings from server."""
        try:
            settings = self.client.get_discovery_settings()
            self.tcpip_checkbox.setChecked(settings.get("scan_tcpip", True))
            self.usb_checkbox.setChecked(settings.get("scan_usb", True))
            self.serial_checkbox.setChecked(settings.get("scan_serial", False))
            self.gpib_checkbox.setChecked(settings.get("scan_gpib", False))
        except Exception as e:
            logger.error(f"Error loading discovery settings: {e}")
            # Use defaults
            self.tcpip_checkbox.setChecked(True)
            self.usb_checkbox.setChecked(True)
            self.serial_checkbox.setChecked(False)
            self.gpib_checkbox.setChecked(False)

    def get_settings(self):
        """Get selected settings as a dictionary."""
        return {
            "scan_tcpip": self.tcpip_checkbox.isChecked(),
            "scan_usb": self.usb_checkbox.isChecked(),
            "scan_serial": self.serial_checkbox.isChecked(),
            "scan_gpib": self.gpib_checkbox.isChecked(),
        }


class WebSocketSignals(QObject):
    """Qt signals for WebSocket callbacks (thread-safe)."""

    stream_data_received = pyqtSignal(str, dict)  # equipment_id, data
    stream_started = pyqtSignal(str)  # equipment_id
    stream_stopped = pyqtSignal(str)  # equipment_id


class EquipmentPanel(QWidget):
    """Panel for equipment control and monitoring."""

    equipment_selected = pyqtSignal(str)  # equipment_id

    def __init__(self, parent=None):
        """Initialize equipment panel."""
        super().__init__(parent)

        self.client: Optional[LabLinkClient] = None
        self.equipment_list: List[Equipment] = []
        self.selected_equipment: Optional[Equipment] = None

        # WebSocket streaming state
        self.ws_signals = WebSocketSignals()
        self.streaming_equipment: Set[str] = (
            set()
        )  # Track equipment with active streams

        self._setup_ui()
        self._connect_ws_signals()

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
        self.equipment_list_widget.itemSelectionChanged.connect(
            self._on_equipment_selected
        )
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
        self._register_ws_handlers()

    def _connect_ws_signals(self):
        """Connect WebSocket signals to slot handlers."""
        self.ws_signals.stream_data_received.connect(self._on_stream_data)
        self.ws_signals.stream_started.connect(self._on_stream_started)
        self.ws_signals.stream_stopped.connect(self._on_stream_stopped)

    def _register_ws_handlers(self):
        """Register WebSocket message handlers with the client."""
        if not self.client or not self.client.ws_manager:
            return

        # Register handlers with WebSocket manager
        try:
            self.client.ws_manager.on_stream_data(self._ws_stream_data_callback)
            logger.info("Registered WebSocket stream handlers for equipment panel")
        except Exception as e:
            logger.warning(f"Could not register WebSocket handlers: {e}")

    def _ws_stream_data_callback(self, message: Dict):
        """WebSocket callback for stream data (runs in WebSocket thread).

        This emits a Qt signal for thread-safe GUI updates.

        Args:
            message: WebSocket message with stream data
        """
        equipment_id = message.get("equipment_id")
        data = message.get("data", {})

        if equipment_id:
            # Emit signal to update GUI thread
            self.ws_signals.stream_data_received.emit(equipment_id, data)

    def _on_stream_data(self, equipment_id: str, data: Dict):
        """Handle stream data in GUI thread (thread-safe).

        Args:
            equipment_id: ID of equipment sending data
            data: Stream data dictionary
        """
        # Only update if this is the selected equipment
        if (
            self.selected_equipment
            and self.selected_equipment.equipment_id == equipment_id
        ):
            # Update readings display
            self.readings_display.setPlainText(self._format_readings(data))

            # Update equipment object
            self.selected_equipment.current_readings = data

    def _on_stream_started(self, equipment_id: str):
        """Handle stream started notification.

        Args:
            equipment_id: ID of equipment with started stream
        """
        self.streaming_equipment.add(equipment_id)
        logger.info(f"Stream started for equipment {equipment_id}")

    def _on_stream_stopped(self, equipment_id: str):
        """Handle stream stopped notification.

        Args:
            equipment_id: ID of equipment with stopped stream
        """
        self.streaming_equipment.discard(equipment_id)
        logger.info(f"Stream stopped for equipment {equipment_id}")

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
            QMessageBox.warning(
                self, "Error", f"Failed to refresh equipment list: {str(e)}"
            )

    def _update_equipment_list_widget(self):
        """Update equipment list widget."""
        self.equipment_list_widget.clear()

        for equipment in self.equipment_list:
            status_icon = (
                "●"
                if equipment.connection_status == ConnectionStatus.CONNECTED
                else "○"
            )
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
            self.status_label.setText(
                f"<span style='color: green;'>{status_text}</span>"
            )
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
        else:
            self.status_label.setText(f"<span style='color: red;'>{status_text}</span>")
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)

        # Update readings if available
        if eq.current_readings:
            self.readings_display.setPlainText(
                self._format_readings(eq.current_readings)
            )

    def _format_readings(self, readings: dict) -> str:
        """Format readings for display."""
        lines = []
        for key, value in readings.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)

    async def _start_equipment_stream(self, equipment_id: str):
        """Start WebSocket stream for equipment (async).

        Args:
            equipment_id: ID of equipment to stream from
        """
        if (
            not self.client
            or not self.client.ws_manager
            or not self.client.ws_manager.connected
        ):
            logger.debug("WebSocket not available - using polling fallback")
            return

        try:
            logger.info(f"Starting equipment stream for {equipment_id}")
            await self.client.start_equipment_stream(
                equipment_id=equipment_id,
                stream_type="readings",
                interval_ms=500,  # 2 Hz update rate
            )
            self.ws_signals.stream_started.emit(equipment_id)
            logger.info(f"Stream started successfully for {equipment_id}")

        except Exception as e:
            logger.warning(f"Could not start equipment stream: {e}")
            # Fall back to polling - no error shown to user

    async def _stop_equipment_stream(self, equipment_id: str):
        """Stop WebSocket stream for equipment (async).

        Args:
            equipment_id: ID of equipment to stop streaming
        """
        if not self.client or not self.client.ws_manager:
            return

        try:
            logger.info(f"Stopping equipment stream for {equipment_id}")
            await self.client.stop_equipment_stream(equipment_id)
            self.ws_signals.stream_stopped.emit(equipment_id)
            logger.info(f"Stream stopped for {equipment_id}")

        except Exception as e:
            logger.warning(f"Could not stop equipment stream: {e}")

    def discover_equipment(self):
        """Discover available equipment."""
        if not self.client:
            QMessageBox.warning(
                self, "Not Connected", "Please connect to a server first"
            )
            return

        # Show settings dialog (blocking is OK here - happens before async work)
        settings_dialog = DiscoverySettingsDialog(self.client, self)
        if settings_dialog.exec() != QDialog.DialogCode.Accepted:
            return

        # Get settings and start async discovery
        settings = settings_dialog.get_settings()
        logger.info(f"Applying discovery settings: {settings}")

        # Start async discovery (non-blocking)
        asyncio.create_task(self._discover_equipment_async(settings))

    async def _discover_equipment_async(self, settings: dict):
        """Perform equipment discovery asynchronously (non-blocking).

        Args:
            settings: Discovery settings dictionary
        """
        try:
            # Update settings on server (async)
            await self.client.update_discovery_settings_async(**settings)

            # Call discover endpoint (async - this is the long-running operation)
            data = await self.client.discover_equipment_async()
            resources = data.get("resources", [])
            discovered_count = len(resources)

            # Use QTimer to schedule UI updates on the main Qt thread
            # This prevents blocking the event loop from async context
            from PyQt6.QtCore import QTimer

            if discovered_count > 0:
                # Schedule the dialog to show on the main thread
                QTimer.singleShot(0, lambda: self._show_connect_dialog(resources))
            else:
                QTimer.singleShot(0, lambda: QMessageBox.information(
                    self, "Discovery Complete",
                    "No devices found.\n\nTry enabling different scan types (Serial, GPIB) or check your connections."
                ))
                QTimer.singleShot(100, self.refresh)

        except Exception as e:
            logger.error(f"Error discovering equipment: {e}")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: QMessageBox.warning(
                self, "Error", f"Discovery failed: {str(e)}"
            ))

    def _show_connect_dialog(self, resources):
        """Show connect dialog on main thread after discovery completes.

        Args:
            resources: List of discovered resource strings
        """
        from client.ui.connect_dialog import ConnectDeviceDialog
        connect_dialog = ConnectDeviceDialog(resources, self.client, self)
        if connect_dialog.exec() == QDialog.DialogCode.Accepted:
            # Device was connected, refresh the list
            self.refresh()
        else:
            # User cancelled, still refresh in case something changed
            self.refresh()

    def connect_equipment(self):
        """Connect to selected equipment."""
        if not self.selected_equipment or not self.client:
            return

        try:
            result = self.client.connect_equipment(self.selected_equipment.equipment_id)

            if result.get("success"):
                QMessageBox.information(
                    self, "Success", "Equipment connected successfully"
                )
                self.refresh()
                self._on_equipment_selected()  # Refresh details

                # Auto-start WebSocket streaming for connected equipment
                equipment_id = self.selected_equipment.equipment_id
                asyncio.create_task(self._start_equipment_stream(equipment_id))
            else:
                QMessageBox.warning(
                    self, "Failed", result.get("message", "Connection failed")
                )

        except Exception as e:
            logger.error(f"Error connecting equipment: {e}")
            QMessageBox.critical(self, "Error", f"Connection failed: {str(e)}")

    def disconnect_equipment(self):
        """Disconnect from selected equipment."""
        if not self.selected_equipment or not self.client:
            return

        equipment_id = self.selected_equipment.equipment_id

        try:
            # Stop streaming first
            if equipment_id in self.streaming_equipment:
                asyncio.create_task(self._stop_equipment_stream(equipment_id))

            result = self.client.disconnect_equipment(equipment_id)

            if result.get("success"):
                QMessageBox.information(
                    self, "Success", "Equipment disconnected successfully"
                )
                self.refresh()
                self._on_equipment_selected()  # Refresh details
            else:
                QMessageBox.warning(
                    self, "Failed", result.get("message", "Disconnection failed")
                )

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
                self.selected_equipment.equipment_id, command, {}
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
