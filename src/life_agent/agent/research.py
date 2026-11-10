"""Deep-research engine — gathers verified research papers and live web evidence:

1. PAPERS: Queries arXiv API (and Hugging Face Daily Papers) for recent, verified
   papers with real titles, authors, and URLs. Treated as a resilient fallback.
2. OPPORTUNITIES & NEWS: Searches live web for real fellowships, pre-doc roles,
   and market trends.
3. EVIDENCE DOSSIER: Synthesized into structured evidence without fabrication.
   If evidence is unavailable for an item, it is explicitly omitted.
"""
import re
import time
import xml.etree.ElementTree as ET
import requests

from life_agent import browseros
from life_agent.agent import llm


def fetch_arxiv_papers(query: str = "cat:cs.CL AND (all:RAG OR all:retrieval OR all:interpretability OR all:safety)", max_results: int = 3) -> list[dict]:
    """Fetch recent verified papers from arXiv API. Treated as a resilient fallback."""
    url = f"http://export.arxiv.org/api/query?search_query={requests.utils.quote(query)}&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
    try:
        r = requests.get(url, timeout=12)
        if r.status_code != 200:
            print(f"[research] arXiv API returned status {r.status_code}")
            return []
        root = ET.fromstring(r.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        papers = []
        for entry in root.findall("atom:entry", ns):
            title = (entry.find("atom:title", ns).text or "").strip().replace("\n", " ")
            summary = (entry.find("atom:summary", ns).text or "").strip().replace("\n", " ")
            link = (entry.find("atom:id", ns).text or "").strip()
            published = (entry.find("atom:published", ns).text or "").strip()[:10]
            authors = [a.find("atom:name", ns).text.strip() for a in entry.findall("atom:author", ns) if a.find("atom:name", ns) is not None]
            papers.append({
                "title": title,
                "authors": ", ".join(authors[:3]),
                "published": published,
                "url": link,
                "summary": summary[:300] + ("..." if len(summary) > 300 else ""),
            })
        return papers
    except Exception as e:
        print(f"[research] arXiv fallback request note: {e}")
        return []


def plan_queries(goal: str, n: int = 4) -> list[str]:
    raw = llm.generate(
        f"You are a research planner. Today's research goal:\n{goal}\n\n"
        f"Decompose this into exactly {n} distinct, specific web search queries "
        "for currently-open AI/ML research fellowships, pre-doc programs, and NLP/LLM engineer roles "
        "in India or remote. "
        "Output ONLY the queries, one per line, no numbering.",
        think=False,
        temperature=0.7,
    )
    queries = [q.strip("-• ").strip() for q in raw.splitlines() if q.strip()]
    return queries[:n]


SEARCH_STAGGER_SECONDS = 1.5
SEARCH_UNAVAILABLE = "NOTHING FOUND (live web search was unavailable)"


def api_search(query: str, limit: int = 8) -> list[dict] | None:
    """Real web results from a search API when a key is configured: TAVILY_API_KEY or BRAVE_API_KEY.
    Returns [{title, url, snippet}] ([] if nothing found), or None when no key is set or the call failed."""
    import os

    tavily, brave = os.getenv("TAVILY_API_KEY", "").strip(), os.getenv("BRAVE_API_KEY", "").strip()
    try:
        if tavily:
            r = requests.post("https://api.tavily.com/search", timeout=25,
                              headers={"Authorization": f"Bearer {tavily}"},
                              json={"query": query, "max_results": limit, "search_depth": "basic"})
            r.raise_for_status()
            return [{"title": x.get("title", ""), "url": x.get("url", ""), "snippet": x.get("content", "")[:400]}
                    for x in r.json().get("results", []) if str(x.get("url", "")).startswith("http")]
        if brave:
            r = requests.get("https://api.search.brave.com/res/v1/web/search", timeout=25,
                             headers={"X-Subscription-Token": brave, "Accept": "application/json"},
                             params={"q": query, "count": limit})
            r.raise_for_status()
            return [{"title": x.get("title", ""), "url": x.get("url", ""), "snippet": x.get("description", "")[:400]}
                    for x in r.json().get("web", {}).get("results", []) if str(x.get("url", "")).startswith("http")]
    except Exception as e:
        print(f"[research] search API failed for '{query[:40]}': {str(e)[:120]}")
    return None


_FACT_KEYS = re.compile(
    r"(deadline|apply by|applications?\s+(?:are\s+)?(?:due|close|closed|open)|closes?|due\s+(?:on\s+)?[A-Z][a-z]+|rolling|"
    r"eligib|open to|enrolled|undergraduate|graduate students?|recent graduates?|remote|online|stipend)", re.I)


def page_facts(url: str, max_facts: int = 4, timeout: int = 12) -> list[str]:
    """Short sentences from the opportunity's own page that state a deadline, status or eligibility rule.
    Plain HTTP (no JavaScript); [] when the page cannot be read. These are quoted facts, never inferred."""
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (life-agent research)"}, timeout=timeout)
        if r.status_code >= 400:
            return []
        html = r.text
    except Exception:
        return []
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    facts: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\s{2,}", text):
        s = sentence.strip()
        if 25 <= len(s) <= 220 and _FACT_KEYS.search(s) and re.search(r"\d{1,2}\s*(?:st|nd|rd|th)?\b|20\d\d|closed|rolling|open", s, re.I):
            if s not in facts:
                facts.append(s)
        if len(facts) >= max_facts:
            break
    return facts


def _summarize_results(query: str, hits: list[dict]) -> str:
    from concurrent.futures import ThreadPoolExecutor

    top = hits[:4]                                       # read the top pages themselves: snippets rarely carry deadlines
    with ThreadPoolExecutor(max_workers=4) as pool:      # in parallel: one slow site no longer stalls the others
        all_facts = list(pool.map(lambda h: page_facts(h["url"]), top))
    for h, facts in zip(top, all_facts):
        if facts:
            h["snippet"] = (h["snippet"] + " || PAGE SAYS: " + " | ".join(facts))[:900]
    listing = "\n".join(f"- {h['title']} | {h['url']} | {h['snippet']}" for h in hits)
    return llm.generate(
        f"Search query: {query}\n\nReal search results (the ONLY sources you may use):\n{listing}\n\n"
        "Where a result has 'PAGE SAYS:' text, that is quoted from the opportunity's own page: use it for the deadline, "
        "open/closed status and eligibility, and if it contradicts itself (for example a future deadline next to "
        "'applications closed'), report both statements as written. "
        "From these results only, list the concrete opportunities or findings: name, the exact URL from the list, "
        "deadline or date if the snippet states one, eligibility if stated. Do not add anything the results do not say. "
        "Skip results that are not an actual opportunity or finding. If none qualify, reply exactly: NOTHING FOUND.",
        think=False, temperature=0.2,
    )


def search_one(query: str, attempts: int = 3) -> str:
    """Grounded findings for one query. Order: a configured search API (real URLs, summarised strictly from what
    came back), then Gemini web search. Results from a provider that cannot search (it would answer from memory)
    are discarded; transient Gemini overloads are retried."""
    hits = api_search(query)
    if hits is None:
        hits = browseros.search(query)          # free: a real search in the user's own BrowserOS browser
    if hits is not None:
        if not hits:
            return "NOTHING FOUND"
        try:
            return _summarize_results(query, hits)
        except Exception as e:
            print(f"[research] summarising results note for '{query[:40]}': {str(e)[:120]}")
    prompt = (
        f"Search the web for: {query}\n\n"
        "Report ONLY concrete, current findings: names, exact URLs, dates, "
        "deadlines, eligibility, one-line substance of each item. "
        "3-5 bullet findings. No fluff, no speculation, no invented links. "
        "If nothing solid is found, reply exactly: NOTHING FOUND."
    )
    for i in range(attempts):
        try:
            res = llm.generate(prompt, web_search=True, think=False, temperature=0.3, provider="gemini")
            if getattr(res, "search_grounded", False):
                return res
        except Exception as e:
            print(f"[research] grounded search attempt {i + 1}/{attempts} for '{query[:40]}': {str(e)[:120]}")
        if i + 1 < attempts:
            time.sleep(4 * (i + 1))
    return SEARCH_UNAVAILABLE


def deep_research(goal: str, n_queries: int = 4) -> str:
    """Returns a structured evidence dossier separating papers and opportunities."""
    sections = []

    # 1. Verified Papers (arXiv fallback)
    print("[research] fetching recent verified papers from arXiv...")
    arxiv_papers = fetch_arxiv_papers()
    if arxiv_papers:
        paper_lines = []
        for p in arxiv_papers:
            paper_lines.append(
                f"- **{p['title']}** ({p['published']})\n"
                f"  Authors: {p['authors']}\n"
                f"  URL: {p['url']}\n"
                f"  Summary: {p['summary']}"
            )
        sections.append("### Verified Research Papers (arXiv)\n" + "\n".join(paper_lines))
    else:
        sections.append("### Verified Research Papers\n(arXiv query returned no items; omit paper section if no verified sources available)")

    # 2. Opportunities & News (Web searches)
    _t = time.time()
    queries = plan_queries(goal, n_queries)
    print(f"[time] planned queries in {time.time() - _t:.0f}s")
    web_findings = []
    unavailable = 0
    for q in queries:
        print(f"[research] searching: {q}")

    def _one(indexed):
        i, q = indexed
        time.sleep(i * SEARCH_STAGGER_SECONDS)    # stagger the start so the browser and the model are not hit at once
        started = time.time()
        found = search_one(q)
        print(f"[time] search {i + 1}/{len(queries)} took {time.time() - started:.0f}s")
        return found

    # Searches are independent, so run a few at a time (each uses its own BrowserOS tab and a model call):
    # sequentially they took 45-95 s each, about 7 minutes in total.
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=3) as pool:
        findings = list(pool.map(_one, enumerate(queries)))
    for q, finding in zip(queries, findings):
        if finding == SEARCH_UNAVAILABLE:
            unavailable += 1
        elif finding and "NOTHING FOUND" not in finding and "(search failed" not in finding:
            web_findings.append(f"#### Query: {q}\n{finding}")

    if web_findings:
        sections.append("### Verified Web Opportunities & Industry News\n" + "\n\n".join(web_findings))
    else:
        why = (f"Live web search was unavailable for {unavailable} of {len(queries)} queries (Gemini overloaded or no key)."
               if unavailable else "The searches ran but returned nothing concrete.")
        sections.append("### Verified Web Opportunities\n(No verified live web listings captured today; omit opportunities rather than inventing)\n"
                        f"[search status] {why}")

    dossier = "\n\n".join(sections).strip()
    if not dossier:
        raise RuntimeError("Deep research produced no usable findings")
    return dossier

