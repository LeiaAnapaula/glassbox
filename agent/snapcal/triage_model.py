"""Holo3.1 extraction for the synthetic, human-review-only triage demo."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from .config import Config
from .model_client import _data_uri, _extract_json
from .triage_schema import TRIAGE_JSON_SCHEMA, TriageCandidate, validate


_SYSTEM = (
    "You are an evidence-preserving assistant for a FICTIONAL training demo. "
    "Inspect one synthetic screenshot and quote only observable first-person or "
    "direct statements that a trained safeguarding professional may want to review. "
    "You must never decide that trafficking occurred, identify a victim or perpetrator, "
    "infer protected traits, assess credibility, accuse anyone, or recommend police action. "
    "Indicators are not proof and a screenshot lacks context. Prefer insufficient_context. "
    "Do not treat job offers, travel, nationality, gender, clothing, or occupation alone as "
    "signals. Return exactly one JSON object and no prose."
)


def _prompt() -> str:
    return (
        "Extract only verbatim statements visible in this synthetic screenshot. Categories "
        "are organizational labels, not findings. Set immediate_danger_language only when "
        "the screenshot explicitly says someone faces imminent physical danger or asks for "
        "emergency help. Always list missing context and include the limitation that a human "
        "must assess the original material. Schema:\n" + json.dumps(TRIAGE_JSON_SCHEMA)
    )


class TriageModelClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        if not cfg.has_api_key:
            raise RuntimeError("No HAI_API_KEY found. Run `holo login`.")

    def extract(self, image_path: Path) -> TriageCandidate:
        body = {
            "model": self.cfg.model,
            "max_tokens": 900,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": [
                    {"type": "text", "text": _prompt()},
                    {"type": "image_url", "image_url": {"url": _data_uri(image_path)}},
                ]},
            ],
        }
        req = urllib.request.Request(
            f"{self.cfg.base_url}/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self.cfg.api_key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"model gateway {exc.code}: {exc.read().decode()[:300]}") from exc
        candidate = TriageCandidate.from_dict(
            _extract_json(payload["choices"][0]["message"]["content"])
        )
        return validate(candidate)
