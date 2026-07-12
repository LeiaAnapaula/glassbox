"""Experimental `--cua` path: create the event via HoloDesktop, not the API.

The reliable default is the Google Calendar API (see gcal.py). This module is the
opt-in computer-use alternative: it opens a prefilled Google Calendar editor in
the user's browser, then hands a bounded task to HoloDesktop's *background*
window-bound agent (holo_mcp.py) to verify the fields and click Save. Clicks go
to the bound window only, so the user's cursor and other apps are untouched. The
run is converted to a Glassbox flight-recorder trace (trace.py).

Google Calendar's web Save step is genuinely hard to automate reliably, which is
why this is experimental and the API path is the default.
"""

from __future__ import annotations

import subprocess
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .config import Config, HOLO_HOME
from .schema import EventCandidate
from .trace import write_glassbox_trace


@dataclass
class RunResult:
    ok: bool
    run_id: str
    events_path: Optional[Path]
    trace_path: Optional[Path]
    steps: int
    answer: str
    error: str


def _default_browser_bundle_id() -> Optional[str]:
    """The bundle id of the user's default browser (https handler), or None.

    We create the event in whatever browser the user actually uses — that's
    where their Google session already lives — rather than forcing a specific one.
    """
    import plistlib
    plist = Path.home() / "Library/Preferences/com.apple.LaunchServices/com.apple.launchservices.secure.plist"
    try:
        with plist.open("rb") as f:
            data = plistlib.load(f)
    except Exception:
        return None
    for handler in data.get("LSHandlers", []):
        if handler.get("LSHandlerURLScheme") == "https":
            return handler.get("LSHandlerRoleAll")
    return None


def _gcal_stamp(iso_local: str) -> Optional[str]:
    """'2026-07-15T15:00' -> '20260715T150000' (Google Calendar wall-clock form)."""
    try:
        dt = datetime.fromisoformat(iso_local)
    except ValueError:
        return None
    return dt.strftime("%Y%m%dT%H%M%S")


def google_calendar_url(candidate: EventCandidate) -> str:
    """Build a prefilled Google Calendar event-creation URL.

    Using the `render?action=TEMPLATE` deep link means we control the field
    parsing; the browser opens straight into the event editor with everything
    filled, so HoloDesktop only has to verify and click Save.
    """
    params: list[tuple[str, str]] = [
        ("action", "TEMPLATE"),
        ("text", candidate.title or "Untitled event"),
    ]
    start = _gcal_stamp(candidate.start_local) if candidate.start_local else None
    end = _gcal_stamp(candidate.end_local) if candidate.end_local else None
    if start and not end:
        try:  # default to a 1-hour block when only a start is known
            end = (datetime.fromisoformat(candidate.start_local) + timedelta(hours=1)).strftime("%Y%m%dT%H%M%S")
        except ValueError:
            end = None
    if start and end:
        params.append(("dates", f"{start}/{end}"))
    if candidate.timezone:
        params.append(("ctz", candidate.timezone))
    if candidate.location:
        params.append(("location", candidate.location))
    if candidate.source_text:
        params.append(("details", f"Captured by snapcal from a screenshot:\n{candidate.source_text}"))
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"https://calendar.google.com/calendar/render?{query}"


def build_task(candidate: EventCandidate) -> str:
    """Turn a confirmed EventCandidate into a precise HoloDesktop task string.

    The app has already opened the prefilled Google Calendar event editor in the
    default browser, so Holo only has to verify the fields and click Save — the
    part that genuinely needs vision. No invitees. Surfaces success/failure.
    """
    url = google_calendar_url(candidate)
    title = candidate.title or "Untitled event"
    when = candidate.start_local or "the shown time"
    loc = f' at "{candidate.location}"' if candidate.location else ""
    parts = [
        "The frontmost app is the user's web browser, already showing Google "
        "Calendar's new-event editor, pre-filled from a screenshot. Stay in that "
        "browser — do not open or switch to any other app or browser. Verify the "
        f'editor shows an event titled "{title}" starting {when}{loc}.',
        "If instead a Google sign-in page or an empty calendar is shown, briefly "
        "wait for it to load; if it still is not the pre-filled editor, click the "
        f"address bar and go to this exact URL, then continue:\n{url}\n",
        'First clear anything covering the Save button: if a "Stay organized '
        'with Google Calendar in Chrome" banner or popup is shown, dismiss it '
        '(click "Don\'t switch" or its X); if any macOS or Claude system dialog '
        "asks to install a helper or for credentials, click Cancel. Do NOT add "
        "any guests or invitees, and leave the calendar as the user's primary "
        'calendar. Then click the blue "Save" button at the top-left of the '
        "event editor (if a normal click does not register, try pressing Enter "
        "while the title field is focused). After saving, the editor should close "
        "and the event should appear on the calendar grid — confirm this and "
        "report clearly whether it was actually saved.",
    ]
    return " ".join(parts)


_FAILURE_MARKERS = (
    "status: failed", "could not be completed", "was not created",
    "were not created", "unable to", "failed to create", "not created",
    "could not create", "task failed", "not completed successfully",
    "not completed", "was not saved", "not saved", "remains unsaved",
    "does not appear", "did not appear", "never successfully", "not be saved",
    "was never saved", "could not save",
)


def _answer_indicates_failure(answer: str) -> bool:
    low = answer.lower()
    return any(m in low for m in _FAILURE_MARKERS)


def _newest_run_dir(runs_dir: Path, before: set[str]) -> Optional[Path]:
    if not runs_dir.exists():
        return None
    after = {p.name for p in runs_dir.iterdir() if p.is_dir()}
    new = sorted(after - before)
    if new:
        return runs_dir / new[-1]
    # No new dir (e.g. reused); fall back to most-recently modified.
    dirs = [p for p in runs_dir.iterdir() if p.is_dir()]
    return max(dirs, key=lambda p: p.stat().st_mtime, default=None)


def create_event_background(cfg: Config, candidate: EventCandidate, *,
                            browser_bundle_id: Optional[str] = None) -> RunResult:
    """Experimental: create the event via the background window-bound CUA (holo mcp).

    Opens the prefilled editor in the user's browser, then hands a bounded task
    to HoloDesktop's background agent — clicks go to that window only, the user's
    cursor is untouched. Converts the resulting run to a Glassbox trace.
    """
    from .holo_mcp import HoloMCP

    url = google_calendar_url(candidate)
    bid = browser_bundle_id or _default_browser_bundle_id()
    if bid:
        subprocess.run(["open", "-b", bid, url], capture_output=True)
    else:
        subprocess.run(["open", url], capture_output=True)
    time.sleep(4)

    runs_dir = HOLO_HOME / "runs"
    before = {p.name for p in runs_dir.iterdir() if p.is_dir()} if runs_dir.exists() else set()

    mcp = HoloMCP(cfg.holo_bin)
    try:
        answer = mcp.run_task(build_task(candidate), timeout_s=cfg.max_time_s)
    except Exception as e:
        return RunResult(False, "", None, None, 0, "", f"background CUA error: {e}")
    finally:
        mcp.close()

    run_dir = _newest_run_dir(runs_dir, before)
    trace_path = None
    steps = 0
    events_path = None
    if run_dir is not None and (run_dir / "events.jsonl").exists():
        events_path = run_dir / "events.jsonl"
        label = f"calendar-{time.strftime('%Y%m%d-%H%M%S')}"
        trace_path = cfg.traces_dir / f"{label}.jsonl"
        steps = write_glassbox_trace(events_path, trace_path, label)

    failed = _answer_indicates_failure(answer) if answer else True
    ok = bool(answer) and not failed
    error = "" if ok else "Holo reported the event was not created (see report)."
    return RunResult(ok, run_dir.name if run_dir else "", events_path, trace_path, steps, answer, error)
