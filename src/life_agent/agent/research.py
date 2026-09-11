"""Deep-research engine — gathers verified research papers and live web evidence:

1. PAPERS: Queries arXiv API (and Hugging Face Daily Papers) for recent, verified
   papers with real titles, authors, and URLs. Treated as a resilient fallback.
2. OPPORTUNITIES & NEWS: Searches live web for real fellowships, pre-doc roles,
   and market trends.
3. EVIDENCE DOSSIER: Synthesized into structured evidence without fabrication.
   If evidence is unavailable for an item, it is explicitly omitted.
"""
import time
import xml.etree.ElementTree as ET
import requests

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


def search_one(query: str) -> str:
    try:
        return llm.generate(
            f"Search the web for: {query}\n\n"
            "Report ONLY concrete, current findings: names, exact URLs, dates, "
            "deadlines, eligibility, one-line substance of each item. "
            "3-5 bullet findings. No fluff, no speculation, no invented links. "
            "If nothing solid is found, reply exactly: NOTHING FOUND.",
            web_search=True,
            think=False,
            temperature=0.3,
        )
    except Exception as e:
        print(f"[research] web search note for '{query[:40]}': {e}")
        return "NOTHING FOUND"


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
    queries = plan_queries(goal, n_queries)
    web_findings = []
    for q in queries:
        print(f"[research] searching: {q}")
        time.sleep(2)  # courteous pacing to protect rate limits
        finding = search_one(q)
        if finding and "NOTHING FOUND" not in finding and "(search failed" not in finding:
            web_findings.append(f"#### Query: {q}\n{finding}")

    if web_findings:
        sections.append("### Verified Web Opportunities & Industry News\n" + "\n\n".join(web_findings))
    else:
        sections.append("### Verified Web Opportunities\n(No verified live web listings captured today; omit opportunities rather than inventing)")

    dossier = "\n\n".join(sections).strip()
    if not dossier:
        raise RuntimeError("Deep research produced no usable findings")
    return dossier

