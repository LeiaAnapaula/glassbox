"""Synthetic-only pause-before-queue demo for trained human review."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import messagebox

from .config import Config
from .triage_model import TriageModelClient


def _verify_synthetic(image: Path) -> dict:
    manifest_path = image.with_suffix(image.suffix + ".synthetic.json")
    if not manifest_path.exists():
        raise ValueError("refusing input without a .synthetic.json sidecar")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("synthetic") is not True:
        raise ValueError("sidecar does not declare synthetic=true")
    return manifest


def _review_text(candidate) -> str:
    lines = [
        "FICTIONAL TRAINING CASE — NOT A TRAFFICKING DETERMINATION",
        "",
        f"Model disposition: {candidate.kind}",
        f"Extraction confidence: {candidate.confidence:.0%} (not a risk score)",
        f"Summary: {candidate.summary or 'No summary'}",
        "",
        "Observable quoted statements:",
    ]
    if candidate.observable_statements:
        for item in candidate.observable_statements:
            lines.append(f"• [{item.category}] “{item.quote}”")
    else:
        lines.append("• None")
    lines.extend(["", "Missing context:"])
    lines.extend(f"• {item}" for item in (candidate.missing_context or ["Context not established"] ))
    lines.extend(["", "Indicators are not proof. A trained human must review the original material."])
    return "\n".join(lines)


def _append_log(cfg: Config, image: Path, manifest: dict, candidate, decision: str) -> Path:
    out = cfg.data_dir / "synthetic-triage-log.jsonl"
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "synthetic_case_id": manifest.get("case_id", image.stem),
        "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        "candidate": candidate.to_dict(),
        "human_decision": decision,
        "external_route": None,
    }
    with out.open("a") as handle:
        handle.write(json.dumps(row) + "\n")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic safeguarding triage demo")
    parser.add_argument("image", help="Synthetic screenshot with a matching sidecar manifest")
    args = parser.parse_args(argv)
    image = Path(args.image).expanduser().resolve()
    if not image.is_file():
        print(f"No such image: {image}", file=sys.stderr)
        return 2
    try:
        manifest = _verify_synthetic(image)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"Synthetic-only guardrail: {exc}", file=sys.stderr)
        return 2

    cfg = Config.load()
    candidate = TriageModelClient(cfg).extract(image)
    root = tk.Tk()
    root.withdraw()
    if candidate.kind == "review":
        approved = messagebox.askyesno(
            "Glassbox · synthetic human-review triage",
            _review_text(candidate) + "\n\nQueue this fictional case for local human review?",
            icon="warning",
        )
    else:
        messagebox.showinfo(
            "Glassbox · no review recommendation",
            _review_text(candidate) + "\n\nNo case will be queued.",
        )
        approved = False
    decision = "queued_for_local_review" if approved else "dismissed"
    log_path = _append_log(cfg, image, manifest, candidate, decision)
    root.destroy()
    print(json.dumps({"decision": decision, "log": str(log_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
