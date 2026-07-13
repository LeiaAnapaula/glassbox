# Glassbox

**See what your agent is thinking. Stop it before it does anything it can't undo.**

Computer-use agents are black boxes: they move your mouse, type into your apps, and click Save, and you find out what they were thinking after the fact. Glassbox is a transparency layer that makes agent runs observable in real time and hard-pauses before any irreversible action so a human makes the final call.

Built at the H Company hackathon (Track 1: Computer Use) on top of [Holo](https://www.hcompany.ai/). Demo case: safeguarding review of suspicious recruitment messages, where the agent extracts observable evidence, records extraction confidence, and never declares a conclusion. A trained human decides. That restraint is the product.

## What it does

- **Live trace viewer.** Every step the agent takes (what it sees, types, clicks, and why) streams into a viewer as it happens, with per-step reasoning, extraction confidence, latency, and before/after screenshots.
- **Pause and approve.** Any step marked `"irreversible": true` freezes the run. The viewer shows the full reasoning up to that point and waits. Approve, and the action commits. Reject, and it's blocked. Nothing irreversible happens without a human.
- **Watch mode.** The viewer tails a run file while the agent is still writing it, so you watch the agent's mind and its actions side by side.

## Quick start

Serve the repo (the viewer fetches run files, so no file://):

```bash
python3 -m http.server
```

Open the viewer:

```
http://localhost:8000/viewer/glassbox.html
```

Drag any `.jsonl` run file from `runs/` onto the page. Done.

### Watch a live run

```
http://localhost:8000/viewer/glassbox.html?watch=runs/live.jsonl
```

No agent handy? Simulate one:

```bash
python3 scripts/simulate_run.py
```

It appends a step every 1.5s, including an irreversible step, so you can try the pause gate without a real run.

## Run file format

One JSON object per line:

```json
{"run_id": "...", "step": 6, "timestamp": "...", "screenshot_before": "../runs/step6_before.png", "screenshot_after": "../runs/step6_after.png", "action": {"type": "click", "x": 612, "y": 338, "target_text": "Save"}, "reasoning": "All fields verified; clicking Save publishes the event", "confidence": 0.88, "irreversible": true, "latency_ms": 900}
```

Notes:
- `confidence` is extraction confidence (how sure the agent is about what it read), not a judgment about the situation.
- Screenshot paths resolve relative to `viewer/glassbox.html`.
- Set `"irreversible": true` on any step that should trigger the pause gate. That's the whole integration: make your agent append JSONL as it runs, flush after each line, and mark the risky steps.

## Repo layout

```
glassbox/
├── viewer/
│   └── glassbox.html      # the whole viewer, single file, no dependencies
├── runs/                  # JSONL run logs + screenshots
├── scripts/
│   └── simulate_run.py    # fake agent for testing watch mode
└── holo-desktop-cli/      # vendored CUA harness
```

## Why this exists

Trafficking recruitment hides in plain sight, in DMs and job offers, and the humans trained to spot it are drowning in volume. Agents could help triage, but nobody should trust a black box with decisions about real people. Glassbox is what it takes to deploy an agent in any domain where a wrong irreversible action is unacceptable: full observability, evidence only, human in the loop, every time.

## Team

- **Leia Chavarria-Davila** ([@LeiaAnapaula](https://github.com/LeiaAnapaula)) - viewer, pause-and-approve UI, confidence logging, pitch
- **Vedant** - agent side: Holo CUA harness, routing, synthetic safeguarding cases

All safeguarding demo cases are synthetic and labeled as such. No real people, no real conversations.
