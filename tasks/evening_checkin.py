"""~9:30 PM IST — weight-loss habit accountability check-in.
Writes to today's Notion Daily Log entry under '🌙 Evening Check-in' and emails."""
import dates
import emailer
import llm
import notion_api
import prompt_loader


def run():
    d = dates.today()
    prompt = prompt_loader.load("evening_checkin", TODAY_LABEL=dates.day_label(d))
    nudge = llm.generate(prompt, temperature=0.9)  # higher temp → varied wording
    print(nudge)

    # Write to today's Notion Daily Log entry (primary delivery)
    try:
        entry = notion_api.find_entry_by_date(dates.iso(d))
        if entry:
            notion_api.replace_section(entry["id"], "🌙 Evening Check-in", nudge)
            print("[notion] updated evening check-in section.")
        else:
            body = f"## 🌙 Evening Check-in\n\n{nudge}\n\n---\n"
            notion_api.create_daily_entry(dates.day_label(d), dates.iso(d), body)
            print("[notion] created today's entry with evening check-in.")
    except Exception as e:
        print(f"[notion] write failed (check-in still emailed/printed): {e}")

    emailer.send(f"Evening check-in — {dates.day_label(d)} 🌙", nudge)
