"""Local → Cloud event sync (one-way) — synced by event ID, not timestamp."""
import json
from pathlib import Path

from life_agent.integrations import notion_api
from life_agent import config
from life_agent.events import store


# Resolve path relative to this file's location (project root / data), not cwd
SYNCED_IDS_PATH = Path(__file__).parent.parent.parent.parent / "data" / ".synced_event_ids.json"


def _read_synced_ids() -> set[str]:
    """Read the set of event IDs that have been successfully synced."""
    if not SYNCED_IDS_PATH.exists():
        return set()
    try:
        data = json.loads(SYNCED_IDS_PATH.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except (json.JSONDecodeError, OSError):
        return set()


def _write_synced_ids(synced_ids: set[str]) -> None:
    """Write the set of synced event IDs."""
    SYNCED_IDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SYNCED_IDS_PATH.write_text(json.dumps(sorted(list(synced_ids)), ensure_ascii=False), encoding="utf-8")


def events_since_last_sync() -> list[dict]:
    """Return events whose id is NOT in the synced set."""
    synced = _read_synced_ids()
    all_events = store.load_all()
    return [e for e in all_events if e.get("id") not in synced]


def _event_exists_in_notion(event_id: str) -> bool:
    """Check if an event with this Event ID already exists in the Notion database.
    Returns True if exists, False if confirmed not exists, raises if check failed."""
    if not config.EVENTS_SYNC_DATA_SOURCE_ID:
        return False
    try:
        data = notion_api._req("POST", f"/data_sources/{config.EVENTS_SYNC_DATA_SOURCE_ID}/query",
                               json={"filter": {"property": "Event ID", "rich_text": {"equals": event_id}}})
        results = data.get("results", [])
        return len(results) > 0
    except Exception as e:
        print(f"[sync] ERROR: existence check failed for event_id={event_id}: {e}")
        raise


def _build_notion_properties(event: dict) -> dict:
    """Map local event to Notion database properties."""
    kind = event.get("kind", "")
    ts = event.get("ts", "")
    date_iso = ts[:10] if ts else ""

    props = {
        "Name": {"title": [{"text": {"content": event.get("task", event.get("text", "event"))[:100]}}]},
        "Date": {"date": {"start": date_iso}} if date_iso else {"date": None},
        "Kind": {"select": {"name": kind}} if kind else {"select": None},
        "Task": {"rich_text": [{"text": {"content": event.get("task", event.get("text", ""))[:2000]}}]},
        "Source": {"select": {"name": event.get("source", "unknown")}} if event.get("source") else {"select": None},
        "Event ID": {"rich_text": [{"text": {"content": event.get("id", "")}}]},
    }

    # Optional fields
    if event.get("intent_id"):
        props["Intent ID"] = {"rich_text": [{"text": {"content": event["intent_id"]}}]}
    # Duration (sec) omitted - Notion database may not have this property

    # Remove None values - safely handle nested dicts
    filtered = {}
    for k, v in props.items():
        keep = False
        if isinstance(v, dict):
            if "title" in v and v["title"] and v["title"][0].get("text", {}).get("content"):
                keep = True
            elif "date" in v and v["date"] and v["date"].get("start"):
                keep = True
            elif "select" in v and v["select"] and v["select"].get("name"):
                keep = True
            elif "rich_text" in v and v["rich_text"] and v["rich_text"][0].get("text", {}).get("content"):
                keep = True
            elif "number" in v and v["number"] is not None:
                keep = True
        if keep:
            filtered[k] = v
    return filtered


def push_to_cloud(events: list[dict]) -> tuple[list[str], list[tuple[str, str]], list[tuple[str, str]]]:
    """Push events to Notion Events database.
    Returns (success_event_ids, failed_list, existence_check_failed_list) where:
    - success_event_ids = list of event 'id' for each succeeded event (including dedup-skipped)
    - failed_list = [(event_id, error_msg), ...] for push failures
    - existence_check_failed_list = [(event_id, error_msg), ...] for existence check failures"""
    if not config.EVENTS_SYNC_DB_ID or not config.EVENTS_SYNC_DATA_SOURCE_ID:
        raise ValueError("EVENTS_SYNC_DB_ID or EVENTS_SYNC_DATA_SOURCE_ID not configured in config.py")

    success_ids = []
    failed = []
    existence_check_failed = []

    for event in events:
        event_id = event.get("id", "unknown")
        try:
            # Defense in depth: check Notion for existing row with this Event ID
            if _event_exists_in_notion(event_id):
                success_ids.append(event_id)
                continue

            props = _build_notion_properties(event)
            notion_api.append_to_database(config.EVENTS_SYNC_DB_ID, props)
            success_ids.append(event_id)
        except RuntimeError as e:
            if "existence check failed" in str(e).lower() or "existence check" in str(e).lower():
                existence_check_failed.append((event_id, str(e)[:200]))
            else:
                failed.append((event_id, str(e)[:200]))
        except Exception as e:
            failed.append((event_id, str(e)[:200]))

    return success_ids, failed, existence_check_failed


def mark_synced(success_ids: list[str]) -> None:
    """Add successfully synced event IDs to the synced set."""
    if not success_ids:
        return
    synced = _read_synced_ids()
    synced.update(success_ids)
    _write_synced_ids(synced)


def sync_events() -> dict:
    """Main sync entry point. Returns summary dict."""
    events = events_since_last_sync()

    if not events:
        return {"pushed": 0, "failed": 0, "skipped_empty": True}

    success_ids, failed, existence_check_failed = push_to_cloud(events)

    # Record all successful syncs (including those skipped by dedup guard)
    mark_synced(success_ids)

    return {
        "pushed": len(success_ids),
        "failed": len(failed),
        "existence_check_failed": len(existence_check_failed),
        "skipped_empty": False,
        "failed_details": failed,
        "existence_check_failed_details": existence_check_failed,
    }