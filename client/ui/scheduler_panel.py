"""Scheduler management panel for LabLink GUI."""

import logging
import asyncio
from typing import Optional, Dict, Set
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
import qasync

from api.client import LabLinkClient

logger = logging.getLogger(__name__)


class SchedulerWebSocketSignals(QObject):
    """Qt signals for WebSocket callbacks (thread-safe)."""

    job_created = pyqtSignal(dict)  # New job created
    job_updated = pyqtSignal(dict)  # Job configuration updated
    job_deleted = pyqtSignal(str)  # Job deleted (job_id)
    job_started = pyqtSignal(dict)  # Job execution started
    job_completed = pyqtSignal(dict)  # Job execution completed
    job_failed = pyqtSignal(dict)  # Job execution failed


class SchedulerPanel(QWidget):
    """Panel for scheduler management."""

    def __init__(self, parent=None):
        """Initialize scheduler panel."""
        super().__init__(parent)

        self.client: Optional[LabLinkClient] = None

        # WebSocket streaming state
        self.ws_signals = SchedulerWebSocketSignals()
        self.scheduler_streaming_active = False

        self._setup_ui()
        self._connect_ws_signals()

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
        self._register_ws_handlers()

    def _connect_ws_signals(self):
        """Connect WebSocket signals to slot handlers."""
        self.ws_signals.job_created.connect(self._on_job_created)
        self.ws_signals.job_updated.connect(self._on_job_updated)
        self.ws_signals.job_deleted.connect(self._on_job_deleted)
        self.ws_signals.job_started.connect(self._on_job_started)
        self.ws_signals.job_completed.connect(self._on_job_completed)
        self.ws_signals.job_failed.connect(self._on_job_failed)

    def _register_ws_handlers(self):
        """Register WebSocket message handlers with the client."""
        if not self.client or not self.client.ws_manager:
            return

        # Register handlers with WebSocket manager
        try:
            # Register for scheduler event notifications
            # Note: This assumes the server will broadcast scheduler events via WebSocket
            # If not implemented yet, this will fail gracefully
            logger.info("Registering WebSocket scheduler event handlers")
            # The WebSocket manager should have methods to subscribe to scheduler events
            if hasattr(self.client.ws_manager, 'on_scheduler_event'):
                self.client.ws_manager.on_scheduler_event(self._ws_scheduler_callback)
            logger.info("Registered WebSocket scheduler handlers for scheduler panel")
        except Exception as e:
            logger.warning(f"Could not register WebSocket scheduler handlers: {e}")
            logger.info("Scheduler panel will use polling fallback")

    def _ws_scheduler_callback(self, message: Dict):
        """WebSocket callback for scheduler events (runs in WebSocket thread).

        This emits a Qt signal for thread-safe GUI updates.

        Args:
            message: WebSocket message with scheduler event data
        """
        event_type = message.get("type")
        event_data = message.get("data", {})

        if event_type == "job_created":
            self.ws_signals.job_created.emit(event_data)
        elif event_type == "job_updated":
            self.ws_signals.job_updated.emit(event_data)
        elif event_type == "job_deleted":
            job_id = event_data.get("job_id")
            if job_id:
                self.ws_signals.job_deleted.emit(job_id)
        elif event_type == "job_started":
            self.ws_signals.job_started.emit(event_data)
        elif event_type == "job_completed":
            self.ws_signals.job_completed.emit(event_data)
        elif event_type == "job_failed":
            self.ws_signals.job_failed.emit(event_data)

    def _on_job_created(self, job: Dict):
        """Handle new job creation in GUI thread (thread-safe).

        Args:
            job: Job data
        """
        logger.info(f"Job created: {job.get('job_id')} - {job.get('name')}")
        self.refresh()

    def _on_job_updated(self, job: Dict):
        """Handle job update in GUI thread (thread-safe).

        Args:
            job: Updated job data
        """
        logger.info(f"Job updated: {job.get('job_id')}")
        self.refresh()

    def _on_job_deleted(self, job_id: str):
        """Handle job deletion in GUI thread (thread-safe).

        Args:
            job_id: ID of deleted job
        """
        logger.info(f"Job deleted: {job_id}")
        self.refresh()

    def _on_job_started(self, execution: Dict):
        """Handle job execution start in GUI thread (thread-safe).

        Args:
            execution: Job execution data
        """
        job_id = execution.get("job_id")
        logger.info(f"Job started: {job_id}")
        # Optionally show a status indicator or notification
        # For now, just refresh to show updated state
        self.refresh()

    def _on_job_completed(self, execution: Dict):
        """Handle job execution completion in GUI thread (thread-safe).

        Args:
            execution: Job execution result data
        """
        job_id = execution.get("job_id")
        logger.info(f"Job completed: {job_id}")
        self.refresh()

    def _on_job_failed(self, execution: Dict):
        """Handle job execution failure in GUI thread (thread-safe).

        Args:
            execution: Job execution failure data
        """
        job_id = execution.get("job_id")
        error = execution.get("error", "Unknown error")
        logger.warning(f"Job failed: {job_id} - {error}")
        # Could show a notification dialog here
        self.refresh()

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
