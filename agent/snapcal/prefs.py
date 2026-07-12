"""Transparent local preference memory.

Stores only aggregate counts over explicit user outcomes (added / dismissed /
not-an-event), never raw screenshots. Enough to learn a simple signal — e.g.
"you dismiss most low-confidence suggestions" — without any opaque profiling.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import Config


class Prefs:
    def __init__(self, cfg: Config):
        self.path = cfg.data_dir / "prefs.json"
        self.data: dict[str, Any] = {
            "added": 0, "dismissed": 0, "not_event": 0,
            "added_confidence_sum": 0.0,
            "by_frontmost": {},
        }
        if self.path.exists():
            try:
                self.data.update(json.loads(self.path.read_text()))
            except json.JSONDecodeError:
                pass

    def record(self, decision: str, *, confidence: float = 0.0, frontmost: str = "") -> None:
        if decision == "add":
            self.data["added"] += 1
            self.data["added_confidence_sum"] += confidence
        elif decision == "dismiss":
            self.data["dismissed"] += 1
        elif decision == "not_event":
            self.data["not_event"] += 1
        if frontmost:
            fm = self.data.setdefault("by_frontmost", {})
            entry = fm.setdefault(frontmost, {"added": 0, "dismissed": 0})
            if decision == "add":
                entry["added"] += 1
            elif decision in ("dismiss", "not_event"):
                entry["dismissed"] += 1
        self._save()

    def hint(self) -> str:
        """A short, human-readable summary for the confirmation card."""
        added, dismissed = self.data["added"], self.data["dismissed"] + self.data["not_event"]
        total = added + dismissed
        if total == 0:
            return "No history yet."
        rate = added / total
        return f"You've added {added} and dismissed {dismissed} suggestions ({rate:.0%} kept)."

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2))
