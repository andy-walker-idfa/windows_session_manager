"""Connection checks for a network store, shared by the configurator and tools/check_store.py.

Each check yields (name, passed, detail). Write checks work in a random "selftest-..." folder and
remove it afterwards.
"""

import shutil
import uuid
from collections.abc import Iterator
from urllib.parse import urlsplit, urlunsplit

import requests

from storage.base import Store, StoreError
from storage.folder import FolderStore

CheckResult = tuple[str, bool, str]


def _run(name, fn) -> CheckResult:
    try:
        return name, True, fn() or ""
    except Exception as e:  # every failure becomes a readable line
        return name, False, str(e)


def _store_checks(store: Store) -> Iterator[CheckResult]:
    base = f"selftest-{uuid.uuid4().hex[:8]}"
    key = f"{base}/records/writer/2026-01-01.json"
    payload = b'{"hello": "time manager"}'

    yield _run("Log in and list the store", lambda: f"{len(store.list(''))} item(s) at the top level")
    yield _run("Write a file in new folders", lambda: store.put(key, payload))
    yield _run("Overwrite the file", lambda: store.put(key, payload + b" "))

    def read_back():
        data = store.get(key, 1024)
        if data != payload + b" ":
            raise ValueError(f"read back {data!r}")
    yield _run("Read the file back", read_back)

    def listing():
        names = store.list(f"{base}/records")
        if names != ["writer"]:
            raise ValueError(f"listing returned {names}")
    yield _run("List a folder", listing)

    def cleanup():
        store.delete(key)
        if store.get(key, 1024) is not None:
            raise ValueError("file still there after delete")
        if isinstance(store, FolderStore):
            shutil.rmtree(store.root / base, ignore_errors=True)  # folders are not objects in a folder store
        else:
            for folder in (f"{base}/records/writer", f"{base}/records", base):
                store.delete(folder)
        if base in store.list(""):
            raise ValueError(f"test folder {base} could not be removed; delete it by hand")
    yield _run("Delete the test file and folders", cleanup)


def check_webdav(url: str, username: str, password: str, ca_file: str = "", timeout: float = 10,
                 http_port: int = 30034) -> Iterator[CheckResult]:
    from storage.webdav import WebDavStore, make_session

    parts = urlsplit(url)

    def https_only():
        if parts.scheme != "https":
            raise ValueError("URL must start with https://")
    yield _run("URL uses HTTPS", https_only)
    if parts.scheme != "https":
        return

    def has_share_name():
        if not parts.path.strip("/"):
            raise ValueError("URL has no share name; add it, e.g. https://nas:30036/timemanager")
    yield _run("URL includes the share name", has_share_name)

    def tls_and_auth_required():
        # Same certificate handling as the tracker uses, so the test predicts the real connection.
        r = make_session(ca_file).get(url.rstrip("/") + "/", timeout=timeout)
        if r.status_code != 401:
            raise ValueError(f"request without password returned HTTP {r.status_code}, expected 401")
        return "certificate verified, password required"
    name, ok, detail = _run("Certificate valid for this host name; anonymous access refused", tls_and_auth_required)
    yield name, ok, detail
    if not ok and ("SSL" in detail or "certificate" in detail.lower() or "Max retries" in detail):
        return  # nothing else can work without a verified connection

    def wrong_password_refused():
        try:
            WebDavStore(url, username or "x", "wrong-" + uuid.uuid4().hex, ca_file, timeout).list("")
        except StoreError as e:
            if "401" in str(e):
                return "HTTP 401"
            raise
        raise ValueError("a wrong password was accepted")
    yield _run("Wrong password refused", wrong_password_refused)

    def plain_http_closed():
        for port in {http_port, parts.port or 443}:
            plain = urlunsplit(("http", f"{parts.hostname}:{port}", parts.path, "", ""))
            try:
                r = requests.get(plain, timeout=5)
            except requests.RequestException:
                continue  # closed or not speaking HTTP: good
            if r.status_code < 400 or r.status_code == 401:
                raise ValueError(f"{plain} answers over plain HTTP; disable HTTP in the WebDAV app")
        return "no plain HTTP access"
    yield _run("Plain HTTP not available", plain_http_closed)

    yield from _store_checks(WebDavStore(url, username, password, ca_file, timeout))


def check_folder(path: str) -> Iterator[CheckResult]:
    yield from _store_checks(FolderStore(path))
