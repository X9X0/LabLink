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
    [switch]$Force
)

$ErrorActionPreference = "Stop"

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
Write-Host "Python and Git are left installed." -ForegroundColor DarkGray
if (-not $RemoveSettings) {
    Write-Host "Saved credentials are kept. Use -RemoveSettings to clear them." -ForegroundColor DarkGray
}
Write-Host ""

if (-not $Force) {
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
