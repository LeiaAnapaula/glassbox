"""Hackathon preflight checks without performing consequential actions."""

from __future__ import annotations

import json
from pathlib import Path

from .config import Config


def collect(cfg: Config, repo_root: Path | None = None) -> list[tuple[str, bool, str]]:
    if repo_root is None:
        cwd = Path.cwd()
        repo_root = cwd if (cwd / "agent" / "pyproject.toml").is_file() else Path(__file__).resolve().parents[2]
    checks: list[tuple[str, bool, str]] = []
    checks.append(("H API credential", cfg.has_api_key, "run `holo login`"))
    checks.append(("HoloDesktop CLI", cfg.has_holo_cli, "install HoloDesktop CLI"))
    whatsapp = Path("/Applications/WhatsApp.app").exists()
    checks.append(("WhatsApp Desktop", whatsapp, "install and sign into WhatsApp Desktop"))
    oauth_client = cfg.data_dir / "credentials.json"
    oauth_token = cfg.data_dir / "token.json"
    checks.append(("Google OAuth client", oauth_client.is_file(), f"place Desktop OAuth JSON at {oauth_client}"))
    checks.append(("Google OAuth token", oauth_token.is_file(), "run one Calendar test to complete consent"))

    fixture = repo_root / "runs" / "fixture-demo.json"
    fixture_ok = False
    if fixture.is_file():
        try:
            rows = [json.loads(line) for line in fixture.read_text().splitlines() if line.strip()]
            fixture_ok = sum(row.get("irreversible") is True for row in rows) == 1
        except (OSError, json.JSONDecodeError):
            pass
    checks.append(("Pause-gate fixture", fixture_ok, "fixture must contain exactly one irreversible step"))

    examples = repo_root / "agent" / "demo" / "synthetic-triage"
    images = sorted(examples.glob("*.png"))
    manifests_ok = len(images) == 3 and all(
        image.with_suffix(image.suffix + ".synthetic.json").is_file() for image in images
    )
    checks.append(("Synthetic triage cases", manifests_ok, "expected three images with synthetic manifests"))
    return checks


def main() -> int:
    cfg = Config.load()
    checks = collect(cfg)
    for name, ok, fix in checks:
        print(f"{'✓' if ok else '✕'} {name}" + ("" if ok else f" — {fix}"))
    blockers = [name for name, ok, _ in checks if not ok]
    if blockers:
        print(f"\n{len(blockers)} blocker(s) remain.")
        return 1
    print("\nStatic preflight green. Live sends and Calendar writes still require explicit confirmation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
