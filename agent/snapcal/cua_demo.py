"""Real-CUA demo for the three-way screenshot action router.

Holo3.1 routes a screenshot to Calendar, WhatsApp, or Glassbox Review. A real
foreground HoloDesktop run then narrates and opens the selected destination.
Consequential actions remain human-controlled and the run becomes a Glassbox
trace. The safeguarding route is synthetic-only in this hackathon prototype.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import Config, HOLO_HOME
from .holo_desktop import google_calendar_url
from .model_client import RealModelClient
from .schema import EventCandidate
from .trace import write_glassbox_trace
from .triage_app import _verify_synthetic
from .triage_model import TriageModelClient
from .triage_schema import ObservableStatement, TriageCandidate


@dataclass
class DemoRoute:
    name: str
    summary: str
    event: Optional[EventCandidate] = None
    triage: Optional[TriageCandidate] = None


def _looks_like_concerning_recruitment(text: str) -> bool:
    """Conservative routing hint, never a trafficking determination."""
    low = " ".join((text or "").lower().split())
    groups = [
        ("adult modeling", "webcam model", "adult model"),
        ("per week", "$4,000", "4000 a week", "make $"),
        ("no experience", "no followers"),
        ("seeking women", "trans women"),
    ]
    return sum(any(term in low for term in group) for group in groups) >= 2


def _context_review(source_text: str, confidence: float) -> TriageCandidate:
    return TriageCandidate(
        kind="insufficient_context",
        confidence=confidence,
        summary="Recruitment claims need trained human review; the screenshot alone proves nothing.",
        observable_statements=[ObservableStatement(
            category="other",
            quote=(source_text or "Recruitment advertisement visible in screenshot")[:700],
            explanation="Visible recruitment language preserved for human review.",
        )],
        missing_context=[
            "Employer identity and legitimacy are unverified",
            "Consent, working conditions, and surrounding context are unknown",
        ],
        limitations=["Routing to review is not a trafficking determination."],
    )


def classify(image: Path, cfg: Config) -> DemoRoute:
    """Choose exactly one product route without performing its action."""
    event = RealModelClient(cfg).extract(image)
    if event.kind == "event" and event.title and event.start_local:
        return DemoRoute("calendar", "Event found — propose Add to Calendar.", event=event)

    if _looks_like_concerning_recruitment(event.source_text or ""):
        return DemoRoute(
            "glassbox_review",
            "Recruitment claims need context — propose Glassbox human review; not a trafficking determination.",
            triage=_context_review(event.source_text or "", event.confidence),
        )

    # Only declared synthetic training material enters the sensitive pipeline.
    # Ordinary non-event screenshots fall through to the share suggestion.
    try:
        _verify_synthetic(image)
    except ValueError:
        return DemoRoute("whatsapp", "No event found — propose sharing on WhatsApp.")

    triage = TriageModelClient(cfg).extract(image)
    if triage.kind == "review":
        return DemoRoute(
            "glassbox_review",
            "Observable concern found — human review recommended; not a trafficking determination.",
            triage=triage,
        )
    return DemoRoute(
        "whatsapp",
        "No validated review signal found — propose sharing on WhatsApp.",
        triage=triage,
    )


def classify_with_progress(image: Path, cfg: Config) -> DemoRoute:
    """Show immediate native feedback while hosted vision classification runs."""
    import tkinter as tk

    result: dict[str, object] = {}
    root = tk.Tk()
    root.title("Screenshot captured")
    root.attributes("-topmost", True)
    root.resizable(False, False)
    frame = tk.Frame(root, padx=30, pady=24)
    frame.pack()
    tk.Label(frame, text="Screenshot captured", font=("Helvetica", 18, "bold")).pack()
    status = tk.Label(frame, text="Analyzing and choosing the safest action…", pady=10)
    status.pack()

    def worker() -> None:
        try:
            # The watcher deliberately opens this panel as soon as the filename
            # appears. Wait here—not before the UI—for macOS to finish writing.
            previous = -1
            stable_reads = 0
            for _ in range(100):
                try:
                    size = image.stat().st_size
                except OSError:
                    size = 0
                if size > 0 and size == previous:
                    stable_reads += 1
                    if stable_reads >= 2:
                        break
                else:
                    stable_reads = 0
                previous = size
                time.sleep(.05)
            result["route"] = classify(image, cfg)
        except Exception as exc:
            result["error"] = exc

    def poll() -> None:
        if "route" in result or "error" in result:
            root.destroy()
        else:
            root.after(50, poll)

    threading.Thread(target=worker, daemon=True).start()
    root.after(50, poll)
    root.eval("tk::PlaceWindow . center")
    root.mainloop()
    if "error" in result:
        raise result["error"]  # type: ignore[misc]
    return result["route"]  # type: ignore[return-value]


def choose_route(route: DemoRoute, source_text: str = "") -> DemoRoute | None:
    """Native, topmost approval overlay. No destination opens before a click."""
    import tkinter as tk

    choice: dict[str, str | None] = {"value": None}
    root = tk.Tk()
    root.title("Screenshot understood")
    root.attributes("-topmost", True)
    root.resizable(False, False)
    frame = tk.Frame(root, padx=24, pady=20)
    frame.pack()
    tk.Label(frame, text="What should I do with this screenshot?", font=("Helvetica", 18, "bold")).pack(pady=(0, 8))
    tk.Label(frame, text=f"Suggested: {route.name.replace('_', ' ')}\n{route.summary}",
             justify="center", wraplength=520).pack(pady=(0, 18))

    def pick(value: str | None) -> None:
        choice["value"] = value
        root.destroy()

    buttons = tk.Frame(frame)
    buttons.pack()
    tk.Button(buttons, text="Add to Calendar", width=18, command=lambda: pick("calendar")).grid(row=0, column=0, padx=5)
    tk.Button(buttons, text="Send on WhatsApp", width=18, command=lambda: pick("whatsapp")).grid(row=0, column=1, padx=5)
    tk.Button(buttons, text="Review in Glassbox", width=18, command=lambda: pick("glassbox_review")).grid(row=0, column=2, padx=5)
    tk.Button(frame, text="Cancel", command=lambda: pick(None)).pack(pady=(14, 0))
    root.protocol("WM_DELETE_WINDOW", lambda: pick(None))
    root.eval("tk::PlaceWindow . center")
    root.mainloop()

    selected = choice["value"]
    if selected is None:
        return None
    if selected == route.name:
        return route
    if selected == "glassbox_review":
        return DemoRoute(
            "glassbox_review", "User selected Glassbox human review.",
            triage=route.triage or _context_review(source_text, route.event.confidence if route.event else .5),
        )
    if selected == "calendar":
        # Do not invent event fields when the screenshot was not an event.
        if route.event is None:
            return None
        return DemoRoute("calendar", "User selected Calendar.", event=route.event)
    return DemoRoute("whatsapp", "User selected WhatsApp sharing.")


def run_whatsapp_confirmation(cfg: Config, image: Path) -> int:
    """Collect an exact contact and require a second explicit send confirmation."""
    import tkinter as tk
    from tkinter import messagebox, simpledialog
    from .whatsapp import send_screenshot

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    contact = simpledialog.askstring(
        "WhatsApp recipient",
        "Enter the exact displayed WhatsApp contact name:",
        parent=root,
    )
    if not contact or not contact.strip():
        root.destroy()
        print("WhatsApp cancelled — no recipient selected.")
        return 0
    contact = contact.strip()
    from .voice_approval import approve
    try:
        approved = approve(
            f"Send this screenshot to {contact}?",
            title="Confirm WhatsApp Send",
        )
    except Exception as exc:
        messagebox.showerror("Gradium approval failed", str(exc), parent=root)
        root.destroy()
        return 1
    if not approved:
        root.destroy()
        print("WhatsApp cancelled — human rejected Send.")
        return 0
    runs = HOLO_HOME / "runs"
    before = {p.name for p in runs.iterdir() if p.is_dir()} if runs.exists() else set()
    try:
        result = send_screenshot(cfg, image, contact)
    except Exception as exc:
        messagebox.showerror("WhatsApp error", str(exc), parent=root)
        root.destroy()
        return 1
    finally:
        subprocess.run([str(cfg.holo_bin), "stop"], capture_output=True)
    run_dir = _new_run(runs, before)
    if run_dir and (run_dir / "events.jsonl").exists() and (run_dir / "events.jsonl").stat().st_size:
        latest = Path.cwd() / "runs" / "latest.jsonl"
        write_glassbox_trace(run_dir / "events.jsonl", latest, "latest-whatsapp")
    if result.ok:
        messagebox.showinfo("WhatsApp", "Screenshot sent and visually verified.", parent=root)
        code = 0
    else:
        messagebox.showerror(
            "WhatsApp not verified",
            result.error or "The screenshot was not confirmed as sent.",
            parent=root,
        )
        code = 1
    root.destroy()
    return code


def _data_uri(image: Path) -> str:
    mime = "image/jpeg" if image.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    return f"{mime};base64,{base64.b64encode(image.read_bytes()).decode()}"


_STYLE = """body{font:18px system-ui;background:#0b1020;color:#eef2ff;max-width:980px;margin:32px auto}
.card{border:1px solid #53618d;border-radius:18px;padding:24px;background:#111831;overflow:auto}
img{max-width:360px;max-height:440px;float:right;margin-left:24px;border-radius:12px}
textarea,input{width:52%;font:18px system-ui;padding:12px;background:#080d1c;color:#7fffd4;border:1px solid #53618d}
textarea{height:90px}a,button{display:inline-block;padding:14px 20px;background:#5b7cfa;color:white;border:0;border-radius:10px;text-decoration:none;margin:4px}
.warn{color:#ffd479}.quote{border-left:3px solid #7fffd4;padding:10px 12px;background:#0c1328;border-radius:4px}
small,.muted{color:#aab4d6}.topline{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #2d385d;padding-bottom:14px}
.badge{font:13px ui-monospace;padding:6px 10px;border:1px solid #ffd479;border-radius:99px;color:#ffd479}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.panel{border:1px solid #2d385d;border-radius:12px;padding:16px;background:#0d1429}.label{font:12px ui-monospace;text-transform:uppercase;color:#8491bc;letter-spacing:.08em}
.danger{background:#26304f}.secondary{background:transparent;border:1px solid #66719a}"""


def write_review_page(page: Path, image: Path, route: DemoRoute) -> None:
    triage = route.triage
    assert triage is not None
    case_id = "GBX-" + hashlib.sha256(image.read_bytes()).hexdigest()[:10].upper()
    statements = "".join(
        f'<div class="quote"><div class="label">{html.escape(item.category.replace("_", " "))}</div>“{html.escape(item.quote)}”<br><small>{html.escape(item.explanation)}</small></div>'
        for item in triage.observable_statements
    ) or "<p>No validated observable statements.</p>"
    missing = "".join(f"<li>{html.escape(item)}</li>" for item in triage.missing_context)
    limitations = "".join(f"<li>{html.escape(item)}</li>" for item in triage.limitations)
    page.write_text(f"""<!doctype html><meta charset="utf-8"><title>Glassbox Review</title><style>{_STYLE}</style>
<div class="card"><div class="topline"><div><div class="label">Glassbox safeguarding triage</div><h1>Human Review Record</h1></div><span class="badge">AWAITING DECISION</span></div>
<img src="data:{_data_uri(image)}"><p><span class="label">Case ID</span><br><b>{case_id}</b></p>
<p class="warn"><b>Not a trafficking determination.</b><br>This record preserves observable content for trained review. It does not identify a victim, perpetrator, crime, or level of risk.</p>
<div class="grid"><div class="panel"><div class="label">Model disposition</div><b>{html.escape(triage.kind.replace('_', ' '))}</b></div>
<div class="panel"><div class="label">Extraction confidence · not a risk score</div><b>{triage.confidence:.0%}</b></div></div>
<h2>Preliminary summary</h2><p>{html.escape(triage.summary)}</p><h2>Observable evidence</h2>{statements}
<div class="grid"><section class="panel"><div class="label">Missing context</div><ul>{missing or '<li>Context not established</li>'}</ul></section>
<section class="panel"><div class="label">Method limitations</div><ul>{limitations or '<li>Single screenshot; trained human review required</li>'}</ul></section></div>
<h2>Agent-prepared review note</h2><textarea id="review-note" aria-label="CUA review note" placeholder="Evidence-only note; no accusation or determination."></textarea>
<p class="muted">The note and original screenshot will remain together in the local review record.</p>
<div class="panel"><div class="label">Human decision required</div><p id="decision" class="warn">Awaiting human decision.</p>
<button class="danger" onclick="decision('submitted')">Submit to review queue</button>
<button class="secondary" onclick="decision('dismissed')">Dismiss</button></div>
<p><small>Submission is to the local Glassbox demo queue only. No hotline, law-enforcement, or external report is created.</small></p></div>
<script>
const caseId={json.dumps(case_id)};
function decision(x){{
  if(x==='submitted'){{
    const queue=JSON.parse(localStorage.getItem('glassbox.reviewQueue')||'[]');
    queue.push({{case_id:caseId,status:'submitted',submitted_at:new Date().toISOString(),note:document.querySelector('#review-note').value}});
    localStorage.setItem('glassbox.reviewQueue',JSON.stringify(queue));
  }}
  document.querySelector('#decision').textContent='Human decision: '+x;
  document.querySelector('.badge').textContent=x.toUpperCase();
  document.querySelectorAll('button').forEach(b=>b.disabled=true);
}}
</script>""")


def write_share_page(page: Path, image: Path) -> None:
    page.write_text(f"""<!doctype html><meta charset="utf-8"><title>WhatsApp handoff</title><style>{_STYLE}</style>
<div class="card"><img src="data:{_data_uri(image)}"><h1>WhatsApp Share</h1>
<p>Choose the exact recipient and confirm before the CUA sends this screenshot.</p>
<label>Recipient</label><br><input placeholder="Exact contact"><p><button>Confirm recipient</button></p>
<small>No message has been sent.</small></div>""")


def write_handoff(page: Path, image: Path, route: DemoRoute, destination: Path) -> None:
    if route.name == "calendar":
        assert route.event is not None
        action_url = google_calendar_url(route.event)
        action_label = "Continue to Calendar"
        proposed = route.event.title or "Calendar event"
    elif route.name == "glassbox_review":
        action_url = destination.as_uri()
        action_label = "Open Glassbox Review"
        proposed = "Analyze evidence and request a trained human decision"
    else:
        action_url = destination.as_uri()
        action_label = "Open WhatsApp Handoff"
        proposed = "Choose an exact recipient and confirm sharing"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(f"""<!doctype html><meta charset="utf-8"><title>Screenshot Action Router</title><style>{_STYLE}</style>
<div class="card"><img src="data:{_data_uri(image)}"><h1>Screenshot Action Router</h1>
<p><b>Selected action:</b> {html.escape(route.name)}</p><p class="warn">{html.escape(route.summary)}</p>
<p><b>Next:</b> {html.escape(proposed)}</p><label><b>CUA live status</b></label><br>
<textarea id="status" autofocus placeholder="The CUA will type one concise status here."></textarea><p>
<a id="continue" href="{html.escape(action_url, quote=True)}">{html.escape(action_label)}</a></p>
<small>The router proposes an action; a human controls the consequential decision.</small></div>""")


def prepare_pages(root: Path, image: Path, route: DemoRoute) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    handoff = root / "cua-demo-handoff.html"
    destination = root / (
        "glassbox-review.html" if route.name == "glassbox_review" else "whatsapp-handoff.html"
    )
    if route.name == "glassbox_review":
        write_review_page(destination, image, route)
    elif route.name == "whatsapp":
        write_share_page(destination, image)
    write_handoff(handoff, image, route, destination)
    return handoff, destination


def prepare_destination(root: Path, image: Path, route: DemoRoute) -> Path:
    """Build only the selected destination; the old router handoff is not shown."""
    root.mkdir(parents=True, exist_ok=True)
    if route.name == "glassbox_review":
        destination = root / "glassbox-review.html"
        write_review_page(destination, image, route)
        return destination
    if route.name == "whatsapp":
        destination = root / "whatsapp-handoff.html"
        write_share_page(destination, image)
        return destination
    return root / "calendar-opens-directly"


def _new_run(runs: Path, before: set[str]) -> Path | None:
    candidates = [p for p in runs.iterdir() if p.is_dir() and p.name not in before]
    return max(candidates, key=lambda p: p.stat().st_mtime, default=None)


def _task(route: DemoRoute) -> str:
    if route.name == "glassbox_review":
        return (
            "You are demonstrating Glassbox on the visible desktop. Stay in the browser. "
            "On the Glassbox Human Review page, read the warning, disposition, observable statements and "
            "missing context. Type one short evidence-only sentence in CUA review note. DO NOT click "
            "Submit to review queue or Dismiss. Stop and report that Glassbox is awaiting a trained human decision."
        )
    if route.name == "calendar":
        return (
            "You are demonstrating the Calendar route on the visible desktop. Stay in the browser. "
            "Wait for the pre-filled Google Calendar editor and verify title/time. DO NOT CLICK SAVE. "
            "Stop and report that Calendar is awaiting human approval."
        )
    return (
        "You are demonstrating the WhatsApp route on the visible desktop. Stay in the browser. "
        "On WhatsApp Share, verify the screenshot and recipient confirmation field are visible. "
        "Do not enter a recipient and do not send. Stop and report that sharing awaits human input."
    )


def _commit_task(route: DemoRoute) -> str:
    if route.name == "calendar":
        return (
            "The human approved the irreversible Calendar action. Stay in the visible Google "
            "Calendar editor, click the blue Save button exactly once, verify the event appears, "
            "and report whether it was saved. Do not change any fields or add guests."
        )
    return (
        "The human approved submitting this review. Stay on the Glassbox Human Review page, click "
        "Submit to review queue exactly once, verify the page says Human decision: submitted, "
        "and report the result. Do not click Dismiss."
    )


def _approval_prompt(route: DemoRoute) -> str:
    if route.name == "calendar":
        title = route.event.title if route.event else "this event"
        return f"Save {title} to Google Calendar?"
    return "Submit this screenshot and evidence note to the trained human review queue?"


def _append_trace(first: Path, second: Path, out: Path) -> None:
    rows = []
    for path in (first, second):
        for line in path.read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    for index, row in enumerate(rows):
        row["step"] = index
    out.write_text("".join(json.dumps(row) + "\n" for row in rows))


def run_cua(cfg: Config, destination: Path, route: DemoRoute, out: Path) -> tuple[int, str]:
    from .holo_mcp import HoloMCP

    if route.name == "calendar":
        assert route.event is not None
        subprocess.run(["open", google_calendar_url(route.event)], check=True)
    else:
        subprocess.run(["open", str(destination)], check=True)
    time.sleep(2)
    runs = HOLO_HOME / "runs"
    before = {p.name for p in runs.iterdir() if p.is_dir()} if runs.exists() else set()
    answer = ""
    code = 0
    mcp = None
    try:
        mcp = HoloMCP(cfg.holo_bin)
        answer = mcp.run_task(_task(route), timeout_s=150)
    except Exception as exc:
        code = 1
        answer = f"CUA error: {exc}"
    finally:
        if mcp is not None:
            mcp.close()
        subprocess.run([str(cfg.holo_bin), "stop"], capture_output=True)
    run_dir = _new_run(runs, before)
    if not run_dir or not (run_dir / "events.jsonl").exists() or not (run_dir / "events.jsonl").stat().st_size:
        return code or 1, f"CUA finished but no non-empty event trace was found; {answer[:160]}"
    steps = write_glassbox_trace(run_dir / "events.jsonl", out, out.stem)
    latest = out.parent / "latest.jsonl"
    if out != latest:
        shutil.copyfile(out, latest)
    from .voice_approval import approve
    try:
        approved = approve(_approval_prompt(route), title="Human approval required")
    except Exception as exc:
        return 1, f"Gradium approval failed; action blocked: {exc}"
    if not approved:
        return 0, f"{steps} preparation steps recorded; human clicked No, action blocked"

    before_commit = {p.name for p in runs.iterdir() if p.is_dir()} if runs.exists() else set()
    commit_answer = ""
    commit_mcp = None
    try:
        commit_mcp = HoloMCP(cfg.holo_bin)
        commit_answer = commit_mcp.run_task(_commit_task(route), timeout_s=90)
    except Exception as exc:
        return 1, f"Approval recorded but CUA commit failed: {exc}"
    finally:
        if commit_mcp is not None:
            commit_mcp.close()
        subprocess.run([str(cfg.holo_bin), "stop"], capture_output=True)
    commit_dir = _new_run(runs, before_commit)
    if commit_dir and (commit_dir / "events.jsonl").exists() and (commit_dir / "events.jsonl").stat().st_size:
        commit_trace = out.with_name(out.stem + "-commit.jsonl")
        write_glassbox_trace(commit_dir / "events.jsonl", commit_trace, out.stem + "-commit")
        prepared = out.with_name(out.stem + "-prepare.jsonl")
        shutil.copyfile(out, prepared)
        _append_trace(prepared, commit_trace, out)
    if out != latest:
        shutil.copyfile(out, latest)
    return code, f"Approved and committed. Trace: {out}; {commit_answer[:200]}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the three-way screenshot/CUA demo")
    parser.add_argument("image", nargs="?")
    parser.add_argument("--watch", action="store_true",
                        help="Watch for real macOS screenshots with an immediate native panel")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--trace", default="runs/unified-cua-demo.jsonl")
    args = parser.parse_args(argv)
    if args.watch:
        if args.image:
            parser.error("do not provide IMAGE with --watch")
        cfg = Config.load()
        print(f"Watching {cfg.screenshot_dir} — take a screenshot with Cmd+Shift+4", flush=True)
        known = {
            p: p.stat().st_mtime_ns for p in cfg.screenshot_dir.iterdir()
            if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg"}
        } if cfg.screenshot_dir.exists() else {}
        try:
            while True:
                if cfg.screenshot_dir.exists():
                    for path in cfg.screenshot_dir.iterdir():
                        if not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                            continue
                        try:
                            mtime = path.stat().st_mtime_ns
                        except OSError:
                            continue
                        if known.get(path) == mtime:
                            continue
                        known[path] = mtime
                        if not path.name.startswith(("Screenshot", "Screen Shot")):
                            continue
                        trace = Path.cwd() / "runs" / f"demo-{time.strftime('%H%M%S')}.jsonl"
                        code = process_image(path, cfg, trace=trace, prepare_only=False)
                        print(f"Ready for next screenshot (last exit={code})", flush=True)
                time.sleep(.05)
        except KeyboardInterrupt:
            subprocess.run([str(cfg.holo_bin), "stop"], capture_output=True)
            print("\nScreenshot watcher stopped.")
            return 0
    if not args.image:
        parser.error("IMAGE is required unless --watch is used")
    image = Path(args.image).expanduser().resolve()
    if not image.is_file():
        print(f"No such image: {image}", file=sys.stderr)
        return 2
    cfg = Config.load()
    return process_image(
        image, cfg, trace=Path(args.trace).resolve(), prepare_only=args.prepare_only
    )


def process_image(image: Path, cfg: Config, *, trace: Path, prepare_only: bool) -> int:
    """Process one screenshot; shared by one-shot and persistent watcher modes."""
    try:
        route = classify(image, cfg) if prepare_only else classify_with_progress(image, cfg)
    except Exception as exc:
        print(f"Routing failed: {exc}", file=sys.stderr)
        return 2
    if not prepare_only:
        chosen = choose_route(route, route.event.source_text if route.event else "")
        if chosen is None:
            print("Cancelled — no action opened.")
            return 0
        route = chosen
        if route.name == "whatsapp":
            return run_whatsapp_confirmation(cfg, image)
    destination = prepare_destination(Path.cwd() / "runs", image, route)
    print(json.dumps({"route": route.name, "summary": route.summary,
                      "destination": "Google Calendar" if route.name == "calendar" else str(destination)}, indent=2))
    if prepare_only:
        return 0
    code, message = run_cua(cfg, destination, route, trace)
    print(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
