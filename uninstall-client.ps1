<#
.SYNOPSIS
    Removes a LabLink client installation from this machine.

.DESCRIPTION
    Undoes what install-client.ps1 created: the install directory (including
    the virtual environment), the desktop shortcut, and the Start Menu folder.

    It deliberately does NOT remove Python or Git. The installer may have
    installed them, but other software may be relying on them by now, and a
    LabLink uninstaller is not the right place to decide that.

    Saved credentials are removed only when -RemoveSettings is given, because
    they are the one thing a reinstall cannot recreate.

.PARAMETER InstallPath
    Where LabLink was installed. Defaults to the installer's own default.

.PARAMETER RemoveSettings
    Also remove saved credentials, the Windows Credential Manager entry, and
    the crash log. Use this for a genuinely clean slate.

.PARAMETER Force
    Skip the confirmation prompt. Intended for scripted reinstall testing.

.EXAMPLE
    .\uninstall-client.ps1

.EXAMPLE
    .\uninstall-client.ps1 -RemoveSettings -Force
#>

param(
    [string]$InstallPath = "$env:USERPROFILE\LabLink",
    [switch]$RemoveSettings,
    [switch]$Force,
    # Set when this script has already copied itself to TEMP. Not for callers.
    [switch]$Relocated
)

$ErrorActionPreference = "Stop"

#: Set when the install directory is a git checkout with uncommitted work.
$script:TreeIsDirty = $false

# Windows will not remove a directory that a running process is sitting in, and
# this script normally lives inside the directory it is about to delete. Rather
# than asking the user to copy files out -- which fails anyway, because the .bat
# wrapper resolves the .ps1 relative to itself -- relocate to TEMP and re-run
# from there. -Relocated stops that recursing.
if (-not $Relocated) {
    $scriptPath = $MyInvocation.MyCommand.Path
    if ($scriptPath -and $scriptPath.StartsWith($InstallPath, [StringComparison]::OrdinalIgnoreCase)) {
        $tempCopy = Join-Path $env:TEMP "lablink-uninstall-$PID.ps1"
        Copy-Item -Path $scriptPath -Destination $tempCopy -Force

        $forward = @("-InstallPath", $InstallPath, "-Relocated")
        if ($RemoveSettings) { $forward += "-RemoveSettings" }
        if ($Force)          { $forward += "-Force" }

        try {
            & powershell -ExecutionPolicy Bypass -File $tempCopy @forward
            $code = $LASTEXITCODE
        }
        finally {
            # Best effort: the copy is in TEMP either way.
            Remove-Item -Path $tempCopy -Force -ErrorAction SilentlyContinue
        }
        exit $code
    }
}

function Write-Step    { param($m) Write-Host "[*] $m" -ForegroundColor Cyan }
function Write-Removed { param($m) Write-Host "[-] $m" -ForegroundColor Yellow }
function Write-Skipped { param($m) Write-Host "[ ] $m" -ForegroundColor DarkGray }
function Write-ErrorMsg { param($m) Write-Host "[!] $m" -ForegroundColor Red }

function Remove-IfPresent {
    param([string]$Path, [string]$Label)

    if (Test-Path $Path) {
        try {
            Remove-Item -Path $Path -Recurse -Force
            Write-Removed "$Label  ($Path)"
            return $true
        }
        catch {
            # Most often a running LabLink still holds the directory open.
            Write-ErrorMsg "Could not remove $Label : $_"
            Write-ErrorMsg "Close LabLink if it is running, then run this again."
            return $false
        }
    }

    Write-Skipped "$Label not present"
    return $true
}

Write-Host ""
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host " LabLink Client Uninstall" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

$startMenuFolder = "$([Environment]::GetFolderPath('Programs'))\LabLink"
$desktopShortcut = "$([Environment]::GetFolderPath('Desktop'))\LabLink.lnk"
# Installs from before the Start Menu folder existed left a loose entry.
$legacyStartMenu = "$([Environment]::GetFolderPath('Programs'))\LabLink.lnk"

Write-Host "This will remove:"
Write-Host "  - Install directory : $InstallPath"
Write-Host "  - Start Menu folder : $startMenuFolder"
Write-Host "  - Desktop shortcut  : $desktopShortcut"
if ($RemoveSettings) {
    Write-Host "  - Saved settings and credentials" -ForegroundColor Yellow
}
Write-Host ""

# An install directory that is also a git checkout is somebody's working copy,
# and deleting it takes uncommitted work and local data with it: measurements
# under data/, saved profiles/, logs/, config. The installer creates the
# directory by cloning, so this is the normal case on a development machine
# rather than an edge case -- and nothing about "uninstall the client" tells
# the user their measurements are inside it.
if (Test-Path (Join-Path $InstallPath ".git")) {
    Write-Host "WARNING: $InstallPath is a git repository." -ForegroundColor Yellow

    Push-Location $InstallPath
    try {
        $dirty = git status --porcelain 2>$null
        if ($dirty) {
            $script:TreeIsDirty = $true
            $count = ($dirty | Measure-Object -Line).Lines
            Write-Host "         It has $count uncommitted or untracked item(s)," -ForegroundColor Yellow
            Write-Host "         which removing the directory would destroy:" -ForegroundColor Yellow
            $dirty | Select-Object -First 12 | ForEach-Object {
                Write-Host "           $_" -ForegroundColor DarkGray
            }
            if ($count -gt 12) {
                Write-Host "           ... and $($count - 12) more" -ForegroundColor DarkGray
            }
            Write-Host "         Commit or copy anything you need first." -ForegroundColor Yellow
        } else {
            Write-Host "         The working tree is clean." -ForegroundColor DarkGray
        }
    }
    catch {
        Write-Host "         (Could not inspect it: $_)" -ForegroundColor DarkGray
    }
    finally {
        Pop-Location
    }
    Write-Host ""
}

Write-Host "Python and Git are left installed." -ForegroundColor DarkGray
if (-not $RemoveSettings) {
    Write-Host "Saved credentials are kept. Use -RemoveSettings to clear them." -ForegroundColor DarkGray
}
Write-Host ""

# -Force means "do not ask the routine question", not "destroy uncommitted work
# without telling anyone". A dirty tree is the one case where the answer might
# genuinely have been no, so it stops even under -Force.
if ($script:TreeIsDirty -and $Force) {
    Write-ErrorMsg "Refusing to run with -Force: $InstallPath has uncommitted work."
    Write-Host ""
    Write-Host "Commit or copy what you need, then either:" -ForegroundColor Yellow
    Write-Host "  - re-run without -Force, to confirm interactively, or" -ForegroundColor Yellow
    Write-Host "  - re-run once the working tree is clean." -ForegroundColor Yellow
    Write-Host ""
    exit 2
}

if (-not $Force) {
    if ($script:TreeIsDirty) {
        Write-Host "This will destroy the uncommitted work listed above." -ForegroundColor Yellow
    }
    $response = Read-Host "Continue? (y/N)"
    if ($response -ne 'y' -and $response -ne 'Y') {
        Write-Host "Cancelled. Nothing was removed." -ForegroundColor Yellow
        exit 0
    }
    Write-Host ""
}

$allOk = $true

Write-Step "Removing shortcuts..."
if (-not (Remove-IfPresent -Path $startMenuFolder -Label "Start Menu folder")) { $allOk = $false }
if (-not (Remove-IfPresent -Path $desktopShortcut -Label "Desktop shortcut"))  { $allOk = $false }
if (-not (Remove-IfPresent -Path $legacyStartMenu -Label "Legacy Start Menu shortcut")) { $allOk = $false }

Write-Step "Removing install directory..."
# Running from inside the directory about to be deleted would fail on Windows,
# which will not remove the current working directory of a live process.
if ((Get-Location).Path.StartsWith($InstallPath, [StringComparison]::OrdinalIgnoreCase)) {
    Set-Location $env:USERPROFILE
}
if (-not (Remove-IfPresent -Path $InstallPath -Label "Install directory")) { $allOk = $false }

if ($RemoveSettings) {
    Write-Step "Removing settings and credentials..."

    # QSettings writes under HKCU; the client falls back to it when the
    # Windows Credential Manager is unavailable.
    $registryKey = "HKCU:\Software\LabLink"
    if (Test-Path $registryKey) {
        Remove-Item -Path $registryKey -Recurse -Force
        Write-Removed "Registry settings  ($registryKey)"
    } else {
        Write-Skipped "Registry settings not present"
    }

    Remove-IfPresent -Path "$env:LOCALAPPDATA\LabLink" -Label "Local application data" | Out-Null

    # Tokens stored through keyring land in the Windows Credential Manager.
    try {
        $stored = cmdkey /list 2>$null | Select-String -Pattern "LabLink"
        if ($stored) {
            Write-Host "    Credential Manager still holds LabLink entries:" -ForegroundColor Yellow
            $stored | ForEach-Object { Write-Host "      $_" -ForegroundColor DarkGray }
            Write-Host "    Remove them with:  cmdkey /delete:<target>" -ForegroundColor DarkGray
        } else {
            Write-Skipped "No Credential Manager entries"
        }
    }
    catch {
        Write-Skipped "Could not query Credential Manager"
    }
}

Write-Host ""
if ($allOk) {
    Write-Host "===============================================" -ForegroundColor Green
    Write-Host " LabLink has been removed." -ForegroundColor Green
    Write-Host "===============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "To reinstall, run install-client.bat from a fresh copy." -ForegroundColor DarkGray
    Write-Host ""
    exit 0
}

Write-Host "===============================================" -ForegroundColor Red
Write-Host " Uninstall finished with errors (see above)." -ForegroundColor Red
Write-Host "===============================================" -ForegroundColor Red
Write-Host ""
exit 1
