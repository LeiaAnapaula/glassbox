"""Evidence-preserving contract for the synthetic anti-trafficking demo.

The object records only observable text from a fictional screenshot.  It is not
a trafficking determination, risk score, suspect profile, or recommendation to
law enforcement.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


_ADVERSE_LANGUAGE: dict[str, tuple[str, ...]] = {
    "document_control": ("kept my passport", "keeping my passport", "took my passport", "holds my id"),
    "movement_restriction": ("cannot leave", "can't leave", "not allowed to leave", "permission to leave"),
    "threat_or_coercion": ("threatened", "threaten", "hurt me", "forced me", "force me"),
    "withheld_pay_or_debt": ("not been paid", "unpaid", "owe them", "debt", "withheld my pay"),
    "basic_needs_denial": ("no food", "denied food", "denied water", "denied sleep", "no medical care"),
    "isolation_or_control": ("cannot talk", "can't talk", "not allowed to talk", "watching me"),
    "request_for_help": ("help me", "need help", "want to talk to someone privately", "not safe"),
}


TRIAGE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["review", "insufficient_context", "unrelated"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "summary": {"type": "string"},
        "observable_statements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [
                            "document_control", "movement_restriction", "threat_or_coercion",
                            "withheld_pay_or_debt", "basic_needs_denial", "isolation_or_control",
                            "request_for_help", "other",
                        ],
                    },
                    "quote": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": ["category", "quote", "explanation"],
            },
        },
        "missing_context": {"type": "array", "items": {"type": "string"}},
        "immediate_danger_language": {"type": "boolean"},
        "limitations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["kind", "confidence", "summary", "observable_statements", "missing_context"],
}


@dataclass
class ObservableStatement:
    category: str
    quote: str
    explanation: str


@dataclass
class TriageCandidate:
    kind: str = "insufficient_context"
    confidence: float = 0.0
    summary: str = ""
    observable_statements: list[ObservableStatement] = field(default_factory=list)
    missing_context: list[str] = field(default_factory=list)
    immediate_danger_language: bool = False
    limitations: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TriageCandidate":
        statements = []
        for raw in value.get("observable_statements") or []:
            if not isinstance(raw, dict):
                continue
            quote = str(raw.get("quote") or "").strip()
            if not quote:
                continue
            statements.append(ObservableStatement(
                category=str(raw.get("category") or "other"),
                quote=quote,
                explanation=str(raw.get("explanation") or "Observable statement for human review"),
            ))
        try:
            confidence = min(1.0, max(0.0, float(value.get("confidence", 0))))
        except (TypeError, ValueError):
            confidence = 0.0
        kind = value.get("kind") if value.get("kind") in {
            "review", "insufficient_context", "unrelated"
        } else "insufficient_context"
        if kind == "review" and not statements:
            kind = "insufficient_context"
        return cls(
            kind=kind,
            confidence=confidence,
            summary=str(value.get("summary") or ""),
            observable_statements=statements,
            missing_context=[str(x) for x in value.get("missing_context") or []],
            immediate_danger_language=bool(value.get("immediate_danger_language", False)),
            limitations=[str(x) for x in value.get("limitations") or []],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate(candidate: TriageCandidate) -> TriageCandidate:
    """Discard model category assignments unsupported by adverse quoted language.

    This intentionally favors false negatives in a synthetic demonstration. A
    protective sentence such as “your passport stays with you” must never become
    a document-control observation merely because the model chose that category.
    """
    supported: list[ObservableStatement] = []
    for item in candidate.observable_statements:
        quote = " ".join(item.quote.lower().split())
        anchors = _ADVERSE_LANGUAGE.get(item.category, ())
        if anchors and any(anchor in quote for anchor in anchors):
            supported.append(item)
    candidate.observable_statements = supported
    if not supported:
        candidate.kind = "unrelated"
        candidate.immediate_danger_language = False
        candidate.confidence = min(candidate.confidence, 0.5)
        candidate.limitations.append(
            "No quoted adverse assertion passed deterministic post-validation."
        )
    candidate.limitations = list(dict.fromkeys(candidate.limitations))
    return candidate
