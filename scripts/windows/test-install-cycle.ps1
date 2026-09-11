<#
.SYNOPSIS
    Exercises install -> verify -> uninstall against a disposable directory.

.DESCRIPTION
    The installer and uninstaller are the two pieces that cannot be checked by
    reading them: one installs Python and clones a repository, the other
    deletes directories. That makes them exactly the things nobody wants to run
    against a real machine to find out whether they work.

    This runs the whole cycle somewhere disposable. It never touches
    %USERPROFILE%\LabLink, and with -NoShortcuts it never touches the Start
    Menu, so the machine's real installation -- and any development checkout
    sharing that default path -- is left alone.

    What it cannot do is tell you whether a shortcut opens a console window.
    Nothing scriptable can. Use -KeepShortcuts and click them if you want that
    covered, and read scripts/windows/verify-install.ps1 for the rest.

.PARAMETER TestPath
    The disposable directory. Must not be an existing LabLink install.

.PARAMETER KeepShortcuts
    Create the desktop and Start Menu entries too, so the console check can be
    done by hand. They are removed again by the uninstall step.

.PARAMETER SkipUninstall
    Leave the test install in place, for poking at afterwards. Remove it with
    uninstall-client.ps1 -InstallPath <TestPath> when done.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\windows\test-install-cycle.ps1

.EXAMPLE
    .\scripts\windows\test-install-cycle.ps1 -TestPath D:\scratch\LabLink -KeepShortcuts
#>

param(
    [string]$TestPath = "$env:TEMP\LabLinkInstallTest",
    [switch]$KeepShortcuts,
    [switch]$SkipUninstall
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path

function Write-Phase {
    param($m)
    Write-Host ""
    Write-Host "=== $m ===" -ForegroundColor Cyan
}

# Refuse to point the cycle at anything that looks real. The whole value of
# this script is that it cannot damage a working installation, and the default
# install path is also where a development checkout tends to live.
$realInstall = "$env:USERPROFILE\LabLink"
if ($TestPath -eq $realInstall -or $TestPath -eq $repoRoot) {
    Write-Host "Refusing to run against $TestPath - that is a real location." -ForegroundColor Red
    Write-Host "Pass -TestPath somewhere disposable." -ForegroundColor Red
    exit 2
}
if (Test-Path (Join-Path $TestPath ".git")) {
    Write-Host "Refusing: $TestPath contains a git checkout." -ForegroundColor Red
    Write-Host "This script deletes what it creates; point it somewhere empty." -ForegroundColor Red
    exit 2
}

Write-Host ""
Write-Host "LabLink install cycle test" -ForegroundColor Cyan
Write-Host "  repo      : $repoRoot"
Write-Host "  test path : $TestPath"
Write-Host "  shortcuts : $(if ($KeepShortcuts) { 'created (click them to check for consoles)' } else { 'skipped' })"

$installArgs = @("-InstallPath", $TestPath, "-Unattended")
if (-not $KeepShortcuts) { $installArgs += "-NoShortcuts" }

Write-Phase "1/3  Install"
& powershell -ExecutionPolicy Bypass -File "$repoRoot\install-client.ps1" @installArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "Install failed (exit $LASTEXITCODE). Stopping here so the tree can be inspected." -ForegroundColor Red
    exit 1
}

Write-Phase "2/3  Verify"
& powershell -ExecutionPolicy Bypass -File "$repoRoot\scripts\windows\verify-install.ps1" -InstallPath $TestPath
$verifyCode = $LASTEXITCODE
# Not fatal on its own: without -KeepShortcuts the shortcut checks are expected
# to fail, because no shortcuts were asked for.
if ($verifyCode -ne 0 -and $KeepShortcuts) {
    Write-Host "Verification failed with shortcuts present - that is a real failure." -ForegroundColor Red
}

if ($SkipUninstall) {
    Write-Phase "3/3  Uninstall - SKIPPED"
    Write-Host "Test install left at $TestPath" -ForegroundColor Yellow
    Write-Host "Remove it with:" -ForegroundColor DarkGray
    Write-Host "  .\uninstall-client.ps1 -InstallPath `"$TestPath`" -Force" -ForegroundColor DarkGray
    exit $verifyCode
}

Write-Phase "3/3  Uninstall"
& powershell -ExecutionPolicy Bypass -File "$repoRoot\uninstall-client.ps1" -InstallPath $TestPath -Force
$uninstallCode = $LASTEXITCODE

Write-Phase "Result"
$leftover = Test-Path $TestPath
Write-Host "  install   : ok"
Write-Host "  verify    : exit $verifyCode$(if (-not $KeepShortcuts) { '  (shortcut checks expected to fail: -NoShortcuts)' })"
Write-Host "  uninstall : exit $uninstallCode"
Write-Host "  directory removed : $(-not $leftover)"

if ($uninstallCode -ne 0 -or $leftover) {
    Write-Host ""
    Write-Host "Uninstall did not fully clean up. $TestPath still exists." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Cycle completed against a disposable directory." -ForegroundColor Green
if (-not $KeepShortcuts) {
    Write-Host "Shortcuts were not created, so the console check is still outstanding." -ForegroundColor DarkGray
    Write-Host "Re-run with -KeepShortcuts to cover it." -ForegroundColor DarkGray
}
Write-Host ""
exit 0
