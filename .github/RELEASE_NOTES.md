First release of Alma Sync.

## Features
- **Notion:** every Alma assignment becomes a row in your Notion database, with class, due date and status. It updates every hour.
- **Google Calendar:** assignments show up as all-day events on their due dates.
- **Google Sheets:** a Grades tab with every class's current grade, rebuilt after each sync.
- **Alma+ tasks:** your own tasks from the Alma+ extension reach Notion and Google Calendar within seconds of adding or editing them.
- **Runs by itself:** a background job checks Alma once an hour on macOS (launchd) or Windows (Task Scheduler), and catches up after the computer wakes.
- **Never deletes:** it only adds and updates rows and events, so nothing you made by hand is removed.

## Privacy
- Your Alma password and Notion token stay in your computer's password store (macOS Keychain or Windows Credential Manager), never in files.
- `config.json`, exported data and logs are never uploaded to GitHub.
- It only reads from Alma; it never submits or changes anything there.

## Install
Follow **Setup** in the README, or `WINDOWS_SETUP.md` on Windows.

> ⚠️ Works only with **student** Alma accounts.
