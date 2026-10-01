"""Deterministic parser for the Life OS master sequencing checklist (§6 of
``docs/life_os_master_architecture.md``).

The dashboard's workstreams panel is generated from this — the markdown
document stays the single source of truth, and status is never invented here.
"""
from __future__ import annotations

import pathlib
import re

CHECKLIST_PATH = pathlib.Path("docs/life_os_master_architecture.md")
CHECKLIST_HEADING = "## 6. Master sequencing checklist"
SECTION_END_HEADING = "## 7."

_ITEM_RE = re.compile(r"^- \[( |x|X)\] (.+)$")


def _extract_section(text: str) -> str:
    start = text.find(CHECKLIST_HEADING)
    if start == -1:
        return ""
    start = text.find("\n", start) + 1
    end = text.find(SECTION_END_HEADING, start)
    return text[start:end] if end != -1 else text[start:]


def read_master_checklist(path: str | pathlib.Path = CHECKLIST_PATH) -> list[dict]:
    """Parse the §6 checklist into ``{label, done, note}`` records.

    Raises ``FileNotFoundError`` when the document is missing — a missing
    source is reported as missing, never silently replaced by defaults.
    """
    text = pathlib.Path(path).read_text(encoding="utf-8")
    items: list[dict] = []
    for line in _extract_section(text).splitlines():
        match = _ITEM_RE.match(line.strip())
        if not match:
            continue
        checked, rest = match.group(1), match.group(2)
        note = ""
        if " — " in rest:
            rest, note = rest.split(" — ", 1)
            note = note.strip().strip("*").strip()
        items.append({"label": rest.strip(), "done": checked.lower() == "x", "note": note})
    return items


def workstreams_status(path: str | pathlib.Path = CHECKLIST_PATH) -> dict:
    """Summarize the checklist: items, progress counts, and the current step."""
    items = read_master_checklist(path)
    done = sum(1 for item in items if item["done"])
    return {
        "items": items,
        "done": done,
        "total": len(items),
        "current": next((item["label"] for item in items if not item["done"]), None),
        "complete": bool(items) and done == len(items),
    }
