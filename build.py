"""Build Time Manager for the current OS and package it as a release zip.

    python build.py

Result:
    dist/<os>/TimeManager/                     ready to copy to the install folder
    dist/TimeManager-<version>-<os>.zip        the same folder, for publishing

PyInstaller cannot cross-compile, so run this once on each OS.
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from shared.defaults import __version__  # noqa: E402

OS_NAME = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
DIST = ROOT / "dist" / OS_NAME / "TimeManager"
# Service definition template for Linux / macOS (the Windows scheduled task is described in README.md).
SERVICE_TEMPLATE = {"linux": "timemanager-tracker.service", "macos": "local.timemanager.tracker.plist"}.get(OS_NAME)


def check_tkinter() -> bool:
    """The configurator needs Tk. Without it PyInstaller silently builds a GUI that cannot start."""
    try:
        import tkinter
        tkinter.Tcl()
        return True
    except Exception as e:
        print(f"\nERROR: Tk (tkinter) is not usable in this Python: {e}\n"
              "Install it, then run build.py again:\n"
              "  Debian/Ubuntu: sudo apt install python3-tk\n"
              "  Fedora:        sudo dnf install python3-tkinter\n"
              "  Arch:          sudo pacman -S tk\n"
              "  macOS:         Homebrew Python: brew install python-tk@3.X (X = your Python version);\n"
              "                 or use Python from python.org, which includes Tk\n")
        return False


def main() -> int:
    if not check_tkinter():
        return 1
    for spec in ("tracker.spec", "configurator.spec"):
        result = subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                                 "--distpath", str(DIST), "--workpath", str(ROOT / "build" / OS_NAME), spec],
                                cwd=ROOT)
        if result.returncode != 0:
            return result.returncode
    shutil.copy2(ROOT / "README.md", DIST / "README.md")
    if SERVICE_TEMPLATE:
        shutil.copy2(ROOT / "service" / SERVICE_TEMPLATE, DIST / SERVICE_TEMPLATE)
    archive = shutil.make_archive(str(ROOT / "dist" / f"TimeManager-{__version__}-{OS_NAME}"), "zip",
                                  root_dir=DIST.parent, base_dir=DIST.name)
    print(f"\nBuilt into {DIST}\nRelease zip: {archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
