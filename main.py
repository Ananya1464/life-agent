"""Entry point. Run one task:  python main.py <task>
Or run self-test:              python main.py --selftest
"""
import json
import importlib
import sys
from datetime import datetime

import inbound
import dates
import event_model
import metrics
import store
import outbound

TASKS = (
    "meal_plan", "ai_edge", "evening_checkin",
    "goal_planner", "tomorrow_planner", "set_reminders",
    "weekly_review", "unstick_me", "deep_work_session",
)


def run(task: str):
    if task not in TASKS:
        sys.exit(f"Unknown task '{task}'. Choose from: {', '.join(TASKS)}")
    mod = importlib.import_module(f"tasks.{task}")
    event_model.record_task_started(task, date_iso=dates.today().isoformat())
    try:
        outbound.send_task_start_notification(task)
        mod.run()
        event_model.record_task_completed(task, date_iso=dates.today().isoformat())
        metrics.update_metrics()
    except Exception as e:
        store.append("task_failed", {"task": task, "error": str(e)})
        raise


def read_replies() -> list[dict]:
    replies = inbound.fetch_replies()
    return replies


def selftest():
    import emailer
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"life-agent selftest {timestamp}"
    body = f"This is a self-test email from life-agent sent at {timestamp}."
    emailer.send_email(subject, body, debug=True)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)

    arg = sys.argv[1]
    if arg == "--selftest":
        try:
            selftest()
            sys.exit(0)
        except Exception as e:
            print(f"Selftest failed: {e}", file=sys.stderr)
            sys.exit(1)
    if arg == "--read-replies":
        try:
            print(json.dumps(read_replies(), ensure_ascii=False, indent=2))
            metrics.update_metrics()
            sys.exit(0)
        except Exception as e:
            print(f"Read-replies failed: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        run(arg)
    except Exception as e:
        print(f"Task failed: {e}", file=sys.stderr)
        sys.exit(1)

