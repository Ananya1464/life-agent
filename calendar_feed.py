"""Optional read-only Google Calendar access via the calendar's *secret iCal URL*.
No OAuth needed: Google Calendar → Settings → your calendar →
'Secret address in iCal format'. Put that URL in the ICAL_URL secret."""
from datetime import date, datetime

import config


def events_on(day: date) -> list[str]:
    """Return e.g. ['09:00 Deep work block', '18:30 Gym'] for the given day."""
    if not config.ICAL_URL:
        return []
    try:
        import requests
        from ics import Calendar

        cal = Calendar(requests.get(config.ICAL_URL, timeout=30).text)
        out = []
        for ev in cal.events:
            begin = ev.begin.datetime if hasattr(ev.begin, "datetime") else ev.begin
            if isinstance(begin, datetime) and begin.date() == day:
                out.append(f"{begin.strftime('%H:%M')} {ev.name or '(untitled)'}")
        return sorted(out)
    except Exception as e:
        print(f"[calendar] failed (continuing): {e}")
        return []
