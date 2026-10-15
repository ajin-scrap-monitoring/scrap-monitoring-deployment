from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from delivery.release_applier import validate_target_inputs

REPOSITORY = Path(__file__).resolve().parents[1]


class ServerPreflightTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.environment = self.root / "server.env"
        self.environment.write_text(
            (REPOSITORY / "targets/server/hardware/.env.example").read_text()
        )
        for name in ("backend", "media"):
            (self.root / "srv/scrap-monitoring/data" / name).mkdir(parents=True)
        self.commands = []

    def checked(self, command, **kwargs):
        self.commands.append(command)
        if Path(command[0]).name == "validate-auth-secrets":
            return subprocess.CompletedProcess(command, 0)
        return subprocess.run(command, check=True, capture_output=True, text=True)

    def validate(self):
        with patch("delivery.release_applier.run_checked", side_effect=self.checked):
            return validate_target_inputs(
                REPOSITORY, "server", "hardware", self.environment, self.root
            )

    def install_dashboard(self):
        subprocess.run(
            [
                str(REPOSITORY / "delivery/install-dashboard-configuration"),
                "--root",
                str(self.root),
                "--pit-id",
                "pit-example",
                "--camera-id",
                "camera-example",
            ],
            check=True,
            capture_output=True,
        )
        return self.root / "etc/scrap-monitoring/dashboard/runtime-config.json"

    def test_missing_dashboard_configuration_fails_without_creating_or_changing_inputs(
        self,
    ):
        original = self.environment.read_bytes()
        with self.assertRaises(subprocess.CalledProcessError):
            self.validate()
        self.assertEqual(original, self.environment.read_bytes())
        self.assertFalse((self.root / "etc").exists())
        self.assertFalse(
            any(
                Path(c[0]).name in ("systemctl", "docker", "validate-auth-secrets")
                for c in self.commands
            )
        )

    def test_valid_dashboard_is_checked_without_changing_file(self):
        path = self.install_dashboard()
        before = path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns
        environment, generated = self.validate()
        self.assertEqual("hardware", environment["DEPLOYMENT_SCENARIO"])
        self.assertIsNone(generated)
        self.assertEqual(
            before, (path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns)
        )
        self.assertTrue(
            any(
                Path(c[0]).name == "validate-dashboard-configuration"
                for c in self.commands
            )
        )

    def test_invalid_json_and_file_permissions_fail_before_secret_checks(self):
        path = self.install_dashboard()
        original = path.read_bytes()
        for content, mode in (
            (b'{"token":"private-placeholder"}', 0o644),
            (original, 0o600),
        ):
            path.write_bytes(content)
            path.chmod(mode)
            self.commands.clear()
            with self.assertRaises(subprocess.CalledProcessError):
                self.validate()
            self.assertEqual(content, path.read_bytes())
            self.assertFalse(
                any(Path(c[0]).name == "validate-auth-secrets" for c in self.commands)
            )


if __name__ == "__main__":
    unittest.main()
