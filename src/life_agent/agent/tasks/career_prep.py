"""Weekly 'global career prep' plan: a reading list, skills to build, verified opportunities worldwide and three
small steps. Same evidence-first pipeline as ai_edge (search -> synthesize from the dossier -> verify links ->
review). Output is a local note for Lifebot and Obsidian; nothing is sent anywhere."""
from life_agent import briefs
from life_agent import dates
from life_agent.agent import grounding
from life_agent.agent import llm
from life_agent.agent import prompt_loader
from life_agent.agent import quality
from life_agent.agent import research
from life_agent.agent.tasks.ai_edge import is_dossier_empty


def run():
    d = dates.today()
    goal = (
        f"Weekly global-career prep for a recent BE graduate in Mumbai (NLP/RAG/LLMs/interpretability/AI safety), "
        f"today {dates.iso(d)}: (a) a strong reading list of papers, courses or books that build toward international "
        "AI/ML research or remote engineering roles and Masters programs (NUS, Stanford, MIT, CMU, ETH); "
        "(b) the skills that recur in currently-open international research roles and fellowships; "
        "(c) currently-open programs, labs, fellowships or remote roles worldwide open to recent graduates."
    )
    prefs = briefs.preferences_text()
    if prefs:
        goal += " What she told us she wants: " + prefs
    dossier = research.deep_research(goal, n_queries=6)

    if is_dossier_empty(dossier):
        print("[career_prep] research dossier is empty: no plan generated this week")
        plan = (f"# Global career prep: {dates.day_label(d)}\n\nNo verified findings were captured this week, so "
                "no plan was generated. Try Run now again later.")
    else:
        prompt = prompt_loader.load("career_prep", TODAY_ISO=dates.iso(d), RESEARCH_NOTES=dossier,
                                    PREFERENCES=prefs or "(She has not answered the preference questions yet: ask her in the final section.)")
        plan = llm.generate(prompt, think=True)
        dead = quality.find_dead_links(plan)
        plan = quality.critique_and_revise(
            plan,
            checklist=(
                "- Has all 4 sections (Reading list / Skills / Global opportunities / Three small steps)\n"
                "- Every reading item and opportunity has a link that appears in the research dossier\n"
                "- Programs requiring current enrolment are flagged likely-ineligible\n"
                "- No invented people, deadlines or requirements; no vague filler"
            ),
            web_search=True,
            extra_issues=([f"These links are DEAD or unreachable: replace or remove them: {dead}"] if dead else None),
        )
        plan, unmatched = grounding.scrub_ungrounded(plan, dossier)
        for entity in unmatched:
            print(f"[guard] removed ungrounded entity: {entity}")
    print(plan)
    briefs.save("career_prep", plan)
