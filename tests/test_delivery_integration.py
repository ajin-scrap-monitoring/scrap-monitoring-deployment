from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from delivery.release_applier import apply_release
from tests.test_apply_release import (
    apply_arguments,
    build_assets,
    install_fake_commands,
    prepare_edge_host,
)

REPOSITORY = Path(__file__).resolve().parents[1]
FETCH_RELEASE = REPOSITORY / "delivery" / "online" / "fetch-release"
IMPORT_BUNDLE = REPOSITORY / "delivery" / "offline" / "import-bundle"


class DeliveryIntegrationTest(unittest.TestCase):
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

    def test_online_fetch_to_apply_handoff(self) -> None:
        assets = build_assets(self.temporary_path, "v0.0.1")
        fetched = self.temporary_path / "fetched"
        self.environment["FIXTURE_DIR"] = str(assets)
        with patch.dict(os.environ, self.environment, clear=True):
            subprocess.run(
                [
                    str(FETCH_RELEASE),
                    "--version",
                    "v0.0.1",
                    "--target",
                    "edge",
                    "--scenario",
                    "hardware",
                    "--output",
                    str(fetched),
                ],
                check=True,
                capture_output=True,
                text=True,
                env=self.environment,
            )
            destination = apply_release(
                apply_arguments(
                    self.temporary_path,
                    fetched,
                    "v0.0.1",
                    self.host_root,
                    self.environment_file,
                ),
                host_platform="linux/arm64",
            )

        self.assertEqual(
            destination,
            (self.temporary_path / "deployment" / "current").resolve(),
        )

    def test_offline_import_to_apply_handoff(self) -> None:
        assets = build_assets(self.temporary_path, "v0.0.1")
        bundle = assets / "scrap-monitoring-edge-hardware-v0.0.1-offline.tar.gz"
        with patch.dict(os.environ, self.environment, clear=True):
            subprocess.run(
                [
                    str(IMPORT_BUNDLE),
                    "--version",
                    "v0.0.1",
                    "--target",
                    "edge",
                    "--scenario",
                    "hardware",
                    "--bundle",
                    str(bundle),
                    "--checksums",
                    str(assets / "SHA256SUMS"),
                ],
                check=True,
                capture_output=True,
                text=True,
                env=self.environment,
            )
            destination = apply_release(
                apply_arguments(
                    self.temporary_path,
                    assets,
                    "v0.0.1",
                    self.host_root,
                    self.environment_file,
                    mode="offline",
                ),
                host_platform="linux/arm64",
            )

        self.assertEqual(
            (self.temporary_path / "images" / "edge-hardware-images.tar").read_bytes(),
            (self.temporary_path / "loaded-images.tar").read_bytes(),
        )
        self.assertEqual(
            destination,
            (self.temporary_path / "deployment" / "current").resolve(),
        )


if __name__ == "__main__":
    unittest.main()
