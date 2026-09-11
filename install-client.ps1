# LabLink GUI Client - Windows Installation Script
# PowerShell Script for Windows 10/11
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File install-client.ps1
#   OR
#   iwr -useb https://raw.githubusercontent.com/X9X0/LabLink/main/install-client.ps1 | iex

# Requires -Version 5.1

<#
.SYNOPSIS
    Installs the LabLink client on Windows.

.DESCRIPTION
    Installs Python and Git if missing, fetches LabLink, builds a virtual
    environment with the client and server dependencies, and creates a desktop
    shortcut plus a Start Menu folder holding the client, launcher and server.

    Run with no arguments for the interactive install. The parameters exist so
    the whole thing can be exercised against a throwaway directory: pointing
    -InstallPath somewhere disposable means a test never goes near a real
    install -- or near a development checkout that happens to share the default
    location.

.PARAMETER InstallPath
    Where to install. Skips the interactive prompt when given.

.PARAMETER NoShortcuts
    Create no desktop or Start Menu shortcuts. For testing the install itself
    without touching the user's Start Menu.

.PARAMETER NoDesktopShortcut
    Create the Start Menu entries but no desktop shortcut.

.PARAMETER Unattended
    Ask nothing. Takes the default for every prompt, including installing Git
    when it is missing. Implies the answers, not the shortcuts: combine with
    -NoShortcuts to leave the Start Menu alone.

.PARAMETER ReplaceExistingShortcuts
    Take over shortcuts that point at a different LabLink installation. Without
    this, the install stops rather than overwriting them -- the Desktop and
    Start Menu are machine-wide, so an install pointed somewhere harmless can
    still clobber a real installation's entries.

.EXAMPLE
    .\install-client.ps1

.EXAMPLE
    # A disposable install, asking nothing and leaving the Start Menu alone
    .\install-client.ps1 -InstallPath C:\LabLinkTest -NoShortcuts -Unattended
#>

param(
    [string]$InstallPath,
    [switch]$NoShortcuts,
    [switch]$NoDesktopShortcut,
    [switch]$Unattended,
    [switch]$ReplaceExistingShortcuts
)

# Configuration
$LablinkDir = if ($InstallPath) { $InstallPath } else { "$env:USERPROFILE\LabLink" }
$CreateDesktopShortcut = -not ($NoShortcuts -or $NoDesktopShortcut)
$CreateStartMenuShortcut = -not $NoShortcuts
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

function Invoke-Checked {
    <#
    Fail when the last external command failed.

    There was not a single exit-code check in this script. pip would fail to
    resolve a package, print ERROR, and the next line would announce
    "dependencies installed" -- so an install where nothing installed reported
    success and exited 0. A user told the install worked is worse off than one
    told it failed.
    #>
    param([string]$What)

    if ($LASTEXITCODE -ne 0) {
        throw "$What failed (exit code $LASTEXITCODE). See the output above."
    }
}

function Get-PythonVersion {
    param([string]$Exe = "python")

    try {
        $pythonVersion = & $Exe --version 2>&1
        if ($pythonVersion -match "Python (\d+\.\d+\.\d+)") {
            return [Version]$Matches[1]
        }
    }
    catch {
        return $null
    }
    return $null
}

function Find-SuitablePython {
    <#
    Locate an interpreter new enough to install with, by asking each candidate
    rather than trusting PATH order.

    PATH is not reliable here. A machine-wide Python shadows a per-user one,
    and the installer places its own per-user: it was possible to install 3.12,
    report success, and then build the virtual environment with the 3.10 that
    was still first on PATH -- which is how an install came to declare success
    over a tree whose client could not import.

    Returns the path to a suitable interpreter, or $null.
    #>
    $candidates = @()

    # Where this script's own Install-Python puts it, checked first because it
    # is the one we most recently guaranteed.
    $candidates += "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"

    # The launcher reports interpreters properly, newest first.
    try {
        $listed = & py -0p 2>$null
        foreach ($line in $listed) {
            if ($line -match "([A-Za-z]:\\[^\s].*python\.exe)") {
                $candidates += $Matches[1]
            }
        }
    }
    catch { }

    # Whatever PATH offers, last rather than first.
    try {
        $onPath = (Get-Command python -ErrorAction SilentlyContinue).Source
        if ($onPath) { $candidates += $onPath }
    }
    catch { }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not (Test-Path $candidate)) { continue }
        $version = Get-PythonVersion -Exe $candidate
        if ($version -and $version -ge $PythonMinVersion) {
            return $candidate
        }
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

    # Refresh PATH, user entries FIRST. InstallAllUsers=0 puts Python under
    # %LOCALAPPDATA% and PrependPath=1 prepends it to the *user* path, so
    # putting Machine first lets an older machine-wide Python shadow the one
    # just installed. Callers should still prefer Find-SuitablePython, which
    # does not depend on PATH order at all.
    $env:Path = [System.Environment]::GetEnvironmentVariable('Path','User') + ';' + [System.Environment]::GetEnvironmentVariable('Path','Machine')

    Write-Step "Python installer finished"
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

    # Build the environment with the interpreter we verified, not with whatever
    # "python" resolves to. Those were not the same thing: a machine-wide 3.10
    # shadowed the 3.12 this script had just installed, and the venv inherited
    # the wrong one.
    if (-not (Test-Path "venv")) {
        & $script:PythonExe -m venv venv
        Invoke-Checked "Creating the virtual environment"
        Write-Step "Created Python virtual environment"
    }

    # Address the venv's own executables directly. Activate.ps1 edits PATH for
    # the process, which works, but naming them leaves nothing to resolve.
    $venvPython = "$LablinkDir\client\venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        throw "The virtual environment has no python.exe at $venvPython."
    }

    $venvVersion = Get-PythonVersion -Exe $venvPython
    if (-not $venvVersion -or $venvVersion -lt $PythonMinVersion) {
        throw ("The virtual environment was built with Python $venvVersion, but " +
               "$PythonMinVersion or newer is required. Delete " +
               "$LablinkDir\client\venv and re-run this script.")
    }
    Write-Step "Virtual environment uses Python $venvVersion"

    & $venvPython -m pip install --upgrade pip
    Invoke-Checked "Upgrading pip"

    & $venvPython -m pip install -r requirements.txt
    Invoke-Checked "Installing client dependencies"
    Write-Step "Client dependencies installed"

    # The Start Menu offers a Server entry, so the server's dependencies have
    # to be here too -- a shortcut that opens nothing is worse than no
    # shortcut. This is ~20 further packages (fastapi, uvicorn, pyvisa and so
    # on) on top of the client's.
    Write-Step "Installing server dependencies (for the Server shortcut)..."
    & $venvPython -m pip install -r "$LablinkDir\shared\requirements.txt"
    Invoke-Checked "Installing shared dependencies"

    & $venvPython -m pip install -r "$LablinkDir\server\requirements.txt"
    Invoke-Checked "Installing server dependencies"

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

    # The Desktop and Start Menu belong to the machine, not to this install, so
    # -InstallPath cannot scope where a shortcut is written. An install pointed
    # at a throwaway directory would still overwrite the real installation's
    # desktop shortcut, and the uninstall would then correctly remove it as its
    # own -- leaving the real install with no shortcut and nobody having been
    # told.
    #
    # A shortcut already pointing somewhere else therefore belongs to another
    # installation, and is not ours to replace silently.
    if ((Test-Path $Path) -and -not $ReplaceExistingShortcuts) {
        try {
            $existing = (New-Object -ComObject WScript.Shell).CreateShortcut($Path).TargetPath
        }
        catch {
            $existing = $null
        }

        if ($existing) {
            $normalizedExisting = [System.IO.Path]::GetFullPath($existing).TrimEnd('\')
            $normalizedRoot = [System.IO.Path]::GetFullPath($LablinkDir).TrimEnd('\')
            $belongsHere = $normalizedExisting.StartsWith(
                $normalizedRoot + [System.IO.Path]::DirectorySeparatorChar,
                [StringComparison]::OrdinalIgnoreCase)

            if (-not $belongsHere) {
                throw ("$Path already exists and points at $existing, which is " +
                       "outside $LablinkDir. It belongs to another LabLink " +
                       "installation. Re-run with -ReplaceExistingShortcuts to " +
                       "take it over, or with -NoShortcuts to leave it alone.")
            }
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

    # Prompt for installation options, unless they were supplied. A caller who
    # named a path or asked for no shortcuts has already answered; asking again
    # would make the switches useless for scripting.
    if (-not $InstallPath -and -not $Unattended) {
        $response = Read-Host "Installation directory [$LablinkDir]"
        if ($response) {
            $LablinkDir = $response
        }
    } else {
        Write-Step "Installing to $LablinkDir"
    }

    if (-not $NoShortcuts -and -not $NoDesktopShortcut -and -not $Unattended) {
        $response = Read-Host "Create desktop shortcut? (Y/n)"
        if ($response -eq 'n' -or $response -eq 'N') {
            $CreateDesktopShortcut = $false
        }
    }

    if ($NoShortcuts) {
        Write-Step "Shortcuts disabled (-NoShortcuts)"
    }

    Write-Host ""

    # Check Python. The result of installing it has to be checked: this used to
    # call Install-Python, re-read the version, assign it, and never compare it
    # -- so an install that changed nothing looked identical to one that
    # worked, and the venv was then built with the old interpreter.
    Write-Step "Checking Python installation..."
    $script:PythonExe = Find-SuitablePython

    if (-not $script:PythonExe) {
        Install-Python
        $script:PythonExe = Find-SuitablePython

        if (-not $script:PythonExe) {
            throw ("Python $PythonMinVersion or newer is still not available after " +
                   "installing it. If an older Python is installed machine-wide it " +
                   "may be taking precedence; install Python 3.12 manually and " +
                   "re-run this script.")
        }
    }

    $pythonVersion = Get-PythonVersion -Exe $script:PythonExe
    Write-Step "Using Python $pythonVersion  ($script:PythonExe)"

    # Check Git (optional, but helpful)
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        if ($Unattended) {
            # The default answer is yes, and an unattended run takes defaults.
            Install-Git
        } else {
            $response = Read-Host "Git not found. Install Git for easier updates? (Y/n)"
            if ($response -ne 'n' -and $response -ne 'N') {
                Install-Git
            }
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
