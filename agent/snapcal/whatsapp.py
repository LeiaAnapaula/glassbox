"""Explicitly confirmed screenshot forwarding through WhatsApp Desktop."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .holo_mcp import HoloMCP


@dataclass
class SendResult:
    ok: bool
    answer: str
    error: str = ""


_FAILURE_MARKERS = (
    "unable to", "could not", "did not send", "was not sent", "not sent",
    "failed to send", "send failed", "couldn't send", "cannot send",
    "can't send", "not completed", "task failed", "not logged in",
    "contact was not found", "could not find",
)
_SUCCESS_MARKERS = (
    "successfully sent", "sent successfully", "screenshot was sent",
    "image was sent", "attachment was sent", "confirmed sent",
)


def answer_confirms_send(answer: str) -> bool:
    """Require affirmative evidence and reject reports containing failure text."""
    low = " ".join(answer.lower().split())
    if not low or any(marker in low for marker in _FAILURE_MARKERS):
        return False
    return any(marker in low for marker in _SUCCESS_MARKERS)


def build_task(image_path: Path, contact: str) -> str:
    """Build a narrow task with user-controlled values represented as JSON strings."""
    safe_contact = json.dumps(contact, ensure_ascii=True)
    safe_path = json.dumps(str(image_path.resolve()), ensure_ascii=True)
    return (
        "The bound window is WhatsApp Desktop. Stay only in WhatsApp and do not "
        "open or switch to another messaging app. Search for the contact whose "
        f"exact displayed name is {safe_contact}. If there are multiple matches, "
        "if the exact match is unavailable, or if WhatsApp is not logged in, stop "
        "without sending and report the problem. Open that exact conversation, "
        f"attach the existing image file at {safe_path}, and send exactly that "
        "image with no caption or additional message. Do not send to a group unless "
        "the displayed name explicitly identifies a group. After clicking Send, "
        "verify the image appears as the newest outgoing message in that exact "
        "conversation. End with 'Successfully sent' only after visual verification, "
        "or 'Not sent' followed by the reason. Never claim success merely because "
        "the file picker closed."
    )


def send_screenshot(cfg: Config, image_path: Path, contact: str) -> SendResult:
    """Open WhatsApp and run one bounded background HoloDesktop task."""
    image_path = image_path.expanduser().resolve()
    contact = contact.strip()
    if not image_path.is_file():
        return SendResult(False, "", "Screenshot file no longer exists.")
    if not contact:
        return SendResult(False, "", "A contact name is required.")
    if not cfg.has_holo_cli:
        return SendResult(False, "", "HoloDesktop CLI is not installed.")

    opened = subprocess.run(
        ["open", "-a", "WhatsApp"], capture_output=True, text=True, timeout=15,
    )
    if opened.returncode != 0:
        return SendResult(False, "", "WhatsApp Desktop could not be opened.")
    time.sleep(2)

    mcp = HoloMCP(cfg.holo_bin)
    try:
        answer = mcp.run_task(build_task(image_path, contact), timeout_s=cfg.max_time_s)
    except Exception as exc:
        return SendResult(False, "", f"WhatsApp computer-use error: {exc}")
    finally:
        mcp.close()

    if answer_confirms_send(answer):
        return SendResult(True, answer)
    return SendResult(False, answer, "HoloDesktop did not verify that the screenshot was sent.")
