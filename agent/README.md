# snapcal — screenshot → calendar

Take a screenshot of an invite, a booking, or a "let's meet Friday at 3" message
and snapcal reads it with H Company's Holo3.1 vision model, books the event in
your Google Calendar automatically, and drops a small lower-right toast with an
**Undo**. From that toast, you can also explicitly send the source screenshot to
a WhatsApp Desktop contact through HoloDesktop's background computer-use mode.

Built on H Company's Holo3.1 model (credited per hackathon rules).

The repository also contains a separate, synthetic-only safeguarding triage
demonstration. It preserves visible statements for trained human review and is
not a trafficking detector. See [`TRIAGE_DEMO.md`](TRIAGE_DEMO.md).

## Unified visible-CUA demo

From the repository root, run:

```bash
PYTHONPATH=agent .venv/bin/python -m snapcal.cua_demo \
  agent/demo/synthetic-triage/case-01-document-control.png \
  --trace runs/unified-cua-demo.jsonl
```

The command routes the screenshot with hosted Holo3.1 to Calendar, WhatsApp, or
Glassbox Review, opens a local handoff page, and starts a real foreground
HoloDesktop run. The CUA types one concise status line and opens the selected
destination. It stops before Save, Send, Queue, or Dismiss for real human input,
always issues `holo stop` afterward, and converts the run into a Glassbox JSONL
trace. The sensitive review route accepts synthetic cases only.

## How it works

```
macOS screenshot (Cmd-Shift-4 / Cmd-Shift-3)
        │  detected via kMDItemIsScreenCapture (not arbitrary image files)
        ▼
  watcher ── hash/dedupe ──►  Holo3.1 image request  (H model gateway /v1)
                                   │
                                   ▼
                     validated EventCandidate JSON
                                   │
                    non_event ─────┴───── event
                       ignore              ▼
                              Google Calendar API  (create event)
                                   │
                                   ▼
              lower-right toast:  "✓ Added · <title>   [Undo]"
                                   │  Undo = API delete
                                   │  Send to WhatsApp = contact + confirmation
                                   ▼
                     local outcome / preference counts
```

**What each piece does.** Detection is a filesystem event (ours — it isn't
computer use). Holo3.1 does the intelligence: read the screenshot, decide if it's
an event, extract title/date/time/location, resolve relative dates. The Google
Calendar API does the booking — reliable and instant, so Undo is a real delete.

> An experimental `--cua` flag books via HoloDesktop's **background** window-bound
> computer-use agent instead of the API (drives a browser window without touching
> your cursor). It's less reliable than the API path — Google Calendar's web Save
> step is genuinely hard to automate — so the API is the default.

WhatsApp forwarding is deliberately different from calendar booking. Personal
WhatsApp has no public send API, so the GUI is the integration surface. It is
never automatic: choose **Send to WhatsApp…**, enter the exact contact name, and
approve the final confirmation. HoloDesktop then operates the WhatsApp window in
background mode and reports success only after visually verifying the outgoing
image. If Holo3.1 decides the screenshot is not an event, the popup skips all
Calendar actions and offers only the confirmed WhatsApp action.

## Setup

```bash
cd agent
python3 -m pip install .        # installs the `snapcal` command + deps
```

Requires macOS and Python 3.10+.

- **Holo3.1 key:** sign into HoloDesktop once (`holo login`) so `~/.holo/.env`
  holds `HAI_API_KEY` — the key for the model gateway. (Or export `HAI_API_KEY`.)
- **Google Calendar credential (one time):** the Calendar API needs an OAuth
  "installed app" client.
  1. <https://console.cloud.google.com/> → create/pick a project.
  2. **APIs & Services → Library →** enable **Google Calendar API**.
  3. **OAuth consent screen →** *External*; add your Google address under
     **Test users**.
  4. **Credentials → Create credentials → OAuth client ID → Desktop app**,
     download the JSON.
  5. Save it as `~/.snapcal/credentials.json`.

- **WhatsApp forwarding (optional):** install and sign into WhatsApp Desktop,
  and install HoloDesktop CLI. The send action uses `holo mcp`; it does not use
  `holo run` and therefore does not move the real cursor. The action appears in
  the screenshot result card and always asks for confirmation.

  The first run opens a browser once for consent; the refreshable token is cached
  at `~/.snapcal/token.json`.

State (token, caches, traces) lives in `~/.snapcal` (override with `$SNAPCAL_HOME`).

## Usage

```bash
snapcal --watch                       # watch the screenshot folder (default)
snapcal --once /path/to/screenshot.png   # process one screenshot and exit
snapcal --watch --cua                 # experimental: book via HoloDesktop, not the API
glassbox-preflight                    # non-consequential readiness checks
```

(Equivalently `python3 -m snapcal …` without installing.)

## Layout

| File | Role |
|---|---|
| `snapcal/watcher.py` | Detect genuine screen captures (`kMDItemIsScreenCapture`); settle + hash-dedupe. |
| `snapcal/frontmost.py` | Capture the app/browser frontmost at screenshot time (`lsappinfo`). |
| `snapcal/model_client.py` | Holo3.1 image → `EventCandidate` via the H model gateway. |
| `snapcal/schema.py` | `EventCandidate` contract + local validation/abstain. |
| `snapcal/gcal.py` | Google Calendar API: OAuth, create, delete (Undo). |
| `snapcal/popup.py` | Native lower-right toast (Tkinter) with Undo. |
| `snapcal/app.py` | Orchestrator wiring the stages together. |
| `snapcal/prefs.py` | Aggregate outcome counts (never raw screenshots). |
| `snapcal/holo_desktop.py`, `holo_mcp.py` | Experimental `--cua` computer-use booking + Glassbox trace. |
| `snapcal/whatsapp.py` | Confirmed background-CUA screenshot forwarding to WhatsApp Desktop. |

## Notes & limitations

- **Only real screen captures trigger it** — a downloaded or dragged-in image in
  the folder is ignored.
- **Extraction is probabilistic.** Ambiguous dates resolve conservatively; the
  toast shows the extracted title so a wrong guess is obvious, and Undo reverses
  it in one click.
- **Timezone** defaults to this machine's local offset when the screenshot
  doesn't state one.
- The `--cua` path drives Google Calendar's web UI, whose Save step is
  unreliable to automate; prefer the default API path.
- WhatsApp forwarding requires an exact contact match and a visual success
  report. Ambiguous contacts, login problems, or an unverified send are surfaced
  as failures rather than treated as success.
