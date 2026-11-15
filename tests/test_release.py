from __future__ import annotations

import copy
import hashlib
import io
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
VERIFY_ASSETS = REPOSITORY / "release" / "verify-assets"


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
        component("scrap-monitoring-dashboard", "server", "b")
    ]
    return manifest


def dashboard_asset_directory(temporary_path: Path) -> Path:
    directory = temporary_path / "dashboard-assets"
    directory.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name in (
            "https.conf",
            "upstreams/10-dashboard-upstreams.conf",
            "runtime/20-dashboard-locations.conf",
        ):
            content = f"# fixture {name}\n".encode()
            info = tarfile.TarInfo(f"deploy/example/nginx/{name}")
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    content = buffer.getvalue()
    (directory / "deployment-example.tar.gz").write_bytes(content)
    (directory / "SHA256SUMS").write_text(
        f"{hashlib.sha256(content).hexdigest()}  deployment-example.tar.gz\n",
        encoding="utf-8",
    )
    (directory / "release-version.txt").write_text("v0.1.0\n", encoding="utf-8")
    return directory


def image_directory(temporary_path: Path) -> Path:
    directory = temporary_path / "images"
    directory.mkdir(parents=True, exist_ok=True)
    for target in ("edge", "server"):
        directory.joinpath(f"{target}-images.tar").write_bytes(
            f"{target} image archive fixture\n".encode()
        )
    return directory


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
            "schemaVersion": 2,
            "version": "v0.0.1",
            "target": "edge",
            "mode": "online",
            "platform": "linux/amd64",
            "manifestSha256": "a" * 64,
        }
        with self.assertRaises(ValidationError):
            Draft202012Validator(self.package_schema).validate(package)

    def build_component(self) -> dict[str, object]:
        entry = component(
            "ajin-camera-media-service", "scrap-monitoring-deployment/x", "c"
        )
        del entry["version"]
        entry["imageProvider"] = "deployment-build"
        return entry

    def test_deployment_build_component_has_no_version_and_own_namespace(self) -> None:
        validator = Draft202012Validator(self.schema)
        manifest = copy.deepcopy(self.manifest)
        manifest["targets"]["server"]["components"] = [self.build_component()]
        validator.validate(manifest)
        sys.path.insert(0, str(REPOSITORY / "delivery"))
        import release_verifier

        release_verifier.validate_component(
            manifest["targets"]["server"]["components"][0]
        )

        with_version = copy.deepcopy(manifest)
        with_version["targets"]["server"]["components"][0]["version"] = "v0.1.0"
        with self.assertRaises(ValidationError):
            validator.validate(with_version)
        with self.assertRaises(ValueError):
            release_verifier.validate_component(
                with_version["targets"]["server"]["components"][0]
            )

        foreign = copy.deepcopy(manifest)
        foreign["targets"]["server"]["components"][0]["image"] = (
            "ghcr.io/ajin-scrap-monitoring/other@sha256:" + "c" * 64
        )
        with self.assertRaises(ValidationError):
            validator.validate(foreign)
        with self.assertRaises(ValueError):
            release_verifier.validate_component(
                foreign["targets"]["server"]["components"][0]
            )

    def test_component_release_requires_version(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        del manifest["targets"]["edge"]["components"][0]["version"]
        with self.assertRaises(ValidationError):
            Draft202012Validator(self.schema).validate(manifest)

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

    def test_release_workflow_rejects_private_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = manifest_with_components()
            private_component = manifest["targets"]["edge"]["components"][0]
            private_component["packageVisibility"] = "private"
            private_component["pullAuthentication"] = "ghcr-read-token"
            private_component["privateReason"] = "Contractual distribution limit"
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
                    "--require-public-packages",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("private package is not supported", result.stderr)

    def test_publishable_manifest_requires_components(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = copy.deepcopy(self.manifest)
            manifest["targets"]["edge"]["components"] = []
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
printf '%s\\n' "$*" >> "${DOCKER_LOG}"
if [[ "$1" == "pull" ]]; then
  printf '%s\\n' "$3" > "${DOCKER_LOG}.platform"
  exit 0
fi
if [[ "$1" == "image" && "$2" == "inspect" ]]; then
  printf '%s\\n' "${FAKE_PLATFORM:-$(cat "${DOCKER_LOG}.platform")}"
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
            environment["DOCKER_LOG"] = str(temporary_path / "docker.log")

            subprocess.run(
                [str(PULL_IMAGES), str(manifest_path), str(output)],
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )

            mismatch = subprocess.run(
                [str(PULL_IMAGES), str(manifest_path), str(temporary_path / "other")],
                check=False,
                capture_output=True,
                text=True,
                env={**environment, "FAKE_PLATFORM": "linux/s390x"},
            )
            self.assertNotEqual(0, mismatch.returncode)
            self.assertIn("does not match", mismatch.stderr)

            for target in ("edge", "server"):
                self.assertTrue((output / f"{target}-images.tar").is_file())
            pulled_images = {
                line.removeprefix("pull --platform linux/arm64 ")
                if line.startswith("pull --platform linux/arm64 ")
                else line.removeprefix("pull --platform linux/amd64 ")
                for line in (temporary_path / "docker.log")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.startswith("pull --platform")
            }
            self.assertEqual(
                {
                    f"ghcr.io/ajin-scrap-monitoring/edge@sha256:{'a' * 64}",
                    f"ghcr.io/ajin-scrap-monitoring/server@sha256:{'b' * 64}",
                },
                pulled_images,
            )


class ReleaseAssetsTest(unittest.TestCase):
    def build_assets(self, temporary_path: Path) -> Path:
        images = image_directory(temporary_path)
        output = temporary_path / "output"
        manifest_path = temporary_path / "v0.0.1.json"
        manifest_path.write_text(
            json.dumps(manifest_with_components()), encoding="utf-8"
        )
        subprocess.run(
            [
                sys.executable,
                str(BUILD_ASSETS),
                "--version",
                "v0.0.1",
                "--manifest",
                str(manifest_path),
                "--image-directory",
                str(images),
                "--dashboard-asset-directory",
                str(dashboard_asset_directory(temporary_path)),
                "--output",
                str(output),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return output

    def test_rejects_symbolic_image_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            images = image_directory(temporary_path)
            real_edge_images = temporary_path / "real-edge-images.tar"
            edge_images = images / "edge-images.tar"
            manifest_path = temporary_path / "v0.0.1.json"
            real_edge_images.write_bytes(b"edge image archive fixture\n")
            edge_images.unlink()
            edge_images.symlink_to(real_edge_images)
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
                    "--image-directory",
                    str(images),
                    "--dashboard-asset-directory",
                    str(dashboard_asset_directory(temporary_path)),
                    "--output",
                    str(temporary_path / "output"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)

    def test_builds_eight_packages_and_checksum_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            images = image_directory(temporary_path)
            output = temporary_path / "output"
            second_output = temporary_path / "second-output"
            manifest_path = temporary_path / "v0.0.1.json"
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
                        "--image-directory",
                        str(images),
                        "--dashboard-asset-directory",
                        str(dashboard_asset_directory(temporary_path)),
                        "--output",
                        str(destination),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )

            expected = {
                f"scrap-monitoring-{target}-v0.0.1-{mode}.tar.gz"
                for target in ("edge", "server")
                for mode in ("online", "offline")
            }
            expected.add("SHA256SUMS")
            self.assertEqual(expected, {path.name for path in output.iterdir()})
            self.assert_checksums(output)
            self.assert_package_members(output)
            self.assertEqual(
                {path.name: path.read_bytes() for path in output.iterdir()},
                {path.name: path.read_bytes() for path in second_output.iterdir()},
            )

    def test_verifies_complete_release_asset_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = self.build_assets(Path(temporary))
            result = subprocess.run(
                [
                    sys.executable,
                    str(VERIFY_ASSETS),
                    "--version",
                    "v0.0.1",
                    "--directory",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)

    def test_asset_verifier_rejects_unexpected_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = self.build_assets(Path(temporary))
            (output / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(VERIFY_ASSETS),
                    "--version",
                    "v0.0.1",
                    "--directory",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("asset set does not match", result.stderr)

    def test_asset_verifier_rejects_symbolic_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            output = self.build_assets(temporary_path)
            symbolic_output = temporary_path / "symbolic-output"
            symbolic_output.symlink_to(output, target_is_directory=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(VERIFY_ASSETS),
                    "--version",
                    "v0.0.1",
                    "--directory",
                    str(symbolic_output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("missing or symbolic", result.stderr)

    def test_asset_verifier_rejects_extra_checksum_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = self.build_assets(Path(temporary))
            checksums = output / "SHA256SUMS"
            checksums.write_text(
                checksums.read_text(encoding="utf-8")
                + f"{'0' * 64}  unexpected.tar.gz\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(VERIFY_ASSETS),
                    "--version",
                    "v0.0.1",
                    "--directory",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("checksum asset set does not match", result.stderr)

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
            self.assertIn("delivery/quick-start", names)
            self.assertIn("delivery/release_applier.py", names)
            self.assertNotIn("delivery/install-dashboard-configuration", names)
            self.assertIn("delivery/online/fetch-release", names)
            self.assertIn("delivery/quick-start", names)
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
                0o755,
                archive.getmember("delivery/quick-start").mode,
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
            self.assertIn("delivery/dashboard_configuration.py", names)
            for entrypoint in (
                "delivery/install-dashboard-configuration",
                "delivery/validate-dashboard-configuration",
            ):
                self.assertIn(entrypoint, names)
                self.assertEqual(0o755, archive.getmember(entrypoint).mode)
            self.assertFalse(any(name.startswith("images/") for name in names))
        with tarfile.open(edge_offline, "r:gz") as archive:
            self.assertIn("delivery/edge_configuration.py", archive.getnames())
            self.assertIn("delivery/validate-edge-configuration", archive.getnames())
            self.assertEqual(
                0o755, archive.getmember("delivery/validate-edge-configuration").mode
            )
            self.assertIn("images/edge-images.tar", archive.getnames())
            self.assertIn("delivery/offline/bundle_importer.py", archive.getnames())
            self.assertIn("delivery/offline/import-bundle", archive.getnames())
            self.assertNotIn("delivery/quick-start", archive.getnames())
            self.assertNotIn("delivery/online/fetch-release", archive.getnames())
            package = json.load(archive.extractfile("release-package.json"))
            self.assertEqual("images/edge-images.tar", package["imageArchive"])
        with tarfile.open(server_offline, "r:gz") as archive:
            self.assertIn("images/server-images.tar", archive.getnames())
            self.assertIn(
                "delivery/install-dashboard-configuration", archive.getnames()
            )


if __name__ == "__main__":
    unittest.main()
