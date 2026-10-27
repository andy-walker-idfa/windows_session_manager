"""The storage contract, limited to what every backend (folder, WebDAV, object store) can do.

Keys are relative, "/"-separated paths such as "records/<writer>/2026-10-26.json".
There is no append, lock or rename: a writer only ever replaces whole objects it owns.
"""

import re
from abc import ABC, abstractmethod

_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class StoreError(Exception):
    """The store could not be reached or refused the operation. Callers treat this as offline."""


def check_key(key: str) -> list[str]:
    """Validate a key and return its segments. Rejects anything that could escape the store root."""
    segments = key.split("/")
    if not segments or not all(_SEGMENT_RE.match(s) and s not in (".", "..") for s in segments):
        raise ValueError(f"invalid storage key: {key!r}")
    return segments


def check_prefix(prefix: str) -> list[str]:
    return check_key(prefix.strip("/")) if prefix.strip("/") else []


class Store(ABC):
    @abstractmethod
    def get(self, key: str, max_bytes: int) -> bytes | None:
        """Return the object's content, or None if it does not exist.

        Raises StoreError if the object is larger than max_bytes or the store is unreachable.
        """

    @abstractmethod
    def put(self, key: str, data: bytes) -> None:
        """Create or replace the whole object atomically, creating parent folders as needed."""

    @abstractmethod
    def list(self, prefix: str) -> list[str]:
        """Names (not full keys) of the direct children of prefix; empty if prefix does not exist."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove the object; deleting a missing object is not an error."""

    @abstractmethod
    def describe(self) -> str:
        """Short human readable location for logs."""
