# LabLink Client - Windows Installation Guide

## Quick Start (Recommended Method)

The easiest way to install LabLink Client on Windows is using the provided PowerShell installation script:

### Option 1: Using the Batch File Wrapper (Easiest)

1. Download or clone the LabLink repository
2. Open the LabLink folder in File Explorer
3. Double-click `install-client.bat`

That's it! The batch file handles the PowerShell execution policy automatically.

### Option 2: Using PowerShell Directly

Open PowerShell (no admin rights needed) and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-client.ps1
```

**Important:** You must use the `-ExecutionPolicy Bypass` flag because Windows blocks running PowerShell scripts by default for security reasons.

### Option 3: Remote Installation (One Command)

If you don't have the repository yet, you can install directly from GitHub:

```powershell
iwr -useb https://raw.githubusercontent.com/X9X0/LabLink/main/install-client.ps1 | iex
```

## Understanding the Execution Policy Error

If you try to run `.\install-client.ps1` directly, you'll see this error:

```
File C:\...\install-client.ps1 cannot be loaded because running scripts
is disabled on this system. For more information, see about_Execution_Policies
```

**This is a security feature of Windows PowerShell** that prevents untrusted scripts from running automatically. It's not a bug in LabLink!

### Why This Happens

Windows has several execution policies:
- **Restricted** (default): No scripts can run
- **RemoteSigned**: Only scripts from trusted publishers can run
- **Unrestricted**: All scripts can run (not recommended)
- **Bypass**: Temporarily allows a specific script to run

### Solutions

You have three options to solve this:

#### Solution 1: Use `-ExecutionPolicy Bypass` Flag (Recommended)

This is the safest approach - it only bypasses the policy for this one script:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-client.ps1
```

#### Solution 2: Use the Batch File Wrapper

Double-click `install-client.bat` - it automatically uses the bypass flag.

#### Solution 3: Change Your System Policy (Not Recommended)

You can permanently change your execution policy, but this reduces security:

```powershell
# Run PowerShell as Administrator, then:
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then you can run scripts normally:
```powershell
.\install-client.ps1
```

**Note:** We don't recommend this approach unless you understand the security implications.

## What the Installation Script Does

The `install-client.ps1` script will:

1. **Check for Python 3.11+** - Installs if missing or too old
2. **Optionally install Git** - Makes updates easier (you'll be prompted)
3. **Download LabLink** - Clones repository or downloads ZIP
4. **Create virtual environment** - Isolates Python dependencies
5. **Install dependencies** - Installs PyQt6 and other required packages
6. **Create launcher** - Makes a `lablink-client.bat` file
7. **Create shortcuts** - Desktop and Start Menu shortcuts

Installation typically takes 5-10 minutes depending on your internet connection.

## Manual Installation (Alternative)

If you prefer to install manually or the script doesn't work for some reason:

### Prerequisites

1. **Python 3.11 or higher**
   - Download from: https://www.python.org/downloads/
   - During installation, check "Add Python to PATH"

2. **Git** (optional, but recommended)
   - Download from: https://git-scm.com/download/win

### Steps

1. **Get the code**
   ```powershell
   # Option A: With Git
   git clone https://github.com/X9X0/LabLink.git
   cd LabLink

   # Option B: Download ZIP
   # Download from https://github.com/X9X0/LabLink/archive/refs/heads/main.zip
   # Extract and navigate to the folder
   ```

2. **Create virtual environment**
   ```powershell
   cd client
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install dependencies**
   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Run the client**
   ```powershell
   python main.py
   ```

5. **Create a shortcut (optional)**
   - Create a batch file `lablink-client.bat` in the LabLink folder:
   ```batch
   @echo off
   cd /d "%~dp0client"
   call venv\Scripts\activate.bat
   python main.py %*
   ```
   - Right-click the batch file and create a shortcut to your desktop

## System Requirements

- **OS:** Windows 10 or Windows 11 (64-bit)
- **Python:** 3.11 or higher
- **RAM:** 4 GB minimum, 8 GB recommended
- **Disk Space:** ~500 MB for installation
- **Network:** Required for connecting to LabLink servers

## Troubleshooting

### Python Not Found

If you see "Python is not recognized as an internal or external command":

1. Install Python from https://www.python.org/downloads/
2. During installation, **check "Add Python to PATH"**
3. Restart PowerShell after installation

### Permission Denied During Installation

If Python installation fails:

1. Right-click PowerShell
2. Select "Run as Administrator"
3. Try the installation command again

### Virtual Environment Activation Fails

If `.\venv\Scripts\activate` doesn't work:

```powershell
# Try this instead:
.\venv\Scripts\Activate.ps1
```

If you still get an execution policy error:
```powershell
powershell -ExecutionPolicy Bypass -File .\venv\Scripts\Activate.ps1
```

### PyQt6 Installation Fails

PyQt6 requires Visual C++ redistributables. Install from:
https://aka.ms/vs/17/release/vc_redist.x64.exe

### Shortcut Doesn't Work

If the desktop shortcut doesn't launch LabLink:

1. Right-click the shortcut → Properties
2. Check that "Target" points to `lablink-client.bat`
3. Check that "Start in" points to your LabLink folder

### SD Card Writer Shows "Not Supported on Windows"

The SD card image writer is not implemented for Windows in the GUI. Use one of these alternatives:

- **Win32 Disk Imager**: https://sourceforge.net/projects/win32diskimager/
- **Rufus**: https://rufus.ie/
- **balenaEtcher**: https://www.balena.io/etcher/

You can still use the SSH Deployment Wizard to deploy LabLink to an existing Raspberry Pi.

## Getting Help

If you encounter issues:

1. Check this troubleshooting section
2. Check the [main README](README.md) for general documentation
3. File an issue on GitHub: https://github.com/X9X0/LabLink/issues

## Next Steps

Once installed, you can:

1. **Launch LabLink Client**
   - Double-click the desktop shortcut, or
   - Run `lablink-client.bat`, or
   - Navigate to `client` folder and run `python main.py`

2. **Connect to a Server**
   - Use the SSH Deployment Wizard to set up a new Raspberry Pi server
   - Or connect to an existing LabLink server via File → Connect to Server

3. **Discover Raspberry Pis**
   - Use Tools → Raspberry Pi Discovery to find LabLink servers on your network

4. **Explore the Documentation**
   - See [Getting Started Guide](docs/GETTING_STARTED.md)
   - See [API Reference](docs/API_REFERENCE.md)
   - See [Client README](client/README.md)

## License

TBD
