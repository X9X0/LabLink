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
import shutil
import logging
import time
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
    handlers=[
        logging.FileHandler('lablink_debug.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Log startup
logger.info("=" * 70)
logger.info("LabLink Launcher Debug Log Started")
logger.info("=" * 70)

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
    print("PyQt6 is not installed - Setting up environment...")
    print("="*70)

    # Make sure pip is available first
    check_and_install_pip()

    # Check if Python is externally managed (PEP 668)
    venv_path = Path("venv")
    needs_venv = False

    # Check for EXTERNALLY-MANAGED marker
    import sysconfig
    stdlib = sysconfig.get_path('stdlib')
    if stdlib:
        marker = Path(stdlib) / 'EXTERNALLY-MANAGED'
        if marker.exists():
            needs_venv = True
            print("\n⚠️  Detected externally-managed Python (Ubuntu 24.04/PEP 668)")
            print("Creating virtual environment for LabLink...")

    if needs_venv:
        # Create venv if it doesn't exist
        if not venv_path.exists():
            try:
                print(f"\nCreating virtual environment at {venv_path}...")
                subprocess.check_call([sys.executable, "-m", "venv", "venv"])
                print("✓ Virtual environment created")
            except subprocess.CalledProcessError as e:
                print("\n" + "="*70)
                print("ERROR: Failed to create virtual environment")
                print("="*70)
                print(f"\nError: {e}")
                print("\nPlease install python3-venv:")
                print("  sudo apt update")
                print("  sudo apt install -y python3-venv")
                print("="*70 + "\n")
                sys.exit(1)

        # Install PyQt6 in venv
        venv_python = venv_path / "bin" / "python"
        venv_pip = venv_path / "bin" / "pip"

        try:
            print("\nInstalling PyQt6 in virtual environment...")
            subprocess.check_call([str(venv_pip), "install", "PyQt6"])
            print("\n" + "="*70)
            print("✓ SUCCESS: Environment setup complete!")
            print("="*70)
            print("\nRestarting launcher with virtual environment...")
            print("="*70 + "\n")

            # Re-run this script with venv python
            import os
            os.execv(str(venv_python), [str(venv_python)] + sys.argv)

        except subprocess.CalledProcessError as e:
            print("\n" + "="*70)
            print("ERROR: Failed to install PyQt6")
            print("="*70)
            print(f"\nError: {e}")
            print("\nPlease try manually:")
            print("  python3 -m venv venv")
            print("  source venv/bin/activate")
            print("  pip install PyQt6")
            print(f"  python3 {sys.argv[0]}")
            print("="*70 + "\n")
            sys.exit(1)
    else:
        # Try direct install (non-externally-managed system)
        try:
            print("\nInstalling PyQt6...")
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
        self.setStyleSheet("""
            LEDIndicator {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                margin: 2px;
            }
        """)

    def set_status(self, status: StatusLevel):
        """Update the LED status and repaint."""
        self.status = status
        self.update()

    def paintEvent(self, event):
        """Draw the LED indicator."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw widget background with border
        painter.setPen(QColor("#dee2e6"))
        painter.setBrush(QColor("#f8f9fa"))
        painter.drawRoundedRect(0, 0, self.width()-1, self.height()-1, 6, 6)

        # Draw LED circle
        color = QColor(self.status.value)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(15, 18, 24, 24)

        # Add glow effect
        glow_color = QColor(self.status.value)
        glow_color.setAlpha(80)
        painter.setBrush(glow_color)
        painter.drawEllipse(12, 15, 30, 30)

        # Draw LED border for definition
        painter.setPen(QColor("#2c3e50"))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(15, 18, 24, 24)

        # Draw label
        painter.setPen(QColor("#2c3e50"))
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(55, 33, self.label)

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
        elif self.check_type == "utils_deps":
            results = self.check_utils_dependencies()

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
            # Venv exists - this is good! The launcher uses it automatically
            results['venv'] = CheckResult(
                "Virtual Environment",
                StatusLevel.OK,
                "Available",
                [
                    "✓ Virtual environment found",
                    f"  Path: {venv_path.absolute()}",
                    "  Note: The launcher automatically uses this venv",
                    "  Manual activation not required for the launcher"
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

        if is_externally_managed and not in_venv and not venv_path.exists():
            # Externally managed with no venv - this is a problem
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
        elif is_externally_managed and (in_venv or venv_path.exists()):
            # Externally managed but venv exists - this is OK, we handle it
            results['pep668'] = CheckResult(
                "Package Installation",
                StatusLevel.OK,
                "Handled via venv",
                [
                    "✓ System is externally-managed (PEP 668)",
                    "  This is normal for Ubuntu 24.04",
                    "  The launcher uses the virtual environment to handle this",
                    "  All package installations go to the venv"
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
                "libgl1"  # Ubuntu 24.04: libgl1-mesa-glx replaced by libgl1
            ]

            # USB libraries for equipment
            usb_packages = [
                "libusb-1.0-0"
            ]

            # Build tools for Raspberry Pi image builder
            build_packages = [
                "kpartx",        # Partition mapping for disk images
                "qemu-user-static",  # ARM emulation for chroot
                "parted",        # Partition manipulation
                "wget",          # Download utilities
                "xz-utils"       # Compression utilities
            ]

            # Check all packages
            all_packages = core_packages + qt_packages + usb_packages + build_packages
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
                        f"  USB: {', '.join(usb_packages)}",
                        f"  Build tools: {', '.join(build_packages)}"
                    ]
                )
            else:
                # Categorize missing packages
                missing_core = [p for p in missing_packages if p in core_packages]
                missing_qt = [p for p in missing_packages if p in qt_packages]
                missing_usb = [p for p in missing_packages if p in usb_packages]
                missing_build = [p for p in missing_packages if p in build_packages]

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
                if missing_build:
                    details.append(f"Build tools (for Pi image builder): {', '.join(missing_build)}")

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

    def check_utils_dependencies(self) -> Dict[str, CheckResult]:
        """Check client utilities (deployment and discovery tools)."""
        results = {}

        self.progress.emit("Checking client utilities...")

        # Utilities for deployment
        deployment_utils = {
            'paramiko': 'SSH client library for deployment',
            'scp': 'SCP (secure copy) support',
        }

        # Utilities for network discovery
        discovery_utils = {
            'scapy': 'Network packet manipulation and discovery',
            'zeroconf': 'mDNS/Bonjour service discovery',
        }

        all_utils = {**deployment_utils, **discovery_utils}

        # Check which utilities are installed
        installed = []
        missing = []

        # Map package names to import names for special cases
        package_to_import = {
            'python-dotenv': 'dotenv',
            'python-dateutil': 'dateutil',
            'pydantic-settings': 'pydantic_settings',
            'pyserial': 'serial',
            'pyusb': 'usb',
            'PyJWT': 'jwt',
        }

        # Determine which Python to use for checking
        venv_python = Path("venv/bin/python")
        use_venv = venv_python.exists()

        for pkg, description in all_utils.items():
            # Get the correct import name
            import_name = package_to_import.get(pkg, pkg.replace("-", "_"))

            if use_venv:
                # Check if package is installed in venv using subprocess
                result = subprocess.run(
                    [str(venv_python), '-c', f'import {import_name}'],
                    capture_output=True,
                    check=False
                )
                if result.returncode == 0:
                    installed.append(pkg)
                else:
                    missing.append(pkg)
            else:
                # Check if package is installed in current environment
                try:
                    __import__(import_name)
                    installed.append(pkg)
                except ImportError:
                    missing.append(pkg)

        # Determine status
        if not missing:
            results['utils_deps'] = CheckResult(
                "Client Utilities",
                StatusLevel.OK,
                f"All installed ({len(installed)})",
                [
                    f"✓ All {len(installed)} utilities are installed",
                    "",
                    "Deployment utilities:",
                    *[f"  ✓ {pkg}: {deployment_utils[pkg]}" for pkg in deployment_utils if pkg in installed],
                    "",
                    "Discovery utilities:",
                    *[f"  ✓ {pkg}: {discovery_utils[pkg]}" for pkg in discovery_utils if pkg in installed],
                ]
            )
        else:
            # Categorize missing utilities
            missing_deployment = [p for p in missing if p in deployment_utils]
            missing_discovery = [p for p in missing if p in discovery_utils]

            details = [
                f"✗ {len(missing)} utilities missing",
                "",
            ]

            if missing_deployment:
                details.append("Missing deployment utilities:")
                for pkg in missing_deployment:
                    details.append(f"  ✗ {pkg}: {deployment_utils[pkg]}")
                details.append("")

            if missing_discovery:
                details.append("Missing discovery utilities:")
                for pkg in missing_discovery:
                    details.append(f"  ✗ {pkg}: {discovery_utils[pkg]}")
                details.append("")

            if installed:
                details.append(f"Installed: {len(installed)}/{len(all_utils)}")

            details.append("")
            details.append("These utilities can be installed automatically.")

            results['utils_deps'] = CheckResult(
                "Client Utilities",
                StatusLevel.ERROR,
                f"{len(missing)} missing",
                details,
                fixable=True,
                fix_command="pip_install:client_utils"
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
        """Check which packages are installed (optimized batch check).

        If a venv exists, checks packages in the venv.
        Otherwise, checks packages in the current environment.
        """
        installed = []
        missing = []

        # Map package names to import names for special cases
        package_to_import = {
            'python-dotenv': 'dotenv',
            'python-dateutil': 'dateutil',
            'pydantic-settings': 'pydantic_settings',
            'uvicorn': 'uvicorn',
            'pyvisa-py': 'pyvisa_py',
            'PyQt6-Qt6': 'PyQt6',  # PyQt6-Qt6 is just Qt binaries, check PyQt6 instead
            'pyserial': 'serial',  # pyserial package imports as 'serial'
            'pyusb': 'usb',  # pyusb package imports as 'usb'
            'PyJWT': 'jwt',  # PyJWT package imports as 'jwt'
            'email-validator': 'email_validator',  # email-validator imports as 'email_validator'
        }

        # Determine which Python to use for checking
        venv_python = Path("venv/bin/python")
        use_venv = venv_python.exists()

        logger.debug(f"Checking {len(packages)} packages, use_venv={use_venv}, venv_python={venv_python}")

        if use_venv:
            # OPTIMIZED: Check all packages in a single subprocess call
            # Build a proper multiline Python script
            import_checks = []
            for pkg in packages:
                import_name = package_to_import.get(pkg, pkg.replace("-", "_"))
                import_checks.append((pkg, import_name))

            # Create a properly formatted multiline script
            batch_check = "import sys\nresults = {}\n"
            for pkg, import_name in import_checks:
                # Use proper multiline try/except blocks
                batch_check += f"try:\n"
                batch_check += f"    __import__('{import_name}')\n"
                batch_check += f"    results['{pkg}'] = 'OK'\n"
                batch_check += f"except Exception:\n"
                batch_check += f"    results['{pkg}'] = 'MISS'\n"
            batch_check += "print('|'.join(f'{k}={v}' for k, v in results.items()))\n"

            result = subprocess.run(
                [str(venv_python), '-c', batch_check],
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode == 0 and result.stdout.strip():
                # Parse batch results
                for item in result.stdout.strip().split('|'):
                    if '=' in item:
                        pkg, status = item.split('=', 1)
                        if status == 'OK':
                            installed.append(pkg)
                            logger.debug(f"  {pkg}: INSTALLED")
                        else:
                            missing.append(pkg)
                            logger.debug(f"  {pkg}: MISSING")
            else:
                # Fallback: if batch check fails, assume all missing
                logger.warning("Batch package check failed, marking all as missing")
                missing.extend(packages)
        else:
            # Check in current environment (also batched)
            for pkg in packages:
                import_name = package_to_import.get(pkg, pkg.replace("-", "_"))
                try:
                    __import__(import_name)
                    logger.debug(f"  {pkg}: INSTALLED (system environment)")
                    installed.append(pkg)
                except ImportError:
                    logger.debug(f"  {pkg}: MISSING (system environment)")
                    missing.append(pkg)

        logger.debug(f"Package check complete: {len(installed)} installed, {len(missing)} missing")
        return installed, missing


class FixWorker(QThread):
    """Background worker for applying fixes."""

    progress_update = pyqtSignal(str, int)  # message, progress value
    fix_error = pyqtSignal(str, str)  # issue name, error message
    finished = pyqtSignal()

    def __init__(self, issues: List[CheckResult], parent_launcher):
        super().__init__()
        self.issues = issues
        self.launcher = parent_launcher

    def run(self):
        """Apply fixes in background."""
        logger.info(f"FixWorker: Starting to apply {len(self.issues)} fixes")

        # Sort fixes by priority
        def fix_priority(issue):
            if issue.fix_command.startswith("apt_install:"):
                return 0
            elif issue.fix_command == "ensurepip":
                return 1
            elif issue.fix_command == "create_venv":
                return 2
            elif issue.fix_command.startswith("pip_install:"):
                return 3
            return 4

        sorted_issues = sorted(self.issues, key=fix_priority)

        # Check environment status
        venv_exists = Path("venv/bin/pip").exists()
        externally_managed = self.launcher._check_externally_managed()
        logger.info(f"Externally managed: {externally_managed}, venv exists: {venv_exists}")

        for i, issue in enumerate(sorted_issues):
            logger.info(f"Fixing issue {i+1}/{len(sorted_issues)}: {issue.name}")
            self.progress_update.emit(f"Fixing: {issue.name}", i)

            try:
                if issue.fix_command == "ensurepip":
                    logger.info("Running ensurepip")
                    subprocess.check_call([sys.executable, '-m', 'ensurepip', '--upgrade'])

                elif issue.fix_command == "create_venv":
                    venv_path = Path("venv")
                    venv_pip = venv_path / "bin" / "pip"

                    if venv_path.exists() and not venv_pip.exists():
                        logger.warning(f"Venv exists but is broken, recreating...")
                        self.progress_update.emit("Removing broken venv...", i)
                        shutil.rmtree(venv_path)
                        logger.info("Removed broken venv")

                    if not venv_path.exists():
                        logger.info("Creating virtual environment...")
                        subprocess.check_call([sys.executable, '-m', 'venv', 'venv'])
                        logger.info("Virtual environment created successfully")

                        if not venv_pip.exists():
                            raise Exception(f"venv created but {venv_pip} not found. Ensure python3-venv is installed.")

                elif issue.fix_command.startswith("pip_install:"):
                    target = issue.fix_command.split(':')[1]

                    # Special handling for client utilities
                    if target == "client_utils":
                        logger.info("Installing client utilities packages")
                        packages = ['paramiko', 'scp', 'scapy', 'zeroconf']

                        venv_pip = Path("venv/bin/pip")
                        if venv_pip.exists():
                            logger.info(f"Using venv pip: {venv_pip}")
                            subprocess.check_call([str(venv_pip), 'install'] + packages)
                            logger.info("Client utilities install completed successfully")
                        else:
                            logger.info("Using system pip")
                            subprocess.check_call([sys.executable, '-m', 'pip', 'install'] + packages)
                            logger.info("Client utilities install completed successfully")
                    else:
                        # Standard requirements.txt installation
                        req_file = f"{target}/requirements.txt"
                        logger.info(f"Installing pip packages from {req_file}")

                        venv_pip = Path("venv/bin/pip")
                        if venv_pip.exists():
                            logger.info(f"Using venv pip: {venv_pip}")
                            subprocess.check_call([str(venv_pip), 'install', '-r', req_file])
                            logger.info("Pip install completed successfully")
                        else:
                            logger.info("Using system pip")
                            subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', req_file])
                            logger.info("Pip install completed successfully")

                elif issue.fix_command.startswith("apt_install:"):
                    packages = issue.fix_command.split(':')[1]
                    logger.info(f"Installing apt packages: {packages}")

                    # Run apt install directly with pkexec (no GUI dialogs from worker thread)
                    # pkexec will handle the password GUI prompt itself
                    package_list = packages.split()

                    # Check if pkexec is available
                    pkexec_check = subprocess.run(
                        ['which', 'pkexec'],
                        capture_output=True,
                        check=False
                    )

                    if pkexec_check.returncode == 0:
                        # Use pkexec for GUI password prompt
                        logger.info("Running apt update with pkexec...")
                        result = subprocess.run(
                            ['pkexec', 'apt', 'update'],
                            capture_output=True,
                            text=True,
                            check=False
                        )

                        if result.returncode != 0:
                            if "dismissed" in result.stderr.lower() or "cancelled" in result.stderr.lower():
                                logger.info("User cancelled apt update")
                                raise Exception("User cancelled package installation")
                            else:
                                logger.error(f"apt update failed: {result.stderr}")
                                raise Exception(f"apt update failed: {result.stderr}")

                        logger.info("Running apt install with pkexec...")
                        result = subprocess.run(
                            ['pkexec', 'apt', 'install', '-y'] + package_list,
                            capture_output=True,
                            text=True,
                            check=False
                        )

                        if result.returncode != 0:
                            logger.error(f"apt install failed: {result.stderr}")
                            raise Exception(f"apt install failed: {result.stderr}")

                        logger.info(f"Successfully installed system packages: {packages}")
                    else:
                        # pkexec not available, fail with error
                        logger.error("pkexec not available for system package installation")
                        raise Exception("pkexec not available. Please install: sudo apt install policykit-1")

                    logger.info("apt install completed successfully")

            except Exception as e:
                logger.error(f"Failed to fix {issue.name}: {str(e)}", exc_info=True)
                self.fix_error.emit(issue.name, str(e))

        logger.info(f"All fixes applied")
        self.progress_update.emit("✓ Fixes applied", len(sorted_issues))
        self.finished.emit()


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

        # Add defined border to main window
        self.setStyleSheet("""
            QMainWindow {
                border: 6px solid #0d1419;
                background-color: #ecf0f1;
            }
        """)

        # Store check results
        self.env_results = {}
        self.sys_results = {}
        self.server_results = {}
        self.client_results = {}
        self.utils_results = {}

        # Cache for check results (prevents redundant checks)
        self._check_cache = {}
        self._cache_timeout = 30  # seconds

        # Easter egg: Debug mode
        self._click_count = 0
        self._last_click_time = 0
        self.debug_mode = False

        # Initialize UI
        self.init_ui()

        # Auto-check on startup
        QTimer.singleShot(500, self.check_all)

    def init_ui(self):
        """Initialize the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Set main window background
        central_widget.setStyleSheet("QWidget { background-color: #ecf0f1; }")

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        central_widget.setLayout(main_layout)

        # Header (with Easter egg - click 7 times for debug mode!)
        self.header = QLabel("LabLink System Launcher")
        self.header.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header.setStyleSheet("""
            padding: 20px;
            background-color: #1a252f;
            color: white;
            border-radius: 8px;
            border: 2px solid #0d1419;
        """)
        self.header.mousePressEvent = self._header_clicked
        main_layout.addWidget(self.header)

        # Status indicators section
        status_group = QGroupBox("System Status")
        status_group.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        status_group.setStyleSheet("""
            QGroupBox {
                border: 2px solid #bdc3c7;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 15px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 5px 10px;
                background-color: white;
            }
        """)
        status_layout = QVBoxLayout()
        status_layout.setSpacing(8)

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

        # Client utilities status
        self.utils_led = LEDIndicator("Client Utilities (Deployment, Discovery)")
        self.utils_led.clicked.connect(self.show_utils_details)
        status_layout.addWidget(self.utils_led)

        status_group.setLayout(status_layout)
        main_layout.addWidget(status_group)

        # Progress bar
        self.progress_label = QLabel("Ready")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_label.setFont(QFont("Arial", 10))
        self.progress_label.setStyleSheet("""
            QLabel {
                padding: 8px;
                background-color: white;
                border: 1px solid #bdc3c7;
                border-radius: 4px;
                color: #2c3e50;
            }
        """)
        main_layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #bdc3c7;
                border-radius: 6px;
                background-color: white;
                text-align: center;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #3498db;
                border-radius: 4px;
            }
        """)
        main_layout.addWidget(self.progress_bar)

        # Control buttons
        control_group = QGroupBox("Actions")
        control_group.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        control_group.setStyleSheet("""
            QGroupBox {
                border: 2px solid #bdc3c7;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 15px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 5px 10px;
                background-color: white;
            }
        """)
        control_layout = QVBoxLayout()
        control_layout.setSpacing(10)

        # Check button
        check_btn = QPushButton("🔄 Refresh Status")
        check_btn.setFont(QFont("Arial", 11))
        check_btn.setMinimumHeight(40)
        check_btn.setStyleSheet("""
            QPushButton {
                background-color: #ecf0f1;
                border: 2px solid #bdc3c7;
                border-radius: 6px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #d5dbdb;
                border: 2px solid #95a5a6;
            }
            QPushButton:pressed {
                background-color: #bdc3c7;
            }
        """)
        check_btn.clicked.connect(self.check_all)
        control_layout.addWidget(check_btn)

        # Fix issues button
        self.fix_btn = QPushButton("🔧 Fix Issues Automatically")
        self.fix_btn.setFont(QFont("Arial", 11))
        self.fix_btn.setMinimumHeight(40)
        self.fix_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                border: 2px solid #d68910;
                border-radius: 6px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #e67e22;
                border: 2px solid #ca6f1e;
            }
            QPushButton:pressed {
                background-color: #d68910;
            }
        """)
        self.fix_btn.clicked.connect(self.fix_issues)
        control_layout.addWidget(self.fix_btn)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #bdc3c7; margin: 10px 0px;")
        control_layout.addWidget(line)

        # Launch buttons
        launch_layout = QHBoxLayout()
        launch_layout.setSpacing(10)

        self.server_btn = QPushButton("▶️  Start Server")
        self.server_btn.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.server_btn.setMinimumHeight(50)
        self.server_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: 2px solid #1e8449;
                border-radius: 6px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #229954;
                border: 2px solid #186a3b;
            }
            QPushButton:pressed {
                background-color: #1e8449;
            }
            QPushButton:disabled {
                background-color: #95a5a6;
                border: 2px solid #7f8c8d;
            }
        """)
        self.server_btn.clicked.connect(self.launch_server)
        launch_layout.addWidget(self.server_btn)

        self.client_btn = QPushButton("▶️  Start Client")
        self.client_btn.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.client_btn.setMinimumHeight(50)
        self.client_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: 2px solid #2471a3;
                border-radius: 6px;
                padding: 5px;
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
            }
        """)
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

    def _header_clicked(self, event):
        """Easter egg: Enable debug mode by clicking header 7 times."""
        current_time = time.time()

        # Reset click count if more than 2 seconds since last click
        if current_time - self._last_click_time > 2.0:
            self._click_count = 0

        self._click_count += 1
        self._last_click_time = current_time

        # Activate debug mode after 7 clicks
        if self._click_count == 7:
            if not self.debug_mode:
                self.debug_mode = True
                self._click_count = 0  # Reset

                # Change header to indicate debug mode
                self.header.setStyleSheet("""
                    padding: 20px;
                    background-color: #c0392b;
                    color: white;
                    border-radius: 8px;
                    border: 2px solid #e74c3c;
                """)
                self.header.setText("LabLink System Launcher [DEBUG MODE]")

                # Show funny Easter egg message
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Icon.Information)
                msg.setWindowTitle("🐛 Debug Mode Unlocked!")
                msg.setText("Well well well... looks like someone found the secret button! 🕵️")
                msg.setInformativeText(
                    "Debug mode is now ENABLED! 🎉\n\n"
                    "The server and client will now launch with verbose logging.\n"
                    "Prepare for an avalanche of debug messages! 🌊\n\n"
                    "Click the header 7 more times to disable debug mode."
                )
                msg.setStandardButtons(QMessageBox.StandardButton.Ok)
                msg.setStyleSheet("""
                    QMessageBox {
                        background-color: #2c3e50;
                    }
                    QLabel {
                        color: #ecf0f1;
                        font-size: 11pt;
                    }
                    QPushButton {
                        background-color: #27ae60;
                        color: white;
                        border: none;
                        padding: 8px 16px;
                        border-radius: 4px;
                        font-weight: bold;
                        min-width: 80px;
                    }
                    QPushButton:hover {
                        background-color: #2ecc71;
                    }
                """)
                msg.exec()
                logger.info("🐛 DEBUG MODE ENABLED via Easter egg!")
            else:
                # Disable debug mode
                self.debug_mode = False
                self._click_count = 0

                # Restore normal header
                self.header.setStyleSheet("""
                    padding: 20px;
                    background-color: #1a252f;
                    color: white;
                    border-radius: 8px;
                    border: 2px solid #0d1419;
                """)
                self.header.setText("LabLink System Launcher")

                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Icon.Information)
                msg.setWindowTitle("Debug Mode Disabled")
                msg.setText("Debug mode has been disabled.")
                msg.setInformativeText("Server and client will now launch normally.")
                msg.exec()
                logger.info("Debug mode disabled")

    def check_all(self):
        """Check all system components."""
        logger.info("Starting comprehensive system check")
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
        logger.info(f"Environment check completed with {len(results)} results")
        for key, result in results.items():
            logger.debug(f"  {key}: {result.status.name} - {result.message}")

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

        # Start next check
        self.check_utils_deps()

    def check_utils_deps(self):
        """Check client utilities dependencies."""
        worker = CheckWorker("utils_deps")
        worker.progress.connect(self.update_progress)
        worker.finished.connect(self.on_utils_checked)
        worker.start()
        self.utils_worker = worker

    def on_utils_checked(self, results):
        """Handle utilities dependencies check completion."""
        self.utils_results = results
        self.update_led_status(self.utils_led, results)

        # All checks complete
        self.progress_bar.setVisible(False)
        self.progress_label.setText("✓ Status check complete")

        # Re-enable buttons
        self.fix_btn.setEnabled(True)
        self.update_launch_buttons()

        # Auto-trigger fix dialog if there are fixable errors
        self.auto_fix_if_needed()

    def update_progress(self, message):
        """Update progress label."""
        self.progress_label.setText(message)

    def update_led_status(self, led: LEDIndicator, results: Dict[str, CheckResult]):
        """Update LED based on check results."""
        logger.debug(f"Updating LED '{led.label}' with {len(results)} results")

        if not results:
            led.set_status(StatusLevel.UNKNOWN)
            return

        # Determine overall status
        has_error = any(r.status == StatusLevel.ERROR for r in results.values())
        has_warning = any(r.status == StatusLevel.WARNING for r in results.values())

        if has_error:
            logger.info(f"  Setting {led.label} LED to RED (has errors)")
            led.set_status(StatusLevel.ERROR)
        elif has_warning:
            logger.info(f"  Setting {led.label} LED to YELLOW (has warnings)")
            led.set_status(StatusLevel.WARNING)
        else:
            logger.info(f"  Setting {led.label} LED to GREEN (all OK)")
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

    def show_utils_details(self):
        """Show utilities dependencies details."""
        if self.utils_results:
            dialog = IssueDetailsDialog("Client Utilities Details", self.utils_results, self)
            dialog.exec()

    def auto_fix_if_needed(self):
        """Automatically prompt to fix issues if errors are detected."""
        fixable_errors = []

        # Collect fixable issues that are errors (not just warnings)
        for results in [self.env_results, self.sys_results, self.server_results, self.client_results, self.utils_results]:
            for result in results.values():
                if result.fixable and result.fix_command and result.status == StatusLevel.ERROR:
                    fixable_errors.append(result)

        # If we have fixable errors, automatically show the fix dialog
        if fixable_errors:
            logger.info(f"Auto-fix: Found {len(fixable_errors)} fixable errors, showing fix dialog")
            QTimer.singleShot(500, self.fix_issues)

    def fix_issues(self):
        """Automatically fix detected issues."""
        fixable_issues = []

        # Collect all fixable issues
        for results in [self.env_results, self.sys_results, self.server_results, self.client_results, self.utils_results]:
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
        """Apply fixes for issues in background."""
        logger.info(f"Starting to apply {len(issues)} fixes")
        for issue in issues:
            logger.debug(f"  Will fix: {issue.name} - {issue.fix_command}")

        self.progress_label.setText("Fixing issues...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(issues))

        # Disable buttons during fix
        self.fix_btn.setEnabled(False)
        self.server_btn.setEnabled(False)
        self.client_btn.setEnabled(False)

        # Create and start fix worker
        self.fix_worker = FixWorker(issues, self)
        self.fix_worker.progress_update.connect(self.on_fix_progress)
        self.fix_worker.fix_error.connect(self.on_fix_error)
        self.fix_worker.finished.connect(self.on_fixes_complete)
        self.fix_worker.start()

    def on_fix_progress(self, message: str, value: int):
        """Update progress during fixes."""
        self.progress_label.setText(message)
        self.progress_bar.setValue(value)

    def on_fix_error(self, issue_name: str, error_message: str):
        """Handle fix error."""
        QMessageBox.warning(
            self,
            "Fix Failed",
            f"Failed to fix {issue_name}:\n{error_message}"
        )

    def on_fixes_complete(self):
        """Handle fixes completion."""
        logger.info("All fixes applied, re-checking system in 1 second...")
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
                        logger.info(f"apt install succeeded for packages: {packages}")
                        QMessageBox.information(
                            self,
                            "Success",
                            f"System packages installed successfully:\n{packages}"
                        )
                        return True
                    else:
                        logger.error(f"apt install failed with return code {result.returncode}")
                        logger.error(f"apt install stderr: {result.stderr}")
                        logger.error(f"apt install stdout: {result.stdout}")
                        raise Exception(f"apt install failed: {result.stderr}")
                else:
                    # User cancelled or authentication failed
                    if "dismissed" in result.stderr.lower() or "cancelled" in result.stderr.lower():
                        logger.info("User cancelled package installation")
                        QMessageBox.information(
                            self,
                            "Cancelled",
                            "Package installation was cancelled."
                        )
                        return False
                    logger.error(f"apt update failed with return code {result.returncode}")
                    logger.error(f"apt update stderr: {result.stderr}")
                    logger.error(f"apt update stdout: {result.stdout}")
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
            logger.error(f"System package installation failed: {str(e)}", exc_info=True)
            QMessageBox.critical(
                self,
                "Installation Failed",
                f"Failed to install system packages:\n{str(e)}\n\n"
                f"Please install manually:\n"
                f"sudo apt update && sudo apt install -y {packages}"
            )
            return False

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
                check=False
            )
            return result.returncode == 0
        except Exception:
            return False

    def _show_auto_close_message(self, title: str, message: str, timeout_ms: int = 3000):
        """Show a message box that auto-closes after timeout."""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)

        # Auto-close after timeout
        QTimer.singleShot(timeout_ms, msg_box.accept)

        msg_box.exec()

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

        # Get absolute paths
        lablink_root = Path.cwd().absolute()
        server_dir = lablink_root / "server"

        # Use venv python if available, otherwise system python (use absolute path)
        venv_python = lablink_root / "venv" / "bin" / "python"
        python_exe = str(venv_python) if venv_python.exists() else sys.executable

        try:
            # Add --debug flag if debug mode is enabled
            debug_flag = " --debug" if self.debug_mode else ""

            # Launch in new terminal
            # Server has mixed imports - needs both server/ as cwd AND LabLink root in PYTHONPATH
            if platform.system() == "Linux":
                cmd = f'cd {server_dir} && PYTHONPATH={lablink_root}:$PYTHONPATH {python_exe} main.py{debug_flag}'
                subprocess.Popen(['x-terminal-emulator', '-e', f'bash -c "{cmd}; exec bash"'])
            elif platform.system() == "Darwin":  # macOS
                cmd = f'cd {server_dir} && PYTHONPATH={lablink_root}:$PYTHONPATH {python_exe} main.py{debug_flag}'
                subprocess.Popen(['open', '-a', 'Terminal', f'bash -c "{cmd}; exec bash"'])
            elif platform.system() == "Windows":
                subprocess.Popen(['start', 'cmd', '/k', f'cd {server_dir} && set PYTHONPATH={lablink_root};%PYTHONPATH% && {python_exe} main.py{debug_flag}'], shell=True)

            self._show_auto_close_message(
                "Server Starting",
                "LabLink server is starting in a new terminal window.\n\n"
                "(This message will close automatically in 3 seconds)"
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

        # Get absolute path to LabLink root directory
        lablink_root = Path.cwd().absolute()

        # Use venv python if available, otherwise system python (use absolute path)
        venv_python = lablink_root / "venv" / "bin" / "python"
        python_exe = str(venv_python) if venv_python.exists() else sys.executable

        try:
            # Launch client using python -m to handle imports correctly
            # Change to LabLink root and run as module
            # Add --debug flag if debug mode is enabled
            args = [python_exe, '-m', 'client.main']
            if self.debug_mode:
                args.append('--debug')

            subprocess.Popen(
                args,
                cwd=str(lablink_root)
            )

            self._show_auto_close_message(
                "Client Starting",
                "LabLink client is starting...\n\n"
                "(This message will close automatically in 3 seconds)"
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

    # Dark theme with high contrast
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.ColorRole.Window, QColor(45, 45, 48))
    dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 32))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 48))
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(53, 53, 57))
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.ColorRole.Button, QColor(60, 60, 64))
    dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.Link, QColor(100, 149, 237))
    dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 122, 204))
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(dark_palette)

    # Global stylesheet for borders and enhanced visuals
    app.setStyleSheet("""
        QMainWindow {
            background-color: #2d2d30;
        }
        QGroupBox {
            border: 2px solid #3c3c3f;
            border-radius: 6px;
            margin-top: 12px;
            padding-top: 18px;
            background-color: #252526;
            font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 8px;
            color: #dcdcdc;
        }
        QPushButton {
            background-color: #3c3c3f;
            border: 1px solid #555555;
            border-radius: 4px;
            padding: 8px 16px;
            color: #dcdcdc;
        }
        QPushButton:hover {
            background-color: #505050;
            border: 1px solid #007acc;
        }
        QPushButton:pressed {
            background-color: #007acc;
        }
        QPushButton:disabled {
            background-color: #3c3c3f;
            color: #6d6d6d;
            border: 1px solid #444444;
        }
        QProgressBar {
            border: 1px solid #555555;
            border-radius: 4px;
            background-color: #1e1e1e;
            text-align: center;
            color: #dcdcdc;
        }
        QProgressBar::chunk {
            background-color: #007acc;
            border-radius: 3px;
        }
        QTextEdit, QPlainTextEdit {
            background-color: #1e1e1e;
            border: 1px solid #3c3c3f;
            border-radius: 4px;
            color: #dcdcdc;
            selection-background-color: #264f78;
        }
        QLabel {
            color: #dcdcdc;
        }
        QMessageBox {
            background-color: #2d2d30;
        }
        QDialog {
            background-color: #2d2d30;
            border: 2px solid #555555;
        }
    """)

    # Create and show launcher
    launcher = LabLinkLauncher()
    launcher.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
