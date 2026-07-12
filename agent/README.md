# Glassbox — screenshot → calendar agent

Take a screenshot of an invite, a booking, or a "let's meet Friday at 3" message
and this agent reads it with H Company's Holo3.1 vision model, books the event in
your Google Calendar automatically, and drops a small lower-right toast with an
**Undo**. No confirmation clicks, no screen takeover.

Built on H Company's Holo3.1 model (credited per hackathon rules).

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

## Setup

```bash
cd agent
python3 -m pip install .        # installs the `glassbox` command + deps
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
  5. Save it as `~/.glassbox/credentials.json`.

  The first run opens a browser once for consent; the refreshable token is cached
  at `~/.glassbox/token.json`.

State (token, caches, traces) lives in `~/.glassbox` (override with `$GLASSBOX_HOME`).

## Usage

```bash
glassbox --watch                       # watch the screenshot folder (default)
glassbox --once /path/to/screenshot.png   # process one screenshot and exit
glassbox --watch --cua                 # experimental: book via HoloDesktop, not the API
```

(Equivalently `python3 -m glassbox_agent …` without installing.)

## Layout

| File | Role |
|---|---|
| `glassbox_agent/watcher.py` | Detect genuine screen captures (`kMDItemIsScreenCapture`); settle + hash-dedupe. |
| `glassbox_agent/frontmost.py` | Capture the app/browser frontmost at screenshot time (`lsappinfo`). |
| `glassbox_agent/model_client.py` | Holo3.1 image → `EventCandidate` (real gateway + offline mock). |
| `glassbox_agent/schema.py` | `EventCandidate` contract + local validation/abstain. |
| `glassbox_agent/gcal.py` | Google Calendar API: OAuth, create, delete (Undo). |
| `glassbox_agent/popup.py` | Native lower-right toast (Tkinter) with Undo. |
| `glassbox_agent/app.py` | Orchestrator wiring the stages together. |
| `glassbox_agent/prefs.py` | Aggregate outcome counts (never raw screenshots). |
| `glassbox_agent/holo_desktop.py`, `holo_mcp.py` | Experimental `--cua` computer-use booking + Glassbox trace. |

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
