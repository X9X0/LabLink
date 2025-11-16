#!/usr/bin/env python3
"""
LabLink - Unified GUI Entry Point
==================================

A comprehensive GUI launcher for LabLink that provides:
- Environment compatibility checking
- Dependency verification and installation
- LED status indicators for system health
- One-click server/client launching
- Issue resolution and troubleshooting

Author: LabLink Team
License: MIT
"""

import sys
import os
import subprocess
import platform
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

# Bootstrap check: Ensure pip is available before trying to install PyQt6
def check_and_install_pip():
    """Check if pip is available, and install if needed."""
    # Check if pip is available
    result = subprocess.run(
        [sys.executable, '-m', 'pip', '--version'],
        capture_output=True,
        text=True,
        check=False
    )

    if result.returncode != 0:
        print("\n" + "="*70)
        print("ERROR: pip is not installed")
        print("="*70)
        print("\nLabLink requires pip to install dependencies.")
        print("\nOn Ubuntu 24.04, install pip with:")
        print("  sudo apt update")
        print("  sudo apt install -y python3-pip python3-venv")
        print("\nOr use the system package manager to install LabLink dependencies.")
        print("="*70 + "\n")
        sys.exit(1)

# Qt imports with bootstrap handling
try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QGroupBox, QTextEdit, QDialog, QMessageBox,
        QProgressBar, QScrollArea, QFrame
    )
    from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QSize
    from PyQt6.QtGui import QPainter, QColor, QFont, QPalette, QIcon
except ImportError:
    print("\n" + "="*70)
    print("PyQt6 is not installed - Installing now...")
    print("="*70)

    # Make sure pip is available first
    check_and_install_pip()

    # Try to install PyQt6
    try:
        print("\nInstalling PyQt6 for the launcher...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "PyQt6"])
        print("\n" + "="*70)
        print("SUCCESS: PyQt6 installed successfully!")
        print("="*70)
        print("\nPlease run the launcher again:")
        print(f"  python3 {sys.argv[0]}")
        print("="*70 + "\n")
        sys.exit(0)
    except subprocess.CalledProcessError as e:
        print("\n" + "="*70)
        print("ERROR: Failed to install PyQt6")
        print("="*70)
        print(f"\nError: {e}")
        print("\nPlease install manually:")
        print("  python3 -m pip install PyQt6")
        print("\nOr use a virtual environment:")
        print("  python3 -m venv venv")
        print("  source venv/bin/activate")
        print("  pip install PyQt6")
        print(f"  python3 {sys.argv[0]}")
        print("="*70 + "\n")
        sys.exit(1)


# Status levels
class StatusLevel(Enum):
    """Status indicator levels."""
    OK = "green"
    WARNING = "yellow"
    ERROR = "red"
    UNKNOWN = "gray"


@dataclass
class CheckResult:
    """Result of a system check."""
    name: str
    status: StatusLevel
    message: str
    details: List[str]
    fixable: bool = False
    fix_command: Optional[str] = None


class LEDIndicator(QWidget):
    """Custom LED-style status indicator widget."""

    clicked = pyqtSignal()

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.label = label
        self.status = StatusLevel.UNKNOWN
        self.setMinimumSize(200, 60)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_status(self, status: StatusLevel):
        """Update the LED status and repaint."""
        self.status = status
        self.update()

    def paintEvent(self, event):
        """Draw the LED indicator."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw LED circle
        color = QColor(self.status.value)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(10, 15, 30, 30)

        # Add glow effect
        glow_color = QColor(self.status.value)
        glow_color.setAlpha(100)
        painter.setBrush(glow_color)
        painter.drawEllipse(5, 10, 40, 40)

        # Draw label
        painter.setPen(QColor("black"))
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(55, 30, self.label)

    def mousePressEvent(self, event):
        """Handle click events."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class CheckWorker(QThread):
    """Background worker for running system checks."""

    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)

    def __init__(self, check_type: str):
        super().__init__()
        self.check_type = check_type

    def run(self):
        """Run the checks in background."""
        results = {}

        if self.check_type == "environment":
            results = self.check_environment()
        elif self.check_type == "system_deps":
            results = self.check_system_dependencies()
        elif self.check_type == "server_deps":
            results = self.check_server_dependencies()
        elif self.check_type == "client_deps":
            results = self.check_client_dependencies()

        self.finished.emit(results)

    def check_environment(self) -> Dict[str, CheckResult]:
        """Check Python environment."""
        results = {}

        # Python version
        self.progress.emit("Checking Python version...")
        version = sys.version_info
        if version.major >= 3 and version.minor >= 8:
            if version.minor >= 10:
                results['python'] = CheckResult(
                    "Python Version",
                    StatusLevel.OK,
                    f"Python {version.major}.{version.minor}.{version.micro}",
                    [f"✓ Python {version.major}.{version.minor}.{version.micro} is excellent for LabLink"]
                )
            else:
                results['python'] = CheckResult(
                    "Python Version",
                    StatusLevel.WARNING,
                    f"Python {version.major}.{version.minor}.{version.micro}",
                    [
                        f"⚠ Python {version.major}.{version.minor}.{version.micro} works but 3.10+ is recommended",
                        "Consider upgrading to Python 3.10 or higher for best performance"
                    ]
                )
        else:
            results['python'] = CheckResult(
                "Python Version",
                StatusLevel.ERROR,
                f"Python {version.major}.{version.minor}.{version.micro} (too old)",
                [
                    f"✗ Python {version.major}.{version.minor}.{version.micro} is not supported",
                    "LabLink requires Python 3.8 or higher",
                    "Please upgrade Python to continue"
                ],
                fixable=False
            )

        # pip check
        self.progress.emit("Checking pip...")
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', '--version'],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                pip_version = result.stdout.split()[1]
                results['pip'] = CheckResult(
                    "pip",
                    StatusLevel.OK,
                    f"pip {pip_version}",
                    [f"✓ pip {pip_version} is installed"]
                )
            else:
                results['pip'] = CheckResult(
                    "pip",
                    StatusLevel.ERROR,
                    "Not installed",
                    [
                        "✗ pip is not installed",
                        "Install with: python3 -m ensurepip --upgrade"
                    ],
                    fixable=True,
                    fix_command="ensurepip"
                )
        except Exception as e:
            results['pip'] = CheckResult(
                "pip",
                StatusLevel.ERROR,
                "Error checking",
                [f"✗ Error: {str(e)}"],
                fixable=True,
                fix_command="ensurepip"
            )

        # Virtual environment check
        self.progress.emit("Checking virtual environment...")
        in_venv = sys.prefix != sys.base_prefix
        venv_path = Path("venv")

        if in_venv:
            results['venv'] = CheckResult(
                "Virtual Environment",
                StatusLevel.OK,
                "Active",
                [
                    "✓ Running in virtual environment",
                    f"  Path: {sys.prefix}"
                ]
            )
        elif venv_path.exists():
            results['venv'] = CheckResult(
                "Virtual Environment",
                StatusLevel.WARNING,
                "Exists but not active",
                [
                    "⚠ Virtual environment exists but is not activated",
                    f"  Path: {venv_path.absolute()}",
                    "  Activate with: source venv/bin/activate (Linux/macOS)",
                    "  or: venv\\Scripts\\activate (Windows)"
                ]
            )
        else:
            results['venv'] = CheckResult(
                "Virtual Environment",
                StatusLevel.WARNING,
                "Not created",
                [
                    "⚠ No virtual environment found",
                    "  Creating a venv is recommended for isolated dependencies",
                    "  This launcher can create one for you"
                ],
                fixable=True,
                fix_command="create_venv"
            )

        # PEP 668 check
        self.progress.emit("Checking for PEP 668...")
        is_externally_managed = self._check_externally_managed()

        if is_externally_managed and not in_venv:
            results['pep668'] = CheckResult(
                "Package Installation",
                StatusLevel.WARNING,
                "Externally managed",
                [
                    "⚠ This is an externally-managed Python environment (PEP 668)",
                    "  Ubuntu 24.04 and similar systems prevent system-wide pip installs",
                    "  A virtual environment is strongly recommended",
                    "  Or use: apt install python3-<package>"
                ]
            )
        else:
            results['pep668'] = CheckResult(
                "Package Installation",
                StatusLevel.OK,
                "Unrestricted",
                ["✓ Can install packages freely"]
            )

        return results

    def check_system_dependencies(self) -> Dict[str, CheckResult]:
        """Check system-level dependencies."""
        results = {}
        os_type = platform.system()

        self.progress.emit("Checking system dependencies...")

        # Only check apt packages on Linux
        if os_type == "Linux":
            # Check if apt is available
            if not self._check_command_exists('apt'):
                results['system_packages'] = CheckResult(
                    "System Packages",
                    StatusLevel.WARNING,
                    "apt not found",
                    [
                        "⚠ apt package manager not found",
                        "  System package checks are limited to Debian/Ubuntu-based systems"
                    ]
                )
                return results

            # Core system packages needed for LabLink
            core_packages = [
                "python3",
                "python3-pip",
                "python3-venv",
                "git"
            ]

            # Qt libraries for GUI
            qt_packages = [
                "libxcb-xinerama0",
                "libxcb-icccm4",
                "libxcb-keysyms1",
                "libgl1-mesa-glx"
            ]

            # USB libraries for equipment
            usb_packages = [
                "libusb-1.0-0"
            ]

            # Check all packages
            all_packages = core_packages + qt_packages + usb_packages
            missing_packages = []

            self.progress.emit("Checking system packages...")
            for pkg in all_packages:
                if not self._check_lib_installed(pkg):
                    missing_packages.append(pkg)

            if not missing_packages:
                results['system_packages'] = CheckResult(
                    "System Packages",
                    StatusLevel.OK,
                    "All installed",
                    [
                        "✓ All required system packages are installed",
                        f"  Core: {', '.join(core_packages)}",
                        f"  Qt: {', '.join(qt_packages)}",
                        f"  USB: {', '.join(usb_packages)}"
                    ]
                )
            else:
                # Categorize missing packages
                missing_core = [p for p in missing_packages if p in core_packages]
                missing_qt = [p for p in missing_packages if p in qt_packages]
                missing_usb = [p for p in missing_packages if p in usb_packages]

                status = StatusLevel.ERROR if missing_core else StatusLevel.WARNING

                details = [
                    f"✗ {len(missing_packages)} system packages missing",
                    ""
                ]

                if missing_core:
                    details.append(f"Critical: {', '.join(missing_core)}")
                if missing_qt:
                    details.append(f"Qt libraries: {', '.join(missing_qt)}")
                if missing_usb:
                    details.append(f"USB support: {', '.join(missing_usb)}")

                details.append("")
                details.append("These packages can be installed automatically.")

                results['system_packages'] = CheckResult(
                    "System Packages",
                    status,
                    f"{len(missing_packages)} missing",
                    details,
                    fixable=True,
                    fix_command=f"apt_install:{' '.join(missing_packages)}"
                )

        # VISA library check (optional)
        visa_paths = [
            '/usr/local/vxipnp/linux',
            '/usr/lib/libvisa.so',
            '/usr/local/lib/libvisa.so'
        ]
        visa_found = any(Path(p).exists() for p in visa_paths)

        if visa_found:
            results['visa'] = CheckResult(
                "NI-VISA",
                StatusLevel.OK,
                "Installed",
                ["✓ NI-VISA library found", "  Hardware control available"]
            )
        else:
            results['visa'] = CheckResult(
                "NI-VISA",
                StatusLevel.WARNING,
                "Not installed",
                [
                    "⚠ NI-VISA not detected (optional)",
                    "  PyVISA-py (pure Python) will be used as fallback",
                    "  For better performance, install from:",
                    "  https://www.ni.com/en-us/support/downloads/drivers/download.ni-visa.html"
                ]
            )

        return results

    def check_server_dependencies(self) -> Dict[str, CheckResult]:
        """Check server Python dependencies."""
        results = {}

        self.progress.emit("Checking server dependencies...")

        req_file = Path("server/requirements.txt")
        if not req_file.exists():
            results['server_deps'] = CheckResult(
                "Server Dependencies",
                StatusLevel.ERROR,
                "requirements.txt not found",
                [
                    "✗ server/requirements.txt not found",
                    "Are you in the LabLink root directory?"
                ]
            )
            return results

        packages = self._parse_requirements(req_file)
        installed, missing = self._check_packages(packages)

        if not missing:
            results['server_deps'] = CheckResult(
                "Server Dependencies",
                StatusLevel.OK,
                f"All installed ({len(installed)})",
                [f"✓ All {len(installed)} server packages are installed"]
            )
        else:
            results['server_deps'] = CheckResult(
                "Server Dependencies",
                StatusLevel.ERROR,
                f"{len(missing)} missing",
                [
                    f"✗ {len(missing)} packages missing: {', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}",
                    f"Installed: {len(installed)}/{len(packages)}"
                ],
                fixable=True,
                fix_command="pip_install:server"
            )

        return results

    def check_client_dependencies(self) -> Dict[str, CheckResult]:
        """Check client Python dependencies."""
        results = {}

        self.progress.emit("Checking client dependencies...")

        req_file = Path("client/requirements.txt")
        if not req_file.exists():
            results['client_deps'] = CheckResult(
                "Client Dependencies",
                StatusLevel.ERROR,
                "requirements.txt not found",
                [
                    "✗ client/requirements.txt not found",
                    "Are you in the LabLink root directory?"
                ]
            )
            return results

        packages = self._parse_requirements(req_file)
        installed, missing = self._check_packages(packages)

        if not missing:
            results['client_deps'] = CheckResult(
                "Client Dependencies",
                StatusLevel.OK,
                f"All installed ({len(installed)})",
                [f"✓ All {len(installed)} client packages are installed"]
            )
        else:
            results['client_deps'] = CheckResult(
                "Client Dependencies",
                StatusLevel.ERROR,
                f"{len(missing)} missing",
                [
                    f"✗ {len(missing)} packages missing: {', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}",
                    f"Installed: {len(installed)}/{len(packages)}"
                ],
                fixable=True,
                fix_command="pip_install:client"
            )

        return results

    def _check_externally_managed(self) -> bool:
        """Check if Python is externally managed (PEP 668)."""
        if sys.prefix != sys.base_prefix:
            return False

        import sysconfig
        stdlib = sysconfig.get_path('stdlib')
        if stdlib:
            marker = Path(stdlib) / 'EXTERNALLY-MANAGED'
            return marker.exists()
        return False

    def _check_command_exists(self, command: str) -> bool:
        """Check if a command exists in PATH."""
        try:
            result = subprocess.run(
                ['which', command],
                capture_output=True,
                text=True,
                check=False
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def _check_lib_installed(self, lib_name: str) -> bool:
        """Check if a system library/package is installed (dpkg)."""
        try:
            result = subprocess.run(
                ['dpkg', '-s', lib_name],
                capture_output=True,
                text=True,
                check=False
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def _parse_requirements(self, req_file: Path) -> List[str]:
        """Parse requirements.txt file."""
        packages = []
        for line in req_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                # Extract package name
                pkg = line.split('>=')[0].split('==')[0].split('[')[0]
                packages.append(pkg)
        return packages

    def _check_packages(self, packages: List[str]) -> Tuple[List[str], List[str]]:
        """Check which packages are installed."""
        installed = []
        missing = []

        for pkg in packages:
            try:
                __import__(pkg.replace('-', '_'))
                installed.append(pkg)
            except ImportError:
                missing.append(pkg)

        return installed, missing


class IssueDetailsDialog(QDialog):
    """Dialog to show detailed information about issues."""

    def __init__(self, title: str, results: Dict[str, CheckResult], parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(600, 400)
        self.results = results
        self.init_ui()

    def init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout()

        # Create text display
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setFont(QFont("Monospace", 10))

        # Build detailed text
        details_text = ""
        for name, result in self.results.items():
            details_text += f"{'='*60}\n"
            details_text += f"{result.name}\n"
            details_text += f"{'='*60}\n"
            details_text += f"Status: {result.status.name}\n"
            details_text += f"Summary: {result.message}\n\n"

            if result.details:
                details_text += "Details:\n"
                for detail in result.details:
                    details_text += f"  {detail}\n"

            if result.fixable:
                details_text += f"\n✓ This issue can be automatically fixed\n"

            details_text += "\n"

        text_edit.setPlainText(details_text)
        layout.addWidget(text_edit)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.setLayout(layout)


class LabLinkLauncher(QMainWindow):
    """Main LabLink launcher window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LabLink Launcher")
        self.setMinimumSize(800, 700)

        # Store check results
        self.env_results = {}
        self.sys_results = {}
        self.server_results = {}
        self.client_results = {}

        # Initialize UI
        self.init_ui()

        # Auto-check on startup
        QTimer.singleShot(500, self.check_all)

    def init_ui(self):
        """Initialize the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # Header
        header = QLabel("LabLink System Launcher")
        header.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("padding: 20px; background-color: #2c3e50; color: white; border-radius: 5px;")
        main_layout.addWidget(header)

        # Status indicators section
        status_group = QGroupBox("System Status")
        status_group.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        status_layout = QVBoxLayout()

        # Environment status
        self.env_led = LEDIndicator("Environment (Python, pip, venv)")
        self.env_led.clicked.connect(self.show_env_details)
        status_layout.addWidget(self.env_led)

        # System dependencies status
        self.sys_led = LEDIndicator("System Dependencies (Qt, USB)")
        self.sys_led.clicked.connect(self.show_sys_details)
        status_layout.addWidget(self.sys_led)

        # Server dependencies status
        self.server_led = LEDIndicator("Server Dependencies")
        self.server_led.clicked.connect(self.show_server_details)
        status_layout.addWidget(self.server_led)

        # Client dependencies status
        self.client_led = LEDIndicator("Client Dependencies")
        self.client_led.clicked.connect(self.show_client_details)
        status_layout.addWidget(self.client_led)

        status_group.setLayout(status_layout)
        main_layout.addWidget(status_group)

        # Progress bar
        self.progress_label = QLabel("Ready")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # Control buttons
        control_group = QGroupBox("Actions")
        control_group.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        control_layout = QVBoxLayout()

        # Check button
        check_btn = QPushButton("🔄 Refresh Status")
        check_btn.setFont(QFont("Arial", 11))
        check_btn.setMinimumHeight(40)
        check_btn.clicked.connect(self.check_all)
        control_layout.addWidget(check_btn)

        # Fix issues button
        self.fix_btn = QPushButton("🔧 Fix Issues Automatically")
        self.fix_btn.setFont(QFont("Arial", 11))
        self.fix_btn.setMinimumHeight(40)
        self.fix_btn.clicked.connect(self.fix_issues)
        control_layout.addWidget(self.fix_btn)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        control_layout.addWidget(line)

        # Launch buttons
        launch_layout = QHBoxLayout()

        self.server_btn = QPushButton("▶️  Start Server")
        self.server_btn.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.server_btn.setMinimumHeight(50)
        self.server_btn.setStyleSheet("background-color: #27ae60; color: white; border-radius: 5px;")
        self.server_btn.clicked.connect(self.launch_server)
        launch_layout.addWidget(self.server_btn)

        self.client_btn = QPushButton("▶️  Start Client")
        self.client_btn.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.client_btn.setMinimumHeight(50)
        self.client_btn.setStyleSheet("background-color: #3498db; color: white; border-radius: 5px;")
        self.client_btn.clicked.connect(self.launch_client)
        launch_layout.addWidget(self.client_btn)

        control_layout.addLayout(launch_layout)

        control_group.setLayout(control_layout)
        main_layout.addWidget(control_group)

        # Info section
        info_label = QLabel("💡 Click on any LED indicator to see detailed information")
        info_label.setFont(QFont("Arial", 9))
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet("color: #7f8c8d; padding: 10px;")
        main_layout.addWidget(info_label)

    def check_all(self):
        """Check all system components."""
        self.progress_label.setText("Checking system...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate

        # Disable buttons during check
        self.fix_btn.setEnabled(False)
        self.server_btn.setEnabled(False)
        self.client_btn.setEnabled(False)

        # Run checks
        self.check_environment()

    def check_environment(self):
        """Check environment in background."""
        worker = CheckWorker("environment")
        worker.progress.connect(self.update_progress)
        worker.finished.connect(self.on_env_checked)
        worker.start()
        self.env_worker = worker  # Keep reference

    def on_env_checked(self, results):
        """Handle environment check completion."""
        self.env_results = results
        self.update_led_status(self.env_led, results)

        # Start next check
        self.check_system_deps()

    def check_system_deps(self):
        """Check system dependencies."""
        worker = CheckWorker("system_deps")
        worker.progress.connect(self.update_progress)
        worker.finished.connect(self.on_sys_checked)
        worker.start()
        self.sys_worker = worker

    def on_sys_checked(self, results):
        """Handle system dependencies check completion."""
        self.sys_results = results
        self.update_led_status(self.sys_led, results)

        # Start next check
        self.check_server_deps()

    def check_server_deps(self):
        """Check server dependencies."""
        worker = CheckWorker("server_deps")
        worker.progress.connect(self.update_progress)
        worker.finished.connect(self.on_server_checked)
        worker.start()
        self.server_worker = worker

    def on_server_checked(self, results):
        """Handle server dependencies check completion."""
        self.server_results = results
        self.update_led_status(self.server_led, results)

        # Start next check
        self.check_client_deps()

    def check_client_deps(self):
        """Check client dependencies."""
        worker = CheckWorker("client_deps")
        worker.progress.connect(self.update_progress)
        worker.finished.connect(self.on_client_checked)
        worker.start()
        self.client_worker = worker

    def on_client_checked(self, results):
        """Handle client dependencies check completion."""
        self.client_results = results
        self.update_led_status(self.client_led, results)

        # All checks complete
        self.progress_bar.setVisible(False)
        self.progress_label.setText("✓ Status check complete")

        # Re-enable buttons
        self.fix_btn.setEnabled(True)
        self.update_launch_buttons()

    def update_progress(self, message):
        """Update progress label."""
        self.progress_label.setText(message)

    def update_led_status(self, led: LEDIndicator, results: Dict[str, CheckResult]):
        """Update LED based on check results."""
        if not results:
            led.set_status(StatusLevel.UNKNOWN)
            return

        # Determine overall status
        has_error = any(r.status == StatusLevel.ERROR for r in results.values())
        has_warning = any(r.status == StatusLevel.WARNING for r in results.values())

        if has_error:
            led.set_status(StatusLevel.ERROR)
        elif has_warning:
            led.set_status(StatusLevel.WARNING)
        else:
            led.set_status(StatusLevel.OK)

    def update_launch_buttons(self):
        """Update launch button states based on dependencies."""
        # Server can launch if server deps are OK or WARNING
        server_status = self.get_overall_status(self.server_results)
        self.server_btn.setEnabled(server_status != StatusLevel.ERROR)

        # Client can launch if client deps are OK or WARNING
        client_status = self.get_overall_status(self.client_results)
        self.client_btn.setEnabled(client_status != StatusLevel.ERROR)

    def get_overall_status(self, results: Dict[str, CheckResult]) -> StatusLevel:
        """Get overall status from results."""
        if not results:
            return StatusLevel.UNKNOWN

        has_error = any(r.status == StatusLevel.ERROR for r in results.values())
        has_warning = any(r.status == StatusLevel.WARNING for r in results.values())

        if has_error:
            return StatusLevel.ERROR
        elif has_warning:
            return StatusLevel.WARNING
        else:
            return StatusLevel.OK

    def show_env_details(self):
        """Show environment details."""
        if self.env_results:
            dialog = IssueDetailsDialog("Environment Details", self.env_results, self)
            dialog.exec()

    def show_sys_details(self):
        """Show system dependencies details."""
        if self.sys_results:
            dialog = IssueDetailsDialog("System Dependencies Details", self.sys_results, self)
            dialog.exec()

    def show_server_details(self):
        """Show server dependencies details."""
        if self.server_results:
            dialog = IssueDetailsDialog("Server Dependencies Details", self.server_results, self)
            dialog.exec()

    def show_client_details(self):
        """Show client dependencies details."""
        if self.client_results:
            dialog = IssueDetailsDialog("Client Dependencies Details", self.client_results, self)
            dialog.exec()

    def fix_issues(self):
        """Automatically fix detected issues."""
        fixable_issues = []

        # Collect all fixable issues
        for results in [self.env_results, self.sys_results, self.server_results, self.client_results]:
            for result in results.values():
                if result.fixable and result.fix_command:
                    fixable_issues.append(result)

        if not fixable_issues:
            QMessageBox.information(
                self,
                "No Fixable Issues",
                "There are no automatically fixable issues detected."
            )
            return

        # Show confirmation
        msg = f"Found {len(fixable_issues)} fixable issue(s):\n\n"
        for issue in fixable_issues:
            msg += f"• {issue.name}\n"
        msg += "\nDo you want to fix these automatically?"

        reply = QMessageBox.question(
            self,
            "Fix Issues",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.apply_fixes(fixable_issues)

    def apply_fixes(self, issues: List[CheckResult]):
        """Apply fixes for issues."""
        self.progress_label.setText("Fixing issues...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(issues))

        for i, issue in enumerate(issues):
            self.progress_label.setText(f"Fixing: {issue.name}")
            self.progress_bar.setValue(i)

            try:
                if issue.fix_command == "ensurepip":
                    subprocess.check_call([sys.executable, '-m', 'ensurepip', '--upgrade'])
                elif issue.fix_command == "create_venv":
                    subprocess.check_call([sys.executable, '-m', 'venv', 'venv'])
                elif issue.fix_command.startswith("pip_install:"):
                    target = issue.fix_command.split(':')[1]
                    req_file = f"{target}/requirements.txt"
                    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', req_file])
                elif issue.fix_command.startswith("apt_install:"):
                    packages = issue.fix_command.split(':')[1]
                    success = self._install_apt_packages(packages)
                    if not success:
                        raise Exception("Failed to install system packages")
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Fix Failed",
                    f"Failed to fix {issue.name}:\n{str(e)}"
                )

        self.progress_bar.setValue(len(issues))
        self.progress_label.setText("✓ Fixes applied")

        # Re-check after fixes
        QTimer.singleShot(1000, self.check_all)

    def _install_apt_packages(self, packages: str) -> bool:
        """Install system packages using apt with sudo."""
        # First, inform the user
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle("System Package Installation")
        msg.setText("LabLink needs to install system packages with administrator privileges.")
        msg.setInformativeText(f"Packages to install:\n{packages}\n\n"
                              "You will be prompted for your password.")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)

        if msg.exec() != QMessageBox.StandardButton.Ok:
            return False

        try:
            # Try pkexec first (graphical password prompt)
            if self._check_command_exists('pkexec'):
                self.progress_label.setText("Waiting for password (pkexec)...")
                result = subprocess.run(
                    ['pkexec', 'apt', 'update'],
                    check=False,
                    capture_output=True,
                    text=True
                )

                if result.returncode == 0:
                    self.progress_label.setText("Installing packages...")
                    result = subprocess.run(
                        ['pkexec', 'apt', 'install', '-y'] + packages.split(),
                        check=False,
                        capture_output=True,
                        text=True
                    )

                    if result.returncode == 0:
                        QMessageBox.information(
                            self,
                            "Success",
                            f"System packages installed successfully:\n{packages}"
                        )
                        return True
                    else:
                        raise Exception(f"apt install failed: {result.stderr}")
                else:
                    # User cancelled or authentication failed
                    if "dismissed" in result.stderr.lower() or "cancelled" in result.stderr.lower():
                        QMessageBox.information(
                            self,
                            "Cancelled",
                            "Package installation was cancelled."
                        )
                        return False
                    raise Exception(f"apt update failed: {result.stderr}")

            # Fall back to terminal-based sudo
            else:
                QMessageBox.information(
                    self,
                    "Terminal Required",
                    "Please run the following commands in a terminal:\n\n"
                    f"sudo apt update\n"
                    f"sudo apt install -y {packages}\n\n"
                    "Then click 'Refresh Status' to continue."
                )
                return False

        except Exception as e:
            QMessageBox.critical(
                self,
                "Installation Failed",
                f"Failed to install system packages:\n{str(e)}\n\n"
                f"Please install manually:\n"
                f"sudo apt update && sudo apt install -y {packages}"
            )
            return False

    def launch_server(self):
        """Launch the LabLink server."""
        server_path = Path("server/main.py")

        if not server_path.exists():
            QMessageBox.warning(
                self,
                "Server Not Found",
                "server/main.py not found.\nAre you in the LabLink root directory?"
            )
            return

        try:
            # Launch in new terminal
            if platform.system() == "Linux":
                subprocess.Popen(['x-terminal-emulator', '-e', f'cd server && {sys.executable} main.py'])
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(['open', '-a', 'Terminal', 'server/main.py'])
            elif platform.system() == "Windows":
                subprocess.Popen(['start', 'cmd', '/k', f'cd server && {sys.executable} main.py'], shell=True)

            QMessageBox.information(
                self,
                "Server Starting",
                "LabLink server is starting in a new terminal window."
            )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Launch Failed",
                f"Failed to launch server:\n{str(e)}"
            )

    def launch_client(self):
        """Launch the LabLink client."""
        client_path = Path("client/main.py")

        if not client_path.exists():
            QMessageBox.warning(
                self,
                "Client Not Found",
                "client/main.py not found.\nAre you in the LabLink root directory?"
            )
            return

        try:
            # Launch client directly (GUI application)
            subprocess.Popen([sys.executable, str(client_path)])

            QMessageBox.information(
                self,
                "Client Starting",
                "LabLink client is starting..."
            )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Launch Failed",
                f"Failed to launch client:\n{str(e)}"
            )


def main():
    """Main entry point."""
    app = QApplication(sys.argv)

    # Set application style
    app.setStyle("Fusion")

    # Create and show launcher
    launcher = LabLinkLauncher()
    launcher.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
