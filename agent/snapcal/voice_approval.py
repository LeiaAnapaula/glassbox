"""Strict Gradium-spoken, click-confirmed gate for irreversible actions."""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
from pathlib import Path


DEFAULT_VOICE_ID = "YTpq7expH9539ERJ"  # documented Gradium example voice


def _synthesise(prompt: str) -> bytes:
    """Return Gradium WAV audio; raise on missing config or any API failure."""
    if not os.environ.get("GRADIUM_API_KEY"):
        raise RuntimeError("GRADIUM_API_KEY is required; irreversible action blocked")
    try:
        import gradium
    except ImportError as exc:
        raise RuntimeError("Gradium SDK is not installed; irreversible action blocked") from exc

    async def run() -> bytes:
        client = gradium.client.GradiumClient(api_key=os.environ["GRADIUM_API_KEY"])
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
    from tkinter import messagebox

    audio = _synthesise(prompt)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        path = Path(handle.name)
        handle.write(audio)
    try:
        subprocess.run(["/usr/bin/afplay", str(path)], check=True, timeout=30)
    finally:
        path.unlink(missing_ok=True)

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return bool(messagebox.askyesno(
            title,
            prompt + "\n\nClick Yes to approve or No to block.",
            parent=root,
            icon="warning",
        ))
    finally:
        root.destroy()
