@echo off
REM LabLink Client - Windows Installation Wrapper
REM This batch file makes it easier to run the PowerShell installation script
REM by automatically handling the execution policy.

echo.
echo ========================================
echo  LabLink Client Installation
echo ========================================
echo.
echo Starting installation...
echo.

REM Check if install-client.ps1 exists
if not exist "%~dp0install-client.ps1" (
    echo ERROR: install-client.ps1 not found!
    echo Please make sure you're running this from the LabLink directory.
    echo.
    pause
    exit /b 1
)

REM Run the PowerShell script with execution policy bypass
powershell -ExecutionPolicy Bypass -File "%~dp0install-client.ps1"

REM Check if installation succeeded
if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo  Installation Complete!
    echo ========================================
    echo.
) else (
    echo.
    echo ========================================
    echo  Installation Failed
    echo ========================================
    echo.
    echo Please check the error messages above.
    echo.
)

pause
