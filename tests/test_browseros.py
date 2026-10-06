"""BrowserOS search client: parsing and protocol are tested without any real browser or network."""
from life_agent import browseros
from life_agent.agent import research

PAGE = """[DuckDuckGo](https://duckduckgo.com/)

- [**All**](https://duckduckgo.com/?q=x)

1. Recent graduates can apply for the Memories.ai fellowship.

[opportunitiesforyouth.org](https://opportunitiesforyouth.org/a)

Show
1. research.nvidia.com

[https://research.nvidia.com](https://research.nvidia.com/fellowships/2026)

## [2026 Graduate Fellows | NVIDIA Research](https://research.nvidia.com/fellowships/2026)

**2026** NVIDIA **Graduate** **Fellowship** recipients. Applications close Oct 15.
1. aifellowshiphub.com

## [Autumn 2026 Fellowship - Remote](https://aifellowshiphub.com/opportunities/autumn-2026)

Sep 4, 2026A remote fellowship for **recent** graduates.
## [Duplicate](https://aifellowshiphub.com/opportunities/autumn-2026)

dup
"""


def test_parse_results_extracts_titles_urls_snippets_and_skips_chrome_and_duplicates():
    hits = browseros.parse_results(PAGE)
    assert [h["url"] for h in hits] == ["https://research.nvidia.com/fellowships/2026", "https://aifellowshiphub.com/opportunities/autumn-2026"]
    assert hits[0]["title"] == "2026 Graduate Fellows | NVIDIA Research"
    assert "Applications close Oct 15" in hits[0]["snippet"] and "**" not in hits[0]["snippet"]
    assert len(browseros.parse_results(PAGE, limit=1)) == 1


class FakeResp:
    def __init__(self, payload=None, headers=None):
        self.text = "data: \nid: 0\n\ndata: " + __import__("json").dumps(payload or {"result": {}}) + "\n"
        self.headers = headers or {}

    def raise_for_status(self):
        pass


def test_client_speaks_mcp_and_scopes_every_call_to_its_own_session(monkeypatch):
    sent = []

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.append((json, dict(headers)))
        if json["method"] == "initialize":
            return FakeResp({"result": {"protocolVersion": "2025-03-26"}}, {"Mcp-Session-Id": "abc"})
        if json["method"] == "tools/call" and json["params"]["name"] == "tabs":
            return FakeResp({"result": {"content": [{"type": "text", "text": "opened page 7"}]}})
        if json["method"] == "tools/call" and json["params"]["name"] == "read":
            return FakeResp({"result": {"content": [{"type": "text", "text": PAGE}]}})
        return FakeResp()

    monkeypatch.setattr(browseros.requests, "post", fake_post)
    with browseros.BrowserOS("http://x/mcp") as b:
        page = b.open_page("https://duckduckgo.com/?q=a")
        assert page == 7 and "NVIDIA" in b.read_page(page)
        b.close_page(page)
    methods = [m["method"] for m, _ in sent]
    assert methods[:2] == ["initialize", "notifications/initialized"]
    assert all(h.get("Mcp-Session-Id") == "abc" for m, h in sent[1:])
    calls = [m["params"] for m, _ in sent if m["method"] == "tools/call"]
    assert all("session" not in c["arguments"] for c in calls)      # BrowserOS rejects an unknown per-call field
    assert [c["name"] for c in calls][-1] == "tabs" and calls[-1]["arguments"]["action"] == "close"      # tab cleaned up


def test_search_returns_none_when_browseros_is_not_available(monkeypatch):
    monkeypatch.setattr(browseros, "ensure_running", lambda *a, **k: False)
    assert browseros.search("anything") is None


def test_search_closes_its_tab_even_when_reading_fails(monkeypatch):
    closed = []

    class Stub:
        def __enter__(self):
            return self

        def __exit__(self, *e):
            return None

        def open_page(self, url):
            return 3

        def read_page(self, page):
            raise RuntimeError("boom")

        def close_page(self, page):
            closed.append(page)

    monkeypatch.setattr(browseros, "ensure_running", lambda *a, **k: True)
    monkeypatch.setattr(browseros, "BrowserOS", Stub)
    monkeypatch.setattr(browseros.time, "sleep", lambda s: None)
    assert browseros.search("q") is None and closed == [3]


def test_research_uses_browseros_results_when_no_api_key(monkeypatch):
    prompts = []
    monkeypatch.setattr(research, "api_search", lambda q, limit=8: None)
    monkeypatch.setattr(research.browseros, "search", lambda q, limit=8: [{"title": "Real", "url": "https://example.org/r", "snippet": "open until Oct 31"}])
    monkeypatch.setattr(research.llm, "generate", lambda p, **k: prompts.append(p) or "- Real | https://example.org/r | Oct 31")
    assert "example.org/r" in research.search_one("q")
    assert "ONLY sources you may use" in prompts[0] and "open until Oct 31" in prompts[0]
