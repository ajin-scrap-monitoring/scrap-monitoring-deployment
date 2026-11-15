"""Fetch and verify the Dashboard Release nginx files used by the Server target."""

from __future__ import annotations

import hashlib
import io
import re
import tarfile
from collections.abc import Callable
from pathlib import Path
from urllib.request import urlopen

DASHBOARD_COMPONENT = "scrap-monitoring-dashboard"
DASHBOARD_REPOSITORY = "ajin-scrap-monitoring/scrap-monitoring-dashboard"
ARCHIVE_NAME = "deployment-example.tar.gz"
CHECKSUM_NAME = "SHA256SUMS"
VERSION_NAME = "release-version.txt"
MAX_ASSET_BYTES = 1024 * 1024
VERSION_PATTERN = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+")
ARCHIVE_PREFIX = "deploy/example/nginx/"
PAYLOAD_PREFIX = "targets/server/dashboard/nginx/"
# Archive members the Server target consumes; the destinations are fixed here.
REQUIRED_MEMBERS = (
    "https.conf",
    "upstreams/10-dashboard-upstreams.conf",
    "runtime/20-dashboard-locations.conf",
)

Opener = Callable[..., object]


def dashboard_version(manifest: dict[str, object]) -> str:
    components = manifest["targets"]["server"]["components"]  # type: ignore[index]
    versions = [
        c.get("version", "") for c in components if c["name"] == DASHBOARD_COMPONENT
    ]
    if len(versions) != 1 or not VERSION_PATTERN.fullmatch(versions[0]):
        raise ValueError(
            "manifest must pin exactly one Dashboard Release version (a deployment-build image has none)"
        )
    return versions[0]


def download(url: str, opener: Opener = urlopen) -> bytes:
    if not url.startswith("https://github.com/"):
        raise ValueError("Dashboard asset URL must use HTTPS on github.com")
    with opener(url, timeout=30) as response:  # type: ignore[operator]
        content = response.read(MAX_ASSET_BYTES + 1)
    if len(content) > MAX_ASSET_BYTES:
        raise ValueError("Dashboard asset exceeds the size limit")
    return content


def checksum_for(checksums: bytes, name: str) -> str:
    matches = []
    for line in checksums.decode("utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64}) [ *](\S+)", line)
        if match and match.group(2) == name:
            matches.append(match.group(1))
    if len(matches) != 1:
        raise ValueError(f"checksum entry is missing or ambiguous: {name}")
    return matches[0]


def fetch_dashboard_assets(
    version: str, directory: Path, opener: Opener = urlopen
) -> None:
    """Download the archive and its SHA256SUMS, verify, and write them to directory."""
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError("invalid Dashboard Release version")
    base = f"https://github.com/{DASHBOARD_REPOSITORY}/releases/download/{version}/"
    archive = download(base + ARCHIVE_NAME, opener)
    checksums = download(base + CHECKSUM_NAME, opener)
    if hashlib.sha256(archive).hexdigest() != checksum_for(checksums, ARCHIVE_NAME):
        raise ValueError("Dashboard asset checksum mismatch")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ARCHIVE_NAME).write_bytes(archive)
    (directory / CHECKSUM_NAME).write_bytes(checksums)
    (directory / VERSION_NAME).write_text(version + "\n", encoding="utf-8")


def read_regular(directory: Path, name: str) -> bytes:
    path = directory / name
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Dashboard asset is missing or not a regular file: {name}")
    return path.read_bytes()


def verified_nginx_files(directory: Path, version: str) -> list[tuple[str, bytes]]:
    """Verify the fetched asset and return (payload path, content) pairs."""
    recorded = read_regular(directory, VERSION_NAME).decode("utf-8").strip()
    if recorded != version:
        raise ValueError("fetched Dashboard assets do not match the manifest version")
    archive = read_regular(directory, ARCHIVE_NAME)
    checksums = read_regular(directory, CHECKSUM_NAME)
    if hashlib.sha256(archive).hexdigest() != checksum_for(checksums, ARCHIVE_NAME):
        raise ValueError("Dashboard asset checksum mismatch")
    found: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for member in tar.getmembers():
            parts = member.name.split("/")
            if (
                member.name.startswith("/")
                or ".." in parts
                or member.issym()
                or member.islnk()
                or not (member.isfile() or member.isdir())
            ):
                raise ValueError(f"unsafe Dashboard asset member: {member.name}")
            if member.isfile() and member.name.startswith(ARCHIVE_PREFIX):
                relative = member.name.removeprefix(ARCHIVE_PREFIX)
                if relative in REQUIRED_MEMBERS:
                    if relative in found:
                        raise ValueError(
                            f"duplicate Dashboard asset member: {relative}"
                        )
                    stream = tar.extractfile(member)
                    assert stream is not None
                    found[relative] = stream.read(MAX_ASSET_BYTES + 1)
    missing = [name for name in REQUIRED_MEMBERS if name not in found]
    if missing:
        raise ValueError(f"Dashboard asset member is missing: {missing[0]}")
    return [(PAYLOAD_PREFIX + name, found[name]) for name in REQUIRED_MEMBERS]
