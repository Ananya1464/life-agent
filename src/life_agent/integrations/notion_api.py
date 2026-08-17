"""Minimal Notion API client (no SDK) for the Daily Log + Weight Loss page.

Uses Notion API version 2025-09-03 (data sources). The integration token must
be granted access to both the "🌱 Daily Life Tracker" page and the
"Weight Loss Plan" page (Share → connections → your integration).
"""
import json
import re

import requests

from life_agent import config
from life_agent.events import store

BASE = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {config.NOTION_TOKEN}",
    "Notion-Version": "2025-09-03",
    "Content-Type": "application/json",
}


def _req(method: str, path: str, **kwargs):
    r = requests.request(method, f"{BASE}{path}", headers=HEADERS, timeout=30, **kwargs)
    if not r.ok:
        raise RuntimeError(f"Notion {method} {path} failed {r.status_code}: {r.text[:500]}")
    return r.json()


# ---------------------------------------------------------------- markdown → blocks
def _rich(text: str):
    """Plain text with basic **bold** support."""
    parts, out = re.split(r"(\*\*[^*]+\*\*)", text), []
    for p in parts:
        if not p:
            continue
        if p.startswith("**") and p.endswith("**"):
            out.append({"type": "text", "text": {"content": p[2:-2]},
                        "annotations": {"bold": True}})
        else:
            out.append({"type": "text", "text": {"content": p[:2000]}})
    return out or [{"type": "text", "text": {"content": ""}}]


def md_to_blocks(md: str):
    blocks = []
    for line in md.splitlines():
        s = line.rstrip()
        if not s.strip():
            continue
        if s.startswith("## "):
            blocks.append({"type": "heading_2", "heading_2": {"rich_text": _rich(s[3:])}})
        elif s.startswith("### "):
            blocks.append({"type": "heading_3", "heading_3": {"rich_text": _rich(s[4:])}})
        elif s.strip() == "---":
            blocks.append({"type": "divider", "divider": {}})
        elif s.startswith("> "):
            blocks.append({"type": "quote", "quote": {"rich_text": _rich(s[2:])}})
        elif s.lstrip().startswith(("- ", "* ")):
            blocks.append({"type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": _rich(s.lstrip()[2:])}})
        elif re.match(r"^\d+\.\s", s.lstrip()):
            blocks.append({"type": "numbered_list_item",
                           "numbered_list_item": {"rich_text": _rich(re.sub(r"^\d+\.\s", "", s.lstrip()))}})
        else:
            blocks.append({"type": "paragraph", "paragraph": {"rich_text": _rich(s)}})
    return blocks


def _block_text(block: dict) -> str:
    t = block.get("type", "")
    rich = block.get(t, {}).get("rich_text", [])
    return "".join(x.get("plain_text", "") for x in rich)


# ---------------------------------------------------------------- Daily Log queries
def find_entry_by_date(date_iso: str):
    """Return the Daily Log page whose Date property equals date_iso, or None."""
    data = _req("POST", f"/data_sources/{config.DAILY_LOG_DATA_SOURCE_ID}/query",
                json={"filter": {"property": "Date", "date": {"equals": date_iso}}})
    results = data.get("results", [])
    return results[0] if results else None


def get_prop_text(page: dict, prop_name: str) -> str:
    prop = page.get("properties", {}).get(prop_name, {})
    rich = prop.get("rich_text") or prop.get("title") or []
    return "".join(x.get("plain_text", "") for x in rich)


def create_daily_entry(day_label: str, date_iso: str, body_md: str) -> str:
    """Create a new Daily Log row. Returns the new page id."""
    page = _req("POST", "/pages", json={
        "parent": {"type": "data_source_id",
                   "data_source_id": config.DAILY_LOG_DATA_SOURCE_ID},
        "properties": {
            "Day": {"title": [{"type": "text", "text": {"content": day_label}}]},
            "Date": {"date": {"start": date_iso}},
        },
        "children": md_to_blocks(body_md),
    })
    return page["id"]


# ---------------------------------------------------------------- section editing
def _children(page_id: str):
    blocks, cursor = [], None
    while True:
        path = f"/blocks/{page_id}/children?page_size=100"
        if cursor:
            path += f"&start_cursor={cursor}"
        data = _req("GET", path)
        blocks += data.get("results", [])
        if not data.get("has_more"):
            return blocks
        cursor = data.get("next_cursor")


def _section_range(blocks, heading_contains: str):
    """Indexes of (heading block, blocks belonging to that section)."""
    start = None
    for i, b in enumerate(blocks):
        if b.get("type") == "heading_2" and heading_contains in _block_text(b):
            start = i
            break
    if start is None:
        return None, []
    body = []
    for b in blocks[start + 1:]:
        if b.get("type") in ("heading_2", "divider"):
            break
        body.append(b)
    return start, body


def get_section_text(page_id: str, heading_contains: str) -> str:
    blocks = _children(page_id)
    _, body = _section_range(blocks, heading_contains)
    return "\n".join(_block_text(b) for b in body).strip()


def replace_section(page_id: str, heading_contains: str, new_md: str):
    """Replace the content under a '## heading' (up to next heading/divider)."""
    blocks = _children(page_id)
    idx, body = _section_range(blocks, heading_contains)
    if idx is None:
        # Heading missing — just append heading + content at the end.
        _req("PATCH", f"/blocks/{page_id}/children",
             json={"children": md_to_blocks(f"## {heading_contains}\n{new_md}")})
        return
    for b in body:
        _req("DELETE", f"/blocks/{b['id']}")
    _req("PATCH", f"/blocks/{page_id}/children",
         json={"children": md_to_blocks(new_md), "after": blocks[idx]["id"]})


def append_to_page(page_id: str, md: str):
    _req("PATCH", f"/blocks/{page_id}/children", json={"children": md_to_blocks(md)})


def sync_event(event: dict) -> str:
    """Mirror one parsed reply into Notion and record the sync event."""
    if not config.REPLIES_DB_ID:
        raise ValueError("REPLIES_DB_ID not configured")

    event_id = event.get("id")
    if not event_id:
        raise ValueError("sync_event requires event['id']")

    for ev in store.load_all():
        if ev.get("kind") == "notion_synced" and ev.get("event_id") == event_id:
            return ev.get("notion_page_id", "")

    date_iso = (event.get("ts") or "")[:10]
    if not date_iso:
        raise ValueError("sync_event requires event['ts']")

    slot = event.get("slot")
    if not slot:
        token = event.get("token", "")
        slot = {"M": "morning", "D": "midday", "E": "evening"}.get(token[-1:], "")

    page = _req("POST", "/pages", json={
        "parent": {"database_id": config.REPLIES_DB_ID},
        "properties": {
            "Date": {"date": {"start": date_iso}},
            "Slot": {"select": {"name": slot}},
            "Energy": {"number": event.get("energy")},
            "Sleep": {"number": event.get("sleep_hours")},
            "Soreness": {"select": {"name": event.get("soreness")}} if event.get("soreness") else {"select": None},
            "Tasks": {"rich_text": [{"text": {"content": json.dumps(event.get("checkins", []), ensure_ascii=False)[:2000]}}]},
            "Captures": {"rich_text": [{"text": {"content": json.dumps(event.get("captures", []), ensure_ascii=False)[:2000]}}]},
            "Raw Reply": {"rich_text": [{"text": {"content": (event.get("raw_text") or "")[:2000]}}]},
        },
    })

    store.append("notion_synced", {"event_id": event_id, "notion_page_id": page["id"]})
    return page["id"]


# ---------------------------------------------------------------- range queries
def find_entries_range(start_iso: str, end_iso: str) -> list[dict]:
    """Return Daily Log pages whose Date is between start_iso and end_iso (inclusive)."""
    data = _req("POST", f"/data_sources/{config.DAILY_LOG_DATA_SOURCE_ID}/query",
                json={"filter": {"and": [
                    {"property": "Date", "date": {"on_or_after": start_iso}},
                    {"property": "Date", "date": {"on_or_before": end_iso}},
                ]}})
    return data.get("results", [])


# ---------------------------------------------------------------- reminders
def create_reminder_entry(title: str, remind_at_iso: str):
    """Create a page in the Reminders database with a date+reminder property."""
    if not config.REMINDERS_DB_ID:
        return
    _req("POST", "/pages", json={
        "parent": {"database_id": config.REMINDERS_DB_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": title}}]},
            "When": {"date": {"start": remind_at_iso,
                              "reminder": {"value": 0, "unit": "minute"}}},
        },
    })


# ---------------------------------------------------------------- evening check-in
def create_checkin_entry(day_label: str, date_iso: str, body_md: str) -> str:
    """Create a new row in the Evening Check-in database. Returns the page id."""
    if not config.EVENING_CHECKIN_DB_ID:
        return ""
    page = _req("POST", "/pages", json={
        "parent": {"database_id": config.EVENING_CHECKIN_DB_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": f"🌙 {day_label}"}}]},
            "Date": {"date": {"start": date_iso}},
            "Energy Level": {"rich_text": [{"text": {"content": ""}}]},
        },
        "children": md_to_blocks(body_md),
    })
    return page["id"]


def find_checkin_by_date(date_iso: str):
    """Return the Evening Check-in entry for date_iso, or None."""
    if not config.EVENING_CHECKIN_DB_ID:
        return None
    data = _req("POST", f"/databases/{config.EVENING_CHECKIN_DB_ID}/query",
                json={"filter": {"property": "Date", "date": {"equals": date_iso}}})
    results = data.get("results", [])
    return results[0] if results else None


# ---------------------------------------------------------------- ADHD tools
def fetch_dopamine_menu_items() -> list[str]:
    """Fetch all items from the Dopamine Menu database."""
    if not config.DOPAMINE_MENU_DB_ID:
        return []
    data = _req("POST", f"/databases/{config.DOPAMINE_MENU_DB_ID}/query", json={})
    items = []
    for row in data.get("results", []):
        name = get_prop_text(row, "Name")
        if name:
            items.append(name)
    return items


def write_brain_dump(content: str):
    """Write a new entry to the Brain Dump database."""
    if not config.BRAIN_DUMP_DB_ID:
        return
    _req("POST", "/pages", json={
        "parent": {"database_id": config.BRAIN_DUMP_DB_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": content[:50] + ("..." if len(content) > 50 else "")}}]},
        },
        "children": md_to_blocks(content),
    })
