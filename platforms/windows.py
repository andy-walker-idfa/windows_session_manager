"""Windows adapter: Terminal Services API for sessions, LogonUI.exe presence for locked sessions."""

import json
import logging
import subprocess
import winreg

import win32ts
import wmi

from platforms.base import Session

_SERVER = win32ts.WTS_CURRENT_SERVER_HANDLE


def get_sessions() -> list[Session]:
    # LogonUI.exe runs inside a session while it shows the lock screen.
    locked_ids = {int(p.SessionId) for p in wmi.WMI().Win32_Process(Name="LogonUI.exe")}
    sessions = []
    for s in win32ts.WTSEnumerateSessions(_SERVER):
        session_id = s["SessionId"]
        account = win32ts.WTSQuerySessionInformation(_SERVER, session_id, win32ts.WTSUserName)
        if not account:
            continue  # services session, login screen, listener
        sessions.append(Session(
            account=account,
            session_id=session_id,
            active=s["State"] == win32ts.WTSActive,
            locked=session_id in locked_ids,
        ))
    return sessions


def log_off(session: Session) -> None:
    win32ts.WTSLogoffSession(_SERVER, session.session_id, False)


def notify(session: Session, message: str) -> None:
    """Not implemented yet: warnings before logoff are a planned feature."""


def list_local_accounts() -> list[str]:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-LocalUser | Where-Object Enabled | Select-Object -ExpandProperty Name | ConvertTo-Json"],
        capture_output=True, text=True, timeout=30,
    )
    try:
        names = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        logging.error(f"Could not list local accounts: {result.stderr.strip()}")
        return []
    return [names] if isinstance(names, str) else list(names)


def machine_id() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            return str(winreg.QueryValueEx(key, "MachineGuid")[0])
    except OSError:
        return ""
