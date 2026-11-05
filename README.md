# Alma Sync

Keeps my school assignments and grades up to date outside the Alma student portal. A background job on my Mac reads every class page in Alma once an hour and sends the results to the tools I use.

| Destination | What it gets | Why |
|---|---|---|
| Notion database | Recent and upcoming assignments at their class period time | Main calendar view in Notion Calendar |
| Google Calendar | The same assignments | Alerts, which Notion Calendar only sends for Google events |
| Google Sheets | Every assignment and grade, grouped by class | Gradebook with a recently graded section |

## How it works

```
Alma class pages
      |  Playwright (headless Chromium)
      v
   sync.py  (launchd, 5 minutes past every hour)
      |
      +--> notion_store.py   --> Notion database
      +--> google_store.py   --> Google Calendar
      +--> grades_sheet.py   --> Google Sheets "Grades" tab
```

It scrapes class pages instead of Alma's To Do list because the To Do list hides graded work, even assignments due the same day. Notion rows and calendar events are matched on the Alma assignment ID, so reruns update them instead of creating duplicates. Nothing in Notion or Google Calendar is ever deleted, so past assignments stay.

## Project layout

```
alma_sync/
  sync.py                       Runs one full sync
  alma_scraper.py               Alma login and class page scraping
  notion_store.py               Writes to Notion
  google_store.py               Writes to Google Calendar
  grades_sheet.py               Rebuilds the Grades tab
  config.example.json           Template for config.json
  requirements.txt              Python packages
  install_schedule.sh           Installs the hourly launchd job
  com.alma.sync.plist.template  launchd job template
legacy/
  calendar_store.py             Old Apple Calendar writer, no longer used
```

## Setup (macOS)

1. Install the dependencies:

   ```bash
   cd alma_sync
   python3 -m pip install -r requirements.txt
   python3 -m playwright install chromium
   ```

2. Copy `config.example.json` to `config.json` and fill it in.

3. Add two items to the **login** keychain in Keychain Access (not iCloud):

   | Keychain Item Name | Account Name | Password |
   |---|---|---|
   | `AlmaPortal` | your Alma username | your Alma password |
   | `NotionToken` | `notion` | your Notion integration token |

4. Share the Notion database with your Notion integration.

5. For Google Calendar and Sheets, create a Google Cloud service account with the Calendar and Sheets APIs enabled. Save its JSON key as `~/.alma_sync/google-service-account.json`, then share the calendar and the spreadsheet with the service account's email. Google steps are skipped if this isn't set up.

6. Run it once by hand, then install the schedule:

   ```bash
   python3 sync.py --setup
   ./install_schedule.sh
   ```

## Using it

- Sync right away: `python3 sync.py`
- Check what happened: `~/.alma_sync/sync.log`
- Export assignments to a file without syncing: `python3 sync.py --dump assignments.json`

The job only runs while the Mac is awake and catches up after it wakes. Failures are logged and show a macOS notification.

## Adapting it to another school

Class period times are hardcoded in `PERIOD_TIMES` in `alma_scraper.py`. Change them to your school's bell schedule, and set `base_url` in `config.json`.

## Privacy

Passwords and tokens live in the macOS Keychain, and the Google key lives in `~/.alma_sync/`. `config.json`, exported data, and logs are not part of this repo.
