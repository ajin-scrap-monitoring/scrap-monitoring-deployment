from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

REPOSITORY = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPOSITORY / "release" / "manifest.schema.json"
MANIFEST_PATH = REPOSITORY / "release" / "manifest.example.json"
BUILD_ASSETS = REPOSITORY / "release" / "build-assets"
PULL_IMAGES = REPOSITORY / "release" / "pull-images"
VALIDATE_MANIFEST = REPOSITORY / "release" / "validate-manifest"


class ReleaseManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_schema_and_example_manifest(self) -> None:
        Draft202012Validator.check_schema(self.schema)
        Draft202012Validator(self.schema).validate(self.manifest)

    def test_mutable_image_reference_is_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["targets"]["edge"]["components"] = [
            {
                "name": "camera-edge-agent",
                "image": "ghcr.io/example/camera-edge-agent:latest",
            }
        ]
        with self.assertRaises(ValidationError):
            Draft202012Validator(self.schema).validate(manifest)

    def test_publishable_manifest_requires_components(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATE_MANIFEST),
                "--version",
                "v0.0.1",
                "--manifest",
                str(MANIFEST_PATH),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, result.returncode)

    def test_publishable_manifest_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest_path = Path(temporary) / "v0.0.1.json"
            manifest_path.write_text(
                json.dumps(self.manifest_with_components()),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    sys.executable,
                    str(VALIDATE_MANIFEST),
                    "--version",
                    "v0.0.1",
                    "--manifest",
                    str(manifest_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

    def test_pulls_target_images_into_archives(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            manifest_path = temporary_path / "v0.0.1.json"
            output = temporary_path / "images"
            fake_bin = temporary_path / "bin"
            fake_bin.mkdir()
            fake_docker = fake_bin / "docker"
            fake_docker.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "pull" ]]; then
  exit 0
fi
if [[ "$1" == "image" && "$2" == "save" && "$3" == "--output" ]]; then
  printf '%s\\n' 'image archive fixture' > "$4"
  exit 0
fi
exit 1
""",
                encoding="utf-8",
            )
            fake_docker.chmod(0o755)
            manifest_path.write_text(
                json.dumps(self.manifest_with_components()),
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"

            subprocess.run(
                [str(PULL_IMAGES), str(manifest_path), str(output)],
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )

            self.assertTrue((output / "edge-images.tar").is_file())
            self.assertTrue((output / "server-images.tar").is_file())

    def manifest_with_components(self) -> dict[str, object]:
        manifest = copy.deepcopy(self.manifest)
        manifest["targets"]["edge"]["components"] = [
            {
                "name": "edge-component",
                "image": f"ghcr.io/example/edge@sha256:{'a' * 64}",
            }
        ]
        manifest["targets"]["server"]["components"] = [
            {
                "name": "server-component",
                "image": f"ghcr.io/example/server@sha256:{'b' * 64}",
            }
        ]
        return manifest


class ReleaseAssetsTest(unittest.TestCase):
    def test_builds_four_packages_and_checksum_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            edge_images = temporary_path / "edge-images.tar"
            server_images = temporary_path / "server-images.tar"
            output = temporary_path / "output"
            edge_images.write_bytes(b"edge image archive fixture\n")
            server_images.write_bytes(b"server image archive fixture\n")

            subprocess.run(
                [
                    sys.executable,
                    str(BUILD_ASSETS),
                    "--version",
                    "v0.0.1",
                    "--manifest",
                    str(MANIFEST_PATH),
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

            expected = {
                "scrap-monitoring-edge-v0.0.1-online.tar.gz",
                "scrap-monitoring-server-v0.0.1-online.tar.gz",
                "scrap-monitoring-edge-v0.0.1-offline.tar.gz",
                "scrap-monitoring-server-v0.0.1-offline.tar.gz",
                "SHA256SUMS",
            }
            self.assertEqual(expected, {path.name for path in output.iterdir()})
            self.assert_checksums(output)
            self.assert_package_members(output)

    def assert_checksums(self, output: Path) -> None:
        for line in (output / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            expected_digest, filename = line.split("  ", maxsplit=1)
            actual_digest = hashlib.sha256((output / filename).read_bytes()).hexdigest()
            self.assertEqual(expected_digest, actual_digest)

    def assert_package_members(self, output: Path) -> None:
        edge_online = output / "scrap-monitoring-edge-v0.0.1-online.tar.gz"
        edge_offline = output / "scrap-monitoring-edge-v0.0.1-offline.tar.gz"
        server_online = output / "scrap-monitoring-server-v0.0.1-online.tar.gz"
        server_offline = output / "scrap-monitoring-server-v0.0.1-offline.tar.gz"

        with tarfile.open(edge_online, "r:gz") as archive:
            names = set(archive.getnames())
            self.assertIn("release-manifest.json", names)
            self.assertIn("targets/edge/compose.yaml", names)
            self.assertIn("docs/configuration-management.md", names)
            self.assertIn("delivery/validate-environment", names)
            self.assertFalse(any(name.startswith("images/") for name in names))
        with tarfile.open(server_online, "r:gz") as archive:
            names = set(archive.getnames())
            self.assertIn("targets/server/compose.yaml", names)
            self.assertIn("pki/config/ca.template.json", names)
            self.assertIn("docs/configuration-management.md", names)
            self.assertIn("delivery/validate-environment", names)
            self.assertFalse(any(name.startswith("images/") for name in names))
        with tarfile.open(edge_offline, "r:gz") as archive:
            self.assertIn("images/edge-images.tar", archive.getnames())
        with tarfile.open(server_offline, "r:gz") as archive:
            self.assertIn("images/server-images.tar", archive.getnames())


if __name__ == "__main__":
    unittest.main()
