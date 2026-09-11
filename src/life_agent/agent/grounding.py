"""Deterministic entity grounding checker for AI Edge briefings.

Extracts named entities (people, academic titles, institutions, fellowships,
paper titles, requisition codes, arXiv IDs, URLs) and verifies whether each
entity appears in the retrieved evidence dossier.
"""
from __future__ import annotations

import re
from typing import Iterable

# Standard markdown headers and template boilerplate that are not entities
_COMMON_SECTIONS = {
    "opportunities",
    "opportunities to apply to",
    "research & releases",
    "research and releases",
    "research + news",
    "ai research + news in your field",
    "one high-leverage idea",
    "one leverage idea",
    "market note",
    "your ai edge",
    "daily totals",
    "estimated calories",
    "estimated protein",
    "tomorrow's plan",
    "tomorrow's 3 priorities",
    "outreach quota",
    "one reflection prompt",
}

# Personal profile terms established in system/task prompts
_PROFILE_TERMS = {
    "ananya",
    "mumbai",
    "india",
    "rag",
    "nlp",
    "llm",
    "llms",
    "faiss",
    "langchain",
    "gpt-2",
}

_DAY_NAMES = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


def extract_entities(text: str) -> list[str]:
    """Extract candidate named entities from a briefing string.

    Captures:
    - People with titles (Prof. X, Professor X, Dr. X)
    - Stated contact persons (alumni contact X, recruiter X)
    - Universities, institutes, departments, fellowships
    - Requisition / job codes (e.g. NTL-2024-09)
    - arXiv IDs (e.g. 2506.00054)
    - URLs (http:// or https://)
    - Bolded opportunity / paper titles
    """
    if not text:
        return []

    entities: list[str] = []

    # 1. People with honorifics/titles (Prof., Professor, Dr., etc.)
    for m in re.finditer(
        r"\b(?:Prof\.|Professor|Dr\.)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\b",
        text,
    ):
        entities.append(m.group(0).strip())

    # 2. Designated roles (alumni contact, recruiter, etc.)
    for m in re.finditer(
        r"\b(?:alumni contact|advisor|collaborator|recruiter)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\b",
        text,
        re.IGNORECASE,
    ):
        entities.append(m.group(1).strip())

    # 3. Institutional / fellowship bodies
    for m in re.finditer(
        r"\b[A-Z][a-zA-Z0-9]*(?:\s+[A-Z][a-zA-Z0-9]*)*\s+(?:University|Institute|Fellowship|Lab|Laboratory|Department|Dept)\b",
        text,
    ):
        entities.append(m.group(0).strip())

    for m in re.finditer(
        r"\b(?:University|Institute)\s+of\s+[A-Z][a-zA-Z0-9]*(?:\s+[A-Z][a-zA-Z0-9]*)*\b",
        text,
    ):
        entities.append(m.group(0).strip())

    # 4. Requisition / job codes (e.g. NTL-2024-09)
    for m in re.finditer(r"\b[A-Z]{2,}-\d{3,}-\d+\b", text):
        entities.append(m.group(0).strip())

    # 5. arXiv IDs (e.g. 2506.00054)
    for m in re.finditer(r"\b(?:arXiv:)?\d{4}\.\d{4,5}(?:v\d+)?\b", text):
        entities.append(m.group(0).strip())

    # 6. URLs
    for m in re.finditer(r"https?://[^\s)\]]+", text):
        entities.append(m.group(0).strip())

    # 7. Bolded item titles (papers, programs, roles)
    for m in re.finditer(r"\*\*([^*]+)\*\*", text):
        item = m.group(1).strip()
        item_clean = item.lower().strip(":").strip()
        if item_clean in _COMMON_SECTIONS or any(
            item_clean.startswith(cs) for cs in _COMMON_SECTIONS
        ):
            continue
        if any(day in item_clean for day in _DAY_NAMES):
            continue
        if len(item) < 3 or len(item) > 140:
            continue
        entities.append(item)

    # Deduplicate preserving original order
    seen: set[str] = set()
    deduped: list[str] = []
    for e in entities:
        norm = e.strip().lower()
        if norm and norm not in seen:
            seen.add(norm)
            deduped.append(e.strip())

    return deduped


def check_grounding(output: str, context: str) -> list[str]:
    """Return entities in output that do not appear anywhere in retrieved context.

    Uses deterministic, case-insensitive substring matching.
    Returns an empty list if all extracted entities are traceable to context.
    """
    if not output:
        return []
    if not context:
        # If context is empty, any extracted entities are ungrounded
        return extract_entities(output)

    extracted = extract_entities(output)
    context_lower = context.lower()
    unmatched: list[str] = []

    for entity in extracted:
        # 0. Check quoted title (e.g. **"Title" (Venue)**)
        inner_quote = re.search(r'["“]([^"”]+)["”]', entity)
        if inner_quote and inner_quote.group(1).strip().lower() in context_lower:
            continue

        clean = entity.strip("\"'()[]{}.,;: ")
        clean_lower = clean.lower()

        if not clean or clean_lower in _PROFILE_TERMS:
            continue

        # Check title without trailing parenthetical: "Title (Venue)" -> "Title"
        base_title = re.sub(r"\s*\([^)]*\)$", "", clean).strip("\"' ")
        if base_title and base_title.lower() in context_lower:
            continue

        # 1. URL check: check full URL or host+path
        if clean.startswith("http://") or clean.startswith("https://"):
            bare_url = re.sub(r"^https?://", "", clean).rstrip("/")
            if bare_url.lower() in context_lower or clean_lower in context_lower:
                continue
            unmatched.append(entity)
            continue

        # 2. Honorific / Title check (e.g. Prof. Maya Chen -> also check "Maya Chen")
        title_match = re.match(
            r"^(?:Prof\.|Professor|Dr\.)\s+(.+)$", clean, re.IGNORECASE
        )
        if title_match:
            name_part = title_match.group(1).strip().lower()
            if clean_lower in context_lower or name_part in context_lower:
                continue
            unmatched.append(entity)
            continue

        # 3. arXiv ID check
        arxiv_match = re.search(r"\d{4}\.\d{4,5}", clean)
        if arxiv_match and arxiv_match.group(0) in context:
            continue

        # 4. Exact substring check
        if clean_lower in context_lower:
            continue

        unmatched.append(entity)

    return unmatched
