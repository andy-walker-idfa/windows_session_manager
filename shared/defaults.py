import sys
from pathlib import Path

app_name = "Time Manager"
__version__ = "2.0.0"

# Names inside the install folder.
instance_file = "instance.toml"
legacy_config_file = Path("config") / "limits.toml"


def get_install_root() -> Path:
    """Folder that holds instance.toml, data/ and logs/.

    PyInstaller one-folder build: <root>/tracker/tracker(.exe), so the root is one level above the
    executable's folder. From source: the repository folder.
    """
    if hasattr(sys, "_MEIPASS"):
        return Path(sys.executable).resolve().parent.parent
    return Path(__file__).resolve().parent.parent
