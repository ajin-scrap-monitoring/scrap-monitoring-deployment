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


def run(
    *arguments: str | Path, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(argument) for argument in arguments],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
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
            for path in (
                target_root / "opt/ajin/secrets/edge-token",
                target_root / "opt/ajin/secrets/camera-token",
                edge_registry_path,
                target_root
                / "srv/scrap-monitoring/secrets/media/camera-token-digests.json",
            ):
                with self.subTest(path=path):
                    self.assertEqual(0o640, path.stat().st_mode & 0o7777)
                    self.assertEqual(target_root.stat().st_gid, path.stat().st_gid)
                    self.assertEqual(0o700, path.parent.stat().st_mode & 0o7777)
                    self.assertEqual(
                        0o600,
                        (path.parent / ".auth-secret.lock").stat().st_mode & 0o7777,
                    )
            self.assertEqual(
                0o600,
                (target_root / "opt/ajin/secrets/edge-token.metadata.json")
                .stat()
                .st_mode
                & 0o7777,
            )

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
            self.assertEqual(0o640, registry_path.stat().st_mode & 0o7777)

            only_active = run(RETIRE, "--root", target_root, new_bundle)
            self.assertNotEqual(0, only_active.returncode)

    def test_explicit_rotation_retry_repairs_metadata_without_replacing_token(
        self,
    ) -> None:
        for kind, identity, name in (
            ("edge-backend", "edge-01", "edge-token"),
            ("camera-media", "camera-01", "camera-token"),
        ):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                workspace = Path(temporary)
                target_root = workspace / "target"
                target_root.mkdir()
                old_bundle = self.generate(workspace, "old", kind, identity)
                new_bundle = self.generate(workspace, "new", kind, identity)
                initial = run(INSTALL, "--root", target_root, "edge", old_bundle)
                self.assertEqual(0, initial.returncode, initial.stderr)
                token = target_root / "opt/ajin/secrets" / name
                metadata = token.with_name(f"{name}.metadata.json")
                original_metadata = metadata.read_bytes()
                commands = workspace / "commands"
                commands.mkdir()
                fake_mv = commands / "mv"
                fake_mv.write_text(
                    "#!/usr/bin/env bash\n"
                    'if [[ "${2:-}" == *.metadata.json ]]; then exit 42; fi\n'
                    'exec /bin/mv "$@"\n',
                    encoding="utf-8",
                )
                fake_mv.chmod(0o755)
                environment = os.environ.copy()
                environment["PATH"] = f"{commands}{os.pathsep}{environment['PATH']}"
                failed = run(
                    INSTALL,
                    "--root",
                    target_root,
                    "--rotate",
                    "edge",
                    new_bundle,
                    environment=environment,
                )
                self.assertEqual(42, failed.returncode, failed.stderr)
                self.assertEqual(
                    (new_bundle / "token").read_bytes(), token.read_bytes()
                )
                self.assertEqual(original_metadata, metadata.read_bytes())
                inode = token.stat().st_ino
                implicit = run(INSTALL, "--root", target_root, "edge", new_bundle)
                self.assertNotEqual(0, implicit.returncode)
                self.assertEqual(original_metadata, metadata.read_bytes())
                repaired = run(
                    INSTALL, "--root", target_root, "--rotate", "edge", new_bundle
                )
                self.assertEqual(0, repaired.returncode, repaired.stderr)
                self.assertEqual(inode, token.stat().st_ino)
                self.assertEqual(
                    (new_bundle / "metadata.json").read_bytes(), metadata.read_bytes()
                )
                self.assertEqual(0o640, token.stat().st_mode & 0o7777)
                self.assertEqual(0o600, metadata.stat().st_mode & 0o7777)
                for result in (failed, implicit, repaired):
                    self.assertNotIn(token.read_text(), result.stdout + result.stderr)

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

    def test_reinstall_preserves_bytes_and_inodes_and_repairs_private_mode(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            target_root = workspace / "target"
            target_root.mkdir()
            bundle = self.generate(workspace, "bundle", "edge-backend", "edge-01")
            for target, relative in (
                ("edge", "opt/ajin/secrets/edge-token"),
                (
                    "server",
                    "srv/scrap-monitoring/secrets/backend/edge-token-digests.json",
                ),
            ):
                with self.subTest(target=target):
                    initial = run(INSTALL, "--root", target_root, target, bundle)
                    self.assertEqual(0, initial.returncode, initial.stderr)
                    path = target_root / relative
                    original = path.read_bytes()
                    inode = path.stat().st_ino
                    path.chmod(0o600)
                    repeated = run(INSTALL, "--root", target_root, target, bundle)
                    self.assertEqual(0, repeated.returncode, repeated.stderr)
                    self.assertEqual(original, path.read_bytes())
                    self.assertEqual(inode, path.stat().st_ino)
                    self.assertEqual(0o640, path.stat().st_mode & 0o7777)

    def test_validation_rejects_incorrect_application_and_private_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            target_root = workspace / "target"
            target_root.mkdir()
            for kind, identity in (
                ("edge-backend", "edge-01"),
                ("camera-media", "camera-01"),
            ):
                bundle = self.generate(workspace, kind, kind, identity)
                installed = run(INSTALL, "--root", target_root, "edge", bundle)
                self.assertEqual(0, installed.returncode, installed.stderr)
            environment = workspace / "edge.env"
            environment.write_text(
                "EDGE_ID=edge-01\nCAMERA_ID=camera-01\n", encoding="utf-8"
            )
            for name, invalid_mode, correct_mode in (
                ("edge-token", 0o600, 0o640),
                ("edge-token", 0o644, 0o640),
                ("edge-token", 0o660, 0o640),
                ("edge-token", 0o4640, 0o640),
                ("edge-token.metadata.json", 0o640, 0o600),
                ("", 0o750, 0o700),
            ):
                with self.subTest(name=name, mode=invalid_mode):
                    path = target_root / "opt/ajin/secrets" / name
                    path.chmod(invalid_mode)
                    result = run(VALIDATE, "--root", target_root, "edge", environment)
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn("ownership or mode", result.stderr)
                    path.chmod(correct_mode)

    def test_installer_rejects_symlink_directories_files_and_locks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            bundle = self.generate(workspace, "bundle", "edge-backend", "edge-01")
            outside = workspace / "outside"
            outside.mkdir()
            protected = outside / "protected"
            protected.write_bytes(b"unchanged")
            protected.chmod(0o644)
            for index, (target, relative, is_directory) in enumerate(
                (
                    ("edge", "opt/ajin/secrets", True),
                    ("edge", "opt/ajin/secrets/edge-token", False),
                    ("edge", "opt/ajin/secrets/edge-token.metadata.json", False),
                    ("edge", "opt/ajin/secrets/.auth-secret.lock", False),
                    ("server", "srv/scrap-monitoring/secrets/backend", True),
                    (
                        "server",
                        "srv/scrap-monitoring/secrets/backend/edge-token-digests.json",
                        False,
                    ),
                    (
                        "server",
                        "srv/scrap-monitoring/secrets/backend/.auth-secret.lock",
                        False,
                    ),
                )
            ):
                with self.subTest(target=target, relative=relative):
                    target_root = workspace / f"target-{index}"
                    path = target_root / relative
                    path.parent.mkdir(parents=True)
                    path.symlink_to(outside if is_directory else protected)
                    result = run(INSTALL, "--root", target_root, target, bundle)
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn("symbolic link", result.stderr)
                    self.assertEqual(b"unchanged", protected.read_bytes())
                    self.assertEqual(0o644, protected.stat().st_mode & 0o7777)

    def test_hardlinked_application_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            target_root = workspace / "target"
            bundle = self.generate(workspace, "bundle", "edge-backend", "edge-01")
            path = target_root / "opt/ajin/secrets/edge-token"
            path.parent.mkdir(parents=True)
            outside = workspace / "outside"
            outside.write_bytes(b"unchanged")
            os.link(outside, path)
            result = run(INSTALL, "--root", target_root, "edge", bundle)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual(b"unchanged", outside.read_bytes())

    def test_hardlinked_bundle_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            target_root = workspace / "target"
            target_root.mkdir()
            bundle = self.generate(workspace, "bundle", "edge-backend", "edge-01")
            os.link(bundle / "token", workspace / "other-token")
            result = run(INSTALL, "--root", target_root, "edge", bundle)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("single-link regular file", result.stderr)


if __name__ == "__main__":
    unittest.main()
