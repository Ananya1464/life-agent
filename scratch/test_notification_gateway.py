"""Scratch test for the shared notification gateway routing and fallback behavior."""
from __future__ import annotations

import pathlib
import sys
from contextlib import contextmanager

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import event_model
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
    calls: list[tuple[str, str, str | None]] = []
    events: list[dict] = []

    def fake_ntfy(title: str, body: str, *, tags: str | None = None) -> None:
        calls.append(("ntfy", title, tags))
        if len(calls) == 1:
            return
        raise RuntimeError("simulated push failure")

    def fake_email(subject: str, body: str) -> bool:
        calls.append(("email", subject, None))
        return True

    def fake_append(kind: str, payload: dict) -> str:
        event = {"kind": kind, **payload, "id": f"{kind}-{len(events)}"}
        events.append(event)
        return event["id"]

    original_ntfy = outbound._send_ntfy
    original_email = outbound._send_email
    original_load_all = event_model.store.load_all
    original_append = event_model.store.append
    try:
        outbound._send_ntfy = fake_ntfy
        outbound._send_email = fake_email
        event_model.store.load_all = lambda: events
        event_model.store.append = fake_append

        with preserve_file(EVENTS_FILE):
            token = outbound.send_notification("task_start", task_name="meal_plan")
            assert token.endswith("-T"), token
            assert calls[0][0] == "ntfy"
            assert any(event.get("kind") == "notification_sent" for event in events)

            calls.clear()
            outbound._send_ntfy = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline"))
            token = outbound.send_notification("task_start", task_name="ai_edge")
            assert token.endswith("-T"), token
            assert calls and calls[0][0] == "email", calls
            assert any(event.get("kind") == "notification_sent" and event.get("channel") == "email" for event in events)

        print("notification gateway test passed")
    finally:
        outbound._send_ntfy = original_ntfy
        outbound._send_email = original_email
        event_model.store.load_all = original_load_all
        event_model.store.append = original_append


if __name__ == "__main__":
    main()