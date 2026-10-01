import json
import sys
from pathlib import Path

# Make life_agent importable when run as a script (pytest resolves it via the installed package)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from life_agent.obsidian.generator import generate_daily_note


def _write_events(base: Path, events: list[dict]) -> None:
    (base / "data").mkdir()
    (base / "data" / "events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )


def test_generate_daily_note(tmp_path, monkeypatch):
    # Events are read from ./data/events.jsonl, so use an isolated working directory
    monkeypatch.chdir(tmp_path)
    date_iso = "2026-09-21"
    _write_events(tmp_path, [
        {"id": "1", "ts": "2026-09-21T10:00:00Z", "kind": "focus_started", "date": date_iso,
         "task": "Test Pomodoro Session", "intent_id": "p:s1", "source": "pomodoro_app"},
        {"id": "2", "ts": "2026-09-21T10:25:00Z", "kind": "focus_completed", "date": date_iso,
         "task": "Test Pomodoro Session", "duration_seconds": 1500, "intent_id": "p:s1",
         "source": "pomodoro_app"},
    ])

    markdown = generate_daily_note(date_iso)

    assert "Daily Sessions" in markdown
    assert "Test Pomodoro Session" in markdown
    assert "Completed" in markdown
    assert "25 min" in markdown


def test_generate_daily_note_no_sessions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_events(tmp_path, [])

    assert "No focus sessions recorded." in generate_daily_note("2026-09-21")
