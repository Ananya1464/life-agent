"""The agent's brain — pluggable, two backends, hardened.

1. "claude"  — real Claude via the Anthropic API. Defaults to claude-fable-5
   (Anthropic's most capable model) with extended thinking + web search.
   Activated automatically when ANTHROPIC_API_KEY is set.
2. "gemini"  — free-tier fallback (Google AI Studio key). Gemini thinking
   mode + Google Search grounding.

Hardening:
  - Retries with exponential backoff on rate limits / transient errors
  - Model fallback chain within Claude (fable-5 → opus-4-8 → sonnet-5)
  - Cross-provider fallback: if Claude fails entirely and a Gemini key
    exists, the task still completes on Gemini instead of crashing

Force a backend with LLM_PROVIDER=claude|gemini. One public function:
    generate(prompt, web_search=False, temperature=0.7, think=True) -> str
"""
import os
import pathlib
import time

import config


def _system_prompt() -> str:
    """Claude-style system prompt (system_prompt.md), '' if missing."""
    p = pathlib.Path(__file__).parent / "system_prompt.md"
    try:
        return p.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


SYSTEM_PROMPT = _system_prompt()

PROVIDER = getattr(config, "LLM_PROVIDER", None) or os.getenv(
    "LLM_PROVIDER",
    "claude" if os.getenv("ANTHROPIC_API_KEY") else "gemini",
)
PROVIDER = PROVIDER.lower()

THINKING_BUDGET = int(os.getenv("THINKING_BUDGET", "8000"))  # tokens of reasoning
MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))

# Claude model fallback chain — first available wins.
CLAUDE_MODELS = [
    os.getenv("CLAUDE_MODEL", "claude-fable-5"),
    "claude-opus-4-8",
    "claude-sonnet-5",
]


def _retry(fn, *args, **kwargs):
    """Run fn with exponential backoff on transient errors (429/5xx/timeouts)."""
    delay = 5
    for attempt in range(MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            msg = str(e)
            transient = any(t in msg for t in (
                "429", "529", "500", "502", "503", "504",
                "overloaded", "rate", "RESOURCE_EXHAUSTED", "timeout", "timed out",
            ))
            if not transient or attempt == MAX_RETRIES - 1:
                raise
            print(f"[llm] transient error, retrying in {delay}s: {msg[:120]}")
            time.sleep(delay)
            delay *= 2


# --------------------------------------------------------------------- Claude
def _call_claude(model, prompt, web_search, temperature, think):
    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    kwargs = {
        "model": model,
        "max_tokens": 8192 + (THINKING_BUDGET if think else 0),
        "messages": [{"role": "user", "content": prompt}],
    }
    if SYSTEM_PROMPT:
        kwargs["system"] = SYSTEM_PROMPT
    if think:
        # Extended thinking — the same deliberate reasoning Claude uses in-app.
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": THINKING_BUDGET}
    else:
        kwargs["temperature"] = temperature
    if web_search:
        kwargs["tools"] = [{"type": "web_search_20250305",
                            "name": "web_search", "max_uses": 8}]
    resp = client.messages.create(**kwargs)
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def _generate_claude(prompt, web_search, temperature, think):
    last_err = None
    for model in CLAUDE_MODELS:
        try:
            return _retry(_call_claude, model, prompt, web_search, temperature, think)
        except Exception as e:
            msg = str(e)
            last_err = e
            # Model not available on this account/tier → try the next one.
            if "404" in msg or "not_found" in msg or "model" in msg.lower():
                print(f"[llm] {model} unavailable, trying next model")
                continue
            raise
    raise last_err


# --------------------------------------------------------------------- Gemini
def _generate_gemini(prompt, web_search, temperature, think):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    cfg_kwargs = {"temperature": temperature}
    if SYSTEM_PROMPT:
        cfg_kwargs["system_instruction"] = SYSTEM_PROMPT
    if web_search:
        cfg_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    if think:
        try:  # give a generous fixed reasoning budget
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_budget=THINKING_BUDGET
            )
        except Exception:
            pass  # non-thinking model / older SDK — degrade gracefully

    def _call():
        resp = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(**cfg_kwargs),
        )
        return resp.text or ""

    return _retry(_call)


# ----------------------------------------------------------------------- API
def generate(prompt: str, web_search: bool = False, temperature: float = 0.7,
             think: bool = True) -> str:
    if PROVIDER == "claude":
        try:
            text = _generate_claude(prompt, web_search, temperature, think)
        except Exception as e:
            if config.GEMINI_API_KEY:
                print(f"[llm] Claude failed ({str(e)[:120]}) — falling back to Gemini")
                text = _generate_gemini(prompt, web_search, temperature, think)
            else:
                raise
    else:
        text = _generate_gemini(prompt, web_search, temperature, think)

    text = (text or "").strip()
    if not text:
        raise RuntimeError(f"LLM ({PROVIDER}) returned empty response")
    return text
