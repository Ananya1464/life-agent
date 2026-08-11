"""Inbound reply polling and parsing for life-agent."""
from __future__ import annotations

import html
import imaplib
import json
import re
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr

import config
import dates
import event_model
import llm
import notion_api
import store

TOKEN_RE = re.compile(r"\[LA-\d{8}-[MDE]\]")
_STOP_PATTERNS = (
    re.compile(r"^On .+ wrote:$"),
    re.compile(r"^-----Original Message-----$"),
    re.compile(r"^_{10,}$"),
    re.compile(r"^\s*>") ,
    re.compile(r"^From: .+$"),
)
_SIGNATURE_RE = re.compile(r"^-- \s*$")
_JSON_PROMPT = """You extract structured data from a person's free-form email reply to a daily check-in. They write casually and may skip fields.

Return ONLY valid JSON, no prose, no markdown fences:
{
  "energy": int 1-5 or null,
  "sleep_hours": float or null,
  "soreness": "none"|"some"|"lots"|null,
  "checkins": [{"task": str, "status": "done"|"partial"|"never_started"|"forgot", "friction": str|null}],
  "captures": [{"bucket": "curiosity"|"build"|"obligation"|"tomorrow", "text": str}],
  "tomorrow": [{"text": str, "first_action": str|null}]
}

Rules:
- Use null for anything not stated. NEVER guess or infer a value the person did not give.
- Do not rephrase their words in capture text. Copy them.
- If they mention agreeing to something for someone else, that is an "obligation" capture.
"""


def strip_quotes(body: str) -> str:
    lines = body.splitlines()
    cut_at = len(lines)
    for index, line in enumerate(lines):
        if _STOP_PATTERNS[3].match(line):
            cut_at = index
            break
        if _STOP_PATTERNS[4].match(line) and index + 1 < len(lines) and lines[index + 1].startswith("Sent: "):
            cut_at = index
            break
        if any(pattern.match(line) for pattern in _STOP_PATTERNS[:3]):
            cut_at = index
            break

    stripped = lines[:cut_at]
    for index, line in enumerate(stripped):
        if _SIGNATURE_RE.match(line):
            stripped = stripped[:index]
            break

    result = "\n".join(stripped).strip()
    return result or body


def _body_from_message(message) -> str:
    part = message.get_body(preferencelist=("plain", "html")) if hasattr(message, "get_body") else None
    if part is not None:
        payload = part.get_content()
        if part.get_content_type() == "html":
            return re.sub(r"<[^>]+>", " ", html.unescape(payload))
        return payload

    if message.is_multipart():
        for subpart in message.walk():
            if subpart.get_content_maintype() != "text" or subpart.get_content_disposition() == "attachment":
                continue
            payload = subpart.get_content()
            if subpart.get_content_type() == "html":
                return re.sub(r"<[^>]+>", " ", html.unescape(payload))
            return payload

    payload = message.get_content() if hasattr(message, "get_content") else message.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="replace")
    return payload or ""


def _parse_json(text: str) -> dict:
    raw = llm.generate(f"{_JSON_PROMPT}\n\nReply:\n{text}", temperature=0.0, think=False)
    return json.loads(raw)


def parse_reply(token: str, text: str) -> dict:
    attempts = [text, f"Previous output was invalid JSON. Return only valid JSON.\n\n{text}"]
    for attempt_text in attempts:
        try:
            raw = llm.generate(
                f"{_JSON_PROMPT}\n\nReply:\n{attempt_text}",
                temperature=0.0,
                think=False,
            )
            data = json.loads(raw)
            data["token"] = token
            data["slot"] = {"M": "morning", "D": "midday", "E": "evening"}.get(token[-1:], "")
            data["parse_ok"] = True
            return data
        except (json.JSONDecodeError, RuntimeError, ValueError):
            continue

    result = {
        "token": token,
        "energy": None,
        "sleep_hours": None,
        "soreness": None,
        "checkins": [],
        "captures": [],
        "tomorrow": [],
        "parse_ok": False,
        "parse_error": "LLM parsing failed after one retry",
        "raw_text": text,
    }
    return result


def fetch_replies() -> list[dict]:
    if not config.GMAIL_ADDRESS or not config.GMAIL_APP_PASSWORD:
        raise ValueError("GMAIL_ADDRESS or GMAIL_APP_PASSWORD not configured")

    client = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        status, _ = client.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
        if status != "OK":
            raise RuntimeError("IMAP login failed")
        status, _ = client.select("INBOX")
        if status != "OK":
            raise RuntimeError("IMAP inbox select failed")

        status, data = client.uid("search", None, '(UNSEEN SUBJECT "[LA-")')
        if status != "OK":
            raise RuntimeError("IMAP search failed")

        results = []
        for uid in (data[0].split() if data and data[0] else []):
            status, fetched = client.uid("fetch", uid, "(RFC822)")
            if status != "OK":
                raise RuntimeError(f"IMAP fetch failed for UID {uid.decode('ascii', 'ignore')}")

            raw_bytes = fetched[0][1]
            message = BytesParser(policy=policy.default).parsebytes(raw_bytes)
            subject = message.get("Subject", "")
            token_match = TOKEN_RE.search(subject)
            if not token_match:
                continue

            token = token_match.group(0).strip("[]")
            from_addr = parseaddr(message.get("From", ""))[1]
            body_raw = _body_from_message(message)

            store.append("reply_raw", {
                "token": token,
                "from_addr": from_addr,
                "gmail_uid": uid.decode("ascii", errors="ignore"),
                "body_raw": body_raw,
            })

            stripped = strip_quotes(body_raw)
            parsed = parse_reply(token, stripped)
            parsed_id = store.append("reply_parsed", parsed)
            parsed["id"] = parsed_id
            if not parsed.get("parse_ok"):
                raise RuntimeError(f"Reply parse failed for token {token}: {parsed.get('parse_error')}")

            notion_api.sync_event(parsed)
            reply_slot = {"M": "morning", "D": "midday", "E": "evening"}.get(token[-1:], "")
            event_model.normalize_reply_events(
                date_iso=dates.today().isoformat(),
                token=token,
                reply_id=parsed_id,
                captures=parsed.get("captures", []),
                checkins=parsed.get("checkins", []),
                planned_intentions=[
                    ev for ev in store.load_all()
                    if ev.get("kind") == "task_planned"
                    and ev.get("date") == dates.today().isoformat()
                    and ev.get("slot") == reply_slot
                ],
            )

            client.uid("store", uid, "+FLAGS", "\\Seen")
            results.append(parsed)

        return results
    finally:
        try:
            client.logout()
        except Exception:
            pass