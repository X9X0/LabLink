"""SD Card Writer - Write Raspberry Pi images to SD cards."""

import logging
import platform
import subprocess
import os
from pathlib import Path
from typing import List, Optional, Dict
import hashlib

try:
    from PyQt6.QtWidgets import (
        QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QComboBox, QProgressBar, QTextEdit, QFileDialog, QMessageBox,
        QGroupBox, QFormLayout, QCheckBox
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal
    from PyQt6.QtGui import QFont
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

logger = logging.getLogger(__name__)


class ImageWriterThread(QThread):
    """Thread for writing images to SD cards."""

    progress = pyqtSignal(int, str)  # Progress percentage, message
    finished = pyqtSignal(bool, str)  # Success, message

    def __init__(self, image_path: str, device_path: str, verify: bool = True):
        """Initialize writer thread.

        Args:
            image_path: Path to image file
            device_path: Device path (e.g., /dev/sdb, \\.\PhysicalDrive1)
            verify: Whether to verify after writing
        """
        super().__init__()
        self.image_path = image_path
        self.device_path = device_path
        self.verify = verify
        self._stop_requested = False

    def run(self):
        """Write image to SD card."""
        try:
            # Check if image exists
            if not os.path.exists(self.image_path):
                self.finished.emit(False, f"Image file not found: {self.image_path}")
                return

            self.progress.emit(5, "Preparing to write image...")

            # Get image size
            image_size = os.path.getsize(self.image_path)
            self.progress.emit(10, f"Image size: {image_size / (1024**3):.2f} GB")

            # Unmount device (Linux/macOS)
            if platform.system() in ["Linux", "Darwin"]:
                self._unmount_device()

            self.progress.emit(15, "Writing image...")

            # Write image
            if platform.system() == "Windows":
                success = self._write_windows()
            else:
                success = self._write_unix()

            if not success or self._stop_requested:
                self.finished.emit(False, "Write cancelled or failed")
                return

            self.progress.emit(90, "Write complete")

            # Verify if requested
            if self.verify:
                self.progress.emit(92, "Verifying write...")
                if self._verify_write():
                    self.progress.emit(100, "Verification successful")
                else:
                    self.finished.emit(False, "Verification failed!")
                    return

            # Eject/sync
            self._safely_eject()

            self.finished.emit(True, "Image written successfully!")

        except Exception as e:
            logger.exception("Image write failed")
            self.finished.emit(False, f"Write failed: {e}")

    def _unmount_device(self):
        """Unmount device partitions."""
        try:
            if platform.system() == "Darwin":  # macOS
                subprocess.run(["diskutil", "unmountDisk", self.device_path],
                             check=False, capture_output=True)
            elif platform.system() == "Linux":
                # Unmount all partitions
                result = subprocess.run(
                    ["lsblk", "-ln", "-o", "NAME", self.device_path],
                    capture_output=True, text=True
                )
                for line in result.stdout.strip().split('\n')[1:]:  # Skip device itself
                    part = f"/dev/{line.strip()}"
                    subprocess.run(["umount", part], check=False, capture_output=True)

            self.progress.emit(12, "Device unmounted")
        except Exception as e:
            logger.warning(f"Failed to unmount: {e}")

    def _write_unix(self) -> bool:
        """Write image on Linux/macOS using dd."""
        try:
            # Decompress if needed
            if self.image_path.endswith('.xz'):
                self.progress.emit(20, "Decompressing image...")
                cmd = f"xz -dc '{self.image_path}' | sudo dd of={self.device_path} bs=4M status=progress"
            elif self.image_path.endswith('.gz'):
                cmd = f"gunzip -c '{self.image_path}' | sudo dd of={self.device_path} bs=4M status=progress"
            else:
                cmd = f"sudo dd if='{self.image_path}' of={self.device_path} bs=4M status=progress"

            # Execute dd with progress monitoring
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Monitor progress
            image_size = os.path.getsize(self.image_path)
            while True:
                if self._stop_requested:
                    process.kill()
                    return False

                line = process.stderr.readline()
                if not line and process.poll() is not None:
                    break

                # Parse dd progress
                if "bytes" in line:
                    try:
                        bytes_written = int(line.split()[0])
                        percent = min(int((bytes_written / image_size) * 70) + 20, 90)
                        self.progress.emit(percent, f"Writing: {bytes_written / (1024**3):.2f} GB")
                    except:
                        pass

            # Check exit code
            return_code = process.wait()
            if return_code != 0:
                error = process.stderr.read()
                raise Exception(f"dd failed: {error}")

            return True

        except Exception as e:
            logger.error(f"Unix write failed: {e}")
            return False

    def _write_windows(self) -> bool:
        """Write image on Windows."""
        # For Windows, we need special handling
        # This requires Win32DiskImager or similar tool, or using pywin32
        # For now, provide instructions to user

        self.progress.emit(50, "Windows write not yet implemented")
        self.finished.emit(
            False,
            "Windows SD card writing requires administrator privileges.\n\n"
            "Please use one of these tools:\n"
            "- Raspberry Pi Imager (recommended)\n"
            "- balenaEtcher\n"
            "- Win32 Disk Imager\n\n"
            f"Image file: {self.image_path}"
        )
        return False

    def _verify_write(self) -> bool:
        """Verify written image."""
        try:
            # Read back some of the written data and compare
            block_size = 4096
            blocks_to_verify = 1000  # Verify first ~4MB

            with open(self.image_path, 'rb') as img_file:
                with open(self.device_path, 'rb') as dev_file:
                    for i in range(blocks_to_verify):
                        if self._stop_requested:
                            return False

                        img_block = img_file.read(block_size)
                        dev_block = dev_file.read(block_size)

                        if img_block != dev_block:
                            return False

                        if i % 100 == 0:
                            percent = 92 + int((i / blocks_to_verify) * 7)
                            self.progress.emit(percent, f"Verifying: {percent}%")

            return True

        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return False

    def _safely_eject(self):
        """Safely eject the SD card."""
        try:
            self.progress.emit(98, "Syncing and ejecting...")

            if platform.system() == "Darwin":
                subprocess.run(["diskutil", "eject", self.device_path], check=True)
            elif platform.system() == "Linux":
                subprocess.run(["sync"], check=True)
                subprocess.run(["eject", self.device_path], check=False)

            self.progress.emit(100, "SD card ejected safely")

        except Exception as e:
            logger.warning(f"Eject failed: {e}")

    def request_stop(self):
        """Request thread to stop."""
        self._stop_requested = True


def get_removable_drives() -> List[Dict[str, str]]:
    """Get list of removable drives (potential SD cards).

    Returns:
        List of dictionaries with drive information
    """
    drives = []

    try:
        if platform.system() == "Linux":
            # Use lsblk to find removable drives
            result = subprocess.run(
                ["lsblk", "-d", "-n", "-o", "NAME,SIZE,RM,TYPE,VENDOR,MODEL"],
                capture_output=True,
                text=True,
                check=True
            )

            for line in result.stdout.strip().split('\n'):
                parts = line.split()
                if len(parts) >= 3 and parts[2] == '1':  # Removable
                    drives.append({
                        'device': f"/dev/{parts[0]}",
                        'name': f"{parts[0]} - {parts[1]}",
                        'size': parts[1],
                        'vendor': ' '.join(parts[4:]) if len(parts) > 4 else 'Unknown'
                    })

        elif platform.system() == "Darwin":  # macOS
            result = subprocess.run(
                ["diskutil", "list", "-plist"],
                capture_output=True,
                text=True,
                check=True
            )

            # Parse diskutil output
            result = subprocess.run(
                ["diskutil", "list"],
                capture_output=True,
                text=True,
                check=True
            )

            # Simple parsing for /dev/diskN
            for line in result.stdout.split('\n'):
                if '/dev/disk' in line and 'external' in line.lower():
                    parts = line.split()
                    device = parts[0]
                    drives.append({
                        'device': device,
                        'name': device,
                        'size': 'Unknown',
                        'vendor': 'Removable'
                    })

        elif platform.system() == "Windows":
            # Windows drive detection
            import string
            import ctypes

            kernel32 = ctypes.windll.kernel32
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                drive_type = kernel32.GetDriveTypeW(drive)

                # DRIVE_REMOVABLE = 2
                if drive_type == 2:
                    drives.append({
                        'device': f"\\\\.\\PhysicalDrive{ord(letter) - ord('A')}",
                        'name': f"{letter}: (Removable)",
                        'size': 'Unknown',
                        'vendor': 'Removable'
                    })

    except Exception as e:
        logger.error(f"Failed to list drives: {e}")

    return drives


class SDCardWriter(QDialog):
    """SD Card Writer dialog."""

    def __init__(self, parent=None):
        """Initialize SD card writer."""
        if not PYQT_AVAILABLE:
            raise ImportError("PyQt6 is required")

        super().__init__(parent)

        self.writer_thread: Optional[ImageWriterThread] = None
        self.image_path: Optional[str] = None
        self.device_path: Optional[str] = None

        self.setWindowTitle("SD Card Writer")
        self.resize(700, 600)

        self._setup_ui()

    def _setup_ui(self):
        """Set up user interface."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("<h2>SD Card Writer</h2>")
        layout.addWidget(header)

        # Warning
        warning = QLabel(
            "⚠️ <b>WARNING:</b> This will erase ALL data on the selected device!"
        )
        warning.setStyleSheet("QLabel { color: red; background-color: #fff3cd; padding: 10px; }")
        warning.setWordWrap(True)
        layout.addWidget(warning)

        # Image selection
        image_group = QGroupBox("1. Select Image")
        image_layout = QFormLayout()

        image_row = QHBoxLayout()
        self.image_path_label = QLabel("<i>No image selected</i>")
        image_row.addWidget(self.image_path_label)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_image)
        image_row.addWidget(browse_btn)

        image_layout.addRow("Image File:", image_row)
        image_group.setLayout(image_layout)
        layout.addWidget(image_group)

        # Device selection
        device_group = QGroupBox("2. Select Target Device")
        device_layout = QVBoxLayout()

        device_row = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(300)
        device_row.addWidget(self.device_combo)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_drives)
        device_row.addWidget(refresh_btn)

        device_layout.addLayout(device_row)

        self.device_info_label = QLabel("<i>No device selected</i>")
        self.device_info_label.setWordWrap(True)
        device_layout.addWidget(self.device_info_label)

        device_group.setLayout(device_layout)
        layout.addWidget(device_group)

        # Options
        options_group = QGroupBox("3. Options")
        options_layout = QVBoxLayout()

        self.verify_check = QCheckBox("Verify after writing (recommended)")
        self.verify_check.setChecked(True)
        options_layout.addWidget(self.verify_check)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # Progress
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout()

        self.progress_bar = QProgressBar()
        progress_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready")
        progress_layout.addWidget(self.status_label)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(150)
        self.log_output.setFont(QFont("Monospace", 9))
        progress_layout.addWidget(self.log_output)

        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)

        # Buttons
        button_layout = QHBoxLayout()

        self.write_btn = QPushButton("Write Image")
        self.write_btn.clicked.connect(self._write_image)
        self.write_btn.setEnabled(False)
        self.write_btn.setStyleSheet("QPushButton { font-weight: bold; padding: 10px; }")
        button_layout.addWidget(self.write_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel_write)
        self.cancel_btn.setEnabled(False)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

        # Initial drive refresh
        self._refresh_drives()

    def _browse_image(self):
        """Browse for image file."""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Raspberry Pi Image",
            str(Path.home()),
            "Image Files (*.img *.img.xz *.img.gz);;All Files (*)"
        )

        if filename:
            self.image_path = filename
            self.image_path_label.setText(Path(filename).name)
            self._log(f"Selected image: {filename}")
            self._update_write_button()

    def _refresh_drives(self):
        """Refresh list of removable drives."""
        self._log("Scanning for removable drives...")

        self.device_combo.clear()
        drives = get_removable_drives()

        if not drives:
            self.device_combo.addItem("No removable drives found")
            self._log("No removable drives detected")
            self.device_info_label.setText("<i>No removable drives detected</i>")
        else:
            for drive in drives:
                self.device_combo.addItem(drive['name'], drive)

            self._log(f"Found {len(drives)} removable drive(s)")
            self._on_device_changed()

        self.device_combo.currentIndexChanged.connect(self._on_device_changed)
        self._update_write_button()

    def _on_device_changed(self):
        """Handle device selection change."""
        drive = self.device_combo.currentData()
        if drive:
            self.device_path = drive['device']
            info = f"Device: {drive['device']}\nSize: {drive['size']}\nVendor: {drive['vendor']}"
            self.device_info_label.setText(info)
        else:
            self.device_path = None
            self.device_info_label.setText("<i>No device selected</i>")

        self._update_write_button()

    def _update_write_button(self):
        """Update write button state."""
        can_write = (
            self.image_path is not None and
            self.device_path is not None and
            self.device_combo.currentData() is not None
        )
        self.write_btn.setEnabled(can_write)

    def set_image_path(self, image_path: str):
        """Set the image path and update UI.

        Args:
            image_path: Path to image file
        """
        if os.path.exists(image_path):
            self.image_path = image_path
            self.image_path_label.setText(Path(image_path).name)
            self._log(f"Pre-selected image: {image_path}")
            self._update_write_button()
        else:
            logger.warning(f"Image path does not exist: {image_path}")

    def _write_image(self):
        """Write image to SD card."""
        # Final confirmation
        reply = QMessageBox.warning(
            self,
            "Confirm Write",
            f"⚠️ WARNING ⚠️\n\n"
            f"This will ERASE ALL DATA on:\n"
            f"{self.device_path}\n\n"
            f"Image: {Path(self.image_path).name}\n\n"
            f"Are you absolutely sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Check for admin/root privileges
        if platform.system() != "Windows" and os.geteuid() != 0:
            QMessageBox.warning(
                self,
                "Insufficient Privileges",
                "SD card writing requires administrator/root privileges.\n\n"
                "Please run the LabLink client with sudo:\n"
                "sudo python main.py"
            )
            return

        # Start write
        self._log("=" * 60)
        self._log(f"Writing image: {self.image_path}")
        self._log(f"To device: {self.device_path}")
        self._log("=" * 60)

        self.writer_thread = ImageWriterThread(
            self.image_path,
            self.device_path,
            self.verify_check.isChecked()
        )
        self.writer_thread.progress.connect(self._on_progress)
        self.writer_thread.finished.connect(self._on_finished)
        self.writer_thread.start()

        self.write_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.device_combo.setEnabled(False)

    def _cancel_write(self):
        """Cancel ongoing write operation."""
        if self.writer_thread and self.writer_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "Cancel Write",
                "Are you sure you want to cancel the write operation?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.writer_thread.request_stop()
                self._log("Cancelling write...")

    def _on_progress(self, percent: int, message: str):
        """Handle progress update."""
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)
        self._log(f"[{percent}%] {message}")

    def _on_finished(self, success: bool, message: str):
        """Handle write completion."""
        self.progress_bar.setValue(100 if success else 0)
        self.status_label.setText(message)
        self._log("=" * 60)
        self._log(f"Result: {'SUCCESS' if success else 'FAILED'}")
        self._log(message)
        self._log("=" * 60)

        self.write_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.device_combo.setEnabled(True)

        # Show result dialog
        if success:
            QMessageBox.information(
                self,
                "Success",
                "Image written successfully!\n\n"
                "You can now remove the SD card and insert it into your Raspberry Pi."
            )
        else:
            QMessageBox.critical(
                self,
                "Failed",
                f"Image write failed:\n\n{message}"
            )

    def _log(self, message: str):
        """Add message to log output."""
        self.log_output.append(message)
        logger.info(message)
