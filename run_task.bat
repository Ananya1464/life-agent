@echo off
REM Run ONE life-agent task:  run_task.bat <task_name>
REM Used by the Windows scheduled tasks (one per time slot).
REM .env is auto-loaded by config.py, so no env parsing needed here.

cd /d %~dp0
if not exist logs mkdir logs

for /f "tokens=2-4 delims=/ " %%a in ('date /t') do (set mydate=%%c-%%a-%%b)
set LOGFILE=logs\daily_%mydate%.log

if "%~1"=="" (
    echo [%date% %time%] ERROR: no task name given >> %LOGFILE%
    exit /b 1
)

echo [%date% %time%] ===== Running task: %1 ===== >> %LOGFILE%
.venv\Scripts\python.exe -m life_agent.agent.main %1 >> %LOGFILE% 2>&1
if errorlevel 1 (
    echo [%date% %time%] WARNING: %1 failed >> %LOGFILE%
    exit /b 1
)
echo [%date% %time%] %1 done >> %LOGFILE%
exit /b 0
