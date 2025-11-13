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
$PythonMinVersion = [Version]"3.8.0"

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
    Write-Step "Python not found or version too old. Installing Python 3.11..."

    $pythonInstallerUrl = "https://www.python.org/ftp/python/3.11.7/python-3.11.7-amd64.exe"
    $installerPath = "$env:TEMP\python-installer.exe"

    Write-Step "Downloading Python installer..."
    Invoke-WebRequest -Uri $pythonInstallerUrl -OutFile $installerPath

    Write-Step "Installing Python (this may take a few minutes)..."
    Start-Process -FilePath $installerPath -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_test=0" -Wait

    Remove-Item $installerPath

    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

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
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

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

    Write-Step "Dependencies installed"
}

function Create-LauncherScript {
    Write-Step "Creating launcher script..."

    $launcherPath = "$LablinkDir\lablink-client.bat"

    $batchContent = @"
@echo off
cd /d "%~dp0client"
call venv\Scripts\activate.bat
python main.py %*
"@

    Set-Content -Path $launcherPath -Value $batchContent

    Write-Step "Launcher script created: $launcherPath"
}

function Create-DesktopShortcut {
    if (-not $CreateDesktopShortcut) {
        return
    }

    Write-Step "Creating desktop shortcut..."

    $desktopPath = [Environment]::GetFolderPath("Desktop")
    $shortcutPath = "$desktopPath\LabLink.lnk"

    $WScriptShell = New-Object -ComObject WScript.Shell
    $shortcut = $WScriptShell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "$LablinkDir\lablink-client.bat"
    $shortcut.WorkingDirectory = $LablinkDir
    $shortcut.Description = "LabLink - Laboratory Equipment Control"
    #$shortcut.IconLocation = "$LablinkDir\client\resources\icon.ico"
    $shortcut.Save()

    Write-Step "Desktop shortcut created"
}

function Create-StartMenuShortcut {
    if (-not $CreateStartMenuShortcut) {
        return
    }

    Write-Step "Creating Start Menu shortcut..."

    $startMenuPath = [Environment]::GetFolderPath("Programs")
    $shortcutPath = "$startMenuPath\LabLink.lnk"

    $WScriptShell = New-Object -ComObject WScript.Shell
    $shortcut = $WScriptShell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "$LablinkDir\lablink-client.bat"
    $shortcut.WorkingDirectory = $LablinkDir
    $shortcut.Description = "LabLink - Laboratory Equipment Control"
    #$shortcut.IconLocation = "$LablinkDir\client\resources\icon.ico"
    $shortcut.Save()

    Write-Step "Start Menu shortcut created"
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
    Write-Host "To start LabLink Client:"
    Write-Host "  - Double-click the desktop shortcut"
    Write-Host "  - Or run: $LablinkDir\lablink-client.bat"
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
