"""Lifebot's chat must not show 'could not reach my brain' for a short outage or a rate-limited model."""
import types

from life_agent import config
from life_agent.agent import llm
from life_agent.lifebot import chat


def test_omniroute_default_models_end_with_its_own_auto_routing_models():
    assert config.OMNIROUTE_MODELS[:2] == ["antigravity/claude-sonnet-4-6", "antigravity/claude-opus-4-6-thinking"]
    assert {"auto/best-chat", "auto/best-fast", "ai"} <= set(config.OMNIROUTE_MODELS)


def _fake_openai(monkeypatch, behaviour, calls):
    class Completions:
        def create(self, model, **kw):
            calls.append(model)
            return behaviour(model)

    class Client:
        def __init__(self, **kw):
            self.chat = types.SimpleNamespace(completions=Completions())

    import sys
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=Client))


def _answer(model):
    msg = types.SimpleNamespace(content="a perfectly fine answer")
    return types.SimpleNamespace(model=model, choices=[types.SimpleNamespace(message=msg, finish_reason="stop")])


def test_rate_limited_models_fall_through_to_auto_routing_and_are_then_skipped(monkeypatch):
    calls = []

    def behaviour(model):
        if model.startswith("antigravity/"):
            raise RuntimeError("Error code: 429 - All credentials for model are rate limited")
        return _answer(model)

    _fake_openai(monkeypatch, behaviour, calls)
    monkeypatch.setattr(config, "OMNIROUTE_MODELS", ["antigravity/claude-sonnet-4-6", "antigravity/claude-opus-4-6-thinking", "auto/best-chat"])
    assert llm._generate_omniroute("hi", False, 0.3, False) == "a perfectly fine answer"
    assert calls == ["antigravity/claude-sonnet-4-6", "antigravity/claude-opus-4-6-thinking", "auto/best-chat"]
    calls.clear()
    llm._generate_omniroute("hi again", False, 0.3, False)
    assert calls == ["auto/best-chat"]                              # the rate-limited models are not retried for a few minutes


def test_when_every_model_is_cooling_down_they_are_all_tried_anyway(monkeypatch):
    calls = []
    _fake_openai(monkeypatch, _answer, calls)
    monkeypatch.setattr(config, "OMNIROUTE_MODELS", ["a", "b"])
    import time
    llm._model_cooldown_until.update({"a": time.time() + 999, "b": time.time() + 999})
    assert llm._generate_omniroute("hi", False, 0.3, False)
    assert calls == ["a"]


def test_chat_retries_the_whole_provider_chain_before_giving_up(monkeypatch):
    attempts = []

    def flaky(prompt, **kw):
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("503 overloaded")
        return '{"reply": "Focus on the report first."}'

    monkeypatch.setattr(llm, "generate", flaky)
    monkeypatch.setattr(chat.time, "sleep", lambda s: None)
    out = chat.respond("What should I focus on today?", state={})
    assert out["reply"] == "Focus on the report first." and len(attempts) == 3


def test_chat_still_gives_a_friendly_message_when_everything_stays_down(monkeypatch):
    monkeypatch.setattr(llm, "generate", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("all down")))
    monkeypatch.setattr(chat.time, "sleep", lambda s: None)
    out = chat.respond("hello", state={})
    assert "could not reach my brain" in out["reply"] and out["actions"] == []
