"""Windows versions of the things that differ from macOS.

alma_sync/platform_support.py loads this file when the sync runs on Windows.

- Secrets: Windows Credential Manager, through the `keyring` package.
- Notifications: Windows toast notifications, through PowerShell.
- Staying awake: asks Windows not to sleep until the sync finishes.
"""
import getpass
import os
import subprocess

# Keeps PowerShell from flashing a console window.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def get_secret(service: str, account: str) -> str:
    import keyring
    value = keyring.get_password(service, account)
    if not value:
        raise RuntimeError(
            f"Nothing saved in Windows Credential Manager for '{service}' (account '{account}'). "
            "Run: python sync.py --save-secrets"
        )
    return value


def save_secret(service: str, account: str, prompt: str) -> None:
    import keyring
    value = getpass.getpass(f"{prompt}: ").strip()
    if not value:
        raise RuntimeError("Nothing was entered, so nothing was saved.")
    keyring.set_password(service, account, value)


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


def notify(title: str, message: str) -> None:
    env = dict(os.environ, ALMA_TOAST_TITLE=title, ALMA_TOAST_MESSAGE=message)
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _TOAST_SCRIPT],
        env=env, capture_output=True, timeout=20, creationflags=_NO_WINDOW,
    )


def keep_awake() -> None:
    """Stops Windows from sleeping until this process exits."""
    import ctypes
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
