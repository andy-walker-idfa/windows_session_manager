"""Loading and saving the shared configuration, with a revision check against concurrent edits."""

import copy

from core.config import MAX_CONFIG_BYTES, parse_config, serialize_config
from shared.instance import InstanceSettings, build_remote_store
from storage.base import Store, StoreError
from storage.folder import FolderStore
from tracker.sync import CONFIG_CACHE_KEY, CONFIG_KEY, EMPTY_CONFIG


class RevisionConflict(Exception):
    pass


class ConfigSession:
    def __init__(self, instance: InstanceSettings):
        self.local = FolderStore(instance.data_dir)
        remote = build_remote_store(instance.remote)
        # Without a network store, the configurator edits this installation's cached config.
        self.store: Store = remote or self.local
        self.key = CONFIG_KEY if remote else CONFIG_CACHE_KEY
        self.is_remote = remote is not None
        self.loaded_revision: int | None = None

    @property
    def store_is_empty(self) -> bool:
        """True after load() if the network store had no configuration yet."""
        return self.is_remote and self.loaded_revision is None

    def describe(self) -> str:
        return self.store.describe() if self.is_remote else f"local only ({self.local.describe()})"

    def _read(self) -> dict | None:
        data = self.store.get(self.key, MAX_CONFIG_BYTES)
        return parse_config(data) if data else None

    def load(self) -> dict:
        """Load the current config. Raises StoreError when offline, ConfigError when invalid."""
        config = self._read()
        self.loaded_revision = config["revision"] if config else None
        if config is None and self.is_remote:
            # Empty network store: start from this installation's cached or seed config.
            data = self.local.get(CONFIG_CACHE_KEY, MAX_CONFIG_BYTES)
            config = parse_config(data) if data else None
        return copy.deepcopy(config or EMPTY_CONFIG)

    def save(self, config: dict) -> int:
        """Save config if nobody else saved since load(). Returns the new revision."""
        current = self._read()
        current_revision = current["revision"] if current else None
        if current_revision != self.loaded_revision:
            raise RevisionConflict(
                f"The configuration was changed elsewhere (revision {current_revision}, you loaded "
                f"{self.loaded_revision}). Reload and apply your changes again.")
        new_config = copy.deepcopy(config)
        new_config["schema"] = 1
        new_config["revision"] = (current_revision or 0) + 1
        data = serialize_config(new_config)
        self.store.put(self.key, data)
        if self.is_remote:
            try:
                self.local.put(CONFIG_CACHE_KEY, data)
            except StoreError:
                pass  # the tracker refreshes its cache from the network on its next cycle
        self.loaded_revision = new_config["revision"]
        return new_config["revision"]
