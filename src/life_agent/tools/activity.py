"""Deterministic activity tool for querying canonical JSONL event store."""
from typing import List, Dict, Optional, Union
from datetime import date, timedelta

from life_agent.events import queries


def get_activity(date_spec: Union[str, int] = "today") -> List[Dict]:
    """
    Get activity for a specified date.

    Args:
        date_spec: One of:
            - "today" (default)
            - "yesterday"
            - int offset (e.g., -1 for yesterday, -7 for last week)
            - YYYY-MM-DD string (explicit date)

    Returns:
        List of activity records, one per focus session.
        Each record contains: date, task, start, end, duration_seconds, source, status.
        Empty list if no activity found or date is invalid.

    Semantics:
    - Reads only from canonical JSONL via existing queries.py
    - No LLM, no network, no SQLite, no Markdown parsing
    - Deterministic: same input always returns same output
    - Empty dates return explicit empty result (not fabricated data)
    - Invalid dates handled safely (returned as empty)
    """
    # Resolve date_spec to YYYY-MM-DD string
    try:
        if isinstance(date_spec, str):
            if date_spec == "today":
                date_iso = queries.get_local_date_iso(0)
            elif date_spec == "yesterday":
                date_iso = queries.get_local_date_iso(-1)
            else:
                # Assume explicit YYYY-MM-DD
                date_iso = date_spec
        elif isinstance(date_spec, int):
            # Offset days (e.g., -1, -7)
            date_iso = queries.get_local_date_iso(date_spec)
        else:
            # Invalid type
            return []
    except Exception:
        # Invalid date specification
        return []

    # Query canonical event store
    try:
        sessions = queries.get_focus_sessions(date_iso)
        return sessions
    except Exception:
        # Query failure (malformed JSONL, file not found, etc.)
        return []


def get_activity_summary(date_spec: Union[str, int] = "today") -> Dict:
    """
    Get summary statistics for activity on a date.

    Returns dict with:
    - date: the date queried
    - session_count: total sessions
    - completed_count: sessions with status=completed
    - abandoned_count: sessions with status=abandoned
    - unfinished_count: sessions with status=unfinished
    - total_focus_seconds: sum of all duration_seconds (only completed/abandoned)
    - sessions: list of full session records
    """
    sessions = get_activity(date_spec)

    # Resolve date for reporting
    try:
        if isinstance(date_spec, str):
            if date_spec == "today":
                date_iso = queries.get_local_date_iso(0)
            elif date_spec == "yesterday":
                date_iso = queries.get_local_date_iso(-1)
            else:
                date_iso = date_spec
        elif isinstance(date_spec, int):
            date_iso = queries.get_local_date_iso(date_spec)
        else:
            date_iso = "unknown"
    except Exception:
        date_iso = "unknown"

    completed = sum(1 for s in sessions if s.get("status") == "completed")
    abandoned = sum(1 for s in sessions if s.get("status") == "abandoned")
    unfinished = sum(1 for s in sessions if s.get("status") == "unfinished")
    total_seconds = sum(s.get("duration_seconds", 0) for s in sessions if s.get("duration_seconds"))

    return {
        "date": date_iso,
        "session_count": len(sessions),
        "completed_count": completed,
        "abandoned_count": abandoned,
        "unfinished_count": unfinished,
        "total_focus_seconds": total_seconds,
        "sessions": sessions
    }
