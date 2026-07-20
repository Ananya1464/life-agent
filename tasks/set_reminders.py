"""~11:00 PM IST — parse tomorrow's time-blocked plan and create Notion reminders.
Requires REMINDERS_DB_ID to be set in .env (otherwise skips silently)."""
import re

import config
import dates
import notion_api


_TIME_RE = re.compile(
    r"(\d{1,2}:\d{2})\s*(?:–|—|-|to)\s*\d{1,2}:\d{2}\s+(.+)",
)


def run():
    if not config.NTFY_TOPIC:
        print("[reminders] NTFY_TOPIC not set — skipping.")
        return

    tmrw = dates.tomorrow()

    # STEP 1 — read tomorrow's plan
    plan_text = ""
    try:
        entry = notion_api.find_entry_by_date(dates.iso(tmrw))
        if entry:
            plan_text = (
                notion_api.get_section_text(entry["id"], "📋 Full Day Plan")
                or notion_api.get_section_text(entry["id"], "Tomorrow's Plan")
                or ""
            )
    except Exception as e:
        print(f"[reminders] failed reading tomorrow's entry: {e}")

    if not plan_text.strip():
        print("[reminders] no plan found for tomorrow — skipping.")
        return

    # STEP 2 — parse time-blocked items
    items = _TIME_RE.findall(plan_text)
    if not items:
        print("[reminders] no time-blocked items found in plan.")
        return

    # STEP 3 — create ntfy reminders
    import requests
    from datetime import datetime, timezone, timedelta
    
    created = 0
    ist = timezone(timedelta(hours=5, minutes=30))
    
    for time_str, description in items:
        # Normalise "6:30" → "06:30"
        hh, mm = time_str.split(":")
        iso_dt = f"{dates.iso(tmrw)}T{int(hh):02d}:{mm}:00"
        title = description.strip().rstrip("*").strip()
        
        dt = datetime.fromisoformat(iso_dt).replace(tzinfo=ist)
        unix_ts = int(dt.timestamp())
        
        # Add a 5 minute advance warning
        unix_ts_warning = unix_ts - 300
        
        try:
            requests.post(
                f"https://ntfy.sh/{config.NTFY_TOPIC}",
                data=f"{time_str} - {title}".encode('utf-8'),
                headers={
                    "Title": "Life Agent 🧠 Next Task",
                    "Delay": str(unix_ts_warning),
                    "Tags": "calendar_spiral"
                },
                timeout=10
            )
            created += 1
        except Exception as e:
            print(f"[reminders] failed creating reminder for {time_str}: {e}")

    print(f"[reminders] scheduled {created}/{len(items)} push notifications via ntfy for {dates.day_label(tmrw)}.")
