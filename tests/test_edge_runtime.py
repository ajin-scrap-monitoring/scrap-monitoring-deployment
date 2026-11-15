from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from delivery import edge_runtime

REPOSITORY = Path(__file__).resolve().parents[1]
INSTALL = REPOSITORY / "delivery" / "install-edge-runtime"


class EdgeRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.env_file = self.root / "etc" / "scrap-monitoring" / "edge.env"
        self.env_file.parent.mkdir(parents=True)
        self.env_file.write_text(
            (REPOSITORY / "targets" / "edge" / ".env.example").read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )

    def run_install(self, *extra_args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(INSTALL), "--root", str(self.root), *extra_args],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_prepares_edge_runtime_directories_idempotently(self) -> None:
        result = self.run_install()
        self.assertEqual(0, result.returncode, result.stderr)

        runtime_dir = self.root / "opt" / "ajin" / "runtime" / "v2"
        control_dir = runtime_dir / "control"
        for relative in edge_runtime.RUNTIME_SUBDIRECTORIES:
            target = runtime_dir / relative
            self.assertTrue(target.is_dir(), str(target))
            self.assertEqual(0o750, stat.S_IMODE(target.stat().st_mode))
        self.assertEqual(0o750, stat.S_IMODE(runtime_dir.stat().st_mode))
        self.assertTrue(control_dir.is_dir())
        self.assertEqual(0o750, stat.S_IMODE(control_dir.stat().st_mode))

        existing = runtime_dir / "outbox" / "outbox.db"
        existing.write_text("keep-state\n", encoding="utf-8")
        rerun = self.run_install()
        self.assertEqual(0, rerun.returncode, rerun.stderr)
        self.assertEqual("keep-state\n", existing.read_text(encoding="utf-8"))

    def test_rejects_symlink_and_non_directory_paths(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        link = self.root / "opt"
        link.symlink_to(outside)

        symlink_result = self.run_install()
        self.assertNotEqual(0, symlink_result.returncode)
        self.assertIn("symbolic link", symlink_result.stderr)

        link.unlink()
        runtime_sockets = self.root / "opt" / "ajin" / "runtime" / "v2" / "sockets"
        runtime_sockets.parent.mkdir(parents=True)
        (runtime_sockets.parent / "sockets").write_text("file\n", encoding="utf-8")

        file_result = self.run_install()
        self.assertNotEqual(0, file_result.returncode)
        self.assertIn("not a directory", file_result.stderr)

    def test_rejects_colliding_control_directory_and_bad_paths(self) -> None:
        text = self.env_file.read_text(encoding="utf-8")
        self.env_file.write_text(
            text.replace(
                "CONTROL_DIR=/opt/ajin/runtime/v2/control",
                "CONTROL_DIR=/opt/ajin/runtime/v2/sockets/a",
            ),
            encoding="utf-8",
        )
        result = self.run_install()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("collide", result.stderr)
        self.assertFalse((self.root / "opt").exists())

    def test_requires_root_when_targeting_host_slash(self) -> None:
        with (
            patch.object(edge_runtime.os, "geteuid", return_value=1000),
            self.assertRaisesRegex(PermissionError, "root privileges"),
        ):
            edge_runtime.install_edge_runtime(self.env_file, Path("/"))

    def test_sets_uid_gid_10001_when_targeting_host_slash(self) -> None:
        chowned: list[tuple[Path, int, int]] = []
        chowned_paths: set[Path] = set()
        real_lstat = os.lstat

        def fake_chown(path: Path, uid: int, gid: int) -> None:
            resolved = Path(path)
            chowned.append((resolved, uid, gid))
            chowned_paths.add(resolved)

        def fake_lstat(path: Path) -> os.stat_result:
            real = real_lstat(path)
            if Path(path) in chowned_paths:
                return os.stat_result(
                    (
                        real.st_mode,
                        real.st_ino,
                        real.st_dev,
                        real.st_nlink,
                        edge_runtime.EDGE_RUNTIME_UID,
                        edge_runtime.EDGE_RUNTIME_GID,
                        real.st_size,
                        int(real.st_atime),
                        int(real.st_mtime),
                        int(real.st_ctime),
                    )
                )
            return real

        env = {
            "RUNTIME_DIR": "/opt/ajin/runtime/v2",
            "CONTROL_DIR": "/opt/ajin/runtime/v2/control",
        }
        with (
            patch.object(edge_runtime.os, "geteuid", return_value=0),
            patch.object(edge_runtime, "resolve_host_root", return_value=Path("/")),
            patch.object(
                edge_runtime, "resolve_existing_file", return_value=self.env_file
            ),
            patch.object(
                edge_runtime.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 0, "", ""),
            ),
            patch.object(edge_runtime, "parse_environment_file", return_value=env),
            patch.object(
                edge_runtime,
                "resolve_target_path",
                side_effect=lambda _root, posix, _label: (
                    self.root.joinpath(*posix.parts[1:]),
                    [
                        self.root.joinpath(*posix.parts[1 : index + 1])
                        for index in range(1, len(posix.parts))
                    ],
                ),
            ),
            patch.object(edge_runtime.os, "chown", side_effect=fake_chown),
            patch.object(edge_runtime.os, "lstat", side_effect=fake_lstat),
        ):
            edge_runtime.install_edge_runtime(None, Path("/"))

        expected_count = 1 + len(edge_runtime.RUNTIME_SUBDIRECTORIES) + 1
        self.assertEqual(expected_count, len(chowned))
        self.assertTrue(
            all(
                uid == edge_runtime.EDGE_RUNTIME_UID
                and gid == edge_runtime.EDGE_RUNTIME_GID
                for _, uid, gid in chowned
            )
        )


if __name__ == "__main__":
    unittest.main()
