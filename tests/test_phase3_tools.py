import json

import pytest

from life_agent.tools import deterministic_tools


@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setattr(deterministic_tools, "VAULT_ROOT", tmp_path.resolve())
    return tmp_path.resolve()


def test_safe_path_validation(vault):
    target = deterministic_tools._validate_vault_path("02_EXECUTION/Daily/2026-09-21.md")
    assert target == vault / "02_EXECUTION" / "Daily" / "2026-09-21.md"

    with pytest.raises(ValueError, match="Access denied"):
        deterministic_tools._validate_vault_path("../secret.txt")
    with pytest.raises(ValueError, match="Absolute paths"):
        deterministic_tools._validate_vault_path(str(vault / "note.md"))


def test_get_recent_activity_reads_local_events(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    events = [
        {"id": "1", "ts": "2026-09-22T10:00:00Z", "kind": "focus_started", "date": "2026-09-22",
         "task": "Task A", "intent_id": "p:s1", "source": "pomodoro_app"},
        {"id": "2", "ts": "2026-09-22T10:25:00Z", "kind": "focus_completed", "date": "2026-09-22",
         "task": "Task A", "duration_seconds": 1500, "intent_id": "p:s1", "source": "pomodoro_app"},
    ]
    (tmp_path / "data" / "events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )

    monkeypatch.setattr("life_agent.events.queries.get_local_date_iso", lambda offset=0: "2026-09-22")
    sessions = deterministic_tools.get_recent_activity(days_back=0)

    assert [s["task"] for s in sessions] == ["Task A"]
    assert sessions[0]["status"] == "completed"
    assert sessions[0]["duration_seconds"] == 1500
