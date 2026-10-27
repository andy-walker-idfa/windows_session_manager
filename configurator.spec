# -*- mode: python ; coding: utf-8 -*-
# Build with:  python build.py   (runs PyInstaller with the right output folder for this OS)
import sys

from PyInstaller.utils.hooks import collect_data_files

windows = sys.platform == "win32"
excludes = [] if windows else ["platforms.windows", "win32ts", "wmi", "winreg"]

a = Analysis(
    ["run_configurator.py"],
    pathex=["."],
    datas=collect_data_files("customtkinter"),
    hiddenimports=["platforms.windows"] if windows else
                  (["platforms.macos"] if sys.platform == "darwin" else ["platforms.linux"]),
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="configurator",
    console=not windows,     # started with sudo from a terminal on Linux/macOS
    uac_admin=windows,       # needs to read instance.toml, which only administrators can read
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="configurator", upx=False)
