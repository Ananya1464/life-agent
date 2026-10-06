"""The agent's brain — pluggable, two backends, hardened.

1. "gemini"  — primary provider (Google AI Studio key). Gemini thinking
   mode + Google Search grounding.
2. "nvidia"  — fallback provider (NVIDIA NIM). Nemotron 3 Ultra.

Hardening:
  - Retries with exponential backoff on transient errors
  - Quota-aware handling for Gemini daily free-tier exhaustion
  - Cross-provider fallback: Gemini -> NVIDIA when configured

Force the default backend with LLM_PROVIDER=gemini|nvidia, or override a
single call with provider="gemini"|"nvidia". One public function:
    generate(prompt, web_search=False, temperature=0.7, think=True,
             provider=None) -> str
"""
import os
import pathlib
import time

from life_agent import config


class GenerateResult(str):
    """String subclass that carries provider and search-grounding metadata."""
    provider: str
    search_grounded: bool
    model: str

    def __new__(cls, text: str, provider: str = "", search_grounded: bool = False, model: str = ""):
        obj = super().__new__(cls, text)
        obj.provider = provider
        obj.search_grounded = search_grounded
        obj.model = model
        return obj


def _load_system_prompt() -> tuple[str, str]:
    candidates = [
        pathlib.Path(__file__).resolve().parents[3] / "system_prompt.md",
        pathlib.Path(__file__).resolve().parent / "system_prompt.md",
        pathlib.Path.cwd() / "system_prompt.md",
    ]
    for p in candidates:
        if p.is_file():
            try:
                content = p.read_text(encoding="utf-8").strip()
                if content:
                    return content, str(p)
            except OSError:
                pass
    return "", ""


SYSTEM_PROMPT, SYSTEM_PROMPT_PATH = _load_system_prompt()
if SYSTEM_PROMPT:
    print(f"[llm] system prompt loaded ({len(SYSTEM_PROMPT)} chars) from {SYSTEM_PROMPT_PATH}")
else:
    print("[llm] WARNING: system prompt is empty or not found!")

PROVIDER = getattr(config, "LLM_PROVIDER", None) or os.getenv("LLM_PROVIDER", "gemini")
PROVIDER = PROVIDER.lower()

FALLBACK_PROVIDER = getattr(config, "LLM_FALLBACK_PROVIDER", None) or os.getenv(
    "LLM_FALLBACK_PROVIDER",
    "nvidia",
)
FALLBACK_PROVIDER = FALLBACK_PROVIDER.lower()

THINKING_BUDGET = int(os.getenv("THINKING_BUDGET", "8000"))
OMNIROUTE_TIMEOUT = float(os.getenv("OMNIROUTE_TIMEOUT", "90"))
_last_model: dict = {}  # provider -> model that actually answered
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
    """Run fn with backoff on transient errors; do not retry exhausted quotas."""
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


def _generate_omniroute(prompt, web_search, temperature, think):
    """OmniRoute gateway (OpenAI-compatible). Tries each model in OMNIROUTE_MODELS in order and
    moves on when one is refused (rate limit, bad request, server error)."""
    from openai import OpenAI

    client = OpenAI(base_url=config.OMNIROUTE_BASE_URL, api_key=config.OMNIROUTE_API_KEY,
                    timeout=OMNIROUTE_TIMEOUT, max_retries=0)
    messages = []
    if SYSTEM_PROMPT:
        messages.append({"role": "system", "content": SYSTEM_PROMPT})
    messages.append({"role": "user", "content": prompt})

    errors = []
    for model in config.OMNIROUTE_MODELS:
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages, max_tokens=4096, temperature=temperature)
            choice = resp.choices[0]
            text = (choice.message.content or "").strip()
            if getattr(choice, "finish_reason", "stop") == "length" or (text and len(text) < 8):
                errors.append(f"{model}: truncated answer")      # a cut-off plan is worse than a retry
                continue
            if text:
                _last_model["omniroute"] = getattr(resp, "model", None) or model
                return text
            errors.append(f"{model}: empty response")
        except Exception as exc:
            errors.append(f"{model}: {type(exc).__name__} {str(exc)[:80]}")
    raise RuntimeError("OmniRoute: all models failed (" + "; ".join(errors) + ")")


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
        messages = []
        if SYSTEM_PROMPT:
            messages.append({"role": "system", "content": SYSTEM_PROMPT})
        messages.append({"role": "user", "content": prompt})

        resp = client.chat.completions.create(
            model=config.NVIDIA_MODEL,
            messages=messages,
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
    if provider == "omniroute":
        if not config.OMNIROUTE_API_KEY:
            raise RuntimeError("OMNIROUTE_API_KEY not configured")
        return _generate_omniroute(prompt, web_search, temperature, think)
    if provider == "gemini":
        return _generate_gemini(prompt, web_search, temperature, think)
    if provider == "nvidia":
        if not config.NVIDIA_API_KEY:
            raise RuntimeError("NVIDIA_API_KEY not configured")
        return _generate_nvidia(prompt, web_search, temperature, think)
    raise RuntimeError(f"Unknown LLM_PROVIDER: {provider}")


# ----------------------------------------------------------------------- API
PROVIDER_CHAINS = {
    "omniroute": ["omniroute", "gemini", "nvidia"],
    "gemini": ["gemini", "nvidia"],
    "nvidia": ["nvidia"],
}


def _provider_available(provider: str) -> bool:
    return bool({"omniroute": config.OMNIROUTE_API_KEY, "gemini": config.GEMINI_API_KEY,
                 "nvidia": config.NVIDIA_API_KEY}.get(provider))


def generate(prompt: str, web_search: bool = False, temperature: float = 0.7,
             think: bool = True, provider: str | None = None) -> GenerateResult:
    """Generate text. With no explicit provider, falls down the chain omniroute -> gemini -> nvidia
    (starting at the configured primary), skipping providers without a key."""
    explicit_provider = provider is not None
    primary = (provider if explicit_provider else PROVIDER).strip().lower()
    chain = [primary] if explicit_provider else [
        p for p in PROVIDER_CHAINS.get(primary, [primary]) if p == primary or _provider_available(p)]
    if web_search and not explicit_provider and "gemini" in chain and chain[0] != "gemini":
        # only Gemini can really search the web; the others would answer from memory and call it search
        chain = ["gemini"] + [p for p in chain if p != "gemini"]

    last_error: Exception | None = None
    for i, active in enumerate(chain):
        try:
            text = (_generate_with_provider(active, prompt, web_search, temperature, think) or "").strip()
            if not text:
                raise RuntimeError(f"LLM ({active}) returned empty response")
            model = {"omniroute": _last_model.get("omniroute"), "gemini": config.GEMINI_MODEL,
                     "nvidia": config.NVIDIA_MODEL}.get(active) or ""
            return GenerateResult(text, provider=active, search_grounded=bool(web_search and active == "gemini"),
                                  model=model)
        except Exception as exc:
            last_error = exc
            nxt = chain[i + 1] if i + 1 < len(chain) else None
            kind = "quota exhausted" if isinstance(exc, LLMQuotaExceededError) else f"failed ({str(exc)[:120]})"
            if nxt:
                print(f"[llm] {active} {kind} - falling back to {nxt}")
    if isinstance(last_error, LLMQuotaExceededError):
        raise RuntimeError(f"LLM quota exhausted for provider '{chain[-1]}'. No fallback provider is configured.") from last_error
    raise last_error
