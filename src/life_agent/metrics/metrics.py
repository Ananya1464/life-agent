"""Life OS metrics: derive daily and weekly signals from events and Notion data."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import statistics
import pathlib

from life_agent.integrations import calendar_feed
from life_agent import config
from life_agent import dates
from life_agent.integrations import notion_api
from life_agent.events import store


NORMALIZED_OUTCOME_KINDS = {
    "task_completed",
    "task_partial",
    "task_never_started",
    "task_forgot",
    "task_skipped",
    "task_not_now",
    "task_no_response",
}


def _day_events(day) -> list[dict]:
    prefix = day.isoformat()
    return [ev for ev in store.load_all() if str(ev.get("ts", "")).startswith(prefix)]


def _slot_from_token(token: str) -> str:
    return {"M": "morning", "D": "midday", "E": "evening"}.get((token or "")[-1:], "")


def _checkins(reply: dict | None) -> list[dict]:
    return reply.get("checkins", []) if reply else []


def goal_trajectory(current_progress: float | None, expected_progress: float | None) -> dict:
    if current_progress is None or expected_progress is None:
        return {"status": "No data", "current": current_progress, "expected": expected_progress}
    gap = current_progress - expected_progress
    status = "On track" if gap >= 0 else "At risk" if gap >= -10 else "Behind"
    return {"status": status, "current": current_progress, "expected": expected_progress}


def _quote_of_the_day() -> dict:
    try:
        from outbound import _MORNING_QUOTES  # local import to avoid a hard dependency at startup

        quote, author = _MORNING_QUOTES[dates.today().day % len(_MORNING_QUOTES)]
        return {"text": quote, "author": author}
    except Exception:
        return {"text": "Small steps still count.", "author": "Life Agent"}


def _area_rows() -> list[dict]:
    if not config.LIFE_AREAS_GOALS_DB_ID:
        return []
    rows = goal_rows()
    area_scores = life_area_scores()
    out = []
    seen = set()
    for row in rows:
        props = row.get("properties", {})
        area = (props.get("Area", {}).get("select") or {}).get("name")
        if not area:
            continue
        seen.add(area)
        out.append({"area": area, "progress": area_scores.get(area), "measurable": area in area_scores})
    for area, pct in area_scores.items():
        if area not in seen:
            out.append({"area": area, "progress": pct, "measurable": True})
    return sorted(out, key=lambda row: row["area"])


def _goal_snapshot() -> list[dict]:
    rows = goal_rows()
    out = []
    for row in rows:
        props = row.get("properties", {})
        goal = "".join(t.get("plain_text", "") for t in props.get("Goal", {}).get("title", []))
        area = (props.get("Area", {}).get("select") or {}).get("name")
        progress = props.get("Progress %", {}).get("number")
        target_date = props.get("Target Date", {}).get("date", {})
        status = (props.get("Status", {}).get("select") or {}).get("name")
        if not goal:
            continue
        out.append({
            "goal": goal,
            "area": area,
            "progress": progress,
            "deadline": target_date.get("start"),
            "status": status,
            "measurable": progress is not None,
            "trajectory": goal_trajectory(progress, progress),
        })
    return out


def _weekly_win(weekly: dict) -> dict:
    active_days = weekly.get("active_days") or 0
    tasks_done = weekly.get("tasks_done") or 0
    tasks_planned = weekly.get("tasks_planned") or 0
    if active_days:
        text = f"You showed up for {active_days} days this week."
    elif tasks_done:
        text = f"You completed {tasks_done} tasks this week."
    else:
        text = "Not enough data yet."

    prev_rows = [calculate_daily_metrics(dates.today() - timedelta(days=i)) for i in range(14, 7, -1)]
    prev_done = sum(r.get("tasks_done") or 0 for r in prev_rows)
    prev_planned = sum(r.get("tasks_planned") or 0 for r in prev_rows)
    comparative = None
    if prev_planned and tasks_planned:
        comparative = tasks_done - prev_done
    return {"text": text, "comparison": comparative}


def _attention(daily_rows: list[dict]) -> list[str]:
    notes = []
    if not daily_rows:
        return ["Not enough data yet."]
    by_area = {}
    for row in daily_rows:
        area_scores = row.get("areas", {})
        for area, pct in area_scores.items():
            by_area.setdefault(area, []).append(pct)
    if by_area:
        worst_area, worst_value = min(((area, statistics.mean(values)) for area, values in by_area.items()), key=lambda item: item[1])
        notes.append(f"{worst_area} has had the lowest average progress over the last 7 days ({round(worst_value)}%).")
    no_response = sum(row.get("no_response") or 0 for row in daily_rows)
    if no_response:
        notes.append(f"{no_response} tasks received no response over the last 7 days.")
    return notes[:2] or ["Not enough data yet."]


def generate_dashboard_data(day=None) -> dict:
    day = day or dates.today()
    daily = calculate_daily_metrics(day)
    weekly = aggregate_weekly_metrics(day)
    daily_rows = weekly["daily_rows"]
    outcomes = {
        "completed": sum(r.get("tasks_done") or 0 for r in daily_rows),
        "partial": sum(r.get("partial") or 0 for r in daily_rows),
        "forgot": sum(r.get("forgot") or 0 for r in daily_rows),
        "never_started": sum(r.get("never_started") or 0 for r in daily_rows),
        "skipped": sum(r.get("skipped") or 0 for r in daily_rows),
        "not_now": sum(ev.get("kind") == "task_not_now" for ev in store.load_all()),
        "no_response": sum(r.get("no_response") or 0 for r in daily_rows),
    }
    execution_trend = [
        {"date": row["date"], "completion_pct": row.get("completion_pct")}
        for row in daily_rows
    ]
    goal_snapshot = _goal_snapshot()
    metrics = {
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "today": daily,
        "week": {k: v for k, v in weekly.items() if k != "daily_rows"},
        "daily_execution": execution_trend,
        "outcomes": outcomes,
        "life_areas": _area_rows(),
        "goals": goal_snapshot,
        "weekly_win": _weekly_win(weekly),
        "attention": {"items": _attention(daily_rows)},
        "quote": _quote_of_the_day(),
        "notes": daily.get("notes"),
        "state": {
            "today_message": "Not enough data yet" if daily.get("completion_pct") is None else f"{daily.get('completion_pct')}% completion",
            "history_available": any(row.get("completion_pct") is not None for row in daily_rows),
        },
    }
    return metrics


def write_dashboard_data(output_dir: str | pathlib.Path = "docs/data") -> dict:
    output_path = pathlib.Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    data = generate_dashboard_data()
    (output_path / "metrics.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    goals_path = output_path / "goals.json"
    goals_path.write_text(json.dumps({"goals": data.get("goals", []), "life_areas": data.get("life_areas", [])}, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def calculate_daily_metrics(day=None) -> dict:
    day = day or dates.today()
    events = _day_events(day)
    reply = next((ev for ev in reversed(events) if ev.get("kind") == "reply_parsed"), None)
    planned_events = [ev for ev in events if ev.get("kind") == "task_planned"]
    planned_ids = {ev.get("intent_id") for ev in planned_events if ev.get("intent_id")}
    outcome_events = [ev for ev in events if ev.get("kind") in NORMALIZED_OUTCOME_KINDS]
    normalized_mode = bool(planned_events or outcome_events)
    checkins = _checkins(reply)
    from_checkins = bool(checkins)
    if normalized_mode:
        planned = len(planned_events)
        if planned:
            done = sum(ev.get("kind") == "task_completed" and ev.get("intent_id") in planned_ids for ev in outcome_events)
            partial = sum(ev.get("kind") == "task_partial" and ev.get("intent_id") in planned_ids for ev in outcome_events)
            forgotten = sum(ev.get("kind") == "task_forgot" and ev.get("intent_id") in planned_ids for ev in outcome_events)
            never = sum(ev.get("kind") == "task_never_started" and ev.get("intent_id") in planned_ids for ev in outcome_events)
            skipped = sum(ev.get("kind") == "task_skipped" and ev.get("intent_id") in planned_ids for ev in outcome_events)
            no_response = sum(ev.get("kind") == "task_no_response" and ev.get("intent_id") in planned_ids for ev in outcome_events)
        else:
            done = partial = forgotten = never = skipped = no_response = 0
    else:
        planned = len(checkins) or sum(ev.get("kind") == "task_started" for ev in events) or None
        done = sum(c.get("status") == "done" for c in checkins) if from_checkins else sum(ev.get("kind") == "task_completed" for ev in events)
        partial = sum(c.get("status") == "partial" for c in checkins) if from_checkins else sum(ev.get("kind") == "task_partial" for ev in events)
        forgotten = sum(c.get("status") == "forgot" for c in checkins) if from_checkins else sum(ev.get("kind") == "task_forgot" for ev in events)
        never = sum(c.get("status") == "never_started" for c in checkins) if from_checkins else sum(ev.get("kind") == "task_never_started" for ev in events)
        skipped = sum(ev.get("kind") == "task_skipped" for ev in events)
        no_response = sum(ev.get("kind") == "task_no_response" for ev in events)
    completion = round((done / planned) * 100) if planned else None
    execution = round(((done or 0) + 0.5 * (partial or 0)) / planned * 100) if planned else None
    workout = any(ev.get("kind") == "workout_completed" for ev in events) or any(
        "workout" in (c.get("task", "").lower()) and c.get("status") == "done" for c in checkins
    ) or any(_slot_from_token(ev.get("token", "")) == "evening" and ev.get("kind") == "reply_raw" for ev in events) or any(
        "workout" in e.lower() for e in calendar_feed.events_on(day)
    )
    goals_note = "No goal rows yet." if not config.LIFE_AREAS_GOALS_DB_ID else ""
    notes = []
    if reply and reply.get("raw_text"):
        notes.append((reply.get("captures") or [{}])[0].get("text") if reply.get("captures") else "")
    if not planned:
        notes.append("No task or reply data yet.")
    if goals_note:
        notes.append(goals_note)
    area_scores = life_area_scores()
    return {
        "date": day.isoformat(),
        "tasks_planned": planned,
        "tasks_done": done,
        "partial": partial,
        "forgot": forgotten,
        "never_started": never,
        "skipped": skipped,
        "no_response": no_response,
        "completion_pct": completion,
        "execution_score": execution,
        "sleep_hours": reply.get("sleep_hours") if reply else None,
        "energy": reply.get("energy") if reply else None,
        "soreness": reply.get("soreness") if reply else None,
        "workout": workout,
        "morning_brief_sent": any((ev.get("kind") in ("email_sent", "notification_sent", "notification_delivered")) and ev.get("slot") == "morning" for ev in events),
        "evening_checkin_completed": any(ev.get("kind") == "reply_raw" and _slot_from_token(ev.get("token", "")) == "evening" for ev in events),
        "notifications_sent": sum(ev.get("kind") == "notification_sent" for ev in events) + sum(ev.get("kind") == "email_sent" for ev in events),
        "notifications_delivered": sum(ev.get("kind") == "notification_delivered" for ev in events),
        "notifications_acknowledged": sum(ev.get("kind") == "reply_raw" for ev in events),
        "life_area": None,
        "notes": " | ".join(n for n in notes if n),
        "areas": area_scores,
        "goal_rows": goal_rows(),
    }


def life_area_scores() -> dict[str, float]:
    if not config.LIFE_AREAS_GOALS_DB_ID:
        return {}
    rows = notion_api._req("POST", f"/data_sources/{config.LIFE_AREAS_GOALS_DB_ID}/query", json={}).get("results", [])
    groups: dict[str, list[float]] = {}
    for row in rows:
        area = (row.get("properties", {}).get("Area", {}).get("select") or {}).get("name")
        progress = row.get("properties", {}).get("Progress %", {}).get("number")
        if area and progress is not None:
            groups.setdefault(area, []).append(float(progress))
    return {area: round(statistics.mean(values)) for area, values in groups.items()}


def goal_rows() -> list[dict]:
    if not config.LIFE_AREAS_GOALS_DB_ID:
        return []
    return notion_api._req("POST", f"/data_sources/{config.LIFE_AREAS_GOALS_DB_ID}/query", json={}).get("results", [])


def aggregate_weekly_metrics(day=None, window: int = 7) -> dict:
    day = day or dates.today()
    days = [day - timedelta(days=i) for i in range(window - 1, -1, -1)]
    rows = [calculate_daily_metrics(d) for d in days]
    planned = sum(r.get("tasks_planned") or 0 for r in rows)
    done = sum(r.get("tasks_done") or 0 for r in rows)
    active_days = sum(1 for r in rows if (r.get("tasks_planned") or 0) > 0 or r.get("notifications_sent") or r.get("sleep_hours") is not None)
    missed_days = window - active_days
    return {
        "start": days[0].isoformat(),
        "end": days[-1].isoformat(),
        "completion_pct": round(done / planned * 100) if planned else None,
        "tasks_planned": planned or None,
        "tasks_done": done or None,
        "execution_score": round(sum(r.get("execution_score") or 0 for r in rows) / sum(1 for r in rows if r.get("execution_score") is not None)) if any(r.get("execution_score") is not None for r in rows) else None,
        "workout_consistency": round(sum(1 for r in rows if r.get("workout")) / active_days * 100) if active_days else None,
        "checkin_consistency": round(sum(1 for r in rows if r.get("notifications_acknowledged")) / active_days * 100) if active_days else None,
        "active_days": active_days,
        "missed_days": missed_days,
        "daily_rows": rows,
        "areas": life_area_scores(),
    }


def _title_value(db_id: str, title: str) -> dict | None:
    rows = notion_api._req("POST", f"/data_sources/{db_id}/query", json={"filter": {"property": "Date", "title": {"equals": title}}}).get("results", [])
    return rows[0] if rows else None


def _metric_props(row: dict) -> dict:
    props = {"Date": {"title": [{"type": "text", "text": {"content": row["date"]}}]}}
    mapping = {
        "tasks_planned": "Tasks Planned",
        "tasks_done": "Tasks Done",
        "partial": "Partial",
        "forgot": "Forgot",
        "never_started": "Never Started",
        "completion_pct": "Completion %",
        "sleep_hours": "Sleep Hours",
        "energy": "Energy",
        "soreness": "Soreness",
        "workout": "Workout",
    }
    for key, name in mapping.items():
        val = row.get(key)
        if val is not None:
            props[name] = {"number": val} if name != "Workout" else {"checkbox": bool(val)}
    if row.get("notes"):
        props["Notes"] = {"rich_text": [{"type": "text", "text": {"content": row["notes"][:2000]}}]}
    if row.get("execution_score") is not None:
        notes_text = row.get("notes", "")
        suffix = f"Execution score: {row['execution_score']}%"
        combined = f"{notes_text} | {suffix}" if notes_text else suffix
        props["Notes"] = {"rich_text": [{"type": "text", "text": {"content": combined[:2000]}}]}
    for area, pct in row.get("areas", {}).items():
        prop = f"{area} Progress %"
        if prop in {"Career Progress %", "Health Progress %", "Learning Progress %", "Finance Progress %", "Personal Progress %"}:
            props[prop] = {"number": pct}
    return props


def update_daily_metrics(day=None) -> dict:
    row = calculate_daily_metrics(day)
    existing = _title_value(config.LIFE_OS_METRICS_DB_ID, row["date"])
    props = _metric_props(row)
    if existing:
        notion_api._req("PATCH", f"/pages/{existing['id']}", json={"properties": props})
    else:
        notion_api._req("POST", "/pages", json={
            "parent": {"database_id": config.LIFE_OS_METRICS_DB_ID},
            "properties": props,
        })
    return row


def update_weekly_metrics(day=None) -> dict:
    return aggregate_weekly_metrics(day)


def _bar(pct: float | None) -> str:
    if pct is None:
        return "not enough data"
    filled = round(pct / 10)
    return f"{'█' * filled}{'░' * (10 - filled)} {pct}%"


def update_dashboard(day=None) -> str:
    day = day or dates.today()
    daily = calculate_daily_metrics(day)
    weekly = aggregate_weekly_metrics(day)
    areas = life_area_scores()
    goals = goal_rows()
    trend = "\n".join(f"- {r['date']}: {_bar(r.get('completion_pct'))}" for r in weekly["daily_rows"])
    area_lines = "\n".join(f"- {area}: {pct}%" for area, pct in sorted(areas.items(), key=lambda x: x[1], reverse=True)) or "- No life area data yet."
    goal_lines = "\n".join(f"- {''.join(x.get('plain_text','') for x in g.get('properties', {}).get('Goal', {}).get('title', []))}: {g.get('properties', {}).get('Progress %', {}).get('number')}%" for g in goals) or "- No active goals yet."
    md = f"""### TODAY
- Completion: {_bar(daily.get('completion_pct'))}
- Tasks: {daily.get('tasks_done') or 0}/{daily.get('tasks_planned') or 0}
- Execution score: {daily.get('execution_score') if daily.get('execution_score') is not None else 'not enough data'}
- Workout: {'done' if daily.get('workout') else 'not yet'}
- Morning brief: {'sent' if daily.get('morning_brief_sent') else 'not yet'}
- Evening check-in: {'completed' if daily.get('evening_checkin_completed') else 'not yet'}

### THIS WEEK
- Weekly completion: {_bar(weekly.get('completion_pct'))}
- Active days: {weekly.get('active_days')}
- Missed days: {weekly.get('missed_days')}
- Workout consistency: {_bar(weekly.get('workout_consistency'))}
- Check-in consistency: {_bar(weekly.get('checkin_consistency'))}

### LIFE AREAS
{area_lines}

### GOALS
{goal_lines}

### TRENDS
{trend or '- Not enough data yet.'}

### LIFE AGENT
- Notifications sent: {daily.get('notifications_sent') or 0}
- Replies processed: {daily.get('notifications_acknowledged') or 0}
- Notes: {daily.get('notes') or 'No notes yet.'}
"""
    notion_api.replace_section(config.LIFE_OS_DASHBOARD_PAGE_ID, "Current snapshot", md)
    return md


def update_metrics(day=None) -> dict:
    daily = update_daily_metrics(day)
    weekly = update_weekly_metrics(day)
    dashboard = update_dashboard(day)
    return {"daily": daily, "weekly": weekly, "dashboard": dashboard}