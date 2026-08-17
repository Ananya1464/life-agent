"""Scratch test for normalized event recording and deduplication."""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from life_agent.events import event_model


def main() -> None:
    events = []

    def fake_load_all():
        return events

    def fake_append(kind: str, payload: dict) -> str:
        events.append({"kind": kind, "id": f"{kind}-{len(events)}", **payload})
        return events[-1]["id"]

    original_load_all = event_model.store.load_all
    original_append = event_model.store.append
    try:
        event_model.store.load_all = fake_load_all
        event_model.store.append = fake_append

        planned = event_model.record_planned_intentions(
            "2026-08-11",
            "morning",
            [
                {"task": "Career block", "life_area": "Career"},
                {"task": "Workout", "life_area": "Health"},
                {"task": "Study", "life_area": "Learning"},
            ],
        )
        event_model.record_planned_intentions(
            "2026-08-11",
            "morning",
            [
                {"task": "Career block", "life_area": "Career"},
                {"task": "Workout", "life_area": "Health"},
                {"task": "Study", "life_area": "Learning"},
            ],
        )
        assert len([ev for ev in events if ev["kind"] == "task_planned"]) == 3

        event_model.record_notification_state(
            slot="task_start",
            token="LA-20260811-T",
            subject="Task start",
            state="sent",
            channel="ntfy",
        )
        event_model.record_notification_state(
            slot="task_start",
            token="LA-20260811-T",
            subject="Task start",
            state="sent",
            channel="ntfy",
        )
        assert len([ev for ev in events if ev["kind"] == "notification_sent"]) == 1
        assert len([ev for ev in events if ev["kind"] == "notification_delivered"]) == 1

        event_model.record_task_started("meal_plan", date_iso="2026-08-11")
        event_model.record_task_started("meal_plan", date_iso="2026-08-11")
        event_model.record_task_completed("meal_plan", date_iso="2026-08-11")
        event_model.record_task_completed("meal_plan", date_iso="2026-08-11")
        assert len([ev for ev in events if ev["kind"] == "task_started"]) == 1
        assert len([ev for ev in events if ev["kind"] == "task_completed"]) == 1

        for status in ["partial", "never_started", "forgot", "skipped", "not_now", "no_response"]:
            event_model.record_task_outcome(
                status,
                date_iso="2026-08-11",
                task=status,
                intent_id=f"intent-{status}",
            )
            event_model.record_task_outcome(
                status,
                date_iso="2026-08-11",
                task=status,
                intent_id=f"intent-{status}",
            )
        assert len([ev for ev in events if ev["kind"] == "task_partial"]) == 1
        assert len([ev for ev in events if ev["kind"] == "task_never_started"]) == 1
        assert len([ev for ev in events if ev["kind"] == "task_forgot"]) == 1
        assert len([ev for ev in events if ev["kind"] == "task_skipped"]) == 1
        assert len([ev for ev in events if ev["kind"] == "task_not_now"]) == 1
        assert len([ev for ev in events if ev["kind"] == "task_no_response"]) == 1

        event_model.record_capture(date_iso="2026-08-11", token="LA-20260811-E", bucket="build", text="Ship inbound")
        event_model.record_capture(date_iso="2026-08-11", token="LA-20260811-E", bucket="build", text="Ship inbound")
        event_model.record_workout(date_iso="2026-08-11", token="LA-20260811-E")
        event_model.record_workout(date_iso="2026-08-11", token="LA-20260811-E")
        assert len([ev for ev in events if ev["kind"] == "capture_recorded"]) == 1
        assert len([ev for ev in events if ev["kind"] == "workout_completed"]) == 1

        event_model.normalize_checkins(
            date_iso="2026-08-11",
            token="LA-20260811-E",
            reply_id="reply-1",
            checkins=[
                {"task": "Career block", "status": "done", "friction": None},
                {"task": "Workout", "status": "partial", "friction": "time"},
            ],
            planned_intentions=planned,
        )
        assert any(ev["kind"] == "task_completed" and ev.get("intent_id") for ev in events)
        assert any(ev["kind"] == "task_partial" and ev.get("intent_id") for ev in events)

    finally:
        event_model.store.load_all = original_load_all
        event_model.store.append = original_append

    print("event model test passed")


if __name__ == "__main__":
    main()