from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
GENERATE = REPOSITORY / "delivery" / "generate-auth-secret"
INSTALL = REPOSITORY / "delivery" / "install-auth-secret"
RETIRE = REPOSITORY / "delivery" / "retire-auth-secret"
VALIDATE = REPOSITORY / "delivery" / "validate-auth-secrets"


def run(*arguments: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(argument) for argument in arguments],
        check=False,
        capture_output=True,
        text=True,
    )


class AuthenticationSecretTest(unittest.TestCase):
    def generate(self, root: Path, name: str, kind: str, identity: str) -> Path:
        bundle = root / name
        result = run(GENERATE, kind, identity, bundle)
        self.assertEqual(0, result.returncode, result.stderr)
        return bundle

    def test_bootstrap_installs_raw_client_tokens_and_server_digests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            target_root = workspace / "target"
            target_root.mkdir()
            edge_bundle = self.generate(
                workspace, "edge-bundle", "edge-backend", "edge-01"
            )
            camera_bundle = self.generate(
                workspace, "camera-bundle", "camera-media", "camera-01"
            )

            edge_token = (edge_bundle / "token").read_bytes()
            camera_token = (camera_bundle / "token").read_bytes()
            self.assertEqual(64, len(edge_token))
            self.assertEqual(64, len(camera_token))
            self.assertNotEqual(edge_token, camera_token)
            self.assertEqual(0o600, os.stat(edge_bundle / "token").st_mode & 0o777)

            for bundle in (edge_bundle, camera_bundle):
                for target in ("server", "edge"):
                    result = run(INSTALL, "--root", target_root, target, bundle)
                    self.assertEqual(0, result.returncode, result.stderr)

            environment = workspace / "edge.env"
            environment.write_text(
                "EDGE_ID=edge-01\nCAMERA_ID=camera-01\n", encoding="utf-8"
            )
            edge_validation = run(VALIDATE, "--root", target_root, "edge", environment)
            server_validation = run(VALIDATE, "--root", target_root, "server")
            self.assertEqual(0, edge_validation.returncode, edge_validation.stderr)
            self.assertEqual(0, server_validation.returncode, server_validation.stderr)

            edge_registry_path = (
                target_root
                / "srv/scrap-monitoring/secrets/backend/edge-token-digests.json"
            )
            edge_registry_text = edge_registry_path.read_text(encoding="utf-8")
            edge_registry = json.loads(edge_registry_text)
            expected_digest = hashlib.sha256(edge_token).hexdigest()
            self.assertEqual([expected_digest], edge_registry["identities"]["edge-01"])
            self.assertNotIn(edge_token.decode(), edge_registry_text)

    def test_rotation_overlaps_server_digests_then_retires_old_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            target_root = workspace / "target"
            target_root.mkdir()
            old_bundle = self.generate(
                workspace, "old-bundle", "edge-backend", "edge-01"
            )
            new_bundle = self.generate(
                workspace, "new-bundle", "edge-backend", "edge-01"
            )
            third_bundle = self.generate(
                workspace, "third-bundle", "edge-backend", "edge-01"
            )

            initial = run(INSTALL, "--root", target_root, "server", old_bundle)
            edge_initial = run(INSTALL, "--root", target_root, "edge", old_bundle)
            duplicate = run(INSTALL, "--root", target_root, "server", old_bundle)
            refused = run(INSTALL, "--root", target_root, "server", new_bundle)
            rotated = run(
                INSTALL,
                "--root",
                target_root,
                "--rotate",
                "server",
                new_bundle,
            )
            self.assertEqual(0, initial.returncode, initial.stderr)
            self.assertEqual(0, edge_initial.returncode, edge_initial.stderr)
            self.assertEqual(0, duplicate.returncode, duplicate.stderr)
            self.assertNotEqual(0, refused.returncode)
            self.assertEqual(0, rotated.returncode, rotated.stderr)

            third_refused = run(
                INSTALL,
                "--root",
                target_root,
                "--rotate",
                "server",
                third_bundle,
            )
            self.assertNotEqual(0, third_refused.returncode)

            registry_path = (
                target_root
                / "srv/scrap-monitoring/secrets/backend/edge-token-digests.json"
            )
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertEqual(2, len(registry["identities"]["edge-01"]))

            edge_rotated = run(
                INSTALL,
                "--root",
                target_root,
                "--rotate",
                "edge",
                new_bundle,
            )
            self.assertEqual(0, edge_rotated.returncode, edge_rotated.stderr)
            self.assertEqual(
                (new_bundle / "token").read_bytes(),
                (target_root / "opt/ajin/secrets/edge-token").read_bytes(),
            )

            retired = run(RETIRE, "--root", target_root, old_bundle)
            repeated = run(RETIRE, "--root", target_root, old_bundle)
            self.assertEqual(0, retired.returncode, retired.stderr)
            self.assertEqual(0, repeated.returncode, repeated.stderr)

            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            new_digest = hashlib.sha256((new_bundle / "token").read_bytes()).hexdigest()
            self.assertEqual([new_digest], registry["identities"]["edge-01"])

            only_active = run(RETIRE, "--root", target_root, new_bundle)
            self.assertNotEqual(0, only_active.returncode)

    def test_tampered_bundle_is_rejected_without_printing_token(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            target_root = workspace / "target"
            target_root.mkdir()
            bundle = self.generate(workspace, "edge-bundle", "edge-backend", "edge-01")
            token = "f" * 64
            (bundle / "token").write_text(token, encoding="utf-8")

            result = run(INSTALL, "--root", target_root, "server", bundle)

            self.assertNotEqual(0, result.returncode)
            self.assertNotIn(token, result.stdout)
            self.assertNotIn(token, result.stderr)

    def test_group_readable_bundle_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            target_root = workspace / "target"
            target_root.mkdir()
            bundle = self.generate(workspace, "edge-bundle", "edge-backend", "edge-01")
            (bundle / "token").chmod(0o640)

            result = run(INSTALL, "--root", target_root, "server", bundle)

            self.assertNotEqual(0, result.returncode)
            self.assertIn("group or other access", result.stderr)


if __name__ == "__main__":
    unittest.main()
