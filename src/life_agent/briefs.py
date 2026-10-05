"""Save each scheduled task's finished output as a plain markdown note Lifebot (and Obsidian) can read.

Notes land in <vault>/Briefings/<YYYY-MM-DD> <task>.md, next to the dashboard. Best effort: a failed
save is logged and never stops the task. Tests and smoke runs point LIFE_AGENT_BRIEFS_DIR at a temp dir.
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from life_agent import dates
from life_agent.obsidian import dashboard

LABELS = {
    "meal_plan": "Meal plan",
    "ai_edge": "AI Edge: opportunities and research",
    "tomorrow_planner": "Tomorrow's plan",
    "evening_checkin": "Evening check-in",
    "goal_planner": "Full day plan",
    "weekly_review": "Weekly review",
    "career_prep": "Global career prep",
}


def briefs_dir() -> Path:
    env = os.environ.get("LIFE_AGENT_BRIEFS_DIR")
    return Path(env) if env else dashboard.DEFAULT_DIR.parent / "Briefings"


def save(task: str, text: object, day: date | None = None) -> Path | None:
    """Write the note and return its path, or None if it could not be written."""
    try:
        body = str(text).strip()
        if not body:
            return None
        day = day or dates.today()
        folder = briefs_dir()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{day.isoformat()} {task}.md"
        tmp = path.with_suffix(".md.tmp")
        tmp.write_text(f"# {LABELS.get(task, task)}: {day.isoformat()}\n\n{body}\n", encoding="utf-8")
        tmp.replace(path)
        print(f"[briefs] saved {path.name}")
        return path
    except Exception as err:  # never let a local note stop the task
        print(f"[briefs] not saved ({err})")
        return None
