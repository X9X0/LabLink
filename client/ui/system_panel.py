"""System Management panel for LabLink GUI."""

import logging
from typing import Optional

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from client.api.client import LabLinkClient
from client.ui.theme import dialog_palette

logger = logging.getLogger(__name__)


class AsyncWorker(QThread):
    """Worker thread for async operations to prevent GUI blocking."""

    finished = pyqtSignal(object)  # Emits result when done
    error = pyqtSignal(str)  # Emits error message if failed

    def __init__(self, func, *args, **kwargs):
        """Initialize worker.

        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
        """
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        """Execute the function in background thread."""
        try:
            result = self.func(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            logger.error(f"Async worker error: {e}")
            self.error.emit(str(e))


class UpdateDialog(QDialog):
    """Dialog for configuring update parameters."""

    def __init__(self, parent=None):
        """Initialize update dialog."""
        super().__init__(parent)
        _c = dialog_palette()
        self.setWindowTitle("Server Update Configuration")
        self.setModal(True)
        self.resize(400, 200)

        layout = QVBoxLayout(self)

        # Git remote
        remote_layout = QHBoxLayout()
        remote_layout.addWidget(QLabel("Git Remote:"))
        self.remote_input = QLineEdit("origin")
        remote_layout.addWidget(self.remote_input)
        layout.addLayout(remote_layout)

        # Git branch
        branch_layout = QHBoxLayout()
        branch_layout.addWidget(QLabel("Git Branch:"))
        self.branch_input = QLineEdit()
        self.branch_input.setPlaceholderText("(current branch)")
        branch_layout.addWidget(self.branch_input)
        layout.addLayout(branch_layout)

        # Warning
        warning = QLabel(
            "⚠️ WARNING: This will pull latest code from git.\n"
            "In Docker environments, a rebuild and restart will be required."
        )
        warning.setStyleSheet("color: {warn_text}; padding: 10px;".format(**_c))
        warning.setWordWrap(True)
        layout.addWidget(warning)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_config(self):
        """Get update configuration.

        Returns:
            Tuple of (git_remote, git_branch or None)
        """
        remote = self.remote_input.text().strip() or "origin"
        branch = self.branch_input.text().strip() or None
        return remote, branch


class SystemPanel(QWidget):
    """Panel for system management and server updates."""

    def __init__(self, parent=None):
        """Initialize system panel."""
        super().__init__(parent)

        self.client: Optional[LabLinkClient] = None
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._poll_update_status)

        self._setup_ui()

    def _setup_ui(self):
        """Set up user interface."""
        _c = dialog_palette()

        layout = QVBoxLayout(self)

        # Header
        header = QLabel("<h2>System Management</h2>")
        layout.addWidget(header)

        # Update notification banner (hidden by default)
        self.notification_banner = QLabel()
        self.notification_banner.setWordWrap(True)
        self.notification_banner.setStyleSheet("background-color: {warn_bg}; color: {warn_text}; padding: 10px; border-radius: 5px; font-weight: bold;".format(**_c))
        self.notification_banner.hide()
        layout.addWidget(self.notification_banner)

        # Server Information Group
        server_info_group = QGroupBox("Server Information")
        server_info_layout = QVBoxLayout()

        self.version_label = QLabel("Version: Loading...")
        server_info_layout.addWidget(self.version_label)

        self.status_label = QLabel("Status: Unknown")
        server_info_layout.addWidget(self.status_label)

        server_info_group.setLayout(server_info_layout)
        layout.addWidget(server_info_group)

        # Update Controls Group
        update_group = QGroupBox("Server Updates")
        update_layout = QVBoxLayout()

        # Update mode selection
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Update Mode:"))
        self.update_mode_combo = QComboBox()
        self.update_mode_combo.addItem("Stable (VERSION releases)", "stable")
        self.update_mode_combo.addItem("Development (all commits)", "development")
        self.update_mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.update_mode_combo)

        mode_info = QLabel("ℹ️ Stable tracks version releases, Development tracks all commits")
        mode_info.setWordWrap(True)
        mode_info.setStyleSheet("color: {muted_text}; font-size: 10px;".format(**_c))

        update_layout.addLayout(mode_layout)
        update_layout.addWidget(mode_info)

        # Version selector (for stable mode - git tags)
        self.version_selector_widget = QWidget()
        version_selector_layout = QHBoxLayout(self.version_selector_widget)
        version_selector_layout.setContentsMargins(0, 0, 0, 0)

        version_selector_layout.addWidget(QLabel("Select Version:"))
        self.version_selector = QComboBox()
        self.version_selector.setMinimumWidth(500)  # Allow longer version names to be visible
        version_selector_layout.addWidget(self.version_selector)

        self.refresh_versions_btn = QPushButton("Refresh Versions")
        self.refresh_versions_btn.clicked.connect(self._populate_versions)
        version_selector_layout.addWidget(self.refresh_versions_btn)

        version_selector_layout.addStretch()

        self.version_selector_widget.show()  # Shown by default (stable mode)
        update_layout.addWidget(self.version_selector_widget)

        # Branch selector (for development mode)
        self.branch_selector_widget = QWidget()
        branch_selector_layout = QVBoxLayout(self.branch_selector_widget)
        branch_selector_layout.setContentsMargins(0, 0, 0, 0)
        branch_selector_layout.setSpacing(3)

        # First row: Branch dropdown and refresh button
        branch_row1 = QHBoxLayout()
        branch_row1.addWidget(QLabel("Track Branch:"))
        self.branch_combo = QComboBox()
        self.branch_combo.setMinimumWidth(500)  # Allow longer branch names to be visible
        self.branch_combo.currentIndexChanged.connect(self._on_branch_changed)
        branch_row1.addWidget(self.branch_combo)

        self.refresh_branches_btn = QPushButton("Refresh Branches")
        self.refresh_branches_btn.clicked.connect(self._refresh_branches)
        branch_row1.addWidget(self.refresh_branches_btn)

        branch_row1.addStretch()
        branch_selector_layout.addLayout(branch_row1)

        # Second row: Show all branches checkbox
        branch_row2 = QHBoxLayout()
        self.show_all_branches_checkbox = QCheckBox("Show all branches (including inactive)")
        self.show_all_branches_checkbox.setStyleSheet("""
            QCheckBox {{
                background: transparent;
                border: none;
                font-size: 9px;
                color: {muted_text};
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border: 2px solid {accent};
                border-radius: 3px;
                background: {field_bg};
            }}
            QCheckBox::indicator:checked {{
                background: {accent};
                border: 2px solid {accent};
            }}
        """.format(**_c))
        self.show_all_branches_checkbox.setToolTip(
            "When unchecked, only shows current and active branches (with commits in last 6 months).\n"
            "When checked, shows all branches sorted by most recent."
        )
        self.show_all_branches_checkbox.stateChanged.connect(self._refresh_branches)
        branch_row2.addWidget(self.show_all_branches_checkbox)
        branch_row2.addStretch()
        branch_selector_layout.addLayout(branch_row2)

        self.branch_selector_widget.hide()  # Hidden by default (stable mode)
        update_layout.addWidget(self.branch_selector_widget)

        # Check server version button
        check_version_layout = QHBoxLayout()
        self.check_version_btn = QPushButton("Check Connected Server Version")
        self.check_version_btn.clicked.connect(self._check_and_display_version)
        self.check_version_btn.setToolTip("Compare currently connected server version with local git")
        check_version_layout.addWidget(self.check_version_btn)

        # Keep old buttons but hide them (for backward compatibility with existing methods)
        self.check_updates_btn = QPushButton("Check for Updates")
        self.check_updates_btn.clicked.connect(self.check_for_updates)
        self.check_updates_btn.hide()

        self.start_update_btn = QPushButton("Update Server")
        self.start_update_btn.clicked.connect(self.start_update)
        self.start_update_btn.hide()

        self.rollback_btn = QPushButton("Rollback")
        self.rollback_btn.clicked.connect(self.rollback)
        check_version_layout.addWidget(self.rollback_btn)

        self.rebuild_btn = QPushButton("Rebuild Now")
        self.rebuild_btn.clicked.connect(self.execute_rebuild)
        check_version_layout.addWidget(self.rebuild_btn)

        check_version_layout.addStretch()
        update_layout.addLayout(check_version_layout)

        # Update status and progress bar
        self.update_status_label = QLabel("Update Status: Idle")
        update_layout.addWidget(self.update_status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        update_layout.addWidget(self.progress_bar)

        # Separator
        separator1 = QLabel("─" * 120)
        separator1.setStyleSheet("color: {panel_border};".format(**_c))
        update_layout.addWidget(separator1)

        # Side-by-side layout for Local and Remote sections
        side_by_side_layout = QHBoxLayout()
        side_by_side_layout.setSpacing(15)

        # ========== Local Server Section ==========
        local_section = QWidget()
        local_section.setStyleSheet("""
            QWidget {{
                background-color: {panel_bg};
                border: 1px solid {panel_border};
                border-radius: 6px;
            }}
        """.format(**_c))
        local_layout = QVBoxLayout(local_section)
        local_layout.setContentsMargins(8, 8, 8, 8)

        local_server_label = QLabel("<b>🖥️  Local Server</b>")
        local_server_label.setStyleSheet("background: transparent; border: none;")
        local_layout.addWidget(local_server_label)

        # Spacing
        local_layout.addSpacing(2)

        # Checkbox for automatic rebuild (local)
        self.auto_docker_rebuild_local = QCheckBox("Auto-rebuild")
        self.auto_docker_rebuild_local.setChecked(True)
        self.auto_docker_rebuild_local.setToolTip(
            "If enabled, will try to rebuild Docker containers automatically. "
            "If disabled or if automatic fails, manual instructions will be shown."
        )
        self.auto_docker_rebuild_local.setStyleSheet("""
            QCheckBox {{
                background: transparent;
                border: none;
                font-weight: bold;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 2px solid {accent};
                border-radius: 3px;
                background: {field_bg};
            }}
            QCheckBox::indicator:checked {{
                background: {accent};
                border: 2px solid {accent};
            }}
            QCheckBox::indicator:checked:hover {{
                background: {accent_hover};
            }}
        """.format(**_c))
        local_layout.addWidget(self.auto_docker_rebuild_local)

        # Push button to bottom
        local_layout.addStretch()

        # Update button
        self.update_local_server_btn = QPushButton("Update Local Server")
        self.update_local_server_btn.clicked.connect(self._update_local_server)
        self.update_local_server_btn.setToolTip(
            "Checkout selected version/branch locally and rebuild Docker containers on this machine"
        )
        local_layout.addWidget(self.update_local_server_btn)

        # ========== Vertical Separator ==========
        separator_frame = QFrame()
        separator_frame.setFrameShape(QFrame.Shape.VLine)
        separator_frame.setFrameShadow(QFrame.Shadow.Sunken)
        separator_frame.setStyleSheet("color: {panel_border};".format(**_c))

        # ========== Remote Server Section ==========
        remote_section = QWidget()
        remote_section.setStyleSheet("""
            QWidget {{
                background-color: {panel_bg};
                border: 1px solid {panel_border};
                border-radius: 6px;
            }}
        """.format(**_c))
        remote_layout = QVBoxLayout(remote_section)
        remote_layout.setContentsMargins(8, 8, 8, 8)

        remote_server_label = QLabel("<b>🌐  Remote Server</b>")
        remote_server_label.setStyleSheet("background: transparent; border: none;")
        remote_layout.addWidget(remote_server_label)

        # Spacing
        remote_layout.addSpacing(2)

        # SSH configuration with label on same line
        ssh_layout = QHBoxLayout()
        ssh_label = QLabel("SSH:")
        ssh_label.setStyleSheet("background: transparent; border: none; font-size: 9px; font-weight: bold;")
        ssh_layout.addWidget(ssh_label)

        self.ssh_host_input = QLineEdit()
        self.ssh_host_input.setPlaceholderText("user@hostname")
        self.ssh_host_input.setToolTip(
            "SSH connection string for remote server.\n"
            "Format: username@hostname or username@ip-address\n"
            "Example: pi@192.168.1.100"
        )
        ssh_layout.addWidget(self.ssh_host_input)
        remote_layout.addLayout(ssh_layout)

        # Where LabLink lives on that host. This used to be taken from the
        # local checkout, so the update sent a Windows path to a Raspberry
        # Pi and died on the first cd.
        path_layout = QHBoxLayout()
        path_label = QLabel("Path:")
        path_label.setStyleSheet(
            "background: transparent; border: none; font-size: 9px; font-weight: bold;"
        )
        path_layout.addWidget(path_label)

        self.remote_path_input = QLineEdit()
        self.remote_path_input.setText("/opt/lablink")
        self.remote_path_input.setPlaceholderText("/opt/lablink")
        self.remote_path_input.setToolTip(
            "The LabLink checkout on the remote host.\n"
            "It must be a git checkout; the image builder and the SSH "
            "deploy wizard both create one."
        )
        path_layout.addWidget(self.remote_path_input)
        remote_layout.addLayout(path_layout)

        # Checkbox for automatic rebuild (remote)
        self.auto_docker_rebuild_remote = QCheckBox("Auto-rebuild")
        self.auto_docker_rebuild_remote.setChecked(True)
        self.auto_docker_rebuild_remote.setToolTip(
            "If enabled, will try to rebuild Docker containers on remote host via SSH. "
            "If disabled or if automatic fails, manual instructions will be shown."
        )
        self.auto_docker_rebuild_remote.setStyleSheet("""
            QCheckBox {{
                background: transparent;
                border: none;
                font-weight: bold;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 2px solid {accent};
                border-radius: 3px;
                background: {field_bg};
            }}
            QCheckBox::indicator:checked {{
                background: {accent};
                border: 2px solid {accent};
            }}
            QCheckBox::indicator:checked:hover {{
                background: {accent_hover};
            }}
        """.format(**_c))
        remote_layout.addWidget(self.auto_docker_rebuild_remote)

        # Push button to bottom
        remote_layout.addStretch()

        # Update button
        self.update_remote_server_btn = QPushButton("Update Remote Server")
        self.update_remote_server_btn.clicked.connect(self._update_remote_server)
        self.update_remote_server_btn.setToolTip(
            "Checkout selected version/branch locally and rebuild Docker containers on remote host via SSH"
        )
        remote_layout.addWidget(self.update_remote_server_btn)

        # Add sections to side-by-side layout with equal stretch
        side_by_side_layout.addWidget(local_section, 1)  # Equal stretch factor
        side_by_side_layout.addWidget(separator_frame, 0)  # No stretch
        side_by_side_layout.addWidget(remote_section, 1)  # Equal stretch factor

        # Add side-by-side layout to update layout
        update_layout.addLayout(side_by_side_layout)

        # Close the Server Updates group
        update_group.setLayout(update_layout)
        layout.addWidget(update_group)

        # Configuration Group (Client, Auto-Rebuild, Scheduled Checks side-by-side)
        config_group = QGroupBox("Additional Configuration")
        config_group_layout = QVBoxLayout()

        # Side-by-side layout for three configuration sections
        config_side_by_side_layout = QHBoxLayout()
        config_side_by_side_layout.setSpacing(15)

        # ========== Client Self-Update Section ==========
        client_section = QWidget()
        client_section.setStyleSheet("""
            QWidget {{
                background-color: {panel_bg};
                border: 1px solid {panel_border};
                border-radius: 6px;
            }}
        """.format(**_c))
        client_layout = QVBoxLayout(client_section)
        client_layout.setContentsMargins(8, 8, 8, 8)

        client_label = QLabel("<b>📱 Client Self-Update</b>")
        client_label.setStyleSheet("background: transparent; border: none;")
        client_layout.addWidget(client_label)

        client_layout.addSpacing(2)

        # Push button to bottom
        client_layout.addStretch()

        self.update_client_btn = QPushButton("Update Client")
        self.update_client_btn.clicked.connect(self._update_client)
        self.update_client_btn.setToolTip("Update client to selected version/branch and restart")
        client_layout.addWidget(self.update_client_btn)

        # ========== Vertical Separator 1 ==========
        separator_frame1 = QFrame()
        separator_frame1.setFrameShape(QFrame.Shape.VLine)
        separator_frame1.setFrameShadow(QFrame.Shadow.Sunken)
        separator_frame1.setStyleSheet("color: {panel_border};".format(**_c))

        # ========== Auto-Rebuild Section ==========
        auto_rebuild_section = QWidget()
        auto_rebuild_section.setStyleSheet("""
            QWidget {{
                background-color: {panel_bg};
                border: 1px solid {panel_border};
                border-radius: 6px;
            }}
        """.format(**_c))
        auto_rebuild_layout = QVBoxLayout(auto_rebuild_section)
        auto_rebuild_layout.setContentsMargins(8, 8, 8, 8)

        auto_rebuild_label = QLabel("<b>🔧 Automatic Rebuild</b>")
        auto_rebuild_label.setStyleSheet("background: transparent; border: none;")
        auto_rebuild_layout.addWidget(auto_rebuild_label)

        auto_rebuild_layout.addSpacing(2)

        self.auto_rebuild_checkbox = QCheckBox("Enable after updates")
        self.auto_rebuild_checkbox.setStyleSheet("""
            QCheckBox {{
                background: transparent;
                border: none;
                font-weight: bold;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 2px solid {accent};
                border-radius: 3px;
                background: {field_bg};
            }}
            QCheckBox::indicator:checked {{
                background: {accent};
                border: 2px solid {accent};
            }}
            QCheckBox::indicator:checked:hover {{
                background: {accent_hover};
            }}
        """.format(**_c))
        self.auto_rebuild_checkbox.setToolTip("Enable automatic Docker rebuild after updates")
        auto_rebuild_layout.addWidget(self.auto_rebuild_checkbox)

        # Push button to bottom
        auto_rebuild_layout.addStretch()

        self.configure_rebuild_btn = QPushButton("Configure")
        self.configure_rebuild_btn.clicked.connect(self.configure_auto_rebuild)
        auto_rebuild_layout.addWidget(self.configure_rebuild_btn)

        # ========== Vertical Separator 2 ==========
        separator_frame2 = QFrame()
        separator_frame2.setFrameShape(QFrame.Shape.VLine)
        separator_frame2.setFrameShadow(QFrame.Shadow.Sunken)
        separator_frame2.setStyleSheet("color: {panel_border};".format(**_c))

        # ========== Scheduled Checks Section ==========
        scheduled_section = QWidget()
        scheduled_section.setStyleSheet("""
            QWidget {{
                background-color: {panel_bg};
                border: 1px solid {panel_border};
                border-radius: 6px;
            }}
        """.format(**_c))
        scheduled_layout = QVBoxLayout(scheduled_section)
        scheduled_layout.setContentsMargins(8, 8, 8, 8)

        scheduled_label = QLabel("<b>🕒 Scheduled Checks</b>")
        scheduled_label.setStyleSheet("background: transparent; border: none;")
        scheduled_layout.addWidget(scheduled_label)

        scheduled_layout.addSpacing(2)

        # Checkbox and interval on same line
        checkbox_interval_layout = QHBoxLayout()
        self.scheduled_checkbox = QCheckBox("Enable")
        self.scheduled_checkbox.setStyleSheet("""
            QCheckBox {{
                background: transparent;
                border: none;
                font-weight: bold;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 2px solid {accent};
                border-radius: 3px;
                background: {field_bg};
            }}
            QCheckBox::indicator:checked {{
                background: {accent};
                border: 2px solid {accent};
            }}
            QCheckBox::indicator:checked:hover {{
                background: {accent_hover};
            }}
        """.format(**_c))
        self.scheduled_checkbox.setToolTip("Enable automatic update checking")
        checkbox_interval_layout.addWidget(self.scheduled_checkbox)

        interval_label = QLabel("Every:")
        interval_label.setStyleSheet("background: transparent; border: none; font-size: 9px; margin-left: 5px;")
        checkbox_interval_layout.addWidget(interval_label)

        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setRange(1, 168)  # 1 hour to 1 week
        self.interval_spinbox.setValue(24)
        self.interval_spinbox.setFixedWidth(50)
        checkbox_interval_layout.addWidget(self.interval_spinbox)

        hours_label = QLabel("hrs")
        hours_label.setStyleSheet("background: transparent; border: none; font-size: 9px;")
        checkbox_interval_layout.addWidget(hours_label)

        checkbox_interval_layout.addStretch()
        scheduled_layout.addLayout(checkbox_interval_layout)

        # Push button to bottom
        scheduled_layout.addStretch()

        self.configure_scheduled_btn = QPushButton("Configure")
        self.configure_scheduled_btn.clicked.connect(self.configure_scheduled)
        scheduled_layout.addWidget(self.configure_scheduled_btn)

        # Add sections to side-by-side layout with equal stretch
        config_side_by_side_layout.addWidget(client_section, 1)
        config_side_by_side_layout.addWidget(separator_frame1, 0)
        config_side_by_side_layout.addWidget(auto_rebuild_section, 1)
        config_side_by_side_layout.addWidget(separator_frame2, 0)
        config_side_by_side_layout.addWidget(scheduled_section, 1)

        config_group_layout.addLayout(config_side_by_side_layout)
        config_group.setLayout(config_group_layout)
        layout.addWidget(config_group)

        # Update Logs Group
        logs_group = QGroupBox("Update Logs")
        logs_layout = QVBoxLayout()

        self.logs_text = QTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setMaximumHeight(200)
        logs_layout.addWidget(self.logs_text)

        clear_logs_btn = QPushButton("Clear Logs")
        clear_logs_btn.clicked.connect(self.logs_text.clear)
        logs_layout.addWidget(clear_logs_btn)

        logs_group.setLayout(logs_layout)
        layout.addWidget(logs_group)

        # Stretch to fill remaining space
        layout.addStretch()

    def set_client(self, client: LabLinkClient):
        """Set API client."""
        self.client = client
        self._prefill_ssh_from_connection()
        self.refresh()

    def _prefill_ssh_from_connection(self):
        """Offer the connected server as the host to update.

        The client already knows which machine it is talking to, so asking
        the user to type the address again invites a typo that points the
        update at the wrong Pi. The SSH user is remembered per server, since
        it is the one part the API connection cannot tell us.

        Only fills an empty field: whatever the user typed wins.
        """
        if self.ssh_host_input.text().strip():
            return

        host = getattr(self.client, "host", None)
        if not host:
            return

        user = None
        try:
            from client.utils.server_manager import ServerManager

            active = ServerManager().get_active_server()
            if active and active.host == host:
                user = getattr(active, "user", None)
        except Exception as e:
            logger.debug(f"Could not read the saved SSH user: {e}")

        self.ssh_host_input.setText(f"{user}@{host}" if user else host)
        if not user:
            # A bare host would make ssh try the local Windows username.
            self.ssh_host_input.setToolTip(
                f"Add the SSH user for {host}, as user@{host}.\n"
                "It is remembered for this server once the update succeeds."
            )

    def refresh(self):
        """Refresh system information."""
        if not self.client:
            return

        try:
            # Get server version
            version_data = self.client.get_server_version()
            version = version_data.get("version", "Unknown")
            self.version_label.setText(f"Version: {version}")

            # Get update status
            self._update_status_display()

            # Populate versions/branches based on current mode
            mode = self.update_mode_combo.currentData()
            if mode == "stable":
                self._populate_versions()
            else:  # development
                # Branches will be populated when switching to dev mode
                pass

        except Exception as e:
            logger.error(f"Error refreshing system info: {e}")
            QMessageBox.critical(
                self, "Error", f"Failed to refresh system info:\n{str(e)}"
            )

    def _on_mode_changed(self, index: int):
        """Handle update mode selection change."""
        mode = self.update_mode_combo.currentData()

        # Show/hide selectors based on mode (client-side operation, works without API client)
        if mode == "stable":
            # Show version selector, hide branch selector
            self.version_selector_widget.show()
            self.branch_selector_widget.hide()
            # Populate versions when switching to stable mode
            self._populate_versions()
        else:  # development
            # Hide version selector, show branch selector
            self.version_selector_widget.hide()
            self.branch_selector_widget.show()
            # Load branches when switching to dev mode
            self._refresh_branches()

        # Only configure server if client is connected
        if not self.client:
            return

        try:
            self.logs_text.append(f"\n🔧 Changing update mode to: {mode}...")

            result = self.client.configure_update_mode(mode=mode)

            if result.get("success"):
                description = result.get("description", "")
                self.logs_text.append(f"✅ Update mode changed: {description}")

                QMessageBox.information(
                    self,
                    "Update Mode Changed",
                    f"Update mode set to: {mode}\n\n{description}",
                )
            else:
                error = result.get("error", "Unknown error")
                self.logs_text.append(f"❌ Failed to change mode: {error}")
                QMessageBox.critical(
                    self, "Configuration Failed", f"Failed to change update mode:\n{error}"
                )

            self._update_status_display()

        except Exception as e:
            logger.error(f"Error changing update mode: {e}")
            self.logs_text.append(f"\n❌ Error: {str(e)}")
            QMessageBox.critical(
                self, "Error", f"Failed to change update mode:\n{str(e)}"
            )

    def _refresh_branches(self):
        """Refresh the list of available branches (client-side)."""
        from client.utils.git_operations import (
            get_branch_hashes, get_git_branches, get_current_git_branch,
        )

        try:
            show_all = self.show_all_branches_checkbox.isChecked()
            filter_text = "all" if show_all else "active"
            self.logs_text.append(f"\n🌿 Fetching {filter_text} branches...")
            self.refresh_branches_btn.setEnabled(False)
            self.refresh_branches_btn.setText("Loading...")

            # Get branches from local git with filtering
            branches = get_git_branches(show_all=show_all, sort_by_date=True)
            current_branch = get_current_git_branch()
            # A branch name alone does not say which code it is. Two machines
            # both "on main" can be a week apart, and after the update picker
            # sent one install to a branch 30 commits behind there was nothing
            # on screen that would have shown it.
            hashes = get_branch_hashes()

            if branches:
                # Update combo box
                self.branch_combo.blockSignals(True)
                self.branch_combo.clear()

                selected_index = 0
                for i, branch_name in enumerate(branches):
                    # Add indicator for current branch
                    display_name = branch_name
                    is_current = (branch_name == current_branch)

                    if is_current:
                        display_name += " (current)"
                        selected_index = i

                    # The hash is display only; currentData stays the branch
                    # name, which is what the checkout is given.
                    short_hash = hashes.get(branch_name)
                    if short_hash:
                        display_name += f"  [{short_hash}]"

                    self.branch_combo.addItem(display_name, branch_name)

                self.branch_combo.setCurrentIndex(selected_index)
                self.branch_combo.blockSignals(False)

                self.logs_text.append(f"✅ Found {len(branches)} {filter_text} branches (sorted by most recent)")
                if current_branch:
                    self.logs_text.append(f"   Current: {current_branch}")
            else:
                self.logs_text.append("⚠️  No branches found")
                QMessageBox.warning(
                    self,
                    "No Branches Found",
                    "No git branches found in the repository."
                )

        except Exception as e:
            logger.error(f"Error fetching branches: {e}")
            self.logs_text.append(f"\n❌ Error: {str(e)}")
            QMessageBox.critical(
                self, "Error", f"Failed to fetch branches:\n{str(e)}"
            )

        finally:
            self.refresh_branches_btn.setEnabled(True)
            self.refresh_branches_btn.setText("Refresh Branches")

    def _on_branch_changed(self, index: int):
        """Handle branch selection change."""
        if index < 0:
            return

        branch_name = self.branch_combo.currentData()
        if not branch_name:
            return

        # In client-driven mode, just log the selection
        # No need to notify server since client manages all updates
        self.logs_text.append(f"📌 Selected branch: {branch_name}")
        logger.info(f"Branch selected: {branch_name}")

    def _update_status_display(self):
        """Update the status display from server."""
        if not self.client:
            return

        try:
            status_data = self.client.get_update_status()

            # Update mode combo box based on server setting
            update_mode = status_data.get("update_mode", "stable")
            for i in range(self.update_mode_combo.count()):
                if self.update_mode_combo.itemData(i) == update_mode:
                    # Block signals to avoid triggering _on_mode_changed
                    self.update_mode_combo.blockSignals(True)
                    self.update_mode_combo.setCurrentIndex(i)
                    self.update_mode_combo.blockSignals(False)
                    break

            # Show/hide selectors based on mode
            if update_mode == "stable":
                self.version_selector_widget.show()
                self.branch_selector_widget.hide()
            else:  # development
                self.version_selector_widget.hide()
                self.branch_selector_widget.show()

            # Update status label
            status = status_data.get("status", "unknown")
            current_version = status_data.get("current_version", "unknown")
            available_version = status_data.get("available_version")

            status_text = f"Update Status: {status.title()}"
            if available_version:
                status_text += f" (Available: {available_version})"

            self.update_status_label.setText(status_text)

            # Update progress bar
            progress = status_data.get("progress", 0)
            self.progress_bar.setValue(int(progress))

            # Update logs
            logs = status_data.get("logs", [])
            if logs:
                self.logs_text.setText("\n".join(logs))
                # Scroll to bottom
                scrollbar = self.logs_text.verticalScrollBar()
                scrollbar.setValue(scrollbar.maximum())

            # Enable/disable update button based on status
            if status in ["idle", "failed"]:
                self.start_update_btn.setEnabled(available_version is not None)
                self.check_updates_btn.setEnabled(True)
            elif status in ["checking", "downloading", "installing", "restarting"]:
                self.start_update_btn.setEnabled(False)
                self.check_updates_btn.setEnabled(False)
            elif status == "completed":
                self.start_update_btn.setEnabled(False)
                self.check_updates_btn.setEnabled(True)

            # Show error if present
            error = status_data.get("error")
            if error and not self.logs_text.toPlainText().endswith(f"ERROR: {error}"):
                self.logs_text.append(f"\n❌ ERROR: {error}")

            # Show/hide notification banner
            if available_version and status == "idle":
                self.notification_banner.setText(
                    f"🔔 Update Available: {available_version} (Current: {current_version}) - Click 'Update Server' to install"
                )
                self.notification_banner.show()
            else:
                self.notification_banner.hide()

        except Exception as e:
            logger.error(f"Error updating status display: {e}")

    def _poll_update_status(self):
        """Poll update status periodically."""
        self._update_status_display()

    def check_for_updates(self):
        """Check for available updates (async to avoid blocking GUI)."""
        if not self.client:
            return

        # Show config dialog
        dialog = UpdateDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        remote, branch = dialog.get_config()

        self.logs_text.append(
            f"\n🔍 Checking for updates from {remote}/{branch or 'current branch'}..."
        )
        self.check_updates_btn.setEnabled(False)
        self.check_updates_btn.setText("Checking...")

        # Run check in background thread
        self.check_worker = AsyncWorker(
            self.client.check_for_updates,
            git_remote=remote,
            git_branch=branch
        )
        self.check_worker.finished.connect(self._on_check_updates_complete)
        self.check_worker.error.connect(self._on_check_updates_error)
        self.check_worker.start()

    def _on_check_updates_complete(self, result):
        """Handle check updates completion."""
        try:
            if result.get("updates_available"):
                available = result.get("available_version", "unknown")
                current = result.get("current_version", "unknown")
                commits = result.get("commits_behind", 0)

                message = (
                    f"✅ Update available!\n\n"
                    f"Current version: {current}\n"
                    f"Available version: {available}\n"
                    f"Commits behind: {commits}"
                )
                self.logs_text.append(f"\n{message}")

                QMessageBox.information(self, "Update Available", message)
                self.start_update_btn.setEnabled(True)
            else:
                message = result.get("message", "No updates available")
                self.logs_text.append(f"\n✅ {message}")
                QMessageBox.information(self, "No Updates", message)
                self.start_update_btn.setEnabled(False)

            self._update_status_display()

        finally:
            self.check_updates_btn.setEnabled(True)
            self.check_updates_btn.setText("Check for Updates")

    def _on_check_updates_error(self, error):
        """Handle check updates error."""
        logger.error(f"Error checking for updates: {error}")
        self.logs_text.append(f"\n❌ Error: {error}")
        QMessageBox.critical(self, "Error", f"Failed to check for updates:\n{error}")
        self.check_updates_btn.setEnabled(True)
        self.check_updates_btn.setText("Check for Updates")

    def start_update(self):
        """Start server update process."""
        if not self.client:
            return

        # Confirm action
        reply = QMessageBox.question(
            self,
            "Confirm Update",
            "Are you sure you want to update the server?\n\n"
            "This will pull the latest code and may require a rebuild and restart.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            # Show config dialog
            dialog = UpdateDialog(self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            remote, branch = dialog.get_config()

            self.logs_text.append(f"\n🚀 Starting update from {remote}/{branch or 'current branch'}...")
            self.start_update_btn.setEnabled(False)

            # Start update
            result = self.client.start_server_update(
                git_remote=remote, git_branch=branch
            )

            if result.get("success"):
                message = result.get("message", "Update completed")
                self.logs_text.append(f"\n✅ {message}")

                # Check if rebuild is required
                if result.get("requires_rebuild"):
                    rebuild_cmd = result.get("rebuild_command", "")
                    detail_msg = (
                        f"{message}\n\n"
                        f"Docker rebuild required. Run on the server:\n\n"
                        f"{rebuild_cmd}"
                    )
                    QMessageBox.information(self, "Update Downloaded", detail_msg)
                    self.logs_text.append(f"\n📋 Rebuild command:\n{rebuild_cmd}")
                else:
                    QMessageBox.information(
                        self, "Update Complete", f"{message}\n\nRestart the server to apply changes."
                    )

                # Start polling for status updates
                self.update_timer.start(2000)  # Poll every 2 seconds

            else:
                error = result.get("error", "Unknown error")
                self.logs_text.append(f"\n❌ Update failed: {error}")
                QMessageBox.critical(self, "Update Failed", f"Update failed:\n{error}")

            self._update_status_display()

        except Exception as e:
            logger.error(f"Error starting update: {e}")
            self.logs_text.append(f"\n❌ Error: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to start update:\n{str(e)}")

    def rollback(self):
        """Rollback to previous version."""
        if not self.client:
            return

        # Confirm action
        reply = QMessageBox.question(
            self,
            "Confirm Rollback",
            "Are you sure you want to rollback to the previous version?\n\n"
            "This will revert the code to the last backup.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.logs_text.append("\n⏪ Starting rollback...")
            self.rollback_btn.setEnabled(False)

            result = self.client.rollback_server()

            if result.get("success"):
                message = result.get("message", "Rollback completed")
                rolled_back_to = result.get("rolled_back_to", "unknown")
                self.logs_text.append(f"\n✅ {message}")
                self.logs_text.append(f"   Rolled back to version: {rolled_back_to}")

                QMessageBox.information(
                    self,
                    "Rollback Complete",
                    f"{message}\n\nRolled back to: {rolled_back_to}\n\nRestart the server to apply changes.",
                )
            else:
                error = result.get("error", "Unknown error")
                self.logs_text.append(f"\n❌ Rollback failed: {error}")
                QMessageBox.critical(self, "Rollback Failed", f"Rollback failed:\n{error}")

            self._update_status_display()

        except Exception as e:
            logger.error(f"Error during rollback: {e}")
            self.logs_text.append(f"\n❌ Error: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to rollback:\n{str(e)}")

        finally:
            self.rollback_btn.setEnabled(True)

    def configure_auto_rebuild(self):
        """Configure automatic rebuild."""
        if not self.client:
            return

        try:
            enabled = self.auto_rebuild_checkbox.isChecked()

            self.logs_text.append(
                f"\n🔧 Configuring auto-rebuild: {'enabled' if enabled else 'disabled'}..."
            )

            result = self.client.configure_auto_rebuild(enabled=enabled)

            if result.get("success"):
                message = f"Auto-rebuild {'enabled' if enabled else 'disabled'}"
                if result.get("rebuild_command"):
                    message += f"\nRebuild command: {result['rebuild_command']}"

                self.logs_text.append(f"\n✅ {message}")
                QMessageBox.information(self, "Auto-Rebuild Configured", message)
            else:
                error = result.get("error", "Unknown error")
                self.logs_text.append(f"\n❌ Configuration failed: {error}")
                QMessageBox.critical(
                    self, "Configuration Failed", f"Failed to configure auto-rebuild:\n{error}"
                )

        except Exception as e:
            logger.error(f"Error configuring auto-rebuild: {e}")
            self.logs_text.append(f"\n❌ Error: {str(e)}")
            QMessageBox.critical(
                self, "Error", f"Failed to configure auto-rebuild:\n{str(e)}"
            )

    def execute_rebuild(self):
        """Execute manual rebuild."""
        if not self.client:
            return

        # Confirm action
        reply = QMessageBox.question(
            self,
            "Confirm Rebuild",
            "Are you sure you want to rebuild the Docker containers?\n\n"
            "This will rebuild and restart the server.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.logs_text.append("\n🔨 Executing Docker rebuild...")
            self.rebuild_btn.setEnabled(False)

            result = self.client.execute_rebuild()

            if result.get("success"):
                message = result.get("message", "Rebuild completed")
                self.logs_text.append(f"\n✅ {message}")
                QMessageBox.information(self, "Rebuild Complete", message)
            else:
                error = result.get("error", "Unknown error")
                manual_instructions = result.get("manual_instructions", "")

                self.logs_text.append(f"\n❌ Rebuild failed: {error}")

                if manual_instructions:
                    self.logs_text.append(f"\n📋 Manual instructions:\n{manual_instructions}")
                    QMessageBox.warning(
                        self,
                        "Rebuild Failed",
                        f"{error}\n\n{manual_instructions}",
                    )
                else:
                    QMessageBox.critical(self, "Rebuild Failed", f"Rebuild failed:\n{error}")

            self._update_status_display()

        except Exception as e:
            logger.error(f"Error executing rebuild: {e}")
            self.logs_text.append(f"\n❌ Error: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to execute rebuild:\n{str(e)}")

        finally:
            self.rebuild_btn.setEnabled(True)

    def configure_scheduled(self):
        """Configure scheduled update checks."""
        if not self.client:
            return

        try:
            enabled = self.scheduled_checkbox.isChecked()
            interval_hours = self.interval_spinbox.value()

            # Show config dialog for git settings
            dialog = UpdateDialog(self)
            dialog.setWindowTitle("Scheduled Check Configuration")
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            remote, branch = dialog.get_config()

            self.logs_text.append(
                f"\n⏰ Configuring scheduled checks: {'enabled' if enabled else 'disabled'}..."
            )
            self.logs_text.append(f"   Interval: {interval_hours} hours")
            self.logs_text.append(f"   Remote: {remote}/{branch or 'current branch'}")

            result = self.client.configure_scheduled_checks(
                enabled=enabled,
                interval_hours=interval_hours,
                git_remote=remote,
                git_branch=branch,
            )

            if result.get("success"):
                message = f"Scheduled checks {'enabled' if enabled else 'disabled'}"
                if enabled:
                    message += f"\nInterval: {interval_hours} hours"
                    message += f"\nMonitoring: {remote}/{branch or 'current branch'}"

                self.logs_text.append(f"\n✅ {message}")
                QMessageBox.information(self, "Scheduled Checks Configured", message)
            else:
                error = result.get("error", "Unknown error")
                self.logs_text.append(f"\n❌ Configuration failed: {error}")
                QMessageBox.critical(
                    self, "Configuration Failed", f"Failed to configure scheduled checks:\n{error}"
                )

        except Exception as e:
            logger.error(f"Error configuring scheduled checks: {e}")
            self.logs_text.append(f"\n❌ Error: {str(e)}")
            QMessageBox.critical(
                self, "Error", f"Failed to configure scheduled checks:\n{str(e)}"
            )

    def _populate_versions(self):
        """Populate version selector with git tags (client-side)."""
        from client.utils.git_operations import get_git_tags

        try:
            self.logs_text.append("\n🏷️  Fetching git tags...")
            self.refresh_versions_btn.setEnabled(False)
            self.refresh_versions_btn.setText("Loading...")

            # The user pressed Refresh, so actually go and look.
            tags = get_git_tags(fetch=True)

            if tags:
                # Update combo box
                self.version_selector.blockSignals(True)
                self.version_selector.clear()

                for tag in tags:
                    self.version_selector.addItem(tag, tag)

                self.version_selector.blockSignals(False)

                self.logs_text.append(f"✅ Found {len(tags)} versions")
            else:
                self.logs_text.append("⚠️  No git tags found")
                QMessageBox.warning(
                    self,
                    "No Versions Found",
                    "No git tags found in the repository.\n\n"
                    "Create version tags to use stable mode."
                )

        except Exception as e:
            logger.error(f"Error fetching git tags: {e}")
            self.logs_text.append(f"\n❌ Error: {str(e)}")
            QMessageBox.critical(
                self, "Error", f"Failed to fetch git tags:\n{str(e)}"
            )

        finally:
            self.refresh_versions_btn.setEnabled(True)
            self.refresh_versions_btn.setText("Refresh Versions")

    def _check_server_vs_local(self):
        """Compare server version with local git.

        Returns:
            Dict with server_version, local_ref, and update_available
        """
        from client.utils.git_operations import get_git_version_from_tag

        try:
            # Get server version via API
            version_data = self.client.get_server_version()
            server_version = version_data.get("version", "Unknown")

            # Get local version based on mode
            mode = self.update_mode_combo.currentData()

            if mode == "stable":
                # Get selected tag
                local_ref = self.version_selector.currentData()
                if local_ref:
                    local_version = get_git_version_from_tag(local_ref) or local_ref
                else:
                    local_version = "None selected"
            else:  # development
                # Get selected branch
                local_ref = self.branch_combo.currentData()
                local_version = local_ref if local_ref else "None selected"

            # Compare versions
            update_available = (local_ref and local_version != server_version)

            return {
                "server_version": server_version,
                "local_ref": local_ref or "None",
                "local_version": local_version,
                "update_available": update_available
            }

        except Exception as e:
            logger.error(f"Error comparing versions: {e}")
            return {
                "server_version": "Error",
                "local_ref": "Error",
                "local_version": "Error",
                "update_available": False,
                "error": str(e)
            }

    def _check_and_display_version(self):
        """Check server version and compare with local git."""
        if not self.client:
            return

        try:
            self.check_version_btn.setEnabled(False)
            self.check_version_btn.setText("Checking...")

            comparison = self._check_server_vs_local()

            if comparison.get("error"):
                self.logs_text.append(f"\n❌ Error: {comparison['error']}")
                QMessageBox.critical(
                    self, "Error", f"Failed to check version:\n{comparison['error']}"
                )
                return

            server_ver = comparison["server_version"]
            local_ref = comparison["local_ref"]
            local_ver = comparison["local_version"]
            update_available = comparison["update_available"]

            if update_available:
                self.logs_text.append(
                    f"\n⚠️  Server version mismatch:\n"
                    f"   Server: {server_ver}\n"
                    f"   Local: {local_ver} ({local_ref})\n"
                    f"   Update available!"
                )

                self.notification_banner.setText(
                    f"🔔 Server Update Available: {local_ver} (Server: {server_ver})"
                )
                self.notification_banner.show()

                QMessageBox.information(
                    self,
                    "Update Available",
                    f"Server version differs from local:\n\n"
                    f"Server: {server_ver}\n"
                    f"Local: {local_ver} ({local_ref})\n\n"
                    f"Click 'Update Server' to deploy the changes."
                )
            else:
                self.logs_text.append(
                    f"\n✅ Version check:\n"
                    f"   Server: {server_ver}\n"
                    f"   Local: {local_ver} ({local_ref})"
                )

                if server_ver == local_ver:
                    self.notification_banner.hide()
                    QMessageBox.information(
                        self,
                        "No Update Needed",
                        f"Server and local are in sync:\n\nVersion: {server_ver}"
                    )
                else:
                    QMessageBox.information(
                        self,
                        "Version Info",
                        f"Server: {server_ver}\nLocal: {local_ver} ({local_ref})"
                    )

        except Exception as e:
            logger.error(f"Error checking version: {e}")
            self.logs_text.append(f"\n❌ Error: {str(e)}")
            QMessageBox.critical(
                self, "Error", f"Failed to check version:\n{str(e)}"
            )

        finally:
            self.check_version_btn.setEnabled(True)
            self.check_version_btn.setText("Check Connected Server Version")

    def _update_local_server(self):
        """Update local server by checking out git ref and rebuilding Docker locally."""
        from client.utils.git_operations import (
            checkout_git_ref, compare_ref_to_head, get_git_root,
        )
        from client.utils.docker_operations import (
            is_docker_available_locally,
            rebuild_docker_local,
            generate_rebuild_instructions
        )

        try:
            # Get selected ref (tag or branch)
            mode = self.update_mode_combo.currentData()
            if mode == "stable":
                ref = self.version_selector.currentData()
            else:  # development
                ref = self.branch_combo.currentData()

            if not ref:
                QMessageBox.warning(
                    self,
                    "No Version Selected",
                    "Please select a version or branch first."
                )
                return

            # The checkout below is this clone -- the one the client is
            # running from -- so an older ref moves the client's own code
            # backwards as a side effect of a local update.
            position = compare_ref_to_head(ref)
            if position and position["ahead"] == 0 and position["behind"] > 0:
                behind = position["behind"]
                plural = "s" if behind != 1 else ""
                going_back = QMessageBox.warning(
                    self,
                    "This Is Older Than What You Are Running",
                    f"{ref} is {behind} commit{plural} behind the code this "
                    f"client is running.\n\n"
                    f"The checkout is shared, so this moves the client back to "
                    f"it as well.\n\n"
                    f"Continue anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if going_back != QMessageBox.StandardButton.Yes:
                    self.logs_text.append(
                        f"\nLocal server update to {ref} "
                        f"cancelled: {behind} commit{plural} behind HEAD"
                    )
                    return

            # Confirm with user
            reply = QMessageBox.question(
                self,
                "Confirm Local Server Update",
                f"Update LOCAL server to {ref}?\n\n"
                f"This will:\n"
                f"1. Checkout {ref} in this clone -- the one this client also\n"
                f"   runs from, so the client's own code changes too\n"
                f"2. Rebuild Docker containers on THIS MACHINE\n"
                f"3. Restart local server\n\n"
                f"A tag leaves the clone on no branch. Restart the client "
                f"afterwards so it runs what is now checked out.\n\n"
                f"This may take several minutes.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

            # Disable button during update
            self.update_local_server_btn.setEnabled(False)
            self.update_local_server_btn.setText("Updating...")

            # Progress: 0% - Starting
            self.update_status_label.setText(f"Update Status: Starting local server update to {ref}")
            self.progress_bar.setValue(0)

            # Step 1: Checkout git ref
            self.logs_text.append(f"\n🔄 Checking out {ref}...")
            self.update_status_label.setText(f"Update Status: Checking out {ref}...")
            self.progress_bar.setValue(10)

            if not checkout_git_ref(ref):
                raise Exception(f"Failed to checkout {ref}")

            self.logs_text.append(f"✅ Checked out {ref}")

            # Progress: 25% - Git checkout complete
            self.update_status_label.setText(f"Update Status: Git checkout complete")
            self.progress_bar.setValue(25)

            # Get project directory
            project_dir = get_git_root()
            if not project_dir:
                raise Exception("Could not determine project root directory")

            # Step 2: Docker rebuild (if auto-enabled)
            if self.auto_docker_rebuild_local.isChecked():
                # Local rebuild
                if not is_docker_available_locally():
                    raise Exception("Docker not available locally")

                # Progress: 50% - Docker rebuild started
                self.logs_text.append(f"\n🐳 Rebuilding Docker locally...")
                self.update_status_label.setText(f"Update Status: Rebuilding Docker containers...")
                self.progress_bar.setValue(50)

                result = rebuild_docker_local(project_dir)

                if result.success:
                    # Progress: 100% - Complete
                    self.progress_bar.setValue(100)
                    self.update_status_label.setText(f"Update Status: Local server updated successfully!")

                    self.logs_text.append(f"✅ Docker rebuild successful!")
                    self.logs_text.append(f"\nOutput:\n{result.output}")

                    QMessageBox.information(
                        self,
                        "Local Server Updated",
                        f"Local server successfully updated to {ref} and rebuilt!\n\n"
                        f"The server should now be running the new version."
                    )

                    # Refresh server version display
                    self.refresh()
                else:
                    # Rebuild failed - show manual instructions
                    self.progress_bar.setValue(0)
                    self.update_status_label.setText(f"Update Status: Docker rebuild failed")

                    self.logs_text.append(f"❌ Docker rebuild failed: {result.error}")

                    instructions = generate_rebuild_instructions(project_dir, ref)
                    self.logs_text.append(f"\n📋 Manual Instructions:\n{instructions}")

                    QMessageBox.warning(
                        self,
                        "Rebuild Failed",
                        f"Git checkout succeeded but Docker rebuild failed.\n\n"
                        f"{result.error}\n\n"
                        f"Manual steps required:\n\n{instructions}"
                    )
            else:
                # Manual rebuild - show instructions
                self.progress_bar.setValue(25)
                self.update_status_label.setText(f"Update Status: Git checkout complete - manual rebuild required")

                instructions = generate_rebuild_instructions(project_dir, ref)

                self.logs_text.append(f"\n📋 Manual rebuild required:\n{instructions}")

                QMessageBox.information(
                    self,
                    "Manual Rebuild Required",
                    f"Git checkout complete. Follow these steps to rebuild:\n\n{instructions}"
                )

        except Exception as e:
            logger.error(f"Error updating local server: {e}")
            self.logs_text.append(f"\n❌ Error: {str(e)}")
            self.progress_bar.setValue(0)
            self.update_status_label.setText(f"Update Status: Update failed")
            QMessageBox.critical(
                self, "Update Failed", f"Failed to update local server:\n{str(e)}"
            )

        finally:
            self.update_local_server_btn.setEnabled(True)
            self.update_local_server_btn.setText("Update Local Server")

    def _remember_ssh_user(self, ssh_host: str):
        """Store the SSH user against the server it worked for.

        The API connection knows the host but never the SSH user, so without
        this it is retyped every session -- and a typo points a rebuild at
        the wrong machine.
        """
        if "@" not in ssh_host:
            return
        user, _, host = ssh_host.partition("@")
        try:
            from client.utils.server_manager import ServerManager

            manager = ServerManager()
            active = manager.get_active_server()
            if active and active.host == host and getattr(active, "user", None) != user:
                manager.update_server(active.name, user=user)
                logger.info(f"Remembered SSH user {user} for {host}")
        except Exception as e:
            # Not worth failing an otherwise successful update over.
            logger.debug(f"Could not remember the SSH user: {e}")

    def _update_remote_server(self):
        """Update a remote LabLink over SSH and rebuild its containers.

        This used to check the ref out in the *local* clone and then run
        docker compose on the remote in a directory named by the local git
        root -- so it moved this machine's code and then told a Raspberry Pi
        to "cd C:/LabLinkTest", which fails on the first command. Nothing ever
        updated the remote's own code.

        The remote already ships the right procedure in lablink-update.sh.
        Driving that means a bench Pi updates identically whether somebody
        ssh'd in and ran it or pressed this button.
        """
        from client.utils.docker_operations import update_remote_server

        try:
            ssh_host = self.ssh_host_input.text().strip()
            if not ssh_host:
                QMessageBox.warning(
                    self,
                    "SSH Host Required",
                    "Please enter an SSH host (e.g. user@hostname).\n\n"
                    "Example: admin@192.168.91.191"
                )
                return

            remote_dir = self.remote_path_input.text().strip() or "/opt/lablink"

            mode = self.update_mode_combo.currentData()
            ref = (self.version_selector.currentData() if mode == "stable"
                   else self.branch_combo.currentData())
            if not ref:
                QMessageBox.warning(
                    self,
                    "No Version Selected",
                    "Please select a version or branch first."
                )
                return

            reply = QMessageBox.question(
                self,
                "Confirm Remote Server Update",
                f"Update {ssh_host}:{remote_dir} to {ref}?\n\n"
                f"On that host this will:\n"
                f"1. Fetch and check out {ref}\n"
                f"2. Rebuild the containers\n"
                f"3. Bring them back up\n\n"
                f"This machine's own checkout is not touched.\n"
                f"The remote must be a git checkout, and SSH must work "
                f"without a password.\n\n"
                f"This may take several minutes.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            # Something on screen before the SSH call, which is minutes long.
            self.update_remote_server_btn.setEnabled(False)
            self.update_remote_server_btn.setText("Updating...")
            self.logs_text.append(f"\nUpdating {ssh_host}:{remote_dir} to {ref}...")
            self.update_status_label.setText(
                f"Update Status: Updating {ssh_host} to {ref} (this takes minutes)"
            )
            self.progress_bar.setValue(10)
            QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
            QApplication.processEvents()

            result = update_remote_server(ssh_host, remote_dir, ref)

            if result.success:
                self._remember_ssh_user(ssh_host)
                self.progress_bar.setValue(100)
                self.update_status_label.setText("Update Status: Remote server updated")
                self.logs_text.append(f"Remote update succeeded on {ssh_host}")
                self.logs_text.append(result.output)
                QMessageBox.information(
                    self,
                    "Remote Server Updated",
                    f"{ssh_host}:{remote_dir} is now on {ref}.\n\n"
                    f"Its containers were rebuilt and restarted."
                )
            else:
                self.progress_bar.setValue(0)
                self.update_status_label.setText("Update Status: Remote update failed")
                self.logs_text.append(f"Remote update failed: {result.error}")
                if result.output:
                    self.logs_text.append(result.output)
                QMessageBox.critical(
                    self,
                    "Remote Update Failed",
                    f"Updating {ssh_host} failed.\n\n{result.error}\n\n"
                    f"To do it by hand:\n"
                    f"  ssh {ssh_host}\n"
                    f"  cd {remote_dir}\n"
                    f"  sudo ./lablink-update.sh {ref} --yes"
                )

        except Exception as e:
            logger.error(f"Error updating remote server: {e}")
            self.logs_text.append(f"\nError: {str(e)}")
            QMessageBox.critical(
                self, "Update Failed", f"Failed to update remote server:\n{str(e)}"
            )
        finally:
            QApplication.restoreOverrideCursor()
            self.update_remote_server_btn.setEnabled(True)
            self.update_remote_server_btn.setText("Update Remote Server")

    def _update_client(self):
        """Update client by marking for update on next restart."""
        from client.utils.git_operations import compare_ref_to_head
        from client.utils.self_update import mark_for_update
        import sys

        try:
            # Get selected ref (tag or branch)
            mode = self.update_mode_combo.currentData()
            if mode == "stable":
                ref = self.version_selector.currentData()
            else:  # development
                ref = self.branch_combo.currentData()

            if not ref:
                QMessageBox.warning(
                    self,
                    "No Version Selected",
                    "Please select a version or branch first."
                )
                return

            # Something on screen the instant the button is pressed. The
            # direction check fetches, which is seconds on a slow link, and
            # until it returned the button looked ignored -- so it got
            # pressed again.
            self.update_client_btn.setEnabled(False)
            self.update_client_btn.setText("Checking...")
            self.logs_text.append(
                f"\nChecking {ref} against the running client..."
            )
            QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
            QApplication.processEvents()

            # Say so before going backwards.
            #
            # The version list offers tags, and a tag is a fixed point: the
            # only tag here, v2.0.0, is well behind main. Selecting it read as
            # "update" and silently installed an older client. Going back on
            # purpose is what the rollback button is for, so this asks rather
            # than refuses -- but it asks with the number, and defaults to No.
            position = compare_ref_to_head(ref)
            if position and position["same"]:
                QMessageBox.information(
                    self,
                    "Already Up To Date",
                    f"The client is already running {ref}.\n\n"
                    f"There is nothing to update."
                )
                return

            if position and position["ahead"] == 0 and position["behind"] > 0:
                behind = position["behind"]
                plural = "s" if behind != 1 else ""
                going_back = QMessageBox.warning(
                    self,
                    "This Is Older Than What You Are Running",
                    f"{ref} is {behind} commit{plural} behind the code "
                    f"you are running now.\n\n"
                    f"Updating to it will replace your client with an older "
                    f"build, losing anything added since.\n\n"
                    f"To go back to an earlier version deliberately, use "
                    f"Rollback instead.\n\n"
                    f"Continue anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if going_back != QMessageBox.StandardButton.Yes:
                    self.logs_text.append(
                        f"\nUpdate to {ref} cancelled: "
                        f"{behind} commit{plural} behind HEAD"
                    )
                    return

            # Confirm with user
            reply = QMessageBox.question(
                self,
                "Confirm Client Update",
                f"Update client to {ref}?\n\n"
                f"This will:\n"
                f"1. Mark the client for update to {ref}\n"
                f"2. Restart the client application\n"
                f"3. On restart, checkout {ref} and launch\n\n"
                f"Do you want to proceed?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

            # Mark for update
            self.logs_text.append(f"\n🔄 Marking client for update to {ref}...")

            if mark_for_update(ref, mode):
                self.logs_text.append(f"✅ Client marked for update")

                QMessageBox.information(
                    self,
                    "Client Update Scheduled",
                    f"Client has been marked for update to {ref}.\n\n"
                    f"LabLink will close and reopen once. The update is "
                    f"applied in between, before any window appears."
                )

                # Actually restart, rather than exiting and hoping.
                #
                # This called sys.exit(0) on the theory that "the launcher
                # should detect the flag" -- but nothing watches for it, so
                # the client just closed and the update sat there until
                # somebody started it by hand, while the dialog above
                # promised the application would restart.
                self.logs_text.append("🔄 Restarting application...")
                from client.main import _restart_client

                _restart_client()

            else:
                self.logs_text.append(f"❌ Failed to mark client for update")
                QMessageBox.critical(
                    self,
                    "Update Failed",
                    "Failed to mark client for update.\n\nCheck logs for details."
                )

        except Exception as e:
            logger.error(f"Error updating client: {e}")
            self.logs_text.append(f"\n❌ Error: {str(e)}")
            QMessageBox.critical(
                self, "Update Failed", f"Failed to update client:\n{str(e)}"
            )

        finally:
            # Also runs on the SystemExit the relaunch raises, which costs
            # nothing and keeps the button usable on every other path.
            QApplication.restoreOverrideCursor()
            self.update_client_btn.setEnabled(True)
            self.update_client_btn.setText("Update Client")

    def closeEvent(self, event):
        """Handle widget close event."""
        # Stop update polling
        if self.update_timer.isActive():
            self.update_timer.stop()
        super().closeEvent(event)
