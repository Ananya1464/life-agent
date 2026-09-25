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

    Pairs focus_started with focus_completed/abandoned via intent_id.
    Returns list of sessions with: date, task, start, end, duration_seconds, source, status.
    """
    # Check if events file exists
    events_file = Path("data/events.jsonl")
    if not events_file.exists():
        return []

    # Load all events
    events = store.load_all()

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

    # Pair started with completed/abandoned
    sessions = []
    for intent_id, events_list in by_intent.items():
        # Sort by timestamp (chronological)
        events_list = sorted(events_list, key=lambda e: e.get("ts", ""))

        started = next((e for e in events_list if e.get("kind") == "focus_started"), None)
        end_event = next((e for e in events_list if e.get("kind") in ["focus_completed", "focus_abandoned"]), None)

        if started and end_event:
            # Paired session
            session = {
                "date": date_iso,
                "task": started.get("task", "(unknown)"),
                "start": started.get("ts"),
                "end": end_event.get("ts"),
                "duration_seconds": end_event.get("duration_seconds"),
                "source": started.get("source", "unknown"),
                "status": "completed" if end_event.get("kind") == "focus_completed" else "abandoned"
            }
            sessions.append(session)
        elif started:
            # Unfinished session
            session = {
                "date": date_iso,
                "task": started.get("task", "(unknown)"),
                "start": started.get("ts"),
                "end": None,
                "duration_seconds": None,
                "source": started.get("source", "unknown"),
                "status": "unfinished"
            }
            sessions.append(session)
        elif end_event:
            # Standalone end event
            duration = end_event.get("duration_seconds", 0)
            end_ts = end_event.get("ts")
            # Calculate start as end_ts minus duration_seconds
            try:
                end_dt = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
                start_dt = end_dt - timedelta(seconds=duration)
                start_ts = start_dt.isoformat().replace("+00:00", "Z")
            except:
                start_ts = end_ts

            session = {
                "date": date_iso,
                "task": end_event.get("task", "(unknown)"),
                "start": start_ts,
                "end": end_ts,
                "duration_seconds": duration,
                "source": end_event.get("source", "unknown"),
                "status": "completed" if end_event.get("kind") == "focus_completed" else "abandoned"
            }
            sessions.append(session)

    return sessions


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
