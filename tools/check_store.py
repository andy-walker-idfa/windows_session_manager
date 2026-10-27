"""Check a WebDAV network store from the command line (the configurator has the same checks).

    python tools/check_store.py https://nas.home.arpa:30036/timemanager --user timemanager --ca-file nas.crt
    python tools/check_store.py --instance "C:\\Program Files\\TimeManager\\instance.toml"

The password is read from the TM_PASSWORD environment variable if set, otherwise asked for
without echo (or read from instance.toml with --instance).
"""

import argparse
import getpass
import os
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.diagnostics import check_webdav  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", nargs="?")
    parser.add_argument("--user", default="")
    parser.add_argument("--ca-file", default="")
    parser.add_argument("--instance", type=Path, help="read url/username/password/ca_file from instance.toml")
    parser.add_argument("--http-port", type=int, default=30034, help="plain HTTP port that must NOT answer")
    args = parser.parse_args()

    if args.instance:
        remote = tomllib.loads(args.instance.read_text(encoding="utf-8"))["remote"]
        url, user, password, ca = remote["url"], remote.get("username", ""), remote.get("password", ""), remote.get("ca_file", "")
    else:
        if not args.url:
            parser.error("give a URL or --instance")
        url, user, ca = args.url, args.user, args.ca_file
        password = os.environ.get("TM_PASSWORD") or (getpass.getpass(f"Password for {user}: ") if user else "")
    print(f"Store: {url}\nCertificate file: {ca or '(system trust store)'}\n")

    results = []
    for name, ok, detail in check_webdav(url, user, password, ca, http_port=args.http_port):
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    print(f"\n{sum(results)}/{len(results)} checks passed.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
