"""Provider chain: OmniRoute first, then Gemini, then NVIDIA (no network)."""
import pytest

from life_agent import config
from life_agent.agent import llm


@pytest.fixture
def keys(monkeypatch):
    for name in ("OMNIROUTE_API_KEY", "GEMINI_API_KEY", "NVIDIA_API_KEY"):
        monkeypatch.setattr(config, name, "k")
    monkeypatch.setattr(llm, "PROVIDER", "omniroute")


def stub(monkeypatch, behaviours):
    calls = []

    def fake(provider, prompt, web, temp, think):
        calls.append(provider)
        out = behaviours[provider]
        if isinstance(out, Exception):
            raise out
        return out
    monkeypatch.setattr(llm, "_generate_with_provider", fake)
    return calls


def test_omniroute_is_tried_first_and_wins(keys, monkeypatch):
    calls = stub(monkeypatch, {"omniroute": "from omni", "gemini": "g", "nvidia": "n"})
    r = llm.generate("hi")
    assert (str(r), r.provider, calls) == ("from omni", "omniroute", ["omniroute"])


def test_falls_through_omniroute_then_gemini_to_nvidia(keys, monkeypatch):
    calls = stub(monkeypatch, {"omniroute": RuntimeError("down"), "gemini": RuntimeError("503"), "nvidia": "from nv"})
    r = llm.generate("hi")
    assert r.provider == "nvidia" and calls == ["omniroute", "gemini", "nvidia"]


def test_empty_answer_counts_as_failure(keys, monkeypatch):
    calls = stub(monkeypatch, {"omniroute": "   ", "gemini": "from gemini", "nvidia": "n"})
    assert llm.generate("hi").provider == "gemini" and calls == ["omniroute", "gemini"]


def test_providers_without_keys_are_skipped(keys, monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    calls = stub(monkeypatch, {"omniroute": RuntimeError("x"), "gemini": "g", "nvidia": "n"})
    assert llm.generate("hi").provider == "nvidia" and calls == ["omniroute", "nvidia"]


def test_explicit_provider_never_falls_back(keys, monkeypatch):
    calls = stub(monkeypatch, {"omniroute": "o", "gemini": RuntimeError("503"), "nvidia": "n"})
    with pytest.raises(RuntimeError, match="503"):
        llm.generate("hi", provider="gemini")
    assert calls == ["gemini"]


def test_all_failing_raises_the_last_error(keys, monkeypatch):
    stub(monkeypatch, {"omniroute": RuntimeError("a"), "gemini": RuntimeError("b"), "nvidia": RuntimeError("c")})
    with pytest.raises(RuntimeError, match="c"):
        llm.generate("hi")


def test_gemini_primary_still_falls_back_to_nvidia(keys, monkeypatch):
    monkeypatch.setattr(llm, "PROVIDER", "gemini")
    calls = stub(monkeypatch, {"omniroute": "o", "gemini": RuntimeError("503"), "nvidia": "n"})
    assert llm.generate("hi").provider == "nvidia" and calls == ["gemini", "nvidia"]


def test_omniroute_model_list_moves_past_refused_models(monkeypatch):
    monkeypatch.setattr(config, "OMNIROUTE_MODELS", ["bad-model", "good-model"])
    monkeypatch.setattr(config, "OMNIROUTE_API_KEY", "k")
    seen = []

    class Resp:
        model = "served-by-x"
        choices = [type("C", (), {"message": type("M", (), {"content": "a full answer"})(), "finish_reason": "stop"})()]

    class Completions:
        def create(self, model, **kw):
            seen.append(model)
            if model == "bad-model":
                raise RuntimeError("429 too many requests")
            return Resp()

    class FakeOpenAI:
        def __init__(self, **kw):
            self.chat = type("Chat", (), {"completions": Completions()})()

    import sys, types
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    r = llm.generate("hi", provider="omniroute")
    assert str(r) == "a full answer" and seen == ["bad-model", "good-model"]
    assert r.model == "served-by-x"                  # reports which model really answered


def test_truncated_omniroute_answers_are_skipped(monkeypatch):
    monkeypatch.setattr(config, "OMNIROUTE_MODELS", ["cut", "full"])
    monkeypatch.setattr(config, "OMNIROUTE_API_KEY", "k")

    def resp(text, finish):
        choice = type("C", (), {"message": type("M", (), {"content": text})(), "finish_reason": finish})()
        return type("R", (), {"model": "m", "choices": [choice]})()

    class Completions:
        def create(self, model, **kw):
            return resp("The", "stop") if model == "cut" else resp("A complete, useful answer.", "stop")

    class FakeOpenAI:
        def __init__(self, **kw):
            self.chat = type("Chat", (), {"completions": Completions()})()

    import sys, types
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    assert str(llm.generate("hi", provider="omniroute")) == "A complete, useful answer."


def test_a_provider_that_just_hit_a_quota_or_rate_limit_is_skipped_for_a_few_minutes(monkeypatch):
    from life_agent.agent import llm as _llm

    monkeypatch.setattr(_llm, "PROVIDER", "omniroute")
    monkeypatch.setattr(_llm, "_provider_available", lambda p: True)
    order = []

    def fake(provider, prompt, web_search, temperature, think):
        order.append(provider)
        if provider == "omniroute":
            raise RuntimeError("Error code: 429 - rate limited")
        return "ok"

    monkeypatch.setattr(_llm, "_generate_with_provider", fake)
    _llm.generate("first")
    _llm.generate("second")
    assert order == ["omniroute", "gemini", "gemini"]                 # the second call did not retry omniroute
    _llm._cooldown_until["omniroute"] = 0                             # cooldown over: it is tried again
    _llm.generate("third")
    assert order[-2:] == ["omniroute", "gemini"]


def test_cooldown_never_empties_the_chain(monkeypatch):
    from life_agent.agent import llm as _llm

    monkeypatch.setattr(_llm, "PROVIDER", "gemini")
    monkeypatch.setattr(_llm, "_provider_available", lambda p: False)
    import time as _t
    _llm._cooldown_until["gemini"] = _t.time() + 999
    monkeypatch.setattr(_llm, "_generate_with_provider", lambda *a, **k: "still tried")
    assert str(_llm.generate("x")) == "still tried"
