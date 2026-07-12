"""Glassbox screenshot-to-calendar agent.

Watches the macOS screenshot folder, asks Holo3.1 whether a new screenshot
describes an event, shows an editable confirmation card, and — only after the
user clicks Add — drives the visible macOS Calendar via HoloDesktop, logging the
run as a Glassbox-compatible flight-recorder trace.
"""

__version__ = "0.1.0"
