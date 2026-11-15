from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "tools/build-component-image"
SPEC = importlib.util.spec_from_loader(
    "build_component_image", SourceFileLoader("build_component_image", str(PATH))
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

REVISION = "a" * 40
IMAGE_ID = "sha256:" + "b" * 64


def inspect_output(
    revision: str = REVISION,
    platform: tuple[str, str] = ("linux", "arm64"),
    development: bool = True,
) -> str:
    labels = {"org.opencontainers.image.revision": revision}
    if development:
        labels[MODULE.BUILD_LABEL] = "development"
    return json.dumps(
        [
            {
                "Id": IMAGE_ID,
                "Os": platform[0],
                "Architecture": platform[1],
                "Config": {"Labels": labels},
            }
        ]
    )


class BuildComponentImageTest(unittest.TestCase):
    def test_validates_inputs(self) -> None:
        good = ("repo", "image", REVISION, "linux/arm64", "Dockerfile", ".")
        MODULE.validate_arguments(*good)
        bad = (
            ("Repo", "image", REVISION, "linux/arm64", "Dockerfile", "."),
            ("repo", "image", "main", "linux/arm64", "Dockerfile", "."),
            ("repo", "image", REVISION[:7], "linux/arm64", "Dockerfile", "."),
            ("repo", "image", REVISION, "linux/386", "Dockerfile", "."),
            ("repo", "image", REVISION, "linux/arm64", "../Dockerfile", "."),
            ("repo", "image", REVISION, "linux/arm64", "/etc/passwd", "."),
            ("repo", "image", REVISION, "linux/arm64", "Dockerfile", "a/../.."),
            ("repo", "bad image", REVISION, "linux/arm64", "Dockerfile", "."),
        )
        for arguments in bad:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                MODULE.validate_arguments(*arguments)

    def test_tag_and_build_command(self) -> None:
        self.assertEqual(
            "scrap-dev/ajin-lidar-driver:main-aaaaaaa",
            MODULE.image_tag("ajin-lidar-driver", REVISION),
        )
        command = MODULE.build_command(
            "repo",
            "image",
            REVISION,
            "linux/arm64",
            "docker/Dockerfile",
            "docker",
            Path("/source"),
        )
        self.assertEqual(["docker", "buildx", "build"], command[:3])
        self.assertIn("--load", command)
        self.assertIn(f"{MODULE.BUILD_LABEL}=development", command)
        self.assertIn(f"org.opencontainers.image.revision={REVISION}", command)
        self.assertIn(
            "org.opencontainers.image.source=https://github.com/"
            "ajin-scrap-monitoring/repo",
            command,
        )
        self.assertEqual("/source/docker", command[-1])
        self.assertEqual(
            "/source/docker/Dockerfile", command[command.index("--file") + 1]
        )

    def test_fetch_rejects_head_mismatch(self) -> None:
        calls: list[list[str]] = []

        def runner(command):
            calls.append(list(command))
            return "c" * 40 + "\n" if "rev-parse" in command else ""

        with (
            tempfile.TemporaryDirectory() as temporary,
            self.assertRaises(ValueError),
        ):
            MODULE.fetch_source("repo", REVISION, Path(temporary), runner)
        self.assertTrue(any("fetch" in command for command in calls))
        fetch = next(command for command in calls if "fetch" in command)
        self.assertEqual(REVISION, fetch[-1])

    def test_fetch_accepts_matching_head(self) -> None:
        def runner(command):
            return REVISION + "\n" if "rev-parse" in command else ""

        with tempfile.TemporaryDirectory() as temporary:
            MODULE.fetch_source("repo", REVISION, Path(temporary), runner)

    def test_verify_image_checks_labels_and_platform(self) -> None:
        def runner(output):
            return lambda command: output

        tag = MODULE.image_tag("image", REVISION)
        self.assertEqual(
            IMAGE_ID,
            MODULE.verify_image(tag, REVISION, "linux/arm64", runner(inspect_output())),
        )
        for output in (
            inspect_output(revision="d" * 40),
            inspect_output(platform=("linux", "amd64")),
            inspect_output(development=False),
        ):
            with self.subTest(output=output), self.assertRaises(ValueError):
                MODULE.verify_image(tag, REVISION, "linux/arm64", runner(output))

    def test_append_record_writes_tab_separated_line(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            record = Path(temporary) / "nested" / "builds.tsv"
            now = datetime(2026, 11, 15, 1, 2, 3, tzinfo=timezone.utc)
            MODULE.append_record(
                record,
                "scrap-dev/x:main-aaaaaaa",
                REVISION,
                "linux/arm64",
                IMAGE_ID,
                now,
            )
            MODULE.append_record(
                record,
                "scrap-dev/y:main-aaaaaaa",
                REVISION,
                "linux/amd64",
                IMAGE_ID,
                now,
            )
            lines = record.read_text(encoding="utf-8").splitlines()
        self.assertEqual(2, len(lines))
        self.assertEqual(
            [
                "2026-11-15T01:02:03Z",
                "scrap-dev/x:main-aaaaaaa",
                REVISION,
                "linux/arm64",
                IMAGE_ID,
            ],
            lines[0].split("\t"),
        )

    def test_build_runs_steps_without_docker_and_records_result(self) -> None:
        calls: list[list[str]] = []

        def runner(command):
            calls.append(list(command))
            if "rev-parse" in command:
                return REVISION + "\n"
            if command[:3] == ["docker", "image", "inspect"]:
                return inspect_output()
            if command[:3] == ["docker", "buildx", "build"]:
                source = Path(command[command.index("--file") + 1]).parent
                self.assertTrue(source.exists())
            if command[:2] == ["git", "fetch"] or "fetch" in command:
                pass
            return ""

        original = MODULE.fetch_source

        def fake_fetch(repository, revision, destination, run=None):
            (destination / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
            original(repository, revision, destination, run)

        with tempfile.TemporaryDirectory() as temporary:
            record = Path(temporary) / "builds.tsv"
            MODULE.fetch_source = fake_fetch
            try:
                image_id = MODULE.build(
                    "repo",
                    "image",
                    REVISION,
                    "linux/arm64",
                    "Dockerfile",
                    ".",
                    record,
                    runner,
                )
            finally:
                MODULE.fetch_source = original
            self.assertEqual(IMAGE_ID, image_id)
            self.assertEqual(1, len(record.read_text(encoding="utf-8").splitlines()))
        self.assertTrue(
            any(command[:3] == ["docker", "buildx", "build"] for command in calls)
        )

    def test_main_rejects_branch_name_before_running_anything(self) -> None:
        self.assertEqual(
            1,
            MODULE.main(
                [
                    "--repository",
                    "repo",
                    "--image",
                    "image",
                    "--revision",
                    "main",
                    "--platform",
                    "linux/arm64",
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
