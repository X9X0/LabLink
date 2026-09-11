# LabLink GUI Client - Windows Installation Script
# PowerShell Script for Windows 10/11
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File install-client.ps1
#   OR
#   iwr -useb https://raw.githubusercontent.com/X9X0/LabLink/main/install-client.ps1 | iex

# Requires -Version 5.1

# Configuration
$LablinkDir = "$env:USERPROFILE\LabLink"
$CreateDesktopShortcut = $true
$CreateStartMenuShortcut = $true
# LabLink 2.0 requires Python 3.12+: numpy 2.5 and scipy 1.18 both drop 3.11.
$PythonMinVersion = [Version]"3.12.0"

# Color output functions
function Write-Step {
    param([string]$Message)
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Message" -ForegroundColor Green
}

function Write-ErrorMsg {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-WarningMsg {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-Header {
    Write-Host ""
    Write-Host "╔═══════════════════════════════════════════════════════╗" -ForegroundColor Blue
    Write-Host "║                                                       ║" -ForegroundColor Blue
    Write-Host "║           LabLink Client Installation                 ║" -ForegroundColor Blue
    Write-Host "║            Desktop GUI Application                    ║" -ForegroundColor Blue
    Write-Host "║                                                       ║" -ForegroundColor Blue
    Write-Host "╚═══════════════════════════════════════════════════════╝" -ForegroundColor Blue
    Write-Host ""
}

function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-PythonVersion {
    try {
        $pythonVersion = python --version 2>&1
        if ($pythonVersion -match "Python (\d+\.\d+\.\d+)") {
            return [Version]$Matches[1]
        }
    }
    catch {
        return $null
    }
    return $null
}

function Install-Python {
    Write-Step "Python not found or older than 3.12. Installing Python 3.12..."

    $pythonInstallerUrl = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
    $installerPath = "$env:TEMP\python-3.12-installer.exe"

    Write-Step "Downloading Python installer..."
    Invoke-WebRequest -Uri $pythonInstallerUrl -OutFile $installerPath

    Write-Step "Installing Python (this may take a few minutes)..."
    Start-Process -FilePath $installerPath -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_test=0" -Wait

    Remove-Item $installerPath

    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')

    Write-Step "Python installed"
}

function Install-Git {
    Write-Step "Git not found. Installing Git..."

    $gitInstallerUrl = "https://github.com/git-for-windows/git/releases/download/v2.43.0.windows.1/Git-2.43.0-64-bit.exe"
    $installerPath = "$env:TEMP\git-installer.exe"

    Write-Step "Downloading Git installer..."
    Invoke-WebRequest -Uri $gitInstallerUrl -OutFile $installerPath

    Write-Step "Installing Git..."
    Start-Process -FilePath $installerPath -ArgumentList "/VERYSILENT", "/NORESTART" -Wait

    Remove-Item $installerPath

    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')

    Write-Step "Git installed"
}

function Download-LabLink {
    Write-Step "Downloading LabLink Client..."

    # Create installation directory
    if (-not (Test-Path $LablinkDir)) {
        New-Item -ItemType Directory -Path $LablinkDir -Force | Out-Null
    }

    Set-Location $LablinkDir

    # Check if git is available
    if (Get-Command git -ErrorAction SilentlyContinue) {
        Write-Step "Cloning LabLink repository..."
        if (Test-Path ".git") {
            git pull
        }
        else {
            git clone https://github.com/X9X0/LabLink.git .
        }
    }
    else {
        Write-Step "Git not found. Downloading archive..."
        $archiveUrl = "https://github.com/X9X0/LabLink/archive/refs/heads/main.zip"
        $archivePath = "$env:TEMP\lablink.zip"

        Invoke-WebRequest -Uri $archiveUrl -OutFile $archivePath
        Expand-Archive -Path $archivePath -DestinationPath $env:TEMP\lablink-extract -Force

        # Move contents
        $extractedDir = Get-ChildItem "$env:TEMP\lablink-extract" | Select-Object -First 1
        Move-Item "$($extractedDir.FullName)\*" $LablinkDir -Force

        # Cleanup
        Remove-Item $archivePath
        Remove-Item "$env:TEMP\lablink-extract" -Recurse -Force
    }

    Write-Step "LabLink downloaded to $LablinkDir"
}

function Install-ClientDependencies {
    Write-Step "Installing Python dependencies..."

    Set-Location "$LablinkDir\client"

    # Create virtual environment
    if (-not (Test-Path "venv")) {
        python -m venv venv
        Write-Step "Created Python virtual environment"
    }

    # Activate virtual environment and install dependencies
    & ".\venv\Scripts\Activate.ps1"

    # Upgrade pip
    python -m pip install --upgrade pip

    # Install requirements
    pip install -r requirements.txt

    Write-Step "Client dependencies installed"

    # The Start Menu offers a Server entry, so the server's dependencies have
    # to be here too -- a shortcut that opens nothing is worse than no
    # shortcut. This is ~20 further packages (fastapi, uvicorn, pyvisa and so
    # on) on top of the client's.
    Write-Step "Installing server dependencies (for the Server shortcut)..."
    pip install -r "$LablinkDir\shared\requirements.txt"
    pip install -r "$LablinkDir\server\requirements.txt"

    Write-Step "Server dependencies installed"
}

function Create-LauncherScript {
    Write-Step "Creating launcher script..."

    $launcherPath = "$LablinkDir\lablink-client.bat"

    $batchContent = @'
@echo off
REM LabLink Launcher
REM This batch file activates the virtual environment and runs the LabLink launcher

REM Change to LabLink root directory (handles spaces in path)
cd /d "%~dp0"

REM Check if virtual environment exists
if not exist "client\venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found!
    echo Please run install-client.bat again.
    pause
    exit /b 1
)

REM Activate virtual environment
call "client\venv\Scripts\activate.bat"
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment!
    pause
    exit /b 1
)

REM Set PYTHONPATH to LabLink root so Python can find the client module
set PYTHONPATH=%~dp0

REM Run LabLink launcher from root directory
python lablink.py %*
'@

    Set-Content -Path $launcherPath -Value $batchContent

    Write-Step "Launcher script created: $launcherPath"
}

function New-LabLinkShortcut {
    param(
        [string]$Path,
        [string]$Target,
        [string]$Description
    )

    # Point at pythonw.exe rather than a .bat file. Windows opens a console
    # window for any batch file, and python.exe attaches one of its own, so
    # either would leave a black window sitting behind the GUI for the whole
    # session. pythonw.exe has no console at all.
    #
    # That is why lablink_launch.pyw exists: with no console there is nowhere
    # for a traceback to go, so it catches startup failures and shows them in
    # a message box instead of failing silently.
    $pythonw = "$LablinkDir\client\venv\Scripts\pythonw.exe"
    $launcher = "$LablinkDir\scripts\windows\lablink_launch.pyw"

    # Never point a shortcut at something that is not there. Without a console
    # there is nothing to print a "file not found" to, so a shortcut aimed at a
    # missing shim does not fail -- it does nothing at all, which is the exact
    # failure this whole design exists to prevent. Refusing loudly here is the
    # only place that silence can still be turned back into a message.
    foreach ($required in @($pythonw, $launcher)) {
        if (-not (Test-Path $required)) {
            throw ("Cannot create the '$Target' shortcut: $required is missing. " +
                   "The installed copy of LabLink is missing files the shortcuts " +
                   "need; re-run the installer against a complete checkout.")
        }
    }

    $WScriptShell = New-Object -ComObject WScript.Shell
    $shortcut = $WScriptShell.CreateShortcut($Path)
    $shortcut.TargetPath = $pythonw
    $shortcut.Arguments = "`"$launcher`" $Target"
    $shortcut.WorkingDirectory = $LablinkDir
    $shortcut.Description = $Description
    $shortcut.IconLocation = "$LablinkDir\images\icon.ico"
    $shortcut.Save()
}

function Create-DesktopShortcut {
    if (-not $CreateDesktopShortcut) {
        return
    }

    Write-Step "Creating desktop shortcut..."

    $desktopPath = [Environment]::GetFolderPath("Desktop")
    New-LabLinkShortcut -Path "$desktopPath\LabLink.lnk" -Target "client" `
        -Description "LabLink - Laboratory Equipment Control"

    Write-Step "Desktop shortcut created"
}

function Create-StartMenuShortcut {
    if (-not $CreateStartMenuShortcut) {
        return
    }

    Write-Step "Creating Start Menu shortcuts..."

    # A folder rather than three loose entries, so the Start Menu shows one
    # "LabLink" group holding the client, the launcher and the server.
    $startMenuPath = [Environment]::GetFolderPath("Programs")
    $folder = "$startMenuPath\LabLink"
    if (-not (Test-Path $folder)) {
        New-Item -ItemType Directory -Path $folder -Force | Out-Null
    }

    # The client is what a lab user wants; it is named plainly so it is what
    # they find when they type "lablink".
    New-LabLinkShortcut -Path "$folder\LabLink.lnk" -Target "client" `
        -Description "LabLink - Laboratory Equipment Control"

    # The launcher checks the installation and repairs dependencies. It is
    # where the error message box sends people when something is wrong.
    New-LabLinkShortcut -Path "$folder\LabLink Launcher.lnk" -Target "launcher" `
        -Description "LabLink Launcher - environment checks and repair"

    # Running the server on this machine rather than on a Pi.
    New-LabLinkShortcut -Path "$folder\LabLink Server.lnk" -Target "server" `
        -Description "LabLink Server - run the API server on this machine"

    Write-Step "Start Menu shortcuts created (client, launcher, server)"
}

function Write-Success {
    Write-Host ""
    Write-Host "╔═══════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║                                                       ║" -ForegroundColor Green
    Write-Host "║        LabLink Client Installed Successfully!        ║" -ForegroundColor Green
    Write-Host "║                                                       ║" -ForegroundColor Green
    Write-Host "╚═══════════════════════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""

    Write-Host "Installation Directory: $LablinkDir"
    Write-Host ""
    Write-Host "Start Menu -> LabLink:"
    Write-Host "  LabLink            the client. This is the one to use."
    Write-Host "  LabLink Launcher   environment checks and dependency repair"
    Write-Host "  LabLink Server     run the API server on this machine"
    Write-Host ""
    Write-Host "The desktop shortcut opens the client."
    Write-Host "None of them open a console window."
    Write-Host ""
    Write-Host "If a shortcut appears to do nothing, open 'LabLink Launcher':"
    Write-Host "it checks the installation and can repair it. Startup errors"
    Write-Host "are also logged to $env:LOCALAPPDATA\LabLink\launch.log"
    Write-Host ""
    Write-Host "To remove LabLink: $LablinkDir\uninstall-client.bat"
    Write-Host ""
    Write-Host "For help and documentation: https://docs.lablink.io"
    Write-Host ""
}

# Main installation flow
function Main {
    Write-Header

    # Check if running as administrator
    if (Test-Administrator) {
        Write-WarningMsg "Running as Administrator. This is not required."
    }

    # Prompt for installation options
    $response = Read-Host "Installation directory [$LablinkDir]"
    if ($response) {
        $LablinkDir = $response
    }

    $response = Read-Host "Create desktop shortcut? (Y/n)"
    if ($response -eq 'n' -or $response -eq 'N') {
        $CreateDesktopShortcut = $false
    }

    Write-Host ""

    # Check Python
    Write-Step "Checking Python installation..."
    $pythonVersion = Get-PythonVersion

    if ($null -eq $pythonVersion) {
        Install-Python
        $pythonVersion = Get-PythonVersion
    }
    elseif ($pythonVersion -lt $PythonMinVersion) {
        Write-WarningMsg "Python version $pythonVersion is too old (need >= $PythonMinVersion)"
        Install-Python
        $pythonVersion = Get-PythonVersion
    }
    else {
        Write-Step "Python $pythonVersion found"
    }

    # Check Git (optional, but helpful)
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        $response = Read-Host "Git not found. Install Git for easier updates? (Y/n)"
        if ($response -ne 'n' -and $response -ne 'N') {
            Install-Git
        }
    }

    Download-LabLink
    Install-ClientDependencies
    Create-LauncherScript
    Create-DesktopShortcut
    Create-StartMenuShortcut

    Write-Success
}

# Run main installation
try {
    Main
}
catch {
    Write-ErrorMsg "Installation failed: $_"
    Write-Host $_.ScriptStackTrace
    exit 1
}
