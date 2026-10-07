"""Turn recent focus sessions into verified facts and a plan-load recommendation for the prompts.

Everything here is deterministic (no LLM): the numbers handed to the model are computed, so the
model can adapt to what actually happened without inventing statistics.

Sources: the Notion "Life Agent Events" database (what the cloud agent can see), merged with the
local JSONL store when one exists (desktop runs). Failure to read either degrades to "no data".
"""
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from life_agent import config, dates
from life_agent.events import cloud_activity, queries, store

WINDOW_DAYS = 7
RECENT_ACTIVE_DAYS = 3
LIGHT_BELOW = 0.5      # recent completion rate under this -> lighter plan
STRONG_AT_LEAST = 0.8  # at/above this (with enough sessions) -> room for a stretch task


@dataclass
class ActivityContext:
    mode: str                     # "unknown" | "light" | "standard" | "strong"
    stats: dict
    summary: str                  # factual lines for the planner / weekly review
    load_guidance: str            # instruction on how big tomorrow's plan should be
    patterns: str                 # kind, specific observations for the evening check-in
    sessions: list[dict] = field(default_factory=list)


def _local_events(start: date, end: date) -> list[dict]:
    try:
        return [
            e for e in store.load_all()
            if e.get("kind") in cloud_activity.FOCUS_KINDS
            and start.isoformat() <= (e.get("date") or "") <= end.isoformat()
        ]
    except Exception as exc:
        print(f"[activity] local events unavailable: {exc}")
        return []


def load_events(start: date, end: date) -> list[dict]:
    """Focus events for [start, end] from Notion and the local store, de-duplicated by id."""
    events: list[dict] = []
    if config.NOTION_TOKEN and config.EVENTS_SYNC_DATA_SOURCE_ID:
        try:
            events.extend(cloud_activity.fetch_focus_events(start, end))
        except Exception as exc:
            print(f"[activity] Notion focus events unavailable: {exc}")
    seen = {e.get("id") for e in events if e.get("id")}
    for e in _local_events(start, end):
        if e.get("id") not in seen:
            events.append(e)
    return events


def sessions_for_range(events: list[dict], start: date, end: date) -> list[dict]:
    sessions = []
    day = start
    while day <= end:
        sessions.extend(queries.sessions_from_events(events, day.isoformat()))
        day += timedelta(days=1)
    return sessions


def _minutes(seconds: int) -> str:
    m = round(seconds / 60)
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def _local_hour(ts: str | None) -> int | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(dates.TZ).hour
    except ValueError:
        return None


def compute_stats(sessions: list[dict], start: date, end: date) -> dict:
    per_day = {}
    day = start
    while day <= end:
        per_day[day.isoformat()] = {"date": day.isoformat(), "completed": 0, "abandoned": 0,
                                    "unfinished": 0, "focus_seconds": 0}
        day += timedelta(days=1)

    abandoned_tasks: Counter = Counter()
    hour_seconds: Counter = Counter()
    completed_count = 0
    for s in sessions:
        row = per_day.get(s["date"])
        if row is None:
            continue
        status = s["status"]
        row[status] += 1
        if status in ("completed", "abandoned"):
            row["focus_seconds"] += int(s.get("duration_seconds") or 0)
        if status == "abandoned":
            abandoned_tasks[(s.get("task") or "").strip().lower()] += 1
        if status == "completed":
            completed_count += 1
            hour = _local_hour(s.get("start"))
            if hour is not None:
                hour_seconds[hour] += int(s.get("duration_seconds") or 0)

    rows = list(per_day.values())
    completed = sum(r["completed"] for r in rows)
    abandoned = sum(r["abandoned"] for r in rows)
    finished = completed + abandoned

    # The last few days that actually had finished sessions drive the load recommendation
    active_rows = [r for r in rows if r["completed"] + r["abandoned"] > 0]
    recent = active_rows[-RECENT_ACTIVE_DAYS:]
    recent_completed = sum(r["completed"] for r in recent)
    recent_finished = sum(r["completed"] + r["abandoned"] for r in recent)

    best_hour = None
    if completed_count >= 3 and hour_seconds:
        best_hour = hour_seconds.most_common(1)[0][0]

    display_names = {}
    for s in sessions:
        display_names.setdefault((s.get("task") or "").strip().lower(), (s.get("task") or "").strip())

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": rows,
        "completed": completed,
        "abandoned": abandoned,
        "unfinished": sum(r["unfinished"] for r in rows),
        "finished": finished,
        "completion_rate": (completed / finished) if finished else None,
        "focus_seconds": sum(r["focus_seconds"] for r in rows),
        "active_days": len(active_rows),
        "recent_finished": recent_finished,
        "recent_completion_rate": (recent_completed / recent_finished) if recent_finished else None,
        "best_hour": best_hour,
        "often_abandoned": [
            display_names.get(t, t) for t, n in abandoned_tasks.most_common(3) if n >= 2 and t
        ],
    }


def recommend_mode(stats: dict) -> str:
    if stats["finished"] == 0:
        return "unknown"
    rate, n = stats["recent_completion_rate"], stats["recent_finished"]
    if n >= 2 and rate is not None and rate < LIGHT_BELOW:
        return "light"
    if n >= 3 and rate is not None and rate >= STRONG_AT_LEAST:
        return "strong"
    return "standard"


_GUIDANCE = {
    "unknown": "No recent focus-session data is available. Use the standard 3 priorities and do not "
               "comment on her focus habits.",
    "standard": "Her recent focus sessions are mixed. Keep the standard 3 priorities.",
    "light": "Her last few focus sessions were often cut short. Plan only 2 priorities, make the first "
             "a small starter task of about 25 minutes or less, and include no stretch task. Be "
             "encouraging; do not mention failure or guilt.",
    "strong": "Her recent focus sessions went well. Keep 3 priorities and make one of them a modest "
              "stretch task.",
}


def _summary(stats: dict) -> str:
    if stats["finished"] == 0 and stats["unfinished"] == 0:
        return f"Focus sessions, last {len(stats['days'])} days: no data recorded."
    lines = [
        f"Focus sessions, last {len(stats['days'])} days (local time): "
        f"{stats['completed']} completed, {stats['abandoned']} stopped early, "
        f"{_minutes(stats['focus_seconds'])} total focus across {stats['active_days']} active day(s)."
    ]
    if stats["completion_rate"] is not None:
        lines.append(f"Completion rate: {round(stats['completion_rate'] * 100)}%.")
    for row in stats["days"][-3:]:
        if row["completed"] + row["abandoned"]:
            lines.append(f"- {row['date']}: {row['completed']} completed, {row['abandoned']} stopped "
                         f"early, {_minutes(row['focus_seconds'])}")
    return "\n".join(lines)


def _patterns(stats: dict) -> str:
    facts = []
    if stats["completion_rate"] is not None and stats["finished"] >= 3:
        facts.append(f"{stats['completed']} of {stats['finished']} focus sessions finished this week")
    if stats["best_hour"] is not None:
        h = stats["best_hour"]
        facts.append(f"her completed focus time clusters around {h:02d}:00-{(h + 1) % 24:02d}:00")
    for task in stats["often_abandoned"]:
        facts.append(f'"{task}" was stopped early more than once this week')
    return "\n".join(f"- {f}" for f in facts)


def build(days: int = WINDOW_DAYS, today: date | None = None, events: list[dict] | None = None) -> ActivityContext:
    """Build the context for the last `days` days ending today. Never raises."""
    end = today or dates.today()
    start = end - timedelta(days=days - 1)
    try:
        if events is None:
            events = load_events(start, end)
        sessions = sessions_for_range(events, start, end)
        stats = compute_stats(sessions, start, end)
    except Exception as exc:
        print(f"[activity] could not build context: {exc}")
        sessions = []
        stats = compute_stats([], start, end)
    mode = recommend_mode(stats)
    return ActivityContext(
        mode=mode, stats=stats, summary=_summary(stats),
        load_guidance=_GUIDANCE[mode], patterns=_patterns(stats), sessions=sessions,
    )
