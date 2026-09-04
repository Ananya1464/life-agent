"""~7:00 AM IST — vegetarian fat-loss meal plan (email + appended to
the 'Weight Loss Plan — 83 → 53 kg' Notion page)."""
from life_agent import config
from life_agent import dates
from life_agent.agent import llm
from life_agent.integrations import notion_api
from life_agent.agent import prompt_loader
from life_agent.agent import quality
from life_agent.notifications import outbound


def _configured_id(value: str | None) -> bool:
    """Return True only if the ID is a real (non-placeholder) value."""
    compact = (value or "").replace("-", "").strip()
    return bool(compact) and set(compact) != {"x"}


def run():
    d = dates.today()
    try:
        outbound.send_notification("morning")
    except Exception as e:
        print(f"[notify] morning skipped: {e}")

    # Deterministic lunch rotation: even day-of-year = rajma, odd = soya.
    lunch = "rajma" if d.timetuple().tm_yday % 2 == 0 else "soya chunk (soybean) curry"
    prompt = prompt_loader.load(
        "meal_plan", TODAY_LABEL=dates.day_label(d), LUNCH_TODAY=lunch
    )
    plan = llm.generate(prompt)

    # Verification pass: double-checks the macro math.
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

    outbound.send_prompt_email(
        "morning", f"Today's meal plan — {dates.day_label(d)} 🥗", plan
    )

    if not _configured_id(config.WEIGHT_LOSS_PAGE_ID):
        print("[notion] WEIGHT_LOSS_PAGE_ID not configured — skipping Notion append.")
    else:
        try:
            notion_api.append_to_page(
                config.WEIGHT_LOSS_PAGE_ID,
                f"## 🍽️ Meal plan — {dates.day_label(d)}\n{plan}\n---",
            )
            print("[notion] appended meal plan to Weight Loss page.")
        except Exception as e:
            print(f"[notion] append failed (plan was still emailed/printed): {e}")
