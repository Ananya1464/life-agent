"""Deep-research engine — replicates the multi-step research pipeline Claude
uses for Cowork research tasks, instead of one shallow search call:

  1. PLAN       — decompose the goal into targeted search queries
  2. SEARCH     — run each query against the live web, collect evidence notes
                  with exact URLs and dates
  3. SYNTHESIZE — the caller writes the final output FROM the evidence
  (4. VERIFY    — quality.py link-checks and critiques the result)
"""
from life_agent.agent import llm


def plan_queries(goal: str, n: int = 6) -> list[str]:
    raw = llm.generate(
        f"You are a research planner. Today's research goal:\n{goal}\n\n"
        f"Decompose this into exactly {n} distinct, specific web search queries "
        "that together cover the goal from different angles (include recency "
        "words like 'this week' / current month-year where useful). "
        "Output ONLY the queries, one per line, no numbering.",
        think=True,
        temperature=0.8,
    )
    queries = [q.strip("-• ").strip() for q in raw.splitlines() if q.strip()]
    return queries[:n]


def search_one(query: str) -> str:
    return llm.generate(
        f"Search the web for: {query}\n\n"
        "Report ONLY concrete, current findings: names, exact URLs, dates, "
        "deadlines, eligibility, one-line substance of each item. "
        "3-8 bullet findings. No fluff, no speculation, no invented links. "
        "If nothing solid is found, reply exactly: NOTHING FOUND.",
        web_search=True,
        think=False,
        temperature=0.3,
    )


def deep_research(goal: str, n_queries: int = 6) -> str:
    """Returns an evidence dossier the synthesis prompt can cite from."""
    notes = []
    for q in plan_queries(goal, n_queries):
        print(f"[research] searching: {q}")
        try:
            finding = search_one(q)
        except Exception as e:
            finding = f"(search failed: {e})"
        if "NOTHING FOUND" not in finding:
            notes.append(f"### Query: {q}\n{finding}")
    if not notes:
        raise RuntimeError("Deep research produced no usable findings")
    return "\n\n".join(notes)
