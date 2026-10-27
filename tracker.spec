# -*- mode: python ; coding: utf-8 -*-
# Build with:  python build.py   (runs PyInstaller with the right output folder for this OS)
import sys

windows = sys.platform == "win32"
# Keep other OSs' adapters out of the bundle so PyInstaller does not look for pywin32 on Linux/macOS.
excludes = [] if windows else ["platforms.windows", "win32ts", "wmi", "winreg"]

a = Analysis(
    ["run_tracker.py"],
    pathex=["."],
    hiddenimports=["platforms.windows"] if windows else
                  (["platforms.macos"] if sys.platform == "darwin" else ["platforms.linux"]),
    excludes=excludes + ["customtkinter", "tkinter", "configurator"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="tracker",
    console=not windows,  # no console window on Windows; plain service process elsewhere
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="tracker", upx=False)
