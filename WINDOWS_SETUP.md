# Alma Sync on Windows

How to set up Alma Sync on a Windows PC. For a Mac, see the [main README](README.md). The rest of the project works the same on both.

## What's in the windows folder

| File | What it does |
|---|---|
| `windows_support.py` | Saves passwords in Windows Credential Manager, shows Windows notifications, and keeps the PC awake during a sync |
| `install_schedule.ps1` | Sets up a Task Scheduler task that runs the sync 5 minutes past every hour |
| `requirements.txt` | Python packages for Windows |

The sync code itself lives in the `alma_sync` folder. Keep the `windows` and `alma_sync` folders next to each other.

## Setup

1. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/). In the installer, tick **Add python.exe to PATH**.

2. Open PowerShell in the project folder (the one with `alma_sync` and `windows` in it) and install the dependencies:

   ```powershell
   python -m pip install -r windows\requirements.txt
   python -m playwright install chromium
   ```

3. In the `alma_sync` folder, copy `config.example.json` to `config.json` and fill it in.

4. Save your Alma password and Notion integration token in Windows Credential Manager:

   ```powershell
   python alma_sync\sync.py --save-secrets
   ```

   Nothing shows on screen while you type. That's normal.

5. Share the Notion database with your Notion integration.

6. For Google Calendar and Sheets, create a Google Cloud service account with the Calendar and Sheets APIs enabled. Save its JSON key as `C:\Users\<you>\.alma_sync\google-service-account.json`, then share the calendar and the spreadsheet with the service account's email. Google steps are skipped if this isn't set up.

7. Run it once by hand. A browser window opens so you can sign in to Alma:

   ```powershell
   python alma_sync\sync.py --setup
   ```

8. Install the hourly schedule:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\windows\install_schedule.ps1
   ```

## Using it

- Sync right away: `python alma_sync\sync.py`
- Check what happened: `C:\Users\<you>\.alma_sync\sync.log`
- See or change the schedule: open **Task Scheduler** and find **Alma Sync**.
- Remove the schedule:

  ```powershell
  Unregister-ScheduledTask -TaskName "Alma Sync" -Confirm:$false
  ```

The task only runs while the PC is on and you're signed in. Runs missed while it was asleep catch up after it wakes. Failures are logged and show a Windows notification.
