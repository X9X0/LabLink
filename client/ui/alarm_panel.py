"""Alarm monitoring panel for LabLink GUI."""

import logging
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from api.client import LabLinkClient

logger = logging.getLogger(__name__)


class AlarmPanel(QWidget):
    """Panel for alarm monitoring and management."""

    def __init__(self, parent=None):
        """Initialize alarm panel."""
        super().__init__(parent)

        self.client: Optional[LabLinkClient] = None

        self._setup_ui()

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
