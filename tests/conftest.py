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


@pytest.fixture(autouse=True)
def _fresh_provider_cooldowns():
    from life_agent.agent import llm

    llm._cooldown_until.clear()
    llm._model_cooldown_until.clear()
    yield
    llm._cooldown_until.clear()
    llm._model_cooldown_until.clear()


@pytest.fixture(autouse=True)
def _no_real_browser(monkeypatch):
    """Tests never start or drive the real BrowserOS browser."""
    from life_agent import browseros

    monkeypatch.setattr(browseros, "ensure_running", lambda *a, **k: False)
