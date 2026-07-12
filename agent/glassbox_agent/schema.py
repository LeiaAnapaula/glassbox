"""The EventCandidate contract shared between the model, validation, and the card.

The model is asked to return exactly this object. We never trust it blindly:
:func:`validate` re-checks required fields, date ordering, and ambiguity so the
confirmation card can surface problems instead of silently creating a wrong
event.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional

# JSON schema handed to the model via response_format-style instructions.
EVENT_CANDIDATE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["event", "non_event", "uncertain"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "title": {"type": ["string", "null"]},
        "start_local": {"type": ["string", "null"], "description": "ISO 8601 local, e.g. 2026-07-15T14:00"},
        "end_local": {"type": ["string", "null"], "description": "ISO 8601 local"},
        "timezone": {"type": ["string", "null"], "description": "IANA tz, e.g. America/Los_Angeles"},
        "location": {"type": ["string", "null"]},
        "source_text": {"type": ["string", "null"], "description": "Verbatim text the extraction is based on"},
        "missing_fields": {"type": "array", "items": {"type": "string"}},
        "ambiguities": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["kind", "confidence"],
}


@dataclass
class EventCandidate:
    kind: str = "uncertain"
    confidence: float = 0.0
    title: Optional[str] = None
    start_local: Optional[str] = None
    end_local: Optional[str] = None
    timezone: Optional[str] = None
    location: Optional[str] = None
    source_text: Optional[str] = None
    missing_fields: list[str] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EventCandidate":
        allowed = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        clean = {k: v for k, v in d.items() if k in allowed}
        for list_key in ("missing_fields", "ambiguities"):
            if not isinstance(clean.get(list_key), list):
                clean[list_key] = []
        try:
            clean["confidence"] = float(clean.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            clean["confidence"] = 0.0
        return cls(**clean)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def validate(candidate: EventCandidate) -> EventCandidate:
    """Locally re-derive missing_fields / ambiguities and clamp obvious problems.

    Runs on top of whatever the model returned so the card can trust these
    lists. Never invents values; only flags what is absent or contradictory.
    Downgrades ``event`` -> ``uncertain`` when the event is not actually
    actionable, so the card always shows a warning instead of a false green.
    """
    if candidate.kind == "non_event":
        # Nothing to schedule — don't manufacture missing-field noise.
        candidate.missing_fields = []
        candidate.ambiguities = []
        return candidate

    missing: list[str] = []
    ambiguities = list(candidate.ambiguities)

    if not candidate.title:
        missing.append("title")
    if not candidate.start_local:
        missing.append("start_local")

    start = _parse_iso(candidate.start_local)
    end = _parse_iso(candidate.end_local)
    if candidate.start_local and start is None:
        ambiguities.append("start time could not be parsed as ISO 8601")
    if candidate.end_local and end is None:
        ambiguities.append("end time could not be parsed as ISO 8601")
    if start and end and end < start:
        ambiguities.append("end time is before start time")
    if not candidate.timezone:
        # Not fatal (Calendar assumes local tz) but worth flagging.
        ambiguities.append("timezone not specified; assuming this machine's local time")

    # De-dupe while preserving order.
    candidate.missing_fields = list(dict.fromkeys(missing))
    candidate.ambiguities = list(dict.fromkeys(ambiguities))

    # A candidate that claims to be an event but lacks a start time or title
    # is not actionable — force it back to uncertain so the user must confirm.
    if candidate.kind == "event" and ({"title", "start_local"} & set(candidate.missing_fields)):
        candidate.kind = "uncertain"

    return candidate
