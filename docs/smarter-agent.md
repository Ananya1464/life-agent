# Smarter Agent

Smarter Agent adapts your plan size to your focus sessions (from Notion) and syncs focus data back to your "Life Agent Events" database, including a "Duration (sec)" column.

## Features
- **Adaptive Planning**: Adjusts workload based on recent focus patterns.
- **Notion Sync**: Syncs focus session data back to the "Life Agent Events" database.
- **Proactive Alerts**: Sends a notification when a scheduled task fails.
- **Lifebot Integration**: Pixel-art Crystal-cave themed UI for managing focus sessions, tasks, and reminders.

## Lifebot desktop app
`apps/lifebot` is one Electron app with a Lifebot chat (your Gemini/NVIDIA brain with tools), a Typewriter task list whose Start button launches the Pomodoro for that task, and reminders (desktop notifications, in-app, ntfy phone push). It lives in the system tray and can start with Windows.

- Install: `powershell -ExecutionPolicy Bypass -File scripts\install_lifebot.ps1` (creates the Desktop and Start Menu shortcut).
- Game layer: diamonds, levels and a streak are computed from your real events (`src/life_agent/gamification.py`): 1 diamond per 5 focused minutes, 3 per completed task, level n starts at 20*(n-1)^2 diamonds. Sound effects are synthesized and can be muted.
- Obsidian dashboard: `python -m life_agent.obsidian.dashboard` writes a pixel-style note (charts as inline SVG, no plugins) into the vault; the app refreshes it at launch and after each session. Set `LIFE_AGENT_DASHBOARD_DIR` to change the folder.
- Setup notes: `pip install -r requirements.txt` in the venv (the backup model needs `openai`); set `NTFY_TOPIC` for phone push. The pixel font is Press Start 2P (SIL OFL, license in `assets/fonts`).
