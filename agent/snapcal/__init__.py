"""snapcal: turn macOS screenshots into Google Calendar events.

Watches for genuine screen captures, asks H Company's Holo3.1 vision model
whether one depicts an event, and books it straight to Google Calendar via the
Calendar API — zero-click, with a native toast and Undo. An experimental
`--cua` flag books instead through HoloDesktop's background computer-use agent,
logging the run as a Glassbox-compatible flight-recorder trace.
"""

__version__ = "0.1.0"
