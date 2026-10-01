"""Read focus events back from the Notion "Life Agent Events" database.

The desktop app writes events to a local JSONL file; `desktop.sync` mirrors them to Notion. The
scheduled GitHub Actions agent has no local file, so it reads them here instead.
"""
from datetime import date, datetime, timedelta, timezone

from life_agent import config, dates
from life_agent.integrations import notion_api

FOCUS_KINDS = ("focus_started", "focus_completed", "focus_abandoned")


def _is_test_source(source: str) -> bool:
    return source == "test" or source.endswith("_test") or source.startswith("failure_test")


def _rich_text(prop: dict) -> str:
    return "".join(part.get("plain_text", "") for part in (prop or {}).get("rich_text", []))


def _title(prop: dict) -> str:
    return "".join(part.get("plain_text", "") for part in (prop or {}).get("title", []))


def _select(prop: dict) -> str:
    return ((prop or {}).get("select") or {}).get("name", "")


def _to_utc_ts(start: str) -> str | None:
    """Normalise a Notion date start (date or datetime, any offset) to ISO UTC with a Z suffix."""
    if not start:
        return None
    try:
        dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def event_from_page(page: dict) -> dict | None:
    """Map one Notion row to a local-style event dict; None if it is not a usable focus event."""
    props = page.get("properties", {})
    kind = _select(props.get("Kind"))
    if kind not in FOCUS_KINDS:
        return None
    source = _select(props.get("Source")) or "unknown"
    if _is_test_source(source):
        return None
    ts = _to_utc_ts(((props.get("Date") or {}).get("date") or {}).get("start", ""))
    if not ts:
        return None

    local_date = (
        datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(dates.TZ).date().isoformat()
    )
    event = {
        "id": _rich_text(props.get("Event ID")) or page.get("id", ""),
        "ts": ts,
        "kind": kind,
        "date": local_date,
        "task": _rich_text(props.get("Task")) or _title(props.get("Name")),
        "intent_id": _rich_text(props.get("Intent ID")) or None,
        "source": source,
    }
    duration = (props.get("Duration (sec)") or {}).get("number")
    if duration is not None:
        event["duration_seconds"] = int(duration)
    return event


def fetch_focus_events(start: date, end: date) -> list[dict]:
    """Focus events whose local date is within [start, end], de-duplicated by Event ID."""
    # Widen the Notion filter by a day on each side: Date stores UTC, `date` is local.
    flt = {"and": [
        {"or": [{"property": "Kind", "select": {"equals": k}} for k in FOCUS_KINDS]},
        {"property": "Date", "date": {"on_or_after": (start - timedelta(days=1)).isoformat()}},
        {"property": "Date", "date": {"on_or_before": (end + timedelta(days=1)).isoformat()}},
    ]}
    pages = notion_api.query_data_source(config.EVENTS_SYNC_DATA_SOURCE_ID, flt)

    events, seen = [], set()
    for page in pages:
        event = event_from_page(page)
        if not event or event["id"] in seen:
            continue
        if not (start.isoformat() <= event["date"] <= end.isoformat()):
            continue
        seen.add(event["id"])
        events.append(event)
    return events
