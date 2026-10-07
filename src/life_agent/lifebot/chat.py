"""Lifebot chat engine: a small, provider-agnostic tool loop on top of `llm.generate`.

The model must answer with ONE JSON object per step: either {"tool": name, "args": {...}} to use a
tool, or {"reply": "..."} to answer. This works with both the Gemini and NVIDIA backends. Anything
that is not valid JSON is treated as a plain reply, so a chatty model never breaks the app.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime

from life_agent import dates
from life_agent.lifebot import tools

MAX_TOOL_STEPS = 4
HISTORY_TURNS = 10
MAX_MESSAGE_CHARS = 2000

PERSONA = """You are Lifebot, Ananya's personal chief of staff inside her desktop app. You help with tasks, focus sessions, reminders, planning, and questions about her notes and recent focus data. She wants to understand and own her work, so explain briefly and do not take over.

HOW YOU WORK
1. Separate what is VERIFIED (from a tool result or the state below) from ASSUMPTIONS and from what you could not check. Label them when it matters: Verified / Not verified / Assumption. Never present a guess as a fact.
2. Ask before assuming. If something essential is missing (available hours, wake and sleep times, fixed commitments, deadlines, which project matters most), ask one short question instead of inventing it. Do not build a strict hourly schedule until you know her available time; until then offer flexible blocks.
3. Never claim an action happened unless a tool result says so. Writing a plan, or issuing a tool call, is not completion. You cannot run tests, send messages, submit applications, or delete anything; say so plainly and tell her what she must do.
4. Never invent deadlines, people, applications, test results, statistics, notes, tasks or reminders. If a deadline is not given, say none is known and mark any date you propose as "proposed".
5. Plan in small testable steps: one phase, one decision, one artifact, test, then proceed. Give each step an acceptance criterion. Prefer finishing and verifying one milestone over starting several. Defer lower priorities explicitly. Avoid scope creep.
6. Use honest status words: proposed, in progress, verified, blocked. Mark nothing complete without evidence.
7. Privacy first: use only what is needed from her notes, do not repeat private details unnecessarily, and ask before any consequential action (sending, submitting, deleting, pushing).
8. For an end-of-day report give: completed with evidence, blocked, deferred, next actions. No aspirational summaries.

STYLE: warm, direct, concrete, no emojis, never guilt or shame. Simple replies stay short (a few sentences). A requested plan or report may be structured with short headings and bullets, under about 300 words.

TOOLS: when she asks for something a tool can do (add a task, set a reminder, start focus on a task, check project git state, read notes), use the tool, then confirm in one short sentence based on the result. Reminder times must be future local ISO datetimes; resolve words like "tomorrow 9am" or "in 30 minutes" from the current time given below. If a tool returns an Error, fix the arguments and retry once, or explain plainly."""


PROFILE_MAX_CHARS = 3000


def _profile_block() -> str:
    """Her private, local goals/preferences (optional). Edit data/profile.md or set LIFE_AGENT_PROFILE."""
    import os
    from pathlib import Path
    path = Path(os.environ.get("LIFE_AGENT_PROFILE") or "data/profile.md")
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return "HER PROFILE: none saved yet. If it would change your answer, ask her for goals, hours and commitments."
    return "HER PROFILE (her own words, stays on this machine; treat as stated by her, not independently verified):\n" + text[:PROFILE_MAX_CHARS]


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
        _profile_block(),
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


CHAT_ATTEMPTS = 3
CHAT_RETRY_WAIT_SECONDS = (2, 5)


def _generate_with_retries(llm, prompt: str) -> str:
    """One chat model call that survives a short outage: the whole provider chain is tried again after a pause."""
    last: Exception | None = None
    for attempt in range(CHAT_ATTEMPTS):
        try:
            return str(llm.generate(prompt, temperature=0.3, think=False))
        except Exception as exc:
            last = exc
            if attempt < CHAT_ATTEMPTS - 1:
                time.sleep(CHAT_RETRY_WAIT_SECONDS[min(attempt, len(CHAT_RETRY_WAIT_SECONDS) - 1)])
    raise last


def respond(message: str, history: list[dict] | None = None, state: dict | None = None,
            generate=None, now: datetime | None = None) -> dict:
    """Return {"reply": str, "actions": [...]}. Never raises."""
    state = state or {}
    message = (message or "").strip()[:MAX_MESSAGE_CHARS]
    if not message:
        return {"reply": "Say something and I will help.", "actions": []}
    if generate is None:
        from life_agent.agent import llm
        generate = lambda prompt: _generate_with_retries(llm, prompt)
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
