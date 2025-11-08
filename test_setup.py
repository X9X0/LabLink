#!/usr/bin/env python3
"""Test script to verify LabLink setup and basic functionality."""

import sys
import subprocess
from pathlib import Path

def check_python_version():
    """Check Python version."""
    version = sys.version_info
    print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
    if version.major < 3 or (version.major == 3 and version.minor < 11):
        print("  ⚠ Warning: Python 3.11+ recommended")
        return False
    return True

def check_module(module_name, package_name=None):
    """Check if a Python module is installed."""
    package_name = package_name or module_name
    try:
        __import__(module_name)
        print(f"✓ {package_name} installed")
        return True
    except ImportError:
        print(f"✗ {package_name} not installed")
        return False

def check_server_dependencies():
    """Check server dependencies."""
    print("\n=== Server Dependencies ===")

    required = [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("websockets", "websockets"),
        ("pyvisa", "pyvisa"),
        ("numpy", "numpy"),
        ("pandas", "pandas"),
        ("h5py", "h5py"),
        ("pydantic", "pydantic"),
    ]

    optional = [
        ("PyQt6", "PyQt6"),
        ("pyqtgraph", "pyqtgraph"),
        ("matplotlib", "matplotlib"),
    ]

    missing = []
    for module, package in required:
        if not check_module(module, package):
            missing.append(package)

    if missing:
        print(f"\n⚠ Missing required packages: {', '.join(missing)}")
        print("\nTo install server dependencies:")
        print("  cd server && pip install -r requirements.txt")
        return False

    return True

def check_client_dependencies():
    """Check client dependencies."""
    print("\n=== Client Dependencies ===")

    required = [
        ("PyQt6", "PyQt6"),
        ("requests", "requests"),
        ("websockets", "websockets"),
    ]

    optional = [
        ("pyqtgraph", "pyqtgraph"),
        ("matplotlib", "matplotlib"),
        ("numpy", "numpy"),
    ]

    missing = []
    for module, package in required:
        if not check_module(module, package):
            missing.append(package)

    if missing:
        print(f"\n⚠ Missing required packages: {', '.join(missing)}")
        print("\nTo install client dependencies:")
        print("  cd client && pip install -r requirements.txt")
        return False

    return True

def check_file_structure():
    """Check if required files exist."""
    print("\n=== File Structure ===")

    files = [
        "server/main.py",
        "server/requirements.txt",
        "client/main.py",
        "client/requirements.txt",
        "client/api/client.py",
        "client/ui/main_window.py",
    ]

    all_exist = True
    for file_path in files:
        path = Path(file_path)
        if path.exists():
            print(f"✓ {file_path}")
        else:
            print(f"✗ {file_path} not found")
            all_exist = False

    return all_exist

def main():
    """Run all checks."""
    print("=" * 60)
    print("LabLink Setup Verification")
    print("=" * 60)

    python_ok = check_python_version()
    files_ok = check_file_structure()
    server_ok = check_server_dependencies()
    client_ok = check_client_dependencies()

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    if all([python_ok, files_ok, server_ok, client_ok]):
        print("✓ All checks passed! Ready to run LabLink.")
        print("\nNext steps:")
        print("  1. Start server:  cd server && python3 main.py")
        print("  2. Start client:  cd client && python3 main.py")
        return 0
    else:
        print("⚠ Some checks failed. Please review above.")
        print("\nQuick fix:")
        if not server_ok:
            print("  cd server && pip install -r requirements.txt")
        if not client_ok:
            print("  cd client && pip install -r requirements.txt")
        return 1

if __name__ == "__main__":
    sys.exit(main())
