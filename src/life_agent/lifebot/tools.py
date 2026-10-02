"""Tools Lifebot can call from chat.

Every tool is `fn(args: dict, state: dict) -> ToolResult`. Tools never mutate app state directly:
anything the desktop app must do (add a reminder, start a focus session) is returned as an
*action* that the app applies, so the app stays the single owner of tasks and reminders.

`state` is a snapshot the app sends with each message:
    {"tasks": [{"id", "text", "checked"}], "reminders": [{"id", "text", "at", "repeat", "status"}]}
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from life_agent import dates

REPEATS = ("none", "daily", "weekdays")


@dataclass
class ToolResult:
    text: str
    actions: list[dict] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(dates.TZ)


def parse_when(value: str, now: datetime | None = None) -> datetime:
    """Parse an ISO datetime (naive = local time). Raises ValueError if unusable or in the past."""
    now = now or _now()
    if not isinstance(value, str) or not value.strip():
        raise ValueError("'at' must be an ISO datetime like 2026-10-02T09:00")
    try:
        when = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"Could not read '{value}' as a datetime; use ISO format like 2026-10-02T09:00")
    if when.tzinfo is None:
        when = when.replace(tzinfo=dates.TZ)
    if when < now - timedelta(minutes=1):
        raise ValueError(f"{when.isoformat(timespec='minutes')} is in the past (now is "
                         f"{now.isoformat(timespec='minutes')})")
    return when.astimezone(dates.TZ)


def focus_summary(args: dict, state: dict) -> ToolResult:
    from life_agent.agent import activity_context
    ctx = activity_context.build()
    parts = [ctx.summary]
    if ctx.patterns:
        parts.append("Patterns:\n" + ctx.patterns)
    return ToolResult("\n".join(parts))


def read_note(args: dict, state: dict) -> ToolResult:
    from life_agent.tools import deterministic_tools
    path = (args.get("path") or "").strip()
    if not path:
        return ToolResult("Error: 'path' is required.")
    try:
        text = deterministic_tools.read_vault_note(path)
    except (ValueError, FileNotFoundError) as exc:
        return ToolResult(f"Error: {exc}")
    return ToolResult(text[:6000] + ("\n[truncated]" if len(text) > 6000 else ""))


def list_notes(args: dict, state: dict) -> ToolResult:
    from life_agent.tools import deterministic_tools
    try:
        notes = deterministic_tools.list_vault_notes((args.get("folder") or "").strip())
    except (ValueError, FileNotFoundError) as exc:
        return ToolResult(f"Error: {exc}")
    shown = notes[:60]
    return ToolResult("\n".join(shown) + (f"\n[{len(notes) - 60} more]" if len(notes) > 60 else "")
                      or "No notes found.")


def list_tasks(args: dict, state: dict) -> ToolResult:
    tasks = state.get("tasks") or []
    if not tasks:
        return ToolResult("No tasks yet.")
    return ToolResult("\n".join(f"- [{'x' if t.get('checked') else ' '}] {t.get('text')} (id {t.get('id')})"
                                for t in tasks))


def list_reminders(args: dict, state: dict) -> ToolResult:
    items = [r for r in (state.get("reminders") or []) if r.get("status") != "done"]
    if not items:
        return ToolResult("No upcoming reminders.")
    return ToolResult("\n".join(
        f"- {r.get('text')} at {r.get('at')}" + (f" (repeats {r['repeat']})" if r.get("repeat", "none") != "none" else "")
        for r in sorted(items, key=lambda r: r.get("at") or "")))


def add_reminder(args: dict, state: dict) -> ToolResult:
    text = (args.get("text") or "").strip()
    repeat = (args.get("repeat") or "none").strip().lower()
    if not text:
        return ToolResult("Error: 'text' is required.")
    if repeat not in REPEATS:
        return ToolResult(f"Error: 'repeat' must be one of {', '.join(REPEATS)}.")
    try:
        when = parse_when(args.get("at"))
    except ValueError as exc:
        return ToolResult(f"Error: {exc}")
    iso = when.isoformat(timespec="minutes")
    return ToolResult(f"Reminder set: '{text}' at {iso}.",
                      [{"type": "add_reminder", "text": text, "at": iso, "repeat": repeat}])


def add_task(args: dict, state: dict) -> ToolResult:
    text = (args.get("text") or "").strip()
    if not text:
        return ToolResult("Error: 'text' is required.")
    return ToolResult(f"Task added: '{text}'.", [{"type": "add_task", "text": text}])


def start_focus(args: dict, state: dict) -> ToolResult:
    wanted = (args.get("task") or "").strip().lower()
    open_tasks = [t for t in (state.get("tasks") or []) if not t.get("checked")]
    match = next((t for t in open_tasks if t.get("id") == args.get("task")), None) \
        or next((t for t in open_tasks if (t.get("text") or "").strip().lower() == wanted), None) \
        or next((t for t in open_tasks if wanted and wanted in (t.get("text") or "").lower()), None)
    if not match:
        return ToolResult("Error: no open task matches that. Use list_tasks first or add_task.")
    return ToolResult(f"Starting a focus session on '{match['text']}'.",
                      [{"type": "start_focus", "taskId": match["id"], "text": match["text"]}])


TOOLS = {
    "focus_summary": (focus_summary, "Facts about her focus sessions over the last 7 days.", {}),
    "list_tasks": (list_tasks, "Her current task list.", {}),
    "list_reminders": (list_reminders, "Her upcoming reminders.", {}),
    "add_task": (add_task, "Add a task to her list.", {"text": "task text"}),
    "add_reminder": (add_reminder, "Create a reminder. 'at' is a local ISO datetime in the future; "
                     "'repeat' is none, daily or weekdays.",
                     {"text": "what to remind", "at": "2026-10-02T09:00", "repeat": "none"}),
    "start_focus": (start_focus, "Start a 25-minute focus session on one of her open tasks.",
                    {"task": "task text or id"}),
    "list_notes": (list_notes, "List notes in her Obsidian vault (read-only).", {"folder": "optional subfolder"}),
    "read_note": (read_note, "Read one vault note by relative path (read-only).", {"path": "relative/path.md"}),
}


def describe_tools() -> str:
    lines = []
    for name, (_, desc, params) in TOOLS.items():
        arg_text = ", ".join(f'"{k}": "{v}"' for k, v in params.items())
        lines.append(f'- {name}({{{arg_text}}}): {desc}')
    return "\n".join(lines)


def run_tool(name: str, args: dict, state: dict) -> ToolResult:
    entry = TOOLS.get(name)
    if not entry:
        return ToolResult(f"Error: unknown tool '{name}'. Available: {', '.join(TOOLS)}.")
    if not isinstance(args, dict):
        return ToolResult("Error: 'args' must be an object.")
    try:
        return entry[0](args, state)
    except Exception as exc:  # a broken tool must not take the chat down
        return ToolResult(f"Error: {name} failed ({type(exc).__name__}).")
