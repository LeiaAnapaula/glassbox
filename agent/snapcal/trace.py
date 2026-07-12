"""Convert a HoloDesktop ``events.jsonl`` run into a Glassbox flight-recorder trace.

The Glassbox viewer (viewer/glassbox.html) ingests one JSON step per line:
    {run_id, step, action:{type,x,y,target_text}, reasoning,
     confidence, latency_ms, screenshot_before, screenshot_after, timestamp}

HoloDesktop emits a richer event stream (message/observation/policy/tool_result/
answer/error) keyed by ``step_parts``. We fold each step's events into one
Glassbox row, embedding observation screenshots as self-contained data URIs and
scaling HoloDesktop's normalized (0..1) click coordinates into the pixel space
the viewer's marker math expects.

Note: HoloDesktop does not emit a calibrated per-step confidence, so we derive a
transparent proxy from execution outcome (error in the step -> low). This is
documented as a heuristic, not a model score.
"""

from __future__ import annotations

import base64
import json
import struct
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def _img_size(raw: bytes) -> Optional[tuple[int, int]]:
    """(width, height) for PNG/JPEG without any image library, else None."""
    if raw[:8] == b"\x89PNG\r\n\x1a\n" and raw[12:16] == b"IHDR":
        w, h = struct.unpack(">II", raw[16:24])
        return w, h
    if raw[:2] == b"\xff\xd8":  # JPEG: walk segments to a start-of-frame marker
        i = 2
        n = len(raw)
        while i + 9 < n:
            if raw[i] != 0xFF:
                i += 1
                continue
            marker = raw[i + 1]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", raw[i + 5 : i + 9])
                return w, h
            seg_len = struct.unpack(">H", raw[i + 2 : i + 4])[0]
            i += 2 + seg_len
    return None


def _b64_to_data_uri(source_b64: str) -> tuple[str, Optional[tuple[int, int]]]:
    """HoloDesktop observation image (base64 jpeg) -> data URI + pixel size."""
    try:
        raw = base64.b64decode(source_b64)
    except Exception:
        return "", None
    size = _img_size(raw)
    return f"data:image/jpeg;base64,{source_b64}", size


def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _action_from_tool(tool_name: str, args: dict[str, Any],
                      size: Optional[tuple[int, int]]) -> dict[str, Any]:
    """Map a HoloDesktop tool call to a Glassbox action {type,x,y,target_text}."""
    action: dict[str, Any] = {"type": tool_name}
    # Normalized (0..1) coords -> pixels for the viewer's marker overlay.
    x, y = args.get("x"), args.get("y")
    if isinstance(x, (int, float)) and isinstance(y, (int, float)) and size:
        w, h = size
        if 0 <= x <= 1 and 0 <= y <= 1:
            action["x"], action["y"] = round(x * w), round(y * h)
        else:
            action["x"], action["y"] = round(x), round(y)
    target = None
    if tool_name == "hotkey_desktop":
        target = "+".join(args.get("keys", []))
    elif tool_name == "write_desktop":
        target = args.get("content")
    elif tool_name == "click_desktop":
        target = args.get("element")
    elif tool_name == "answer":
        target = "(final answer)"
    if target:
        action["target_text"] = str(target)[:120]
    return action


def convert(events_path: Path, run_label: str) -> list[dict[str, Any]]:
    """Read events.jsonl and return an ordered list of Glassbox step rows."""
    # Group events by step number.
    by_step: dict[int, dict[str, Any]] = {}
    order: list[int] = []
    for line in events_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        step_parts = rec.get("step_parts") or [0]
        step = step_parts[0] if step_parts else 0
        bucket = by_step.get(step)
        if bucket is None:
            bucket = by_step[step] = {"ts": rec.get("ts"), "events": []}
            order.append(step)
        bucket["events"].append(rec.get("event", {}))

    order.sort()
    rows: list[dict[str, Any]] = []
    observations: dict[int, tuple[str, Optional[tuple[int, int]]]] = {}

    # First pass: decode each step's observation image (the "before" shot).
    for step in order:
        for ev in by_step[step]["events"]:
            if ev.get("kind") == "observation_event":
                src = (((ev.get("observation") or {}).get("image")) or {}).get("source")
                if src:
                    observations[step] = _b64_to_data_uri(src)
                    break

    for idx, step in enumerate(order):
        bucket = by_step[step]
        events = bucket["events"]
        note = thought = None
        tool_calls: list[dict[str, Any]] = []
        tool_reqs: list[dict[str, Any]] = []
        user_msg = None
        answer = None
        had_error = False

        for ev in events:
            kind = ev.get("kind")
            if kind == "message_event" and ev.get("caller_id") == "user":
                content = ev.get("content") or []
                user_msg = " ".join(str(c) for c in content)
            elif kind == "policy_event":
                raw = (ev.get("message") or {}).get("content")
                try:
                    parsed = json.loads(raw) if isinstance(raw, str) else (raw or {})
                except json.JSONDecodeError:
                    parsed = {}
                note = parsed.get("note")
                thought = parsed.get("thought")
                tool_calls = parsed.get("tool_calls") or []
            elif kind == "tool_result":
                tool_reqs.append(ev.get("tool_req") or {})
            elif kind == "answer_event":
                answer = ev.get("answer")
            elif kind == "error_event":
                had_error = True
                note = note or ev.get("error")

        size = observations.get(step, ("", None))[1]

        # Prefer the actually-executed tool call; fall back to the planned one.
        action = None
        if tool_reqs:
            tr = tool_reqs[-1]
            action = _action_from_tool(tr.get("tool_name", "action"), tr.get("args") or {}, size)
        elif tool_calls:
            tc = dict(tool_calls[-1])
            name = tc.pop("tool_name", "action")
            action = _action_from_tool(name, tc, size)
        elif answer:
            action = {"type": "answer", "target_text": "(final answer)"}

        reasoning = thought or note or user_msg or ("Task complete." if answer else "")
        if user_msg and idx == 0:
            reasoning = f"Task: {user_msg}"

        # Latency = gap until the next step's first event.
        this_ts = _parse_ts(bucket["ts"])
        next_ts = _parse_ts(by_step[order[idx + 1]]["ts"]) if idx + 1 < len(order) else None
        latency_ms = int((next_ts - this_ts).total_seconds() * 1000) if (this_ts and next_ts) else 0

        confidence = 0.4 if had_error else (0.95 if answer else 0.85)

        row: dict[str, Any] = {
            "run_id": run_label,
            "step": step,
            "reasoning": reasoning,
            "action": action,
            "confidence": confidence,
            "latency_ms": max(latency_ms, 0),
            "timestamp": bucket["ts"],
        }
        before = observations.get(step, ("", None))[0]
        after = observations.get(order[idx + 1], ("", None))[0] if idx + 1 < len(order) else ""
        if before:
            row["screenshot_before"] = before
        if after:
            row["screenshot_after"] = after
        rows.append(row)

    return rows


def write_glassbox_trace(events_path: Path, out_path: Path, run_label: str) -> int:
    """Convert and write a .jsonl trace loadable by the Glassbox viewer.

    Returns the number of steps written.
    """
    rows = convert(events_path, run_label)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return len(rows)
