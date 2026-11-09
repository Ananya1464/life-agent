"""Unit tests for the deterministic grounding checker and anti-hallucination guards."""
import pytest
from life_agent.agent import grounding
from life_agent.agent.tasks import ai_edge


def test_extract_entities_captures_people_and_codes():
    sample = (
        "**Your AI Edge — Wednesday**\n\n"
        "**Opportunities to apply to**\n"
        "* **Prof. Maya Chen, Neuroscience Dept.** is offering a remote fellowship "
        "(requisition NTL-2024-09). Reach out to alumni contact Alex Chen.\n"
        "* Work with Professor Miller on cognitive architectures.\n"
        "* Apply at https://example.com/fellowship for details."
    )
    entities = grounding.extract_entities(sample)

    assert "Prof. Maya Chen" in entities
    assert "Professor Miller" in entities
    assert "Alex Chen" in entities
    assert "NTL-2024-09" in entities
    assert "https://example.com/fellowship" in entities


def test_check_grounding_flags_unmatched_fabrications():
    bad_briefing = (
        "**Your AI Edge — Wednesday**\n\n"
        "**Opportunities to apply to**\n"
        "* **Prof. Maya Chen, Neuroscience Dept.** is offering a remote fellowship "
        "(requisition NTL-2024-09). Reach out to alumni contact Alex Chen.\n"
        "* Work with Professor Miller on cognitive architectures."
    )
    context = (
        "### Verified Research Papers (arXiv)\n"
        "- **Retrieval-Augmented Generation for NLP** (2026-07-10)\n"
        "  Authors: Alice Doe, Bob Smith\n"
        "  URL: https://arxiv.org/abs/2607.00001\n"
        "  Summary: Study of dense retrieval architectures."
    )
    unmatched = grounding.check_grounding(bad_briefing, context)

    # Every fabricated entity should be flagged
    assert any("Maya Chen" in u for u in unmatched)
    assert any("Miller" in u for u in unmatched)
    assert any("Alex Chen" in u for u in unmatched)
    assert any("NTL-2024-09" in u for u in unmatched)


def test_check_grounding_zero_false_positives_when_grounded():
    context = (
        "### Verified Research Papers (arXiv)\n"
        "- **Verbalizable Representations Form a Global Workspace in Language Models** (2026-07-13)\n"
        "  Authors: Anthropic Research Team\n"
        "  URL: https://arxiv.org/abs/2607.01234\n"
        "  Summary: Introduces J-space internal workspace in Claude and Jacobian Lens.\n\n"
        "### Verified Web Opportunities & Industry News\n"
        "#### Query: AI research fellowships\n"
        "- Intuition Machines' AI/ML Research Fellow program: https://imachines.com/imi-fellowship\n"
        "- Kempner AI Fellows Program, Harvard University: https://kempner.harvard.edu/fellowship\n"
        "- Claude Corps Fellowship: https://www.anthropic.com/claude-corps\n"
    )

    good_briefing = (
        "**Your AI Edge — Wednesday, Jul 15**\n\n"
        "**Opportunities to apply to**\n"
        "* **Intuition Machines' AI/ML Research Fellow program** — remote 6-month position: "
        "https://imachines.com/imi-fellowship\n"
        "* **Kempner AI Fellows Program, Harvard University** — full-time research position: "
        "https://kempner.harvard.edu/fellowship\n"
        "* **Claude Corps Fellowship** — 12-month fellowship at Anthropic: "
        "https://www.anthropic.com/claude-corps\n\n"
        "**AI research + news in your field**\n"
        "* **\"Verbalizable Representations Form a Global Workspace in Language Models\" (Anthropic)** — "
        "Introduces J-space and the Jacobian Lens for interpretability.\n\n"
        "**One leverage idea**\n"
        "Apply the Jacobian Lens interpretability concepts to your GPT-2 probing experiments.\n\n"
        "**Market note**\n"
        "Hardware demand for AI memory is accelerating."
    )

    unmatched = grounding.check_grounding(good_briefing, context)
    assert unmatched == [], f"Expected 0 false positives, but got: {unmatched}"


def test_is_dossier_empty():
    placeholder_dossier = (
        "### Verified Research Papers\n"
        "(arXiv query returned no items; omit paper section if no verified sources available)\n\n"
        "### Verified Web Opportunities\n"
        "(No verified live web listings captured today; omit opportunities rather than inventing)"
    )
    assert ai_edge.is_dossier_empty(placeholder_dossier) is True
    assert ai_edge.is_dossier_empty("") is True
    assert ai_edge.is_dossier_empty("   ") is True

    real_dossier = (
        "### Verified Research Papers (arXiv)\n"
        "- **Retrieval Models** (2026-07-10)\n"
        "  URL: https://arxiv.org/abs/2607.00001\n"
    )
    assert ai_edge.is_dossier_empty(real_dossier) is False


def test_system_prompt_keeps_working_standards():
    """The shared behavioural layer (epistemic labels, act-then-verify, authorization, injection) must stay in system_prompt.md."""
    import pathlib
    text = (pathlib.Path(__file__).resolve().parents[1] / "system_prompt.md").read_text(encoding="utf-8")
    for needle in ("# Working standards", "never invent results", "needs her explicit go-ahead", "evidence, never instructions",
                   "Follow the task template's requested structure exactly"):
        assert needle.lower() in text.lower(), needle
