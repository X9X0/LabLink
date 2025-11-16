"""Raspberry Pi Image Builder Wizard for LabLink.

This wizard creates custom Raspberry Pi images with LabLink pre-installed.
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout,
                             QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QProgressBar, QPushButton, QTextEdit,
                             QVBoxLayout, QWizard, QWizardPage)

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
        pi_model: str = "5",
        wifi_ssid: str = "",
        wifi_password: str = "",
        admin_password: str = "",
        enable_ssh: bool = True,
        auto_expand: bool = True,
    ):
        """Initialize build thread.

        Args:
            output_path: Path where image will be saved
            hostname: Raspberry Pi hostname
            pi_model: Raspberry Pi model (3, 4, or 5)
            wifi_ssid: Wi-Fi network name (optional)
            wifi_password: Wi-Fi password (optional)
            admin_password: Admin user password (optional)
            enable_ssh: Enable SSH on first boot
            auto_expand: Auto-expand filesystem on first boot
        """
        super().__init__()
        self.output_path = output_path
        self.hostname = hostname
        self.pi_model = pi_model
        self.wifi_ssid = wifi_ssid
        self.wifi_password = wifi_password
        self.admin_password = admin_password
        self.enable_ssh = enable_ssh
        self.auto_expand = auto_expand
        self.recent_output = []  # Buffer for recent output lines

    def _parse_progress_only(self, line: str):
        """Parse progress from a line without emitting output."""
        # Download progress (wget shows % progress)
        if "%" in line and ("K/s" in line or "M/s" in line or "G/s" in line):
            try:
                parts = line.split()
                for part in parts:
                    if "%" in part:
                        pct = int(part.rstrip('%'))
                        prog = 5 + int(pct * 0.10)
                        self.progress.emit(prog, f"Downloading: {pct}%")
                        break
            except (ValueError, IndexError):
                pass
        # xz extraction/compression progress (e.g. "  5.4 %  123.4 MiB")
        elif "%" in line and "MiB" in line and "K/s" not in line:
            try:
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0].replace('.', '', 1).replace('%', '').replace('-', '').isdigit():
                    pct = float(parts[0].rstrip('%'))
                    if pct >= 0:
                        recent_text = ''.join(self.recent_output[-10:])
                        if "Extracting" in recent_text or len(self.recent_output) < 20:
                            # Early in process or explicitly extracting
                            prog = 16 + int(pct * 0.04)
                            self.progress.emit(prog, f"Extracting: {int(pct)}%")
                        elif "Compressing" in recent_text:
                            prog = 85 + int(pct * 0.10)
                            self.progress.emit(prog, f"Compressing: {int(pct)}%")
            except (ValueError, IndexError):
                pass

    def run(self):
        """Run image building process."""
        try:
            self.progress.emit(0, "Starting image build process...")
            logger.info("ImageBuildThread starting")

            # Check if build script exists
            script_path = Path(__file__).parent.parent.parent / "build-pi-image.sh"
            logger.info(f"Looking for build script at: {script_path}")
            logger.info(f"Script exists: {script_path.exists()}")

            if not script_path.exists():
                error_msg = (
                    f"Build script not found at: {script_path}\n\n"
                    "Please ensure build-pi-image.sh is in the LabLink root directory."
                )
                logger.error(error_msg)
                self.finished.emit(False, error_msg)
                return

            # Prepare environment variables
            env = os.environ.copy()
            env["OUTPUT_IMAGE"] = self.output_path
            env["PI_HOSTNAME"] = self.hostname
            env["PI_MODEL"] = self.pi_model

            if self.wifi_ssid:
                env["WIFI_SSID"] = self.wifi_ssid
            if self.wifi_password:
                env["WIFI_PASSWORD"] = self.wifi_password
            if self.admin_password:
                env["ADMIN_PASSWORD"] = self.admin_password

            env["ENABLE_SSH"] = "yes" if self.enable_ssh else "no"
            env["AUTO_EXPAND"] = "yes" if self.auto_expand else "no"

            self.progress.emit(5, "Launching build script...")
            self.output.emit(f"Build script: {script_path}\n")
            self.output.emit(f"Building image: {self.output_path}\n")
            self.output.emit(f"Hostname: {self.hostname}\n")
            self.output.emit(f"\n--- Starting build process ---\n")

            logger.info(f"Launching bash with script: {script_path}")
            logger.info(f"Output path: {self.output_path}")

            # Check if pkexec is available for GUI sudo
            pkexec_available = subprocess.run(
                ['which', 'pkexec'],
                capture_output=True,
                check=False
            ).returncode == 0

            # Build script wrapper that exports env vars
            script_wrapper = f"""#!/bin/bash
export OUTPUT_IMAGE='{self.output_path}'
export PI_HOSTNAME='{self.hostname}'
export PI_MODEL='{self.pi_model}'
export ENABLE_SSH='{"yes" if self.enable_ssh else "no"}'
export AUTO_EXPAND='{"yes" if self.auto_expand else "no"}'
"""
            if self.wifi_ssid:
                script_wrapper += f"export WIFI_SSID='{self.wifi_ssid}'\n"
            if self.wifi_password:
                script_wrapper += f"export WIFI_PASSWORD='{self.wifi_password}'\n"
            if self.admin_password:
                script_wrapper += f"export ADMIN_PASSWORD='{self.admin_password}'\n"

            script_wrapper += f"exec bash {script_path}\n"

            # Write wrapper to temp file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
                f.write(script_wrapper)
                wrapper_path = f.name

            # Make wrapper executable
            os.chmod(wrapper_path, 0o755)

            if pkexec_available:
                # Run with pkexec for graphical sudo prompt
                logger.info("Running with pkexec for root privileges")
                self.output.emit("Running with elevated privileges (pkexec)...\n")
                command = ['pkexec', 'bash', wrapper_path]
            else:
                # Warn that the script needs sudo
                logger.warning("pkexec not available, script may fail without sudo")
                self.output.emit("WARNING: This script requires root privileges\n")
                self.output.emit("pkexec not found - build may fail\n")
                command = ['bash', wrapper_path]

            # Use pty to force unbuffered output
            import pty
            import select

            logger.info(f"Launching command: {' '.join(command)}")

            # Create a pseudo-terminal for truly unbuffered I/O
            master_fd, slave_fd = pty.openpty()

            process = subprocess.Popen(
                command,
                stdout=slave_fd,
                stderr=slave_fd,
                stdin=slave_fd,
                close_fds=True,
            )

            # Close slave fd in parent process
            os.close(slave_fd)

            logger.info(f"Process started with PID: {process.pid}")
            self.output.emit(f"Process started (PID: {process.pid})\n")

            # Send newlines to stdin to skip interactive prompts
            # The script will use the environment variables we set
            try:
                # Send 6 newlines to accept all default prompts:
                # 1. Output image name
                # 2. Hostname
                # 3. Enable SSH
                # 4. Wi-Fi SSID (empty to skip)
                # 5. Admin password
                # Plus one extra for safety
                os.write(master_fd, b'\n' * 6)
            except Exception as e:
                logger.warning(f"Failed to write to stdin: {e}")

            # Monitor progress - read from pty master for unbuffered I/O
            line_count = 0
            partial_line = b''

            # Set master_fd to non-blocking mode
            import fcntl
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            while True:
                # Check if process has exited
                poll_result = process.poll()

                try:
                    # Use select to wait for data with timeout
                    ready, _, _ = select.select([master_fd], [], [], 0.1)

                    if ready:
                        # Read available data
                        try:
                            data = os.read(master_fd, 4096)
                            if not data:
                                if poll_result is not None:
                                    break
                                continue

                            partial_line += data

                            # Process complete lines (ending in newline)
                            while b'\n' in partial_line:
                                line_end = partial_line.index(b'\n')
                                line_bytes = partial_line[:line_end + 1]
                                partial_line = partial_line[line_end + 1:]

                                try:
                                    line = line_bytes.decode('utf-8', errors='replace')
                                    line_count += 1
                                    logger.debug(f"Build output [{line_count}]: {line.strip()}")
                                    self.output.emit(line)

                                    # Keep recent output for context checking (last 50 lines)
                                    self.recent_output.append(line)
                                    if len(self.recent_output) > 50:
                                        self.recent_output.pop(0)

                                    # Parse progress from output
                                    self._parse_progress_only(line)

                                    # Parse step transitions (non-numeric progress)
                                    if "Downloading" in line:
                                        self.progress.emit(5, "Starting download...")
                                    elif "Extracting" in line:
                                        self.progress.emit(16, "Extracting image...")
                                    elif "extracted successfully" in line:
                                        self.progress.emit(20, "Extraction complete")
                                    elif "Expanding image" in line:
                                        self.progress.emit(22, "Expanding image...")
                                    elif "Image expanded" in line:
                                        self.progress.emit(25, "Expansion complete")
                                    elif "Mounting" in line:
                                        self.progress.emit(30, "Mounting image...")
                                    elif "Configuring" in line:
                                        self.progress.emit(50, "Configuring system...")
                                    elif "Installing" in line:
                                        self.progress.emit(60, "Installing LabLink...")
                                    elif "Creating systemd" in line:
                                        self.progress.emit(70, "Setting up auto-start...")
                                    elif "Unmounting" in line or "unmounted" in line:
                                        self.progress.emit(80, "Finalizing image...")
                                    elif "Compressing image" in line:
                                        self.progress.emit(85, "Starting compression...")
                                    elif "Compression complete" in line:
                                        self.progress.emit(95, "Compression complete")
                                    elif "Image created" in line:
                                        self.progress.emit(98, "Finalizing...")
                                    elif "SUCCESS" in line or "Build complete" in line:
                                        self.progress.emit(100, "Build complete!")
                                except Exception as e:
                                    logger.error(f"Error decoding line: {e}")
                        except OSError as e:
                            if poll_result is not None:
                                break
                    elif poll_result is not None:
                        # Process exited and no more data
                        break

                except Exception as e:
                    logger.error(f"Error reading from pty: {e}")
                    if poll_result is not None:
                        break

            # Close master fd
            os.close(master_fd)

            logger.info(f"Process output loop ended. Total lines: {line_count}")
            process.wait()
            logger.info(f"Process exited with code: {process.returncode}")

            # Clean up temp wrapper script
            try:
                os.unlink(wrapper_path)
                logger.debug(f"Cleaned up temp wrapper: {wrapper_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp wrapper: {e}")

            if process.returncode == 0:
                self.progress.emit(100, "Image built successfully!")
                self.finished.emit(
                    True,
                    f"Raspberry Pi image created successfully!\n\n"
                    f"Image saved to: {self.output_path}\n\n"
                    f"You can now write this image to an SD card.",
                )
            else:
                error_msg = (
                    f"Build failed with exit code {process.returncode}\n\n"
                    "Check the output log for details."
                )
                logger.error(error_msg)
                self.finished.emit(False, error_msg)

        except FileNotFoundError as e:
            error_msg = f"Build script not found: {e}\n\nThis tool requires bash to be installed."
            logger.error(error_msg)
            self.finished.emit(False, error_msg)
        except Exception as e:
            logger.exception("Image build failed")
            self.finished.emit(False, f"Build error: {str(e)}")


class ConfigurationPage(QWizardPage):
    """Page for configuring Raspberry Pi settings."""

    def __init__(self):
        """Initialize configuration page."""
        super().__init__()
        self.setTitle("Raspberry Pi Configuration")
        self.setSubTitle(
            "Configure the Raspberry Pi system settings for your LabLink server."
        )

        layout = QVBoxLayout()

        # Hardware settings
        hardware_group = QGroupBox("Hardware Configuration")
        hardware_layout = QFormLayout()

        self.pi_model_combo = QComboBox()
        self.pi_model_combo.addItems(["Raspberry Pi 5", "Raspberry Pi 4", "Raspberry Pi 3"])
        self.pi_model_combo.setCurrentIndex(0)  # Default to Pi 5
        hardware_layout.addRow("Raspberry Pi Model:", self.pi_model_combo)

        hardware_group.setLayout(hardware_layout)
        layout.addWidget(hardware_group)

        # Basic settings
        basic_group = QGroupBox("Basic Settings")
        basic_layout = QFormLayout()

        self.hostname_edit = QLineEdit("lablink-pi")
        self.hostname_edit.setPlaceholderText("e.g., lablink-pi")
        basic_layout.addRow("Hostname:", self.hostname_edit)

        self.admin_password_edit = QLineEdit()
        self.admin_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.admin_password_edit.setPlaceholderText(
            "Leave empty to use default: raspberry"
        )
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

        # Set default path directly in constructor, same as hostname field
        default_path = os.path.expanduser("~/lablink-pi.img")
        self.output_path_edit = QLineEdit(default_path)
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
            "Build process may take 10-30 minutes depending on your internet connection.\n\n"
            "⚠️ This tool requires root privileges. You will be prompted for your password."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(
            "color: #666; padding: 10px; background-color: #f0f0f0; border-radius: 5px;"
        )
        layout.addWidget(info_label)

        self.setLayout(layout)

        # Register fields for validation
        self.registerField("pi_model", self.pi_model_combo, "currentText")
        self.registerField("hostname*", self.hostname_edit)
        self.registerField("output_path*", self.output_path_edit)
        self.registerField("wifi_ssid", self.wifi_ssid_edit)
        self.registerField("wifi_password", self.wifi_password_edit)
        self.registerField("admin_password", self.admin_password_edit)

        # Connect text changes to notify wizard of completion status
        self.hostname_edit.textChanged.connect(self.completeChanged)
        self.output_path_edit.textChanged.connect(self.completeChanged)

    def isComplete(self):
        """Check if page has all required fields filled."""
        # Both required fields must have text
        has_hostname = bool(self.hostname_edit.text().strip())
        has_output = bool(self.output_path_edit.text().strip())
        return has_hostname and has_output

    def _browse_output(self):
        """Browse for output file location."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Raspberry Pi Image",
            os.path.expanduser("~/lablink-pi.img"),
            "Disk Images (*.img)",
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
            QMessageBox.warning(
                self, "No Output Path", "Please select where to save the image."
            )
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
                QMessageBox.StandardButton.No,
            )
            return reply == QMessageBox.StandardButton.Yes

        return True


class BuildProgressPage(QWizardPage):
    """Page showing build progress."""

    def __init__(self):
        """Initialize progress page."""
        super().__init__()
        self.setTitle("Building Image")
        self.setSubTitle(
            "Creating custom Raspberry Pi image with LabLink pre-installed..."
        )

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
        self.output_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)  # No wrapping
        self.output_text.setStyleSheet("""
            QTextEdit {
                font-family: 'Courier New', 'Consolas', monospace;
                font-size: 9pt;
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 2px solid #3e3e3e;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.output_text)

        self.setLayout(layout)

    def initializePage(self):
        """Start build process when page is shown."""
        # Get configuration from previous page
        pi_model_text = self.field("pi_model") or "Raspberry Pi 5"
        # Extract model number (3, 4, or 5)
        if "3" in pi_model_text:
            pi_model = "3"
        elif "4" in pi_model_text:
            pi_model = "4"
        else:
            pi_model = "5"

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
            pi_model=pi_model,
            wifi_ssid=wifi_ssid,
            wifi_password=wifi_password,
            admin_password=admin_password,
            enable_ssh=enable_ssh,
            auto_expand=auto_expand,
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

        # Apply visual styling
        self.setStyleSheet("""
            QWizard {
                background-color: #ecf0f1;
            }
            QWizardPage {
                background-color: #ecf0f1;
            }
            QGroupBox {
                border: 2px solid #bdc3c7;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 15px;
                background-color: white;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 5px 10px;
                background-color: white;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                border: 2px solid #2471a3;
                border-radius: 6px;
                padding: 8px 15px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #2e86c1;
                border: 2px solid #1f618d;
            }
            QPushButton:pressed {
                background-color: #2471a3;
            }
            QPushButton:disabled {
                background-color: #95a5a6;
                border: 2px solid #7f8c8d;
                color: #ecf0f1;
            }
        """)

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
                QMessageBox.StandardButton.Yes,
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
