"""Mirrors Alma assignments into a Google Calendar so Notion Calendar (and the
Google Calendar app) send notifications for them.

Auth is a Google Cloud service account. The calendar is owned by the user and
shared with the service account's email. Events use the calendar's default
reminders, which are set by the user in Google Calendar settings.

Each event's ID is derived from the Alma assignment ID, so reruns update the same
event instead of duplicating it. Events are never deleted.
"""
import time
from datetime import date, timedelta
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

KEY_PATH = Path.home() / ".alma_sync" / "google-service-account.json"
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
API = "https://www.googleapis.com/calendar/v3"
TIMEZONE = "Asia/Seoul"


def is_configured(calendar_id: str | None) -> bool:
    return bool(calendar_id) and KEY_PATH.exists()


def _session() -> AuthorizedSession:
    creds = service_account.Credentials.from_service_account_file(str(KEY_PATH), scopes=SCOPES)
    return AuthorizedSession(creds)


def _event_id(alma_id: str) -> str:
    # Google event IDs allow only a-v and 0-9; Alma IDs are lowercase hex, so they fit.
    return f"alma{alma_id}"


def _event_body(a, period_time: tuple[str, str] | None) -> dict:
    if period_time:
        start = {"dateTime": f"{a.due.isoformat()}T{period_time[0]}:00", "timeZone": TIMEZONE}
        end = {"dateTime": f"{a.due.isoformat()}T{period_time[1]}:00", "timeZone": TIMEZONE}
    else:
        # Google all-day events use an exclusive end date.
        start = {"date": a.due.isoformat()}
        end = {"date": (a.due + timedelta(days=1)).isoformat()}
    title = f"{a.class_name}: {a.name}" if a.class_name else a.name
    body = {
        "summary": title,
        "description": a.url or "",
        "start": start,
        "end": end,
        "status": "confirmed",
        "reminders": {"useDefault": True},
    }
    if a.url:
        body["source"] = {"title": "Alma", "url": a.url}
    return body


def _call(session, method: str, url: str, **kw):
    for attempt in range(4):
        try:
            resp = session.request(method, url, timeout=30, **kw)
        except Exception as e:  # network errors, e.g. the Mac sleeping mid-request
            if attempt < 3:
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(f"Google Calendar {method} failed after retries: {type(e).__name__}: {e}")
        if resp.status_code in (403, 429, 500, 502, 503) and attempt < 3 and (
            resp.status_code != 403 or "rateLimitExceeded" in resp.text or "userRateLimitExceeded" in resp.text
        ):
            time.sleep(2 * (attempt + 1))
            continue
        return resp
    return resp


def upsert_assignments(calendar_id: str, assignments, period_times: dict) -> tuple[int, int, list[str]]:
    """Creates or updates one event per assignment. Returns (created, updated, failures)."""
    session = _session()
    base = f"{API}/calendars/{calendar_id}/events"
    created = updated = 0
    failures = []
    for a in assignments:
        body = _event_body(a, period_times.get(a.period) if a.period else None)
        event_id = _event_id(a.id)
        try:
            resp = _call(session, "PUT", f"{base}/{event_id}", json=body)
            was_created = False
            if resp.status_code == 404:
                resp = _call(session, "POST", base, json={**body, "id": event_id})
                was_created = True
                if resp.status_code == 409:  # ID belongs to a deleted event; restore it
                    resp = _call(session, "PUT", f"{base}/{event_id}", json=body)
                    was_created = False
            if resp.status_code >= 400:
                raise RuntimeError(f"{resp.status_code} {resp.text[:300]}")
            if was_created:
                created += 1
            else:
                updated += 1
        except RuntimeError as e:
            failures.append(f"{a.class_name}: {a.name} ({e})")
        time.sleep(0.2)
    return created, updated, failures
