"""Shared pytest setup."""
import os

# life_agent.config reads NOTION_TOKEN at import time (fail-fast for real runs). Give tests a
# placeholder so modules that import config can be collected without a real secret.
os.environ.setdefault("NOTION_TOKEN", "test-notion-token")
