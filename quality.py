"""Self-verification layer — replicates Claude's habit of checking its own
work before delivering: a critique→revise pass, plus real HTTP link checking
for the web-researched briefing (Claude verifies links resolve; so do we)."""
import re

import requests

import llm

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


def critique_and_revise(draft: str, checklist: str, web_search: bool = False,
                        extra_issues: list[str] | None = None) -> str:
    """One review pass: a fresh 'reviewer' call grades the draft against the
    checklist; if problems are found, one revision call fixes them."""
    issues = list(extra_issues or [])
    critique = llm.generate(
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
    return llm.generate(
        "Revise the draft to fix ALL the issues listed. Keep everything that "
        "was already good. Output only the revised draft, same format.\n\n"
        "ISSUES:\n" + "\n".join(issues) + f"\n\nDRAFT:\n{draft}",
        web_search=web_search,
        temperature=0.4,
    )
