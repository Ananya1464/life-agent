"""Normalized Life Agent event helpers."""
from __future__ import annotations

import re

from life_agent.events import store


OUTCOME_KIND = {
    "completed": "task_completed",
    "partial": "task_partial",
    "never_started": "task_never_started",
    "forgot": "task_forgot",
    "skipped": "task_skipped",
    "not_now": "task_not_now",
    "no_response": "task_no_response",
}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "item"


def intent_id(date_iso: str, slot: str, index: int, task: str) -> str:
    return f"{date_iso}:{slot}:{index}:{slugify(task)}"


def append_once(kind: str, payload: dict, dedupe_key: str) -> str:
    for event in store.load_all():
        if event.get("kind") == kind and event.get("dedupe_key") == dedupe_key:
            return event.get("id", "")
    stored = {**payload, "dedupe_key": dedupe_key}
    return store.append(kind, stored)


def record_planned_intentions(date_iso: str, slot: str, intentions: list[dict]) -> list[dict]:
    out = []
    for index, intention in enumerate(intentions, start=1):
        task = intention.get("task", "")
        iid = intent_id(date_iso, slot, index, task)
        payload = {
            "date": date_iso,
            "slot": slot,
            "intent_id": iid,
            "index": index,
            "task": task,
            "life_area": intention.get("life_area"),
            "goal": intention.get("goal"),
            "source": intention.get("source", "morning_notification"),
        }
        append_once("task_planned", payload, f"task_planned:{iid}")
        out.append(payload)
    return out


def record_notification_state(
    *,
    slot: str,
    token: str,
    subject: str,
    state: str,
    channel: str | None = None,
    message_id: str | None = None,
    error: str | None = None,
) -> None:
    payload = {
        "slot": slot,
        "token": token,
        "subject": subject,
        "channel": channel,
        "message_id": message_id,
        "error": error,
    }
    if state == "failed":
        append_once("notification_failed", payload, f"notification_failed:{slot}:{token}")
        return
    append_once("notification_sent", {**payload, "state": "sent"}, f"notification_sent:{slot}:{token}:{channel or 'unknown'}")
    append_once(
        "notification_delivered",
        {**payload, "state": "delivered"},
        f"notification_delivered:{slot}:{token}:{channel or 'unknown'}",
    )


def record_task_started(task_name: str, *, date_iso: str, source: str = "runner", intent_id: str | None = None) -> None:
    append_once(
        "task_started",
        {"date": date_iso, "task": task_name, "source": source, "intent_id": intent_id},
        f"task_started:{date_iso}:{task_name}:{intent_id or source}",
    )


def record_task_completed(task_name: str, *, date_iso: str, source: str = "runner", intent_id: str | None = None) -> None:
    append_once(
        "task_completed",
        {"date": date_iso, "task": task_name, "source": source, "intent_id": intent_id},
        f"task_completed:{date_iso}:{task_name}:{intent_id or source}",
    )


def record_task_outcome(
    status: str,
    *,
    date_iso: str,
    task: str,
    intent_id: str | None = None,
    reply_id: str | None = None,
    token: str | None = None,
    friction: str | None = None,
    text: str | None = None,
) -> None:
    kind = OUTCOME_KIND.get(status)
    if not kind:
        raise ValueError(f"Unsupported status: {status}")
    append_once(
        kind,
        {
            "date": date_iso,
            "task": task,
            "status": status,
            "intent_id": intent_id,
            "reply_id": reply_id,
            "token": token,
            "friction": friction,
            "text": text,
        },
        f"{kind}:{date_iso}:{intent_id or slugify(task)}:{reply_id or token or status}",
    )


def record_capture(*, date_iso: str, token: str, bucket: str, text: str, reply_id: str | None = None) -> None:
    append_once(
        "capture_recorded",
        {"date": date_iso, "token": token, "bucket": bucket, "text": text, "reply_id": reply_id},
        f"capture_recorded:{date_iso}:{token}:{bucket}:{slugify(text)}",
    )


def record_workout(*, date_iso: str, token: str, reply_id: str | None = None, source: str = "reply") -> None:
    append_once(
        "workout_completed",
        {"date": date_iso, "token": token, "reply_id": reply_id, "source": source},
        f"workout_completed:{date_iso}:{token}:{reply_id or source}",
    )


def record_reply_no_response(*, date_iso: str, token: str, intent_id: str, task: str) -> None:
    record_task_outcome("no_response", date_iso=date_iso, task=task, intent_id=intent_id, token=token)


def normalize_checkins(
    *,
    date_iso: str,
    token: str,
    reply_id: str,
    checkins: list[dict],
    planned_intentions: list[dict] | None = None,
) -> None:
    planned_intentions = planned_intentions or []
    matched: set[str] = set()
    for checkin in checkins:
        task = checkin.get("task", "")
        status = checkin.get("status", "")
        friction = checkin.get("friction")
        intent = next((item for item in planned_intentions if slugify(item.get("task", "")) == slugify(task)), None)
        intent_id_value = intent.get("intent_id") if intent else None
        if intent_id_value:
            matched.add(intent_id_value)
        normalized_status = "completed" if status == "done" else status
        if normalized_status in OUTCOME_KIND:
            record_task_outcome(
                normalized_status,
                date_iso=date_iso,
                task=task,
                intent_id=intent_id_value,
                reply_id=reply_id,
                token=token,
                friction=friction,
            )
        if "not now" in f"{task} {friction or ''}".lower():
            record_task_outcome(
                "not_now",
                date_iso=date_iso,
                task=task,
                intent_id=intent_id_value,
                reply_id=reply_id,
                token=token,
                friction=friction,
            )

    for intent in planned_intentions:
        if intent.get("intent_id") not in matched:
            record_reply_no_response(
                date_iso=date_iso,
                token=token,
                intent_id=intent["intent_id"],
                task=intent.get("task", ""),
            )


def normalize_reply_events(
    *,
    date_iso: str,
    token: str,
    reply_id: str,
    captures: list[dict] | None = None,
    checkins: list[dict] | None = None,
    planned_intentions: list[dict] | None = None,
) -> None:
    for capture in captures or []:
        record_capture(
            date_iso=date_iso,
            token=token,
            bucket=capture.get("bucket", "curiosity"),
            text=capture.get("text", ""),
            reply_id=reply_id,
        )
    for checkin in checkins or []:
        if "workout" in (checkin.get("task", "").lower()) and checkin.get("status") == "done":
            record_workout(date_iso=date_iso, token=token, reply_id=reply_id)
    normalize_checkins(
        date_iso=date_iso,
        token=token,
        reply_id=reply_id,
        checkins=checkins or [],
        planned_intentions=planned_intentions,
    )


def record_focus_started(*, date_iso: str, task: str, intent_id: str | None = None, source: str = "focus_tab") -> None:
    append_once(
        "focus_started",
        {"date": date_iso, "task": task, "intent_id": intent_id, "source": source},
        f"focus_started:{date_iso}:{intent_id or slugify(task)}:{source}",
    )


def record_focus_completed(*, date_iso: str, task: str, duration_seconds: int,
                           intent_id: str | None = None, source: str = "focus_tab") -> None:
    append_once(
        "focus_completed",
        {"date": date_iso, "task": task, "duration_seconds": duration_seconds,
         "intent_id": intent_id, "source": source},
        f"focus_completed:{date_iso}:{intent_id or slugify(task)}",
    )


def record_focus_abandoned(*, date_iso: str, task: str, duration_seconds: int,
                           intent_id: str | None = None, source: str = "focus_tab") -> None:
    append_once(
        "focus_abandoned",
        {"date": date_iso, "task": task, "duration_seconds": duration_seconds,
         "intent_id": intent_id, "source": source},
        f"focus_abandoned:{date_iso}:{intent_id or slugify(task)}",
    )


def record_reflection(*, date_iso: str, text: str, source: str = "typewriter") -> None:
    store.append(
        "reflection_added",
        {"date": date_iso, "text": text, "source": source},
    )