"""Entry point. Run one task:  python main.py <task>
Or run self-test:              python main.py --selftest
"""
import importlib
import sys
from datetime import datetime

TASKS = (
    "meal_plan", "ai_edge", "evening_checkin",
    "goal_planner", "tomorrow_planner", "set_reminders",
    "weekly_review", "unstick_me", "deep_work_session",
)


def run(task: str):
    if task not in TASKS:
        sys.exit(f"Unknown task '{task}'. Choose from: {', '.join(TASKS)}")
    mod = importlib.import_module(f"tasks.{task}")
    mod.run()


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

    try:
        run(arg)
    except Exception as e:
        print(f"Task failed: {e}", file=sys.stderr)
        sys.exit(1)

