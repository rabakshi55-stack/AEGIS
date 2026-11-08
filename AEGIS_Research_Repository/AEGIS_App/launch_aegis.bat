@echo off
setlocal
set "PYTHONUTF8=1"
title AEGIS - Local Research Application
cd /d "%~dp0"
echo.
echo Starting AEGIS on this computer...
echo No external hosting. No automatic procurement.
echo.
python desktop.py
if errorlevel 1 (
    echo.
    echo Unable to start with 'python'. Trying the Windows Python launcher...
    py -3 desktop.py
    if errorlevel 1 (
        echo.
        echo AEGIS could not start. Check that Python is installed.
        pause
    )
)
