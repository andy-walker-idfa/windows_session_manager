"""instance.toml editing and the connection checks, including a real HTTPS WebDAV server."""

import shutil
import socket
import subprocess
import threading

import pytest

from shared.instance import (InstanceError, RemoteSettings, install_certificate, load_instance,
                             save_remote_settings)
from storage.diagnostics import check_folder, check_webdav


def test_save_remote_settings_round_trip_keeps_local_section(tmp_path):
    (tmp_path / "instance.toml").write_text('[local]\ndata_dir = "mydata"\n\n[remote]\ntype = "none"\n', encoding="utf-8")
    remote = RemoteSettings(type="webdav", url="https://nas.home.arpa:30036/timemanager", username="tm",
                            password='p"a\\ss', ca_file=r"C:\Program Files\TimeManager\nas-ca.crt", timeout_seconds=7)
    save_remote_settings(tmp_path, remote)
    instance = load_instance(tmp_path)
    assert instance.remote == remote
    assert instance.data_dir == (tmp_path / "mydata").resolve()
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("remote", [
    RemoteSettings(type="webdav", url="http://nas/timemanager", username="tm"),
    RemoteSettings(type="webdav", url="https://nas/timemanager", username=""),
    RemoteSettings(type="folder", path=""),
    RemoteSettings(type="none", timeout_seconds=0),
])
def test_invalid_remote_settings_are_refused(tmp_path, remote):
    with pytest.raises(InstanceError):
        save_remote_settings(tmp_path, remote)


def test_broken_instance_file_can_be_replaced(tmp_path):
    (tmp_path / "instance.toml").write_text("this is not toml = =", encoding="utf-8")
    with pytest.raises(InstanceError):
        load_instance(tmp_path)
    save_remote_settings(tmp_path, RemoteSettings(type="none"))
    assert load_instance(tmp_path).remote.type == "none"


def test_install_certificate_copies_into_install_folder(tmp_path):
    source = tmp_path / "elsewhere" / "nas.crt"
    source.parent.mkdir()
    source.write_text("CERT", encoding="utf-8")
    target = install_certificate(tmp_path, source)
    assert (tmp_path / "nas-ca.crt").read_text(encoding="utf-8") == "CERT"
    assert install_certificate(tmp_path, target) == target  # installing the installed copy is a no-op


def test_folder_checks_pass(tmp_path):
    results = list(check_folder(str(tmp_path)))
    assert all(ok for _, ok, _ in results), results
    assert list(tmp_path.iterdir()) == []


# ----- real HTTPS WebDAV server with a self-signed certificate (needs the openssl command) ---------
def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def https_webdav(tmp_path):
    pytest.importorskip("wsgidav.wsgidav_app")
    openssl = shutil.which("openssl") or (r"C:\Program Files\Git\usr\bin\openssl.exe"
                                          if shutil.which("git") else None)
    if not openssl or subprocess.run([openssl, "version"], capture_output=True).returncode != 0:
        pytest.skip("openssl not available")
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
                    "-keyout", str(key), "-out", str(cert), "-subj", "/CN=localhost",
                    "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
                    "-addext", "basicConstraints=critical,CA:TRUE",
                    "-addext", "keyUsage=critical,digitalSignature,keyCertSign,keyEncipherment",
                    "-addext", "extendedKeyUsage=serverAuth"],
                   check=True, capture_output=True)
    from cheroot import wsgi
    from cheroot.ssl.builtin import BuiltinSSLAdapter
    from wsgidav.wsgidav_app import WsgiDAVApp
    root = tmp_path / "dav"
    root.mkdir()
    app = WsgiDAVApp({
        "provider_mapping": {"/timemanager": str(root)},
        "simple_dc": {"user_mapping": {"*": {"tracker": {"password": "secret"}}}},
        "http_authenticator": {"accept_basic": True, "accept_digest": False, "default_to_digest": False},
        "verbose": 0, "logging": {"enable": False},
    })
    port = _free_port()
    server = wsgi.Server(("127.0.0.1", port), app)
    server.ssl_adapter = BuiltinSSLAdapter(str(cert), str(key))
    threading.Thread(target=server.start, daemon=True).start()
    while not server.ready:
        pass
    yield f"https://localhost:{port}/timemanager", str(cert), root
    server.stop()


def test_webdav_checks_pass_over_https_with_pinned_certificate(https_webdav):
    url, cert, root = https_webdav
    results = list(check_webdav(url, "tracker", "secret", cert, timeout=10, http_port=_free_port()))
    assert all(ok for _, ok, _ in results), results
    assert list(root.iterdir()) == []


def test_webdav_checks_report_untrusted_certificate(https_webdav):
    url, _, _ = https_webdav
    results = list(check_webdav(url, "tracker", "secret", "", timeout=10))
    name, ok, detail = results[-1]
    assert not ok and "certificate" in name.lower() and "CERTIFICATE_VERIFY_FAILED" in detail


def test_webdav_checks_report_wrong_password(https_webdav):
    url, cert, _ = https_webdav
    results = dict((name, ok) for name, ok, _ in check_webdav(url, "tracker", "nope", cert, timeout=10))
    assert results["Wrong password refused"] and not results["Log in and list the store"]


# ----- installation permission checks ---------------------------------------------------------
import sys  # noqa: E402

from shared.security import find_issues, fix_all, tracker_command  # noqa: E402


@pytest.mark.skipif(sys.platform != "win32", reason="Windows access lists")
def test_windows_permission_issues_are_found_and_fixed(tmp_path):
    (tmp_path / "instance.toml").write_text("[remote]\ntype = 'none'\n", encoding="utf-8")
    users, everyone = "*S-1-5-32-545", "*S-1-1-0"
    subprocess.run(["icacls", str(tmp_path), "/grant", f"{users}:(OI)(CI)M"], capture_output=True, check=True)
    subprocess.run(["icacls", str(tmp_path / "instance.toml"), "/grant", f"{everyone}:R"], capture_output=True, check=True)
    assert {i.problem for i in find_issues(tmp_path)} == {"writable", "readable"}
    try:
        assert fix_all(tmp_path) == []
    finally:
        subprocess.run(["icacls", str(tmp_path), "/reset", "/T", "/C", "/Q"], capture_output=True)


def test_tracker_command_points_at_this_installation(tmp_path):
    assert "run_tracker.py" in tracker_command(tmp_path) or "tracker" in tracker_command(tmp_path)


def test_untrusted_certificate_error_explains_the_fix(https_webdav):
    from storage.base import StoreError
    from storage.webdav import WebDavStore
    url, _, _ = https_webdav
    with pytest.raises(StoreError) as error:
        WebDavStore(url, "tracker", "secret", timeout=10).get("config/limits.toml", 1000)
    assert "no certificate file is set" in str(error.value)


@pytest.fixture
def ca_signed_webdav(tmp_path):
    """HTTPS WebDAV whose certificate is signed by a private CA (like the NAS in this setup)."""
    pytest.importorskip("wsgidav.wsgidav_app")
    openssl = shutil.which("openssl") or r"C:\Program Files\Git\usr\bin\openssl.exe"
    try:
        if subprocess.run([openssl, "version"], capture_output=True).returncode != 0:
            pytest.skip("openssl not available")
    except OSError:
        pytest.skip("openssl not available")

    def run(*args):
        subprocess.run([openssl, *args], check=True, capture_output=True)

    ca_key, ca_cert = tmp_path / "ca.key", tmp_path / "ca.pem"
    key, csr, cert = tmp_path / "nas.key", tmp_path / "nas.csr", tmp_path / "nas.pem"
    ext = tmp_path / "ext.cnf"
    ext.write_text("subjectAltName=DNS:localhost,IP:127.0.0.1\nbasicConstraints=CA:FALSE\n"
                   "keyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n"
                   "authorityKeyIdentifier=keyid\nsubjectKeyIdentifier=hash\n")
    run("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2", "-keyout", str(ca_key), "-out", str(ca_cert),
        "-subj", "/CN=Test Home CA", "-addext", "basicConstraints=critical,CA:TRUE",
        "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    run("req", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(csr), "-subj", "/CN=localhost")
    run("x509", "-req", "-in", str(csr), "-CA", str(ca_cert), "-CAkey", str(ca_key), "-CAcreateserial",
        "-days", "2", "-out", str(cert), "-extfile", str(ext))
    from cheroot import wsgi
    from cheroot.ssl.builtin import BuiltinSSLAdapter
    from wsgidav.wsgidav_app import WsgiDAVApp
    root = tmp_path / "dav"
    root.mkdir()
    app = WsgiDAVApp({"provider_mapping": {"/timemanager": str(root)},
                      "simple_dc": {"user_mapping": {"*": {"tracker": {"password": "secret"}}}},
                      "http_authenticator": {"accept_basic": True, "accept_digest": False, "default_to_digest": False},
                      "verbose": 0, "logging": {"enable": False}})
    port = _free_port()
    server = wsgi.Server(("127.0.0.1", port), app)
    server.ssl_adapter = BuiltinSSLAdapter(str(cert), str(key))
    threading.Thread(target=server.start, daemon=True).start()
    while not server.ready:
        pass
    yield f"https://localhost:{port}/timemanager", str(cert), str(ca_cert)
    server.stop()


def test_server_certificate_file_works_on_every_python_version(ca_signed_webdav):
    """The macOS case: only the NAS certificate (signed by a CA) is given as the certificate file.
    Python < 3.13 rejects that by default ('unable to get local issuer certificate')."""
    import ssl

    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.ssl_ import create_urllib3_context

    from storage.webdav import WebDavStore
    url, server_cert, ca_cert = ca_signed_webdav

    # How Python 3.11 / 3.12 behave: no partial chains, so the server certificate alone is not enough.
    old = create_urllib3_context()
    old.verify_flags &= ~ssl.VERIFY_X509_PARTIAL_CHAIN
    old.load_verify_locations(cafile=server_cert)

    class OldAdapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            kwargs["ssl_context"] = old
            return super().init_poolmanager(*args, **kwargs)

    session = requests.Session()
    session.mount("https://", OldAdapter())
    with pytest.raises(requests.exceptions.SSLError, match="unable to get local issuer certificate"):
        session.get(url + "/", timeout=10)

    # Time Manager accepts either the server certificate or its CA, whatever the Python version.
    for trusted in (server_cert, ca_cert):
        assert WebDavStore(url, "tracker", "secret", trusted, timeout=10).list("") == []
        assert all(ok for _, ok, _ in check_webdav(url, "tracker", "secret", trusted, timeout=10,
                                                   http_port=_free_port())), trusted
