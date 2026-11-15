from __future__ import annotations

import hashlib
import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "release"))

import dashboard_assets
from typing_extensions import Self

MEMBERS = (
    "https.conf",
    "upstreams/10-dashboard-upstreams.conf",
    "runtime/20-dashboard-locations.conf",
)


def archive_bytes(names: tuple[str, ...] = (), *, symlink: str | None = None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name in names or tuple(f"deploy/example/nginx/{m}" for m in MEMBERS):
            content = f"fixture {name}\n".encode()
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
        if symlink:
            info = tarfile.TarInfo(symlink)
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            archive.addfile(info)
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *arguments: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.content[:size] if size >= 0 else self.content


def write_directory(
    directory: Path, archive: bytes, checksum: str | None = None
) -> None:
    digest = checksum or hashlib.sha256(archive).hexdigest()
    (directory / "deployment-example.tar.gz").write_bytes(archive)
    (directory / "SHA256SUMS").write_text(
        f"{digest}  deployment-example.tar.gz\n", encoding="utf-8"
    )
    (directory / "release-version.txt").write_text("v0.6.0\n", encoding="utf-8")


class DashboardAssetsTest(unittest.TestCase):
    def test_returns_fixed_payload_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            write_directory(directory, archive_bytes())
            files = dashboard_assets.verified_nginx_files(directory, "v0.6.0")
        self.assertEqual(
            [f"targets/server/dashboard/nginx/{name}" for name in MEMBERS],
            [name for name, _ in files],
        )

    def test_rejects_checksum_version_member_and_link_problems(self) -> None:
        cases = {
            "checksum": (archive_bytes(), "0" * 64, "v0.6.0"),
            "version": (archive_bytes(), None, "v0.7.0"),
            "missing": (
                archive_bytes(("deploy/example/nginx/https.conf",)),
                None,
                "v0.6.0",
            ),
            "traversal": (
                archive_bytes(
                    (
                        "deploy/../escape",
                        *(f"deploy/example/nginx/{m}" for m in MEMBERS),
                    )
                ),
                None,
                "v0.6.0",
            ),
            "symlink": (
                archive_bytes(symlink="deploy/example/nginx/link"),
                None,
                "v0.6.0",
            ),
        }
        for label, (archive, checksum, version) in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                write_directory(directory, archive, checksum)
                with self.assertRaises(ValueError):
                    dashboard_assets.verified_nginx_files(directory, version)

    def test_fetch_verifies_checksum_and_uses_pinned_release_url(self) -> None:
        archive = archive_bytes()
        urls: list[str] = []

        def opener(url: str, timeout: int) -> FakeResponse:
            urls.append(url)
            if url.endswith("SHA256SUMS"):
                digest = hashlib.sha256(archive).hexdigest()
                return FakeResponse(f"{digest}  deployment-example.tar.gz\n".encode())
            return FakeResponse(archive)

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "out"
            dashboard_assets.fetch_dashboard_assets("v0.6.0", directory, opener)
            self.assertEqual(
                3, len(dashboard_assets.verified_nginx_files(directory, "v0.6.0"))
            )
        self.assertTrue(all("/releases/download/v0.6.0/" in url for url in urls))

        def tampered(url: str, timeout: int) -> FakeResponse:
            if url.endswith("SHA256SUMS"):
                return FakeResponse(b"0" * 64 + b"  deployment-example.tar.gz\n")
            return FakeResponse(archive)

        with tempfile.TemporaryDirectory() as temporary, self.assertRaises(ValueError):
            dashboard_assets.fetch_dashboard_assets(
                "v0.6.0", Path(temporary) / "x", tampered
            )

    def test_requires_one_manifest_dashboard_version(self) -> None:
        manifest = {
            "targets": {
                "server": {"components": [{"name": "other", "version": "v1.0.0"}]}
            }
        }
        with self.assertRaises(ValueError):
            dashboard_assets.dashboard_version(manifest)
