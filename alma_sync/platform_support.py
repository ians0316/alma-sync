"""The few things that work differently on macOS and Windows.

The macOS versions are here. On Windows, the versions in windows/windows_support.py
are used instead.

- Secrets: macOS Keychain, through the `security` tool.
- Notifications: macOS notification banners.
- Staying awake: launchd already wraps the job in `caffeinate`, so nothing to do.
- Dates: `%-d` (day without a leading zero) doesn't exist on Windows, so dates are
  built by hand on every platform.
"""
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "windows"))
    import windows_support as _windows


def get_secret(service: str, account: str) -> str:
    """Reads a saved password or token. Raises RuntimeError if it isn't saved."""
    if IS_WINDOWS:
        return _windows.get_secret(service, account)
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
        return _windows.save_secret(service, account, prompt)
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
            _windows.notify(title, message)
        elif sys.platform == "darwin":
            script = f"display notification {message!r} with title {title!r}"
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
    except Exception:
        pass


def keep_awake() -> None:
    """Keeps the computer awake until the sync finishes."""
    if IS_WINDOWS:
        _windows.keep_awake()


def short_date(d: date) -> str:
    """'Nov 7', on every platform."""
    return f"{d:%b} {d.day}"


def long_timestamp(t: datetime) -> str:
    """'Sat, Nov 7, 2026 at 3:05 PM', on every platform."""
    hour = t.hour % 12 or 12
    return f"{t:%a, %b} {t.day}, {t.year} at {hour}:{t:%M %p}"
