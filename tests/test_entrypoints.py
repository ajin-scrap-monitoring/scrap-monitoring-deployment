from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
SHELL_ENTRYPOINTS = [
    REPOSITORY / "delivery" / "apply-release",
    REPOSITORY / "delivery" / "verify-release",
    REPOSITORY / "delivery" / "online" / "fetch-release",
    REPOSITORY / "delivery" / "offline" / "build-bundle",
    REPOSITORY / "delivery" / "offline" / "import-bundle",
    REPOSITORY / "pki" / "validate-ca-state",
    REPOSITORY / "pki" / "ensure-server-certificate",
    REPOSITORY / "pki" / "verify-server-certificate",
]


class EntrypointTest(unittest.TestCase):
    def test_shell_entrypoints_are_executable_and_have_help(self) -> None:
        for entrypoint in SHELL_ENTRYPOINTS:
            with self.subTest(entrypoint=entrypoint):
                self.assertTrue(os.access(entrypoint, os.X_OK))
                result = subprocess.run(
                    [str(entrypoint), "--help"],
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
