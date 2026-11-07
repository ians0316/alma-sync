"""The few things that work differently on macOS and Windows.

- Secrets: macOS Keychain (through the `security` tool) or Windows Credential
  Manager (through the `keyring` package).
- Notifications: macOS notification banners or Windows toast notifications.
- Staying awake during a run: launchd wraps the job in `caffeinate` on macOS;
  on Windows the job asks the system itself.
- Dates: `%-d` (day without a leading zero) only exists on macOS and Linux.
"""
import os
import subprocess
import sys
from datetime import date, datetime

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# Windows: keeps PowerShell from flashing a console window.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def get_secret(service: str, account: str) -> str:
    """Reads a saved password or token. Raises RuntimeError if it isn't saved."""
    if IS_WINDOWS:
        import keyring
        value = keyring.get_password(service, account)
        if not value:
            raise RuntimeError(
                f"Nothing saved in Windows Credential Manager for '{service}' (account '{account}'). "
                "Run: python sync.py --save-secrets"
            )
        return value
    result = subprocess.run(
        ["security", "find-generic-password", "-a", account, "-s", service, "-w"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Could not read '{service}' (account '{account}') from Keychain. "
            f"Add it in Keychain Access or run: python3 sync.py --save-secrets. Details: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def save_secret(service: str, account: str, prompt: str) -> None:
    """Asks for a secret in the terminal (without showing it) and saves it."""
    if IS_WINDOWS:
        import getpass
        import keyring
        value = getpass.getpass(f"{prompt}: ").strip()
        if not value:
            raise RuntimeError("Nothing was entered, so nothing was saved.")
        keyring.set_password(service, account, value)
        return
    # `security` asks for the value itself when -w comes last, so it never shows up
    # in the process list. -U replaces an item that already exists.
    print(f"{prompt} (type it twice when asked):")
    result = subprocess.run(["security", "add-generic-password", "-U", "-a", account, "-s", service, "-w"])
    if result.returncode != 0:
        raise RuntimeError(f"Keychain did not save '{service}'.")


def notify(title: str, message: str) -> None:
    """Shows a desktop notification. Never raises; a missed notification isn't worth a crash."""
    try:
        if IS_WINDOWS:
            _notify_windows(title, message)
        elif IS_MAC:
            script = f"display notification {message!r} with title {title!r}"
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
    except Exception:
        pass


# Title and message are passed through environment variables, so no text from them
# is ever run as PowerShell code. The app ID is Windows PowerShell's own, which lets
# the toast show without registering a new app.
_TOAST_SCRIPT = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$text = $xml.GetElementsByTagName('text')
$text.Item(0).AppendChild($xml.CreateTextNode($env:ALMA_TOAST_TITLE)) | Out-Null
$text.Item(1).AppendChild($xml.CreateTextNode($env:ALMA_TOAST_MESSAGE)) | Out-Null
$appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
"""


def _notify_windows(title: str, message: str) -> None:
    env = dict(os.environ, ALMA_TOAST_TITLE=title, ALMA_TOAST_MESSAGE=message)
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _TOAST_SCRIPT],
        env=env, capture_output=True, timeout=20, creationflags=_NO_WINDOW,
    )


def keep_awake() -> None:
    """Stops Windows from sleeping until this process exits. macOS uses caffeinate instead."""
    if IS_WINDOWS:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)


def short_date(d: date) -> str:
    """'Nov 7', on every platform."""
    return f"{d:%b} {d.day}"


def long_timestamp(t: datetime) -> str:
    """'Sat, Nov 7, 2026 at 3:05 PM', on every platform."""
    hour = t.hour % 12 or 12
    return f"{t:%a, %b} {t.day}, {t.year} at {hour}:{t:%M %p}"
