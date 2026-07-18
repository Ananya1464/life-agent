"""~10:00 PM IST — adaptive 'Tomorrow's plan'.
Reads today's achievements from Notion, writes the plan into tomorrow's entry."""
import calendar_feed
import dates
import emailer
import llm
import notion_api
import prompt_loader
import quality


def run():
    today, tmrw = dates.today(), dates.tomorrow()

    # STEP 1 — read today's progress from Notion (this makes the plan adaptive)
    achievements, achieved_section = "(no entry found)", "(no entry found)"
    try:
        entry = notion_api.find_entry_by_date(dates.iso(today))
        if entry:
            achievements = notion_api.get_prop_text(entry, "Achievements") or "(empty)"
            achieved_section = (
                notion_api.get_section_text(entry["id"], "What I achieved today")
                or "(empty)"
            )
    except Exception as e:
        print(f"[notion] read failed, planning without today's log: {e}")

    events = calendar_feed.events_on(tmrw)
    cal_text = "; ".join(events) if events else "(none / calendar not connected)"

    # STEP 2 — produce the briefing
    prompt = prompt_loader.load(
        "tomorrow_planner",
        TODAY_LABEL=dates.day_label(today),
        TOMORROW_LABEL=dates.day_label(tmrw),
        ACHIEVEMENTS=achievements,
        ACHIEVED_SECTION=achieved_section,
        CALENDAR_EVENTS=cal_text,
    )
    plan = llm.generate(prompt)

    # Verification pass: does the plan actually reflect what she logged?
    plan = quality.critique_and_revise(
        plan,
        checklist=(
            "- Under 200 words, exactly 3 sections (3 priorities / outreach "
            "quota / one reflection prompt)\n"
            f"- Does NOT re-assign anything already completed in: "
            f"{achievements} | {achieved_section}\n"
            "- Names a specific professor to contact first\n"
            "- No invented deadlines"
        ),
    )
    print(plan)

    # STEP 3 — write it into TOMORROW's Notion entry (primary delivery)
    try:
        entry = notion_api.find_entry_by_date(dates.iso(tmrw))
        if entry:
            notion_api.replace_section(entry["id"], "Tomorrow's Plan", plan)
            print("[notion] updated tomorrow's plan section.")
        else:
            body = dates.NEW_ENTRY_BODY.format(
                ai_edge=dates.AI_EDGE_PLACEHOLDER, tomorrow_plan=plan
            )
            notion_api.create_daily_entry(dates.day_label(tmrw), dates.iso(tmrw), body)
            print("[notion] created tomorrow's entry with the plan.")
    except Exception as e:
        print(f"[notion] write failed (plan still emailed/printed): {e}")

    emailer.send(f"Tomorrow's 3 priorities — {dates.day_label(tmrw)}", plan)
