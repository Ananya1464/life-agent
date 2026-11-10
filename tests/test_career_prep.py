"""career_prep: grounded plan saved as a note; empty research never reaches the LLM; no network in tests."""
from life_agent import briefs
from life_agent.agent import main
from life_agent.agent.tasks import career_prep


def test_task_is_registered_and_has_a_prompt():
    assert "career_prep" in main.TASKS
    from life_agent.agent import prompt_loader
    assert "{{RESEARCH_NOTES}}" in prompt_loader.load("career_prep")


def test_empty_dossier_skips_the_llm_and_still_saves_a_note(monkeypatch, tmp_path):
    monkeypatch.setenv("LIFE_AGENT_BRIEFS_DIR", str(tmp_path))
    monkeypatch.setattr(career_prep.research, "deep_research", lambda goal, n_queries=6: "")
    monkeypatch.setattr(career_prep.llm, "generate", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM called")))
    career_prep.run()
    notes = list(tmp_path.glob("* career_prep.md"))
    assert len(notes) == 1 and "No verified findings" in notes[0].read_text(encoding="utf-8")


def test_good_dossier_is_synthesized_checked_and_saved(monkeypatch, tmp_path):
    monkeypatch.setenv("LIFE_AGENT_BRIEFS_DIR", str(tmp_path))
    monkeypatch.setattr(career_prep.research, "deep_research", lambda goal, n_queries=6: "Source: https://example.org/paper - a real finding")
    monkeypatch.setattr(career_prep.llm, "generate", lambda *a, **k: "1. **Reading list** https://example.org/paper")
    monkeypatch.setattr(career_prep.quality, "find_dead_links", lambda text: [])
    monkeypatch.setattr(career_prep.quality, "critique_and_revise", lambda text, **k: text)
    monkeypatch.setattr(career_prep.grounding, "check_grounding", lambda text, dossier: [])
    career_prep.run()
    note = next(tmp_path.glob("* career_prep.md")).read_text(encoding="utf-8")
    assert "Reading list" in note and "example.org/paper" in note
