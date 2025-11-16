# LabLink Setup Guide for Ubuntu 24.04

> **Quick Start Guide for New Users on Ubuntu 24.04 LTS**

This guide will help you get LabLink up and running on Ubuntu 24.04 in just a few minutes.

## 📋 What You'll Need

- Ubuntu 24.04 LTS (fresh installation or existing system)
- Internet connection
- About 1GB of free disk space
- 10-15 minutes of time

---

## 🚀 Quick Start (Recommended)

### Option 1: Fully Automated (One Command!)

If you just want to get started quickly without installing anything manually:

```bash
# Just clone and run the launcher
git clone https://github.com/X9X0/LabLink.git
cd LabLink
python3 lablink.py
```

**That's it!** The LabLink GUI launcher will:
- ✅ Check your environment automatically
- ✅ Detect missing system packages (Qt libraries, USB support, etc.)
- ✅ **Install system packages automatically with your permission**
- ✅ Show you what's missing with colored LED indicators
- ✅ Install Python dependencies with one click
- ✅ Let you start the server or client with one click

The launcher uses `pkexec` for a graphical password prompt when installing system packages, so you won't need to type commands in the terminal.

---

### Option 2: Manual System Dependencies First (Traditional)

If you prefer to install system dependencies manually before running the launcher:

**Step 1:** Install system dependencies:

```bash
sudo apt update && sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    libusb-1.0-0 \
    libxcb-xinerama0 \
    libxcb-icccm4 \
    libxcb-keysyms1 \
    libgl1-mesa-glx
```

This installs Python 3, pip, virtual environment support, Git, and required system libraries for Qt and USB communication.

**Step 2:** Clone LabLink:

```bash
cd ~
git clone https://github.com/X9X0/LabLink.git
cd LabLink
```

**Step 3:** Launch the GUI launcher:

```bash
python3 lablink.py
```

The launcher will verify all dependencies are installed and show green LED indicators.

---

## 🎨 Using the LabLink GUI Launcher

The GUI launcher (`lablink.py`) is your central hub for managing LabLink:

### LED Status Indicators

| Color | Meaning |
|-------|---------|
| 🟢 **Green** | All OK - Everything is working perfectly |
| 🟡 **Yellow** | Warning - Optional dependencies missing or minor issues |
| 🔴 **Red** | Error - Critical dependencies missing, must be fixed |
| ⚫ **Gray** | Unknown - Check hasn't been run yet |

### What Gets Checked

1. **Environment** (Python, pip, venv)
   - Python version (3.8+ required, 3.10+ recommended)
   - pip installation
   - Virtual environment status
   - PEP 668 compliance (Ubuntu 24.04 package management)

2. **System Dependencies** (Qt, USB)
   - Qt6 libraries for the GUI
   - USB libraries for equipment communication
   - NI-VISA (optional, for professional hardware support)

3. **Server Dependencies**
   - All Python packages needed to run the LabLink server
   - FastAPI, PyVISA, NumPy, etc.

4. **Client Dependencies**
   - All Python packages needed to run the LabLink client GUI
   - PyQt6, pyqtgraph, requests, etc.

### Interactive Features

- **Click any LED** to see detailed information about what's working and what's not
- **"Refresh Status" button** to re-check everything
- **"Fix Issues Automatically" button** to install missing dependencies
- **"Start Server" button** to launch the LabLink server in a new terminal
- **"Start Client" button** to launch the LabLink GUI client

---

## 🔧 Ubuntu 24.04 Specific Notes

### PEP 668 - Externally Managed Python

Ubuntu 24.04 implements PEP 668, which prevents you from installing Python packages system-wide with `pip install`. This is a **good thing** - it protects your system from conflicts.

**The LabLink launcher handles this automatically** by:
1. Detecting if you're in a virtual environment
2. Recommending virtual environment creation
3. Offering to create one for you

### Python Version

Ubuntu 24.04 comes with **Python 3.12** by default, which works great with LabLink. You're all set!

### Wayland vs X11

If you're using Wayland (default in Ubuntu 24.04), PyQt6 will work automatically. No configuration needed.

---

## 📖 Manual Installation (Alternative)

If you prefer to install manually or the GUI launcher isn't working:

### Server Installation

```bash
cd ~/LabLink/server

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create configuration file
cp .env.example .env

# Edit configuration (optional)
nano .env

# Run server
python main.py
```

The server will start on:
- API: http://localhost:8000
- WebSocket: ws://localhost:8001
- API Docs: http://localhost:8000/docs

### Client Installation

```bash
cd ~/LabLink/client

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Run client
python main.py
```

---

## 🔌 USB Permissions (For Hardware Control)

If you plan to connect lab equipment via USB, you'll need to set up udev rules:

```bash
# Create udev rules file
sudo nano /etc/udev/rules.d/99-lablink.rules
```

Add this content (adjust for your equipment):

```
# Generic USB instruments (USBTMC)
SUBSYSTEMS=="usb", ATTRS{idVendor}=="*", ATTRS{idProduct}=="*", MODE="0666", GROUP="plugdev"

# Specific vendors (examples)
SUBSYSTEMS=="usb", ATTRS{idVendor}=="0957", MODE="0666", GROUP="plugdev"  # Agilent/Keysight
SUBSYSTEMS=="usb", ATTRS{idVendor}=="1ab1", MODE="0666", GROUP="plugdev"  # Rigol
SUBSYSTEMS=="usb", ATTRS{idVendor}=="05ff", MODE="0666", GROUP="plugdev"  # Tektronix
```

Then reload udev rules:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Add your user to the `plugdev` group:

```bash
sudo usermod -a -G plugdev $USER
```

**Log out and back in** for group changes to take effect.

---

## 🌐 Firewall Configuration (Optional)

If you want to access the LabLink server from other computers on your network:

```bash
# Allow LabLink ports through UFW firewall
sudo ufw allow 8000/tcp comment 'LabLink API'
sudo ufw allow 8001/tcp comment 'LabLink WebSocket'
sudo ufw allow 80/tcp comment 'LabLink Dashboard'

# Enable firewall if not already enabled
sudo ufw enable
```

---

## 🐛 Troubleshooting

### "PyQt6 is not installed" on first run

This is expected! The `lablink.py` launcher will automatically install PyQt6 for itself. Just run it again:

```bash
python3 lablink.py
```

### Virtual environment activation issues

If you see "command not found" errors after creating a venv:

```bash
# Make sure you're in the LabLink directory
cd ~/LabLink

# Activate properly
source venv/bin/activate

# Your prompt should change to show (venv)
```

### "Permission denied" when accessing USB devices

Make sure you:
1. Created the udev rules (see USB Permissions section)
2. Added yourself to the `plugdev` group
3. **Logged out and back in** (or run `newgrp plugdev`)

### Qt platform plugin errors

If you see "qt.qpa.plugin: Could not load the Qt platform plugin":

```bash
sudo apt install --reinstall libxcb-xinerama0 libxcb-icccm4 libxcb-keysyms1
```

### Server won't start - Port already in use

Check if something is already using port 8000:

```bash
sudo lsof -i :8000
```

Kill the process or change the port in `server/.env`:

```bash
PORT=8080  # Change to any available port
```

---

## 📚 Next Steps

Once you have LabLink running:

1. **Read the User Guide**: [docs/USER_GUIDE.md](USER_GUIDE.md)
2. **Try the Demo Mode**: Run without hardware to explore features
3. **Connect Equipment**: Follow [docs/GETTING_STARTED.md](GETTING_STARTED.md)
4. **Check API Docs**: Visit http://localhost:8000/docs

---

## 🆘 Getting Help

- **Documentation**: Check the [docs/](.) folder
- **Issues**: Report bugs at https://github.com/X9X0/LabLink/issues
- **Discussions**: Ask questions in GitHub Discussions

---

## ✅ Quick Checklist

Before using LabLink, make sure:

- [ ] System dependencies installed (`libxcb-*`, `libusb`, etc.)
- [ ] Python 3.8+ installed (Python 3.12 recommended)
- [ ] Git installed
- [ ] LabLink cloned from GitHub
- [ ] Launched `lablink.py` and all LEDs are green or yellow
- [ ] (For hardware) USB permissions configured
- [ ] (For network access) Firewall ports opened

---

**Welcome to LabLink! 🎉**

You're now ready to control laboratory equipment like a pro. Start with the GUI launcher and explore from there.
