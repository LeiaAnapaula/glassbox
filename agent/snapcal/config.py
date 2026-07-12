"""Runtime configuration: paths, model gateway, and HoloDesktop discovery.

Everything is resolved lazily from the environment and the local ``~/.holo``
install so the agent works out of the box on a machine that already ran
``holo login`` — no config file required.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

HOLO_HOME = Path(os.environ.get("HOLO_HOME", str(Path.home() / ".holo")))
HOLO_BIN = HOLO_HOME / "bin" / "holo"
HOLO_ENV = HOLO_HOME / ".env"

# The H model gateway is OpenAI-compatible; base is the `/v1` root.
DEFAULT_BASE_URL = "https://api.hcompany.ai/v1"
# Holo3.1 — the smaller, faster multimodal model. Good enough for extraction.
DEFAULT_MODEL = "holo3-1-35b-a3b"

# User-scoped state (works regardless of where the package is installed):
# OAuth client + token, seen-hash/prefs stores, and --cua traces all live here.
# Override with $SNAPCAL_HOME.
DATA_DIR = Path(os.environ.get("SNAPCAL_HOME", str(Path.home() / ".snapcal")))
TRACES_DIR = DATA_DIR / "traces"


def _read_dotenv(path: Path) -> dict[str, str]:
    """Parse a minimal KEY=VALUE .env, trimming quotes/whitespace."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip().strip("'\"").strip()
    return out


def _mac_screenshot_dir() -> Path:
    """Where macOS writes screenshots (defaults to ~/Desktop)."""
    try:
        out = subprocess.run(
            ["defaults", "read", "com.apple.screencapture", "location"],
            capture_output=True, text=True, timeout=5,
        )
        loc = out.stdout.strip()
        if loc:
            return Path(loc).expanduser()
    except Exception:
        pass
    return Path.home() / "Desktop"


@dataclass
class Config:
    api_key: str = ""
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    screenshot_dir: Path = field(default_factory=_mac_screenshot_dir)
    traces_dir: Path = TRACES_DIR
    data_dir: Path = DATA_DIR
    holo_bin: Path = HOLO_BIN
    # Time budget for the experimental --cua background run (seconds).
    max_time_s: float = 180.0
    # Poll cadence for the screenshot watcher (seconds).
    poll_interval: float = 1.0

    @classmethod
    def load(cls) -> "Config":
        dotenv = _read_dotenv(HOLO_ENV)
        api_key = (
            os.environ.get("HAI_API_KEY")
            or dotenv.get("HAI_API_KEY")
            or ""
        )
        base_url = (
            os.environ.get("HAI_BASE_URL")
            or dotenv.get("HAI_BASE_URL")
            or DEFAULT_BASE_URL
        ).rstrip("/")
        cfg = cls(
            api_key=api_key,
            base_url=base_url,
            model=os.environ.get("SNAPCAL_MODEL", DEFAULT_MODEL),
        )
        if os.environ.get("SNAPCAL_SCREENSHOT_DIR"):
            cfg.screenshot_dir = Path(os.environ["SNAPCAL_SCREENSHOT_DIR"]).expanduser()
        cfg.traces_dir.mkdir(parents=True, exist_ok=True)
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        return cfg

    @property
    def has_holo_cli(self) -> bool:
        return self.holo_bin.exists()

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)
