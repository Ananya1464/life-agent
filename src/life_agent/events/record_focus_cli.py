"""CLI tool to record focus events from Pomodoro app via stdin."""
import json
import re
import sys

from life_agent.events import event_model


def main():
    """
    Read one JSON object from stdin with structure:
    {
      "phase": "started|completed|abandoned",
      "date_iso": "YYYY-MM-DD",
      "task": "task description (optional)",
      "duration_seconds": int (for completed/abandoned),
      "session_id": "unique session id"
    }

    Call event_model.record_focus_* with source="pomodoro_app"
    and intent_id=f"pomodoro:{session_id}".

    Exit 0 on success, 1 on failure.
    """
    try:
        input_json = sys.stdin.buffer.read().decode("utf-8")
        input_data = json.loads(input_json)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"ERROR: Failed to parse JSON from stdin", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected error reading stdin", file=sys.stderr)
        sys.exit(1)

    phase = input_data.get("phase")
    date_iso = input_data.get("date_iso")
    task = (input_data.get("task") or "").strip() or "(no task)"
    duration_seconds = input_data.get("duration_seconds")
    session_id = input_data.get("session_id")

    # Validate required fields
    missing = []
    if not phase:
        missing.append("phase")
    if not date_iso:
        missing.append("date_iso")
    if not session_id:
        missing.append("session_id")

    if missing:
        print(f"ERROR: Missing required fields: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    # Validate phase
    if phase not in ["started", "completed", "abandoned"]:
        print(f"ERROR: Invalid phase; must be one of: started, completed, abandoned", file=sys.stderr)
        sys.exit(1)

    # Validate date_iso format
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_iso):
        print(f"ERROR: Invalid date_iso format; must be YYYY-MM-DD", file=sys.stderr)
        sys.exit(1)

    # Validate session_id
    if not isinstance(session_id, str) or not session_id.strip():
        print(f"ERROR: session_id must be a non-empty string", file=sys.stderr)
        sys.exit(1)

    # Validate duration_seconds for completed/abandoned
    if phase in ["completed", "abandoned"]:
        try:
            duration_seconds = int(duration_seconds) if duration_seconds is not None else None
            if duration_seconds is None or duration_seconds < 0:
                print(f"ERROR: duration_seconds required and must be >= 0 for {phase}", file=sys.stderr)
                sys.exit(1)
        except (ValueError, TypeError):
            print(f"ERROR: duration_seconds must be a non-negative integer", file=sys.stderr)
            sys.exit(1)

    intent_id = f"pomodoro:{session_id}"
    source = "pomodoro_app"

    try:
        if phase == "started":
            event_model.record_focus_started(
                date_iso=date_iso,
                task=task,
                intent_id=intent_id,
                source=source
            )
        elif phase == "completed":
            event_model.record_focus_completed(
                date_iso=date_iso,
                task=task,
                duration_seconds=duration_seconds,
                intent_id=intent_id,
                source=source
            )
        elif phase == "abandoned":
            event_model.record_focus_abandoned(
                date_iso=date_iso,
                task=task,
                duration_seconds=duration_seconds,
                intent_id=intent_id,
                source=source
            )
    except Exception as e:
        print(f"ERROR: Failed to record focus event", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
