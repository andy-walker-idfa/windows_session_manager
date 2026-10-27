"""Settings and identity of one installation (one OS on one machine).

instance.toml is written by the configurator (Connection tab) or the installer and is never shared. It holds the network
store location and credentials, so it must be readable only by SYSTEM / root.
"""

import hashlib
import json
import shutil
import logging
import platform as std_platform
import socket
import tomllib
import uuid

import tomli_w
from dataclasses import dataclass, field
from pathlib import Path

from shared import defaults
from storage.base import Store, StoreError
from storage.folder import FolderStore

STATE_KEY = "state/instance.json"


class InstanceError(ValueError):
    pass


class InstanceAccessError(InstanceError):
    """instance.toml exists but cannot be read, normally because administrator rights are missing."""


CERTIFICATE_FILE = "nas-ca.crt"
REMOTE_TYPES = ("webdav", "folder", "none")


@dataclass
class RemoteSettings:
    type: str = "none"          # "webdav", "folder" or "none"
    url: str = ""
    username: str = ""
    password: str = ""
    ca_file: str = ""
    path: str = ""
    timeout_seconds: float = 5.0


@dataclass
class InstanceSettings:
    root: Path
    data_dir: Path
    log_dir: Path
    remote: RemoteSettings = field(default_factory=RemoteSettings)


def instance_path(root: Path) -> Path:
    return root / defaults.instance_file


def _read_raw(root: Path) -> dict:
    path = instance_path(root)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as e:
        raise InstanceAccessError(f"Cannot read {path}: {e}") from e
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise InstanceError(f"{path} is not valid TOML: {e}") from e


def validate_remote(remote: RemoteSettings) -> list[str]:
    errors = []
    if remote.type not in REMOTE_TYPES:
        errors.append("store type must be webdav, folder or none")
    if remote.type == "webdav":
        if not remote.url.lower().startswith("https://"):
            errors.append("the URL must start with https://")
        if not remote.username:
            errors.append("a username is required")
    if remote.type == "folder" and not remote.path:
        errors.append("a folder path is required")
    if not isinstance(remote.timeout_seconds, (int, float)) or not 1 <= remote.timeout_seconds <= 60:
        errors.append("the timeout must be 1-60 seconds")
    return errors


def load_instance(root: Path) -> InstanceSettings:
    path = instance_path(root)
    raw = _read_raw(root)
    local = raw.get("local", {})
    remote_raw = raw.get("remote", {})
    unknown = set(remote_raw) - set(RemoteSettings.__dataclass_fields__)
    if unknown:
        raise InstanceError(f"{path}: unknown [remote] keys: {', '.join(sorted(unknown))}")
    remote = RemoteSettings(**remote_raw)
    errors = validate_remote(remote)
    if errors:
        raise InstanceError(f"{path}: {'; '.join(errors)}")
    return InstanceSettings(
        root=root,
        data_dir=(root / local.get("data_dir", "data")).resolve(),
        log_dir=(root / local.get("log_dir", "logs")).resolve(),
        remote=remote,
    )


def default_instance(root: Path) -> InstanceSettings:
    return InstanceSettings(root, (root / "data").resolve(), (root / "logs").resolve())


def save_remote_settings(root: Path, remote: RemoteSettings) -> None:
    """Write the [remote] section, keeping everything else in instance.toml.

    The file is replaced atomically and inherits the install folder's permissions
    (SYSTEM/Administrators or root only), which the installers set up.
    """
    errors = validate_remote(remote)
    if errors:
        raise InstanceError("; ".join(errors))
    try:
        raw = _read_raw(root)
    except InstanceAccessError:
        raise
    except InstanceError:
        raw = {}  # an unreadable file is replaced entirely
    values = {"type": remote.type, "timeout_seconds": remote.timeout_seconds}
    if remote.type == "webdav":
        values.update(url=remote.url, username=remote.username, password=remote.password, ca_file=remote.ca_file)
    elif remote.type == "folder":
        values["path"] = remote.path
    raw["remote"] = values
    header = ("# Settings of this installation only. Edited by the configurator (Connection tab).\n"
              "# Holds the network store password: keep it readable by SYSTEM/Administrators or root only.\n\n")
    FolderStore(root).put(defaults.instance_file, (header + tomli_w.dumps(raw)).encode("utf-8"))


def install_certificate(root: Path, source: Path) -> str:
    """Copy the certificate that verifies the server into the install folder; return its new path."""
    target = (root / CERTIFICATE_FILE).resolve()
    if Path(source).resolve() != target:
        shutil.copyfile(source, target)
    return str(target)


def instance_mtime(root: Path) -> float | None:
    try:
        return instance_path(root).stat().st_mtime
    except OSError:
        return None


def build_remote_store(settings: RemoteSettings) -> Store | None:
    if settings.type == "webdav":
        from storage.webdav import WebDavStore
        return WebDavStore(settings.url, settings.username, settings.password,
                           settings.ca_file, settings.timeout_seconds)
    if settings.type == "folder":
        return FolderStore(settings.path)
    return None


@dataclass
class WriterIdentity:
    writer_id: str
    label: str


def _fingerprint(os_name: str, machine_id: str) -> str:
    text = f"{socket.gethostname().casefold()}|{os_name}|{machine_id}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_writer_identity(local: FolderStore, os_name: str, machine_id: str) -> WriterIdentity:
    """Return this installation's writer id, creating one on first run.

    The stored fingerprint protects against a copied install folder or restored backup: two
    machines with the same writer id would silently overwrite each other's records.
    """
    fingerprint = _fingerprint(os_name, machine_id)
    label = f"{socket.gethostname()} ({os_name})"
    state = None
    try:
        data = local.get(STATE_KEY, 64 * 1024)
        state = json.loads(data) if data else None
    except (ValueError, StoreError) as e:
        logging.warning(f"Instance state is unreadable ({e}), creating a new writer id.")
    if state and state.get("fingerprint") == fingerprint and state.get("writer_id"):
        return WriterIdentity(state["writer_id"], label)
    if state and state.get("writer_id"):
        logging.warning(f"Machine fingerprint changed (copied install or renamed host): replacing writer id "
                        f"{state['writer_id']} with a new one.")
    writer_id = str(uuid.uuid4())
    local.put(STATE_KEY, json.dumps({"writer_id": writer_id, "fingerprint": fingerprint}).encode("utf-8"))
    logging.info(f"Writer id for this installation: {writer_id}")
    return WriterIdentity(writer_id, label)


def writer_info(identity: WriterIdentity, os_name: str, now_iso: str) -> bytes:
    return json.dumps({
        "writer_id": identity.writer_id,
        "label": identity.label,
        "os": os_name,
        "os_version": std_platform.platform(),
        "version": defaults.__version__,
        "last_seen": now_iso,
    }, indent=1).encode("utf-8")
