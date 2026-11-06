# Alma Sync + Calendar Integration

Alma Sync is a tool that adds convenient features for Seoul Academy students using Alma and technically everyone who uses Alma to calendar. Its purpose is to provide comfortable environment through putting todo assignments into calendar. It Keeps school assignments and grades up to date outside the Alma portal (seoulacademy.getalma.com). A background sync on a Mac reads every class page & todo list in Alma once an hour and sends the data to Notion, Google Calendar, and Google Sheets.

## Why this exists

Alma is where teachers post assignments, change due dates, and enter grades, but it has no calendar feed to subscribe to and no alerts for due dates. Checking it means logging in and reading a list that keeps changing. This project puts assignments on a calendar automatically, at the time of the class they're due in, and keeps all grades in one organized place.

## What it does

| Destination | What it gets | Why |
|---|---|---|
| Notion database | Recent and upcoming assignments at their class period time | Main calendar view in Notion Calendar |
| Google Calendar | The same assignments | Alerts, which Notion Calendar only sends for Google events |
| Google Sheets | Every assignment and grade, grouped by class | Gradebook with a recently graded section |

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

## Features

**Calendar**

- New assignments appear automatically, and changed due dates update in place.
- Each assignment sits at its real class period time instead of an all-day block.
- Past assignments stay on the calendar as a record. The sync never deletes anything from Notion or Google Calendar.
- The Done checkbox in Notion is left alone, so checking off an assignment sticks.
- Google Calendar sends alerts from its own servers, so assignments that have already synced still alert while the Mac is asleep.

**Gradebook**

- A "Last updated" line shows when the data was refreshed.
- A summary table lists each class's current grade, how many assignments are graded, not graded yet, or upcoming, and the lowest score so far.
- A "Recently graded" section lists everything graded in the last 7 days, newest first.
- Each class gets its own color-coded section with every assignment's due date, status, grade, score, points, weight, teacher comment, and graded date.
- Low scores are highlighted red and high scores green.

**Reliability**

- Requests retry on timeouts and server errors, and the Alma scrape gets three attempts.
- If one assignment fails to write, the rest still go through.
- Notion, Google Calendar, and the gradebook are separate steps, so a problem with one doesn't stop the others from being attempted.
- The Mac stays awake while a sync is running, and missed runs catch up after it wakes.
- Failures are written to a log and shown as a macOS notification.

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

Each run follows the same steps:

1. **Log in.** Playwright opens a headless browser and signs in to Alma with the password stored in the macOS Keychain.
2. **Scrape.** It finds every class on the schedule, then reads each class page for assignments, grades, and the class's current grade.
3. **Update the calendars.** Assignments due from 3 days ago onward go to Notion and Google Calendar. Each one is matched on its Alma assignment ID, so reruns update it instead of creating a duplicate.
4. **Rebuild the gradebook.** The Grades tab is cleared and rewritten from the full scrape, so it always matches Alma.

## Bugs fixed

- **The To Do list hides things.** Alma's To Do page drops an assignment as soon as it's graded, even on the day it's due. Scraping class pages fixed this, and it also made grades available.
- **Apple Calendar was blocked.** The first version wrote to Apple Calendar, but macOS kept denying calendar access to the background job. Moving to Notion and Google's web APIs removed that permission problem.
- **Notion Calendar has no alerts for database items.** Its reminders only work for Google Calendar events, so assignments are also copied to a Google calendar.
- **Laptops sleep.** A timer-based schedule kept missing runs, and sleep killed runs partway through. Fixed times, keeping the Mac awake during a run, and retries solved it.

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
  legacy/calendar_store.py      Old Apple Calendar writer, no longer used
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

## Bugs

If you happen to find a bug, please contact at ian.shin0316@gmail.com or ian.shin0316@seoulacademy.org.

## License

MIT. See [LICENSE](LICENSE).
