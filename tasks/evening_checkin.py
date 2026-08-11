"""~9:30 PM IST — weight-loss habit accountability check-in.
Writes to the dedicated Evening Check-in database in Notion and emails."""
import dates
import event_model
import llm
import notion_api
import prompt_loader
import outbound


def run():
    d = dates.today()
    evening_intentions = [
        {"task": "Logged all meals", "life_area": "Health"},
        {"task": "Hit protein target (110–120 g)", "life_area": "Health"},
        {"task": "Stayed around 1,600 kcal", "life_area": "Health"},
        {"task": "8,000+ steps", "life_area": "Health"},
        {"task": "Workout done (if a training day)", "life_area": "Health"},
        {"task": "2.5 L+ water", "life_area": "Health"},
        {"task": "7+ hours sleep planned", "life_area": "Personal"},
    ]
    prompt = prompt_loader.load("evening_checkin", TODAY_LABEL=dates.day_label(d))
    nudge = llm.generate(prompt, temperature=0.9)  # higher temp → varied wording
    print(nudge)

    # Write to the dedicated Evening Check-in database (primary delivery)
    try:
        existing = notion_api.find_checkin_by_date(dates.iso(d))
        if existing:
            # Update today's existing entry
            notion_api.replace_section(existing["id"], "Evening Check-in", nudge)
            print("[notion] updated today's evening check-in entry.")
        else:
            # Create a new entry for today
            notion_api.create_checkin_entry(
                dates.day_label(d), dates.iso(d), nudge
            )
            print("[notion] created evening check-in entry.")
    except Exception as e:
        print(f"[notion] write failed (check-in still emailed/printed): {e}")

    # Also write to the Daily Log (secondary — so tomorrow_planner can see it)
    try:
        entry = notion_api.find_entry_by_date(dates.iso(d))
        if entry:
            notion_api.replace_section(entry["id"], "🌙 Evening Check-in", nudge)
    except Exception:
        pass  # best-effort, the dedicated DB is the primary

    outbound.send_prompt_email(
        "evening", f"Evening check-in — {dates.day_label(d)} 🌙", nudge
    )
    event_model.record_planned_intentions(dates.iso(d), "evening", evening_intentions)
