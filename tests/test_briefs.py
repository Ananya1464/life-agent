from datetime import date

from life_agent import briefs


def test_save_writes_a_dated_markdown_note(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFE_AGENT_BRIEFS_DIR", str(tmp_path))
    path = briefs.save("ai_edge", "1. Open role\n2. A paper", day=date(2026, 10, 5))
    assert path == tmp_path / "2026-10-05 ai_edge.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# AI Edge: opportunities and research: 2026-10-05")
    assert "1. Open role" in text
    assert not list(tmp_path.glob("*.tmp"))


def test_empty_text_and_unwritable_dir_never_raise(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFE_AGENT_BRIEFS_DIR", str(tmp_path))
    assert briefs.save("meal_plan", "   ") is None
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("LIFE_AGENT_BRIEFS_DIR", str(blocker / "sub"))       # a file where a folder is needed
    assert briefs.save("meal_plan", "plan") is None


def test_default_location_is_beside_the_dashboard(monkeypatch):
    monkeypatch.delenv("LIFE_AGENT_BRIEFS_DIR", raising=False)
    assert briefs.briefs_dir().name == "Briefings"
