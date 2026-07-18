"""~7:00 AM IST — vegetarian fat-loss meal plan (email + appended to
the 'Weight Loss Plan — 83 → 53 kg' Notion page)."""
import config
import dates
import emailer
import llm
import notion_api
import prompt_loader
import quality


def run():
    d = dates.today()
    # Deterministic lunch rotation: even day-of-year = rajma, odd = soya.
    lunch = "rajma" if d.timetuple().tm_yday % 2 == 0 else "soya chunk (soybean) curry"
    prompt = prompt_loader.load(
        "meal_plan", TODAY_LABEL=dates.day_label(d), LUNCH_TODAY=lunch
    )
    plan = llm.generate(prompt)

    # Verification pass: Claude double-checks the macro math — so do we.
    plan = quality.critique_and_revise(
        plan,
        checklist=(
            "- Per-meal calories and protein actually SUM to the stated totals "
            "(recompute the arithmetic)\n"
            "- Total lands near 1,600 kcal and 110–120 g protein\n"
            f"- Lunch is {lunch} as required by today's rotation\n"
            "- Fully vegetarian, concise and skimmable"
        ),
    )
    print(plan)

    emailer.send(f"Today's meal plan — {dates.day_label(d)} 🥗", plan)
    try:
        notion_api.append_to_page(
            config.WEIGHT_LOSS_PAGE_ID,
            f"## 🍽️ Meal plan — {dates.day_label(d)}\n{plan}\n---",
        )
        print("[notion] appended meal plan to Weight Loss page.")
    except Exception as e:
        print(f"[notion] append failed (plan was still emailed/printed): {e}")
