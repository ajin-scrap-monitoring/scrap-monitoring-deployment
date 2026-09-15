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
PACKAGE_SCHEMA_PATH = REPOSITORY / "release" / "package.schema.json"
MANIFEST_PATH = REPOSITORY / "release" / "manifest.example.json"
BUILD_ASSETS = REPOSITORY / "release" / "build-assets"
PULL_IMAGES = REPOSITORY / "release" / "pull-images"
VALIDATE_MANIFEST = REPOSITORY / "release" / "validate-manifest"


def component(
    name: str,
    image_name: str,
    digest_character: str,
) -> dict[str, object]:
    return {
        "name": name,
        "sourceRepository": (f"https://github.com/ajin-scrap-monitoring/{name}"),
        "sourceRevision": digest_character * 40,
        "version": "v0.1.0",
        "image": (
            f"ghcr.io/ajin-scrap-monitoring/{image_name}@sha256:{digest_character * 64}"
        ),
        "packageVisibility": "public",
        "pullAuthentication": "none",
        "notices": ["notices/README.md"],
    }


def manifest_with_components() -> dict[str, object]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["targets"]["edge"]["components"] = [
        component("edge-component", "edge", "a")
    ]
    manifest["targets"]["server"]["components"] = [
        component("server-component", "server", "b")
    ]
    return manifest


class ReleaseManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.package_schema = json.loads(PACKAGE_SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_schema_and_example_manifest(self) -> None:
        Draft202012Validator.check_schema(self.schema)
        Draft202012Validator(self.schema).validate(self.manifest)
        Draft202012Validator.check_schema(self.package_schema)

    def test_package_target_and_platform_must_match(self) -> None:
        package = {
            "schemaVersion": 1,
            "version": "v0.0.1",
            "target": "edge",
            "mode": "online",
            "platform": "linux/amd64",
            "manifestSha256": "a" * 64,
        }
        with self.assertRaises(ValidationError):
            Draft202012Validator(self.package_schema).validate(package)

    def test_mutable_image_reference_is_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["targets"]["edge"]["components"] = [
            component("camera-edge-agent", "camera-edge-agent", "a")
        ]
        manifest["targets"]["edge"]["components"][0]["image"] = (
            "ghcr.io/ajin-scrap-monitoring/camera-edge-agent:latest"
        )
        with self.assertRaises(ValidationError):
            Draft202012Validator(self.schema).validate(manifest)

    def test_publishable_manifest_rejects_noncanonical_image_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = manifest_with_components()
            manifest["targets"]["edge"]["components"][0]["image"] = (
                f"ghcr.io/ajin-scrap-monitoring/edge/../other@sha256:{'a' * 64}"
            )
            manifest_path = Path(temporary) / "v0.0.1.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATE_MANIFEST),
                    "--version",
                    "v0.0.1",
                    "--manifest",
                    str(manifest_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("invalid component image path", result.stderr)

    def test_component_provenance_is_required(self) -> None:
        manifest = manifest_with_components()
        del manifest["targets"]["edge"]["components"][0]["sourceRevision"]
        with self.assertRaises(ValidationError):
            Draft202012Validator(self.schema).validate(manifest)

    def test_private_package_requires_reason_and_read_authentication(self) -> None:
        manifest = manifest_with_components()
        private_component = manifest["targets"]["edge"]["components"][0]
        private_component["packageVisibility"] = "private"
        with self.assertRaises(ValidationError):
            Draft202012Validator(self.schema).validate(manifest)

        private_component["privateReason"] = "Contractual distribution limit"
        private_component["pullAuthentication"] = "ghcr-read-token"
        Draft202012Validator(self.schema).validate(manifest)

    def test_public_package_rejects_private_reason(self) -> None:
        manifest = manifest_with_components()
        manifest["targets"]["edge"]["components"][0]["privateReason"] = "Not applicable"
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
                json.dumps(manifest_with_components()),
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

    def test_publishable_manifest_rejects_duplicate_component_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = manifest_with_components()
            manifest["targets"]["server"]["components"][0]["name"] = "edge-component"
            manifest_path = Path(temporary) / "v0.0.1.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATE_MANIFEST),
                    "--version",
                    "v0.0.1",
                    "--manifest",
                    str(manifest_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("duplicate component name", result.stderr)

    def test_publishable_manifest_rejects_missing_notice(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = manifest_with_components()
            manifest["targets"]["edge"]["components"][0]["notices"] = [
                "notices/missing.md"
            ]
            manifest_path = Path(temporary) / "v0.0.1.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATE_MANIFEST),
                    "--version",
                    "v0.0.1",
                    "--manifest",
                    str(manifest_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)

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
                json.dumps(manifest_with_components()),
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


class ReleaseAssetsTest(unittest.TestCase):
    def test_rejects_symbolic_image_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            real_edge_images = temporary_path / "real-edge-images.tar"
            edge_images = temporary_path / "edge-images.tar"
            server_images = temporary_path / "server-images.tar"
            manifest_path = temporary_path / "v0.0.1.json"
            real_edge_images.write_bytes(b"edge image archive fixture\n")
            edge_images.symlink_to(real_edge_images)
            server_images.write_bytes(b"server image archive fixture\n")
            manifest_path.write_text(
                json.dumps(manifest_with_components()),
                encoding="utf-8",
            )
            result = subprocess.run(
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
                    str(temporary_path / "output"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)

    def test_builds_four_packages_and_checksum_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            edge_images = temporary_path / "edge-images.tar"
            server_images = temporary_path / "server-images.tar"
            output = temporary_path / "output"
            second_output = temporary_path / "second-output"
            manifest_path = temporary_path / "v0.0.1.json"
            edge_images.write_bytes(b"edge image archive fixture\n")
            server_images.write_bytes(b"server image archive fixture\n")
            manifest_path.write_text(
                json.dumps(manifest_with_components()),
                encoding="utf-8",
            )

            for destination in (output, second_output):
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
                        str(destination),
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
            self.assertEqual(
                {path.name: path.read_bytes() for path in output.iterdir()},
                {path.name: path.read_bytes() for path in second_output.iterdir()},
            )

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
            package = json.load(archive.extractfile("release-package.json"))
            manifest_bytes = archive.extractfile("release-manifest.json").read()
            self.assertIn("release-manifest.json", names)
            self.assertIn("release/package.schema.json", names)
            self.assertIn("targets/edge/compose.yaml", names)
            self.assertIn("docs/configuration-management.md", names)
            self.assertIn("delivery/validate-environment", names)
            self.assertIn("delivery/online/fetch-release", names)
            self.assertNotIn("delivery/offline/import-bundle", names)
            self.assertNotIn("delivery/offline/build-bundle", names)
            self.assertNotIn("release/build-assets", names)
            self.assertNotIn("release/pull-images", names)
            self.assertFalse(any(name.startswith("images/") for name in names))
            self.assertEqual("edge", package["target"])
            self.assertEqual("online", package["mode"])
            self.assertEqual("linux/arm64", package["platform"])
            self.assertEqual(
                hashlib.sha256(manifest_bytes).hexdigest(),
                package["manifestSha256"],
            )
            self.assertEqual(
                0o755,
                archive.getmember("delivery/apply-release").mode,
            )
            self.assertEqual(
                0o644,
                archive.getmember("targets/edge/compose.yaml").mode,
            )
            Draft202012Validator(
                json.loads(PACKAGE_SCHEMA_PATH.read_text(encoding="utf-8"))
            ).validate(package)
        with tarfile.open(server_online, "r:gz") as archive:
            names = set(archive.getnames())
            self.assertIn("targets/server/compose.yaml", names)
            self.assertIn("pki/config/ca.template.json", names)
            self.assertIn("docs/configuration-management.md", names)
            self.assertIn("delivery/validate-environment", names)
            self.assertFalse(any(name.startswith("images/") for name in names))
        with tarfile.open(edge_offline, "r:gz") as archive:
            self.assertIn("images/edge-images.tar", archive.getnames())
            self.assertIn("delivery/offline/bundle_importer.py", archive.getnames())
            self.assertIn("delivery/offline/import-bundle", archive.getnames())
            self.assertNotIn("delivery/online/fetch-release", archive.getnames())
            package = json.load(archive.extractfile("release-package.json"))
            self.assertEqual("images/edge-images.tar", package["imageArchive"])
        with tarfile.open(server_offline, "r:gz") as archive:
            self.assertIn("images/server-images.tar", archive.getnames())


if __name__ == "__main__":
    unittest.main()
