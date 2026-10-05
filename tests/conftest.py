"""Shared pytest setup."""
import os

# life_agent.config reads NOTION_TOKEN at import time (fail-fast for real runs). Give tests a
# placeholder so modules that import config can be collected without a real secret.
os.environ.setdefault("NOTION_TOKEN", "test-notion-token")


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _briefs_to_tmp(tmp_path_factory, monkeypatch):
    """No test may write notes into the real Obsidian vault."""
    monkeypatch.setenv("LIFE_AGENT_BRIEFS_DIR", str(tmp_path_factory.mktemp("briefs")))
