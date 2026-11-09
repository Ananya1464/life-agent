"""Tests for the deterministic activity context (stats, plan-load mode, patterns) and the
Notion -> event reader that feeds it."""
from datetime import date

import pytest

from life_agent.agent import activity_context as ac
from life_agent.events import cloud_activity

TODAY = date(2026, 10, 1)


def ev(kind, day, ts, task="Task A", intent="t1", duration=None, source="focus_tab", eid=None):
    e = {"id": eid or f"{kind}-{ts}-{intent}", "ts": ts, "kind": kind, "date": day, "task": task,
         "intent_id": intent, "source": source}
    if duration is not None:
        e["duration_seconds"] = duration
    return e


def completed(day, hour, task="Task A", intent="t1", minutes=25):
    start = f"{day}T{hour:02d}:00:00Z"
    end = f"{day}T{hour:02d}:{minutes:02d}:00Z"
    return [ev("focus_started", day, start, task, intent),
            ev("focus_completed", day, end, task, intent, duration=minutes * 60)]


def abandoned(day, hour, task="Task A", intent="t1", seconds=300):
    start = f"{day}T{hour:02d}:00:00Z"
    end = f"{day}T{hour:02d}:05:00Z"
    return [ev("focus_started", day, start, task, intent),
            ev("focus_abandoned", day, end, task, intent, duration=seconds)]


def test_no_events_is_unknown_and_makes_no_claims():
    ctx = ac.build(today=TODAY, events=[])
    assert ctx.mode == "unknown"
    assert ctx.stats["finished"] == 0
    assert "no data" in ctx.summary
    assert ctx.patterns == ""
    assert "standard 3 priorities" in ctx.load_guidance


def test_strong_recent_week_allows_stretch():
    events = []
    for i, day in enumerate(["2026-09-29", "2026-09-30", "2026-10-01"]):
        events += completed(day, 10, intent=f"t{i}")
    ctx = ac.build(today=TODAY, events=events)
    assert ctx.mode == "strong"
    assert ctx.stats["completed"] == 3
    assert ctx.stats["completion_rate"] == 1.0
    assert "stretch" in ctx.load_guidance


def test_rough_recent_days_lighten_the_plan():
    events = (abandoned("2026-09-30", 9, intent="a") + abandoned("2026-10-01", 9, intent="b")
              + completed("2026-10-01", 14, intent="c"))
    ctx = ac.build(today=TODAY, events=events)
    assert ctx.stats["recent_finished"] == 3
    assert ctx.mode == "light"
    assert "only 2 priorities" in ctx.load_guidance
    assert "guilt" in ctx.load_guidance  # tone guard travels with the instruction


def test_two_sessions_is_not_enough_for_strong():
    events = completed("2026-09-30", 10, intent="a") + completed("2026-10-01", 10, intent="b")
    assert ac.build(today=TODAY, events=events).mode == "standard"


def test_abandon_then_complete_on_same_task_counts_both():
    events = (abandoned("2026-10-01", 9, intent="same")
              + [ev("focus_completed", "2026-10-01", "2026-10-01T11:00:00Z", intent="same", duration=1500)])
    stats = ac.build(today=TODAY, events=events).stats
    assert (stats["completed"], stats["abandoned"]) == (1, 1)
    assert stats["focus_seconds"] == 300 + 1500


def test_unfinished_sessions_do_not_affect_rates_or_focus_time():
    events = [ev("focus_started", "2026-10-01", "2026-10-01T10:00:00Z", intent="x")]
    stats = ac.build(today=TODAY, events=events).stats
    assert stats["unfinished"] == 1
    assert stats["finished"] == 0 and stats["focus_seconds"] == 0
    assert ac.recommend_mode(stats) == "unknown"


def test_best_hour_needs_three_completed_sessions():
    # 04:30 UTC = 10:00 IST (TIMEZONE default Asia/Kolkata)
    events = []
    for i, day in enumerate(["2026-09-28", "2026-09-29", "2026-09-30"]):
        events += [ev("focus_started", day, f"{day}T04:30:00Z", intent=f"h{i}"),
                   ev("focus_completed", day, f"{day}T04:55:00Z", intent=f"h{i}", duration=1500)]
    stats = ac.build(today=TODAY, events=events).stats
    assert stats["best_hour"] == 10
    assert "10:00-11:00" in ac.build(today=TODAY, events=events).patterns

    few = ac.build(today=TODAY, events=events[:4]).stats
    assert few["best_hour"] is None


def test_often_abandoned_requires_two_and_keeps_display_name():
    events = (abandoned("2026-09-29", 9, task="Write Report", intent="a")
              + abandoned("2026-09-30", 9, task="write report", intent="b")
              + abandoned("2026-10-01", 9, task="One-off", intent="c"))
    ctx = ac.build(today=TODAY, events=events)
    assert ctx.stats["often_abandoned"] == ["Write Report"]
    assert '"Write Report" was stopped early' in ctx.patterns


def test_events_outside_window_are_ignored():
    events = completed("2026-09-01", 10, intent="old")
    assert ac.build(today=TODAY, events=events).stats["finished"] == 0


def test_build_never_raises_on_bad_events():
    bad = [{"kind": "focus_completed", "date": "2026-10-01", "ts": None, "intent_id": "z"}]
    ctx = ac.build(today=TODAY, events=bad)
    assert ctx.mode in {"unknown", "standard", "light", "strong"}


# ---- Notion rows -> events

def page(kind="focus_completed", start="2026-10-01T04:55:00.000+00:00", task="Task A", source="focus_tab",
         duration=1500, eid="evt-1", intent="t1"):
    rt = lambda t: {"rich_text": [{"plain_text": t}]} if t else {"rich_text": []}
    props = {
        "Kind": {"select": {"name": kind}},
        "Source": {"select": {"name": source}},
        "Date": {"date": {"start": start}},
        "Task": rt(task), "Event ID": rt(eid), "Intent ID": rt(intent),
        "Name": {"title": [{"plain_text": task}]},
        "Duration (sec)": {"number": duration},
    }
    return {"id": "page-1", "properties": props}


def test_event_from_page_maps_fields_and_local_date():
    e = cloud_activity.event_from_page(page(start="2026-09-30T20:30:00Z"))
    assert e["ts"] == "2026-09-30T20:30:00Z"
    assert e["date"] == "2026-10-01"          # 20:30 UTC is 02:00 IST the next day
    assert e["duration_seconds"] == 1500 and e["intent_id"] == "t1" and e["id"] == "evt-1"


@pytest.mark.parametrize("kwargs", [
    {"kind": "task_completed"},        # not a focus event
    {"source": "sync_test"},           # test rows are ignored
    {"source": "failure_test_1"},
    {"start": ""},                      # no timestamp
])
def test_event_from_page_skips_unusable_rows(kwargs):
    assert cloud_activity.event_from_page(page(**kwargs)) is None


def test_event_from_page_without_duration_and_date_only():
    p = page(duration=None, start="2026-10-01")
    p["properties"]["Duration (sec)"] = {"number": None}
    e = cloud_activity.event_from_page(p)
    assert "duration_seconds" not in e and e["ts"] == "2026-10-01T00:00:00Z"


def test_fetch_dedupes_by_event_id_and_filters_to_range(monkeypatch):
    pages = [page(eid="a"), page(eid="a"), page(eid="b", start="2026-08-01T05:00:00Z")]
    monkeypatch.setattr(cloud_activity.notion_api, "query_data_source", lambda ds, flt: pages)
    got = cloud_activity.fetch_focus_events(date(2026, 9, 25), date(2026, 10, 1))
    assert [e["id"] for e in got] == ["a"]


def test_load_events_merges_notion_and_local_without_duplicates(monkeypatch):
    notion = [ev("focus_completed", "2026-10-01", "2026-10-01T10:00:00Z", eid="same", duration=60)]
    local = [ev("focus_completed", "2026-10-01", "2026-10-01T10:00:00Z", eid="same", duration=60),
             ev("focus_completed", "2026-10-01", "2026-10-01T12:00:00Z", eid="only-local", duration=60)]
    monkeypatch.setattr(ac.cloud_activity, "fetch_focus_events", lambda s, e: notion)
    monkeypatch.setattr(ac.store, "load_all", lambda: local)
    ids = sorted(e["id"] for e in ac.load_events(date(2026, 9, 25), TODAY))
    assert ids == ["only-local", "same"]


def test_load_events_survives_notion_outage(monkeypatch):
    def boom(s, e):
        raise RuntimeError("notion down")
    monkeypatch.setattr(ac.cloud_activity, "fetch_focus_events", boom)
    monkeypatch.setattr(ac.store, "load_all", lambda: [])
    assert ac.load_events(date(2026, 9, 25), TODAY) == []
