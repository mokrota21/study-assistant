"""OS desktop notifications — the solo-mode gap fix (PRD §3.4.1, item 5).

When the user is working alone no hooks fire, because hooks need a message or a
tool call. The human is the one who needs the signal then, so the MCP server
pushes it out of band, through the OS.

Deliberately dependency-free: a failed notification must never take the study
block down with it, so every backend is best-effort and errors are swallowed
into a status string.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Optional

from .config import get_settings

_PS_TOAST = r"""
$ErrorActionPreference = 'Stop'
try {{
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType=WindowsRuntime] | Out-Null
    $xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
        [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $texts = $xml.GetElementsByTagName('text')
    $texts.Item(0).AppendChild($xml.CreateTextNode('{title}')) | Out-Null
    $texts.Item(1).AppendChild($xml.CreateTextNode('{message}')) | Out-Null
    $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier(
        '{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\WindowsPowerShell\v1.0\powershell.exe').Show($toast)
}} catch {{
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $icon = New-Object System.Windows.Forms.NotifyIcon
    $icon.Icon = [System.Drawing.SystemIcons]::Information
    $icon.Visible = $true
    $icon.ShowBalloonTip(10000, '{title}', '{message}', [System.Windows.Forms.ToolTipIcon]::Info)
    Start-Sleep -Seconds 7
    $icon.Dispose()
}}
{sound}
"""

_PS_SOUND = "[System.Media.SystemSounds]::Exclamation.Play(); Start-Sleep -Milliseconds 700"


def _escape_ps(text: str) -> str:
    return text.replace("'", "''").replace("\r", " ").replace("\n", " ")


def notify(title: str, message: str, sound: Optional[bool] = None) -> dict[str, object]:
    """Fire a desktop notification. Never raises."""
    settings = get_settings()
    if not settings.notifications_enabled:
        return {"sent": False, "reason": "notifications disabled in config"}
    play_sound = settings.notification_sound if sound is None else sound
    try:
        if sys.platform == "win32":
            return _notify_windows(title, message, play_sound)
        if sys.platform == "darwin":
            return _notify_macos(title, message, play_sound)
        return _notify_linux(title, message)
    except Exception as exc:  # pragma: no cover - platform dependent
        return {"sent": False, "reason": f"{type(exc).__name__}: {exc}"}


def _spawn(args: list[str]) -> None:
    """Detached, no console window, no waiting — the block clock must not stall."""
    kwargs: dict[str, object] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x08000000 | 0x00000008  # CREATE_NO_WINDOW | DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(args, **kwargs)  # type: ignore[arg-type]


def _notify_windows(title: str, message: str, sound: bool) -> dict[str, object]:
    script = _PS_TOAST.format(
        title=_escape_ps(title),
        message=_escape_ps(message),
        sound=_PS_SOUND if sound else "",
    )
    _spawn(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script])
    return {"sent": True, "backend": "powershell-toast"}


def _notify_macos(title: str, message: str, sound: bool) -> dict[str, object]:
    script = f'display notification "{message}" with title "{title}"'
    if sound:
        script += ' sound name "Glass"'
    _spawn(["osascript", "-e", script])
    return {"sent": True, "backend": "osascript"}


def _notify_linux(title: str, message: str) -> dict[str, object]:
    if not shutil.which("notify-send"):
        return {"sent": False, "reason": "notify-send not installed"}
    _spawn(["notify-send", title, message])
    return {"sent": True, "backend": "notify-send"}
