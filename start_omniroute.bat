@echo off
REM Double-click launcher: starts OmniRoute, waits (retrying) until it is healthy, then runs the Desktop commands file.
REM The API key stays in that Desktop file; nothing secret lives in this repo.
title OmniRoute launcher
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0start_omniroute.ps1"
