"""Tracker entry point: runs forever as a SYSTEM / root service, one cycle per check interval."""

import argparse
import logging
import time
from pathlib import Path

from platforms import get_platform, os_name
from shared import defaults
from shared.instance import (InstanceError, build_remote_store, instance_mtime, load_instance,
                             load_writer_identity)
from shared.logging_setup import configure_logging
from storage.folder import FolderStore
from tracker.cycle import Tracker
from tracker.sync import Repository

SEED_CONFIG = "seed-limits.toml"
RETRY_SECONDS = 60


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=f"{defaults.app_name} tracker {defaults.__version__}")
    parser.add_argument("--root", type=Path, help="install folder holding instance.toml (default: auto)")
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="log decisions but never log anyone off")
    return parser.parse_args(argv)


def build_tracker(root: Path, dry_run: bool) -> Tracker:
    instance = load_instance(root)
    configure_logging(instance.log_dir, "tracker")
    logging.info(f"{defaults.app_name} tracker {defaults.__version__} starting, install folder {root}")
    platform = get_platform()
    local = FolderStore(instance.data_dir)
    remote = build_remote_store(instance.remote)
    logging.info(f"Local store: {local.describe()}; network store: {remote.describe() if remote else 'none'}")
    identity = load_writer_identity(local, os_name(), platform.machine_id())
    repo = Repository(local, remote, identity.writer_id)
    # A seed placed by the installer, or the config of a 1.x installation, if nothing is cached yet.
    for seed in (root / SEED_CONFIG, root / defaults.legacy_config_file):
        repo.import_seed_config(seed)
    return Tracker(platform, repo, identity, os_name(), dry_run=dry_run)


def main(argv=None) -> int:
    args = parse_args(argv)
    root = (args.root or defaults.get_install_root()).resolve()
    while True:
        try:
            tracker = build_tracker(root, args.dry_run)
            break
        except InstanceError as e:
            configure_logging(root / "logs", "tracker")
            logging.error(f"{e}. Fix instance.toml; retrying in {RETRY_SECONDS} s.")
        except Exception:
            logging.exception(f"Tracker failed to start; retrying in {RETRY_SECONDS} s.")
        if args.once:
            return 1
        time.sleep(RETRY_SECONDS)

    interval = 5
    settings_mtime = instance_mtime(root)
    while True:
        # Connection settings saved in the configurator take effect at the next cycle.
        if instance_mtime(root) != settings_mtime:
            settings_mtime = instance_mtime(root)
            try:
                tracker = build_tracker(root, args.dry_run)
                logging.info("instance.toml changed: reconnected with the new settings.")
            except Exception:
                logging.exception("instance.toml changed but cannot be used; keeping the previous settings.")
        try:
            interval = tracker.run_cycle().interval_minutes
        except Exception:
            logging.exception("Tracker cycle failed; trying again next cycle.")
        if args.once:
            return 0
        time.sleep(interval * 60)
