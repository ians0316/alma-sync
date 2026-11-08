#!/usr/bin/env python3
"""Bridge between the Alma+ Chrome extension and Alma Sync.

The extension keeps your own tasks inside Chrome. Chrome starts this script as a
"native messaging host" whenever your tasks change and sends it the full list.
This script saves the list to ~/.alma_sync/tasks.json and starts a quick
tasks-only sync (python3 sync.py --tasks-only) in the background, so tasks show
up in Notion and Google Calendar within seconds. The hourly sync includes them
too.

Messages follow Chrome's native messaging format: a 4-byte little-endian length,
then that many bytes of JSON, on stdin. Replies go to stdout the same way.
Nothing else may be written to stdout.
"""
import hashlib
import json
import os
import struct
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

# ALMA_SYNC_DIR / ALMA_SYNC_NO_SPAWN are only for testing without touching your real data.
APP_DIR = Path(os.environ.get("ALMA_SYNC_DIR") or Path.home() / ".alma_sync")
TASKS_PATH = APP_DIR / "tasks.json"
HERE = Path(__file__).resolve().parent
NO_CLASS = "My tasks"


# ---- Reading tasks for sync.py ----

def load_tasks():
    """Tasks from the extension as Assignment objects, ready for notion_store and google_store."""
    sys.path.insert(0, str(HERE))
    from alma_scraper import Assignment, get_period_code

    if not TASKS_PATH.exists():
        return []
    try:
        raw = json.loads(TASKS_PATH.read_text(encoding="utf-8")).get("tasks", [])
    except (json.JSONDecodeError, OSError):
        return []
    items = []
    for t in raw:
        try:
            due = date.fromisoformat(t["due"])
        except (KeyError, TypeError, ValueError):
            continue
        end = None
        if t.get("end"):
            try:
                end = date.fromisoformat(t["end"])
            except ValueError:
                end = None
        category = (t.get("category") or "").strip()
        # IDs: "task" + the task's id without dashes. Google event IDs only allow
        # a-v and 0-9, and the extension's ids are hex, so "almatask<hex>" fits.
        raw_id = str(t.get("id", ""))
        hex_id = "".join(ch for ch in raw_id.lower() if ch in "0123456789abcdef")
        if len(hex_id) < 16:  # not the usual id format (e.g. from an old backup): derive a stable one
            hex_id = hashlib.md5(raw_id.encode("utf-8")).hexdigest() if raw_id else ""
        task_id = "task" + hex_id
        if not hex_id or not (t.get("name") or "").strip():
            continue
        items.append(Assignment(
            id=task_id,
            class_name=category or NO_CLASS,
            name=t["name"].strip(),
            due=due,
            url="",
            period=get_period_code(category) if category else None,
            category="My task",
            end=end,
            notes=(t.get("notes") or "").strip(),
        ))
    return items


# ---- Native messaging host ----

def _read_message():
    header = sys.stdin.buffer.read(4)
    if len(header) < 4:
        return None
    (length,) = struct.unpack("<I", header)
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))


def _send(message):
    data = json.dumps(message).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(data)) + data)
    sys.stdout.buffer.flush()


def _start_tasks_sync():
    """Run `sync.py --tasks-only` in the background, detached from Chrome."""
    if os.environ.get("ALMA_SYNC_NO_SPAWN"):
        return
    APP_DIR.mkdir(parents=True, exist_ok=True)
    log = open(APP_DIR / "tasks_sync.log", "a", encoding="utf-8")
    subprocess.Popen(
        [sys.executable, str(HERE / "sync.py"), "--tasks-only"],
        cwd=str(HERE), stdin=subprocess.DEVNULL, stdout=log, stderr=log,
        start_new_session=True,
    )


def main():
    try:
        message = _read_message()
        if not message or message.get("type") != "tasks" or not isinstance(message.get("tasks"), list):
            _send({"ok": False, "error": "Unexpected message"})
            return
        APP_DIR.mkdir(parents=True, exist_ok=True)
        tmp = TASKS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps({"saved": datetime.now().isoformat(timespec="seconds"),
                                   "tasks": message["tasks"]}, indent=1), encoding="utf-8")
        os.replace(tmp, TASKS_PATH)
        _start_tasks_sync()
        _send({"ok": True, "count": len(message["tasks"])})
    except Exception as e:  # report to the extension instead of failing silently
        _send({"ok": False, "error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    main()
