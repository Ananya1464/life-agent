"""Tests for Lifebot: tools, chat tool-loop, and the JSON-lines bridge (no network, no real LLM)."""
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from life_agent import dates
from life_agent.lifebot import bridge, chat, tools

NOW = datetime(2026, 10, 1, 21, 0, tzinfo=dates.TZ)
STATE = {
    "tasks": [{"id": "t1", "text": "Write the report", "checked": False},
              {"id": "t2", "text": "Email professor", "checked": True}],
    "reminders": [{"id": "r1", "text": "Stretch", "at": "2026-10-02T08:00+05:30", "repeat": "daily", "status": "pending"},
                  {"id": "r2", "text": "Old", "at": "2026-09-01T08:00+05:30", "repeat": "none", "status": "done"}],
}


class Script:
    """Fake LLM: returns canned replies in order and records the prompts it saw."""
    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.replies.pop(0)


# ---------------------------------------------------------------- tools
def test_parse_when_accepts_naive_local_and_rejects_past():
    assert tools.parse_when("2026-10-02T09:00", NOW).isoformat() == "2026-10-02T09:00:00+05:30"
    with pytest.raises(ValueError, match="past"):
        tools.parse_when("2026-09-30T09:00", NOW)
    for bad in ("", "tomorrow", None):
        with pytest.raises(ValueError):
            tools.parse_when(bad, NOW)


def test_add_reminder_returns_action_and_validates(monkeypatch):
    monkeypatch.setattr(tools, "_now", lambda: NOW)
    ok = tools.add_reminder({"text": "Call mum", "at": "2026-10-02T18:30", "repeat": "daily"}, {})
    assert ok.actions == [{"type": "add_reminder", "text": "Call mum", "at": "2026-10-02T18:30+05:30", "repeat": "daily"}]
    assert tools.add_reminder({"text": "x", "at": "2026-10-02T18:30", "repeat": "monthly"}, {}).actions == []
    assert "past" in tools.add_reminder({"text": "x", "at": "2026-01-01T00:00"}, {}).text
    assert tools.add_reminder({"at": "2026-10-02T18:30"}, {}).text.startswith("Error")


def test_start_focus_matches_open_tasks_only():
    by_id = tools.start_focus({"task": "t1"}, STATE)
    assert by_id.actions == [{"type": "start_focus", "taskId": "t1", "text": "Write the report"}]
    assert tools.start_focus({"task": "report"}, STATE).actions[0]["taskId"] == "t1"      # fuzzy
    assert tools.start_focus({"task": "Email professor"}, STATE).actions == []            # already done
    assert tools.start_focus({"task": ""}, STATE).actions == []


def test_list_tools_summarise_state():
    assert "Write the report" in tools.list_tasks({}, STATE).text and "[x] Email professor" in tools.list_tasks({}, STATE).text
    text = tools.list_reminders({}, STATE).text
    assert "Stretch" in text and "daily" in text and "Old" not in text   # done reminders hidden


def test_vault_tools_report_errors_instead_of_raising():
    assert tools.read_note({"path": "../secret.md"}, {}).text.startswith("Error")
    assert tools.read_note({}, {}).text.startswith("Error")


def test_unknown_tool_and_crashing_tool_are_contained(monkeypatch):
    assert "unknown tool" in tools.run_tool("nope", {}, {}).text
    monkeypatch.setitem(tools.TOOLS, "boom", (lambda a, s: 1 / 0, "d", {}))
    assert "failed" in tools.run_tool("boom", {}, {}).text
    assert tools.run_tool("add_task", "notadict", {}).text.startswith("Error")


# ---------------------------------------------------------------- chat loop
def test_plain_reply():
    out = chat.respond("hi", generate=Script('{"reply": "Hello Ananya"}'), now=NOW)
    assert out == {"reply": "Hello Ananya", "actions": []}


def test_tool_then_reply_collects_actions(monkeypatch):
    monkeypatch.setattr(tools, "_now", lambda: NOW)
    gen = Script('{"tool": "add_reminder", "args": {"text": "Stretch", "at": "2026-10-02T08:00", "repeat": "none"}}',
                 '{"reply": "Done, I will remind you at 8."}')
    out = chat.respond("remind me tomorrow 8am to stretch", state=STATE, generate=gen, now=NOW)
    assert out["reply"] == "Done, I will remind you at 8."
    assert out["actions"][0]["type"] == "add_reminder"
    assert "Reminder set" in gen.prompts[1]          # tool result is fed back to the model


def test_prompt_contains_time_state_and_history():
    gen = Script('{"reply": "ok"}')
    chat.respond("what next?", history=[{"role": "user", "text": "earlier question"}], state=STATE, generate=gen, now=NOW)
    p = gen.prompts[0]
    assert "Thursday 2026-10-01 21:00" in p and "Write the report" in p and "Stretch" in p
    assert "Ananya: earlier question" in p and "Ananya: what next?" in p


@pytest.mark.parametrize("raw, expected", [
    ('```json\n{"reply": "fenced"}\n```', "fenced"),
    ('Sure! {"reply": "chatty"} hope that helps', "chatty"),
    ("just plain words, no json", "just plain words, no json"),
])
def test_tolerates_messy_model_output(raw, expected):
    assert chat.respond("x", generate=Script(raw), now=NOW)["reply"] == expected


def test_tool_loop_is_bounded():
    gen = Script(*['{"tool": "list_tasks", "args": {}}'] * 10)
    out = chat.respond("loop", state=STATE, generate=gen, now=NOW)
    assert "could not finish" in out["reply"] and len(gen.prompts) == chat.MAX_TOOL_STEPS + 1


def test_llm_failure_gives_friendly_reply_and_keeps_earlier_actions(monkeypatch):
    monkeypatch.setattr(tools, "_now", lambda: NOW)
    calls = iter([
        '{"tool": "add_task", "args": {"text": "Buy milk"}}',
    ])

    def flaky(prompt):
        try:
            return next(calls)
        except StopIteration:
            raise RuntimeError("quota exhausted")
    out = chat.respond("add buy milk", generate=flaky, now=NOW)
    assert "could not reach my brain" in out["reply"]
    assert out["actions"] == [{"type": "add_task", "text": "Buy milk"}]


def test_empty_message_does_not_call_the_model():
    gen = Script()
    assert chat.respond("   ", generate=gen, now=NOW)["actions"] == [] and gen.prompts == []


# ---------------------------------------------------------------- bridge
@pytest.fixture
def recorded(monkeypatch):
    calls = []
    from life_agent.events import event_model
    for name in ("record_focus_started", "record_focus_completed", "record_focus_abandoned", "record_task_completed"):
        monkeypatch.setattr(event_model, name, lambda *a, _n=name, **k: calls.append((_n, a, k)))
    monkeypatch.setattr(event_model, "append_once", lambda kind, payload, key: calls.append(("append_once", kind, payload, key)))
    monkeypatch.setattr(bridge, "_after_session", lambda: calls.append(("after_session",)))
    # deterministic game stats: each call to compute() reports 5 more diamonds than the last
    from life_agent import gamification
    counter = {"n": 0}

    def fake_compute(*a, **k):
        counter["n"] += 1
        total = 5 * counter["n"]
        return {"total": total, "level": 1 + total // 20, "title": "t", "streak": 1, "per_day": {}}
    monkeypatch.setattr(gamification, "compute", fake_compute)
    return calls


def test_dispatch_errors_never_raise():
    assert bridge.dispatch("not json")["error"].startswith("JSONDecodeError")
    r = bridge.dispatch(json.dumps({"id": 3, "method": "nope"}))
    assert r["id"] == 3 and "unknown method" in r["error"]
    assert bridge.dispatch(json.dumps({"id": 1, "method": "ping"})) == {"id": 1, "result": {"ok": True}}


def test_record_focus_uses_a_unique_intent_per_run(recorded):
    p = {"task": "Write", "task_id": "t1", "run_id": "111", "phase": "started"}
    assert bridge.dispatch(json.dumps({"id": 1, "method": "record_focus", "params": p}))["result"] == {"ok": True}
    bridge.dispatch(json.dumps({"id": 2, "method": "record_focus",
                                "params": {**p, "phase": "completed", "duration_seconds": 1500}}))
    started, completed = recorded[0], recorded[1]
    assert started[0] == "record_focus_started" and started[2]["intent_id"] == "lifebot:t1:111"
    assert completed[0] == "record_focus_completed" and completed[2]["duration_seconds"] == 1500
    assert completed[2]["source"] == "lifebot" and ("after_session",) in recorded
    # a second run of the same task gets its own intent id, so nothing is deduplicated away
    bridge.dispatch(json.dumps({"id": 3, "method": "record_focus", "params": {**p, "run_id": "222"}}))
    assert recorded[-1][2]["intent_id"] == "lifebot:t1:222"


@pytest.mark.parametrize("params", [
    {"phase": "completed", "task": "T", "task_id": "t"},                       # missing duration
    {"phase": "completed", "task": "T", "task_id": "t", "duration_seconds": -5},
    {"phase": "paused", "task": "T", "task_id": "t"},
])
def test_record_focus_rejects_bad_input(recorded, params):
    r = bridge.dispatch(json.dumps({"id": 1, "method": "record_focus", "params": params}))
    assert "error" in r and recorded == []


def test_record_task_planned_and_completed(recorded):
    bridge.dispatch(json.dumps({"id": 1, "method": "record_task",
                                "params": {"status": "planned", "task": "Write", "task_id": "t1"}}))
    assert recorded[0][:2] == ("append_once", "task_planned") and recorded[0][3] == "task_planned:t1"
    bridge.dispatch(json.dumps({"id": 2, "method": "record_task",
                                "params": {"status": "completed", "task": "Write", "task_id": "t1"}}))
    assert recorded[1][0] == "record_task_completed" and recorded[1][2]["intent_id"] == "t1"
    assert "error" in bridge.dispatch(json.dumps({"id": 3, "method": "record_task", "params": {"status": "completed"}}))


def test_serve_handles_requests_concurrently_and_in_one_line_each():
    stdin = io.StringIO("\n".join(json.dumps({"id": i, "method": "ping"}) for i in range(8)) + "\n\n")
    out = io.StringIO()
    bridge.serve(stdin, out)
    ids = sorted(json.loads(l)["id"] for l in out.getvalue().splitlines())
    assert ids == list(range(8))


def test_subprocess_protocol_keeps_stdout_clean():
    """Real process: library prints must not corrupt the protocol stream."""
    repo = Path(__file__).resolve().parent.parent
    reqs = "\n".join(json.dumps(r) for r in [
        {"id": 1, "method": "ping"},
        {"id": 2, "method": "bogus"},
    ]) + "\n"
    proc = subprocess.run(
        [sys.executable, "-m", "life_agent.lifebot.bridge"], input=reqs, capture_output=True, text=True,
        encoding="utf-8", cwd=repo, timeout=60,
        env={**os.environ, "PYTHONPATH": str(repo / "src"), "NOTION_TOKEN": "x"})
    lines = [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]   # every stdout line is JSON
    by_id = {l["id"]: l for l in lines}
    assert by_id[1]["result"] == {"ok": True} and "unknown method" in by_id[2]["error"]
    assert proc.returncode == 0


def test_finished_session_and_task_return_a_reward(recorded):
    done = bridge.dispatch(json.dumps({"id": 1, "method": "record_focus", "params": {
        "phase": "completed", "task": "T", "task_id": "t1", "run_id": "1", "duration_seconds": 1500}}))
    assert done["result"]["reward"]["diamonds"] == 5 and done["result"]["reward"]["level_up"] is False
    task = bridge.dispatch(json.dumps({"id": 2, "method": "record_task",
                                       "params": {"status": "completed", "task": "T", "task_id": "t1"}}))
    assert task["result"]["reward"]["diamonds"] == 5
    started = bridge.dispatch(json.dumps({"id": 3, "method": "record_focus", "params": {
        "phase": "started", "task": "T", "task_id": "t1", "run_id": "2"}}))
    assert "reward" not in started["result"]                       # nothing earned by merely starting


def test_reward_failure_never_breaks_recording(recorded, monkeypatch):
    from life_agent import gamification
    monkeypatch.setattr(gamification, "compute", lambda *a, **k: 1 / 0)
    r = bridge.dispatch(json.dumps({"id": 1, "method": "record_focus", "params": {
        "phase": "completed", "task": "T", "task_id": "t1", "run_id": "1", "duration_seconds": 60}}))
    assert r["result"] == {"ok": True}


def test_game_stats_method_omits_the_per_day_table(recorded):
    r = bridge.dispatch(json.dumps({"id": 1, "method": "game_stats"}))["result"]
    assert r["level"] == 1 and "per_day" not in r
