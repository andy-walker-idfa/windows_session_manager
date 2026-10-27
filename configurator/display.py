"""Display fixes for the configurator: screen scaling on Linux and a customtkinter scroll bug.

On Windows and macOS customtkinter follows the system's display scaling by itself. On Linux it does
not, and a configurator started with sudo does not even see the desktop's scale settings, so on a
high resolution screen everything is tiny. We read the scale the desktop announces to X programs
(Xft.dpi, e.g. 192 for 200 %) and apply it. TM_UI_SCALE=1.5 (or similar) overrides it.
"""

import logging
import os
import re
import shutil
import subprocess
import sys


def _xft_dpi() -> float | None:
    if not shutil.which("xrdb"):
        return None
    try:
        output = subprocess.run(["xrdb", "-query"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"^Xft\.dpi:\s*([\d.]+)", output, re.MULTILINE)
    return float(match.group(1)) if match else None


def _screen_dpi() -> float | None:
    """Physical screen density as Tk sees it, if the desktop does not announce a scale."""
    try:
        import tkinter
        root = tkinter.Tk()
        root.withdraw()
        dpi = root.winfo_fpixels("1i")
        root.destroy()
        return dpi
    except Exception:
        return None


def detect_scale() -> float:
    override = os.environ.get("TM_UI_SCALE")
    if override:
        try:
            return max(0.5, min(4.0, float(override)))
        except ValueError:
            logging.warning(f"Ignoring TM_UI_SCALE={override!r}: not a number")
    if not sys.platform.startswith("linux"):
        return 1.0  # customtkinter handles Windows and macOS itself
    dpi = _xft_dpi() or _screen_dpi() or 96.0
    scale = round((dpi / 96.0) * 4) / 4  # steps of 25 %
    return max(1.0, min(4.0, scale))


def apply_scaling() -> float:
    """Call before the window is created. Returns the factor used (1.0 = unchanged)."""
    import customtkinter
    scale = detect_scale()
    if scale != 1.0:
        customtkinter.set_widget_scaling(scale)
        customtkinter.set_window_scaling(scale)
    logging.info(f"Display scale {scale:g}")
    return scale


def patch_customtkinter() -> None:
    """Work around two customtkinter problems. Call before any widget is created.

    1. On Linux customtkinter draws rounded corners with a font it copies into ~/.fonts at start-up.
       Tk only sees that font after the font cache is rebuilt, so the corners appear as broken
       glyphs (stray boxes around every field). Draw them as polygons instead, as on macOS.
    2. Its scrollable frame handles every mouse wheel event in the application. Over plain Tk
       elements (option menu lists, file dialogs) the event carries a widget *name* instead of a
       widget, and customtkinter raises AttributeError. Ignore those events.
    """
    try:
        from customtkinter.windows.widgets import ctk_scrollable_frame
        from customtkinter.windows.widgets.core_rendering import DrawEngine
    except ImportError:
        return
    if sys.platform.startswith("linux"):
        DrawEngine.preferred_drawing_method = "polygon_shapes"
    cls = ctk_scrollable_frame.CTkScrollableFrame
    original = getattr(cls, "_mouse_wheel_all", None)
    if original is None or getattr(original, "_tm_patched", False):
        return

    def mouse_wheel_all(self, event):
        if isinstance(getattr(event, "widget", None), str):
            return None
        return original(self, event)

    mouse_wheel_all._tm_patched = True
    cls._mouse_wheel_all = mouse_wheel_all
