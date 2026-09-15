from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
SHELL_ENTRYPOINTS = [
    REPOSITORY / "delivery" / "apply-release",
]
IMPLEMENTED_ENTRYPOINTS = [
    REPOSITORY / "delivery" / "verify-release",
    REPOSITORY / "delivery" / "online" / "fetch-release",
    REPOSITORY / "delivery" / "offline" / "import-bundle",
    REPOSITORY / "delivery" / "generate-auth-secret",
    REPOSITORY / "delivery" / "install-auth-secret",
    REPOSITORY / "delivery" / "retire-auth-secret",
    REPOSITORY / "delivery" / "validate-auth-secrets",
    REPOSITORY / "delivery" / "validate-environment",
    REPOSITORY / "pki" / "validate-ca-state",
    REPOSITORY / "pki" / "ensure-server-certificate",
    REPOSITORY / "pki" / "verify-server-certificate",
    REPOSITORY / "release" / "pull-images",
]
PYTHON_ENTRYPOINTS = [
    REPOSITORY / "release" / "build-assets",
    REPOSITORY / "release" / "validate-manifest",
]


class EntrypointTest(unittest.TestCase):
    def test_shell_entrypoints_are_executable_and_have_help(self) -> None:
        for entrypoint in [*SHELL_ENTRYPOINTS, *IMPLEMENTED_ENTRYPOINTS]:
            with self.subTest(entrypoint=entrypoint):
                self.assertTrue(os.access(entrypoint, os.X_OK))
                result = subprocess.run(
                    [str(entrypoint), "--help"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(0, result.returncode, result.stderr)

        for entrypoint in PYTHON_ENTRYPOINTS:
            with self.subTest(entrypoint=entrypoint):
                self.assertTrue(os.access(entrypoint, os.X_OK))
                result = subprocess.run(
                    [sys.executable, str(entrypoint), "--help"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(0, result.returncode, result.stderr)

    def test_unimplemented_entrypoints_do_not_report_success(self) -> None:
        for entrypoint in SHELL_ENTRYPOINTS:
            with self.subTest(entrypoint=entrypoint):
                result = subprocess.run(
                    [str(entrypoint)],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(0, result.returncode)


if __name__ == "__main__":
    unittest.main()
