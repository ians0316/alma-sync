"""Upserts Alma assignments into a Notion database through Notion's REST API.

Assignments are matched on the "Alma Assignment ID" property, so reruns update
existing rows instead of duplicating them. Rows are never deleted, and the
"Done" checkbox is only set when a row is first created.
"""
import json
import os
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from datetime import date

API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
TIMEZONE = "Asia/Seoul"
KEYCHAIN_SERVICE = "NotionToken"
KEYCHAIN_ACCOUNT = "notion"

# Python installed from python.org ships without CA certificates, so HTTPS fails
# with CERTIFICATE_VERIFY_FAILED. macOS's own bundle works for every Python build.
_MAC_CA_BUNDLE = "/etc/ssl/cert.pem"
_SSL_CONTEXT = ssl.create_default_context(cafile=_MAC_CA_BUNDLE if os.path.exists(_MAC_CA_BUNDLE) else None)


def get_token() -> str:
    result = subprocess.run(
        ["security", "find-generic-password", "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_SERVICE, "-w"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Could not read the Notion token from Keychain (item '{KEYCHAIN_SERVICE}', account "
            f"'{KEYCHAIN_ACCOUNT}'). Details: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _request(token: str, method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API}{path}", data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    # Retries cover rate limits, Notion 5xx errors, and network timeouts (e.g. the
    # Mac sleeping mid-run, which kills in-flight connections).
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if (e.code == 429 or e.code >= 500) and attempt < 3:
                time.sleep(float(e.headers.get("Retry-After", 2 * (attempt + 1))))
                continue
            raise RuntimeError(f"Notion API {method} {path} failed: {e.code} {e.read().decode(errors='replace')}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt < 3:
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(f"Notion API {method} {path} failed after retries: {type(e).__name__}: {e}")
    raise RuntimeError(f"Notion API {method} {path} kept failing")


def _existing_pages(token: str, database_id: str) -> dict[str, str]:
    """Returns {alma_assignment_id: notion_page_id} for every row in the database."""
    pages = {}
    cursor = None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        resp = _request(token, "POST", f"/databases/{database_id}/query", body)
        for page in resp["results"]:
            rich = page["properties"].get("Alma Assignment ID", {}).get("rich_text", [])
            if rich:
                pages[rich[0]["plain_text"]] = page["id"]
        if not resp.get("has_more"):
            return pages
        cursor = resp["next_cursor"]


def _due_property(due: date, period_time: tuple[str, str] | None) -> dict:
    if period_time:
        return {"date": {
            "start": f"{due.isoformat()}T{period_time[0]}:00",
            "end": f"{due.isoformat()}T{period_time[1]}:00",
            "time_zone": TIMEZONE,
        }}
    return {"date": {"start": due.isoformat()}}


def upsert_assignments(token: str, database_id: str, assignments, period_times: dict) -> tuple[int, int, list[str]]:
    """Creates or updates one row per assignment. Returns (created, updated, failures).

    One assignment failing doesn't stop the rest; its name goes into `failures`.
    """
    existing = _existing_pages(token, database_id)
    created = updated = 0
    failures = []
    for a in assignments:
        props = {
            "Assignment": {"title": [{"text": {"content": a.name}}]},
            "Class": {"select": {"name": a.class_name}},
            "Period": {"select": {"name": a.period} if a.period else None},
            "Due": _due_property(a.due, period_times.get(a.period) if a.period else None),
            "Alma Link": {"url": a.url or None},
            "Alma Assignment ID": {"rich_text": [{"text": {"content": a.id}}]},
        }
        page_id = existing.get(a.id)
        try:
            if page_id:
                _request(token, "PATCH", f"/pages/{page_id}", {"properties": props})
                updated += 1
            else:
                props["Done"] = {"checkbox": False}
                _request(token, "POST", "/pages", {"parent": {"database_id": database_id}, "properties": props})
                created += 1
        except RuntimeError as e:
            failures.append(f"{a.class_name}: {a.name} ({e})")
        time.sleep(0.35)
    return created, updated, failures
