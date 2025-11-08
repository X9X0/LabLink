"""Scheduler management panel for LabLink GUI."""

import logging
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt

from api.client import LabLinkClient

logger = logging.getLogger(__name__)


class SchedulerPanel(QWidget):
    """Panel for scheduler management."""

    def __init__(self, parent=None):
        """Initialize scheduler panel."""
        super().__init__(parent)

        self.client: Optional[LabLinkClient] = None

        self._setup_ui()

    def _setup_ui(self):
        """Set up user interface."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("<h2>Scheduled Jobs</h2>")
        layout.addWidget(header)

        # Jobs table
        self.jobs_table = QTableWidget()
        self.jobs_table.setColumnCount(5)
        self.jobs_table.setHorizontalHeaderLabels([
            "Job ID", "Name", "Type", "Trigger", "Enabled"
        ])
        self.jobs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.jobs_table)

        # Buttons
        button_layout = QHBoxLayout()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        button_layout.addWidget(refresh_btn)

        run_now_btn = QPushButton("Run Now")
        run_now_btn.clicked.connect(self.run_job_now)
        button_layout.addWidget(run_now_btn)

        layout.addLayout(button_layout)

    def set_client(self, client: LabLinkClient):
        """Set API client."""
        self.client = client

    def refresh(self):
        """Refresh scheduler data."""
        if not self.client:
            return

        try:
            jobs = self.client.list_jobs()
            self.jobs_table.setRowCount(len(jobs))

            for row, job in enumerate(jobs):
                self.jobs_table.setItem(row, 0, QTableWidgetItem(job.get("job_id", "")))
                self.jobs_table.setItem(row, 1, QTableWidgetItem(job.get("name", "")))
                self.jobs_table.setItem(row, 2, QTableWidgetItem(job.get("schedule_type", "")))
                self.jobs_table.setItem(row, 3, QTableWidgetItem(job.get("trigger_type", "")))
                self.jobs_table.setItem(row, 4, QTableWidgetItem(str(job.get("enabled", False))))

        except Exception as e:
            logger.error(f"Error refreshing scheduler: {e}")

    def run_job_now(self):
        """Run selected job immediately."""
        current_row = self.jobs_table.currentRow()
        if current_row < 0:
            return

        job_id = self.jobs_table.item(current_row, 0).text()

        try:
            self.client.run_job_now(job_id)
            self.refresh()
        except Exception as e:
            logger.error(f"Error running job: {e}")
