from __future__ import annotations

import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]


class RepositoryStructureTest(unittest.TestCase):
    def test_required_paths_exist(self) -> None:
        required_paths = [
            ".github/workflows/ci.yml",
            ".github/workflows/release.yml",
            "package-lock.json",
            "package.json",
            "delivery/apply-release",
            "delivery/install-container-runtime",
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
        ]
        missing = [path for path in required_paths if not (REPOSITORY / path).is_file()]
        self.assertEqual([], missing)

    def test_agent_instruction_symlink(self) -> None:
        agent_file = REPOSITORY / "AGENTS.md"
        self.assertTrue(agent_file.is_symlink())
        self.assertEqual(Path(".agents/AGENTS.md"), agent_file.readlink())

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
        self.assertIn("-o root -g scrap-admin -m 0640", readme)
        self.assertIn("sudo tests/validate-container", readme)
        self.assertIn("외부 의존성에는 각 저작권자가 정한 라이선스를 적용한다.", readme)


if __name__ == "__main__":
    unittest.main()
