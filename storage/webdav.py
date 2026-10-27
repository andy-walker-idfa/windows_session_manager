"""Store backed by a WebDAV server over HTTPS (e.g. the TrueNAS WebDAV app or a cloud provider)."""

import posixpath
import xml.etree.ElementTree as ET
from urllib.parse import quote, unquote, urlsplit

import ssl

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

from storage.base import Store, StoreError, check_key, check_prefix

_PROPFIND_BODY = b'<?xml version="1.0" encoding="utf-8"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>'
_MAX_LISTING_BYTES = 1024 * 1024


def make_session(ca_file: str = "") -> requests.Session:
    """HTTPS session that always verifies the server.

    Without ca_file the public certificate authorities are trusted. With ca_file, only that file is
    trusted, and as given: it may hold the CA that signed the NAS certificate or the NAS certificate
    itself. Python 3.13+ allows the latter by default (VERIFY_X509_PARTIAL_CHAIN); we set it
    explicitly so every Python version and OS behaves the same.
    """
    session = requests.Session()
    if not ca_file:
        session.verify = True
        return session
    context = create_urllib3_context()
    context.load_verify_locations(cafile=ca_file)
    context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN

    class _PinnedAdapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            kwargs["ssl_context"] = context
            return super().init_poolmanager(*args, **kwargs)

    session.mount("https://", _PinnedAdapter())
    session.verify = True  # verification stays on; the trusted certificates come from the context
    return session


class WebDavStore(Store):
    def __init__(self, url: str, username: str = "", password: str = "", ca_file: str = "",
                 timeout: float = 5.0, allow_http: bool = False):
        scheme = urlsplit(url).scheme.lower()
        if scheme != "https" and not (allow_http and scheme == "http"):
            raise ValueError("WebDAV URL must use https://")
        self.base_url = url.rstrip("/") + "/"
        self.timeout = timeout
        # Certificates are always verified; a certificate file can be given for a private NAS certificate.
        self.ca_file = ca_file
        self.session = make_session(ca_file)
        if username:
            self.session.auth = (username, password)
        self._known_collections: set[str] = set()

    def _url(self, segments: list[str], collection: bool = False) -> str:
        path = "/".join(quote(s) for s in segments)
        return self.base_url + path + ("/" if collection and path else "")

    def _failure(self, method: str, url: str, error: requests.RequestException) -> StoreError:
        message = f"{method} {url} failed: {error}"
        if isinstance(error, requests.exceptions.SSLError) and "CERTIFICATE_VERIFY_FAILED" in str(error):
            if not self.ca_file:
                message += ("\nThe server certificate is not publicly trusted and no certificate file is set. "
                            "Select the server's certificate (or its CA certificate) as 'Certificate file' on "
                            "the Connection tab.")
            else:
                message += (f"\nThe certificate file {self.ca_file} does not verify this server. "
                            "Select the certificate the NAS actually uses (or the CA that signed it).")
        return StoreError(message)

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        try:
            return self.session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.RequestException as e:
            raise self._failure(method, url, e) from e

    def get(self, key: str, max_bytes: int) -> bytes | None:
        url = self._url(check_key(key))
        try:
            with self.session.get(url, timeout=self.timeout, stream=True) as response:
                if response.status_code == 404:
                    return None
                if response.status_code != 200:
                    raise StoreError(f"GET {url} returned HTTP {response.status_code}")
                data = b""
                for chunk in response.iter_content(65536):
                    data += chunk
                    if len(data) > max_bytes:
                        raise StoreError(f"{url} is larger than {max_bytes} bytes")
                return data
        except requests.RequestException as e:
            raise self._failure("GET", url, e) from e

    def _ensure_collections(self, segments: list[str]) -> None:
        for i in range(1, len(segments) + 1):
            path = "/".join(segments[:i])
            if path in self._known_collections:
                continue
            response = self._request("MKCOL", self._url(segments[:i], collection=True))
            # 201 created, 405 already exists (some servers answer 301 for an existing collection)
            if response.status_code not in (201, 405, 301):
                raise StoreError(f"MKCOL {path} returned HTTP {response.status_code}")
            self._known_collections.add(path)

    def put(self, key: str, data: bytes) -> None:
        segments = check_key(key)
        url = self._url(segments)
        headers = {"Content-Type": "application/octet-stream"}
        response = self._request("PUT", url, data=data, headers=headers)
        if response.status_code == 409 or (response.status_code == 404 and len(segments) > 1):
            # Parent collection missing: create it and try once more.
            self._ensure_collections(segments[:-1])
            response = self._request("PUT", url, data=data, headers=headers)
        if response.status_code not in (200, 201, 204):
            raise StoreError(f"PUT {url} returned HTTP {response.status_code}")

    def list(self, prefix: str) -> list[str]:
        segments = check_prefix(prefix)
        url = self._url(segments, collection=True)
        response = self._request("PROPFIND", url, data=_PROPFIND_BODY,
                                 headers={"Depth": "1", "Content-Type": "application/xml"})
        if response.status_code == 404:
            return []
        if response.status_code != 207:
            raise StoreError(f"PROPFIND {url} returned HTTP {response.status_code}")
        if len(response.content) > _MAX_LISTING_BYTES:
            raise StoreError(f"PROPFIND {url} answer is too large")
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as e:
            raise StoreError(f"PROPFIND {url} returned invalid XML: {e}") from e
        own_path = unquote(urlsplit(url).path).rstrip("/")
        names = set()
        for href in root.iter("{DAV:}href"):
            path = unquote(urlsplit(href.text or "").path).rstrip("/")
            if not path or path == own_path:
                continue
            if posixpath.dirname(path) != own_path:
                continue
            names.add(posixpath.basename(path))
        return sorted(names)

    def delete(self, key: str) -> None:
        url = self._url(check_key(key))
        response = self._request("DELETE", url)
        if response.status_code not in (200, 204, 404):
            raise StoreError(f"DELETE {url} returned HTTP {response.status_code}")

    def describe(self) -> str:
        return f"WebDAV {self.base_url}"
