"""Shared notification gateway for ntfy push and email fallback/channel delivery."""
from __future__ import annotations

import re

import calendar_feed
import config
import dates
import emailer
import event_model
import store

try:
    import requests
except Exception:  # pragma: no cover - requests is already a dependency
    requests = None

SLOT_CODES = {
    "morning": "M",
    "midday": "D",
    "evening": "E",
    "task_start": "T",
}

_WORKOUT_RE = re.compile(r"\b(gym|workout|training|train|run|cardio|strength|lift|yoga|pilates|swim|walk)\b", re.I)
_MORNING_QUOTES = (
    ("Start small, start now.", "Unknown"),
    ("A calm start is still progress.", "Unknown"),
    ("You only need the next step.", "Unknown"),
)


def _slot_code(slot: str) -> str:
    code = SLOT_CODES.get(slot.lower())
    if not code:
        raise ValueError(f"Unknown/unsupported slot: {slot}")
    return code


def _token_for_slot(slot: str) -> str:
    today = dates.today()
    return f"LA-{today.strftime('%Y%m%d')}-{_slot_code(slot)}"


def _send_ntfy(title: str, body: str, *, tags: str | None = None) -> None:
    if not config.NTFY_TOPIC:
        raise RuntimeError("NTFY_TOPIC not configured")
    if requests is None:
        raise RuntimeError("requests is not available")

    headers = {"Title": title}
    if tags:
        headers["Tags"] = tags

    requests.post(  # same call shape as the existing ntfy task helpers
        f"https://ntfy.sh/{config.NTFY_TOPIC}",
        data=body.encode("utf-8"),
        headers=headers,
        timeout=10,
    )


def _send_email(subject: str, body: str) -> str | None:
    if not config.GMAIL_ADDRESS or not config.GMAIL_APP_PASSWORD:
        return None
    return emailer.send_email(subject, body)


def _morning_quote() -> str:
    quote, author = _MORNING_QUOTES[dates.today().day % len(_MORNING_QUOTES)]
    return f'"{quote}"\n\n— {author}'


def _morning_intentions() -> list[dict]:
    today = dates.today()
    schedule = calendar_feed.events_on(today)
    intentions = []
    for item in schedule[:3]:
        lower = item.lower()
        life_area = None
        if any(word in lower for word in ("workout", "gym", "run", "walk", "yoga", "swim", "strength")):
            life_area = "Health"
        elif any(word in lower for word in ("learn", "study", "read", "practice", "course")):
            life_area = "Learning"
        elif any(word in lower for word in ("apply", "job", "career", "interview", "email")):
            life_area = "Career"
        elif any(word in lower for word in ("budget", "finance", "money", "bank")):
            life_area = "Finance"
        elif any(word in lower for word in ("family", "rest", "call", "personal", "life")):
            life_area = "Personal"
        intentions.append({"task": item, "life_area": life_area, "goal": None, "source": "morning_notification"})
    if not intentions:
        intentions = [
            {"task": "Review today's plan", "life_area": None, "goal": None, "source": "morning_notification"},
            {"task": "Do one focused work block", "life_area": None, "goal": None, "source": "morning_notification"},
            {"task": "Move your body", "life_area": "Health", "goal": None, "source": "morning_notification"},
        ]
    return intentions


def _morning_notification_body() -> tuple[str, list[dict]]:
    today = dates.today()
    intentions = _morning_intentions()
    workout = next((item["task"] for item in intentions if _WORKOUT_RE.search(item["task"])), "Workout not on the calendar today.")

    focus_items = intentions[:3]

    lines = [
        "☀️ GOOD MORNING",
        "",
        "Today's energy:",
        f"{dates.day_label(today)} — {len(schedule)} scheduled item(s)",
        "",
        "━━━━━━━━━━━━━━",
        "",
        "🎯 TODAY'S 3",
        "",
    ]

    for index, item in enumerate(focus_items[:3], start=1):
        lines.extend([f"{index}. {item['task']}", ""])

    lines.extend(
        [
            "━━━━━━━━━━━━━━",
            "",
            "🏋️ WORKOUT",
            "",
            workout,
            "",
            "━━━━━━━━━━━━━━",
            "",
            "✦ TODAY'S THOUGHT",
            "",
            _morning_quote(),
            "",
            "━━━━━━━━━━━━━━",
            "",
            "A small start is still a start.",
        ]
    )
    return "\n".join(lines), intentions


def _task_start_body(task_name: str) -> str:
    return f"Starting {task_name} now."


def send_notification(slot: str, *, task_name: str | None = None) -> str:
    token = _token_for_slot(slot)

    if slot == "morning":
        subject = "☀️ GOOD MORNING"
        body, intentions = _morning_notification_body()
        event_model.record_planned_intentions(dates.today().isoformat(), slot, intentions)
    elif slot == "task_start":
        task = task_name or "task"
        subject = f"Task start — {task}"
        body = _task_start_body(task)
    else:
        subject = f"{slot.replace('_', ' ').title()}"
        body = task_name or f"{slot.replace('_', ' ')} notification"

    delivered_via = ""
    message_id: str | None = None
    push_error: Exception | None = None
    try:
        _send_ntfy(subject, body, tags={"morning": "sunny,calendar", "task_start": "rocket"}.get(slot.lower()))
        delivered_via = "ntfy"
    except Exception as e:
        push_error = e
        try:
            daily_log_url = f"https://notion.so/{config.DAILY_LOG_DATA_SOURCE_ID.replace('-', '')}"
            message_id = _send_email(f"[{token}] {subject}", f"{body}\n\n---\nReply in your own words if you want to capture this elsewhere.\nOr open chat in Notion: {daily_log_url}")
            if message_id:
                delivered_via = "email"
        except Exception as email_error:
            push_error = email_error

    if delivered_via:
        if slot == "morning":
            event_model.record_planned_intentions(dates.today().isoformat(), slot, intentions)
        event_model.record_notification_state(
            slot=slot,
            token=token,
            subject=subject,
            state="sent",
            channel=delivered_via,
            message_id=message_id,
        )
    else:
        event_model.record_notification_state(
            slot=slot,
            token=token,
            subject=subject,
            state="failed",
            error=str(push_error),
        )
        raise RuntimeError(f"notification delivery failed for slot {slot}: {push_error}")

    return token


def send_prompt_email(slot: str, subject_text: str, body: str) -> str:
    token = _token_for_slot(slot)
    subject = f"[{token}] {subject_text}"
    daily_log_url = f"https://notion.so/{config.DAILY_LOG_DATA_SOURCE_ID.replace('-', '')}"
    final_body = "\n".join(
        [
            body.rstrip(),
            "---",
            "Just reply to this email in your own words. No format needed.",
            f"Or open chat in Notion: {daily_log_url}",
        ]
    )

    message_id = emailer.send_email(subject, final_body)

    store.append(
        "email_sent",
        {
            "slot": slot,
            "token": token,
            "subject": subject,
            "message_id": message_id,
        },
    )

    return token


def send_task_start_notification(task_name: str) -> str:
    return send_notification("task_start", task_name=task_name)
