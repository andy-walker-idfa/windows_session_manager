"""Local store, network store and the rules for moving data between them.

Local store layout (data/ next to the executable):
    records/<own writer>/<date>.json        this installation's usage, always written here first
    cache/records/<writer>/<date>.json      last good copy of other writers' records
    cache/config/limits.toml                last valid shared config (or the seed from install)
    state/instance.json                     writer id + fingerprint
    state/dirty.json                        own record keys not yet pushed to the network

Network store layout:
    config/limits.toml
    records/<writer>/<date>.json
    writers/<writer>.json
"""

import datetime
import json
import logging

from core.config import ConfigError, MAX_CONFIG_BYTES, parse_config
from core.usage import MAX_RECORD_BYTES, DailyRecord, NewerSchemaError, RecordError, parse_record, serialize_record
from storage.base import Store, StoreError
from storage.folder import FolderStore

CONFIG_KEY = "config/limits.toml"
CONFIG_CACHE_KEY = "cache/config/limits.toml"
DIRTY_KEY = "state/dirty.json"

EMPTY_CONFIG = {"schema": 1, "revision": 0, "defaults": {}, "users": {}}


def record_key(writer_id: str, date: str) -> str:
    return f"records/{writer_id}/{date}.json"


def cache_record_key(writer_id: str, date: str) -> str:
    return f"cache/{record_key(writer_id, date)}"


class Repository:
    def __init__(self, local: FolderStore, remote: Store | None, writer_id: str):
        self.local = local
        self.remote = remote
        self.writer_id = writer_id
        self._warned: set[tuple] = set()
        self._dirty = self._load_dirty()

    # ----- helpers -------------------------------------------------------------------------
    def _warn_once(self, key: tuple, message: str, level=logging.WARNING) -> None:
        if key not in self._warned:
            self._warned.add(key)
            logging.log(level, message)

    def _load_dirty(self) -> set[str]:
        try:
            data = self.local.get(DIRTY_KEY, 1024 * 1024)
            return set(json.loads(data)) if data else set()
        except (StoreError, ValueError) as e:
            logging.warning(f"Unsent-records list is unreadable ({e}); all own records will be re-sent.")
            return {f"records/{self.writer_id}/{name}" for name in self.local.list(f"records/{self.writer_id}")
                    if name.endswith(".json")}

    def _save_dirty(self) -> None:
        self.local.put(DIRTY_KEY, json.dumps(sorted(self._dirty)).encode("utf-8"))

    # ----- own records ---------------------------------------------------------------------
    def load_own(self, date: str) -> DailyRecord:
        key = record_key(self.writer_id, date)
        try:
            data = self.local.get(key, MAX_RECORD_BYTES)
            if data is None:
                return DailyRecord(self.writer_id, date)
            return parse_record(data, self.writer_id, date)
        except (StoreError, RecordError) as e:
            stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            logging.error(f"Own record {key} is damaged ({e}); keeping it as {key}.corrupt-{stamp}.")
            try:
                self.local.rename_aside(key, f".corrupt-{stamp}")
            except StoreError as rename_error:
                logging.error(f"Could not move the damaged record aside: {rename_error}")
            record = DailyRecord(self.writer_id, date)
            if self._restore_from_remote(record):
                logging.info(f"Restored {key} from the network store.")
            else:
                logging.error(f"Could not restore {key}; usage for today restarts at 0 on this installation.")
            self.save_own(record)
            return record

    def save_own(self, record: DailyRecord) -> None:
        key = record_key(record.writer_id, record.date)
        self.local.put(key, serialize_record(record))
        if self.remote is not None and key not in self._dirty:
            self._dirty.add(key)
            self._save_dirty()

    def _restore_from_remote(self, record: DailyRecord) -> bool:
        """Merge this writer's network copy into record (per account maximum)."""
        if self.remote is None:
            return False
        key = record_key(record.writer_id, record.date)
        try:
            data = self.remote.get(key, MAX_RECORD_BYTES)
        except StoreError as e:
            logging.debug(f"Network copy of {key} not reachable: {e}")
            return False
        if data is None:
            return True
        try:
            remote_record = parse_record(data, record.writer_id, record.date)
        except RecordError as e:
            logging.warning(f"Network copy of {key} is unusable: {e}")
            return True
        record.merge_max(remote_record)
        return True

    def recover(self, record: DailyRecord) -> bool:
        """Startup recovery: local = max(local, network) per account. Returns False while offline."""
        before = {a: u.minutes for a, u in record.accounts.items()}
        if not self._restore_from_remote(record):
            return False
        if {a: u.minutes for a, u in record.accounts.items()} != before:
            logging.info("Recovered usage from the network copy of this installation's records.")
            self.save_own(record)
        return True

    def push_dirty(self) -> bool:
        if self.remote is None:
            return True
        for key in sorted(self._dirty):
            try:
                data = self.local.get(key, MAX_RECORD_BYTES)
                if data is not None:
                    self.remote.put(key, data)
            except StoreError as e:
                logging.debug(f"Push of {key} postponed: {e}")
                return False
            self._dirty.discard(key)
            self._save_dirty()
        return True

    # ----- other writers -------------------------------------------------------------------
    def fetch_others(self, date: str) -> list[DailyRecord] | None:
        """Today's records of all other writers from the network store, or None when offline.

        Each good copy refreshes the local cache; a bad or unreachable file falls back to the cache.
        """
        if self.remote is None:
            return None
        try:
            writers = self.remote.list("records")
        except StoreError as e:
            self._warn_once(("offline", date), f"Network store unreachable, enforcing offline limits: {e}")
            return None
        self._warned.discard(("offline", date))
        records = []
        for writer in writers:
            if writer == self.writer_id:
                continue
            key = record_key(writer, date)
            try:
                data = self.remote.get(key, MAX_RECORD_BYTES)
                if data is None:
                    continue
                record = parse_record(data, writer, date)
            except (StoreError, ValueError) as e:
                level = logging.INFO if isinstance(e, NewerSchemaError) else logging.WARNING
                self._warn_once((key, "bad"), f"Skipping {key}: {e}", level)
                cached = self._cached_record(writer, date)
                if cached:
                    records.append(cached)
                continue
            records.append(record)
            try:
                self.local.put(cache_record_key(writer, date), data)
            except StoreError as e:
                logging.warning(f"Could not cache {key}: {e}")
        return records

    def _cached_record(self, writer: str, date: str) -> DailyRecord | None:
        try:
            data = self.local.get(cache_record_key(writer, date), MAX_RECORD_BYTES)
            return parse_record(data, writer, date) if data else None
        except (StoreError, ValueError):
            return None

    def cached_others(self, date: str) -> list[DailyRecord]:
        records = []
        for writer in self.local.list("cache/records"):
            if writer != self.writer_id:
                record = self._cached_record(writer, date)
                if record:
                    records.append(record)
        return records

    # ----- configuration -------------------------------------------------------------------
    def _cached_config(self) -> tuple[dict, bytes | None]:
        try:
            data = self.local.get(CONFIG_CACHE_KEY, MAX_CONFIG_BYTES)
        except StoreError as e:
            logging.error(f"Cannot read cached config: {e}")
            return EMPTY_CONFIG, None
        if data is None:
            return EMPTY_CONFIG, None
        try:
            return parse_config(data), data
        except ConfigError as e:
            self._warn_once(("cache-config", data), f"Cached config is invalid ({e}); no limits can be applied.",
                            logging.ERROR)
            return EMPTY_CONFIG, None

    def refresh_config(self) -> dict:
        """Fetch the shared config; adopt it only if valid. Falls back to the local cache."""
        cached, cached_bytes = self._cached_config()
        if self.remote is None:
            return cached
        try:
            data = self.remote.get(CONFIG_KEY, MAX_CONFIG_BYTES)
        except StoreError as e:
            logging.debug(f"Config fetch failed, using cached copy: {e}")
            return cached
        if data is None:
            if cached_bytes is not None:
                # New or emptied store: publish the seed / last known config so others get it too.
                try:
                    self.remote.put(CONFIG_KEY, cached_bytes)
                    logging.info("Network store had no config; uploaded this installation's copy.")
                except StoreError as e:
                    logging.debug(f"Config upload postponed: {e}")
            else:
                self._warn_once(("no-config",), "No configuration anywhere yet: nothing is enforced. "
                                                "Run the configurator.")
            return cached
        if data == cached_bytes:
            return cached
        try:
            config = parse_config(data)
        except ConfigError as e:
            self._warn_once(("bad-config", data), f"Shared config rejected, keeping cached copy: {e}")
            return cached
        try:
            self.local.put(CONFIG_CACHE_KEY, data)
        except StoreError as e:
            logging.warning(f"Could not cache config: {e}")
        logging.info(f"Using shared config revision {config['revision']}.")
        return config

    def import_seed_config(self, path) -> None:
        """Install-time seed or a 1.x limits.toml becomes the cached config if none is cached yet."""
        if self.local.get(CONFIG_CACHE_KEY, MAX_CONFIG_BYTES) is not None:
            return
        try:
            data = path.read_bytes()
            config = parse_config(data)
        except FileNotFoundError:
            return
        except (OSError, ConfigError) as e:
            logging.error(f"Seed config {path} is not usable: {e}")
            return
        from core.config import serialize_config
        self.local.put(CONFIG_CACHE_KEY, serialize_config(config))
        logging.info(f"Imported seed config from {path}.")

    # ----- housekeeping --------------------------------------------------------------------
    def publish_writer(self, info: bytes) -> None:
        if self.remote is not None:
            try:
                self.remote.put(f"writers/{self.writer_id}.json", info)
            except StoreError as e:
                logging.debug(f"Writer info not published: {e}")

    def prune(self, today: datetime.date, retention_days: int, online: bool) -> None:
        """Delete own records older than the retention period and other writers' old cache files."""
        cut_off = today - datetime.timedelta(days=retention_days)
        own_prefix = f"records/{self.writer_id}"
        stores = [self.local] + ([self.remote] if online and self.remote is not None else [])
        for store in stores:
            try:
                names = store.list(own_prefix)
            except StoreError as e:
                logging.debug(f"Prune skipped for {store.describe()}: {e}")
                continue
            for name in names:
                try:
                    day = datetime.date.fromisoformat(name.removesuffix(".json")[:10])
                except ValueError:
                    continue
                key = f"{own_prefix}/{name}"
                if day < cut_off and key not in self._dirty:
                    try:
                        store.delete(key)
                    except StoreError as e:
                        logging.debug(f"Could not delete {key}: {e}")
        for writer in self.local.list("cache/records"):
            for name in self.local.list(f"cache/records/{writer}"):
                if name != f"{today.isoformat()}.json":
                    self.local.delete(f"cache/records/{writer}/{name}")
