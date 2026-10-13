from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
REQUIREMENTS = REPOSITORY / "delivery" / "runtime-requirements.sh"


class RuntimeRequirementsTest(unittest.TestCase):
    def run_helper(
        self, command: str, *arguments: str, environment: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "bash",
                "-euo",
                "pipefail",
                "-c",
                '. "$1"; shift; "$@"',
                "runtime-check",
                str(REQUIREMENTS),
                command,
                *arguments,
            ],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_selects_literal_package_version_without_prefix_collisions(self) -> None:
        versions = [
            "5:29x8x0-1",
            "5:29.8.00-1",
            "5:129.8.0-1",
            "5:29.8.0~rc1-1",
            "5:29.8.0-1~ubuntu.24.04~noble",
            "5:29.8.0-0~ubuntu.24.04~noble",
        ]
        with tempfile.TemporaryDirectory() as temporary:
            fake_cache = Path(temporary) / "apt-cache"
            entries = [f"docker-ce | {version} | repository" for version in versions]
            fake_cache.write_text(
                "#!/usr/bin/env bash\nprintf '%s\\n' "
                + " ".join(shlex.quote(entry) for entry in entries)
                + "\n",
                encoding="utf-8",
            )
            fake_cache.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = f"{temporary}{os.pathsep}{environment['PATH']}"

            result = self.run_helper(
                "package_version", "docker-ce", "5:29.8.0", environment=environment
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("5:29.8.0-1~ubuntu.24.04~noble\n", result.stdout)
            result = self.run_helper(
                "package_version", "docker-ce", "5:29.9.0", environment=environment
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("required package version is unavailable", result.stderr)

    def source_state(
        self,
        sources: dict[str, str],
        *,
        uri: str = "https://download.docker.com/linux/ubuntu",
        suite: str = "noble",
        component: str = "stable",
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, bytes]]:
        with tempfile.TemporaryDirectory() as temporary:
            apt = Path(temporary)
            for relative, content in sources.items():
                path = apt / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            before = {
                str(path.relative_to(apt)): path.read_bytes()
                for path in apt.rglob("*")
                if path.is_file()
            }
            result = self.run_helper(
                "runtime_apt_source_state", str(apt), uri, suite, component, "amd64"
            )
            after = {
                str(path.relative_to(apt)): path.read_bytes()
                for path in apt.rglob("*")
                if path.is_file()
            }
            self.assertEqual(before, after)
            return result, after

    def test_absent_repository_does_not_change_existing_files(self) -> None:
        for sources in (
            {},
            {"sources.list": "deb https://example.invalid/debian stable main\n"},
        ):
            with self.subTest(sources=sources):
                result, _ = self.source_state(sources)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("absent\n", result.stdout)

    def test_existing_docker_deb822_source_is_reused_without_rewriting_its_key(
        self,
    ) -> None:
        source = (
            "Types: deb\nURIs: https://download.docker.com/linux/ubuntu\n"
            "Suites: noble\nComponents: stable\nArchitectures: amd64\n"
            "Signed-By: /etc/apt/keyrings/docker.asc\n"
        )
        for _ in range(2):
            result, unchanged = self.source_state(
                {"sources.list.d/docker.sources": source}
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("present\n", result.stdout)
            self.assertEqual(
                source.encode(), unchanged["sources.list.d/docker.sources"]
            )

    def test_existing_docker_list_sources_accept_current_architecture(self) -> None:
        for options in (
            "",
            "[arch=amd64] ",
            "[arch=amd64,arm64 signed-by=/etc/apt/keyrings/docker.gpg] ",
        ):
            with self.subTest(options=options):
                result, _ = self.source_state(
                    {
                        "sources.list.d/docker.list": f"deb {options}https://download.docker.com/linux/ubuntu noble stable\n"
                    }
                )
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("present\n", result.stdout)

    def test_duplicate_active_repository_sources_are_rejected_without_changes(
        self,
    ) -> None:
        result, _ = self.source_state(
            {
                "sources.list.d/docker.list": "deb [signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu noble stable\n",
                "sources.list.d/docker.sources": "Types: deb\nURIs: https://download.docker.com/linux/ubuntu\nSuites: noble\nComponents: stable\nSigned-By: /etc/apt/keyrings/docker.asc\n",
            }
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("duplicate or incompatible", result.stderr)

    def test_incompatible_repository_suite_component_and_architecture_are_rejected(
        self,
    ) -> None:
        for definition in (
            "deb https://download.docker.com/linux/ubuntu jammy stable\n",
            "deb https://download.docker.com/linux/ubuntu noble test\n",
            "deb [arch=arm64] https://download.docker.com/linux/ubuntu noble stable\n",
            "Types: deb\nURIs: https://download.docker.com/linux/ubuntu\nSuites: jammy\nComponents: stable\n",
            "Types: deb\nURIs: https://download.docker.com/linux/ubuntu\nSuites: noble\nComponents: stable\nArchitectures: arm64\n",
        ):
            with self.subTest(definition=definition):
                suffix = "sources" if definition.startswith("Types:") else "list"
                result, _ = self.source_state(
                    {f"sources.list.d/docker.{suffix}": definition}
                )
                self.assertNotEqual(0, result.returncode)

    def test_disabled_and_comment_only_sources_do_not_count_as_active(self) -> None:
        result, _ = self.source_state(
            {
                "sources.list": "# deb https://download.docker.com/linux/ubuntu noble stable\ndeb https://example.invalid/debian stable main #ignore https://download.docker.com/linux/ubuntu noble stable\n",
                "sources.list.d/docker.sources": "Types: deb\nURIs: https://download.docker.com/linux/ubuntu\nSuites: noble\nComponents: stable\nEnabled: no\n",
            }
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("absent\n", result.stdout)

    def test_source_only_repositories_are_rejected_before_a_binary_source_is_added(
        self,
    ) -> None:
        for sources in (
            {
                "sources.list.d/docker.list": "deb-src [signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable\n"
            },
            {
                "sources.list.d/docker.sources": "Types: deb-src\nURIs: https://download.docker.com/linux/ubuntu\nSuites: noble\nComponents: stable\nSigned-By: /etc/apt/keyrings/docker.asc\n"
            },
            {
                "sources.list.d/docker.list": "deb-src [signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable\n",
                "sources.list.d/additional.list": "deb [signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu noble stable\n",
            },
        ):
            with self.subTest(sources=sources):
                result, _ = self.source_state(sources)
                self.assertNotEqual(0, result.returncode)
                self.assertIn("duplicate or incompatible", result.stderr)

    def test_combined_binary_and_source_deb822_record_is_reused(self) -> None:
        result, _ = self.source_state(
            {
                "sources.list.d/docker.sources": "Types: deb deb-src\nURIs: https://download.docker.com/linux/ubuntu\nSuites: noble\nComponents: stable\nSigned-By: /etc/apt/keyrings/docker.asc\n",
            }
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("present\n", result.stdout)

    def test_smallstep_deb822_source_uses_the_same_read_only_preflight(self) -> None:
        result, _ = self.source_state(
            {
                "sources.list.d/smallstep.sources": "Types: deb\nURIs: https://packages.smallstep.com/stable/debian\nSuites: debs\nComponents: main\nSigned-By: /etc/apt/keyrings/smallstep.asc\n"
            },
            uri="https://packages.smallstep.com/stable/debian",
            suite="debs",
            component="main",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("present\n", result.stdout)

    def test_repository_preflight_precedes_any_apt_installation(self) -> None:
        installer = (REPOSITORY / "delivery/install-container-runtime").read_text()
        self.assertLess(
            installer.index("runtime_apt_source_state"),
            installer.index("apt-get update"),
        )

    def test_checks_minimum_supported_versions(self) -> None:
        for actual, expected_success in (
            ("3.9.20", False),
            ("3.10", True),
            ("3.10.21", True),
            ("3.13.15", True),
            ("", False),
        ):
            with self.subTest(actual=actual):
                result = self.run_helper(
                    "require_minimum_version", "Python", actual, "3.10"
                )
                self.assertEqual(expected_success, result.returncode == 0)

    def test_rejects_runtime_version_suffixes_and_other_versions(self) -> None:
        for actual in ("29.8.0", "29.8.1", "29.8.0-rc1", "v29.8.0", ""):
            with self.subTest(actual=actual):
                result = self.run_helper(
                    "require_exact_version", "Docker Engine", actual, "29.8.0"
                )
                self.assertEqual(actual == "29.8.0", result.returncode == 0)


if __name__ == "__main__":
    unittest.main()
