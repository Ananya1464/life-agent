"""Tests for the Obsidian dashboard renderer (inline SVG, no plugins)."""
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

import pytest

from life_agent import dates
from life_agent.obsidian import dashboard as dash

TODAY = date(2026, 10, 1)
NOW = datetime(2026, 10, 1, 22, 10, tzinfo=dates.TZ)


def session(day, hour_utc, minutes, kind="focus_completed", intent=None, task="Task A"):
    intent = intent or f"{day}-{hour_utc}-{kind}"
    start = f"{day}T{hour_utc:02d}:00:00Z"
    end = f"{day}T{hour_utc:02d}:{minutes % 60:02d}:00Z"
    return [
        {"id": f"s-{intent}", "ts": start, "kind": "focus_started", "date": day, "task": task,
         "intent_id": intent, "source": "focus_tab"},
        {"id": f"e-{intent}", "ts": end, "kind": kind, "date": day, "task": task, "intent_id": intent,
         "source": "focus_tab", "duration_seconds": minutes * 60},
    ]


def task_event(kind, day, task="Write", intent="x"):
    return {"id": f"{kind}-{day}-{intent}", "ts": f"{day}T05:00:00Z", "kind": kind, "date": day,
            "task": task, "intent_id": intent}


@pytest.fixture
def events():
    ev = []
    ev += session("2026-10-01", 4, 25)                                  # today, completed 25m
    ev += session("2026-09-30", 4, 25)                                  # yesterday, completed
    ev += session("2026-09-29", 5, 10, kind="focus_abandoned")           # stopped early
    ev += [task_event("task_planned", "2026-10-01", intent="a"), task_event("task_planned", "2026-10-01", intent="b"),
           task_event("task_completed", "2026-10-01", intent="a"),
           task_event("task_forgot", "2026-09-30", intent="c"),
           task_event("task_planned", "2026-09-30", intent="c"), task_event("task_completed", "2026-09-30", intent="d"),
           task_event("task_planned", "2026-09-30", intent="d")]
    return ev


def svgs(note):
    return re.findall(r"<svg.*?</svg>", note, flags=re.S)


def test_every_chart_is_well_formed_xml(events):
    note = dash.render_note(events, today=TODAY, now=NOW)
    found = svgs(note)
    charts = re.findall(r'data-chart="(\w+)"', note)
    assert sorted(charts) == ["focus", "heat", "sessions", "tasks", "trend"]
    assert len(found) > 5             # five charts plus the pixel icons (HUD and card titles)
    for s in found:
        ET.fromstring(s)


def test_empty_data_renders_placeholders_not_errors():
    note = dash.render_note([], today=TODAY, now=NOW)
    assert "No focus sessions in this period yet" in note
    assert "No data in this period yet" in note
    assert "Need at least 2 days of data for a trend" in note
    assert "No focus time recorded yet" in note
    for s in svgs(note):
        ET.fromstring(s)


def test_kpis_are_computed_from_events(events):
    d = dash.collect(events, TODAY)
    k = d["kpi"]
    assert k["today_min"] == 25
    assert k["week_min"] == 25 + 25 + 10
    assert (k["week_sessions"], k["week_finished"]) == (2, 3)
    assert k["streak"] == 2                       # today + yesterday
    assert (k["tasks_today"], k["planned_today"]) == (1, 2)


def test_streak_survives_an_empty_today():
    ev = session("2026-09-30", 4, 25) + session("2026-09-29", 4, 25)
    assert dash.collect(ev, TODAY)["kpi"]["streak"] == 2
    assert dash.collect(session("2026-09-27", 4, 25), TODAY)["kpi"]["streak"] == 0


def test_donut_counts_and_hover_titles(events):
    d = dash.collect(events, TODAY)
    assert d["session_counts"]["completed"] == 2 and d["session_counts"]["abandoned"] == 1
    assert d["task_counts"]["task_completed"] == 2 and d["task_counts"]["task_forgot"] == 1
    ring = dash.pixel_pie([("Completed", 2, dash.GREEN), ("Stopped early", 1, dash.ORANGE)], "sessions")
    assert "Completed: 2 (67%)" in ring and "Stopped early: 1 (33%)" in ring


def test_trend_uses_completed_over_planned_and_leaves_gaps(events):
    trend = dict(dash.collect(events, TODAY)["trend"])
    assert trend[date(2026, 10, 1)] == 50.0
    assert trend[date(2026, 9, 30)] == 50.0
    assert trend[date(2026, 9, 29)] is None


def test_heatmap_buckets_by_local_weekday_and_hour():
    # 2026-10-01 is a Thursday; 04:00 UTC = 09:30 IST -> hour 9
    d = dash.collect(session("2026-10-01", 4, 25), TODAY)
    assert d["heat"][3][9] == 25
    assert sum(sum(r) for r in d["heat"]) == 25


def test_unfinished_sessions_do_not_count_as_focus_time():
    ev = [{"id": "s", "ts": "2026-10-01T04:00:00Z", "kind": "focus_started", "date": "2026-10-01",
           "task": "T", "intent_id": "u", "source": "focus_tab"}]
    d = dash.collect(ev, TODAY)
    assert d["kpi"]["today_min"] == 0 and d["session_counts"]["unfinished"] == 1


def test_html_is_escaped():
    out = dash.stacked_bars([{"date": TODAY, "completed_min": 5, "stopped_min": 0}])
    assert "<script" not in out
    assert dash._esc('<img src=x onerror="a">') == "&lt;img src=x onerror=&quot;a&quot;&gt;"


def test_note_has_no_blank_lines_inside_the_html_block(events):
    body = dash.render_note(events, today=TODAY, now=NOW).split("*Auto-generated", 1)[1]
    html_part = body.split("\n", 1)[1].strip("\n")
    assert "\n\n" not in html_part   # a blank line would end the HTML block and break rendering
    assert not re.search(r"^\s{4,}<", html_part, flags=re.M)  # 4-space indent would become a code block


def test_frontmatter_and_title(events):
    note = dash.render_note(events, today=TODAY, now=NOW)
    assert note.startswith("---\ntags: [dashboard, auto-generated]\nupdated: 2026-10-01T22:10:00+05:30\n---\n")
    assert "# Life Agent Dashboard" in note


def test_write_dashboard_is_atomic_and_idempotent(tmp_path, events):
    path = dash.write_dashboard(tmp_path / "Dash", events=events, today=TODAY)
    assert path.name == dash.NOTE_NAME and path.read_text(encoding="utf-8").startswith("---")
    assert list(path.parent.glob("*.tmp")) == []
    first = path.read_text(encoding="utf-8")
    dash.write_dashboard(tmp_path / "Dash", events=events, today=TODAY)
    assert path.read_text(encoding="utf-8").split("updated:")[0] == first.split("updated:")[0]


def test_output_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("LIFE_AGENT_DASHBOARD_DIR", str(tmp_path / "custom"))
    assert dash.dashboard_dir() == tmp_path / "custom"
    monkeypatch.delenv("LIFE_AGENT_DASHBOARD_DIR")
    assert dash.dashboard_dir() == dash.DEFAULT_DIR


def test_background_refresh_never_raises_and_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(dash.store, "load_all", lambda: [])
    seen = {}
    dash.refresh_in_background(tmp_path, on_done=lambda p, e: seen.update(path=p, error=e)).join(10)
    assert seen["error"] is None and seen["path"].exists()

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(dash, "write_dashboard", boom)
    seen.clear()
    dash.refresh_in_background(tmp_path, on_done=lambda p, e: seen.update(path=p, error=e)).join(10)
    assert seen["path"] is None and "disk full" in str(seen["error"])


def test_cli_writes_note(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(dash.store, "load_all", lambda: [])
    assert dash.main(["--out", str(tmp_path)]) == 0
    assert (tmp_path / dash.NOTE_NAME).exists()
    assert str(tmp_path) in capsys.readouterr().out
