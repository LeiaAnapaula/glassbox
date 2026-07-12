# Glassbox

Turn a macOS screenshot into a Google Calendar event. Screenshot an invite, a
booking, or a "let's meet Friday at 3" message — H Company's **Holo3.1** vision
model reads it, the **Google Calendar API** books it, and a small lower-right
toast confirms with an **Undo**. Zero clicks, no screen takeover.

Built on H Company's Holo3.1 model + HoloDesktop CLI (credited per hackathon rules).

- **[`agent/`](agent/)** — the agent. See [agent/README.md](agent/README.md) for
  setup and usage (`glassbox --watch`).
- **[`viewer/glassbox.html`](viewer/glassbox.html)** — a standalone flight-recorder
  viewer for HoloDesktop runs, used by the experimental `--cua` computer-use path
  which logs each step as a replayable trace.

## Quick start

```bash
cd agent
python3 -m pip install .
# one-time: holo login, and drop a Google OAuth client at ~/.glassbox/credentials.json
glassbox --watch
```
