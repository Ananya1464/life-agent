@echo off
REM Double-click launcher for OmniRoute.
REM Your own commands (and API key) live in omniroute_commands.local.bat, which is gitignored.
title OmniRoute
cd /d "%~dp0"
if not exist omniroute_commands.local.bat (
    echo Missing omniroute_commands.local.bat - create it and paste your OmniRoute commands in it.
    pause
    exit /b 1
)
call omniroute_commands.local.bat
echo.
echo OmniRoute stopped or exited. Press any key to close.
pause >nul
