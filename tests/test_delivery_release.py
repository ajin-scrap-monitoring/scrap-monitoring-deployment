from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

from tests.test_release import BUILD_ASSETS, manifest_with_components

REPOSITORY = Path(__file__).resolve().parents[1]
VERIFY_RELEASE = REPOSITORY / "delivery" / "verify-release"
FETCH_RELEASE = REPOSITORY / "delivery" / "online" / "fetch-release"
IMPORT_BUNDLE = REPOSITORY / "delivery" / "offline" / "import-bundle"


def build_assets(temporary_path: Path) -> Path:
    manifest_path = temporary_path / "v0.0.1.json"
    edge_images = temporary_path / "edge-images.tar"
    server_images = temporary_path / "server-images.tar"
    output = temporary_path / "assets"
    manifest_path.write_text(
        json.dumps(manifest_with_components()),
        encoding="utf-8",
    )
    edge_images.write_bytes(b"edge image archive fixture\n")
    server_images.write_bytes(b"server image archive fixture\n")
    subprocess.run(
        [
            sys.executable,
            str(BUILD_ASSETS),
            "--version",
            "v0.0.1",
            "--manifest",
            str(manifest_path),
            "--edge-image-archive",
            str(edge_images),
            "--server-image-archive",
            str(server_images),
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output


class VerifyReleaseTest(unittest.TestCase):
    def test_verifies_online_and_offline_packages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            assets = build_assets(Path(temporary))
            for target in ("edge", "server"):
                for mode in ("online", "offline"):
                    package = assets / f"scrap-monitoring-{target}-v0.0.1-{mode}.tar.gz"
                    with self.subTest(target=target, mode=mode):
                        subprocess.run(
                            [
                                str(VERIFY_RELEASE),
                                "--version",
                                "v0.0.1",
                                "--target",
                                target,
                                "--package",
                                str(package),
                                "--checksums",
                                str(assets / "SHA256SUMS"),
                            ],
                            check=True,
                            capture_output=True,
                            text=True,
                        )

    def test_rejects_checksum_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            assets = build_assets(Path(temporary))
            package = assets / "scrap-monitoring-edge-v0.0.1-online.tar.gz"
            with package.open("ab") as output:
                output.write(b"tampered")
            result = subprocess.run(
                [
                    str(VERIFY_RELEASE),
                    "--version",
                    "v0.0.1",
                    "--target",
                    "edge",
                    "--package",
                    str(package),
                    "--checksums",
                    str(assets / "SHA256SUMS"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("checksum does not match", result.stderr)

    def test_rejects_unsafe_archive_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            package = temporary_path / "scrap-monitoring-edge-v0.0.1-online.tar.gz"
            with tarfile.open(package, "w:gz") as archive:
                member = tarfile.TarInfo("../escape")
                member.size = 0
                member.mode = 0o644
                member.uid = 0
                member.gid = 0
                member.uname = "root"
                member.gname = "root"
                member.mtime = 0
                archive.addfile(member)
            checksum = hashlib.sha256(package.read_bytes()).hexdigest()
            checksums = temporary_path / "SHA256SUMS"
            checksums.write_text(
                f"{checksum}  {package.name}\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    str(VERIFY_RELEASE),
                    "--version",
                    "v0.0.1",
                    "--target",
                    "edge",
                    "--package",
                    str(package),
                    "--checksums",
                    str(checksums),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("unsafe archive path", result.stderr)

    def test_rejects_requested_target_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            assets = build_assets(Path(temporary))
            package = assets / "scrap-monitoring-edge-v0.0.1-online.tar.gz"
            result = subprocess.run(
                [
                    str(VERIFY_RELEASE),
                    "--version",
                    "v0.0.1",
                    "--target",
                    "server",
                    "--package",
                    str(package),
                    "--checksums",
                    str(assets / "SHA256SUMS"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)


class FetchReleaseTest(unittest.TestCase):
    def install_fake_curl(self, temporary_path: Path) -> Path:
        fake_bin = temporary_path / "bin"
        fake_bin.mkdir()
        fake_curl = fake_bin / "curl"
        fake_curl.write_text(
            """#!/usr/bin/env bash
set -euo pipefail
output=""
url="${*: -1}"
while [[ "$#" -gt 0 ]]; do
  if [[ "$1" == "--output" ]]; then
    output="$2"
    shift 2
  else
    shift
  fi
done
name="$(basename "${url}")"
if [[ "${FAIL_CHECKSUM:-0}" == "1" && "${name}" == "SHA256SUMS" ]]; then
  exit 22
fi
cp "${FIXTURE_DIR}/${name}" "${output}"
""",
            encoding="utf-8",
        )
        fake_curl.chmod(0o755)
        return fake_bin

    def test_fetches_and_publishes_verified_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            assets = build_assets(temporary_path)
            fake_bin = self.install_fake_curl(temporary_path)
            output = temporary_path / "fetched"
            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
            environment["FIXTURE_DIR"] = str(assets)
            subprocess.run(
                [
                    str(FETCH_RELEASE),
                    "--version",
                    "v0.0.1",
                    "--target",
                    "edge",
                    "--output",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(
                {
                    "SHA256SUMS",
                    "scrap-monitoring-edge-v0.0.1-online.tar.gz",
                },
                {path.name for path in output.iterdir()},
            )

    def test_fetch_failure_does_not_publish_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            assets = build_assets(temporary_path)
            fake_bin = self.install_fake_curl(temporary_path)
            output = temporary_path / "fetched"
            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
            environment["FIXTURE_DIR"] = str(assets)
            environment["FAIL_CHECKSUM"] = "1"
            result = subprocess.run(
                [
                    str(FETCH_RELEASE),
                    "--version",
                    "v0.0.1",
                    "--target",
                    "edge",
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertFalse(output.exists())
            self.assertEqual([], list(temporary_path.glob(".fetched.*")))


class OfflineImportTest(unittest.TestCase):
    def install_fake_docker(self, temporary_path: Path) -> Path:
        fake_bin = temporary_path / "bin"
        fake_bin.mkdir()
        fake_docker = fake_bin / "docker"
        fake_docker.write_text(
            """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "image" && "$2" == "load" ]]; then
  cat > "${LOADED_ARCHIVE}"
  exit "${LOAD_EXIT_CODE:-0}"
fi
if [[ "$1" == "image" && "$2" == "inspect" ]]; then
  printf '%s\n' "${INSPECT_PLATFORM}"
  printf '%s\n' "${*: -1}" >> "${INSPECT_LOG}"
  exit 0
fi
exit 1
""",
            encoding="utf-8",
        )
        fake_docker.chmod(0o755)
        return fake_bin

    def environment(self, temporary_path: Path, fake_bin: Path) -> dict[str, str]:
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
        environment["LOADED_ARCHIVE"] = str(temporary_path / "loaded.tar")
        environment["INSPECT_LOG"] = str(temporary_path / "inspect.log")
        environment["INSPECT_PLATFORM"] = "linux/arm64"
        return environment

    def test_imports_images_and_verifies_digest_platform(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            assets = build_assets(temporary_path)
            fake_bin = self.install_fake_docker(temporary_path)
            environment = self.environment(temporary_path, fake_bin)
            bundle = assets / "scrap-monitoring-edge-v0.0.1-offline.tar.gz"
            subprocess.run(
                [
                    str(IMPORT_BUNDLE),
                    "--version",
                    "v0.0.1",
                    "--target",
                    "edge",
                    "--bundle",
                    str(bundle),
                    "--checksums",
                    str(assets / "SHA256SUMS"),
                ],
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(
                (temporary_path / "edge-images.tar").read_bytes(),
                (temporary_path / "loaded.tar").read_bytes(),
            )
            self.assertEqual(
                [f"ghcr.io/ajin-scrap-monitoring/edge@sha256:{'a' * 64}"],
                (temporary_path / "inspect.log")
                .read_text(encoding="utf-8")
                .splitlines(),
            )

    def test_rejects_platform_mismatch_after_import(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            assets = build_assets(temporary_path)
            fake_bin = self.install_fake_docker(temporary_path)
            environment = self.environment(temporary_path, fake_bin)
            environment["INSPECT_PLATFORM"] = "linux/amd64"
            bundle = assets / "scrap-monitoring-edge-v0.0.1-offline.tar.gz"
            result = subprocess.run(
                [
                    str(IMPORT_BUNDLE),
                    "--version",
                    "v0.0.1",
                    "--target",
                    "edge",
                    "--bundle",
                    str(bundle),
                    "--checksums",
                    str(assets / "SHA256SUMS"),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("platform does not match", result.stderr)

    def test_rejects_online_package_before_docker_load(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            assets = build_assets(temporary_path)
            fake_bin = self.install_fake_docker(temporary_path)
            environment = self.environment(temporary_path, fake_bin)
            package = assets / "scrap-monitoring-edge-v0.0.1-online.tar.gz"
            result = subprocess.run(
                [
                    str(IMPORT_BUNDLE),
                    "--version",
                    "v0.0.1",
                    "--target",
                    "edge",
                    "--bundle",
                    str(package),
                    "--checksums",
                    str(assets / "SHA256SUMS"),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertFalse((temporary_path / "loaded.tar").exists())


if __name__ == "__main__":
    unittest.main()
