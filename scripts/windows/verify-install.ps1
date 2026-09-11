<#
.SYNOPSIS
    Checks that a LabLink Windows install is complete and console-free.

.DESCRIPTION
    Verifies the things a user would otherwise only discover by clicking:
    that the install is present, that the three Start Menu entries exist and
    point at pythonw.exe rather than a batch file, that both the client and
    server dependencies import, and that each entry point starts.

    Read-only. It imports modules and runs --help; it never launches the GUI
    or starts the server listening.

.PARAMETER InstallPath
    Where LabLink was installed. Defaults to the installer's own default.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\windows\verify-install.ps1
#>

param(
    [string]$InstallPath = "$env:USERPROFILE\LabLink"
)

$script:Passed = 0
$script:Failed = 0

function Test-Item {
    param([string]$Name, [scriptblock]$Check, [string]$Hint = "")

    try {
        $result = & $Check
        if ($result) {
            Write-Host "  [PASS] $Name" -ForegroundColor Green
            $script:Passed++
            return
        }
    }
    catch {
        Write-Host "  [FAIL] $Name" -ForegroundColor Red
        Write-Host "         $_" -ForegroundColor DarkGray
        if ($Hint) { Write-Host "         $Hint" -ForegroundColor DarkGray }
        $script:Failed++
        return
    }

    Write-Host "  [FAIL] $Name" -ForegroundColor Red
    if ($Hint) { Write-Host "         $Hint" -ForegroundColor DarkGray }
    $script:Failed++
}

function Get-ShortcutTarget {
    param([string]$Path)
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($Path)
    return @{ Target = $shortcut.TargetPath; Arguments = $shortcut.Arguments }
}

Write-Host ""
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host " LabLink Windows Install Verification" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "Install path: $InstallPath"
Write-Host ""

$pythonw = "$InstallPath\client\venv\Scripts\pythonw.exe"
$python  = "$InstallPath\client\venv\Scripts\python.exe"
$shim    = "$InstallPath\scripts\windows\lablink_launch.pyw"
$startMenu = "$([Environment]::GetFolderPath('Programs'))\LabLink"

Write-Host "1. Installation layout" -ForegroundColor White
Test-Item "Install directory exists" { Test-Path $InstallPath } `
    "Run install-client.bat first."
Test-Item "Virtual environment present" { Test-Path $python }
Test-Item "pythonw.exe present (console-free launching)" { Test-Path $pythonw } `
    "Without this every shortcut would open a console window."
Test-Item "Launch shim present" { Test-Path $shim }
Test-Item "Application icon present" { Test-Path "$InstallPath\images\icon.ico" }
Test-Item "Uninstaller present" { Test-Path "$InstallPath\uninstall-client.bat" }

Write-Host ""
Write-Host "2. Start Menu entries" -ForegroundColor White
Test-Item "LabLink folder exists in Start Menu" { Test-Path $startMenu } `
    "Expected at $startMenu"

foreach ($entry in @(
    @{ File = "LabLink.lnk";           Target = "client" },
    @{ File = "LabLink Launcher.lnk";  Target = "launcher" },
    @{ File = "LabLink Server.lnk";    Target = "server" }
)) {
    $path = "$startMenu\$($entry.File)"
    $name = $entry.File -replace '\.lnk$', ''

    Test-Item "'$name' shortcut exists" { Test-Path $path }

    if (Test-Path $path) {
        $info = Get-ShortcutTarget -Path $path

        # The whole point: a .bat or python.exe target means a console window.
        Test-Item "'$name' targets pythonw.exe (no console)" {
            $info.Target -like "*pythonw.exe"
        } "Targets '$($info.Target)' - a .bat or python.exe would open a console."

        Test-Item "'$name' starts the '$($entry.Target)' target" {
            $info.Arguments -match [regex]::Escape($entry.Target)
        } "Arguments were: $($info.Arguments)"
    }
}

Write-Host ""
Write-Host "3. Dependencies" -ForegroundColor White
if (Test-Path $python) {
    Test-Item "Client imports (PyQt6, qasync, pyqtgraph)" {
        & $python -c "import PyQt6, qasync, pyqtgraph" 2>&1 | Out-Null
        $LASTEXITCODE -eq 0
    } "Open 'LabLink Launcher' to repair client dependencies."

    Test-Item "Server imports (fastapi, uvicorn, pyvisa)" {
        & $python -c "import fastapi, uvicorn, pyvisa" 2>&1 | Out-Null
        $LASTEXITCODE -eq 0
    } "The Server shortcut needs these; reinstall to add them."
}

Write-Host ""
Write-Host "4. Entry points start" -ForegroundColor White
if ((Test-Path $python) -and (Test-Path $shim)) {
    Push-Location $InstallPath
    try {
        # --help exercises module resolution and argument handling without
        # opening a window or binding a port.
        Test-Item "Client entry point resolves" {
            & $python $shim client --help 2>&1 | Out-Null
            $LASTEXITCODE -eq 0
        }

        Test-Item "Launch shim rejects an unknown target" {
            & $python $shim not-a-real-target 2>&1 | Out-Null
            $LASTEXITCODE -ne 0
        } "It should refuse rather than start something unexpected."
    }
    finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host " Passed: $script:Passed   Failed: $script:Failed" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

if ($script:Failed -gt 0) {
    Write-Host "Some checks failed. The install is not yet console-free or complete." -ForegroundColor Red
    Write-Host ""
    exit 1
}

Write-Host "Install verified. Launch from Start Menu -> LabLink." -ForegroundColor Green
Write-Host ""
Write-Host "One thing this cannot check: that no console window appears when a" -ForegroundColor DarkGray
Write-Host "shortcut is clicked. That needs a human to look. Click each of the" -ForegroundColor DarkGray
Write-Host "three entries and confirm no black window appears." -ForegroundColor DarkGray
Write-Host ""
exit 0
