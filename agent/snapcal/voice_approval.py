"""Strict Gradium-spoken, click-confirmed gate for irreversible actions."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
from pathlib import Path


DEFAULT_VOICE_ID = "YTpq7expH9539ERJ"  # documented Gradium example voice


def _gradium_key() -> str:
    key = os.environ.get("GRADIUM_API_KEY", "").strip()
    if key:
        return key
    env_file = Path.home() / ".holo" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() == "GRADIUM_API_KEY":
                return value.strip().strip("'\"")
    return ""


def _synthesise(prompt: str) -> bytes:
    """Return Gradium WAV audio; raise on missing config or any API failure."""
    api_key = _gradium_key()
    if not api_key:
        raise RuntimeError("GRADIUM_API_KEY is required; irreversible action blocked")
    try:
        import gradium
    except ImportError as exc:
        raise RuntimeError("Gradium SDK is not installed; irreversible action blocked") from exc

    async def run() -> bytes:
        client = gradium.client.GradiumClient(api_key=api_key)
        result = await client.tts(
            setup={
                "model_name": "default",
                "voice_id": os.environ.get("GRADIUM_VOICE_ID", DEFAULT_VOICE_ID),
                "output_format": "wav",
            },
            text=prompt,
        )
        return bytes(result.raw_data)

    audio = asyncio.run(run())
    if not audio:
        raise RuntimeError("Gradium returned no audio; irreversible action blocked")
    return audio


def approve(prompt: str, *, title: str = "Irreversible action") -> bool:
    """Speak with Gradium, then accept an explicit computer click: Yes or No."""
    import tkinter as tk

    audio = _synthesise(prompt)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        path = Path(handle.name)
        handle.write(audio)
    try:
        subprocess.run(["/usr/bin/afplay", str(path)], check=True, timeout=30)
    finally:
        path.unlink(missing_ok=True)

    decision = {"approved": False}
    root = tk.Tk()
    root.title(title)
    root.attributes("-topmost", True)
    root.resizable(False, False)
    frame = tk.Frame(root, padx=28, pady=22)
    frame.pack()
    tk.Label(frame, text="Human approval required", font=("Helvetica", 18, "bold")).pack(pady=(0, 10))
    tk.Label(frame, text=prompt, wraplength=520, justify="center").pack(pady=(0, 18))
    buttons = tk.Frame(frame)
    buttons.pack()

    def pick(value: bool) -> None:
        decision["approved"] = value
        # Remove the window before returning control to the CUA commit path.
        root.grab_release()
        root.withdraw()
        root.update_idletasks()
        root.destroy()

    tk.Button(buttons, text="Yes — approve", width=20, command=lambda: pick(True)).grid(row=0, column=0, padx=6)
    tk.Button(buttons, text="No — block", width=20, command=lambda: pick(False)).grid(row=0, column=1, padx=6)
    root.protocol("WM_DELETE_WINDOW", lambda: pick(False))
    root.eval("tk::PlaceWindow . center")
    root.grab_set()
    root.focus_force()
    root.mainloop()
    return bool(decision["approved"])


def notify_decision(approved: bool, action: str) -> None:
    """Immediate, non-focus-stealing feedback while the commit CUA starts."""
    if approved:
        message = f"Approved — CUA is {action} now. This may take several seconds."
    else:
        message = "Blocked — nothing will happen."
    print(f"[approval] {message}", flush=True)
    script = f'display notification {json.dumps(message)} with title "Glassbox approval"'
    subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True)
