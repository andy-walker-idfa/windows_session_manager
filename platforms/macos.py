"""macOS adapter: console users from the IORegistry, logoff through launchctl.

IOConsoleUsers lists every logged in GUI user. kCGSSessionOnConsoleKey marks the one on screen
(others are switched away by fast user switching), CGSSessionScreenIsLocked marks the lock screen.
"""

import plistlib
import pwd
import re
import subprocess

from platforms.base import Session, run


def _console_users() -> list[dict]:
    data = plistlib.loads(run(["ioreg", "-n", "Root", "-d1", "-a"]).encode("utf-8"))
    entries = data if isinstance(data, list) else [data]
    users = []
    for entry in entries:
        users.extend(entry.get("IOConsoleUsers", []) or [])
    return users


def get_sessions() -> list[Session]:
    sessions = []
    for user in _console_users():
        name = user.get("kCGSSessionUserNameKey")
        uid = user.get("kCGSSessionUserIDKey")
        if not name or uid is None or not user.get("kCGSessionLoginDoneKey", True):
            continue
        sessions.append(Session(
            account=name,
            session_id=int(uid),
            active=bool(user.get("kCGSSessionOnConsoleKey", False)),
            locked=bool(user.get("CGSSessionScreenIsLocked", False)),
        ))
    return sessions


def log_off(session: Session) -> None:
    run(["launchctl", "bootout", f"gui/{session.session_id}"], timeout=30)


_dialogs: list[subprocess.Popen] = []


def _applescript_text(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def notify(session: Session, title: str, message: str, seconds: int) -> None:
    """Show a dialog in the user's GUI session that closes itself after `seconds`. Does not wait.

    The tracker runs as root (LaunchDaemon); `launchctl asuser` + `sudo -u` run osascript in the
    user's login session, where it may show windows.
    """
    for done in [p for p in _dialogs if p.poll() is not None]:  # reap dialogs that have closed
        _dialogs.remove(done)
    script = (f"display dialog {_applescript_text(message)} with title {_applescript_text(title)} "
              f'buttons {{"OK"}} default button "OK" with icon caution giving up after {int(seconds)}')
    _dialogs.append(subprocess.Popen(
        ["launchctl", "asuser", str(session.session_id), "sudo", "-u", session.account,
         "osascript", "-e", script],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))


def list_local_accounts() -> list[str]:
    return sorted(p.pw_name for p in pwd.getpwall() if p.pw_uid >= 501 and not p.pw_name.startswith("_"))


def machine_id() -> str:
    try:
        output = run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"])
    except (RuntimeError, OSError):
        return ""
    match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', output)
    return match.group(1) if match else ""
