<#
.SYNOPSIS
    Exercises install -> verify -> uninstall against a disposable directory.

.DESCRIPTION
    The installer and uninstaller are the two pieces that cannot be checked by
    reading them: one installs Python and clones a repository, the other
    deletes directories. That makes them exactly the things nobody wants to run
    against a real machine to find out whether they work.

    This runs the whole cycle somewhere disposable. It never touches
    %USERPROFILE%\LabLink, so the machine's real installation -- and any
    development checkout sharing that default path -- is left alone.

    Shortcuts need saying precisely, because an earlier version of this file
    made a promise it could not keep. The Start Menu and Desktop belong to the
    machine, not to any one installation, so -InstallPath cannot scope them by
    location: the uninstaller used to delete every LabLink shortcut it found,
    which meant a run against a throwaway directory removed the real install's
    entries on the way out. It now reads each shortcut's target and removes
    only those pointing into the directory it was given, so a cycle here
    leaves other installations' shortcuts alone.

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
#
# Compare resolved paths rather than the strings as typed: a trailing
# separator, different casing, or a relative spelling all name the same
# directory and would otherwise walk straight past the guard.
function Resolve-ForComparison {
    param([string]$Path)
    try {
        return [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    }
    catch {
        return $Path.TrimEnd('\', '/')
    }
}

$normalizedTest = Resolve-ForComparison $TestPath
foreach ($forbidden in @("$env:USERPROFILE\LabLink", $repoRoot)) {
    if ($normalizedTest -eq (Resolve-ForComparison $forbidden)) {
        Write-Host "Refusing to run against $TestPath - that is a real location." -ForegroundColor Red
        Write-Host "Pass -TestPath somewhere disposable." -ForegroundColor Red
        exit 2
    }
}

# Walk up to the drive root, not just the directory itself: a subdirectory of a
# checkout is still inside somebody's working tree, and deleting it takes their
# files with it.
$ancestor = $normalizedTest
while ($ancestor) {
    if (Test-Path (Join-Path $ancestor ".git")) {
        Write-Host "Refusing: $TestPath is inside the git checkout at $ancestor." -ForegroundColor Red
        Write-Host "This script deletes what it creates; point it somewhere empty." -ForegroundColor Red
        exit 2
    }
    $parent = Split-Path $ancestor -Parent
    if (-not $parent -or $parent -eq $ancestor) { break }
    $ancestor = $parent
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
