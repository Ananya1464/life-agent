"""Scratch test for reply-to-Notion mirroring and idempotence."""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from life_agent import config
from life_agent.integrations import notion_api


def main() -> None:
    config.REPLIES_DB_ID = "replies-db"

    events = []
    requests = []

    def fake_load_all():
        return events

    def fake_append(kind: str, payload: dict) -> str:
        events.append({"kind": kind, **payload})
        return f"{kind}-id"

    def fake_req(method: str, path: str, **kwargs):
        requests.append((method, path, kwargs))
        return {"id": "page-123"}

    original_load_all = notion_api.store.load_all
    original_append = notion_api.store.append
    original_req = notion_api._req
    try:
        notion_api.store.load_all = fake_load_all
        notion_api.store.append = fake_append
        notion_api._req = fake_req

        event = {
            "id": "reply-1",
            "ts": "2026-08-11T01:23:45Z",
            "slot": "morning",
            "energy": 4,
            "sleep_hours": 7.5,
            "soreness": "some",
            "checkins": [{"task": "Workout", "status": "done", "friction": None}],
            "captures": [{"bucket": "build", "text": "Ship inbound"}],
            "raw_text": "Feeling good",
        }

        page_id = notion_api.sync_event(event)
        assert page_id == "page-123"
        assert requests and requests[0][0] == "POST"
        assert any(ev.get("kind") == "notion_synced" and ev.get("event_id") == "reply-1" for ev in events)

        requests.clear()
        page_id_again = notion_api.sync_event(event)
        assert page_id_again == "page-123"
        assert not requests, "idempotent sync should skip duplicate Notion writes"
    finally:
        notion_api.store.load_all = original_load_all
        notion_api.store.append = original_append
        notion_api._req = original_req

    print("notion sync test passed")


if __name__ == "__main__":
    main()