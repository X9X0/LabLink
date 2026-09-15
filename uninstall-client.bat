@echo off
REM LabLink Client - Windows Uninstall Wrapper
REM Mirrors install-client.bat: runs the PowerShell uninstaller with the
REM execution policy bypassed, so a user only has to double-click this file.

echo.
echo ========================================
echo  LabLink Client Uninstall
echo ========================================
echo.

if not exist "%~dp0uninstall-client.ps1" (
    echo ERROR: uninstall-client.ps1 not found!
    echo Please make sure you're running this from the LabLink directory.
    echo.
    pause
    exit /b 1
)

REM %* forwards the script's switches, so -RemoveSettings and -Force still
REM work when this wrapper is called from a shell rather than double-clicked.
powershell -ExecutionPolicy Bypass -File "%~dp0uninstall-client.ps1" %*

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo  Uninstall Complete
    echo ========================================
    echo.
) else (
    echo.
    echo ========================================
    echo  Uninstall Failed
    echo ========================================
    echo.
    echo Please check the error messages above.
    echo.
)

pause
