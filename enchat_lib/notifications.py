import sys
import subprocess
from shutil import which
from . import state


def _notify_macos(msg: str) -> None:
    """Pass notification text as data, never as executable AppleScript source."""
    subprocess.run(
        [
            "osascript",
            "-e", "on run argv",
            "-e", 'display notification (item 1 of argv) with title "Enchat"',
            "-e", "end run",
            "--",
            msg,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

def notify(msg: str):
    """Sends a desktop notification if notifications are enabled."""
    if not state.notifications_enabled:
        return
    
    if sys.platform.startswith("linux") and which("notify-send"):
        subprocess.run(["notify-send", "Enchat", msg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif sys.platform == "darwin" and which("osascript"):
        _notify_macos(msg)
    elif sys.platform == "win32":
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass

def notify_mention(msg: str):
    """Sends a desktop notification, bypassing the global notification setting."""
    if sys.platform.startswith("linux") and which("notify-send"):
        subprocess.run(["notify-send", "Enchat", msg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif sys.platform == "darwin" and which("osascript"):
        _notify_macos(msg)
    elif sys.platform == "win32":
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass
