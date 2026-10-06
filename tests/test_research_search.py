"""Web search must really search: Gemini first, retried; never answer 'search' from memory."""
from life_agent.agent import llm, research
from life_agent.agent.tasks import ai_edge


class Grounded(str):
    search_grounded = True


class Ungrounded(str):
    search_grounded = False


def test_web_search_goes_to_gemini_first_even_when_omniroute_is_primary(monkeypatch):
    order = []
    monkeypatch.setattr(llm, "PROVIDER", "omniroute")
    monkeypatch.setattr(llm, "_provider_available", lambda p: True)

    def fake(provider, prompt, web_search, temperature, think):
        order.append(provider)
        if provider == "gemini":
            raise RuntimeError("503")
        return "answer"

    monkeypatch.setattr(llm, "_generate_with_provider", fake)
    res = llm.generate("find roles", web_search=True)
    assert order[0] == "gemini" and res.provider != "gemini" and not res.search_grounded
    order.clear()
    llm.generate("no search needed", web_search=False)
    assert order[0] == "omniroute"                      # normal calls keep the configured order


def test_search_one_uses_only_grounded_gemini_and_retries_overloads(monkeypatch):
    calls = []

    def fake(prompt, **kw):
        calls.append(kw)
        if len(calls) < 3:
            raise RuntimeError("503 UNAVAILABLE")
        return Grounded("- Real item | https://example.org")

    monkeypatch.setattr(research.llm, "generate", fake)
    monkeypatch.setattr(research.time, "sleep", lambda s: None)
    assert "example.org" in research.search_one("q")
    assert all(c.get("provider") == "gemini" and c.get("web_search") for c in calls)


def test_ungrounded_answers_are_discarded_not_passed_off_as_search(monkeypatch):
    monkeypatch.setattr(research.llm, "generate", lambda *a, **k: Ungrounded("made-up opportunity https://fake.example"))
    monkeypatch.setattr(research.time, "sleep", lambda s: None)
    assert research.search_one("q") == research.SEARCH_UNAVAILABLE


def test_deep_research_reports_why_there_were_no_opportunities(monkeypatch):
    monkeypatch.setattr(research, "fetch_arxiv_papers", lambda *a, **k: [])
    monkeypatch.setattr(research, "plan_queries", lambda goal, n: ["a", "b"])
    monkeypatch.setattr(research, "search_one", lambda q, attempts=3: research.SEARCH_UNAVAILABLE)
    monkeypatch.setattr(research.time, "sleep", lambda s: None)
    dossier = research.deep_research("goal", 2)
    assert "unavailable for 2 of 2 queries" in dossier
    assert ai_edge.is_dossier_empty(dossier)            # still counts as empty: the LLM is never asked to invent


class _Resp:
    def __init__(self, data):
        self._d = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._d


def test_api_search_uses_tavily_when_keyed_and_maps_results(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    seen = {}

    def fake_post(url, **kw):
        seen["url"], seen["auth"] = url, kw["headers"]["Authorization"]
        return _Resp({"results": [{"title": "Fellowship", "url": "https://example.org/f", "content": "closes 31 Oct"},
                                  {"title": "junk", "url": "not-a-url", "content": ""}]})

    monkeypatch.setattr(research.requests, "post", fake_post)
    hits = research.api_search("q")
    assert hits == [{"title": "Fellowship", "url": "https://example.org/f", "snippet": "closes 31 Oct"}]
    assert seen["url"] == "https://api.tavily.com/search" and seen["auth"] == "Bearer k"


def test_api_search_uses_brave_and_reports_none_without_keys_or_on_failure(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    assert research.api_search("q") is None                              # no key: caller falls back to Gemini
    monkeypatch.setenv("BRAVE_API_KEY", "b")
    monkeypatch.setattr(research.requests, "get", lambda url, **kw: _Resp(
        {"web": {"results": [{"title": "RA role", "url": "https://lab.example.edu", "description": "remote RA"}]}}))
    assert research.api_search("q")[0]["url"] == "https://lab.example.edu"
    monkeypatch.setattr(research.requests, "get", lambda url, **kw: (_ for _ in ()).throw(RuntimeError("down")))
    assert research.api_search("q") is None


def test_search_one_prefers_real_api_results_and_never_invents(monkeypatch):
    prompts = []
    monkeypatch.setattr(research, "api_search", lambda q, limit=8: [{"title": "Real", "url": "https://example.org/r", "snippet": "open"}])
    monkeypatch.setattr(research.llm, "generate", lambda p, **k: prompts.append(p) or "- Real | https://example.org/r")
    assert "example.org/r" in research.search_one("q")
    assert "ONLY sources you may use" in prompts[0] and "https://example.org/r" in prompts[0]
    monkeypatch.setattr(research, "api_search", lambda q, limit=8: [])
    assert research.search_one("q") == "NOTHING FOUND"


def test_page_facts_quotes_deadline_and_eligibility_sentences_and_ignores_scripts(monkeypatch):
    html = ("<html><script>var deadline = 'x 12 y';</script><body><p>Welcome to our programme.</p>"
            "<p>Deadline: Sunday, October 18 at 11:59pm PT for the November cohort.</p>"
            "<p>Open to early-career professionals and postgraduate students.</p>"
            "<p>Applications are due September 6 at 11:59 pm.</p></body></html>")

    class R:
        status_code = 200
        text = html

    monkeypatch.setattr(research.requests, "get", lambda url, **kw: R())
    facts = research.page_facts("https://example.org")
    assert any("October 18" in f for f in facts) and any("September 6" in f for f in facts)
    assert not any("var deadline" in f for f in facts)


def test_page_facts_is_empty_when_the_page_cannot_be_read(monkeypatch):
    monkeypatch.setattr(research.requests, "get", lambda url, **kw: (_ for _ in ()).throw(RuntimeError("down")))
    assert research.page_facts("https://example.org") == []


def test_summarizer_receives_the_page_quotes(monkeypatch):
    seen = []
    monkeypatch.setattr(research, "page_facts", lambda url, **k: ["Applications are due September 6 at 11:59 pm."])
    monkeypatch.setattr(research.llm, "generate", lambda p, **k: seen.append(p) or "ok")
    research._summarize_results("q", [{"title": "CBAI", "url": "https://example.org", "snippet": "fellowship"}])
    assert "PAGE SAYS: Applications are due September 6" in seen[0] and "report both statements as written" in seen[0]


def test_deep_research_runs_searches_in_parallel_but_keeps_query_order(monkeypatch):
    import threading
    import time as _time

    active, peak = [0], [0]
    lock = threading.Lock()

    def slow_search(q, attempts=3):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        _time.sleep(0.15)
        with lock:
            active[0] -= 1
        return f"- finding for {q}"

    monkeypatch.setattr(research, "fetch_arxiv_papers", lambda *a, **k: [])
    monkeypatch.setattr(research, "plan_queries", lambda goal, n: ["q1", "q2", "q3", "q4", "q5", "q6"])
    monkeypatch.setattr(research, "search_one", slow_search)
    monkeypatch.setattr(research, "SEARCH_STAGGER_SECONDS", 0)
    dossier = research.deep_research("goal", 6)
    assert 2 <= peak[0] <= 3                                              # parallel, but never more than 3 at once
    order = [dossier.index(f"#### Query: q{i}") for i in range(1, 7)]
    assert order == sorted(order)                                         # findings stay in query order
