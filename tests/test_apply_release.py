from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from delivery.release_applier import CertificateSnapshot, apply_release
from tests.test_release import BUILD_ASSETS, manifest_with_components

REPOSITORY = Path(__file__).resolve().parents[1]


def build_assets(temporary_path: Path, version: str) -> Path:
    manifest = manifest_with_components()
    manifest["version"] = version
    manifest_path = temporary_path / f"{version}.json"
    edge_images = temporary_path / f"{version}-edge-images.tar"
    server_images = temporary_path / f"{version}-server-images.tar"
    output = temporary_path / f"{version}-assets"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    edge_images.write_bytes(b"edge image archive fixture\n")
    server_images.write_bytes(b"server image archive fixture\n")
    subprocess.run(
        [
            sys.executable,
            str(BUILD_ASSETS),
            "--version",
            version,
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


def write_edge_credential(
    host_root: Path,
    name: str,
    kind: str,
    identity: str,
) -> None:
    secret_directory = host_root / "opt" / "ajin" / "secrets"
    secret_directory.mkdir(parents=True, exist_ok=True)
    secret_directory.chmod(0o700)
    token = secret_directory / name
    with token.open("xb") as output:
        subprocess.run(
            ["openssl", "rand", "-hex", "32"],
            check=True,
            stdout=output,
        )
        output.truncate(64)
    token.chmod(0o600)
    digest = hashlib.sha256(token.read_bytes()).hexdigest()
    metadata = secret_directory / f"{name}.metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "kind": kind,
                "identity": identity,
                "digest": digest,
            }
        ),
        encoding="utf-8",
    )
    metadata.chmod(0o600)


def prepare_edge_host(temporary_path: Path) -> tuple[Path, Path]:
    host_root = temporary_path / "host"
    environment_file = host_root / "etc" / "scrap-monitoring" / "edge.env"
    environment_file.parent.mkdir(parents=True)
    environment_file.write_text(
        (REPOSITORY / "targets" / "edge" / ".env.example").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    environment_file.chmod(0o640)
    config = host_root / "opt" / "ajin" / "config" / "edge.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "SITE_ID": "example-site",
                "EDGE_ID": "example-edge",
                "CAMERA_ID": "example-camera",
                "CONFIG_REVISION": "example-config-r1",
            }
        ),
        encoding="utf-8",
    )
    (host_root / "opt" / "ajin" / "runtime").mkdir(parents=True)
    camera = host_root / "dev" / "video0"
    camera.parent.mkdir(parents=True)
    camera.write_text("camera fixture\n", encoding="utf-8")
    root_ca = (
        host_root
        / "usr"
        / "local"
        / "share"
        / "ca-certificates"
        / "scrap-monitoring-root-ca.crt"
    )
    root_ca.parent.mkdir(parents=True)
    root_ca.write_text("Root CA fixture\n", encoding="utf-8")
    write_edge_credential(
        host_root,
        "edge-token",
        "edge-backend",
        "example-edge",
    )
    write_edge_credential(
        host_root,
        "camera-token",
        "camera-media",
        "example-camera",
    )
    return host_root, environment_file


def install_fake_commands(temporary_path: Path) -> Path:
    fake_bin = temporary_path / "bin"
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${DOCKER_LOG}"
if [[ "$1" == "pull" ]]; then
  exit 0
fi
if [[ "$1" == "image" && "$2" == "load" ]]; then
  cat > "${LOADED_ARCHIVE}"
  exit "${LOAD_EXIT_CODE:-0}"
fi
if [[ "$1" == "image" && "$2" == "inspect" ]]; then
  printf '%s\n' "${INSPECT_PLATFORM:-linux/arm64}"
  exit "${INSPECT_EXIT_CODE:-0}"
fi
if [[ "$1" == "compose" && "${*: -2}" == "config --services" ]]; then
  if [[ "${COMPOSE_NO_SERVICES:-0}" != "1" ]]; then
    printf '%s\n' 'app'
  fi
  exit 0
fi
if [[ "$1" == "compose" && "$*" == *"config --quiet" ]]; then
  exit 0
fi
if [[ "$1" == "compose" && "$*" == *"ps --status running --services" ]]; then
  if [[ "${COMPOSE_UNHEALTHY:-0}" == "1" ]]; then
    exit 1
  fi
  printf '%s\n' 'app'
  exit 0
fi
exit 1
""",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    systemctl = fake_bin / "systemctl"
    systemctl.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${SYSTEMCTL_LOG}"
if [[ "$1" == "restart" && "${FAIL_RESTART:-0}" == "1" ]]; then
  exit 1
fi
exit 0
""",
        encoding="utf-8",
    )
    systemctl.chmod(0o755)
    curl = fake_bin / "curl"
    curl.write_text(
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
cp "${FIXTURE_DIR}/$(basename "${url}")" "${output}"
""",
        encoding="utf-8",
    )
    curl.chmod(0o755)
    return fake_bin


def apply_arguments(
    temporary_path: Path,
    assets: Path,
    version: str,
    host_root: Path,
    environment_file: Path,
    mode: str = "online",
    package_mode: str | None = None,
) -> argparse.Namespace:
    selected_package_mode = package_mode or mode
    return argparse.Namespace(
        version=version,
        target="edge",
        package=(
            assets / f"scrap-monitoring-edge-{version}-{selected_package_mode}.tar.gz"
        ),
        checksums=assets / "SHA256SUMS",
        mode=mode,
        deployment_root=temporary_path / "deployment",
        environment_file=environment_file,
        host_root=host_root,
        lock_file=temporary_path / "deployment.lock",
    )


class ApplyReleaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.temporary_path = Path(self.temporary.name)
        self.host_root, self.environment_file = prepare_edge_host(self.temporary_path)
        self.fake_bin = install_fake_commands(self.temporary_path)
        self.environment = os.environ.copy()
        self.environment["PATH"] = (
            f"{self.fake_bin}{os.pathsep}{self.environment['PATH']}"
        )
        self.environment["DOCKER_LOG"] = str(self.temporary_path / "docker.log")
        self.environment["SYSTEMCTL_LOG"] = str(self.temporary_path / "systemctl.log")
        self.environment["LOADED_ARCHIVE"] = str(
            self.temporary_path / "loaded-images.tar"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def apply(self, args: argparse.Namespace) -> Path:
        with patch.dict(os.environ, self.environment, clear=True):
            return apply_release(args, host_platform="linux/arm64")

    def test_applies_online_release_and_is_idempotent(self) -> None:
        assets = build_assets(self.temporary_path, "v0.0.1")
        args = apply_arguments(
            self.temporary_path,
            assets,
            "v0.0.1",
            self.host_root,
            self.environment_file,
        )

        destination = self.apply(args)
        self.apply(args)

        deployment = self.temporary_path / "deployment"
        self.assertEqual(destination, (deployment / "current").resolve())
        release_environment = (
            destination / "targets" / "edge" / "release.env"
        ).read_text(encoding="utf-8")
        self.assertIn("DEPLOYMENT_REVISION=v0.0.1\n", release_environment)
        self.assertIn("EDGE_COMPONENT_IMAGE=", release_environment)
        self.assertTrue((deployment / "state" / "edge.generated.env").is_file())
        state = json.loads(
            (deployment / "state" / "edge.json").read_text(encoding="utf-8")
        )
        self.assertEqual("success", state["result"])
        self.assertEqual("versions/v0.0.1", state["current"])
        systemctl_log = (self.temporary_path / "systemctl.log").read_text(
            encoding="utf-8"
        )
        self.assertEqual(1, systemctl_log.count("restart"))

    def test_rejects_package_mode_mismatch_without_switching(self) -> None:
        assets = build_assets(self.temporary_path, "v0.0.1")
        args = apply_arguments(
            self.temporary_path,
            assets,
            "v0.0.1",
            self.host_root,
            self.environment_file,
            mode="offline",
            package_mode="online",
        )

        with self.assertRaisesRegex(ValueError, "package mode"):
            self.apply(args)

        deployment = self.temporary_path / "deployment"
        self.assertFalse((deployment / "current").exists())
        state = json.loads(
            (deployment / "state" / "edge.json").read_text(encoding="utf-8")
        )
        self.assertEqual("failed", state["result"])

    def test_applies_offline_release_without_pulling_images(self) -> None:
        assets = build_assets(self.temporary_path, "v0.0.1")
        args = apply_arguments(
            self.temporary_path,
            assets,
            "v0.0.1",
            self.host_root,
            self.environment_file,
            mode="offline",
        )

        self.apply(args)

        docker_log = (self.temporary_path / "docker.log").read_text(encoding="utf-8")
        self.assertNotIn("pull --platform", docker_log)
        self.assertIn("image inspect", docker_log)

    def test_restores_previous_release_when_restart_fails(self) -> None:
        first_assets = build_assets(self.temporary_path, "v0.0.1")
        first_args = apply_arguments(
            self.temporary_path,
            first_assets,
            "v0.0.1",
            self.host_root,
            self.environment_file,
        )
        self.apply(first_args)
        second_assets = build_assets(self.temporary_path, "v0.0.2")
        second_args = apply_arguments(
            self.temporary_path,
            second_assets,
            "v0.0.2",
            self.host_root,
            self.environment_file,
        )
        self.environment["FAIL_RESTART"] = "1"

        with self.assertRaises(subprocess.CalledProcessError):
            self.apply(second_args)

        deployment = self.temporary_path / "deployment"
        self.assertEqual(
            "v0.0.1",
            (deployment / "current").resolve().name,
        )
        self.assertFalse((deployment / "previous").exists())
        state = json.loads(
            (deployment / "state" / "edge.json").read_text(encoding="utf-8")
        )
        self.assertEqual("failed", state["result"])
        self.assertEqual("versions/v0.0.1", state["current"])

    def test_rejects_modified_existing_version(self) -> None:
        assets = build_assets(self.temporary_path, "v0.0.1")
        args = apply_arguments(
            self.temporary_path,
            assets,
            "v0.0.1",
            self.host_root,
            self.environment_file,
        )
        destination = self.apply(args)
        (destination / "README.md").write_text("modified\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "content was modified"):
            self.apply(args)

    def test_rejects_image_platform_mismatch_without_switching(self) -> None:
        assets = build_assets(self.temporary_path, "v0.0.1")
        args = apply_arguments(
            self.temporary_path,
            assets,
            "v0.0.1",
            self.host_root,
            self.environment_file,
        )
        self.environment["INSPECT_PLATFORM"] = "linux/amd64"

        with self.assertRaisesRegex(RuntimeError, "image platform"):
            self.apply(args)

        self.assertFalse((self.temporary_path / "deployment" / "current").exists())

    def test_rejects_missing_secret_without_switching(self) -> None:
        assets = build_assets(self.temporary_path, "v0.0.1")
        args = apply_arguments(
            self.temporary_path,
            assets,
            "v0.0.1",
            self.host_root,
            self.environment_file,
        )
        (self.host_root / "opt" / "ajin" / "secrets" / "edge-token").unlink()

        with self.assertRaises(subprocess.CalledProcessError):
            self.apply(args)

        self.assertFalse((self.temporary_path / "deployment" / "current").exists())

    def test_rejects_edge_configuration_identity_mismatch(self) -> None:
        assets = build_assets(self.temporary_path, "v0.0.1")
        args = apply_arguments(
            self.temporary_path,
            assets,
            "v0.0.1",
            self.host_root,
            self.environment_file,
        )
        config = self.host_root / "opt" / "ajin" / "config" / "edge.json"
        document = json.loads(config.read_text(encoding="utf-8"))
        document["EDGE_ID"] = "different-edge"
        config.write_text(json.dumps(document), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "does not match EDGE_ID"):
            self.apply(args)

        self.assertFalse((self.temporary_path / "deployment" / "current").exists())

    def test_rejects_compose_without_services(self) -> None:
        assets = build_assets(self.temporary_path, "v0.0.1")
        args = apply_arguments(
            self.temporary_path,
            assets,
            "v0.0.1",
            self.host_root,
            self.environment_file,
        )
        self.environment["COMPOSE_NO_SERVICES"] = "1"

        with self.assertRaisesRegex(ValueError, "has no services"):
            self.apply(args)

        self.assertFalse((self.temporary_path / "deployment" / "current").exists())

    def test_restores_release_and_generated_environment_when_health_fails(
        self,
    ) -> None:
        first_assets = build_assets(self.temporary_path, "v0.0.1")
        first_args = apply_arguments(
            self.temporary_path,
            first_assets,
            "v0.0.1",
            self.host_root,
            self.environment_file,
        )
        self.apply(first_args)
        deployment = self.temporary_path / "deployment"
        generated = deployment / "state" / "edge.generated.env"
        original_generated = generated.read_bytes()
        config = self.host_root / "opt" / "ajin" / "config" / "edge.json"
        document = json.loads(config.read_text(encoding="utf-8"))
        document["calibration"] = "updated"
        config.write_text(json.dumps(document), encoding="utf-8")
        second_assets = build_assets(self.temporary_path, "v0.0.2")
        second_args = apply_arguments(
            self.temporary_path,
            second_assets,
            "v0.0.2",
            self.host_root,
            self.environment_file,
        )
        self.environment["COMPOSE_UNHEALTHY"] = "1"

        with self.assertRaisesRegex(RuntimeError, "not healthy"):
            self.apply(second_args)

        self.assertEqual("v0.0.1", (deployment / "current").resolve().name)
        self.assertEqual(original_generated, generated.read_bytes())

    def test_certificate_snapshot_restores_all_tls_files(self) -> None:
        tls = self.temporary_path / "pki" / "tls"
        tls.mkdir(parents=True)
        original_digests = {}
        for name in ("server.crt", "server.key", "server-fullchain.pem"):
            path = tls / name
            with path.open("xb") as output:
                subprocess.run(
                    ["openssl", "rand", "32"],
                    check=True,
                    stdout=output,
                )
            path.chmod(0o640)
            original_digests[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        snapshot = CertificateSnapshot(tls)
        snapshot.capture()
        for path in tls.iterdir():
            path.unlink()
        with (tls / "server.key").open("xb") as output:
            subprocess.run(
                ["openssl", "rand", "16"],
                check=True,
                stdout=output,
            )

        snapshot.restore()
        snapshot.cleanup()

        self.assertEqual(
            original_digests,
            {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in tls.iterdir()
            },
        )


if __name__ == "__main__":
    unittest.main()
