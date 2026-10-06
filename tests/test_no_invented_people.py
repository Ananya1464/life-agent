"""The 'Dr. Sarah Chen' bug: the planner named an advisor that does not exist. Three layers must hold."""
import pathlib

from life_agent.agent import grounding, quality

ROOT = pathlib.Path(__file__).resolve().parents[1]
FACTS = "Tasks: finish lifebot. Project: life-agent. Goal: apply to NUS."
DRAFT = "**Tomorrow's mission**\nFinish lifebot.\nEmail Dr. Sarah Chen about a thesis chapter.\nApply to NUS."


def test_prompts_and_checklists_never_contain_fake_example_names():
    """Naming a fake person in a prompt, even as a 'don't do this' example, primes the model to produce it."""
    files = list((ROOT / "prompts").glob("*.md")) + list((ROOT / "src" / "life_agent" / "agent" / "prompts").glob("*.md"))
    files += [ROOT / "system_prompt.md", ROOT / "src" / "life_agent" / "agent" / "quality.py"]
    files += list((ROOT / "src" / "life_agent" / "agent" / "tasks").glob("*.py"))
    for f in files:
        text = f.read_text(encoding="utf-8")
        for name in ("Sarah Chen", "Alex Rivera"):
            assert name not in text, f"{name} found in {f.name}"


def test_scrub_removes_lines_naming_people_not_in_the_facts_and_keeps_the_rest():
    clean, removed = grounding.scrub_ungrounded(DRAFT, FACTS)
    assert "Sarah Chen" not in clean and any("Sarah Chen" in e for e in removed)
    assert "Finish lifebot." in clean and "Apply to NUS." in clean


def test_a_named_person_who_is_in_the_facts_is_kept():
    clean, removed = grounding.scrub_ungrounded("Email Prof. Rao today.", FACTS + " Contact: Prof. Rao (IIT Bombay).")
    assert clean == "Email Prof. Rao today." and removed == []


def test_reviewer_pass_cannot_let_a_fabricated_advisor_through(monkeypatch):
    monkeypatch.setattr(quality.llm, "generate", lambda *a, **k: "PASS")          # a lazy reviewer approves the draft
    out = quality.critique_and_revise(DRAFT, checklist="- ok", grounded_in=FACTS)
    assert "Sarah Chen" not in out and "Finish lifebot." in out


def test_without_grounded_in_the_text_is_untouched(monkeypatch):
    monkeypatch.setattr(quality.llm, "generate", lambda *a, **k: "PASS")
    assert quality.critique_and_revise(DRAFT, checklist="- ok") == DRAFT
