"""~8:00 AM IST — 'Your AI Edge' deep-researched briefing.
Pipeline (mirrors Claude's Cowork research runs):
  read memory (recent Notion briefings) → plan queries → search web →
  synthesize from evidence → verify links → critique/revise → deliver.
Primary delivery: today's Notion Daily Log entry. Email is secondary."""
from datetime import timedelta

import dates
import emailer
import llm
import notion_api
import prompt_loader
import quality
import research


def _recently_covered(days: int = 3) -> str:
    """Last few days' briefings — so today's never repeats them."""
    out = []
    for i in range(1, days + 1):
        day = dates.today() - timedelta(days=i)
        try:
            entry = notion_api.find_entry_by_date(dates.iso(day))
            if entry:
                text = notion_api.get_section_text(entry["id"], "Your AI Edge")
                if text:
                    out.append(f"[{dates.day_label(day)}]\n{text[:1500]}")
        except Exception:
            pass
    return "\n\n".join(out) or "(nothing — first run or no recent entries)"


def run():
    d = dates.today()

    # 1-2. Plan queries + search the live web (multi-query, evidence-based)
    goal = (
        f"Daily 'AI Edge' scout for a recent BE grad in Mumbai focused on "
        f"NLP/RAG/LLMs/interpretability/AI safety (today: {dates.iso(d)}): "
        "(a) currently-open AI/ML research fellowships, RA/pre-doctoral "
        "programs, and remote NLP/LLM engineer roles open to recent graduates "
        "(remote or India); (b) notable NLP/RAG/interpretability/AI-safety "
        "papers or releases from the last few days; (c) one current, concrete "
        "skill/project/income trend she could act on; (d) one AI-market "
        "headline from today."
    )
    dossier = research.deep_research(goal, n_queries=6)

    # 3. Synthesize the briefing FROM the evidence (with anti-repeat memory)
    prompt = prompt_loader.load(
        "ai_edge",
        TODAY_LABEL=dates.day_label(d),
        TODAY_ISO=dates.iso(d),
        RESEARCH_NOTES=dossier,
        RECENTLY_COVERED=_recently_covered(),
    )
    briefing = llm.generate(prompt, think=True)

    # 4. Verify: HTTP-check every link, then a reviewer pass
    dead = quality.find_dead_links(briefing)
    briefing = quality.critique_and_revise(
        briefing,
        checklist=(
            "- Has all 4 sections (Opportunities / Research+news / One leverage "
            "idea / Market note) and is under ~320 words\n"
            "- Every opportunity has a link and says why it fits Ananya "
            "(NLP/RAG, recent grad, remote or India)\n"
            "- Programs requiring current enrollment are flagged likely-ineligible\n"
            "- Nothing repeats the 'already covered' items\n"
            "- No vague filler; no invented deadlines"
        ),
        web_search=True,
        extra_issues=(
            [f"These links are DEAD or unreachable — replace or remove them: {dead}"]
            if dead else None
        ),
    )
    print(briefing)

    # 5. Deliver — Notion primary, email secondary
    try:
        entry = notion_api.find_entry_by_date(dates.iso(d))
        if entry:
            notion_api.replace_section(entry["id"], "Your AI Edge", briefing)
            print("[notion] updated today's AI Edge section.")
        else:
            body = dates.NEW_ENTRY_BODY.format(
                ai_edge=briefing, tomorrow_plan=dates.PLAN_PLACEHOLDER
            )
            notion_api.create_daily_entry(dates.day_label(d), dates.iso(d), body)
            print("[notion] created today's entry with the briefing.")
    except Exception as e:
        print(f"[notion] write failed (briefing still emailed/printed): {e}")

    emailer.send(f"Your AI Edge — {dates.day_label(d)}", briefing)
