"""Scratch test for inbound reply stripping and parsing."""
from __future__ import annotations

import json
import pathlib
import sys
from email.message import EmailMessage

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from life_agent.notifications import inbound

inbound.config.GMAIL_ADDRESS = "ananya@example.com"
inbound.config.GMAIL_APP_PASSWORD = "app-password"


def main() -> None:
    sample = """Yep, done.

On Tue, Aug 11, 2026 at 7:00 AM Life Agent wrote:
> quoted line
> another quoted line
"""
    stripped = inbound.strip_quotes(sample)
    assert stripped == "Yep, done.", stripped

    calls = []

    def fake_generate(prompt: str, web_search: bool = False, temperature: float = 0.7, think: bool = True) -> str:
        calls.append(prompt)
        return json.dumps({
            "energy": 4,
            "sleep_hours": 7.5,
            "soreness": "some",
            "checkins": [],
            "captures": [],
            "tomorrow": [],
        })

    original_generate = inbound.llm.generate
    try:
        inbound.llm.generate = fake_generate
        parsed = inbound.parse_reply("LA-20260811-M", stripped)
        assert parsed["parse_ok"] is True
        assert parsed["token"] == "LA-20260811-M"
        assert parsed["energy"] == 4
        assert calls, "expected one LLM call"
    finally:
        inbound.llm.generate = original_generate

    failure_events = []

    def fake_fail_generate(prompt: str, web_search: bool = False, temperature: float = 0.7, think: bool = True) -> str:
        failure_events.append(prompt)
        return "not json"

    original_generate = inbound.llm.generate
    try:
        inbound.llm.generate = fake_fail_generate
        failed = inbound.parse_reply("LA-20260811-M", "messy body")
        assert failed["parse_ok"] is False
        assert failed["parse_error"] == "LLM parsing failed after one retry"
    finally:
        inbound.llm.generate = original_generate

    events = []

    def fake_append(kind: str, payload: dict) -> str:
        events.append((kind, payload))
        return f"{kind}-id"

    class FakeIMAP:
        def __init__(self, *args, **kwargs):
            self.flags = []

        def login(self, *args, **kwargs):
            return "OK", [b"logged in"]

        def select(self, *args, **kwargs):
            return "OK", [b"1"]

        def uid(self, command, *args):
            if command == "search":
                return "OK", [b"1"]
            if command == "fetch":
                message = EmailMessage()
                message["Subject"] = "[LA-20260811-M] morning"
                message["From"] = "Ananya <ananya@example.com>"
                message.set_content("Feeling good.\n\nOn Tue, Aug 11, 2026 at 7:00 AM Life Agent wrote:\n> quoted")
                return "OK", [(b"1 (RFC822 {0})", message.as_bytes())]
            if command == "store":
                self.flags.append(args)
                return "OK", [b"stored"]
            raise AssertionError(f"unexpected uid command {command}")

        def logout(self):
            return "OK", [b"bye"]

    original_imap = inbound.imaplib.IMAP4_SSL
    original_append = inbound.store.append
    original_generate = inbound.llm.generate
    try:
        inbound.imaplib.IMAP4_SSL = FakeIMAP
        inbound.store.append = fake_append
        inbound.llm.generate = fake_generate

        fetched = inbound.fetch_replies()
        assert len(fetched) == 1
        assert fetched[0]["token"] == "LA-20260811-M"
        assert fetched[0]["parse_ok"] is True
        assert any(kind == "reply_raw" for kind, _ in events)
        assert any(kind == "reply_parsed" for kind, _ in events)
    finally:
        inbound.imaplib.IMAP4_SSL = original_imap
        inbound.store.append = original_append
        inbound.llm.generate = original_generate

    parse_failure_events = []

    def fake_append_failure(kind: str, payload: dict) -> str:
        parse_failure_events.append((kind, payload))
        return f"{kind}-id"

    class FakeFailIMAP(FakeIMAP):
        pass

    original_imap = inbound.imaplib.IMAP4_SSL
    original_append = inbound.store.append
    original_generate = inbound.llm.generate
    try:
        inbound.imaplib.IMAP4_SSL = FakeFailIMAP
        inbound.store.append = fake_append_failure
        inbound.llm.generate = fake_fail_generate

        try:
            inbound.fetch_replies()
            raise AssertionError("expected fetch_replies to raise on parse failure")
        except RuntimeError as exc:
            assert "Reply parse failed" in str(exc)

        assert any(kind == "reply_parsed" and payload.get("parse_ok") is False for kind, payload in parse_failure_events)
    finally:
        inbound.imaplib.IMAP4_SSL = original_imap
        inbound.store.append = original_append
        inbound.llm.generate = original_generate

    print("inbound test passed")


if __name__ == "__main__":
    main()