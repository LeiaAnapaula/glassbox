"""Best-effort 'was a browser frontmost' hint.

Filename alone cannot prove a screenshot came from a browser, so we record the
frontmost app at the moment the file is detected and treat a known browser as a
best-effort provenance signal. This is explicitly not proof of origin.
"""

from __future__ import annotations

import subprocess

BROWSER_HINTS = (
    "safari", "chrome", "arc", "firefox", "brave", "edge", "opera",
    "vivaldi", "chromium", "orion", "zen",
)


def _lsappinfo(field: str, asn: str) -> str:
    try:
        out = subprocess.run(
            ["lsappinfo", "info", "-only", field, asn],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return ""
    # Output looks like: "CFBundleIdentifier"="com.brave.Browser"
    text = out.stdout.strip()
    if "=" in text:
        value = text.split("=", 1)[1].strip().strip('"')
        return "" if value in ("(null)", "") else value
    return ""


def frontmost_app_info() -> tuple[str, str]:
    """Return the frontmost application's (name, bundle_id); "" for parts we can't read.

    Captured at screenshot-detection time, this identifies the browser the user
    was actually in when they took the screenshot — which is where their Google
    session lives and where we should create the event. Uses ``lsappinfo`` (no
    Accessibility/Automation permission required).
    """
    try:
        asn = subprocess.run(
            ["lsappinfo", "front"], capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        return "", ""
    if not asn:
        return "", ""
    name = _lsappinfo("name", asn)
    bundle_id = _lsappinfo("bundleid", asn)
    return name, bundle_id


def frontmost_app() -> str:
    """Return the frontmost application's name, or "" if it can't be read."""
    return frontmost_app_info()[0]


def looks_like_browser(app_name: str) -> bool:
    name = (app_name or "").lower()
    return any(hint in name for hint in BROWSER_HINTS)
