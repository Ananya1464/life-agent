"""The agent's brain — pluggable, two backends, hardened.

1. "gemini"  — primary provider (Google AI Studio key). Gemini thinking
   mode + Google Search grounding.
2. "nvidia"  — fallback provider (NVIDIA NIM). Nemotron 3 Ultra.

Hardening:
  - Retries with exponential backoff on rate limits / transient errors
  - Cross-provider fallback: if Gemini fails and NVIDIA key exists,
    the task still completes on NVIDIA instead of crashing

Force a backend with LLM_PROVIDER=gemini|nvidia. One public function:
    generate(prompt, web_search=False, temperature=0.7, think=True) -> str
"""
import os
import pathlib
import time

from life_agent import config


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
    "gemini",
)
PROVIDER = PROVIDER.lower()

FALLBACK_PROVIDER = getattr(config, "LLM_FALLBACK_PROVIDER", None) or os.getenv(
    "LLM_FALLBACK_PROVIDER",
    "nvidia",
)
FALLBACK_PROVIDER = FALLBACK_PROVIDER.lower()

THINKING_BUDGET = int(os.getenv("THINKING_BUDGET", "8000"))  # tokens of reasoning
MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))


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


# --------------------------------------------------------------------- Gemini
def _generate_gemini(prompt, web_search, temperature, think):
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=config.GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=30_000)
    )
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


# ---------------------------------------------------------------------- NVIDIA
def _generate_nvidia(prompt, web_search, temperature, think):
    from openai import OpenAI

    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=config.NVIDIA_API_KEY,
    )
    model = config.NVIDIA_MODEL

    # NVIDIA NIM doesn't support web_search or thinking natively
    # Those are handled at the research layer (research.py)
    def _call():
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=temperature,
        )
        return resp.choices[0].message.content

    return _retry(_call)


# ----------------------------------------------------------------------- API
def generate(prompt: str, web_search: bool = False, temperature: float = 0.7,
             think: bool = True, provider: str = None) -> str:
    # Use explicit provider if provided, otherwise fall back to configured PROVIDER
    active_provider = (provider or PROVIDER).lower()

    # Primary provider logic
    if active_provider == "gemini":
        try:
            text = _generate_gemini(prompt, web_search, temperature, think)
        except Exception as e:
            if config.NVIDIA_API_KEY and FALLBACK_PROVIDER == "nvidia":
                print(f"[llm] Gemini failed ({str(e)[:120]}) — falling back to NVIDIA")
                text = _generate_nvidia(prompt, web_search, temperature, think)
            else:
                raise
    elif active_provider == "nvidia":
        if not config.NVIDIA_API_KEY:
            raise RuntimeError("NVIDIA_API_KEY not configured")
        text = _generate_nvidia(prompt, web_search, temperature, think)
    else:
        raise RuntimeError(f"Unknown LLM_PROVIDER: {active_provider}")

    text = (text or "").strip()
    if not text:
        raise RuntimeError(f"LLM ({active_provider}) returned empty response")
    return text