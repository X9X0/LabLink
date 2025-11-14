"""Alarm monitoring panel for LabLink GUI."""

import logging
import asyncio
from typing import Optional, Dict, Set
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QColor
import qasync

from client.api.client import LabLinkClient

logger = logging.getLogger(__name__)


class AlarmWebSocketSignals(QObject):
    """Qt signals for WebSocket callbacks (thread-safe)."""

    alarm_event_received = pyqtSignal(dict)  # New alarm event
    alarm_updated = pyqtSignal(dict)  # Alarm state changed
    alarm_cleared = pyqtSignal(str)  # Alarm cleared (event_id)


class AlarmPanel(QWidget):
    """Panel for alarm monitoring and management."""

    def __init__(self, parent=None):
        """Initialize alarm panel."""
        super().__init__(parent)

        self.client: Optional[LabLinkClient] = None

        # WebSocket streaming state
        self.ws_signals = AlarmWebSocketSignals()
        self.alarm_streaming_active = False

        self._setup_ui()
        self._connect_ws_signals()

    def _setup_ui(self):
        """Set up user interface."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("<h2>Alarms & Notifications</h2>")
        layout.addWidget(header)

        # Active alarms table
        self.alarms_table = QTableWidget()
        self.alarms_table.setColumnCount(5)
        self.alarms_table.setHorizontalHeaderLabels([
            "Event ID", "Alarm Name", "Severity", "Status", "Timestamp"
        ])
        self.alarms_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.alarms_table)

        # Buttons
        button_layout = QHBoxLayout()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        button_layout.addWidget(refresh_btn)

        acknowledge_btn = QPushButton("Acknowledge Selected")
        acknowledge_btn.clicked.connect(self.acknowledge_alarm)
        button_layout.addWidget(acknowledge_btn)

        layout.addLayout(button_layout)

    def set_client(self, client: LabLinkClient):
        """Set API client."""
        self.client = client
        self._register_ws_handlers()

    def _connect_ws_signals(self):
        """Connect WebSocket signals to slot handlers."""
        self.ws_signals.alarm_event_received.connect(self._on_alarm_event)
        self.ws_signals.alarm_updated.connect(self._on_alarm_updated)
        self.ws_signals.alarm_cleared.connect(self._on_alarm_cleared)

    def _register_ws_handlers(self):
        """Register WebSocket message handlers with the client."""
        if not self.client or not self.client.ws_manager:
            return

        # Register handlers with WebSocket manager
        try:
            # Register for alarm event notifications
            # Note: This assumes the server will broadcast alarm events via WebSocket
            # If not implemented yet, this will fail gracefully
            logger.info("Registering WebSocket alarm event handlers")
            # The WebSocket manager should have methods to subscribe to alarm events
            # For now, we'll use a generic message handler
            if hasattr(self.client.ws_manager, 'on_alarm_event'):
                self.client.ws_manager.on_alarm_event(self._ws_alarm_callback)
            logger.info("Registered WebSocket alarm handlers for alarm panel")
        except Exception as e:
            logger.warning(f"Could not register WebSocket alarm handlers: {e}")
            logger.info("Alarm panel will use polling fallback")

    def _ws_alarm_callback(self, message: Dict):
        """WebSocket callback for alarm events (runs in WebSocket thread).

        This emits a Qt signal for thread-safe GUI updates.

        Args:
            message: WebSocket message with alarm event data
        """
        event_type = message.get("type")
        event_data = message.get("data", {})

        if event_type == "alarm_event":
            # New alarm event
            self.ws_signals.alarm_event_received.emit(event_data)
        elif event_type == "alarm_updated":
            # Alarm state changed (acknowledged, etc.)
            self.ws_signals.alarm_updated.emit(event_data)
        elif event_type == "alarm_cleared":
            # Alarm cleared
            event_id = event_data.get("event_id")
            if event_id:
                self.ws_signals.alarm_cleared.emit(event_id)

    def _on_alarm_event(self, event: Dict):
        """Handle new alarm event in GUI thread (thread-safe).

        Args:
            event: Alarm event data
        """
        logger.info(f"Received alarm event: {event.get('event_id')} - {event.get('alarm_name')}")

        # Refresh the entire table to show new alarm
        # In a more optimized version, we could just add the single row
        self.refresh()

    def _on_alarm_updated(self, event: Dict):
        """Handle alarm update in GUI thread (thread-safe).

        Args:
            event: Updated alarm event data
        """
        logger.info(f"Alarm updated: {event.get('event_id')}")

        # Refresh to show updated state
        self.refresh()

    def _on_alarm_cleared(self, event_id: str):
        """Handle alarm cleared in GUI thread (thread-safe).

        Args:
            event_id: ID of cleared alarm event
        """
        logger.info(f"Alarm cleared: {event_id}")

        # Refresh to remove cleared alarm from active list
        self.refresh()

    def refresh(self):
        """Refresh alarm data."""
        if not self.client:
            return

        try:
            events = self.client.get_active_alarm_events()
            self.alarms_table.setRowCount(len(events))

            for row, event in enumerate(events):
                self.alarms_table.setItem(row, 0, QTableWidgetItem(event.get("event_id", "")))
                self.alarms_table.setItem(row, 1, QTableWidgetItem(event.get("alarm_name", "")))

                severity = event.get("severity", "")
                severity_item = QTableWidgetItem(severity)

                # Color code by severity
                if severity == "critical":
                    severity_item.setBackground(QColor(255, 200, 200))
                elif severity == "error":
                    severity_item.setBackground(QColor(255, 230, 200))
                elif severity == "warning":
                    severity_item.setBackground(QColor(255, 255, 200))

                self.alarms_table.setItem(row, 2, severity_item)
                self.alarms_table.setItem(row, 3, QTableWidgetItem(event.get("state", "")))
                self.alarms_table.setItem(row, 4, QTableWidgetItem(event.get("timestamp", "")))

        except Exception as e:
            logger.error(f"Error refreshing alarms: {e}")

    def acknowledge_alarm(self):
        """Acknowledge selected alarm."""
        current_row = self.alarms_table.currentRow()
        if current_row < 0:
            return

        event_id = self.alarms_table.item(current_row, 0).text()

        try:
            self.client.acknowledge_alarm(event_id)
            self.refresh()
        except Exception as e:
            logger.error(f"Error acknowledging alarm: {e}")
