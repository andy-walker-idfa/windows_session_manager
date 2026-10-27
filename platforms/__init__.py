"""OS adapters. get_platform() returns the module for the running OS.

Imports are plain statements inside the selector, so PyInstaller still sees and bundles them, while
Linux and macOS never try to import the Windows-only pywin32 modules.
"""

import sys


def get_platform():
    if sys.platform == "win32":
        from platforms import windows
        return windows
    if sys.platform.startswith("linux"):
        from platforms import linux
        return linux
    if sys.platform == "darwin":
        from platforms import macos
        return macos
    raise RuntimeError(f"Unsupported operating system: {sys.platform}")


def os_name() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"
