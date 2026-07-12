"""Google Calendar API booking.

The reliable, zero-click way to create the event: Holo3.1 reads the screenshot,
this writes the event straight to Google Calendar via the REST API. No web-UI
automation, no Save button to fight. Undo is a real API delete.

Auth is standard OAuth "installed app": the user provides a Google OAuth client
(`credentials.json`), and the first run opens a browser once for consent; the
refreshable token is cached in the data dir thereafter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .config import Config
from .schema import EventCandidate

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
API_BASE = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


@dataclass
class BookResult:
    ok: bool
    event_id: str = ""
    html_link: str = ""
    error: str = ""


class NeedsSetup(RuntimeError):
    """Raised when the OAuth client (credentials.json) is missing."""


def _credentials_path(cfg: Config) -> Path:
    return cfg.data_dir / "credentials.json"


def _token_path(cfg: Config) -> Path:
    return cfg.data_dir / "token.json"


def get_credentials(cfg: Config) -> Credentials:
    """Load cached credentials, refreshing or running the consent flow as needed."""
    token_path = _token_path(cfg)
    creds: Optional[Credentials] = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        cred_file = _credentials_path(cfg)
        if not cred_file.exists():
            raise NeedsSetup(
                f"Google OAuth client not found at {cred_file}. See agent/README.md "
                "(Google Calendar setup) to create one."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(cred_file), SCOPES)
        creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json())
    return creds


def _event_time(iso_local: str, tz: Optional[str]) -> dict:
    dt = datetime.fromisoformat(iso_local)
    if dt.tzinfo is None:
        dt = dt.astimezone()  # attach this machine's UTC offset
    body = {"dateTime": dt.isoformat()}
    if tz:
        body["timeZone"] = tz
    return body


def _event_body(candidate: EventCandidate) -> dict:
    start_iso = candidate.start_local
    end_iso = candidate.end_local
    if start_iso and not end_iso:
        try:
            end_iso = (datetime.fromisoformat(start_iso) + timedelta(hours=1)).isoformat()
        except ValueError:
            end_iso = start_iso
    body: dict = {"summary": candidate.title or "Untitled event"}
    if candidate.location:
        body["location"] = candidate.location
    if candidate.source_text:
        body["description"] = f"Captured by Glassbox from a screenshot:\n{candidate.source_text}"
    if start_iso:
        body["start"] = _event_time(start_iso, candidate.timezone)
        body["end"] = _event_time(end_iso or start_iso, candidate.timezone)
    return body


def create_event(cfg: Config, candidate: EventCandidate) -> BookResult:
    try:
        creds = get_credentials(cfg)
    except NeedsSetup as e:
        return BookResult(False, error=str(e))
    except Exception as e:
        return BookResult(False, error=f"auth failed: {e}")
    try:
        resp = requests.post(
            API_BASE,
            headers={"Authorization": f"Bearer {creds.token}"},
            json=_event_body(candidate),
            timeout=30,
        )
    except requests.RequestException as e:
        return BookResult(False, error=f"network error: {e}")
    if resp.status_code not in (200, 201):
        return BookResult(False, error=f"Calendar API {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    return BookResult(True, event_id=data.get("id", ""), html_link=data.get("htmlLink", ""))


def delete_event(cfg: Config, event_id: str) -> bool:
    """Delete a previously created event (the Undo action)."""
    try:
        creds = get_credentials(cfg)
        resp = requests.delete(
            f"{API_BASE}/{event_id}",
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=30,
        )
    except Exception:
        return False
    return resp.status_code in (200, 204)
