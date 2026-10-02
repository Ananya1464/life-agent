"""Lifebot chat engine: a small, provider-agnostic tool loop on top of `llm.generate`.

The model must answer with ONE JSON object per step: either {"tool": name, "args": {...}} to use a
tool, or {"reply": "..."} to answer. This works with both the Gemini and NVIDIA backends. Anything
that is not valid JSON is treated as a plain reply, so a chatty model never breaks the app.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from life_agent import dates
from life_agent.lifebot import tools

MAX_TOOL_STEPS = 4
HISTORY_TURNS = 10
MAX_MESSAGE_CHARS = 2000

PERSONA = """You are Lifebot, Ananya's personal assistant inside her desktop app. You help with her tasks, \
focus sessions, reminders, and questions about her notes and recent focus data.

Style: warm, brief, practical; at most a few sentences. No emojis. Never use guilt or shame about missed \
work. Only state facts you got from tools or from the state below; if you do not know, say so. Never \
invent tasks, notes, reminders, or statistics.

When she asks for something you can do with a tool (add a task, set a reminder, start focus on a task), \
do it with the tool, then confirm in one short sentence. Reminder times must be future local ISO \
datetimes; resolve words like "tomorrow 9am" or "in 30 minutes" from the current time given below. \
If a tool returns an Error, fix the arguments and retry once, or explain plainly."""


def _extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of a model reply (handles ```json fences and chatter)."""
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    candidates = [fenced.group(1)] if fenced else []
    candidates.append(text)
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            depth += text[i] == "{"
            depth -= text[i] == "}"
            if depth == 0:
                candidates.append(text[start:i + 1])
                break
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _state_block(state: dict) -> str:
    tasks = state.get("tasks") or []
    reminders = [r for r in (state.get("reminders") or []) if r.get("status") != "done"]
    task_lines = "\n".join(f"- [{'x' if t.get('checked') else ' '}] {t.get('text')} (id {t.get('id')})"
                           for t in tasks[:40]) or "(none)"
    rem_lines = "\n".join(f"- {r.get('text')} at {r.get('at')}" for r in reminders[:20]) or "(none)"
    return f"TASKS:\n{task_lines}\n\nUPCOMING REMINDERS:\n{rem_lines}"


def _build_prompt(message: str, history: list[dict], state: dict, scratch: list[str], now: datetime) -> str:
    convo = "\n".join(
        f"{'Ananya' if h.get('role') == 'user' else 'Lifebot'}: {str(h.get('text', ''))[:MAX_MESSAGE_CHARS]}"
        for h in (history or [])[-HISTORY_TURNS:])
    parts = [
        PERSONA,
        f"Current local time: {now.strftime('%A %Y-%m-%d %H:%M')} ({dates.TZ.key}).",
        _state_block(state),
        "TOOLS:\n" + tools.describe_tools(),
        'Answer with ONE JSON object only: {"tool": "<name>", "args": {...}} or {"reply": "<text for Ananya>"}.',
    ]
    if convo:
        parts.append("CONVERSATION SO FAR:\n" + convo)
    parts.append(f"Ananya: {message}")
    if scratch:
        parts.append("TOOL RESULTS SO FAR:\n" + "\n".join(scratch))
    parts.append("Lifebot (JSON only):")
    return "\n\n".join(parts)


def respond(message: str, history: list[dict] | None = None, state: dict | None = None,
            generate=None, now: datetime | None = None) -> dict:
    """Return {"reply": str, "actions": [...]}. Never raises."""
    state = state or {}
    message = (message or "").strip()[:MAX_MESSAGE_CHARS]
    if not message:
        return {"reply": "Say something and I will help.", "actions": []}
    if generate is None:
        from life_agent.agent import llm
        generate = lambda prompt: str(llm.generate(prompt, temperature=0.3, think=False))
    now = now or datetime.now(dates.TZ)

    actions: list[dict] = []
    scratch: list[str] = []
    try:
        for _ in range(MAX_TOOL_STEPS + 1):
            raw = generate(_build_prompt(message, history or [], state, scratch, now))
            obj = _extract_json(raw)
            if obj is None:
                return {"reply": (raw or "").strip() or "Sorry, I had nothing to say.", "actions": actions}
            if "reply" in obj:
                return {"reply": str(obj["reply"]).strip(), "actions": actions}
            name = obj.get("tool")
            if not name:
                return {"reply": (raw or "").strip(), "actions": actions}
            result = tools.run_tool(str(name), obj.get("args") or {}, state)
            actions.extend(result.actions)
            scratch.append(f"{name} -> {result.text}")
        return {"reply": "I could not finish that. Could you rephrase it?", "actions": actions}
    except Exception as exc:
        print(f"[lifebot] chat failed: {type(exc).__name__}: {str(exc)[:200]}")
        return {"reply": "I could not reach my brain just now (the AI service may be down). "
                         "Your tasks and reminders still work. Try again in a minute.",
                "actions": actions}
