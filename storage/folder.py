"""Store backed by a local or mounted folder."""

import os
import tempfile
from pathlib import Path

from storage.base import Store, StoreError, check_key, check_prefix


class FolderStore(Store):
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root.joinpath(*check_key(key))

    def get(self, key: str, max_bytes: int) -> bytes | None:
        path = self._path(key)
        try:
            with open(path, "rb") as f:
                data = f.read(max_bytes + 1)
        except FileNotFoundError:
            return None
        except OSError as e:
            raise StoreError(f"cannot read {path}: {e}") from e
        if len(data) > max_bytes:
            raise StoreError(f"{path} is larger than {max_bytes} bytes")
        return data

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write a temporary file in the same folder, flush it to disk, then swap it in, so a
            # crash or power cut leaves either the old or the new file, never a half written one.
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
        except OSError as e:
            raise StoreError(f"cannot write {path}: {e}") from e

    def list(self, prefix: str) -> list[str]:
        path = self.root.joinpath(*check_prefix(prefix))
        try:
            return sorted(p.name for p in path.iterdir() if not p.name.endswith(".tmp"))
        except FileNotFoundError:
            return []
        except OSError as e:
            raise StoreError(f"cannot list {path}: {e}") from e

    def delete(self, key: str) -> None:
        path = self._path(key)
        try:
            path.unlink(missing_ok=True)
        except OSError as e:
            raise StoreError(f"cannot delete {path}: {e}") from e

    def rename_aside(self, key: str, suffix: str) -> None:
        """Keep a damaged file for diagnosis by renaming it next to the original (local use only)."""
        path = self._path(key)
        try:
            path.replace(path.with_name(path.name + suffix))
        except OSError as e:
            raise StoreError(f"cannot rename {path}: {e}") from e

    def describe(self) -> str:
        return f"folder {self.root}"
