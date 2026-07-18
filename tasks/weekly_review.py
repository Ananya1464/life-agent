"""Weekly review — generates a 7-day intelligence report from Notion logs.
Best run on Sunday evening or Monday morning."""
from datetime import timedelta

import dates
import emailer
import llm
import notion_api
import prompt_loader


def run():
    today = dates.today()
    week_start = today - timedelta(days=6)
    week_label = f"{dates.day_label(week_start)} → {dates.day_label(today)}"

    # STEP 1 — read the last 7 days
    daily_summaries = []
    goals_vs_achievements = []
    for i in range(6, -1, -1):  # oldest first
        d = today - timedelta(days=i)
        label = dates.day_label(d)
        achievements = "(no entry)"
        goals = ""
        achieved_section = ""
        try:
            entry = notion_api.find_entry_by_date(dates.iso(d))
            if entry:
                achievements = (
                    notion_api.get_prop_text(entry, "Achievements") or "(empty)"
                )
                goals = (
                    notion_api.get_prop_text(entry, "Tomorrow's Goals") or "(none set)"
                )
                achieved_section = (
                    notion_api.get_section_text(entry["id"], "What I achieved today")
                    or ""
                )
        except Exception as e:
            print(f"[notion] failed reading {label}: {e}")

        summary = f"**{label}**: {achievements}"
        if achieved_section:
            summary += f"\n  Details: {achieved_section}"
        daily_summaries.append(summary)
        goals_vs_achievements.append(
            f"**{label}** — Goals: {goals} | Achieved: {achievements}"
        )

    summaries_text = "\n\n".join(daily_summaries)
    gva_text = "\n".join(goals_vs_achievements)

    # STEP 2 — generate the review
    prompt = prompt_loader.load(
        "weekly_review",
        WEEK_LABEL=week_label,
        DAILY_SUMMARIES=summaries_text,
        GOALS_VS_ACHIEVEMENTS=gva_text,
    )
    review = llm.generate(prompt)
    print(review)

    # STEP 3 — write to today's Notion entry
    try:
        entry = notion_api.find_entry_by_date(dates.iso(today))
        if entry:
            notion_api.replace_section(entry["id"], "📊 Weekly Review", review)
            print("[notion] updated weekly review section.")
        else:
            body = f"## 📊 Weekly Review\n\n{review}\n\n---\n"
            notion_api.create_daily_entry(dates.day_label(today), dates.iso(today), body)
            print("[notion] created today's entry with the review.")
    except Exception as e:
        print(f"[notion] write failed (review still emailed/printed): {e}")

    emailer.send(f"Weekly review — {week_label} 📊", review)
