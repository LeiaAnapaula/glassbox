"""Holo3.1 image -> EventCandidate.

One schema-constrained vision request per screenshot. We deliberately do NOT
run a desktop agent loop here — classification/extraction is a single, cheap,
deterministic call. HoloDesktop is reserved for the actual Calendar interaction.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from .config import Config
from .schema import EVENT_CANDIDATE_JSON_SCHEMA, EventCandidate, validate

_SYSTEM = (
    "You inspect a single screenshot and decide whether it depicts a concrete, "
    "schedulable calendar event (a meeting, appointment, booking, class, flight, "
    "reservation, deadline with a time, etc.). You extract candidate fields for "
    "the user to confirm. You never fabricate: if a year, timezone, end time, or "
    "recurrence is not visible, leave it null and note it. When an event reading "
    "is plausible but the date/time semantics are incomplete, return kind "
    '"uncertain" rather than "event". Reply with ONE JSON object only, no prose.'
)


def _prompt(now: datetime, tz_name: str) -> str:
    schema = json.dumps(EVENT_CANDIDATE_JSON_SCHEMA, indent=2)
    return (
        f"Current local date-time: {now.isoformat(timespec='minutes')} "
        f"({tz_name}). Resolve relative dates ('tomorrow', 'Friday') against this.\n\n"
        f"Return JSON matching this schema:\n{schema}\n\n"
        "Rules:\n"
        "- start_local / end_local are ISO 8601 local wall-clock (YYYY-MM-DDTHH:MM), no offset.\n"
        "- Put the exact words you read into source_text.\n"
        "- If it is clearly not an event (a chat, a webpage, code, a meme), "
        'return kind "non_event" with confidence.\n'
        "- Never guess a year or timezone that is not shown; list what is missing."
    )


def _local_now() -> tuple[datetime, str]:
    now = datetime.now().astimezone()
    return now, (now.tzname() or "local")


def _extract_json(text: str) -> dict:
    """Parse the model reply, tolerating stray prose or code fences."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    # Last resort: first balanced-looking {...} span.
    start = text.find("{")
    end = text.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"model did not return JSON: {text[:200]!r}")


def _data_uri(image_path: Path) -> str:
    raw = image_path.read_bytes()
    b64 = base64.b64encode(raw).decode()
    suffix = image_path.suffix.lower().lstrip(".") or "png"
    mime = "jpeg" if suffix in ("jpg", "jpeg") else suffix
    return f"data:image/{mime};base64,{b64}"


class RealModelClient:
    """Calls the H model gateway (OpenAI-compatible /v1/chat/completions)."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        if not cfg.has_api_key:
            raise RuntimeError(
                "No HAI_API_KEY found (checked $HAI_API_KEY and ~/.holo/.env). "
                "Run `holo login`."
            )

    def extract(self, image_path: Path) -> EventCandidate:
        now, tz_name = _local_now()
        body = {
            "model": self.cfg.model,
            "max_tokens": 700,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _prompt(now, tz_name)},
                        {"type": "image_url", "image_url": {"url": _data_uri(image_path)}},
                    ],
                },
            ],
        }
        req = urllib.request.Request(
            f"{self.cfg.base_url}/chat/completions",
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {self.cfg.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"model gateway {e.code}: {e.read().decode()[:300]}") from e
        content = payload["choices"][0]["message"]["content"]
        candidate = EventCandidate.from_dict(_extract_json(content))
        return validate(candidate)
