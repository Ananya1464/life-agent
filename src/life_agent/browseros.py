"""Free web search through BrowserOS neo, the real browser Ananya already runs for agents.

BrowserOS exposes an MCP server (streamable HTTP, default http://127.0.0.1:9010/mcp, no key). We drive it with plain
JSON-RPC: open our own tab on a search page, read the results as markdown, close the tab. A real browser is not
blocked the way scripted HTTP clients are, and it costs nothing. Everything is best effort: callers get None when
BrowserOS is not reachable and fall back to something else.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import requests

DEFAULT_URL = "http://127.0.0.1:9010/mcp"
SEARCH_URL = "https://duckduckgo.com/?q={q}&ia=web"
SESSION_NAME = "life-agent-research"
_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def endpoint() -> str:
    return os.environ.get("BROWSEROS_MCP_URL", DEFAULT_URL)


def is_up(timeout: float = 2.0) -> bool:
    try:
        requests.get(endpoint(), timeout=timeout)
        return True
    except requests.exceptions.ConnectionError:
        return False
    except Exception:
        return True            # something answered (even with an error status): the server is there


def launcher() -> Path | None:
    """The shortcut that starts BrowserOS: BROWSEROS_LAUNCH, else the Desktop shortcut."""
    env = os.environ.get("BROWSEROS_LAUNCH")
    candidates = [Path(env)] if env else [Path.home() / "OneDrive" / "Desktop" / "BrowserOS neo.lnk",
                                          Path.home() / "Desktop" / "BrowserOS neo.lnk"]
    return next((p for p in candidates if p.exists()), None)


def ensure_running(wait_seconds: int = 45) -> bool:
    """True when the MCP server answers; starts BrowserOS from its shortcut if needed (Windows)."""
    if is_up():
        return True
    link = launcher()
    if link is None or not hasattr(os, "startfile"):
        return False
    try:
        os.startfile(str(link))                                  # nosec - the user's own shortcut
    except Exception as err:
        print(f"[browseros] could not start BrowserOS: {err}")
        return False
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        time.sleep(2)
        if is_up():
            return True
    return False


class BrowserOS:
    """One MCP session. Use as a context manager."""

    def __init__(self, url: str | None = None, timeout: float = 60):
        self.url = url or endpoint()
        self.timeout = timeout
        self.session_id: str | None = None
        self._next = 1

    def _rpc(self, method: str, params: dict | None = None, want_reply: bool = True):
        body: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        if want_reply:
            body["id"] = self._next
            self._next += 1
        headers = dict(_HEADERS)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        resp = requests.post(self.url, json=body, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        if self.session_id is None:
            self.session_id = resp.headers.get("Mcp-Session-Id")
        last = None
        for line in resp.text.splitlines():
            if line.startswith("data:") and line[5:].strip().startswith("{"):
                last = json.loads(line[5:].strip())
        return last

    def __enter__(self) -> "BrowserOS":
        self._rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                 "clientInfo": {"name": "life-agent", "version": "1"}})
        self._rpc("notifications/initialized", {}, want_reply=False)
        self.call("name_session", {"name": "career search", "category": "research",
                                   "summary": "web search for opportunities and reading"})
        return self

    def __exit__(self, *exc) -> None:
        return None

    def call(self, tool: str, args: dict | None = None) -> tuple[bool, str]:
        reply = self._rpc("tools/call", {"name": tool, "arguments": dict(args or {})}) or {}
        result = reply.get("result", {})
        text = "\n".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
        return bool(result.get("isError")), text

    def open_page(self, url: str) -> int:
        is_err, text = self.call("tabs", {"action": "new", "url": url})
        m = re.search(r"opened page (\d+)", text)
        if is_err or not m:
            raise RuntimeError(f"BrowserOS could not open a tab: {text[:120]}")
        return int(m.group(1))

    def close_page(self, page: int) -> None:
        try:
            self.call("tabs", {"action": "close", "page": page})
        except Exception:
            pass

    def read_page(self, page: int) -> str:
        is_err, text = self.call("read", {"page": page, "format": "markdown", "includeLinks": True})
        if is_err:
            raise RuntimeError(f"BrowserOS could not read the page: {text[:120]}")
        return text


_RESULT = re.compile(r"^## \[(?P<title>[^\]]+)\]\((?P<url>https?://[^)\s]+)\)[ \t]*\n+(?P<body>.*?)(?=\n\d+\. |\n## |\Z)", re.S | re.M)


def parse_results(markdown: str, limit: int = 8) -> list[dict]:
    """Search-result blocks from a DuckDuckGo results page read as markdown: [{title, url, snippet}]."""
    out, seen = [], set()
    for m in _RESULT.finditer(markdown):
        url = m.group("url")
        if url in seen or "duckduckgo.com" in url:
            continue
        seen.add(url)
        snippet = re.sub(r"\s+", " ", re.sub(r"[*_`]|\[([^\]]*)\]\([^)]*\)", r"\1", m.group("body"))).strip()[:400]
        out.append({"title": re.sub(r"\s+", " ", m.group("title")).strip(), "url": url, "snippet": snippet})
        if len(out) >= limit:
            break
    return out


def search(query: str, limit: int = 8, settle_seconds: float = 5.0) -> list[dict] | None:
    """Real results for a query, [] if the page had none, or None when BrowserOS is unavailable or failed."""
    if not ensure_running():
        return None
    try:
        with BrowserOS() as browser:
            page = browser.open_page(SEARCH_URL.format(q=requests.utils.quote(query)))
            try:
                time.sleep(settle_seconds)
                return parse_results(browser.read_page(page), limit)
            finally:
                browser.close_page(page)
    except Exception as err:
        print(f"[browseros] search failed for '{query[:40]}': {str(err)[:120]}")
        return None
