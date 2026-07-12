"""Minimal MCP stdio client for HoloDesktop's background window-bound agent.

`holo mcp` exposes a single tool, ``holo_desktop(task) -> {result}``, which binds
to ONE OS window and drives it via Holo3 in the background — synthesized clicks
go only to that window, the user's real cursor and other apps are untouched.
This is the mode the agent uses to create calendar events without hijacking the
screen (unlike `holo run`, which controls the visible desktop).

We speak newline-delimited JSON-RPC over the process's stdio. Responses are read
raw (non-blocking) and split on newlines, because the server does not always
terminate a message with a newline immediately.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import time
from pathlib import Path
from typing import Any, Optional


class HoloMCPError(RuntimeError):
    pass


class HoloMCP:
    def __init__(self, holo_bin: Path):
        self._proc = subprocess.Popen(
            [str(holo_bin), "mcp"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        os.set_blocking(self._proc.stdout.fileno(), False)
        self._buf = b""
        self._next_id = 1
        self._initialize()

    # -- JSON-RPC plumbing -------------------------------------------------
    def _send(self, obj: dict) -> None:
        self._proc.stdin.write((json.dumps(obj) + "\n").encode())
        self._proc.stdin.flush()

    def _notify(self, method: str, params: dict | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _await_id(self, want_id: int, timeout_s: float) -> dict:
        """Read until the response with `want_id` arrives; return its full envelope."""
        end = time.time() + timeout_s
        while time.time() < end:
            if self._proc.poll() is not None:
                raise HoloMCPError("holo mcp process exited unexpectedly")
            r, _, _ = select.select([self._proc.stdout], [], [], 1.0)
            if not r:
                continue
            chunk = self._proc.stdout.read(65536)
            if not chunk:
                continue
            self._buf += chunk
            while b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("id") == want_id:
                    if "error" in msg:
                        raise HoloMCPError(str(msg["error"]))
                    return msg.get("result", {})
        raise TimeoutError(f"no MCP response for id={want_id} within {timeout_s}s")

    def _request(self, method: str, params: dict, timeout_s: float) -> dict:
        req_id = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        return self._await_id(req_id, timeout_s)

    def _initialize(self) -> None:
        self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "glassbox", "version": "0.1"},
        }, timeout_s=60)
        self._notify("notifications/initialized")

    # -- public API --------------------------------------------------------
    def run_task(self, task: str, timeout_s: float = 300.0) -> str:
        """Run one background window-bound desktop task; return its text result."""
        result = self._request(
            "tools/call",
            {"name": "holo_desktop", "arguments": {"task": task}},
            timeout_s=timeout_s,
        )
        structured = result.get("structuredContent") or {}
        if "result" in structured:
            return str(structured["result"])
        for block in result.get("content", []):
            if block.get("type") == "text":
                return str(block.get("text", ""))
        return ""

    def close(self) -> None:
        try:
            self._proc.terminate()
        except Exception:
            pass
