"""Entry point. Run one task:  python main.py <task>

Tasks:
  meal_plan         ~7:00 AM IST  — vegetarian fat-loss meal plan → email + Weight Loss page
  ai_edge           ~8:00 AM IST  — web-researched AI briefing → Notion Daily Log
  evening_checkin   ~9:30 PM IST  — habit accountability nudge → email
  goal_planner      ~9:45 PM IST  — goals → time-blocked plan for tomorrow → Notion + email
  tomorrow_planner  ~10:00 PM IST — adaptive plan for tomorrow → Notion Daily Log
  set_reminders     ~10:15 PM IST — parse tomorrow's plan → Notion reminders → phone push
  weekly_review     Sun ~8:00 PM  — 7-day performance review → Notion + email
"""
import importlib
import sys

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


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    run(sys.argv[1])
