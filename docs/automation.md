# Automation Architecture

Life Agent is designed to run autonomously without manual intervention. It can be scheduled using either local OS schedulers (like Windows Task Scheduler/cron) or cloud CI/CD pipelines (like GitHub Actions).

## Option A: GitHub Actions (Recommended)

The easiest way to run Life Agent continuously is via GitHub Actions.

1. Ensure your repository is **Private**.
2. Go to `Settings -> Secrets and variables -> Actions`.
3. Add your repository secrets (`ANTHROPIC_API_KEY`, `NOTION_TOKEN`, etc.).
4. The `.github/workflows/agent.yml` file is already configured with the standard daily schedule:
   - Morning Planning (e.g., 08:00)
   - Evening Check-in (e.g., 21:00)
   - Deep Work Reminders

## Option B: Local OS Scheduler

If you prefer to keep all execution on a local machine (e.g., a home server or always-on laptop), you can use the provided batch scripts.

1. Configure `.env` locally.
2. Use Windows Task Scheduler or Linux `cron` to trigger the agent.
3. Example cron expression for the evening check-in:
   ```bash
   0 21 * * * cd /path/to/life-agent && python -m life_agent.agent.main evening_checkin
   ```

*(See `run_daily.bat` and `run_task.bat` for Windows wrapper scripts).*
