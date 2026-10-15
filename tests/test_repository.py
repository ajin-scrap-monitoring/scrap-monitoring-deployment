from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]


class RepositoryStructureTest(unittest.TestCase):
    def test_required_paths_exist(self) -> None:
        required_paths = [
            ".markdownlint.json",
            ".github/workflows/ci.yml",
            ".github/workflows/release.yml",
            "package-lock.json",
            "package.json",
            "delivery/apply-release",
            "delivery/auth-secret-permissions.sh",
            "delivery/install-container-runtime",
            "delivery/install-environment",
            "delivery/dashboard_configuration.py",
            "delivery/edge_configuration.py",
            "delivery/validate-edge-configuration",
            "delivery/install-dashboard-configuration",
            "delivery/validate-dashboard-configuration",
            "delivery/runtime-requirements.sh",
            "delivery/quick-start",
            "delivery/release_applier.py",
            "delivery/generate-auth-secret",
            "delivery/install-auth-secret",
            "delivery/retire-auth-secret",
            "delivery/validate-auth-secrets",
            "delivery/validate-environment",
            "delivery/verify-release",
            "tests/test_delivery_release.py",
            "tests/test_delivery_integration.py",
            "tests/test_apply_release.py",
            "tests/test_pki.py",
            "tests/test_environment_installation.py",
            "tests/test_dashboard_configuration.py",
            "tests/test_runtime_requirements.py",
            "tests/test_markdown.mjs",
            "tests/test_auth_secret_permissions.py",
            "docs/configuration-management.md",
            "delivery/online/fetch-release",
            "delivery/release_verifier.py",
            "delivery/offline/bundle_importer.py",
            "delivery/offline/import-bundle",
            "docs/deployment-contract.md",
            "pki/config/ca.template.json",
            "pki/ensure-server-certificate",
            "pki/validate-ca-state",
            "pki/verify-server-certificate",
            "notices/README.md",
            "release/build-assets",
            "release/manifest.example.json",
            "release/manifest.schema.json",
            "release/package.schema.json",
            "release/manifests/README.md",
            "release/pull-images",
            "release/release_manifest.py",
            "release/target_validation.py",
            "release/validate-manifest",
            "release/validate-targets",
            "release/verify-assets",
            "requirements-tooling.in",
            "requirements-tooling.txt",
            "targets/edge/hardware/compose.yaml",
            "targets/edge/simulation/compose.yaml",
            "targets/server/hardware/compose.yaml",
            "targets/server/simulation/compose.yaml",
            "tests/validate-repository",
            "tests/validate-container",
            "Dockerfile.validation",
            "tests/validate-test-host",
            "tools/go.mod",
            "tools/go.sum",
            "tools/install-validation",
            "tools/lint-markdown.mjs",
            "tools/check-component-updates",
        ]
        missing = [path for path in required_paths if not (REPOSITORY / path).is_file()]
        self.assertEqual([], missing)

    def test_agent_instruction_symlink(self) -> None:
        agent_file = REPOSITORY / "AGENTS.md"
        self.assertTrue(agent_file.is_symlink())
        self.assertEqual(Path(".agents/AGENTS.md"), agent_file.readlink())

    def test_markdown_engine_is_fixed_without_pattern_expansion_dependencies(
        self,
    ) -> None:
        package = json.loads((REPOSITORY / "package.json").read_text(encoding="utf-8"))
        lock = json.loads(
            (REPOSITORY / "package-lock.json").read_text(encoding="utf-8")
        )
        self.assertEqual({"markdownlint": "0.41.1"}, package["devDependencies"])
        self.assertEqual(
            package["devDependencies"], lock["packages"][""]["devDependencies"]
        )
        self.assertEqual(
            "0.41.1", lock["packages"]["node_modules/markdownlint"]["version"]
        )
        for dependency in ("braces", "micromatch", "markdownlint-cli2"):
            with self.subTest(dependency=dependency):
                self.assertNotIn(f"node_modules/{dependency}", lock["packages"])

    def test_markdown_rules_keep_only_the_line_length_exception(self) -> None:
        config = json.loads(
            (REPOSITORY / ".markdownlint.json").read_text(encoding="utf-8")
        )
        self.assertEqual({"MD013": False}, config)

    def test_validation_runs_markdown_regressions_and_high_security_gate(self) -> None:
        validation = (REPOSITORY / "tests/validate-repository").read_text(
            encoding="utf-8"
        )
        self.assertIn("node tools/lint-markdown.mjs\n", validation)
        self.assertIn("node --test tests/test_markdown.mjs\n", validation)
        self.assertIn("npm audit --audit-level=high\n", validation)

    def test_readme_has_required_repository_sections(self) -> None:
        readme = (REPOSITORY / "README.md").read_text(encoding="utf-8")
        headings = [
            "# 스크랩 모니터링 배포",
            "## 주요 기능",
            "## 사전 조건",
            "## 설정",
            "## 빠른 시작",
            "## 개발 및 검증",
            "## 문서",
            "## 이용 조건",
        ]
        positions = [readme.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("install-container-runtime --target edge", readme)
        self.assertIn("install-container-runtime --target server", readme)
        self.assertIn("sudo delivery/install-environment --target edge", readme)
        self.assertIn("sudo delivery/install-environment --target server", readme)
        self.assertIn("sudo tests/validate-container", readme)
        self.assertIn("외부 의존성에는 각 저작권자가 정한 라이선스를 적용한다.", readme)

    def test_component_source_references_use_full_matching_commit_links(self) -> None:
        implementation = (REPOSITORY / "docs/implementation.md").read_text(
            encoding="utf-8"
        )
        expected = {
            "Simulator": "scrap-monitoring-simulator",
            "Edge Platform": "ajin-edge-platform",
            "Backend": "scrap-monitoring-backend",
            "Camera Media Service": "ajin-camera-media-service",
            "Dashboard": "scrap-monitoring-dashboard",
        }
        for component, repository in expected.items():
            with self.subTest(component=component):
                pattern = (
                    rf"^\| {re.escape(component)} \| \[([0-9a-f]{{40}})\]"
                    rf"\(https://github\.com/ajin-scrap-monitoring/"
                    rf"{re.escape(repository)}/tree/\1\) \|$"
                )
                self.assertEqual(
                    1, len(re.findall(pattern, implementation, re.MULTILINE))
                )


if __name__ == "__main__":
    unittest.main()
