## Alma Sync + Calendar Integration

> [!IMPORTANT]
> **Alma Sync is an unofficial student project.** It is not made, supported, or approved by Alma
> or Seoul Academy. It signs in with your own Alma account and only reads your pages, but Alma can
> change its website at any time and break the sync, so always double-check due dates in Alma itself.
> Your password stays in your computer's password store (macOS Keychain or Windows Credential Manager) and is never put in this repo.

> [!WARNING]
> Only works with **student** Alma accounts. Parent and teacher accounts are not supported.

Alma Sync is a tool that adds convenient features for Seoul Academy students using Alma and technically everyone who uses Alma to calendar. Its purpose is to provide comfortable environment through putting todo assignments into calendar. It Keeps school assignments and grades up to date outside the Alma portal (seoulacademy.getalma.com). A background sync on a Mac or Windows PC reads every class page & todo list in Alma once an hour and sends the data to Notion, Google Calendar, and Google Sheets.

## Setup and Installation (macOS)

> [!NOTE]
> **On Windows?** Follow the [Windows setup guide](WINDOWS_SETUP.md) instead. The steps below are for macOS.

Needs **Python 3.10 or newer**.

1. Install the dependencies:

   ```sh
   cd alma_sync
   python3 -m pip install -r requirements.txt
   python3 -m playwright install chromium
   ```

2. Copy `config.example.json` to `config.json` and fill it in.

3. Save your Alma password and Notion integration token in the Keychain:

   ```sh
   python3 sync.py --save-secrets
   ```

   Or add them by hand in Keychain Access, in the **login** keychain (not iCloud):

   | Keychain item name | Account name | Password |
   |---|---|---|
   | `AlmaPortal` | your Alma username | your Alma password |
   | `NotionToken` | `notion` | your Notion integration token |

4. Share the Notion database with your Notion integration.

5. For Google Calendar and Sheets, create a Google Cloud service account with the Calendar and
   Sheets APIs turned on. Save its JSON key as `~/.alma_sync/google-service-account.json`, then share
   the calendar and the spreadsheet with the service account's email. Google steps are skipped if
   this isn't set up.

6. Run it once by hand, then install the hourly schedule:

   ```sh
   python3 sync.py --setup
   ./install_schedule.sh
   ```

## Why this exists

Alma is where teachers post assignments, change due dates and enter grades, but it has no calendar
feed to subscribe to and no due-date alerts. Checking it means logging in and reading a list that
keeps changing. Alma Sync puts assignments on a calendar automatically, at the time of the class
they're due in, and keeps every grade in one organized place.

## What it does

| Destination | What it gets | Why |
|---|---|---|
| **Notion database** | Recent and upcoming assignments at their class period time | Main calendar view in Notion Calendar |
| **Google Calendar** | The same assignments | Alerts, which Notion Calendar only sends for Google events |
| **Google Sheets** | Every assignment and grade, grouped by class | A gradebook with a recently graded section |

## How it works

Once an hour (5 minutes past), on its own, in four steps:

1. **Log in:** a headless browser signs in to Alma with the password from your Keychain or Credential Manager.
2. **Read:** it finds every class on your schedule and reads each class page for assignments, grades and the current grade.
3. **Update calendars:** assignments due from 3 days ago onward go to Notion and Google Calendar, matched on their Alma ID so reruns update instead of duplicating.
4. **Rebuild the gradebook:** the Grades tab is cleared and rewritten from the full read, so it always matches Alma.

```
Alma class pages
      |  Playwright (headless Chromium)
      v
   sync.py  (launchd or Task Scheduler, 5 minutes past every hour)
      |
      +--> notion_store.py   --> Notion database
      +--> google_store.py   --> Google Calendar
      +--> grades_sheet.py   --> Google Sheets "Grades" tab
```

## Features

### Calendar

- New assignments appear automatically, and changed due dates update in place.
- Each assignment sits at its real class period time instead of an all-day block.
- Past assignments stay as a record. The sync **never deletes** anything from Notion or Google Calendar.
- The Done checkbox in Notion is left alone, so checking off an assignment sticks.
- Google Calendar sends alerts from its own servers, so synced assignments still alert while the computer sleeps.

### Your own tasks (from Alma+)

- Tasks you add in the [Alma+](https://github.com/ians0316/alma-plus) Chrome extension also go to Notion and Google Calendar, **within seconds** of adding or editing them.
- They sit at their class period time like assignments; tasks without a class are all-day, and multi-day tasks span their days. The description goes in the event notes.
- Like assignments, they're never deleted.
- One-time setup on macOS: run `./install_task_bridge.sh` in the `alma_sync` folder. The hourly sync includes them too.

### Gradebook

- A "Last updated" line shows when the data was refreshed.
- A summary table lists each class's current grade, how many assignments are graded, not graded yet or upcoming, and the lowest score so far.
- **Recently graded** lists everything graded in the last 7 days, newest first.
- Each class gets its own color-coded section with every assignment's due date, status, grade, score, points, weight, teacher comment and graded date.
- Low scores are highlighted red and high scores green.

### Reliability

- Requests retry on timeouts and server errors, and the Alma read gets three attempts.
- If one assignment fails to write, the rest still go through.
- Notion, Google Calendar and the gradebook are separate steps, so one problem doesn't stop the others.
- The computer stays awake during a sync, and missed runs catch up after it wakes.
- Failures go to a log and show as a desktop notification.

## Using this program

```sh
python3 sync.py                              # sync right away (python sync.py on Windows)
python3 sync.py --tasks-only                 # sync only your Alma+ tasks (log: tasks_sync.log)
python3 sync.py --dump assignments.json      # export assignments to a file without syncing
```

What happened is in `sync.log` in the `.alma_sync` folder in your home folder. The job only runs
while the computer is awake and catches up after it wakes.

### Adapting it to another school

Class period times are set in `PERIOD_TIMES` in `alma_scraper.py`. Change them to your school's
bell schedule, and set `base_url` in `config.json`.

## Structure

Four parts that work together, each one replaceable:

- **Scraper** (`alma_scraper.py`) signs in to Alma and reads every class page for assignments, due dates and grades.
- **Writers** (`notion_store.py`, `google_store.py`, `grades_sheet.py`) send that data to Notion, Google Calendar and Google Sheets. Each one runs on its own.
- **Runner** (`sync.py`) runs the scraper, then each writer in order, and logs the result.
- **Schedule** (`install_schedule.sh` on macOS, `windows/install_schedule.ps1` on Windows) sets up a launchd job or Task Scheduler task that runs once an hour.

`platform_support.py` (plus `windows/windows_support.py`) handles what differs between macOS and
Windows: saved passwords, notifications and keeping the computer awake.

## Project layout

```
alma_sync/
  sync.py                       Runs one full sync
  alma_scraper.py               Alma login and class page scraping
  notion_store.py               Writes to Notion
  google_store.py               Writes to Google Calendar
  grades_sheet.py               Rebuilds the Grades tab
  tasks_bridge.py               Receives tasks from the Alma+ extension
  install_task_bridge.sh        One-time setup so Chrome can hand tasks over
  config.example.json           Template for config.json
  requirements.txt              Python packages
  platform_support.py           macOS and Windows differences
  install_schedule.sh           Installs the hourly job on macOS
  com.alma.sync.plist.template  launchd job template
  legacy/calendar_store.py      Old Apple Calendar writer, no longer used
WINDOWS_SETUP.md                Windows setup guide
windows/
  windows_support.py            Windows passwords, notifications, staying awake
  install_schedule.ps1          Installs the hourly Task Scheduler task
  requirements.txt              Python packages for Windows
```

## Bugs fixed

- **The To Do list hides things.** Alma's To Do page drops an assignment as soon as it's graded, even on the day it's due. Scraping class pages fixed this, and it also made grades available.
- **Apple Calendar was blocked.** The first version wrote to Apple Calendar, but macOS kept denying calendar access to the background job. Moving to Notion and Google's web APIs removed that permission problem.
- **Notion Calendar has no alerts for database items.** Its reminders only work for Google Calendar events, so assignments are also copied to a Google calendar.
- **Laptops sleep.** A timer-based schedule kept missing runs, and sleep killed runs partway through. Fixed times, keeping the Mac awake during a run, and retries solved it.

## Status

> [!IMPORTANT]
> **Status:** used every day at Seoul Academy.
>
> - **Works today:** hourly sync to Notion, Google Calendar and Google Sheets on macOS and Windows;
>   Alma+ task sync on macOS.
> - **Limits:** runs only while the computer is awake (it catches up after); if Alma changes its
>   pages, the scraper may need an update.
> - **Other schools:** works with any `getalma.com` site after changing the bell schedule.

## Privacy

Passwords and tokens live in the macOS Keychain or Windows Credential Manager, and the Google key
lives in the `.alma_sync` folder in your home folder. `config.json`, exported data and logs are
never part of this repo.

## Contributing

Want to help? See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for how to report bugs, suggest features and make changes.

## Report a bug

If you happen to find a bug, please contact at ian.shin0316@gmail.com or ian.shin0316@seoulacademy.org.

## License

[MIT](LICENSE). Copyright (c) 2026 ians0316.

<p align="center">
  <sub>Made by a Seoul Academy student, for Seoul Academy students. Not affiliated with Alma or Seoul Academy.</sub>
</p>
