"""Date helpers, all in Ananya's timezone (Asia/Kolkata by default)."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import config

TZ = ZoneInfo(config.TIMEZONE)


def today() -> date:
    return datetime.now(TZ).date()


def tomorrow() -> date:
    return today() + timedelta(days=1)


def day_label(d: date) -> str:
    """Notion 'Day' title format, e.g. 'Tue, Jul 7' (no leading zero)."""
    return f"{d.strftime('%a')}, {d.strftime('%b')} {d.day}"


def iso(d: date) -> str:
    return d.isoformat()


# Body used when a Daily Log row doesn't exist yet and the agent creates it.
NEW_ENTRY_BODY = """## 🌅 Your AI Edge

{ai_edge}

---

## 🌙 Tomorrow's Plan

{tomorrow_plan}

---

## ✍️ What I achieved today

> Jot down what you actually got done — courses, job applications, professor emails, anything. This is what tonight's plan reads from.

- """

AI_EDGE_PLACEHOLDER = "> The 8 AM briefing drops here each morning."
PLAN_PLACEHOLDER = "> Written at 11 PM, tailored to what you logged in Achievements today."
