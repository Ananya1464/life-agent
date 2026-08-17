"""On-demand task to break ADHD paralysis.
Reads the current plan, finds the active time block, and pushes a tiny next step to the user's phone via ntfy."""
import re
import requests
from datetime import datetime, timezone, timedelta

from life_agent import config
from life_agent import dates
from life_agent.agent import llm
from life_agent.integrations import notion_api
from life_agent.agent import prompt_loader

_TIME_RE = re.compile(
    r"(\d{1,2}:\d{2})\s*(?:–|—|-|to)\s*(\d{1,2}:\d{2})\s+(.+)",
)

def run():
    if not config.NTFY_TOPIC:
        print("[unstick] NTFY_TOPIC not set — skipping.")
        return

    today = dates.today()
    ist = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(ist)

    # STEP 1 — read today's plan
    plan_text = ""
    try:
        entry = notion_api.find_entry_by_date(dates.iso(today))
        if entry:
            plan_text = (
                notion_api.get_section_text(entry["id"], "📋 Full Day Plan")
                or notion_api.get_section_text(entry["id"], "Tomorrow's Plan")
                or ""
            )
    except Exception as e:
        print(f"[unstick] failed reading today's entry: {e}")

    if not plan_text.strip():
        print("[unstick] no plan found for today.")
        return

    # STEP 2 — find active task
    items = _TIME_RE.findall(plan_text)
    active_task = "You don't have anything scheduled right now. Just breathe!"
    
    for start_str, end_str, description in items:
        h1, m1 = map(int, start_str.split(':'))
        h2, m2 = map(int, end_str.split(':'))
        
        start_time = now.replace(hour=h1, minute=m1, second=0, microsecond=0)
        end_time = now.replace(hour=h2, minute=m2, second=0, microsecond=0)
        
        if start_time <= now <= end_time:
            active_task = f"{start_str} - {end_str}: {description.strip()}"
            break

    # STEP 3 - generate friction-free physical action
    prompt = prompt_loader.load("unstick_me", CURRENT_TASK=active_task)
    action = llm.generate(prompt)

    # STEP 4 - push notification
    try:
        requests.post(
            f"https://ntfy.sh/{config.NTFY_TOPIC}",
            data=action.encode('utf-8'),
            headers={
                "Title": "⚡ Unstick Me",
                "Tags": "zap,brain"
            },
            timeout=10
        )
        print(f"[unstick] pushed action to ntfy: {action}")
    except Exception as e:
        print(f"[unstick] failed pushing to ntfy: {e}")
