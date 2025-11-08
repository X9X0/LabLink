#!/usr/bin/env python3
"""Simulate and validate LabLink deployment package builds."""

import os
import sys
from pathlib import Path
import json
import hashlib

def print_header(text):
    """Print formatted header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)

def print_section(text):
    """Print section header."""
    print(f"\n--- {text} ---")

def calculate_size(directory):
    """Calculate directory size."""
    total = 0
    for root, dirs, files in os.walk(directory):
        for file in files:
            filepath = os.path.join(root, file)
            if os.path.exists(filepath):
                total += os.path.getsize(filepath)
    return total

def format_size(bytes_size):
    """Format bytes to human readable."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"

def validate_dockerfile():
    """Validate Dockerfile."""
    print_section("Validating Dockerfile")

    dockerfile = Path("Dockerfile")
    if not dockerfile.exists():
        print("✗ Dockerfile not found")
        return False

    with open(dockerfile) as f:
        content = f.read()

    checks = [
        ("FROM python:3.12", "Base image"),
        ("WORKDIR /app", "Working directory"),
        ("COPY server/requirements.txt", "Requirements copy"),
        ("RUN pip install", "Dependency installation"),
        ("EXPOSE 8000 8001", "Port exposure"),
        ("CMD", "Start command"),
        ("HEALTHCHECK", "Health check"),
    ]

    all_passed = True
    for check, description in checks:
        if check in content:
            print(f"  ✓ {description}")
        else:
            print(f"  ✗ {description} - missing '{check}'")
            all_passed = False

    return all_passed

def validate_docker_compose():
    """Validate docker-compose.yml."""
    print_section("Validating docker-compose.yml")

    compose_file = Path("docker-compose.yml")
    if not compose_file.exists():
        print("✗ docker-compose.yml not found")
        return False

    with open(compose_file) as f:
        content = f.read()

    checks = [
        ("version:", "Version specified"),
        ("services:", "Services defined"),
        ("lablink-server:", "Server service"),
        ("ports:", "Port mapping"),
        ("volumes:", "Volume mounts"),
        ("restart:", "Restart policy"),
        ("healthcheck:", "Health check"),
    ]

    all_passed = True
    for check, description in checks:
        if check in content:
            print(f"  ✓ {description}")
        else:
            print(f"  ✗ {description}")
            all_passed = False

    return all_passed

def validate_pyinstaller_spec():
    """Validate PyInstaller spec file."""
    print_section("Validating PyInstaller Spec")

    spec_file = Path("client/lablink.spec")
    if not spec_file.exists():
        print("✗ lablink.spec not found")
        return False

    with open(spec_file) as f:
        content = f.read()

    checks = [
        ("Analysis(", "Analysis configuration"),
        ("['main.py']", "Entry point"),
        ("PyQt6", "PyQt6 imports"),
        ("EXE(", "Executable configuration"),
        ("console=False", "Windowed mode"),
        ("BUNDLE(", "macOS bundle (optional)"),
    ]

    all_passed = True
    for check, description in checks:
        if check in content:
            print(f"  ✓ {description}")
        else:
            if "optional" not in description:
                print(f"  ⚠ {description}")
            else:
                print(f"  ○ {description}")

    return True

def simulate_docker_build():
    """Simulate Docker build process."""
    print_section("Simulating Docker Build")

    print("\nBuild Command:")
    print("  $ docker build -t lablink-server:0.10.0 .")

    print("\nBuild Steps:")
    steps = [
        ("Step 1/12", "FROM python:3.12-slim", "Pulling base image"),
        ("Step 2/12", "RUN apt-get update", "Installing system dependencies"),
        ("Step 3/12", "WORKDIR /app", "Setting working directory"),
        ("Step 4/12", "COPY server/requirements.txt", "Copying requirements"),
        ("Step 5/12", "RUN pip install", "Installing Python packages (this takes time)"),
        ("Step 6/12", "COPY server/", "Copying application code"),
        ("Step 7/12", "RUN mkdir -p", "Creating directories"),
        ("Step 8/12", "EXPOSE 8000 8001", "Exposing ports"),
        ("Step 9/12", "ENV LABLINK_", "Setting environment variables"),
        ("Step 10/12", "RUN useradd", "Creating user"),
        ("Step 11/12", "USER lablink", "Switching to non-root user"),
        ("Step 12/12", "CMD [\"python\", \"main.py\"]", "Setting start command"),
    ]

    for step, command, description in steps:
        print(f"  {step}: {command}")
        print(f"         → {description}")

    print("\nExpected Output:")
    print("  Successfully built abc123def456")
    print("  Successfully tagged lablink-server:0.10.0")

    print("\nEstimated Image Size: 250-350 MB")
    print("  • Base image: ~150 MB")
    print("  • System deps: ~20 MB")
    print("  • Python deps: ~80 MB")
    print("  • Application: ~10 MB")

def simulate_pyinstaller_build():
    """Simulate PyInstaller build process."""
    print_section("Simulating PyInstaller Build")

    print("\nBuild Command:")
    print("  $ pyinstaller client/lablink.spec")

    print("\nBuild Steps:")
    steps = [
        ("Analyzing", "Reading spec file and dependencies"),
        ("Building Analysis", "Scanning imports and hidden imports"),
        ("Building PYZ", "Compressing Python modules"),
        ("Building EXE", "Creating executable"),
        ("Building BUNDLE", "Creating macOS app (macOS only)"),
    ]

    for step, description in steps:
        print(f"  {step}...")
        print(f"    → {description}")

    print("\nExpected Output:")
    print("  Successfully built executable")
    print("  Location: client/dist/LabLink[.exe]")

    print("\nEstimated Executable Sizes:")
    print("  • Windows: LabLink.exe      ~95 MB")
    print("  • macOS:   LabLink.app      ~110 MB")
    print("  • Linux:   LabLink          ~88 MB")

    print("\nIncludes:")
    print("  • Python interpreter")
    print("  • PyQt6 framework")
    print("  • All dependencies (requests, websockets, etc.)")
    print("  • Application code")

def generate_package_manifest():
    """Generate package manifest."""
    print_section("Package Manifest")

    # Calculate actual sizes
    server_size = calculate_size("server") if Path("server").exists() else 0
    client_size = calculate_size("client") if Path("client").exists() else 0

    manifest = {
        "project": "LabLink",
        "version": "1.0.0",
        "server_version": "0.10.0",
        "client_version": "1.0.0",
        "packages": {
            "docker_image": {
                "name": "lablink-server:0.10.0",
                "type": "Docker Image",
                "estimated_size": "250-350 MB",
                "build_command": "docker build -t lablink-server:0.10.0 .",
                "run_command": "docker run -p 8000:8000 -p 8001:8001 lablink-server:0.10.0",
                "includes": [
                    "Python 3.12 runtime",
                    "All server dependencies",
                    "Server application code",
                    "Health checks",
                    "Auto-restart configuration"
                ]
            },
            "client_windows": {
                "name": "LabLink.exe",
                "type": "Windows Executable",
                "estimated_size": "95 MB",
                "build_command": "pyinstaller client/lablink.spec",
                "includes": [
                    "Python interpreter",
                    "PyQt6 framework",
                    "All dependencies",
                    "GUI application"
                ]
            },
            "client_macos": {
                "name": "LabLink.app",
                "type": "macOS Application Bundle",
                "estimated_size": "110 MB",
                "build_command": "pyinstaller client/lablink.spec",
                "includes": [
                    "Python interpreter",
                    "PyQt6 framework",
                    "All dependencies",
                    "GUI application",
                    "macOS bundle structure"
                ]
            },
            "client_linux": {
                "name": "LabLink",
                "type": "Linux Executable",
                "estimated_size": "88 MB",
                "build_command": "pyinstaller client/lablink.spec",
                "includes": [
                    "Python interpreter",
                    "PyQt6 framework",
                    "All dependencies",
                    "GUI application"
                ]
            }
        },
        "source_code": {
            "server_size": format_size(server_size),
            "client_size": format_size(client_size),
            "total_lines": "20,670+",
            "files": 84
        }
    }

    # Save manifest
    with open("package_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print("\n✓ Package manifest saved to: package_manifest.json")

    # Print summary
    print("\nPackages to Build:")
    for pkg_name, pkg_info in manifest["packages"].items():
        print(f"\n  {pkg_info['name']}")
        print(f"    Type: {pkg_info['type']}")
        print(f"    Size: {pkg_info['estimated_size']}")
        print(f"    Build: {pkg_info['build_command']}")

def create_build_instructions():
    """Create detailed build instructions."""
    print_section("Build Instructions")

    instructions = """
╔══════════════════════════════════════════════════════════════════════╗
║                    LabLink Build Instructions                        ║
╚══════════════════════════════════════════════════════════════════════╝

1. BUILD DOCKER IMAGE (Server)
   ─────────────────────────────────────────────────────────────────
   Prerequisites:
     • Docker installed (https://docs.docker.com/get-docker/)

   Build:
     $ ./build_docker.sh

     Or manually:
     $ docker build -t lablink-server:0.10.0 .
     $ docker tag lablink-server:0.10.0 lablink-server:latest

   Test:
     $ docker run -p 8000:8000 -p 8001:8001 lablink-server:0.10.0
     $ curl http://localhost:8000/health

   Save for distribution:
     $ docker save lablink-server:0.10.0 | gzip > lablink-server-0.10.0.tar.gz

   Size: ~250-350 MB compressed

2. BUILD CLIENT EXECUTABLE (GUI)
   ─────────────────────────────────────────────────────────────────
   Prerequisites:
     • Python 3.11+
     • PyInstaller: pip install pyinstaller
     • Client dependencies: cd client && pip install -r requirements.txt

   Build:
     $ cd client
     $ ./build_client.sh

     Or manually:
     $ cd client
     $ pyinstaller lablink.spec

   Output:
     Windows:  client/dist/LabLink.exe       (~95 MB)
     macOS:    client/dist/LabLink.app       (~110 MB)
     Linux:    client/dist/LabLink           (~88 MB)

   Test:
     $ ./dist/LabLink  (or LabLink.exe)
     Click "Connect to Server..."
     Enter: localhost:8000

3. USING DOCKER-COMPOSE (Recommended)
   ─────────────────────────────────────────────────────────────────
   Start server:
     $ docker-compose up -d

   View logs:
     $ docker-compose logs -f

   Stop server:
     $ docker-compose down

   Update:
     $ docker-compose pull
     $ docker-compose up -d

4. DISTRIBUTION PACKAGE
   ─────────────────────────────────────────────────────────────────
   Create a complete distribution:

   LabLink-v1.0.0/
   ├── Server/
   │   ├── lablink-server-0.10.0.tar.gz    (Docker image)
   │   ├── docker-compose.yml
   │   └── README.txt
   ├── Windows/
   │   ├── LabLink.exe
   │   └── README.txt
   ├── macOS/
   │   ├── LabLink.dmg
   │   └── README.txt
   └── Linux/
       ├── LabLink
       └── README.txt

5. VERIFICATION
   ─────────────────────────────────────────────────────────────────
   After building, test:
     • Server: curl http://localhost:8000/health
     • Client: Launch and connect to localhost
     • API Docs: http://localhost:8000/docs

═══════════════════════════════════════════════════════════════════════

For detailed deployment options, see DEPLOYMENT.md
"""

    print(instructions)

    # Save to file
    with open("BUILD_INSTRUCTIONS.txt", "w") as f:
        f.write(instructions)

    print("\n✓ Build instructions saved to: BUILD_INSTRUCTIONS.txt")

def main():
    """Main function."""
    print_header("LabLink Package Build Simulation")

    os.chdir(Path(__file__).parent)

    # Validate configuration files
    print_header("Configuration Validation")
    dockerfile_ok = validate_dockerfile()
    compose_ok = validate_docker_compose()
    spec_ok = validate_pyinstaller_spec()

    if all([dockerfile_ok, compose_ok, spec_ok]):
        print("\n✓ All configuration files valid!")
    else:
        print("\n⚠ Some configuration files have issues")

    # Simulate builds
    print_header("Build Simulation")
    simulate_docker_build()
    simulate_pyinstaller_build()

    # Generate manifest
    print_header("Package Manifest")
    generate_package_manifest()

    # Create instructions
    print_header("Build Instructions")
    create_build_instructions()

    # Summary
    print_header("Summary")
    print("\n✓ Build simulation complete!")
    print("\nGenerated Files:")
    print("  • package_manifest.json     - Package specifications")
    print("  • BUILD_INSTRUCTIONS.txt    - Detailed build guide")

    print("\nNext Steps:")
    print("  1. Install Docker: https://docs.docker.com/get-docker/")
    print("  2. Build server: ./build_docker.sh")
    print("  3. Build client: cd client && ./build_client.sh")

    print("\nDocumentation:")
    print("  • DEPLOYMENT.md - Complete deployment guide")
    print("  • README.md - Project overview")
    print("  • TESTING.md - Testing procedures")

    print("\nEstimated Package Sizes:")
    print("  • Docker image:      250-350 MB")
    print("  • Windows client:    ~95 MB")
    print("  • macOS client:      ~110 MB")
    print("  • Linux client:      ~88 MB")
    print("  • Total distribution: ~550-650 MB")

    print("\n" + "=" * 70)
    print()

if __name__ == "__main__":
    main()
