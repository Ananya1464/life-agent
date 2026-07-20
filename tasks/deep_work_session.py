"""Simulated Body Doubling session.
Dispatches 4 delayed push notifications to ntfy.sh (at +30m, +60m, +90m, +120m) 
to act as accountability checks during a deep work session."""
import requests
from datetime import datetime, timezone, timedelta
import random

import config

def run():
    if not config.NTFY_TOPIC:
        print("[deep_work] NTFY_TOPIC not set — skipping.")
        return

    ist = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(ist)

    messages = [
        "👀 Quick check: What are you working on right now?",
        "🧠 Body double check-in: Are you still on task?",
        "⏳ 30 minutes passed! Are you focused or wandering?",
        "🚀 Keep going! What's the exact physical step you are doing now?",
        "🎯 Focus check! Reply out loud: what is your current micro-step?"
    ]

    print("[deep_work] Initiating a 2-hour body-doubling session...")

    for i in range(1, 5):
        delay_mins = i * 30
        ping_time = now + timedelta(minutes=delay_mins)
        unix_ts = int(ping_time.timestamp())
        
        msg = random.choice(messages)
        
        try:
            requests.post(
                f"https://ntfy.sh/{config.NTFY_TOPIC}",
                data=msg.encode('utf-8'),
                headers={
                    "Title": "Life Agent 🤝 Body Double",
                    "Delay": str(unix_ts),
                    "Tags": "eyes,hourglass"
                },
                timeout=10
            )
            print(f"  - Scheduled ping for {ping_time.strftime('%H:%M')} (+{delay_mins}m)")
        except Exception as e:
            print(f"  - Failed scheduling ping for +{delay_mins}m: {e}")
            
    print("[deep_work] Session successfully scheduled. Get to work!")
