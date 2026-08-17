"""Scratch tests for Life OS metrics calculations and idempotent writes."""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from life_agent.events import event_model
from life_agent.metrics import metrics


def main() -> None:
    day = metrics.dates.today()
    day_iso = day.isoformat()
    sample_events = [
        {"kind": "task_planned", "ts": f"{day_iso}T00:00:00Z", "date": day_iso, "slot": "morning", "intent_id": f"i{i}", "task": f"t{i}"} for i in range(10)
    ]
    sample_events += [
        *[{"kind": "task_completed", "ts": f"{day_iso}T02:00:00Z", "date": day_iso, "task": f"t{i}", "intent_id": f"i{i}"} for i in range(7)],
        *[{"kind": "task_partial", "ts": f"{day_iso}T02:10:00Z", "date": day_iso, "task": f"t{i}", "intent_id": f"i{7 + i}"} for i in range(2)],
        {"kind": "task_forgot", "ts": f"{day_iso}T02:20:00Z", "date": day_iso, "task": "forgot", "intent_id": "i9"},
        {"kind": "notification_sent", "ts": f"{day_iso}T03:00:00Z", "slot": "morning", "token": f"LA-{day_iso.replace('-', '')}-M", "subject": "brief", "channel": "ntfy"},
        {"kind": "notification_delivered", "ts": f"{day_iso}T03:01:00Z", "slot": "morning", "token": f"LA-{day_iso.replace('-', '')}-M", "subject": "brief", "channel": "ntfy"},
    ]

    original_load_all = metrics.store.load_all
    original_events_on = metrics.calendar_feed.events_on
    original_goal_rows = metrics.goal_rows
    original_life_area_scores = metrics.life_area_scores
    try:
        metrics.store.load_all = lambda: sample_events
        metrics.calendar_feed.events_on = lambda *_: ["18:00 Workout"]
        metrics.goal_rows = lambda: []
        metrics.life_area_scores = lambda: {}

        daily = metrics.calculate_daily_metrics(day)
        assert daily["tasks_planned"] == 10
        assert daily["tasks_done"] == 7
        assert daily["partial"] == 2
        assert daily["forgot"] == 1
        assert daily["completion_pct"] == 70
        assert daily["execution_score"] == 80
        assert daily["workout"] is True
        assert daily["morning_brief_sent"] is True
        assert daily["notifications_sent"] == 1
        assert daily["notifications_delivered"] == 1

        metrics.store.load_all = lambda: sample_events + [
            {"kind": "task_planned", "ts": f"{(day - metrics.timedelta(days=1)).isoformat()}T00:00:00Z", "date": (day - metrics.timedelta(days=1)).isoformat(), "slot": "morning", "intent_id": "prev-1", "task": "y"},
            {"kind": "task_completed", "ts": f"{(day - metrics.timedelta(days=1)).isoformat()}T01:00:00Z", "date": (day - metrics.timedelta(days=1)).isoformat(), "task": "y", "intent_id": "prev-1"},
        ]
        weekly = metrics.aggregate_weekly_metrics(day)
        assert weekly["active_days"] >= 1
        assert weekly["tasks_planned"] >= 10

        events = []
        calls = []
        state = {"created": 0}

        def fake_query(method: str, path: str, **kwargs):
            calls.append((method, path, kwargs))
            if method == "POST" and path.endswith("/query"):
                return {"results": events}
            if method == "POST" and path == "/pages":
                state["created"] += 1
                events.append({"id": "row-1"})
                return {"id": "row-1"}
            if method == "PATCH" and path.startswith("/pages/"):
                return {"id": "row-1"}
            raise AssertionError((method, path))

        original_req = metrics.notion_api._req
        original_db = metrics.config.LIFE_OS_METRICS_DB_ID
        metrics.notion_api._req = fake_query
        metrics.config.LIFE_OS_METRICS_DB_ID = "metrics-db"
        try:
            metrics.update_daily_metrics(day)
            metrics.update_daily_metrics(day)
            assert state["created"] == 1
        finally:
            metrics.notion_api._req = original_req
            metrics.config.LIFE_OS_METRICS_DB_ID = original_db

        assert metrics.goal_trajectory(60, 55)["status"] == "On track"
        assert metrics.goal_trajectory(50, 55)["status"] == "At risk"
        assert metrics.goal_trajectory(30, 55)["status"] == "Behind"
        assert metrics.goal_trajectory(None, 55)["status"] == "No data"
    finally:
        metrics.store.load_all = original_load_all
        metrics.calendar_feed.events_on = original_events_on
        metrics.goal_rows = original_goal_rows
        metrics.life_area_scores = original_life_area_scores

    print("metrics test passed")


if __name__ == "__main__":
    main()