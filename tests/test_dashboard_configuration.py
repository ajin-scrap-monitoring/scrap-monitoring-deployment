from __future__ import annotations

import grp
import importlib.util
import json
import os
import stat
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
INSTALL = REPOSITORY / "delivery/install-dashboard-configuration"
VALIDATE = REPOSITORY / "delivery/validate-dashboard-configuration"
SPEC = importlib.util.spec_from_file_location(
    "dashboard_configuration", REPOSITORY / "delivery/dashboard_configuration.py"
)
assert SPEC is not None and SPEC.loader is not None
CONFIGURATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONFIGURATION)
DOCUMENT = {"schemaVersion": 1, "pitId": "pit-example", "cameraId": "camera-example"}


class DashboardDocumentTest(unittest.TestCase):
    def test_accepts_unicode_pit_and_camera_boundary_lengths(self) -> None:
        for pit_id, camera_id in (
            ("pit-example", "A1._~-"),
            ("한" * 50, "a" * 128),
            (chr(0x10000) * 50, "1"),
            ("pit with spaces", "camera-main"),
        ):
            with self.subTest(pit_id=pit_id, camera_id=camera_id):
                document = {**DOCUMENT, "pitId": pit_id, "cameraId": camera_id}
                self.assertEqual(document, CONFIGURATION.validate_document(document))

    def test_rejects_invalid_pit_identifiers(self) -> None:
        for pit_id in (
            None,
            1,
            "",
            " ",
            "\ufeff",
            "a" * 51,
            "pit\n",
            "pit\x7f",
            "\ud800",
        ):
            with self.subTest(pit_id=repr(pit_id)), self.assertRaises(ValueError):
                CONFIGURATION.validate_document({**DOCUMENT, "pitId": pit_id})

    def test_rejects_camera_path_and_query_injection(self) -> None:
        for camera_id in (
            None,
            1,
            "",
            "a" * 129,
            "_camera",
            "camera/name",
            "camera%2fother",
            "camera?query=true",
            "camera#fragment",
            "camera\n",
            "한글",
        ):
            with self.subTest(camera_id=camera_id), self.assertRaises(ValueError):
                CONFIGURATION.validate_document({**DOCUMENT, "cameraId": camera_id})

    def test_rejects_missing_extra_fields_and_unsupported_schema(self) -> None:
        for document in (
            None,
            [],
            {},
            {key: value for key, value in DOCUMENT.items() if key != "cameraId"},
            {**DOCUMENT, "token": "must-not-be-public"},
            *({**DOCUMENT, "schemaVersion": value} for value in (True, "1", 0, 2, 1.1)),
        ):
            with self.subTest(document=document), self.assertRaises(ValueError):
                CONFIGURATION.validate_document(document)
        self.assertEqual(
            {**DOCUMENT, "schemaVersion": 1.0},
            CONFIGURATION.validate_document({**DOCUMENT, "schemaVersion": 1.0}),
        )


class DashboardConfigurationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / CONFIGURATION.CONFIGURATION_PATH

    def install(
        self, pit_id: str = "pit-example", camera_id: str = "camera-example"
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(INSTALL),
                "--pit-id",
                pit_id,
                "--camera-id",
                camera_id,
                "--root",
                str(self.root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def validate(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(VALIDATE), "--root", str(self.root), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_installs_configuration_and_non_secret_permissions(self) -> None:
        result = self.install()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(DOCUMENT, json.loads(self.path.read_text(encoding="utf-8")))
        self.assertEqual(0o644, stat.S_IMODE(self.path.stat().st_mode))
        self.assertEqual(self.root.stat().st_uid, self.path.stat().st_uid)
        self.assertEqual(self.root.stat().st_gid, self.path.stat().st_gid)
        for directory in (self.path.parent, self.path.parent.parent):
            self.assertEqual(0o750, stat.S_IMODE(directory.stat().st_mode))
        lock = self.path.parent / ".configuration.lock"
        self.assertEqual(0o600, stat.S_IMODE(lock.stat().st_mode))
        self.assertEqual(0, self.validate().returncode)
        self.assertNotIn("pit-example", result.stdout + result.stderr)
        self.assertNotIn("camera-example", result.stdout + result.stderr)
        self.assertFalse(list(self.path.parent.glob(".runtime-config.*")))

    def test_reinstall_preserves_bytes_inode_and_operator_formatting(self) -> None:
        self.assertEqual(0, self.install().returncode)
        self.path.write_text(
            '{"cameraId":"camera-example", "pitId":"pit-example", "schemaVersion":1}\n',
            encoding="utf-8",
        )
        original = self.path.read_bytes(), self.path.stat().st_ino
        result = self.install()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(original, (self.path.read_bytes(), self.path.stat().st_ino))
        self.assertIn("preserved", result.stdout)

    def test_reinstall_rejects_changed_identifiers_and_preserves_file(self) -> None:
        self.assertEqual(0, self.install().returncode)
        original = self.path.read_bytes(), self.path.stat().st_ino
        for pit_id, camera_id in (
            ("other-pit", "camera-example"),
            ("pit-example", "other-camera"),
        ):
            with self.subTest(pit_id=pit_id, camera_id=camera_id):
                result = self.install(pit_id, camera_id)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(
                    original, (self.path.read_bytes(), self.path.stat().st_ino)
                )

    def test_validation_compares_expected_identifiers_without_writing(self) -> None:
        self.assertEqual(0, self.install().returncode)
        metadata = self.path.stat()
        success = self.validate(
            "--expected-pit-id", "pit-example", "--expected-camera-id", "camera-example"
        )
        self.assertEqual(0, success.returncode, success.stderr)
        for arguments in (
            ("--expected-pit-id", "other-pit"),
            ("--expected-camera-id", "other-camera"),
        ):
            self.assertNotEqual(0, self.validate(*arguments).returncode)
        self.assertEqual(metadata.st_ino, self.path.stat().st_ino)
        self.assertEqual(metadata.st_mtime_ns, self.path.stat().st_mtime_ns)

    def test_validation_missing_file_does_not_create_paths(self) -> None:
        self.assertNotEqual(0, self.validate().returncode)
        self.assertFalse((self.root / "etc").exists())

    def test_invalid_input_does_not_create_paths(self) -> None:
        for pit_id, camera_id in (
            ("", "camera-example"),
            ("pit-example", "camera/name"),
        ):
            with self.subTest(pit_id=pit_id, camera_id=camera_id):
                result = self.install(pit_id, camera_id)
                self.assertNotEqual(0, result.returncode)
                self.assertFalse((self.root / "etc").exists())

    def test_rejects_invalid_json_and_preserves_content_without_echo(self) -> None:
        self.assertEqual(0, self.install().returncode)
        for payload in (
            b'{"private": "must-not-appear"',
            b'{"schemaVersion":1,"schemaVersion":1,"pitId":"pit-example","cameraId":"camera-example"}',
            json.dumps({**DOCUMENT, "token": "must-not-appear"}).encode(),
            json.dumps({**DOCUMENT, "schemaVersion": True}).encode(),
            b'{"schemaVersion":NaN,"pitId":"pit-example","cameraId":"camera-example"}',
            b"\xff",
            b" " * (CONFIGURATION.MAX_CONFIGURATION_BYTES + 1),
        ):
            with self.subTest(payload=payload[:40]):
                self.path.write_bytes(payload)
                for result in (self.install(), self.validate()):
                    self.assertNotEqual(0, result.returncode)
                    self.assertNotIn("must-not-appear", result.stdout + result.stderr)
                self.assertEqual(payload, self.path.read_bytes())

    def test_rejects_wrong_modes_without_repairing_existing_paths(self) -> None:
        self.assertEqual(0, self.install().returncode)
        original = self.path.read_bytes()
        for path, mode in (
            (self.path, 0o666),
            (self.path.parent, 0o755),
            (self.path.parent.parent, 0o777),
        ):
            with self.subTest(path=path):
                correct_mode = stat.S_IMODE(path.stat().st_mode)
                path.chmod(mode)
                self.assertNotEqual(0, self.install().returncode)
                self.assertNotEqual(0, self.validate().returncode)
                self.assertEqual(mode, stat.S_IMODE(path.stat().st_mode))
                self.assertEqual(original, self.path.read_bytes())
                path.chmod(correct_mode)

    def test_rejects_symbolic_files_directories_and_root_ancestors(self) -> None:
        self.assertEqual(0, self.install().returncode)
        original = self.path.read_bytes()
        outside = self.root / "outside.json"
        self.path.rename(outside)
        self.path.symlink_to(outside)
        self.assertNotEqual(0, self.install().returncode)
        self.assertNotEqual(0, self.validate().returncode)
        self.assertEqual(original, outside.read_bytes())
        self.path.unlink()
        outside.rename(self.path)
        directory = self.path.parent
        outside_directory = self.root / "outside-directory"
        directory.rename(outside_directory)
        directory.symlink_to(outside_directory, target_is_directory=True)
        self.assertNotEqual(0, self.install().returncode)
        self.assertNotEqual(0, self.validate().returncode)
        directory.unlink()
        outside_directory.rename(directory)
        root_alias = self.root / "alias"
        root_alias.symlink_to(self.root, target_is_directory=True)
        self.root = root_alias / "alias"
        self.assertNotEqual(0, self.install().returncode)

    def test_rejects_configuration_hard_links(self) -> None:
        self.assertEqual(0, self.install().returncode)
        os.link(self.path, self.root / "hard-link")
        self.assertNotEqual(0, self.install().returncode)
        self.assertNotEqual(0, self.validate().returncode)

    def test_rejects_symbolic_hard_link_and_non_regular_locks(self) -> None:
        self.assertEqual(0, self.install().returncode)
        lock = self.path.parent / ".configuration.lock"
        lock.unlink()
        outside = self.root / "outside-lock"
        outside.write_text("preserve-this-lock\n", encoding="utf-8")
        lock.symlink_to(outside)
        self.assertNotEqual(0, self.install().returncode)
        self.assertEqual("preserve-this-lock\n", outside.read_text(encoding="utf-8"))
        lock.unlink()
        outside.chmod(0o600)
        os.link(outside, lock)
        self.assertNotEqual(0, self.install().returncode)
        lock.unlink()
        os.mkfifo(lock, 0o600)
        result = self.install()
        self.assertNotEqual(0, result.returncode)

    def test_concurrent_initial_installations_preserve_one_complete_file(self) -> None:
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: self.install(), range(2)))
        self.assertTrue(all(result.returncode == 0 for result in results))
        self.assertEqual(DOCUMENT, json.loads(self.path.read_text(encoding="utf-8")))
        self.assertEqual(1, self.path.stat().st_nlink)
        self.assertFalse(list(self.path.parent.glob(".runtime-config.*")))


@unittest.skipUnless(
    Path("/.dockerenv").is_file() and os.geteuid() == 0,
    "host ownership checks require the isolated root validation container",
)
class DashboardHostPermissionTest(unittest.TestCase):
    def test_fixture_owned_by_a_different_user_keeps_fixture_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            os.chown(root, 101, 101)
            CONFIGURATION.install_configuration(root, "pit-example", "camera-example")
            path = root / CONFIGURATION.CONFIGURATION_PATH
            for installed in (path, path.parent / ".configuration.lock"):
                self.assertEqual(
                    (101, 101),
                    (installed.stat().st_uid, installed.stat().st_gid),
                )
            CONFIGURATION.validate_configuration(root, "pit-example", "camera-example")

    def test_production_ownership_and_invalid_owner_detection(self) -> None:
        path = Path("/") / CONFIGURATION.CONFIGURATION_PATH
        if path.parent.parent.exists():
            self.skipTest("container configuration paths must be empty")
        try:
            group = grp.getgrnam("scrap-admin")
        except KeyError:
            subprocess.run(["groupadd", "--system", "scrap-admin"], check=True)
            group = grp.getgrnam("scrap-admin")

        def cleanup() -> None:
            for name in (path, path.parent / ".configuration.lock"):
                name.unlink(missing_ok=True)
            path.parent.rmdir()
            path.parent.parent.rmdir()

        self.addCleanup(cleanup)
        result = subprocess.run(
            [str(INSTALL), "--pit-id", "pit-example", "--camera-id", "camera-example"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual((0, group.gr_gid), (path.stat().st_uid, path.stat().st_gid))
        self.assertEqual(0o644, stat.S_IMODE(path.stat().st_mode))
        lock = path.parent / ".configuration.lock"
        self.assertEqual((0, 0), (lock.stat().st_uid, lock.stat().st_gid))
        for owner, reader_group in ((101, group.gr_gid), (0, 0)):
            with self.subTest(owner=owner, group=reader_group):
                os.chown(path, owner, reader_group)
                self.assertRaises(
                    ValueError,
                    CONFIGURATION.validate_configuration,
                    Path("/"),
                    None,
                    None,
                )
        os.chown(path, 0, group.gr_gid)
        CONFIGURATION.validate_configuration(Path("/"), "pit-example", "camera-example")

    def test_root_aliases_require_privileges(self) -> None:
        for root in ("/", "/.", "/tmp/.."):
            with self.subTest(root=root):
                result = subprocess.run(
                    [
                        str(INSTALL),
                        "--root",
                        root,
                        "--pit-id",
                        "pit-example",
                        "--camera-id",
                        "camera-example",
                    ],
                    user=101,
                    group=101,
                    extra_groups=(),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertNotEqual(0, result.returncode)
                self.assertIn("require root", result.stderr)


if __name__ == "__main__":
    unittest.main()
