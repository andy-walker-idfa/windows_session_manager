"""Installation security checks, shown on the configurator's Connection tab.

The tracker runs as SYSTEM / root, so:
  * standard users must not be able to change the program folder (they could replace the program
    and run anything with full rights), and
  * standard users must not be able to read instance.toml (it holds the network store password).
"""

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from shared import defaults


@dataclass
class Issue:
    path: Path
    problem: str      # "writable" (folder) or "readable" (secret file)
    message: str


def tracker_command(root: Path) -> str:
    """What the scheduled task / service must run."""
    if hasattr(sys, "_MEIPASS"):
        name = "tracker.exe" if sys.platform == "win32" else "tracker"
        return str(root / "tracker" / name)
    python = Path(sys.executable)
    if sys.platform == "win32" and python.name.lower() == "python.exe":
        python = python.with_name("pythonw.exe")  # no console window
    return f'"{python}" "{root / "run_tracker.py"}"'


def _program_folders(root: Path) -> list[Path]:
    folders = [root]
    if hasattr(sys, "_MEIPASS"):
        folders += [root / "tracker", root / "configurator"]
    return [f for f in folders if f.exists()]


# ----- Windows ---------------------------------------------------------------------------------
# Groups that include standard users. Everything else (SYSTEM, Administrators, TrustedInstaller,
# CREATOR OWNER placeholders) is trusted.
_UNTRUSTED_SIDS = {
    "S-1-1-0": "Everyone",
    "S-1-5-11": "Authenticated Users",
    "S-1-5-32-545": "Users",
    "S-1-5-4": "INTERACTIVE",
    "S-1-5-32-546": "Guests",
}
_WRITE_BITS = 0x0002 | 0x0004 | 0x00010000 | 0x00040000 | 0x00080000 | 0x40000000 | 0x10000000
#             write data, append, DELETE, WRITE_DAC, WRITE_OWNER, GENERIC_WRITE, GENERIC_ALL
_READ_BITS = 0x0001 | 0x80000000 | 0x10000000   # read data, GENERIC_READ, GENERIC_ALL
_INHERIT_ONLY = 0x08


def _windows_untrusted_access(path: Path, bits: int) -> list[str]:
    import win32security
    descriptor = win32security.GetFileSecurity(str(path), win32security.DACL_SECURITY_INFORMATION)
    dacl = descriptor.GetSecurityDescriptorDacl()
    if dacl is None:
        return ["Everyone (no access list at all)"]
    found = []
    for i in range(dacl.GetAceCount()):
        (ace_type, ace_flags), mask, sid = dacl.GetAce(i)[:3]
        if ace_type != win32security.ACCESS_ALLOWED_ACE_TYPE or ace_flags & _INHERIT_ONLY:
            continue
        name = _UNTRUSTED_SIDS.get(win32security.ConvertSidToStringSid(sid))
        if name and mask & bits:
            found.append(name)
    return sorted(set(found))


def _windows_issues(root: Path) -> list[Issue]:
    issues = []
    for folder in _program_folders(root):
        who = _windows_untrusted_access(folder, _WRITE_BITS)
        if who:
            issues.append(Issue(folder, "writable", f"{folder} can be changed by {', '.join(who)}"))
    secret = root / defaults.instance_file
    if secret.exists():
        who = _windows_untrusted_access(secret, _READ_BITS)
        if who:
            issues.append(Issue(secret, "readable", f"{secret.name} (network password) can be read by {', '.join(who)}"))
    return issues


def _icacls(path: Path, *args: str) -> None:
    result = subprocess.run(["icacls", str(path), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise OSError(f"icacls {path} failed: {(result.stdout + result.stderr).strip()}")


def _windows_fix(issue: Issue) -> None:
    system, admins, users = "*S-1-5-18", "*S-1-5-32-544", "*S-1-5-32-545"
    untrusted = [f"*{sid}" for sid in _UNTRUSTED_SIDS]
    if issue.problem == "readable":
        # Own access list: SYSTEM and Administrators only, nothing inherited, no other entries.
        _icacls(issue.path, "/inheritance:r")
        _icacls(issue.path, "/remove:g", *untrusted)
        _icacls(issue.path, "/grant:r", f"{system}:F", f"{admins}:F")
        return
    # Folder: SYSTEM and Administrators may change it, standard users may only read and run it.
    _icacls(issue.path, "/inheritance:r")
    _icacls(issue.path, "/remove:g", *untrusted)
    _icacls(issue.path, "/grant:r", f"{system}:(OI)(CI)F", f"{admins}:(OI)(CI)F", f"{users}:(OI)(CI)RX")
    # Everything inside goes back to inheriting from the folder only (drops stray explicit entries).
    # fix_all() locks instance.toml down again afterwards.
    if any(issue.path.iterdir()):
        _icacls(issue.path / "*", "/reset", "/T", "/C", "/Q")


# ----- Linux / macOS ---------------------------------------------------------------------------
def _posix_issues(root: Path) -> list[Issue]:
    issues = []
    for folder in _program_folders(root):
        st = folder.stat()
        if st.st_uid != 0 or st.st_mode & 0o022:
            issues.append(Issue(folder, "writable", f"{folder} is not owned by root or can be changed by other users"))
    secret = root / defaults.instance_file
    if secret.exists():
        st = secret.stat()
        if st.st_uid != 0 or st.st_mode & 0o077:
            issues.append(Issue(secret, "readable", f"{secret.name} (network password) is not readable by root only"))
    return issues


def _posix_fix(issue: Issue) -> None:
    if issue.problem == "readable":
        os.chown(issue.path, 0, 0)
        os.chmod(issue.path, 0o600)
        return
    for current, dirs, files in os.walk(issue.path):
        for name in [current, *(os.path.join(current, f) for f in files)]:
            os.chown(name, 0, 0)
            mode = os.stat(name).st_mode
            os.chmod(name, mode & ~0o022)
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(current, d))]


# ----- public ----------------------------------------------------------------------------------
def find_issues(root: Path) -> list[Issue]:
    return _windows_issues(root) if sys.platform == "win32" else _posix_issues(root)


def fix_issue(issue: Issue) -> None:
    if sys.platform == "win32":
        _windows_fix(issue)
    else:
        _posix_fix(issue)


def protect_secret_file(path: Path) -> None:
    """Make instance.toml readable by SYSTEM/Administrators or root only."""
    fix_issue(Issue(path, "readable", ""))


def fix_all(root: Path) -> list[Issue]:
    """Fix every issue and return what is still wrong afterwards.

    Folders first: fixing a folder re-applies permissions to everything in it, so the password
    file is locked down again at the end.
    """
    for issue in find_issues(root):
        if issue.problem == "writable":
            fix_issue(issue)
    secret = root / defaults.instance_file
    if secret.exists():
        protect_secret_file(secret)
    return find_issues(root)
