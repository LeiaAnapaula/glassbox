"""Dependency-free screenshot watcher.

Reacts only to genuine macOS screen captures (Cmd-Shift-4 / Cmd-Shift-3), not
to arbitrary images that happen to land in the folder. A real screen capture
carries the Spotlight attribute ``kMDItemIsScreenCapture=1``; a downloaded or
dragged-in PNG does not. We poll the configured screenshot folder, wait until
each new file's size is stable (so we don't read a half-written PNG), confirm it
is a screen capture, and de-duplicate by content hash. A poller (rather than
watchdog) keeps this zero-install and robust across Python versions.
"""

from __future__ import annotations

import hashlib
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

from .config import Config

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
# Filename fallback for the brief window before Spotlight indexes a new capture.
# Covers the current default ("Screenshot ...") and the legacy ("Screen Shot ...").
SCREENSHOT_NAME_PREFIXES = ("Screenshot", "Screen Shot")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _configured_prefix() -> str | None:
    """The user's custom screenshot filename prefix, if they set one."""
    try:
        out = subprocess.run(
            ["defaults", "read", "com.apple.screencapture", "name"],
            capture_output=True, text=True, timeout=5,
        )
        name = out.stdout.strip()
        return name or None
    except Exception:
        return None


def is_screen_capture(path: Path) -> bool:
    """True if the file is a genuine macOS screen capture.

    Primary signal is the ``kMDItemIsScreenCapture`` Spotlight attribute; when
    that isn't indexed yet (a just-written file), fall back to the screenshot
    filename prefix so we don't miss the capture the user just took.
    """
    try:
        out = subprocess.run(
            ["mdls", "-raw", "-name", "kMDItemIsScreenCapture", str(path)],
            capture_output=True, text=True, timeout=5,
        )
        value = out.stdout.strip()
    except Exception:
        value = ""
    if value == "1":
        return True
    if value in ("0",):
        return False
    # value == "(null)" or unreadable -> not indexed yet; use the name prefix.
    prefixes = list(SCREENSHOT_NAME_PREFIXES)
    custom = _configured_prefix()
    if custom:
        prefixes.append(custom)
    return path.name.startswith(tuple(prefixes))


class SeenStore:
    """Remembers content hashes we've already processed, across restarts."""

    def __init__(self, cfg: Config):
        self.path = cfg.data_dir / "seen_hashes.txt"
        self._seen: set[str] = set()
        if self.path.exists():
            self._seen = set(self.path.read_text().split())

    def __contains__(self, digest: str) -> bool:
        return digest in self._seen

    def add(self, digest: str) -> None:
        if digest not in self._seen:
            self._seen.add(digest)
            with self.path.open("a") as f:
                f.write(digest + "\n")


def _is_stable(path: Path, settle: float = 0.4) -> bool:
    """True once the file size stops changing (finished writing)."""
    try:
        first = path.stat().st_size
    except OSError:
        return False
    time.sleep(settle)
    try:
        return first == path.stat().st_size and first > 0
    except OSError:
        return False


def watch_new_screenshots(cfg: Config, seen: SeenStore) -> Iterator[Path]:
    """Yield each new, fully-written, not-seen-before screenshot as it appears."""
    start = time.time()
    known_mtimes: dict[Path, float] = {}
    # Seed with existing files so we only react to genuinely new ones.
    for p in _images(cfg.screenshot_dir):
        known_mtimes[p] = p.stat().st_mtime

    while True:
        for path in _images(cfg.screenshot_dir):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if known_mtimes.get(path) == mtime:
                continue
            known_mtimes[path] = mtime
            if mtime < start - 1:
                continue  # pre-existing file touched; ignore
            if not _is_stable(path):
                known_mtimes.pop(path, None)  # revisit next tick
                continue
            if not is_screen_capture(path):
                continue  # a dragged-in / downloaded image, not a screen capture
            digest = sha256_file(path)
            if digest in seen:
                continue
            seen.add(digest)
            yield path
        time.sleep(cfg.poll_interval)


def _images(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return [
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES and not p.name.startswith(".")
    ]
