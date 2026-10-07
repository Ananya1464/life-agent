"""JSON-lines bridge between the Lifebot desktop app (Electron) and the Python agent.

Protocol (one JSON object per line):
    request:  {"id": 7, "method": "chat", "params": {...}}
    response: {"id": 7, "result": {...}}   or   {"id": 7, "error": "message"}

stdout carries ONLY protocol lines; everything else (library prints) goes to stderr. Requests run
on a small thread pool so a slow chat never blocks recording a focus session.

Run from the repo root so relative paths (data/events.jsonl) resolve:
    python -m life_agent.lifebot.bridge
"""
from __future__ import annotations

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

LIFEBOT_SOURCE = "lifebot"


def _today_iso() -> str:
    from life_agent import dates
    return dates.today().isoformat()


def _rid(params: dict, key: str = "task_id") -> str:
    """Stable intent id for one focus run: unique per run so repeated runs of a task are all kept."""
    task_id = str(params.get("task_id") or "adhoc")
    run_id = str(params.get("run_id") or "")
    return f"lifebot:{task_id}:{run_id}" if run_id else f"lifebot:{task_id}"


def handle_ping(params: dict) -> dict:
    return {"ok": True}


def _snapshot() -> dict | None:
    """Game stats before an action, to compute its reward. Never raises."""
    try:
        from life_agent import gamification
        return gamification.compute()
    except Exception as exc:
        print(f"[lifebot] game stats unavailable: {exc}")
        return None


def _with_reward(before: dict | None, result: dict) -> dict:
    if before is None:
        return result
    try:
        from life_agent import gamification
        result["reward"] = gamification.reward(before, gamification.compute())
    except Exception as exc:
        print(f"[lifebot] reward unavailable: {exc}")
    return result


def handle_game_stats(params: dict) -> dict:
    from life_agent import gamification
    return {k: v for k, v in gamification.compute().items() if k != "per_day"}


def handle_chat(params: dict) -> dict:
    from life_agent.lifebot import chat
    return chat.respond(params.get("message", ""), params.get("history"), params.get("state"))


def handle_record_focus(params: dict) -> dict:
    """phase: started | completed | abandoned. Completed/abandoned also trigger sync + dashboard."""
    from life_agent.events import event_model
    phase = params.get("phase")
    task = (params.get("task") or "").strip() or "(no task)"
    intent_id = _rid(params)
    base = {"date_iso": _today_iso(), "task": task, "intent_id": intent_id, "source": LIFEBOT_SOURCE}
    if phase == "started":
        event_model.record_focus_started(**base)
        return {"ok": True}
    if phase in ("completed", "abandoned"):
        duration = params.get("duration_seconds")
        if not isinstance(duration, (int, float)) or duration < 0:
            raise ValueError("duration_seconds must be a non-negative number")
        record = event_model.record_focus_completed if phase == "completed" else event_model.record_focus_abandoned
        before = _snapshot()
        record(duration_seconds=int(duration), **base)
        _after_session()
        return _with_reward(before, {"ok": True})
    raise ValueError("phase must be started, completed or abandoned")


def _after_session() -> None:
    """Refresh the Obsidian dashboard and focus log, without blocking. Sessions live in Obsidian only (no Notion push)."""
    from life_agent.obsidian import dashboard
    dashboard.refresh_in_background()


def handle_record_task(params: dict) -> dict:
    """status: planned | completed. Idempotent per task id and day."""
    from life_agent.events import event_model
    status = params.get("status")
    task = (params.get("task") or "").strip()
    task_id = str(params.get("task_id") or "")
    if not task or not task_id:
        raise ValueError("task and task_id are required")
    date_iso = _today_iso()
    if status == "planned":
        event_model.append_once(
            "task_planned",
            {"date": date_iso, "slot": LIFEBOT_SOURCE, "intent_id": task_id, "task": task,
             "life_area": None, "goal": None, "source": LIFEBOT_SOURCE},
            f"task_planned:{task_id}")
    elif status == "completed":
        before = _snapshot()
        event_model.record_task_completed(task, date_iso=date_iso, source=LIFEBOT_SOURCE, intent_id=task_id)
        _after_session()
        return _with_reward(before, {"ok": True})
    else:
        raise ValueError("status must be planned or completed")
    return {"ok": True}


def handle_refresh_dashboard(params: dict) -> dict:
    from life_agent.obsidian import dashboard
    return {"path": str(dashboard.write_dashboard())}


def handle_sync(params: dict) -> dict:
    from life_agent.desktop import sync
    return sync.sync_events()


HANDLERS = {
    "ping": handle_ping,
    "game_stats": handle_game_stats,
    "chat": handle_chat,
    "record_focus": handle_record_focus,
    "record_task": handle_record_task,
    "refresh_dashboard": handle_refresh_dashboard,
    "sync": handle_sync,
}


def dispatch(line: str) -> dict:
    """Process one request line into a response dict. Never raises."""
    req_id = None
    try:
        req = json.loads(line)
        req_id = req.get("id")
        handler = HANDLERS.get(req.get("method"))
        if handler is None:
            raise ValueError(f"unknown method: {req.get('method')}")
        return {"id": req_id, "result": handler(req.get("params") or {})}
    except Exception as exc:
        return {"id": req_id, "error": f"{type(exc).__name__}: {str(exc)[:300]}"}


def serve(stdin, out) -> None:
    lock = threading.Lock()

    def work(line: str) -> None:
        response = json.dumps(dispatch(line), default=str)
        with lock:
            out.write(response + "\n")
            out.flush()

    with ThreadPoolExecutor(max_workers=4) as pool:
        for line in stdin:
            line = line.strip()
            if line:
                pool.submit(work, line)


def main() -> int:
    proto_out = sys.stdout
    sys.stdout = sys.stderr  # keep stdout clean for the protocol
    os.environ.setdefault("NOTION_TOKEN", "")  # Notion features degrade instead of crashing the bridge
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    serve(sys.stdin, proto_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
