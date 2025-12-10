@echo off
cd /d "%~dp0"
set PYTHONPATH=%~dp0
call "client\venv\Scripts\activate.bat"
python "client\main.py" %*
