"""Data acquisition panel for LabLink GUI."""

import logging
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QListWidget, QMessageBox, QComboBox,
    QSpinBox, QFormLayout
)
from PyQt6.QtCore import Qt

from api.client import LabLinkClient

logger = logging.getLogger(__name__)


class AcquisitionPanel(QWidget):
    """Panel for data acquisition control and visualization."""

    def __init__(self, parent=None):
        """Initialize acquisition panel."""
        super().__init__(parent)

        self.client: Optional[LabLinkClient] = None

        self._setup_ui()

    def _setup_ui(self):
        """Set up user interface."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("<h2>Data Acquisition</h2>")
        layout.addWidget(header)

        # Configuration group
        config_group = QGroupBox("Acquisition Configuration")
        config_layout = QFormLayout()

        self.equipment_combo = QComboBox()
        config_layout.addRow("Equipment:", self.equipment_combo)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["continuous", "single_shot", "triggered"])
        config_layout.addRow("Mode:", self.mode_combo)

        self.sample_rate_spin = QSpinBox()
        self.sample_rate_spin.setRange(1, 1000000)
        self.sample_rate_spin.setValue(1000)
        config_layout.addRow("Sample Rate (Hz):", self.sample_rate_spin)

        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 3600)
        self.duration_spin.setValue(10)
        config_layout.addRow("Duration (s):", self.duration_spin)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # Control buttons
        button_layout = QHBoxLayout()

        start_btn = QPushButton("Start Acquisition")
        start_btn.clicked.connect(self.start_acquisition)
        button_layout.addWidget(start_btn)

        stop_btn = QPushButton("Stop")
        stop_btn.clicked.connect(self.stop_acquisition)
        button_layout.addWidget(stop_btn)

        layout.addLayout(button_layout)

        # Active acquisitions list
        sessions_group = QGroupBox("Active Sessions")
        sessions_layout = QVBoxLayout()

        self.sessions_list = QListWidget()
        sessions_layout.addWidget(self.sessions_list)

        sessions_group.setLayout(sessions_layout)
        layout.addWidget(sessions_group)

        # Placeholder for visualization
        viz_label = QLabel("<i>Real-time visualization will appear here</i>")
        viz_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(viz_label)

        layout.addStretch()

    def set_client(self, client: LabLinkClient):
        """Set API client."""
        self.client = client

    def refresh(self):
        """Refresh acquisition data."""
        if not self.client:
            return

        try:
            # Refresh equipment list
            equipment_list = self.client.list_equipment()
            self.equipment_combo.clear()
            for eq in equipment_list:
                self.equipment_combo.addItem(
                    eq.get("name", "Unknown"),
                    eq.get("equipment_id")
                )

            # Refresh active sessions
            sessions = self.client.list_acquisitions()
            self.sessions_list.clear()
            for session in sessions:
                self.sessions_list.addItem(
                    f"{session['acquisition_id']} - {session.get('status', 'unknown')}"
                )

        except Exception as e:
            logger.error(f"Error refreshing acquisition panel: {e}")

    def start_acquisition(self):
        """Start data acquisition."""
        if not self.client:
            QMessageBox.warning(self, "Not Connected", "Please connect to a server first")
            return

        equipment_id = self.equipment_combo.currentData()
        if not equipment_id:
            QMessageBox.warning(self, "No Equipment", "Please select equipment")
            return

        try:
            config = {
                "mode": self.mode_combo.currentText(),
                "sample_rate_hz": self.sample_rate_spin.value(),
                "duration_seconds": self.duration_spin.value()
            }

            result = self.client.create_acquisition(equipment_id, config)
            acquisition_id = result.get("acquisition", {}).get("acquisition_id")

            if acquisition_id:
                self.client.start_acquisition(acquisition_id)
                QMessageBox.information(self, "Success", "Acquisition started")
                self.refresh()

        except Exception as e:
            logger.error(f"Error starting acquisition: {e}")
            QMessageBox.critical(self, "Error", f"Failed to start acquisition: {str(e)}")

    def stop_acquisition(self):
        """Stop data acquisition."""
        # TODO: Implement stop functionality
        QMessageBox.information(self, "Info", "Stop functionality not yet implemented")
