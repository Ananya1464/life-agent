"""Self-verification layer — replicates Claude's habit of checking its own
work before delivering: a critique→revise pass, plus real HTTP link checking
for the web-researched briefing (Claude verifies links resolve; so do we)."""
import re
from datetime import date

import requests

from life_agent.agent import grounding
from life_agent.agent import llm

_URL_RE = re.compile(r"https?://[^\s\)\]>\"']+")


def find_dead_links(text: str, timeout: int = 10) -> list[str]:
    """Actually request every URL in the text; return the ones that fail."""
    dead = []
    for url in dict.fromkeys(_URL_RE.findall(text)):  # dedupe, keep order
        u = url.rstrip(".,;")
        try:
            r = requests.head(u, timeout=timeout, allow_redirects=True,
                              headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code >= 400:
                r = requests.get(u, timeout=timeout, allow_redirects=True,
                                 headers={"User-Agent": "Mozilla/5.0"}, stream=True)
            if r.status_code >= 400:
                dead.append(u)
        except Exception:
            dead.append(u)
    return dead


_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"')\]]+")


def _extract_dead_urls(issues: list[str]) -> list[str]:
    """Unique URLs mentioned in the issue lines, in order, without trailing punctuation."""
    seen: list[str] = []
    for issue in issues:
        for url in _URL_IN_TEXT.findall(issue):
            url = url.rstrip(",.;:!?")
            if url not in seen:
                seen.append(url)
    return seen


def critique_and_revise(draft: str, checklist: str, web_search: bool = False,
                        extra_issues: list[str] | None = None, grounded_in: str | None = None) -> str:
    """One review pass: a fresh 'reviewer' call grades the draft against the
    checklist; if problems are found, one revision call fixes them. When `grounded_in` (the facts the model was
    given) is passed, any line still naming a person, code or link not found in it is removed from the result."""
    text = _critique_and_revise(draft, checklist, web_search, extra_issues)
    if grounded_in:
        text, ungrounded = grounding.scrub_ungrounded(text, grounded_in)
        for entity in ungrounded:
            print(f"[guard] removed ungrounded entity: {entity}")
    return text


def _critique_and_revise(draft: str, checklist: str, web_search: bool,
                         extra_issues: list[str] | None) -> str:
    issues = list(extra_issues or [])
    today_context = (
        f"Today's date is {date.today().isoformat()}. Do not assume papers, programs or events dated up to today are "
        "fictional or in the future, and treat all dates provided in the dossier as ground truth.\n\n"
    )
    critique = llm.generate(
        today_context +
        "You are a strict reviewer. Check this draft against the checklist. "
        "If EVERYTHING passes, reply with exactly PASS and nothing else. "
        "Otherwise list only the concrete problems, one per line.\n\n"
        f"CHECKLIST:\n{checklist}\n\nDRAFT:\n{draft}",
        temperature=0.2,
    )
    if critique.strip().upper() != "PASS":
        issues.append(critique.strip())
    if not issues:
        return draft
    print("[quality] revising — issues found:\n" + "\n".join(issues))
    dead_urls = _extract_dead_urls(issues)
    dead_context = (
        "\nDEAD LINKS TO REMOVE (remove ONLY the entry containing each URL; preserve all other entries):\n"
        + "\n".join(f"  - {url}" for url in dead_urls) + "\n"
    ) if dead_urls else ""
    return llm.generate(
        f"Today's date is {date.today().isoformat()}.\n"
        "You are Ananya's chief-of-staff. Revise the draft to fix ALL the issues listed.\n"
        "Strict rules: Never invent people, advisors, collaborators, deadlines, or courses. Keep only verified, grounded facts.\n"
        "When fixing a dead link, remove ONLY the specific bullet point or entry containing the flagged URL. "
        "Preserve every other entry in that section completely untouched. Do not remove or condense entire sections "
        "because one entry in them is bad.\n"
        "Output only the revised deliverable, same format.\n\n"
        "ISSUES:\n" + "\n".join(issues) + dead_context + f"\n\nDRAFT:\n{draft}",
        web_search=web_search,
        temperature=0.3,
    )
