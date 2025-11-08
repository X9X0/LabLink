# LabLink Deployment Guide

This guide covers different deployment methods for LabLink server and client.

---

## 🎯 Quick Overview

| Method | Platform | Use Case | Difficulty |
|--------|----------|----------|------------|
| **Docker** | All | Server deployment | ⭐ Easy |
| **PyInstaller** | All | Client executable | ⭐⭐ Moderate |
| **Python Wheel** | All | Developer install | ⭐ Easy |
| **System Service** | Linux | Production server | ⭐⭐ Moderate |
| **Installers** | OS-specific | End users | ⭐⭐⭐ Advanced |
| **Raspberry Pi** | RPi | Turnkey solution | ⭐⭐⭐⭐ Advanced |

---

## 🐳 Docker Deployment (Recommended)

### Server Container

**1. Create Dockerfile:**
```dockerfile
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libusb-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy and install requirements
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY server/ .

# Expose ports
EXPOSE 8000 8001

# Health check
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**2. Create docker-compose.yml:**
```yaml
version: '3.8'

services:
  lablink-server:
    build: .
    container_name: lablink
    ports:
      - "8000:8000"
      - "8001:8001"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./states:/app/states
    environment:
      - LABLINK_SERVER_NAME=LabLink Production
      - LABLINK_LOG_LEVEL=INFO
    restart: unless-stopped
    devices:
      - /dev/bus/usb:/dev/bus/usb  # USB device access
    privileged: true  # For USB access

  # Optional: Add database if needed
  # postgres:
  #   image: postgres:15
  #   environment:
  #     POSTGRES_DB: lablink
  #     POSTGRES_PASSWORD: changeme
  #   volumes:
  #     - postgres-data:/var/lib/postgresql/data

volumes:
  postgres-data:
```

**3. Build and Run:**
```bash
# Build image
docker build -t lablink-server:1.0.0 .

# Run with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

**4. Production Deployment:**
```bash
# Save image
docker save lablink-server:1.0.0 | gzip > lablink-server-1.0.0.tar.gz

# Load on another machine
gunzip -c lablink-server-1.0.0.tar.gz | docker load

# Or push to registry
docker tag lablink-server:1.0.0 myregistry/lablink-server:1.0.0
docker push myregistry/lablink-server:1.0.0
```

---

## 📱 Client Executable (PyInstaller)

### Windows/macOS/Linux Standalone

**1. Create spec file:**

```python
# lablink.spec
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['client/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('client/ui/*.py', 'ui'),
        ('client/api/*.py', 'api'),
        ('client/models/*.py', 'models'),
    ],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'requests',
        'websockets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='LabLink',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='resources/icon.ico',  # Add your icon
)

# macOS bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='LabLink.app',
        icon='resources/icon.icns',
        bundle_identifier='com.lablink.client',
    )
```

**2. Build:**
```bash
# Install PyInstaller
pip install pyinstaller

# Build from spec
pyinstaller lablink.spec

# Or simple one-liner
pyinstaller --onefile --windowed --name LabLink client/main.py

# Output in dist/ folder
```

**3. Platform-Specific Notes:**

**Windows:**
```bash
# Add icon
pyinstaller --icon=resources/icon.ico --onefile --windowed client/main.py

# Result: dist/LabLink.exe (~80MB)
```

**macOS:**
```bash
# Create .app bundle
pyinstaller --onefile --windowed --name LabLink client/main.py

# Sign the app (requires Apple Developer account)
codesign --deep --force --verify --verbose \
  --sign "Developer ID Application: Your Name" \
  dist/LabLink.app

# Create DMG
create-dmg \
  --volname "LabLink" \
  --window-pos 200 120 \
  --window-size 600 400 \
  --icon-size 100 \
  --app-drop-link 425 120 \
  LabLink-1.0.0.dmg \
  dist/LabLink.app
```

**Linux:**
```bash
# Build executable
pyinstaller --onefile client/main.py

# Create .desktop file
cat > lablink.desktop << EOF
[Desktop Entry]
Type=Application
Name=LabLink
Comment=Laboratory Equipment Control
Exec=/usr/local/bin/lablink
Icon=/usr/share/icons/lablink.png
Terminal=false
Categories=Science;Education;
EOF

# Install
sudo cp dist/LabLink /usr/local/bin/lablink
sudo cp lablink.desktop /usr/share/applications/
```

---

## 🔧 Python Wheel Package

### For pip installation

**1. Create setup.py:**
```python
from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

# Server package
setup(
    name="lablink-server",
    version="0.10.0",
    author="Your Name",
    description="Laboratory equipment control server",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/lablink",
    packages=find_packages(where="server"),
    package_dir={"": "server"},
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.11",
    install_requires=[
        "fastapi==0.109.0",
        "uvicorn[standard]==0.27.0",
        "websockets==12.0",
        "pyvisa==1.14.1",
        "pyvisa-py==0.7.1",
        "numpy==1.26.3",
        "pandas==2.2.0",
        "h5py==3.10.0",
        "pydantic==2.5.3",
        "pyyaml",
        "python-dotenv",
        "apscheduler",
        "psutil",
    ],
    entry_points={
        "console_scripts": [
            "lablink-server=main:main",
        ],
    },
)
```

**2. Build and distribute:**
```bash
# Install build tools
pip install build twine

# Build wheel
python -m build

# Result:
# dist/lablink_server-0.10.0-py3-none-any.whl
# dist/lablink-server-0.10.0.tar.gz

# Test locally
pip install dist/lablink_server-0.10.0-py3-none-any.whl

# Upload to PyPI (requires account)
twine upload dist/*

# Users can then install with:
pip install lablink-server
```

---

## ⚙️ System Service (Linux)

### Systemd Service

**1. Create service file:**
```bash
sudo nano /etc/systemd/system/lablink.service
```

```ini
[Unit]
Description=LabLink Equipment Control Server
Documentation=https://github.com/yourusername/lablink
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=lablink
Group=lablink
WorkingDirectory=/opt/lablink
Environment="PATH=/opt/lablink/venv/bin"
ExecStart=/opt/lablink/venv/bin/python main.py

# Restart policy
Restart=always
RestartSec=10

# Logging
StandardOutput=append:/var/log/lablink/server.log
StandardError=append:/var/log/lablink/error.log

# Security
NoNewPrivileges=true
PrivateTmp=true

# Resource limits
MemoryLimit=512M
CPUQuota=50%

[Install]
WantedBy=multi-user.target
```

**2. Install:**
```bash
# Create user
sudo useradd -r -s /bin/false lablink

# Create directories
sudo mkdir -p /opt/lablink /var/log/lablink
sudo chown lablink:lablink /opt/lablink /var/log/lablink

# Copy application
sudo cp -r server/* /opt/lablink/

# Create virtual environment
cd /opt/lablink
sudo -u lablink python3 -m venv venv
sudo -u lablink venv/bin/pip install -r requirements.txt

# Enable and start service
sudo systemctl enable lablink
sudo systemctl start lablink
sudo systemctl status lablink

# View logs
sudo journalctl -u lablink -f
```

---

## 📦 Complete Installer Packages

### Windows Installer (Inno Setup)

**1. Create installer script:**
```iss
; lablink-setup.iss
#define MyAppName "LabLink"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Your Company"
#define MyAppURL "https://lablink.example.com"

[Setup]
AppId={{UNIQUE-GUID-HERE}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\LabLink
DefaultGroupName=LabLink
OutputDir=installers
OutputBaseFilename=LabLink-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Additional icons:"
Name: "startserver"; Description: "Start server automatically"; GroupDescription: "Server options:"

[Files]
Source: "dist\LabLink.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\server\*"; DestDir: "{app}\server"; Flags: ignoreversion recursesubdirs
Source: "README.md"; DestDir: "{app}"; Flags: isreadme

[Icons]
Name: "{group}\LabLink"; Filename: "{app}\LabLink.exe"
Name: "{autodesktop}\LabLink"; Filename: "{app}\LabLink.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\LabLink.exe"; Description: "Launch LabLink"; Flags: nowait postinstall skipifsilent
```

**2. Build:**
```bash
# Install Inno Setup
# Download from: https://jrsoftware.org/isdl.php

# Compile
iscc lablink-setup.iss

# Output: installers/LabLink-Setup-1.0.0.exe
```

### Debian/Ubuntu Package

**1. Create package structure:**
```bash
mkdir -p lablink-1.0.0/DEBIAN
mkdir -p lablink-1.0.0/opt/lablink
mkdir -p lablink-1.0.0/usr/share/applications
mkdir -p lablink-1.0.0/usr/share/icons
```

**2. Create control file:**
```
Package: lablink
Version: 1.0.0
Section: science
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.11), python3-pip
Maintainer: Your Name <your.email@example.com>
Description: Laboratory equipment control system
 LabLink provides comprehensive control and monitoring
 of laboratory equipment with data acquisition capabilities.
```

**3. Build:**
```bash
# Copy files
cp -r server/* lablink-1.0.0/opt/lablink/
cp lablink.desktop lablink-1.0.0/usr/share/applications/
cp icon.png lablink-1.0.0/usr/share/icons/lablink.png

# Build package
dpkg-deb --build lablink-1.0.0

# Result: lablink-1.0.0.deb
```

---

## 🥧 Raspberry Pi Image

### Pre-configured SD Card Image

**1. Base setup:**
```bash
# Start with Raspberry Pi OS Lite
# Install LabLink
sudo apt update
sudo apt install -y python3-pip git

# Clone and install
git clone https://github.com/yourusername/lablink.git /opt/lablink
cd /opt/lablink/server
pip3 install -r requirements.txt

# Configure auto-start
sudo systemctl enable lablink
sudo systemctl start lablink
```

**2. Create image:**
```bash
# On the Pi
sudo dd if=/dev/mmcblk0 of=/path/to/lablink-rpi-1.0.0.img bs=4M status=progress

# Compress
gzip lablink-rpi-1.0.0.img

# Users flash with:
# - Raspberry Pi Imager
# - balenaEtcher
# - dd command
```

---

## 📋 Deployment Checklist

### Pre-Deployment
- [ ] Test on clean system
- [ ] Verify all dependencies
- [ ] Check file permissions
- [ ] Test with sample data
- [ ] Review security settings
- [ ] Update documentation
- [ ] Create backup procedure

### Package Creation
- [ ] Build for all platforms
- [ ] Test installers
- [ ] Sign executables (Windows/macOS)
- [ ] Create checksums
- [ ] Write release notes
- [ ] Tag git release

### Distribution
- [ ] Upload to GitHub Releases
- [ ] Publish to PyPI (optional)
- [ ] Update website
- [ ] Announce release
- [ ] Monitor feedback

---

## 🔒 Security Considerations

### Code Signing
- **Windows:** Sign .exe with certificate
- **macOS:** Sign and notarize .app
- **Linux:** GPG sign packages

### Configuration
- Use environment variables for secrets
- Don't hardcode passwords
- Enable HTTPS for production
- Implement authentication

### Updates
- Implement auto-update mechanism
- Verify update signatures
- Backup before updating
- Rollback capability

---

## 📊 Size Estimates

| Package Type | Typical Size |
|--------------|-------------|
| Python wheel | 50-100 KB |
| PyInstaller exe (Windows) | 80-150 MB |
| PyInstaller app (macOS) | 100-200 MB |
| Docker image | 200-400 MB |
| Debian package | 50 KB + dependencies |
| Full installer | 100-200 MB |
| Raspberry Pi image | 2-4 GB |

---

## 🚀 Recommended Approach

**For End Users:**
1. **Client:** PyInstaller executable (easiest)
2. **Server:** Docker container (most flexible)

**For Developers:**
1. **Both:** Python wheel via pip (fastest iteration)

**For Production:**
1. **Server:** Docker + systemd service
2. **Client:** Platform-specific installer

---

This covers all major deployment methods. Would you like me to create any of these packages?
