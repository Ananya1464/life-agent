import pytest
from pathlib import Path
from life_agent.tools import deterministic_tools
from unittest.mock import patch

@pytest.fixture
def mock_vault(tmp_path):
    # Set VAULT_ROOT to tmp_path for the duration of the test
    original_root = deterministic_tools.VAULT_ROOT
    deterministic_tools.VAULT_ROOT = tmp_path

    # Create files
    (tmp_path / "note1.md").write_text("content1", encoding="utf-8")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir/note2.md").write_text("content2", encoding="utf-8")

    yield tmp_path
    deterministic_tools.VAULT_ROOT = original_root

def test_get_recent_activity():
    with patch("life_agent.tools.activity.get_activity") as mocked:
        deterministic_tools.get_recent_activity(days_back=0)
        mocked.assert_called_with(date_spec=0)

        deterministic_tools.get_recent_activity(days_back=1)
        mocked.assert_called_with(date_spec=-1)

        deterministic_tools.get_recent_activity(days_back=5)
        mocked.assert_called_with(date_spec=-5)

def test_read_vault_note_cases(mock_vault):
    # Valid note
    assert deterministic_tools.read_vault_note("note1.md") == "content1"

    # Missing file
    with pytest.raises(FileNotFoundError):
        deterministic_tools.read_vault_note("missing.md")

    # Directory passed
    (mock_vault / "subdir").mkdir(exist_ok=True)
    with pytest.raises(ValueError, match="Path is not a file"):
        deterministic_tools.read_vault_note("subdir")

def test_security_traversal(mock_vault):
    # ../ traversal
    with pytest.raises(ValueError, match="Access denied"):
        deterministic_tools.read_vault_note("../note1.md")

    # Outside-vault path
    outside = mock_vault.parent / "outside.md"
    outside.write_text("hacking", encoding="utf-8")
    # This path will resolve outside the vault
    with pytest.raises(ValueError, match="Access denied"):
        # We need a relative path that resolves to the outside file
        deterministic_tools.read_vault_note("../" + outside.name)

    # Absolute path rejected
    with pytest.raises(ValueError, match="Absolute paths"):
        deterministic_tools.read_vault_note(str(mock_vault / "note1.md"))

def test_list_vault_notes(mock_vault):
    notes = deterministic_tools.list_vault_notes()
    assert len(notes) == 2
    assert "note1.md" in notes
    assert str(Path("subdir/note2.md")) in notes
    # Sorted order check
    assert notes == sorted(notes)

    # Nested directory
    sub_notes = deterministic_tools.list_vault_notes("subdir")
    assert len(sub_notes) == 1
    assert sub_notes[0] == str(Path("subdir/note2.md"))

    # Missing directory
    with pytest.raises(ValueError, match="Not a directory"):
        deterministic_tools.list_vault_notes("missing_dir")

def test_read_utf8(mock_vault):
    path = mock_vault / "utf8.md"
    content = "café ☕"
    path.write_text(content, encoding="utf-8")
    assert deterministic_tools.read_vault_note("utf8.md") == content
