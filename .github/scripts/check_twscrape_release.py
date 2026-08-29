"""Compare the pinned twscrape version against the latest release on PyPI.

Writes `pinned`, `latest` and `outdated` as GitHub Actions step outputs on
stdout. Prereleases and yanked files are skipped: we only want a version we
would actually pin.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import urllib.request

PYPROJECT = pathlib.Path(__file__).resolve().parents[2] / "pyproject.toml"
PIN = re.compile(r'"twscrape==([^"]+)"')


def pinned_version() -> str:
    match = PIN.search(PYPROJECT.read_text())
    if not match:
        sys.exit("No `twscrape==` pin found in pyproject.toml")
    return match.group(1)


def latest_version() -> str:
    with urllib.request.urlopen("https://pypi.org/pypi/twscrape/json", timeout=30) as r:
        data = json.load(r)
    version = data["info"]["version"]
    files = data["releases"].get(version) or []
    if not files or all(f.get("yanked") for f in files):
        sys.exit(f"Latest twscrape {version} has no usable files")
    return version


def main() -> None:
    pinned, latest = pinned_version(), latest_version()
    print(f"pinned={pinned}")
    print(f"latest={latest}")
    print(f"outdated={'true' if pinned != latest else 'false'}")


if __name__ == "__main__":
    main()
