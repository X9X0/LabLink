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
