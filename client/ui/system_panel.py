"""System Management panel for LabLink GUI."""

import logging
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from client.api.client import LabLinkClient

logger = logging.getLogger(__name__)


class UpdateDialog(QDialog):
    """Dialog for configuring update parameters."""

    def __init__(self, parent=None):
        """Initialize update dialog."""
        super().__init__(parent)
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
        warning.setStyleSheet("color: orange; padding: 10px;")
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
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("<h2>System Management</h2>")
        layout.addWidget(header)

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

        # Update status
        self.update_status_label = QLabel("Update Status: Idle")
        update_layout.addWidget(self.update_status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        update_layout.addWidget(self.progress_bar)

        # Update buttons
        button_layout = QHBoxLayout()

        self.check_updates_btn = QPushButton("Check for Updates")
        self.check_updates_btn.clicked.connect(self.check_for_updates)
        button_layout.addWidget(self.check_updates_btn)

        self.start_update_btn = QPushButton("Update Server")
        self.start_update_btn.clicked.connect(self.start_update)
        self.start_update_btn.setEnabled(False)
        button_layout.addWidget(self.start_update_btn)

        self.rollback_btn = QPushButton("Rollback")
        self.rollback_btn.clicked.connect(self.rollback)
        button_layout.addWidget(self.rollback_btn)

        update_layout.addLayout(button_layout)
        update_group.setLayout(update_layout)
        layout.addWidget(update_group)

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
        self.refresh()

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

        except Exception as e:
            logger.error(f"Error refreshing system info: {e}")
            QMessageBox.critical(
                self, "Error", f"Failed to refresh system info:\n{str(e)}"
            )

    def _update_status_display(self):
        """Update the status display from server."""
        if not self.client:
            return

        try:
            status_data = self.client.get_update_status()

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

        except Exception as e:
            logger.error(f"Error updating status display: {e}")

    def _poll_update_status(self):
        """Poll update status periodically."""
        self._update_status_display()

    def check_for_updates(self):
        """Check for available updates."""
        if not self.client:
            return

        try:
            # Show config dialog
            dialog = UpdateDialog(self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            remote, branch = dialog.get_config()

            self.logs_text.append(
                f"\n🔍 Checking for updates from {remote}/{branch or 'current branch'}..."
            )
            self.check_updates_btn.setEnabled(False)

            # Check for updates
            result = self.client.check_for_updates(
                git_remote=remote, git_branch=branch
            )

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

        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            self.logs_text.append(f"\n❌ Error: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to check for updates:\n{str(e)}")

        finally:
            self.check_updates_btn.setEnabled(True)

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

    def closeEvent(self, event):
        """Handle widget close event."""
        # Stop update polling
        if self.update_timer.isActive():
            self.update_timer.stop()
        super().closeEvent(event)
