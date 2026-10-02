"""Tests for the Notion sync payload/filters and the scheduled-task failure notice."""
import pytest

from life_agent.desktop import sync
from life_agent.notifications import outbound


def test_sync_payload_keeps_timestamp_and_duration():
    event = {"id": "e1", "ts": "2026-10-01T04:55:00Z", "kind": "focus_completed", "task": "Task A",
             "source": "focus_tab", "intent_id": "t1", "duration_seconds": 1500}
    props = sync._build_notion_properties(event)
    assert props["Date"]["date"]["start"] == "2026-10-01T04:55:00Z"
    assert props["Duration (sec)"] == {"number": 1500}
    assert props["Event ID"]["rich_text"][0]["text"]["content"] == "e1"


def test_sync_payload_omits_duration_when_absent():
    props = sync._build_notion_properties(
        {"id": "e2", "ts": "2026-10-01T04:00:00Z", "kind": "focus_started", "task": "T", "source": "focus_tab"})
    assert "Duration (sec)" not in props


def test_only_activity_events_are_synced(monkeypatch):
    events = [{"id": str(i), "kind": k} for i, k in enumerate(
        ["focus_completed", "notification_sent", "task_started", "task_completed", "task_failed"])]
    monkeypatch.setattr(sync.store, "load_all", lambda: events)
    monkeypatch.setattr(sync, "_read_synced_ids", lambda: set())
    assert [e["kind"] for e in sync.events_since_last_sync()] == ["focus_completed", "task_completed"]


def test_background_sync_never_raises_and_reports_error(monkeypatch):
    def boom():
        raise RuntimeError("offline")
    monkeypatch.setattr(sync, "sync_events", boom)
    seen = {}
    t = sync.sync_in_background(on_done=lambda r, e: seen.update(result=r, error=e))
    t.join(5)
    assert seen["result"] is None and "offline" in str(seen["error"])


def test_background_sync_skips_when_one_is_running(monkeypatch):
    assert sync._sync_lock.acquire(blocking=False)
    try:
        assert sync.sync_in_background() is None
    finally:
        sync._sync_lock.release()


def test_failure_notice_redacts_secrets_and_never_raises(monkeypatch):
    sent = []
    monkeypatch.setattr(outbound, "_send_ntfy", lambda title, body, tags=None: sent.append(("ntfy", title, body)))
    monkeypatch.setattr(outbound, "_send_email", lambda subject, body: sent.append(("email", subject, body)))
    outbound.send_failure_notification("tomorrow_planner", RuntimeError("404 at https://x/y?key=SECRET123 failed"))
    assert [s[0] for s in sent] == ["ntfy", "email"]
    assert "tomorrow_planner failed" in sent[0][1]
    assert "SECRET123" not in sent[0][2] and "[redacted]" in sent[0][2]


def test_failure_notice_survives_unconfigured_channels(monkeypatch):
    def nope(*a, **k):
        raise RuntimeError("NTFY_TOPIC not configured")
    monkeypatch.setattr(outbound, "_send_ntfy", nope)
    monkeypatch.setattr(outbound, "_send_email", nope)
    outbound.send_failure_notification("ai_edge", "boom")  # must not raise


def test_main_run_sends_failure_notice_and_reraises(monkeypatch):
    from life_agent.agent import main
    calls = []
    monkeypatch.setattr(main.event_model, "record_task_started", lambda *a, **k: None)
    monkeypatch.setattr(main.store, "append", lambda *a, **k: None)
    monkeypatch.setattr(main.outbound, "send_task_start_notification", lambda t: None)
    monkeypatch.setattr(main.outbound, "send_failure_notification", lambda t, e: calls.append((t, str(e))))

    class Boom:
        @staticmethod
        def run():
            raise RuntimeError("llm exploded")
    monkeypatch.setattr(main.importlib, "import_module", lambda name: Boom)
    with pytest.raises(RuntimeError):
        main.run("ai_edge")
    assert calls == [("ai_edge", "llm exploded")]
