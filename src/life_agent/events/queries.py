"""Query layer for focus events - Phase 1."""
import json
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

from life_agent.events import store


def get_focus_sessions(date_iso: str) -> list[dict]:
    """
    Get all focus sessions for a given date (local YYYY-MM-DD).

    Pairs focus_started with focus_completed/abandoned chronologically within each intent_id,
    so a task run more than once under the same intent_id yields one session per run.
    Returns list of sessions with: date, task, start, end, duration_seconds, source, status.
    """
    # Check if events file exists
    events_file = Path("data/events.jsonl")
    if not events_file.exists():
        return []

    return sessions_from_events(store.load_all(), date_iso)


def sessions_from_events(events: list[dict], date_iso: str) -> list[dict]:
    """Build focus sessions for one date from an in-memory list of events.

    Pure function: used for the local event store and for events read back from Notion.
    """
    # Filter to focus events for this date
    focus_events = [
        e for e in events
        if e.get("kind") in ["focus_started", "focus_completed", "focus_abandoned"]
        and e.get("date") == date_iso
    ]

    if not focus_events:
        return []

    # Group by intent_id
    by_intent = {}
    for event in focus_events:
        intent_id = event.get("intent_id")
        if intent_id:
            if intent_id not in by_intent:
                by_intent[intent_id] = []
            by_intent[intent_id].append(event)

    # Walk each intent's events chronologically. A focus_started opens a session, the next
    # completed/abandoned closes it. A task can be run several times under one intent_id
    # (e.g. START, STOP, START, finish), so every end event yields its own session.
    sessions = []
    for intent_id, events_list in by_intent.items():
        events_list = sorted(events_list, key=lambda e: e.get("ts", ""))

        open_start = None
        for event in events_list:
            kind = event.get("kind")
            if kind == "focus_started":
                if open_start is not None:
                    sessions.append(_unfinished_session(date_iso, open_start))
                open_start = event
            else:
                sessions.append(_ended_session(date_iso, open_start, event))
                open_start = None
        if open_start is not None:
            sessions.append(_unfinished_session(date_iso, open_start))

    return sessions


def _unfinished_session(date_iso: str, started: dict) -> dict:
    return {
        "date": date_iso,
        "task": started.get("task", "(unknown)"),
        "start": started.get("ts"),
        "end": None,
        "duration_seconds": None,
        "source": started.get("source", "unknown"),
        "status": "unfinished"
    }


def _ended_session(date_iso: str, started: Optional[dict], end_event: dict) -> dict:
    """Session closed by a completed/abandoned event; started is None if no start was recorded."""
    end_ts = end_event.get("ts")
    duration = end_event.get("duration_seconds") if started else end_event.get("duration_seconds", 0)
    if started:
        start_ts = started.get("ts")
    else:
        # No matching start: derive it as end_ts minus duration_seconds
        try:
            end_dt = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
            start_dt = end_dt - timedelta(seconds=duration or 0)
            start_ts = start_dt.isoformat().replace("+00:00", "Z")
        except (AttributeError, TypeError, ValueError):
            start_ts = end_ts
    source_event = started or end_event
    return {
        "date": date_iso,
        "task": source_event.get("task", "(unknown)"),
        "start": start_ts,
        "end": end_ts,
        "duration_seconds": duration,
        "source": source_event.get("source", "unknown"),
        "status": "completed" if end_event.get("kind") == "focus_completed" else "abandoned"
    }


def get_local_date_iso(offset_days: int = 0) -> str:
    """Get local date as YYYY-MM-DD, optionally offset by days."""
    d = date.today() + timedelta(days=offset_days)
    return d.isoformat()


def cli_main():
    """CLI: python -m life_agent.events.queries today|yesterday|YYYY-MM-DD [--json]"""
    if len(sys.argv) < 2:
        print("Usage: python -m life_agent.events.queries today|yesterday|YYYY-MM-DD [--json]", file=sys.stderr)
        sys.exit(1)

    date_arg = sys.argv[1]
    json_output = "--json" in sys.argv

    # Resolve date
    if date_arg == "today":
        date_iso = get_local_date_iso(0)
    elif date_arg == "yesterday":
        date_iso = get_local_date_iso(-1)
    else:
        date_iso = date_arg

    # Validate date format
    try:
        datetime.strptime(date_iso, "%Y-%m-%d")
    except ValueError:
        print(f"ERROR: Invalid date format: {date_iso}", file=sys.stderr)
        sys.exit(1)

    # Check if events file exists
    events_file = Path("data/events.jsonl")
    if not events_file.exists():
        if json_output:
            print(json.dumps([], indent=2))
        else:
            print("no event file")
        sys.exit(0)

    # Get sessions
    sessions = get_focus_sessions(date_iso)

    if json_output:
        print(json.dumps(sessions, indent=2))
    else:
        if not sessions:
            print(f"No sessions on {date_iso}")
        else:
            # Table format
            print(f"Sessions on {date_iso}:")
            print()
            for i, session in enumerate(sessions, 1):
                print(f"{i}. {session['task']}")
                print(f"   Status: {session['status']}")
                print(f"   Start:  {session['start']}")
                print(f"   End:    {session['end']}")
                if session['duration_seconds'] is not None:
                    print(f"   Duration: {session['duration_seconds']} seconds ({session['duration_seconds']//60}m {session['duration_seconds']%60}s)")
                print(f"   Source: {session['source']}")
                print()


if __name__ == "__main__":
    cli_main()
