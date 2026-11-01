"""Linux adapter: systemd-logind through loginctl. Only local graphical sessions are counted."""

import pwd
import shutil
from pathlib import Path

from platforms.base import Session, run

_GRAPHICAL_TYPES = {"x11", "wayland", "mir"}
_NO_LOGIN_SHELLS = ("nologin", "false")


def _show_session(session_id: str) -> dict:
    output = run(["loginctl", "show-session", session_id,
                  "-p", "Name", "-p", "Active", "-p", "LockedHint", "-p", "Class",
                  "-p", "Type", "-p", "Remote", "-p", "State"])
    props = {}
    for line in output.splitlines():
        key, _, value = line.partition("=")
        props[key] = value
    return props


def get_sessions() -> list[Session]:
    output = run(["loginctl", "list-sessions", "--no-legend", "--no-pager"])
    sessions = []
    for line in output.splitlines():
        fields = line.split()
        if not fields:
            continue
        session_id = fields[0]
        try:
            props = _show_session(session_id)
        except RuntimeError:
            continue  # session ended between list and show
        if props.get("Class") != "user" or props.get("Type") not in _GRAPHICAL_TYPES:
            continue
        if props.get("Remote") == "yes" or props.get("State") == "closing":
            continue
        sessions.append(Session(
            account=props.get("Name", ""),
            session_id=session_id,
            active=props.get("Active") == "yes",
            locked=props.get("LockedHint") == "yes",
        ))
    return sessions


def log_off(session: Session) -> None:
    run(["loginctl", "terminate-session", str(session.session_id)])


def notify(session: Session, title: str, message: str, seconds: int) -> None:
    """Show a desktop notification in the user's session (GNOME, KDE, ...).

    The tracker runs as root, so the notification is sent as the user, to the user's session D-Bus.
    notify-send is used if installed, otherwise gdbus (part of GLib, present on GNOME and KDE).
    """
    user = pwd.getpwnam(session.account)
    bus = f"unix:path=/run/user/{user.pw_uid}/bus"
    as_user = ["runuser", "-u", session.account, "--", "env", f"DBUS_SESSION_BUS_ADDRESS={bus}"]
    if shutil.which("notify-send"):
        command = [*as_user, "notify-send", "--urgency=critical", "--app-name=Time Manager",
                   f"--expire-time={seconds * 1000}", title, message]
    else:
        command = [*as_user, "gdbus", "call", "--session", "--dest", "org.freedesktop.Notifications",
                   "--object-path", "/org/freedesktop/Notifications",
                   "--method", "org.freedesktop.Notifications.Notify",
                   "Time Manager", "0", "dialog-warning", title, message, "[]", "{'urgency': <byte 2>}",
                   str(seconds * 1000)]
    run(command, timeout=10)


def list_local_accounts() -> list[str]:
    return sorted(
        p.pw_name for p in pwd.getpwall()
        if 1000 <= p.pw_uid < 65534 and not p.pw_shell.endswith(_NO_LOGIN_SHELLS)
    )


def machine_id() -> str:
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            continue
    return ""
