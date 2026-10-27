import logging
import logging.handlers
from pathlib import Path

_FORMAT = "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"


def configure_logging(log_dir: Path, name: str, level: str = "INFO") -> None:
    """Log to a rotating file (5 x 1 MB) and to the console."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.handlers.RotatingFileHandler(
            log_dir / f"{name}.log", maxBytes=1024 * 1024, backupCount=4, encoding="utf-8"))
    except OSError as e:
        print(f"Cannot write log files to {log_dir}: {e}")
    logging.basicConfig(level=level, format=_FORMAT, handlers=handlers, force=True)
    # The HTTP library logs every request at DEBUG; our own messages say what matters.
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def set_level(level: str) -> None:
    logging.getLogger().setLevel(level)
