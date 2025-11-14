"""Multi-instrument synchronization panel for LabLink GUI."""

import logging
from typing import Optional, Dict, List
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QMessageBox,
    QComboBox, QDoubleSpinBox, QFormLayout, QCheckBox,
    QLineEdit, QTextEdit, QTableWidget, QTableWidgetItem,
    QHeaderView
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from client.api.client import LabLinkClient
from models import SyncState

logger = logging.getLogger(__name__)


class SyncPanel(QWidget):
    """Panel for multi-instrument synchronization management."""

    # Signals
    sync_group_created = pyqtSignal(str)  # group_id
    sync_group_started = pyqtSignal(str)  # group_id
    sync_group_stopped = pyqtSignal(str)  # group_id

    def __init__(self, parent=None):
        """Initialize synchronization panel."""
        super().__init__(parent)

        self.client: Optional[LabLinkClient] = None
        self.sync_groups: Dict[str, Dict] = {}  # group_id -> group info
        self.current_group_id: Optional[str] = None
        self.available_equipment: List[Dict] = []
        self.available_acquisitions: Dict[str, List[str]] = {}  # equipment_id -> [acquisition_ids]

        # Auto-refresh timer
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._auto_refresh)
        self.refresh_timer.setInterval(2000)  # 2 seconds

        self._setup_ui()

    def _setup_ui(self):
        """Set up user interface."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("<h2>Multi-Instrument Synchronization</h2>")
        layout.addWidget(header)

        # Top section: Configuration and group list
        top_layout = QHBoxLayout()

        # Left: Sync group configuration
        config_widget = self._create_config_section()
        top_layout.addWidget(config_widget, stretch=3)

        # Right: Active sync groups
        groups_widget = self._create_groups_section()
        top_layout.addWidget(groups_widget, stretch=2)

        layout.addLayout(top_layout)

        # Bottom section: Group details and equipment status
        details_widget = self._create_details_section()
        layout.addWidget(details_widget, stretch=2)

    def _create_config_section(self) -> QWidget:
        """Create sync group configuration section."""
        group = QGroupBox("Create Synchronization Group")
        layout = QFormLayout()

        # Group ID
        self.group_id_edit = QLineEdit()
        self.group_id_edit.setPlaceholderText("Unique group identifier")
        layout.addRow("Group ID:", self.group_id_edit)

        # Equipment selection (multi-select list)
        self.equipment_list = QListWidget()
        self.equipment_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.equipment_list.setMaximumHeight(150)
        layout.addRow("Equipment:", self.equipment_list)

        # Master equipment
        self.master_combo = QComboBox()
        self.master_combo.addItem("(Auto-select)", None)
        layout.addRow("Master Equipment:", self.master_combo)

        # Sync tolerance
        self.tolerance_spin = QDoubleSpinBox()
        self.tolerance_spin.setRange(0.1, 1000.0)
        self.tolerance_spin.setValue(10.0)
        self.tolerance_spin.setDecimals(1)
        self.tolerance_spin.setSuffix(" ms")
        layout.addRow("Sync Tolerance:", self.tolerance_spin)

        # Wait for all checkbox
        self.wait_for_all_check = QCheckBox("Wait for all equipment before starting")
        self.wait_for_all_check.setChecked(True)
        layout.addRow("", self.wait_for_all_check)

        # Auto-align timestamps
        self.auto_align_check = QCheckBox("Auto-align timestamps")
        self.auto_align_check.setChecked(True)
        layout.addRow("", self.auto_align_check)

        # Control buttons
        button_layout = QHBoxLayout()

        refresh_eq_btn = QPushButton("Refresh Equipment")
        refresh_eq_btn.clicked.connect(self.refresh_equipment)
        button_layout.addWidget(refresh_eq_btn)

        create_btn = QPushButton("Create Group")
        create_btn.clicked.connect(self.create_sync_group)
        button_layout.addWidget(create_btn)

        layout.addRow("", button_layout)

        group.setLayout(layout)
        return group

    def _create_groups_section(self) -> QWidget:
        """Create sync groups list section."""
        group = QGroupBox("Active Sync Groups")
        layout = QVBoxLayout()

        # Groups list
        self.groups_list = QListWidget()
        self.groups_list.itemClicked.connect(self._on_group_selected)
        layout.addWidget(self.groups_list)

        # Group control buttons
        btn_layout = QHBoxLayout()

        self.start_group_btn = QPushButton("Start Group")
        self.start_group_btn.clicked.connect(self.start_sync_group)
        self.start_group_btn.setEnabled(False)
        btn_layout.addWidget(self.start_group_btn)

        self.stop_group_btn = QPushButton("Stop Group")
        self.stop_group_btn.clicked.connect(self.stop_sync_group)
        self.stop_group_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_group_btn)

        layout.addLayout(btn_layout)

        # More controls
        btn_layout2 = QHBoxLayout()

        self.pause_group_btn = QPushButton("Pause")
        self.pause_group_btn.clicked.connect(self.pause_sync_group)
        self.pause_group_btn.setEnabled(False)
        btn_layout2.addWidget(self.pause_group_btn)

        self.resume_group_btn = QPushButton("Resume")
        self.resume_group_btn.clicked.connect(self.resume_sync_group)
        self.resume_group_btn.setEnabled(False)
        btn_layout2.addWidget(self.resume_group_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self.delete_sync_group)
        btn_layout2.addWidget(delete_btn)

        layout.addLayout(btn_layout2)

        # Auto-refresh
        self.auto_refresh_check = QCheckBox("Auto-refresh")
        self.auto_refresh_check.setChecked(True)
        self.auto_refresh_check.toggled.connect(self._toggle_auto_refresh)
        layout.addWidget(self.auto_refresh_check)

        group.setLayout(layout)
        return group

    def _create_details_section(self) -> QWidget:
        """Create group details section."""
        group = QGroupBox("Group Details")
        layout = QVBoxLayout()

        # Group info text
        self.group_info_text = QTextEdit()
        self.group_info_text.setReadOnly(True)
        self.group_info_text.setMaximumHeight(100)
        layout.addWidget(QLabel("Group Information:"))
        layout.addWidget(self.group_info_text)

        # Equipment/acquisition mapping table
        self.equipment_table = QTableWidget()
        self.equipment_table.setColumnCount(3)
        self.equipment_table.setHorizontalHeaderLabels(["Equipment ID", "Acquisition ID", "Status"])
        self.equipment_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(QLabel("Equipment & Acquisitions:"))
        layout.addWidget(self.equipment_table)

        # Add/remove acquisition buttons
        btn_layout = QHBoxLayout()

        self.add_acq_combo = QComboBox()
        self.add_acq_combo.setPlaceholderText("Select acquisition to add...")
        btn_layout.addWidget(self.add_acq_combo, stretch=2)

        add_acq_btn = QPushButton("Add to Group")
        add_acq_btn.clicked.connect(self.add_acquisition_to_group)
        btn_layout.addWidget(add_acq_btn, stretch=1)

        layout.addLayout(btn_layout)

        group.setLayout(layout)
        return group

    def _on_group_selected(self, item: QListWidgetItem):
        """Handle group selection."""
        group_id = item.data(Qt.ItemDataRole.UserRole)
        self.current_group_id = group_id

        if group_id in self.sync_groups:
            group = self.sync_groups[group_id]
            self._update_group_info(group)
            self._update_control_buttons(group.get("status", {}).get("state", "idle"))
            self._load_group_acquisitions(group)

    def _update_group_info(self, group: Dict):
        """Update group info display."""
        status = group.get("status", {})
        info_text = f"""
Group ID: {group.get('group_id', 'N/A')}
State: {status.get('state', 'N/A')}
Equipment Count: {status.get('equipment_count', 0)}
Master: {status.get('master', 'None')}
Ready Equipment: {status.get('ready_count', 0)}/{status.get('equipment_count', 0)}
        """.strip()
        self.group_info_text.setText(info_text)

    def _update_control_buttons(self, state: str):
        """Update control button states based on group state."""
        self.start_group_btn.setEnabled(state in ["idle", "ready", "stopped"])
        self.stop_group_btn.setEnabled(state in ["running", "paused"])
        self.pause_group_btn.setEnabled(state == "running")
        self.resume_group_btn.setEnabled(state == "paused")

    def _load_group_acquisitions(self, group: Dict):
        """Load and display group acquisitions."""
        status = group.get("status", {})
        acquisition_ids = status.get("acquisition_ids", {})

        self.equipment_table.setRowCount(len(acquisition_ids))

        for row, (equipment_id, acquisition_id) in enumerate(acquisition_ids.items()):
            self.equipment_table.setItem(row, 0, QTableWidgetItem(equipment_id))
            self.equipment_table.setItem(row, 1, QTableWidgetItem(acquisition_id))
            self.equipment_table.setItem(row, 2, QTableWidgetItem("Ready"))

    def _toggle_auto_refresh(self, enabled: bool):
        """Toggle auto-refresh."""
        if enabled:
            self.refresh_timer.start()
        else:
            self.refresh_timer.stop()

    def _auto_refresh(self):
        """Auto-refresh groups."""
        if self.client:
            self.refresh_groups(silent=True)

    def set_client(self, client: LabLinkClient):
        """Set API client."""
        self.client = client
        self.refresh_equipment()
        self.refresh_groups()

        if self.auto_refresh_check.isChecked():
            self.refresh_timer.start()

    def refresh_equipment(self):
        """Refresh available equipment list."""
        if not self.client:
            return

        try:
            equipment_list = self.client.list_equipment()
            self.available_equipment = equipment_list

            # Update equipment list widget
            self.equipment_list.clear()
            self.master_combo.clear()
            self.master_combo.addItem("(Auto-select)", None)

            for eq in equipment_list:
                eq_id = eq.get("id")
                eq_name = eq.get("model", "Unknown")
                eq_type = eq.get("type", "")

                # Add to multi-select list
                item = QListWidgetItem(f"{eq_name} ({eq_type})")
                item.setData(Qt.ItemDataRole.UserRole, eq_id)
                self.equipment_list.addItem(item)

                # Add to master combo
                self.master_combo.addItem(f"{eq_name} ({eq_type})", eq_id)

            # Also refresh available acquisitions
            self.refresh_acquisitions()

        except Exception as e:
            logger.error(f"Error refreshing equipment: {e}")

    def refresh_acquisitions(self):
        """Refresh available acquisition sessions."""
        if not self.client:
            return

        try:
            sessions = self.client.list_acquisition_sessions()
            self.available_acquisitions.clear()

            # Group acquisitions by equipment
            for session in sessions:
                equipment_id = session.get("equipment_id")
                acquisition_id = session.get("acquisition_id")

                if equipment_id not in self.available_acquisitions:
                    self.available_acquisitions[equipment_id] = []

                self.available_acquisitions[equipment_id].append(acquisition_id)

            # Update add acquisition combo
            self.add_acq_combo.clear()
            for eq_id, acq_ids in self.available_acquisitions.items():
                for acq_id in acq_ids:
                    self.add_acq_combo.addItem(
                        f"{eq_id}: {acq_id[:8]}...",
                        (eq_id, acq_id)
                    )

        except Exception as e:
            logger.error(f"Error refreshing acquisitions: {e}")

    def refresh_groups(self, silent: bool = False):
        """Refresh sync groups list."""
        if not self.client:
            return

        try:
            groups = self.client.list_sync_groups()
            self.sync_groups.clear()
            self.groups_list.clear()

            for group in groups:
                group_id = group.get("group_id")

                # Get detailed status
                try:
                    status = self.client.get_sync_group_status(group_id)
                    group["status"] = status.get("status", {})
                except Exception as e:
                    logger.warning(f"Could not get status for group {group_id}: {e}")
                    group["status"] = {}

                self.sync_groups[group_id] = group

                # Add to list
                state = group.get("status", {}).get("state", "unknown")
                eq_count = group.get("status", {}).get("equipment_count", "?")

                item_text = f"{group_id} [{state}] ({eq_count} equipment)"
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, group_id)
                self.groups_list.addItem(item)

            if not silent:
                logger.info(f"Refreshed {len(groups)} sync groups")

        except Exception as e:
            if not silent:
                logger.error(f"Error refreshing sync groups: {e}")

    def create_sync_group(self):
        """Create new sync group."""
        if not self.client:
            QMessageBox.warning(self, "Not Connected", "Please connect to a server first")
            return

        group_id = self.group_id_edit.text().strip()
        if not group_id:
            QMessageBox.warning(self, "Invalid Input", "Please enter a group ID")
            return

        # Get selected equipment
        selected_items = self.equipment_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Equipment", "Please select at least one equipment")
            return

        equipment_ids = [item.data(Qt.ItemDataRole.UserRole) for item in selected_items]

        try:
            result = self.client.create_sync_group(
                group_id=group_id,
                equipment_ids=equipment_ids,
                master_equipment_id=self.master_combo.currentData(),
                sync_tolerance_ms=self.tolerance_spin.value(),
                wait_for_all=self.wait_for_all_check.isChecked(),
                auto_align_timestamps=self.auto_align_check.isChecked()
            )

            if result.get("success"):
                QMessageBox.information(self, "Success", f"Sync group '{group_id}' created")
                self.sync_group_created.emit(group_id)
                self.refresh_groups()
                self.group_id_edit.clear()
        except Exception as e:
            logger.error(f"Error creating sync group: {e}")
            QMessageBox.critical(self, "Error", f"Failed to create group:\n{str(e)}")

    def add_acquisition_to_group(self):
        """Add acquisition to current sync group."""
        if not self.current_group_id:
            QMessageBox.warning(self, "No Group Selected", "Please select a sync group first")
            return

        data = self.add_acq_combo.currentData()
        if not data:
            QMessageBox.warning(self, "No Acquisition", "Please select an acquisition")
            return

        equipment_id, acquisition_id = data

        try:
            result = self.client.add_to_sync_group(
                self.current_group_id,
                equipment_id,
                acquisition_id
            )

            if result.get("success"):
                QMessageBox.information(self, "Success", "Acquisition added to group")
                self.refresh_groups()
        except Exception as e:
            logger.error(f"Error adding acquisition to group: {e}")
            QMessageBox.critical(self, "Error", f"Failed to add:\n{str(e)}")

    def start_sync_group(self):
        """Start synchronized acquisition."""
        if not self.current_group_id:
            QMessageBox.warning(self, "No Group", "Please select a sync group first")
            return

        try:
            result = self.client.start_sync_group(self.current_group_id)
            if result.get("success"):
                QMessageBox.information(self, "Success", "Sync group started")
                self.sync_group_started.emit(self.current_group_id)
                self.refresh_groups()
        except Exception as e:
            logger.error(f"Error starting sync group: {e}")
            QMessageBox.critical(self, "Error", f"Failed to start:\n{str(e)}")

    def stop_sync_group(self):
        """Stop synchronized acquisition."""
        if not self.current_group_id:
            return

        try:
            result = self.client.stop_sync_group(self.current_group_id)
            if result.get("success"):
                QMessageBox.information(self, "Success", "Sync group stopped")
                self.sync_group_stopped.emit(self.current_group_id)
                self.refresh_groups()
        except Exception as e:
            logger.error(f"Error stopping sync group: {e}")
            QMessageBox.critical(self, "Error", f"Failed to stop:\n{str(e)}")

    def pause_sync_group(self):
        """Pause synchronized acquisition."""
        if not self.current_group_id:
            return

        try:
            result = self.client.pause_sync_group(self.current_group_id)
            if result.get("success"):
                QMessageBox.information(self, "Success", "Sync group paused")
                self.refresh_groups()
        except Exception as e:
            logger.error(f"Error pausing sync group: {e}")
            QMessageBox.critical(self, "Error", f"Failed to pause:\n{str(e)}")

    def resume_sync_group(self):
        """Resume synchronized acquisition."""
        if not self.current_group_id:
            return

        try:
            result = self.client.resume_sync_group(self.current_group_id)
            if result.get("success"):
                QMessageBox.information(self, "Success", "Sync group resumed")
                self.refresh_groups()
        except Exception as e:
            logger.error(f"Error resuming sync group: {e}")
            QMessageBox.critical(self, "Error", f"Failed to resume:\n{str(e)}")

    def delete_sync_group(self):
        """Delete current sync group."""
        if not self.current_group_id:
            QMessageBox.warning(self, "No Group", "Please select a sync group first")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete sync group '{self.current_group_id}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                result = self.client.delete_sync_group(self.current_group_id)
                if result.get("success"):
                    QMessageBox.information(self, "Success", "Sync group deleted")
                    self.current_group_id = None
                    self.refresh_groups()
            except Exception as e:
                logger.error(f"Error deleting sync group: {e}")
                QMessageBox.critical(self, "Error", f"Failed to delete:\n{str(e)}")

    def closeEvent(self, event):
        """Handle widget close event."""
        self.refresh_timer.stop()
        event.accept()
