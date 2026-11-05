#!/usr/bin/env python3
"""
Alma -> Notion calendar sync.

Setup (one-time, run by hand):
    1. Store your Alma password in Keychain Access.app (login keychain):
       Keychain Item Name: AlmaPortal, Account Name: <your Alma username>, Password: <your password>
    2. Create a Notion internal integration, share the "Alma Assignments" database with it,
       and store its secret in Keychain Access.app (login keychain):
       Keychain Item Name: NotionToken, Account Name: notion, Password: <integration secret>
    3. Edit config.json next to this script (username, base_url, notion_database_id).
    4. Run:  python3 sync.py --setup
       This opens a visible browser window so you can complete any 2FA prompt once;
       the device is then remembered for future headless runs.

Scheduled runs (via launchd) call:  python3 sync.py
"""
import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from alma_scraper import run_scrape, get_keychain_password, notify, PERIOD_TIMES
import notion_store
import google_store
import grades_sheet

APP_DIR = Path.home() / ".alma_sync"
CONFIG_PATH = Path(__file__).parent / "config.json"
PROFILE_DIR = APP_DIR / "browser_profile"
LOG_PATH = APP_DIR / "sync.log"

KEYCHAIN_SERVICE = "AlmaPortal"


def load_config():
    if not CONFIG_PATH.exists():
        sys.exit(f"Missing config file: {CONFIG_PATH}. Copy config.example.json to config.json and edit it.")
    return json.loads(CONFIG_PATH.read_text())


def log(msg):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}\n")
    print(msg)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", action="store_true", help="Run once with a visible browser to complete 2FA / establish trusted device.")
    parser.add_argument("--dump", metavar="PATH", help="Scrape, write the assignments to PATH as JSON, and exit without writing to Notion.")
    args = parser.parse_args()

    config = load_config()
    username = config["username"]
    base_url = config["base_url"].rstrip("/")

    try:
        password = get_keychain_password(KEYCHAIN_SERVICE, username)
    except RuntimeError as e:
        log(f"ERROR: {e}")
        sys.exit(1)

    def otp_prompt():
        return input("Enter the 2FA code shown on your device: ").strip()

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    log("Starting Alma scrape...")
    for attempt in (1, 2, 3):
        try:
            result = run_scrape(
                base_url, username, password, str(PROFILE_DIR),
                headless=not args.setup,
                otp_prompt=otp_prompt if args.setup else None,
            )
            break
        except Exception as e:
            log(f"Scrape attempt {attempt} failed: {type(e).__name__}: {str(e).splitlines()[0]}")
            if attempt == 3:
                raise
            time.sleep(20)

    if result is None:
        log("Login requires 2FA and no trusted session was available. Run: python3 sync.py --setup")
        notify("Alma Sync failed", "Run `python3 sync.py --setup` to re-authenticate.")
        sys.exit(2)

    # Notion and Google Calendar only track recent and upcoming work; the Grades tab gets everything.
    min_due = date.today() - timedelta(days=3)
    assignments = [a for a in result.assignments if a.due >= min_due]
    log(f"Scraped {len(result.assignments)} assignments ({len(assignments)} due from {min_due:%b %-d} on).")

    if args.dump:
        Path(args.dump).write_text(json.dumps([
            {"id": a.id, "class": a.class_name, "name": a.name, "due": a.due.isoformat(),
             "period": a.period, "url": a.url}
            for a in sorted(assignments, key=lambda a: a.due)
        ], indent=2))
        print(f"Wrote {len(assignments)} assignments to {args.dump}")
        return

    token = notion_store.get_token()
    created, updated, failures = notion_store.upsert_assignments(
        token, config["notion_database_id"], assignments, PERIOD_TIMES,
    )
    for f in failures:
        log(f"ERROR: could not write to Notion: {f}")
    log(f"Sync complete: {created} created, {updated} updated, {len(failures)} failed in Notion (of {len(assignments)} scraped). Nothing is ever deleted.")
    if failures:
        notify("Alma Sync", f"{len(failures)} assignment(s) failed to reach Notion. See sync.log.")

    sync_google_calendar(config, assignments)
    sync_grades_sheet(config, result)


def sync_google_calendar(config, assignments):
    calendar_id = config.get("google_calendar_id")
    if not google_store.is_configured(calendar_id):
        log("Google Calendar mirror not set up yet (needs google_calendar_id in config.json and the key file); skipping.")
        return
    try:
        g_created, g_updated, g_failures = google_store.upsert_assignments(calendar_id, assignments, PERIOD_TIMES)
    except Exception as e:
        log(f"ERROR: Google Calendar step failed: {type(e).__name__}: {e}")
        notify("Alma Sync", "Google Calendar step failed. See sync.log.")
        return
    for f in g_failures:
        log(f"ERROR: could not write to Google Calendar: {f}")
    log(f"Google Calendar: {g_created} created, {g_updated} updated, {len(g_failures)} failed.")
    if g_failures:
        notify("Alma Sync", f"{len(g_failures)} assignment(s) failed to reach Google Calendar. See sync.log.")


def sync_grades_sheet(config, result):
    sheet_id = config.get("google_sheet_id")
    if not sheet_id or not google_store.KEY_PATH.exists():
        return
    try:
        n = grades_sheet.write_grades(sheet_id, result)
    except Exception as e:
        log(f"ERROR: Grades sheet step failed: {type(e).__name__}: {e}")
        notify("Alma Sync", "Grades sheet step failed. See sync.log.")
        return
    log(f"Grades sheet: rewrote {n} assignments across {len(result.class_grades)} class grades.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        log(f"ERROR: {type(e).__name__}: {e}")
        notify("Alma Sync failed", f"{type(e).__name__}: {str(e)[:120]}")
        raise
