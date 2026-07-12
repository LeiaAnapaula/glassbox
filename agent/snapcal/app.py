"""Orchestrator: screenshot -> extract -> book -> notify.

Owns the product workflow. Holo3.1 reads the screenshot (one image request);
the Google Calendar API books the event (reliable, zero-click). Detection,
dedupe, validation, and outcome memory live here. A small lower-right toast
confirms with an Undo (a real API delete).

The confirmation UI is a native lower-right popup (see popup.py). Because macOS
requires Tk on the main thread, the watch/extract/book work runs on a background
worker thread while the Tk event loop owns the main thread.

`--cua` swaps the API booking for the experimental background computer-use path
(HoloDesktop drives the browser window-bound; see holo_mcp.py).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import gcal
from .config import Config
from .frontmost import frontmost_app_info, looks_like_browser
from .model_client import RealModelClient
from .popup import PopupUI
from .prefs import Prefs
from .watcher import SeenStore, watch_new_screenshots


def _log(msg: str) -> None:
    print(f"[snapcal] {msg}", flush=True)


def _book_via_cua(cfg: Config, candidate, browser_bundle_id, ui: PopupUI) -> None:
    """Experimental: create the event with the background window-bound CUA."""
    from .holo_desktop import create_event_background
    result = create_event_background(cfg, candidate, browser_bundle_id=browser_bundle_id)
    if result.ok:
        ui.result(True, "")
        _log(f"CUA created event. trace: {result.trace_path}")
    else:
        ui.result(False, (result.error or "could not confirm")[:60])
        _log(f"CUA could not confirm: {result.error[:200]}")


def process_one(cfg: Config, ui: PopupUI, prefs: Prefs, client: RealModelClient,
                image_path: Path, *, use_cua: bool) -> None:
    _log(f"screenshot: {image_path.name}")
    fm, fm_bundle = frontmost_app_info()
    is_browser = looks_like_browser(fm)
    origin = f"{fm}{' (browser)' if is_browser else ''}" if fm else "unknown"
    browser_bundle_id = fm_bundle if (is_browser and fm_bundle) else None

    ui.begin(image_path)  # show the card immediately; no wait on the model call

    try:
        candidate = client.extract(image_path)
    except Exception as e:
        _log(f"extraction failed: {e}")
        ui.result(False, "extraction failed")
        return

    _log(f"kind={candidate.kind} confidence={candidate.confidence:.2f} title={candidate.title!r} from {origin}")
    if candidate.kind == "non_event":
        _log("not an event — dismissing.")
        ui.close_quiet()
        return

    title = candidate.title or "event"
    ui.status(f"Adding ‘{title}’ to your calendar…")

    if use_cua:
        _book_via_cua(cfg, candidate, browser_bundle_id, ui)
        prefs.record("add", confidence=candidate.confidence, frontmost=fm)
        return

    book = gcal.create_event(cfg, candidate)
    if book.ok:
        prefs.record("add", confidence=candidate.confidence, frontmost=fm)
        _log(f"added to Google Calendar: {book.html_link}")
        ui.added(title, on_undo=lambda: _undo(cfg, book.event_id, ui))
    else:
        _log(f"could not add: {book.error}")
        ui.result(False, book.error[:80])


def _undo(cfg: Config, event_id: str, ui: PopupUI) -> None:
    ok = gcal.delete_event(cfg, event_id)
    _log("undo: removed event" if ok else "undo: delete failed")
    ui.removed()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="snapcal",
        description="Screenshot -> Google Calendar agent (Holo3.1 + Calendar API).")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--watch", action="store_true",
                      help="Watch the macOS screenshot folder (default).")
    mode.add_argument("--once", metavar="IMAGE", help="Process a single screenshot and exit.")
    ap.add_argument("--cua", action="store_true",
                    help="Experimental: book via the background computer-use agent "
                         "instead of the Calendar API.")
    args = ap.parse_args(argv)

    cfg = Config.load()
    if not cfg.has_api_key:
        _log("No HAI_API_KEY found (checked $HAI_API_KEY and ~/.holo/.env). Run `holo login`.")
        return 2

    client = RealModelClient(cfg)
    prefs = Prefs(cfg)
    ui = PopupUI(cfg)

    def worker() -> None:
        if args.once:
            path = Path(args.once).expanduser()
            if not path.exists():
                _log(f"no such file: {path}")
            else:
                process_one(cfg, ui, prefs, client, path, use_cua=args.cua)
            ui.quit_soon(9500)
            return
        _log(f"watching {cfg.screenshot_dir} — take a screenshot of an event…")
        seen = SeenStore(cfg)
        for image_path in watch_new_screenshots(cfg, seen):
            process_one(cfg, ui, prefs, client, image_path, use_cua=args.cua)
            _log(f"watching {cfg.screenshot_dir} …")

    ui.run(worker)
    return 0


if __name__ == "__main__":
    sys.exit(main())
