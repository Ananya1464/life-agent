"""Email is off by default and never touches SMTP unless explicitly enabled."""
import pytest

from life_agent import config
from life_agent.notifications import emailer


@pytest.fixture
def smtp(monkeypatch):
    calls = []
    monkeypatch.setattr(emailer.smtplib, "SMTP_SSL", lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError("SMTP used")))
    monkeypatch.setattr(config, "GMAIL_ADDRESS", "a@example.com")
    monkeypatch.setattr(config, "GMAIL_APP_PASSWORD", "pw")
    return calls


def test_disabled_by_default_sends_nothing(smtp, monkeypatch):
    monkeypatch.setattr(config, "EMAIL_ENABLED", False)
    assert emailer.send_email("s", "b") == "" and emailer.send("s", "b") == ""
    assert smtp == []


def test_enabled_flag_parsing():
    import importlib, os
    for value, expected in (("on", True), ("TRUE", True), ("1", True), ("off", False), ("", False), ("no", False)):
        os.environ["LIFE_AGENT_EMAIL"] = value
        assert importlib.reload(config).EMAIL_ENABLED is expected
    os.environ.pop("LIFE_AGENT_EMAIL")
    assert importlib.reload(config).EMAIL_ENABLED is False
