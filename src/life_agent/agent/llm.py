"""The agent's brain — pluggable, two backends, hardened.

1. "gemini"  — primary provider (Google AI Studio key). Gemini thinking
   mode + Google Search grounding.
2. "nvidia"  — fallback provider (NVIDIA NIM). Nemotron 3 Ultra.

Hardening:
  - Retries with exponential backoff on transient errors
  - Quota-aware handling for Gemini daily free-tier exhaustion
  - Cross-provider fallback: Gemini -> NVIDIA when configured

Force a backend with LLM_PROVIDER=gemini|nvidia. One public function:
    generate(prompt, web_search=False, temperature=0.7, think=True) -> str
"""
import os
import pathlib
import time

from life_agent import config


def _system_prompt() -> str:
    p = pathlib.Path(__file__).parent / "system_prompt.md"
    try:
        return p.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


SYSTEM_PROMPT = _system_prompt()

PROVIDER = getattr(config, "LLM_PROVIDER", None) or os.getenv("LLM_PROVIDER", "gemini")
PROVIDER = PROVIDER.lower()

FALLBACK_PROVIDER = getattr(config, "LLM_FALLBACK_PROVIDER", None) or os.getenv(
    "LLM_FALLBACK_PROVIDER",
    "nvidia",
)
FALLBACK_PROVIDER = FALLBACK_PROVIDER.lower()

THINKING_BUDGET = int(os.getenv("THINKING_BUDGET", "8000"))
MAX_RETRIES = int(getattr(config, "LLM_MAX_RETRIES", None) or os.getenv("LLM_MAX_RETRIES", "3"))


class LLMQuotaExceededError(RuntimeError):
    """Raised when provider quota is exhausted and retries should stop."""


def _is_quota_exhausted_error(msg: str) -> bool:
    m = (msg or "").lower()
    return any(t in m for t in (
        "resource_exhausted",
        "quota exceeded",
        "free_tier_requests",
        "generativelanguage.googleapis.com/generate_content_free_tier_requests",
        "generaterequestsperdayperprojectpermodel-freetier",
    ))


def _is_transient_error(msg: str) -> bool:
    m = (msg or "").lower()
    return any(t in m for t in (
        "429", "529", "500", "502", "503", "504",
        "overloaded", "rate limit", "too many requests", "timeout", "timed out",
    ))


def _retry(fn, *args, **kwargs):
    delay = 5
    for attempt in range(MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            msg = str(e)
            if _is_quota_exhausted_error(msg):
                raise LLMQuotaExceededError(msg) from e
            transient = _is_transient_error(msg)
            if not transient or attempt == MAX_RETRIES - 1:
                raise
            print(f"[llm] transient error, retrying in {delay}s: {msg[:120]}")
            time.sleep(delay)
            delay *= 2


def _generate_gemini(prompt, web_search, temperature, think):
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=config.GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=30_000),
    )
    cfg_kwargs = {"temperature": temperature}
    if SYSTEM_PROMPT:
        cfg_kwargs["system_instruction"] = SYSTEM_PROMPT
    if web_search:
        cfg_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    if think:
        try:
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_budget=THINKING_BUDGET
            )
        except Exception:
            pass

    def _call():
        resp = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(**cfg_kwargs),
        )
        return resp.text or ""

    return _retry(_call)


def _generate_nvidia(prompt, web_search, temperature, think):
    from openai import OpenAI

    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=config.NVIDIA_API_KEY,
    )

    def _call():
        resp = client.chat.completions.create(
            model=config.NVIDIA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=temperature,
        )
        return resp.choices[0].message.content

    return _retry(_call)


def _configured_fallback_provider(primary: str) -> str | None:
    explicit = (
        getattr(config, "LLM_FALLBACK_PROVIDER", None)
        or os.getenv("LLM_FALLBACK_PROVIDER", "")
        or FALLBACK_PROVIDER
    ).strip().lower()
    if not explicit or explicit == primary:
        return None
    return explicit


def _generate_with_provider(provider: str, prompt: str, web_search: bool,
                            temperature: float, think: bool) -> str:
    if provider == "gemini":
        return _generate_gemini(prompt, web_search, temperature, think)
    if provider == "nvidia":
        if not config.NVIDIA_API_KEY:
            raise RuntimeError("NVIDIA_API_KEY not configured")
        return _generate_nvidia(prompt, web_search, temperature, think)
    raise RuntimeError(f"Unknown LLM_PROVIDER: {provider}")


def generate(prompt: str, web_search: bool = False, temperature: float = 0.7,
             think: bool = True, provider: str = None) -> str:
    active_provider = (provider or PROVIDER).lower()
    provider_used = active_provider
    try:
        text = _generate_with_provider(active_provider, prompt, web_search, temperature, think)
    except Exception as e:
        is_quota = isinstance(e, LLMQuotaExceededError)
        fallback = _configured_fallback_provider(active_provider)
        can_fallback = (
            active_provider == "gemini"
            and fallback == "nvidia"
            and bool(config.NVIDIA_API_KEY)
        )

        if can_fallback:
            if is_quota:
                print("[llm] gemini quota exhausted — falling back to nvidia")
            else:
                print(f"[llm] gemini failed ({str(e)[:120]}) — falling back to nvidia")
            text = _generate_with_provider("nvidia", prompt, web_search, temperature, think)
            provider_used = "nvidia"
        elif is_quota:
            raise RuntimeError(
                "LLM quota exhausted for provider 'gemini'. "
                "No fallback provider is configured."
            ) from e
        else:
            raise

    text = (text or "").strip()
    if not text:
        raise RuntimeError(f"LLM ({provider_used}) returned empty response")
    return text
