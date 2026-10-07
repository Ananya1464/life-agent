"""replace_section must remove the WHOLE previous section, even when the briefing itself contains headings and dividers
(otherwise every re-run stacked another copy of the briefing on the page)."""
from life_agent.integrations import notion_api


def block(kind, text="", bid=None):
    b = {"type": kind, "id": bid or f"{kind}-{text[:6]}"}
    b[kind] = {"rich_text": [{"plain_text": text}]} if text else {"rich_text": []}
    return b


def page_with_old_briefing():
    return [
        block("heading_2", "🌅 Your AI Edge", "h-edge"),
        block("paragraph", "# Your AI Edge", "p1"),
        block("divider", "", "d-inner1"),
        block("heading_2", "1. Opportunities to apply to", "h-opps"),
        block("paragraph", "Old item", "p2"),
        block("divider", "", "d-inner2"),
        block("heading_2", "4. Market note", "h-mkt"),
        block("paragraph", "Old note", "p3"),
        block("divider", "", "d-sep"),
        block("heading_2", "🌙 Evening Check-in", "h-eve"),
        block("paragraph", "keep me", "p4"),
    ]


def test_template_section_covers_inner_headings_and_dividers_but_not_the_next_template_section():
    blocks = page_with_old_briefing()
    start, body = notion_api._section_range(blocks, "Your AI Edge")
    assert start == 0
    assert [b["id"] for b in body] == ["p1", "d-inner1", "h-opps", "p2", "d-inner2", "h-mkt", "p3"]   # everything of the old briefing
    assert "d-sep" not in [b["id"] for b in body]                                                      # the separator before the next section stays


def test_plain_heading_sections_still_end_at_the_next_heading_or_divider():
    blocks = [block("heading_2", "Current snapshot", "h1"), block("paragraph", "a", "p1"), block("divider", "", "d1"),
              block("heading_2", "Other", "h2")]
    assert [b["id"] for b in notion_api._section_range(blocks, "Current snapshot")[1]] == ["p1"]


def test_replace_section_deletes_every_old_block_and_inserts_after_the_heading(monkeypatch):
    blocks = page_with_old_briefing()
    calls = []
    monkeypatch.setattr(notion_api, "_children", lambda page_id: blocks)
    monkeypatch.setattr(notion_api, "_req", lambda method, path, **kw: calls.append((method, path, kw)) or {})
    monkeypatch.setattr(notion_api, "md_to_blocks", lambda md: [{"new": md}])
    notion_api.replace_section("page", "Your AI Edge", "new briefing")
    deleted = [p.split("/")[-1] for m, p, kw in calls if m == "DELETE"]
    assert deleted == ["p1", "d-inner1", "h-opps", "p2", "d-inner2", "h-mkt", "p3"]
    patch = [kw for m, p, kw in calls if m == "PATCH"][0]
    assert patch["json"]["after"] == "h-edge"


def test_append_to_database_falls_back_to_a_data_source_parent_when_the_id_is_a_data_source(monkeypatch):
    sent = []

    def fake_req(method, path, **kw):
        sent.append(kw["json"]["parent"])
        if "database_id" in kw["json"]["parent"]:
            raise RuntimeError('Notion POST /pages failed 404: {"code":"object_not_found","message":"Could not find database with ID"}')
        return {"id": "new-page"}

    monkeypatch.setattr(notion_api, "_req", fake_req)
    assert notion_api.append_to_database("data-source-id", {"Name": {}}) == "new-page"
    assert sent == [{"database_id": "data-source-id"}, {"type": "data_source_id", "data_source_id": "data-source-id"}]


def test_append_to_database_uses_the_database_parent_when_it_works_and_reraises_other_errors(monkeypatch):
    calls = []
    monkeypatch.setattr(notion_api, "_req", lambda m, p, **kw: calls.append(kw["json"]["parent"]) or {"id": "p"})
    assert notion_api.append_to_database("real-db-id", {}) == "p" and calls == [{"database_id": "real-db-id"}]
    monkeypatch.setattr(notion_api, "_req", lambda m, p, **kw: (_ for _ in ()).throw(RuntimeError("Notion POST /pages failed 500: boom")))
    try:
        notion_api.append_to_database("x", {})
        raise AssertionError("should have raised")
    except RuntimeError as err:
        assert "500" in str(err)
