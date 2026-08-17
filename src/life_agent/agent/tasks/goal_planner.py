"""~10:30 PM IST — convert 'Tomorrow's Goals' into a time-blocked full-day plan.
Reads goals from today's Notion entry, builds a schedule around calendar events,
and writes the plan into tomorrow's entry under '📋 Full Day Plan'."""
from datetime import timedelta

from life_agent.integrations import calendar_feed
from life_agent import dates
from life_agent.notifications import emailer
from life_agent.agent import llm
from life_agent.integrations import notion_api
from life_agent.agent import prompt_loader
from life_agent.agent import quality


def _completion_stats(days: int = 7) -> str:
    """Read the last `days` entries and summarise how many had achievements."""
    logged, total = 0, 0
    for i in range(1, days + 1):
        d = dates.today() - timedelta(days=i)
        try:
            entry = notion_api.find_entry_by_date(dates.iso(d))
            total += 1
            if entry:
                ach = notion_api.get_prop_text(entry, "Achievements")
                if ach and ach.strip():
                    logged += 1
        except Exception:
            pass
    if total == 0:
        return "(no recent data)"
    return f"{logged}/{total} days had achievements logged ({logged/total:.0%} rate)"


def run():
    import random
    today, tmrw = dates.today(), dates.tomorrow()

    # STEP 1 — read goals from today's entry
    goals = ""
    achievements_today = "(no entry found)"
    try:
        entry = notion_api.find_entry_by_date(dates.iso(today))
        if entry:
            goals = notion_api.get_prop_text(entry, "Tomorrow's Goals") or ""
            achievements_today = (
                notion_api.get_prop_text(entry, "Achievements") or "(empty)"
            )
    except Exception as e:
        print(f"[notion] read failed: {e}")

    if not goals.strip():
        print("[goal_planner] no goals set in 'Tomorrow's Goals' — skipping.")
        return

    # STEP 2 — gather context
    events = calendar_feed.events_on(tmrw)
    cal_text = "; ".join(events) if events else "(none / calendar not connected)"
    stats = _completion_stats()
    
    # ADHD Context: Energy Level
    energy_level = "Unknown (Assume normal)"
    try:
        checkin_entry = notion_api.find_checkin_by_date(dates.iso(today))
        if checkin_entry:
            val = notion_api.get_prop_text(checkin_entry, "Energy Level")
            if val:
                energy_level = val.strip()
    except Exception as e:
        print(f"[notion] could not fetch energy level: {e}")
        
    # ADHD Context: Dopamine Menu
    dopamine_items = "(No items configured)"
    try:
        all_dopamine = notion_api.fetch_dopamine_menu_items()
        if all_dopamine:
            dopamine_items = "\n".join("- " + item for item in random.sample(all_dopamine, min(3, len(all_dopamine))))
    except Exception as e:
        print(f"[notion] could not fetch dopamine menu: {e}")

    # STEP 3 — generate the plan
    prompt = prompt_loader.load(
        "goal_planner",
        TOMORROW_LABEL=dates.day_label(tmrw),
        GOALS=goals,
        CALENDAR_EVENTS=cal_text,
        RECENT_COMPLETION_STATS=stats,
        ACHIEVEMENTS_TODAY=achievements_today,
        ENERGY_LEVEL=energy_level,
        DOPAMINE_MENU=dopamine_items,
    )
    plan = llm.generate(prompt)

    # Verification pass
    plan = quality.critique_and_revise(
        plan,
        checklist=(
            "- Every goal broken down into 15-20m physical micro-steps\n"
            "- 30% time padding applied to all blocks\n"
            "- 30m Context-Switch Reset blocks between major category shifts\n"
            "- Explicit dopamine menu items scheduled instead of generic breaks\n"
            "- High contrast visual formatting (emoji, bold main physical actions)\n"
            "- If Energy is Low, 50% non-essential goals dropped"
        ),
    )
    print(plan)

    # STEP 4 — write to tomorrow's Notion entry
    try:
        entry = notion_api.find_entry_by_date(dates.iso(tmrw))
        if entry:
            notion_api.replace_section(entry["id"], "📋 Full Day Plan", plan)
            print("[notion] updated full day plan section.")
        else:
            body = f"## 📋 Full Day Plan\n\n{plan}\n\n---\n"
            notion_api.create_daily_entry(dates.day_label(tmrw), dates.iso(tmrw), body)
            print("[notion] created tomorrow's entry with the plan.")
    except Exception as e:
        print(f"[notion] write failed (plan still emailed/printed): {e}")

    emailer.send(f"Full day plan — {dates.day_label(tmrw)} 📋", plan)
