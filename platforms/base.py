"""Types shared by all OS adapters.

Every adapter module provides:

    get_sessions() -> list[Session]
    log_off(session: Session) -> None          # raises on failure
    notify(session: Session, message: str) -> None
    list_local_accounts() -> list[str]
    machine_id() -> str                        # stable per OS installation, "" if unknown
"""

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Session:
    account: str        # account name as reported by the OS
    session_id: object  # opaque to everything except the adapter that produced it
    active: bool        # in the foreground (not disconnected / switched away)
    locked: bool        # showing the lock screen


def run(args: list[str], timeout: float = 10) -> str:
    """Run a command and return stdout; raise RuntimeError with stderr on failure."""
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed ({result.returncode}): {result.stderr.strip()}")
    return result.stdout
