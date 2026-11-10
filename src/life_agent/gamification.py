"""Light game mechanics computed from real events (nothing is stored, nothing can drift).

Rules
  * A completed focus session earns 1 diamond per 5 focused minutes (25 min = 5 diamonds, min 1).
  * A session stopped early earns 1 diamond per full 10 focused minutes (effort counts, no shame).
  * Completing a task opens a chest worth 3 diamonds.
  * Level n starts at 20 * (n-1)^2 total diamonds (L2 = 20, L3 = 80, L4 = 180, L5 = 320 ...).
  * Streak = consecutive days with at least one completed session or completed task. A day that
    has not had any activity yet does not break the streak until it is over.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta

from life_agent import dates
from life_agent.events import queries, store

DIAMONDS_PER_COMPLETED_5MIN = 1
CHEST_DIAMONDS = 3
XP_BASE = 20

TITLES = [
    "Rookie Explorer", "Cave Scout", "Gem Hunter", "Crystal Seeker", "Relic Finder",
    "Temple Raider", "Treasure Master", "Diamond Baron", "Legend of the Deep",
]


def session_diamonds(session: dict) -> int:
    minutes = (session.get("duration_seconds") or 0) / 60
    status = session.get("status")
    if status == "completed":
        return max(1, round(minutes / 5) * DIAMONDS_PER_COMPLETED_5MIN)
    if status == "abandoned":
        return int(minutes // 10)
    return 0


def level_for(total: int) -> int:
    return int(math.sqrt(max(total, 0) / XP_BASE)) + 1


def title_for(level: int) -> str:
    return TITLES[min(level, len(TITLES)) - 1]


def compute(events: list[dict] | None = None, today: date | None = None) -> dict:
    """All game stats as of `today`. Pure given `events`; reads the local store when omitted."""
    today = today or dates.today()
    events = store.load_all() if events is None else events

    per_day = defaultdict(int)          # diamonds earned per ISO date
    active_days = set()                 # days with a completed session or task
    sessions_today = chests_today = 0
    today_iso = today.isoformat()

    focus_dates = {e.get("date") for e in events
                   if e.get("kind") in ("focus_started", "focus_completed", "focus_abandoned") and e.get("date")}
    for day in focus_dates:
        for s in queries.sessions_from_events(events, day):
            per_day[day] += session_diamonds(s)
            if s["status"] == "completed":
                active_days.add(day)
                if day == today_iso:
                    sessions_today += 1

    seen_tasks = set()
    for e in events:
        if e.get("kind") != "task_completed" or not e.get("date"):
            continue
        key = (e["date"], e.get("intent_id") or e.get("task"))
        if key in seen_tasks:
            continue
        seen_tasks.add(key)
        per_day[e["date"]] += CHEST_DIAMONDS
        active_days.add(e["date"])
        if e["date"] == today_iso:
            chests_today += 1

    total = sum(per_day.values())
    level = level_for(total)
    floor, ceiling = XP_BASE * (level - 1) ** 2, XP_BASE * level ** 2

    day = today if today_iso in active_days else today - timedelta(days=1)
    streak = 0
    while day.isoformat() in active_days:
        streak += 1
        day -= timedelta(days=1)

    return {
        "total": total,
        "today": per_day.get(today_iso, 0),
        "level": level,
        "title": title_for(level),
        "xp": total - floor,
        "xp_needed": ceiling - floor,
        "xp_pct": round(100 * (total - floor) / (ceiling - floor)),
        "streak": streak,
        "sessions_today": sessions_today,
        "chests_today": chests_today,
        "per_day": dict(per_day),
    }


def reward(before: dict, after: dict) -> dict:
    """What changed between two snapshots, for the reward animation."""
    return {
        "diamonds": after["total"] - before["total"],
        "level_up": after["level"] > before["level"],
        "stats": {k: v for k, v in after.items() if k != "per_day"},
    }
