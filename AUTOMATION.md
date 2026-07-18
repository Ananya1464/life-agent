# Windows Daily Automation Setup

This guide sets up the life-agent to run automatically every day using Windows Task Scheduler.

## Prerequisites

1. **Python venv created and dependencies installed:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. **Environment variables / secrets configured** (see below)

3. **Administrator access** (to create scheduled tasks)

## Step 1: Set up environment variables / secrets

### Option A: Using .env file (recommended for local testing)

1. Copy `.env.example` to `.env`:
   ```powershell
   Copy-Item .env.example .env
   ```

2. Edit `.env` and fill in your secrets:
   - `NOTION_TOKEN` (required) — from https://www.notion.so/my-integrations
   - `ANTHROPIC_API_KEY` or `GEMINI_API_KEY` (one of the two)
   - `GMAIL_APP_PASSWORD` (optional) — for email delivery
   - `ICAL_URL` (optional) — for calendar integration

### Option B: Using Windows environment variables (more secure for production)

1. Open Windows Settings → Environment Variables
2. Click "New" (under User variables or System variables)
3. Add each variable from `.env.example` (e.g., `NOTION_TOKEN`, `ANTHROPIC_API_KEY`)
4. Restart your terminal/IDE for changes to take effect

**If using Option B**, delete or rename the `.env` file so it doesn't conflict.

## Step 2: Test the batch script manually

Run the batch file in Command Prompt to verify it works:

```powershell
.\.venv\Scripts\Activate.ps1
& ".\run_daily.bat"
```

Or in Command Prompt:
```cmd
.venv\Scripts\activate
run_daily.bat
```

Check the output:
- All 4 tasks should run and appear in `logs/daily_YYYY-MM-DD.log`
- Check Notion for updated entries
- Check email for any delivery confirmations

## Step 3: Create Windows Task Scheduler entry

Open PowerShell **as Administrator** and run:

```powershell
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
.\setup_scheduler.ps1
```

The script will:
- Create a task named `life-agent-daily`
- Schedule it to run daily at 09:00 AM (edit the `$StartTime` in the script to change this)
- Set it to run even when not logged in

## Step 4: Verify the scheduled task

### In PowerShell:
```powershell
Get-ScheduledTask -TaskName "life-agent-daily" | Select-Object -Property TaskName, State, NextRunTime
```

### Or in GUI:
1. Open Task Scheduler (search "Task Scheduler" in Windows)
2. Find "life-agent-daily" under Task Scheduler Library
3. Right-click → Properties to view/edit details

## Step 5: Test the scheduled task

Run it immediately (don't wait for tomorrow):

```powershell
Start-ScheduledTask -TaskName "life-agent-daily"
```

Then check the logs:
```powershell
Get-Content logs\daily_*.log -Tail 20
```

## Troubleshooting

### Task doesn't run at scheduled time
- **Cause**: Computer was off or locked at trigger time (default is "wake up if sleeping")
- **Solution**: Edit the task in Task Scheduler → Triggers → check "Start task only if the computer is on AC power" is unchecked, and "Allow task to be run on demand" is checked

### "python" not found when task runs
- **Cause**: The venv may not have been activated; the full Python path should be used
- **Solution**: In `run_daily.bat`, change `python` to the full venv path:
  ```batch
  %CD%\.venv\Scripts\python.exe main.py meal_plan
  ```

### Secrets not loading from .env
- **Cause**: The batch parser is simple and may not handle all special characters
- **Solution**: Use Windows environment variables (Option B above) instead

### Task runs but produces no output / logs
- **Cause**: The `logs/` folder wasn't created
- **Solution**: Manually create `logs/` folder:
  ```powershell
  New-Item -ItemType Directory -Path logs -Force
  ```

## Advanced: Modifying run times

The default `.env.example` shows IST times (7 AM, 8 AM, 9:30 PM, 10 PM).

To change Task Scheduler time, edit `setup_scheduler.ps1` and change the `$StartTime` variable, then re-run it:

```powershell
$StartTime = "19:30"  # 7:30 PM
.\setup_scheduler.ps1
```

To run tasks individually at different times, create multiple tasks (e.g., `life-agent-meal-plan`, `life-agent-ai-edge`) with different triggers and modify the batch file accordingly.

## Optional: Delete the scheduled task

```powershell
Unregister-ScheduledTask -TaskName "life-agent-daily" -Confirm:$false
```

## Logs

Daily logs are saved to:
```
logs/daily_YYYY-MM-DD.log
```

Each entry shows:
- Timestamp
- Task name (1/4, 2/4, etc.)
- Any errors or warnings
- Success indicator

View recent logs:
```powershell
Get-ChildItem logs\ -Name | Sort-Object -Descending | Select-Object -First 5
Get-Content logs\daily_*.log -Tail 50  # Last 50 lines of latest log
```
