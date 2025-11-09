#!/usr/bin/env python3
"""
LabLink Setup Script

This script checks and installs all dependencies for LabLink server and client.
It handles:
- Python version verification
- System package checks
- Python package installation
- Virtual environment setup (optional)
- Configuration file generation
- Installation verification

Usage:
    python3 setup.py              # Full setup (interactive)
    python3 setup.py --server     # Server only
    python3 setup.py --client     # Client only
    python3 setup.py --check      # Check only (no install)
    python3 setup.py --auto       # Auto-install without prompts
"""

import sys
import subprocess
import os
import platform
import argparse
from pathlib import Path
from typing import List, Tuple, Optional


# Color codes for terminal output
class Colors:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text: str):
    """Print header text."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text:^70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}\n")


def print_success(text: str):
    """Print success message."""
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_warning(text: str):
    """Print warning message."""
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")


def print_info(text: str):
    """Print info message."""
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")


def check_python_version() -> bool:
    """Check if Python version is >= 3.8."""
    print_header("Checking Python Version")

    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"

    print(f"Python version: {version_str}")

    if version.major >= 3 and version.minor >= 8:
        print_success(f"Python {version_str} is supported")
        return True
    else:
        print_error(f"Python {version_str} is not supported")
        print_error("LabLink requires Python 3.8 or higher")
        return False


def check_pip_installed() -> bool:
    """Check if pip is installed."""
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', '--version'],
            capture_output=True,
            text=True,
            check=False
        )
        return result.returncode == 0
    except Exception:
        return False


def install_pip(auto: bool = False) -> bool:
    """Install pip using ensurepip or get-pip.py."""
    print_header("Installing pip")

    print_info("pip is not installed, attempting to install...")

    # Try ensurepip first (built into Python 3.4+)
    print_info("Trying ensurepip...")
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'ensurepip', '--upgrade'],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode == 0:
            print_success("pip installed successfully using ensurepip")
            return True
        else:
            print_warning("ensurepip failed, trying get-pip.py...")
    except Exception as e:
        print_warning(f"ensurepip failed: {e}")
        print_info("Trying get-pip.py...")

    # Try get-pip.py as fallback
    try:
        import urllib.request

        print_info("Downloading get-pip.py...")
        url = "https://bootstrap.pypa.io/get-pip.py"

        with urllib.request.urlopen(url) as response:
            get_pip_script = response.read()

        # Save to temporary file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.py', delete=False) as f:
            f.write(get_pip_script)
            get_pip_path = f.name

        print_info("Running get-pip.py...")
        result = subprocess.run(
            [sys.executable, get_pip_path],
            capture_output=True,
            text=True,
            check=False
        )

        # Clean up
        try:
            os.unlink(get_pip_path)
        except Exception:
            pass

        if result.returncode == 0:
            print_success("pip installed successfully using get-pip.py")
            return True
        else:
            print_error("Failed to install pip using get-pip.py")
            if result.stderr:
                print(result.stderr)
            return False

    except Exception as e:
        print_error(f"Failed to download/run get-pip.py: {e}")
        print_error("\nPlease install pip manually:")
        print_info("  Ubuntu/Debian: sudo apt install python3-pip")
        print_info("  Fedora/RHEL: sudo dnf install python3-pip")
        print_info("  macOS: python3 -m ensurepip --upgrade")
        print_info("  Windows: Download and run get-pip.py from https://bootstrap.pypa.io/get-pip.py")
        return False


def check_externally_managed() -> bool:
    """Check if this is an externally-managed Python environment (PEP 668)."""
    # Check for EXTERNALLY-MANAGED file (Debian/Ubuntu)
    import sysconfig
    stdlib = sysconfig.get_path('stdlib')
    if stdlib:
        marker = os.path.join(stdlib, 'EXTERNALLY-MANAGED')
        return os.path.exists(marker)
    return False


def get_os_info() -> dict:
    """Get operating system information."""
    return {
        'system': platform.system(),
        'release': platform.release(),
        'version': platform.version(),
        'machine': platform.machine(),
        'python': platform.python_version()
    }


def check_system_packages() -> Tuple[bool, List[str]]:
    """Check for required system packages."""
    print_header("Checking System Dependencies")

    os_info = get_os_info()
    print(f"Operating System: {os_info['system']} {os_info['release']}")
    print(f"Architecture: {os_info['machine']}")

    missing = []

    # Check for VISA library (for SCPI equipment communication)
    if os_info['system'] == 'Linux':
        print_info("Checking for NI-VISA or libusb...")
        # Check for common VISA installations
        visa_paths = [
            '/usr/local/vxipnp/linux',
            '/usr/lib/libvisa.so',
            '/usr/local/lib/libvisa.so'
        ]

        visa_found = any(os.path.exists(path) for path in visa_paths)

        if not visa_found:
            print_warning("NI-VISA not detected (optional for hardware control)")
            print_info("Install from: https://www.ni.com/en-us/support/downloads/drivers/download.ni-visa.html")
        else:
            print_success("VISA library found")

    elif os_info['system'] == 'Windows':
        print_info("On Windows, NI-VISA should be installed separately")
        print_info("Download from: https://www.ni.com/en-us/support/downloads/drivers/download.ni-visa.html")

    elif os_info['system'] == 'Darwin':  # macOS
        print_info("On macOS, NI-VISA should be installed separately")
        print_info("Download from: https://www.ni.com/en-us/support/downloads/drivers/download.ni-visa.html")

    return len(missing) == 0, missing


def check_package_installed(package: str) -> bool:
    """Check if a Python package is installed."""
    try:
        __import__(package.split('[')[0].replace('-', '_'))
        return True
    except ImportError:
        return False


def get_package_version(package: str) -> Optional[str]:
    """Get installed package version."""
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'show', package],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if line.startswith('Version:'):
                    return line.split(':', 1)[1].strip()
    except Exception:
        pass
    return None


def check_python_packages(packages: List[str], name: str) -> Tuple[List[str], List[str]]:
    """Check which Python packages are installed."""
    print_header(f"Checking {name} Python Dependencies")

    installed = []
    missing = []

    for package in packages:
        # Handle packages with extras like "fastapi[all]"
        pkg_name = package.split('[')[0].split('>=')[0].split('==')[0]

        if check_package_installed(pkg_name):
            version = get_package_version(pkg_name)
            version_str = f" ({version})" if version else ""
            print_success(f"{pkg_name}{version_str}")
            installed.append(package)
        else:
            print_error(f"{package} - NOT INSTALLED")
            missing.append(package)

    print(f"\nInstalled: {len(installed)}/{len(packages)}")

    return installed, missing


def install_packages(packages: List[str], name: str, auto: bool = False) -> bool:
    """Install Python packages."""
    if not packages:
        print_success(f"All {name} dependencies already installed")
        return True

    print_header(f"Installing {name} Dependencies")

    print(f"The following packages will be installed:")
    for pkg in packages:
        print(f"  • {pkg}")

    if not auto:
        response = input(f"\nInstall {len(packages)} package(s)? [Y/n]: ").strip().lower()
        if response and response not in ['y', 'yes']:
            print_warning("Installation cancelled by user")
            return False

    print(f"\nInstalling {len(packages)} package(s)...")

    # Install all packages at once
    cmd = [sys.executable, '-m', 'pip', 'install'] + packages

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print_success(f"Successfully installed {len(packages)} package(s)")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Installation failed: {e}")
        if e.stderr:
            print(e.stderr)
        return False


def create_requirements_files():
    """Create requirements files if they don't exist."""
    print_header("Checking Requirements Files")

    # Server requirements
    server_requirements = [
        "fastapi>=0.104.0",
        "uvicorn[standard]>=0.24.0",
        "pyvisa>=1.13.0",
        "pyvisa-py>=0.7.0",
        "python-dotenv>=1.0.0",
        "pydantic>=2.4.0",
        "numpy>=1.24.0",
        "scipy>=1.11.0",
        "h5py>=3.9.0",
        "zeroconf>=0.119.0",
        "apscheduler>=3.10.0",
        "websockets>=12.0",
    ]

    # Client requirements
    client_requirements = [
        "PyQt6>=6.6.0",
        "requests>=2.31.0",
        "numpy>=1.24.0",
        "pyqtgraph>=0.13.0",
        "matplotlib>=3.8.0",
        "zeroconf>=0.119.0",
    ]

    # Test requirements
    test_requirements = [
        "pytest>=7.4.0",
        "pytest-asyncio>=0.21.0",
        "pytest-cov>=4.1.0",
        "pytest-qt>=4.2.0",
        "httpx>=0.25.0",
    ]

    # Create server requirements.txt
    server_req_path = Path("server/requirements.txt")
    if not server_req_path.exists():
        print_info(f"Creating {server_req_path}")
        server_req_path.write_text('\n'.join(server_requirements) + '\n')
        print_success(f"Created {server_req_path}")
    else:
        print_success(f"{server_req_path} exists")

    # Create client requirements.txt
    client_req_path = Path("client/requirements.txt")
    if not client_req_path.exists():
        print_info(f"Creating {client_req_path}")
        client_req_path.parent.mkdir(exist_ok=True)
        client_req_path.write_text('\n'.join(client_requirements) + '\n')
        print_success(f"Created {client_req_path}")
    else:
        print_success(f"{client_req_path} exists")

    # Create requirements-test.txt (already exists from previous work)
    test_req_path = Path("requirements-test.txt")
    if not test_req_path.exists():
        print_info(f"Creating {test_req_path}")
        test_req_path.write_text('\n'.join(test_requirements) + '\n')
        print_success(f"Created {test_req_path}")
    else:
        print_success(f"{test_req_path} exists")

    return server_requirements, client_requirements, test_requirements


def create_env_file():
    """Create .env file if it doesn't exist."""
    print_header("Checking Configuration Files")

    env_path = Path("server/.env")
    env_example_path = Path("server/.env.example")

    if env_path.exists():
        print_success(f"{env_path} already exists")
        return True

    if env_example_path.exists():
        print_info(f"Copying {env_example_path} to {env_path}")
        env_path.write_text(env_example_path.read_text())
        print_success(f"Created {env_path}")
        print_warning("Please review and update server/.env with your settings")
        return True
    else:
        print_warning(f"{env_example_path} not found")
        print_info("Creating default .env file")

        default_env = """# LabLink Server Configuration

# Server Settings
HOST=0.0.0.0
PORT=8000
WS_PORT=8001

# Logging
LOG_LEVEL=INFO
LOG_FILE=lablink.log

# VISA Settings
VISA_LIBRARY=@py
VISA_TIMEOUT=5000

# Data Storage
DATA_DIR=./data
EXPORT_DIR=./exports

# Safety Settings
ENABLE_SAFETY_LIMITS=true
MAX_VOLTAGE=50.0
MAX_CURRENT=10.0
MAX_POWER=500.0

# Acquisition Settings
DEFAULT_BUFFER_SIZE=10000
MAX_BUFFER_SIZE=10000000
DEFAULT_SAMPLE_RATE=1000.0

# mDNS Settings
ENABLE_MDNS=true
MDNS_SERVICE_NAME=LabLink Server
"""
        env_path.write_text(default_env)
        print_success(f"Created {env_path}")
        print_warning("Please review and update server/.env with your settings")
        return True


def verify_installation() -> bool:
    """Verify that installation was successful."""
    print_header("Verifying Installation")

    success = True

    # Test imports
    tests = [
        ("FastAPI", "fastapi"),
        ("PyVISA", "pyvisa"),
        ("NumPy", "numpy"),
        ("SciPy", "scipy"),
    ]

    for name, module in tests:
        try:
            __import__(module)
            print_success(f"{name} import successful")
        except ImportError as e:
            print_error(f"{name} import failed: {e}")
            success = False

    return success


def setup_virtual_env(auto: bool = False) -> bool:
    """Optionally create and activate virtual environment."""
    print_header("Virtual Environment Setup")

    venv_path = Path("venv")

    if venv_path.exists():
        print_success("Virtual environment already exists")
        print_info(f"Activate with: source venv/bin/activate (Linux/macOS) or venv\\Scripts\\activate (Windows)")
        return True

    if not auto:
        response = input("Create virtual environment? [Y/n]: ").strip().lower()
        if response and response not in ['y', 'yes']:
            print_info("Skipping virtual environment creation")
            return True

    print_info("Creating virtual environment...")

    try:
        subprocess.run([sys.executable, '-m', 'venv', 'venv'], check=True)
        print_success("Virtual environment created")
        print_warning("Please activate the virtual environment and run setup again:")
        print_info("  Linux/macOS: source venv/bin/activate")
        print_info("  Windows: venv\\Scripts\\activate")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to create virtual environment: {e}")
        return False


def main():
    """Main setup function."""
    parser = argparse.ArgumentParser(
        description='LabLink Setup Script - Install dependencies and configure',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 setup.py              # Full interactive setup
  python3 setup.py --auto       # Auto-install everything
  python3 setup.py --server     # Server dependencies only
  python3 setup.py --client     # Client dependencies only
  python3 setup.py --check      # Check only (no install)
  python3 setup.py --venv       # Setup virtual environment first
        """
    )

    parser.add_argument('--server', action='store_true', help='Install server dependencies only')
    parser.add_argument('--client', action='store_true', help='Install client dependencies only')
    parser.add_argument('--check', action='store_true', help='Check dependencies without installing')
    parser.add_argument('--auto', action='store_true', help='Auto-install without prompts')
    parser.add_argument('--venv', action='store_true', help='Setup virtual environment')
    parser.add_argument('--skip-system', action='store_true', help='Skip system package checks')

    args = parser.parse_args()

    # Print banner
    print(f"""
{Colors.HEADER}{Colors.BOLD}
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║                    LabLink Setup Script                           ║
║                                                                   ║
║         Automated dependency installation and configuration       ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
{Colors.ENDC}
    """)

    # Virtual environment setup
    if args.venv:
        setup_virtual_env(args.auto)
        return 0

    # Check Python version
    if not check_python_version():
        return 1

    # Check for externally-managed environment (PEP 668)
    is_externally_managed = check_externally_managed()

    # Check and install pip if needed
    if not check_pip_installed():
        print_warning("pip is not installed")

        if is_externally_managed:
            print_error("\nThis is a Debian/Ubuntu system with PEP 668 protection.")
            print_info("pip must be installed via apt or you can use a virtual environment.\n")

            print(f"{Colors.OKGREEN}Option 1: Install pip via apt (system-wide){Colors.ENDC}")
            print(f"  Commands: sudo apt update && sudo apt install python3-pip python3-venv\n")

            print(f"{Colors.OKGREEN}Option 2: Use virtual environment (isolated, recommended for development){Colors.ENDC}")
            print(f"  This script can create and set up a virtual environment for you.\n")

            if args.auto:
                print_info("Auto mode: Creating virtual environment...")
                choice = '2'
            else:
                choice = input(f"{Colors.BOLD}Choose an option [1/2]: {Colors.ENDC}").strip()

            if choice == '1':
                print_info("\nPlease run the following commands to install pip:")
                print(f"{Colors.OKCYAN}  sudo apt update{Colors.ENDC}")
                print(f"{Colors.OKCYAN}  sudo apt install python3-pip python3-venv{Colors.ENDC}")
                print(f"\nThen run this script again:")
                print(f"{Colors.OKCYAN}  python3 setup.py --auto{Colors.ENDC}")
                return 1
            elif choice == '2':
                if not setup_virtual_env(args.auto):
                    return 1
                print_error("\nVirtual environment created successfully!")
                print_info("Please activate it and run setup again:")
                print(f"{Colors.OKCYAN}  source venv/bin/activate{Colors.ENDC}")
                print(f"{Colors.OKCYAN}  python3 setup.py --auto{Colors.ENDC}")
                return 0
            else:
                print_error("Invalid choice. Exiting.")
                return 1

        if not args.check:
            if not install_pip(args.auto):
                print_error("Failed to install pip")
                print_error("Please install pip manually and run setup again")
                return 1
        else:
            print_error("pip is required but not installed")
            return 1
    else:
        print_success("pip is installed")

    # Check system packages
    if not args.skip_system:
        system_ok, missing_system = check_system_packages()
        if not system_ok and not args.auto:
            response = input("\nContinue anyway? [Y/n]: ").strip().lower()
            if response and response not in ['y', 'yes']:
                return 1

    # Create requirements files
    server_reqs, client_reqs, test_reqs = create_requirements_files()

    # Determine what to install
    install_server = args.server or (not args.client)
    install_client = args.client or (not args.server)

    all_success = True

    # Check and install server dependencies
    if install_server:
        installed, missing = check_python_packages(server_reqs, "Server")

        if not args.check and missing:
            success = install_packages(missing, "Server", args.auto)
            all_success = all_success and success

    # Check and install client dependencies
    if install_client:
        installed, missing = check_python_packages(client_reqs, "Client")

        if not args.check and missing:
            success = install_packages(missing, "Client", args.auto)
            all_success = all_success and success

    # Create configuration files
    if not args.check:
        create_env_file()

    # Verify installation
    if not args.check and all_success:
        verify_installation()

    # Print summary
    print_header("Setup Summary")

    if args.check:
        print_info("Check-only mode completed")
    elif all_success:
        print_success("Setup completed successfully!")
        print("\nNext steps:")
        print("  1. Review and update server/.env configuration")
        print("  2. Start the server: cd server && python3 main.py")
        print("  3. Run demo: python3 demo_acquisition_full.py")
        print("\nFor more information, see:")
        print("  • README.md - Project overview")
        print("  • client/ACQUISITION_CLIENT.md - Client documentation")
        print("  • server/ACQUISITION_SYSTEM.md - Server documentation")
    else:
        print_error("Setup completed with errors")
        print_warning("Some dependencies may not have installed correctly")
        print_info("Try running with --auto flag or install manually")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
