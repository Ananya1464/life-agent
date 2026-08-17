@echo off
REM Daily automation wrapper for life-agent
REM This script:
REM   1. Loads .env file for secrets
REM   2. Activates the Python venv
REM   3. Runs all 4 daily tasks in order
REM   4. Logs output to logs/daily_YYYY-MM-DD.log

setlocal enabledelayedexpansion

cd /d %~dp0
set PYTHONIOENCODING=utf-8

REM Create logs directory if it doesn't exist
if not exist logs mkdir logs

REM Set timestamp for log file
for /f "tokens=2-4 delims=/ " %%a in ('date /t') do (set mydate=%%c-%%a-%%b)
for /f "tokens=1-2 delims=/:" %%a in ('time /t') do (set mytime=%%a%%b)
set LOGFILE=logs\daily_%mydate%.log

REM Load .env file (simple parser for KEY=VALUE lines)
if exist .env (
    echo [%date% %time%] Loading .env file... >> %LOGFILE%
    for /f "tokens=*" %%a in ('type .env ^| findstr /v "^REM" ^| findstr /v "^#"') do (
        set "%%a"
        echo [%date% %time%] Set: %%a >> %LOGFILE%
    )
) else (
    echo [%date% %time%] WARNING: .env file not found. Using system environment variables only. >> %LOGFILE%
)

REM Activate venv
if not exist .venv\Scripts\activate.bat (
    echo [%date% %time%] ERROR: Virtual environment not found. Run: python -m venv .venv >> %LOGFILE%
    exit /b 1
)

echo [%date% %time%] ========== Starting daily agent run ========== >> %LOGFILE%

call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [%date% %time%] ERROR: Failed to activate venv >> %LOGFILE%
    exit /b 1
)

REM Run all 4 tasks in order
echo [%date% %time%] Task 1/4: meal_plan >> %LOGFILE%
python -m life_agent.agent.main meal_plan >> %LOGFILE% 2>&1
if errorlevel 1 echo [%date% %time%] WARNING: meal_plan failed >> %LOGFILE%

echo [%date% %time%] Task 2/4: ai_edge >> %LOGFILE%
python -m life_agent.agent.main ai_edge >> %LOGFILE% 2>&1
if errorlevel 1 echo [%date% %time%] WARNING: ai_edge failed >> %LOGFILE%

echo [%date% %time%] Task 3/4: evening_checkin >> %LOGFILE%
python -m life_agent.agent.main evening_checkin >> %LOGFILE% 2>&1
if errorlevel 1 echo [%date% %time%] WARNING: evening_checkin failed >> %LOGFILE%

echo [%date% %time%] Task 4/4: tomorrow_planner >> %LOGFILE%
python -m life_agent.agent.main tomorrow_planner >> %LOGFILE% 2>&1
if errorlevel 1 echo [%date% %time%] WARNING: tomorrow_planner failed >> %LOGFILE%

echo [%date% %time%] ========== Daily run complete ========== >> %LOGFILE%
exit /b 0
