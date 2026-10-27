import socket
import threading

import pytest

from storage.base import StoreError
from storage.folder import FolderStore


def exercise_store(store):
    assert store.get("records/w1/2026-10-26.json", 1000) is None
    assert store.list("records") == []
    store.put("records/w1/2026-10-26.json", b"one")
    store.put("records/w1/2026-10-26.json", b"two")  # replace
    store.put("records/w2/2026-10-26.json", b"x" * 50)
    assert store.get("records/w1/2026-10-26.json", 1000) == b"two"
    assert store.list("records") == ["w1", "w2"]
    assert store.list("records/w1") == ["2026-10-26.json"]
    with pytest.raises(StoreError):
        store.get("records/w2/2026-10-26.json", 10)  # over the size limit
    store.delete("records/w1/2026-10-26.json")
    store.delete("records/w1/2026-10-26.json")  # deleting twice is fine
    assert store.get("records/w1/2026-10-26.json", 1000) is None
    for bad in ("../x", "/abs", "a//b", "a/../b", ".hidden", ""):
        with pytest.raises(ValueError):
            store.get(bad, 10)


def test_folder_store(tmp_path):
    store = FolderStore(tmp_path)
    exercise_store(store)
    assert not list(tmp_path.rglob("*.tmp"))


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def webdav_server(tmp_path):
    wsgidav = pytest.importorskip("wsgidav.wsgidav_app")
    from cheroot import wsgi
    root = tmp_path / "dav"
    root.mkdir()
    app = wsgidav.WsgiDAVApp({
        "provider_mapping": {"/timemanager": str(root)},
        "simple_dc": {"user_mapping": {"*": {"tracker": {"password": "secret"}}}},
        "http_authenticator": {"accept_basic": True, "accept_digest": False, "default_to_digest": False},
        "verbose": 0,
        "logging": {"enable": False},
    })
    port = _free_port()
    server = wsgi.Server(("127.0.0.1", port), app)
    thread = threading.Thread(target=server.start, daemon=True)
    thread.start()
    while not server.ready:
        pass
    yield f"http://127.0.0.1:{port}/timemanager"
    server.stop()


def test_webdav_store(webdav_server):
    from storage.webdav import WebDavStore
    exercise_store(WebDavStore(webdav_server, "tracker", "secret", allow_http=True))


def test_webdav_wrong_password_is_store_error(webdav_server):
    from storage.webdav import WebDavStore
    store = WebDavStore(webdav_server, "tracker", "wrong", allow_http=True)
    with pytest.raises(StoreError):
        store.list("records")


def test_webdav_unreachable_is_store_error():
    from storage.webdav import WebDavStore
    store = WebDavStore(f"http://127.0.0.1:{_free_port()}/x", timeout=1, allow_http=True)
    with pytest.raises(StoreError):
        store.get("config/limits.toml", 100)


def test_webdav_requires_https():
    from storage.webdav import WebDavStore
    with pytest.raises(ValueError):
        WebDavStore("http://nas.lan/timemanager")
