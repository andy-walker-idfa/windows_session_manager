import argparse
import logging
from pathlib import Path
from tkinter import messagebox

from configurator.display import apply_scaling, patch_customtkinter
from configurator.gui import ConfiguratorApp
from platforms import get_platform
from shared import defaults
from shared.instance import InstanceAccessError, InstanceError, default_instance, load_instance
from shared.logging_setup import configure_logging


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=f"{defaults.app_name} configurator {defaults.__version__}")
    parser.add_argument("--root", type=Path, help="install folder holding instance.toml (default: auto)")
    args = parser.parse_args(argv)
    root = (args.root or defaults.get_install_root()).resolve()
    warning = ""
    try:
        instance = load_instance(root)
    except InstanceAccessError as e:
        messagebox.showerror(defaults.app_name, f"{e}\n\nRun the configurator as administrator (Windows) "
                                                "or with sudo (Linux/macOS).")
        return 1
    except InstanceError as e:
        # Still open, so the Connection tab can repair the settings.
        instance = default_instance(root)
        warning = f"The saved connection settings are not usable:\n{e}\n\nPlease set them on the Connection tab."
    configure_logging(instance.log_dir, "configurator")
    try:
        accounts = get_platform().list_local_accounts()
    except Exception as e:
        logging.warning(f"Could not list local accounts: {e}")
        accounts = []
    patch_customtkinter()
    scale = apply_scaling()
    app = ConfiguratorApp(instance, accounts, f"{defaults.app_name} {defaults.__version__}", warning)
    if scale != 1.0:
        # Standard Tk dialogs (file chooser, message boxes) use Tk's own scaling (pixels per point).
        app.tk.call("tk", "scaling", scale * 96 / 72)
    app.mainloop()
    return 0
