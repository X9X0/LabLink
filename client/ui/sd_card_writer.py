"""SD Card Writer - Write Raspberry Pi images to SD cards."""

import hashlib
import logging
import os
import platform
import shlex
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

try:
    from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
    from PyQt6.QtGui import QFont, QAction
    from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog,
                                 QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                                 QListWidget, QListWidgetItem, QMenu,
                                 QMessageBox, QProgressBar, QPushButton,
                                 QTextEdit, QVBoxLayout, QWidget)

    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

logger = logging.getLogger(__name__)


class _DiskScanThread(QThread):
    """Enumerate disks off the GUI thread.

    ``list_disks`` starts PowerShell, which measured at about three seconds on
    the machine this was written for. Called from a QTimer that would run on
    the GUI thread, and freeze it -- at the exact moment the user inserts the
    card and is watching for a response.
    """

    result = pyqtSignal(object)  # list[Disk], or None if the scan failed

    def run(self):
        try:
            from client.utils.sd_write_win import list_disks

            self.result.emit(list_disks())
        except Exception:  # a failed scan is a retry, not a crash
            logger.debug("Disk scan failed", exc_info=True)
            self.result.emit(None)


class DetectCardDialog(QDialog):
    """Identify the card by watching one appear.

    Picking a disk from a list is where this goes wrong: the entries look
    alike, a card reader often reports itself as a fixed disk, and the cost of
    a misclick is somebody's drive. Asking the user to insert the card and
    taking whatever turns up removes the guess entirely -- the disk that was
    not there ten seconds ago is the card, whatever it claims to be.

    The manual chooser is still here behind a button, because sometimes the
    watch does not fire -- a reader that stays enumerated with the card in it,
    for instance -- and someone who knows their hardware should not be stuck.
    It refuses non-removable media until it is confirmed a second time, and
    refuses the system disk always.
    """

    POLL_MS = 1000

    def __init__(self, image_size: int, parent=None):
        super().__init__(parent)
        self.image_size = image_size
        self.selected_disk = None
        self.override_used = False
        self._baseline = set()
        self._manual = False

        self.setWindowTitle("Insert the SD card")
        self.setMinimumWidth(560)
        self._setup_ui()
        self._start_watching()

    def _setup_ui(self):
        layout = QVBoxLayout()

        title = QLabel("Insert the SD card now")
        f = QFont()
        f.setPointSize(12)
        f.setBold(True)
        title.setFont(f)
        layout.addWidget(title)

        self.instructions = QLabel(
            "Please insert the SD card now.\n\n"
            "If it is already inserted, remove it and insert it again.\n\n"
            "Watching for a new drive to appear -- whichever one shows up is "
            "the card, so there is nothing to pick and nothing to get wrong."
        )
        self.instructions.setWordWrap(True)
        layout.addWidget(self.instructions)

        self.status = QLabel("<i>Waiting for a card...</i>")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.disk_list = QListWidget()
        self.disk_list.setVisible(False)
        self.disk_list.itemSelectionChanged.connect(self._on_manual_selection)
        layout.addWidget(self.disk_list)

        buttons = QHBoxLayout()
        self.manual_button = QPushButton("Choose manually (advanced)")
        self.manual_button.setToolTip(
            "Skip detection and pick a disk yourself. Only if you are certain "
            "which one it is."
        )
        self.manual_button.clicked.connect(self._show_manual)
        buttons.addWidget(self.manual_button)

        buttons.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)

        self.use_button = QPushButton("Use this card")
        self.use_button.setEnabled(False)
        self.use_button.setDefault(True)
        self.use_button.clicked.connect(self._accept_selection)
        buttons.addWidget(self.use_button)

        layout.addLayout(buttons)
        self.setLayout(layout)

    def _start_watching(self):
        """Take the baseline on a worker, so the dialog opens immediately."""
        self._mask = self._drive_letter_mask()
        self._ticks = 0
        self._scan = None
        self._baseline = None  # not established yet

        self.status.setText("<i>Looking at the drives already attached...</i>")

        self._baseline_scan = _DiskScanThread(self)
        self._baseline_scan.result.connect(self._on_baseline)
        self._baseline_scan.start()

    def _on_baseline(self, disks):
        if disks is None:
            self.status.setText(
                "<b>Could not list disks.</b> Use "
                "<i>Choose manually</i>, or close and try again."
            )
            return

        self._baseline = {d.number for d in disks}
        self.status.setText(
            f"<i>Watching. {len(disks)} drive(s) already attached -- "
            "insert the card now.</i>"
        )

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(self.POLL_MS)

    def _drive_letter_mask(self) -> int:
        """A cheap fingerprint of what is mounted, for skipping the real scan.

        Enumerating disks means starting PowerShell, which costs a good part
        of a second. Doing that once a second is heavy on its own and was
        visibly janky besides. GetLogicalDrives is a single call into
        kernel32, so it can be polled freely, and inserting a card almost
        always changes it -- the boot partition is FAT and gets a letter.

        It is only a trigger, not the answer: a full scan still runs on a
        slower beat, so a card that somehow claims no drive letter is found a
        few seconds later rather than never.
        """
        try:
            import ctypes

            return int(ctypes.windll.kernel32.GetLogicalDrives())
        except Exception:
            return -1  # unavailable, so always take the slow path

    def _poll(self):
        """Decide whether a scan is worth starting. Never scans inline."""
        if self._manual or self._scan is not None or self._baseline is None:
            return

        self._ticks = getattr(self, "_ticks", 0) + 1
        mask = self._drive_letter_mask()
        changed = mask != getattr(self, "_mask", mask)
        self._mask = mask

        # Full scan when something mounted or unmounted, and every few ticks
        # regardless as a backstop.
        if not changed and mask != -1 and self._ticks % 4:
            return

        self._scan = _DiskScanThread(self)
        self._scan.result.connect(self._on_scan)
        self._scan.finished.connect(self._scan_done)
        self._scan.start()

    def _scan_done(self):
        self._scan = None

    def _on_scan(self, disks):
        from client.utils.sd_write_win import newly_appeared

        if disks is None or self._manual:
            return

        found = newly_appeared(self._baseline, disks)

        if not found:
            return
        if len(found) > 1:
            # Two at once is ambiguous, and guessing is the one thing this
            # dialog exists to avoid.
            self.status.setText(
                "<b>More than one drive appeared.</b> Remove them all, then "
                "insert only the SD card."
            )
            return

        self.timer.stop()
        disk = found[0]
        self.selected_disk = disk
        self.status.setText(
            f"<b>Found:</b> {disk.describe()}<br><br>"
            "Everything on it will be erased."
        )
        self.use_button.setEnabled(True)

    def _show_manual(self):
        """The override. Lists every disk, with the dangerous ones marked."""
        from client.utils.sd_write_win import SDWriteError, list_disks

        self._manual = True
        if hasattr(self, "timer"):
            self.timer.stop()

        try:
            disks = list_disks()
        except SDWriteError as exc:
            self.status.setText(f"<b>Could not list disks:</b> {exc}")
            return

        self.disk_list.clear()
        for disk in disks:
            label = disk.describe()
            if disk.is_system or disk.is_boot:
                label += "   [SYSTEM DISK - cannot be written]"
            elif not disk.looks_removable:
                label += "   [not removable media]"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, disk)
            if disk.is_system or disk.is_boot:
                item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.disk_list.addItem(item)

        self.disk_list.setVisible(True)
        self.instructions.setText(
            "Choosing manually. The disk you pick will be completely erased.\n\n"
            "The system disk cannot be selected. Anything that is not "
            "removable media will ask again before writing."
        )
        self.status.setText("<i>Select a disk.</i>")
        self.manual_button.setEnabled(False)
        self.selected_disk = None
        self.use_button.setEnabled(False)

    def _on_manual_selection(self):
        items = self.disk_list.selectedItems()
        if not items:
            self.selected_disk = None
            self.use_button.setEnabled(False)
            return
        disk = items[0].data(Qt.ItemDataRole.UserRole)
        self.selected_disk = disk
        self.status.setText(f"<b>Selected:</b> {disk.describe()}")
        self.use_button.setEnabled(True)

    def _accept_selection(self):
        from client.utils.sd_write_win import SDWriteError, check_target

        disk = self.selected_disk
        if disk is None:
            return

        # Try the strict rules first; only ask about the override if they are
        # what stands in the way.
        try:
            check_target(disk, self.image_size, override=False)
        except SDWriteError as exc:
            if disk.is_system or disk.is_boot:
                QMessageBox.critical(self, "Refused", str(exc))
                return
            if self.image_size > disk.size or disk.size <= 0:
                QMessageBox.critical(self, "Refused", str(exc))
                return

            reply = QMessageBox.warning(
                self, "Not removable media",
                f"{exc}\n\nWrite to it anyway? Everything on it will be lost.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self.override_used = True

        letters = ", ".join(f"{d}:" for d in disk.drive_letters)
        confirm = QMessageBox.warning(
            self, "Erase this card?",
            f"{disk.describe()}\n\n"
            + (f"This will erase {letters} and everything on the card.\n\n"
               if letters else "This will erase everything on the card.\n\n")
            + "This cannot be undone. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.accept()

    def closeEvent(self, event):
        if hasattr(self, "timer"):
            self.timer.stop()
        super().closeEvent(event)


class ImageWriterThread(QThread):
    """Thread for writing images to SD cards."""

    progress = pyqtSignal(int, str)  # Progress percentage, message
    finished = pyqtSignal(bool, str)  # Success, message

    def __init__(self, image_path: str, device_path: str, verify: bool = True):
        r"""Initialize writer thread.

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
            self.progress.emit(8, f"Image size: {image_size / (1024**3):.2f} GB")

            # Unmount device (Linux/macOS)
            if platform.system() in ["Linux", "Darwin"]:
                self._unmount_device()

            self.progress.emit(10, "Checking device readiness...")
            self.progress.emit(15, "Starting write operation...")

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
                subprocess.run(
                    ["diskutil", "unmountDisk", self.device_path],
                    check=False,
                    capture_output=True,
                )
            elif platform.system() == "Linux":
                # Unmount all partitions
                result = subprocess.run(
                    ["lsblk", "-ln", "-o", "NAME", self.device_path],
                    capture_output=True,
                    text=True,
                )
                for line in result.stdout.strip().split("\n")[1:]:  # Skip device itself
                    part = f"/dev/{line.strip()}"
                    subprocess.run(["umount", part], check=False, capture_output=True)

            self.progress.emit(12, "Device unmounted")

            # Wait a moment for the kernel to settle after unmount
            import time
            time.sleep(1)

        except Exception as e:
            logger.warning(f"Failed to unmount: {e}")

    def _write_unix(self) -> bool:
        """Write image on Linux/macOS using dd."""
        try:
            # Check if pkexec is available
            pkexec_available = subprocess.run(
                ['which', 'pkexec'],
                capture_output=True,
                check=False
            ).returncode == 0

            # Create a wrapper script for the write operation
            import tempfile

            # Build the dd command — quote paths to prevent shell injection
            qimage = shlex.quote(self.image_path)
            qdevice = shlex.quote(self.device_path)
            if self.image_path.endswith(".xz"):
                dd_cmd = f"xz -dc {qimage} | dd of={qdevice} bs=4M status=progress"
            elif self.image_path.endswith(".gz"):
                dd_cmd = f"gunzip -c {qimage} | dd of={qdevice} bs=4M status=progress"
            else:
                dd_cmd = f"dd if={qimage} of={qdevice} bs=4M status=progress"

            # Create wrapper script
            script_content = f"""#!/bin/bash
set -e
exec 2>&1  # Redirect stderr to stdout so we can capture it

# Function to check if device is ready
check_device_ready() {{
    local device="$1"
    local max_attempts=10
    local attempt=1

    echo "Checking if device $device is ready..."

    while [ $attempt -le $max_attempts ]; do
        # Check if device exists as a block device
        if [ ! -b "$device" ]; then
            echo "Attempt $attempt/$max_attempts: Device $device is not a block device"
            sleep 1
            attempt=$((attempt + 1))
            continue
        fi

        # Try to read device size to verify medium is present
        if blockdev --getsize64 "$device" &>/dev/null; then
            local size=$(blockdev --getsize64 "$device" 2>/dev/null)
            if [ "$size" -gt 0 ]; then
                echo "Device ready: $device (size: $size bytes)"
                return 0
            fi
        fi

        echo "Attempt $attempt/$max_attempts: Device not ready or no medium found"
        sleep 1
        attempt=$((attempt + 1))
    done

    echo "Error: Device $device is not ready after $max_attempts attempts"
    echo "Please check that:"
    echo "  1. The SD card is properly inserted"
    echo "  2. The SD card reader is connected"
    echo "  3. Try unplugging and re-plugging the SD card reader"
    return 1
}}

# Check if device is ready
if ! check_device_ready "{self.device_path}"; then
    exit 1
fi

# Flush filesystem buffers and re-read partition table
echo "Flushing buffers and re-reading partition table..."
sync
blockdev --rereadpt "{self.device_path}" 2>/dev/null || true
sleep 1

# Final verification before writing
echo "Final device check before writing..."
if ! blockdev --getsize64 "{self.device_path}" &>/dev/null; then
    echo "Error: Device became unavailable just before writing"
    exit 1
fi

echo "Starting write operation..."
{dd_cmd}

# Ensure all writes are flushed
echo "Flushing final writes..."
sync
"""

            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
                f.write(script_content)
                script_path = f.name

            # Make script executable
            os.chmod(script_path, 0o755)

            try:
                if self.image_path.endswith(".xz"):
                    self.progress.emit(20, "Decompressing and writing image...")
                elif self.image_path.endswith(".gz"):
                    self.progress.emit(20, "Decompressing and writing image...")
                else:
                    self.progress.emit(20, "Writing image...")

                # Execute with pkexec or sudo
                if pkexec_available:
                    cmd = ['pkexec', 'bash', script_path]
                else:
                    cmd = ['sudo', 'bash', script_path]

                # Execute with progress monitoring
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,  # Combine stderr into stdout
                    text=True,
                )

                # Monitor progress
                image_size = os.path.getsize(self.image_path)
                output_lines = []

                while True:
                    if self._stop_requested:
                        process.kill()
                        return False

                    line = process.stdout.readline()
                    if not line and process.poll() is not None:
                        break

                    if line:
                        output_lines.append(line.strip())
                        logger.debug(f"dd output: {line.strip()}")

                    # Parse dd progress (format: "123456789 bytes (123 MB, 117 MiB) copied")
                    if "bytes" in line and "copied" in line:
                        try:
                            parts = line.split()
                            bytes_written = int(parts[0])
                            percent = min(int((bytes_written / image_size) * 70) + 20, 90)
                            self.progress.emit(
                                percent, f"Writing: {bytes_written / (1024**3):.2f} GB"
                            )
                        except (ValueError, IndexError) as e:
                            logger.debug(f"Failed to parse progress: {e}")

                # Wait for completion
                return_code = process.wait()

                # Clean up script
                try:
                    os.unlink(script_path)
                except Exception as e:
                    logger.warning(f"Failed to clean up script: {e}")

                if return_code != 0:
                    error_output = '\n'.join(output_lines[-10:])  # Last 10 lines
                    raise Exception(f"dd failed with exit code {return_code}:\n{error_output}")

                return True

            except Exception as e:
                # Clean up script on error
                try:
                    os.unlink(script_path)
                except Exception:
                    pass
                raise

        except Exception as e:
            logger.error(f"Unix write failed: {e}")
            return False

    def _write_windows(self) -> bool:
        """Write the card through an elevated helper process.

        Raw device access needs administrator rights, and a process cannot
        elevate itself, so this starts a second one via ShellExecute's
        ``runas`` verb. That is where the UAC prompt comes from.

        Note the scope: the image *builder* needs no privileges on any
        platform, which is the point of that work. Only putting a finished
        image onto a card does -- Raspberry Pi Imager prompts for it too.

        ``self.device_path`` must be a real ``\\\\.\\PhysicalDriveN``. It is
        set from the disk number that ``DetectCardDialog`` identified, never
        derived from a drive letter.
        """
        import json
        import tempfile
        import time

        from client.utils.sd_write_win import (SDWriteError, list_disks,
                                               run_elevated)

        try:
            number = int(str(self.device_path).rsplit("PhysicalDrive", 1)[1])
        except (IndexError, ValueError):
            self.finished.emit(
                False, f"Not a physical disk path: {self.device_path}")
            return False

        # The card may have been pulled between choosing and writing.
        try:
            disk = next((d for d in list_disks() if d.number == number), None)
        except SDWriteError as exc:
            self.finished.emit(False, str(exc))
            return False
        if disk is None:
            self.finished.emit(
                False, f"Disk {number} is no longer present. Was the card removed?")
            return False

        progress_path = os.path.join(tempfile.gettempdir(),
                                     f"lablink-sdwrite-{os.getpid()}.jsonl")
        if os.path.exists(progress_path):
            os.remove(progress_path)

        self.progress.emit(2, "Asking for administrator rights...")
        try:
            run_elevated(self.image_path, number, progress_path,
                         override=getattr(self, "override", False),
                         verify=self.verify)
        except SDWriteError as exc:
            self.finished.emit(False, str(exc))
            return False

        # ShellExecute does not give us a pipe, so the helper appends its
        # progress to a file and we follow it.
        last = 0
        failure = None
        seen_end = False
        idle_since = time.time()

        while not self._stop_requested:
            time.sleep(0.5)
            if not os.path.exists(progress_path):
                if time.time() - idle_since > 120:
                    failure = "The elevated writer never started."
                    break
                continue
            try:
                with open(progress_path, "r", encoding="utf-8") as fh:
                    lines = fh.read().splitlines()
            except OSError:
                continue

            for line in lines[last:]:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                pct, msg = event.get("percent", 0), event.get("message", "")
                if pct < 0:
                    failure = msg
                    seen_end = True
                else:
                    self.progress.emit(pct, msg)
                    if pct >= 100:
                        seen_end = True
                idle_since = time.time()
            last = len(lines)

            if seen_end:
                break
            if time.time() - idle_since > 600:
                failure = "The elevated writer stopped responding."
                break

        try:
            os.remove(progress_path)
        except OSError:
            pass

        if self._stop_requested:
            self.finished.emit(False, "Cancelled. The card is probably unusable.")
            return False
        if failure:
            self.finished.emit(False, failure)
            return False

        self.finished.emit(True, f"Card written and verified: {disk.describe()}")
        return True

    def _verify_write(self) -> bool:
        """Verify written image."""
        try:
            import tempfile

            # Check if pkexec is available
            pkexec_available = subprocess.run(
                ['which', 'pkexec'],
                capture_output=True,
                check=False
            ).returncode == 0

            # Create verification script that compares first 100MB of image with device
            qimage = shlex.quote(self.image_path)
            qdevice = shlex.quote(self.device_path)
            verify_script = f"""#!/bin/bash
set -e
exec 2>&1

echo "Verifying first 100MB of written image..."

# Compare first 100MB (102400 blocks of 1024 bytes)
if cmp -n 104857600 {qimage} {qdevice}; then
    echo "Verification successful: Data matches!"
    exit 0
else
    echo "Verification failed: Data mismatch!"
    exit 1
fi
"""

            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
                f.write(verify_script)
                script_path = f.name

            # Make script executable
            os.chmod(script_path, 0o755)

            try:
                # Execute with pkexec or sudo
                if pkexec_available:
                    cmd = ['pkexec', 'bash', script_path]
                else:
                    cmd = ['sudo', 'bash', script_path]

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

                # Monitor verification output
                while True:
                    if self._stop_requested:
                        process.kill()
                        return False

                    line = process.stdout.readline()
                    if not line and process.poll() is not None:
                        break

                    if line:
                        logger.debug(f"Verify output: {line.strip()}")
                        if "Verifying" in line:
                            self.progress.emit(95, "Verifying: 50%")

                # Wait for completion
                return_code = process.wait()

                # Clean up script
                try:
                    os.unlink(script_path)
                except Exception as e:
                    logger.warning(f"Failed to clean up verify script: {e}")

                return return_code == 0

            except Exception as e:
                # Clean up script on error
                try:
                    os.unlink(script_path)
                except Exception:
                    pass
                raise

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
                # Sync is already done in the write script, but do it again to be safe
                subprocess.run(["sync"], check=True)

                # Check if pkexec is available for eject
                pkexec_available = subprocess.run(
                    ['which', 'pkexec'],
                    capture_output=True,
                    check=False
                ).returncode == 0

                # Try to eject with elevated privileges
                if pkexec_available:
                    subprocess.run(["pkexec", "eject", self.device_path], check=False, capture_output=True)
                else:
                    subprocess.run(["sudo", "eject", self.device_path], check=False, capture_output=True)

            self.progress.emit(100, "SD card ready to remove")

        except Exception as e:
            logger.warning(f"Eject failed: {e}")

    def request_stop(self):
        """Request thread to stop."""
        self._stop_requested = True


def find_recent_images(max_results: int = 10) -> List[Dict[str, str]]:
    """Find recent Raspberry Pi image files in common locations.

    Args:
        max_results: Maximum number of results to return

    Returns:
        List of dictionaries with image file information
    """
    images = []
    search_paths = []

    # Add common search locations
    home = Path.home()

    # Build output directory
    search_paths.append(home)

    # LabLink directory
    lablink_dir = home / "LabLink"
    if lablink_dir.exists():
        search_paths.append(lablink_dir)

    # LabLink-* directories (case-insensitive)
    try:
        for item in home.iterdir():
            if item.is_dir() and item.name.lower().startswith("lablink-"):
                search_paths.append(item)
    except Exception as e:
        logger.debug(f"Error scanning for LabLink-* directories: {e}")

    # Downloads directory
    downloads = home / "Downloads"
    if downloads.exists():
        search_paths.append(downloads)

    # Temp build directory
    temp_build = Path("/tmp/lablink-pi-build")
    if temp_build.exists():
        search_paths.append(temp_build)

    # Desktop (sometimes used for output)
    desktop = home / "Desktop"
    if desktop.exists():
        search_paths.append(desktop)

    # Find all .img and .img.xz files
    for search_path in search_paths:
        try:
            # Search for .img files
            for pattern in ["*.img", "*.img.xz", "*.img.gz"]:
                for img_path in search_path.glob(pattern):
                    if img_path.is_file():
                        stat = img_path.stat()
                        images.append({
                            "path": str(img_path),
                            "name": img_path.name,
                            "size": stat.st_size,
                            "modified": stat.st_mtime,
                            "modified_str": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                        })

            # Also check subdirectories one level deep for build directories
            if search_path == home or search_path == temp_build:
                for subdir in search_path.iterdir():
                    if subdir.is_dir():
                        for pattern in ["*.img", "*.img.xz", "*.img.gz"]:
                            for img_path in subdir.glob(pattern):
                                if img_path.is_file():
                                    stat = img_path.stat()
                                    images.append({
                                        "path": str(img_path),
                                        "name": img_path.name,
                                        "size": stat.st_size,
                                        "modified": stat.st_mtime,
                                        "modified_str": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                                    })
        except Exception as e:
            logger.debug(f"Error searching {search_path}: {e}")

    # Remove duplicates and sort by modification time (newest first)
    seen = set()
    unique_images = []
    for img in sorted(images, key=lambda x: x["modified"], reverse=True):
        if img["path"] not in seen:
            seen.add(img["path"])
            unique_images.append(img)

    return unique_images[:max_results]


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
                check=True,
            )

            for line in result.stdout.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 3 and parts[2] == "1":  # Removable
                    drives.append(
                        {
                            "device": f"/dev/{parts[0]}",
                            "name": f"{parts[0]} - {parts[1]}",
                            "size": parts[1],
                            "vendor": (
                                " ".join(parts[4:]) if len(parts) > 4 else "Unknown"
                            ),
                        }
                    )

        elif platform.system() == "Darwin":  # macOS
            result = subprocess.run(
                ["diskutil", "list", "-plist"],
                capture_output=True,
                text=True,
                check=True,
            )

            # Parse diskutil output
            result = subprocess.run(
                ["diskutil", "list"], capture_output=True, text=True, check=True
            )

            # Simple parsing for /dev/diskN
            for line in result.stdout.split("\n"):
                if "/dev/disk" in line and "external" in line.lower():
                    parts = line.split()
                    device = parts[0]
                    drives.append(
                        {
                            "device": device,
                            "name": device,
                            "size": "Unknown",
                            "vendor": "Removable",
                        }
                    )

        elif platform.system() == "Windows":
            # Ask Get-Disk for the real disk number. This used to walk drive
            # letters and compute the device as
            #
            #     f"\\\\.\\PhysicalDrive{ord(letter) - ord('A')}"
            #
            # which is not a mapping that exists: D: became PhysicalDrive3
            # whatever disk 3 happened to be, and C: became PhysicalDrive2 on
            # a machine whose only disk is 0. It was never noticed because the
            # write itself was a stub, so the wrong path was never opened.
            from client.utils.sd_write_win import list_disks

            for disk in list_disks():
                if disk.is_system or disk.is_boot:
                    continue
                letters = ", ".join(f"{d}:" for d in disk.drive_letters)
                drives.append(
                    {
                        "device": disk.device_path,
                        "name": f"Disk {disk.number}: {disk.name or 'unknown'}"
                                + (f" ({letters})" if letters else ""),
                        "size": f"{disk.size_gb} GB",
                        "vendor": disk.bus_type or "unknown bus",
                    }
                )

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

        # Apply visual styling. Colours come from the theme: a stylesheet set
        # on a widget overrides the application one, so hardcoded white here
        # survived into dark mode and met the dark sheet's pale text.
        from client.ui.theme import dialog_palette

        _c = dialog_palette()
        self.setStyleSheet("""
            QDialog {{
                background-color: {window_bg};
                color: {text};
            }}
            QGroupBox {{
                border: 2px solid {panel_border};
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 15px;
                background-color: {panel_bg};
                color: {text};
                font-weight: bold;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 15px;
                padding: 5px 10px;
                background-color: {panel_bg};
                color: {text};
            }}
            QLabel {{
                color: {text};
            }}
            QListWidget, QComboBox, QTextEdit, QLineEdit {{
                background-color: {field_bg};
                color: {text};
                border: 1px solid {panel_border};
                border-radius: 4px;
            }}
            QPushButton {{
                background-color: #3498db;
                color: white;
                border: 2px solid #2471a3;
                border-radius: 6px;
                padding: 8px 15px;
                min-height: 30px;
            }}
            QPushButton:hover {{
                background-color: #2e86c1;
                border: 2px solid #1f618d;
            }}
            QPushButton:pressed {{
                background-color: #2471a3;
            }}
            QPushButton:disabled {{
                background-color: #95a5a6;
                border: 2px solid #7f8c8d;
            }}
        """.format(**_c))

        self._setup_ui()

    def _setup_ui(self):
        """Set up user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Header
        header = QLabel("<h2>SD Card Writer</h2>")
        layout.addWidget(header)

        # Warning
        warning = QLabel(
            "⚠️ <b>WARNING:</b> This will erase ALL data on the selected device!"
        )
        warning.setStyleSheet(
            "QLabel { color: red; background-color: #fff3cd; padding: 10px; }"
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)

        # Image selection
        image_group = QGroupBox("1. Select Image")
        image_layout = QFormLayout()

        image_row = QHBoxLayout()
        self.image_path_label = QLabel("<i>No image selected</i>")
        image_row.addWidget(self.image_path_label)

        recent_btn = QPushButton("Recent Images")
        recent_btn.clicked.connect(self._show_recent_images)
        recent_btn.setToolTip("Select from recently created or downloaded images")
        image_row.addWidget(recent_btn)

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

        self.verify_check = QCheckBox("Verify after writing (compares first 100MB)")
        self.verify_check.setChecked(False)  # Disabled by default to speed up the process
        self.verify_check.setToolTip("Reads back and compares the first 100MB to verify the write was successful.\nRequires entering your password for root access.")
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
        self.write_btn.setStyleSheet(
            "QPushButton { font-weight: bold; padding: 10px; }"
        )
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
            "Image Files (*.img *.img.xz *.img.gz);;All Files (*)",
        )

        if filename:
            self.image_path = filename
            self.image_path_label.setText(Path(filename).name)
            self._log(f"Selected image: {filename}")
            self._update_write_button()

    def _show_recent_images(self):
        """Show menu with recently created/downloaded images."""
        self._log("Searching for recent images...")

        recent_images = find_recent_images(max_results=15)

        if not recent_images:
            QMessageBox.information(
                self,
                "No Images Found",
                "No recent Raspberry Pi images found.\n\n"
                "Searched in:\n"
                "- Home directory\n"
                "- ~/LabLink/\n"
                "- ~/LabLink-* directories\n"
                "- Downloads folder\n"
                "- /tmp/lablink-pi-build\n"
                "- Desktop\n\n"
                "Use 'Browse...' to select an image manually.",
            )
            return

        # Create menu with recent images
        menu = QMenu(self)

        for img in recent_images:
            # Format: filename (size, date)
            size_mb = img["size"] / (1024 * 1024)
            if size_mb < 1024:
                size_str = f"{size_mb:.1f} MB"
            else:
                size_str = f"{size_mb / 1024:.1f} GB"

            action_text = f"{img['name']}\n    {size_str}, {img['modified_str']}"
            action = QAction(action_text, self)
            action.setData(img["path"])
            action.triggered.connect(lambda checked, path=img["path"]: self._select_image(path))
            menu.addAction(action)

        # Show menu at button
        sender = self.sender()
        if sender:
            menu.exec(sender.mapToGlobal(sender.rect().bottomLeft()))

    def _select_image(self, image_path: str):
        """Select an image from the recent images menu."""
        if os.path.exists(image_path):
            self.image_path = image_path
            self.image_path_label.setText(Path(image_path).name)
            self._log(f"Selected recent image: {image_path}")
            self._update_write_button()
        else:
            QMessageBox.warning(
                self,
                "Image Not Found",
                f"The selected image file no longer exists:\n{image_path}",
            )
            self._log(f"Image not found: {image_path}")

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
                self.device_combo.addItem(drive["name"], drive)

            self._log(f"Found {len(drives)} removable drive(s)")
            self._on_device_changed()

        self.device_combo.currentIndexChanged.connect(self._on_device_changed)
        self._update_write_button()

    def _on_device_changed(self):
        """Handle device selection change."""
        drive = self.device_combo.currentData()
        if drive:
            self.device_path = drive["device"]
            info = f"Device: {drive['device']}\nSize: {drive['size']}\nVendor: {drive['vendor']}"
            self.device_info_label.setText(info)
        else:
            self.device_path = None
            self.device_info_label.setText("<i>No device selected</i>")

        self._update_write_button()

    def _update_write_button(self):
        """Update write button state."""
        can_write = (
            self.image_path is not None
            and self.device_path is not None
            and self.device_combo.currentData() is not None
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
        override = False

        if platform.system() == "Windows":
            # Identify the card by watching one appear rather than trusting
            # whatever is selected in the combo. The dialog does its own
            # confirmation, including the disk's model and size, so there is
            # no second generic "are you sure" after it.
            try:
                image_size = os.path.getsize(self.image_path)
            except OSError as exc:
                QMessageBox.critical(self, "Cannot read image", str(exc))
                return

            dialog = DetectCardDialog(image_size, parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self._log("Write cancelled at card selection")
                return

            disk = dialog.selected_disk
            override = dialog.override_used
            self.device_path = disk.device_path
            self._log(f"Card identified: {disk.describe()}")
            if override:
                self._log("Selected manually, overriding the removable-media check")
        else:
            reply = QMessageBox.warning(
                self,
                "Confirm Write",
                f"⚠️ WARNING ⚠️\n\n"
                f"This will ERASE ALL DATA on:\n"
                f"{self.device_path}\n\n"
                f"Image: {Path(self.image_path).name}\n\n"
                f"Are you absolutely sure?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

        # No privilege check needed - pkexec or UAC handles it in the thread

        # Start write
        self._log("=" * 60)
        self._log(f"Writing image: {self.image_path}")
        self._log(f"To device: {self.device_path}")
        self._log("=" * 60)

        self.writer_thread = ImageWriterThread(
            self.image_path, self.device_path, self.verify_check.isChecked()
        )
        self.writer_thread.override = override
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
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
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

        # Clean up thread
        if self.writer_thread:
            self.writer_thread.wait()  # Wait for thread to finish
            self.writer_thread.deleteLater()  # Schedule for deletion
            self.writer_thread = None

        self.write_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.device_combo.setEnabled(True)

        # Show result dialog
        if success:
            QMessageBox.information(
                self,
                "Success",
                "Image written successfully!\n\n"
                "You can now remove the SD card and insert it into your Raspberry Pi.",
            )
        else:
            QMessageBox.critical(self, "Failed", f"Image write failed:\n\n{message}")

    def _log(self, message: str):
        """Add message to log output."""
        self.log_output.append(message)
        logger.info(message)

    def closeEvent(self, event):
        """Handle window close event.

        Args:
            event: Close event
        """
        # If thread is running, ask for confirmation
        if self.writer_thread and self.writer_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "Write in Progress",
                "An SD card write operation is in progress.\n\n"
                "Closing this window will cancel the operation.\n\n"
                "Are you sure you want to close?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self._log("Cancelling write due to window close...")
                self.writer_thread.request_stop()
                self.writer_thread.wait(3000)  # Wait up to 3 seconds
                if self.writer_thread.isRunning():
                    self.writer_thread.terminate()
                    self.writer_thread.wait()
                event.accept()
            else:
                event.ignore()
        else:
            # Clean up thread if it exists
            if self.writer_thread:
                self.writer_thread.wait()
                self.writer_thread.deleteLater()
                self.writer_thread = None
            event.accept()
