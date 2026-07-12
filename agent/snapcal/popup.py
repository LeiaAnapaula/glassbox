"""Native lower-right confirmation popup (Tkinter).

Instead of redirecting to a browser page, a small borderless card appears in the
bottom-right corner — next to where macOS drops the screenshot thumbnail — the
moment a screenshot is taken. It shows "Analyzing…" immediately (no waiting on a
browser to open), then fills in the extracted event with editable fields and
Add / Dismiss / Not-an-event buttons.

macOS requires all Tk work on the main thread, so the watcher runs on a
background thread and calls these methods, which marshal onto the Tk thread via
``root.after``. Worker threads block on :meth:`wait` for the user's decision.
"""

from __future__ import annotations

import math
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog
from pathlib import Path
from typing import Any, Optional

# snapcal palette.
BG = "#0E1526"
PANEL = "#121A30"
LINE = "#233052"
TEXT = "#E8ECF4"
MUTED = "#8A93A8"
HI = "#2DD4A7"
MID = "#F5A524"
ACCENT = "#6E8BFF"
LO = "#F0564A"
FONT = "Helvetica Neue"


class PopupUI:
    def __init__(self, cfg):
        self.cfg = cfg
        self.root = tk.Tk()
        self.root.withdraw()
        self._win: Optional[tk.Toplevel] = None
        self._entries: dict[str, tk.Entry] = {}
        self._img = None  # keep a reference so Tk doesn't GC the thumbnail
        self._status: Optional[tk.Label] = None
        self._btnbar: Optional[tk.Frame] = None
        self._decision: Optional[tuple[str, dict]] = None
        self._decided = threading.Event()

    # -- lifecycle ---------------------------------------------------------
    def run(self, worker) -> None:
        """Start the watcher on a background thread and run the Tk loop here."""
        threading.Thread(target=worker, daemon=True).start()
        self.root.mainloop()

    def _sched(self, fn) -> None:
        self.root.after(0, fn)

    def quit_soon(self, ms: int) -> None:
        """Stop the Tk loop after `ms` (used by --once so the process exits)."""
        self._sched(lambda: self.root.after(ms, self.root.quit))

    # -- worker-thread API (all thread-safe) -------------------------------
    def begin(self, image_path: Path) -> None:
        """Show the card immediately in 'Analyzing…' state."""
        self._decision = None
        self._decided.clear()
        self._sched(lambda: self._build(image_path))

    def offer(self, candidate: dict) -> None:
        """Fill in the extracted fields and enable the buttons."""
        self._sched(lambda: self._fill(candidate))

    def wait(self) -> tuple[str, dict]:
        self._decided.wait()
        assert self._decision is not None
        return self._decision

    def status(self, text: str) -> None:
        self._sched(lambda: self._set_status(text))

    def result(self, ok: bool, msg: str) -> None:
        self._sched(lambda: self._show_result(ok, msg))

    def added(self, title: str, on_undo, on_send=None) -> None:
        """Show calendar success, Undo, and an optional confirmed WhatsApp action."""
        self._sched(lambda: self._added(title, on_undo, on_send))

    def share_only(self, on_send) -> None:
        """Offer forwarding when the screenshot contains no calendar event."""
        self._sched(lambda: self._share_only(on_send))

    def removed(self) -> None:
        self._sched(self._removed)

    def close_quiet(self) -> None:
        self._sched(self._destroy)

    # -- Tk-thread implementation ------------------------------------------
    def _destroy(self) -> None:
        if self._win is not None:
            self._win.destroy()
            self._win = None

    def _position(self, win: tk.Toplevel) -> None:
        win.update_idletasks()
        w = win.winfo_reqwidth()
        h = win.winfo_reqheight()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = sw - w - 24
        y = sh - h - 96  # sit above the Dock, near the screenshot thumbnail
        win.geometry(f"+{x}+{y}")

    def _build(self, image_path: Path) -> None:
        self._destroy()
        self._entries = {}
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=LINE)  # 1px border effect via padding
        outer = tk.Frame(win, bg=PANEL, padx=16, pady=14)
        outer.pack(padx=1, pady=1)

        header = tk.Frame(outer, bg=PANEL)
        header.pack(fill="x", anchor="w")
        tk.Label(header, text="●", fg=ACCENT, bg=PANEL, font=(FONT, 11)).pack(side="left")
        tk.Label(header, text="  snapcal", fg=TEXT, bg=PANEL,
                 font=(FONT, 13, "bold")).pack(side="left")

        body = tk.Frame(outer, bg=PANEL)
        body.pack(fill="x", pady=(10, 0))

        # Thumbnail (PNG only; Tk can't read jpeg without extras).
        thumb = tk.Frame(body, bg=PANEL)
        thumb.pack(side="left", anchor="n")
        try:
            img = tk.PhotoImage(file=str(image_path))
            factor = max(1, math.ceil(img.width() / 150))
            self._img = img.subsample(factor, factor)
            tk.Label(thumb, image=self._img, bg=PANEL, bd=1, relief="solid").pack()
        except Exception:
            self._img = None
            tk.Label(thumb, text="screenshot", fg=MUTED, bg=PANEL,
                     width=18, height=6, relief="solid", bd=1).pack()

        self._detail = tk.Frame(body, bg=PANEL)
        self._detail.pack(side="left", anchor="n", padx=(14, 0))
        self._status = tk.Label(self._detail, text="Analyzing screenshot…",
                                fg=MUTED, bg=PANEL, font=(FONT, 12))
        self._status.pack(anchor="w")

        self._win = win
        self._position(win)
        win.lift()
        # Borderless macOS windows can start click-shy; force focus so the
        # buttons respond on the first click.
        win.focus_force()
        self.root.after(120, win.focus_force)

    def _field(self, parent, key: str, label: str, value: str) -> None:
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", pady=2)
        tk.Label(row, text=label, fg=MUTED, bg=PANEL, width=7, anchor="w",
                 font=(FONT, 10)).pack(side="left")
        e = tk.Entry(row, bg=BG, fg=TEXT, insertbackground=TEXT,
                     relief="flat", width=26, font=(FONT, 11),
                     highlightthickness=1, highlightbackground=LINE,
                     highlightcolor=ACCENT)
        e.insert(0, value or "")
        e.pack(side="left", ipady=3)
        self._entries[key] = e

    def _fill(self, candidate: dict) -> None:
        if self._win is None:
            return
        kind = candidate.get("kind", "uncertain")
        conf = candidate.get("confidence", 0.0) or 0.0
        color = {"event": HI, "uncertain": MID, "non_event": LO}.get(kind, MID)
        self._status.configure(
            text=f"Event detected  ·  {conf:.0%} confident" if kind != "non_event"
            else "Not an event", fg=color, font=(FONT, 12, "bold"))

        self._field(self._detail, "title", "title", candidate.get("title") or "")
        self._field(self._detail, "start_local", "start", candidate.get("start_local") or "")
        self._field(self._detail, "end_local", "end", candidate.get("end_local") or "")
        self._field(self._detail, "location", "where", candidate.get("location") or "")

        problems = list(candidate.get("missing_fields") or []) + list(candidate.get("ambiguities") or [])
        if problems:
            tk.Label(self._detail, text="⚠ " + "; ".join(problems[:2]), fg=MID, bg=PANEL,
                     font=(FONT, 9), wraplength=240, justify="left").pack(anchor="w", pady=(4, 0))

        # Button bar at the bottom of the outer frame (detail -> body -> outer).
        outer = self._status.master.master.master
        bar = tk.Frame(outer, bg=PANEL)
        bar.pack(fill="x", pady=(12, 0))
        self._btnbar = bar
        self._mk_button(bar, "Add to Calendar", HI, lambda: self._decide("add"), primary=True)
        self._mk_button(bar, "Dismiss", MUTED, lambda: self._decide("dismiss"))
        self._mk_button(bar, "Not an event", LO, lambda: self._decide("not_event"))
        self._position(self._win)

    def _mk_button(self, parent, text: str, color: str, cmd, primary: bool = False) -> None:
        # tk.Button ignores bg on macOS; use a styled clickable Label instead.
        lbl = tk.Label(parent, text=text, fg=(BG if primary else color),
                       bg=(color if primary else PANEL), font=(FONT, 11, "bold"),
                       padx=12, pady=6, cursor="pointinghand",
                       bd=1, relief="solid")
        lbl.configure(highlightbackground=color)
        lbl.pack(side="left", padx=(0, 8))
        lbl.bind("<Button-1>", lambda _e: cmd())

    def _decide(self, action: str) -> None:
        fields = {k: (e.get().strip() or None) for k, e in self._entries.items()}
        self._decision = (action, fields)
        if action == "add":
            self._set_status("Creating the event in your browser…")
            if self._btnbar is not None:
                self._btnbar.destroy()
                self._btnbar = None
        else:
            self._destroy()
        self._decided.set()

    def _set_status(self, text: str) -> None:
        if self._status is not None and self._win is not None:
            self._status.configure(text=text, fg=MUTED, font=(FONT, 12))

    def _show_result(self, ok: bool, msg: str) -> None:
        if self._win is None:
            return
        if self._status is not None:
            self._status.configure(text=("✓ Action completed" if ok else "✕ " + msg),
                                   fg=(HI if ok else LO), font=(FONT, 12, "bold"))
        # auto-dismiss shortly after
        self.root.after(4000, self._destroy)

    def _added(self, title: str, on_undo, on_send=None) -> None:
        if self._win is None or self._status is None:
            return
        self._status.configure(text=f"✓ Added  ·  {title}", fg=HI, font=(FONT, 12, "bold"))
        outer = self._status.master.master.master
        bar = tk.Frame(outer, bg=PANEL)
        bar.pack(fill="x", pady=(10, 0))
        self._btnbar = bar
        self._mk_button(bar, "Undo", LO, lambda: self._do_undo(on_undo))
        if on_send is not None:
            self._mk_button(bar, "Send to WhatsApp…", ACCENT,
                            lambda: self._confirm_whatsapp(on_send))
        self._position(self._win)
        self._autoclose = self.root.after(9000, self._destroy)

    def _share_only(self, on_send) -> None:
        if self._win is None or self._status is None:
            return
        self._status.configure(text="No calendar event detected", fg=MUTED,
                               font=(FONT, 12, "bold"))
        outer = self._status.master.master.master
        bar = tk.Frame(outer, bg=PANEL)
        bar.pack(fill="x", pady=(10, 0))
        self._btnbar = bar
        self._mk_button(bar, "Send to WhatsApp…", ACCENT,
                        lambda: self._confirm_whatsapp(on_send), primary=True)
        self._mk_button(bar, "Dismiss", MUTED, self._destroy)
        self._position(self._win)
        self._autoclose = self.root.after(12000, self._destroy)

    def _confirm_whatsapp(self, on_send) -> None:
        """Collect the destination and confirm immediately before the real send."""
        if getattr(self, "_autoclose", None):
            self.root.after_cancel(self._autoclose)
            self._autoclose = None
        contact = simpledialog.askstring(
            "Send screenshot to WhatsApp", "Exact WhatsApp contact name:",
            parent=self._win,
        )
        if not contact or not contact.strip():
            self._autoclose = self.root.after(9000, self._destroy)
            return
        contact = contact.strip()
        confirmed = messagebox.askyesno(
            "Confirm WhatsApp send",
            f"Send this screenshot to {contact}?\n\n"
            "HoloDesktop will operate WhatsApp and send the image. This cannot be undone here.",
            parent=self._win,
        )
        if not confirmed:
            self._autoclose = self.root.after(9000, self._destroy)
            return
        self._set_status(f"Sending screenshot to {contact}…")
        if self._btnbar is not None:
            self._btnbar.destroy()
            self._btnbar = None
        threading.Thread(target=lambda: on_send(contact), daemon=True).start()

    def _do_undo(self, on_undo) -> None:
        if getattr(self, "_autoclose", None):
            self.root.after_cancel(self._autoclose)
        self._set_status("Removing from calendar…")
        if self._btnbar is not None:
            self._btnbar.destroy()
            self._btnbar = None
        threading.Thread(target=on_undo, daemon=True).start()

    def _removed(self) -> None:
        if self._status is not None and self._win is not None:
            self._status.configure(text="Removed from calendar", fg=MUTED, font=(FONT, 12))
        self.root.after(2500, self._destroy)
