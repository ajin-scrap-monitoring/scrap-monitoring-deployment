from __future__ import annotations

import grp
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_auth_secrets import GENERATE, INSTALL, VALIDATE, run

REPOSITORY = Path(__file__).resolve().parents[1]
LIBRARY = REPOSITORY / "delivery/auth-secret-permissions.sh"


class ReaderGroupTest(unittest.TestCase):
    def test_four_consumers_have_distinct_reader_group_names(self) -> None:
        names = []
        for target in ("edge", "server"):
            for kind in ("edge-backend", "camera-media"):
                result = run(
                    "bash",
                    "-c",
                    'source "$1"; auth_reader_group "$2" "$3"',
                    "test",
                    LIBRARY,
                    target,
                    kind,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                names.append(result.stdout.strip())
        self.assertEqual(4, len(set(names)))

    def test_fixture_root_never_creates_host_groups(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = run(
                "bash",
                "-c",
                'source "$1"; getent() { return 99; }; groupadd() { return 99; }; '
                'auth_reader_gid "$2" scrap-edge-uplink true',
                "test",
                LIBRARY,
                temporary,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(str(Path(temporary).stat().st_gid), result.stdout.strip())

    def test_existing_root_group_is_rejected(self) -> None:
        result = run(
            "bash",
            "-c",
            'source "$1"; getent() { printf "%s\\n" "scrap-edge-uplink:x:0:"; }; '
            "auth_reader_gid / scrap-edge-uplink",
            "test",
            LIBRARY,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("invalid ID", result.stderr)


@unittest.skipUnless(
    Path("/.dockerenv").is_file() and os.geteuid() == 0,
    "production ownership checks require the isolated root validation container",
)
class ContainerCredentialPermissionTest(unittest.TestCase):
    def test_host_root_aliases_require_root(self) -> None:
        for root in ("/", "/.", "/tmp/.."):
            with self.subTest(root=root):
                result = subprocess.run(
                    [str(INSTALL), "--root", root, "edge", "/missing-bundle"],
                    user=10001,
                    group=10001,
                    extra_groups=(),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertNotEqual(0, result.returncode)
                self.assertIn("require root", result.stderr)

    def test_production_installation_and_non_root_read_permissions(self) -> None:
        secret_directories = (
            Path("/opt/ajin/secrets"),
            Path("/srv/scrap-monitoring/secrets/backend"),
            Path("/srv/scrap-monitoring/secrets/media"),
        )
        for directory in secret_directories:
            if directory.exists() or directory.is_symlink():
                self.skipTest("container credential paths must be empty")

        def cleanup() -> None:
            for directory in secret_directories:
                if directory.is_dir():
                    for child in directory.iterdir():
                        child.unlink()
                    directory.rmdir()

        self.addCleanup(cleanup)
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            workspace.chmod(0o755)
            environment = workspace / "edge.env"
            environment.write_text(
                "EDGE_ID=edge-01\nCAMERA_ID=camera-01\n", encoding="utf-8"
            )
            for kind, identity in (
                ("edge-backend", "edge-01"),
                ("camera-media", "camera-01"),
            ):
                bundle = workspace / kind
                generated = run(GENERATE, kind, identity, bundle)
                self.assertEqual(0, generated.returncode, generated.stderr)
                for target in ("edge", "server"):
                    installed = run(INSTALL, target, bundle)
                    self.assertEqual(0, installed.returncode, installed.stderr)
            for arguments in (("edge", environment), ("server",)):
                valid = run(VALIDATE, *arguments)
                self.assertEqual(0, valid.returncode, valid.stderr)

            consumers = (
                (Path("/opt/ajin/secrets/edge-token"), "scrap-edge-uplink", 10001),
                (Path("/opt/ajin/secrets/camera-token"), "scrap-camera-agent", 10001),
                (
                    Path(
                        "/srv/scrap-monitoring/secrets/backend/edge-token-digests.json"
                    ),
                    "scrap-backend-auth",
                    1000,
                ),
                (
                    Path(
                        "/srv/scrap-monitoring/secrets/media/camera-token-digests.json"
                    ),
                    "scrap-media-auth",
                    10002,
                ),
            )
            gids = {name: grp.getgrnam(name).gr_gid for _, name, _ in consumers}
            self.assertEqual(4, len(set(gids.values())))
            for directory in secret_directories:
                self.assertEqual(0, directory.stat().st_uid)
                self.assertEqual(0o700, directory.stat().st_mode & 0o7777)
            for index, (path, group, uid) in enumerate(consumers):
                with self.subTest(group=group):
                    self.assertEqual(0, path.stat().st_uid)
                    self.assertEqual(gids[group], path.stat().st_gid)
                    self.assertEqual(0o640, path.stat().st_mode & 0o7777)
                    view = workspace / f"consumer-file-{index}"
                    os.link(path, view)
                    try:
                        self.assertEqual(
                            0, self.access(view, uid, [gids[group]]).returncode
                        )
                        self.assertNotEqual(
                            0,
                            self.access(
                                view, uid, [gids[group]], write=True
                            ).returncode,
                        )
                        self.assertNotEqual(0, self.access(view, uid, []).returncode)
                        for other_group, gid in gids.items():
                            if other_group != group:
                                self.assertNotEqual(
                                    0, self.access(view, uid, [gid]).returncode
                                )
                    finally:
                        view.unlink()

            token = Path("/opt/ajin/secrets/edge-token")
            os.chown(token, 0, gids["scrap-camera-agent"])
            rejected = run(VALIDATE, "edge", environment)
            self.assertNotEqual(0, rejected.returncode)
            os.chown(token, 10001, gids["scrap-edge-uplink"])
            rejected = run(VALIDATE, "edge", environment)
            self.assertNotEqual(0, rejected.returncode)
            repaired = run(INSTALL, "edge", workspace / "edge-backend")
            self.assertEqual(0, repaired.returncode, repaired.stderr)
            valid = run(VALIDATE, "edge", environment)
            self.assertEqual(0, valid.returncode, valid.stderr)

            metadata = Path("/opt/ajin/secrets/edge-token.metadata.json")
            view = workspace / "metadata"
            os.link(metadata, view)
            self.assertEqual(0o600, view.stat().st_mode & 0o7777)
            self.assertNotEqual(
                0, self.access(view, 10001, [gids["scrap-edge-uplink"]]).returncode
            )

    @staticmethod
    def access(
        path: Path, uid: int, gids: list[int], *, write: bool = False
    ) -> subprocess.CompletedProcess[str]:
        def drop_privileges() -> None:
            os.setgroups(gids)
            os.setgid(uid)
            os.setuid(uid)

        code = (
            'with open(__import__("sys").argv[1], "r+b"): pass'
            if write
            else '__import__("pathlib").Path(__import__("sys").argv[1]).read_bytes()'
        )
        return subprocess.run(
            ["/usr/bin/python3", "-c", code, str(path)],
            preexec_fn=drop_privileges,
            capture_output=True,
            text=True,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
