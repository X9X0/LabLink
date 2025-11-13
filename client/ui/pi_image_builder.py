"""Raspberry Pi Image Builder Wizard for LabLink.

This wizard creates custom Raspberry Pi images with LabLink pre-installed.
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import Optional
from PyQt6.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QProgressBar, QTextEdit,
    QFileDialog, QCheckBox, QGroupBox, QMessageBox, QComboBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

logger = logging.getLogger(__name__)


class ImageBuildThread(QThread):
    """Background thread for building Raspberry Pi images."""

    progress = pyqtSignal(int, str)  # percent, message
    finished = pyqtSignal(bool, str)  # success, message/error
    output = pyqtSignal(str)  # stdout/stderr output

    def __init__(
        self,
        output_path: str,
        hostname: str = "lablink-pi",
        wifi_ssid: str = "",
        wifi_password: str = "",
        admin_password: str = "",
        enable_ssh: bool = True,
        auto_expand: bool = True
    ):
        """Initialize build thread.

        Args:
            output_path: Path where image will be saved
            hostname: Raspberry Pi hostname
            wifi_ssid: Wi-Fi network name (optional)
            wifi_password: Wi-Fi password (optional)
            admin_password: Admin user password (optional)
            enable_ssh: Enable SSH on first boot
            auto_expand: Auto-expand filesystem on first boot
        """
        super().__init__()
        self.output_path = output_path
        self.hostname = hostname
        self.wifi_ssid = wifi_ssid
        self.wifi_password = wifi_password
        self.admin_password = admin_password
        self.enable_ssh = enable_ssh
        self.auto_expand = auto_expand

    def run(self):
        """Run image building process."""
        try:
            self.progress.emit(0, "Starting image build process...")

            # Check if build script exists
            script_path = Path(__file__).parent.parent.parent / "build-pi-image.sh"

            if not script_path.exists():
                self.finished.emit(
                    False,
                    f"Build script not found at: {script_path}\n\n"
                    "Please ensure build-pi-image.sh is in the LabLink root directory."
                )
                return

            # Prepare environment variables
            env = os.environ.copy()
            env["OUTPUT_IMAGE"] = self.output_path
            env["PI_HOSTNAME"] = self.hostname

            if self.wifi_ssid:
                env["WIFI_SSID"] = self.wifi_ssid
            if self.wifi_password:
                env["WIFI_PASSWORD"] = self.wifi_password
            if self.admin_password:
                env["ADMIN_PASSWORD"] = self.admin_password

            env["ENABLE_SSH"] = "yes" if self.enable_ssh else "no"
            env["AUTO_EXPAND"] = "yes" if self.auto_expand else "no"

            self.progress.emit(5, "Launching build script...")
            self.output.emit(f"Building image: {self.output_path}\n")
            self.output.emit(f"Hostname: {self.hostname}\n")

            # Run build script
            process = subprocess.Popen(
                ["bash", str(script_path)],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            # Monitor progress
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break

                self.output.emit(line)

                # Parse progress from output
                if "Downloading" in line:
                    self.progress.emit(10, "Downloading base image...")
                elif "Expanding" in line or "Creating" in line:
                    self.progress.emit(20, "Expanding image...")
                elif "Mounting" in line:
                    self.progress.emit(30, "Mounting image...")
                elif "Configuring" in line:
                    self.progress.emit(50, "Configuring system...")
                elif "Installing" in line:
                    self.progress.emit(60, "Installing LabLink...")
                elif "Creating systemd" in line:
                    self.progress.emit(70, "Setting up auto-start...")
                elif "Unmounting" in line:
                    self.progress.emit(80, "Finalizing image...")
                elif "Compressing" in line:
                    self.progress.emit(90, "Compressing image...")
                elif "SUCCESS" in line or "Complete" in line:
                    self.progress.emit(100, "Build complete!")

            process.wait()

            if process.returncode == 0:
                self.progress.emit(100, "Image built successfully!")
                self.finished.emit(
                    True,
                    f"Raspberry Pi image created successfully!\n\n"
                    f"Image saved to: {self.output_path}\n\n"
                    f"You can now write this image to an SD card."
                )
            else:
                self.finished.emit(
                    False,
                    f"Build failed with exit code {process.returncode}\n\n"
                    "Check the output log for details."
                )

        except FileNotFoundError:
            self.finished.emit(
                False,
                "Build script not found.\n\n"
                "This tool requires bash to be installed."
            )
        except Exception as e:
            logger.exception("Image build failed")
            self.finished.emit(False, f"Build error: {str(e)}")


class ConfigurationPage(QWizardPage):
    """Page for configuring Raspberry Pi settings."""

    def __init__(self):
        """Initialize configuration page."""
        super().__init__()
        self.setTitle("Raspberry Pi Configuration")
        self.setSubTitle("Configure the Raspberry Pi system settings for your LabLink server.")

        layout = QVBoxLayout()

        # Basic settings
        basic_group = QGroupBox("Basic Settings")
        basic_layout = QFormLayout()

        self.hostname_edit = QLineEdit("lablink-pi")
        self.hostname_edit.setPlaceholderText("e.g., lablink-pi")
        basic_layout.addRow("Hostname:", self.hostname_edit)

        self.admin_password_edit = QLineEdit()
        self.admin_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.admin_password_edit.setPlaceholderText("Leave empty to use default: raspberry")
        basic_layout.addRow("Admin Password:", self.admin_password_edit)

        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)

        # Wi-Fi settings
        wifi_group = QGroupBox("Wi-Fi Configuration (Optional)")
        wifi_layout = QFormLayout()

        self.wifi_ssid_edit = QLineEdit()
        self.wifi_ssid_edit.setPlaceholderText("Your Wi-Fi network name")
        wifi_layout.addRow("Wi-Fi SSID:", self.wifi_ssid_edit)

        self.wifi_password_edit = QLineEdit()
        self.wifi_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.wifi_password_edit.setPlaceholderText("Wi-Fi password")
        wifi_layout.addRow("Wi-Fi Password:", self.wifi_password_edit)

        wifi_group.setLayout(wifi_layout)
        layout.addWidget(wifi_group)

        # Additional options
        options_group = QGroupBox("Additional Options")
        options_layout = QVBoxLayout()

        self.enable_ssh_check = QCheckBox("Enable SSH on first boot")
        self.enable_ssh_check.setChecked(True)
        options_layout.addWidget(self.enable_ssh_check)

        self.auto_expand_check = QCheckBox("Auto-expand filesystem on first boot")
        self.auto_expand_check.setChecked(True)
        options_layout.addWidget(self.auto_expand_check)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # Output file selection
        output_group = QGroupBox("Output Image")
        output_layout = QHBoxLayout()

        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("Select where to save the image...")
        output_layout.addWidget(self.output_path_edit)

        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse_output)
        output_layout.addWidget(browse_button)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        layout.addStretch()

        # Info label
        info_label = QLabel(
            "ℹ️ The image will be based on Raspberry Pi OS Lite with LabLink pre-installed.\n"
            "Build process may take 10-30 minutes depending on your internet connection."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; padding: 10px; background-color: #f0f0f0; border-radius: 5px;")
        layout.addWidget(info_label)

        self.setLayout(layout)

        # Register fields for validation
        self.registerField("hostname*", self.hostname_edit)
        self.registerField("output_path*", self.output_path_edit)
        self.registerField("wifi_ssid", self.wifi_ssid_edit)
        self.registerField("wifi_password", self.wifi_password_edit)
        self.registerField("admin_password", self.admin_password_edit)

    def _browse_output(self):
        """Browse for output file location."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Raspberry Pi Image",
            os.path.expanduser("~/lablink-pi.img"),
            "Disk Images (*.img)"
        )

        if file_path:
            self.output_path_edit.setText(file_path)

    def validatePage(self) -> bool:
        """Validate page inputs.

        Returns:
            True if valid, False otherwise
        """
        # Check hostname
        hostname = self.hostname_edit.text().strip()
        if not hostname:
            QMessageBox.warning(self, "Invalid Hostname", "Please enter a hostname.")
            return False

        # Check output path
        output_path = self.output_path_edit.text().strip()
        if not output_path:
            QMessageBox.warning(self, "No Output Path", "Please select where to save the image.")
            return False

        # Check if Wi-Fi SSID and password are both provided or both empty
        wifi_ssid = self.wifi_ssid_edit.text().strip()
        wifi_password = self.wifi_password_edit.text().strip()

        if wifi_ssid and not wifi_password:
            reply = QMessageBox.question(
                self,
                "No Wi-Fi Password",
                "You entered a Wi-Fi SSID but no password. Continue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            return reply == QMessageBox.StandardButton.Yes

        return True


class BuildProgressPage(QWizardPage):
    """Page showing build progress."""

    def __init__(self):
        """Initialize progress page."""
        super().__init__()
        self.setTitle("Building Image")
        self.setSubTitle("Creating custom Raspberry Pi image with LabLink pre-installed...")

        self.build_thread: Optional[ImageBuildThread] = None
        self.build_complete = False
        self.build_success = False

        layout = QVBoxLayout()

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Initializing...")
        layout.addWidget(self.status_label)

        # Output log
        log_label = QLabel("Build Output:")
        layout.addWidget(log_label)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setStyleSheet("font-family: monospace; font-size: 10pt;")
        layout.addWidget(self.output_text)

        self.setLayout(layout)

    def initializePage(self):
        """Start build process when page is shown."""
        # Get configuration from previous page
        hostname = self.field("hostname")
        output_path = self.field("output_path")
        wifi_ssid = self.field("wifi_ssid") or ""
        wifi_password = self.field("wifi_password") or ""
        admin_password = self.field("admin_password") or ""

        # Get checkbox states from previous page
        config_page = self.wizard().page(0)
        enable_ssh = config_page.enable_ssh_check.isChecked()
        auto_expand = config_page.auto_expand_check.isChecked()

        # Reset state
        self.build_complete = False
        self.build_success = False
        self.progress_bar.setValue(0)
        self.output_text.clear()

        # Create build thread
        self.build_thread = ImageBuildThread(
            output_path=output_path,
            hostname=hostname,
            wifi_ssid=wifi_ssid,
            wifi_password=wifi_password,
            admin_password=admin_password,
            enable_ssh=enable_ssh,
            auto_expand=auto_expand
        )

        # Connect signals
        self.build_thread.progress.connect(self._on_progress)
        self.build_thread.output.connect(self._on_output)
        self.build_thread.finished.connect(self._on_finished)

        # Start build
        self.build_thread.start()

        # Disable back button during build
        self.wizard().button(QWizard.WizardButton.BackButton).setEnabled(False)

    def _on_progress(self, percent: int, message: str):
        """Handle progress update.

        Args:
            percent: Progress percentage (0-100)
            message: Status message
        """
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)

    def _on_output(self, text: str):
        """Handle output text.

        Args:
            text: Output text line
        """
        self.output_text.insertPlainText(text)
        # Scroll to bottom
        scrollbar = self.output_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_finished(self, success: bool, message: str):
        """Handle build completion.

        Args:
            success: True if successful, False otherwise
            message: Completion message
        """
        self.build_complete = True
        self.build_success = success

        if success:
            self.status_label.setText("✅ Build completed successfully!")
            QMessageBox.information(self, "Build Complete", message)
        else:
            self.status_label.setText("❌ Build failed")
            QMessageBox.critical(self, "Build Failed", message)

        # Re-enable navigation
        self.wizard().button(QWizard.WizardButton.BackButton).setEnabled(True)
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        """Check if page is complete.

        Returns:
            True if build is complete, False otherwise
        """
        return self.build_complete

    def cleanupPage(self):
        """Clean up when leaving page."""
        if self.build_thread and self.build_thread.isRunning():
            self.build_thread.terminate()
            self.build_thread.wait()


class PiImageBuilderWizard(QWizard):
    """Wizard for building Raspberry Pi images with LabLink."""

    def __init__(self, parent=None):
        """Initialize wizard.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.setWindowTitle("Raspberry Pi Image Builder")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.resize(700, 600)

        # Add pages
        self.config_page = ConfigurationPage()
        self.addPage(self.config_page)

        self.progress_page = BuildProgressPage()
        self.addPage(self.progress_page)

        # Customize buttons
        self.setButtonText(QWizard.WizardButton.FinishButton, "Write to SD Card")
        self.setButtonText(QWizard.WizardButton.CancelButton, "Close")

    def done(self, result: int):
        """Handle wizard completion.

        Args:
            result: Dialog result code
        """
        if result == QWizard.DialogCode.Accepted and self.progress_page.build_success:
            # Ask if user wants to write to SD card
            reply = QMessageBox.question(
                self,
                "Write to SD Card?",
                "Would you like to write this image to an SD card now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )

            if reply == QMessageBox.StandardButton.Yes:
                # Import here to avoid circular import
                from ui.sd_card_writer import SDCardWriter

                # Get image path
                image_path = self.field("output_path")

                # Show SD card writer
                writer = SDCardWriter(self.parent())
                writer.set_image_path(image_path)
                writer.exec()

        super().done(result)
