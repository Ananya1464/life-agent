"""Scratch check for outbound tokening, footer appending, and event logging."""
from __future__ import annotations

import json
import pathlib
import sys
from contextlib import contextmanager

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dates
import outbound


EVENTS_FILE = ROOT / "data" / "events.jsonl"


@contextmanager
def preserve_file(path: pathlib.Path):
    original_exists = path.exists()
    original_text = path.read_text(encoding="utf-8") if original_exists else ""
    try:
        yield
    finally:
        if original_exists:
            path.write_text(original_text, encoding="utf-8")
        elif path.exists():
            path.unlink()


def main() -> None:
    captured = {}
    expected_token = f"LA-{dates.today().strftime('%Y%m%d')}-M"

    def fake_send_email(subject: str, body_markdown: str, debug: bool = False) -> str:
        captured["subject"] = subject
        captured["body"] = body_markdown
        return "<test-message-id@example.com>"

    original_send_email = outbound.emailer.send_email
    try:
        with preserve_file(EVENTS_FILE):
            outbound.emailer.send_email = fake_send_email
            token = outbound.send_prompt_email("morning", "test subject", "test body")

            assert token == expected_token, token
            assert captured["subject"] == f"[{expected_token}] test subject"
            assert captured["body"].endswith(
                "---\nJust reply to this email in your own words. No format needed."
            )

            lines = EVENTS_FILE.read_text(encoding="utf-8").splitlines()
            assert lines, "expected an event line in data/events.jsonl"
            event = json.loads(lines[-1])
            assert event["kind"] == "email_sent"
            assert event["slot"] == "morning"
            assert event["token"] == expected_token
            assert event["subject"] == f"[{expected_token}] test subject"
            assert event["message_id"] == "<test-message-id@example.com>"
    finally:
        outbound.emailer.send_email = original_send_email

    print("outbound test passed")


if __name__ == "__main__":
    main()