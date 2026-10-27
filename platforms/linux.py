"""Linux adapter: systemd-logind through loginctl. Only local graphical sessions are counted."""

import pwd
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


def notify(session: Session, message: str) -> None:
    """Not implemented yet: warnings before logoff are a planned feature."""


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
